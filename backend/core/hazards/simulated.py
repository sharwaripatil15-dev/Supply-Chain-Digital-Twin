"""Simulated hazard injector: deterministic artificial scenarios that run through the real scoring pipeline.

A scenario fixture (data/weather_scenarios/*.json) describes hazard *fields* over time, never risk outputs:
    anchors   named places: {"city": "Chennai", "lat": .., "lon": ..} or {"pick": "northernmost", "kind": "factory",
              "offset_km": 80, "bearing_deg": 0}. A city anchor moves to the active network's nodes in that city
              (their centroid); a missing city falls back to the nearest node by coordinates. Every mapping is
              logged and returned (`mapping`) so the demo says exactly what it matched.
    hazards   one of
              cyclone  track [{day, dlat, dlon}] relative to its anchor, radius_km per day and per-day peaks for
                       wind_gust_kmh, rain_mm, wave_height_m
              rain     anchor + dlat/dlon, radius_km, per-day rain_mm (and optional river_discharge_ratio)
              fog      anchor, radius_km, per-day visibility_m
              heat     anchor, radius_km, per-day temp_c
              quake    anchor, magnitude, day (felt on that day and the next: inspections and aftershocks)
    expected  assertions the tests (and scripts/weather_e2e.py) check against the end-to-end result
Field shape: full strength within 40% of the radius, fading linearly to calm weather at the radius. Calm weather
(2 mm rain, 22 km/h gusts, 8 km visibility, 33 C, river at its mean, 1 m waves) gets a small seeded jitter, so a
scenario is deterministic for its seed.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from pathlib import Path

import networkx as nx
import numpy as np

from core.hazards.providers import HazardSample
from core.hazards.route_sampling import has_coords
from core.hazards.scoring import interp, quake_score, THRESHOLDS
from node_types import haversine_km

log = logging.getLogger("aegis.weather")

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "data" / "weather_scenarios"
CALM = {"rain_mm": 2.0, "rain_prob": 0.2, "wind_gust_kmh": 22.0, "visibility_m": 8000.0, "temp_c": 33.0,
        "river_discharge_ratio": 1.0, "wave_height_m": 1.0}
CORE_SHARE = 0.4
QUAKE_FELT_DAYS = 2


def list_scenarios() -> list[dict]:
    out = []
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        try:
            fx = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("weather: bad scenario fixture %s (%s)", path.name, exc)
            continue
        out.append(fx)
    return out


def get_scenario(scenario_id: str) -> dict | None:
    return next((fx for fx in list_scenarios() if fx.get("id") == scenario_id), None)


def summary(fx: dict) -> dict:
    return {"id": fx["id"], "label": fx["label"], "description": fx.get("description", ""), "days": fx.get("days", 7),
            "hazard_types": sorted({h["type"] for h in fx.get("hazards", [])})}


# ------------------------------------------------------------------ anchors
def _offset(lat: float, lon: float, km: float, bearing_deg: float) -> tuple[float, float]:
    b = math.radians(bearing_deg)
    dlat = km * math.cos(b) / 111.0
    dlon = km * math.sin(b) / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def resolve_anchors(fx: dict, G: nx.DiGraph) -> tuple[dict[str, tuple[float, float]], list[dict]]:
    """{anchor name: (lat, lon)} for this network, plus the mapping log."""
    located = [(n, d) for n, d in G.nodes(data=True) if has_coords(d)]
    anchors: dict[str, tuple[float, float]] = {}
    mapping: list[dict] = []
    for name, spec in (fx.get("anchors") or {}).items():
        if "pick" in spec:
            pool = [(n, d) for n, d in located if d.get("kind") == spec.get("kind")] or located
            if not pool:
                anchors[name] = (spec.get("lat", 22.0), spec.get("lon", 79.0))
                mapping.append({"anchor": name, "wanted": spec.get("label", name), "matched": None, "how": "fixture coordinates",
                                "note": "network has no located nodes"})
                continue
            key = {"northernmost": lambda nd: -nd[1]["lat"], "southernmost": lambda nd: nd[1]["lat"],
                   "easternmost": lambda nd: -nd[1]["lon"], "westernmost": lambda nd: nd[1]["lon"]}[spec["pick"]]
            n, d = sorted(pool, key=key)[0]
            point = _offset(float(d["lat"]), float(d["lon"]), spec.get("offset_km", 0.0), spec.get("bearing_deg", 0.0))
            anchors[name] = point
            mapping.append({"anchor": name, "wanted": spec.get("label", name), "matched": [n],
                            "how": f"{spec['pick']} {spec.get('kind', 'node')}",
                            "note": f"{n} {d.get('name') or ''} ({d.get('city') or ''}); centre {spec.get('offset_km', 0):.0f} km away"})
            continue
        city = str(spec.get("city") or "").strip().lower()
        hits = [(n, d) for n, d in located if str(d.get("city") or "").strip().lower() == city] if city else []
        if hits:
            anchors[name] = (sum(float(d["lat"]) for _, d in hits) / len(hits), sum(float(d["lon"]) for _, d in hits) / len(hits))
            mapping.append({"anchor": name, "wanted": spec.get("city"), "matched": [n for n, _ in hits], "how": "city name"})
        elif located:
            want = (float(spec["lat"]), float(spec["lon"]))
            n, d = min(located, key=lambda nd: haversine_km(want, (float(nd[1]["lat"]), float(nd[1]["lon"]))))
            km = haversine_km(want, (float(d["lat"]), float(d["lon"])))
            anchors[name] = (float(d["lat"]), float(d["lon"]))
            mapping.append({"anchor": name, "wanted": spec.get("city"), "matched": [n], "how": "nearest node",
                            "note": f"{spec.get('city')} is not in this network; used {n} {d.get('name') or ''} ({d.get('city') or ''}), {km:.0f} km away"})
            log.info("weather scenario %s: %s -> nearest node %s (%.0f km)", fx.get("id"), spec.get("city"), n, km)
        else:
            anchors[name] = (float(spec["lat"]), float(spec["lon"]))
            mapping.append({"anchor": name, "wanted": spec.get("city"), "matched": None, "how": "fixture coordinates",
                            "note": "network has no located nodes"})
    return anchors, mapping


# ------------------------------------------------------------------ fields
def _strength(distance_km: float, radius_km: float) -> float:
    if radius_km <= 0:
        return 0.0
    r = distance_km / radius_km
    if r <= CORE_SHARE:
        return 1.0
    return max(0.0, 1.0 - (r - CORE_SHARE) / (1.0 - CORE_SHARE))


def _day_value(values, day: int):
    if not values or day < 0 or day >= len(values):
        return None
    return values[day]


def _centre(hz: dict, anchors: dict, day: int) -> tuple[float, float] | None:
    base = anchors.get(hz.get("anchor"))
    if base is None:
        return None
    if hz["type"] == "cyclone":
        pts = {p["day"]: p for p in hz.get("track", [])}
        p = pts.get(day)
        return None if p is None else (base[0] + p.get("dlat", 0.0), base[1] + p.get("dlon", 0.0))
    return base[0] + hz.get("dlat", 0.0), base[1] + hz.get("dlon", 0.0)


def _radius(hz: dict, day: int) -> float:
    r = hz.get("radius_km", 100.0)
    if isinstance(r, list):
        return float(_day_value(r, day) or 0.0)
    return float(r)


class ScenarioField:
    """Evaluates a fixture's hazards at any point and day (after anchoring to a network)."""

    def __init__(self, fx: dict, G: nx.DiGraph):
        self.fx = fx
        self.days = int(fx.get("days", 7))
        self.anchors, self.mapping = resolve_anchors(fx, G)
        self.seed = int(fx.get("seed", 7))

    def _jitter(self, lat: float, lon: float, day: int) -> np.random.Generator:
        key = (self.seed * 1_000_003 + int(round(lat * 100)) * 7919 + int(round(lon * 100)) * 104729 + day) % (2**32)
        return np.random.default_rng(key)

    def sample(self, lat: float, lon: float, day: int, today: date) -> HazardSample:
        rng = self._jitter(lat, lon, day)
        j = lambda v, spread=0.05: v * (1 + rng.uniform(-spread, spread))  # noqa: E731
        s = HazardSample(lat=lat, lon=lon, date=(today + timedelta(days=day)).isoformat(),
                         rain_mm=j(CALM["rain_mm"]), rain_prob=CALM["rain_prob"], wind_gust_kmh=j(CALM["wind_gust_kmh"]),
                         visibility_m=j(CALM["visibility_m"]), temp_c=j(CALM["temp_c"], 0.02),
                         river_discharge_ratio=j(CALM["river_discharge_ratio"]), wave_height_m=j(CALM["wave_height_m"]),
                         source="simulated", quality="simulated")
        for hz in self.fx.get("hazards", []):
            t = hz["type"]
            if t == "quake":
                qday = int(hz.get("day", 0))
                if 0 <= day - qday < QUAKE_FELT_DAYS:
                    centre = self.anchors.get(hz.get("anchor"))
                    if centre:
                        d = haversine_km((lat, lon), centre)
                        if quake_score(hz["magnitude"], d) > quake_score(s.quake_magnitude, s.quake_distance_km):
                            s.quake_magnitude, s.quake_distance_km = float(hz["magnitude"]), round(d, 1)
                continue
            centre = _centre(hz, self.anchors, day)
            if centre is None:
                continue
            f = _strength(haversine_km((lat, lon), centre), _radius(hz, day))
            if f <= 0:
                continue
            fields = hz.get("fields", {})
            if t == "fog":
                vis = _day_value(fields.get("visibility_m"), day)
                if vis:
                    v = math.exp(math.log(CALM["visibility_m"]) * (1 - f) + math.log(vis) * f)
                    s.visibility_m = min(s.visibility_m, v)
                continue
            for key in ("rain_mm", "wind_gust_kmh", "wave_height_m", "river_discharge_ratio", "temp_c"):
                peak = _day_value(fields.get(key), day)
                if peak is None:
                    continue
                v = CALM[key] + (peak - CALM[key]) * f
                setattr(s, key, max(getattr(s, key) or 0.0, v))
                if key == "rain_mm" and v > 20:
                    s.rain_prob = max(s.rain_prob or 0.0, min(0.95, 0.5 + f * 0.45))
        for key in ("rain_mm", "wind_gust_kmh", "visibility_m", "temp_c", "river_discharge_ratio", "wave_height_m"):
            setattr(s, key, round(getattr(s, key), 2))
        return s

    def overlays(self) -> list[dict]:
        """Map features per hazard with per-day centre, radius and 0..1 intensity (drives fade with the day slider)."""
        feats = []
        for i, hz in enumerate(self.fx.get("hazards", [])):
            t = hz["type"]
            fields = hz.get("fields", {})
            daily = []
            for day in range(self.days):
                if t == "quake":
                    qday = int(hz.get("day", 0))
                    centre = self.anchors.get(hz.get("anchor"))
                    on = 0 <= day - qday < QUAKE_FELT_DAYS
                    radius = 150.0 * 10 ** (0.5 * (hz["magnitude"] - 5.5))
                    intensity = interp(hz["magnitude"], THRESHOLDS["quake_mag"]) * (1.0 if day == qday else 0.6) if on else 0.0
                    daily.append({"day": day, "lat": centre[0] if centre else None, "lon": centre[1] if centre else None,
                                  "radius_km": round(radius), "intensity": round(intensity, 2),
                                  "value": f"M{hz['magnitude']:.1f}" if on else None})
                    continue
                centre = _centre(hz, self.anchors, day)
                radius = _radius(hz, day)
                intensity, value = 0.0, None
                if centre is not None and radius > 0:
                    if t == "fog":
                        vis = _day_value(fields.get("visibility_m"), day)
                        intensity = interp(vis, THRESHOLDS["fog"]) if vis else 0.0
                        value = f"{vis:.0f} m visibility" if vis else None
                    else:
                        scores = {
                            "rain_mm": interp(_day_value(fields.get("rain_mm"), day), THRESHOLDS["rain"]),
                            "wind_gust_kmh": interp(_day_value(fields.get("wind_gust_kmh"), day), THRESHOLDS["wind"]),
                            "wave_height_m": interp(_day_value(fields.get("wave_height_m"), day), THRESHOLDS["wave"]),
                            "river_discharge_ratio": interp(_day_value(fields.get("river_discharge_ratio"), day), THRESHOLDS["flood"]),
                            "temp_c": interp(_day_value(fields.get("temp_c"), day), THRESHOLDS["heat"]),
                        }
                        key = max(scores, key=scores.get)
                        intensity = scores[key]
                        raw = _day_value(fields.get(key), day)
                        unit = {"rain_mm": "mm/day", "wind_gust_kmh": "km/h gusts", "wave_height_m": "m waves",
                                "river_discharge_ratio": "x normal river flow", "temp_c": "°C"}[key]
                        value = f"{raw:.0f} {unit}" if raw is not None else None
                daily.append({"day": day, "lat": centre[0] if centre else None, "lon": centre[1] if centre else None,
                              "radius_km": round(radius), "intensity": round(intensity, 2), "value": value})
            kind = {"cyclone": "cyclone", "rain": "flood" if fields.get("river_discharge_ratio") else "rain",
                    "fog": "fog", "heat": "heat", "quake": "quake"}.get(t, t)
            feats.append({"id": hz.get("id", f"h{i}"), "type": kind, "label": hz.get("label", t.title()), "daily": daily})
        return feats


# ------------------------------------------------------------------ expected assertions
def _nodes_in_cities(G: nx.DiGraph, cities: list[str], mapping: list[dict]) -> set[str]:
    want = {c.lower() for c in cities}
    hit = {n for n, d in G.nodes(data=True) if str(d.get("city") or "").strip().lower() in want}
    for m in mapping:  # a city missing from the network counts as the node it was mapped to
        if str(m.get("wanted") or "").lower() in want and m.get("matched"):
            hit.update(m["matched"])
    return hit


def check_expected(fx: dict, G: nx.DiGraph, risk: dict, reroute: dict | None = None, chaos_delta: dict | None = None) -> list[dict]:
    """Evaluate a fixture's `expected` list. Returns [{check, passed, detail}]; checks that do not apply to this
    network (e.g. sea lanes on a road-only network) pass with detail "n/a"."""
    rank = {"low": 0, "moderate": 1, "high": 2, "severe": 3}
    mapping = risk.get("mapping") or []
    results = []
    options = (reroute or {}).get("options", [])
    for exp in fx.get("expected", []):
        check = exp["check"]
        passed, detail = False, ""
        if check == "lanes_at_level":
            nodes = _nodes_in_cities(G, exp.get("cities", []), mapping)
            d0, d1 = exp.get("days", [0, 99])
            modes = set(exp.get("modes") or ["road", "rail", "sea", "air"])
            lanes = []
            for e in risk["edges"]:
                if e["mode"] not in modes or not ({e["source"], e["target"]} & nodes):
                    continue
                days = [d for d in e["daily"][d0:d1 + 1] if rank[d["level"]] >= rank[exp.get("min_level", "high")]]
                if exp.get("closed"):
                    days = [d for d in days if d.get("closed")]
                if "lead_between" in exp:
                    lo, hi = exp["lead_between"]
                    days = [d for d in days if lo <= d["lead_multiplier"] <= hi or d.get("closed")]
                if days:
                    lanes.append(e["id"])
            passed = len(lanes) >= exp.get("min_count", 1)
            detail = f"{len(lanes)} lane(s): {', '.join(lanes[:6])}"
        elif check == "sea_lanes_closed":
            sea = [e for e in risk["edges"] if e["mode"] == "sea"]
            if not sea:
                passed, detail = True, "n/a (no sea lanes in this network)"
            else:
                d0, d1 = exp.get("days", [0, 99])
                closed = [e["id"] for e in sea if any(d.get("closed") for d in e["daily"][d0:d1 + 1])]
                passed, detail = bool(closed), f"closed: {', '.join(closed) or 'none'}"
        elif check == "recommended_alternative":
            recs = [o for o in options if any(a["recommended"] for a in o["alternatives"])]
            passed, detail = bool(recs), f"{len(recs)} blocked route(s) with a recommended alternative"
        elif check == "alternative_via_cities":
            nodes = _nodes_in_cities(G, exp.get("cities", []), mapping)
            via = [a for o in options for a in o["alternatives"] if set(a["path"][1:-1]) & nodes or (a["path"] and a["path"][0] in nodes)]
            passed, detail = bool(via), f"{len(via)} alternative(s) via {', '.join(exp.get('cities', []))}"
        elif check == "alternative_has_deltas":
            alts = [a for o in options for a in o["alternatives"] if a["recommended"]]
            passed = bool(alts) and all(a.get("eta_delta") is not None and a.get("cost_delta") is not None for a in alts)
            detail = "; ".join(f"{'→'.join(a['path'])}: ETA {a['eta_delta']:+.1f} d, cost {a['cost_delta']:+.1f}/unit" for a in alts[:3])
        elif check == "safety_warning":
            flagged = []
            for o in options:
                alts = o["alternatives"]
                if not alts:
                    continue
                cheapest = min(alts, key=lambda a: a["cost"])
                if not cheapest["safety_check"]["passed"]:
                    flagged.append(f"{o['blocked_edge']}: {cheapest['safety_check']['warning']}")
            passed, detail = bool(flagged), " | ".join(flagged[:2]) or "no warning on the cheapest option"
        elif check == "preposition_option":
            pre = [o for o in options if (o.get("preposition_option") or {}).get("viable")]
            passed, detail = bool(pre), f"{len(pre)} pre-positioning option(s)"
        elif check == "dispatch_before":
            day = exp["day"]
            hits = [o for o in options if (o.get("dispatch_window") or {}).get("latest_safe_day") is not None
                    and o["dispatch_window"]["latest_safe_day"] < day]
            passed, detail = bool(hits), "; ".join(o["dispatch_window"]["text"] for o in hits[:2]) or "no dispatch-before window"
        elif check == "node_partial_loss":
            hits = [n["id"] for n in risk["nodes"] if n.get("kind") == exp.get("kind")
                    and any(0 < d["capacity_multiplier"] < 1 for d in n["daily"])]
            passed, detail = bool(hits), f"partial capacity loss at {', '.join(hits) or 'none'}"
        elif check == "mode_switch_option":
            alts = [a for o in options for a in o["alternatives"] if a.get("kind") == "mode_switch" and a["mode"] == exp.get("to")]
            passed, detail = bool(alts), f"{len(alts)} switch(es) to {exp.get('to')}"
        elif check == "mixed_actions":
            kinds = set()
            for o in options:
                kinds.add(o.get("recommended_action"))
                if (o.get("preposition_option") or {}).get("viable"):
                    kinds.add("preposition")
            for a in (reroute or {}).get("node_actions", []):
                kinds.add(a["action"])
            want = set(exp.get("any_of", []))
            passed = len(kinds & (want | {"mode_switch", "reroute"})) >= exp.get("min_kinds", 2) and bool(kinds & want)
            detail = f"actions: {', '.join(sorted(k for k in kinds if k))}"
        elif check == "chaos_changes":
            passed = bool(chaos_delta and chaos_delta.get("changed"))
            detail = (chaos_delta or {}).get("detail", "not evaluated")
        else:
            detail = f"unknown check {check!r}"
        results.append({"check": check, "passed": bool(passed), "detail": detail})
    return results
