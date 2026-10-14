"""ML surrogates of the engine, with SHAP explanations. Owner: D.

Two models live here:
  1. Node criticality (below, unchanged): share of demand lost if one node fails, used for node "risk" in GET /network.
  2. Scenario surrogate (section 2 further down): predicts the outcomes of a whole disruption scenario (unmet %,
     avg delay, stock-out day, recovery days) with 80% intervals, trained on the synthetic dataset (core.synth.build)
     labelled by the exact simulator. It pre-screens scenarios (Chaos Finder, what-if preview); the exact simulator
     stays the source of truth for every number the UI displays.

--- 1. Node criticality ---

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

import json
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


# ================================================================ 2. scenario surrogate
"""Scenario surrogate (multi-output gradient boosting).

Data      data/synth/dataset.parquet (core.synth.build): one row per (network, disruption), labels from core.sim.simulate,
          features core.features.SCENARIO_FEATURES. Splits are by network: train 60% / val 10% / calib 10% / test 20%.
Targets   unmet_pct (% of horizon demand), avg_delay (days), stockout_day (day of first stock-out, 30 = none),
          recovery_days (days from disruption start to the last day with unmet demand).
Model     one XGBoost regressor per target (squared error), hyper-parameters by randomized search (N_ITER draws scored
          on the validation networks) with early stopping on the same networks, monotonic constraints where the
          physics is one-directional (MONOTONE: more severity / duration / lost capacity never helps; more stock
          cover never hurts). Intervals: conformalized quantile regression - an XGBoost multi-quantile model
          (P10/P50/P90) is widened by the calibration-network conformity score so the 80% band has finite-sample
          coverage; empirical coverage on the test networks is reported.
Baselines mean predictor (train mean) and a centrality heuristic: y ~ a + b * h with h = (betweenness_max + pagerank_max)
          x severity_max x duration / horizon, fitted on train. Metrics on held-out networks: MAE, RMSE, R2, Spearman,
          top-10 recall (per test network, share of the model's 10 worst-ranked scenarios that are truly among the
          worst 10; ties at the 10th value count as hits), interval coverage and width, residuals, per-archetype and
          per-disruption MAE, inference time and speedup vs the exact simulator.
Artifacts models/scenario_surrogate_v{SCENARIO_MODEL_VERSION}.joblib + models/metrics.json. If missing, a fast model
          is trained automatically (core.synth.build --fast data); if that fails every caller degrades gracefully.
Train     python -m core.risk_ml --scenario          (needs data/synth/dataset.parquet; --fast for the small set)
Optional stretch (not in the default requirements): a GNN over the network graph could replace the hand-built
          graph features; it is deliberately not implemented here.
"""
SCENARIO_MODEL_VERSION = 1
SCENARIO_TARGETS = ["unmet_pct", "avg_delay", "stockout_day", "recovery_days"]
METRICS_PATH = MODEL_PATH.parent / "metrics.json"
HORIZON = 30
TARGET_INFO = {  # label, unit, higher is worse, valid range
    "unmet_pct": ("unmet demand", "% of demand", True, (0.0, 100.0)),
    "avg_delay": ("average extra delay", "days", True, (0.0, 60.0)),
    "stockout_day": ("first stock-out day", "day", False, (0.0, float(HORIZON))),
    "recovery_days": ("recovery time", "days", True, (0.0, float(HORIZON))),
}
_WORSE = {"severity_max": 1, "duration": 1, "capacity_lost_share": 1, "loss_max": 1, "downstream_cover_min": -1}
MONOTONE = {
    "unmet_pct": _WORSE,
    "recovery_days": _WORSE,
    "stockout_day": {k: -v for k, v in _WORSE.items()},
    "avg_delay": {},
}
N_ITER = {"full": 12, "fast": 3}
PARAM_SPACE = {
    "max_depth": [3, 4, 5, 6, 7, 8], "learning_rate": [0.03, 0.05, 0.08, 0.12], "min_child_weight": [1, 3, 5, 10],
    "subsample": [0.7, 0.8, 0.9, 1.0], "colsample_bytree": [0.6, 0.75, 0.9, 1.0], "reg_lambda": [0.5, 1.0, 2.0, 5.0],
}
INTERVAL = 0.8

_scenario_lock = threading.Lock()
_scenario_bundle: dict | None = None
_scenario_error: str | None = None


def scenario_model_path(version: int = SCENARIO_MODEL_VERSION) -> Path:
    return MODEL_PATH.parent / f"scenario_surrogate_v{version}.joblib"


def centrality_heuristic(X: pd.DataFrame) -> np.ndarray:
    return ((X["betweenness_max"] + X["pagerank_max"]) * X["severity_max"] * X["duration"] / HORIZON).to_numpy()


def _spearman(a, b) -> float:
    from scipy.stats import spearmanr

    if np.ptp(a) == 0 or np.ptp(b) == 0:
        return 0.0
    return float(spearmanr(a, b).statistic)


def _top_recall(df: pd.DataFrame, y: np.ndarray, pred: np.ndarray, worse_high: bool, k: int = 10) -> float:
    """Mean over networks of: share of the model's top-k (worst) scenarios that are truly in the worst k (tie-aware)."""
    sign = 1 if worse_high else -1
    out = []
    for _, idx in df.groupby("network_id").indices.items():
        if len(idx) < 2 * k:
            continue
        yt, yp = sign * y[idx], sign * pred[idx]
        cutoff = np.sort(yt)[-k]
        out.append(float(np.mean(yt[np.argsort(-yp, kind="stable")[:k]] >= cutoff)))
    return round(float(np.mean(out)), 3) if out else 0.0


def _metrics(df: pd.DataFrame, y: np.ndarray, pred: np.ndarray, worse_high: bool) -> dict:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    return {
        "mae": round(float(mean_absolute_error(y, pred)), 4),
        "rmse": round(float(np.sqrt(mean_squared_error(y, pred))), 4),
        "r2": round(float(r2_score(y, pred)), 4),
        "spearman": round(_spearman(y, pred), 4),
        "top10_recall": _top_recall(df, y, pred, worse_high),
    }


def _xgb(params: dict, target: str, n_estimators: int, seed: int, quantile: bool = False):
    from xgboost import XGBRegressor

    extra = {"objective": "reg:quantileerror", "quantile_alpha": np.array([0.1, 0.5, 0.9])} if quantile else {}
    return XGBRegressor(n_estimators=n_estimators, early_stopping_rounds=50, tree_method="hist", random_state=seed,
                        n_jobs=4, monotone_constraints=MONOTONE[target] or None, **params, **extra)


def train_scenario_surrogate(df: pd.DataFrame | None = None, fast: bool = False, seed: int = 42, save: bool = True,
                             verbose: bool = False) -> dict:
    """Tune, fit, calibrate and evaluate the scenario surrogate. Returns the bundle (metrics under "metrics")."""
    from core.features import SCENARIO_FEATURES

    if df is None:
        from core.synth.build import load_dataset

        df = load_dataset(fast)
        if df is None:
            raise FileNotFoundError("no synthetic dataset: run python -m core.synth.build" + (" --fast" if fast else ""))
    mode = "fast" if fast else "full"
    rng = np.random.default_rng(seed)
    part = {k: df[df["split"] == k].reset_index(drop=True) for k in ("train", "val", "calib", "test")}
    X = {k: v[SCENARIO_FEATURES].astype(float) for k, v in part.items()}
    n_est = 400 if fast else 2000
    models, quantile, qhat, report = {}, {}, {}, {}
    draws = [{k: v[int(rng.integers(len(v)))] for k, v in PARAM_SPACE.items()} for _ in range(N_ITER[mode])]
    for target in SCENARIO_TARGETS:
        label, unit, worse_high, (lo_v, hi_v) = TARGET_INFO[target]
        y = {k: v[target].to_numpy(dtype=float) for k, v in part.items()}
        best = None
        for params in draws:
            m = _xgb(params, target, n_est, seed)
            m.fit(X["train"], y["train"], eval_set=[(X["val"], y["val"])], verbose=False)
            mae = float(np.mean(np.abs(np.clip(m.predict(X["val"]), lo_v, hi_v) - y["val"])))
            if best is None or mae < best[0]:
                best = (mae, params, m)
        val_mae, params, model = best
        qm = _xgb(params, target, n_est, seed, quantile=True)
        qm.fit(X["train"], y["train"], eval_set=[(X["val"], y["val"])], verbose=False)
        qc = qm.predict(X["calib"])
        scores = np.maximum(qc[:, 0] - y["calib"], y["calib"] - qc[:, 2])
        n = len(scores)
        level = min(1.0, np.ceil((n + 1) * INTERVAL) / n)
        q = float(np.quantile(scores, level, method="higher"))
        pred = np.clip(model.predict(X["test"]), lo_v, hi_v)
        qt = qm.predict(X["test"])
        lo = np.minimum(np.clip(qt[:, 0] - q, lo_v, hi_v), pred)
        hi = np.maximum(np.clip(qt[:, 2] + q, lo_v, hi_v), pred)
        # baselines (fitted on train only)
        mean_pred = np.full_like(y["test"], y["train"].mean())
        h_train, h_test = centrality_heuristic(X["train"]), centrality_heuristic(X["test"])
        b, a = np.polyfit(h_train, y["train"], 1) if np.std(h_train) > 0 else (0.0, y["train"].mean())
        heur_pred = np.clip(a + b * h_test, lo_v, hi_v)
        resid = pred - y["test"]
        test = part["test"]

        def breakdown(col: str) -> dict:
            return {str(g): {"mae": round(float(np.mean(np.abs(resid[idx]))), 4),
                             "mae_mean_baseline": round(float(np.mean(np.abs(mean_pred[idx] - y["test"][idx]))), 4),
                             "n": int(len(idx))}
                    for g, idx in test.groupby(col).indices.items()}

        gain = model.get_booster().get_score(importance_type="gain")
        tot = sum(gain.values()) or 1.0
        report[target] = {
            "label": label, "unit": unit, "best_params": params, "best_iteration": int(model.best_iteration),
            "val_mae": round(val_mae, 4),
            "model": {**_metrics(test, y["test"], pred, worse_high),
                      "interval_coverage": round(float(np.mean((y["test"] >= lo) & (y["test"] <= hi))), 4),
                      "interval_width": round(float(np.mean(hi - lo)), 4)},
            "baseline_mean": _metrics(test, y["test"], mean_pred, worse_high),
            "baseline_centrality": _metrics(test, y["test"], heur_pred, worse_high),
            "residuals": {"mean": round(float(resid.mean()), 4), "std": round(float(resid.std()), 4),
                          **{f"p{p}": round(float(np.percentile(resid, p)), 4) for p in (5, 50, 95)}},
            "by_archetype": breakdown("archetype"), "by_disruption": breakdown("disruption"),
            "top_features": sorted(({"feature": f, "importance": round(gain.get(f, 0.0) / tot, 4)} for f in SCENARIO_FEATURES),
                                   key=lambda r: -r["importance"])[:10],
            "monotone": MONOTONE[target],
        }
        models[target], quantile[target], qhat[target] = model, qm, q
        if verbose:
            r = report[target]
            print(f"{target:14s} MAE {r['model']['mae']:.3f} (mean {r['baseline_mean']['mae']:.3f}, centrality "
                  f"{r['baseline_centrality']['mae']:.3f})  R2 {r['model']['r2']:.3f}  rho {r['model']['spearman']:.3f}  "
                  f"top10 {r['model']['top10_recall']:.2f}  cov {r['model']['interval_coverage']:.2f}")
    bundle = {"version": SCENARIO_MODEL_VERSION, "features": SCENARIO_FEATURES, "targets": SCENARIO_TARGETS,
              "models": models, "quantile": quantile, "qhat": qhat, "mode": mode}
    # inference time (model only): a 2,000-scenario batch and single scenarios, vs the exact simulator per case
    Xb = pd.concat([X["test"]] * (2000 // max(1, len(X["test"])) + 1)).iloc[:2000]
    t = time.perf_counter()
    _predict_frame(bundle, Xb)
    batch_ms = (time.perf_counter() - t) * 1000 / len(Xb)
    t = time.perf_counter()
    for i in range(20):
        _predict_frame(bundle, X["test"].iloc[[i % len(X["test"])]])
    single_ms = (time.perf_counter() - t) * 1000 / 20
    sim_ms = float(df["sim_ms"].mean())
    feat_ms = 0.25  # core.features.scenario_features per scenario (measured; the network context is computed once)
    bundle["metrics"] = {
        "version": SCENARIO_MODEL_VERSION, "mode": mode, "artifact": scenario_model_path().name,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dataset": {"rows": int(len(df)), "networks": int(df["network_id"].nunique()),
                    **{f"{k}_networks": int(v["network_id"].nunique()) for k, v in part.items()},
                    **{f"{k}_rows": int(len(v)) for k, v in part.items()}},
        "targets": report,
        "interval": {"level": INTERVAL, "method": "conformalized quantile regression (XGBoost P10/P90 + calibration networks)",
                     "qhat": {t: round(v, 4) for t, v in qhat.items()}},
        "timing": {"inference_ms_per_scenario_batch": round(batch_ms, 4), "inference_ms_single": round(single_ms, 3),
                   "features_ms_per_scenario": feat_ms, "exact_sim_ms_per_scenario": round(sim_ms, 2),
                   "speedup_batch": round(sim_ms / (batch_ms + feat_ms), 1)},
        "note": "Labels come from the AEGIS simulator, so this is a fast surrogate validated on held-out synthetic "
                "networks, not on real-world outcomes.",
    }
    if save:
        import joblib

        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, scenario_model_path())
        METRICS_PATH.write_text(json.dumps(bundle["metrics"], indent=1), encoding="utf-8")
    return bundle


def _booster(model):
    return model.get_booster()


def _best(model) -> tuple[int, int]:
    """Trees up to the early-stopping best iteration (what XGBRegressor.predict uses)."""
    return (0, int(model.best_iteration) + 1)


def _predict_frame(bundle: dict, X: pd.DataFrame) -> dict[str, np.ndarray]:
    """{target: array (n, 3) of [low, point, high]} for a feature frame."""
    out = {}
    A = np.ascontiguousarray(X[bundle["features"]].to_numpy(dtype=np.float32))
    for t in bundle["targets"]:
        lo_v, hi_v = TARGET_INFO[t][3]
        # booster.inplace_predict skips the sklearn wrapper's DMatrix build (~10 ms per call on one row)
        point = np.clip(_booster(bundle["models"][t]).inplace_predict(A, iteration_range=_best(bundle["models"][t])), lo_v, hi_v)
        q = np.asarray(_booster(bundle["quantile"][t]).inplace_predict(A, iteration_range=_best(bundle["quantile"][t]))).reshape(len(A), -1)
        lo = np.minimum(np.clip(q[:, 0] - bundle["qhat"][t], lo_v, hi_v), point)
        hi = np.maximum(np.clip(q[:, 2] + bundle["qhat"][t], lo_v, hi_v), point)
        out[t] = np.stack([lo, point, hi], axis=1)
    return out


def load_scenario_model(auto_train: bool = True) -> dict | None:
    """The current scenario surrogate bundle (memoised). Missing -> train a fast one (if allowed); failure -> None."""
    global _scenario_bundle, _scenario_error
    with _scenario_lock:
        if _scenario_bundle is not None:
            return _scenario_bundle
        path = scenario_model_path()
        try:
            import joblib

            from core.features import SCENARIO_FEATURES

            if path.exists():
                cand = joblib.load(path)
                if cand.get("version") == SCENARIO_MODEL_VERSION and cand.get("features") == SCENARIO_FEATURES:
                    _scenario_bundle = cand
                    return cand
            if not auto_train:
                _scenario_error = f"no current scenario model at models/{path.name}"
                return None
            from core.synth.build import build, load_dataset

            df = load_dataset(fast=True)
            if df is None:
                df = build(42, 20, seed=42, fast=True, verbose=False)
            _scenario_bundle = train_scenario_surrogate(df, fast=True)
            return _scenario_bundle
        except Exception as exc:  # the surrogate is optional: callers fall back to the exact engine
            _scenario_error = f"{type(exc).__name__}: {exc}"
            return None


def scenario_model_status() -> dict:
    b = load_scenario_model(auto_train=False)
    return {"available": b is not None, "version": SCENARIO_MODEL_VERSION, "mode": (b or {}).get("mode"),
            "error": None if b is not None else _scenario_error}


def scenario_metrics() -> dict | None:
    """models/metrics.json (written at training time), or None."""
    if METRICS_PATH.exists():
        try:
            return json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    b = load_scenario_model(auto_train=False)
    return b["metrics"] if b else None


def predict_scenarios(G: nx.DiGraph, scenarios: list, dtypes: list | None = None, horizon: int = HORIZON) -> list[dict] | None:
    """Surrogate predictions for several event lists on one network: [{target: {low, point, high}}]. None if no model."""
    from core.features import context, feature_frame, scenario_features

    bundle = load_scenario_model()
    if bundle is None or not scenarios:
        return None
    ctx = context(G)
    dtypes = dtypes or [None] * len(scenarios)
    X = feature_frame([scenario_features(ctx, ev, dtypes[i], horizon) for i, ev in enumerate(scenarios)])
    pred = _predict_frame(bundle, X)
    return [{t: {"low": round(float(pred[t][i, 0]), 3), "point": round(float(pred[t][i, 1]), 3),
                 "high": round(float(pred[t][i, 2]), 3)} for t in bundle["targets"]} for i in range(len(X))]


FEATURE_TEXT = {  # feature -> (plain-English name, formatter)
    "capacity_lost_share": ("capacity knocked out", lambda v: f"{v:.0%} of daily flow"),
    "loss_max": ("worst single-target loss", lambda v: f"{v:.0%} of demand"),
    "loss_sum": ("combined target loss", lambda v: f"{v:.0%} of demand"),
    "severity_max": ("severity", lambda v: f"{v:.0%}"),
    "severity_mean": ("average severity", lambda v: f"{v:.0%}"),
    "duration": ("duration", lambda v: f"{v:.0f} days"),
    "start": ("start day", lambda v: f"day {v:.0f}"),
    "start_frac": ("timing in the horizon", lambda v: f"{v:.0%} in"),
    "downstream_cover_min": ("stock cover downstream", lambda v: f"{v:.1f} days"),
    "cover_minus_duration": ("stock cover minus outage length", lambda v: f"{v:+.1f} days"),
    "cover_over_duration": ("stock cover / outage length", lambda v: f"{v:.2f}x"),
    "alt_paths_min": ("alternate paths around the target", lambda v: f"{v:.0f}"),
    "extra_lead_alt_max": ("extra lead time on the best detour", lambda v: f"{v:.1f} days"),
    "articulation_any": ("single point of failure hit", lambda v: "yes" if v >= 0.5 else "no"),
    "downstream_demand_max": ("demand downstream of the target", lambda v: f"{v:.0%}"),
    "target_util_max": ("target utilisation", lambda v: f"{v:.0%}"),
    "target_headroom_min": ("spare capacity at the target", lambda v: f"{v:.0%} of demand"),
    "demand_up_share": ("demand surge", lambda v: f"+{v:.0%} of total demand"),
    "demand_down_share": ("demand drop", lambda v: f"-{v:.0%} of total demand"),
    "lead_mult_max": ("lead-time multiplier", lambda v: f"x{v:.1f}"),
    "lead_inflation_share": ("flow-weighted lead-time inflation", lambda v: f"{v:.2f}"),
    "supplier_hhi": ("supplier concentration (HHI)", lambda v: f"{v:.2f}"),
    "backup_share": ("backup capacity", lambda v: f"{v:.0%} of demand"),
    "mean_util": ("network utilisation", lambda v: f"{v:.0%}"),
    "mean_cover_days": ("average stock cover", lambda v: f"{v:.1f} days"),
    "min_cover_vs_lead": ("thinnest cover vs lead time", lambda v: f"{v:.2f}x"),
    "betweenness_max": ("target betweenness", lambda v: f"{v:.2f}"),
    "pagerank_max": ("target PageRank", lambda v: f"{v:.3f}"),
    "regional_correlation": ("regional correlation", lambda v: f"{v:.0%}"),
    "n_events": ("number of events", lambda v: f"{v:.0f}"),
    "mean_lead": ("average lane lead time", lambda v: f"{v:.1f} days"),
}


def _feature_phrase(f: str, v: float) -> tuple[str, str]:
    if f in FEATURE_TEXT:
        name, fmt = FEATURE_TEXT[f]
        return name, fmt(v)
    if f.startswith("dt_"):
        return f"disruption type {f[3:].replace('_', ' ')}", "yes" if v >= 0.5 else "no"
    if f.startswith("ind_"):
        return f"industry {f[4:]}", "yes" if v >= 0.5 else "no"
    return f.replace("_", " "), f"{v:.3g}"


def explain_scenario(G: nx.DiGraph, events: list, target: str = "unmet_pct", top_k: int = 4, dtype: str | None = None) -> list[str]:
    """Plain-English SHAP explanation of the surrogate's prediction for one scenario (empty if no model)."""
    import shap

    from core.features import context, feature_frame, scenario_features

    bundle = load_scenario_model()
    if bundle is None:
        return []
    X = feature_frame([scenario_features(context(G), events, dtype)])
    values = shap.TreeExplainer(bundle["models"][target]).shap_values(X)[0]
    label, unit, _, _ = TARGET_INFO[target]
    unit_s = "percentage points" if target == "unmet_pct" else unit
    out = []
    for j in np.argsort(-np.abs(values))[:top_k]:
        if abs(values[j]) < 1e-3:
            continue
        name, val = _feature_phrase(X.columns[j], float(X.iloc[0, j]))
        verb = "raises" if values[j] > 0 else "lowers"
        out.append(f"{name[0].upper() + name[1:]} ({val}) {verb} the predicted {label} by {abs(values[j]):.2f} {unit_s}.")
    return out


if __name__ == "__main__":
    import sys

    if "--scenario" in sys.argv:
        t0 = time.perf_counter()
        b = train_scenario_surrogate(fast="--fast" in sys.argv, verbose=True)
        print(f"trained in {time.perf_counter() - t0:.0f}s -> {scenario_model_path()} and {METRICS_PATH}")
        print(json.dumps(b["metrics"]["timing"]))
        raise SystemExit(0)
    t0 = time.perf_counter()
    b = train_surrogate()
    print(f"trained in {time.perf_counter() - t0:.1f}s -> {MODEL_PATH}")
    print({k: v for k, v in b["metrics"].items() if k != "top_features"})
    for f in b["metrics"]["top_features"]:
        print(f"  {f['feature']:<24} {f['importance']:.3f}")
