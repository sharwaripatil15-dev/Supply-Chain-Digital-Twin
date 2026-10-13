"""Weather assessment for any network: sampling plan -> samples (live providers or a simulated scenario) -> scores.

`assess` returns the GET /weather/risk payload. It never raises for provider trouble: partial provider failures give
partial results plus warnings, and the overall data_quality is
    live         every provider that was needed answered now
    cached       at least one answer came from the cache (the provider failed or USE_MOCK_WEATHER is on)
    simulated    a built-in hazard scenario is active, or nothing live or cached exists while offline by design
                 (USE_MOCK_WEATHER=true): calm weather is used so the views still render
    unavailable  the providers failed and nothing is cached: calm weather is used, with a warning
The active simulated scenario is part of the persisted weather state (DATA_DIR/weather_state.json).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import networkx as nx

from config import settings
from core.hazards import providers as prov
from core.hazards import simulated as sim_hz
from core.hazards.impact_mapping import day_confidence, impact
from core.hazards.providers import IST, HazardSample
from core.hazards.route_sampling import edge_mode, has_coords, plan_sampling, SamplingPlan
from core.hazards.scoring import score
from node_types import haversine_km, is_demand

log = logging.getLogger("aegis.weather")

MAX_HORIZON = 16
QUAKE_FELT_DAYS = 2
STATE_FILE = "weather_state.json"
QUALITY_RANK = {"live": 0, "cached": 1, "simulated": 2, "unavailable": 3}


# ------------------------------------------------------------------ persisted state
class WeatherState:
    """Active simulated scenario + the last weather events applied to the scenario (so they can be cleared)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.scenario_id: str | None = None
        self.applied: list[dict] = []
        self.last_live_fetch: float = 0.0
        self._loaded_from: Path | None = None

    def _path(self) -> Path:
        return Path(settings.data_dir) / STATE_FILE

    def load(self) -> None:
        path = self._path()
        if self._loaded_from == path:
            return
        self._loaded_from = path
        self.scenario_id, self.applied = None, []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            sid = raw.get("scenario_id")
            self.scenario_id = sid if sid and sim_hz.get_scenario(sid) else None
            self.applied = list(raw.get("applied") or [])
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        path = self._path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"scenario_id": self.scenario_id, "applied": self.applied}), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            log.info("weather: could not persist state (%s)", exc)

    def set_scenario(self, scenario_id: str | None) -> None:
        with self._lock:
            self.load()
            self.scenario_id = scenario_id
            self.save()

    def set_applied(self, events: list[dict]) -> None:
        with self._lock:
            self.load()
            self.applied = events
            self.save()


state = WeatherState()


# ------------------------------------------------------------------ samples
def _today() -> date:
    return datetime.now(tz=IST).date()


def _calm(plan: SamplingPlan, days: int, today: date, quality: str) -> dict:
    field = sim_hz.ScenarioField({"id": "calm", "seed": 1, "days": days, "anchors": {}, "hazards": []}, nx.DiGraph())
    out = {}
    for cell in plan.all_cells:
        rows = [field.sample(cell[0], cell[1], d, today) for d in range(days)]
        for r in rows:
            r.quality, r.source = quality, "calm baseline"
        out[cell] = rows
    return out


def simulated_samples(plan: SamplingPlan, G: nx.DiGraph, fx: dict, days: int, today: date):
    field = sim_hz.ScenarioField(fx, G)
    samples = {cell: [field.sample(cell[0], cell[1], d, today) for d in range(days)] for cell in plan.all_cells}
    marine = set(plan.marine_cells)
    for cell, rows in samples.items():
        if cell not in marine:
            for r in rows:
                r.wave_height_m = None  # waves only matter (and are only "measured") at sea and at ports
    return samples, field


async def live_samples(plan: SamplingPlan, days: int, today: date, force: bool):
    """Merge the providers into {cell: [HazardSample per day]}. Returns (samples, quality per provider, warnings, extras)."""
    warnings: list[str] = []
    quality: dict[str, str] = {}
    forecast, quality["forecast"], err = await prov.fetch_forecast(plan.forecast_cells, days, force) if plan.forecast_cells else ({}, "live", None)
    if err:
        warnings.append(f"Forecast: {err}")
    flood, quality["flood"], err = await prov.fetch_flood(plan.flood_cells, days, force) if plan.flood_cells else ({}, "live", None)
    if err:
        warnings.append(f"Flood data unavailable for some locations ({err}); flood risk is not included there.")
    marine, quality["marine"], err = await prov.fetch_marine(plan.marine_cells, days, force) if plan.marine_cells else ({}, "live", None)
    if err:
        warnings.append(f"Marine data unavailable ({err}); wave risk is not included.")
    quakes, quality["quakes"], err = await prov.fetch_quakes(force)
    if err:
        warnings.append(f"Earthquake feed unavailable ({err}).")
    cyclones = await prov.fetch_gdacs(force)

    dates = [(today + timedelta(days=d)).isoformat() for d in range(days)]
    samples: dict = {}
    for cell in plan.all_cells:
        by_date = {s.date: s for s in forecast.get(cell, [])}
        rows = []
        for d, ds in enumerate(dates):
            s = by_date.get(ds)
            s = HazardSample(**{**s.to_dict()}) if s else HazardSample(lat=cell[0], lon=cell[1], date=ds, quality="unavailable")
            s.quality = quality["forecast"] if ds in by_date else "unavailable"
            s.river_discharge_ratio = flood.get(cell, {}).get(ds)
            s.wave_height_m = marine.get(cell, {}).get(ds)
            for q in quakes:
                qd = (date.fromisoformat(q["date"]) - today).days
                if 0 <= d - qd < QUAKE_FELT_DAYS:
                    dist = haversine_km(cell, (q["lat"], q["lon"]))
                    if s.quake_magnitude is None or q["magnitude"] > s.quake_magnitude:
                        s.quake_magnitude, s.quake_distance_km = q["magnitude"], round(dist, 1)
            rows.append(s)
        samples[cell] = rows
    return samples, quality, warnings, {"quakes": quakes, "cyclones": cyclones}


# ------------------------------------------------------------------ assessment
def _overall_quality(qualities: list[str]) -> str:
    if not qualities:
        return "live"
    worst = max(qualities, key=lambda q: QUALITY_RANK.get(q, 3))
    if worst == "partial":
        return "cached"
    return worst


def _daily_rows(sample_rows: list[list[HazardSample]], mode: str, days: int, dates: list[str], where: str) -> list[dict]:
    out = []
    for d in range(days):
        day_samples = [rows[d] for rows in sample_rows if d < len(rows) and rows[d].quality != "unavailable"]
        sc = score(day_samples, mode, where)
        imp = impact(sc["risk"])
        rain_driven = bool(sc["drivers"]) and sc["drivers"][0]["hazard"] == "rain"
        prob = max((s.rain_prob or 0.0) for s in day_samples) if day_samples else None
        out.append({
            "day": d, "date": dates[d], "risk": sc["risk"], "level": sc["level"], "closed": imp["closed"],
            "drivers": sc["drivers"], "reason": sc["reason"], "components": sc["components"],
            "lead_multiplier": imp["lead_multiplier"], "capacity_multiplier": imp["capacity_multiplier"],
            "confidence": day_confidence(d, prob, rain_driven),
            "measured": bool(day_samples),
        })
    return out


def score_graph(G: nx.DiGraph, plan: SamplingPlan, samples: dict, days: int, dates: list[str]) -> tuple[list[dict], list[dict]]:
    edges = []
    for u, v, d in G.edges(data=True):
        key = f"{u}->{v}"
        info = plan.edges.get(key, {"mode": edge_mode(d), "cells": [], "coverage": "no_coordinates"})
        rows = [samples[c] for c in info["cells"] if c in samples]
        daily = _daily_rows(rows, info["mode"], days, dates, "along the route") if info["coverage"] == "full" else []
        worst = max(daily, key=lambda r: r["risk"]) if daily else None
        edges.append({
            "id": key, "lane_id": d.get("id"), "source": u, "target": v, "mode": info["mode"], "coverage": info["coverage"],
            "distance_km": d.get("distance_km") or (round(haversine_km((G.nodes[u]["lat"], G.nodes[u]["lon"]), (G.nodes[v]["lat"], G.nodes[v]["lon"])), 1)
                                                    if has_coords(G.nodes[u]) and has_coords(G.nodes[v]) else None),
            "daily": daily, "max_risk": worst["risk"] if worst else 0.0, "max_level": worst["level"] if worst else "low",
            "worst_day": worst["day"] if worst else None, "samples": len(info["cells"]),
        })
    nodes = []
    for n, d in G.nodes(data=True):
        info = plan.nodes.get(n, {"cell": None, "port": False, "coverage": "no_coordinates"})
        mode = "port" if info["port"] else "site"
        daily = (_daily_rows([samples[info["cell"]]], mode, days, dates, f"at {d.get('city') or n}")
                 if info["cell"] in samples else [])
        worst = max(daily, key=lambda r: r["risk"]) if daily else None
        nodes.append({
            "id": n, "name": d.get("name"), "city": d.get("city"), "kind": d.get("kind"), "port": info["port"],
            "demand_node": is_demand(d.get("kind")), "coverage": info["coverage"], "daily": daily,
            "max_risk": worst["risk"] if worst else 0.0, "max_level": worst["level"] if worst else "low",
            "worst_day": worst["day"] if worst else None,
        })
    return edges, nodes


def _live_hotspots(plan: SamplingPlan, samples: dict, days: int, extras: dict) -> list[dict]:
    """Map features from live data: hazard cells (rain, wind, fog, heat, flood, waves), quake rings, cyclone points."""
    from core.hazards.scoring import components

    feats: dict[tuple, dict] = {}
    radius = max(25.0, plan.grid * 111 * 0.6)
    for cell, rows in samples.items():
        for d, s in enumerate(rows[:days]):
            if s.quality == "unavailable":
                continue
            for h, v in components(s).items():
                if h == "quake" or v < 0.3:
                    continue
                kind = {"rain": "rain", "flood": "flood", "wind": "wind", "fog": "fog", "heat": "heat", "wave": "wave"}[h]
                f = feats.setdefault((kind, cell), {
                    "id": f"{kind}-{cell[0]}-{cell[1]}", "type": kind, "label": kind.title(),
                    "daily": [{"day": i, "lat": cell[0], "lon": cell[1], "radius_km": round(radius), "intensity": 0.0, "value": None}
                              for i in range(days)],
                })
                f["daily"][d]["intensity"] = round(v, 2)
                f["daily"][d]["value"] = {"rain": f"{s.rain_mm:.0f} mm/day" if s.rain_mm is not None else None,
                                          "flood": f"{s.river_discharge_ratio:.1f}x normal river flow" if s.river_discharge_ratio else None,
                                          "wind": f"{s.wind_gust_kmh:.0f} km/h gusts" if s.wind_gust_kmh is not None else None,
                                          "fog": f"{s.visibility_m:.0f} m visibility" if s.visibility_m is not None else None,
                                          "heat": f"{s.temp_c:.0f} °C" if s.temp_c is not None else None,
                                          "wave": f"{s.wave_height_m:.1f} m waves" if s.wave_height_m is not None else None}[kind]
    out = list(feats.values())
    today = _today()
    for i, q in enumerate(extras.get("quakes", [])):
        qd = (date.fromisoformat(q["date"]) - today).days
        r = 150.0 * 10 ** (0.5 * (q["magnitude"] - 5.5))
        out.append({"id": f"quake-{i}", "type": "quake", "label": f"M{q['magnitude']:.1f} earthquake", "place": q.get("place"),
                    "daily": [{"day": d, "lat": q["lat"], "lon": q["lon"], "radius_km": round(r),
                               "intensity": round(min(1.0, max(0.0, (q["magnitude"] - 4.5) / 2.5)), 2) if 0 <= d - qd < QUAKE_FELT_DAYS else 0.0,
                               "value": f"M{q['magnitude']:.1f}"} for d in range(days)]})
    for i, c in enumerate(extras.get("cyclones", [])):
        out.append({"id": f"cyclone-{i}", "type": "cyclone", "label": c["name"], "alert": c.get("alert"),
                    "daily": [{"day": d, "lat": c["lat"], "lon": c["lon"], "radius_km": 150, "intensity": 0.8 if d == 0 else 0.5,
                               "value": f"GDACS {c.get('alert') or ''} alert".strip()} for d in range(days)]})
    return out


def _hotspot_points(features: list[dict]) -> list[dict]:
    """Flat list for /weather/risk: each feature at its peak day."""
    out = []
    for f in features:
        peak = max(f["daily"], key=lambda r: r["intensity"]) if f["daily"] else None
        if not peak or peak["intensity"] <= 0 or peak["lat"] is None:
            continue
        out.append({"lat": round(peak["lat"], 3), "lon": round(peak["lon"], 3), "type": f["type"], "severity": peak["intensity"],
                    "day": peak["day"], "radius_km": peak["radius_km"], "label": f"{f['label']}" + (f" ({peak['value']})" if peak.get("value") else "")})
    return sorted(out, key=lambda h: -h["severity"])


async def assess(G: nx.DiGraph, horizon: int = 7, force: bool = False, scenario_id: str | None = "__state__") -> dict:
    """GET /weather/risk payload (plus private keys "_samples" and "_plan" used by re-routing; strip before sending)."""
    state.load()
    horizon = max(1, min(MAX_HORIZON, int(horizon)))
    sid = state.scenario_id if scenario_id == "__state__" else scenario_id
    fx = sim_hz.get_scenario(sid) if sid else None
    today = _today()
    plan = plan_sampling(G, None if fx is not None else settings.weather_max_cells)  # simulated: no API cost
    warnings: list[str] = []
    notes: list[str] = []
    mapping: list[dict] = []
    providers_quality: dict[str, str] = {}
    hazards: list[dict] = []
    days = horizon

    if fx is not None:
        samples, field = simulated_samples(plan, G, fx, days, today)
        data_quality = "simulated"
        mapping = field.mapping
        hazards = [f for f in field.overlays()]
        for f in hazards:  # pad/trim the scenario's days to the horizon
            f["daily"] = (f["daily"] + [{**f["daily"][-1], "day": d, "intensity": 0.0, "value": None} for d in range(len(f["daily"]), days)])[:days] if f["daily"] else []
        notes.append(f"Simulated scenario: {fx['label']}.")
    elif not plan.all_cells:
        samples, data_quality = {}, "live"
        notes.append("No located sites or lanes to assess.")
    else:
        if force and time.time() - state.last_live_fetch < settings.weather_min_refresh_s:
            force = False
            notes.append("Refreshed less than 10 minutes ago; serving the cached forecast (fair use).")
        samples, providers_quality, warnings, extras = await live_samples(plan, days, today, force)
        if any(q in ("live", "partial") for q in providers_quality.values()):
            state.last_live_fetch = time.time()
        fq = providers_quality.get("forecast", "unavailable")
        if fq == "unavailable":
            data_quality = "simulated" if settings.mock_weather else "unavailable"
            samples = _calm(plan, days, today, data_quality)
            warnings.insert(0, "No live or cached forecast is available; showing calm baseline weather, so lane risks are not real. "
                               "Pick a simulated scenario to demo the hazards." if not settings.mock_weather else
                            "Live weather is switched off (USE_MOCK_WEATHER=true) and nothing is cached; showing calm baseline weather.")
        else:
            # providers that answered set the quality; ones that failed are reported as warnings (partial results)
            data_quality = _overall_quality([q for q in providers_quality.values() if q != "unavailable"])
            if fq == "partial":
                warnings.insert(0, "Part of the forecast could not be fetched; affected lanes show no weather risk.")
            hazards = _live_hotspots(plan, samples, days, extras)

    dates = [(today + timedelta(days=d)).isoformat() for d in range(days)]
    edges, nodes = score_graph(G, plan, samples, days, dates)
    if any(e["coverage"] == "no_coordinates" for e in edges):
        warnings.append("Some lanes have endpoints without coordinates and are not assessed.")

    max_by_day = [round(max([e["daily"][d]["risk"] for e in edges if e["daily"]] + [n["daily"][d]["risk"] for n in nodes if n["daily"] and not n["demand_node"]] + [0.0]), 3)
                  for d in range(days)]
    conf_by_day = [day_confidence(d) for d in range(days)]
    high = [e for e in edges if e["max_level"] in ("high", "severe")]
    closed = [e for e in edges if any(r["closed"] for r in e["daily"])]
    affected = [n for n in nodes if not n["demand_node"] and n["max_level"] in ("high", "severe")]
    return {
        "generated_at": datetime.now(tz=IST).isoformat(timespec="seconds"),
        "data_quality": data_quality,
        "scenario": sim_hz.summary(fx) if fx else None,
        "horizon": days,
        "dates": dates,
        "edges": edges,
        "nodes": nodes,
        "hotspots": _hotspot_points(hazards),
        "summary": {
            "high_risk_edges": len(high), "closed_edges": len(closed), "affected_nodes": len(affected),
            "max_risk_by_day": max_by_day, "confidence_by_day": conf_by_day,
            "high_risk_edge_ids": [e["id"] for e in high], "closed_edge_ids": [e["id"] for e in closed],
            "affected_node_ids": [n["id"] for n in affected],
        },
        "providers": providers_quality,
        "mapping": mapping,
        "warnings": warnings,
        "notes": notes,
        "sampling": {"grid_deg": plan.grid, "step_km": None if plan.step_km == float("inf") else plan.step_km, "cells": len(plan.all_cells), "forecast_cells": len(plan.forecast_cells),
                     "flood_cells": len(plan.flood_cells), "marine_cells": len(plan.marine_cells)},
        "attribution": "Weather data by Open-Meteo.com (CC BY 4.0); earthquakes: USGS",
        "_hazards": hazards,
        "_samples": samples,
        "_plan": plan,
    }


def public(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def lane_scorer(G: nx.DiGraph, payload: dict):
    """score_as(edge "U->V", mode, day) -> scored row, using the same samples (for mode-switch options)."""
    plan: SamplingPlan = payload["_plan"]
    samples = payload["_samples"]
    dates = payload["dates"]

    def score_as(key: str, mode: str, day: int) -> dict:
        info = plan.edges.get(key)
        if not info or info["coverage"] != "full":
            return {"risk": 0.0, "level": "low", "reason": "No coordinates.", "drivers": []}
        cells = info["cells"]
        if mode == "air":
            cells = [cells[0], cells[-1]] if len(cells) > 1 else cells
        rows = [samples[c] for c in cells if c in samples]
        return _daily_rows(rows, mode, len(dates), dates, "along the route")[day]

    return score_as
