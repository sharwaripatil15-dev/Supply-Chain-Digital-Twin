"""Tests for the real engine: core/graph.py, core/sim.py, core/delay.py, and the live routers."""
from pathlib import Path

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from cache import cache
from config import settings
from core.delay import arrival_lead
from core.graph import build_network, load_network_from_csv
from core.sim import solve_flow, simulate, unmet_frac
from main import app
from schemas import Event, NetworkResponse, SimulateResponse

MOCK_DIR = Path(__file__).resolve().parent.parent / "mock"


@pytest.fixture(scope="module")
def G():
    return build_network(seed=7)


def ev(**kw) -> Event:
    return Event(**{"start": 2, "duration": 10, "severity": 1.0, **kw})


def biggest_primary(G) -> str:
    return max((n for n, d in G.nodes(data=True) if d["kind"] == "supplier" and not d["backup"]),
               key=lambda n: G.nodes[n]["capacity"])


# ---------------------------------------------------------------- graph
def test_network_shape(G):
    kinds = [d["kind"] for _, d in G.nodes(data=True)]
    assert {k: kinds.count(k) for k in set(kinds)} == {"supplier": 5, "factory": 3, "warehouse": 4, "customer": 4}
    backups = [n for n, d in G.nodes(data=True) if d["backup"]]
    assert len(backups) == 1 and G.nodes[backups[0]]["kind"] == "supplier"
    assert nx.is_directed_acyclic_graph(G)


def test_no_orphans_and_valid_attributes(G):
    assert all(G.degree(n) > 0 for n in G)
    for _, d in G.nodes(data=True):
        assert -90 <= d["lat"] <= 90 and -180 <= d["lon"] <= 180 and 0 < d["reliability"] <= 1
        assert (d["demand"] > 0) == (d["kind"] == "customer")
    for _, _, d in G.edges(data=True):
        assert 1 <= d["lead"] <= 5 and d["capacity"] > 0 and d["cost"] > 0 and d["co2"] > 0
    tier = {"supplier": 0, "factory": 1, "warehouse": 2, "customer": 3}
    assert all(tier[G.nodes[v]["kind"]] == tier[G.nodes[u]["kind"]] + 1 for u, v in G.edges)


def test_demo_scenario_targets_exist(G):
    # the UI's one-click demos and the mock layer rely on these ids/lanes
    for n in ("S2", "W4", "C3"):
        assert n in G
    for e in (("F1", "W3"), ("S1", "F1")):
        assert G.has_edge(*e)


def test_deterministic_for_seed_7(G):
    G2 = build_network(seed=7)
    assert nx.utils.graphs_equal(G, G2)
    events = [ev(type="node", target="S2")]
    assert simulate(G, events) == simulate(G2, events)
    assert not nx.utils.graphs_equal(G, build_network(seed=8))


def test_load_network_from_csv():
    G, warnings = load_network_from_csv(MOCK_DIR / "sample_nodes.csv", MOCK_DIR / "sample_edges.csv")
    assert G.number_of_nodes() == 16 and G.number_of_edges() == 23 and isinstance(warnings, list)
    assert G.graph["unit_price"] > 0


# ---------------------------------------------------------------- flow
def test_baseline_unmet_is_zero(G):
    res = solve_flow(G)
    assert sum(res["unmet"].values()) == 0 and unmet_frac(G, res) == 0
    backup = next(n for n, d in G.nodes(data=True) if d["backup"])
    assert res["throughput"][backup] == 0, "backup stays closed unless allowed"


def test_flow_respects_capacities_and_conservation(G):
    res = solve_flow(G, down_nodes=["S2"], allow_backup=True)
    for (u, v), f in res["flow"].items():
        assert f <= G.edges[u, v]["capacity"] + 1e-9
    for n, d in G.nodes(data=True):
        if d["kind"] in ("factory", "warehouse"):
            inflow = sum(res["flow"].get((u, n), 0) for u in G.predecessors(n))
            outflow = sum(res["flow"].get((n, v), 0) for v in G.successors(n))
            assert inflow == outflow == res["throughput"][n] <= d["capacity"]
    assert res["throughput"]["S2"] == 0


def test_partial_reduction_and_demand_multiplier(G):
    s = biggest_primary(G)
    half = solve_flow(G, node_factor={s: 0.5})
    assert half["throughput"][s] <= 0.5 * G.nodes[s]["capacity"] + 1
    spike = solve_flow(G, demand_multiplier=1.5)
    assert sum(spike["unmet"].values()) > 0


def test_backup_lanes_cost_more(G):
    s = biggest_primary(G)
    closed = solve_flow(G, down_nodes=[s])
    opened = solve_flow(G, down_nodes=[s], allow_backup=True)
    assert sum(opened["unmet"].values()) < sum(closed["unmet"].values())


# ---------------------------------------------------------------- simulate
def test_supplier_failure_raises_unmet(G):
    base = simulate(G, [ev(type="demand", target="C1", severity=0.0)])
    assert base["total_unmet"] == 0 and base["survival_clock_days"] == 30
    r = simulate(G, [ev(type="node", target=biggest_primary(G))])
    assert r["total_unmet"] > 0
    assert r["survival_clock_days"] == min(r["stockout_day"].values()) < 30
    assert r["revenue_at_risk"] == pytest.approx(r["total_unmet"] * G.graph["unit_price"], abs=1)
    assert any("STOCKOUT" in line for line in r["log"])


def test_route_block_raises_delay(G):
    r = simulate(G, [Event(type="edge", target="F1->W3", start=3, duration=8, severity=1.0)])
    assert r["delay"]["avg_days"] > 0 and r["delay"]["p90_days"] >= r["delay"]["avg_days"]
    assert max(r["delay"]["per_customer"].values()) > 0


def test_timeline_contract(G):
    r = SimulateResponse.model_validate(simulate(G, [ev(type="node", target="S2")], horizon=20))
    assert len(r.timeline) == 20
    assert all(set(d.utilization) == set(d.node_status) == set(G.nodes) for d in r.timeline)
    assert r.timeline[2].node_status["S2"] == "down" and r.timeline[2].utilization["S2"] == 0
    assert all(b.utilization > 0.9 for b in r.bottlenecks)
    assert r.timeline[0].unmet == 0
    assert all(s == "ok" for s in r.timeline[0].node_status.values()), "no stress before the first event"


def test_stock_buffers_delay_stockout(G):
    r = simulate(G, [ev(type="node", target=biggest_primary(G))])
    first_out = min(r["stockout_day"].values())
    assert first_out > 2, "customer stock should absorb the first shortfall days"
    assert any(s == "stressed" for d in r["timeline"][2:first_out] for s in d["node_status"].values())


def test_arrival_lead_baseline(G):
    lead = arrival_lead(G, solve_flow(G)["flow"])
    assert all(lead[n] == 0 for n, d in G.nodes(data=True) if d["kind"] == "supplier")
    assert all(lead[c] is not None and lead[c] >= 3 for c, d in G.nodes(data=True) if d["kind"] == "customer")


# ---------------------------------------------------------------- live routers
@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(settings, "mock_network", False)
    monkeypatch.setattr(settings, "mock_simulate", False)
    cache.clear()
    yield TestClient(app)
    cache.clear()


def test_live_network(live, G):
    body = NetworkResponse.model_validate(live.get("/network").json())
    assert len(body.nodes) == G.number_of_nodes() and len(body.edges) == G.number_of_edges()
    assert 0 < body.resilience_score <= 100
    assert all(0 <= n.risk <= 1 and n.top_factors for n in body.nodes)


def test_live_simulate_matches_engine(live, G):
    events = [{"type": "node", "target": "S2", "start": 2, "duration": 10, "severity": 1.0}]
    r = live.post("/simulate", json={"events": events})
    assert r.status_code == 200
    assert r.json()["total_unmet"] == simulate(G, [Event(**events[0])])["total_unmet"]


def test_live_simulate_rejects_unknown_ids(live):
    r = live.post("/simulate", json={"events": [{"type": "node", "target": "C5", "start": 0, "duration": 2, "severity": 1}]})
    assert r.status_code == 422  # C5 exists only in the mock demo network
