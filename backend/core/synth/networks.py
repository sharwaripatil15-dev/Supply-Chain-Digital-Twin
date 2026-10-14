"""Seeded synthetic network generator: 7 archetypes x 6 industry profiles, 10-60 nodes, engine-ready graphs.

generate_network(archetype, industry, n_nodes, seed) returns a networkx.DiGraph that follows the core.graph
conventions (node attrs kind/city/lat/lon/capacity/stock/demand/reliability/name/backup; edge attrs
capacity/lead/cost/co2) plus synthetic extras every engine module ignores but core.features uses:
    node   region, port (city has a sea port), demand_cv (bullwhip-amplified demand variability), tier_cv
    edge   mode, distance_km, lead_cv (lead-time coefficient of variation)
    graph  seed, unit_price, industry, archetype, margin, penalty_cost, holding_cost, shelf_life_days, month,
           seasonal_factor, source="synthetic"

Construction (assumptions in data/synth_assumptions.md):
    1. Tier sizes from the archetype's TIER_SHARE; demand nodes are retailers or customers per industry.
    2. Sites are placed in Indian cities (profiles.CITIES, jittered +-0.12 deg); two_region_port uses two regions and
       one port city.
    3. Topology by archetype (_topology): every downstream node is fed by its nearest k upstream nodes and every upstream
       node ships to at least its nearest downstream node, so there are no orphans.
    4. Planned flow: each node's requirement is split across its suppliers with Dirichlet weights (concentrated and
       port archetypes are biased toward one dominant source); requirements roll up tier by tier.
    5. Capacities: node = planned throughput / U(0.55, 0.85) (planned utilisation band), lane = planned flow /
       U(0.50, 0.85); idle lanes get 30-60% of their endpoints' capacity. Backup suppliers hold 15-30% of demand.
    6. Lanes: mode drawn from the industry mix among feasible modes (rail >= 300 km, air >= 500 km, sea only between
       port cities), lead = node_types.suggest_lead(mode, km) x industry lead multiplier, cost and CO2 from the mode.
    7. The undisrupted network must serve 100% of demand (checked with the exact flow engine).
"""
from __future__ import annotations

import math

import networkx as nx
import numpy as np

from core.synth.profiles import (
    ARCHETYPES, CITIES, INDUSTRIES, MODE_LEAD_CV, MODE_MIN_KM, REGIONS, bullwhip_ratio, region_of, seasonal_factor,
)
from node_types import ID_PREFIX, haversine_km, suggest_co2, suggest_cost, suggest_lead

MIN_NODES, MAX_NODES = 10, 60
UTIL_BAND = (0.55, 0.85)
LANE_SLACK = (0.50, 0.85)
IDLE_LANE_SHARE = (0.30, 0.60)
BACKUP_SHARE = (0.15, 0.30)
RELIABILITY = (0.85, 0.99)
COLD_CHAIN_COST = 1.3  # pharma lanes cost 30% more (reefer trucks, temperature logging)
JITTER_DEG = 0.12

# share of nodes per tier (supplier, factory, warehouse); the rest are demand nodes
TIER_SHARE = {
    "linear": (0.15, 0.15, 0.20),
    "multi_source": (0.22, 0.15, 0.18),
    "hub_spoke": (0.15, 0.10, 0.06),
    "two_region_port": (0.18, 0.14, 0.14),
    "backup_supplier": (0.20, 0.15, 0.17),
    "concentrated": (0.18, 0.13, 0.17),
    "long_tail": (0.40, 0.10, 0.12),
}

MATERIALS = {
    "fmcg": ["Packaging", "Edible Oils", "Flour", "Resins", "Sugar", "Surfactants"],
    "pharma": ["API", "Excipients", "Vials", "Cold Packs", "Blister Foil"],
    "electronics": ["Semiconductors", "PCBs", "Displays", "Batteries", "Plastics", "Connectors"],
    "automotive": ["Steel", "Castings", "Tyres", "Electronics", "Glass", "Forgings"],
    "apparel": ["Cotton", "Yarn", "Dyes", "Trims", "Denim"],
    "agri": ["Farm Produce", "Seeds", "Crates", "Dairy", "Grains"],
}


class SynthError(RuntimeError):
    pass


# ---------------------------------------------------------------- placement
def _place(rng: np.random.Generator, region: str | None = None, port: bool = False) -> tuple[str, float, float]:
    pool = [c for c in CITIES if (region is None or c[3] == region) and (not port or c[4])]
    if not pool:
        pool = [c for c in CITIES if c[4]] if port else list(CITIES)
    name, lat, lon, _, _ = pool[int(rng.integers(len(pool)))]
    return name, round(lat + rng.uniform(-JITTER_DEG, JITTER_DEG), 4), round(lon + rng.uniform(-JITTER_DEG, JITTER_DEG), 4)


def _tier_counts(archetype: str, n: int, rng: np.random.Generator) -> dict[str, int]:
    s_share, f_share, w_share = TIER_SHARE[archetype]
    s = max(1 if archetype == "linear" else 2, round(n * s_share))
    f = max(1, round(n * f_share))
    w = max(1, round(n * w_share))
    if archetype == "two_region_port":
        f, w = max(2, f), max(3, w)
    if archetype == "hub_spoke":
        w = int(np.clip(w, 1, 3))
    d = n - s - f - w
    while d < 2:  # tiny networks: take from the largest upstream tier
        if s >= max(f, w) and s > 1:
            s -= 1
        elif f >= w and f > 1:
            f -= 1
        else:
            w -= 1
        d = n - s - f - w
    return {"supplier": s, "factory": f, "warehouse": w, "demand": d}


# ---------------------------------------------------------------- topology
def _nearest(G: nx.DiGraph, node: str, candidates: list[str], k: int) -> list[str]:
    p = (G.nodes[node]["lat"], G.nodes[node]["lon"])
    return sorted(candidates, key=lambda c: (haversine_km(p, (G.nodes[c]["lat"], G.nodes[c]["lon"])), c))[:k]


def _connect(G: nx.DiGraph, ups: list[str], downs: list[str], fan_in: int, fan_out: int = 1) -> set[tuple[str, str]]:
    """Each downstream node <- its nearest `fan_in` ups; each up -> its nearest `fan_out` downs."""
    pairs = set()
    for d in downs:
        pairs.update((u, d) for u in _nearest(G, d, ups, fan_in))
    for u in ups:
        pairs.update((u, d) for d in _nearest(G, u, downs, fan_out))
    return pairs


def _topology(G: nx.DiGraph, archetype: str, tiers: dict[str, list[str]], rng: np.random.Generator) -> set[tuple[str, str]]:
    S = [s for s in tiers["supplier"] if not G.nodes[s]["backup"]]
    F, W, D = tiers["factory"], tiers["warehouse"], tiers["demand"]
    pairs: set[tuple[str, str]] = set()
    if archetype == "linear":
        pairs |= _connect(G, S, F, 1) | _connect(G, F, W, 1) | _connect(G, W, D, 1)
    elif archetype == "multi_source":
        pairs |= _connect(G, S, F, min(3, len(S))) | _connect(G, F, W, min(2, len(F))) | _connect(G, W, D, min(2, len(W)))
    elif archetype == "hub_spoke":
        pairs |= _connect(G, S, F, min(2, len(S)))
        pairs |= {(f, w) for f in F for w in W}  # every plant ships to every hub
        pairs |= _connect(G, W, D, 1)
    elif archetype == "two_region_port":
        port = W[0]
        regional = W[1:]
        pairs |= _connect(G, S, F, min(2, len(S)))
        pairs |= {(f, port) for f in F}
        for f in F:
            same = [w for w in regional if G.nodes[w]["region"] == G.nodes[f]["region"]] or regional
            pairs |= {(f, w) for w in _nearest(G, f, same, 1)}
        for d in D:
            pairs.add((port, d))
            same = [w for w in regional if G.nodes[w]["region"] == G.nodes[d]["region"]] or regional
            pairs |= {(w, d) for w in _nearest(G, d, same, 1)}
        for w in regional:  # every regional DC is fed by its nearest plant and serves its nearest demand node
            pairs |= {(f, w) for f in _nearest(G, w, F, 1)} | {(w, d) for d in _nearest(G, w, D, 1)}
    elif archetype == "backup_supplier":
        pairs |= _connect(G, S, F, min(2, len(S))) | _connect(G, F, W, min(2, len(F))) | _connect(G, W, D, min(2, len(W)))
    elif archetype == "concentrated":
        dominant = S[0]
        pairs |= {(dominant, f) for f in F} | _connect(G, S[1:] or S, F, 1)
        pairs |= _connect(G, F, W, min(2, len(F))) | _connect(G, W, D, 1)
    elif archetype == "long_tail":
        pairs |= {(s, _nearest(G, s, F, 1)[0]) for s in S}
        for f in F:  # every plant keeps at least two small suppliers
            pairs |= {(s, f) for s in _nearest(G, f, S, min(2, len(S)))}
        pairs |= _connect(G, F, W, min(2, len(F))) | _connect(G, W, D, 1)
    else:
        raise SynthError(f"unknown archetype {archetype!r}")
    for b in (s for s in tiers["supplier"] if G.nodes[s]["backup"]):
        pairs |= {(b, f) for f in _nearest(G, b, F, min(len(F), int(rng.integers(2, 4))))}
    return pairs


def _weights(G: nx.DiGraph, archetype: str, node: str, preds: list[str], rng: np.random.Generator) -> dict[str, float]:
    """Planned share of `node`'s requirement sourced from each predecessor (backup suppliers get none)."""
    preds = [p for p in preds if not G.nodes[p].get("backup")]
    if len(preds) == 1:
        return {preds[0]: 1.0}
    w = rng.dirichlet([2.0] * len(preds))
    bias = None
    if archetype == "concentrated" and G.nodes[node]["kind"] == "factory":
        bias = next((p for p in preds if G.nodes[p].get("dominant")), None)
    elif archetype == "two_region_port" and G.nodes[node]["kind"] != "warehouse":
        bias = next((p for p in preds if G.nodes[p].get("port_hub")), None)
    if bias is not None:
        share = rng.uniform(0.7, 0.85)
        rest = [p for p in preds if p != bias]
        w_rest = rng.dirichlet([2.0] * len(rest)) * (1 - share)
        return {bias: share, **dict(zip(rest, w_rest))}
    return dict(zip(preds, w))


# ---------------------------------------------------------------- lanes
def _mode(profile, km: float, ports: bool, rng: np.random.Generator) -> str:
    feasible = {m: p for m, p in profile.modes.items() if km >= MODE_MIN_KM[m] and (m != "sea" or (ports and km >= 300))}
    feasible.setdefault("road", 0.0)
    total = sum(feasible.values())
    if total <= 0:
        return "road"
    modes = sorted(feasible)
    return str(rng.choice(modes, p=[feasible[m] / total for m in modes]))


# ---------------------------------------------------------------- main
def generate_network(archetype: str, industry: str, n_nodes: int = 24, seed: int = 0) -> nx.DiGraph:
    """Generate one synthetic network (see the module docstring). Deterministic for a given argument tuple."""
    if archetype not in ARCHETYPES:
        raise SynthError(f"unknown archetype {archetype!r}; expected one of {ARCHETYPES}")
    if industry not in INDUSTRIES:
        raise SynthError(f"unknown industry {industry!r}; expected one of {list(INDUSTRIES)}")
    n_nodes = int(np.clip(n_nodes, MIN_NODES, MAX_NODES))
    profile = INDUSTRIES[industry]
    rng = np.random.default_rng([seed, ARCHETYPES.index(archetype), list(INDUSTRIES).index(industry), n_nodes])
    month = int(rng.integers(1, 13))
    G = nx.DiGraph(seed=seed, unit_price=float(profile.unit_price), industry=industry, archetype=archetype,
                   margin=profile.margin, penalty_cost=float(profile.penalty_cost), holding_cost=profile.holding_cost,
                   shelf_life_days=profile.shelf_life_days, month=month, seasonal_factor=seasonal_factor(profile, month),
                   source="synthetic")

    counts = _tier_counts(archetype, n_nodes, rng)
    regions = list(rng.choice(REGIONS, size=2, replace=False)) if archetype == "two_region_port" else [None]
    demand_kind = profile.demand_kind
    n_backup = (1 if n_nodes < 30 else 2) if archetype == "backup_supplier" else 0
    materials = MATERIALS[industry]

    tiers: dict[str, list[str]] = {"supplier": [], "factory": [], "warehouse": [], "demand": []}
    for tier, kind in (("supplier", "supplier"), ("factory", "factory"), ("warehouse", "warehouse"), ("demand", demand_kind)):
        for i in range(counts[tier]):
            nid = f"{ID_PREFIX[kind]}{i + 1}"
            region = regions[i % len(regions)]
            port_hub = archetype == "two_region_port" and tier == "warehouse" and i == 0
            city, lat, lon = _place(rng, None if port_hub else region, port=port_hub)
            backup = tier == "supplier" and i >= counts["supplier"] - n_backup
            if tier == "supplier":
                name = f"{city} {materials[i % len(materials)]}" + (" (backup)" if backup else "")
            elif tier == "factory":
                name = f"{city} Plant"
            elif tier == "warehouse":
                name = f"{city} {'Port DC' if port_hub else 'Hub' if archetype == 'hub_spoke' else 'DC'}"
            else:
                name = f"{city} {'Retail' if kind == 'retailer' else 'Distributor'}"
            G.add_node(nid, kind=kind, name=name, city=city, lat=lat, lon=lon, backup=backup,
                       region=region_of(city), port=any(c[0] == city and c[4] for c in CITIES),
                       dominant=archetype == "concentrated" and tier == "supplier" and i == 0, port_hub=port_hub,
                       material=materials[i % len(materials)] if tier == "supplier" else None)
            tiers[tier].append(nid)

    pairs = _topology(G, archetype, tiers, rng)

    # demand (seasonal), then planned requirements rolled up tier by tier
    req: dict[str, float] = {}
    sf = G.graph["seasonal_factor"]
    for d in tiers["demand"]:
        req[d] = float(max(5, round(rng.lognormal(math.log(profile.demand_median), profile.demand_sigma) * sf)))
        G.nodes[d]["demand"] = req[d]
    flow: dict[tuple[str, str], float] = {}
    preds = {}
    for u, v in pairs:
        preds.setdefault(v, []).append(u)
    for tier in ("demand", "warehouse", "factory"):
        for v in tiers[tier]:
            need = req.get(v, 0.0)
            for u, w in _weights(G, archetype, v, sorted(preds.get(v, [])), rng).items():
                flow[(u, v)] = need * w
                req[u] = req.get(u, 0.0) + need * w
    total_demand = sum(G.nodes[d]["demand"] for d in tiers["demand"])

    for tier in ("supplier", "factory", "warehouse"):
        planned = [req.get(n, 0.0) for n in tiers[tier] if req.get(n, 0.0) > 0]
        fallback = (np.median(planned) if planned else total_demand / max(1, len(tiers[tier]))) * 0.5
        for n in tiers[tier]:
            d = G.nodes[n]
            if d["backup"]:
                d["capacity"] = float(math.ceil(total_demand * rng.uniform(*BACKUP_SHARE)))
            else:
                thr = req.get(n, 0.0)
                d["capacity"] = float(math.ceil(thr / rng.uniform(*UTIL_BAND))) if thr > 0 else float(math.ceil(fallback))
            d["demand"] = 0.0
            cover = {"supplier": (2, 6), "factory": (1, 3), "warehouse": (3, 10)}[tier]
            base = req.get(n, 0.0) if tier == "warehouse" else d["capacity"]
            d["stock"] = float(round(base * rng.uniform(*cover)))
    lo, hi = profile.cover_days
    for d in tiers["demand"]:
        G.nodes[d]["capacity"] = 0.0
        G.nodes[d]["stock"] = float(round(G.nodes[d]["demand"] * float(np.clip(rng.uniform(lo, hi), 3, 30))))
    for n in G:
        G.nodes[n]["reliability"] = round(float(rng.uniform(*RELIABILITY)), 3)

    for u, v in sorted(pairs):
        a, b = G.nodes[u], G.nodes[v]
        km = round(haversine_km((a["lat"], a["lon"]), (b["lat"], b["lon"])), 1)
        mode = _mode(profile, km, a["port"] and b["port"], rng)
        lead = max(1.0, round(suggest_lead(mode, km) * rng.uniform(*profile.lead_mult), 1))
        f = flow.get((u, v), 0.0)
        if a["backup"]:
            cap = a["capacity"]
        elif f > 0:
            cap = math.ceil(f / rng.uniform(*LANE_SLACK))
        else:
            cap = math.ceil(min(a["capacity"], b["capacity"] or b["demand"]) * rng.uniform(*IDLE_LANE_SHARE))
        cost = suggest_cost(mode, km) * (COLD_CHAIN_COST if industry == "pharma" else 1.0)
        G.add_edge(u, v, capacity=float(max(1, cap)), lead=lead, cost=round(cost, 1), co2=suggest_co2(mode, km),
                   mode=mode, distance_km=km, lead_cv=round(MODE_LEAD_CV[mode] * rng.uniform(0.8, 1.2), 3))

    # bullwhip: order variability grows upstream with the inbound lead time of the tier below
    cv = profile.demand_cv
    for d in tiers["demand"]:
        G.nodes[d]["demand_cv"] = round(cv, 3)
    for tier, below in (("warehouse", "demand"), ("factory", "warehouse"), ("supplier", "factory")):
        leads = [G.edges[u, v]["lead"] for u, v in G.edges if u in tiers[tier] and v in tiers[below]]
        ratio = bullwhip_ratio(float(np.mean(leads)) if leads else 1.0)
        cv = min(1.5, cv * math.sqrt(ratio))
        for n in tiers[tier]:
            G.nodes[n]["demand_cv"] = round(cv, 3)
    for n in G:
        G.nodes[n].pop("port_hub", None)
        G.nodes[n].pop("dominant", None)

    _calibrate_utilization(G, rng)
    _check(G)
    return G


def _calibrate_utilization(G: nx.DiGraph, rng: np.random.Generator, rounds: int = 10) -> None:
    """Re-size sites so the exact min-cost baseline runs them inside UTIL_BAND.

    Min-cost routing concentrates flow on cheap paths, so the planned split is only a starting point: each round
    solves the baseline flow and re-sizes every used, non-backup site to throughput / U(UTIL_BAND). The previous
    flow stays feasible, so demand stays fully served; lanes bound how far flow can shift, so this settles quickly.
    Sites the optimum leaves idle keep their planned (standby) capacity.
    """
    from core.sim import solve_flow

    target = {n: rng.uniform(*UTIL_BAND) for n in G}
    for _ in range(rounds):
        thr = solve_flow(G)["throughput"]
        off = False
        for n, d in G.nodes(data=True):
            if d["kind"] not in ("supplier", "factory", "warehouse") or d.get("backup") or not d["capacity"]:
                continue
            t = thr.get(n, 0.0)
            if t > 0 and not UTIL_BAND[0] - 0.02 <= t / d["capacity"] <= UTIL_BAND[1] + 0.02:
                d["capacity"] = float(math.ceil(t / target[n]))
                off = True
        if not off:
            return


def _check(G: nx.DiGraph) -> None:
    """The undisrupted network must serve every unit of demand, with no orphans."""
    from core.sim import solve_flow

    if any(G.degree(n) == 0 for n in G):
        raise SynthError("generated network has isolated nodes")
    unmet = sum(solve_flow(G)["unmet"].values())
    if unmet > 0:
        for _, _, d in G.edges(data=True):  # integer rounding in the flow engine: widen lanes slightly
            d["capacity"] = float(math.ceil(d["capacity"] * 1.05))
        for n, d in G.nodes(data=True):
            if d["kind"] in ("supplier", "factory", "warehouse") and not d.get("backup"):
                d["capacity"] = float(math.ceil(d["capacity"] * 1.05))
        if sum(solve_flow(G)["unmet"].values()) > 0:
            raise SynthError(f"generated network misses {unmet:.0f} units/day of demand at baseline")


def random_spec(rng: np.random.Generator, min_nodes: int = MIN_NODES, max_nodes: int = MAX_NODES) -> tuple[str, str, int]:
    """(archetype, industry, n_nodes) drawn uniformly."""
    return (str(rng.choice(ARCHETYPES)), str(rng.choice(list(INDUSTRIES))), int(rng.integers(min_nodes, max_nodes + 1)))


def to_builder(G: nx.DiGraph) -> tuple[list[dict], list[dict]]:
    """Builder records for the Manual Builder / POST /network/import, with industry-specific fields filled in."""
    import builder

    profile = INDUSTRIES.get(G.graph.get("industry", ""), None)
    nodes, edges = builder.graph_to_builder(G)
    for rec in nodes:
        d = G.nodes[rec["id"]]
        rec["name"] = d.get("name") or rec["id"]
        if rec["kind"] == "supplier":
            rec["material"] = d.get("material")
            inbound = [G.edges[rec["id"], v]["lead"] for v in G.successors(rec["id"])]
            rec["lead_time_days"] = round(float(np.mean(inbound)), 1) if inbound else None
        elif rec["kind"] == "warehouse" and profile:
            rec["holding_cost"] = profile.holding_cost
        elif rec["kind"] == "retailer" and profile:
            rec["demand_variability_pct"] = round(profile.demand_cv * 100, 1)
        elif rec["kind"] == "customer" and profile:
            rec["penalty_per_unit"] = float(profile.penalty_cost)
    by_pair = {(u, v): d for u, v, d in G.edges(data=True)}
    for rec in edges:
        rec["mode"] = by_pair[(rec["source"], rec["target"])].get("mode", "road")
    return nodes, edges
