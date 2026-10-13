"""Delivery-delay estimation and bottleneck detection. Owner: A.

Delay model (implemented):
    For a day's flow solution, the arrival lead time of a node is the flow-weighted average of
    (upstream arrival lead + lane lead) over its inbound lanes; suppliers start at 0. This is exactly the mean
    path lead time of the units reaching that node when flow mixes proportionally at each node. Networks with a
    cycle (possible in an imported file) are walked in tier order instead; lanes that point back upstream are ignored.
    Extra delay for a demand node (retailer or customer) = its arrival lead under the disrupted flow - its arrival lead under the
    baseline (undisrupted) flow, i.e. the extra lead time caused by rerouting onto longer paths.
    Units that are not delivered at all are counted as unmet demand, not as delay.
    Weather slowdowns: edge events may carry a lead_multiplier; the lane's lead is multiplied by it on the days the
    event is active (`lead_mult` / `daily_lead`), so slower-but-open lanes show up as delay.

`delay_stats` aggregates over the disruption window: per-customer units-weighted mean, plus avg and P90
over every delivered unit. Possible extension: queueing delay when utilization > 1 (SimPy).
"""
from __future__ import annotations

from typing import Iterable, Mapping

import networkx as nx
import numpy as np

from node_types import TIER, demand_nodes

BOTTLENECK_THRESHOLD = 0.9

Flow = Mapping[tuple[str, str], float]


def arrival_lead(G: nx.DiGraph, flow: Flow, lead_mult: Mapping[tuple[str, str], float] | None = None) -> dict[str, float | None]:
    """Flow-weighted mean lead time (days) from suppliers to each node; None where nothing arrives.

    lead_mult: optional {(u, v): factor} applied to lane leads (weather slowdowns)."""
    lead_mult = lead_mult or {}
    lead: dict[str, float | None] = {}
    try:
        order = list(nx.topological_sort(G))
    except nx.NetworkXUnfeasible:  # cycle: fall back to tier order
        order = sorted(G, key=lambda n: (TIER.get(G.nodes[n].get("kind"), 99), str(n)))
    for n in order:
        inbound = [(u, flow.get((u, n), 0.0)) for u in G.predecessors(n)]
        inbound = [(u, f) for u, f in inbound if f > 0 and lead.get(u) is not None]
        if G.nodes[n]["kind"] == "supplier":
            lead[n] = 0.0
        elif inbound:
            total = sum(f for _, f in inbound)
            lead[n] = sum(f * (lead[u] + G.edges[u, n]["lead"] * lead_mult.get((u, n), 1.0)) for u, f in inbound) / total
        else:
            lead[n] = None
    return lead


def _customer_samples(G: nx.DiGraph, daily_flows: Iterable[Flow], base_lead: Mapping[str, float | None], daily_lead=None):
    """Yield (demand node, extra_days, units) per node-day with deliveries."""
    customers = demand_nodes(G)
    daily_flows = list(daily_flows)
    daily_lead = list(daily_lead or []) + [None] * (len(daily_flows) - len(daily_lead or []))
    for flow, mult in zip(daily_flows, daily_lead):
        lead = arrival_lead(G, flow, mult)
        for c in customers:
            units = sum(flow.get((u, c), 0.0) for u in G.predecessors(c))
            if units <= 0 or lead.get(c) is None:
                continue
            extra = max(0.0, lead[c] - (base_lead.get(c) or 0.0))
            yield c, extra, units


def customer_delays(G: nx.DiGraph, daily_flows: Iterable[Flow], base_lead: Mapping[str, float | None]) -> dict[str, float]:
    """{demand_node_id: units-weighted mean extra lead time in days} over the given days."""
    return delay_stats(G, daily_flows, base_lead)["per_customer"]


def delay_stats(G: nx.DiGraph, daily_flows: Iterable[Flow], base_lead: Mapping[str, float | None], daily_lead=None) -> dict:
    """{avg_days, p90_days, per_customer}: avg and P90 are over every delivered unit in `daily_flows`.

    per_customer covers every demand node (retailers and customers); the key name is the API contract.
    daily_lead: optional list (aligned with daily_flows) of {(u, v): lead factor} for weather slowdowns.
    """
    customers = demand_nodes(G)
    samples = list(_customer_samples(G, daily_flows, base_lead, daily_lead))
    per_customer = {}
    for c in customers:
        rows = [(e, w) for cc, e, w in samples if cc == c]
        wsum = sum(w for _, w in rows)
        per_customer[c] = round(sum(e * w for e, w in rows) / wsum, 2) if wsum else 0.0
    if not samples:
        return {"avg_days": 0.0, "p90_days": 0.0, "per_customer": per_customer}
    extra = np.array([e for _, e, _ in samples])
    weight = np.array([w for _, _, w in samples])
    order = np.argsort(extra)
    cum = np.cumsum(weight[order]) / weight.sum()
    p90 = float(extra[order][min(len(extra) - 1, int(np.searchsorted(cum, 0.9)))])
    return {
        "avg_days": round(float(np.average(extra, weights=weight)), 2),
        "p90_days": round(p90, 2),
        "per_customer": per_customer,
    }


def summarize_delays(per_customer: Mapping[str, float]) -> dict:
    """{avg_days, p90_days, per_customer} from per-customer delays (implemented)."""
    values = list(per_customer.values()) or [0.0]
    return {
        "avg_days": round(float(np.mean(values)), 2),
        "p90_days": round(float(np.percentile(values, 90)), 2),
        "per_customer": {k: round(float(v), 2) for k, v in per_customer.items()},
    }


def find_bottlenecks(timeline: Iterable[dict], threshold: float = BOTTLENECK_THRESHOLD) -> list[dict]:
    """Nodes whose utilization exceeds `threshold` on any day, with their peak and the peak day (implemented).

    Sorted by peak utilization, highest first.
    """
    peak: dict[str, tuple[float, int]] = {}
    for row in timeline:
        for node, u in row.get("utilization", {}).items():
            if u > threshold and u > peak.get(node, (0.0, 0))[0]:
                peak[node] = (u, row["day"])
    return [
        {"node": n, "utilization": round(u, 3), "day": d}
        for n, (u, d) in sorted(peak.items(), key=lambda kv: -kv[1][0])
    ]
