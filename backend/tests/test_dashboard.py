"""Tests for the Disruption, Impact, and Recovery Dashboard (Feature 5 / Bullet 10)."""
import pytest
from fastapi.testclient import TestClient

from core.graph import build_network
from main import app
from routers.dashboard import compute_dashboard_summary
from schemas import Event

S2_OUT = [Event(type="node", target="S2", start=2, duration=10, severity=1.0)]


@pytest.fixture(scope="module")
def G():
    return build_network(seed=7)


def test_compute_dashboard_summary(G):
    res = compute_dashboard_summary(G, S2_OUT)

    # 1. Disruptions
    dis = res["disruptions"]
    assert dis["active_events_count"] == 1
    assert "S2" in dis["affected_nodes"]
    assert len(dis["disruptions"]) == 1
    assert dis["disruptions"][0]["target"] == "S2"

    # 2. Impacts
    imp = res["impacts"]
    assert imp["total_demand"] > 0
    assert imp["total_unmet_units"] > 0
    assert 0 <= imp["fulfillment_rate_pct"] <= 100.0
    assert imp["inaction_loss_inr"] > 0
    assert len(imp["regional_impacts"]) > 0
    for reg in imp["regional_impacts"]:
        assert reg["baseline_demand"] > 0
        assert 0 <= reg["fulfillment_pct"] <= 100.0

    # 3. Recovery Strategies
    rec = res["recovery"]
    assert rec["recommended_strategy"]
    assert rec["inaction_loss"] > 0
    assert rec["fix_cost"] >= 0
    assert len(rec["strategies"]) == 7
    assert len(rec["playbook_highlights"]) > 0


def test_dashboard_api_endpoints():
    client = TestClient(app)

    # POST /dashboard/summary
    payload = [
        {"type": "node", "target": "S2", "start": 2, "duration": 10, "severity": 1.0}
    ]
    resp = client.post("/dashboard/summary", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "disruptions" in data
    assert "impacts" in data
    assert "recovery" in data
    assert data["disruptions"]["active_events_count"] == 1

    # GET /dashboard/summary
    resp_get = client.get("/dashboard/summary")
    assert resp_get.status_code == 200
    assert "disruptions" in resp_get.json()
