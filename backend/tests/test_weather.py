"""Weather- and disaster-aware routing. No test touches the network: providers run on httpx.MockTransport."""
from __future__ import annotations

import json
import shutil
from datetime import date, timedelta

import httpx
import networkx as nx
import pytest
from fastapi.testclient import TestClient

from cache import cache
from config import settings
from core.hazards import impact_mapping as im
from core.hazards import providers as prov
from core.hazards import reroute as rr
from core.hazards import route_sampling as rs
from core.hazards import scoring as sc
from core.hazards import service
from core.hazards import simulated as sim_hz
from core.hazards.providers import HazardSample
from core.sim import simulate
from main import app
from network_store import store
from routers.weather import weather_graph
from schemas import Event

client = TestClient(app)
SCENARIOS = ["cyclone-east-coast", "monsoon-mumbai-pune", "compound-north-fog-quake"]


@pytest.fixture(autouse=True)
def clean_weather(monkeypatch):
    store.reset("empty")
    store.use_preset()
    service.state.set_scenario(None)
    service.state.set_applied([])
    service.state.last_live_fetch = 0.0
    prov.reset_state()
    cache.clear()
    shutil.rmtree(prov.cache_dir(), ignore_errors=True)
    monkeypatch.setattr(settings, "mock_weather", True)
    yield
    service.state.set_scenario(None)
    store.reset("empty")
    store.use_preset()


# ------------------------------------------------------------------ canned provider responses
def _dates(n=7):
    today = date.today()
    return [(today + timedelta(days=i)).isoformat() for i in range(n)]


def _forecast_loc(rain=2.0, gust=20.0, vis=9000.0, temp=32.0, prob=10, n=7):
    dates = _dates(n)
    return {
        "daily": {"time": dates, "precipitation_sum": [rain] * n, "precipitation_probability_max": [prob] * n,
                  "wind_gusts_10m_max": [gust] * n, "temperature_2m_max": [temp] * n, "weather_code": [3] * n},
        "hourly": {"time": [f"{d}T{h:02d}:00" for d in dates for h in range(24)], "visibility": [vis] * (24 * n)},
    }


def canned_transport(rain=2.0, gust=20.0, vis=9000.0, flood_ratio=1.0, waves=1.0, quakes=None, fail=()):
    """MockTransport that answers like the real APIs; providers listed in `fail` time out."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        url = str(request.url)
        name = ("flood" if "flood" in url else "marine" if "marine" in url else "quakes" if "usgs" in url
                else "gdacs" if "gdacs" in url else "forecast")
        if name in fail:
            raise httpx.ConnectTimeout("timed out", request=request)
        n = len(request.url.params.get("latitude", "0").split(","))
        if name == "forecast":
            body = [_forecast_loc(rain, gust, vis) for _ in range(n)]
        elif name == "flood":
            body = [{"daily": {"time": _dates(), "river_discharge": [100.0 * flood_ratio] * 7, "river_discharge_mean": [100.0] * 7}}
                    for _ in range(n)]
        elif name == "marine":
            body = [{"daily": {"time": _dates(), "wave_height_max": [waves] * 7, "wave_period_max": [8.0] * 7}} for _ in range(n)]
        elif name == "quakes":
            body = {"features": quakes or []}
        else:
            body = {"features": []}
        if n == 1 and isinstance(body, list):
            body = body[0]
        return httpx.Response(200, json=body)

    return handler, calls


def use_transport(monkeypatch, handler):
    monkeypatch.setattr(settings, "mock_weather", False)
    monkeypatch.setattr(prov, "client_factory", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=1))
    monkeypatch.setattr(prov.RateLimiter, "wait", lambda self: _noop())


async def _noop():
    return None


# ------------------------------------------------------------------ providers
def test_normalize_forecast_single_and_many_locations():
    cells = [(19.0, 73.0), (28.5, 77.0)]
    many = prov.normalize_forecast([_forecast_loc(rain=80, gust=65, vis=150, prob=90), _forecast_loc()], cells)
    s = many[(19.0, 73.0)][0]
    assert (s.rain_mm, s.wind_gust_kmh, s.visibility_m, s.rain_prob) == (80, 65, 150, 0.9)
    assert len(many[(28.5, 77.0)]) == 7
    one = prov.normalize_forecast(_forecast_loc(rain=5), cells[:1])  # a single location is an object, not a list
    assert one[(19.0, 73.0)][0].rain_mm == 5


def test_fog_visibility_uses_the_four_lowest_hours():
    assert prov._fog_visibility([100, 120, 140, 160, 9000, 9000, None]) == 130.0
    assert prov._fog_visibility([None, None]) is None


def test_normalize_flood_marine_quakes_gdacs():
    cells = [(19.0, 73.0), (20.0, 74.0)]
    flood = prov.normalize_flood([{"daily": {"time": ["2026-01-01"], "river_discharge": [450], "river_discharge_mean": [100]}},
                                  {"daily": {"time": ["2026-01-01"], "river_discharge": [None], "river_discharge_mean": [None]}}], cells)
    assert flood == {(19.0, 73.0): {"2026-01-01": 4.5}}  # the river-less cell is skipped
    marine = prov.normalize_marine({"daily": {"time": ["2026-01-01"], "wave_height_max": [5.2]}}, cells[:1])
    assert marine[(19.0, 73.0)]["2026-01-01"] == 5.2
    quakes = prov.normalize_quakes({"features": [
        {"geometry": {"coordinates": [77.0, 28.0, 10]}, "properties": {"mag": 6.1, "time": 1_700_000_000_000, "place": "Delhi"}},
        {"geometry": {"coordinates": [140.0, 35.0, 10]}, "properties": {"mag": 7.0, "time": 1_700_000_000_000}},  # Japan: filtered
        {"geometry": {"coordinates": [77.0, 28.0]}, "properties": {"mag": None}},  # malformed: skipped
    ]})
    assert [q["magnitude"] for q in quakes] == [6.1] and quakes[0]["place"] == "Delhi"
    tc = prov.normalize_gdacs({"features": [{"geometry": {"coordinates": [85.0, 15.0]}, "properties": {"eventtype": "TC", "name": "X"}}]})
    assert tc[0]["name"] == "X"


# ------------------------------------------------------------------ scoring
@pytest.mark.parametrize("field,value,expected", [
    ("rain_mm", 64.5, 0.5), ("rain_mm", 115.5, 0.75), ("rain_mm", 204.5, 1.0), ("rain_mm", 5.0, 0.0),
    ("wind_gust_kmh", 60, 0.5), ("wind_gust_kmh", 90, 0.8), ("wind_gust_kmh", 30, 0.0),
    ("visibility_m", 200, 0.6), ("visibility_m", 1500, 0.0), ("visibility_m", 40, 0.9),
    ("wave_height_m", 4.0, 0.7), ("wave_height_m", 6.5, 1.0),
    ("river_discharge_ratio", 3.0, 0.7), ("temp_c", 47, 0.6),
])
def test_component_thresholds(field, value, expected):
    s = HazardSample(lat=0, lon=0, date="d", **{field: value})
    hazard = {"rain_mm": "rain", "wind_gust_kmh": "wind", "visibility_m": "fog", "wave_height_m": "wave",
              "river_discharge_ratio": "flood", "temp_c": "heat"}[field]
    assert sc.components(s)[hazard] == pytest.approx(expected, abs=1e-6)


def test_quake_threshold_m55_within_150_km():
    assert sc.quake_score(5.5, 0) == pytest.approx(0.6)
    assert sc.quake_score(5.5, 150) == 0.0
    assert 0.5 < sc.quake_score(6.0, 80) < 0.6  # partial capacity loss band
    assert sc.quake_score(4.0, 10) == 0.0


def test_levels_and_reason():
    assert [sc.level_of(r) for r in (0.1, 0.3, 0.55, 0.7)] == ["low", "moderate", "high", "severe"]
    out = sc.score([HazardSample(lat=0, lon=0, date="d", rain_mm=230, wind_gust_kmh=95)], "road")
    assert out["level"] == "severe" and out["risk"] == 1.0
    assert [d["hazard"] for d in out["drivers"]] == ["rain", "wind"]
    assert "Extremely heavy rain (230 mm/day)" in out["reason"]


def test_mode_specific_scoring():
    fog = HazardSample(lat=0, lon=0, date="d", visibility_m=100)
    assert sc.score([fog], "road")["risk"] == pytest.approx(0.8)
    assert sc.score([fog], "rail")["risk"] == 0.0  # rail ignores fog
    assert sc.score([fog], "air")["risk"] == pytest.approx(0.8)
    waves = HazardSample(lat=0, lon=0, date="d", wave_height_m=6)
    assert sc.score([waves], "road")["risk"] == 0.0 and sc.score([waves], "sea")["risk"] == 1.0
    rain = HazardSample(lat=0, lon=0, date="d", rain_mm=150)
    assert sc.score([rain], "air")["risk"] == 0.0 and sc.score([rain], "rail")["risk"] < sc.score([rain], "road")["risk"]
    # compound hazards rank above the single worst one
    both = HazardSample(lat=0, lon=0, date="d", visibility_m=100, rain_mm=70)
    assert sc.score([both], "road")["risk"] > sc.score([fog], "road")["risk"]


# ------------------------------------------------------------------ route sampling
def test_great_circle_point_counts():
    mumbai, pune, delhi, chennai = (19.08, 72.88), (18.52, 73.86), (28.61, 77.21), (13.08, 80.27)
    assert len(rs.great_circle_points(mumbai, pune)) == 3  # ~120 km
    assert len(rs.great_circle_points(delhi, chennai)) == rs.MAX_POINTS  # ~1,750 km: capped
    assert len(rs.great_circle_points(mumbai, mumbai)) == 1  # zero length
    pts = rs.great_circle_points(mumbai, delhi)
    assert pts[0] == pytest.approx(mumbai) and pts[-1] == pytest.approx(delhi)


def _graph(nodes, edges):
    G = nx.DiGraph(unit_price=4200)
    for nid, kind, lat, lon, extra in nodes:
        G.add_node(nid, kind=kind, city=nid, name=nid, lat=lat, lon=lon, capacity=extra.get("capacity", 500.0),
                   stock=extra.get("stock", 500.0), demand=extra.get("demand", 0.0), reliability=0.9, backup=False)
    for u, v, extra in edges:
        G.add_edge(u, v, capacity=extra.get("capacity", 400.0), lead=extra.get("lead", 2.0), cost=extra.get("cost", 20.0),
                   co2=extra.get("co2", 1.0), mode=extra.get("mode", "road"))
    return G


def test_sampling_dedup_modes_and_cap():
    G = _graph(
        [("S", "supplier", 19.08, 72.88, {}), ("F", "factory", 28.61, 77.21, {}), ("C", "customer", 28.7, 77.1, {"demand": 100}),
         ("P", "warehouse", 13.08, 80.27, {}), ("X", "warehouse", None, None, {})],
        [("S", "F", {}), ("F", "C", {"mode": "air"}), ("S", "P", {"mode": "sea"}), ("S", "X", {})],
    )
    plan = rs.plan_sampling(G, None)
    assert plan.edges["F->C"]["cells"] and len(plan.edges["F->C"]["points"]) == 2  # air: endpoints only
    assert set(plan.edges["S->P"]["cells"]) <= set(plan.marine_cells)  # sea lanes use the marine provider
    assert plan.edges["S->X"]["coverage"] == "no_coordinates"
    assert plan.nodes["P"]["port"] and plan.nodes["S"]["port"]
    assert len(plan.all_cells) == len(set(plan.all_cells))
    capped = rs.plan_sampling(G, 6)
    assert len(capped.all_cells) <= 6 or capped.step_km == float("inf")
    assert capped.grid >= plan.grid


# ------------------------------------------------------------------ impact mapping
@pytest.mark.parametrize("risk,lead,cap,closed", [
    (0.2, 1.0, 1.0, False), (0.4, 1.2, 0.9, False), (0.6, 1.6, 0.6, False), (0.8, 2.2, 0.3, False), (0.9, 1.0, 0.0, True),
])
def test_impact_table(risk, lead, cap, closed):
    out = im.impact(risk)
    assert (out["lead_multiplier"], out["capacity_multiplier"], out["closed"]) == (lead, cap, closed)


def test_events_split_by_band_with_confidence():
    daily = [{"day": i, "risk": r, "reason": f"r{i}", "confidence": im.day_confidence(i)} for i, r in enumerate([0.1, 0.6, 0.65, 0.9, 0.9, 0.2])]
    risk = {"edges": [{"id": "A->B", "daily": daily}], "nodes": [{"id": "N", "daily": daily, "demand_node": False}]}
    events = im.events_from_risk(risk, "high", include_nodes=True)
    lanes = [e for e in events if e.type == "edge"]
    assert [(e.start, e.duration, e.severity, e.lead_multiplier) for e in lanes] == [(1, 2, 0.4, 1.6), (3, 2, 1.0, None)]
    assert all(e.source == "weather" and 0.4 <= e.confidence <= 1 for e in events)
    assert lanes[1].confidence < 1.0  # further out, less sure
    assert [e.type for e in events].count("node") == 2
    assert im.events_from_risk(risk, "severe", include_nodes=False)[0].start == 3
    assert im.day_confidence(30) == im.CONFIDENCE_FLOOR


def test_lead_multiplier_feeds_the_delay():
    from routers.deps import mock_demo_graph

    G = mock_demo_graph()
    slow = Event(type="edge", target="F1->W3", start=0, duration=5, severity=0.0, lead_multiplier=2.0, source="weather")
    plain = slow.model_copy(update={"lead_multiplier": None})
    assert simulate(G, [slow], 10)["delay"]["avg_days"] > simulate(G, [plain], 10)["delay"]["avg_days"]


# ------------------------------------------------------------------ re-routing on a small synthetic network
def _risk_for(G, blocked: dict, days=6):
    """Fake /weather/risk payload: {edge: [risk per day]}; everything else calm."""
    def rows(values):
        out = []
        for d, r in enumerate(values):
            imp = im.impact(r)
            out.append({"day": d, "risk": r, "level": sc.level_of(r), "closed": imp["closed"], "reason": "storm",
                        "lead_multiplier": imp["lead_multiplier"], "capacity_multiplier": imp["capacity_multiplier"],
                        "drivers": [], "confidence": 1.0})
        return out
    calm = [0.0] * days
    return {"horizon": days, "dates": [str(i) for i in range(days)],
            "edges": [{"id": f"{u}->{v}", "daily": rows(blocked.get(f"{u}->{v}", calm))} for u, v in G.edges],
            "nodes": [{"id": n, "daily": rows(calm), "kind": G.nodes[n]["kind"], "demand_node": G.nodes[n]["kind"] == "customer"} for n in G]}


def _diamond(stock=2000.0):
    return _graph(
        [("S1", "supplier", 19.0, 73.0, {"capacity": 1000}), ("S2", "supplier", 23.0, 72.6, {"capacity": 1000}),
         ("F1", "factory", 21.0, 79.0, {"capacity": 1000}), ("F2", "factory", 17.4, 78.5, {"capacity": 210}),
         ("F3", "factory", 22.5, 88.3, {"capacity": 1000}),
         ("W", "warehouse", 28.5, 77.0, {"capacity": 1000}), ("C", "customer", 28.7, 77.1, {"demand": 200, "stock": stock})],
        [("S1", "F1", {"cost": 10}), ("F1", "W", {"cost": 10}), ("W", "C", {"cost": 5}),
         ("S1", "F2", {"cost": 14}), ("F2", "W", {"cost": 14}), ("S2", "F3", {"cost": 30}), ("F3", "W", {"cost": 30})],
    )


def test_reroute_k_alternatives_ranked_and_safety_checked():
    G = _diamond()
    risk = _risk_for(G, {"F1->W": [0, 0.9, 0.9, 0.9, 0.9, 0]})
    out = rr.plan_reroutes(G, risk)
    assert [b["edge"] for b in out["blocked_routes"]] == ["F1->W"]
    opt = out["options"][0]
    reroutes = [a for a in opt["alternatives"] if a["kind"] == "reroute"]
    assert 1 <= len(reroutes) <= rr.K_ALTERNATIVES
    assert all(("F1", "W") not in zip(a["path"], a["path"][1:]) for a in reroutes)
    # the cheaper detour via F2 overloads it (210 capacity for 200 more units/day): flagged, so not recommended
    via_f2 = next(a for a in reroutes if "F2" in a["path"])
    assert not via_f2["safety_check"]["passed"] and "F2" in via_f2["safety_check"]["warning"]
    rec = next(a for a in opt["alternatives"] if a["recommended"])
    assert rec["safety_check"]["passed"] and rec["cost"] > via_f2["cost"]
    assert opt["recommended_action"] in ("reroute", "mode_switch")
    assert opt["original"]["eta_weather"] > opt["original"]["eta_days"]
    assert opt["dispatch_window"]["latest_safe_day"] == 0 and opt["preposition_option"]["viable"]
    assert opt["scenario_patch"]["remove_targets"] == ["F1->W"]


def test_mode_switch_options_use_the_same_samples():
    G = _diamond()
    risk = _risk_for(G, {"F1->W": [0, 0.75, 0.75, 0, 0, 0]})
    out = rr.plan_reroutes(G, risk, score_as=lambda key, mode, day: {"risk": 0.0 if mode == "rail" else 0.75})
    switches = [a for a in out["options"][0]["alternatives"] if a["kind"] == "mode_switch"]
    assert {a["mode"] for a in switches} == {"rail", "air"}  # high-value unit (4,200 INR) on a long hop: air is offered
    rail = next(a for a in switches if a["mode"] == "rail")
    assert rail["residual_risk"] < 0.75 and rail["switch"]["from"] == "road"


def test_wait_it_out_for_short_windows_with_stock_cover():
    G = _diamond(stock=5000)
    out = rr.plan_reroutes(G, _risk_for(G, {"F1->W": [0, 0.9, 0.9, 0, 0, 0]}))
    wait = out["options"][0]["wait_option"]
    assert wait["viable"] and wait["days"] == 2 and wait["resume_day"] == 3
    long = rr.plan_reroutes(G, _risk_for(G, {"F1->W": [0, 0.9, 0.9, 0.9, 0.9, 0.9]}))["options"][0]["wait_option"]
    assert not long["viable"]  # longer than WAIT_MAX_DAYS
    thin = _diamond(stock=50)
    assert not rr.plan_reroutes(thin, _risk_for(thin, {"F1->W": [0, 0.9, 0.9, 0, 0, 0]}))["options"][0]["wait_option"]["viable"]


def test_reroute_on_minimal_and_empty_networks():
    one = _graph([("S", "supplier", 19, 73, {}), ("C", "customer", 28, 77, {"demand": 100})], [("S", "C", {})])
    out = rr.plan_reroutes(one, _risk_for(one, {"S->C": [0, 0.9, 0, 0, 0, 0]}))
    alts = out["options"][0]["alternatives"]
    assert not [a for a in alts if a["kind"] == "reroute"]  # one lane: nothing to reroute through...
    assert {a["mode"] for a in alts} <= {"rail", "air"}  # ...but the hop can still change mode
    assert rr.plan_reroutes(nx.DiGraph(), {"horizon": 3, "dates": [], "edges": [], "nodes": []})["options"] == []


# ------------------------------------------------------------------ endpoints and the three scenarios
def test_scenario_list_activate_and_clear():
    body = client.get("/weather/simulated-scenarios").json()
    assert [s["id"] for s in body["scenarios"]] == sorted(SCENARIOS) and body["active"] is None
    assert client.post("/weather/simulated-scenarios", json={"id": "nope"}).status_code == 404
    assert client.post("/weather/simulated-scenarios", json={"id": SCENARIOS[0]}).json()["active"] == SCENARIOS[0]
    assert client.get("/weather/risk").json()["data_quality"] == "simulated"
    assert client.get("/weather/status").json()["mode"] == "simulated"
    assert client.post("/weather/simulated-scenarios", json={"id": None}).json()["active"] is None
    assert client.get("/weather/risk").json()["data_quality"] != "simulated" or settings.mock_weather


@pytest.mark.parametrize("sid", SCENARIOS)
def test_scenario_end_to_end(sid):
    client.post("/weather/simulated-scenarios", json={"id": sid})
    risk = client.get("/weather/risk", params={"horizon": 7}).json()
    assert risk["data_quality"] == "simulated" and risk["scenario"]["id"] == sid and risk["mapping"]
    assert len(risk["summary"]["max_risk_by_day"]) == 7 and "Open-Meteo" in risk["attribution"]
    applied = client.post("/weather/apply", json={"horizon": 7, "min_level": "high"}).json()
    events = applied["events"]
    assert events and all(e["source"] == "weather" for e in events)
    sim = client.post("/simulate", json={"events": events, "horizon": 30})
    assert sim.status_code == 200, sim.text
    reroute = client.post("/weather/reroute", json={"horizon": 7, "events": events})
    assert reroute.status_code == 200, reroute.text
    body = reroute.json()
    assert body["blocked_routes"] and body["applied_strategy_summary"]["name"] == "Weather-aware reroute"
    chaos = client.get("/weather/chaos", params={"horizon": 7}).json()
    hazards = client.get("/weather/hazards", params={"horizon": 7}).json()
    assert hazards["features"] and all(len(f["daily"]) == 7 for f in hazards["features"])
    results = sim_hz.check_expected(sim_hz.get_scenario(sid), weather_graph(), risk, body, chaos)
    failed = [r for r in results if not r["passed"]]
    assert not failed, failed


def test_scenarios_are_deterministic():
    client.post("/weather/simulated-scenarios", json={"id": SCENARIOS[1]})
    a = client.get("/weather/risk").json()
    b = client.get("/weather/risk").json()
    assert [e["daily"] for e in a["edges"]] == [e["daily"] for e in b["edges"]]


def test_apply_is_reversible_and_keeps_user_events():
    client.post("/weather/simulated-scenarios", json={"id": SCENARIOS[0]})
    events = client.post("/weather/apply", json={}).json()["events"]
    assert service.state.applied
    assert client.delete("/weather/apply").json() == {"cleared": True} and service.state.applied == []
    user = {"type": "node", "target": "S1", "start": 1, "duration": 3, "severity": 1}
    r = client.post("/simulate", json={"events": [user] + events})
    assert r.status_code == 200


def test_weather_strategy_joins_the_live_strategy_list(monkeypatch):
    monkeypatch.setattr(settings, "mock_network", False)  # fully live: the shown preset is the engine's preset
    monkeypatch.setattr(settings, "mock_recover", False)
    client.post("/weather/simulated-scenarios", json={"id": SCENARIOS[2]})
    events = client.post("/weather/apply", json={}).json()["events"]
    names = [s["name"] for s in client.post("/recover", json={"events": events}).json()["strategies"]]
    assert "Weather-aware reroute" in names
    plain = client.post("/recover", json={"events": [{"type": "node", "target": "S2", "start": 2, "duration": 5, "severity": 1}]}).json()
    assert "Weather-aware reroute" not in [s["name"] for s in plain["strategies"]]  # unchanged without weather events


# ------------------------------------------------------------------ live mode, offline fallback
def test_live_mode_uses_providers(monkeypatch):
    handler, calls = canned_transport(rain=150, gust=70)
    use_transport(monkeypatch, handler)
    body = client.get("/weather/risk").json()
    assert body["data_quality"] == "live" and calls["n"] > 0
    assert body["summary"]["high_risk_edges"] > 0
    assert body["sampling"]["cells"] <= settings.weather_max_cells
    # cached for 30 minutes: a second call makes no requests
    before = calls["n"]
    client.get("/weather/risk")
    assert calls["n"] == before
    status = client.get("/weather/status").json()
    assert any(p["provider"] == "forecast" and p["ok"] for p in status["providers"])


def test_provider_timeout_falls_back_to_disk_cache_then_unavailable(monkeypatch):
    handler, _ = canned_transport(rain=150)
    use_transport(monkeypatch, handler)
    assert client.get("/weather/risk").json()["data_quality"] == "live"  # fills the disk cache
    prov.reset_state()  # memory cache gone; disk cache remains
    failing, _ = canned_transport(fail=("forecast", "flood", "marine", "quakes", "gdacs"))
    use_transport(monkeypatch, failing)
    cached = client.get("/weather/risk").json()
    assert cached["data_quality"] == "cached" and cached["summary"]["high_risk_edges"] > 0
    shutil.rmtree(prov.cache_dir(), ignore_errors=True)
    prov.reset_state()
    none = client.get("/weather/risk")
    assert none.status_code == 200 and none.json()["data_quality"] == "unavailable" and none.json()["warnings"]


def test_partial_provider_failure_gives_partial_results(monkeypatch):
    handler, _ = canned_transport(rain=150, fail=("flood", "quakes"))
    use_transport(monkeypatch, handler)
    body = client.get("/weather/risk").json()
    assert body["data_quality"] in ("live", "cached") and body["summary"]["high_risk_edges"] > 0
    assert any("Flood" in w for w in body["warnings"]) and any("Earthquake" in w for w in body["warnings"])


def test_offline_by_design_uses_cache_then_simulated(monkeypatch):
    handler, _ = canned_transport(rain=150)
    use_transport(monkeypatch, handler)
    client.get("/weather/risk")
    prov.reset_state()
    monkeypatch.setattr(settings, "mock_weather", True)  # offline: never call the providers
    assert client.get("/weather/risk").json()["data_quality"] == "cached"
    shutil.rmtree(prov.cache_dir(), ignore_errors=True)
    prov.reset_state()
    assert client.get("/weather/risk").json()["data_quality"] == "simulated"


def test_refresh_is_rate_limited(monkeypatch):
    handler, calls = canned_transport()
    use_transport(monkeypatch, handler)
    client.get("/weather/risk")
    first = calls["n"]
    body = client.get("/weather/risk", params={"refresh": True}).json()
    assert calls["n"] == first and any("10 minutes" in n for n in body["notes"])


def test_quakes_from_usgs_raise_site_risk(monkeypatch):
    quake = {"geometry": {"coordinates": [73.8, 20.7, 10]}, "properties": {"mag": 6.2, "time": int(__import__("time").time() * 1000)}}
    handler, _ = canned_transport(quakes=[quake])
    use_transport(monkeypatch, handler)
    body = client.get("/weather/risk").json()
    f3 = next(n for n in body["nodes"] if n["id"] == "F3")
    assert f3["max_level"] in ("high", "severe") and "earthquake" in f3["daily"][0]["reason"]
    assert any(h["type"] == "quake" for h in body["hotspots"])


# ------------------------------------------------------------------ any network
def _manual_coastal_network():
    """Manual builder network with a Chennai port and a sea lane up the coast."""
    def node(body):
        r = client.post("/network/nodes", json=body)
        assert r.status_code in (200, 201), r.text
        return r.json()["node"]["id"]

    s = node({"kind": "supplier", "name": "Chennai Port Supplier", "city": "Chennai", "lat": 13.1, "lon": 80.3, "capacity": 600, "stock": 500})
    f = node({"kind": "factory", "name": "Bengaluru Plant", "city": "Bengaluru", "lat": 12.97, "lon": 77.59, "capacity": 600, "stock": 300})
    w = node({"kind": "warehouse", "name": "Visakhapatnam Port DC", "city": "Visakhapatnam", "lat": 17.69, "lon": 83.22, "capacity": 600, "stock": 300})
    c = node({"kind": "customer", "name": "Hyderabad Retail", "city": "Hyderabad", "lat": 17.44, "lon": 78.38, "daily_demand": 150, "stock": 300})
    for src, dst, mode in ((s, f, "road"), (f, w, "road"), (s, w, "sea"), (w, c, "road")):
        r = client.post("/network/edges", json={"source": src, "target": dst, "capacity": 400, "mode": mode})
        assert r.status_code in (200, 201), r.text
    assert client.put("/network/source", json={"source": "manual"}).status_code == 200
    return s, f, w, c


def test_manual_network_with_sea_lane_under_the_cyclone():
    _manual_coastal_network()
    client.post("/weather/simulated-scenarios", json={"id": "cyclone-east-coast"})
    risk = client.get("/weather/risk").json()
    sea = [e for e in risk["edges"] if e["mode"] == "sea"]
    assert sea and any(d["closed"] for d in sea[0]["daily"][2:4])
    assert any(n["port"] for n in risk["nodes"])
    events = client.post("/weather/apply", json={}).json()["events"]
    assert client.post("/simulate", json={"events": events}).status_code == 200
    body = client.post("/weather/reroute", json={}).json()
    results = sim_hz.check_expected(sim_hz.get_scenario("cyclone-east-coast"), weather_graph(), risk, body)
    assert next(r for r in results if r["check"] == "sea_lanes_closed")["passed"]


def test_city_missing_maps_to_nearest_node():
    _manual_coastal_network()
    client.post("/weather/simulated-scenarios", json={"id": "compound-north-fog-quake"})
    mapping = client.get("/weather/risk").json()["mapping"]
    delhi = next(m for m in mapping if m["wanted"] == "Delhi")
    assert delhi["how"] == "nearest node" and "not in this network" in delhi["note"]


def test_empty_network_and_unlocated_lanes():
    store.source = "manual"  # an empty manual network (the API refuses to activate one; weather must still cope)
    body = client.get("/weather/risk").json()
    assert body["edges"] == [] and body["summary"]["high_risk_edges"] == 0
    G = _graph([("S", "supplier", None, None, {}), ("C", "customer", 28.7, 77.1, {"demand": 50})], [("S", "C", {})])
    import asyncio

    out = asyncio.run(service.assess(G, 3, scenario_id=None))
    assert out["edges"][0]["coverage"] == "no_coordinates" and out["edges"][0]["daily"] == []
    assert any("coordinates" in w for w in out["warnings"])
