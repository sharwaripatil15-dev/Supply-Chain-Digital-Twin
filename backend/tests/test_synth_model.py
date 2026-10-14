"""Phase 1: synthetic generator, disruption library, dataset builder, features and the scenario surrogate."""
import json

import networkx as nx
import numpy as np
import pytest
from fastapi.testclient import TestClient

import builder
from cache import cache
from core import features as F
from core import prescreen, risk_ml
from core.graph import build_network, node_index
from core.sim import simulate, solve_flow
from core.synth import build as synth_build
from core.synth.demos import DEMOS, demo_payload
from core.synth.disruptions import DISRUPTION_TYPES, sample_disruption
from core.synth.networks import SynthError, generate_network, to_builder
from core.synth.profiles import ARCHETYPES, INDUSTRIES
from main import app
from network_store import store
from validation import validate_events

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh():
    cache.clear()
    yield
    cache.clear()


def _dump(G: nx.DiGraph) -> str:
    return json.dumps([sorted(G.graph.items()), sorted((n, sorted(d.items())) for n, d in G.nodes(data=True)),
                       sorted((u, v, sorted(d.items())) for u, v, d in G.edges(data=True))], default=str)


# ---------------------------------------------------------------- generator
def test_generator_is_deterministic():
    a = generate_network("multi_source", "pharma", 33, seed=5)
    b = generate_network("multi_source", "pharma", 33, seed=5)
    c = generate_network("multi_source", "pharma", 33, seed=6)
    assert _dump(a) == _dump(b)
    assert _dump(a) != _dump(c)


@pytest.mark.parametrize("archetype", ARCHETYPES)
@pytest.mark.parametrize("industry", list(INDUSTRIES))
def test_every_archetype_and_industry_passes_the_validator(archetype, industry):
    for n in (10, 37, 60):
        G = generate_network(archetype, industry, n, seed=n)
        assert G.number_of_nodes() == n
        nodes, edges = to_builder(G)
        report = builder.validate(nodes, edges)
        assert report["errors"] == []
        assert {w["code"] for w in report["warnings"]} <= {"no_backup"}, report["warnings"]
        assert not builder.graph_errors(G)
        assert sum(solve_flow(G)["unmet"].values()) == 0  # serves 100% of demand at baseline
        # every builder record is a valid BuilderNode / BuilderEdge (the import path)
        from schemas import BuilderNetwork

        BuilderNetwork.model_validate({"nodes": nodes, "edges": edges})


def test_realism_bands():
    G = generate_network("multi_source", "electronics", 50, seed=1)
    thr = solve_flow(G)["throughput"]
    util = [thr.get(n, 0) / d["capacity"] for n, d in G.nodes(data=True)
            if d["kind"] in ("supplier", "factory", "warehouse") and not d["backup"] and thr.get(n, 0) > 0]
    assert np.mean([0.53 <= u <= 0.87 for u in util]) >= 0.9
    for n, d in G.nodes(data=True):
        assert 0.85 <= d["reliability"] <= 0.99
        if d["kind"] == "customer":
            assert 3 - 1e-6 <= d["stock"] / d["demand"] <= 30 + 1e-6
    modes = {d["mode"] for _, _, d in G.edges(data=True)}
    assert modes <= {"road", "rail", "sea", "air"}
    for u, v, d in G.edges(data=True):
        if d["mode"] == "sea":
            assert G.nodes[u]["port"] and G.nodes[v]["port"]


def test_generator_rejects_unknown_inputs():
    with pytest.raises(SynthError):
        generate_network("ring", "fmcg", 20, 0)
    with pytest.raises(SynthError):
        generate_network("linear", "mining", 20, 0)


# ---------------------------------------------------------------- disruptions
@pytest.mark.parametrize("kind", DISRUPTION_TYPES)
def test_every_disruption_type_produces_valid_events(kind):
    for G in (build_network(7), generate_network("two_region_port", "electronics", 40, seed=2),
              generate_network("linear", "agri", 10, seed=3)):
        nodes, edges = node_index(G)
        rng = np.random.default_rng(0)
        for _ in range(5):
            d = sample_disruption(G, rng, kind)
            assert d["events"], kind
            validate_events(d["events"], nodes, edges)
            assert all(1 <= e.duration <= 30 and 0 <= e.severity <= 1 for e in d["events"])
            simulate(G, d["events"], 30)  # runs on the exact simulator


def test_disruptions_are_deterministic():
    G = generate_network("hub_spoke", "fmcg", 25, seed=4)
    a = [sample_disruption(G, np.random.default_rng(9))["events"] for _ in range(3)]
    b = [sample_disruption(G, np.random.default_rng(9))["events"] for _ in range(3)]
    assert a == b


# ---------------------------------------------------------------- dataset builder
def test_dataset_build_and_no_split_leakage(tmp_path):
    df = synth_build.build(n_networks=10, cases=4, seed=3, fast=True, jobs=1, out_dir=tmp_path, verbose=False)
    assert len(df) == 40 and (tmp_path / "dataset_fast.parquet").exists() and (tmp_path / "DATA_CARD_fast.md").exists()
    assert df.groupby("network_id")["split"].nunique().max() == 1  # each network in exactly one split
    assert set(df["split"]) <= {"train", "val", "calib", "test"}
    assert set(F.SCENARIO_FEATURES) <= set(df.columns) and not df[F.SCENARIO_FEATURES].isna().any().any()
    # labels are reproducible from the stored events with the exact simulator
    row = df.iloc[0]
    archetype, industry, n, net_seed = synth_build.network_spec(3, int(row["network_id"]), True)
    G = generate_network(archetype, industry, n, net_seed)
    from schemas import Event

    events = [Event.model_validate(e) for e in json.loads(row["events_json"])]
    res = simulate(G, events, 30)
    assert synth_build.outcomes(G, res, events)["unmet_pct"] == pytest.approx(row["unmet_pct"])


def test_full_dataset_split_is_grouped():
    df = synth_build.load_dataset()
    if df is None:
        pytest.skip("full dataset not built (python -m core.synth.build)")
    assert len(df) >= 20_000
    assert df.groupby("network_id")["split"].nunique().max() == 1
    train, test = set(df[df.split == "train"].network_id), set(df[df.split == "test"].network_id)
    assert not train & test


# ---------------------------------------------------------------- features (known answers)
def _chain() -> nx.DiGraph:
    G = nx.DiGraph(unit_price=100)
    for n, kind, cap, stock, dem in (("S1", "supplier", 100, 0, 0), ("F1", "factory", 100, 0, 0),
                                     ("W1", "warehouse", 100, 0, 0), ("C1", "customer", 0, 100, 50)):
        G.add_node(n, kind=kind, capacity=float(cap), stock=float(stock), demand=float(dem), city="Pune", lat=18.5, lon=73.9, reliability=0.9)
    for (u, v), lead in zip((("S1", "F1"), ("F1", "W1"), ("W1", "C1")), (1.0, 2.0, 3.0)):
        G.add_edge(u, v, capacity=100.0, lead=lead, cost=1.0, co2=0.0)
    return G


def test_chain_features_known_answers():
    G = _chain()
    nf = F.node_features(G)
    for n in ("S1", "F1", "W1"):
        assert nf.at[n, "articulation"] == 1.0
        assert nf.at[n, "loss_if_down"] == pytest.approx(1.0)
        assert nf.at[n, "flow_share"] == pytest.approx(1.0)
        assert nf.at[n, "alt_paths"] == 0
        assert nf.at[n, "downstream_demand"] == pytest.approx(1.0)
        assert nf.at[n, "extra_lead_alt"] == F.MAX_EXTRA_LEAD
    assert nf.at["F1", "utilization"] == pytest.approx(0.5)
    assert nf.at["C1", "cover_days"] == pytest.approx(2.0)
    assert nf.at["C1", "replenish_lead"] == pytest.approx(6.0)
    assert nf.at["C1", "cover_vs_lead"] == pytest.approx(2.0 / 6.0)
    net = F.network_features(G, nf)
    assert net["supplier_hhi"] == pytest.approx(1.0) and net["n_suppliers"] == 1
    ef = F.edge_features(G)
    assert ef.at["F1->W1", "loss_if_down"] == pytest.approx(1.0) and ef.at["F1->W1", "utilization"] == pytest.approx(0.5)


def _diamond() -> nx.DiGraph:
    """S1 (cheap, cap 60), S2 (cap 60) -> F1 -> W1 (lead 1) / W2 (lead 3) -> C1 (demand 100)."""
    G = nx.DiGraph(unit_price=100)
    for n, kind, cap, dem in (("S1", "supplier", 60, 0), ("S2", "supplier", 60, 0), ("F1", "factory", 200, 0),
                              ("W1", "warehouse", 200, 0), ("W2", "warehouse", 200, 0), ("C1", "customer", 0, 100)):
        G.add_node(n, kind=kind, capacity=float(cap), stock=500.0 if kind == "customer" else 0.0, demand=float(dem),
                   city="Pune", lat=18.5, lon=73.9, reliability=0.9)
    lanes = {("S1", "F1"): (1, 1.0), ("S2", "F1"): (1, 2.0), ("F1", "W1"): (1, 1.0), ("F1", "W2"): (3, 1.0),
             ("W1", "C1"): (1, 1.0), ("W2", "C1"): (1, 1.0)}
    for (u, v), (lead, cost) in lanes.items():
        G.add_edge(u, v, capacity=200.0, lead=float(lead), cost=cost, co2=0.0)
    return G


def test_diamond_features_known_answers():
    G = _diamond()
    nf = F.node_features(G)
    assert nf.at["F1", "articulation"] == 1.0 and nf.at["W1", "articulation"] == 0.0 and nf.at["S1", "articulation"] == 0.0
    assert nf.at["S1", "loss_if_down"] == pytest.approx(0.4)  # S2 alone covers 60 of 100
    assert nf.at["W1", "loss_if_down"] == pytest.approx(0.0)
    assert nf.at["W1", "alt_paths"] == 1
    assert nf.at["W1", "extra_lead_alt"] == pytest.approx(2.0)  # detour via W2: lead 3 instead of 1
    shares = F.supplier_shares(G)
    assert shares == pytest.approx({"S1": 0.6, "S2": 0.4})
    assert F.hhi(shares.values()) == pytest.approx(0.52)


def test_scenario_features_columns_and_values():
    G = _diamond()
    ctx = F.FeatureContext(G)
    from schemas import Event

    f = F.scenario_features(ctx, [Event(type="node", target="S1", start=2, duration=5, severity=1.0)])
    assert list(F.feature_frame([f]).columns) == F.SCENARIO_FEATURES
    assert f["dt_supplier_outage"] == 1.0 and f["capacity_lost_share"] == pytest.approx(0.6)
    assert f["loss_max"] == pytest.approx(0.4) and f["downstream_cover_min"] == pytest.approx(5.0)
    assert f["cover_minus_duration"] == pytest.approx(0.0) and f["duration"] == 5 and f["start"] == 2
    empty = F.scenario_features(ctx, [])
    assert set(empty) == set(F.SCENARIO_FEATURES)


def test_features_on_minimal_and_empty_graphs():
    assert F.node_features(nx.DiGraph()).empty
    G = nx.DiGraph()
    G.add_node("C1", kind="customer", capacity=0.0, stock=0.0, demand=10.0, city="X", lat=0.0, lon=0.0)
    nf = F.node_features(G)
    assert len(nf) == 1 and F.network_features(G, nf)["n_suppliers"] == 0


# ---------------------------------------------------------------- model
@pytest.fixture(scope="module")
def metrics():
    m = risk_ml.scenario_metrics()
    if m is None:
        pytest.skip("no scenario model trained")
    return m


def test_model_beats_both_baselines_on_held_out_networks(metrics):
    assert metrics["dataset"]["test_networks"] > 0 and metrics["dataset"]["train_networks"] > metrics["dataset"]["test_networks"]
    for t, r in metrics["targets"].items():
        for base in ("baseline_mean", "baseline_centrality"):
            assert r["model"]["mae"] < r[base]["mae"], (t, base)
            assert r["model"]["rmse"] < r[base]["rmse"], (t, base)
            assert r["model"]["r2"] > r[base]["r2"], (t, base)
        assert r["model"]["spearman"] > 0.3, t


def test_interval_coverage_in_a_sensible_band(metrics):
    for t, r in metrics["targets"].items():
        assert 0.7 <= r["model"]["interval_coverage"] <= 0.97, (t, r["model"]["interval_coverage"])


def test_predictions_explanations_and_ranges():
    G = build_network(7)
    from schemas import Event

    small = [Event(type="edge", target="F1->W3", start=2, duration=2, severity=0.3)]
    big = [Event(type="node", target="S2", start=1, duration=20, severity=1.0)]
    preds = risk_ml.predict_scenarios(G, [small, big])
    assert preds is not None
    for p in preds:
        for t, v in p.items():
            lo, hi = risk_ml.TARGET_INFO[t][3]
            assert lo <= v["low"] <= v["point"] <= v["high"] <= hi
    assert preds[1]["unmet_pct"]["point"] > preds[0]["unmet_pct"]["point"]
    text = risk_ml.explain_scenario(G, big)
    assert text and all(isinstance(s, str) and s.endswith(".") for s in text)


def test_surrogate_agrees_with_the_exact_simulator():
    out = prescreen.prescreen(build_network(7), n_scenarios=400, top_k=8, seed=3)
    a = out["agreement"]
    assert out["n_scenarios"] == 400 and len(out["candidates"]) == 8
    assert a["spearman"] > 0.3
    assert a["top_mean_exact_unmet_pct"] > a["control_mean_exact_unmet_pct"]
    assert out["timing"]["speedup"] > 1
    for c in out["candidates"]:  # displayed outcomes come from the exact simulator
        assert {"unmet_pct", "total_unmet", "stockout_day"} <= set(c["exact"])


def test_missing_model_degrades_gracefully(monkeypatch, tmp_path):
    monkeypatch.setattr(risk_ml, "_scenario_bundle", None)
    monkeypatch.setattr(risk_ml, "MODEL_PATH", tmp_path / "risk_xgb.joblib")
    assert risk_ml.load_scenario_model(auto_train=False) is None
    assert risk_ml.scenario_model_status()["available"] is False
    monkeypatch.setattr(risk_ml, "load_scenario_model", lambda auto_train=True: None)
    assert risk_ml.predict_scenarios(build_network(7), [[]]) is None
    assert risk_ml.explain_scenario(build_network(7), []) == []


# ---------------------------------------------------------------- endpoints
def test_surrogate_endpoint_reports_scenario_metrics():
    from schemas import SurrogateResponse

    body = client.get("/surrogate").json()
    SurrogateResponse.model_validate(body)
    if body["scenario"] is not None:
        r = body["scenario"]["targets"]["unmet_pct"]
        assert {"mae", "rmse", "r2", "spearman", "top10_recall", "interval_coverage"} <= set(r["model"])
        assert {"baseline_mean", "baseline_centrality"} <= set(r)
        assert body["scenario"]["timing"]["speedup_batch"] > 1


def test_demo_networks_and_generate_go_through_the_import_path():
    opts = client.get("/network/demos").json()
    assert {d["id"] for d in opts["demos"]} == set(DEMOS) and len(opts["archetypes"]) == 7 and len(opts["industries"]) == 6
    try:
        for demo in DEMOS:
            net = client.get(f"/network/demos/{demo}").json()
            assert net["meta"]["industry"] == DEMOS[demo]["industry"]
            r = client.post("/network/import", params={"activate": True}, json=net)
            assert r.status_code == 200, r.text
            assert r.json()["validation"]["errors"] == [] and store.source == "manual"
        gen = client.post("/network/generate", json={"archetype": "concentrated", "industry": "automotive", "n_nodes": 18, "seed": 4}).json()
        assert len(gen["nodes"]) == 18
        assert client.post("/network/import", params={"activate": True}, json=gen).status_code == 200
        r = client.get("/chaos/prescreen", params={"n": 200, "top": 5})
        assert r.status_code == 200 and len(r.json()["candidates"]) == 5
        assert client.get("/network/demos/nope").status_code == 404
        assert client.post("/network/generate", json={"archetype": "ring", "industry": "fmcg"}).status_code == 422
    finally:
        store.use_preset()


def test_demo_payloads_are_stable():
    assert demo_payload("pharma") == demo_payload("pharma")
