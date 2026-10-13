"""Standalone training script for the AEGIS XGBoost Risk Surrogate Model.

Run this script from the `backend` folder:
    cd backend
    .\\.venv\\Scripts\\python.exe train_model.py
"""
import sys
import time
from pathlib import Path

# Add backend directory to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
from xgboost import XGBRegressor

from core.risk_ml import FEATURES, MODEL_PATH, MODEL_VERSION, generate_dataset

# ==========================================
# 1. EXPERIMENT PARAMETERS (Customizable)
# ==========================================
SEEDS_RANGE = range(0, 201)   # Seeds used to generate synthetic supply chain graphs
TEST_FRACTION = 0.20          # 20% held-out network topologies for testing
RANDOM_SEED = 7               # Reproducibility seed

# XGBoost Hyperparameters
XGB_PARAMS = {
    "n_estimators": 400,        # Number of boosting trees
    "max_depth": 4,             # Maximum tree depth (prevents overfitting)
    "learning_rate": 0.05,      # Step size shrinkage
    "subsample": 0.9,           # Row subsample ratio
    "colsample_bytree": 0.9,    # Feature subsample ratio
    "random_state": RANDOM_SEED,
    "n_jobs": 2                 # Parallel CPU threads (-1 for all)
}

def main():
    print("=" * 60)
    print(" AEGIS XGBoost Surrogate Model Training")
    print("=" * 60)

    # 1. Generate Synthetic Dataset
    print(f"\n[1/4] Generating synthetic supply chains across {len(SEEDS_RANGE)} graph seeds...")
    t0 = time.perf_counter()
    data, avg_engine_time = generate_dataset(seeds=SEEDS_RANGE)
    gen_time = time.perf_counter() - t0
    print(f"      Generated {len(data)} node samples in {gen_time:.2f}s")
    print(f"      Features: {FEATURES}")

    # 2. Grouped Train/Test Split
    print(f"\n[2/4] Splitting train ({1-TEST_FRACTION:.0%}) / test ({TEST_FRACTION:.0%}) grouped by network seed...")
    splitter = GroupShuffleSplit(n_splits=1, test_size=TEST_FRACTION, random_state=RANDOM_SEED)
    train_idx, test_idx = next(splitter.split(data, groups=data["seed"]))
    train, test = data.iloc[train_idx], data.iloc[test_idx]
    print(f"      Train samples: {len(train)} | Test samples: {len(test)}")

    # 3. Fit XGBoost Model
    print(f"\n[3/4] Fitting XGBRegressor with params:")
    for k, v in XGB_PARAMS.items():
        print(f"      - {k}: {v}")
    
    t_train = time.perf_counter()
    model = XGBRegressor(**XGB_PARAMS)
    model.fit(train[FEATURES], train["label"])
    train_duration = time.perf_counter() - t_train
    print(f"      Fitted in {train_duration:.2f}s")

    # 4. Evaluate & Benchmark
    print(f"\n[4/4] Evaluating on held-out test networks...")
    t_pred = time.perf_counter()
    raw_preds = model.predict(test[FEATURES])
    pred_time_per_sample = (time.perf_counter() - t_pred) / len(test)
    preds = np.clip(raw_preds, 0, 1)

    mae = float(mean_absolute_error(test["label"], preds))
    rmse = float(np.sqrt(mean_squared_error(test["label"], preds)))
    r2 = float(r2_score(test["label"], preds))
    speedup = round(avg_engine_time / pred_time_per_sample, 1) if pred_time_per_sample > 0 else 0.0

    print("\n" + "=" * 60)
    print(" EVALUATION RESULTS:")
    print("=" * 60)
    print(f"  R^2 Score:    {r2:.4f}  (variance explained)")
    print(f"  MAE:          {mae:.4f}  (mean absolute error in predicted lost demand)")
    print(f"  RMSE:         {rmse:.4f}")
    print(f"  Sim Speedup:  {speedup}x faster than physical solver")

    # Feature Importance (Gain)
    gain_scores = model.get_booster().get_score(importance_type="gain")
    total_gain = sum(gain_scores.values()) or 1.0
    top_features = sorted(
        [{"feature": f, "importance": round(gain_scores.get(f, 0.0) / total_gain, 3)} for f in FEATURES],
        key=lambda x: -x["importance"]
    )

    print("\n Top Feature Importances (Gain):")
    for item in top_features:
        bar = "#" * int(item["importance"] * 30)
        print(f"  {item['feature']:<25} {item['importance']:>5.3f} | {bar}")

    # 5. Save Model Bundle
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "version": MODEL_VERSION,
        "model": model,
        "features": FEATURES,
        "metrics": {
            "target": "share of demand lost if a single node fails (flow engine, backup available)",
            "mae": round(mae, 4),
            "r2": round(r2, 3),
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "speedup": speedup,
            "top_features": top_features[:6],
        },
    }
    joblib.dump(bundle, MODEL_PATH)
    print(f"\n Saved updated model to: {MODEL_PATH}")
    print(" Done!")

if __name__ == "__main__":
    main()
