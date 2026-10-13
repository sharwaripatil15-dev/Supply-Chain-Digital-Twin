from fastapi import APIRouter

from config import settings
from core import recommend as rec_core
from mock import mock_data
from routers.deps import check_events, get_graph, require_runnable, use_mock
from schemas import AlternatesRequest, AlternatesResponse

router = APIRouter(prefix="/recommend", tags=["recommend"])


def _extract_down_elements(events, down_suppliers, down_lanes, G):
    suppliers = set(down_suppliers)
    lanes = set(down_lanes)
    for e in events:
        if e.type == "node" and e.severity >= 0.5:
            if G.nodes.get(e.target, {}).get("kind") == "supplier":
                suppliers.add(e.target)
        elif e.type == "edge" and e.severity >= 0.5:
            lanes.add(e.target)
    # If still empty, fall back to checking top vulnerable supplier
    if not suppliers and not lanes:
        for n, d in G.nodes(data=True):
            if d.get("kind") == "supplier" and not d.get("backup"):
                suppliers.add(n)
                break
    return sorted(suppliers), sorted(lanes)


@router.post("/alternates", response_model=AlternatesResponse)
def get_alternates(req: AlternatesRequest):
    mock = use_mock(settings.mock_recover)
    if not mock:
        require_runnable()
    events = check_events(req.events, mock=mock) if req.events else []
    G = get_graph()
    
    suppliers, lanes = _extract_down_elements(events, req.down_suppliers, req.down_lanes, G)
    down_edges = [tuple(lane.split("->")) for lane in lanes if "->" in lane]
    
    alt_suppliers = rec_core.rank_alternate_suppliers(G, suppliers)
    alt_routes = rec_core.rank_alternate_routes(G, suppliers, down_edges)
    
    return {
        "alternate_suppliers": alt_suppliers,
        "alternate_routes": alt_routes,
        "disrupted_suppliers": suppliers,
        "disrupted_lanes": lanes,
    }


@router.get("/alternates", response_model=AlternatesResponse)
def get_default_alternates():
    """Returns alternate supplier and route recommendations for the default vulnerable elements in the active network."""
    return get_alternates(AlternatesRequest())
