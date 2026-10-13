"""Risk prediction router: POST /risk/predict and GET /risk/status.

Uses core.scenario_ml (XGBoost scenario surrogate) to predict unmet-demand fraction
for a multi-event disruption scenario before running the full simulator.

If the model has not been trained, the endpoint returns a clear status rather than
fabricated risk scores.  Training is NOT triggered on-demand; use the CLI:
    python -m core.scenario_ml
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from core import scenario_ml
from routers.deps import check_events, get_graph
from schemas import (
    RiskModelStatusResponse,
    RiskPredictRequest,
    RiskPredictResponse,
    RiskShapFactor,
    RiskModelMetrics,
)

log = logging.getLogger("aegis.risk")
router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/status", response_model=RiskModelStatusResponse)
def risk_status():
    """Return whether the scenario risk model is trained and its evaluation metrics."""
    status = scenario_ml.model_status()
    metrics = None
    if status["trained"] and status["metrics"]:
        m = status["metrics"]
        metrics = RiskModelMetrics(
            mae=m["mae"], r2=m["r2"],
            n_train=m["n_train"], n_test=m["n_test"],
        )
    return RiskModelStatusResponse(
        trained=status["trained"],
        path=status["path"],
        metrics=metrics,
    )


@router.post("/predict", response_model=RiskPredictResponse)
def risk_predict(req: RiskPredictRequest):
    """Predict the unmet-demand fraction for a disruption scenario.

    This is a fast ML surrogate (XGBoost).  It is NOT the exact simulator output.
    For the exact simulation result use POST /simulate.

    If the model is not trained, returns confidence='no_model' with zero prediction.
    Feature extraction errors return HTTP 422.
    """
    events = check_events(req.events, mock=False)
    G = get_graph()

    # ── check model availability first ──────────────────────────────────────
    try:
        _ = scenario_ml.load_model()
    except FileNotFoundError:
        return RiskPredictResponse(
            unmet_demand_fraction=0.0,
            predicted_unmet_units=0.0,
            risk_score=0,
            risk_level="low",
            confidence="no_model",
            top_factors=[],
            model_metrics=None,
            note=(
                "Scenario risk model has not been trained yet. "
                "Run: python -m core.scenario_ml  in the backend directory."
            ),
        )

    # ── feature extraction ───────────────────────────────────────────────────
    try:
        result = scenario_ml.predict(G, events)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Feature extraction failed: {exc}") from exc
    except Exception as exc:
        log.exception("Unexpected error during scenario risk prediction")
        raise HTTPException(status_code=500, detail=f"Prediction error: {exc}") from exc

    m = result["model_metrics"]
    return RiskPredictResponse(
        unmet_demand_fraction=result["unmet_demand_fraction"],
        predicted_unmet_units=result.get("predicted_unmet_units", 0.0),
        risk_score=result.get("risk_score", 0),
        risk_level=result.get("risk_level", "low"),
        confidence=result["confidence"],
        top_factors=[RiskShapFactor(feature=f["feature"], impact=f["impact"]) for f in result["top_factors"]],
        model_metrics=RiskModelMetrics(mae=m["mae"], r2=m["r2"], n_train=m["n_train"], n_test=m["n_test"]),
        note="XGBoost scenario surrogate — feature-level SHAP contributions, not causal explanations.",
    )
