"""Node kinds, tiers, legal lane directions and transport-mode defaults. The one place these are defined.

Demand nodes: retailers and customers are both demand sinks. Every engine module asks `is_demand(kind)` instead of
comparing against "customer", so a network may contain either, both, or a retailer that also ships on to customers.
The frontend mirror of this module is frontend/src/lib/nodeTypes.js; keep the two in step.
"""
from __future__ import annotations

import math
from typing import Literal, get_args

NodeKind = Literal["supplier", "factory", "warehouse", "retailer", "customer"]
KINDS: list[str] = list(get_args(NodeKind))
TIER: dict[str, int] = {k: i for i, k in enumerate(KINDS)}  # upstream -> downstream
DEMAND_KINDS = frozenset({"retailer", "customer"})
ID_PREFIX = {"supplier": "S", "factory": "F", "warehouse": "W", "retailer": "R", "customer": "C"}

# Lanes the builder accepts. Anything else is flagged as an illegal tier direction.
CORE_EDGES = frozenset({
    ("supplier", "factory"), ("factory", "warehouse"), ("warehouse", "retailer"),
    ("warehouse", "customer"), ("retailer", "customer"),
})
OPTIONAL_EDGES = frozenset({("supplier", "warehouse"), ("factory", "retailer"), ("factory", "customer")})
ALLOWED_EDGES = CORE_EDGES | OPTIONAL_EDGES

TransportMode = Literal["road", "rail", "sea", "air"]
MODES: list[str] = list(get_args(TransportMode))
# speed (km/day), fixed handling (days), CO2 (kg per unit-km), freight (INR per unit: base + per km).
# Road matches the preset generator (~450 km/day, 0.0026 kg/unit-km, 5 + 0.04/km).
MODE_DEFAULTS: dict[str, dict[str, float]] = {
    "road": {"speed": 450.0, "handling": 0.5, "co2_per_km": 0.0026, "base_cost": 5.0, "cost_per_km": 0.04},
    "rail": {"speed": 380.0, "handling": 1.0, "co2_per_km": 0.0011, "base_cost": 8.0, "cost_per_km": 0.025},
    "sea": {"speed": 350.0, "handling": 2.0, "co2_per_km": 0.0008, "base_cost": 12.0, "cost_per_km": 0.015},
    "air": {"speed": 4000.0, "handling": 0.5, "co2_per_km": 0.012, "base_cost": 20.0, "cost_per_km": 0.25},
}


# Builder fields that belong to one node type (everything else in BuilderNode is common to all five).
TYPE_FIELDS: dict[str, tuple[str, ...]] = {
    "supplier": ("material", "lead_time_days", "min_order_qty", "is_backup", "price_per_unit"),
    "factory": ("production_capacity", "production_cost", "overtime_limit_pct", "shifts_per_day"),
    "warehouse": ("storage_capacity", "safety_stock", "holding_cost", "handling_time_days"),
    "retailer": ("daily_demand", "demand_variability_pct", "service_level_pct", "shelf_stock"),
    "customer": ("daily_demand", "priority", "penalty_per_unit"),
}
ALL_TYPE_FIELDS: tuple[str, ...] = tuple(dict.fromkeys(f for fs in TYPE_FIELDS.values() for f in fs))


def is_demand(kind: str | None) -> bool:
    """True for demand sinks (retailers and customers)."""
    return kind in DEMAND_KINDS


def demand_nodes(G) -> list[str]:
    """Ids of every demand node in a NetworkX graph, in graph order."""
    return [n for n, d in G.nodes(data=True) if is_demand(d.get("kind"))]


def total_demand(G) -> float:
    return float(sum(d.get("demand", 0.0) or 0.0 for _, d in G.nodes(data=True) if is_demand(d.get("kind"))))


def edge_allowed(src_kind: str, dst_kind: str) -> bool:
    return (src_kind, dst_kind) in ALLOWED_EDGES


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in km between (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(min(1.0, h)))


def suggest_lead(mode: str, km: float) -> float:
    """Lead time in days for `km` by `mode`: distance / speed + handling, at least 1 day."""
    m = MODE_DEFAULTS.get(mode, MODE_DEFAULTS["road"])
    return max(1.0, round(km / m["speed"] + m["handling"], 1))


def suggest_co2(mode: str, km: float) -> float:
    """kg CO2 per unit shipped."""
    return round(km * MODE_DEFAULTS.get(mode, MODE_DEFAULTS["road"])["co2_per_km"], 2)


def suggest_cost(mode: str, km: float) -> float:
    """INR per unit shipped."""
    m = MODE_DEFAULTS.get(mode, MODE_DEFAULTS["road"])
    return round(m["base_cost"] + km * m["cost_per_km"], 1)
