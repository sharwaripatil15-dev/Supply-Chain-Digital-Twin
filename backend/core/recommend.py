"""Alternate supplier and route recommendations. Owner: B.

rank_alternate_suppliers: for each disrupted supplier s, candidates are the other suppliers (including the backup)
    that are not disrupted, ship to at least one of s's factories, and have spare capacity. Each is scored on
        cost  = mean lane cost to those factories (backup lanes x1.5) vs s's own lanes, as a premium %
        lead  = fastest lane to one of those factories (days)
        spare = capacity - baseline output (the backup's whole capacity is spare)
    combined as 0.4 x cost rank + 0.3 x lead rank + 0.3 x spare rank (lower is better), with a reason string.
rank_alternate_routes: for every customer whose main baseline path (follow the largest inbound flow upstream)
    crosses a disrupted node or lane, find the cheapest path from any working supplier on the graph minus the
    disrupted elements and minus lanes/sites with no spare capacity at baseline, and report old -> new with
    delay_delta (lead days) and cost_delta (INR/unit).
"""
from __future__ import annotations

from typing import Iterable

import networkx as nx

from core.optimizer import lane_cost
from core.sim import solve_flow


def _baseline_flow(G: nx.DiGraph) -> dict:
    return solve_flow(G)


def rank_alternate_suppliers(G: nx.DiGraph, down_suppliers: Iterable[str], top: int = 3) -> list[dict]:
    """Return [{replaces, supplier, name, city, spare_capacity, lead, cost_premium_pct, reliability, reason}]."""
    down = set(down_suppliers)
    base = _baseline_flow(G)
    out = []
    for s in sorted(down):
        factories = set(G.successors(s))
        own_cost = sum(lane_cost(G, s, f) for f in factories) / len(factories) if factories else 0.0
        cands = []
        for c, d in G.nodes(data=True):
            if d["kind"] != "supplier" or c in down:
                continue
            shared = sorted(factories & set(G.successors(c)))
            if not shared:
                continue
            cost = sum(lane_cost(G, c, f) for f in shared) / len(shared)
            spare = d["capacity"] if d.get("backup") else max(0.0, d["capacity"] - base["throughput"].get(c, 0.0))
            if spare < 1:
                continue  # already running flat out: not an alternative
            cands.append({
                "replaces": s, "supplier": c, "name": d.get("name", c), "city": d["city"],
                "spare_capacity": round(spare),
                "lead": min(G.edges[c, f]["lead"] for f in shared),
                "cost_premium_pct": round(100 * (cost - own_cost) / own_cost, 1) if own_cost else 0.0,
                "reliability": d.get("reliability", 1.0),
                "_shared": shared, "_backup": bool(d.get("backup")),
            })
        if not cands:
            continue
        rank = lambda key, reverse=False: {id(x): i for i, x in enumerate(sorted(cands, key=lambda x: x[key], reverse=reverse))}  # noqa: E731
        r_cost, r_lead, r_spare = rank("cost_premium_pct"), rank("lead"), rank("spare_capacity", reverse=True)
        for x in cands:
            x["_score"] = 0.4 * r_cost[id(x)] + 0.3 * r_lead[id(x)] + 0.3 * r_spare[id(x)]
        for x in sorted(cands, key=lambda x: x["_score"])[:top]:
            premium = x["cost_premium_pct"]
            x["reason"] = (
                f"Ships to {', '.join(x['_shared'])} like {s}; {x['spare_capacity']:,} units/day spare; "
                f"{x['lead']:.0f}-day lead; lanes {'+' if premium >= 0 else ''}{premium:.0f}% vs {s}"
                + ("; backup contract (activation fee, opens after the lag)" if x["_backup"] else "")
            )
            out.append({k: v for k, v in x.items() if not k.startswith("_")})
    return out


def _main_path(G: nx.DiGraph, flow: dict, customer: str) -> list[str]:
    """Follow the largest inbound baseline flow upstream from a customer to a supplier."""
    path = [customer]
    node = customer
    while G.nodes[node]["kind"] != "supplier":
        preds = list(G.predecessors(node))
        if not preds:
            break
        node = max(preds, key=lambda p: flow.get((p, node), 0.0))
        path.append(node)
    return path[::-1]


def _path_lead(G: nx.DiGraph, path: list[str]) -> float:
    return sum(G.edges[a, b]["lead"] for a, b in zip(path, path[1:]))


def _path_cost(G: nx.DiGraph, path: list[str]) -> float:
    return sum(lane_cost(G, a, b) for a, b in zip(path, path[1:]))


def rank_alternate_routes(
    G: nx.DiGraph,
    down_nodes: Iterable[str],
    down_edges: Iterable[tuple[str, str]],
    k: int = 5,
) -> list[dict]:
    """Return [{origin, destination, via, old_via, replaces, spare_capacity, extra_lead_days, extra_cost_per_unit}].

    extra_lead_days is the delay_delta and extra_cost_per_unit the cost_delta of new vs old path.
    """
    down_nodes, down_edges = set(down_nodes), {tuple(e) for e in down_edges}
    base = _baseline_flow(G)
    H = G.copy()
    H.remove_nodes_from(down_nodes)
    H.remove_edges_from(down_edges)
    # only route through lanes and sites with spare capacity (saturated ones cannot take rerouted volume)
    H.remove_edges_from([(u, v) for u, v, d in G.edges(data=True) if d["capacity"] - base["flow"].get((u, v), 0.0) < 1])
    H.remove_nodes_from([n for n, d in G.nodes(data=True) if d["kind"] != "customer" and not d.get("backup")
                         and d["capacity"] - base["throughput"].get(n, 0.0) < 1])
    for u, v in H.edges:
        H.edges[u, v]["w"] = lane_cost(G, u, v)
    src = "__SRC__"
    H.add_node(src, kind="source")
    for n, d in G.nodes(data=True):
        if d["kind"] == "supplier" and n in H:
            H.add_edge(src, n, w=0.0)

    routes = []
    for c, d in G.nodes(data=True):
        if d["kind"] != "customer":
            continue
        old = _main_path(G, base["flow"], c)
        hit = [n for n in old if n in down_nodes] + [f"{a}->{b}" for a, b in zip(old, old[1:]) if (a, b) in down_edges]
        if not hit or c not in H or not nx.has_path(H, src, c):
            continue
        new = nx.shortest_path(H, src, c, weight="w")[1:]
        spare = min(
            [G.edges[a, b]["capacity"] - base["flow"].get((a, b), 0.0) for a, b in zip(new, new[1:])]
            + [G.nodes[n]["capacity"] - base["throughput"].get(n, 0.0) for n in new if G.nodes[n]["kind"] != "customer"
               and not G.nodes[n].get("backup")]
        )
        routes.append({
            "origin": new[0], "destination": c, "via": new, "old_via": old, "replaces": hit[0],
            "spare_capacity": round(max(0.0, spare)),
            "extra_lead_days": round(_path_lead(G, new) - _path_lead(G, old), 1),
            "extra_cost_per_unit": round(_path_cost(G, new) - _path_cost(G, old), 1),
        })
    return sorted(routes, key=lambda r: (r["extra_lead_days"], r["extra_cost_per_unit"]))[:k]


# Names used by routers/recover.py
alternate_suppliers = rank_alternate_suppliers
alternate_routes = rank_alternate_routes
