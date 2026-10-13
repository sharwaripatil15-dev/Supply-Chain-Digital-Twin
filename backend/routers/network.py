import logging

from fastapi import APIRouter

from cache import cache
from config import settings
from core import chaos as chaos_core
from core import risk_ml
from core import sim as sim_core
from core.graph import graph_to_payload
from mock import mock_data
from network_store import store
from routers.deps import cache_scope, get_graph, use_mock
from schemas import NetworkResponse

router = APIRouter(tags=["network"])
log = logging.getLogger("aegis.network")


def _live_network() -> dict:
    """Active graph + baseline utilization + ML risk + resilience. Degrades instead of failing: an empty or
    not-yet-runnable network comes back with null risk/resilience, and each enrichment step is independent."""
    G = get_graph()
    H = G.copy()
    errors = store.active_errors()
    if errors or H.number_of_nodes() == 0:
        note = " ".join(e["message"] for e in errors) or "The network is empty."
        for _, d in H.nodes(data=True):
            d.update(risk=None, risk_note=note, top_factors=[], utilization=0.0)
        return graph_to_payload(H, None)
    try:
        baseline = sim_core.solve_flow(G)
        for n, d in H.nodes(data=True):
            cap = d.get("capacity") or 0
            d["utilization"] = round(baseline["throughput"].get(n, 0.0) / cap, 3) if cap else 0.0
    except Exception as exc:  # keep serving the twin even if the flow solve fails
        log.warning("baseline flow failed: %s", exc)
    for nid, info in risk_ml.node_risk_with_shap(G).items():
        H.nodes[nid].update(info)
    try:
        # scored on the unannotated graph so /network and /chaos share one cached scan
        score = chaos_core.resilience_score(G)
    except Exception as exc:
        log.warning("resilience score failed: %s", exc)
        score = None
    return graph_to_payload(H, score)


@router.get("/network", response_model=NetworkResponse)
def get_network():
    compute = mock_data.network if use_mock(settings.mock_network) else _live_network
    return cache.get_or_compute(cache.key("network", cache_scope(settings.mock_network)), compute)
