"""Weather- and disaster-aware route risk and re-routing. Works for any active network (preset, CSV, manual builder).

GET  /weather/risk                    per-lane / per-site daily risk, hotspots, summary, data_quality
POST /weather/apply                   forecast -> disruption events (source "weather") for the active scenario
DELETE /weather/apply                 forget the applied weather events (the client restores its previous scenario)
POST /weather/reroute                 blocked routes and ranked alternatives (+ wait, pre-position, dispatch window)
GET  /weather/hazards                 hazard overlay for the map (rain cells, flood zones, cyclone track, quake rings)
GET  /weather/simulated-scenarios     built-in artificial hazard scenarios (and which one is active)
POST /weather/simulated-scenarios     activate one ({"id": ...}) or go back to live data ({"id": null})
GET  /weather/status                  provider health, last refresh, cache age
GET  /weather/chaos                   Chaos Finder on the network as the weather leaves it, next to the normal scan

Weather always runs on the real engine against the network the UI shows (the mock demo while USE_MOCK_NETWORK is on).
Provider trouble never becomes an HTTP error: responses carry data_quality and warnings instead.
"""
from __future__ import annotations

import hashlib
import json
import logging

import networkx as nx
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from cache import cache
from config import settings
from core import chaos as chaos_core
from core import strategies as strat_core
from core.hazards import providers as prov
from core.hazards import reroute as reroute_core
from core.hazards import service
from core.hazards import simulated as sim_hz
from core.hazards.impact_mapping import IMPACT_TABLE, events_from_risk
from core.hazards.scoring import MODE_SENSITIVITY, THRESHOLDS
from core.graph import node_index
from network_store import store
from routers.deps import get_graph, preset_graph
from schemas import (
    Event,
    WeatherApplyRequest,
    WeatherRerouteRequest,
    WeatherScenarioRequest,
)
from validation import EventValidationError, validate_events

router = APIRouter(prefix="/weather", tags=["weather"])
log = logging.getLogger("aegis.weather")


def weather_graph() -> nx.DiGraph:
    """The network the UI shows: the preset exactly as GET /network serves it, else the active CSV/manual network."""
    return preset_graph() if store.source == "preset" else get_graph()


def _runnable_or_409() -> None:
    errors = store.active_errors() if store.source != "preset" else []
    if errors:
        raise HTTPException(status_code=409, detail="The active network can't be planned for yet: "
                            + " ".join(e["message"] for e in errors) + " Fix it on the Data tab or switch back to the preset demo.")


def _risk_hash(risk: dict) -> str:
    blob = json.dumps([[e["id"], [r["risk"] for r in e["daily"]]] for e in risk["edges"]]
                      + [[n["id"], [r["risk"] for r in n["daily"]]] for n in risk["nodes"]], sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


@router.get("/risk")
async def weather_risk(horizon: int = 7, refresh: bool = False):
    G = weather_graph()
    return service.public(await service.assess(G, horizon, force=refresh))


@router.get("/hazards")
async def weather_hazards(horizon: int = 7):
    G = weather_graph()
    risk = await service.assess(G, horizon)
    return {"generated_at": risk["generated_at"], "data_quality": risk["data_quality"], "dates": risk["dates"],
            "scenario": risk["scenario"], "features": risk["_hazards"], "attribution": risk["attribution"]}


def _apply_events(risk: dict, req: WeatherApplyRequest, G: nx.DiGraph) -> list[Event]:
    events = events_from_risk(risk, req.min_level, req.include_nodes, req.horizon)
    nodes, edges = node_index(G)
    try:
        return validate_events(events, nodes, edges)
    except EventValidationError as exc:  # cannot happen for a consistent graph; never a stack trace
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/apply")
async def weather_apply(req: WeatherApplyRequest):
    G = weather_graph()
    risk = await service.assess(G, req.horizon)
    events = _apply_events(risk, req, G)
    service.state.set_applied([e.model_dump() for e in events])
    return {"events": [e.model_dump(exclude_none=True) for e in events], "data_quality": risk["data_quality"],
            "scenario": risk["scenario"], "generated_at": risk["generated_at"],
            "summary": f"{len(events)} weather event(s) from the {risk['horizon']}-day "
                       f"{'simulated scenario' if risk['scenario'] else 'forecast'} at {req.min_level} risk or above."}


@router.delete("/apply")
def weather_clear():
    service.state.set_applied([])
    return {"cleared": True}


def _strategy_summary(G: nx.DiGraph, events: list[Event]) -> dict | None:
    if not events:
        return None
    nothing = strat_core.optimize_plan(G, events, (), horizon=30)
    plan = strat_core.weather_plan(G, events, 30)
    check = strat_core.safety_check(G, events, plan)
    unit_price = G.graph.get("unit_price", 4200)
    return {
        "name": strat_core.WEATHER_STRATEGY, "cost": plan["cost"], "unmet": plan["unmet"], "co2": plan["co2"],
        "delay_avg_days": plan["delay"]["avg_days"], "recovery_days": plan["recovery_days"],
        "rerouted_lanes": plan["rerouted_lanes"], "inventory_actions": plan["inventory_actions"],
        "safety_check": {"passed": check["passed"], "warning": check["warning"]},
        "do_nothing": {"unmet": nothing["unmet"], "delay_avg_days": nothing["delay"]["avg_days"]},
        "net_saving": round((nothing["unmet"] - plan["unmet"]) * unit_price - plan["cost"], 0),
    }


@router.post("/reroute")
async def weather_reroute(req: WeatherRerouteRequest):
    G = weather_graph()
    _runnable_or_409()
    risk = await service.assess(G, req.horizon)
    nodes, edges = node_index(G)
    try:
        given = validate_events(req.events, nodes, edges) if req.events else None
    except EventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    weather_events = [e for e in (given or []) if e.source == "weather"] or (
        given if given else _apply_events(risk, WeatherApplyRequest(horizon=req.horizon), G))
    key = cache.key("weather-reroute", [store.source, store.version, risk["data_quality"], _risk_hash(risk), req.horizon,
                                        [e.model_dump() for e in (given or [])]])

    def compute():
        score_as = service.lane_scorer(G, risk)
        body = reroute_core.plan_reroutes(G, service.public(risk), given, score_as)
        try:
            body["applied_strategy_summary"] = _strategy_summary(G, weather_events)
        except Exception as exc:  # noqa: BLE001 - the options are still useful without the plan summary
            log.warning("weather strategy summary failed: %s", exc)
            body["applied_strategy_summary"] = None
        body.update(data_quality=risk["data_quality"], scenario=risk["scenario"], generated_at=risk["generated_at"],
                    horizon=risk["horizon"])
        return body

    return await run_in_threadpool(cache.get_or_compute, key, compute)


@router.get("/simulated-scenarios")
def weather_scenarios():
    service.state.load()
    return {"active": service.state.scenario_id, "scenarios": [sim_hz.summary(fx) for fx in sim_hz.list_scenarios()]}


@router.post("/simulated-scenarios")
def weather_set_scenario(req: WeatherScenarioRequest):
    if req.id is not None and sim_hz.get_scenario(req.id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown weather scenario {req.id!r}.")
    service.state.set_scenario(req.id)
    return weather_scenarios()


@router.get("/status")
def weather_status():
    service.state.load()
    return {
        "mode": "simulated" if service.state.scenario_id else "live",
        "active_scenario": service.state.scenario_id,
        "live_calls_enabled": not settings.mock_weather,
        "providers": prov.provider_status(),
        "min_refresh_s": settings.weather_min_refresh_s,
        "cache_ttl_s": settings.weather_cache_ttl,
        "attribution": "Weather data by Open-Meteo.com (CC BY 4.0); earthquakes: USGS",
        "thresholds": THRESHOLDS, "mode_sensitivity": MODE_SENSITIVITY, "impact_table": IMPACT_TABLE,
    }


def _degraded(G: nx.DiGraph, events: list[Event]) -> nx.DiGraph:
    """G with every weather event at full effect (capacities only; the backup stays available, as in /chaos)."""
    H = G.copy()
    node_f, edge_f, _ = strat_core._peak_state([e for e in events if e.type != "demand"])
    for n, f in node_f.items():
        H.nodes[n]["capacity"] = (H.nodes[n].get("capacity") or 0.0) * max(0.0, f)
    for e, f in edge_f.items():
        H.edges[e]["capacity"] *= max(0.0, f)
    return H


@router.get("/chaos")
async def weather_chaos(horizon: int = 7, top: int = 5):
    G = weather_graph()
    _runnable_or_409()
    risk = await service.assess(G, horizon)
    events = _apply_events(risk, WeatherApplyRequest(horizon=horizon), G)
    key = cache.key("weather-chaos", [store.source, store.version, _risk_hash(risk), top])

    def compute():
        base = chaos_core.chaos_find(G, top=top)
        weather = chaos_core.chaos_find(_degraded(G, events), top=top) if events else base
        base_pairs = {tuple(sorted(p["pair"])) for p in base["hidden_pairs"]}
        new_pairs = [p for p in weather["hidden_pairs"] if tuple(sorted(p["pair"])) not in base_pairs]
        base_spof = {s["target"] for s in base["spof"]}
        new_spof = [s for s in weather["spof"] if s["target"] not in base_spof]
        changed = bool(events) and (weather["resilience_score"] != base["resilience_score"] or bool(new_pairs) or bool(new_spof))
        detail = (f"Resilience {base['resilience_score']:.1f} -> {weather['resilience_score']:.1f}; "
                  f"{len(new_spof)} new single point(s) of failure, {len(new_pairs)} new hidden pair(s)") if events else "No weather events."
        return {"base": base, "weather": weather, "events": len(events), "changed": changed, "detail": detail,
                "new_spof": new_spof, "new_hidden_pairs": new_pairs, "data_quality": risk["data_quality"], "scenario": risk["scenario"]}

    return await run_in_threadpool(cache.get_or_compute, key, compute)
