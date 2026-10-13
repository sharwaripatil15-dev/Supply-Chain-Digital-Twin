"""Shared router helpers: the active graph, the mock/live decision, and event validation -> HTTP 422."""
from __future__ import annotations

from functools import lru_cache

import networkx as nx
from fastapi import HTTPException

from config import settings
from core.graph import DEMO_NETWORK, build_network, node_index
from network_store import store
from schemas import Event
from validation import EventValidationError, validate_events


@lru_cache(maxsize=1)
def demo_graph() -> nx.DiGraph:
    return build_network(seed=settings.default_seed)


@lru_cache(maxsize=1)
def mock_demo_graph() -> nx.DiGraph:
    """The network the mock payloads describe (mock/demo_network.json), as an engine graph."""
    return build_network(seed=settings.default_seed, path=DEMO_NETWORK)


def preset_graph() -> nx.DiGraph:
    """The preset exactly as GET /network shows it: the mock demo while USE_MOCK_NETWORK is on, else the generator."""
    return mock_demo_graph() if settings.mock_network else demo_graph()


def get_graph() -> nx.DiGraph:
    """Graph used by core/ (live) routers: the active network (manual builder or activated CSV), else the demo."""
    G = store.graph()
    return G if G is not None else demo_graph()


def set_graph(G: nx.DiGraph | None) -> None:
    """Activate an uploaded graph (source = csv), or None for the preset."""
    if G is None:
        store.use_preset()
    else:
        store.activate_csv(G)


def use_mock(flag: bool) -> bool:
    """Mock payloads only describe the preset, so CSV and manual networks always run on the real engine."""
    return flag and store.source == "preset"


def require_runnable() -> None:
    """409 with a readable message when the active CSV/manual network cannot run (empty, no supplier, no demand)."""
    errors = store.active_errors()
    if errors:
        what = "manual network" if store.source == "manual" else "uploaded network"
        raise HTTPException(
            status_code=409,
            detail=f"The active {what} can't be simulated yet: {' '.join(e['message'] for e in errors)} "
                   "Fix it on the Data tab or switch back to the preset demo.",
        )


def cache_scope(flag: bool) -> list:
    """Cache-key prefix: which engine answered (mock/live) and which network version it answered for."""
    return [use_mock(flag), store.source, store.version]


def check_events(events: list[Event], mock: bool) -> list[Event]:
    """Validate against the graph the handler will actually use (mocks only know the demo network)."""
    nodes, edges = node_index(demo_graph() if mock else get_graph())
    try:
        return validate_events(events, nodes, edges)
    except EventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
