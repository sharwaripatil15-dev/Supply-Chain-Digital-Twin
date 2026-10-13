"""Chaos Finder: reverse stress-test for single and paired points of failure. Owner: B.

Metric: for a set of failed targets, the steady-state unmet share of total daily demand from one min-cost flow
solve (core.sim.solve_flow) with the failed nodes/lanes at capacity 0 and the backup supplier available (i.e.
after it has been activated). Stock buffers are ignored on purpose: Chaos Finder ranks structural weakness, not how
long stock can hide it.

Algorithm:
    1. Targets = every supplier/factory/warehouse and every lane, excluding the backup supplier and its lanes
       (it is the remedy, not a risk) and demand nodes, i.e. retailers and customers (losing one is lost demand,
       not a supply failure). Lanes into and out of demand nodes are still targets.
    2. Singles: unmet(t) for every target. Top-k by unmet = single points of failure (SPOF).
    3. Pairs: all pairs of targets, or only pairs among the top PRUNE_TO singles when there are more than
       PRUNE_ABOVE targets. synergy(a, b) = unmet(a + b) - unmet(a) - unmet(b). A pair is "hidden" when
       synergy > HIDDEN_SYNERGY: together the two fail far worse than their separate failures add up to.
    4. Resilience score = 100 x (1 - mean unmet of the worst RESILIENCE_K pairs).
Results are cached per graph fingerprint, so /chaos, /network and repeated calls do one scan.
API values are converted to units: unmet share x total daily demand x `duration` days of outage. chaos_find reports
the loss a failure *adds* to the baseline (a hand-built network may already miss demand on a normal day); for a
network that serves all demand at baseline (the preset) that is the same number.
"""
from __future__ import annotations

import hashlib
import json
from itertools import combinations

import networkx as nx

from core.sim import solve_flow, unmet_frac
from node_types import is_demand, total_demand

PRUNE_ABOVE = 60
PRUNE_TO = 20
HIDDEN_SYNERGY = 0.03
RESILIENCE_K = 5

_SCAN_CACHE: dict[str, dict] = {}


def _fingerprint(G: nx.DiGraph) -> str:
    payload = [sorted((n, sorted(d.items())) for n, d in G.nodes(data=True) if True),
               sorted((u, v, sorted(d.items())) for u, v, d in G.edges(data=True))]
    return hashlib.sha1(json.dumps(payload, default=str).encode()).hexdigest()


def edge_target(u: str, v: str) -> str:
    return f"{u}->{v}"


def targets(G: nx.DiGraph) -> list[str]:
    """Failure candidates: non-backup supply-side nodes (not retailers/customers), and lanes not leaving the backup."""
    nodes = [n for n, d in G.nodes(data=True) if not is_demand(d["kind"]) and not d.get("backup")]
    edges = [edge_target(u, v) for u, v in G.edges if not G.nodes[u].get("backup")]
    return nodes + edges


def failure_unmet(G: nx.DiGraph, failed: tuple[str, ...] | list[str]) -> float:
    """Unmet share of total daily demand with `failed` (node ids and/or "U->V" lanes) out of action."""
    down_nodes = [t for t in failed if "->" not in t]
    down_edges = [tuple(t.split("->")) for t in failed if "->" in t]
    return unmet_frac(G, solve_flow(G, down_nodes=down_nodes, down_edges=down_edges, allow_backup=True))


def scan(G: nx.DiGraph) -> dict:
    """Run (or fetch from cache) the full single + pair scan. Returns {singles, pairs, n_targets, pruned}."""
    key = _fingerprint(G)
    if key in _SCAN_CACHE:
        return _SCAN_CACHE[key]
    all_targets = targets(G)
    singles = {t: failure_unmet(G, (t,)) for t in all_targets}
    pruned = len(all_targets) > PRUNE_ABOVE
    candidates = sorted(all_targets, key=lambda t: -singles[t])[:PRUNE_TO] if pruned else all_targets
    pairs = {}
    for a, b in combinations(candidates, 2):
        both = failure_unmet(G, (a, b))
        pairs[(a, b)] = {"unmet": both, "synergy": both - singles[a] - singles[b]}
    result = {"singles": singles, "pairs": pairs, "n_targets": len(all_targets), "pruned": pruned}
    _SCAN_CACHE[key] = result
    return result


def chaos_find(G: nx.DiGraph, top: int = 5, duration: int = 10) -> dict:
    """Returns {spof:[{target, unmet}], hidden_pairs:[{pair:[a,b], unmet, synergy}], resilience_score}.

    unmet / synergy are in units over a `duration`-day outage; hidden pairs are those with synergy share > 0.03.
    """
    res = scan(G)
    daily = total_demand(G)
    units = lambda share: round(share * daily * duration, 1)  # noqa: E731
    base = baseline_unmet(G)
    singles = {t: max(0.0, s - base) for t, s in res["singles"].items()}
    pairs = {}
    for (a, b), v in res["pairs"].items():
        both = max(0.0, v["unmet"] - base)
        pairs[(a, b)] = {"unmet": both, "synergy": both - singles[a] - singles[b]}
    spof = sorted(singles.items(), key=lambda kv: -kv[1])
    hidden = sorted(((p, v) for p, v in pairs.items() if v["synergy"] > HIDDEN_SYNERGY), key=lambda kv: -kv[1]["synergy"])
    return {
        "spof": [{"target": t, "unmet": units(s)} for t, s in spof[:top] if s > 0],
        "hidden_pairs": [{"pair": list(p), "unmet": units(v["unmet"]), "synergy": units(v["synergy"])} for p, v in hidden[:top]],
        "resilience_score": resilience_score(G),
    }


def baseline_unmet(G: nx.DiGraph) -> float:
    """Unmet share with nothing failed (backup available); 0 for any network that can serve all of its demand."""
    return failure_unmet(G, ())


def failure_loss(G: nx.DiGraph, failed: tuple[str, ...] | list[str]) -> float:
    """Share of demand a failure loses on top of the baseline."""
    return max(0.0, failure_unmet(G, failed) - baseline_unmet(G))


def resilience_score(G: nx.DiGraph, k: int = RESILIENCE_K) -> float:
    """0..100: 100 x (1 - mean unmet share of the worst `k` failure pairs)."""
    worst = sorted((v["unmet"] for v in scan(G)["pairs"].values()), reverse=True)[:k]
    if not worst:
        return 100.0
    return round(100 * (1 - sum(worst) / len(worst)), 1)
