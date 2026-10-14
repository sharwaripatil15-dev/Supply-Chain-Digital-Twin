"""Smoke tests: every endpoint returns contract-valid JSON in mock mode."""
import pytest
from fastapi.testclient import TestClient

from cache import cache
from config import settings
from main import app
from schemas import (
    ChaosResponse,
    MonteCarloResponse,
    NetworkResponse,
    ParseResponse,
    RecoverResponse,
    SimulateResponse,
)

client = TestClient(app)

SUPPLIER_FAILURE = [{"type": "node", "target": "S2", "start": 2, "duration": 10, "severity": 1.0}]


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and all(r.json()["mock"].values())


def test_network():
    r = client.get("/network")
    assert r.status_code == 200
    body = NetworkResponse.model_validate(r.json())
    kinds = {n.kind for n in body.nodes}
    assert kinds == {"supplier", "factory", "warehouse", "customer"}
    assert len(body.nodes) == 16
    assert any(n.backup for n in body.nodes)
    ids = {n.id for n in body.nodes}
    assert all(e.source in ids and e.target in ids for e in body.edges)


def test_simulate_ripple():
    r = client.post("/simulate", json={"events": SUPPLIER_FAILURE, "horizon": 30})
    assert r.status_code == 200
    body = SimulateResponse.model_validate(r.json())
    assert len(body.timeline) == 30
    disrupted_days = [d.day for d in body.timeline if any(s != "ok" for s in d.node_status.values())]
    assert max(disrupted_days) - min(disrupted_days) >= 12, "ripple should span at least 12 days"
    assert body.total_unmet > 0 and body.revenue_at_risk > 0
    assert body.survival_clock_days == min(body.stockout_day.values())
    assert body.log


@pytest.mark.parametrize("events", [
    [{"type": "edge", "target": "F1->W3", "start": 3, "duration": 8, "severity": 1.0},
     {"type": "demand", "target": "C3", "start": 4, "duration": 6, "severity": 0.5}],
    [{"type": "node", "target": "W4", "start": 1, "duration": 5, "severity": 0.5}],
])
def test_simulate_other_scenarios(events):
    r = client.post("/simulate", json={"events": events})
    assert r.status_code == 200
    SimulateResponse.model_validate(r.json())


@pytest.mark.parametrize("bad, fragment", [
    ({"type": "node", "target": "NOPE", "start": 0, "duration": 3, "severity": 0.5}, "unknown node"),
    ({"type": "edge", "target": "S1->C1", "start": 0, "duration": 3, "severity": 0.5}, "unknown edge"),
    ({"type": "demand", "target": "S1", "start": 0, "duration": 3, "severity": 0.5}, "must target a customer"),
])
def test_simulate_rejects_bad_targets(bad, fragment):
    r = client.post("/simulate", json={"events": [bad]})
    assert r.status_code == 422
    assert fragment in r.text


def test_simulate_rejects_bad_severity():
    bad = {"type": "node", "target": "S1", "start": 0, "duration": 3, "severity": 1.5}
    assert client.post("/simulate", json={"events": [bad]}).status_code == 422


def test_montecarlo():
    r = client.post("/montecarlo", json={"events": SUPPLIER_FAILURE, "n": 200})
    assert r.status_code == 200
    body = MonteCarloResponse.model_validate(r.json())
    assert body.p90 >= body.p50
    assert sum(b.count for b in body.histogram) == 200


def test_chaos():
    r = client.get("/chaos")
    assert r.status_code == 200
    body = ChaosResponse.model_validate(r.json())
    assert body.spof and body.hidden_pairs
    assert all(p.synergy > 0 for p in body.hidden_pairs)


def test_recover_cheapest_is_unsafe():
    r = client.post("/recover", json={"events": SUPPLIER_FAILURE})
    assert r.status_code == 200
    body = RecoverResponse.model_validate(r.json())
    cheapest = min(body.strategies, key=lambda s: s.cost)
    assert cheapest.safety_check.passed is False and cheapest.safety_check.warning
    recommended = [s for s in body.strategies if s.recommended]
    assert len(recommended) == 1 and recommended[0].safety_check.passed
    assert body.roi.net_saving == pytest.approx(body.roi.inaction_loss - body.roi.fix_cost)
    assert body.playbook


def test_parse():
    r = client.post("/parse", json={"text": "Chennai supplier shuts for 10 days from day 2"})
    assert r.status_code == 200
    assert ParseResponse.model_validate(r.json()).events


def test_live_mode_stubs_return_501(monkeypatch):
    # every core module is implemented now; keep the 501 handler covered with an injected stub
    from core import forecast

    def stub(*_a, **_k):
        raise NotImplementedError("core.forecast.forecast_demand")

    monkeypatch.setattr(settings, "mock_network", False)
    monkeypatch.setattr(forecast, "forecast_demand", stub)
    r = client.get("/forecast", params={"horizon": 3})
    assert r.status_code == 501
    assert "NotImplemented" in r.text or "Not implemented" in r.text


def test_cors_allows_the_browser_extension_only():
    ext = "chrome-extension://" + "a" * 32
    r = client.get("/health", headers={"Origin": ext})
    assert r.headers.get("access-control-allow-origin") == ext
    r = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in r.headers
