"""Expansion planner: which new warehouses / factories to open, and where. Owner: D.

Dijkstra alone finds the cheapest PATH; it does not choose LOCATIONS. The planner therefore runs in two stages and then
checks every plan with the engine:

1. DIJKSTRA STAGE (`TransportModel`). A transport graph over the existing nodes plus the candidate sites. Each point
   links to its K_NEAREST nearest points (k-nearest-neighbour edges keep the graph sparse) and keeps the network's own
   lanes. Every link takes its best feasible mode (road always; rail >= 300 km; air >= 500 km; sea between two port
   cities) by generalized cost = freight + TIME_VALUE x lead + (CO2 price x kg if the CO2 toggle is on) + (weather
   penalty if the weather toggle is on: WEATHER_RISK_INR x flood exposure of the endpoints). scipy.sparse.csgraph.dijkstra
   runs from every candidate; the paths give cost, lead-time and CO2 matrices candidate -> demand node (outbound) and
   candidate -> supplier / factory (inbound). Matrices are cached per (network version, candidate set, toggles).
2. LOCATION OPTIMIZATION (`solve_milp`). Capacitated fixed-charge facility location in PuLP/CBC. Options = (candidate,
   facility type). Variables: open y (binary), flow x[o, d] (units/day, only where lead <= max lead), existing flow
   e[d] (<= what today's network can still serve at the planning demand), unmet u[d], and for redundancy link
   indicators z[o, d]. Upstream headroom: the extra units the existing network can deliver to an option's inbound
   sources is measured with the exact flow engine (a probe sink attached to those sources); new flow beyond what is
   moved off today's paths may not exceed the headroom of the open options. Minimise annual cost = fixed (capex x CRF + opex + hazard premium) + 365 x (transport + holding
   + lead-time weight x days + CO2 price x kg) per unit + unmet penalty, minus a resilience reward for demand nodes
   that gain a second source. Constraints: demand balance, site capacity, exactly `n_add` sites, one type per site,
   max sites per type, budget on build cost, factory- and supplier-tier capacity for the extra flow, and optional hard
   redundancy (every demand node reachable from >= 2 sources). CBC runs with a time limit: status "optimal" or "best
   found"; an infeasible model returns an explanation from the pre-checks. A greedy marginal-gain heuristic (one fixed-
   site LP per step, scipy HiGHS) is the fallback and the cross-check (its objective gap is reported).
   Three goals give the three plans: Lowest cost, Best service, Most resilient (GOAL_WEIGHTS).
3. RESILIENCE EVALUATION (`evaluate_plan`). Each plan is applied to a COPY of the network (new nodes + lanes, see
   `plan_graph`); the exact flow engine re-computes service level, lead time, freight and CO2 at the planning demand,
   Chaos Finder re-scores resilience and single points of failure, and the Health Score is recomputed. Savings,
   payback and sensitivity (demand +-20%) come from these engine runs, not from the MILP's estimates.
Costs are illustrative (TYPE_COST, data/candidate_sites.json indices): replace them with client data.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import networkx as nx
import numpy as np

from core import chaos, features, narrative
from core.delay import arrival_lead
from core.optimizer import HOLDING_PER_DAY, W_CO2
from core.sim import solve_flow
from node_types import MODE_DEFAULTS, haversine_km, is_demand, suggest_co2, suggest_cost, suggest_lead, total_demand

SITES_PATH = Path(__file__).resolve().parent.parent / "data" / "candidate_sites.json"
TYPES = ("warehouse", "factory")
K_NEAREST = 6
TIME_VALUE = 0.004  # INR per unit-day of lead time, as a share of the unit price (Dijkstra's generalized cost)
WEATHER_RISK_INR = 250.0
CRF = 0.1314  # capital recovery factor: 10% over 15 years
# capex per unit/day of capacity, as a multiple of the unit price; opex per year as a share of capex
TYPE_COST = {"warehouse": {"capex_x": 50.0, "opex_share": 0.12, "cap_share": 0.25, "handling": 1.0},
             "factory": {"capex_x": 250.0, "opex_share": 0.15, "cap_share": 0.30, "handling": 1.5}}
HAZARD_PREMIUM = 0.05  # annual risk premium, share of capex, at full (flood + seismic) / 2 exposure
SAFETY_DAYS = 5.0  # stock a new site holds, days of its throughput
DEFAULT_GROWTH = 0.15
DEFAULT_MAX_LEAD = 7.0
DEFAULT_MARGIN = 0.25
TOP_DEMAND = 15  # each option may serve at most its 15 cheapest-to-reach demand nodes (keeps the MILP small)
TIME_LIMIT = 8
# lead weight / unmet penalty / resilience reward as multiples of the unit price; hazard premium multiplier
GOAL_WEIGHTS = {
    "cost": {"lead": 0.0, "unmet": "margin", "reward": 0.0, "hazard": 1.0, "label": "Lowest cost"},
    "service": {"lead": 0.02, "unmet": "price", "reward": 0.0, "hazard": 1.0, "label": "Best service"},
    "resilience": {"lead": 0.005, "unmet": "margin", "reward": 0.05, "hazard": 3.0, "label": "Most resilient"},
    "balanced": {"lead": 0.01, "unmet": "mid", "reward": 0.02, "hazard": 2.0, "label": "Balanced"},
}
PLAN_GOALS = ("cost", "service", "resilience")


class Cancelled(Exception):
    pass


class ExpansionError(ValueError):
    """Bad input (shown to the user)."""


def inr(v: float) -> str:
    from core.strategies import fmt_inr

    return fmt_inr(v)


def _r(v, d=2):
    return round(float(v), d)


# ---------------------------------------------------------------- candidates
class CandidateStore:
    """The library (data/candidate_sites.json) plus custom and auto-generated sites, and an exclusion list."""

    def __init__(self, path: Path = SITES_PATH):
        self._lock = threading.Lock()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.note = data["note"]
        self.library = {s["id"]: {**s, "source": "library"} for s in data["sites"]}
        self.custom: dict[str, dict] = {}
        self.excluded: set[str] = set()

    def all(self) -> list[dict]:
        return [{**s, "excluded": s["id"] in self.excluded} for s in [*self.library.values(), *self.custom.values()]]

    def active(self, ids: list[str] | None = None) -> list[dict]:
        pool = [s for s in self.all() if not s["excluded"]]
        return [s for s in pool if s["id"] in set(ids)] if ids else pool

    def add(self, site: dict, source: str = "custom") -> dict:
        with self._lock:
            base = "".join(ch for ch in site.get("name", "SITE").upper() if ch.isalnum())[:4] or "SITE"
            sid, i = f"{'A' if source == 'auto' else 'U'}_{base}", 1
            while sid in self.library or sid in self.custom:
                i += 1
                sid = f"{'A' if source == 'auto' else 'U'}_{base}{i}"
            near = self.nearest_library(site["lat"], site["lon"])
            rec = {"id": sid, "name": site["name"], "state": site.get("state") or (near or {}).get("state", ""),
                   "lat": float(site["lat"]), "lon": float(site["lon"]),
                   "region": (near or {}).get("region") or features.region_of(None, site["lat"], site["lon"]),
                   **{k: (near or {}).get(k, 1.0) for k in ("land_index", "construction_index", "labour_index", "utility_index")},
                   "hub_quality": (near or {}).get("hub_quality", 0.6), "flood_exposure": (near or {}).get("flood_exposure", 0.3),
                   "seismic_exposure": (near or {}).get("seismic_exposure", 0.3), "port": bool((near or {}).get("port")),
                   "source": source, "fixed_cost": site.get("fixed_cost"), "capacity": site.get("capacity"),
                   "types": site.get("types")}
            self.custom[sid] = rec
            return rec

    def remove(self, sid: str) -> None:
        with self._lock:
            self.custom.pop(sid, None)
            self.excluded.discard(sid)

    def exclude(self, sid: str, flag: bool = True) -> None:
        if sid not in self.library and sid not in self.custom:
            raise ExpansionError(f"Unknown candidate {sid!r}.")
        with self._lock:
            (self.excluded.add if flag else self.excluded.discard)(sid)

    def nearest_library(self, lat: float, lon: float) -> dict | None:
        return min(self.library.values(), key=lambda s: haversine_km((lat, lon), (s["lat"], s["lon"])), default=None)

    def reset(self) -> None:
        with self._lock:
            self.custom.clear()
            self.excluded.clear()


candidates = CandidateStore()


def auto_candidates(G: nx.DiGraph, n: int = 4, seed: int = 7) -> list[dict]:
    """Cluster underserved / high cost-to-serve demand (weight = demand x landed cost x lead) and snap each cluster
    centre to the nearest library city that is not already a site of the network."""
    from sklearn.cluster import KMeans

    dem = [c for c, d in G.nodes(data=True) if is_demand(d["kind"]) and (d.get("demand") or 0) > 0]
    if not dem:
        return []
    base = solve_flow(G)
    cost = _arrival_metric(G, base["flow"], "cost")
    lead = arrival_lead(G, base["flow"])
    w = np.array([(G.nodes[c]["demand"]) * (1 + (cost.get(c) or 0)) * (1 + (lead.get(c) or 0))
                  + (base["unmet"].get(c, 0.0) * 10) for c in dem])
    X = np.array([[G.nodes[c]["lat"], G.nodes[c]["lon"]] for c in dem])
    k = max(1, min(n, len(dem)))
    km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(X, sample_weight=w)
    taken = {(round(d["lat"], 1), round(d["lon"], 1)) for _, d in G.nodes(data=True)}
    out = []
    for lat, lon in km.cluster_centers_:
        lib = sorted(candidates.library.values(), key=lambda s: haversine_km((lat, lon), (s["lat"], s["lon"])))
        pick = next((s for s in lib if (round(s["lat"], 1), round(s["lon"], 1)) not in taken and s["id"] not in [o["near"] for o in out]), lib[0])
        out.append({"near": pick["id"], "rec": candidates.add({"name": f"{pick['name']} (auto)", "lat": pick["lat"], "lon": pick["lon"],
                                                              "state": pick["state"]}, source="auto")})
    return [o["rec"] for o in out]


# ---------------------------------------------------------------- economics
def unit_price(G) -> float:
    return float(G.graph.get("unit_price", 4200))


def margin_value(G) -> float:
    return unit_price(G) * float(G.graph.get("margin", DEFAULT_MARGIN))


def site_economics(G: nx.DiGraph, site: dict, kind: str) -> dict:
    tc = TYPE_COST[kind]
    cap = float(site.get("capacity") or max(10.0, math.ceil(tc["cap_share"] * total_demand(G))))
    build_idx = 0.45 * site["land_index"] + 0.55 * site["construction_index"]
    opex_idx = 0.6 * site["labour_index"] + 0.4 * site["utility_index"]
    capex = float(site.get("fixed_cost") or tc["capex_x"] * unit_price(G) * cap * build_idx)
    opex = capex * tc["opex_share"] * opex_idx / max(build_idx, 0.1)
    hazard = HAZARD_PREMIUM * capex * (site["flood_exposure"] + site["seismic_exposure"]) / 2
    handling = tc["handling"] * (1.0 - 0.5 * site["hub_quality"])
    return {"capacity": cap, "build_cost": capex, "annual_opex": opex, "hazard_premium": hazard, "handling_days": handling,
            "annual_fixed": capex * CRF + opex}


def _arrival_metric(G: nx.DiGraph, flow, attr: str) -> dict:
    """Flow-weighted per-unit sum of a lane attribute from suppliers to each node (like core.delay.arrival_lead)."""
    out: dict = {}
    try:
        order = list(nx.topological_sort(G))
    except nx.NetworkXUnfeasible:
        order = list(G)
    for n in order:
        if G.nodes[n]["kind"] == "supplier":
            out[n] = 0.0
            continue
        inb = [(u, flow.get((u, n), 0.0)) for u in G.predecessors(n)]
        inb = [(u, f) for u, f in inb if f > 0 and out.get(u) is not None]
        tot = sum(f for _, f in inb)
        out[n] = sum(f * (out[u] + G.edges[u, n][attr]) for u, f in inb) / tot if tot else None
    return out


def _scaled(G: nx.DiGraph, mult: float) -> nx.DiGraph:
    H = G.copy()
    for _, d in H.nodes(data=True):
        if is_demand(d["kind"]):
            d["demand"] = (d.get("demand") or 0.0) * mult
    return H


# ---------------------------------------------------------------- stage 1: Dijkstra
@dataclass
class TransportModel:
    points: list[str]  # node ids then candidate ids
    coords: np.ndarray
    port: list[bool]
    exposure: list[float]
    cost: dict  # (i, j) -> (generalized, freight, lead, co2, mode) for each link (both directions)
    dist: np.ndarray  # generalized Dijkstra distances from each candidate row
    pred: np.ndarray
    cand_rows: dict  # candidate id -> row in dist
    index: dict  # point id -> index

    def path(self, cid: str, target: str) -> list[int]:
        row, j = self.cand_rows[cid], self.index[target]
        if not np.isfinite(self.dist[row, j]):
            return []
        out, k = [j], j
        src = self.index[cid]
        while k != src:
            k = int(self.pred[row, k])
            if k < 0:
                return []
            out.append(k)
        return out[::-1]

    def path_metrics(self, cid: str, target: str) -> dict | None:
        p = self.path(cid, target)
        if not p:
            return None
        hops = [self.cost[(a, b)] for a, b in zip(p, p[1:])]
        return {"generalized": sum(h[0] for h in hops), "freight": sum(h[1] for h in hops), "lead": sum(h[2] for h in hops),
                "co2": sum(h[3] for h in hops), "km": sum(h[5] for h in hops),
                "hops": [{"from": self.points[a], "to": self.points[b], "mode": self.cost[(a, b)][4],
                          "km": _r(self.cost[(a, b)][5], 0), "lead_days": _r(self.cost[(a, b)][2], 1)} for a, b in zip(p, p[1:])]}


def _best_mode(km: float, ports: bool, price: float, co2_on: bool, penalty: float) -> tuple:
    best = None
    for mode in ("road", "rail", "air", "sea"):
        if (mode == "rail" and km < 300) or (mode == "air" and km < 500) or (mode == "sea" and (not ports or km < 300)):
            continue
        freight, lead, co2 = suggest_cost(mode, km), suggest_lead(mode, km), suggest_co2(mode, km)
        gen = freight + TIME_VALUE * price * lead + (W_CO2 * co2 if co2_on else 0.0) + penalty
        if best is None or gen < best[0]:
            best = (gen, freight, lead, co2, mode, km)
    return best


def _site_exposure(lat, lon) -> float:
    s = candidates.nearest_library(lat, lon)
    if s is None or haversine_km((lat, lon), (s["lat"], s["lon"])) > 80:
        return 0.3
    return s["flood_exposure"]


_TM_CACHE: dict[str, TransportModel] = {}


def transport_model(G: nx.DiGraph, sites: list[dict], co2: bool = False, weather: bool = False) -> TransportModel:
    """Stage 1 (cached per network fingerprint + candidate set + toggles)."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra

    key = hashlib.sha1(json.dumps([features.fingerprint(G), sorted((s["id"], s["lat"], s["lon"]) for s in sites), co2, weather]).encode()).hexdigest()
    if key in _TM_CACHE:
        return _TM_CACHE[key]
    price = unit_price(G)
    nodes = [n for n in G]
    points = nodes + [s["id"] for s in sites]
    coords = np.array([[G.nodes[n]["lat"], G.nodes[n]["lon"]] for n in nodes] + [[s["lat"], s["lon"]] for s in sites], dtype=float).reshape(-1, 2)
    port = [False] * len(nodes) + [bool(s.get("port")) for s in sites]
    # an existing node counts as a port if it says so or a library port city is within 30 km
    for i, n in enumerate(nodes):
        lib = candidates.nearest_library(G.nodes[n]["lat"], G.nodes[n]["lon"])
        port[i] = bool(G.nodes[n].get("port")) or bool(lib and lib.get("port") and haversine_km(tuple(coords[i]), (lib["lat"], lib["lon"])) < 30)
    exposure = [_site_exposure(*coords[i]) for i in range(len(nodes))] + [s["flood_exposure"] for s in sites]
    index = {p: i for i, p in enumerate(points)}
    n = len(points)
    km = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            km[i, j] = km[j, i] = haversine_km(tuple(coords[i]), tuple(coords[j]))
    links: dict = {}

    def link(i, j, data):
        if (i, j) not in links or data[0] < links[(i, j)][0]:
            links[(i, j)] = data
            links[(j, i)] = data

    for i in range(n):
        for j in np.argsort(km[i])[1:K_NEAREST + 1]:
            pen = WEATHER_RISK_INR * (exposure[i] + exposure[int(j)]) / 2 if weather else 0.0
            link(i, int(j), _best_mode(max(km[i, j], 1.0), port[i] and port[int(j)], price, co2, pen))
    for u, v, d in G.edges(data=True):  # the network's own lanes, at their real cost / lead
        i, j = index[u], index[v]
        pen = WEATHER_RISK_INR * (exposure[i] + exposure[j]) / 2 if weather else 0.0
        gen = d["cost"] + TIME_VALUE * price * d["lead"] + (W_CO2 * (d.get("co2") or 0) if co2 else 0.0) + pen
        link(i, j, (gen, d["cost"], d["lead"], d.get("co2") or 0.0, d.get("mode") or "road", km[i, j]))
    rows, cols, vals = zip(*[(i, j, max(v[0], 1e-6)) for (i, j), v in links.items()]) if links else ((), (), ())
    M = csr_matrix((vals, (rows, cols)), shape=(n, n))
    cand_idx = [index[s["id"]] for s in sites]
    if cand_idx:
        dist, pred = dijkstra(M, directed=True, indices=cand_idx, return_predecessors=True)
    else:
        dist, pred = np.zeros((0, n)), np.zeros((0, n), dtype=int)
    tm = TransportModel(points, coords, port, exposure, links, dist, pred, {s["id"]: r for r, s in enumerate(sites)}, index)
    if len(_TM_CACHE) > 8:
        _TM_CACHE.clear()
    _TM_CACHE[key] = tm
    return tm


# ---------------------------------------------------------------- stage 2: options + MILP + greedy
@dataclass
class Problem:
    G: nx.DiGraph
    params: dict
    demand: dict  # d -> planning demand (units/day)
    existing: dict  # d -> units/day the current network can serve at the planning demand
    c0: dict  # d -> current landed freight per unit
    l0: dict  # d -> current lead (days)
    n0: dict  # d -> existing source count
    options: list  # [{key, site, kind, econ, inbound, arcs: {d: {...}}}]
    goal: str
    headroom: dict  # option index -> extra units/day the network can deliver to its inbound sources


def build_problem(G: nx.DiGraph, sites: list[dict], tm: TransportModel, params: dict, goal: str, demand_mult: float = 1.0) -> Problem:
    growth = (1 + params["growth"]) * demand_mult
    H = _scaled(G, growth)
    base = solve_flow(H)
    dem = {c: H.nodes[c]["demand"] for c in H if is_demand(H.nodes[c]["kind"]) and (H.nodes[c].get("demand") or 0) > 0}
    existing = {c: base["served"].get(c, 0.0) for c in dem}
    cost = _arrival_metric(H, base["flow"], "cost")
    lead = arrival_lead(H, base["flow"])
    c0 = {c: float(cost.get(c) or 0.0) for c in dem}
    l0 = {c: float(lead.get(c) or 0.0) for c in dem}
    n0 = {c: sum(1 for p in G.predecessors(c) if not G.nodes[p].get("backup")) for c in dem}
    holding = float(G.graph.get("holding_cost", HOLDING_PER_DAY))
    options = []
    for s in sites:
        for kind in params["types"]:
            if s.get("types") and kind not in s["types"]:
                continue
            ups = [n for n, d in G.nodes(data=True) if d["kind"] == ("factory" if kind == "warehouse" else "supplier") and not d.get("backup")]
            if kind == "warehouse" and not ups:
                ups = [n for n, d in G.nodes(data=True) if d["kind"] == "supplier" and not d.get("backup")]
            inb = sorted(((u, tm.path_metrics(s["id"], u)) for u in ups), key=lambda t: t[1]["generalized"] if t[1] else 1e18)
            inb = [(u, m) for u, m in inb if m][:2]
            if not inb:
                continue
            econ = site_economics(G, s, kind)
            arcs = {}
            for d in dem:
                m = tm.path_metrics(s["id"], d)
                if not m:
                    continue
                lead_od = inb[0][1]["lead"] + econ["handling_days"] + m["lead"]
                if lead_od > params["max_lead_days"]:
                    continue
                arcs[d] = {"freight": inb[0][1]["freight"] + m["freight"], "lead": lead_od, "co2": inb[0][1]["co2"] + m["co2"],
                           "generalized": inb[0][1]["generalized"] + m["generalized"]}
            keep = sorted(arcs, key=lambda d: arcs[d]["generalized"])[:TOP_DEMAND]
            options.append({"key": f"{s['id']}:{kind}", "site": s, "kind": kind, "econ": econ, "inbound": inb,
                            "arcs": {d: arcs[d] for d in keep}, "holding": SAFETY_DAYS * holding})
    served_total = sum(base["served"].values())
    cache: dict = {}
    headroom = {}
    for i, o in enumerate(options):
        key = tuple(sorted(u for u, _ in o["inbound"]))
        if key not in cache:
            cache[key] = _headroom(H, served_total, list(key), o["econ"]["capacity"])
        headroom[i] = min(cache[key], o["econ"]["capacity"])
    return Problem(G, params, dem, existing, c0, l0, n0, options, goal, headroom)


def _headroom(H: nx.DiGraph, served_total: float, sources: list[str], cap: float) -> float:
    """Extra units/day the existing network can push into `sources` (exact flow engine with a probe sink)."""
    K = H.copy()
    K.add_node("__PROBE__", kind="customer", demand=float(cap), capacity=0.0, stock=0.0, lat=0.0, lon=0.0)
    for u in sources:
        K.add_edge(u, "__PROBE__", capacity=float(cap) * 10, lead=1.0, cost=0.0, co2=0.0)
    res = solve_flow(K)
    return max(0.0, sum(res["served"].values()) - served_total)


def _weights(P: Problem) -> dict:
    w = GOAL_WEIGHTS[P.goal]
    price, mv = unit_price(P.G), margin_value(P.G)
    pen = {"margin": mv, "price": price, "mid": (mv + price) / 2}[w["unmet"]]
    lam = W_CO2 if P.params["co2"] else 0.0
    return {"lead": w["lead"] * price, "unmet": pen, "reward": w["reward"] * price, "hazard": w["hazard"], "co2": lam}


def _fixed(o: dict, W: dict, weather: bool) -> float:
    return o["econ"]["annual_fixed"] + (o["econ"]["hazard_premium"] * W["hazard"] if weather else o["econ"]["hazard_premium"])


def _arc_cost(a: dict, o: dict, W: dict) -> float:
    return a["freight"] + o["holding"] + W["lead"] * a["lead"] + W["co2"] * a["co2"]


def precheck(P: Problem) -> str | None:
    """Plain-English reason the model cannot be solved, or None."""
    n = P.params["n_add"]
    if not P.demand:
        return "The network has no demand to serve."
    if not P.options:
        return "No candidate site is eligible: every site is excluded, has no supply route, or none of the chosen facility types fits."
    reach = [o for o in P.options if o["arcs"]]
    sites_reach = {o["site"]["id"] for o in reach}
    if len(sites_reach) < n:
        return (f"Only {len(sites_reach)} candidate site(s) can reach a demand node within {P.params['max_lead_days']:g} days; "
                f"raise the max lead time or add fewer than {n} site(s).")
    cap = sum(min(P.params["max_per_type"].get(k, n), n) for k in P.params["types"])
    if cap < n:
        return f"The max-sites-per-type limits allow only {cap} new site(s), fewer than the {n} requested."
    budget = P.params.get("budget")
    if budget is not None:
        cheapest = sorted({o["site"]["id"]: min(x["econ"]["build_cost"] for x in reach if x["site"]["id"] == o["site"]["id"]) for o in reach}.values())[:n]
        if sum(cheapest) > budget:
            return (f"The budget of {inr(budget)} is below the cheapest combination of {n} site(s), which costs {inr(sum(cheapest))} "
                    f"to build. Raise the budget or add fewer sites.")
    if P.params.get("redundancy"):
        short = [d for d in P.demand if P.n0[d] + len({o['site']['id'] for o in reach if d in o['arcs']}) < 2]
        if short:
            return (f"Redundancy cannot be met: {', '.join(short[:6])} cannot get a second source within "
                    f"{P.params['max_lead_days']:g} days from any candidate.")
    return None


def solve_milp(P: Problem, time_limit: int = TIME_LIMIT) -> dict:
    import pulp

    why = precheck(P)
    if why:
        return {"status": "infeasible", "explanation": why, "open": [], "objective": None}
    W = _weights(P)
    weather = P.params["weather"]
    prob = pulp.LpProblem("expansion", pulp.LpMinimize)
    O = list(range(len(P.options)))
    y = {o: pulp.LpVariable(f"y_{o}", cat="Binary") for o in O}
    x = {(o, d): pulp.LpVariable(f"x_{o}_{i}", 0) for o in O for i, d in enumerate(P.demand) if d in P.options[o]["arcs"]}
    e = {d: pulp.LpVariable(f"e_{i}", 0, P.existing[d]) for i, d in enumerate(P.demand)}
    u = {d: pulp.LpVariable(f"u_{i}", 0) for i, d in enumerate(P.demand)}
    need_z = P.params.get("redundancy") or W["reward"] > 0
    z = {k: pulp.LpVariable(f"z_{k[0]}_{i}", cat="Binary") for i, k in enumerate(x)} if need_z else {}
    di = {d: i for i, d in enumerate(P.demand)}
    for d in P.demand:
        prob += e[d] + pulp.lpSum(x[o, d] for o in O if (o, d) in x) + u[d] == P.demand[d], f"dem_{di[d]}"
    for o in O:
        prob += pulp.lpSum(x[o, d] for d in P.demand if (o, d) in x) <= P.options[o]["econ"]["capacity"] * y[o], f"cap_{o}"
    by_site: dict = {}
    for o in O:
        by_site.setdefault(P.options[o]["site"]["id"], []).append(o)
    for k, os_ in enumerate(by_site.values()):
        prob += pulp.lpSum(y[o] for o in os_) <= 1, f"one_{k}"
    prob += pulp.lpSum(y.values()) == P.params["n_add"], "count"
    for kind in P.params["types"]:
        prob += pulp.lpSum(y[o] for o in O if P.options[o]["kind"] == kind) <= P.params["max_per_type"].get(kind, P.params["n_add"]), f"max_{kind}"
    if P.params.get("budget") is not None:
        prob += pulp.lpSum(P.options[o]["econ"]["build_cost"] * y[o] for o in O) <= P.params["budget"], "budget"
    prob += (pulp.lpSum(x.values()) + pulp.lpSum(e.values()) - sum(P.existing.values())
             <= pulp.lpSum(P.headroom[o] * y[o] for o in O)), "upstream_headroom"
    reward = 0
    if need_z:
        for (o, d), v in z.items():
            prob += x[o, d] <= P.demand[d] * v
            prob += v <= y[o]
        if P.params.get("redundancy"):
            for d in P.demand:
                prob += P.n0[d] + pulp.lpSum(z[o, dd] for (o, dd) in z if dd == d) >= 2, f"red_{di[d]}"
        if W["reward"] > 0:
            wv = {d: pulp.LpVariable(f"w_{di[d]}", 0, 1) for d in P.demand if P.n0[d] < 2}
            for d, v in wv.items():
                prob += v <= pulp.lpSum(z[o, dd] for (o, dd) in z if dd == d)
            reward = 365 * W["reward"] * pulp.lpSum(P.demand[d] * v for d, v in wv.items())
    prob += (pulp.lpSum(_fixed(P.options[o], W, weather) * y[o] for o in O)
             + 365 * (pulp.lpSum(_arc_cost(P.options[o]["arcs"][d], P.options[o], W) * x[o, d] for (o, d) in x)
                      + pulp.lpSum((P.c0[d] + W["lead"] * P.l0[d]) * e[d] for d in P.demand) + W["unmet"] * pulp.lpSum(u.values()))
             - reward)
    t = time.perf_counter()
    prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit))
    secs = time.perf_counter() - t
    st = pulp.LpStatus[prob.status]
    if st == "Infeasible" or prob.sol_status == pulp.LpSolutionInfeasible:
        return {"status": "infeasible", "explanation": "The constraints cannot all be met (budget, site counts, lead-time radius "
                "and capacity together). Relax the budget or the max lead time.", "open": [], "objective": None}
    if prob.sol_status not in (pulp.LpSolutionOptimal, pulp.LpSolutionIntegerFeasible):
        return {"status": "error", "explanation": f"The solver stopped without a solution ({st}).", "open": [], "objective": None}
    val = lambda v: float(pulp.value(v) or 0.0)  # noqa: E731
    opened = [o for o in O if val(y[o]) > 0.5]
    return {"status": "optimal" if prob.sol_status == pulp.LpSolutionOptimal else "best found", "open": opened,
            "objective": val(prob.objective), "seconds": _r(secs, 2),
            "flows": {(o, d): val(v) for (o, d), v in x.items() if val(v) > 1e-6},
            "unmet": sum(val(v) for v in u.values())}


def fixed_set_objective(P: Problem, opened: list[int]) -> float:
    """Annual objective with a fixed set of open options (an LP; same objective as the MILP except the resilience
    reward, which needs binaries)."""
    from scipy.optimize import linprog

    W = _weights(P)
    D = list(P.demand)
    arcs = [(o, d) for o in opened for d in P.options[o]["arcs"]]
    nx_, nd = len(arcs), len(D)
    c = [365 * _arc_cost(P.options[o]["arcs"][d], P.options[o], W) for o, d in arcs]
    c += [365 * (P.c0[d] + W["lead"] * P.l0[d]) for d in D] + [365 * W["unmet"]] * nd
    a_eq, b_eq = [], []
    for k, d in enumerate(D):
        row = [0.0] * (nx_ + 2 * nd)
        for i, (o, dd) in enumerate(arcs):
            if dd == d:
                row[i] = 1
        row[nx_ + k] = 1
        row[nx_ + nd + k] = 1
        a_eq.append(row)
        b_eq.append(P.demand[d])
    a_ub, b_ub = [], []
    for o in opened:
        a_ub.append([1.0 if oo == o else 0.0 for oo, _ in arcs] + [0.0] * (2 * nd))
        b_ub.append(P.options[o]["econ"]["capacity"])
    a_ub.append([1.0] * nx_ + [1.0] * nd + [0.0] * nd)  # upstream headroom of the open options
    b_ub.append(sum(P.existing.values()) + sum(P.headroom[o] for o in opened))
    bounds = [(0, None)] * nx_ + [(0, P.existing[d]) for d in D] + [(0, None)] * nd
    res = linprog(c, A_ub=a_ub or None, b_ub=b_ub or None, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    fixed = sum(_fixed(P.options[o], W, P.params["weather"]) for o in opened)
    return float(res.fun) + fixed if res.status == 0 else float("inf")


def greedy(P: Problem) -> dict:
    """Marginal-gain heuristic: add the option that lowers the objective most, n_add times (respecting budget, one type
    per site and max per type)."""
    why = precheck(P)
    if why:
        return {"status": "infeasible", "explanation": why, "open": [], "objective": None}
    opened: list[int] = []
    spent = 0.0
    for _ in range(P.params["n_add"]):
        best = None
        for o, opt in enumerate(P.options):
            if o in opened or any(P.options[q]["site"]["id"] == opt["site"]["id"] for q in opened):
                continue
            if sum(1 for q in opened if P.options[q]["kind"] == opt["kind"]) >= P.params["max_per_type"].get(opt["kind"], P.params["n_add"]):
                continue
            if P.params.get("budget") is not None and spent + opt["econ"]["build_cost"] > P.params["budget"]:
                continue
            val = fixed_set_objective(P, opened + [o])
            if best is None or val < best[0]:
                best = (val, o)
        if best is None:
            return {"status": "infeasible", "explanation": "The greedy heuristic could not add another site within the budget and "
                    "type limits.", "open": opened, "objective": None}
        opened.append(best[1])
        spent += P.options[best[1]]["econ"]["build_cost"]
    return {"status": "heuristic", "open": opened, "objective": fixed_set_objective(P, opened)}


def marginal_values(P: Problem, cancel: Callable[[], None] | None = None) -> list[dict]:
    """Annual objective improvement from opening each option alone (positive = it pays for itself)."""
    base = fixed_set_objective(P, [])
    out = []
    for o, opt in enumerate(P.options):
        if cancel:
            cancel()
        if not opt["arcs"]:
            continue
        v = fixed_set_objective(P, [o])
        out.append({"site": opt["site"]["id"], "name": opt["site"]["name"], "kind": opt["kind"],
                    "annual_value_inr": _r(base - v, 0), "annual_value_display": inr(base - v),
                    "build_cost_inr": _r(opt["econ"]["build_cost"], 0), "build_cost_display": inr(opt["econ"]["build_cost"]),
                    "reachable_demand_nodes": len(opt["arcs"]), "upstream_headroom_units_per_day": _r(P.headroom[o], 1)})
    return sorted(out, key=lambda r: -r["annual_value_inr"])


# ---------------------------------------------------------------- stage 3: apply to a copy + evaluate
def plan_additions(P: Problem, tm: TransportModel, opened: list[int], flows: dict | None, prefix: str = "X") -> dict:
    """New nodes and lanes for a plan (engine attributes); flows from the MILP or, if None, a fixed-set allocation."""
    G = P.G
    taken = set(G)
    nodes, edges = [], []
    assigned: dict[int, dict] = {o: {} for o in opened}
    for (o, d), f in (flows or {}).items():
        if o in assigned:
            assigned[o][d] = f
    for k, o in enumerate(opened, start=1):
        opt = P.options[o]
        s, kind, econ = opt["site"], opt["kind"], opt["econ"]
        nid = f"{prefix}{k}"
        while nid in taken:
            nid += "x"
        taken.add(nid)
        flows_o = assigned[o] or {d: 0.0 for d in list(opt["arcs"])[:3]}
        thr = sum(flows_o.values())
        nodes.append({"id": nid, "kind": kind, "name": f"{s['name']} {kind}", "city": s["name"], "lat": s["lat"], "lon": s["lon"],
                      "capacity": econ["capacity"], "stock": round(SAFETY_DAYS * thr) if kind == "warehouse" else 0.0,
                      "demand": 0.0, "reliability": 0.95, "backup": False, "candidate": s["id"]})
        per_in = max(1.0, (thr or econ["capacity"]) / len(opt["inbound"])) * 1.3

        def named(hops, inbound=False):
            """Dijkstra paths run from the candidate; show them in shipping direction with the new node's id."""
            hs = [{**h, "from": h["to"], "to": h["from"]} for h in reversed(hops)] if inbound else [dict(h) for h in hops]
            for h in hs:
                h["from"] = nid if h["from"] == s["id"] else h["from"]
                h["to"] = nid if h["to"] == s["id"] else h["to"]
            return hs
        for u, m in opt["inbound"]:
            edges.append({"source": u, "target": nid, "capacity": float(math.ceil(per_in)), "lead": _r(max(0.5, m["lead"]), 1),
                          "cost": _r(m["freight"], 1), "co2": _r(m["co2"], 2), "mode": m["hops"][0]["mode"] if m["hops"] else "road",
                          "distance_km": _r(m["km"], 1), "path": named(m["hops"], inbound=True)})
        for d, f in flows_o.items():
            m = tm.path_metrics(s["id"], d)
            if not m:
                continue
            edges.append({"source": nid, "target": d, "capacity": float(math.ceil(max(f, econ["capacity"] * 0.25) * 1.3)),
                          "lead": _r(max(0.5, m["lead"] + econ["handling_days"]), 1), "cost": _r(m["freight"], 1),
                          "co2": _r(m["co2"], 2), "mode": m["hops"][0]["mode"] if m["hops"] else "road", "distance_km": _r(m["km"], 1),
                          "path": named(m["hops"])})
    return {"nodes": nodes, "edges": edges}


def plan_graph(G: nx.DiGraph, additions: dict) -> nx.DiGraph:
    """A COPY of G with the plan's nodes and lanes (the original graph is never modified)."""
    H = G.copy()
    for n in additions["nodes"]:
        H.add_node(n["id"], **{k: v for k, v in n.items() if k not in ("id", "candidate")})
    for e in additions["edges"]:
        H.add_edge(e["source"], e["target"], **{k: v for k, v in e.items() if k in ("capacity", "lead", "cost", "co2", "mode", "distance_km")})
    return H


def operations(G: nx.DiGraph, mult: float) -> dict:
    """Engine metrics at demand x mult: service level, lead, freight, CO2, lost margin (per day)."""
    H = _scaled(G, mult)
    res = solve_flow(H)
    dem = {c: H.nodes[c]["demand"] for c in H if is_demand(H.nodes[c]["kind"]) and (H.nodes[c].get("demand") or 0) > 0}
    total = sum(dem.values()) or 1.0
    served = sum(res["served"].get(c, 0.0) for c in dem)
    lead = arrival_lead(H, res["flow"])
    lw = [(dem[c], lead[c]) for c in dem if lead.get(c) is not None and res["served"].get(c, 0) > 0]
    co2 = sum(f * (H.edges[e].get("co2") or 0.0) for e, f in res["flow"].items())
    unmet = total - served
    return {"service_level": served / total, "avg_lead_days": sum(q * l for q, l in lw) / sum(q for q, _ in lw) if lw else 0.0,
            "freight_per_day": res["cost"], "co2_kg_per_day": co2, "unmet_per_day": unmet,
            "lost_margin_per_day": unmet * margin_value(G), "lead_by_node": {c: lead.get(c) for c in dem},
            "flow": res["flow"], "demand": dem}


def evaluate_plan(G: nx.DiGraph, P: Problem, tm: TransportModel, solution: dict, goal: str) -> dict:
    """Stage 3: apply the plan to a copy, re-run the engine, Chaos Finder and the Health Score."""
    from core.bottleneck import health

    growth = 1 + P.params["growth"]
    adds = plan_additions(P, tm, solution["open"], solution.get("flows"))
    H = plan_graph(G, adds)
    before, after = operations(G, growth), operations(H, growth)
    new_ids = [n["id"] for n in adds["nodes"]]
    holding_new = sum(n["stock"] for n in adds["nodes"]) * float(G.graph.get("holding_cost", HOLDING_PER_DAY))
    build = sum(P.options[o]["econ"]["build_cost"] for o in solution["open"])
    opex = sum(P.options[o]["econ"]["annual_opex"] + P.options[o]["econ"]["hazard_premium"] for o in solution["open"])
    op_before = before["freight_per_day"] + before["lost_margin_per_day"]
    op_after = after["freight_per_day"] + after["lost_margin_per_day"] + holding_new
    savings = 365 * (op_before - op_after) - opex
    total_change = build * CRF - savings
    chaos_b, chaos_a = chaos.chaos_find(G), chaos.chaos_find(H)
    spof_b = {s["target"]: s["unmet"] for s in chaos_b["spof"]}
    spof_a = {s["target"]: s["unmet"] for s in chaos_a["spof"]}
    removed = [t for t, v in spof_b.items() if spof_a.get(t, 0.0) < 0.5 * v]
    hb, ha = health(G), health(H)
    sites = []
    for nd in adds["nodes"]:
        out = {e[1]: f for e, f in after["flow"].items() if e[0] == nd["id"] and f > 0}
        served = sum(out.values())
        dn = [d for d in out if d in after["demand"]]
        regions = [features.region_of(G.nodes[d].get("city"), G.nodes[d]["lat"], G.nodes[d]["lon"]) for d in dn]
        region = max(set(regions), key=regions.count) if regions else ""
        lb = [before["lead_by_node"].get(d) for d in dn if before["lead_by_node"].get(d) is not None]
        la = [after["lead_by_node"].get(d) for d in dn if after["lead_by_node"].get(d) is not None]
        share = served / (sum(after["demand"].values()) or 1.0)
        lead_b, lead_a = (float(np.mean(lb)) if lb else None), (float(np.mean(la)) if la else None)
        if lead_b is not None and lead_a is not None and lead_a < lead_b - 0.05:
            why = (f"{nd['name']} cuts average lead time to the {len(dn)} {region} demand node(s) from {lead_b:.1f} to "
                   f"{lead_a:.1f} days and serves {100 * share:.0f}% of demand.")
        elif served > 0:
            why = f"{nd['name']} adds {served:,.0f} units/day of capacity near {len(dn)} {region} demand node(s), serving {100 * share:.0f}% of demand."
        else:
            why = f"{nd['name']} carries no flow at the planning demand: it is held in reserve (it still adds an alternate source)."
        opt = next(P.options[o] for o in solution["open"] if P.options[o]["site"]["id"] == nd["candidate"] and P.options[o]["kind"] == nd["kind"])
        biggest = max(out, key=out.get) if out else None
        paths = [{"lane": f"{e['source']}->{e['target']}", "hops": e["path"]} for e in adds["edges"]
                 if e["target"] == nd["id"]][:1]
        if biggest:
            paths += [{"lane": f"{nd['id']}->{biggest}", "hops": next(e["path"] for e in adds["edges"] if e["source"] == nd["id"] and e["target"] == biggest)}]
        sites.append({"node_id": nd["id"], "candidate": nd["candidate"], "name": opt["site"]["name"], "kind": nd["kind"],
                      "lat": nd["lat"], "lon": nd["lon"], "region": opt["site"]["region"], "capacity": _r(opt["econ"]["capacity"], 0),
                      "build_cost": _r(opt["econ"]["build_cost"], 0), "build_cost_display": inr(opt["econ"]["build_cost"]),
                      "annual_opex": _r(opt["econ"]["annual_opex"], 0), "served_units_per_day": _r(served, 1),
                      "share_of_demand_pct": _r(100 * share, 1), "demand_nodes": dn,
                      "lead_before_days": _r(lead_b, 2) if lead_b is not None else None,
                      "lead_after_days": _r(lead_a, 2) if lead_a is not None else None,
                      "flood_exposure": opt["site"]["flood_exposure"], "seismic_exposure": opt["site"]["seismic_exposure"],
                      "hub_quality": opt["site"]["hub_quality"], "rationale": why, "example_paths": paths})
    sens = []
    for label, m in (("Demand -20%", 0.8), ("Demand +20%", 1.2)):
        b2, a2 = operations(G, growth * m), operations(H, growth * m)
        s2 = 365 * ((b2["freight_per_day"] + b2["lost_margin_per_day"]) - (a2["freight_per_day"] + a2["lost_margin_per_day"] + holding_new)) - opex
        sens.append({"variant": label, "annual_savings_inr": _r(s2, 0), "annual_savings_display": inr(s2),
                     "payback_years": _r(build / s2, 1) if s2 > 0 else None,
                     "service_level_pct": _r(100 * a2["service_level"], 2), "service_level_before_pct": _r(100 * b2["service_level"], 2)})
    return {
        "goal": goal, "label": GOAL_WEIGHTS[goal]["label"], "status": solution["status"], "solver_seconds": solution.get("seconds"),
        "objective_inr": _r(solution["objective"], 0) if solution.get("objective") is not None else None,
        "sites": sites, "additions": {"nodes": adds["nodes"], "edges": [{k: v for k, v in e.items() if k != "path"} for e in adds["edges"]]},
        "new_node_ids": new_ids,
        "build_cost_inr": _r(build, 0), "build_cost_display": inr(build),
        "annual_savings_inr": _r(savings, 0), "annual_savings_display": inr(savings),
        "payback_years": _r(build / savings, 1) if savings > 0 else None,
        "total_cost_change_inr": _r(total_change, 0), "total_cost_change_display": inr(total_change),
        "service_level_before_pct": _r(100 * before["service_level"], 2), "service_level_after_pct": _r(100 * after["service_level"], 2),
        "avg_lead_before_days": _r(before["avg_lead_days"], 2), "avg_lead_after_days": _r(after["avg_lead_days"], 2),
        "co2_before_t_per_year": _r(before["co2_kg_per_day"] * 365 / 1000, 1), "co2_after_t_per_year": _r(after["co2_kg_per_day"] * 365 / 1000, 1),
        "resilience_before": chaos_b["resilience_score"], "resilience_after": chaos_a["resilience_score"],
        "health_before": hb["score"], "health_after": ha["score"],
        "spof_removed": removed, "spof_before": list(spof_b), "spof_after": list(spof_a),
        "worst_case_unmet_before": max(spof_b.values(), default=0.0), "worst_case_unmet_after": max(spof_a.values(), default=0.0),
        "sensitivity": sens,
    }


# ---------------------------------------------------------------- orchestration
DEFAULTS = {"goal": "balanced", "types": ["warehouse", "factory"], "n_add": 1, "budget": None, "max_lead_days": DEFAULT_MAX_LEAD,
            "weather": False, "co2": False, "growth": DEFAULT_GROWTH, "redundancy": False, "max_per_type": {}, "candidate_ids": None}


def normalize(params: dict | None) -> dict:
    p = {**DEFAULTS, **{k: v for k, v in (params or {}).items() if v is not None}}
    if p["goal"] not in GOAL_WEIGHTS:
        raise ExpansionError(f"goal must be one of {list(GOAL_WEIGHTS)}")
    p["types"] = [t for t in p["types"] if t in TYPES] or ["warehouse"]
    p["n_add"] = int(np.clip(int(p["n_add"]), 1, 5))
    p["max_per_type"] = {k: int(v) for k, v in (p["max_per_type"] or {}).items()}
    return p


def _balanced_rank(plans: list[dict]) -> list[dict]:
    """Order plans for the 'Balanced' goal: mean rank on total cost change, service level and resilience."""
    def ranks(key, reverse):
        order = sorted(plans, key=lambda p: (p[key] if p[key] is not None else 0), reverse=reverse)
        return {id(p): i for i, p in enumerate(order)}
    rc, rs, rr = ranks("total_cost_change_inr", False), ranks("service_level_after_pct", True), ranks("resilience_after", True)
    return sorted(plans, key=lambda p: rc[id(p)] + rs[id(p)] + rr[id(p)])


def build_sections(result: dict) -> list[dict]:
    plans = result["plans"]
    top = plans[0] if plans else None
    head = (f"{top['label']} plan: open {', '.join(s['name'] + ' ' + s['kind'] for s in top['sites'])} for {top['build_cost_display']}; "
            f"service level {top['service_level_before_pct']:.1f}% -> {top['service_level_after_pct']:.1f}% and average lead time "
            f"{top['avg_lead_before_days']:.1f} -> {top['avg_lead_after_days']:.1f} days at the planning demand (simulated)."
            if top and top["sites"] else result.get("explanation") or "No plan.")
    out = [{"key": "summary", "title": "Recommendation", "paragraphs": [head], "bullets": [], "evidence": {"plans": plans}}]
    for p in plans:
        bullets = [s["rationale"] for s in p["sites"]]
        pay = f"payback {p['payback_years']:.1f} years" if p["payback_years"] else "no payback within the model (savings do not cover running costs)"
        bullets.append(f"Build cost {p['build_cost_display']}, annual savings {p['annual_savings_display']}, {pay} (simulated).")
        bullets.append(f"Resilience {p['resilience_before']:.1f} -> {p['resilience_after']:.1f}; Health Score {p['health_before']:.1f} -> "
                       f"{p['health_after']:.1f}; {len(p['spof_removed'])} single point(s) of failure removed.")
        out.append({"key": p["id"], "title": p["label"], "paragraphs": [], "bullets": bullets, "evidence": {"plan": p}})
    return out


def run_expansion(G: nx.DiGraph, params: dict | None = None, progress: Callable[[str, int, int], None] | None = None,
                  cancelled: Callable[[], bool] | None = None, narrator: Callable | None = None) -> dict:
    """The full planner (stages 1-3) for three goals. Never modifies G."""
    t0 = time.perf_counter()
    p = normalize(params)
    steps = 8

    def step(label: str, i: int) -> None:
        if cancelled and cancelled():
            raise Cancelled()
        if progress:
            progress(label, i, steps)

    if G.number_of_nodes() == 0 or total_demand(G) <= 0 or not any(d.get("kind") == "supplier" for _, d in G.nodes(data=True)):
        return {"status": "empty", "explanation": "The network needs at least one supplier and some demand.", "plans": [], "params": p}
    sites = candidates.active(p["candidate_ids"])
    step("Building the transport graph and running Dijkstra", 0)
    tm = transport_model(G, sites, p["co2"], p["weather"])
    plans, solutions, problems = [], {}, {}
    explanation = None
    for i, goal in enumerate(PLAN_GOALS, start=1):
        step(f"Location MILP: {GOAL_WEIGHTS[goal]['label'].lower()}", i)
        P = build_problem(G, sites, tm, p, goal)
        sol = solve_milp(P)
        if sol["status"] in ("infeasible", "error"):
            explanation = sol["explanation"]
            alt = greedy(P) if sol["status"] == "error" else None
            if not alt or alt["status"] == "infeasible":
                continue
            sol = alt
        problems[goal], solutions[goal] = P, sol
    if not solutions:
        return {"status": "infeasible", "explanation": explanation or "No feasible plan.", "plans": [], "params": p,
                "elapsed_s": _r(time.perf_counter() - t0, 2)}
    goal0 = p["goal"] if p["goal"] in solutions else next(iter(solutions))
    P0 = problems.get(goal0) or build_problem(G, sites, tm, p, goal0)
    step("Greedy cross-check", 4)
    gr = greedy(P0)
    milp_obj = fixed_set_objective(P0, solutions[goal0]["open"]) if goal0 in solutions else None
    cross = {"goal": goal0, "milp_sites": [P0.options[o]["key"] for o in solutions[goal0]["open"]],
             "greedy_sites": [P0.options[o]["key"] for o in gr["open"]],
             "milp_objective_inr": _r(milp_obj, 0) if milp_obj is not None else None,
             "greedy_objective_inr": _r(gr["objective"], 0) if gr.get("objective") is not None else None}
    if cross["milp_objective_inr"] and cross["greedy_objective_inr"]:
        cross["greedy_gap_pct"] = _r(100 * (gr["objective"] - milp_obj) / abs(milp_obj), 2)
        cross["same_sites"] = sorted(cross["milp_sites"]) == sorted(cross["greedy_sites"])
    step("Marginal value of every candidate", 5)
    def check():
        if cancelled and cancelled():
            raise Cancelled()
    mv = marginal_values(P0, cancel=check)
    step("Resilience evaluation on copies of the network", 6)
    seen = {}
    for goal, sol in solutions.items():
        key = tuple(sorted(problems[goal].options[o]["key"] for o in sol["open"]))
        plan = evaluate_plan(G, problems[goal], tm, sol, goal)
        plan["same_as"] = seen.get(key)
        seen.setdefault(key, goal)
        plans.append(plan)
    step("Sensitivity: does the recommendation hold at demand +-20%?", 7)
    stable = []
    for label, m in (("Demand -20%", 0.8), ("Demand +20%", 1.2)):
        Pm = build_problem(G, sites, tm, p, goal0, demand_mult=m)
        s = solve_milp(Pm, time_limit=max(3, TIME_LIMIT // 2))
        stable.append({"variant": label, "sites": sorted(Pm.options[o]["key"] for o in s["open"]), "status": s["status"],
                       "same_as_recommended": sorted(Pm.options[o]["key"] for o in s["open"]) == sorted(cross["milp_sites"])})
    plans = _balanced_rank(plans) if p["goal"] == "balanced" else sorted(plans, key=lambda q: q["goal"] != p["goal"])
    rid = uuid.uuid4().hex[:8]
    for q in plans:
        q["id"] = f"{rid}-{q['goal']}"
    result = {"status": "ok", "id": rid, "params": p, "plans": plans, "cross_check": cross, "marginal_values": mv,
              "recommendation_stability": stable, "label": "simulated",
              "baseline": {k: v for k, v in operations(G, 1 + p["growth"]).items() if k not in ("flow", "lead_by_node", "demand")},
              "candidates_considered": len(sites), "options_considered": len(P0.options),
              "transport_graph": {"points": len(tm.points), "links": len(tm.cost) // 2, "k_nearest": K_NEAREST},
              "assumptions": [
                  f"Planning demand = today's demand x {1 + p['growth']:.2f} (growth {100 * p['growth']:.0f}%).",
                  "Site costs use illustrative indices (data/candidate_sites.json): replace them with client data.",
                  f"Capex = {TYPE_COST['warehouse']['capex_x']:g} x unit price per unit/day of warehouse capacity "
                  f"({TYPE_COST['factory']['capex_x']:g} x for factories) x land/construction index; annualised at a capital "
                  f"recovery factor of {CRF}.",
                  "Savings = change in daily freight and lost gross margin from the exact flow engine, x 365, minus new-site "
                  "opex, hazard premium and holding cost.",
                  "Lanes for new sites follow the Dijkstra paths; their freight, lead time and CO2 are the path totals.",
              ],
              "elapsed_s": _r(time.perf_counter() - t0, 2)}
    if narrator is None:
        from llm.parser import narrate_sections

        narrator = narrate_sections
    narr = narrative.narrate({"plans": plans, "baseline": result["baseline"], "params": p}, build_sections(result), narrator)
    result.update(sections=narr["sections"], narrative_source=narr["source"], narrative_rejected=narr["rejected"],
                  summary=narr["sections"][0]["paragraphs"][0])
    if narr["source"] == "llm":
        for q in plans:
            sec = next((s for s in narr["sections"] if s["key"] == q["id"]), None)
            if sec:
                for s_, text in zip(q["sites"], sec["bullets"]):
                    s_["rationale"] = text
    return result


def baseline_kpis(G: nx.DiGraph) -> dict:
    """Today's KPIs from the exact flow engine (used by the Overview): service level, lead, stock cover, freight, CO2."""
    if G.number_of_nodes() == 0 or total_demand(G) <= 0:
        return {"status": "empty"}
    ops = operations(G, 1.0)
    dem = ops["demand"]
    cover = sum((G.nodes[c].get("stock") or 0.0) for c in dem) / (sum(dem.values()) or 1.0)
    return {"status": "ok", "service_level_pct": _r(100 * ops["service_level"], 2), "avg_lead_days": _r(ops["avg_lead_days"], 2),
            "stock_cover_days": _r(cover, 1), "freight_inr_per_day": _r(ops["freight_per_day"], 0),
            "co2_t_per_year": _r(ops["co2_kg_per_day"] * 365 / 1000, 1), "unmet_units_per_day": _r(ops["unmet_per_day"], 1),
            "total_demand_units_per_day": _r(sum(dem.values()), 0), "unit_price": unit_price(G),
            "revenue_inr_per_day": _r(sum(dem.values()) * unit_price(G), 0)}
