"""Scenario-level XGBoost surrogate: predicts unmet-demand fraction for a multi-event disruption.

Distinct from core.risk_ml (node criticality).  This model takes a *scenario* (list of Events
applied to the current graph) and returns the predicted unmet-demand fraction over the simulation
horizon, together with SHAP feature attributions.

Training data generation
------------------------
For every generated network (seeds) and every sampled scenario (supplier failures, edge blocks,
demand spikes, combined) we run core.sim.simulate() and record:
    - scenario-level features (see SCENARIO_FEATURES)
    - label = unmet_frac over 30-day horizon

Feature schema (SCENARIO_FEATURES)
-----------------------------------
All features are derived from the graph and the event list *before* simulation.
They fall into four groups:

1. Disruption severity / duration
   event_count           number of events
   max_severity          worst single-event severity
   mean_severity         mean severity across events
   total_severity_days   sum(severity * duration) across events
   has_supplier_event    1 if any node event hits a supplier (0/1)
   has_edge_event        1 if any edge event (0/1)
   has_demand_event      1 if any demand event (0/1)

2. Structural importance of disrupted targets
   target_capacity_share      mean capacity_share_in_tier of disrupted non-customer nodes
   target_betweenness         mean betweenness of disrupted nodes
   target_alternate_paths     mean alternate_paths of disrupted nodes
   target_reliability         mean reliability of disrupted nodes
   target_stock_cover         mean stock_cover_days of disrupted non-customer nodes

3. Graph-level supply headroom
   supply_headroom            total supplier capacity / total customer demand
   backup_exists              1 if backup supplier present (0/1)
   n_spof_covered             fraction of top-5 SPOFs affected by events

4. Demand / inventory buffer
   customer_stock_cover_days  mean customer stock / daily demand across customers
   max_demand_spike           max demand multiplier applied (if demand event, else 1.0)

Label: unmet_frac = total_unmet / (horizon * total_daily_demand), clipped to [0, 1].
(Lower horizon leads = more stock buffer = smaller label for the same events.)

Model
-----
XGBRegressor, GroupShuffleSplit on (network_seed, scenario_id) to prevent leakage.
Persisted to MODEL_PATH; NOT retrained on every API request.
Pre-train:  python -m core.scenario_ml
"""
from __future__ import annotations

import itertools
import threading
import time
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd

from schemas import Event

# ---------------------------------------------------------------- constants
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "scenario_xgb.joblib"
MODEL_VERSION = 2
HORIZON = 30

SCENARIO_FEATURES = [
    # disruption characteristics
    "event_count",
    "max_severity",
    "mean_severity",
    "total_severity_days",
    "max_duration",
    "has_supplier_event",
    "has_edge_event",
    "has_demand_event",
    # structural importance of disrupted targets
    "target_capacity_share",
    "total_target_capacity_share",
    "supplier_capacity_lost_share",
    "target_betweenness",
    "target_alternate_paths",
    "target_reliability",
    "target_stock_cover",
    # graph-level headroom
    "supply_headroom",
    "backup_exists",
    "n_spof_covered",
    # inventory buffer
    "customer_stock_cover_days",
    "max_demand_spike",
]

_lock = threading.Lock()
_bundle: dict | None = None


# ---------------------------------------------------------------- feature extraction
def _node_features_cache(G: nx.DiGraph) -> dict[str, dict]:
    """Compute per-node structural features once (expensive operations: betweenness, alt-paths)."""
    from core.risk_ml import _alternate_paths, build_features

    X = build_features(G)
    return {n: X.loc[n].to_dict() for n in X.index}


def extract_features(G: nx.DiGraph, events: list[Event]) -> dict[str, float]:
    """Extract SCENARIO_FEATURES from (graph, events) without running the simulator.

    All values are finite floats.  Raises ValueError for empty event lists.
    """
    if not events:
        raise ValueError("events must not be empty")

    from core.chaos import failure_unmet, scan
    from core.risk_ml import _alternate_paths, build_features

    # ---- node features (betweenness, capacity_share, alt_paths, reliability, stock_cover)
    node_feat = {n: {} for n in G}
    try:
        X = build_features(G)
        for n in X.index:
            node_feat[n] = X.loc[n].to_dict()
    except Exception:
        pass  # degrade gracefully on exotic graphs

    # ---- basic event aggregations
    event_count = len(events)
    severities = [ev.severity for ev in events]
    durations = [ev.duration for ev in events]
    max_severity = max(severities)
    mean_severity = float(np.mean(severities))
    total_severity_days = float(sum(s * d for s, d in zip(severities, durations)))
    max_duration = float(max(durations)) if durations else 0.0

    node_events = [ev for ev in events if ev.type == "node"]
    edge_events = [ev for ev in events if ev.type == "edge"]
    demand_events = [ev for ev in events if ev.type == "demand"]

    has_supplier_event = 0.0
    target_nodes: list[str] = []
    for ev in node_events:
        if ev.target in G and G.nodes[ev.target]["kind"] == "supplier":
            has_supplier_event = 1.0
        if ev.target in G:
            target_nodes.append(ev.target)

    # edge events: add the source node as a proxy target
    for ev in edge_events:
        parts = ev.target.split("->")
        if len(parts) == 2 and parts[0].strip() in G:
            target_nodes.append(parts[0].strip())

    # ---- structural importance of disrupted targets
    def _mean_feat(feat: str, nodes: list[str], default: float = 0.0) -> float:
        vals = [node_feat.get(n, {}).get(feat, default) for n in nodes if n in node_feat]
        return float(np.mean(vals)) if vals else default

    non_customer_targets = [n for n in target_nodes if n in G and G.nodes[n]["kind"] != "customer"]

    target_capacity_share = _mean_feat("capacity_share_in_tier", non_customer_targets)
    total_target_capacity_share = float(
        sum(node_feat.get(n, {}).get("capacity_share_in_tier", 0.0) for n in set(non_customer_targets))
    )

    primary_suppliers = {
        n: d["capacity"] for n, d in G.nodes(data=True)
        if d.get("kind") == "supplier" and not d.get("backup")
    }
    total_primary_cap = sum(primary_suppliers.values()) or 1.0
    hit_suppliers = {ev.target for ev in node_events if ev.target in primary_suppliers}
    supplier_capacity_lost_share = float(
        sum(primary_suppliers[s] for s in hit_suppliers) / total_primary_cap
    )

    target_betweenness = _mean_feat("betweenness", target_nodes)
    target_alternate_paths = _mean_feat("alternate_paths", target_nodes)
    target_reliability = _mean_feat("reliability", target_nodes, default=1.0)
    target_stock_cover = _mean_feat("stock_cover_days", non_customer_targets)

    # ---- graph-level supply headroom
    total_supply = sum(
        d["capacity"] for _, d in G.nodes(data=True)
        if d["kind"] == "supplier" and not d.get("backup")
    )
    total_demand = sum(d["demand"] for _, d in G.nodes(data=True) if d["kind"] == "customer") or 1.0
    supply_headroom = total_supply / total_demand

    backup_exists = float(any(d.get("backup") for _, d in G.nodes(data=True)))

    # fraction of top-5 SPOFs covered by events
    n_spof_covered = 0.0
    try:
        chaos_scan = scan(G)
        top_spofs = sorted(chaos_scan["singles"].items(), key=lambda kv: -kv[1])[:5]
        affected = set(target_nodes) | {ev.target for ev in edge_events}
        covered = sum(1 for t, _ in top_spofs if t in affected)
        n_spof_covered = covered / max(len(top_spofs), 1)
    except Exception:
        n_spof_covered = 0.0

    # ---- demand / inventory buffer
    customers = [(n, d) for n, d in G.nodes(data=True) if d["kind"] == "customer"]
    customer_stock_cover_days = 0.0
    if customers:
        covers = [d["stock"] / d["demand"] for _, d in customers if d["demand"] > 0]
        customer_stock_cover_days = float(np.mean(covers)) if covers else 0.0

    max_demand_spike = 1.0
    if demand_events:
        max_demand_spike = max(1.0 + ev.severity for ev in demand_events)

    return {
        "event_count": float(event_count),
        "max_severity": float(max_severity),
        "mean_severity": float(mean_severity),
        "total_severity_days": float(total_severity_days),
        "max_duration": float(max_duration),
        "has_supplier_event": has_supplier_event,
        "has_edge_event": float(bool(edge_events)),
        "has_demand_event": float(bool(demand_events)),
        "target_capacity_share": target_capacity_share,
        "total_target_capacity_share": total_target_capacity_share,
        "supplier_capacity_lost_share": supplier_capacity_lost_share,
        "target_betweenness": target_betweenness,
        "target_alternate_paths": target_alternate_paths,
        "target_reliability": target_reliability,
        "target_stock_cover": target_stock_cover,
        "supply_headroom": float(supply_headroom),
        "backup_exists": backup_exists,
        "n_spof_covered": float(n_spof_covered),
        "customer_stock_cover_days": float(customer_stock_cover_days),
        "max_demand_spike": float(max_demand_spike),
    }


def features_to_df(feat: dict[str, float]) -> pd.DataFrame:
    """Single-row DataFrame with SCENARIO_FEATURES columns in the correct order."""
    missing = [f for f in SCENARIO_FEATURES if f not in feat]
    if missing:
        raise ValueError(f"Missing scenario features: {missing}")
    row = {f: feat[f] for f in SCENARIO_FEATURES}
    return pd.DataFrame([row], columns=SCENARIO_FEATURES)


# ---------------------------------------------------------------- dataset generation
def _sample_scenarios(G: nx.DiGraph, rng: np.random.Generator, n_per_seed: int = 60) -> list[list[Event]]:
    """Generate varied disruption scenario event-lists for a single graph."""
    nodes_by_kind: dict[str, list[str]] = {}
    for n, d in G.nodes(data=True):
        nodes_by_kind.setdefault(d["kind"], []).append(n)

    primary_suppliers = [n for n in nodes_by_kind.get("supplier", []) if not G.nodes[n].get("backup")]
    factories = nodes_by_kind.get("factory", [])
    warehouses = nodes_by_kind.get("warehouse", [])
    customers = nodes_by_kind.get("customer", [])
    edges = list(G.edges())

    scenarios: list[list[Event]] = []

    def make_node_ev(target: str, severity: float | None = None, duration: int | None = None) -> Event:
        sev = float(rng.uniform(0.5, 1.0)) if severity is None else severity
        dur = int(rng.integers(3, 20)) if duration is None else duration
        return Event(type="node", target=target, start=int(rng.integers(0, 5)), duration=dur, severity=sev)

    def make_edge_ev(u: str, v: str) -> Event:
        return Event(type="edge", target=f"{u}->{v}", start=int(rng.integers(0, 5)),
                     duration=int(rng.integers(3, 15)), severity=float(rng.uniform(0.6, 1.0)))

    def make_demand_ev(customer: str) -> Event:
        return Event(type="demand", target=customer, start=int(rng.integers(0, 5)),
                     duration=int(rng.integers(3, 12)), severity=float(rng.uniform(0.2, 0.8)))

    # 1. Single supplier failures (total outage)
    for sup in primary_suppliers:
        scenarios.append([make_node_ev(sup, severity=1.0, duration=int(rng.integers(5, 20)))])

    # 1b. Multi-supplier concurrent failures (pairs of suppliers)
    if len(primary_suppliers) >= 2:
        for s1, s2 in itertools.combinations(primary_suppliers, 2):
            dur = int(rng.integers(10, 30))
            scenarios.append([
                make_node_ev(s1, severity=float(rng.uniform(0.7, 1.0)), duration=dur),
                make_node_ev(s2, severity=float(rng.uniform(0.7, 1.0)), duration=dur),
            ])

    # 1c. Total or severe supply blackout (all suppliers down)
    if primary_suppliers:
        for dur in [15, 30]:
            scenarios.append([
                make_node_ev(s, severity=1.0, duration=dur)
                for s in primary_suppliers
            ])

    # 2. Single supplier partial disruptions
    for sup in primary_suppliers:
        scenarios.append([make_node_ev(sup)])

    # 3. Single factory failures
    for f in factories:
        scenarios.append([make_node_ev(f)])

    # 3b. Multi-factory concurrent failures (pairs of factories)
    if len(factories) >= 2:
        for f1, f2 in itertools.combinations(factories, 2):
            dur = int(rng.integers(10, 25))
            scenarios.append([
                make_node_ev(f1, severity=float(rng.uniform(0.7, 1.0)), duration=dur),
                make_node_ev(f2, severity=float(rng.uniform(0.7, 1.0)), duration=dur),
            ])

    # 3c. Extended single outages (full 25-30 days)
    for sup in primary_suppliers:
        scenarios.append([make_node_ev(sup, severity=1.0, duration=30)])
    for f in factories:
        scenarios.append([make_node_ev(f, severity=1.0, duration=30)])

    # 4. Single warehouse failures
    for w in warehouses:
        scenarios.append([make_node_ev(w)])

    # 5. Single edge blockages
    for u, v in edges[:min(len(edges), 8)]:
        if not G.nodes[u].get("backup"):
            scenarios.append([make_edge_ev(u, v)])

    # 6. Demand spikes
    for c in customers:
        scenarios.append([make_demand_ev(c)])

    # 7. Combined: supplier + demand spike
    for sup in primary_suppliers:
        if customers:
            c = customers[rng.integers(len(customers))]
            scenarios.append([make_node_ev(sup), make_demand_ev(c)])

    # 8. Combined: edge + warehouse
    if edges and warehouses:
        for _ in range(min(4, len(warehouses))):
            u, v = edges[rng.integers(len(edges))]
            w = warehouses[rng.integers(len(warehouses))]
            scenarios.append([make_edge_ev(u, v), make_node_ev(w)])

    # 9. Cascading: supplier -> warehouse -> edge
    if primary_suppliers and warehouses and edges:
        for _ in range(min(6, n_per_seed // 4)):
            sup = primary_suppliers[rng.integers(len(primary_suppliers))]
            w = warehouses[rng.integers(len(warehouses))]
            u, v = edges[rng.integers(len(edges))]
            scenarios.append([make_node_ev(sup, severity=1.0), make_node_ev(w), make_edge_ev(u, v)])

    # 10. Random single-event fill (to reach n_per_seed)
    all_targets = (
        [(n, "node") for n in primary_suppliers + factories + warehouses]
        + [(f"{u}->{v}", "edge") for u, v in edges if not G.nodes[u].get("backup")]
        + [(c, "demand") for c in customers]
    )
    while len(scenarios) < n_per_seed and all_targets:
        target, etype = all_targets[rng.integers(len(all_targets))]
        if etype == "node":
            scenarios.append([make_node_ev(target)])
        elif etype == "edge":
            parts = target.split("->")
            scenarios.append([make_edge_ev(parts[0], parts[1])])
        else:
            scenarios.append([make_demand_ev(target)])

    # deduplicate by repr
    seen: set[str] = set()
    unique: list[list[Event]] = []
    for sc in scenarios:
        key = repr(sorted(e.model_dump_json() for e in sc))
        if key not in seen:
            seen.add(key)
            unique.append(sc)
    return unique


def generate_dataset(
    seeds: range | list[int] | None = None,
    n_per_seed: int = 60,
    horizon: int = HORIZON,
) -> pd.DataFrame:
    """Generate a scenario-level training dataset.

    For every (seed, scenario) pair:
      - builds the graph from core.graph.build_network(seed)
      - extracts SCENARIO_FEATURES without simulation
      - runs simulate() to get the label (unmet_frac)
      - records seed and scenario_id for GroupShuffleSplit

    Returns a DataFrame with columns SCENARIO_FEATURES + ["label", "seed", "scenario_id"].
    Skips and logs failures; a minimum of 1 valid row is required.
    """
    import logging

    from core.graph import build_network
    from core.sim import simulate, unmet_frac

    if seeds is None:
        seeds = list(range(0, 31))  # 31 networks × ~60 scenarios ≈ 1 860 rows by default

    log = logging.getLogger("aegis.scenario_ml")
    rows: list[dict] = []
    scenario_counter = 0

    for seed in seeds:
        try:
            G = build_network(seed=seed)
        except RuntimeError as e:
            log.warning("seed %d: build_network failed: %s", seed, e)
            continue

        rng = np.random.default_rng(seed)
        scenarios = _sample_scenarios(G, rng, n_per_seed=n_per_seed)

        total_demand = sum(d["demand"] for _, d in G.nodes(data=True) if d["kind"] == "customer")
        if total_demand <= 0:
            continue

        for sc_id, events in enumerate(scenarios):
            scenario_counter += 1
            try:
                feat = extract_features(G, events)
                result = simulate(G, events, horizon=horizon)
                label = float(result["total_unmet"]) / (horizon * total_demand)
                label = min(1.0, max(0.0, label))
                row = {**feat, "label": label, "seed": seed, "scenario_id": f"{seed}_{sc_id}"}
                rows.append(row)
            except Exception as e:
                log.debug("seed %d scenario %d skipped: %s", seed, sc_id, e)
                continue

    if not rows:
        raise RuntimeError("Dataset generation produced no valid rows. Check the simulator.")

    df = pd.DataFrame(rows)
    log.info(
        "Dataset: %d scenarios across %d seeds -> %d valid rows (%.1f%% yield)",
        scenario_counter, len(list(seeds)), len(df),
        100 * len(df) / max(scenario_counter, 1),
    )
    return df


def save_dataset(df: pd.DataFrame, path: Path | None = None) -> Path:
    """Save the dataset to CSV and return the path."""
    if path is None:
        path = MODEL_PATH.parent / "scenario_dataset.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------- training
def train_scenario_model(
    seeds: range | list[int] | None = None,
    test_frac: float = 0.2,
    random_state: int = 42,
    save: bool = True,
    dataset: pd.DataFrame | None = None,
) -> dict:
    """Generate data (or accept pre-built DataFrame), fit XGBRegressor, evaluate, persist.

    Returns the model bundle (also stored in models/ directory).
    Raises RuntimeError if the dataset is too small (< 10 rows) or all labels are constant.
    """
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import GroupShuffleSplit
    from xgboost import XGBRegressor

    if dataset is None:
        dataset = generate_dataset(seeds=seeds)

    if len(dataset) < 10:
        raise RuntimeError(
            f"Dataset too small ({len(dataset)} rows). "
            "Increase seeds range or reduce test_frac."
        )

    # Validate columns
    missing = [c for c in SCENARIO_FEATURES + ["label", "seed"] if c not in dataset.columns]
    if missing:
        raise ValueError(f"Dataset missing columns: {missing}")

    # Remove NaN / Inf rows
    dataset = dataset.replace([np.inf, -np.inf], np.nan).dropna(subset=SCENARIO_FEATURES + ["label"])
    if len(dataset) < 10:
        raise RuntimeError("Too many invalid feature rows after cleaning.")

    # Group-aware train/test split by seed (no test network appears in training)
    split = GroupShuffleSplit(n_splits=1, test_size=test_frac, random_state=random_state)
    train_idx, test_idx = next(split.split(dataset, groups=dataset["seed"]))
    train = dataset.iloc[train_idx]
    test = dataset.iloc[test_idx]

    if len(test) < 3:
        # very small dataset: fall back to random split
        from sklearn.model_selection import train_test_split
        train, test = train_test_split(dataset, test_size=test_frac, random_state=random_state)

    # Baseline: mean of training labels
    baseline_pred = np.full(len(test), train["label"].mean())
    baseline_mae = float(mean_absolute_error(test["label"], baseline_pred))

    model = XGBRegressor(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=3,
        random_state=random_state,
        n_jobs=2,
        verbosity=0,
    )
    model.fit(train[SCENARIO_FEATURES], train["label"])

    # Evaluation on held-out test set
    pred = np.clip(model.predict(test[SCENARIO_FEATURES]), 0.0, 1.0)
    mae = float(mean_absolute_error(test["label"], pred))

    label_std = float(test["label"].std())
    if label_std < 1e-6:
        # Constant target: R² is undefined; set to 0.0 (not meaningful)
        r2 = 0.0
        r2_note = "constant target in test set; R² not meaningful"
    else:
        r2 = float(r2_score(test["label"], pred))
        r2_note = None

    # Feature importance (gain)
    gain = model.get_booster().get_score(importance_type="gain")
    total_gain = sum(gain.values()) or 1.0
    top_features = sorted(
        [{"feature": f, "importance": round(gain.get(f, 0.0) / total_gain, 4)} for f in SCENARIO_FEATURES],
        key=lambda x: -x["importance"],
    )[:8]

    bundle = {
        "version": MODEL_VERSION,
        "model": model,
        "features": SCENARIO_FEATURES,
        "metrics": {
            "target": "unmet_demand_fraction over 30-day horizon (from sim.simulate)",
            "mae": round(mae, 4),
            "r2": round(r2, 3),
            "baseline_mae": round(baseline_mae, 4),
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "top_features": top_features,
            **({"r2_note": r2_note} if r2_note else {}),
        },
    }

    if save:
        import joblib

        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, MODEL_PATH)

    return bundle


# ---------------------------------------------------------------- model loading
def load_model(retrain: bool = False) -> dict:
    """Load the persisted bundle (memoised in process); raise FileNotFoundError if missing.

    Set retrain=True only from the CLI / pre-train script; the API never retrains on-demand.
    """
    global _bundle
    with _lock:
        if _bundle is not None:
            return _bundle
        if MODEL_PATH.exists():
            import joblib

            try:
                cand = joblib.load(MODEL_PATH)
                if (
                    cand.get("version") == MODEL_VERSION
                    and cand.get("features") == SCENARIO_FEATURES
                ):
                    _bundle = cand
                    return _bundle
            except Exception:
                pass  # corrupt file -> fall through
        if retrain:
            _bundle = train_scenario_model()
            return _bundle
        raise FileNotFoundError(
            f"Scenario risk model not found at {MODEL_PATH}. "
            "Run: python -m core.scenario_ml  to train it."
        )


def model_status() -> dict:
    """Return {trained: bool, metrics: dict|None, path: str}."""
    try:
        bundle = load_model()
        return {"trained": True, "metrics": bundle["metrics"], "path": str(MODEL_PATH)}
    except FileNotFoundError:
        return {"trained": False, "metrics": None, "path": str(MODEL_PATH)}


def compute_risk_tier(
    unmet_fraction: float,
    total_daily_demand: float = 890.0,
    horizon: int = 30,
) -> tuple[int, str, float]:
    """Calculate calibrated risk_score (0-100), risk_level, and estimated unmet units.

    Calibrated against supply-chain operational impact:
      - Low risk (< 0.5% unmet demand): Absorbed by buffer/rerouting. OTIF > 99.5%. Score 0-29.
      - Moderate risk (0.5% - 2.5% unmet): Single supplier/lane outage, localized stockouts. Score 30-59.
      - High risk (2.5% - 7.0% unmet): Severe multi-node or cascade outage, multiple customer stockouts. Score 60-84.
      - Critical risk (>= 7.0% unmet): Catastrophic supply blackout, systemic failure. Score 85-100.
    """
    unmet_frac = max(0.0, min(1.0, float(unmet_fraction)))
    predicted_units = round(unmet_frac * horizon * total_daily_demand, 1)

    if unmet_frac < 0.005:
        score = int(round((unmet_frac / 0.005) * 29))
        level = "low"
    elif unmet_frac < 0.025:
        score = int(round(30 + ((unmet_frac - 0.005) / 0.020) * 29))
        level = "moderate"
    elif unmet_frac < 0.070:
        score = int(round(60 + ((unmet_frac - 0.025) / 0.045) * 24))
        level = "high"
    else:
        score = min(100, int(round(85 + ((unmet_frac - 0.070) / 0.150) * 15)))
        level = "critical"

    return max(0, min(100, score)), level, predicted_units


# ---------------------------------------------------------------- prediction
def predict(
    G: nx.DiGraph,
    events: list[Event],
    top_k: int = 5,
) -> dict:
    """Predict unmet_demand_fraction for a scenario.

    Returns:
        {
            "unmet_demand_fraction": float (0..1),
            "predicted_unmet_units": float,
            "risk_score": int (0..100),
            "risk_level": "low" | "moderate" | "high" | "critical",
            "confidence": "model" | "no_model",
            "top_factors": [{"feature": str, "impact": float}, ...],
            "model_metrics": {mae, r2, n_train, n_test},
        }

    If the model is not trained, raises FileNotFoundError (callers should handle gracefully).
    Feature extraction errors propagate as ValueError.
    """
    import shap

    bundle = load_model()
    feat = extract_features(G, events)
    X = features_to_df(feat)

    pred_raw = bundle["model"].predict(X)[0]
    pred = float(np.clip(pred_raw, 0.0, 1.0))

    # SHAP explanations
    explainer = shap.TreeExplainer(bundle["model"])
    shap_values = explainer.shap_values(X)  # shape: (1, n_features)
    sv = shap_values[0]  # 1-D array of length n_features

    order = np.argsort(-np.abs(sv))[:top_k]
    top_factors = [
        {"feature": SCENARIO_FEATURES[j], "impact": round(float(sv[j]), 5)}
        for j in order
    ]

    total_daily_demand = sum(
        d.get("demand", 0.0) for _, d in G.nodes(data=True) if d.get("kind") == "customer"
    ) or 890.0
    risk_score, risk_level, predicted_units = compute_risk_tier(
        pred, total_daily_demand=total_daily_demand, horizon=HORIZON
    )

    metrics = bundle["metrics"]
    return {
        "unmet_demand_fraction": round(pred, 4),
        "predicted_unmet_units": predicted_units,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "confidence": "model",
        "top_factors": top_factors,
        "model_metrics": {
            "mae": metrics["mae"],
            "r2": metrics["r2"],
            "n_train": metrics["n_train"],
            "n_test": metrics["n_test"],
        },
    }


# ---------------------------------------------------------------- CLI pre-train
if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("aegis.scenario_ml")

    t0 = time.perf_counter()
    log.info("Generating scenario dataset (seeds 0..30, ~60 scenarios each)...")
    df = generate_dataset()
    csv_path = save_dataset(df)
    log.info("Saved %d rows to %s", len(df), csv_path)

    log.info("Training XGBRegressor...")
    bundle = train_scenario_model(dataset=df, save=True)
    elapsed = time.perf_counter() - t0

    m = bundle["metrics"]
    print(f"\nTrained in {elapsed:.1f}s -> {MODEL_PATH}")
    print(f"  Dataset:  n_train={m['n_train']}  n_test={m['n_test']}")
    print(f"  MAE:      {m['mae']:.4f}  (baseline MAE: {m['baseline_mae']:.4f})")
    print(f"  R²:       {m['r2']:.3f}")
    print("  Top features:")
    for f in m["top_features"][:6]:
        print(f"    {f['feature']:<30} {f['importance']:.3f}")
