from fastapi import APIRouter

from cache import cache
from config import settings
from core import montecarlo as mc_core
from core import sim as sim_core
from mock import mock_data
from routers.deps import check_events, get_graph
from schemas import MonteCarloRequest, MonteCarloResponse, SimulateRequest, SimulateResponse

router = APIRouter(tags=["simulate"])


@router.post("/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest):
    events = check_events(req.events, mock=settings.mock_simulate)
    compute = mock_data.simulate if settings.mock_simulate else (lambda ev, h: sim_core.simulate(get_graph(), ev, h))
    key = cache.key("simulate", [settings.mock_simulate, req])
    return cache.get_or_compute(key, lambda: compute(events, req.horizon))


@router.post("/montecarlo", response_model=MonteCarloResponse)
def montecarlo(req: MonteCarloRequest):
    events = check_events(req.events, mock=settings.mock_simulate)
    compute = mock_data.montecarlo if settings.mock_simulate else (lambda ev, n: mc_core.monte_carlo(get_graph(), ev, n))
    key = cache.key("montecarlo", [settings.mock_simulate, req])
    return cache.get_or_compute(key, lambda: compute(events, req.n))
