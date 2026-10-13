import joblib, json
import numpy as np

b = joblib.load('models/risk_xgb.joblib')
m = b['model']
booster = m.get_booster()

print("=== BUNDLE METADATA ===")
print(f"Version: {b['version']}")
print(f"Features ({len(b['features'])}): {b['features']}")

print("\n=== TRAINING METRICS ===")
metrics = b['metrics']
print(f"  Target:     {metrics['target']}")
print(f"  Train rows: {metrics['n_train']}")
print(f"  Test rows:  {metrics['n_test']}")
print(f"  MAE:        {metrics['mae']}")
print(f"  R2:         {metrics['r2']}")
print(f"  Speedup:    {metrics['speedup']}x")

print("\n=== MODEL HYPERPARAMETERS ===")
for k, v in m.get_params().items():
    print(f"  {k}: {v}")

print(f"\n  Num boosted rounds (trees): {booster.num_boosted_rounds()}")
print(f"  Num features used:          {m.n_features_in_}")

print("\n=== FEATURE IMPORTANCE (all types) ===")
for itype in ['weight', 'gain', 'cover', 'total_gain', 'total_cover']:
    scores = booster.get_score(importance_type=itype)
    total = sum(scores.values()) or 1.0
    print(f"  [{itype}]")
    for f in b['features']:
        val = scores.get(f, 0.0)
        bar = "#" * int((val / total) * 30)
        print(f"    {f:<28} {val/total:6.4f}  {bar}")

print("\n=== WHAT THE MODEL PREDICTS ===")
print("  Input:  11 graph topology + inventory features per supply chain node")
print("  Output: predicted share of total customer demand LOST if that node fails (0.0 to 1.0)")
print("  Used for: node 'risk' color in map, SHAP explanation tooltips, chaos ranking")
