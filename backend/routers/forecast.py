from fastapi import APIRouter, Query

from cache import cache
from config import settings
from core import forecast as fc_core
from core import risk_ml
from mock import mock_data
from routers.deps import get_graph
from schemas import ForecastResponse, SurrogateResponse

router = APIRouter(tags=["forecast"])


@router.get("/forecast", response_model=ForecastResponse)
def forecast(horizon: int = Query(14, ge=1, le=90)):
    compute = mock_data.forecast if settings.mock_network else (lambda h: fc_core.forecast_demand(get_graph(), h))
    return cache.get_or_compute(cache.key("forecast", [settings.mock_network, horizon]), lambda: compute(horizon))


@router.get("/surrogate", response_model=SurrogateResponse)
def surrogate():
    compute = mock_data.surrogate if settings.mock_network else risk_ml.surrogate_report
    return cache.get_or_compute(cache.key("surrogate", settings.mock_network), compute)
