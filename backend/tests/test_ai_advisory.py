"""Automated tests for Feature 1: AI/ML-based analysis and recommendations."""
import pytest
from fastapi.testclient import TestClient

from core.ai_advisory import analyze_network_and_recommend
from core.graph import build_network
from main import app
from schemas import AdvisoryResponse

client = TestClient(app)


@pytest.fixture(scope="module")
def G():
    return build_network(seed=7)


def test_ai_advisory_core_functionality(G):
    result = analyze_network_and_recommend(G)

    # 1. Verify summary
    summary = result["summary"]
    assert "network_health" in summary
    assert summary["resilience_score"] > 0
    assert summary["critical_sites_count"] > 0
    assert summary["top_spof_node"] is not None
    assert "XGBoost" in summary["ml_engine"]

    # 2. Verify bottlenecks
    bottlenecks = result["bottlenecks"]
    assert len(bottlenecks) > 0
    for b in bottlenecks:
        assert 0.0 <= b["risk"] <= 1.0
        assert 0.0 <= b["utilization"] <= 1.5
        assert b["node_id"] in G.nodes
        assert len(b["top_shap_factors"]) > 0
        assert b["driver_summary"]

    # 3. Verify recommendations
    recs = result["recommendations"]
    assert len(recs) >= 2
    for r in recs:
        assert r["id"].startswith("rec-")
        assert r["priority"] in ["critical", "high", "medium"]
        assert r["category"]
        assert r["title"]
        assert r["target_node"] in G.nodes or r["target_node"] == "C1"
        assert r["ml_insight"]
        assert r["suggested_action"]
        assert r["expected_impact"]
        if r["simulation_event"]:
            assert r["simulation_event"]["type"] in ["node", "edge", "demand"]
            assert r["simulation_event"]["severity"] > 0


def test_ai_advisory_endpoint():
    response = client.get("/ai-advisory")
    assert response.status_code == 200, response.text
    data = response.json()

    # Validate against Pydantic schema
    validated = AdvisoryResponse.model_validate(data)
    assert validated.summary.network_health in ["Resilient", "Moderate", "Fragile"]
    assert len(validated.bottlenecks) > 0
    assert len(validated.recommendations) > 0

    # Ensure prioritized ordering (critical first if any)
    priorities = [r.priority for r in validated.recommendations]
    assert priorities[0] in ["critical", "high"]


def test_ai_advisory_empty_network():
    import networkx as nx
    empty_G = nx.DiGraph()
    res = analyze_network_and_recommend(empty_G)
    assert res["summary"]["network_health"] == "Empty"
    assert res["bottlenecks"] == []
    assert res["recommendations"] == []
