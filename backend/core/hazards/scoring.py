"""Explainable weather risk for lanes and sites.

Each hazard becomes a component score in 0..1 by piecewise-linear interpolation between documented thresholds:

    hazard  input                       thresholds (value -> score)                                  source of cut-offs
    rain    24 h rainfall, mm           7.5 -> 0, 35.5 -> 0.2, 64.5 -> 0.5 (heavy),                  IMD rainfall categories
                                        115.5 -> 0.75 (very heavy), 204.5 -> 1.0 (extremely heavy)
    flood   river discharge / mean      1.5 -> 0, 2 -> 0.4, 3 -> 0.7, 5 -> 1.0                       GloFAS-style return ratios
    wind    max gust, km/h              40 -> 0, 60 -> 0.5 (risky), 90 -> 0.8 (severe), 120 -> 1.0   Beaufort 8+ / cyclone gusts
    fog     visibility, m (lower=worse) 1000 -> 0, 500 -> 0.3, 200 -> 0.6 (dense fog), 100 -> 0.8,    IMD fog categories
                                        50 -> 0.9
    heat    max temperature, C          40 -> 0, 44 -> 0.3, 47 -> 0.6, 50 -> 0.8                     IMD heatwave (40 C+)
    wave    max wave height, m          2 -> 0, 3 -> 0.35, 4 -> 0.7 (ports restrict), 5 -> 0.85,     port operating limits
                                        6 -> 1.0
    quake   magnitude M at distance d   score(M) = 4.5 -> 0, 5.5 -> 0.6, 6 -> 0.8, 7 -> 1.0, times    M5.5+ within 150 km
                                        (1 - d / R) with R = 150 km x 10^(0.5 (M - 5.5))
    (Rain probability is not multiplied in: it lowers the forecast confidence instead, see impact_mapping.)

Mode sensitivity (how much each hazard matters for a lane of that mode, or a site) multiplies the components:

    mode   rain  flood wind  fog   heat  wave  quake
    road   1.0   1.0   0.7   1.0   0.5   0     1.0
    rail   0.7   1.0   0     0     1.0   0     1.0      (rail: rain / flood / heat only, plus track damage from quakes)
    sea    0     0     0.8   0     0     1.0   0        (marine provider: waves, plus wind)
    air    0     0     1.0   1.0   0     0     0        (endpoints only: wind and visibility)
    site   0.8   1.0   0.6   0     0.3   0     1.0      (a flooded or shaken plant; fog does not stop a site)
    port   0.6   0.8   1.0   0     0     1.0   1.0      (a site with a sea lane)

Along a lane each hazard takes its worst sample point that day. Combined risk = the largest weighted component plus a
quarter of the mean of the other six (so compound hazards rank above a single one), capped at 1.
Levels: low < 0.3 <= moderate < 0.5 <= high < 0.7 <= severe. Closed is decided by impact_mapping (risk >= 0.85).
`drivers` lists the top two weighted components with their raw values; `reason` is a plain-English sentence.
"""
from __future__ import annotations

from typing import Iterable

from core.hazards.providers import HazardSample

HAZARDS = ("rain", "flood", "wind", "fog", "heat", "wave", "quake")

THRESHOLDS: dict[str, list[tuple[float, float]]] = {
    "rain": [(7.5, 0.0), (35.5, 0.2), (64.5, 0.5), (115.5, 0.75), (204.5, 1.0)],
    "flood": [(1.5, 0.0), (2.0, 0.4), (3.0, 0.7), (5.0, 1.0)],
    "wind": [(40.0, 0.0), (60.0, 0.5), (90.0, 0.8), (120.0, 1.0)],
    "fog": [(50.0, 0.9), (100.0, 0.8), (200.0, 0.6), (500.0, 0.3), (1000.0, 0.0)],  # ascending visibility
    "heat": [(40.0, 0.0), (44.0, 0.3), (47.0, 0.6), (50.0, 0.8)],
    "wave": [(2.0, 0.0), (3.0, 0.35), (4.0, 0.7), (5.0, 0.85), (6.0, 1.0)],
    "quake_mag": [(4.5, 0.0), (5.5, 0.6), (6.0, 0.8), (7.0, 1.0)],
}
QUAKE_BASE_RADIUS_KM = 150.0
OTHERS_WEIGHT = 0.25

MODE_SENSITIVITY: dict[str, dict[str, float]] = {
    "road": {"rain": 1.0, "flood": 1.0, "wind": 0.7, "fog": 1.0, "heat": 0.5, "wave": 0.0, "quake": 1.0},
    "rail": {"rain": 0.7, "flood": 1.0, "wind": 0.0, "fog": 0.0, "heat": 1.0, "wave": 0.0, "quake": 1.0},
    "sea": {"rain": 0.0, "flood": 0.0, "wind": 0.8, "fog": 0.0, "heat": 0.0, "wave": 1.0, "quake": 0.0},
    "air": {"rain": 0.0, "flood": 0.0, "wind": 1.0, "fog": 1.0, "heat": 0.0, "wave": 0.0, "quake": 0.0},
    "site": {"rain": 0.8, "flood": 1.0, "wind": 0.6, "fog": 0.0, "heat": 0.3, "wave": 0.0, "quake": 1.0},
    "port": {"rain": 0.6, "flood": 0.8, "wind": 1.0, "fog": 0.0, "heat": 0.0, "wave": 1.0, "quake": 1.0},
}
LEVELS = (("low", 0.0), ("moderate", 0.3), ("high", 0.5), ("severe", 0.7))
LEVEL_RANK = {name: i for i, (name, _) in enumerate(LEVELS)}
UNITS = {"rain": "mm/day", "flood": "x normal flow", "wind": "km/h gusts", "fog": "m visibility", "heat": "°C",
         "wave": "m waves", "quake": "M"}


def interp(x: float | None, points: list[tuple[float, float]]) -> float:
    """Piecewise-linear lookup, flat beyond the first and last breakpoints."""
    if x is None:
        return 0.0
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def quake_score(magnitude: float | None, distance_km: float | None) -> float:
    if magnitude is None or distance_km is None:
        return 0.0
    radius = QUAKE_BASE_RADIUS_KM * 10 ** (0.5 * (magnitude - 5.5))
    return interp(magnitude, THRESHOLDS["quake_mag"]) * max(0.0, 1.0 - distance_km / radius)


def components(s: HazardSample) -> dict[str, float]:
    """Raw (mode-independent) component scores for one sample."""
    return {
        "rain": interp(s.rain_mm, THRESHOLDS["rain"]),
        "flood": interp(s.river_discharge_ratio, THRESHOLDS["flood"]),
        "wind": interp(s.wind_gust_kmh, THRESHOLDS["wind"]),
        "fog": interp(s.visibility_m, THRESHOLDS["fog"]) if s.visibility_m is not None else 0.0,
        "heat": interp(s.temp_c, THRESHOLDS["heat"]),
        "wave": interp(s.wave_height_m, THRESHOLDS["wave"]),
        "quake": quake_score(s.quake_magnitude, s.quake_distance_km),
    }


def _raw_value(s: HazardSample, hazard: str):
    return {
        "rain": s.rain_mm, "flood": s.river_discharge_ratio, "wind": s.wind_gust_kmh, "fog": s.visibility_m,
        "heat": s.temp_c, "wave": s.wave_height_m, "quake": s.quake_magnitude,
    }[hazard]


def level_of(risk: float) -> str:
    name = "low"
    for lvl, lo in LEVELS:
        if risk >= lo:
            name = lvl
    return name


def _phrase(hazard: str, value) -> str:
    if value is None:
        return hazard
    if hazard == "rain":
        word = ("extremely heavy" if value >= 204.5 else "very heavy" if value >= 115.6 else "heavy" if value >= 64.5
                else "rather heavy" if value >= 35.6 else "moderate")
        return f"{word} rain ({value:.0f} mm/day)"
    if hazard == "flood":
        return f"river flow at {value:.1f}x normal"
    if hazard == "wind":
        return f"gusts of {value:.0f} km/h"
    if hazard == "fog":
        return f"{'dense ' if value < 200 else ''}fog ({value:.0f} m visibility)"
    if hazard == "heat":
        return f"heat ({value:.0f} °C)"
    if hazard == "wave":
        return f"{value:.1f} m waves"
    if hazard == "quake":
        return f"M{value:.1f} earthquake"
    return hazard


def score(samples: Iterable[HazardSample], mode: str, where: str = "along the route") -> dict:
    """Risk for one lane (or site) on one day from its sample points. Returns
    {risk, level, components, drivers:[{hazard, score, value, unit}], reason}."""
    samples = [s for s in samples if s is not None]
    sens = MODE_SENSITIVITY.get(mode, MODE_SENSITIVITY["road"])
    weighted = {h: 0.0 for h in HAZARDS}
    worst: dict[str, HazardSample] = {}
    for s in samples:
        comp = components(s)
        for h in HAZARDS:
            w = comp[h] * sens[h]
            if w > weighted[h]:
                weighted[h], worst[h] = w, s
    ranked = sorted(HAZARDS, key=lambda h: -weighted[h])
    top = weighted[ranked[0]]
    others = sum(weighted[h] for h in ranked[1:]) / (len(HAZARDS) - 1)
    risk = round(min(1.0, top + OTHERS_WEIGHT * others), 3)
    drivers = []
    for h in ranked[:2]:
        if weighted[h] < 0.05:
            continue
        value = _raw_value(worst[h], h)
        drivers.append({"hazard": h, "score": round(weighted[h], 3), "value": None if value is None else round(float(value), 1),
                        "unit": UNITS[h]})
    level = level_of(risk)
    if not drivers:
        reason = "No significant weather or hazard expected."
    else:
        text = " and ".join(_phrase(d["hazard"], d["value"]) for d in drivers)
        reason = f"{text[0].upper()}{text[1:]} {where}."
    return {"risk": risk, "level": level, "components": {h: round(v, 3) for h, v in weighted.items()}, "drivers": drivers,
            "reason": reason}
