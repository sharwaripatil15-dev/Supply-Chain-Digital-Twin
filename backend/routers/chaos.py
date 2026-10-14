from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from cache import cache
from config import settings
from core import chaos as chaos_core
from mock import mock_data
from core import prescreen as prescreen_core
from network_store import store
from routers.deps import cache_scope, display_graph, get_graph, require_runnable, use_mock
from schemas import ChaosResponse

router = APIRouter(tags=["chaos"])


@router.get("/chaos", response_model=ChaosResponse)
def chaos(top: int = 5):
    mock = use_mock(settings.mock_chaos)
    if not mock:
        require_runnable()
    compute = mock_data.chaos if mock else (lambda: chaos_core.chaos_find(get_graph(), top=top))
    return cache.get_or_compute(cache.key("chaos", [cache_scope(settings.mock_chaos), top]), compute)


@router.get("/chaos/prescreen")
async def chaos_prescreen(n: int = Query(2000, ge=50, le=20000), top: int = Query(15, ge=3, le=50), seed: int = 7):
    """Surrogate pre-screen: rank `n` random single/paired failures with the ML surrogate, re-run the exact simulator on
    the `top` candidates (+ a random control sample), report agreement and speedup. Always the real engine."""
    require_runnable()
    key = cache.key("chaos-prescreen", [store.source, store.version, n, top, seed])
    return await run_in_threadpool(cache.get_or_compute, key, lambda: prescreen_core.prescreen(display_graph(), n, top, seed))
