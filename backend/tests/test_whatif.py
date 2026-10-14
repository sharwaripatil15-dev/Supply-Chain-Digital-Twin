"""Phase 2: what-if recovery planner with grounded reasoning (core/whatif.py, core/narrative.py, routers/whatif.py)."""
import networkx as nx
import pytest
from fastapi.testclient import TestClient

from cache import cache
from config import settings
from core import narrative
from core import whatif as W
from core.graph import build_network
from core.synth.networks import generate_network
from core.synth.profiles import ARCHETYPES
from main import app
from network_store import store
from schemas import Event

client = TestClient(app)


def no_llm(evidence, sections):
    raise RuntimeError("no LLM in tests")


FAST = {"mc_runs": 10, "robustness_runs": 2, "narrator": no_llm}


@pytest.fixture(autouse=True)
def _fresh():
    cache.clear()
    yield
    cache.clear()


def backup_chain() -> nx.DiGraph:
    """S1 (cap 100) and backup S2 (cap 100) -> F1 -> W1 -> C1 (demand 50/day, stock 100 = 2 days)."""
    G = nx.DiGraph(unit_price=4200, seed=1)
    for n, kind, cap, backup in (("S1", "supplier", 100, False), ("S2", "supplier", 100, True), ("F1", "factory", 200, False),
                                 ("W1", "warehouse", 200, False)):
        G.add_node(n, kind=kind, capacity=float(cap), stock=0.0, demand=0.0, backup=backup, city="Pune", lat=18.5, lon=73.9,
                   name=n, reliability=0.9)
    G.add_node("C1", kind="customer", capacity=0.0, stock=100.0, demand=50.0, backup=False, city="Mumbai", lat=19.1, lon=72.9,
               name="C1", reliability=0.9)
    for u, v in (("S1", "F1"), ("S2", "F1"), ("F1", "W1"), ("W1", "C1")):
        G.add_edge(u, v, capacity=200.0, lead=1.0, cost=2.0, co2=0.1)
    return G


S1_DOWN = [Event(type="node", target="S1", start=1, duration=10, severity=1.0)]


# ---------------------------------------------------------------- known answers
def test_known_answer_backup_chain():
    G = backup_chain()
    r = W.run_whatif(G, S1_DOWN, **FAST)
    imp = r["evidence"]["impact"]
    # simulator: backup opens 3 days after the first shortfall (day 1) -> days 1-3 short 150, stock covers 100 -> 50 unmet
    assert imp["unmet_units"] == pytest.approx(50.0)
    assert imp["first_stockout"] == {"node": "C1", "day": 3}
    assert imp["revenue_at_risk"] == pytest.approx(50 * 4200)
    rows = {p["name"]: p for p in r["plans"]}
    assert rows["Do nothing"]["unmet"] == pytest.approx(400.0)  # 10 days x 50 - 100 stock, no backup
    rec = rows[r["recommended"]]
    assert "backup" in rec["levers"] and rec["unmet"] <= 50.0 + 1e-6
    assert rec["safety"]["passed"]
    # the stated rule picked it: minimum total cost among passing plans
    passing = [p for p in r["plans"] if p["safety"]["passed"]]
    assert rec["objective"] == min(p["objective"] for p in passing)
    assert any(p["pareto"] for p in r["plans"]) and rec["pareto"]


def test_known_answer_chain_without_backup_is_all_unmet():
    G = backup_chain()
    G.remove_node("S2")
    r = W.run_whatif(G, S1_DOWN, **FAST)
    assert r["evidence"]["impact"]["unmet_units"] == pytest.approx(400.0)
    texts = " ".join(c["text"] for c in r["evidence"]["cascade"])
    assert "S1" in texts and "C1" in texts and "STOCK-OUT" in texts
    assert r["evidence"]["cascade"][0]["text"].startswith("Day 1:")


def test_attribution_sums_sensibly():
    G = build_network(7)
    r = W.run_whatif(G, [Event(type="node", target="S2", start=2, duration=10, severity=1.0)], **FAST)
    a = r["evidence"]["attribution"]
    rec = next(p for p in r["plans"] if p["recommended"])
    nothing = next(p for p in r["plans"] if p["name"] == "Do nothing")
    assert a["total_benefit_units"] == pytest.approx(nothing["unmet"] - rec["unmet"], abs=0.2)
    assert a["sum_marginal_units"] + a["interaction_units"] == pytest.approx(a["total_benefit_units"], abs=0.2)
    assert {row["lever"] for row in a["rows"]} == set(rec["levers"])
    for row in a["rows"]:
        assert row["marginal_benefit_units"] >= -1.0  # removing a lever never makes the plan serve more
        assert row["unmet_without"] >= rec["unmet"] - 1.0


def test_sensitivity_and_robustness_shape():
    r = W.run_whatif(build_network(7), [Event(type="node", target="S2", start=2, duration=10, severity=1.0)],
                     mc_runs=10, robustness_runs=3, narrator=no_llm)
    ev = r["evidence"]
    assert [s["variant"] for s in ev["sensitivity"]] == ["Duration -30%", "Duration +30%", "Demand -20%", "Demand +20%"]
    assert ev["robustness"]["runs"] == 3 and 0 <= ev["robustness"]["share_best"] <= 1
    assert ev["confidence"]["level"] in {"High", "Medium", "Low"}
    keys = [s["key"] for s in r["sections"]]
    assert keys == ["situation", "impact", "cascade", "recommended", "alternatives", "risks", "confidence", "next_steps"]
    assert all("evidence" in s for s in r["sections"])
    assert "simulated" in r["sections"][0]["paragraphs"][0]
    assert r["brief_markdown"].startswith("# What-if brief")


# ---------------------------------------------------------------- grounded narrative
def test_template_narrative_is_fully_grounded():
    r = W.run_whatif(build_network(7), S1_DOWN, **FAST)
    assert r["narrative_source"] == "template"
    assert narrative.ungrounded(narrative.section_texts(r["sections"]), r["evidence"]) == []


def test_bad_narrative_is_rejected_and_template_used():
    def liar(evidence, sections):
        out = [{"key": s["key"], "paragraphs": list(s["paragraphs"]), "bullets": list(s["bullets"])} for s in sections]
        out[0]["paragraphs"] = ["The outage will cost exactly 9,999,999 units and 77.7% of revenue."]
        return out

    r = W.run_whatif(build_network(7), S1_DOWN, mc_runs=10, robustness_runs=0, narrator=liar)
    assert r["narrative_source"] == "template"
    assert "9999999" in r["narrative_rejected"].replace(",", "")
    assert "9,999,999" not in " ".join(narrative.section_texts(r["sections"]))


def test_faithful_narrative_is_accepted():
    def rewrite(evidence, sections):
        return [{"key": s["key"], "paragraphs": [p.replace("Simulated scenario", "Scenario (simulated)") for p in s["paragraphs"]],
                 "bullets": list(s["bullets"])} for s in sections]

    r = W.run_whatif(build_network(7), S1_DOWN, mc_runs=10, robustness_runs=0, narrator=rewrite)
    assert r["narrative_source"] == "llm" and r["narrative_rejected"] is None
    assert r["sections"][0]["paragraphs"][0].startswith("Scenario (simulated)")
    assert "evidence" in r["sections"][0]  # evidence stays attached


def test_narrator_that_changes_structure_is_rejected():
    r = W.run_whatif(build_network(7), S1_DOWN, mc_runs=10, robustness_runs=0, narrator=lambda e, s: s[:2])
    assert r["narrative_source"] == "template" and "structure" in r["narrative_rejected"]


def test_number_validation_rounding_tolerance():
    ev = {"a": 1234.567, "b": "₹2.9 L", "c": 0.731}
    assert narrative.ungrounded(["1,235 units, 1234.57, ₹2.9 L, 0.73"], ev) == []
    assert narrative.ungrounded(["1,240 units"], ev) == [1240.0]
    assert narrative.ungrounded(["S2 down, lane F1->W3, days 2-5"], {"d": [2, 5]}) == []


# ---------------------------------------------------------------- parsing without an API key
def test_no_api_key_uses_the_rule_parser(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    G = build_network(7)
    events, notes, parser = W.parse_question("What if Supplier S2 fails for 10 days?", G)
    assert parser == "rules"
    assert events == [Event(type="node", target="S2", start=1, duration=10, severity=1.0)]
    events, notes, _ = W.parse_question("What if demand rises 40% in Chennai during the festival season?", G)
    assert events and all(e.type == "demand" and e.severity == pytest.approx(0.4) for e in events)
    assert any("Chennai" in n for n in notes) and any("Festival" in n for n in notes)
    events, _, _ = W.parse_question("lane F1->W3 blocked for 2 weeks from day 3", G)
    assert events == [Event(type="edge", target="F1->W3", start=3, duration=14, severity=1.0)]
    with pytest.raises(W.WhatIfError):
        W.parse_question("tell me a joke", G)


# ---------------------------------------------------------------- follow-up Q&A whitelist
@pytest.fixture(scope="module")
def preset_run():
    G = build_network(7)
    return G, W.run_whatif(G, [Event(type="node", target="S2", start=2, duration=10, severity=1.0)], mc_runs=10,
                           robustness_runs=0, narrator=no_llm)


def test_ask_routes_to_whitelisted_tools(preset_run):
    G, run = preset_run
    a = W.ask(G, run, "Why not air freight?", narrator=no_llm)
    assert a["tool"]["name"] == "compare_plans" and "Expedite by air" in a["tool"]["args"]["names"]
    assert not a["declined"] and a["answer"] and a["narrative_source"] == "template"
    b = W.ask(G, run, "What if the backup supplier is also delayed?", narrator=no_llm)
    assert b["tool"]["name"] == "run_scenario" and b["evidence"]["added_events"]
    assert b["evidence"]["after"]["unmet_units"] >= b["evidence"]["before"]["unmet_units"]
    c = W.ask(G, run, "Try the inventory buffer", narrator=no_llm)
    assert c["tool"] == {"name": "run_strategy", "args": {"name": "Inventory buffer"}}
    for ans in (a, b, c):
        assert narrative.ungrounded(ans["answer"], ans["evidence"]) == []


def test_ask_declines_anything_outside_the_whitelist(preset_run):
    G, run = preset_run
    for q in ("Write me a poem about trucks", "Delete the network", "What is the capital of France?"):
        a = W.ask(G, run, q, narrator=no_llm)
        assert a["declined"] and a["tool"] is None and a["evidence"] is None
    rogue = W.ask(G, run, "Why not air?", router=lambda q, r, g: {"tool": "delete_network", "args": {}}, narrator=no_llm)
    assert rogue["declined"] and "not one of the engine functions" in rogue["answer"][0]
    bad_args = W.ask(G, run, "x", router=lambda q, r, g: {"tool": "run_strategy", "args": {"name": "Teleport"}}, narrator=no_llm)
    assert bad_args["declined"]
    broken = W.ask(G, run, "Why not air freight?", router=lambda q, r, g: 1 / 0, narrator=no_llm)
    assert broken["tool"]["name"] == "compare_plans" and broken["router"] == "rules"  # router failure -> deterministic


# ---------------------------------------------------------------- every network type
@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_runs_on_every_synthetic_archetype(archetype):
    G = generate_network(archetype, "fmcg", 12, seed=3)
    sup = next(n for n, d in G.nodes(data=True) if d["kind"] == "supplier" and not d["backup"])
    r = W.run_whatif(G, [Event(type="node", target=sup, start=1, duration=6, severity=1.0)], mc_runs=10, robustness_runs=0, narrator=no_llm)
    assert r["status"] == "ok" and r["recommended"]
    assert narrative.ungrounded(narrative.section_texts(r["sections"]), r["evidence"]) == []


def test_minimal_and_empty_networks():
    G = nx.DiGraph(unit_price=100)
    G.add_node("S1", kind="supplier", capacity=10.0, stock=0.0, demand=0.0, city="X", lat=10.0, lon=77.0)
    G.add_node("C1", kind="customer", capacity=0.0, stock=5.0, demand=10.0, city="Y", lat=11.0, lon=77.0)
    G.add_edge("S1", "C1", capacity=10.0, lead=1.0, cost=1.0, co2=0.0)
    r = W.run_whatif(G, [Event(type="node", target="S1", start=0, duration=3, severity=1.0)], mc_runs=10, robustness_runs=1, narrator=no_llm)
    assert r["status"] == "ok" and r["evidence"]["impact"]["unmet_units"] == pytest.approx(25.0)
    empty = W.run_whatif(nx.DiGraph(), [], narrator=no_llm)
    assert empty["status"] == "empty" and empty["sections"] == []
    assert W.run_whatif(G, [], narrator=no_llm)["status"] == "empty"


# ---------------------------------------------------------------- endpoints
def test_whatif_endpoints_end_to_end(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    W.history.clear()
    r1 = client.post("/whatif/run", json={"text": "What if Supplier S2 fails for 10 days?", "mc_runs": 10, "robustness_runs": 0})
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["status"] == "ok" and b1["narrative_source"] == "template" and b1["id"]
    r2 = client.post("/whatif/run", json={"events": [{"type": "edge", "target": "F1->W3", "start": 3, "duration": 8, "severity": 1}],
                                          "mc_runs": 10, "robustness_runs": 0})
    assert r2.status_code == 200
    hist = client.get("/whatif/history").json()["runs"]
    assert [h["id"] for h in hist[:2]] == [r2.json()["id"], b1["id"]] and not hist[0]["stale"]
    cmp_ = client.post("/whatif/compare", json={"ids": [b1["id"], r2.json()["id"]]}).json()
    assert len(cmp_["runs"]) == 2 and any(m["key"] == "unmet_units" for m in cmp_["metrics"])
    ask = client.post("/whatif/ask", json={"run_id": b1["id"], "question": "Why not air freight?"}).json()
    assert ask["tool"]["name"] == "compare_plans"
    declined = client.post("/whatif/ask", json={"run_id": b1["id"], "question": "Sing a song"}).json()
    assert declined["declined"]
    brief = client.get(f"/whatif/{b1['id']}/brief")
    assert brief.status_code == 200 and brief.text.startswith("# What-if brief")
    assert client.get("/whatif/nope").status_code == 404
    assert client.post("/whatif/compare", json={"ids": ["a", "b"]}).status_code == 404
    assert client.post("/whatif/run", json={"text": "tell me a joke"}).status_code == 422
    assert client.post("/whatif/run", json={"events": [{"type": "node", "target": "NOPE", "start": 0, "duration": 2, "severity": 1}]}).status_code == 422
    assert client.post("/whatif/run", json={}).status_code == 422


def test_whatif_on_an_empty_manual_network_is_a_clear_409():
    try:
        client.post("/network/reset", params={"to": "empty"})
        store.source = "manual"
        r = client.post("/whatif/run", json={"text": "What if S2 fails?"})
        assert r.status_code == 409 and "can't be simulated" in r.json()["detail"]
    finally:
        store.use_preset()
