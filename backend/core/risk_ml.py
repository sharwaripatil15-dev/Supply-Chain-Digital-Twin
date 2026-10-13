"""Node criticality model (an ML surrogate of the flow engine) with SHAP explanations. Owner: D.

Training data: networks from core.graph.build_network(seed) for seeds 0..200. For every supplier, factory and
warehouse (demand nodes are excluded: a failed retailer/customer loses its own demand plus whatever it forwards, so
that is computed exactly by the flow engine, not learned):
    features  betweenness centrality, in/out degree, capacity share within its tier (demand share for customers),
              stock cover (stock / capacity, or stock / demand for customers, in days), alternate paths (node-disjoint
              supplier->customer paths that avoid the node), reliability, tier one-hot, backup flag
    label     unmet share of total demand if that node fails alone, with the backup available (the same metric as
              core.chaos singles), computed by the min-cost-flow engine
Model: XGBRegressor. Evaluated on a held-out 20% of *networks* (grouped by seed, so no test network is seen in
training): MAE and R^2. Speedup = engine time per label / model time per prediction.
Node "risk" in the API = the model's predicted share of demand lost if the node fails (its criticality); SHAP
TreeExplainer values say which features push that up or down.
The fitted model is persisted to MODEL_PATH and retrained automatically if missing or from an older version.
Small or degenerate networks (fewer than MIN_NODES_FOR_MODEL nodes, no supply-side node, no demand, no
supplier->demand path) get risk = None and a `risk_note` instead of a prediction; so does any model failure.
Pre-train with:  python -m core.risk_ml
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd

from node_types import KINDS, is_demand, total_demand

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "risk_xgb.joblib"
MODEL_VERSION = 3
TRAIN_SEEDS = range(0, 201)
TEST_SHARE = 0.2
MIN_NODES_FOR_MODEL = 4
FEATURES = [
    "betweenness", "in_degree", "out_degree", "capacity_share_in_tier", "stock_cover_days",
    "alternate_paths", "reliability", "is_supplier", "is_factory", "is_warehouse", "is_backup",
]

_lock = threading.Lock()
_bundle: dict | None = None


def _alternate_paths(G: nx.DiGraph) -> dict[str, int]:
    """Node-disjoint supplier->demand-node paths remaining when each node is removed."""
    H = G.copy()
    H.add_node("__SRC__")
    H.add_node("__SINK__")
    for n, d in G.nodes(data=True):
        if d["kind"] == "supplier":
            H.add_edge("__SRC__", n)
        elif is_demand(d["kind"]):
            H.add_edge(n, "__SINK__")
    out = {}
    for n in G:
        K = H.copy()
        K.remove_node(n)
        out[n] = nx.node_connectivity(K, "__SRC__", "__SINK__") if nx.has_path(K, "__SRC__", "__SINK__") else 0
    return out


def build_features(G: nx.DiGraph) -> pd.DataFrame:
    """One row per node (index = node id) with the FEATURES columns."""
    between = nx.betweenness_centrality(G)
    alt = _alternate_paths(G)
    size_of = lambda d: (d.get("demand") if is_demand(d["kind"]) else d.get("capacity")) or 0.0  # noqa: E731
    tier_total = {k: 0.0 for k in KINDS}
    for _, d in G.nodes(data=True):
        tier_total[d["kind"]] = tier_total.get(d["kind"], 0.0) + size_of(d)
    rows = {}
    for n, d in G.nodes(data=True):
        size = size_of(d)
        rows[n] = {
            "betweenness": between[n],
            "in_degree": G.in_degree(n),
            "out_degree": G.out_degree(n),
            "capacity_share_in_tier": size / tier_total[d["kind"]] if tier_total[d["kind"]] else 0.0,
            "stock_cover_days": d.get("stock", 0.0) / size if size else 0.0,
            "alternate_paths": alt[n],
            "reliability": d.get("reliability", 1.0),
            **{f"is_{k}": float(d["kind"] == k) for k in ("supplier", "factory", "warehouse")},
            "is_backup": float(bool(d.get("backup"))),
        }
    return pd.DataFrame.from_dict(rows, orient="index")[FEATURES]


def _labels(G: nx.DiGraph) -> dict[str, float]:
    from core.chaos import failure_unmet

    return {n: failure_unmet(G, (n,)) for n, d in G.nodes(data=True) if not is_demand(d["kind"])}


def generate_dataset(seeds=TRAIN_SEEDS) -> tuple[pd.DataFrame, float]:
    """Rows for every node of every generated network, plus mean engine seconds per label."""
    from core.graph import build_network

    frames, label_time, n_labels = [], 0.0, 0
    for seed in seeds:
        try:
            G = build_network(seed=seed)
        except RuntimeError:  # a seed whose generated network cannot meet baseline demand
            continue
        X = build_features(G)
        X = X[[not is_demand(G.nodes[n]["kind"]) for n in X.index]]
        t = time.perf_counter()
        y = _labels(G)
        label_time += time.perf_counter() - t
        n_labels += len(y)
        X["label"] = X.index.map(y)
        X["seed"] = seed
        frames.append(X)
    return pd.concat(frames), label_time / max(n_labels, 1)


def train_surrogate(seeds=TRAIN_SEEDS, test_frac: float = TEST_SHARE, seed: int = 7, save: bool = True) -> dict:
    """Generate data, fit XGBoost, evaluate on held-out networks, persist. Returns the model bundle."""
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import GroupShuffleSplit
    from xgboost import XGBRegressor

    data, label_seconds = generate_dataset(seeds)
    split = GroupShuffleSplit(n_splits=1, test_size=test_frac, random_state=seed)
    train_idx, test_idx = next(split.split(data, groups=data["seed"]))
    train, test = data.iloc[train_idx], data.iloc[test_idx]
    model = XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.05, subsample=0.9,
                         colsample_bytree=0.9, random_state=seed, n_jobs=2)
    model.fit(train[FEATURES], train["label"])
    t = time.perf_counter()
    pred = np.clip(model.predict(test[FEATURES]), 0, 1)
    predict_seconds = (time.perf_counter() - t) / len(test)
    gain = model.get_booster().get_score(importance_type="gain")
    total = sum(gain.values()) or 1.0
    bundle = {
        "version": MODEL_VERSION,
        "model": model,
        "features": FEATURES,
        "metrics": {
            "target": "share of demand lost if a single node fails (flow engine, backup available)",
            "mae": round(float(mean_absolute_error(test["label"], pred)), 4),
            "r2": round(float(r2_score(test["label"], pred)), 3),
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "speedup": round(label_seconds / predict_seconds, 1) if predict_seconds else 0.0,
            "top_features": sorted(({"feature": f, "importance": round(gain.get(f, 0.0) / total, 3)} for f in FEATURES),
                                   key=lambda x: -x["importance"])[:6],
        },
    }
    if save:
        import joblib

        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, MODEL_PATH)
    return bundle


def train_risk_model(**kwargs) -> Any:
    """Alias: the criticality model is the surrogate."""
    return train_surrogate(**kwargs)["model"]


def load_model(retrain: bool = True) -> dict:
    """Load the persisted bundle (memoised); train and save it first if missing or outdated."""
    global _bundle
    with _lock:
        if _bundle is not None:
            return _bundle
        if MODEL_PATH.exists():
            import joblib

            try:
                cand = joblib.load(MODEL_PATH)
                if cand.get("version") == MODEL_VERSION and cand.get("features") == FEATURES:
                    _bundle = cand
                    return _bundle
            except Exception:
                pass
        if not retrain:
            raise FileNotFoundError(f"no current model at {MODEL_PATH}")
        _bundle = train_surrogate()
        return _bundle


def surrogate_report() -> dict:
    """GET /surrogate shape: {target, mae, r2, n_train, n_test, speedup, top_features:[{feature, importance}]}."""
    return dict(load_model()["metrics"])


def model_unavailable_reason(G: nx.DiGraph) -> str | None:
    """Why the criticality model cannot score this network, or None when it can."""
    if G.number_of_nodes() < MIN_NODES_FOR_MODEL:
        return f"Network too small for the risk model (needs at least {MIN_NODES_FOR_MODEL} nodes)."
    if not any(not is_demand(d["kind"]) for _, d in G.nodes(data=True)):
        return "No supply-side sites to score."
    if total_demand(G) <= 0:
        return "No demand in the network, so there is nothing to lose."
    suppliers = [n for n, d in G.nodes(data=True) if d["kind"] == "supplier"]
    reach = set().union(*(nx.descendants(G, s) for s in suppliers)) if suppliers else set()
    if not any(is_demand(G.nodes[n]["kind"]) for n in reach):
        return "No supplier reaches a demand node, so criticality is undefined."
    return None


def _unscored(G: nx.DiGraph, note: str) -> dict[str, dict]:
    return {n: {"risk": None, "top_factors": [], "risk_note": note} for n in G}


def node_risk_with_shap(G: nx.DiGraph, top_k: int = 4) -> dict[str, dict]:
    """{node_id: {"risk": predicted share lost if it fails (0..1) or None, "top_factors": [{"feature", "impact"}],
    "risk_note": str | None}}. Never raises: unusable networks or model errors give risk None with a note."""
    reason = model_unavailable_reason(G)
    if reason:
        return _unscored(G, reason)
    try:
        return _score(G, top_k)
    except Exception as exc:  # the model is a nice-to-have; the twin must still render
        return _unscored(G, f"Risk model unavailable: {exc}")


def _score(G: nx.DiGraph, top_k: int) -> dict[str, dict]:
    import shap
    import shap.explainers._tree as _st

    if hasattr(_st, "decode_ubjson_buffer") and not getattr(_st, "_aegis_patched", False):
        _orig_decode = _st.decode_ubjson_buffer

        def _safe_decode(fd):
            res = _orig_decode(fd)
            try:
                lmp = res.get("learner", {}).get("learner_model_param", {})
                if "base_score" in lmp:
                    bs = lmp["base_score"]
                    if isinstance(bs, str) and bs.startswith("["):
                        lmp["base_score"] = bs.strip("[]")
            except Exception:
                pass
            return res

        _st.decode_ubjson_buffer = _safe_decode
        _st._aegis_patched = True

    from core.chaos import failure_loss

    bundle = load_model()
    X = build_features(G)
    total = total_demand(G) or 1.0
    out = {}
    for n, d in G.nodes(data=True):  # a failed demand node loses its own demand (+ what it forwards): no model needed
        if is_demand(d["kind"]):
            if G.out_degree(n):  # a retailer that also feeds customers: let the flow engine measure it
                share = failure_loss(G, (n,))
                out[n] = {"risk": round(share, 3), "top_factors": [{"feature": "demand_lost_incl_downstream", "impact": round(share, 4)}]}
            else:
                share = (d.get("demand") or 0.0) / total
                out[n] = {"risk": round(share, 3), "top_factors": [{"feature": "own_demand_share", "impact": round(share, 4)}]}
    X = X[[not is_demand(G.nodes[n]["kind"]) for n in X.index]]
    if X.empty:
        return out
    pred = np.clip(bundle["model"].predict(X), 0, 1)
    values = shap.TreeExplainer(bundle["model"]).shap_values(X)
    for i, n in enumerate(X.index):
        order = np.argsort(-np.abs(values[i]))[:top_k]
        out[n] = {
            "risk": round(float(pred[i]), 3),
            "top_factors": [{"feature": FEATURES[j], "impact": round(float(values[i][j]), 4)} for j in order],
        }
    return out


def _load_risk_thresholds() -> tuple[float, float]:
    import json
    assumptions_path = Path(__file__).resolve().parent.parent / "config" / "assumptions.json"
    if assumptions_path.exists():
        try:
            with open(assumptions_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                rt = data.get("risk_thresholds", {})
                return float(rt.get("high_risk_unmet_share", 0.35)), float(rt.get("moderate_risk_unmet_share", 0.10))
        except Exception:
            pass
    return 0.35, 0.10


def scenario_quick_risk(G: nx.DiGraph, events: Iterable[Any]) -> Any | None:
    """Predict instantaneous scenario risk using the trained XGBoost surrogate and SHAP TreeExplainer."""
    from schemas import QuickRiskEstimate, QuickRiskFactor

    events = list(events)
    if not events:
        return None
    t0 = time.perf_counter()
    try:
        node_scores = node_risk_with_shap(G, top_k=3)
    except Exception:
        return None

    high_thresh, mod_thresh = _load_risk_thresholds()

    # Collect affected nodes
    disrupted_nodes = []
    for ev in events:
        target = getattr(ev, "target", "")
        ev_type = getattr(ev, "type", "")
        if ev_type in ("edge", "route_block"):
            parts = target.split("->")
            if len(parts) == 2:
                disrupted_nodes.append(parts[1].strip())
        else:
            disrupted_nodes.append(target)

    valid_scores = [
        node_scores.get(n) for n in disrupted_nodes if n in node_scores and node_scores.get(n, {}).get("risk") is not None
    ]
    if not valid_scores:
        return None

    # Estimate combined unmet share: 1 - prod(1 - r_i)
    combined_risk = 1.0
    for s in valid_scores:
        r = s.get("risk", 0.0) or 0.0
        combined_risk *= (1.0 - r)
    pred_unmet = round(float(np.clip(1.0 - combined_risk, 0.0, 1.0)), 3)

    if pred_unmet >= high_thresh:
        level = "High"
    elif pred_unmet >= mod_thresh:
        level = "Moderate"
    else:
        level = "Low"

    # Aggregate top SHAP factors across the affected nodes
    factor_map: dict[str, float] = {}
    for s in valid_scores:
        for f in s.get("top_factors", []):
            feat = f["feature"]
            impact = f["impact"]
            factor_map[feat] = factor_map.get(feat, 0.0) + impact

    top_factors = [
        QuickRiskFactor(feature=feat, impact=round(imp, 4))
        for feat, imp in sorted(factor_map.items(), key=lambda x: -abs(x[1]))[:3]
    ]

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    return QuickRiskEstimate(
        risk_level=level,
        predicted_unmet_share=pred_unmet,
        top_factors=top_factors,
        label="estimate",
        latency_ms=elapsed_ms,
    )


def surrogate_compare(predicted_unmet: float, actual_unmet_share: float) -> Any:
    """Compare the pre-simulation surrogate estimate with actual LP simulation results."""
    from schemas import SurrogateComparison

    high_thresh, mod_thresh = _load_risk_thresholds()
    if predicted_unmet >= high_thresh:
        level = "High"
    elif predicted_unmet >= mod_thresh:
        level = "Moderate"
    else:
        level = "Low"

    error = round(abs(predicted_unmet - actual_unmet_share), 4)
    return SurrogateComparison(
        predicted_risk_level=level,
        predicted_unmet_share=round(predicted_unmet, 3),
        actual_unmet_share=round(actual_unmet_share, 3),
        absolute_error=error,
        label="Surrogate vs Simulated LP comparison",
    )


if __name__ == "__main__":
    t0 = time.perf_counter()
    b = train_surrogate()
    print(f"trained in {time.perf_counter() - t0:.1f}s -> {MODEL_PATH}")
    print({k: v for k, v in b["metrics"].items() if k != "top_features"})
    for f in b["metrics"]["top_features"]:
        print(f"  {f['feature']:<24} {f['importance']:.3f}")
