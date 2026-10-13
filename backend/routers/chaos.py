from fastapi import APIRouter

from cache import cache
from config import settings
from core import chaos as chaos_core
from mock import mock_data
from routers.deps import cache_scope, get_graph, require_runnable, use_mock
from schemas import ChaosResponse

router = APIRouter(tags=["chaos"])


@router.get("/chaos", response_model=ChaosResponse)
def chaos(top: int = 5):
    mock = use_mock(settings.mock_chaos)
    if not mock:
        require_runnable()
    compute = mock_data.chaos if mock else (lambda: chaos_core.chaos_find(get_graph(), top=top))
    return cache.get_or_compute(cache.key("chaos", [cache_scope(settings.mock_chaos), top]), compute)
