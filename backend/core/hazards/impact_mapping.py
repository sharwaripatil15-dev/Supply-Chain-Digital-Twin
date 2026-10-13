"""Weather risk -> simulator inputs (ordinary disruption events).

IMPACT_TABLE (configurable; first matching row from the top):
    risk >= 0.85          closed: capacity x 0 (event severity 1)
    0.70 <= risk < 0.85   lead time x 2.2, capacity x 0.3
    0.50 <= risk < 0.70   lead time x 1.6, capacity x 0.6
    0.30 <= risk < 0.50   lead time x 1.2, capacity x 0.9
    risk < 0.30           no impact
Sites use the same capacity factors (a closed site is down); lead factors only apply to lanes.

Events: one per run of consecutive days in the same impact band (so a storm that builds and fades becomes several
events), with severity = 1 - capacity factor, lead_multiplier, source "weather", a reason (the worst day's drivers)
and a confidence that falls with forecast lead time: 1.0 today, -0.05 per day, never below 0.4, scaled by the mean
rain probability when rain drives the risk. Simulated scenarios use the same rule so demos read like forecasts.
"""
from __future__ import annotations

from schemas import Event

IMPACT_TABLE: list[dict] = [
    {"min_risk": 0.85, "lead": 1.0, "capacity": 0.0, "closed": True},
    {"min_risk": 0.70, "lead": 2.2, "capacity": 0.3, "closed": False},
    {"min_risk": 0.50, "lead": 1.6, "capacity": 0.6, "closed": False},
    {"min_risk": 0.30, "lead": 1.2, "capacity": 0.9, "closed": False},
]
LEVEL_MIN_RISK = {"moderate": 0.30, "high": 0.50, "severe": 0.70}
CONFIDENCE_DECAY = 0.05
CONFIDENCE_FLOOR = 0.4


def impact(risk: float) -> dict:
    """{lead_multiplier, capacity_multiplier, closed, band} for a risk value."""
    for i, row in enumerate(IMPACT_TABLE):
        if risk >= row["min_risk"]:
            return {"lead_multiplier": row["lead"], "capacity_multiplier": row["capacity"], "closed": row["closed"], "band": i}
    return {"lead_multiplier": 1.0, "capacity_multiplier": 1.0, "closed": False, "band": None}


def day_confidence(day: int, rain_prob: float | None = None, rain_driven: bool = False) -> float:
    conf = max(CONFIDENCE_FLOOR, 1.0 - CONFIDENCE_DECAY * day)
    if rain_driven and rain_prob is not None:
        conf *= max(0.5, rain_prob)
    return round(conf, 2)


def _runs(daily: list[dict], min_risk: float) -> list[tuple[int, int, int]]:
    """[(start, end inclusive, band)] for consecutive days at or above min_risk in the same impact band."""
    runs = []
    cur = None
    for i, d in enumerate(daily):
        band = impact(d["risk"])["band"] if d["risk"] >= min_risk else None
        if cur and band == cur[2] and band is not None:
            cur[1] = i
            continue
        if cur:
            runs.append(tuple(cur))
        cur = [i, i, band] if band is not None else None
    if cur:
        runs.append(tuple(cur))
    return runs


def events_from_risk(risk: dict, min_level: str = "high", include_nodes: bool = True, horizon: int | None = None) -> list[Event]:
    """Turn a /weather/risk payload into simulator events (edge events per lane; node events per supply-side site)."""
    min_risk = LEVEL_MIN_RISK.get(min_level, LEVEL_MIN_RISK["high"])
    out: list[Event] = []

    def make(kind: str, target: str, daily: list[dict], lane: bool):
        for start, end, band in _runs(daily, min_risk):
            row = IMPACT_TABLE[band]
            days = daily[start:end + 1]
            worst = max(days, key=lambda d: d["risk"])
            conf = round(sum(d.get("confidence", 1.0) for d in days) / len(days), 2)
            out.append(Event(
                type=kind, target=target, start=start, duration=end - start + 1,
                severity=round(1.0 - row["capacity"], 2), source="weather", confidence=conf,
                lead_multiplier=row["lead"] if lane and row["lead"] > 1 else None,
                reason=worst["reason"][:300],
            ))

    for e in risk.get("edges", []):
        if e.get("daily"):
            make("edge", e["id"], e["daily"][:horizon] if horizon else e["daily"], True)
    if include_nodes:
        for n in risk.get("nodes", []):
            if n.get("daily") and not n.get("demand_node"):
                make("node", n["id"], n["daily"][:horizon] if horizon else n["daily"], False)
    return out
