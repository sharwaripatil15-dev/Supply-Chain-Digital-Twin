"""Data-driven follow-up suggestion generator (Zero LLM hallucinations). Owner: Digital Twin Engine."""
from __future__ import annotations

import networkx as nx
from typing import Iterable
from schemas import Event
from node_types import is_demand


def generate_data_followups(G: nx.DiGraph, events: Iterable[Event], max_suggestions: int = 3) -> list[str]:
    """Generate operational follow-up questions directly from network graph metrics and active events."""
    events = list(events)
    disrupted_nodes = {ev.target for ev in events if "->" not in ev.target}
    suggestions: list[str] = []

    # 1. Check alternate suppliers with spare capacity
    for n, d in G.nodes(data=True):
        if d.get("kind") == "supplier" and n not in disrupted_nodes:
            cap = float(d.get("capacity", 0.0))
            util = float(d.get("utilization", 0.70))
            spare_pct = max(0, int(round((1.0 - util) * 100)))
            if spare_pct >= 20:
                name = d.get("name") or n
                suggestions.append(f"Supplier {name} ({n}) has ~{spare_pct}% spare capacity: test shifting volume here?")
                break

    # 2. Check warehouses with critically low inventory buffer (< 5 days cover)
    for n, d in G.nodes(data=True):
        if d.get("kind") == "warehouse" and n not in disrupted_nodes:
            stock = float(d.get("stock", 0.0))
            cap = float(d.get("capacity", 1.0) or 1.0)
            stock_days = stock / cap if cap > 0 else 0
            if stock_days < 5.0:
                name = d.get("name") or n
                suggestions.append(f"Warehouse {name} ({n}) has only {stock_days:.1f} days stock cover: stress-test this node?")
                break

    # 3. Check downstream customers with high demand
    for n, d in G.nodes(data=True):
        if is_demand(d.get("kind", "")) and n not in disrupted_nodes:
            dem = float(d.get("demand", 0.0))
            if dem > 80:
                name = d.get("name") or n
                suggestions.append(f"Customer {name} ({n}) has high baseline volume ({dem:.0f} u/d): simulate concurrent regional demand spike?")
                break

    # 4. Check backup supplier availability
    backup_suppliers = [n for n, d in G.nodes(data=True) if d.get("backup")]
    if backup_suppliers and any(G.nodes[ev.target].get("kind") == "supplier" for ev in events if ev.target in G):
        b_id = backup_suppliers[0]
        b_name = G.nodes[b_id].get("name", b_id)
        suggestions.append(f"Primary supplier affected: evaluate activating backup facility {b_name} ({b_id})?")

    # Fallback generic data prompt if network has no specific anomalies
    if not suggestions:
        suggestions.append("Simulate extending disruption duration by 5 days to assess buffer breakdown?")

    return suggestions[:max_suggestions]
