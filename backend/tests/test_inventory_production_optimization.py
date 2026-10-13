"""Tests for Inventory and Production Plan Optimization (Feature 3)."""
import pytest
from fastapi.testclient import TestClient

from core import optimizer
from core.graph import build_network
from main import app
from schemas import Event

S2_OUT = [Event(type="node", target="S2", start=2, duration=10, severity=1.0)]
FACTORY_DISRUPT = [
    Event(type="node", target="F1", start=2, duration=8, severity=0.8),
    Event(type="demand", target="C3", start=3, duration=6, severity=0.4),
]


@pytest.fixture(scope="module")
def G():
    return build_network(seed=7)


def test_safety_stock_optimization_limits(G):
    plan = optimizer.optimize_plan(G, S2_OUT, ["safety_stock"])
    assert plan["status"] == "Optimal"
    assert len(plan["inventory_actions"]) > 0

    fac_stock = sum(d["stock"] for _, d in G.nodes(data=True) if d["kind"] == "factory")
    max_allowed = optimizer.PREPO_SOURCE_SHARE * fac_stock

    total_prepo = sum(a["units"] for a in plan["inventory_actions"])
    assert 0 < total_prepo <= max_allowed + 1.0

    for a in plan["inventory_actions"]:
        assert a["action"] == "pre-position"
        assert a["day"] < 2
        # Warehouse capacity limit
        w_cap = G.nodes[a["node"]]["capacity"]
        assert a["units"] <= optimizer.PREPO_DAYS * w_cap + 1.0


def test_production_shift_conservation(G):
    plan = optimizer.optimize_plan(G, FACTORY_DISRUPT, ["production_shift", "reroute"])
    assert plan["status"] == "Optimal"
    actions = plan["production_actions"]
    if actions:
        for a in actions:
            assert a["from_factory"] != a["to_factory"]
            assert a["units_per_day"] > 0
            cap_a = G.nodes[a["from_factory"]]["capacity"]
            cap_b = G.nodes[a["to_factory"]]["capacity"]
            assert a["units_per_day"] <= optimizer.SHIFT_MAX * min(cap_a, cap_b) + 1.0


def test_overtime_allocation_ceiling(G):
    plan = optimizer.optimize_plan(G, FACTORY_DISRUPT, ["overtime", "reroute"])
    assert plan["status"] == "Optimal"
    for n, delta in plan["capacity_delta"].items():
        if G.nodes[n]["kind"] in ("factory", "warehouse"):
            cap = G.nodes[n]["capacity"]
            assert delta <= optimizer.OVERTIME_MAX * cap + 1.0


def test_inventory_trajectories_and_insights(G):
    plan = optimizer.optimize_plan(G, S2_OUT, optimizer.LEVERS)
    insights = optimizer.compute_optimization_insights(G, plan, S2_OUT, horizon=30)

    # 1. Financial summary
    fin = insights["financial_summary"]
    assert fin["inaction_loss"] > 0
    assert fin["net_savings"] >= 0
    assert fin["units_saved"] >= 0

    # 2. Daily trajectory
    traj = insights["daily_inventory_trajectory"]
    assert len(traj) == 30
    for pt in traj:
        assert pt["warehouse_stock"] >= 0
        assert pt["factory_stock"] >= 0
        assert pt["safety_buffer"] >= 0
        assert pt["unmet_demand"] >= 0

    # 3. Plant allocations
    allocs = insights["plant_allocations"]
    assert len(allocs) == len([n for n, d in G.nodes(data=True) if d["kind"] == "factory"])
    for a in allocs:
        assert a["baseline_capacity"] > 0
        assert a["utilization_pct"] >= 0


def test_optimize_api_endpoints():
    client = TestClient(app)

    # POST /optimize/plan
    payload = {
        "events": [
            {"type": "node", "target": "S2", "start": 2, "duration": 10, "severity": 1.0}
        ],
        "levers": ["safety_stock", "production_shift", "overtime", "reroute"],
        "horizon": 30,
    }
    resp = client.post("/optimize/plan", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "Optimal"
    assert "daily_inventory_trajectory" in data
    assert len(data["daily_inventory_trajectory"]) == 30
    assert "plant_allocations" in data
    assert len(data["plant_allocations"]) > 0
    assert "financial_summary" in data
    assert data["financial_summary"]["net_savings"] >= 0

    # GET /optimize/plan
    resp_get = client.get("/optimize/plan")
    assert resp_get.status_code == 200
    assert "daily_inventory_trajectory" in resp_get.json()
