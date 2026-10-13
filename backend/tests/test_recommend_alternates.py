"""Tests for alternate supplier and transportation route recommendations (Feature 2)."""
import pytest
from fastapi.testclient import TestClient

from core.graph import build_network
from core.recommend import rank_alternate_routes, rank_alternate_suppliers
from main import app
from schemas import Event


@pytest.fixture(scope="module")
def G():
    return build_network(seed=7)


def test_alternate_supplier_scoring_and_ranking(G):
    alts = rank_alternate_suppliers(G, ["S2"])
    assert len(alts) > 0
    for a in alts:
        assert a["replaces"] == "S2"
        assert a["supplier"] != "S2"
        assert a["spare_capacity"] > 0
        assert a["lead"] > 0
        assert "cost_premium_pct" in a
        assert 0 <= a["reliability"] <= 1.0
        assert a["reason"] and len(a["reason"]) > 10
        assert "score" in a and a["score"] >= 0
        assert "is_backup" in a
    # Candidate backup supplier should be available
    assert any(a["is_backup"] for a in alts)


def test_alternate_routes_bypass_disrupted_elements(G):
    routes = rank_alternate_routes(G, down_nodes=[], down_edges=[("F1", "W3")])
    assert len(routes) > 0
    for r in routes:
        assert r["replaces"] == "F1->W3"
        # Disrupted lane F1->W3 must never be present in new path
        lane_pairs = [f"{a}->{b}" for a, b in zip(r["via"], r["via"][1:])]
        assert "F1->W3" not in lane_pairs
        assert len(r["waypoints"]) == len(r["via"])
        assert len(r["old_waypoints"]) == len(r["old_via"])
        for wp in r["waypoints"]:
            assert "id" in wp and "name" in wp and "city" in wp and "kind" in wp
        assert r["spare_capacity"] >= 0


def test_alternate_routes_bypass_disrupted_nodes(G):
    # Disrupt factory F1
    routes = rank_alternate_routes(G, down_nodes=["F1"], down_edges=[])
    for r in routes:
        assert "F1" not in r["via"]
        assert r["destination"] == r["via"][-1]


def test_recommend_endpoint_post():
    client = TestClient(app)
    payload = {
        "events": [
            {"type": "node", "target": "S2", "start": 2, "duration": 8, "severity": 1.0},
            {"type": "edge", "target": "F1->W3", "start": 3, "duration": 6, "severity": 1.0},
        ],
        "down_suppliers": [],
        "down_lanes": [],
    }
    resp = client.post("/recommend/alternates", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "alternate_suppliers" in data
    assert "alternate_routes" in data
    assert "S2" in data["disrupted_suppliers"]
    assert "F1->W3" in data["disrupted_lanes"]
    assert len(data["alternate_suppliers"]) > 0
    assert len(data["alternate_routes"]) > 0


def test_recommend_endpoint_get():
    client = TestClient(app)
    resp = client.get("/recommend/alternates")
    assert resp.status_code == 200
    data = resp.json()
    assert "alternate_suppliers" in data
    assert "alternate_routes" in data
