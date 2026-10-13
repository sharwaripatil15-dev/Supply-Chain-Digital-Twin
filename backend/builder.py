"""Manual network builder: pure conversion and validation helpers (no state; see network_store.py). Owner: D.

Builder records (schemas.BuilderNode / BuilderEdge as plain dicts) map onto the engine's existing graph attributes,
so no engine module needs builder-specific logic:
    capacity     = production_capacity for a factory when it is given, else capacity (units/day)
    stock        = stock, plus shelf_stock for a retailer
    demand       = daily_demand for retailers and customers, else 0
    backup       = is_backup (suppliers)
    name, city, lat, lon, reliability as entered; every other field goes into `details` for the UI.
Lanes: capacity, lead, cost, co2 (+ id, mode, distance_km). Empty distance/lead/cost/co2 are suggested from the
endpoints' coordinates and the transport mode (node_types.suggest_*).
Inactive nodes, and lanes that are inactive or touch an inactive node, are left out of the engine graph.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Iterable

import networkx as nx

from node_types import (
    ALL_TYPE_FIELDS, ID_PREFIX, KINDS, TIER, edge_allowed, haversine_km, is_demand, suggest_co2, suggest_cost,
    suggest_lead,
)

UNIT_PRICE_INR = 4200  # same list price as the preset (core.graph.UNIT_PRICE_INR)
DETAIL_KEYS = ("op_cost", "status", *[f for f in ALL_TYPE_FIELDS if f != "is_backup"])
CSV_NODE_COLUMNS = ["id", "name", "kind", "city", "lat", "lon", "capacity", "stock", "demand", "reliability", "backup"]
CSV_EDGE_COLUMNS = ["source", "target", "capacity", "lead", "cost", "co2"]


def issue(code: str, message: str, refs: Iterable[str] = ()) -> dict:
    return {"code": code, "message": message, "refs": [str(r) for r in refs]}


def next_id(prefix: str, taken: Iterable[str]) -> str:
    """Smallest unused `prefix<n>` above every existing one (S1, S2, ...)."""
    nums = [int(m.group(1)) for t in taken if (m := re.fullmatch(rf"{re.escape(prefix)}(\d+)", str(t)))]
    return f"{prefix}{max(nums, default=0) + 1}"


def node_id_for(kind: str, taken: Iterable[str]) -> str:
    return next_id(ID_PREFIX.get(kind, "N"), taken)


def resolve_edge(edge: dict, nodes: dict[str, dict]) -> dict:
    """Fill empty distance_km / lead / cost / co2 from the endpoints and mode. Unknown endpoints are left as is."""
    out = dict(edge)
    src, dst = nodes.get(out["source"]), nodes.get(out["target"])
    mode = out.get("mode") or "road"
    out["mode"] = mode
    if src and dst and out.get("distance_km") is None:
        out["distance_km"] = round(haversine_km((src["lat"], src["lon"]), (dst["lat"], dst["lon"])), 1)
    km = out.get("distance_km") or 0.0
    if out.get("lead") is None:
        out["lead"] = suggest_lead(mode, km)
    if out.get("cost") is None:
        out["cost"] = suggest_cost(mode, km)
    if out.get("co2") is None:
        out["co2"] = suggest_co2(mode, km)
    return out


def engine_node_attrs(n: dict) -> dict:
    """Builder node -> engine graph attributes (see module docstring)."""
    kind = n["kind"]
    capacity = n.get("capacity") or 0.0
    if kind == "factory" and n.get("production_capacity"):
        capacity = n["production_capacity"]
    stock = (n.get("stock") or 0.0) + ((n.get("shelf_stock") or 0.0) if kind == "retailer" else 0.0)
    return {
        "kind": kind,
        "name": n.get("name") or n["id"],
        "city": n.get("city") or "",
        "lat": float(n["lat"]),
        "lon": float(n["lon"]),
        "capacity": float(capacity),
        "stock": float(stock),
        "demand": float(n.get("daily_demand") or 0.0) if is_demand(kind) else 0.0,
        "reliability": float(n.get("reliability", 0.95)),
        "backup": bool(n.get("is_backup")) and kind == "supplier",
        "details": {k: n[k] for k in DETAIL_KEYS if n.get(k) not in (None, "")},
    }


def build_graph(nodes: dict[str, dict], edges: dict[str, dict], seed: int = 7) -> nx.DiGraph:
    """Engine graph from builder records: active nodes, and active lanes between active nodes."""
    G = nx.DiGraph(seed=seed, unit_price=UNIT_PRICE_INR, source="manual")
    for nid, n in nodes.items():
        if n.get("status", "active") == "active":
            G.add_node(nid, **engine_node_attrs(n))
    for eid, e in edges.items():
        if e.get("status", "active") != "active" or e["source"] not in G or e["target"] not in G:
            continue
        r = resolve_edge(e, nodes)
        G.add_edge(e["source"], e["target"], id=eid, capacity=float(r["capacity"]), lead=float(r["lead"]),
                   cost=float(r["cost"]), co2=float(r["co2"]), mode=r["mode"], distance_km=r.get("distance_km"))
    return G


# ---------------------------------------------------------------- validation
def integrity_errors(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Structural problems that make a node/edge list unusable: duplicate ids, unknown endpoints, self-loops,
    duplicate lanes. (Field-level problems are caught earlier by the Pydantic models.)"""
    errors = []
    seen: set[str] = set()
    for n in nodes:
        if n.get("id") in seen:
            errors.append(issue("duplicate_id", f"Node id {n['id']} is used more than once.", [n["id"]]))
        seen.add(n.get("id"))
    pairs: dict[tuple[str, str], str] = {}
    edge_ids: set[str] = set()
    for e in edges:
        eid = e.get("id") or f"{e['source']}->{e['target']}"
        if e.get("id") and e["id"] in edge_ids:
            errors.append(issue("duplicate_edge_id", f"Lane id {e['id']} is used more than once.", [e["id"]]))
        edge_ids.add(e.get("id"))
        missing = [x for x in (e["source"], e["target"]) if x not in seen]
        if missing:
            errors.append(issue("missing_node", f"Lane {eid} references missing node(s): {', '.join(missing)}.", [eid, *missing]))
        if e["source"] == e["target"]:
            errors.append(issue("self_loop", f"Lane {eid} starts and ends at {e['source']}.", [eid]))
        pair = (e["source"], e["target"])
        if pair in pairs:
            errors.append(issue("duplicate_edge", f"Lanes {pairs[pair]} and {eid} both connect {pair[0]} -> {pair[1]}.", [pairs[pair], eid]))
        pairs.setdefault(pair, eid)
    return errors


def validate(nodes: list[dict], edges: list[dict]) -> dict:
    """{errors, warnings, runnable}. Errors block Apply and the engine; warnings do not."""
    errors = integrity_errors(nodes, edges)
    warnings: list[dict] = []
    by_id = {n["id"]: n for n in nodes if n.get("id")}
    active = {i: n for i, n in by_id.items() if n.get("status", "active") == "active"}
    suppliers = [i for i, n in active.items() if n["kind"] == "supplier"]
    demand = [i for i, n in active.items() if is_demand(n["kind"])]
    if not suppliers:
        errors.append(issue("no_supplier", "Add at least one active supplier."))
    if not demand:
        errors.append(issue("no_demand", "Add at least one active retailer or customer (a demand node)."))

    live: list[dict] = []
    for e in edges:
        eid = e.get("id") or f"{e['source']}->{e['target']}"
        if e["source"] not in by_id or e["target"] not in by_id:
            continue  # already an error
        off = [x for x in (e["source"], e["target"]) if x not in active]
        if e.get("status", "active") != "active":
            continue
        if off:
            warnings.append(issue("inactive_endpoint", f"Lane {eid} is ignored: {', '.join(off)} is inactive.", [eid, *off]))
            continue
        live.append(e)
        sk, tk = by_id[e["source"]]["kind"], by_id[e["target"]]["kind"]
        if not edge_allowed(sk, tk):
            warnings.append(issue("illegal_direction", f"Lane {eid} runs {sk} -> {tk}, which is not an allowed tier direction.", [eid]))

    linked = {x for e in live for x in (e["source"], e["target"])}
    isolated = [i for i in active if i not in linked]
    for i in isolated:
        warnings.append(issue("isolated", f"{i} ({active[i].get('name', i)}) has no lanes.", [i]))

    G = nx.DiGraph()
    G.add_nodes_from(active)
    G.add_edges_from((e["source"], e["target"]) for e in live)
    reach = set(suppliers).union(*(nx.descendants(G, s) for s in suppliers)) if suppliers else set()
    for i in demand:
        if i not in reach and i not in isolated:
            warnings.append(issue("unreachable", f"{i} ({active[i].get('name', i)}) cannot be reached from any supplier.", [i]))

    supply = sum(engine_node_attrs({"id": i, **active[i]})["capacity"] for i in suppliers if not active[i].get("is_backup"))
    total_demand = sum(active[i].get("daily_demand") or 0.0 for i in demand)
    if demand and total_demand <= 0:
        warnings.append(issue("zero_demand", "Every demand node has zero daily demand, so there is nothing to simulate.", demand))
    elif suppliers and supply < total_demand:
        warnings.append(issue("supply_shortfall", f"Primary supplier capacity ({supply:,.0f}/day) is below total demand "
                                                  f"({total_demand:,.0f}/day), so some demand goes unmet even on a normal day.", suppliers))
    if suppliers and not any(active[i].get("is_backup") for i in suppliers):
        warnings.append(issue("no_backup", "No backup supplier: recovery plans cannot trigger one.", suppliers))
    for i, n in active.items():
        if n["kind"] == "warehouse" and n.get("storage_capacity") is not None and (n.get("stock") or 0) > n["storage_capacity"]:
            warnings.append(issue("over_storage", f"{i} holds {n['stock']:,.0f} units but can store only {n['storage_capacity']:,.0f}.", [i]))
    return {"errors": errors, "warnings": warnings, "runnable": not errors}


def graph_errors(G: nx.DiGraph | None) -> list[dict]:
    """Blocking problems for any engine graph (used for CSV networks, which have no builder records)."""
    if G is None:
        return []
    if G.number_of_nodes() == 0:
        return [issue("empty", "The network is empty.")]
    errors = []
    if not any(d.get("kind") == "supplier" for _, d in G.nodes(data=True)):
        errors.append(issue("no_supplier", "Add at least one active supplier."))
    if not any(is_demand(d.get("kind")) for _, d in G.nodes(data=True)):
        errors.append(issue("no_demand", "Add at least one active retailer or customer (a demand node)."))
    return errors


# ---------------------------------------------------------------- conversions
def graph_to_builder(G: nx.DiGraph) -> tuple[list[dict], list[dict]]:
    """Engine graph (preset or CSV) -> builder records, e.g. to start a manual network from the preset."""
    nodes = []
    for nid, d in sorted(G.nodes(data=True), key=lambda kv: (TIER.get(kv[1].get("kind"), 99), str(kv[0]))):
        kind = d.get("kind")
        if kind not in KINDS:
            continue
        rec = {
            "id": str(nid), "name": str(d.get("name") or nid), "kind": kind, "city": str(d.get("city") or ""),
            "lat": float(d.get("lat", 0.0)), "lon": float(d.get("lon", 0.0)),
            "capacity": float(d.get("capacity") or 0.0), "stock": float(d.get("stock") or 0.0),
            "reliability": float(min(1.0, max(0.0, d.get("reliability", 0.95)))), "op_cost": 0.0, "status": "active",
        }
        if kind == "supplier":
            rec["is_backup"] = bool(d.get("backup"))
        if is_demand(kind):
            rec["daily_demand"] = float(d.get("demand") or 0.0)
        nodes.append(rec)
    edges = []
    for i, (u, v, d) in enumerate(G.edges(data=True), start=1):
        a, b = G.nodes[u], G.nodes[v]
        km = round(haversine_km((a.get("lat", 0.0), a.get("lon", 0.0)), (b.get("lat", 0.0), b.get("lon", 0.0))), 1)
        edges.append({
            "id": f"E{i}", "source": str(u), "target": str(v), "mode": d.get("mode") or "road",
            "distance_km": d.get("distance_km") if d.get("distance_km") is not None else km,
            "lead": float(d.get("lead", 1.0)), "capacity": float(d.get("capacity") or 0.0),
            "cost": float(d.get("cost") or 0.0), "co2": float(d.get("co2") or 0.0), "status": "active",
        })
    return nodes, edges


def graph_to_dict(G: nx.DiGraph) -> dict:
    """JSON-safe dump of an engine graph (CSV networks are persisted this way)."""
    return {
        "graph": {k: v for k, v in G.graph.items() if isinstance(v, (str, int, float, bool))},
        "nodes": [{"id": n, **d} for n, d in G.nodes(data=True)],
        "edges": [{"source": u, "target": v, **d} for u, v, d in G.edges(data=True)],
    }


def graph_from_dict(data: dict) -> nx.DiGraph:
    G = nx.DiGraph(**(data.get("graph") or {}))
    for n in data.get("nodes") or []:
        G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
    for e in data.get("edges") or []:
        G.add_edge(e["source"], e["target"], **{k: v for k, v in e.items() if k not in ("source", "target")})
    return G


def to_csv(G: nx.DiGraph) -> tuple[str, str]:
    """(nodes.csv, edges.csv) in the format POST /upload accepts."""
    nbuf, ebuf = io.StringIO(), io.StringIO()
    nw = csv.DictWriter(nbuf, CSV_NODE_COLUMNS, lineterminator="\n")
    nw.writeheader()
    for nid, d in G.nodes(data=True):
        nw.writerow({"id": nid, "name": d.get("name") or nid, "kind": d["kind"], "city": d.get("city") or "",
                     "lat": d["lat"], "lon": d["lon"], "capacity": d.get("capacity", 0.0), "stock": d.get("stock", 0.0),
                     "demand": d.get("demand", 0.0), "reliability": d.get("reliability", 0.95), "backup": bool(d.get("backup"))})
    ew = csv.DictWriter(ebuf, CSV_EDGE_COLUMNS, lineterminator="\n")
    ew.writeheader()
    for u, v, d in G.edges(data=True):
        ew.writerow({"source": u, "target": v, "capacity": d["capacity"], "lead": d["lead"], "cost": d["cost"], "co2": d.get("co2", 0.0)})
    return nbuf.getvalue(), ebuf.getvalue()
