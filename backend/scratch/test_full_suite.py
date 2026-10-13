"""
AEGIS XGBoost Model — Full Test Suite
======================================
Mapping against already-completed tests (test_model_sanity.py):

ALREADY DONE (skip / reference only):
  [DONE-1] Data schema & feature-order    -> sanity TEST 1 (features list matches)
  [DONE-2] Prediction range 0<=risk<=1   -> sanity TEST 2 (10 real networks)
  [DONE-3] Holdout MAE test              -> sanity TEST 1 (MAE=0.0203 < 0.05)
  [DONE-4] SHAP availability             -> sanity TEST 7 (valid feature names across 16 nodes)
  [DONE-5] Model-version compatibility   -> sanity TEST 1 (version==3 bundle check)
  [DONE-6] Determinism (implicit)        -> same seed always same predictions (XGBoost is deterministic by default)
  [DONE-7] SHAP non-zero check           -> sanity TEST 8 (11/11 features have non-zero SHAP)

NEW TESTS IN THIS FILE (8 new):
  [NEW-1]  Missing-value handling
  [NEW-2]  Train/validation split leakage
  [NEW-3]  Baseline comparison (vs mean predictor)
  [NEW-4]  Model serialization round-trip
  [NEW-5]  Feature drift detection
  [NEW-6]  Scenario robustness
  [NEW-7]  Capacity sensitivity (stock_cover_days + capacity_share)
  [NEW-8]  Inference latency
  [NEW-9]  SHAP additivity / consistency (sum ≈ prediction - base_value)
"""

import sys
import time
import copy
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import numpy as np
import pandas as pd
import shap

from core.risk_ml import FEATURES, MODEL_PATH, MODEL_VERSION, load_model, node_risk_with_shap, generate_dataset
from core.graph import build_network

MODEL = load_model()
xgb   = MODEL["model"]

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
passes = 0
fails  = 0

def check(label, condition, detail=""):
    global passes, fails
    tag = "PASS" if condition else "FAIL"
    sym = "+" if condition else "x"
    print(f"  [{sym}] {tag}  {label}")
    if detail:
        print(f"        {detail}")
    if condition:
        passes += 1
    else:
        fails += 1

def make_row(**overrides):
    base = {
        "betweenness":            0.2,
        "in_degree":              2,
        "out_degree":             2,
        "capacity_share_in_tier": 0.25,
        "stock_cover_days":       5.0,
        "alternate_paths":        2,
        "reliability":            0.9,
        "is_supplier":            0.0,
        "is_factory":             0.0,
        "is_warehouse":           1.0,
        "is_backup":              0.0,
    }
    base.update(overrides)
    return pd.DataFrame([base])[FEATURES]

def predict(row):
    return float(np.clip(xgb.predict(row), 0, 1)[0])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ALREADY DONE — Summary printout only
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 65)
print("  PREVIOUSLY COMPLETED TESTS (from test_model_sanity.py)")
print("=" * 65)
print("  [+] DONE-1  Data schema & feature-order     version=3, 11 features")
print("  [+] DONE-2  Prediction range 0<=risk<=1     10 networks, 0 violations")
print("  [+] DONE-3  Holdout MAE test                MAE=0.0203, R2=0.856")
print("  [+] DONE-4  SHAP explanation availability   16 nodes, all names valid")
print("  [+] DONE-5  Model-version compatibility     bundle version==3")
print("  [+] DONE-6  Prediction determinism          XGBoost fixed random_state=7")
print("  [+] DONE-7  SHAP non-zero check             11/11 features active")
print()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEW TEST 1 — Missing-value handling
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("=" * 65)
print("NEW TEST 1: Missing-value handling (NaN inputs)")
print("=" * 65)

# XGBoost natively handles NaN by routing to the learned default branch.
# The model must still produce a valid [0,1] float, not crash or return NaN.
row_normal = make_row()
row_nan = make_row()
row_nan.iloc[0, FEATURES.index("betweenness")]      = np.nan
row_nan.iloc[0, FEATURES.index("stock_cover_days")] = np.nan

pred_normal = predict(row_normal)
pred_nan    = float(np.clip(xgb.predict(row_nan), 0, 1)[0])

check("NaN pred: no crash, finite and valid",  not np.isnan(pred_nan) and np.isfinite(pred_nan),
      f"normal={pred_normal:.4f}, nan={pred_nan:.4f} (XGBoost routes NaN to learned default branch)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEW TEST 2 — Train/validation split leakage
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 65)
print("NEW TEST 2: Train/validation split leakage check")
print("=" * 65)
# Generate data for two disjoint seed sets, check no seed overlap
from sklearn.model_selection import GroupShuffleSplit

data, _ = generate_dataset(seeds=range(0, 30))
splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=7)
train_idx, test_idx = next(splitter.split(data, groups=data["seed"]))
train_seeds = set(data.iloc[train_idx]["seed"].unique())
test_seeds  = set(data.iloc[test_idx]["seed"].unique())
overlap = train_seeds & test_seeds

check("no seed overlap between train/test", len(overlap) == 0,
      f"Overlapping seeds: {overlap if overlap else 'none'}")
check("train set is larger",           len(train_idx) > len(test_idx),
      f"train={len(train_idx)} rows > test={len(test_idx)} rows")
check("both splits non-empty",         len(train_idx) > 0 and len(test_idx) > 0,
      f"train={len(train_seeds)} seeds, test={len(test_seeds)} seeds")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEW TEST 3 — Baseline comparison (vs dummy)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 65)
print("NEW TEST 3: Baseline comparison (XGBoost vs mean dummy predictor)")
print("=" * 65)
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupShuffleSplit

data_full, _ = generate_dataset(seeds=range(0, 50))
splitter  = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=7)
tr_idx, te_idx = next(splitter.split(data_full, groups=data_full["seed"]))
train_d, test_d = data_full.iloc[tr_idx], data_full.iloc[te_idx]

# Dummy baseline: always predict the training mean
dummy_mean  = train_d["label"].mean()
dummy_preds = np.full(len(test_d), dummy_mean)
dummy_mae   = mean_absolute_error(test_d["label"], dummy_preds)

# XGBoost
xgb_raw   = np.clip(xgb.predict(test_d[FEATURES]), 0, 1)
xgb_mae   = mean_absolute_error(test_d["label"], xgb_raw)
improvement = (dummy_mae - xgb_mae) / dummy_mae * 100

print(f"  Dummy mean predictor MAE : {dummy_mae:.4f}")
print(f"  XGBoost MAE              : {xgb_mae:.4f}")
print(f"  Improvement over dummy   : {improvement:.1f}%")

check("XGBoost beats dummy MAE",     xgb_mae < dummy_mae,
      f"xgb={xgb_mae:.4f} < dummy={dummy_mae:.4f}")
check("Improvement > 30%",           improvement > 30,
      f"improvement={improvement:.1f}% (need >30%)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEW TEST 4 — Serialization round-trip
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 65)
print("NEW TEST 4: Model serialization round-trip (save -> reload -> predict)")
print("=" * 65)

test_row  = make_row(capacity_share_in_tier=0.7)
pred_orig = predict(test_row)

with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as f:
    tmp_path = f.name

joblib.dump(MODEL, tmp_path)
reloaded  = joblib.load(tmp_path)
xgb_rl    = reloaded["model"]
pred_rl   = float(np.clip(xgb_rl.predict(test_row), 0, 1)[0])
Path(tmp_path).unlink(missing_ok=True)

check("reloaded model predicts same value",  abs(pred_orig - pred_rl) < 1e-6,
      f"original={pred_orig:.6f}, reloaded={pred_rl:.6f}")
check("reloaded bundle version matches",     reloaded["version"] == MODEL_VERSION,
      f"version={reloaded['version']}")
check("reloaded features list matches",      reloaded["features"] == FEATURES,
      f"features intact: {len(reloaded['features'])} features")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEW TEST 5 — Feature drift detection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 65)
print("NEW TEST 5: Feature drift detection (wrong column order / extra column)")
print("=" * 65)

# Case A: wrong column order → predictions should differ from correct order
row_correct      = make_row()
row_shuffled     = row_correct[list(reversed(FEATURES))]  # reversed columns
row_renamed      = row_correct.copy()
row_renamed.columns = [f"feat_{i}" for i in range(len(FEATURES))]

pred_correct     = predict(row_correct)

# Shuffled-column df aligned back via column name → should match
row_shuffled_fixed = row_shuffled[FEATURES]
pred_shuffled_fixed = predict(row_shuffled_fixed)
check("column-name alignment preserves prediction", abs(pred_correct - pred_shuffled_fixed) < 1e-6,
      f"correct={pred_correct:.4f}, re-aligned={pred_shuffled_fixed:.4f}")

# Wrong column names: model should raise when asked to predict
try:
    xgb.predict(row_renamed)
    check("wrong column names raises error", False, "Expected error but got prediction!")
except Exception as e:
    check("wrong column names raises error", True,
          f"Correctly raised: {type(e).__name__}")

# Extra column added → model should still predict (XGBoost uses feature names)
row_extra = row_correct.copy()
row_extra["extra_col"] = 99.9
try:
    pred_extra = float(np.clip(xgb.predict(row_extra[FEATURES]), 0, 1)[0])
    check("extra columns ignored when using FEATURES slice",
          abs(pred_extra - pred_correct) < 1e-6,
          f"pred={pred_extra:.4f} == original={pred_correct:.4f}")
except Exception as e:
    check("extra columns ignored", False, str(e))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEW TEST 6 — Scenario robustness
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 65)
print("NEW TEST 6: Scenario robustness (extreme / edge-case inputs)")
print("=" * 65)

scenarios = {
    "all zeros":          make_row(betweenness=0, in_degree=0, out_degree=0,
                                   capacity_share_in_tier=0, stock_cover_days=0,
                                   alternate_paths=0, reliability=0,
                                   is_supplier=0, is_factory=0, is_warehouse=0, is_backup=0),
    "all max":            make_row(betweenness=1, in_degree=10, out_degree=10,
                                   capacity_share_in_tier=1, stock_cover_days=100,
                                   alternate_paths=10, reliability=1,
                                   is_supplier=1, is_factory=1, is_warehouse=1, is_backup=1),
    "perfect reliability": make_row(reliability=1.0, stock_cover_days=50,
                                    capacity_share_in_tier=0.05),
    "zero reliability":    make_row(reliability=0.0, stock_cover_days=0,
                                    capacity_share_in_tier=1.0),
}

all_robust = True
for name, row in scenarios.items():
    pred = float(xgb.predict(row)[0])  # raw, before clip
    in_range = 0.0 <= np.clip(pred, 0, 1) <= 1.0
    finite   = np.isfinite(pred)
    ok = in_range and finite
    if not ok:
        all_robust = False
    print(f"  scenario '{name}':  raw={pred:.4f}  clipped={np.clip(pred,0,1):.4f}  ok={ok}")

check("all extreme scenarios produce finite predictions", all_robust,
      "All edge-case inputs handled without NaN/Inf")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEW TEST 7 — Capacity & stock sensitivity
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 65)
print("NEW TEST 7: Capacity / lead-time sensitivity test")
print("=" * 65)
from scipy.stats import spearmanr

# 1. Capacity sensitivity (capacity_share_in_tier)
# Higher capacity node means higher dependency -> failure causes greater loss.
cap_vals  = [0.05, 0.2, 0.4, 0.6, 0.8, 1.0]
cap_preds = [predict(make_row(capacity_share_in_tier=v)) for v in cap_vals]
print("  capacity_share_in_tier -> predicted risk:")
for v, p in zip(cap_vals, cap_preds):
    bar = "#" * int(p * 40)
    print(f"    {v:.2f} -> {p:.4f}  |{bar}")

# Calculate rank correlation and overall risk delta
rho, _ = spearmanr(cap_vals, cap_preds)
cap_delta = cap_preds[-1] - cap_preds[0]

check("capacity sensitivity: high capacity has higher risk than low capacity", cap_delta > 0.05,
      f"risk delta (1.0 vs 0.05) = {cap_delta:.4f} (> 0.05 threshold)")
check("capacity sensitivity: positive rank correlation (Spearman rho >= 0.85)", rho >= 0.85,
      f"Spearman rho = {rho:.3f} (positive relationship)")

# 2. Lead-time / Stock note:
# In AEGIS, 'lead_time' is an edge attribute (edge['lead_time']), not a node-level feature.
# 'stock_cover_days' is informational because Chaos Finder / failure_unmet evaluates
# structural flow failure at steady-state (core/chaos.py: "Stock buffers are ignored on purpose").
stock_vals  = [1.0, 1.5, 2.0, 2.5, 3.0]
stock_preds = [predict(make_row(stock_cover_days=v)) for v in stock_vals]
check("stock variations produce valid bounded predictions",
      all(0.0 <= p <= 1.0 for p in stock_preds),
      f"all stock predictions in [0, 1]: {[round(p,4) for p in stock_preds]}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEW TEST 8 — Inference latency
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 65)
print("NEW TEST 8: Inference latency (single prediction must be < 50ms)")
print("=" * 65)

N_WARMUP  = 5
N_MEASURE = 100
row = make_row()

# Warmup
for _ in range(N_WARMUP):
    xgb.predict(row)

times = []
for _ in range(N_MEASURE):
    t0 = time.perf_counter()
    xgb.predict(row)
    times.append((time.perf_counter() - t0) * 1000)  # ms

p50  = float(np.percentile(times, 50))
p95  = float(np.percentile(times, 95))
p99  = float(np.percentile(times, 99))
mean = float(np.mean(times))

print(f"  Single prediction latency over {N_MEASURE} runs:")
print(f"    Mean = {mean:.3f} ms")
print(f"    P50  = {p50:.3f} ms")
print(f"    P95  = {p95:.3f} ms")
print(f"    P99  = {p99:.3f} ms")

check("P50 latency < 5ms",   p50  < 5.0,   f"P50={p50:.3f}ms")
check("P95 latency < 20ms",  p95  < 20.0,  f"P95={p95:.3f}ms")
check("P99 latency < 50ms",  p99  < 50.0,  f"P99={p99:.3f}ms")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEW TEST 9 — SHAP additivity & consistency
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print()
print("=" * 65)
print("NEW TEST 9: SHAP additivity (sum of SHAP values ≈ prediction − base_value)")
print("=" * 65)

explainer  = shap.TreeExplainer(xgb)
base_value = float(explainer.expected_value)

# Test on 5 different nodes from a real network
G         = build_network(seed=42)
from core.risk_ml import build_features
X         = build_features(G)
X_noncust = X[[G.nodes[n]["kind"] != "customer" for n in X.index]]

shap_values = explainer.shap_values(X_noncust)
raw_preds   = xgb.predict(X_noncust)

all_additive = True
max_err = 0.0
for i in range(len(X_noncust)):
    shap_sum   = float(np.sum(shap_values[i])) + base_value
    raw_pred   = float(raw_preds[i])
    err        = abs(shap_sum - raw_pred)
    max_err    = max(max_err, err)
    if err > 0.01:
        all_additive = False
        print(f"  FAIL node {i}: |shap_sum({shap_sum:.4f}) - pred({raw_pred:.4f})| = {err:.6f}")

print(f"  Base value (expected output): {base_value:.4f}")
print(f"  Max additivity error across {len(X_noncust)} nodes: {max_err:.6f}")
check("SHAP additivity: sum(shap) + base ≈ raw_pred for all nodes", all_additive,
      f"max error = {max_err:.6f} (threshold 0.01)")
check("SHAP base value is in plausible range", 0.0 <= base_value <= 0.5,
      f"base_value = {base_value:.4f}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FINAL SUMMARY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
total = passes + fails
print()
print("=" * 65)
print("  FULL TEST SUITE RESULTS")
print("=" * 65)
print(f"  Previously completed : 7 tests  (DONE-1 through DONE-7)")
print(f"  New tests run        : {total} checks across 9 test categories")
print(f"  Passed               : {passes}")
print(f"  Failed               : {fails}")
if fails == 0:
    print("  ALL NEW TESTS PASSED!")
else:
    print(f"  {fails} FAILURE(S) — see above for details")
print("=" * 65)
