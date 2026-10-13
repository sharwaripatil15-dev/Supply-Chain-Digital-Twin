"""Where to sample hazards for each lane and site.

Each lane is sampled along the great-circle path between its endpoints, about every STEP_KM (at least MIN_POINTS,
at most MAX_POINTS points, endpoints included). Points are snapped to a GRID_DEG grid and deduplicated, so lanes that
share a corridor share API coordinates. Live data is capped at `max_cells` cells per refresh (fair use): if a network
needs more, sampling relaxes step by step (COARSENING: wider spacing along lanes first, then a coarser grid, up to 1
degree, and finally endpoints only) until it fits. Simulated scenarios make no API calls and always use the finest
sampling.

What each mode looks at:
    road  every hazard at every sample point
    rail  rain, flood and heat (plus earthquakes) at every sample point
    sea   waves (marine provider) and wind at every sample point
    air   wind and visibility at the two endpoints only (airports), not along the path
Sites are sampled at their own location; a site with a sea lane is treated as a port (waves count).
Lanes or sites without usable coordinates are reported with coverage "no_coordinates" and get no weather risk.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import networkx as nx

from node_types import haversine_km

STEP_KM = 75.0
MIN_POINTS = 2
MAX_POINTS = 8
GRID_DEG = 0.25
# (grid degrees, km between samples along a lane), tried in order until the cell count fits the cap
COARSENING = ((0.25, 75.0), (0.5, 75.0), (0.5, 150.0), (1.0, 150.0), (1.0, 300.0), (1.0, float("inf")))

Cell = tuple[float, float]


def has_coords(d: dict) -> bool:
    lat, lon = d.get("lat"), d.get("lon")
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)


def great_circle_points(a: tuple[float, float], b: tuple[float, float], step_km: float = STEP_KM,
                        min_points: int = MIN_POINTS, max_points: int = MAX_POINTS) -> list[tuple[float, float]]:
    """Evenly spaced (lat, lon) points from a to b along the great circle, endpoints included."""
    km = haversine_km(a, b)
    if km < 1e-6:
        return [a]
    n = max(min_points, min(max_points, math.ceil(km / step_km) + 1))
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    d = 2 * math.asin(math.sqrt(math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2))
    pts = []
    for i in range(n):
        f = i / (n - 1)
        A = math.sin((1 - f) * d) / math.sin(d)
        B = math.sin(f * d) / math.sin(d)
        x = A * math.cos(lat1) * math.cos(lon1) + B * math.cos(lat2) * math.cos(lon2)
        y = A * math.cos(lat1) * math.sin(lon1) + B * math.cos(lat2) * math.sin(lon2)
        z = A * math.sin(lat1) + B * math.sin(lat2)
        pts.append((math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))))
    return pts


def snap(lat: float, lon: float, grid: float = GRID_DEG) -> Cell:
    return (round(round(lat / grid) * grid, 4), round(round(lon / grid) * grid, 4))


def edge_mode(d: dict) -> str:
    mode = d.get("mode") or "road"
    return mode if mode in ("road", "rail", "sea", "air") else "road"


def port_nodes(G: nx.DiGraph) -> set[str]:
    """Sites that touch a sea lane, or are named/flagged as ports."""
    ports = {n for u, v, d in G.edges(data=True) if edge_mode(d) == "sea" for n in (u, v)}
    for n, d in G.nodes(data=True):
        name = f"{d.get('name') or ''} {d.get('city') or ''}".lower()
        if " port" in f" {name}" or (d.get("details") or {}).get("port"):
            ports.add(n)
    return ports


@dataclass
class SamplingPlan:
    grid: float
    step_km: float = STEP_KM
    edges: dict[str, dict] = field(default_factory=dict)  # "U->V" -> {mode, points:[(lat,lon)], cells:[cell], coverage}
    nodes: dict[str, dict] = field(default_factory=dict)  # id -> {cell, port, coverage}
    forecast_cells: list[Cell] = field(default_factory=list)
    flood_cells: list[Cell] = field(default_factory=list)
    marine_cells: list[Cell] = field(default_factory=list)

    @property
    def all_cells(self) -> list[Cell]:
        return sorted(set(self.forecast_cells) | set(self.flood_cells) | set(self.marine_cells))


def _edge_points(G: nx.DiGraph, step_km: float) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for u, v, d in G.edges(data=True):
        key = f"{u}->{v}"
        mode = edge_mode(d)
        a, b = G.nodes[u], G.nodes[v]
        if not (has_coords(a) and has_coords(b)):
            out[key] = {"mode": mode, "points": [], "coverage": "no_coordinates"}
            continue
        pa, pb = (float(a["lat"]), float(a["lon"])), (float(b["lat"]), float(b["lon"]))
        if haversine_km(pa, pb) < 1e-6:
            pts = [pa]
        elif mode == "air" or step_km == float("inf"):
            pts = [pa, pb]
        else:
            pts = great_circle_points(pa, pb, step_km)
        out[key] = {"mode": mode, "points": pts, "coverage": "full"}
    return out


def plan_sampling(G: nx.DiGraph, max_cells: int | None = 60) -> SamplingPlan:
    """Sample points per lane/site; with `max_cells`, relax sampling (COARSENING) until the cell count fits."""
    ports = port_nodes(G)
    raw_nodes = {
        n: ({"point": (float(d["lat"]), float(d["lon"])), "port": n in ports, "coverage": "full"} if has_coords(d)
            else {"point": None, "port": n in ports, "coverage": "no_coordinates"})
        for n, d in G.nodes(data=True)
    }

    plan = None
    for grid, step in (COARSENING if max_cells else COARSENING[:1]):
        raw_edges = _edge_points(G, step)
        plan = SamplingPlan(grid=grid, step_km=step)
        fc, fl, mc = set(), set(), set()
        for key, e in raw_edges.items():
            cells = list(dict.fromkeys(snap(*p, grid) for p in e["points"]))
            plan.edges[key] = {**e, "cells": cells}
            if e["mode"] == "sea":
                mc.update(cells)
                fc.update(cells)  # wind
            elif e["mode"] == "air":
                fc.update(cells)
            else:
                fc.update(cells)
                fl.update(cells)
        for n, info in raw_nodes.items():
            cell = snap(*info["point"], grid) if info["point"] else None
            plan.nodes[n] = {**info, "cell": cell}
            if cell:
                fc.add(cell)
                fl.add(cell)
                if info["port"]:
                    mc.add(cell)
        plan.forecast_cells, plan.flood_cells, plan.marine_cells = sorted(fc), sorted(fl), sorted(mc)
        if not max_cells or len(plan.all_cells) <= max_cells:
            break
    return plan
