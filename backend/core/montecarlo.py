"""Monte Carlo over uncertain disruptions. Owner: A.

For each run (seeded, reproducible), every template event is perturbed:
    duration ~ LogNormal(mu = ln(duration), sigma = DURATION_SIGMA), rounded, >= 1 day
               (heavy right tail: most outages end roughly on time, a few run much longer);
    severity ~ Beta with mean = template severity (clipped to 0.02..0.98) and concentration SEVERITY_K,
               so a total outage stays near-total and a 50% hit varies around 50%;
    start    = template start + uniform integer jitter in [-START_JITTER, +START_JITTER], >= 0.
Each run is a full core.sim.simulate(); the statistic is total unmet units over the horizon.
Reports P50, P90, P(shortage) = share of runs with any unmet demand, and a 15-bin histogram.
Results are cached per (graph, events, n, seed, horizon).
"""
from __future__ import annotations

import math
from typing import Iterable

import networkx as nx
import numpy as np

from core.chaos import _fingerprint
from core.sim import simulate
from schemas import Event

DURATION_SIGMA = 0.4
SEVERITY_K = 20.0
START_JITTER = 2
BINS = 15

_CACHE: dict[tuple, dict] = {}


def sample_events(template: Iterable[Event], rng: np.random.Generator) -> list[Event]:
    """Draw one random realisation of the template events."""
    out = []
    for ev in template:
        duration = max(1, int(round(rng.lognormal(math.log(ev.duration), DURATION_SIGMA))))
        mean = min(0.98, max(0.02, ev.severity))
        severity = float(rng.beta(mean * SEVERITY_K, (1 - mean) * SEVERITY_K)) if ev.severity > 0 else 0.0
        start = max(0, ev.start + int(rng.integers(-START_JITTER, START_JITTER + 1)))
        out.append(ev.model_copy(update={"duration": min(duration, 365), "severity": severity, "start": start}))
    return out


def monte_carlo(G: nx.DiGraph, template: Iterable[Event], n: int = 200, seed: int = 7, horizon: int = 30) -> dict:
    """Returns {p50, p90, p_shortage, histogram:[{bin, count}]} (POST /montecarlo shape)."""
    template = list(template)
    key = (_fingerprint(G), tuple(e.model_dump_json() for e in template), n, seed, horizon)
    if key in _CACHE:
        return _CACHE[key]
    rng = np.random.default_rng(seed)
    totals = np.array([simulate(G, sample_events(template, rng), horizon)["total_unmet"] for _ in range(n)])
    if totals.max() > totals.min():
        counts, edges = np.histogram(totals, bins=BINS)
    else:  # every run identical (e.g. no shortage at all): one bin
        counts, edges = np.array([n]), np.array([totals.min(), totals.min() + 1])
    result = {
        "p50": round(float(np.percentile(totals, 50)), 1),
        "p90": round(float(np.percentile(totals, 90)), 1),
        "p_shortage": round(float((totals > 0).mean()), 3),
        "histogram": [{"bin": round(float(edges[i]), 1), "count": int(c)} for i, c in enumerate(counts)],
    }
    _CACHE[key] = result
    return result
