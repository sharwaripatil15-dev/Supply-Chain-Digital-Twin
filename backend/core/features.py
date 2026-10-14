"""Feature engineering: the ONE place graph, inventory and disruption features are defined.

Used by the scenario surrogate (core.risk_ml), the dataset builder (core.synth.build), the bottleneck analyzer
(core.bottleneck) and the what-if planner (core.whatif). Works on any engine graph (preset, CSV, manual, synthetic);
attributes only synthetic networks carry (region, lead_cv, demand_cv, industry) fall back to documented defaults.

Baseline = core.sim.solve_flow(G) (undisrupted min-cost flow, backup closed). "Primary suppliers" exclude backups.

NODE FEATURES  node_features(G) -> DataFrame (index = node id)
    betweenness          nx.betweenness_centrality (directed, unweighted), 0..1
    closeness            nx.closeness_centrality (directed, inward distance), 0..1
    pagerank             PageRank on the REVERSED graph (importance to everything downstream), sums to 1
    in_degree/out_degree lane counts
    articulation         1 if removing the node leaves some demand node with no path from any primary supplier
    loss_if_down         share of total demand the network can no longer serve with the node removed (steady state,
                         backup available) = the drop in source->sink max flow, i.e. its min-cut contribution
    flow_share           baseline throughput / total demand (demand nodes: own demand / total demand)
    downstream_demand    share of total demand at demand nodes reachable from the node (itself included)
    alt_paths            node-disjoint supplier->demand paths left when the node is removed
    extra_lead_alt       mean extra lead time (days) of the fastest remaining path for the demand nodes downstream of
                         the node when it is removed (MAX_EXTRA_LEAD if some lose every path)
    utilization          baseline throughput / capacity (0 for leaf demand nodes)
    headroom_share       (capacity - throughput) / total demand
    cover_days           stock / daily requirement: demand nodes / demand, warehouses / throughput (capacity if idle),
                         factories and suppliers / capacity
    replenish_lead       flow-weighted arrival lead time from suppliers (core.delay.arrival_lead), days
    cover_vs_lead        cover_days / max(1, replenish_lead): < SAFETY_FACTOR means stock runs out before resupply
    lead_cv_in           mean lead-time coefficient of variation of inbound lanes (lane lead_cv, else MODE_LEAD_CV[mode])
    tier                 0 supplier .. 4 customer (node_types.TIER)
    demand_cv            demand variability seen at the node (synthetic bullwhip attr, else DEFAULT_DEMAND_CV)

LANE FEATURES  edge_features(G) -> DataFrame (index = "U->V")
    flow_share, loss_if_down, utilization (flow / capacity), lead, lead_cv, edge_betweenness,
    alt_inbound (other inbound lanes of the target with spare capacity, as a share of the lane's flow)

NETWORK FEATURES  network_features(G) -> dict
    n_nodes, n_edges, log_total_demand, supplier_hhi (sum of squared baseline supplier output shares), max_supplier_share,
    n_suppliers, has_backup, backup_share (backup capacity / demand), mean_util (throughput-weighted), max_util,
    mean_cover_days (demand-weighted, demand nodes), min_cover_vs_lead (demand nodes), mean_lead, mean_lead_cv,
    n_regions, ind_<industry> one-hot (ind_other for non-synthetic networks)

SCENARIO FEATURES  scenario_features(ctx, events, dtype=None, horizon=30) -> dict (SCENARIO_FEATURES columns)
    the network features, plus
    disruption   dt_<type> one-hot, severity_max, severity_mean, duration (first start .. last end), start,
                 start_frac (start / horizon), n_events, n_node_targets, n_edge_targets, n_demand_targets
    targets      capacity_lost_share = sum(flow_share x severity) over node and lane targets,
                 loss_max = max(loss_if_down x severity), loss_sum, betweenness_max, pagerank_max, closeness_max,
                 articulation_any, downstream_demand_max, alt_paths_min, extra_lead_alt_max, target_util_max,
                 target_headroom_min, tier_min, lead_cv_max
    buffers      downstream_cover_min (min cover_days of demand nodes downstream of a capacity target, or of a
                 demand-event target), cover_minus_duration, cover_over_duration
    demand       demand_up_share = sum(demand share x severity) of spikes, demand_down_share likewise for drops
    lead time    lead_mult_max, lead_inflation_share = sum(flow_share x (lead multiplier - 1))
    region       n_regions_hit, region_node_share (share of nodes in the regions hit), regional_correlation (share of
                 targets in the most-hit region; 1 = fully correlated)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import pandas as pd

from core.synth.disruptions import DISRUPTION_TYPES, infer_type
from core.synth.profiles import INDUSTRY_KEYS, MODE_LEAD_CV, region_of
from node_types import TIER, is_demand, total_demand

MAX_EXTRA_LEAD = 30.0
DEFAULT_DEMAND_CV = 0.25
DEFAULT_LEAD_CV = 0.2
SAFETY_FACTOR = 1.5

NODE_FEATURES = [
    "betweenness", "closeness", "pagerank", "in_degree", "out_degree", "articulation", "loss_if_down", "flow_share",
    "downstream_demand", "alt_paths", "extra_lead_alt", "utilization", "headroom_share", "cover_days",
    "replenish_lead", "cover_vs_lead", "lead_cv_in", "tier", "demand_cv",
]
EDGE_FEATURES = ["flow_share", "loss_if_down", "utilization", "lead", "lead_cv", "edge_betweenness", "alt_inbound"]
NETWORK_FEATURES = [
    "n_nodes", "n_edges", "log_total_demand", "supplier_hhi", "max_supplier_share", "n_suppliers", "has_backup",
    "backup_share", "mean_util", "max_util", "mean_cover_days", "min_cover_vs_lead", "mean_lead", "mean_lead_cv",
    "n_regions", *[f"ind_{k}" for k in INDUSTRY_KEYS], "ind_other",
]
DISRUPTION_FEATURES = [
    *[f"dt_{k}" for k in DISRUPTION_TYPES], "severity_max", "severity_mean", "duration", "start", "start_frac",
    "n_events", "n_node_targets", "n_edge_targets", "n_demand_targets",
]
TARGET_FEATURES = [
    "capacity_lost_share", "loss_max", "loss_sum", "betweenness_max", "pagerank_max", "closeness_max",
    "articulation_any", "downstream_demand_max", "alt_paths_min", "extra_lead_alt_max", "target_util_max",
    "target_headroom_min", "tier_min", "lead_cv_max", "downstream_cover_min", "cover_minus_duration",
    "cover_over_duration", "demand_up_share", "demand_down_share", "lead_mult_max", "lead_inflation_share",
    "n_regions_hit", "region_node_share", "regional_correlation",
]
SCENARIO_FEATURES = NETWORK_FEATURES + DISRUPTION_FEATURES + TARGET_FEATURES


def _lane_cv(d: dict) -> float:
    return float(d.get("lead_cv") or MODE_LEAD_CV.get(d.get("mode") or "road", DEFAULT_LEAD_CV))


def _region(G: nx.DiGraph, n: str) -> str:
    d = G.nodes[n]
    return d.get("region") or region_of(d.get("city"), d.get("lat"), d.get("lon"))


def primary_suppliers(G: nx.DiGraph) -> list[str]:
    return [n for n, d in G.nodes(data=True) if d.get("kind") == "supplier" and not d.get("backup")]


def _loss_if_down(G: nx.DiGraph, nodes=(), edges=()) -> float:
    from core.sim import solve_flow, unmet_frac

    return unmet_frac(G, solve_flow(G, down_nodes=nodes, down_edges=edges, allow_backup=True))


def _alt_paths(G: nx.DiGraph) -> dict[str, int]:
    """Node-disjoint primary-supplier -> demand-node paths left when each node is removed."""
    H = nx.DiGraph()
    H.add_nodes_from(G)
    H.add_edges_from(G.edges)
    for s in primary_suppliers(G):
        H.add_edge("__SRC__", s)
    for n, d in G.nodes(data=True):
        if is_demand(d["kind"]):
            H.add_edge(n, "__SINK__")
    if "__SRC__" not in H or "__SINK__" not in H:
        return {n: 0 for n in G}
    out = {}
    for n in G:
        K = H.copy()
        K.remove_node(n)
        out[n] = int(nx.node_connectivity(K, "__SRC__", "__SINK__")) if nx.has_path(K, "__SRC__", "__SINK__") else 0
    return out


def _fastest_lead(G: nx.DiGraph, removed: str | None = None) -> dict[str, float]:
    """Shortest lead-time path (days) from any primary supplier to every node, optionally without `removed`."""
    H = G if removed is None else nx.restricted_view(G, [removed], [])
    srcs = [s for s in primary_suppliers(G) if s != removed]
    if not srcs:
        return {}
    return nx.multi_source_dijkstra_path_length(H, srcs, weight="lead")


def node_features(G: nx.DiGraph) -> pd.DataFrame:
    """One row per node with the NODE_FEATURES columns (see the module docstring)."""
    from core.delay import arrival_lead
    from core.sim import solve_flow

    if G.number_of_nodes() == 0:
        return pd.DataFrame(columns=NODE_FEATURES)
    total = total_demand(G) or 1.0
    base = solve_flow(G)
    base_loss = _loss_if_down(G)
    served_in = {n: sum(base["flow"].get((u, n), 0.0) for u in G.predecessors(n)) for n in G}
    between = nx.betweenness_centrality(G)
    close = nx.closeness_centrality(G)
    try:
        pr = nx.pagerank(G.reverse(copy=False), max_iter=200)
    except nx.PowerIterationFailedConvergence:
        pr = {n: 1.0 / len(G) for n in G}
    alt = _alt_paths(G)
    lead_in = arrival_lead(G, base["flow"])
    fast = _fastest_lead(G)
    demand_nodes = [n for n, d in G.nodes(data=True) if is_demand(d["kind"]) and (d.get("demand") or 0) > 0]
    srcs = primary_suppliers(G)
    reach_all = set(srcs).union(*(nx.descendants(G, s) for s in srcs)) if srcs else set()

    rows = {}
    for n, d in G.nodes(data=True):
        kind = d["kind"]
        cap = float(d.get("capacity") or 0.0)
        thr = base["throughput"].get(n, served_in[n]) if not is_demand(kind) else served_in[n]
        down = nx.descendants(G, n) | {n}
        dd = [c for c in demand_nodes if c in down]
        # articulation (directed): some demand node reachable today loses every path from a primary supplier
        H = nx.restricted_view(G, [n], [])
        reach = set().union(*(nx.descendants(H, s) | {s} for s in srcs if s != n)) if srcs else set()
        articulation = any(c in reach_all and c not in reach for c in demand_nodes if c != n)
        extra = 0.0
        if dd and not is_demand(kind):
            alt_fast = _fastest_lead(G, n)
            gaps = [(alt_fast[c] - fast[c]) if c in alt_fast else MAX_EXTRA_LEAD for c in dd if c != n and c in fast]
            extra = float(min(MAX_EXTRA_LEAD, np.mean(gaps))) if gaps else 0.0
        if is_demand(kind):
            need = float(d.get("demand") or 0.0)
            loss = need / total
        else:
            need = thr if (kind == "warehouse" and thr > 0) else cap
            loss = max(0.0, _loss_if_down(G, nodes=[n]) - base_loss)
        stock = float(d.get("stock") or 0.0)
        cover = stock / need if need > 0 else 0.0
        rl = lead_in.get(n)
        rl = float(rl) if rl is not None else float(fast.get(n, 0.0))
        lanes_in = [G.edges[u, n] for u in G.predecessors(n)]
        rows[n] = {
            "betweenness": between[n], "closeness": close[n], "pagerank": pr[n],
            "in_degree": G.in_degree(n), "out_degree": G.out_degree(n),
            "articulation": float(articulation and not is_demand(kind)),
            "loss_if_down": loss,
            "flow_share": (float(d.get("demand") or 0.0) if is_demand(kind) else thr) / total,
            "downstream_demand": sum(G.nodes[c].get("demand") or 0.0 for c in dd) / total,
            "alt_paths": alt.get(n, 0), "extra_lead_alt": extra,
            "utilization": thr / cap if cap > 0 and not (is_demand(kind) and not G.out_degree(n)) else 0.0,
            "headroom_share": max(0.0, cap - thr) / total if cap > 0 and not is_demand(kind) else 0.0,
            "cover_days": cover, "replenish_lead": rl, "cover_vs_lead": cover / max(1.0, rl),
            "lead_cv_in": float(np.mean([_lane_cv(e) for e in lanes_in])) if lanes_in else 0.0,
            "tier": TIER.get(kind, 0), "demand_cv": float(d.get("demand_cv") or DEFAULT_DEMAND_CV),
        }
    return pd.DataFrame.from_dict(rows, orient="index")[NODE_FEATURES]


def edge_features(G: nx.DiGraph) -> pd.DataFrame:
    """One row per lane ("U->V") with the EDGE_FEATURES columns."""
    from core.sim import solve_flow

    if G.number_of_edges() == 0:
        return pd.DataFrame(columns=EDGE_FEATURES)
    total = total_demand(G) or 1.0
    base = solve_flow(G)
    base_loss = _loss_if_down(G)
    eb = nx.edge_betweenness_centrality(G)
    rows = {}
    for u, v, d in G.edges(data=True):
        f = base["flow"].get((u, v), 0.0)
        spare = sum(max(0.0, G.edges[p, v]["capacity"] - base["flow"].get((p, v), 0.0)) for p in G.predecessors(v) if p != u)
        rows[f"{u}->{v}"] = {
            "flow_share": f / total,
            "loss_if_down": max(0.0, _loss_if_down(G, edges=[(u, v)]) - base_loss) if f > 0 else 0.0,
            "utilization": f / d["capacity"] if d["capacity"] else 0.0,
            "lead": float(d.get("lead") or 0.0), "lead_cv": _lane_cv(d), "edge_betweenness": eb[(u, v)],
            "alt_inbound": min(5.0, spare / f) if f > 0 else 5.0,
        }
    return pd.DataFrame.from_dict(rows, orient="index")[EDGE_FEATURES]


def supplier_shares(G: nx.DiGraph, throughput: dict | None = None) -> dict[str, float]:
    """Baseline output share of each primary supplier (sums to 1 when anything flows)."""
    from core.sim import solve_flow

    thr = throughput if throughput is not None else solve_flow(G)["throughput"]
    out = {s: thr.get(s, 0.0) for s in primary_suppliers(G)}
    tot = sum(out.values())
    return {s: v / tot for s, v in out.items()} if tot > 0 else {s: 0.0 for s in out}


def hhi(shares) -> float:
    """Herfindahl-Hirschman index of shares (0..1): 1 = a single source."""
    return float(sum(s * s for s in shares))


def network_features(G: nx.DiGraph, nf: pd.DataFrame | None = None) -> dict:
    from core.sim import solve_flow

    nf = node_features(G) if nf is None else nf
    total = total_demand(G)
    base = solve_flow(G) if G.number_of_nodes() else {"throughput": {}}
    shares = supplier_shares(G, base["throughput"])
    sites = [n for n, d in G.nodes(data=True) if not is_demand(d["kind"]) and not d.get("backup") and (d.get("capacity") or 0) > 0]
    thr = np.array([base["throughput"].get(n, 0.0) for n in sites])
    util = np.array([nf.at[n, "utilization"] for n in sites]) if sites else np.array([0.0])
    dem = [(n, d.get("demand") or 0.0) for n, d in G.nodes(data=True) if is_demand(d["kind"])]
    w = np.array([q for _, q in dem]) if dem else np.array([0.0])
    cover = np.array([nf.at[n, "cover_days"] for n, _ in dem]) if dem else np.array([0.0])
    cvl = np.array([nf.at[n, "cover_vs_lead"] for n, _ in dem]) if dem else np.array([0.0])
    lanes = list(G.edges(data=True))
    industry = G.graph.get("industry")
    backup_cap = sum(d.get("capacity") or 0.0 for _, d in G.nodes(data=True) if d.get("backup"))
    out = {
        "n_nodes": G.number_of_nodes(), "n_edges": G.number_of_edges(), "log_total_demand": float(np.log1p(total)),
        "supplier_hhi": hhi(shares.values()), "max_supplier_share": max(shares.values(), default=0.0),
        "n_suppliers": len(shares), "has_backup": float(backup_cap > 0), "backup_share": backup_cap / total if total else 0.0,
        "mean_util": float(np.average(util, weights=thr)) if sites and thr.sum() > 0 else 0.0,
        "max_util": float(util.max()) if sites else 0.0,
        "mean_cover_days": float(np.average(cover, weights=w)) if w.sum() > 0 else 0.0,
        "min_cover_vs_lead": float(cvl.min()) if dem else 0.0,
        "mean_lead": float(np.mean([d["lead"] for _, _, d in lanes])) if lanes else 0.0,
        "mean_lead_cv": float(np.mean([_lane_cv(d) for _, _, d in lanes])) if lanes else 0.0,
        "n_regions": len({_region(G, n) for n in G}),
        **{f"ind_{k}": float(industry == k) for k in INDUSTRY_KEYS},
        "ind_other": float(industry not in INDUSTRY_KEYS),
    }
    return out


def fingerprint(G: nx.DiGraph) -> str:
    payload = [sorted((str(n), sorted((k, str(v)) for k, v in d.items())) for n, d in G.nodes(data=True)),
               sorted((str(u), str(v), sorted((k, str(x)) for k, x in d.items())) for u, v, d in G.edges(data=True)),
               sorted((k, str(v)) for k, v in G.graph.items())]
    return hashlib.sha1(json.dumps(payload).encode()).hexdigest()


@dataclass
class FeatureContext:
    """Per-network features computed once and reused for every scenario on that network."""
    G: nx.DiGraph
    nodes: pd.DataFrame = field(init=False)
    edges: pd.DataFrame = field(init=False)
    network: dict = field(init=False)
    regions: dict = field(init=False)
    downstream: dict = field(init=False)
    nrec: dict = field(init=False)  # nodes as {id: {feature: value}} (fast lookups per scenario)
    erec: dict = field(init=False)
    demand: dict = field(init=False)

    def __post_init__(self):
        self.nodes = node_features(self.G)
        self.edges = edge_features(self.G)
        self.network = network_features(self.G, self.nodes)
        self.regions = {n: _region(self.G, n) for n in self.G}
        self.downstream = {n: nx.descendants(self.G, n) | {n} for n in self.G}
        self.nrec = self.nodes.to_dict("index")
        self.erec = self.edges.to_dict("index")
        self.demand = {n: float(d.get("demand") or 0.0) for n, d in self.G.nodes(data=True) if is_demand(d["kind"])}


_CTX_CACHE: dict[str, FeatureContext] = {}


def context(G: nx.DiGraph) -> FeatureContext:
    """Memoised FeatureContext for the app's graphs (keyed by a content fingerprint)."""
    key = fingerprint(G)
    if key not in _CTX_CACHE:
        if len(_CTX_CACHE) > 16:
            _CTX_CACHE.clear()
        _CTX_CACHE[key] = FeatureContext(G)
    return _CTX_CACHE[key]


def scenario_features(ctx: FeatureContext, events, dtype: str | None = None, horizon: int = 30) -> dict:
    """SCENARIO_FEATURES for one disruption (a list of schemas.Event) on ctx.G."""
    G, nr, er = ctx.G, ctx.nrec, ctx.erec
    events = list(events)
    dtype = dtype or (infer_type(G, events) if events else "route_blockage")
    total = total_demand(G) or 1.0
    out = dict(ctx.network)
    out.update({f"dt_{k}": float(dtype == k) for k in DISRUPTION_TYPES})
    if not events:
        out.update({k: 0.0 for k in DISRUPTION_FEATURES if not k.startswith("dt_")})
        out.update({k: 0.0 for k in TARGET_FEATURES})
        return out
    start = min(e.start for e in events)
    end = max(e.start + e.duration for e in events)
    sev = [e.severity for e in events]
    node_t = [(e.target, e.severity) for e in events if e.type == "node" and e.target in nr]
    edge_t = [(e.target.replace(" ", ""), e.severity, e) for e in events if e.type == "edge"]
    edge_t = [(t, s, e) for t, s, e in edge_t if t in er]
    dem_t = [e for e in events if e.type == "demand" and e.target in ctx.demand]
    duration = end - start
    out.update({
        "severity_max": max(sev), "severity_mean": sum(sev) / len(sev), "duration": duration, "start": start,
        "start_frac": start / max(1, horizon), "n_events": len(events), "n_node_targets": len({t for t, _ in node_t}),
        "n_edge_targets": len({t for t, _, _ in edge_t}), "n_demand_targets": len({e.target for e in dem_t}),
    })
    cap_lost = sum(nr[t]["flow_share"] * s for t, s in node_t if t not in ctx.demand)
    cap_lost += sum(er[t]["flow_share"] * s for t, s, _ in edge_t)
    losses = [nr[t]["loss_if_down"] * s for t, s in node_t] + [er[t]["loss_if_down"] * s for t, s, _ in edge_t]
    tnodes = [t for t, _ in node_t] + [t.split("->")[1] for t, _, _ in edge_t]
    feat = [nr[t] for t in sorted({t for t, _ in node_t} | {t.split("->")[0] for t, _, _ in edge_t})]
    affected: set = set()
    for t in tnodes:
        affected |= ctx.downstream.get(t, set())
    affected |= {e.target for e in dem_t}
    covers = [nr[n]["cover_days"] for n in affected if n in ctx.demand]
    cover_min = min(covers) if covers else max((r["cover_days"] for r in nr.values()), default=0.0)
    up = [e for e in dem_t if getattr(e, "direction", None) != "down"]
    dn = [e for e in dem_t if getattr(e, "direction", None) == "down"]
    lead_mults = [e.lead_multiplier or 1.0 for _, _, e in edge_t]
    target_ids = [t for t, _ in node_t] + [t.split("->")[1] for t, _, _ in edge_t] + [e.target for e in dem_t]
    regions = [ctx.regions.get(t, "other") for t in target_ids]
    hit = set(regions)
    top = max((regions.count(r) for r in hit), default=0)
    col = lambda k, f, default: f(r[k] for r in feat) if feat else default  # noqa: E731
    out.update({
        "capacity_lost_share": float(min(3.0, cap_lost)),
        "loss_max": float(max(losses, default=0.0)), "loss_sum": float(min(3.0, sum(losses))),
        "betweenness_max": col("betweenness", max, 0.0), "pagerank_max": col("pagerank", max, 0.0),
        "closeness_max": col("closeness", max, 0.0), "articulation_any": col("articulation", max, 0.0),
        "downstream_demand_max": col("downstream_demand", max, 0.0), "alt_paths_min": col("alt_paths", min, 0.0),
        "extra_lead_alt_max": col("extra_lead_alt", max, 0.0), "target_util_max": col("utilization", max, 0.0),
        "target_headroom_min": col("headroom_share", min, 0.0), "tier_min": col("tier", min, 4.0),
        "lead_cv_max": float(max([nr[t]["lead_cv_in"] for t in tnodes if t in nr] or [0.0])),
        "downstream_cover_min": float(cover_min),
        "cover_minus_duration": float(cover_min - duration),
        "cover_over_duration": float(cover_min / max(1, duration)),
        "demand_up_share": sum(ctx.demand[e.target] * e.severity for e in up) / total,
        "demand_down_share": sum(ctx.demand[e.target] * e.severity for e in dn) / total,
        "lead_mult_max": float(max(lead_mults, default=1.0)),
        "lead_inflation_share": float(sum(er[t]["flow_share"] * ((e.lead_multiplier or 1.0) - 1.0) for t, _, e in edge_t)),
        "n_regions_hit": len(hit),
        "region_node_share": sum(1 for n in G if ctx.regions[n] in hit) / max(1, G.number_of_nodes()),
        "regional_correlation": top / len(regions) if regions else 0.0,
    })
    return out


def feature_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=SCENARIO_FEATURES).astype(float)
