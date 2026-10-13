"""Network construction. Owner: A.

Graph conventions used by every core module:
    node attrs: kind, city, lat, lon, capacity (units/day), stock (units), demand (units/day, customers only),
                reliability (0..1), name, backup (bool); risk/top_factors are added by the risk layer
    edge attrs: capacity (units/day), lead (days), cost (INR/unit), co2 (kg/unit)
    graph attrs: seed, unit_price (INR per finished unit, used for revenue at risk)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import networkx as nx
import numpy as np

DEMO_NETWORK = Path(__file__).resolve().parent.parent / "mock" / "demo_network.json"
UNIT_PRICE_INR = 4200
PRIMARY_SUPPLY_HEADROOM = 1.15  # total primary supplier capacity / total customer demand
SUPPLIER_PRIORITY = ["S2", "S1", "S3", "S5"]  # largest share first: S2 makes the key electronic components
BACKUP_SHARE = 0.25  # backup supplier capacity / total customer demand

# Fixed sites per tier (real Indian cities). Ids line up with the mock layer and the UI demo scenarios.
#            id     name                         city         lat     lon    backup
SITES = {
    "supplier": [
        ("S1", "Pune Steel Coils", "Pune", 18.52, 73.86, False),
        ("S2", "Chennai Electronics", "Chennai", 13.08, 80.27, False),
        ("S3", "Gujarat Polymers", "Ahmedabad", 23.02, 72.57, False),
        ("S4", "Kolkata Backup Components", "Kolkata", 22.57, 88.36, True),
        ("S5", "Jamshedpur Castings", "Jamshedpur", 22.80, 86.18, False),
    ],
    "factory": [
        ("F1", "Bengaluru Assembly", "Bengaluru", 12.97, 77.59, False),
        ("F2", "Hyderabad Plant", "Hyderabad", 17.39, 78.49, False),
        ("F3", "Nashik Works", "Nashik", 19.99, 73.79, False),
    ],
    "warehouse": [
        ("W1", "Bhiwandi DC", "Mumbai", 19.30, 73.06, False),
        ("W2", "Gurugram DC", "Delhi", 28.46, 77.03, False),
        ("W3", "Sriperumbudur DC", "Chennai", 12.97, 79.95, False),
        ("W4", "Nagpur Hub", "Nagpur", 21.15, 79.09, False),
    ],
    "customer": [
        ("C1", "Mumbai Retail", "Mumbai", 19.08, 72.88, False),
        ("C2", "Delhi Retail", "Delhi", 28.70, 77.10, False),
        ("C3", "Bengaluru Retail", "Bengaluru", 12.93, 77.62, False),
        ("C4", "Hyderabad Retail", "Hyderabad", 17.44, 78.38, False),
    ],
}
TIERS = ["supplier", "factory", "warehouse", "customer"]


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _nearest(G: nx.DiGraph, node: str, candidates: list[str], k: int) -> list[str]:
    pos = (G.nodes[node]["lat"], G.nodes[node]["lon"])
    return sorted(candidates, key=lambda c: haversine_km(pos, (G.nodes[c]["lat"], G.nodes[c]["lon"])))[:k]


def build_network(seed: int = 7, path: Path | None = None) -> nx.DiGraph:
    """Generate the 4-tier network (5 suppliers incl. 1 backup, 3 factories, 4 warehouses, 4 customers).

    Topology is geographic and deterministic: every downstream node is fed by its 2 nearest upstream nodes,
    and every upstream node ships to at least its nearest downstream node, so there are no orphans. The backup
    supplier connects to its 2 nearest factories. Quantities are random but seeded:
        customer demand U(150, 300)/day, customer stock 1.5-3 days of demand;
        primary supplier capacity = Dirichlet split of 1.15x total demand (concentrated, like real supply bases;
        the largest share goes to S2, then S1, S3, S5),
        backup supplier 0.25x demand; factory / warehouse capacity 0.48-0.65x / 0.38-0.52x demand each;
        non-customer stock 1-3 days of capacity (informational);
        reliability U(0.82, 0.98); edge lead = distance/450 km/day + jitter, clipped to 1..5 days;
        cost and CO2 proportional to distance; edge capacity a random share of its endpoints' capacity.
    Edge capacities are then scaled until the baseline (no disruption, no backup) serves 100% of demand.

    If `path` is given, load a network from JSON instead (the mock demo format).
    """
    if path is not None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        G = nx.DiGraph(seed=seed, unit_price=UNIT_PRICE_INR)
        for n in data["nodes"]:
            G.add_node(n["id"], **{k: v for k, v in n.items() if k != "id"})
        for e in data["edges"]:
            G.add_edge(e["source"], e["target"], **{k: v for k, v in e.items() if k not in ("source", "target")})
        return G

    rng = np.random.default_rng(seed)
    G = nx.DiGraph(seed=seed, unit_price=UNIT_PRICE_INR)
    for kind in TIERS:
        for nid, name, city, lat, lon, backup in SITES[kind]:
            G.add_node(nid, kind=kind, name=name, city=city, lat=lat, lon=lon, backup=backup)

    by_kind = {k: [n for n, d in G.nodes(data=True) if d["kind"] == k] for k in TIERS}
    customers = by_kind["customer"]
    for c in customers:
        G.nodes[c]["demand"] = float(rng.integers(150, 301))
    total_demand = sum(G.nodes[c]["demand"] for c in customers)

    # Supply is concentrated, as in real networks: a seeded Dirichlet split of PRIMARY_SUPPLY_HEADROOM x demand
    # across primary suppliers in SUPPLIER_PRIORITY order (so losing the biggest one hurts); the backup holds BACKUP_SHARE x demand.
    # Factories and warehouses get independent shares with ~1.5-1.8x aggregate headroom.
    primaries = [s for s in SUPPLIER_PRIORITY if s in G and not G.nodes[s]["backup"]]
    split = sorted(rng.dirichlet([2.0] * len(primaries)), reverse=True)  # sizes random, ranking fixed
    caps = {s: total_demand * PRIMARY_SUPPLY_HEADROOM * w for s, w in zip(primaries, split)}
    caps.update({s: total_demand * BACKUP_SHARE for s in by_kind["supplier"] if G.nodes[s]["backup"]})
    share = {"factory": (0.48, 0.65), "warehouse": (0.38, 0.52)}
    for kind, (lo, hi) in share.items():
        caps.update({n: total_demand * rng.uniform(lo, hi) for n in by_kind[kind]})
    for n, cap in caps.items():
        G.nodes[n]["capacity"] = float(round(cap))
        G.nodes[n]["stock"] = float(round(cap * rng.uniform(1, 3)))
        G.nodes[n]["demand"] = 0.0
    for c in customers:
        G.nodes[c]["capacity"] = 0.0
        G.nodes[c]["stock"] = float(round(G.nodes[c]["demand"] * rng.uniform(1.5, 3)))
    for n in G:
        G.nodes[n]["reliability"] = round(float(rng.uniform(0.82, 0.98)), 3)

    # Geographic topology.
    pairs: set[tuple[str, str]] = set()
    for up_kind, down_kind, ups in (
        ("supplier", "factory", primaries),
        ("factory", "warehouse", by_kind["factory"]),
        ("warehouse", "customer", by_kind["warehouse"]),
    ):
        for d in by_kind[down_kind]:
            pairs.update((u, d) for u in _nearest(G, d, ups, 2))
        for u in ups:
            pairs.update((u, d) for d in _nearest(G, u, by_kind[down_kind], 2 if up_kind == "factory" else 1))
    for s in by_kind["supplier"]:
        if G.nodes[s]["backup"]:
            pairs.update((s, f) for f in _nearest(G, s, by_kind["factory"], 2))

    for u, v in sorted(pairs):
        km = haversine_km((G.nodes[u]["lat"], G.nodes[u]["lon"]), (G.nodes[v]["lat"], G.nodes[v]["lon"]))
        lead = int(np.clip(round(km / 450 + rng.uniform(0.5, 1.5)), 1, 5))
        up_cap = G.nodes[u]["capacity"]
        down_cap = G.nodes[v]["capacity"] or G.nodes[v]["demand"]
        G.add_edge(
            u, v,
            capacity=float(round(min(up_cap, down_cap) * rng.uniform(0.55, 0.85))),
            lead=float(lead),
            cost=round(5 + km * rng.uniform(0.03, 0.05), 1),
            co2=round(km * 0.0026 * rng.uniform(0.9, 1.1), 2),
        )

    _ensure_baseline_feasible(G)
    _check_no_orphans(G)
    return G


def _ensure_baseline_feasible(G: nx.DiGraph, max_rounds: int = 25) -> None:
    """Scale lane capacities (never node capacities) until the undisrupted network meets all demand."""
    from core.sim import solve_flow  # local import: sim depends on graph conventions, not the reverse

    for _ in range(max_rounds):
        if sum(solve_flow(G)["unmet"].values()) == 0:
            return
        for _, _, d in G.edges(data=True):
            d["capacity"] = float(round(d["capacity"] * 1.15))
    raise RuntimeError("generated network cannot meet baseline demand; check capacity shares")


def _check_no_orphans(G: nx.DiGraph) -> None:
    orphans = [n for n in G if G.degree(n) == 0]
    suppliers = [n for n, d in G.nodes(data=True) if d["kind"] == "supplier" and not d.get("backup")]
    reach = set().union(*(nx.descendants(G, s) for s in suppliers))
    unserved = [n for n, d in G.nodes(data=True) if d["kind"] == "customer" and n not in reach]
    if orphans or unserved:
        raise RuntimeError(f"orphan nodes {orphans}, customers unreachable from primary suppliers {unserved}")


def load_network_from_csv(nodes_path: str | Path, edges_path: str | Path) -> tuple[nx.DiGraph, list[str]]:
    """Load nodes.csv + edges.csv (same columns as POST /upload). Returns (graph, warnings).

    Raises GraphDataError for invalid files. See `graph_from_tables` for the validation rules.
    """
    import pandas as pd

    G, warnings = graph_from_tables(pd.read_csv(nodes_path, encoding="utf-8-sig"), pd.read_csv(edges_path, encoding="utf-8-sig"))
    G.graph.setdefault("unit_price", UNIT_PRICE_INR)
    return G, warnings


NODE_REQUIRED = ["id", "kind", "city", "lat", "lon", "capacity", "stock", "demand"]
EDGE_REQUIRED = ["source", "target", "capacity", "lead", "cost"]
KINDS = ["supplier", "factory", "warehouse", "customer"]


class GraphDataError(ValueError):
    """Uploaded tables cannot form a valid network."""


def graph_from_tables(nodes, edges) -> tuple[nx.DiGraph, list[str]]:
    """Build a DiGraph from node/edge DataFrames (e.g. uploaded CSVs). Implemented.

    Raises GraphDataError for hard errors (missing columns, bad kinds, duplicate ids, edges to unknown nodes,
    non-numeric values). Returns soft problems as warnings (backwards-tier edges, isolated nodes,
    customers with no supplier path, missing optional columns).
    """
    import pandas as pd

    errors: list[str] = []
    warnings: list[str] = []
    nodes = nodes.rename(columns=lambda c: str(c).strip().lower())
    edges = edges.rename(columns=lambda c: str(c).strip().lower())

    for name, df, req in (("nodes", nodes, NODE_REQUIRED), ("edges", edges, EDGE_REQUIRED)):
        missing = [c for c in req if c not in df.columns]
        if missing:
            errors.append(f"{name}.csv missing columns: {', '.join(missing)}")
    if errors:
        raise GraphDataError("; ".join(errors))
    if nodes.empty or edges.empty:
        raise GraphDataError("nodes.csv and edges.csv must each have at least one row")

    nodes["id"] = nodes["id"].astype(str).str.strip()
    nodes["kind"] = nodes["kind"].astype(str).str.strip().str.lower()
    edges["source"] = edges["source"].astype(str).str.strip()
    edges["target"] = edges["target"].astype(str).str.strip()

    dupes = sorted(nodes.loc[nodes["id"].duplicated(), "id"].unique())
    if dupes:
        errors.append(f"duplicate node ids: {', '.join(dupes)}")
    bad_kinds = sorted(set(nodes["kind"]) - set(KINDS))
    if bad_kinds:
        errors.append(f"unknown kinds {bad_kinds}; expected one of {KINDS}")

    def numeric(df, cols, label):
        for c in cols:
            if c not in df.columns:
                continue
            converted = pd.to_numeric(df[c], errors="coerce")
            bad = df.loc[converted.isna(), c]
            if len(bad):
                errors.append(f"{label}.{c} has non-numeric values (rows {', '.join(str(i + 2) for i in bad.index[:5])})")
            elif (converted < 0).any() and c not in ("lat", "lon"):
                errors.append(f"{label}.{c} has negative values")
            df[c] = converted

    numeric(nodes, ["lat", "lon", "capacity", "stock", "demand", "reliability", "utilization", "risk"], "nodes")
    numeric(edges, ["capacity", "lead", "cost", "co2"], "edges")

    ids = set(nodes["id"])
    unknown = sorted({*edges["source"], *edges["target"]} - ids)
    if unknown:
        errors.append(f"edges reference unknown node ids: {', '.join(unknown[:10])}")
    if errors:
        raise GraphDataError("; ".join(errors))

    for col, default in (("reliability", 0.9), ("utilization", 0.0), ("risk", None), ("co2", 0.0)):
        df = edges if col == "co2" else nodes
        if col not in df.columns:
            if col != "risk":
                warnings.append(f"column '{col}' not provided; defaulted to {default}")
            df[col] = default

    G = nx.DiGraph()
    for row in nodes.to_dict("records"):
        risk = row.get("risk")
        if risk is None or pd.isna(risk):
            risk = round(min(1.0, (1 - float(row["reliability"])) * 2), 3)  # placeholder until risk_ml runs
        G.add_node(
            row["id"],
            kind=row["kind"],
            name=str(row.get("name") or row["id"]),
            city=str(row["city"]),
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            capacity=float(row["capacity"]),
            stock=float(row["stock"]),
            demand=float(row["demand"]),
            reliability=float(min(1.0, row["reliability"])),
            utilization=float(row["utilization"]),
            risk=float(min(1.0, risk)),
            backup=str(row.get("backup", "")).strip().lower() in {"true", "1", "yes"},
            top_factors=[],
        )
    for row in edges.to_dict("records"):
        G.add_edge(row["source"], row["target"], capacity=float(row["capacity"]), lead=float(row["lead"]),
                   cost=float(row["cost"]), co2=float(row["co2"]))

    tier = {k: i for i, k in enumerate(KINDS)}
    backwards = [f"{u}->{v}" for u, v in G.edges if tier[G.nodes[v]["kind"]] <= tier[G.nodes[u]["kind"]]]
    if backwards:
        warnings.append(f"{len(backwards)} edge(s) do not flow downstream by tier: {', '.join(backwards[:5])}")
    isolated = [n for n in G if G.degree(n) == 0]
    if isolated:
        warnings.append(f"isolated nodes: {', '.join(isolated[:10])}")
    suppliers = [n for n, d in G.nodes(data=True) if d["kind"] == "supplier"]
    reachable = set().union(*(nx.descendants(G, s) for s in suppliers)) if suppliers else set()
    orphans = [n for n, d in G.nodes(data=True) if d["kind"] == "customer" and n not in reachable]
    if orphans:
        warnings.append(f"customers with no path from any supplier: {', '.join(orphans)}")
    return G, warnings


def graph_to_payload(G: nx.DiGraph, resilience_score: float) -> dict:
    """Serialise a graph into the GET /network response shape."""
    nodes = [{"id": nid, **attrs} for nid, attrs in G.nodes(data=True)]
    for n in nodes:
        n.setdefault("top_factors", [])
    edges = [{"source": u, "target": v, **attrs} for u, v, attrs in G.edges(data=True)]
    return {"nodes": nodes, "edges": edges, "resilience_score": resilience_score}


def node_index(G: nx.DiGraph) -> tuple[dict[str, str], set[tuple[str, str]]]:
    """({node_id: kind}, {(src, dst)}) used for event validation."""
    return {n: d["kind"] for n, d in G.nodes(data=True)}, set(G.edges())
