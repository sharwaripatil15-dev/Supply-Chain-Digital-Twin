"""Industry profiles, Indian city catalogue and transport-mode variability for the synthetic generator.

Every number here is an assumption, documented in data/synth_assumptions.md. Units: days, units/day, INR.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------- cities
#        name                lat     lon     region   port
CITIES: list[tuple[str, float, float, str, bool]] = [
    ("Mumbai", 19.08, 72.88, "west", True),
    ("Pune", 18.52, 73.86, "west", False),
    ("Ahmedabad", 23.02, 72.57, "west", False),
    ("Surat", 21.17, 72.83, "west", False),
    ("Vadodara", 22.31, 73.18, "west", False),
    ("Nashik", 19.99, 73.79, "west", False),
    ("Mundra", 22.84, 69.72, "west", True),
    ("Nagpur", 21.15, 79.09, "central", False),
    ("Indore", 22.72, 75.86, "central", False),
    ("Bhopal", 23.26, 77.41, "central", False),
    ("Raipur", 21.25, 81.63, "central", False),
    ("Delhi", 28.70, 77.10, "north", False),
    ("Gurugram", 28.46, 77.03, "north", False),
    ("Noida", 28.54, 77.39, "north", False),
    ("Jaipur", 26.91, 75.79, "north", False),
    ("Lucknow", 26.85, 80.95, "north", False),
    ("Kanpur", 26.45, 80.33, "north", False),
    ("Ludhiana", 30.90, 75.86, "north", False),
    ("Chandigarh", 30.73, 76.78, "north", False),
    ("Dehradun", 30.32, 78.03, "north", False),
    ("Kolkata", 22.57, 88.36, "east", True),
    ("Bhubaneswar", 20.30, 85.82, "east", False),
    ("Patna", 25.59, 85.14, "east", False),
    ("Jamshedpur", 22.80, 86.18, "east", False),
    ("Ranchi", 23.34, 85.31, "east", False),
    ("Visakhapatnam", 17.69, 83.22, "east", True),
    ("Guwahati", 26.14, 91.74, "east", False),
    ("Chennai", 13.08, 80.27, "south", True),
    ("Bengaluru", 12.97, 77.59, "south", False),
    ("Hyderabad", 17.39, 78.49, "south", False),
    ("Kochi", 9.93, 76.27, "south", True),
    ("Coimbatore", 11.02, 76.96, "south", False),
    ("Madurai", 9.93, 78.12, "south", False),
    ("Mangaluru", 12.91, 74.86, "south", True),
    ("Thiruvananthapuram", 8.52, 76.94, "south", False),
    ("Vijayawada", 16.51, 80.65, "south", False),
]
CITY = {c[0]: {"lat": c[1], "lon": c[2], "region": c[3], "port": c[4]} for c in CITIES}
REGIONS = ("north", "south", "east", "west", "central")
PORT_CITIES = [c for c, d in CITY.items() if d["port"]]


def region_of(city: str | None, lat: float | None = None, lon: float | None = None) -> str:
    """Region of a known city, else a coarse lat/lon rule (so uploaded networks get regions too)."""
    if city in CITY:
        return CITY[city]["region"]
    if lat is None or lon is None:
        return "other"
    if lat >= 25.5:
        return "north" if lon < 84 else "east"
    if lon >= 84:
        return "east"
    if lat < 17.5:
        return "south"
    return "west" if lon < 76 else "central"


# ---------------------------------------------------------------- transport modes
# Lead-time coefficient of variation by mode (std / mean); the per-lane value is this x U(0.8, 1.2).
MODE_LEAD_CV = {"road": 0.20, "rail": 0.25, "sea": 0.35, "air": 0.08}
MODE_MIN_KM = {"road": 0.0, "rail": 300.0, "sea": 0.0, "air": 500.0}  # sea also needs both ends in port cities


# ---------------------------------------------------------------- industries
@dataclass(frozen=True)
class IndustryProfile:
    key: str
    label: str
    unit_price: float  # INR per finished unit (revenue at risk)
    margin: float  # gross margin share of the price
    penalty_cost: float  # INR per unmet unit (lost margin + contractual / goodwill penalty)
    holding_cost: float  # INR per unit per day
    demand_median: float  # units/day per demand node (lognormal median)
    demand_sigma: float  # lognormal sigma across demand nodes
    demand_cv: float  # day-to-day demand volatility (coefficient of variation)
    cover_days: tuple[float, float]  # stock cover at demand nodes / warehouses, days (inside 3..30)
    shelf_life_days: float  # finished goods shelf life
    lead_mult: tuple[float, float]  # multiplies the distance-based lead time (handling, QA, cold-chain checks)
    modes: dict[str, float] = field(default_factory=dict)  # mode -> probability before feasibility rules
    festival_peak: float = 0.3  # demand uplift at the Diwali peak (Oct-Nov)
    monsoon_dip: float = -0.1  # demand change at the monsoon trough (Jul-Sep)
    demand_kind: str = "customer"  # demand nodes are B2B customers or retailers


INDUSTRIES: dict[str, IndustryProfile] = {
    "fmcg": IndustryProfile(
        "fmcg", "FMCG", unit_price=250, margin=0.18, penalty_cost=120, holding_cost=0.4, demand_median=420,
        demand_sigma=0.55, demand_cv=0.25, cover_days=(3, 12), shelf_life_days=180, lead_mult=(1.0, 1.15),
        modes={"road": 0.8, "rail": 0.2}, festival_peak=0.35, monsoon_dip=-0.10, demand_kind="retailer",
    ),
    "pharma": IndustryProfile(
        "pharma", "Pharma cold-chain", unit_price=1800, margin=0.35, penalty_cost=5000, holding_cost=6.0,
        demand_median=60, demand_sigma=0.5, demand_cv=0.12, cover_days=(10, 30), shelf_life_days=90,
        lead_mult=(1.1, 1.4), modes={"road": 0.6, "air": 0.3, "rail": 0.1}, festival_peak=0.05, monsoon_dip=0.10,
    ),
    "electronics": IndustryProfile(
        "electronics", "Electronics", unit_price=4200, margin=0.22, penalty_cost=1500, holding_cost=3.0,
        demand_median=150, demand_sigma=0.5, demand_cv=0.30, cover_days=(5, 20), shelf_life_days=720,
        lead_mult=(1.0, 1.2), modes={"road": 0.6, "rail": 0.15, "sea": 0.15, "air": 0.10}, festival_peak=0.45,
        monsoon_dip=-0.05,
    ),
    "automotive": IndustryProfile(
        "automotive", "Automotive", unit_price=9000, margin=0.15, penalty_cost=3500, holding_cost=5.0,
        demand_median=40, demand_sigma=0.45, demand_cv=0.15, cover_days=(3, 10), shelf_life_days=3650,
        lead_mult=(1.0, 1.1), modes={"road": 0.6, "rail": 0.3, "sea": 0.1}, festival_peak=0.30, monsoon_dip=-0.12,
    ),
    "apparel": IndustryProfile(
        "apparel", "Apparel", unit_price=900, margin=0.45, penalty_cost=300, holding_cost=0.8, demand_median=200,
        demand_sigma=0.6, demand_cv=0.35, cover_days=(10, 30), shelf_life_days=120, lead_mult=(1.0, 1.2),
        modes={"road": 0.7, "rail": 0.1, "sea": 0.2}, festival_peak=0.50, monsoon_dip=-0.15, demand_kind="retailer",
    ),
    "agri": IndustryProfile(
        "agri", "Agri / perishables", unit_price=60, margin=0.12, penalty_cost=40, holding_cost=1.5,
        demand_median=2000, demand_sigma=0.6, demand_cv=0.30, cover_days=(3, 6), shelf_life_days=7,
        lead_mult=(1.0, 1.1), modes={"road": 0.9, "rail": 0.1}, festival_peak=0.20, monsoon_dip=-0.25,
        demand_kind="retailer",
    ),
}
INDUSTRY_KEYS = list(INDUSTRIES)

ARCHETYPES = (
    "linear", "multi_source", "hub_spoke", "two_region_port", "backup_supplier", "concentrated", "long_tail",
)
ARCHETYPE_LABEL = {
    "linear": "Linear single-source",
    "multi_source": "Multi-source redundant",
    "hub_spoke": "Hub-and-spoke",
    "two_region_port": "Two-region shared port",
    "backup_supplier": "Backup supplier",
    "concentrated": "Concentrated (high HHI)",
    "long_tail": "Long-tail suppliers",
}


def seasonal_factor(profile: IndustryProfile, month: int) -> float:
    """Demand multiplier for a calendar month (1-12): festival peak in Oct-Nov, monsoon trough in Jul-Sep."""
    festival = {9: 0.35, 10: 1.0, 11: 0.8, 12: 0.2}.get(month, 0.0)
    monsoon = {6: 0.4, 7: 1.0, 8: 1.0, 9: 0.6}.get(month, 0.0)
    return round(1.0 + profile.festival_peak * festival + profile.monsoon_dip * monsoon, 4)


def bullwhip_ratio(lead_days: float, window: int = 7) -> float:
    """Lower bound of order-variance amplification for a moving-average forecast with window p and lead time L
    (Chen, Drezner, Ryan & Simchi-Levi 2000): Var(orders) / Var(demand) >= 1 + 2L/p + 2L^2/p^2."""
    L, p = max(0.0, lead_days), float(window)
    return 1.0 + 2 * L / p + 2 * L * L / (p * p)
