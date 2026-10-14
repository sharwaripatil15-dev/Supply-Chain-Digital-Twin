"""Surrogate pre-screen for Chaos Finder: rank thousands of failure scenarios with the ML surrogate, then re-run the
exact simulator on the top candidates. Owner: D.

Candidates: random single and paired failures of the Chaos Finder targets (core.chaos.targets: supply-side sites and
lanes, backup excluded) with severity in SEVERITIES, duration in DURATIONS and start day START, deduplicated.
1. The surrogate (core.risk_ml.predict_scenarios) predicts unmet % for every candidate.
2. The `top_k` highest-scoring candidates AND a random control sample of `top_k` others are re-run with the exact
   simulator (core.sim.simulate). Only exact numbers are reported as outcomes; predictions are screening scores.
3. Agreement: Spearman rank correlation between predicted and exact unmet % over the re-run scenarios, precision@k
   (share of the top candidates whose exact unmet is at least the control sample's 90th percentile and > 0), the
   exact unmet of the top candidates vs the control sample, and how often the exact value fell in the 80% interval.
4. Speedup: (exact ms per scenario x candidates) / (surrogate time + exact time on the top_k).
"""
from __future__ import annotations

import time

import networkx as nx
import numpy as np

from core import chaos, risk_ml
from core.sim import simulate
from node_types import total_demand
from schemas import Event

SEVERITIES = (0.5, 0.8, 1.0)
DURATIONS = (3, 5, 7, 10, 14, 21)
START = 2
PAIR_SHARE = 0.4


def _events(combo: tuple[str, ...], severity: float, duration: int) -> list[Event]:
    return [Event(type="edge" if "->" in t else "node", target=t, start=START, duration=duration, severity=severity) for t in combo]


def _label(combo: tuple[str, ...], severity: float, duration: int) -> str:
    return f"{' + '.join(combo)} at {severity:.0%} for {duration} d"


def candidates(G: nx.DiGraph, n: int, seed: int) -> list[tuple[tuple[str, ...], float, int]]:
    targets = chaos.targets(G)
    if not targets:
        return []
    rng = np.random.default_rng(seed)
    seen: set = set()
    out = []
    space = len(targets) * (1 + (len(targets) - 1) / 2) * len(SEVERITIES) * len(DURATIONS)
    n = int(min(n, space))
    while len(out) < n:
        k = 2 if (len(targets) > 1 and rng.random() < PAIR_SHARE) else 1
        combo = tuple(sorted(rng.choice(targets, size=k, replace=False).tolist()))
        key = (combo, float(rng.choice(SEVERITIES)), int(rng.choice(DURATIONS)))
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def prescreen(G: nx.DiGraph, n_scenarios: int = 2000, top_k: int = 15, seed: int = 7, horizon: int = 30) -> dict:
    """See the module docstring. Returns {candidates, agreement, timing, model, note}."""
    from scipy.stats import spearmanr

    cands = candidates(G, n_scenarios, seed)
    status = risk_ml.scenario_model_status()
    if not cands or total_demand(G) <= 0:
        return {"n_scenarios": 0, "top_k": 0, "candidates": [], "control": [], "agreement": None, "timing": None,
                "model": status, "note": "No failure targets or no demand in this network."}
    event_sets = [_events(*c) for c in cands]
    t0 = time.perf_counter()
    preds = risk_ml.predict_scenarios(G, event_sets, horizon=horizon)
    t_sur = time.perf_counter() - t0
    if preds is None:
        return {"n_scenarios": len(cands), "top_k": 0, "candidates": [], "control": [], "agreement": None, "timing": None,
                "model": risk_ml.scenario_model_status(), "note": "Surrogate unavailable; use the exact Chaos Finder scan."}
    score = np.array([p["unmet_pct"]["point"] for p in preds])
    order = np.argsort(-score, kind="stable")
    k = min(top_k, len(cands))
    top = order[:k].tolist()
    rest = order[k:]
    control = sorted(np.random.default_rng(seed + 1).choice(rest, size=min(k, len(rest)), replace=False).tolist()) if len(rest) else []
    daily = total_demand(G) * horizon

    def run(i: int) -> dict:
        t = time.perf_counter()
        res = simulate(G, event_sets[i], horizon)
        ms = (time.perf_counter() - t) * 1000
        combo, sev, dur = cands[i]
        return {"label": _label(combo, sev, dur), "targets": list(combo), "severity": sev, "duration": dur,
                "events": [e.model_dump(exclude_none=True) for e in event_sets[i]],
                "predicted_unmet_pct": preds[i]["unmet_pct"],
                "exact": {"unmet_pct": round(100 * res["total_unmet"] / daily, 3) if daily else 0.0,
                          "total_unmet": res["total_unmet"], "stockout_day": res["survival_clock_days"],
                          "avg_delay_days": res["delay"]["avg_days"], "revenue_at_risk": res["revenue_at_risk"]},
                "_ms": ms}

    top_rows = [run(i) for i in top]
    ctrl_rows = [run(i) for i in control]
    rows = top_rows + ctrl_rows
    exact_ms = float(np.mean([r["_ms"] for r in rows])) if rows else 0.0
    pred_v = [r["predicted_unmet_pct"]["point"] for r in rows]
    exact_v = [r["exact"]["unmet_pct"] for r in rows]
    rho = float(spearmanr(pred_v, exact_v).statistic) if len(rows) > 2 and np.ptp(pred_v) > 0 and np.ptp(exact_v) > 0 else 0.0
    ctrl_exact = np.array([r["exact"]["unmet_pct"] for r in ctrl_rows]) if ctrl_rows else np.array([0.0])
    bar = float(np.percentile(ctrl_exact, 90))
    in_band = [r["predicted_unmet_pct"]["low"] <= r["exact"]["unmet_pct"] <= r["predicted_unmet_pct"]["high"] for r in rows]
    t_top = sum(r["_ms"] for r in top_rows) / 1000
    for r in rows:
        r.pop("_ms")
    return {
        "n_scenarios": len(cands), "top_k": k, "candidates": top_rows, "control": ctrl_rows,
        "agreement": {
            "spearman": round(rho, 3),
            "precision_at_k": round(float(np.mean([r["exact"]["unmet_pct"] >= bar and r["exact"]["unmet_pct"] > 0 for r in top_rows])), 3),
            "top_mean_exact_unmet_pct": round(float(np.mean([r["exact"]["unmet_pct"] for r in top_rows])), 3),
            "control_mean_exact_unmet_pct": round(float(ctrl_exact.mean()), 3),
            "interval_hit_rate": round(float(np.mean(in_band)), 3) if in_band else None,
        },
        "timing": {
            "surrogate_s": round(t_sur, 3), "exact_top_s": round(t_top, 3), "exact_ms_per_scenario": round(exact_ms, 1),
            "exact_all_estimate_s": round(exact_ms * len(cands) / 1000, 1),
            "speedup": round((exact_ms * len(cands) / 1000) / max(1e-6, t_sur + t_top), 1),
        },
        "model": risk_ml.scenario_model_status(),
        "note": "Scenarios are ranked by the ML surrogate; every outcome shown is from the exact simulator (simulated).",
    }
