"""Tests for core/risk_ml.py, core/forecast.py and llm/parser.py (no network calls: the LLM client is faked)."""
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from cache import cache
from config import settings
from core import forecast, risk_ml
from core.chaos import failure_unmet
from core.graph import build_network
from core.sim import _active_state, simulate
from llm import parser
from main import app
from schemas import Event, NetworkResponse, ParseResponse

client = TestClient(app)


@pytest.fixture(scope="module")
def G():
    return build_network(seed=7)


# ---------------------------------------------------------------- risk model
def test_features_cover_every_node(G):
    X = risk_ml.build_features(G)
    assert list(X.columns) == risk_ml.FEATURES and set(X.index) == set(G.nodes)
    assert X["alternate_paths"].min() >= 0 and X["betweenness"].between(0, 1).all()


def test_dataset_labels_match_engine(G):
    data, secs = risk_ml.generate_dataset(seeds=[7])
    assert len(data) == 12 and secs > 0  # 5 suppliers + 3 factories + 4 warehouses
    for n, row in data.iterrows():
        assert row["label"] == pytest.approx(failure_unmet(G, (n,)))


def test_surrogate_metrics_on_held_out_networks():
    m = risk_ml.surrogate_report()
    assert m["r2"] > 0.7 and m["mae"] < 0.05
    assert m["n_train"] > m["n_test"] > 0 and m["speedup"] > 1
    assert {f["feature"] for f in m["top_features"]} <= set(risk_ml.FEATURES)


def test_node_risk_and_shap(G):
    out = risk_ml.node_risk_with_shap(G)
    assert set(out) == set(G.nodes)
    for n, v in out.items():
        assert 0 <= v["risk"] <= 1 and v["top_factors"]
    # supply-side predictions track the engine (held-out quality is in the metric test above)
    errs = [abs(out[n]["risk"] - failure_unmet(G, (n,))) for n, d in G.nodes(data=True) if d["kind"] != "customer"]
    assert np.mean(errs) < 0.06
    total = sum(d["demand"] for _, d in G.nodes(data=True) if d["kind"] == "customer")
    assert out["C3"]["risk"] == pytest.approx(G.nodes["C3"]["demand"] / total, abs=1e-3)


def test_live_network_uses_model(monkeypatch, G):
    monkeypatch.setattr(settings, "mock_network", False)
    cache.clear()
    body = NetworkResponse.model_validate(client.get("/network").json())
    cache.clear()
    model = risk_ml.node_risk_with_shap(G)
    assert all(n.risk == model[n.id]["risk"] for n in body.nodes)
    assert all(f.feature in risk_ml.FEATURES + ["own_demand_share"] for n in body.nodes for f in n.top_factors)


# ---------------------------------------------------------------- forecast
def test_history_is_seeded(G):
    a, b = forecast.demand_history(G), forecast.demand_history(G)
    assert all(np.array_equal(a[c], b[c]) for c in a)
    assert all(len(v) == forecast.HISTORY_DAYS for v in a.values())


def test_forecast_quality_and_bands(G):
    fc = forecast.forecast_demand(G, 14)
    assert fc["mape"] < 0.15
    for c in fc["customers"]:
        widths = [p["p90"] - p["p10"] for p in c["forecast"]]
        assert all(p["p10"] <= p["mean"] <= p["p90"] for p in c["forecast"])
        assert widths == sorted(widths), "uncertainty grows with the horizon"


def test_holt_winters_recovers_a_clean_season():
    y = 100 + 10 * np.sin(2 * np.pi * np.arange(42) / 7)
    model = forecast.fit(y)
    assert np.allclose(forecast.predict(model, 7), 100 + 10 * np.sin(2 * np.pi * np.arange(42, 49) / 7), atol=1.0)


def test_spike_uses_forecast_baseline(G):
    ratio = forecast.demand_ratio(G, 30)
    ev = Event(type="demand", target="C1", start=3, duration=2, severity=0.5)
    _, _, mult = _active_state([ev], 3, ratio)
    assert mult["C1"] == pytest.approx(ratio["C1"][3] * 1.5)
    _, _, plain = _active_state([ev], 3)
    assert plain["C1"] == pytest.approx(1.5)


def test_simulate_spike_is_deterministic(G):
    ev = [Event(type="demand", target="C1", start=3, duration=5, severity=0.6)]
    assert simulate(G, ev) == simulate(G, ev)


# ---------------------------------------------------------------- LLM parser (faked client)
class _FakeMessages:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.parsed, self.stop_reason, self.calls = parsed, stop_reason, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=self.parsed, stop_reason=self.stop_reason)


def _fake(monkeypatch, parsed, stop_reason="end_turn"):
    msgs = _FakeMessages(parsed, stop_reason)
    monkeypatch.setattr(parser, "_client", lambda: SimpleNamespace(messages=msgs))
    return msgs


def test_parse_without_key_fails_gracefully(monkeypatch, G):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(parser.LLMUnavailable, match="event builder"):
        parser.parse_scenario("Chennai supplier floods", G)


def test_parse_valid_events(monkeypatch, G):
    ev = [Event(type="node", target="S2", start=2, duration=10, severity=1.0)]
    msgs = _fake(monkeypatch, parser._ParsedScenario(events=ev))
    assert parser.parse_scenario("Chennai electronics supplier down for 10 days from day 2", G) == ev
    call = msgs.calls[0]
    assert call["output_format"] is parser._ParsedScenario and "S2" in call["system"]


@pytest.mark.parametrize("events, fragment", [
    ([], "Couldn't find a disruption"),
    ([Event(type="node", target="X9", start=1, duration=2, severity=0.5)], "unknown node id"),
    ([Event(type="edge", target="S1->C1", start=1, duration=2, severity=0.5)], "unknown edge"),
])
def test_parse_rejects_unusable_answers(monkeypatch, G, events, fragment):
    _fake(monkeypatch, parser._ParsedScenario(events=events))
    with pytest.raises(parser.ScenarioParseError, match=fragment):
        parser.parse_scenario("something", G)


def test_parse_refusal(monkeypatch, G):
    _fake(monkeypatch, None, stop_reason="refusal")
    with pytest.raises(parser.LLMUnavailable, match="declined"):
        parser.parse_scenario("something", G)


def test_parse_endpoint_without_key_returns_ui_message(monkeypatch):
    monkeypatch.setattr(settings, "mock_parse", False)
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    r = client.post("/parse", json={"text": "Chennai supplier floods for a week"})
    assert r.status_code == 503 and "event builder" in r.json()["detail"]


def test_parse_endpoint_with_fake_llm(monkeypatch):
    monkeypatch.setattr(settings, "mock_parse", False)
    _fake(monkeypatch, parser._ParsedScenario(events=[Event(type="demand", target="C3", start=1, duration=5, severity=0.4)]))
    r = client.post("/parse", json={"text": "Bengaluru demand jumps 40% tomorrow for 5 days"})
    assert r.status_code == 200
    assert ParseResponse.model_validate(r.json()).events[0].target == "C3"


# ---------------------------------------------------------------- playbook narration
FACTS = {"recommended_strategy": {"name": "Green plan", "cost": 212200.0, "cost_display": "₹2.1 L", "unmet_units": 0.0,
                                  "inventory_actions": [{"node": "W2", "units": 968, "day": 1}]},
         "roi": {"net_saving": 8045000.0, "net_saving_display": "₹80.5 L"}}


def test_grounding_accepts_copied_numbers():
    steps = ["Day 1: move 968 units to W2.", "Day 2: adopt Green plan (₹2.1 L).", "Day 2: cost ₹2,12,200 total.",
             "Day 3: confirm 0 units unmet.", "Day 12: report ₹80.5 L saved."]
    assert parser.ungrounded_numbers(steps, FACTS) == []


def test_grounding_rejects_invented_numbers():
    assert parser.ungrounded_numbers(["Day 1: move 1,000 units to W2."], FACTS) == [1000.0]


def test_write_playbook_five_grounded_steps(monkeypatch):
    steps = [f"Day {d}: step using ₹2.1 L and 968 units." for d in (1, 2, 3, 4, 5)]
    _fake(monkeypatch, parser._Playbook(steps=steps))
    assert parser.write_playbook(FACTS) == steps


@pytest.mark.parametrize("steps, fragment", [
    (["Day 1: only one step"], "instead of 5"),
    ([f"Day {d}: save ₹99 L" for d in range(1, 6)], "not produced by the engine"),
])
def test_write_playbook_rejects_bad_output(monkeypatch, steps, fragment):
    _fake(monkeypatch, parser._Playbook(steps=steps))
    with pytest.raises(parser.LLMUnavailable, match=fragment):
        parser.write_playbook(FACTS)


def test_recover_falls_back_to_template_without_key(monkeypatch):
    for flag in ("mock_network", "mock_simulate", "mock_chaos", "mock_recover"):
        monkeypatch.setattr(settings, flag, False)
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    cache.clear()
    r = client.post("/recover", json={"events": [{"type": "node", "target": "S2", "start": 2, "duration": 10, "severity": 1.0}]})
    cache.clear()
    assert r.status_code == 200 and r.json()["playbook"]
