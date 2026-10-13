from fastapi import APIRouter

from cache import cache
from config import settings
from core import chaos as chaos_core
from mock import mock_data
from routers.deps import get_graph
from schemas import ChaosResponse

router = APIRouter(tags=["chaos"])


@router.get("/chaos", response_model=ChaosResponse)
def chaos(top: int = 5):
    compute = mock_data.chaos if settings.mock_chaos else (lambda: chaos_core.chaos_find(get_graph(), top=top))
    return cache.get_or_compute(cache.key("chaos", [settings.mock_chaos, top]), compute)
