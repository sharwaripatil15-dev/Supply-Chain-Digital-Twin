"""Tests for the upgrade: utilization/delay/bottlenecks, recovery alternates, forecast, surrogate, upload, flags."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cache import cache
from config import settings
from core.delay import find_bottlenecks, summarize_delays
from main import app
from routers import deps
from schemas import (
    ForecastResponse,
    NetworkResponse,
    RecoverResponse,
    SimulateResponse,
    SurrogateResponse,
    UploadResponse,
)

client = TestClient(app)
MOCK_DIR = Path(__file__).resolve().parent.parent / "mock"
SUPPLIER_FAILURE = [{"type": "node", "target": "S2", "start": 2, "duration": 10, "severity": 1.0}]


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    deps.set_graph(None)
    yield
    cache.clear()
    deps.set_graph(None)


def _csv(name: str) -> bytes:
    return (MOCK_DIR / name).read_bytes()


def test_network_has_reliability_and_utilization():
    body = NetworkResponse.model_validate(client.get("/network").json())
    assert all(0 <= n.reliability <= 1 for n in body.nodes)
    assert any(n.utilization > 0 for n in body.nodes if n.kind != "customer")


def test_simulate_utilization_delay_bottlenecks():
    body = SimulateResponse.model_validate(client.post("/simulate", json={"events": SUPPLIER_FAILURE}).json())
    assert all(set(d.utilization) == set(d.node_status) for d in body.timeline)
    assert body.delay.p90_days >= body.delay.avg_days > 0
    assert set(body.delay.per_customer) == {"C1", "C2", "C3", "C4", "C5"}
    assert body.bottlenecks and all(b.utilization > 0.9 for b in body.bottlenecks)
    peaks = [b.utilization for b in body.bottlenecks]
    assert peaks == sorted(peaks, reverse=True)


def test_recover_new_strategies_and_actions():
    body = RecoverResponse.model_validate(client.post("/recover", json={"events": SUPPLIER_FAILURE}).json())
    names = " ".join(s.name for s in body.strategies)
    assert "Inventory buffer" in names and "Production shift" in names
    assert all(s.delay_avg_days >= 0 for s in body.strategies)
    assert body.alternate_suppliers and all(a.replaces == "S2" and a.supplier != "S2" for a in body.alternate_suppliers)
    assert body.alternate_routes and all(r.via[0] == r.origin and r.via[-1] == r.destination for r in body.alternate_routes)
    assert body.inventory_actions and body.production_actions
    assert min(body.strategies, key=lambda s: s.cost).safety_check.passed is False


def test_recover_no_supplier_event_has_no_alternate_suppliers():
    events = [{"type": "edge", "target": "F1->W3", "start": 3, "duration": 8, "severity": 1.0}]
    body = RecoverResponse.model_validate(client.post("/recover", json={"events": events}).json())
    assert body.alternate_suppliers == []


def test_forecast():
    r = client.get("/forecast", params={"horizon": 10})
    assert r.status_code == 200
    body = ForecastResponse.model_validate(r.json())
    assert body.horizon_days == 10 and len(body.customers) == 5
    for c in body.customers:
        assert len(c.forecast) == 10
        assert all(p.p10 <= p.mean <= p.p90 for p in c.forecast)
    assert client.get("/forecast", params={"horizon": 0}).status_code == 422


def test_surrogate():
    body = SurrogateResponse.model_validate(client.get("/surrogate").json())
    assert body.mae > 0 and 0 < body.r2 <= 1 and body.n_train > body.n_test > 0
    assert body.top_features


def test_upload_sample_csvs():
    files = {"nodes": ("nodes.csv", _csv("sample_nodes.csv"), "text/csv"),
             "edges": ("edges.csv", _csv("sample_edges.csv"), "text/csv")}
    r = client.post("/upload", files=files)
    assert r.status_code == 200, r.text
    body = UploadResponse.model_validate(r.json())
    assert body.summary.n_nodes == 16 and body.summary.n_edges == 23
    assert body.summary.by_kind == {"customer": 5, "factory": 3, "supplier": 4, "warehouse": 4}
    assert body.network.resilience_score is None
    assert body.activated is False and deps.get_graph() is deps.demo_graph()


def test_upload_activate_switches_live_graph():
    files = {"nodes": ("n.csv", _csv("sample_nodes.csv"), "text/csv"),
             "edges": ("e.csv", _csv("sample_edges.csv"), "text/csv")}
    r = client.post("/upload", params={"activate": True}, files=files)
    assert r.status_code == 200 and r.json()["activated"] is True
    assert deps.get_graph() is not deps.demo_graph()
    assert deps.get_graph().number_of_nodes() == 16


@pytest.mark.parametrize("nodes_csv, edges_csv, fragment", [
    (b"id,kind\nA,supplier\n", b"source,target,capacity,lead,cost\nA,A,1,1,1\n", "missing columns"),
    (b"id,kind,city,lat,lon,capacity,stock,demand\nA,spaceship,X,1,1,1,1,0\n",
     b"source,target,capacity,lead,cost\nA,A,1,1,1\n", "unknown kinds"),
    (b"id,kind,city,lat,lon,capacity,stock,demand\nA,supplier,X,1,1,1,1,0\nB,customer,Y,1,1,0,1,5\n",
     b"source,target,capacity,lead,cost\nA,Z,1,1,1\n", "unknown node ids"),
    (b"id,kind,city,lat,lon,capacity,stock,demand\nA,supplier,X,1,1,lots,1,0\nB,customer,Y,1,1,0,1,5\n",
     b"source,target,capacity,lead,cost\nA,B,1,1,1\n", "non-numeric"),
])
def test_upload_rejects_bad_csv(nodes_csv, edges_csv, fragment):
    files = {"nodes": ("n.csv", nodes_csv, "text/csv"), "edges": ("e.csv", edges_csv, "text/csv")}
    r = client.post("/upload", files=files)
    assert r.status_code == 422
    assert fragment in r.text


def test_upload_warnings_for_soft_problems():
    nodes = b"id,kind,city,lat,lon,capacity,stock,demand\nA,supplier,X,1,1,10,1,0\nB,customer,Y,1,1,0,1,5\nC,customer,Z,1,1,0,1,5\n"
    edges = b"source,target,capacity,lead,cost\nA,B,1,1,1\nB,A,1,1,1\n"
    r = client.post("/upload", files={"nodes": ("n.csv", nodes, "text/csv"), "edges": ("e.csv", edges, "text/csv")})
    assert r.status_code == 200
    warnings = " ".join(r.json()["warnings"])
    assert "downstream" in warnings and "isolated" in warnings and "no path" in warnings


def test_per_router_flags_are_independent(monkeypatch):
    monkeypatch.setattr(settings, "mock_network", False)
    assert client.get("/forecast").json()["method"].startswith("Holt-Winters additive, weekly season (fitted")  # live
    assert client.post("/simulate", json={"events": SUPPLIER_FAILURE}).status_code == 200  # still mocked
    assert client.get("/chaos").json()["resilience_score"] == 62.4  # still the mock value
    assert client.get("/health").json()["mock"]["network"] is False


def test_live_forecast_and_surrogate(monkeypatch):
    monkeypatch.setattr(settings, "mock_network", False)
    fc = ForecastResponse.model_validate(client.get("/forecast", params={"horizon": 10}).json())
    assert len(fc.customers) == 4 and all(len(c.forecast) == 10 for c in fc.customers)
    sg = SurrogateResponse.model_validate(client.get("/surrogate").json())
    assert sg.r2 > 0.7 and sg.n_train > sg.n_test > 0


def test_delay_helpers():
    s = summarize_delays({"a": 0.0, "b": 2.0, "c": 4.0})
    assert s["avg_days"] == 2.0 and s["p90_days"] == pytest.approx(3.6)
    timeline = [{"day": 0, "utilization": {"X": 0.95, "Y": 0.5}}, {"day": 1, "utilization": {"X": 1.1, "Y": 0.92}}]
    assert find_bottlenecks(timeline) == [{"node": "X", "utilization": 1.1, "day": 1}, {"node": "Y", "utilization": 0.92, "day": 1}]
