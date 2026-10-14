"""Phase 3: bottleneck and pain-point analyzer (core/bottleneck.py, routers/analysis.py)."""
import networkx as nx
import pytest
from fastapi.testclient import TestClient

from cache import cache
from core import bottleneck as B
from core import narrative
from core.graph import build_network
from core.synth.networks import generate_network
from core.synth.profiles import ARCHETYPES
from main import app
from network_store import store
from routers import analysis as analysis_router
from routers.deps import mock_demo_graph

client = TestClient(app)


def no_llm(evidence, sections):
    raise RuntimeError("no LLM in tests")


@pytest.fixture(autouse=True)
def _fresh():
    cache.clear()
    analysis_router.jobs.clear()
    yield
    cache.clear()
    analysis_router.jobs.clear()


def _node(G, n, kind, cap, stock=0.0, demand=0.0, dx=0.0):
    G.add_node(n, kind=kind, capacity=float(cap), stock=float(stock), demand=float(demand), name=n, city="Pune",
               lat=18.5 + dx, lon=73.8 + dx, reliability=0.95, backup=False)


def known_issues_graph() -> nx.DiGraph:
    """One supplier (S1), a saturated factory (F2 carries all flow at 100%), a thin-stock warehouse (W3: 1 day of cover
    vs a 3.6-day target). Everything else is redundant, idle-but-ready, and well stocked."""
    G = nx.DiGraph(unit_price=1000)
    _node(G, "S1", "supplier", 300)
    for i, f in enumerate(("F1", "F2", "F3")):
        _node(G, f, "factory", 100 if f == "F2" else 150, dx=0.01 * i)
    for i, w in enumerate(("W1", "W2", "W3")):
        _node(G, w, "warehouse", 150, stock=100 if w == "W3" else 1500, dx=0.02 * i)
    for i, c in enumerate(("C1", "C2")):
        _node(G, c, "customer", 0, stock=400, demand=50, dx=0.03 * i)  # 8 days: above the 5.4-day target
    cheap = {("S1", "F2"), ("F2", "W3"), ("W3", "C1"), ("W3", "C2")}
    lanes = [("S1", f) for f in ("F1", "F2", "F3")] + [(f, w) for f in ("F1", "F2", "F3") for w in ("W1", "W2", "W3")]
    lanes += [(w, c) for w in ("W1", "W2", "W3") for c in ("C1", "C2")]
    for u, v in lanes:
        G.add_edge(u, v, capacity=300.0, lead=1.0, cost=1.0 if (u, v) in cheap else 1.1, co2=0.0)
    return G


def test_known_issues_produce_exactly_those_findings():
    r = B.analyze(known_issues_graph(), narrator=no_llm)
    assert r["status"] == "ok" and r["errors"] == []
    got = {(f["type"], f["locations"]["nodes"][0]) for f in r["findings"]}
    assert got == {("supplier_concentration", "S1"), ("capacity_saturation", "F2"), ("inventory_risk", "W3")}, \
        [(f["type"], f["title"]) for f in r["findings"]]
    assert len(r["findings"]) == 3
    by = {f["type"]: f for f in r["findings"]}
    assert by["supplier_concentration"]["evidence"]["supplier_hhi"] == pytest.approx(1.0)
    assert set(by["supplier_concentration"]["evidence"]["single_sourced_plants"]) == {"F1", "F2", "F3"}
    assert by["capacity_saturation"]["evidence"]["utilization_pct"] == pytest.approx(100.0)
    inv = by["inventory_risk"]["evidence"]
    assert inv["days_of_cover"] == pytest.approx(1.0) and inv["target_cover_days"] == pytest.approx(1.5 * 2 * 1.2)
    conc = by["supplier_concentration"]  # the single supplier really hurts, and the tested backup fix really helps
    assert conc["impact"]["unmet_units"] > 0
    assert any(fx["id"] == "backup" and fx["result"]["unmet_units"] < conc["impact"]["unmet_units"] for fx in conc["fixes"])


def test_every_finding_has_the_required_fields_and_tested_fixes():
    r = B.analyze(build_network(7), narrator=no_llm)
    assert r["findings"] and r["errors"] == []
    sev = [f["severity"] for f in r["findings"]]
    assert sev == sorted(sev, reverse=True)
    for f in r["findings"]:
        for k in ("id", "title", "type", "locations", "severity", "severity_level", "confidence", "evidence", "why", "root_cause",
                  "business", "fixes", "stress", "impact", "whatif"):
            assert k in f, k
        assert 0 <= f["severity"] <= 100 and f["severity_level"] in {"critical", "high", "medium", "low"}
        assert "simulated" in f["business"]
        for i, fx in enumerate(f["fixes"], start=1):
            assert fx["rank"] == i and {"unmet_units", "delay_avg_days", "revenue_at_risk"} <= set(fx["result"])
            assert "cost_inr" in fx and "benefit_inr" in fx
        nets = [fx["net_inr"] for fx in f["fixes"]]
        assert nets == sorted(nets, reverse=True)
    assert any(fx["result"]["avoided_units"] > 0 for f in r["findings"] for fx in f["fixes"])
    h = r["health"]
    assert 0 <= h["score"] <= 100 and {b["key"] for b in h["breakdown"]} == set(B.HEALTH_WEIGHTS)
    assert sum(b["weight"] for b in h["breakdown"]) == pytest.approx(1.0)
    assert h["after_fixes"]["score"] >= h["score"] and h["after_fixes"]["fixes_applied"]
    assert "severity" in r["severity_formula"]


def test_template_narrative_is_grounded_and_bad_llm_text_is_rejected():
    G = build_network(7)
    r = B.analyze(G, narrator=no_llm)
    ev = {"health": r["health"], "counts": r["counts"], "findings": r["findings"], "constants": r["constants"]}
    assert narrative.ungrounded(narrative.section_texts(r["sections"]), ev) == []

    def liar(evidence, sections):
        return [{"key": s["key"], "paragraphs": ["Losses reach 123,456,789 units."] + s["paragraphs"][1:], "bullets": s["bullets"]}
                for s in sections]

    r2 = B.analyze(G, narrator=liar)
    assert r2["narrative_source"] == "template" and "123456789" in r2["narrative_rejected"].replace(",", "")


# ---------------------------------------------------------------- shadow prices
def test_shadow_price_matches_re_solving_with_one_more_unit():
    G = nx.DiGraph(unit_price=100)
    _node(G, "S1", "supplier", 500)
    _node(G, "F1", "factory", 100)
    _node(G, "F2", "factory", 10)
    _node(G, "C1", "customer", 0, demand=120)
    for u, v in (("S1", "F1"), ("S1", "F2"), ("F1", "C1"), ("F2", "C1")):
        G.add_edge(u, v, capacity=1000.0, lead=1.0, cost=1.0, co2=0.0)
    lp = B.steady_lp(G)
    assert lp["unmet"] == pytest.approx(10.0)
    for n in ("F1", "F2"):
        assert lp["shadow_units"][n] == pytest.approx(1.0)
        plus = B.steady_lp(G, cap_override={n: G.nodes[n]["capacity"] + 1})
        assert lp["unmet"] - plus["unmet"] == pytest.approx(lp["shadow_units"][n], abs=0.01)
    assert lp["shadow_units"]["S1"] == pytest.approx(0.0)  # not binding
    assert B.steady_lp(G, cap_override={"S1": 501})["unmet"] == pytest.approx(lp["unmet"])


def test_shadow_prices_on_the_preset_agree_with_finite_differences():
    G = build_network(7)
    lp = B.steady_lp(G, demand_mult=1.5)
    assert lp["unmet"] > 0
    binding = [n for n, v in lp["shadow_units"].items() if v > 1e-6]
    assert binding
    exact = 0
    for n in binding:
        plus = B.steady_lp(G, demand_mult=1.5, cap_override={n: (G.nodes[n].get("capacity") or 0.0) + 1})
        diff = lp["unmet"] - plus["unmet"]
        assert -1e-6 <= diff <= lp["shadow_units"][n] + 0.01  # the LP value is concave in capacity
        exact += abs(diff - lp["shadow_units"][n]) <= 0.01
    assert exact >= 1


def test_saturation_finding_reports_the_dual_and_its_statement():
    G = known_issues_graph()
    for c in ("C1", "C2"):
        G.nodes[c]["demand"] = 60.0  # F2 binds and its peers cannot cover a surge
    G.nodes["F1"]["capacity"] = G.nodes["F3"]["capacity"] = 10.0
    findings = B.analyze(G, narrator=no_llm)["findings"]
    f = next(f for f in findings if f["type"] == "capacity_saturation" and "F2" in f["locations"]["nodes"])
    ev = f["evidence"]
    assert ev["shadow_price_units_per_unit"] > 0
    assert ev["shadow_price_statement"].startswith(f"+{ev['added_capacity_units_per_day']:,.0f} units/day at F2 recovers")


# ---------------------------------------------------------------- every network type
@pytest.mark.parametrize("archetype", ARCHETYPES)
def test_runs_on_every_synthetic_archetype(archetype):
    r = B.analyze(generate_network(archetype, "pharma", 12, seed=5), narrator=no_llm)
    assert r["status"] == "ok" and r["errors"] == []
    assert r["health"]["score"] is not None


def test_minimal_empty_and_degenerate_networks():
    G = nx.DiGraph(unit_price=100)
    _node(G, "S1", "supplier", 10)
    _node(G, "C1", "customer", 0, stock=5, demand=10)
    G.add_edge("S1", "C1", capacity=10.0, lead=1.0, cost=1.0, co2=0.0)
    r = B.analyze(G, narrator=no_llm)
    assert r["status"] == "ok" and r["errors"] == []
    assert B.analyze(nx.DiGraph(), narrator=no_llm)["status"] == "empty"
    H = nx.DiGraph()
    _node(H, "C1", "customer", 0, demand=5)
    assert B.analyze(H, narrator=no_llm)["status"] == "empty"
    assert B.analyze(mock_demo_graph(), narrator=no_llm)["status"] == "ok"


# ---------------------------------------------------------------- endpoints
def test_analysis_endpoints_and_cache_invalidation():
    assert client.get("/analysis/latest").json()["status"] == "none"
    r = client.post("/analysis/run", params={"wait": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["findings"] and body["network"]["version"] == store.version
    assert client.get("/analysis/latest").json()["generated_at"] == body["generated_at"]  # cached
    assert client.post("/analysis/run").json()["generated_at"] == body["generated_at"]
    fid = body["findings"][0]["id"]
    assert client.get(f"/analysis/finding/{fid}").json()["id"] == fid
    assert client.get("/analysis/finding/F99").status_code == 404
    store.use_preset()  # any network change bumps the version
    assert client.get("/analysis/latest").json()["status"] == "none"
    assert client.get(f"/analysis/finding/{fid}").status_code == 404


def test_analysis_on_an_empty_manual_network_is_a_clear_409():
    try:
        client.post("/network/reset", params={"to": "empty"})
        store.source = "manual"
        assert client.post("/analysis/run", params={"wait": True}).status_code == 409
    finally:
        store.use_preset()
