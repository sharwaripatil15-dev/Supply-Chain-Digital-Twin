"""Event validation shared by the routers and the LLM parser.

Pydantic already enforces types and severity in [0, 1]; this checks the targets
against the actual network (node ids exist, edges exist, demand targets are demand nodes: retailers or customers).
"""
from __future__ import annotations

from typing import Iterable

from node_types import is_demand
from schemas import Event


class EventValidationError(ValueError):
    pass


def validate_events(events: Iterable[Event], nodes: dict[str, str], edges: set[tuple[str, str]]) -> list[Event]:
    """nodes: {id: kind}; edges: {(source, target)}. Raises EventValidationError listing every problem."""
    events = list(events)
    errors: list[str] = []
    for i, ev in enumerate(events):
        if not 0.0 <= ev.severity <= 1.0:
            errors.append(f"events[{i}]: severity {ev.severity} outside 0..1")
        if ev.type == "edge":
            parts = ev.target.split("->")
            if len(parts) != 2:
                errors.append(f'events[{i}]: edge target must look like "SRC->DST", got {ev.target!r}')
            elif tuple(p.strip() for p in parts) not in edges:
                errors.append(f"events[{i}]: unknown edge {ev.target!r}")
        elif ev.target not in nodes:
            errors.append(f"events[{i}]: unknown node id {ev.target!r}")
        elif ev.type == "demand" and not is_demand(nodes[ev.target]):
            errors.append(f"events[{i}]: demand events must target a customer or retailer, {ev.target!r} is a {nodes[ev.target]}")
    if errors:
        raise EventValidationError("; ".join(errors))
    return events
