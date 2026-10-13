"""Tests for core/optimizer.py, core/recommend.py, core/strategies.py and live /recover (seed 7)."""
import time

import pytest
from fastapi.testclient import TestClient

from cache import cache
from config import settings
from core import optimizer, strategies
from core.graph import build_network
from core.recommend import rank_alternate_routes, rank_alternate_suppliers
from main import app
from schemas import Event, RecoverResponse

S2_OUT = [Event(type="node", target="S2", start=2, duration=10, severity=1.0)]
ROUTE_SPIKE = [Event(type="edge", target="F1->W3", start=3, duration=8, severity=1.0),
               Event(type="demand", target="C3", start=4, duration=6, severity=0.5)]


@pytest.fixture(scope="module")
def G():
    return build_network(seed=7)


@pytest.fixture(scope="module")
def rows(G):
    return strategies.run_strategies(G, S2_OUT)


# ---------------------------------------------------------------- optimizer
def test_no_disruption_window_is_trivial(G):
    plan = optimizer.optimize_plan(G, [], optimizer.LEVERS)
    assert plan["unmet"] == 0 and plan["cost"] == 0 and plan["window"] is None


def test_unknown_lever_rejected(G):
    with pytest.raises(ValueError):
        optimizer.optimize_plan(G, S2_OUT, ["teleport"])


def test_levers_never_make_unmet_worse(G):
    nothing = optimizer.optimize_plan(G, S2_OUT, [])
    for levers in (["reroute"], ["safety_stock"], ["reroute", "backup"], list(optimizer.LEVERS)):
        assert optimizer.optimize_plan(G, S2_OUT, levers)["unmet"] <= nothing["unmet"] + 1e-6, levers


def test_backup_lever_uses_backup_and_pays_fee(G):
    plan = optimizer.optimize_plan(G, S2_OUT, ["reroute", "backup"])
    assert plan["backup_used"] and plan["cost_breakdown"]["backup_fee"] == optimizer.BACKUP_FEE
    assert not optimizer.optimize_plan(G, S2_OUT, ["reroute"])["backup_used"]


def test_without_reroute_lanes_stay_within_baseline(G):
    plan = optimizer.optimize_plan(G, S2_OUT, [])
    base = optimizer.baseline(G)["flow"]["flow"]
    assert all(f <= base.get(e, 0) + 1e-6 for day in plan["daily_flows"] for e, f in day.items())
    assert plan["rerouted_lanes"] == []


def test_overtime_capped_at_30pct(G):
    events = [Event(type="node", target="S2", start=1, duration=12, severity=1.0),
              Event(type="node", target="W4", start=5, duration=8, severity=0.9)]
    plan = optimizer.optimize_plan(G, events, optimizer.LEVERS)
    for n, delta in plan["capacity_delta"].items():
        assert delta <= (optimizer.OVERTIME_MAX + optimizer.SHIFT_MAX) * G.nodes[n]["capacity"] + 1


def test_safety_stock_bounded_by_source_stock(G):
    plan = optimizer.optimize_plan(G, S2_OUT, ["safety_stock"])
    moved = sum(a["units"] for a in plan["inventory_actions"])
    source = optimizer.PREPO_SOURCE_SHARE * sum(d["stock"] for _, d in G.nodes(data=True) if d["kind"] == "factory")
    assert 0 < moved <= source + 1
    assert all(a["action"] == "pre-position" and a["day"] < 2 for a in plan["inventory_actions"])


def test_green_plan_cuts_co2(G):
    full = optimizer.optimize_plan(G, S2_OUT, optimizer.LEVERS)
    green = optimizer.optimize_plan(G, S2_OUT, optimizer.LEVERS, w_co2=optimizer.W_CO2 * strategies.GREEN_CO2_MULTIPLIER)
    assert green["co2"] < full["co2"] and green["unmet"] <= full["unmet"] + 1e-6


# ---------------------------------------------------------------- recommend
def test_alternate_suppliers_ranked_with_reasons(G):
    alts = rank_alternate_suppliers(G, ["S2"])
    assert alts and all(a["replaces"] == "S2" and a["supplier"] != "S2" for a in alts)
    assert all(a["spare_capacity"] > 0 and a["reason"] for a in alts)
    assert any(G.nodes[a["supplier"]]["backup"] for a in alts), "the backup supplier should be offered"


def test_alternate_routes_avoid_disruption(G):
    routes = rank_alternate_routes(G, [], [("F1", "W3")])
    assert routes
    for r in routes:
        assert "F1->W3" not in [f"{a}->{b}" for a, b in zip(r["via"], r["via"][1:])]
        assert r["old_via"][-1] == r["via"][-1] == r["destination"]
        assert r["replaces"] == "F1->W3"
        old_lead = sum(G.edges[a, b]["lead"] for a, b in zip(r["old_via"], r["old_via"][1:]))
        new_lead = sum(G.edges[a, b]["lead"] for a, b in zip(r["via"], r["via"][1:]))
        assert r["extra_lead_days"] == pytest.approx(new_lead - old_lead)


# ---------------------------------------------------------------- strategies
def test_all_seven_strategies_present(rows):
    assert [r["name"] for r in rows] == ["Do nothing", "Reroute only", "Reroute + backup", "Inventory buffer",
                                         "Production shift", "Full plan", "Green plan"]
    for r in rows:
        for key in ("cost", "unmet", "delay_avg_days", "recovery_days", "co2", "resilience_after", "safety_check"):
            assert key in r


def test_exactly_one_recommended_and_it_passes(G, rows):
    rec = [r for r in rows if r["recommended"]]
    assert len(rec) == 1 and rec[0]["safety_check"]["passed"]
    price = G.graph["unit_price"]
    passing = [r for r in rows if r["safety_check"]["passed"]]
    assert rec[0]["cost"] + rec[0]["unmet"] * price == min(r["cost"] + r["unmet"] * price for r in passing)


def test_recommended_beats_doing_nothing(rows):
    nothing = next(r for r in rows if r["name"] == "Do nothing")
    rec = next(r for r in rows if r["recommended"])
    assert rec["unmet"] < nothing["unmet"]


def test_roi(G, rows):
    roi = strategies.roi(G, rows)
    nothing = next(r for r in rows if r["name"] == "Do nothing")
    assert roi["inaction_loss"] == pytest.approx(nothing["unmet"] * G.graph["unit_price"], abs=1)
    assert roi["net_saving"] == pytest.approx(roi["inaction_loss"] - roi["fix_cost"], abs=1)
    assert roi["net_saving"] > 0


def test_safety_check_flags_capacity_concentration(G):
    """A plan that strips a plant to feed another must fail: the check is wired, even though the demo's
    supply-limited scenarios never choose such a plan (see the module docstring)."""
    fake_plan = {"capacity_delta": {"F2": -G.nodes["F2"]["capacity"] * 0.9, "F3": G.nodes["F2"]["capacity"] * 0.9},
                 "backup_used": False}
    check = strategies.safety_check(G, [], fake_plan)
    assert not check["passed"] and "single point of failure" in check["warning"]


def test_safety_check_passes_for_capacity_adding_plan(G):
    check = strategies.safety_check(G, S2_OUT, {"capacity_delta": {"F3": 50.0}, "backup_used": True})
    assert check["passed"] and check["warning"] is None


def test_playbook_uses_engine_numbers(G, rows):
    steps = strategies.template_playbook(G, S2_OUT, rows)
    rec = next(r for r in rows if r["recommended"])
    assert any(rec["name"] in s for s in steps)
    days = [int(s.split(":")[0].split()[1]) for s in steps]
    assert days == sorted(days), "steps are in day order"


def test_strategies_runtime(G):
    t = time.perf_counter()
    strategies.run_strategies(G, ROUTE_SPIKE)
    assert time.perf_counter() - t < 15


# ---------------------------------------------------------------- live /recover
@pytest.fixture
def live(monkeypatch):
    for flag in ("mock_network", "mock_simulate", "mock_chaos", "mock_recover"):
        monkeypatch.setattr(settings, flag, False)
    cache.clear()
    yield TestClient(app)
    cache.clear()


def test_live_recover_endpoint(live):
    r = live.post("/recover", json={"events": [e.model_dump() for e in S2_OUT]})
    assert r.status_code == 200, r.text
    body = RecoverResponse.model_validate(r.json())
    assert len(body.strategies) == 7 and sum(s.recommended for s in body.strategies) == 1
    assert body.alternate_suppliers and body.playbook and body.roi.net_saving > 0
    assert "_plan" not in r.text
