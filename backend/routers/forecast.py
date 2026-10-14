from fastapi import APIRouter, Query

from cache import cache
from config import settings
from core import forecast as fc_core
from core import risk_ml
from mock import mock_data
from routers.deps import cache_scope, get_graph, use_mock
from schemas import ForecastResponse, SurrogateResponse

router = APIRouter(tags=["forecast"])


@router.get("/forecast", response_model=ForecastResponse)
def forecast(horizon: int = Query(14, ge=1, le=90)):
    compute = mock_data.forecast if use_mock(settings.mock_network) else (lambda h: fc_core.forecast_demand(get_graph(), h))
    return cache.get_or_compute(cache.key("forecast", [cache_scope(settings.mock_network), horizon]), lambda: compute(horizon))


@router.get("/surrogate", response_model=SurrogateResponse)
def surrogate():
    # the surrogate is trained on generated networks, so its accuracy report does not depend on the active one
    compute = mock_data.surrogate if settings.mock_network else risk_ml.surrogate_report
    body = dict(cache.get_or_compute(cache.key("surrogate", settings.mock_network), compute))
    # the scenario surrogate's held-out metrics (models/metrics.json) are a static training artifact, shown in both modes
    body["scenario"] = risk_ml.scenario_metrics()
    return body
