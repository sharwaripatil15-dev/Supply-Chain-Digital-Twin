"""Expansion planner: Dijkstra stage, location MILP + greedy, resilience evaluation, API (core/expansion.py)."""
import networkx as nx
import numpy as np
import pytest
from fastapi.testclient import TestClient

import builder
from cache import cache
from core import expansion as X
from core.features import fingerprint
from core.graph import build_network
from core.synth.networks import generate_network
from main import app
from network_store import store
from routers import expansion as exp_router

client = TestClient(app)


def no_llm(evidence, sections):
    raise RuntimeError("no LLM in tests")


@pytest.fixture(autouse=True)
def _fresh():
    cache.clear()
    X.candidates.reset()
    exp_router.jobs.clear()
    yield
    cache.clear()
    X.candidates.reset()
    exp_router.jobs.clear()


def _node(G, n, kind, cap, lat, lon, stock=0.0, demand=0.0):
    G.add_node(n, kind=kind, capacity=float(cap), stock=float(stock), demand=float(demand), name=n, city=n, lat=lat, lon=lon,
               reliability=0.95, backup=False)


def known_case() -> nx.DiGraph:
    """Pune supplier/factory/warehouse; one customer in Pune, two in Delhi. The Pune DC (W1) can only ship 60/day to
    Delhi, so 60/day of Delhi demand is lost: a Delhi warehouse fed from F1 is the obvious optimum."""
    G = nx.DiGraph(unit_price=1000, margin=0.3)
    _node(G, "S1", "supplier", 1000, 18.52, 73.86)
    _node(G, "F1", "factory", 1000, 18.60, 73.80)
    _node(G, "W1", "warehouse", 1000, 18.55, 73.90)
    _node(G, "C1", "customer", 0, 18.50, 73.85, stock=500, demand=100)
    _node(G, "C2", "customer", 0, 28.70, 77.10, stock=100, demand=60)
    _node(G, "C3", "customer", 0, 28.60, 77.20, stock=100, demand=60)
    G.add_edge("S1", "F1", capacity=1000.0, lead=1.0, cost=2.0, co2=0.1)
    G.add_edge("F1", "W1", capacity=1000.0, lead=1.0, cost=2.0, co2=0.1)
    G.add_edge("W1", "C1", capacity=200.0, lead=1.0, cost=2.0, co2=0.1)
    G.add_edge("W1", "C2", capacity=30.0, lead=4.0, cost=60.0, co2=4.0)
    G.add_edge("W1", "C3", capacity=30.0, lead=4.0, cost=60.0, co2=4.0)
    return G


PARAMS = {"types": ["warehouse"], "n_add": 1, "growth": 0.0, "candidate_ids": ["DEL", "TVM", "KOL"], "goal": "cost"}


def test_known_optimum_found_by_milp_and_greedy():
    G = known_case()
    sites = X.candidates.active(PARAMS["candidate_ids"])
    tm = X.transport_model(G, sites)
    P = X.build_problem(G, sites, tm, X.normalize(PARAMS), "cost")
    milp, gr = X.solve_milp(P), X.greedy(P)
    assert milp["status"] == "optimal"
    assert [P.options[o]["site"]["id"] for o in milp["open"]] == ["DEL"]
    assert [P.options[o]["site"]["id"] for o in gr["open"]] == ["DEL"]
    assert gr["objective"] == pytest.approx(X.fixed_set_objective(P, milp["open"]), rel=1e-6)
    r = X.run_expansion(G, PARAMS, narrator=no_llm)
    plan = r["plans"][0]
    assert plan["sites"][0]["candidate"] == "DEL"
    assert plan["service_level_after_pct"] > plan["service_level_before_pct"]  # the engine confirms the lost demand comes back
    assert plan["payback_years"] is not None and plan["annual_savings_inr"] > 0
    assert r["cross_check"]["same_sites"] and r["cross_check"]["greedy_gap_pct"] == pytest.approx(0.0, abs=1e-6)


def test_dijkstra_matrices_match_brute_force():
    G = build_network(7)
    sites = X.candidates.active(["NAG", "IND", "HYD", "VZG", "BHW"])
    tm = X.transport_model(G, sites)
    H = nx.DiGraph()
    for (i, j), v in tm.cost.items():
        H.add_edge(i, j, w=max(v[0], 1e-6))
    for s in sites:
        brute = nx.single_source_dijkstra_path_length(H, tm.index[s["id"]], weight="w")
        for target in list(G):
            j = tm.index[target]
            assert tm.dist[tm.cand_rows[s["id"]], j] == pytest.approx(brute[j], rel=1e-9)
            m = tm.path_metrics(s["id"], target)
            assert m["generalized"] == pytest.approx(brute[j], rel=1e-9)
            assert m["hops"][0]["from"] == s["id"] and m["hops"][-1]["to"] == target
    assert X.transport_model(G, sites) is tm  # cached until the network changes


def test_budget_and_max_facility_constraints():
    G = build_network(7)
    p = {"types": ["warehouse", "factory"], "n_add": 2, "max_per_type": {"factory": 0}, "goal": "service"}
    r = X.run_expansion(G, p, narrator=no_llm)
    assert r["status"] == "ok"
    for plan in r["plans"]:
        assert len(plan["sites"]) == 2 and all(s["kind"] == "warehouse" for s in plan["sites"])
    cheap = sorted(m["build_cost_inr"] for m in r["marginal_values"])
    budget = cheap[0] + cheap[1] + 1
    r2 = X.run_expansion(G, {**p, "budget": budget}, narrator=no_llm)
    for plan in r2["plans"]:
        assert plan["build_cost_inr"] <= budget


def test_infeasible_budget_explains_itself():
    r = X.run_expansion(build_network(7), {"n_add": 2, "budget": 1}, narrator=no_llm)
    assert r["status"] == "infeasible" and "budget" in r["explanation"].lower() and r["plans"] == []
    r = X.run_expansion(build_network(7), {"n_add": 1, "max_lead_days": 0.1}, narrator=no_llm)
    assert r["status"] == "infeasible" and "lead time" in r["explanation"]


def test_original_network_is_untouched_and_networks_of_every_kind_run():
    G = build_network(7)
    before = fingerprint(G)
    r = X.run_expansion(G, {"n_add": 2}, narrator=no_llm)
    assert fingerprint(G) == before and r["status"] == "ok"
    for plan in r["plans"]:
        assert set(plan["new_node_ids"]).isdisjoint(G) and plan["resilience_after"] is not None
        assert plan["health_after"] is not None and len(plan["sensitivity"]) == 2
        for s in plan["sites"]:
            assert s["rationale"] and s["example_paths"]
    gen = generate_network("hub_spoke", "fmcg", 20, seed=2)
    assert X.run_expansion(gen, {}, narrator=no_llm)["status"] in ("ok", "infeasible")
    nodes, edges = builder.graph_to_builder(build_network(7))
    manual = builder.build_graph({n["id"]: n for n in nodes}, {e["id"]: e for e in edges})
    assert X.run_expansion(manual, {}, narrator=no_llm)["status"] == "ok"
    tiny = nx.DiGraph(unit_price=100)
    _node(tiny, "S1", "supplier", 10, 18.5, 73.9)
    _node(tiny, "C1", "customer", 0, 19.1, 72.9, stock=5, demand=10)
    tiny.add_edge("S1", "C1", capacity=10.0, lead=1.0, cost=1.0, co2=0.0)
    assert X.run_expansion(tiny, {}, narrator=no_llm)["status"] in ("ok", "infeasible")
    assert X.run_expansion(nx.DiGraph(), {}, narrator=no_llm)["status"] == "empty"


def test_cancellation_and_template_narrative():
    with pytest.raises(X.Cancelled):
        X.run_expansion(build_network(7), {}, cancelled=lambda: True, narrator=no_llm)
    from core import narrative

    r = X.run_expansion(build_network(7), {}, narrator=no_llm)
    assert r["narrative_source"] == "template"
    assert narrative.ungrounded(narrative.section_texts(r["sections"]), {"plans": r["plans"], "baseline": r["baseline"], "params": r["params"]}) == []


def test_auto_candidates_snap_to_library_cities():
    added = X.auto_candidates(build_network(7), n=3)
    assert len(added) == 3 and all(a["source"] == "auto" for a in added)
    lib = {(s["lat"], s["lon"]) for s in X.candidates.library.values()}
    assert all((a["lat"], a["lon"]) in lib for a in added)


# ---------------------------------------------------------------- API
def test_candidate_endpoints():
    body = client.get("/expansion/candidates").json()
    assert len(body["sites"]) >= 60 and "replace with client data" in body["note"]
    body = client.post("/expansion/candidates", json={"action": "add", "name": "Client yard", "lat": 21.0, "lon": 79.0,
                                                       "fixed_cost": 5e7, "capacity": 300}).json()
    custom = next(s for s in body["sites"] if s["source"] == "custom")
    assert custom["fixed_cost"] == 5e7 and custom["capacity"] == 300
    body = client.post("/expansion/candidates", json={"action": "exclude", "id": "NAG"}).json()
    assert next(s for s in body["sites"] if s["id"] == "NAG")["excluded"]
    assert client.post("/expansion/candidates", json={"action": "exclude", "id": "NOPE"}).status_code == 422
    assert client.post("/expansion/candidates", json={"action": "auto", "n": 2}).status_code == 200
    assert client.get("/expansion/baseline").json()["status"] == "ok"


def test_run_results_cancel_and_apply_is_undoable():
    r = client.post("/expansion/run", params={"wait": True}, json={"n_add": 1})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["status"] == "ok" and len(res["plans"]) == 3
    assert client.get(f"/expansion/results/{res['job_id']}").json()["id"] == res["id"]
    assert client.get("/expansion/latest").json()["id"] == res["id"]
    plan = res["plans"][0]
    before_manual = client.get("/network/manual").json()
    before_source = store.source
    before_ids = {n["id"] for n in client.get("/network").json()["nodes"]}
    v0 = store.version
    a = client.post("/expansion/apply", json={"plan_id": plan["id"]})
    assert a.status_code == 200, a.text
    body = a.json()
    assert store.source == "manual" and store.version > v0
    after = client.get("/network").json()
    ids = {n["id"] for n in after["nodes"]}
    assert ids == before_ids | set(body["added_nodes"])
    lanes = {(e["source"], e["target"]) for e in after["edges"]}
    for e in plan["additions"]["edges"]:
        assert (e["source"], e["target"]) in lanes
    assert client.get("/expansion/latest").json()["status"] == "none"  # new network version
    assert client.post("/expansion/apply", json={"plan_id": plan["id"]}).status_code == 409  # stale plan
    # undo = restore the previous manual records and source (what the UI's undo does, in one step)
    client.post("/network/import", json={"nodes": before_manual["nodes"], "edges": before_manual["edges"]})
    client.put("/network/source", json={"source": before_source})
    assert {n["id"] for n in client.get("/network").json()["nodes"]} == before_ids
    j = client.post("/expansion/run", json={"n_add": 1}).json()
    c = client.post(f"/expansion/results/{j['id']}/cancel").json()
    assert c["status"] in ("cancelled", "ok")
    assert client.get("/expansion/results/nope").status_code == 404
    assert client.post("/expansion/apply", json={"plan_id": "nope"}).status_code == 404
    store.use_preset()
