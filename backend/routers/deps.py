"""Shared router helpers: the demo/active graph and event validation -> HTTP 422."""
from __future__ import annotations

from functools import lru_cache

import networkx as nx
from fastapi import HTTPException

from config import settings
from core.graph import build_network, node_index
from schemas import Event
from validation import EventValidationError, validate_events

_active: nx.DiGraph | None = None  # set by POST /upload?activate=true


@lru_cache(maxsize=1)
def demo_graph() -> nx.DiGraph:
    return build_network(seed=settings.default_seed)


def get_graph() -> nx.DiGraph:
    """Graph used by core/ (live) routers: the uploaded network if one was activated, else the demo."""
    return _active if _active is not None else demo_graph()


def set_graph(G: nx.DiGraph | None) -> None:
    global _active
    _active = G


def check_events(events: list[Event], mock: bool) -> list[Event]:
    """Validate against the graph the handler will actually use (mocks only know the demo network)."""
    nodes, edges = node_index(demo_graph() if mock else get_graph())
    try:
        return validate_events(events, nodes, edges)
    except EventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
