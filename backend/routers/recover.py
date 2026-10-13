from fastapi import APIRouter

from cache import cache
from config import settings
from core import recommend as rec_core
from core import strategies as strat_core
from llm.parser import LLMUnavailable, write_playbook
from mock import mock_data
from routers.deps import cache_scope, check_events, get_graph, require_runnable, use_mock
from schemas import RecoverRequest, RecoverResponse

router = APIRouter(tags=["recover"])


def _live_recover(events) -> dict:
    G = get_graph()
    rows = strat_core.run_strategies(G, events)
    rec = next(r for r in rows if r["recommended"])
    roi = strat_core.roi(G, rows)
    strategies = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    down_nodes = [e.target for e in events if e.type == "node" and e.severity >= 0.5]
    down_edges = [tuple(e.target.split("->")) for e in events if e.type == "edge" and e.severity >= 0.5]
    try:
        playbook = write_playbook(strat_core.playbook_facts(G, rows, roi))
    except LLMUnavailable:
        playbook = strat_core.template_playbook(G, list(events), rows)
    return {
        "strategies": strategies,
        "roi": roi,
        "playbook": playbook,
        "alternate_suppliers": rec_core.rank_alternate_suppliers(G, [n for n in down_nodes if G.nodes[n]["kind"] == "supplier"]),
        "alternate_routes": rec_core.rank_alternate_routes(G, down_nodes, down_edges),
        "inventory_actions": rec["_plan"]["inventory_actions"],
        "production_actions": rec["_plan"]["production_actions"],
    }


@router.post("/recover", response_model=RecoverResponse)
def recover(req: RecoverRequest):
    mock = use_mock(settings.mock_recover)
    if not mock:
        require_runnable()
    events = check_events(req.events, mock=mock)
    compute = mock_data.recover if mock else _live_recover
    return cache.get_or_compute(cache.key("recover", [cache_scope(settings.mock_recover), req]), lambda: compute(events))
