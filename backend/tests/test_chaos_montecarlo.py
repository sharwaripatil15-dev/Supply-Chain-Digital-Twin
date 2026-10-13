"""Tests for core/chaos.py and core/montecarlo.py (real engine, seed 7)."""
import time

import pytest
from fastapi.testclient import TestClient

from cache import cache
from config import settings
from core import chaos, montecarlo
from core.graph import build_network
from core.sim import simulate
from main import app
from schemas import ChaosResponse, Event, MonteCarloResponse

S2_OUTAGE = [Event(type="node", target="S2", start=2, duration=10, severity=1.0)]


@pytest.fixture(scope="module")
def G():
    return build_network(seed=7)


@pytest.fixture
def cold_caches():
    chaos._SCAN_CACHE.clear()
    montecarlo._CACHE.clear()
    yield
    chaos._SCAN_CACHE.clear()
    montecarlo._CACHE.clear()


# ---------------------------------------------------------------- chaos
def test_targets_exclude_backup_and_customers(G):
    t = chaos.targets(G)
    backup = next(n for n, d in G.nodes(data=True) if d["backup"])
    assert backup not in t and not any(x.startswith(f"{backup}->") for x in t)
    assert not any(G.nodes[x]["kind"] == "customer" for x in t if "->" not in x)
    assert len(t) == 11 + G.number_of_edges() - G.out_degree(backup)


def test_at_least_one_hidden_pair_on_seed_7(G):
    body = ChaosResponse.model_validate(chaos.chaos_find(G))
    assert body.hidden_pairs, "the demo needs a genuine hidden pair"
    s = chaos.scan(G)
    for hp in body.hidden_pairs:
        a, b = hp.pair
        v = s["pairs"][(a, b)]
        assert v["synergy"] == pytest.approx(v["unmet"] - s["singles"][a] - s["singles"][b])
        assert v["synergy"] > chaos.HIDDEN_SYNERGY


def test_hidden_pair_is_confirmed_by_the_simulator(G):
    """The top hidden pair must hurt more together in the day-by-day simulator too, not just in the flow scan."""
    a, b = chaos.chaos_find(G)["hidden_pairs"][0]["pair"]

    def outage(t):
        return Event(type="edge" if "->" in t else "node", target=t, start=2, duration=10, severity=1.0)

    ua = simulate(G, [outage(a)])["total_unmet"]
    ub = simulate(G, [outage(b)])["total_unmet"]
    uab = simulate(G, [outage(a), outage(b)])["total_unmet"]
    assert uab > ua + ub


def test_spof_sorted_and_resilience_in_range(G):
    r = chaos.chaos_find(G)
    units = [s["unmet"] for s in r["spof"]]
    assert units == sorted(units, reverse=True) and units[0] > 0
    assert 0 <= r["resilience_score"] <= 100
    assert r["resilience_score"] == chaos.resilience_score(G)


def test_pruning_kicks_in_for_large_target_lists(G, monkeypatch, cold_caches):
    monkeypatch.setattr(chaos, "PRUNE_ABOVE", 10)
    monkeypatch.setattr(chaos, "PRUNE_TO", 6)
    s = chaos.scan(G)
    assert s["pruned"] and len(s["pairs"]) == 15  # C(6, 2)


def test_chaos_runtime_under_10s(G, cold_caches):
    t = time.perf_counter()
    chaos.chaos_find(G)
    assert time.perf_counter() - t < 10
    t = time.perf_counter()
    chaos.chaos_find(G)
    assert time.perf_counter() - t < 0.5, "second call should come from the cache"


# ---------------------------------------------------------------- monte carlo
def test_monte_carlo_shape_and_determinism(G, cold_caches):
    r = MonteCarloResponse.model_validate(montecarlo.monte_carlo(G, S2_OUTAGE, n=200))
    assert sum(b.count for b in r.histogram) == 200
    assert 0 < r.p50 <= r.p90 and 0 < r.p_shortage <= 1
    montecarlo._CACHE.clear()
    assert montecarlo.monte_carlo(G, S2_OUTAGE, n=200) == r.model_dump()


def test_monte_carlo_no_shortage_scenario(G, cold_caches):
    r = montecarlo.monte_carlo(G, [Event(type="edge", target="F1->W3", start=3, duration=8, severity=1.0)], n=50)
    assert r["p_shortage"] == 0 and r["p50"] == r["p90"] == 0
    assert sum(b["count"] for b in r["histogram"]) == 50


def test_sampled_events_stay_valid():
    import numpy as np

    rng = np.random.default_rng(1)
    for _ in range(300):
        for e in montecarlo.sample_events(S2_OUTAGE + [Event(type="demand", target="C3", start=0, duration=3, severity=0.4)], rng):
            assert e.start >= 0 and e.duration >= 1 and 0 <= e.severity <= 1


def test_monte_carlo_runtime_under_10s(G, cold_caches):
    t = time.perf_counter()
    montecarlo.monte_carlo(G, S2_OUTAGE, n=200)
    assert time.perf_counter() - t < 10


# ---------------------------------------------------------------- live routers
@pytest.fixture
def live(monkeypatch):
    for flag in ("mock_network", "mock_simulate", "mock_chaos"):
        monkeypatch.setattr(settings, flag, False)
    cache.clear()
    yield TestClient(app)
    cache.clear()


def test_live_chaos_endpoint(live):
    r = live.get("/chaos")
    assert r.status_code == 200
    assert ChaosResponse.model_validate(r.json()).hidden_pairs


def test_live_montecarlo_endpoint(live):
    events = [{"type": "node", "target": "S2", "start": 2, "duration": 10, "severity": 1.0}]
    r = live.post("/montecarlo", json={"events": events, "n": 200})
    assert r.status_code == 200
    assert MonteCarloResponse.model_validate(r.json()).p_shortage > 0


def test_live_network_uses_real_resilience(live, G):
    assert live.get("/network").json()["resilience_score"] == chaos.resilience_score(G)
