from fastapi import APIRouter

from cache import cache
from config import settings
from core import chaos as chaos_core
from core import risk_ml
from core import sim as sim_core
from core.graph import graph_to_payload
from mock import mock_data
from routers.deps import get_graph
from schemas import NetworkResponse

router = APIRouter(tags=["network"])


def _live_network() -> dict:
    G = get_graph().copy()
    baseline = sim_core.solve_flow(G)
    for n, d in G.nodes(data=True):
        cap = d.get("capacity") or 0
        d["utilization"] = round(baseline["throughput"].get(n, 0.0) / cap, 3) if cap else 0.0
    for nid, info in risk_ml.node_risk_with_shap(get_graph()).items():
        G.nodes[nid].update(info)
    # scored on the unannotated graph so /network and /chaos share one cached scan
    return graph_to_payload(G, chaos_core.resilience_score(get_graph()))


@router.get("/network", response_model=NetworkResponse)
def get_network():
    compute = mock_data.network if settings.mock_network else _live_network
    return cache.get_or_compute(cache.key("network", [settings.mock_network, id(get_graph())]), compute)
