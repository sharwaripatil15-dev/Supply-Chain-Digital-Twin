"""Seeded disruption library: 13 disruption types -> ordinary core events (schemas.Event).

Every draw randomises start (uniform day 0..MAX_START), duration (lognormal around the type's median, sigma 0.5,
clipped to 1..horizon) and severity (a beta distribution per type). Regional types pick one region and hit every
matching site there, so failures are correlated the way storms and strikes are.

    type                 events                                                     duration median  severity
    supplier_outage      node event on one primary supplier                         12 d              1.0
    supplier_partial     node event on one primary supplier                         14 d              0.3 + 0.6 x Beta(4, 4)
    factory_breakdown    node event on one factory                                  8 d               1.0 (60%) else 0.5-0.9
    warehouse_shutdown   node event on one warehouse                                6 d               1.0 (70%) else 0.4-0.9
    route_blockage       edge event on one lane                                     5 d               1.0 (70%) else 0.4-0.9
    port_closure         port-city sites + sea lanes closed (falls back to a lane)  8 d               1.0
    demand_spike         demand up at 1-3 demand nodes in one region                10 d              Beta(2, 3) x 1.2 x volatility
    demand_drop          demand down at the demand nodes of one region              12 d              Beta(2, 5) x 0.7
    lead_time_inflation  1-3 lanes slowed (lead x U(1.3, 3.0)), small capacity loss 10 d              Beta(2, 8) x 0.4
    quality_recall       long partial outage at a supplier or factory               18 d              Beta(5, 3)
    strike               every factory and warehouse in one region                  6 d               0.8 x Beta(5, 2)
    weather_closure      sites and lanes in one region via the hazard impact table  4 d               risk ~ Beta(5, 2)
    compound             2-3 of the above in one region, starts within 3 days      per component     per component

Duration medians reflect reported disruption lengths (supplier and recall events typically run for weeks, weather and
lane closures for days); sigma = DURATION_SIGMA.

weather_closure reuses core.hazards.impact_mapping.impact(): a regional storm risk ~ Beta(5, 2) is perturbed per site
and lane (+-0.1), then mapped to capacity and lead-time factors exactly as forecast weather is in the app.
"""
from __future__ import annotations

import math

import networkx as nx
import numpy as np

from core.hazards.impact_mapping import impact
from core.synth.profiles import region_of
from node_types import is_demand
from schemas import Event

MAX_START = 10
DURATION_SIGMA = 0.5
MEDIAN_DAYS = {
    "supplier_outage": 12, "supplier_partial": 14, "factory_breakdown": 8, "warehouse_shutdown": 6,
    "route_blockage": 5, "port_closure": 8, "demand_spike": 10, "demand_drop": 12, "lead_time_inflation": 10,
    "quality_recall": 18, "strike": 6, "weather_closure": 4,
}
DISRUPTION_TYPES = [*MEDIAN_DAYS, "compound"]
COMPOUND_PARTS = ["supplier_outage", "factory_breakdown", "route_blockage", "weather_closure", "demand_spike", "strike",
                  "warehouse_shutdown", "lead_time_inflation"]


def _duration(kind: str, rng: np.random.Generator, horizon: int) -> int:
    return int(np.clip(round(rng.lognormal(math.log(MEDIAN_DAYS[kind]), DURATION_SIGMA)), 1, horizon))


def _pick(rng: np.random.Generator, items: list):
    return items[int(rng.integers(len(items)))] if items else None


def _region_of_node(G: nx.DiGraph, n: str) -> str:
    """The node's region attr (synthetic networks), else derived from its city or coordinates."""
    d = G.nodes[n]
    return d.get("region") or region_of(d.get("city"), d.get("lat"), d.get("lon"))


def _sites(G: nx.DiGraph, kind: str, region: str | None = None) -> list[str]:
    return sorted(n for n, d in G.nodes(data=True) if d["kind"] == kind and not d.get("backup")
                  and (region is None or _region_of_node(G, n) == region))


def _full_or_partial(rng: np.random.Generator, p_full: float, lo: float, hi: float) -> float:
    return 1.0 if rng.random() < p_full else round(lo + (hi - lo) * float(rng.beta(3, 3)), 3)


def sample_disruption(G: nx.DiGraph, rng: np.random.Generator, kind: str | None = None, horizon: int = 30,
                      region: str | None = None, start: int | None = None) -> dict:
    """One random disruption on G. Returns {type, events, start, duration, severity, region, targets}.

    `kind` None draws a type uniformly. A type the network cannot express (no port, no lane to slow) falls back to a
    route blockage, and the returned `type` says what was actually generated.
    """
    kind = kind or str(rng.choice(DISRUPTION_TYPES))
    start = int(rng.integers(0, MAX_START + 1)) if start is None else start
    if kind == "compound":
        return _compound(G, rng, horizon, start)
    dur = _duration(kind, rng, horizon)
    events: list[Event] = []
    node = lambda t, sev: events.append(Event(type="node", target=t, start=start, duration=dur, severity=round(sev, 3)))  # noqa: E731

    if kind in ("supplier_outage", "supplier_partial"):
        t = _pick(rng, _sites(G, "supplier", region)) or _pick(rng, _sites(G, "supplier"))
        if t is None:
            return sample_disruption(G, rng, "route_blockage", horizon, region, start)
        node(t, 1.0 if kind == "supplier_outage" else 0.3 + 0.6 * float(rng.beta(4, 4)))
        region = _region_of_node(G, t)
    elif kind in ("factory_breakdown", "warehouse_shutdown", "quality_recall"):
        pool_kind = {"factory_breakdown": "factory", "warehouse_shutdown": "warehouse"}.get(kind) or str(rng.choice(["supplier", "factory"]))
        t = _pick(rng, _sites(G, pool_kind, region)) or _pick(rng, _sites(G, pool_kind))
        if t is None:
            return sample_disruption(G, rng, "route_blockage", horizon, region, start)
        sev = {"factory_breakdown": lambda: _full_or_partial(rng, 0.6, 0.5, 0.9),
               "warehouse_shutdown": lambda: _full_or_partial(rng, 0.7, 0.4, 0.9),
               "quality_recall": lambda: float(rng.beta(5, 3))}[kind]()
        node(t, sev)
        region = _region_of_node(G, t)
    elif kind == "route_blockage":
        lanes = [(u, v) for u, v in G.edges if not G.nodes[u].get("backup")
                 and (region is None or region in (_region_of_node(G, u), _region_of_node(G, v)))] or [
                (u, v) for u, v in G.edges if not G.nodes[u].get("backup")]
        u, v = lanes[int(rng.integers(len(lanes)))]
        events.append(Event(type="edge", target=f"{u}->{v}", start=start, duration=dur, severity=_full_or_partial(rng, 0.7, 0.4, 0.9)))
        region = _region_of_node(G, v)
    elif kind == "port_closure":
        ports = [n for n, d in G.nodes(data=True) if d.get("port") and not is_demand(d["kind"]) and not d.get("backup")]
        sea = [(u, v) for u, v, d in G.edges(data=True) if d.get("mode") == "sea"]
        if not ports and not sea:
            out = sample_disruption(G, rng, "route_blockage", horizon, region, start)
            return out
        hub = _pick(rng, sorted(ports)) if ports else None
        if hub:
            node(hub, 1.0)
            region = _region_of_node(G, hub)
        for u, v in sea:
            if hub not in (u, v):
                events.append(Event(type="edge", target=f"{u}->{v}", start=start, duration=dur, severity=1.0))
        region = region or _region_of_node(G, sea[0][1])
    elif kind in ("demand_spike", "demand_drop"):
        dem = [n for n, d in G.nodes(data=True) if is_demand(d["kind"]) and (d.get("demand") or 0) > 0]
        region = region or _region_of_node(G, _pick(rng, dem))
        local = [n for n in dem if _region_of_node(G, n) == region] or dem
        if kind == "demand_spike":
            hit = sorted(rng.choice(local, size=min(len(local), int(rng.integers(1, 4))), replace=False))
            for c in hit:
                vol = math.sqrt((G.nodes[c].get("demand_cv") or 0.25) / 0.25)
                sev = float(np.clip(rng.beta(2, 3) * 1.2 * vol, 0.05, 1.0))
                events.append(Event(type="demand", target=str(c), start=start, duration=dur, severity=round(sev, 3)))
        else:
            sev = float(np.clip(rng.beta(2, 5) * 0.7, 0.03, 0.9))
            for c in sorted(local):
                events.append(Event(type="demand", target=c, start=start, duration=dur, severity=round(sev, 3), direction="down"))
    elif kind == "lead_time_inflation":
        lanes = [(u, v) for u, v in G.edges if not G.nodes[u].get("backup")]
        idx = rng.choice(len(lanes), size=min(len(lanes), int(rng.integers(1, 4))), replace=False)
        for i in sorted(idx):
            u, v = lanes[int(i)]
            events.append(Event(type="edge", target=f"{u}->{v}", start=start, duration=dur,
                                severity=round(float(rng.beta(2, 8) * 0.4), 3),
                                lead_multiplier=round(float(rng.uniform(1.3, 3.0)), 2)))
        region = _region_of_node(G, lanes[int(idx[0])][1])
    elif kind == "strike":
        regions = sorted({_region_of_node(G, n) for n, d in G.nodes(data=True) if d["kind"] in ("factory", "warehouse")})
        region = region if region in regions else _pick(rng, regions)
        sev = 0.8 * float(rng.beta(5, 2))
        for n in _sites(G, "factory", region) + _sites(G, "warehouse", region):
            node(n, sev)
        if not events:
            return sample_disruption(G, rng, "factory_breakdown", horizon, None, start)
    elif kind == "weather_closure":
        regions = sorted({_region_of_node(G, n) for n in G})
        region = region if region in regions else _pick(rng, regions)
        base = float(rng.beta(5, 2))
        for n, d in sorted(G.nodes(data=True)):
            if _region_of_node(G, n) != region or is_demand(d["kind"]) or d.get("backup"):
                continue
            imp = impact(float(np.clip(base + rng.uniform(-0.1, 0.1), 0, 1)))
            if imp["band"] is not None and imp["capacity_multiplier"] < 1:
                node(n, 1.0 - imp["capacity_multiplier"])
        for u, v in sorted(G.edges):
            if region not in (_region_of_node(G, u), _region_of_node(G, v)) or G.nodes[u].get("backup"):
                continue
            imp = impact(float(np.clip(base + rng.uniform(-0.1, 0.1), 0, 1)))
            if imp["band"] is None:
                continue
            lead = imp["lead_multiplier"] if imp["lead_multiplier"] > 1 else None
            events.append(Event(type="edge", target=f"{u}->{v}", start=start, duration=dur,
                                severity=round(1.0 - imp["capacity_multiplier"], 3), lead_multiplier=lead))
        if not events:  # calm draw: the storm missed every site; keep one slowed lane so the case is not empty
            return sample_disruption(G, rng, "lead_time_inflation", horizon, region, start)
    else:
        raise ValueError(f"unknown disruption type {kind!r}")
    return _pack(kind, events, region)


def _compound(G: nx.DiGraph, rng: np.random.Generator, horizon: int, start: int) -> dict:
    """2-3 correlated disruptions in one region, starting within 3 days of each other."""
    regions = sorted({_region_of_node(G, n) for n, d in G.nodes(data=True) if not is_demand(d["kind"])})
    region = _pick(rng, regions)
    parts = rng.choice(COMPOUND_PARTS, size=int(rng.integers(2, 4)), replace=False)
    events: list[Event] = []
    for i, p in enumerate(parts):
        sub = sample_disruption(G, rng, str(p), horizon, region, min(horizon - 1, start + (0 if i == 0 else int(rng.integers(0, 4)))))
        events.extend(sub["events"])
    return _pack("compound", events, region, parts=[str(p) for p in parts])


def _pack(kind: str, events: list[Event], region: str | None, parts: list[str] | None = None) -> dict:
    start = min(e.start for e in events)
    end = max(e.start + e.duration for e in events)
    return {
        "type": kind, "events": events, "start": start, "duration": end - start,
        "severity": max(e.severity for e in events), "region": region or "other",
        "targets": sorted({e.target for e in events}), "parts": parts or [kind],
    }


def infer_type(G: nx.DiGraph, events: list[Event]) -> str:
    """Best-matching library type for user-built events (used by the surrogate's features)."""
    kinds = set()
    for e in events:
        if e.type == "demand":
            kinds.add("demand_drop" if getattr(e, "direction", None) == "down" else "demand_spike")
        elif e.type == "edge":
            if getattr(e, "source", None) == "weather":
                kinds.add("weather_closure")
            elif e.lead_multiplier and e.severity < 0.5:
                kinds.add("lead_time_inflation")
            else:
                kinds.add("route_blockage")
        elif e.target in G:
            k = G.nodes[e.target]["kind"]
            if getattr(e, "source", None) == "weather":
                kinds.add("weather_closure")
            elif k == "supplier":
                kinds.add("supplier_outage" if e.severity >= 0.95 else "supplier_partial")
            elif k == "factory":
                kinds.add("factory_breakdown")
            elif k == "warehouse":
                kinds.add("warehouse_shutdown")
            else:
                kinds.add("demand_drop")
    if len(kinds) == 1:
        return kinds.pop()
    if kinds == {"weather_closure"} or not kinds:
        return "weather_closure" if kinds else "route_blockage"
    return "compound"
