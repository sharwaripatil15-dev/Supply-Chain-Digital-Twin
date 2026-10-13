"""Deterministic cascade computation (Graph + Lead Times + Inventory physics). Owner: Digital Twin Engine.

CORE PRINCIPLE:
Zero LLM hallucination. All numbers (TTS, TTR, impact days) are computed mathematically
from the NetworkX graph, node inventory levels, and edge lead times.

FORMULAS:
1. First Impact Day (t_impact):
   t_impact = disruption_start_day + shortest_path_lead_time(disrupted_node, current_node)

2. Time-To-Survive (TTS):
   The elapsed days from disruption start until local on-hand inventory buffer drops to zero.
   TTS = t_impact + (on_hand_stock / net_depletion_rate)

   Where:
   - For Supply Outage (severity s in [0, 1]):
     inflow drops to normal_inflow * (1 - s).
     net_depletion_rate = normal_demand * s.
     inventory_cover_days = stock / max(normal_demand * s, 1.0)
     TTS = t_impact + inventory_cover_days

   - For Demand Surge (multiplier M > 1.0):
     outflow spikes to normal_demand * M while inflow remains at normal_demand.
     net_depletion_rate = normal_demand * (M - 1.0).
     inventory_cover_days = stock / max(normal_demand * (M - 1.0), 1.0)
     TTS = t_impact + inventory_cover_days

3. Time-To-Recover (TTR):
   - For Supply Outage:
     TTR = disruption_duration + replenishment_lead_time
     (Disrupted site takes `duration` to resume operations, plus shipping transit to restock).
   - For Demand Surge:
     TTR = disruption_duration + (depleted_stock / max(spare_inflow_headroom, 1.0))
     (Surge lasts `duration` days; afterwards, excess depleted buffer requires extra transit cycles to refill).

4. Status:
   - 'survives' if TTS >= t_impact + disruption_duration (stock buffer outlasts the disruption).
   - 'fails' if TTS < t_impact + disruption_duration (stockout occurs before recovery).
"""
from __future__ import annotations

import networkx as nx
from typing import Iterable
from schemas import Event, CascadeNodeImpact
from node_types import is_demand


def compute_cascade(G: nx.DiGraph, events: Iterable[Event]) -> list[CascadeNodeImpact]:
    """Compute deterministic cascade propagation and TTS/TTR for all affected nodes."""
    events = list(events)
    if not events:
        return []

    # Pre-compute shortest lead times from all nodes to all nodes
    lead_times: dict[tuple[str, str], float] = {}
    for u in G.nodes():
        for v in G.nodes():
            if u == v:
                lead_times[(u, v)] = 0.0
            elif nx.has_path(G, u, v):
                # Weight by edge lead time
                lead = nx.shortest_path_length(G, u, v, weight=lambda src, dst, d: d.get("lead", 1.0))
                lead_times[(u, v)] = float(lead)

    impacts: dict[str, CascadeNodeImpact] = {}

    for ev in events:
        sev = ev.severity
        start = ev.start if ev.start is not None else ev.start_day or 0
        duration = ev.duration if ev.duration is not None else ev.duration_days or 7

        is_demand_surge = ev.type in ("demand", "demand_surge")
        is_edge = ev.type in ("edge", "route_block")

        if is_edge:
            parts = ev.target.split("->")
            if len(parts) == 2:
                src_node, dst_node = parts[0].strip(), parts[1].strip()
                disrupted_origins = [dst_node]
            else:
                continue
        else:
            disrupted_origins = [ev.target]

        for orig in disrupted_origins:
            if orig not in G:
                continue

            # Downstream reachable nodes (including the node itself)
            downstream = [orig] + list(nx.descendants(G, orig))

            for n in downstream:
                ndata = G.nodes[n]
                kind = ndata.get("kind", "warehouse")
                stock = float(ndata.get("stock", 0.0))
                cap = float(ndata.get("capacity", 100.0) or 100.0)
                demand = float(ndata.get("demand", 0.0) or (cap if is_demand(kind) else cap * 0.8))

                transit_lead = lead_times.get((orig, n), 0.0)
                first_impact_day = int(round(start + transit_lead))

                if is_demand_surge:
                    # Multiplier: e.g. 1.45 means +45% surge
                    multiplier = sev if sev >= 1.0 else 1.0 + sev
                    surge_delta = max(multiplier - 1.0, 0.05)
                    net_burn_rate = max(demand * surge_delta, 1.0)
                    inventory_cover_days = stock / net_burn_rate
                    tts_days = round(first_impact_day + inventory_cover_days, 1)

                    # TTR for demand surge: duration + safety buffer replenishment lead
                    spare_headroom = max(cap * 0.15, 5.0)
                    refill_days = (net_burn_rate * duration) / spare_headroom
                    ttr_days = round(duration + min(refill_days, 14.0), 1)

                    status = "survives" if tts_days >= (first_impact_day + duration) else "fails"
                    reason = f"Demand surge +{int(round(surge_delta * 100))}% drains stock at {net_burn_rate:.1f} u/day"

                else:
                    # Capacity drop or freeze
                    effective_sev = min(sev, 1.0) if sev > 0 else 0.85
                    net_depletion_rate = max(demand * effective_sev, 1.0)
                    inventory_cover_days = stock / net_depletion_rate
                    tts_days = round(first_impact_day + inventory_cover_days, 1)

                    # TTR for supply disruption: duration + transit replenishment lead
                    replenishment_lead = float(transit_lead) if transit_lead > 0 else 2.0
                    ttr_days = round(duration + replenishment_lead, 1)

                    status = "survives" if tts_days >= (first_impact_day + duration) else "fails"
                    reason = (
                        f"Supply capacity reduced by {int(round(effective_sev * 100))}%; "
                        f"stock cover {inventory_cover_days:.1f} days"
                    )

                existing = impacts.get(n)
                if existing is None or tts_days < existing.tts_days:
                    impacts[n] = CascadeNodeImpact(
                        node=n,
                        name=ndata.get("name", n),
                        city=ndata.get("city", ""),
                        kind=kind,
                        first_impact_day=first_impact_day,
                        tts_days=tts_days,
                        ttr_days=ttr_days,
                        status=status,
                        mode="quick estimate",
                        reason=reason,
                    )

    # Sort downstream by first_impact_day ascending, then TTS ascending
    return sorted(impacts.values(), key=lambda x: (x.first_impact_day, x.tts_days))
