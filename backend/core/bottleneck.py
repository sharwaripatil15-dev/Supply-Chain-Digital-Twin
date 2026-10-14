"""Bottleneck and pain-point analyzer: one call returns ranked, evidence-backed findings for any active network.
Owner: D.

Every finding carries: id, title, type, locations (nodes / lanes for the map), severity (formula below), confidence,
evidence (engine numbers), "why this is a problem", root cause, a STRESS TEST (the exact simulator run that shows the
damage), and ranked FIXES - each fix is applied to a copy of the network and the same stress test is re-run, so every
fix reports its counterfactual (new unmet units, delay, resilience, cost). Nothing is estimated by an LLM.

Detectors (thresholds are module constants):
  1 capacity_saturation   sites above SATURATION_UTIL baseline utilisation. Shadow prices come from the dual values of
                          the steady-state flow LP (scipy HiGHS) solved at demand x (1 + surge): the demand recovered per
                          +1 unit/day of capacity. Stress: every demand node +surge for SURGE_DAYS.
  2 single_point_of_failure  sites whose removal cuts some demand node off from every supplier (articulation), whose
                          loss_if_down >= SPOF_LOSS, or that carry > SPOF_FLOW_SHARE of all flow while their loss is not
                          fully absorbed (loss_if_down >= FRAGILE_LOSS; a busy site with idle twins is not a SPOF); lanes whose
                          loss_if_down >= SPOF_LOSS (min-cut lanes). Stress: OUTAGE_DAYS outage.
  3 supplier_concentration  supplier HHI > HHI_FLAG, plants with a single supplier, no backup supplier. Stress: the
                          largest supplier down for SUPPLIER_OUTAGE_DAYS.
  4 inventory_risk        days of cover vs replenishment lead x SAFETY_FACTOR x (1 + lead CV) (thin), or above
                          max(OVERSTOCK_DAYS, OVERSTOCK_X x target) (capital tied up). Warehouse stock is modelled in the
                          stress test as a temporary local source releasing stock / D units per day while its inbound
                          lanes are down for D days (the simulator itself only buffers at demand nodes).
  5 lead_time             the critical (longest-lead) supplier->demand path on today's flows and its dominating hop; lanes
                          with lead CV >= HIGH_CV carrying >= CV_FLOW_SHARE of flow.
  6 route_fragility       lanes with a partial alternate (FRAGILE_LOSS <= loss_if_down < SPOF_LOSS), costly alternates
                          (premium >= ALT_PREMIUM), or weather exposure (peak forecast risk >= WEATHER_FLAG) when hazard
                          data is available.
  7 regional_imbalance / bullwhip  regions importing >= IMPORT_SHARE of their demand; order variability amplified
                          >= BULLWHIP_FLAG (variance ratio) from demand nodes to suppliers (Chen et al. 2000 bound).
  8 hidden_pair           Chaos Finder pairs whose joint failure is worse than the sum of the parts (synergy).

SEVERITY (0-100): 100 x [ W_IMPACT x min(1, impact_share / IMPACT_SCALE)
                        + W_LOSS   x min(1, probability x revenue_at_risk / (REF_DAYS x daily revenue))
                        + W_CUST   x customers affected / demand nodes ]
    impact_share = unmet units in the stress test / demand over the horizon; probability = chance the trigger happens
    (site: 1 - reliability; lane: 1 - min endpoint reliability; surge: SURGE_PROB; pair: product, x3 in one region;
    weather: peak forecast risk). Overstock findings use the capital tied up in place of revenue at risk.
    Levels: critical >= 70, high >= 45, medium >= 25, else low.
FIX RANKING: by net benefit = avoided unmet units x unit price + avoided delay (DELAY_DAY_INR per unit-day) - fix cost,
    ties by benefit / cost. Fix costs (INR, over the horizon): extra capacity CAPACITY_INR per unit/day per day; new lane
    LANE_SETUP_INR; backup contract optimizer.BACKUP_FEE; extra stock (PREPO_COST + holding x horizon) per unit;
    mode switch = freight difference x flow x horizon; collaborative forecasting CPFR_INR.
HEALTH SCORE (0-100) = weighted mean of: resilience (Chaos Finder score), capacity headroom (100 x share of flow through
    sites at or below SATURATION_UTIL), inventory health (demand-weighted share of demand nodes whose cover is between the
    thin and overstock thresholds), concentration (100 x (1 - supplier HHI)), lead-time risk (100 x (1 - flow-weighted
    lead CV / 0.5)). Weights in HEALTH_WEIGHTS. "After fixes" re-scores the network with the top fix of every finding.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable

import networkx as nx
import numpy as np

from core import chaos, features, narrative
from core.delay import arrival_lead
from core.optimizer import BACKUP_FEE, HOLDING_PER_DAY, OVERTIME_COST, PREPO_COST
from core.sim import simulate, solve_flow
from core.synth.profiles import INDUSTRIES, bullwhip_ratio
from node_types import MODE_DEFAULTS, haversine_km, is_demand, suggest_co2, suggest_cost, suggest_lead, total_demand
from schemas import Event

HORIZON = 30
START = 2
SATURATION_UTIL = 0.85
SURGE_DEFAULT = 0.20
SURGE_DAYS = 10
SURGE_PROB = 0.3
SPOF_LOSS = 0.20
SPOF_FLOW_SHARE = 0.50
FRAGILE_LOSS = 0.05
ALT_PREMIUM = 0.50
OUTAGE_DAYS = 7
SUPPLIER_OUTAGE_DAYS = 10
HHI_FLAG = 0.25
SAFETY_FACTOR = features.SAFETY_FACTOR
OVERSTOCK_DAYS = 30.0
OVERSTOCK_X = 3.0
LEAD_FLAG_DAYS = 6.0
DOMINANT_HOP = 0.40
HIGH_CV = 0.30
CV_FLOW_SHARE = 0.10
IMPORT_SHARE = 0.60
REGION_MIN_SHARE = 0.10
BULLWHIP_FLAG = 3.0
WEATHER_FLAG = 0.50
Z90 = 1.2816
MAX_PER_TYPE = 6

IMPACT_SCALE = 0.10
REF_DAYS = 1.0
W_IMPACT, W_LOSS, W_CUST = 0.45, 0.35, 0.20
LEVELS = ((70, "critical"), (45, "high"), (25, "medium"), (0, "low"))

CAPACITY_INR = OVERTIME_COST  # INR per unit/day of extra capacity, per day of the horizon (priced like overtime)
LANE_SETUP_INR = 50_000.0
CPFR_INR = 100_000.0
DELAY_DAY_INR = 40.0  # INR per unit per day of extra delivery delay (same as the weather-aware strategy)
HEALTH_WEIGHTS = {"resilience": 0.30, "capacity_headroom": 0.20, "inventory_health": 0.20, "concentration": 0.15, "lead_time_risk": 0.15}
TYPE_LABEL = {
    "capacity_saturation": "Capacity saturation", "single_point_of_failure": "Single point of failure",
    "supplier_concentration": "Supplier concentration", "inventory_risk": "Inventory risk", "lead_time": "Lead-time chain",
    "route_fragility": "Route fragility", "regional_imbalance": "Regional imbalance", "bullwhip": "Bullwhip",
    "hidden_pair": "Hidden failure pair",
}
CONFIDENCE = {"capacity_saturation": 0.9, "single_point_of_failure": 0.95, "supplier_concentration": 0.9,
              "inventory_risk": 0.8, "lead_time": 0.75, "route_fragility": 0.85, "regional_imbalance": 0.7,
              "bullwhip": 0.55, "hidden_pair": 0.85}


def inr(v: float) -> str:
    from core.strategies import fmt_inr

    return fmt_inr(v)


def units(v: float) -> str:
    return f"{v:,.0f}"


def _r(v: float, d: int = 2) -> float:
    return round(float(v), d)


# ---------------------------------------------------------------- steady-state LP with duals (shadow prices)
P_UNMET = 1e5


def steady_lp(G: nx.DiGraph, demand_mult: float = 1.0, cap_override: dict | None = None, allow_backup: bool = False) -> dict:
    """Single-period min-cost flow as an LP (same model as core.sim.solve_flow, continuous), solved with HiGHS.

    Returns {unmet, cost, objective, throughput, duals: {node: d objective / d capacity (INR per unit/day, <= 0)},
    shadow_units: {node: demand recovered per +1 unit/day of capacity = -dual / P_UNMET, 2 decimals (the freight part
    of the dual is < 0.1% of P_UNMET)}}."""
    from scipy.optimize import linprog

    cap_override = cap_override or {}
    nodes = list(G)
    edges = list(G.edges)
    dem = [n for n in nodes if is_demand(G.nodes[n]["kind"])]
    ne, nd = len(edges), len(dem)
    if ne == 0 or nd == 0:
        need = sum((G.nodes[c].get("demand") or 0.0) * demand_mult for c in dem)
        return {"unmet": need, "cost": 0.0, "objective": need * P_UNMET, "throughput": {}, "duals": {}, "shadow_units": {}}
    eidx = {e: i for i, e in enumerate(edges)}
    cost = [G.edges[e]["cost"] * (1.5 if G.nodes[e[0]].get("backup") else 1.0) for e in edges] + [P_UNMET] * nd
    bounds = [(0.0, float(G.edges[e]["capacity"])) for e in edges]
    demand = {c: (G.nodes[c].get("demand") or 0.0) * demand_mult for c in dem}
    bounds += [(0.0, demand[c]) for c in dem]
    a_ub, b_ub, ub_nodes = [], [], []
    a_eq, b_eq = [], []
    for n in nodes:
        d = G.nodes[n]
        ins = [eidx[(p, n)] for p in G.predecessors(n)]
        outs = [eidx[(n, s)] for s in G.successors(n)]
        cap = float(cap_override.get(n, d.get("capacity") or 0.0))
        if is_demand(d["kind"]):
            row = [0.0] * (ne + nd)
            for i in ins:
                row[i] += 1
            for i in outs:
                row[i] -= 1
            row[ne + dem.index(n)] = 1
            a_eq.append(row)
            b_eq.append(demand[n])
            if outs and cap > 0:
                row = [0.0] * (ne + nd)
                for i in outs:
                    row[i] = 1
                a_ub.append(row)
                b_ub.append(cap)
                ub_nodes.append(n)
            continue
        if d.get("backup") and not allow_backup:
            cap = 0.0
        row = [0.0] * (ne + nd)
        for i in (outs if d["kind"] == "supplier" else ins):
            row[i] = 1
        a_ub.append(row)
        b_ub.append(cap)
        ub_nodes.append(n)
        if d["kind"] != "supplier":
            row = [0.0] * (ne + nd)
            for i in ins:
                row[i] += 1
            for i in outs:
                row[i] -= 1
            a_eq.append(row)
            b_eq.append(0.0)
    res = linprog(cost, A_ub=a_ub or None, b_ub=b_ub or None, A_eq=a_eq or None, b_eq=b_eq or None, bounds=bounds, method="highs")
    if res.status != 0:
        raise RuntimeError(f"steady-state LP failed: {res.message}")
    x = res.x
    marg = list(res.ineqlin.marginals) if a_ub else []
    duals = {n: float(m) for n, m in zip(ub_nodes, marg)}
    thr = {n: float(sum(x[eidx[(n, s)]] for s in G.successors(n)) if G.nodes[n]["kind"] == "supplier"
                    else sum(x[eidx[(p, n)]] for p in G.predecessors(n))) for n in nodes if not is_demand(G.nodes[n]["kind"])}
    unmet = float(sum(x[ne:]))
    return {"unmet": unmet, "cost": float(np.dot(cost[:ne], x[:ne])), "objective": float(res.fun), "throughput": thr,
            "duals": duals, "shadow_units": {n: _r(max(0.0, -m) / P_UNMET, 2) for n, m in duals.items()}}  # freight shifts this by < 0.1%


# ---------------------------------------------------------------- context
@dataclass
class Ctx:
    G: nx.DiGraph
    horizon: int
    weather: dict | None
    unit_price: float = field(init=False)
    total: float = field(init=False)
    base: dict = field(init=False)
    feat: features.FeatureContext = field(init=False)
    lead: dict = field(init=False)
    resilience: float = field(init=False)
    demand_nodes: list = field(init=False)
    surge: float = field(init=False)

    def __post_init__(self):
        G = self.G
        self.unit_price = float(G.graph.get("unit_price", 4200))
        self.total = total_demand(G)
        self.base = solve_flow(G)
        self.feat = features.context(G)
        self.lead = arrival_lead(G, self.base["flow"])
        self.resilience = chaos.resilience_score(G)
        self.demand_nodes = [n for n, d in G.nodes(data=True) if is_demand(d["kind"]) and (d.get("demand") or 0) > 0]
        prof = INDUSTRIES.get(G.graph.get("industry") or "")
        self.surge = float(prof.festival_peak) if prof and prof.festival_peak >= 0.1 else SURGE_DEFAULT

    @property
    def daily_revenue(self) -> float:
        return self.total * self.unit_price

    def util(self, n: str) -> float:
        cap = self.G.nodes[n].get("capacity") or 0.0
        return self.base["throughput"].get(n, 0.0) / cap if cap else 0.0

    def name(self, n: str) -> str:
        d = self.G.nodes[n] if n in self.G else {}
        return f"{n} ({d.get('name') or n})" if d.get("name") and d.get("name") != n else n


def stress(H: nx.DiGraph, events: list[Event], horizon: int) -> dict:
    res = simulate(H, events, horizon)
    unit_price = H.graph.get("unit_price", 4200)
    hit = [c for c, v in res.get("unmet_by_node", {}).items() if v > 0]
    return {"unmet_units": _r(res["total_unmet"], 1), "revenue_at_risk": _r(res["total_unmet"] * unit_price, 0),
            "delay_avg_days": res["delay"]["avg_days"], "delay_p90_days": res["delay"]["p90_days"],
            "stockout_day": res["survival_clock_days"], "customers_affected": hit, "unmet_by_node": res.get("unmet_by_node", {})}


# ---------------------------------------------------------------- graph edits used by fixes
def _km(G, a, b) -> float:
    return haversine_km((G.nodes[a]["lat"], G.nodes[a]["lon"]), (G.nodes[b]["lat"], G.nodes[b]["lon"]))


def _lane(G: nx.DiGraph, u: str, v: str, cap: float, mode: str = "road") -> None:
    km = _km(G, u, v)
    G.add_edge(u, v, capacity=float(math.ceil(cap)), lead=suggest_lead(mode, km), cost=suggest_cost(mode, km),
               co2=suggest_co2(mode, km), mode=mode, distance_km=round(km, 1))


def _nearest_peer(G: nx.DiGraph, n: str, exclude: set | None = None) -> str | None:
    kind = G.nodes[n]["kind"]
    peers = [m for m, d in G.nodes(data=True) if d["kind"] == kind and m != n and not d.get("backup") and m not in (exclude or set())]
    return min(peers, key=lambda m: (_km(G, n, m), m)) if peers else None


def _flow_through(G: nx.DiGraph, base: dict, n: str) -> float:
    if is_demand(G.nodes[n]["kind"]):
        return G.nodes[n].get("demand") or 0.0
    return base["throughput"].get(n, 0.0)


def add_redundancy(H: nx.DiGraph, n: str, base: dict, exclude: set | None = None) -> list[str]:
    """Give the nearest same-tier site (not in `exclude`) the lanes and spare capacity to take over n's flow."""
    m = _nearest_peer(H, n, exclude)
    if m is None:
        return []
    added = []
    for s in list(H.successors(n)):
        f = max(base["flow"].get((n, s), 0.0), 1.0)
        if H.has_edge(m, s):
            H.edges[m, s]["capacity"] += f
        else:
            _lane(H, m, s, f)
            added.append(f"{m}->{s}")
    if H.nodes[n]["kind"] != "supplier":
        for p in list(H.predecessors(n)):
            if H.nodes[p].get("backup"):
                continue
            f = max(base["flow"].get((p, n), 0.0), 1.0)
            if H.has_edge(p, m):
                H.edges[p, m]["capacity"] += f
            else:
                _lane(H, p, m, f)
                added.append(f"{p}->{m}")
    thr = base["throughput"].get(n, 0.0)
    spare = (H.nodes[m].get("capacity") or 0.0) - base["throughput"].get(m, 0.0)
    if thr > spare:
        H.nodes[m]["capacity"] = (H.nodes[m].get("capacity") or 0.0) + (thr - spare)
    H.graph["_fix_peer"] = m
    return added


def add_backup_supplier(H: nx.DiGraph, near: str, factories: list[str], capacity: float) -> str:
    bid = "BKP_" + str(near)
    i = 1
    while bid in H:
        i += 1
        bid = f"BKP{i}_{near}"
    d = H.nodes[near]
    H.add_node(bid, kind="supplier", name=f"Backup for {near}", city=d.get("city", ""), lat=d["lat"] + 0.3, lon=d["lon"] + 0.3,
               capacity=float(math.ceil(capacity)), stock=0.0, demand=0.0, reliability=0.95, backup=True)
    for f in factories:
        _lane(H, bid, f, capacity)
    return bid


# ---------------------------------------------------------------- fix + finding records
@dataclass
class Fix:
    id: str
    label: str
    description: str
    apply: Callable[[nx.DiGraph], None]
    cost_inr: float
    events: list[Event] | None = None  # override the stress events (e.g. a smaller demand swing)
    prepare: Callable[[nx.DiGraph], list[Event]] | None = None  # build a stress graph + events for this fix


def severity(impact_share: float, probability: float, revenue: float, customers: int, n_customers: int, daily_revenue: float) -> float:
    loss = probability * revenue / max(1.0, REF_DAYS * daily_revenue)
    s = 100 * (W_IMPACT * min(1.0, impact_share / IMPACT_SCALE) + W_LOSS * min(1.0, loss) + W_CUST * (customers / max(1, n_customers)))
    return _r(s, 1)


def level(score: float) -> str:
    return next(name for cut, name in LEVELS if score >= cut)


def _evaluate(cx: Ctx, kind: str, title: str, nodes: list[str], edges: list[str], probability: float, stress_label: str,
              events: list[Event], evidence: dict, why: str, root: str, fixes: list[Fix], *, prepare=None,
              capital_tied: float | None = None) -> dict:
    """Run the stress test before and after every fix; rank fixes; compute severity. The finding id is assigned later."""
    G = cx.G
    H0 = G.copy()
    ev0 = prepare(H0) if prepare else events
    before = stress(H0, ev0, cx.horizon)
    horizon_demand = cx.total * cx.horizon or 1.0
    impact_share = before["unmet_units"] / horizon_demand
    revenue = capital_tied if capital_tied is not None else before["revenue_at_risk"]
    sev = severity(impact_share if capital_tied is None else 0.0, probability, revenue, len(before["customers_affected"]),
                   len(cx.demand_nodes), cx.daily_revenue)
    delivered = max(0.0, horizon_demand - before["unmet_units"])
    rows = []
    best_graph = None
    for fx in fixes:
        H = G.copy()
        fx.apply(H)
        ev = fx.prepare(H) if fx.prepare else (prepare(H) if prepare else (fx.events or events))
        after = stress(H, ev, cx.horizon)
        avoided = before["unmet_units"] - after["unmet_units"]
        delay_gain = (before["delay_avg_days"] - after["delay_avg_days"]) * delivered
        benefit = avoided * cx.unit_price + delay_gain * DELAY_DAY_INR
        rows.append({
            "id": fx.id, "label": fx.label, "description": fx.description,
            "cost_inr": _r(fx.cost_inr, 0), "cost_display": inr(fx.cost_inr),
            "benefit_inr": _r(benefit, 0), "benefit_display": inr(benefit),
            "net_inr": _r(benefit - fx.cost_inr, 0), "net_display": inr(benefit - fx.cost_inr),
            "ratio": _r(benefit / fx.cost_inr, 2) if fx.cost_inr > 0 else None,
            "result": {"unmet_units": after["unmet_units"], "unmet_display": units(after["unmet_units"]),
                       "avoided_units": _r(avoided, 1), "avoided_display": units(avoided),
                       "delay_avg_days": after["delay_avg_days"], "revenue_at_risk": after["revenue_at_risk"],
                       "revenue_at_risk_display": inr(after["revenue_at_risk"]), "stockout_day": after["stockout_day"],
                       "resilience": None},
            "_graph": H,
        })
    rows.sort(key=lambda r: (-r["net_inr"], -(r["ratio"] or 0)))
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    if rows:
        best_graph = rows[0]["_graph"]
        try:
            rows[0]["result"]["resilience"] = chaos.resilience_score(best_graph)
        except Exception:  # noqa: BLE001 - resilience is informative only
            rows[0]["result"]["resilience"] = None
    for r in rows:
        r.pop("_graph")
    best = rows[0] if rows else None
    cust = before["customers_affected"]
    lc = lambda t: t[0].lower() + t[1:] if t else t  # noqa: E731 - keep ids like S1 intact
    if capital_tied is not None:
        business = (f"{title}: {inr(capital_tied)} of working capital is tied up in excess stock; "
                    + (f"{lc(best['label'])} releases it and saves {best['net_display']} over {cx.horizon} days (simulated)." if best else ""))
    elif before["unmet_units"] <= 0:
        business = (f"{title}: in the simulation a {stress_label} is absorbed without lost demand (stock and spare capacity cover it)"
                    + ("; no fix pays off yet, so monitor it (simulated)." if not best or best["net_inr"] <= 0 else
                       f"; {lc(best['label'])} still pays off through shorter delays ({best['net_display']} net, simulated)."))
    else:
        business = (f"{title}: a {stress_label} would leave {units(before['unmet_units'])} units unmet "
                    f"({inr(before['revenue_at_risk'])} of revenue, {len(cust)} demand node(s) hit)"
                    + (f"; {lc(best['label'])} cuts that to {best['result']['unmet_display']} units for {best['cost_display']} (simulated)."
                       if best else " (simulated)."))
    return {
        "title": title, "type": kind, "type_label": TYPE_LABEL[kind], "locations": {"nodes": nodes, "edges": edges},
        "severity": sev, "severity_level": level(sev), "confidence": CONFIDENCE[kind], "probability": _r(probability, 3),
        "impact": {"impact_share_pct": _r(100 * impact_share, 2), "unmet_units": before["unmet_units"],
                   "unmet_display": units(before["unmet_units"]), "revenue_at_risk": before["revenue_at_risk"],
                   "revenue_at_risk_display": inr(before["revenue_at_risk"]), "customers_affected": cust,
                   "customers_affected_count": len(cust), "stockout_day": before["stockout_day"],
                   "delay_avg_days": before["delay_avg_days"],
                   "expected_loss_inr": _r(probability * revenue, 0), "expected_loss_display": inr(probability * revenue),
                   **({"capital_tied_inr": _r(capital_tied, 0), "capital_tied_display": inr(capital_tied)} if capital_tied is not None else {})},
        "stress": {"label": stress_label, "events": [e.model_dump(exclude_none=True) for e in ev0], "horizon_days": cx.horizon},
        "evidence": evidence, "why": why, "root_cause": root, "business": business, "fixes": rows,
        "whatif": {"events": [e.model_dump(exclude_none=True) for e in ev0 if not e.target.startswith("__")],
                   "text": f"What if: {stress_label}?"},
        "_fix_objs": {fx.id: fx for fx in fixes},
    }


def _ev(kind: str, target: str, duration: int, severity_: float = 1.0, **kw) -> Event:
    return Event(type=kind, target=target, start=START, duration=duration, severity=severity_, **kw)


def _surge_events(cx: Ctx, surge: float) -> list[Event]:
    return [_ev("demand", c, SURGE_DAYS, min(1.0, surge)) for c in cx.demand_nodes]


# ---------------------------------------------------------------- 1. capacity saturation
def detect_saturation(cx: Ctx) -> list[dict]:
    G = cx.G
    sites = [n for n, d in G.nodes(data=True) if not is_demand(d["kind"]) and not d.get("backup") and cx.util(n) > SATURATION_UTIL]
    if not sites:
        return []
    lp = steady_lp(G, demand_mult=1 + cx.surge)
    out = []
    for n in sorted(sites, key=lambda n: -cx.util(n))[:MAX_PER_TYPE]:
        d = G.nodes[n]
        cap = d.get("capacity") or 0.0
        thr = cx.base["throughput"].get(n, 0.0)
        delta = float(max(math.ceil(0.15 * cap), math.ceil(thr / 0.75 - cap), 1))
        sp = lp["shadow_units"].get(n, 0.0)
        plus = steady_lp(G, demand_mult=1 + cx.surge, cap_override={n: cap + delta})
        recovered_daily = max(0.0, lp["unmet"] - plus["unmet"])
        evidence = {
            "utilization_pct": _r(100 * cx.util(n), 1), "capacity_units_per_day": cap, "throughput_units_per_day": _r(thr, 1),
            "surge_pct": _r(100 * cx.surge, 0), "surge_days": SURGE_DAYS,
            "lp_unmet_per_day_at_surge": _r(lp["unmet"], 1), "shadow_price_units_per_unit": sp,
            "dual_value_inr_per_unit": _r(lp["duals"].get(n, 0.0), 2),
            "added_capacity_units_per_day": delta, "recovered_units_per_day": _r(recovered_daily, 1),
            "recovered_units_over_surge": _r(recovered_daily * SURGE_DAYS, 0),
            "shadow_prices_all_saturated": {m: lp["shadow_units"].get(m, 0.0) for m in sites},
        }
        sentence = (f"+{units(delta)} units/day at {n} recovers {units(recovered_daily * SURGE_DAYS)} units of demand over a "
                    f"{SURGE_DAYS}-day +{100 * cx.surge:.0f}% surge (LP shadow price {sp:.2f} units per unit of capacity).")
        evidence["shadow_price_statement"] = sentence
        why = (f"{cx.name(n)} runs at {100 * cx.util(n):.0f}% of its {units(cap)} units/day capacity on a normal day, above the "
               f"{100 * SATURATION_UTIL:.0f}% saturation threshold. " + sentence)
        root = ("Demand routed through this site has grown into its capacity: the cheapest paths all pass through it and its "
                "peers have little spare capacity on those lanes." if sp > 0 else
                "The site is the cheapest route, so the optimiser fills it; peers can absorb a surge, but at a higher cost.")
        fixes = [
            Fix("capacity", f"Add {units(delta)} units/day of capacity at {n}", f"Permanent capacity +{units(delta)} units/day "
                f"(utilisation back to about 75%).", lambda H, n=n, delta=delta: H.nodes[n].update(capacity=H.nodes[n]["capacity"] + delta),
                delta * cx.horizon * CAPACITY_INR),
            Fix("overtime", f"Overtime during surges at {n} (+{units(math.ceil(delta / 2))}/day)", "Half of the extra capacity, run only "
                "during the surge window.", lambda H, n=n, delta=delta: H.nodes[n].update(capacity=H.nodes[n]["capacity"] + math.ceil(delta / 2)),
                math.ceil(delta / 2) * SURGE_DAYS * CAPACITY_INR),
        ]
        out.append(_evaluate(cx, "capacity_saturation", f"{cx.name(n)} is running at {100 * cx.util(n):.0f}% capacity", [n], [],
                             SURGE_PROB, f"{SURGE_DAYS}-day +{100 * cx.surge:.0f}% demand surge", _surge_events(cx, cx.surge),
                             evidence, why, root, fixes))
    return out


# ---------------------------------------------------------------- 2. single points of failure
def detect_spof(cx: Ctx, skip: set[str]) -> tuple[list[dict], set[str]]:
    G, nr, er = cx.G, cx.feat.nrec, cx.feat.erec
    flagged: set[str] = set()
    out = []
    cands = []
    for n, d in G.nodes(data=True):
        if is_demand(d["kind"]) or d.get("backup") or n in skip:
            continue
        r = nr[n]
        busy = r["flow_share"] > SPOF_FLOW_SHARE and r["loss_if_down"] >= FRAGILE_LOSS
        if r["articulation"] or r["loss_if_down"] >= SPOF_LOSS or busy:
            cands.append(n)
    cands.sort(key=lambda n: -nr[n]["loss_if_down"])
    for n in cands[:MAX_PER_TYPE]:
        r, d = nr[n], G.nodes[n]
        flagged.add(n)
        reasons = []
        if r["articulation"]:
            reasons.append("removing it cuts at least one demand node off from every supplier")
        if r["loss_if_down"] >= SPOF_LOSS:
            reasons.append(f"losing it leaves {100 * r['loss_if_down']:.0f}% of daily demand unservable even with the backup open")
        if r["flow_share"] > SPOF_FLOW_SHARE and r["loss_if_down"] >= FRAGILE_LOSS:
            reasons.append(f"it carries {100 * r['flow_share']:.0f}% of all flow")
        downstream = [c for c in cx.demand_nodes if c in cx.feat.downstream.get(n, set())]
        evidence = {"articulation": bool(r["articulation"]), "loss_if_down_pct": _r(100 * r["loss_if_down"], 1),
                    "flow_share_pct": _r(100 * r["flow_share"], 1), "downstream_demand_pct": _r(100 * r["downstream_demand"], 1),
                    "alternate_paths": int(r["alt_paths"]), "reliability": d.get("reliability", 1.0),
                    "demand_nodes_downstream": downstream}
        need = sum((G.nodes[c].get("demand") or 0.0) for c in downstream)
        peer = _nearest_peer(G, n)
        fixes = []
        if peer:
            fixes.append(Fix("redundancy", f"Qualify {peer} as a second site for {n}'s flows",
                             f"Lanes and spare capacity so {peer} can take over {n}'s volume.",
                             lambda H, n=n: add_redundancy(H, n, cx.base),
                             LANE_SETUP_INR * (G.out_degree(n) + G.in_degree(n)) + cx.base["throughput"].get(n, 0.0) * cx.horizon * CAPACITY_INR * 0.25))
        units_needed = need * OUTAGE_DAYS

        def buffer(H, downstream=downstream):
            for c in downstream:
                H.nodes[c]["stock"] = max(H.nodes[c].get("stock") or 0.0, (H.nodes[c].get("demand") or 0.0) * (OUTAGE_DAYS + 1))
        extra = sum(max(0.0, (G.nodes[c].get("demand") or 0.0) * (OUTAGE_DAYS + 1) - (G.nodes[c].get("stock") or 0.0)) for c in downstream)
        if downstream and extra > 0:
            fixes.append(Fix("buffer", f"Hold {OUTAGE_DAYS + 1} days of stock downstream of {n}",
                             f"+{units(extra)} units at {', '.join(downstream[:4])}.", buffer, extra * (PREPO_COST + HOLDING_PER_DAY * cx.horizon)))
        out.append(_evaluate(
            cx, "single_point_of_failure", f"{cx.name(n)} is a single point of failure", [n] + downstream, [],
            1 - float(d.get("reliability", 0.9)), f"{OUTAGE_DAYS}-day outage at {n}", [_ev("node", n, OUTAGE_DAYS)], evidence,
            f"{cx.name(n)}: " + "; ".join(reasons) + f". {units(units_needed)} units of demand depend on it over a {OUTAGE_DAYS}-day outage.",
            "No parallel site of the same tier is connected to the same customers with enough spare capacity.", fixes))
    # min-cut lanes not explained by a flagged endpoint
    lanes = [e for e, r in er.items() if r["loss_if_down"] >= SPOF_LOSS]
    for e in sorted(lanes, key=lambda e: -er[e]["loss_if_down"])[:MAX_PER_TYPE]:
        u, v = e.split("->")
        ends = [x for x in (u, v) if x in flagged or x in skip]
        if any(nr[x]["loss_if_down"] + 0.01 >= er[e]["loss_if_down"] for x in ends):
            continue
        flagged.add(e)
        out.append(_lane_finding(cx, e, "single_point_of_failure", f"Lane {e} is a min-cut lane",
                                 f"Blocking lane {e} leaves {100 * er[e]['loss_if_down']:.0f}% of daily demand unservable: every "
                                 f"alternative route together cannot carry its {100 * er[e]['flow_share']:.0f}% share of flow.",
                                 "The network has no second lane with spare capacity between these tiers."))
    return out, flagged


def _lane_finding(cx: Ctx, e: str, kind: str, title: str, why: str, root: str, probability: float | None = None,
                  extra_evidence: dict | None = None) -> dict:
    G, er = cx.G, cx.feat.erec
    u, v = e.split("->")
    f = cx.base["flow"].get((u, v), 0.0)
    evidence = {"loss_if_down_pct": _r(100 * er[e]["loss_if_down"], 1), "flow_share_pct": _r(100 * er[e]["flow_share"], 1),
                "flow_units_per_day": _r(f, 1), "lead_days": er[e]["lead"], "alternate_inbound_spare_x": _r(er[e]["alt_inbound"], 2),
                **(extra_evidence or {})}
    fixes = []
    peer = _nearest_peer(G, u, exclude={v})
    if peer and not G.has_edge(peer, v):
        def alt(H, peer=peer, f=f):
            _lane(H, peer, v, max(f, 1.0))
            spare = (H.nodes[peer].get("capacity") or 0.0) - cx.base["throughput"].get(peer, 0.0)
            if f > spare:
                H.nodes[peer]["capacity"] = (H.nodes[peer].get("capacity") or 0.0) + (f - spare)
        fixes.append(Fix("alt_lane", f"Open lane {peer}->{v}", f"A parallel lane from {peer} with {units(f)} units/day capacity.",
                         alt, LANE_SETUP_INR + max(0.0, f - ((G.nodes[peer].get("capacity") or 0.0) - cx.base["throughput"].get(peer, 0.0))) * cx.horizon * CAPACITY_INR))
    others = [p for p in G.predecessors(v) if p != u and not G.nodes[p].get("backup")]
    if others:
        def widen(H, others=others, f=f):
            for p in others:
                H.edges[p, v]["capacity"] += f / len(others)
                H.nodes[p]["capacity"] = (H.nodes[p].get("capacity") or 0.0) + f / len(others)
        fixes.append(Fix("widen_alternates", f"Add capacity on the alternate lanes into {v}",
                         f"+{units(f)} units/day across {', '.join(others[:4])}.", widen, f * cx.horizon * CAPACITY_INR))
    rel = min(G.nodes[u].get("reliability", 0.9), G.nodes[v].get("reliability", 0.9))
    return _evaluate(cx, kind, title, [u, v], [e], probability if probability is not None else 1 - float(rel),
                     f"{OUTAGE_DAYS}-day closure of lane {e}", [_ev("edge", e, OUTAGE_DAYS)], evidence, why, root, fixes)


# ---------------------------------------------------------------- 3. supplier concentration
def detect_concentration(cx: Ctx) -> tuple[list[dict], set[str]]:
    G = cx.G
    shares = features.supplier_shares(G, cx.base["throughput"])
    if not shares:
        return [], set()
    h = features.hhi(shares.values())
    backups = [n for n, d in G.nodes(data=True) if d.get("kind") == "supplier" and d.get("backup")]
    facs = [n for n, d in G.nodes(data=True) if d["kind"] == "factory"]
    sole = {}
    for f in facs:
        prim = [p for p in G.predecessors(f) if G.nodes[p]["kind"] == "supplier" and not G.nodes[p].get("backup")]
        if len(prim) == 1:
            sole.setdefault(prim[0], []).append(f)
    flagged = set()
    out = []
    cands = sorted(set(sole) | ({max(shares, key=shares.get)} if h > HHI_FLAG else set()), key=lambda s: -shares.get(s, 0.0))
    for s in cands[:MAX_PER_TYPE]:
        flagged.add(s)
        mine = sole.get(s, [])
        covered = [b for b in backups if any(G.has_edge(b, f) for f in G.successors(s))]
        served = sorted(G.successors(s))
        evidence = {"supplier_share_pct": _r(100 * shares.get(s, 0.0), 1), "supplier_hhi": _r(h, 3),
                    "single_sourced_plants": mine, "backup_suppliers": backups, "backup_covering_its_plants": covered,
                    "n_primary_suppliers": len(shares)}
        bits = [f"{cx.name(s)} provides {100 * shares.get(s, 0.0):.0f}% of supply (HHI {h:.2f})"]
        if mine:
            bits.append(f"it is the only supplier of {', '.join(mine)}")
        if not covered:
            bits.append("no backup supplier can serve its plants")
        thr = cx.base["throughput"].get(s, 0.0)
        fixes = []
        targets = mine or served
        if not covered and targets:
            fixes.append(Fix("backup", f"Contract a backup supplier for {s}", f"Backup capacity {units(thr)} units/day with lanes to "
                             f"{', '.join(targets[:4])}; opens after the activation lag.",
                             lambda H, s=s, targets=targets, thr=thr: add_backup_supplier(H, s, targets, max(thr, 1.0)),
                             BACKUP_FEE + LANE_SETUP_INR * len(targets)))
        other = _nearest_peer(G, s)
        if other and targets:
            def dual(H, s=s, other=other, targets=targets, thr=thr):
                for f in targets:
                    if H.has_edge(other, f):
                        H.edges[other, f]["capacity"] += thr / len(targets)
                    else:
                        _lane(H, other, f, max(thr / len(targets), 1.0))
                H.nodes[other]["capacity"] = (H.nodes[other].get("capacity") or 0.0) + thr * 0.5
            fixes.append(Fix("dual_source", f"Dual-source from {other}", f"Lanes from {other} to {', '.join(targets[:4])} and +"
                             f"{units(thr * 0.5)} units/day at {other}.", dual,
                             LANE_SETUP_INR * sum(1 for f in targets if not G.has_edge(other, f)) + thr * 0.5 * cx.horizon * CAPACITY_INR))
        out.append(_evaluate(
            cx, "supplier_concentration", f"Supply depends on {cx.name(s)}", [s] + mine, [], 1 - float(G.nodes[s].get("reliability", 0.9)),
            f"{SUPPLIER_OUTAGE_DAYS}-day outage at {s}", [_ev("node", s, SUPPLIER_OUTAGE_DAYS)], evidence, "; ".join(bits) + ".",
            "Sourcing was optimised for cost: volume is concentrated on one supplier and no second source is qualified.", fixes))
    return out, flagged


# ---------------------------------------------------------------- 4. inventory risk
def _target_cover(cx: Ctx, n: str) -> tuple[float, float, float]:
    r = cx.feat.nrec[n]
    lead = max(1.0, r["replenish_lead"])
    cv = r["lead_cv_in"] or features.DEFAULT_LEAD_CV
    return lead, cv, SAFETY_FACTOR * lead * (1 + cv)


def _warehouse_stress(n: str, days: int):
    """Stress graph + events: inbound lanes of warehouse n down for `days`; its stock released as stock/days per day."""
    def prepare(H: nx.DiGraph) -> list[Event]:
        stock = H.nodes[n].get("stock") or 0.0
        sid = f"__STOCK_{n}"
        H.add_node(sid, kind="supplier", name=f"{n} on-hand stock", city=H.nodes[n].get("city", ""), lat=H.nodes[n]["lat"],
                   lon=H.nodes[n]["lon"], capacity=stock / days, stock=0.0, demand=0.0, reliability=1.0, backup=False)
        H.add_edge(sid, n, capacity=stock / days, lead=0.0, cost=500.0, co2=0.0)  # dear: used only when inbound fails
        evs = [_ev("edge", f"{p}->{n}", days) for p in H.predecessors(n) if p != sid]
        evs.append(Event(type="edge", target=f"{sid}->{n}", start=START + days, duration=max(1, HORIZON - START - days), severity=1.0))
        return evs
    return prepare


def detect_inventory(cx: Ctx) -> list[dict]:
    G, nr = cx.G, cx.feat.nrec
    out = []
    thin, over = [], []
    for n, d in G.nodes(data=True):
        if d.get("backup") or not (is_demand(d["kind"]) or d["kind"] == "warehouse"):
            continue
        need = (d.get("demand") or 0.0) if is_demand(d["kind"]) else (cx.base["throughput"].get(n, 0.0) or 0.0)
        if need <= 0:
            continue
        cover = (d.get("stock") or 0.0) / need
        lead, cv, target = _target_cover(cx, n)
        if cover < target:
            thin.append((n, cover, lead, cv, target, need))
        elif cover > max(OVERSTOCK_DAYS, OVERSTOCK_X * target):
            over.append((n, cover, lead, cv, target, need))
    for n, cover, lead, cv, target, need in sorted(thin, key=lambda t: t[1] / t[4])[:MAX_PER_TYPE]:
        d = G.nodes[n]
        days = int(max(1, math.ceil(target)))
        add = (target - cover) * need
        evidence = {"days_of_cover": _r(cover, 2), "replenishment_lead_days": _r(lead, 2), "lead_time_cv": _r(cv, 3),
                    "safety_factor": SAFETY_FACTOR, "target_cover_days": _r(target, 2), "stock_units": d.get("stock") or 0.0,
                    "daily_requirement_units": _r(need, 1), "shortfall_units": _r(add, 0)}
        if is_demand(d["kind"]):
            preds = sorted(G.predecessors(n), key=lambda p: -cx.base["flow"].get((p, n), 0.0))
            if not preds:
                continue
            up = preds[0]
            ev = [_ev("edge", f"{up}->{n}", days)]
            label = f"{days}-day resupply interruption on lane {up}->{n}"
            prep = None
        else:
            ev, prep = [], _warehouse_stress(n, days)
            label = f"{days}-day stop of all inbound supply to {n}"
        fixes = [Fix("raise_stock", f"Raise stock at {n} to {target:.1f} days of cover", f"+{units(add)} units "
                     f"({SAFETY_FACTOR:g} x lead {lead:.1f} d x (1 + CV {cv:.2f})).",
                     lambda H, n=n, add=add: H.nodes[n].update(stock=(H.nodes[n].get("stock") or 0.0) + add),
                     add * (PREPO_COST + HOLDING_PER_DAY * cx.horizon))]
        out.append(_evaluate(
            cx, "inventory_risk", f"Thin stock at {cx.name(n)}: {cover:.1f} days of cover", [n], [], 1 - float(d.get("reliability", 0.9)),
            label, ev, evidence,
            f"{cx.name(n)} holds {cover:.1f} days of cover but resupply takes {lead:.1f} days with lead-time CV {cv:.2f}; the "
            f"target is {SAFETY_FACTOR:g} x {lead:.1f} x (1 + {cv:.2f}) = {target:.1f} days.",
            "Stock was sized for an undisrupted lead time; it does not cover the time needed to resupply after a delay.",
            fixes, prepare=prep))
    for n, cover, lead, cv, target, need in sorted(over, key=lambda t: -t[1])[:MAX_PER_TYPE]:
        d = G.nodes[n]
        keep = max(OVERSTOCK_X * target, target) * need
        excess = max(0.0, (d.get("stock") or 0.0) - keep)
        margin = float(G.graph.get("margin", 0.25))
        capital = excess * cx.unit_price * (1 - margin)
        holding = excess * float(G.graph.get("holding_cost", HOLDING_PER_DAY)) * cx.horizon
        evidence = {"days_of_cover": _r(cover, 1), "target_cover_days": _r(target, 2), "overstock_threshold_days": _r(max(OVERSTOCK_DAYS, OVERSTOCK_X * target), 1),
                    "excess_units": _r(excess, 0), "capital_tied_inr": _r(capital, 0), "holding_cost_over_horizon_inr": _r(holding, 0)}
        fixes = [Fix("reduce_stock", f"Run {n} down to {OVERSTOCK_X * target:.1f} days of cover", f"Release {units(excess)} units; saves "
                     f"{inr(holding)} of holding cost over {cx.horizon} days.",
                     lambda H, n=n, excess=excess: H.nodes[n].update(stock=(H.nodes[n].get("stock") or 0.0) - excess), -holding)]
        up = sorted(G.predecessors(n), key=lambda p: -cx.base["flow"].get((p, n), 0.0))
        ev = [_ev("edge", f"{up[0]}->{n}", int(math.ceil(target)))] if up and is_demand(d["kind"]) else []
        out.append(_evaluate(
            cx, "inventory_risk", f"Overstock at {cx.name(n)}: {cover:.0f} days of cover", [n], [], 1.0,
            f"{int(math.ceil(target))}-day resupply interruption into {n}" if ev else "normal operations", ev, evidence,
            f"{cx.name(n)} holds {cover:.0f} days of cover against a target of {target:.1f} days, tying up {inr(capital)} at cost.",
            "Replenishment quantities have not been revised to the actual lead time.", fixes,
            prepare=None if is_demand(d["kind"]) else _warehouse_stress(n, int(max(1, math.ceil(target)))), capital_tied=capital))
    return out


# ---------------------------------------------------------------- 5. lead-time chain
def critical_path(cx: Ctx) -> tuple[list[str], float] | None:
    G = cx.G
    best = None
    for c in cx.demand_nodes:
        path, node, total = [c], c, 0.0
        while G.nodes[node]["kind"] != "supplier":
            preds = [p for p in G.predecessors(node) if cx.base["flow"].get((p, node), 0.0) > 0 and p not in path and cx.lead.get(p) is not None]
            if not preds:
                break
            p = max(preds, key=lambda p: cx.lead[p] + G.edges[p, node]["lead"])
            total += G.edges[p, node]["lead"]
            path.append(p)
            node = p
        if len(path) > 1 and (best is None or total > best[1]):
            best = (path[::-1], total)
    return best


def detect_lead_time(cx: Ctx) -> list[dict]:
    G, er = cx.G, cx.feat.erec
    out = []
    cp = critical_path(cx)
    if cp:
        path, total = cp
        hops = [(f"{a}->{b}", G.edges[a, b]["lead"]) for a, b in zip(path, path[1:])]
        dom, dom_lead = max(hops, key=lambda h: h[1])
        share = dom_lead / total if total else 0.0
        if total >= LEAD_FLAG_DAYS and share >= DOMINANT_HOP:
            u, v = dom.split("->")
            ed = G.edges[u, v]
            km = ed.get("distance_km") or _km(G, u, v)
            air_lead = suggest_lead("air", km)
            f = cx.base["flow"].get((u, v), 0.0)
            air_cost = (suggest_cost("air", km) - ed["cost"]) * f * cx.horizon
            evidence = {"critical_path": path, "path_lead_days": _r(total, 1), "hops": [{"lane": h, "lead_days": l} for h, l in hops],
                        "dominating_hop": dom, "dominating_share_pct": _r(100 * share, 0), "mode": ed.get("mode", "road"),
                        "distance_km": _r(km, 0), "air_lead_days": air_lead}
            fixes = []
            if air_lead < ed["lead"]:
                fixes.append(Fix("air", f"Move {dom} to air freight", f"Lead {ed['lead']:.1f} -> {air_lead:.1f} days; freight "
                                 f"+{inr(air_cost)} over {cx.horizon} days.",
                                 lambda H, u=u, v=v, km=km: H.edges[u, v].update(lead=suggest_lead("air", km), mode="air"), max(0.0, air_cost)))
            fixes.append(Fix("cut_handling", f"Cut one day of handling on {dom}", "Pre-cleared paperwork / cross-docking (assumed "
                             f"{inr(LANE_SETUP_INR)} process cost).", lambda H, u=u, v=v: H.edges[u, v].update(lead=max(0.5, H.edges[u, v]["lead"] - 1)),
                             LANE_SETUP_INR))
            out.append(_evaluate(
                cx, "lead_time", f"Critical path {' -> '.join(path)} takes {total:.1f} days", path, [dom], SURGE_PROB,
                f"10-day doubling of the lead time on {dom}", [_ev("edge", dom, 10, 0.0, lead_multiplier=2.0)], evidence,
                f"The slowest supplier-to-customer path takes {total:.1f} days and {dom} alone accounts for {100 * share:.0f}% of it.",
                f"{dom} is a {km:,.0f} km {ed.get('mode', 'road')} lane; any slowdown there moves delivery dates for "
                f"{path[-1]} one-for-one.", fixes))
    risky = [e for e, r in er.items() if r["lead_cv"] >= HIGH_CV and r["flow_share"] >= CV_FLOW_SHARE]
    if risky:
        lanes = sorted(risky, key=lambda e: -er[e]["lead_cv"] * er[e]["flow_share"])[:MAX_PER_TYPE]
        ends = sorted({x for e in lanes for x in e.split("->")})
        evidence = {"lanes": [{"lane": e, "lead_cv": _r(er[e]["lead_cv"], 2), "lead_days": er[e]["lead"],
                               "flow_share_pct": _r(100 * er[e]["flow_share"], 1)} for e in lanes], "threshold_cv": HIGH_CV}
        stress_ev = [_ev("edge", e, 10, 0.0, lead_multiplier=round(min(10.0, 1 + Z90 * er[e]["lead_cv"] * 2), 2)) for e in lanes]
        down = sorted({c for e in lanes for c in cx.demand_nodes if c in cx.feat.downstream.get(e.split("->")[1], set())})
        extra = sum(max(0.0, (G.nodes[c].get("demand") or 0.0) * 2) for c in down)

        def buffer(H, down=down):
            for c in down:
                H.nodes[c]["stock"] = (H.nodes[c].get("stock") or 0.0) + (H.nodes[c].get("demand") or 0.0) * 2
        fixes = [Fix("buffer", "Add 2 days of stock downstream of the volatile lanes", f"+{units(extra)} units at {', '.join(down[:4])}.",
                     buffer, extra * (PREPO_COST + HOLDING_PER_DAY * cx.horizon))] if down else []
        out.append(_evaluate(
            cx, "lead_time", f"{len(lanes)} high-variability lane(s)", ends, lanes, SURGE_PROB, "10-day P90 lead-time slip on the volatile lanes",
            stress_ev, evidence, f"{len(lanes)} lane(s) carrying at least {100 * CV_FLOW_SHARE:.0f}% of flow have a lead-time CV of "
            f"{HIGH_CV:.2f} or more, so delivery dates swing widely.", "Mode (sea / rail) and long distances make transit times unpredictable.",
            fixes))
    return out


# ---------------------------------------------------------------- 6. route fragility
def detect_routes(cx: Ctx, skip: set[str]) -> list[dict]:
    G, er = cx.G, cx.feat.erec
    out = []
    weather = cx.weather or {}
    for e, r in sorted(er.items(), key=lambda kv: -kv[1]["loss_if_down"]):
        if len(out) >= MAX_PER_TYPE or e in skip:
            continue
        u, v = e.split("->")
        if G.nodes[u].get("backup") or cx.base["flow"].get((u, v), 0.0) <= 0:
            continue
        wx = weather.get(e)
        premium = _alt_premium(cx, u, v)
        reasons, prob = [], None
        if FRAGILE_LOSS <= r["loss_if_down"] < SPOF_LOSS:
            reasons.append(f"blocking it loses {100 * r['loss_if_down']:.0f}% of daily demand: the alternates are too thin")
        if premium is not None and premium >= ALT_PREMIUM and r["flow_share"] >= CV_FLOW_SHARE:
            reasons.append(f"the best alternate route costs {100 * premium:.0f}% more per unit")
        if wx and wx.get("peak_risk", 0) >= WEATHER_FLAG:
            reasons.append(f"forecast weather risk peaks at {wx['peak_risk']:.2f} ({wx.get('reason', '')})".rstrip(" ()"))
            prob = float(wx["peak_risk"])
        if not reasons:
            continue
        ends = [x for x in (u, v) if x in skip]
        if ends and not wx:
            continue
        out.append(_lane_finding(cx, e, "route_fragility", f"Lane {e} is fragile", f"Lane {e}: " + "; ".join(reasons) + ".",
                                 "Few lanes connect these tiers, so traffic cannot move to an equivalent route.", probability=prob,
                                 extra_evidence={"alternate_cost_premium_pct": _r(100 * premium, 0) if premium is not None else None,
                                                 "weather": wx}))
    return out


def _alt_premium(cx: Ctx, u: str, v: str) -> float | None:
    """Cost premium of the cheapest supplier->v path that avoids lane u->v, vs the cheapest path using it."""
    G = cx.G
    srcs = [s for s, d in G.nodes(data=True) if d["kind"] == "supplier" and not d.get("backup")]
    if not srcs:
        return None
    try:
        with_lane = nx.multi_source_dijkstra_path_length(G, srcs, weight="cost").get(v)
        H = nx.restricted_view(G, [], [(u, v)])
        without = nx.multi_source_dijkstra_path_length(H, srcs, weight="cost").get(v)
    except nx.NetworkXException:
        return None
    if with_lane is None or without is None or with_lane <= 0:
        return None
    return max(0.0, without / with_lane - 1)


# ---------------------------------------------------------------- 7. regional imbalance + bullwhip
def detect_regional(cx: Ctx) -> list[dict]:
    G = cx.G
    regions = cx.feat.regions
    if len({regions[n] for n in G}) < 2:
        return []
    out = []
    by_region: dict[str, list[str]] = {}
    for c in cx.demand_nodes:
        by_region.setdefault(regions[c], []).append(c)
    for reg, cs in sorted(by_region.items()):
        dem = sum(G.nodes[c]["demand"] for c in cs)
        if dem < REGION_MIN_SHARE * cx.total:
            continue
        inflow = {c: sum(cx.base["flow"].get((p, c), 0.0) for p in G.predecessors(c)) for c in cs}
        imported = sum(cx.base["flow"].get((p, c), 0.0) for c in cs for p in G.predecessors(c) if regions[p] != reg)
        got = sum(inflow.values()) or 1.0
        share = imported / got
        if share < IMPORT_SHARE:
            continue
        lanes = [f"{p}->{c}" for c in cs for p in G.predecessors(c) if regions[p] != reg and cx.base["flow"].get((p, c), 0.0) > 0]
        local = [w for w, d in G.nodes(data=True) if d["kind"] == "warehouse" and regions[w] == reg]
        evidence = {"region": reg, "region_demand_units_per_day": _r(dem, 0), "region_demand_share_pct": _r(100 * dem / cx.total, 1),
                    "imported_share_pct": _r(100 * share, 0), "inbound_lanes": lanes, "local_warehouses": local}
        fixes = []
        hub = max(cs, key=lambda c: G.nodes[c]["demand"])
        if local:
            w = local[0]

            def regional(H, w=w, cs=cs, dem=dem):
                for c in cs:
                    if H.has_edge(w, c):
                        H.edges[w, c]["capacity"] += G.nodes[c]["demand"]
                    else:
                        _lane(H, w, c, G.nodes[c]["demand"])
                H.nodes[w]["capacity"] = (H.nodes[w].get("capacity") or 0.0) + dem * 0.5
                for p in list(H.predecessors(w)):
                    H.edges[p, w]["capacity"] += dem * 0.5 / max(1, H.in_degree(w))
            fixes.append(Fix("regional_dc", f"Serve {reg} from {w}", f"Lanes from {w} to {', '.join(cs[:4])} and +{units(dem * 0.5)} units/day.",
                             regional, LANE_SETUP_INR * len(cs) + dem * 0.5 * cx.horizon * CAPACITY_INR))
        else:
            facs = [f for f, d in G.nodes(data=True) if d["kind"] == "factory"]
            if facs:
                fac = min(facs, key=lambda f: _km(G, f, hub))

                def new_dc(H, fac=fac, cs=cs, dem=dem, reg=reg):
                    wid = f"DC_{reg}"
                    d = H.nodes[hub]
                    H.add_node(wid, kind="warehouse", name=f"New {reg} DC", city=d.get("city", ""), lat=d["lat"] + 0.1, lon=d["lon"] - 0.1,
                               capacity=dem * 0.6, stock=0.0, demand=0.0, reliability=0.95, backup=False)
                    _lane(H, fac, wid, dem * 0.6)
                    H.nodes[fac]["capacity"] = (H.nodes[fac].get("capacity") or 0.0) + dem * 0.3
                    for c in cs:
                        _lane(H, wid, c, G.nodes[c]["demand"])
                fixes.append(Fix("new_dc", f"Open a {reg} DC fed by {fac}", f"New DC near {hub} with {units(dem * 0.6)} units/day.",
                                 new_dc, LANE_SETUP_INR * (len(cs) + 1) + dem * 0.6 * cx.horizon * CAPACITY_INR))
        out.append(_evaluate(
            cx, "regional_imbalance", f"{reg.capitalize()} region imports {100 * share:.0f}% of its demand", cs, lanes, SURGE_PROB,
            f"{OUTAGE_DAYS}-day 50% cut on lanes into the {reg} region", [_ev("edge", e, OUTAGE_DAYS, 0.5) for e in lanes], evidence,
            f"The {reg} region holds {100 * dem / cx.total:.0f}% of demand but {100 * share:.0f}% of it is shipped in from other regions.",
            "Distribution capacity sits outside the region; long inter-regional lanes carry most of its supply.", fixes))
    return out


def detect_bullwhip(cx: Ctx) -> list[dict]:
    G = cx.G
    tiers = {k: [n for n, d in G.nodes(data=True) if d["kind"] == k and not d.get("backup")] for k in ("supplier", "factory", "warehouse")}
    base_cv = float(np.mean([G.nodes[c].get("demand_cv") or features.DEFAULT_DEMAND_CV for c in cx.demand_nodes])) if cx.demand_nodes else 0.0
    if base_cv <= 0:
        return []
    cv, chain, below = base_cv, [], cx.demand_nodes
    for tier in ("warehouse", "factory", "supplier"):
        ups = tiers[tier]
        if not ups:
            continue
        leads = [G.edges[u, v]["lead"] for u in ups for v in G.successors(u) if v in below]
        ratio = bullwhip_ratio(float(np.mean(leads)) if leads else 1.0)
        cv = min(1.5, cv * math.sqrt(ratio))
        chain.append({"tier": tier, "variance_ratio_vs_tier_below": _r(ratio, 2), "order_cv": _r(cv, 3)})
        below = ups
    if not chain:
        return []
    amp = (cv / base_cv) ** 2
    if amp < BULLWHIP_FLAG:
        return []
    top = chain[-1]["tier"]
    ups = tiers[top]
    thr = sum(cx.base["throughput"].get(n, 0.0) for n in ups)
    cap = sum(G.nodes[n].get("capacity") or 0.0 for n in ups)
    peak_orders = thr * (1 + Z90 * cv)
    shortfall = max(0.0, peak_orders - cap)
    evidence = {"demand_cv": _r(base_cv, 3), "tiers": chain, "variance_amplification": _r(amp, 2),
                "upstream_tier": top, "upstream_throughput_units_per_day": _r(thr, 0), "upstream_capacity_units_per_day": _r(cap, 0),
                "p90_order_rate_units_per_day": _r(peak_orders, 0), "headroom_shortfall_units_per_day": _r(shortfall, 0),
                "bound": "1 + 2L/p + 2L^2/p^2 per tier (Chen, Drezner, Ryan & Simchi-Levi 2000), p = 7-day forecast window"}
    swing = min(1.0, Z90 * base_cv)
    evs = [_ev("demand", c, OUTAGE_DAYS, swing) for c in cx.demand_nodes]
    fixes = []
    if shortfall > 0:
        def headroom(H, ups=ups, shortfall=shortfall, thr=thr):
            for n in ups:
                share = (cx.base["throughput"].get(n, 0.0) / thr) if thr else 1 / len(ups)
                H.nodes[n]["capacity"] = (H.nodes[n].get("capacity") or 0.0) + shortfall * share
        fixes.append(Fix("headroom", f"Add {units(shortfall)} units/day of {top} headroom", f"Covers the P90 order rate "
                         f"({units(peak_orders)} units/day) the {top} tier sees.", headroom, shortfall * cx.horizon * CAPACITY_INR))
    extra = sum((G.nodes[c].get("demand") or 0.0) * swing * OUTAGE_DAYS for c in cx.demand_nodes)

    def buffer(H):
        for c in cx.demand_nodes:
            H.nodes[c]["stock"] = (H.nodes[c].get("stock") or 0.0) + (H.nodes[c].get("demand") or 0.0) * swing * OUTAGE_DAYS
    fixes.append(Fix("buffer", "Hold a P90 demand-swing buffer at demand nodes", f"+{units(extra)} units in total.", buffer,
                     extra * (PREPO_COST + HOLDING_PER_DAY * cx.horizon)))
    return [_evaluate(
        cx, "bullwhip", f"Order variability amplifies {amp:.1f}x from customers to {top}s", ups, [], SURGE_PROB,
        f"{OUTAGE_DAYS}-day P90 demand swing (+{100 * swing:.0f}%)", evs, evidence,
        f"Demand varies by {100 * base_cv:.0f}% day to day, but with forecast-based ordering over the tier lead times the {top} "
        f"tier sees order variance {amp:.1f}x larger: a P90 order rate of {units(peak_orders)} units/day against {units(cap)} "
        f"units/day of capacity.",
        "Each tier forecasts from the orders of the tier below over long lead times (bullwhip effect); sharing point-of-sale "
        "data upstream (collaborative forecasting) would shrink the amplification, which the simulator does not model.", fixes)]


# ---------------------------------------------------------------- 8. hidden failure pairs
def detect_pairs(cx: Ctx) -> list[dict]:
    G = cx.G
    res = chaos.chaos_find(G, top=3, duration=OUTAGE_DAYS)
    out = []
    for p in res["hidden_pairs"]:
        a, b = p["pair"]
        nodes = sorted({x for t in (a, b) for x in t.split("->")})
        rel = lambda t: float(G.nodes[t].get("reliability", 0.9)) if "->" not in t else min(  # noqa: E731
            float(G.nodes[x].get("reliability", 0.9)) for x in t.split("->"))
        same = len({cx.feat.regions[x] for x in nodes}) == 1
        prob = min(1.0, (1 - rel(a)) * (1 - rel(b)) * (3 if same else 1))
        evs = [_ev("edge" if "->" in t else "node", t, OUTAGE_DAYS) for t in (a, b)]
        evidence = {"pair": [a, b], "joint_unmet_units": p["unmet"], "synergy_units": p["synergy"], "same_region": same,
                    "outage_days": OUTAGE_DAYS}
        key = max((a, b), key=lambda t: cx.feat.erec[t]["loss_if_down"] if "->" in t else cx.feat.nrec[t]["loss_if_down"])
        fixes = []
        partner = b if key == a else a
        if "->" not in key and _nearest_peer(G, key, {partner}):
            peer = _nearest_peer(G, key, {partner})
            fixes.append(Fix("redundancy", f"Qualify {peer} as a second site for {key}", f"Lanes and spare capacity so {peer} can take "
                             f"over {key}'s flows (it is not part of the failing pair).",
                             lambda H, key=key, partner=partner: add_redundancy(H, key, cx.base, {partner}),
                             LANE_SETUP_INR * (G.out_degree(key) + G.in_degree(key)) + cx.base["throughput"].get(key, 0.0) * cx.horizon * CAPACITY_INR * 0.25))
        elif "->" in key:
            u, v = key.split("->")
            peer = _nearest_peer(G, u, exclude={v, partner})
            if peer and not G.has_edge(peer, v):
                f = cx.base["flow"].get((u, v), 0.0)
                fixes.append(Fix("alt_lane", f"Open lane {peer}->{v}", f"Parallel lane with {units(f)} units/day.",
                                 lambda H, peer=peer, v=v, f=f: _lane(H, peer, v, max(f, 1.0)), LANE_SETUP_INR))
        out.append(_evaluate(
            cx, "hidden_pair", f"{a} + {b} fail far worse together", nodes, [t for t in (a, b) if "->" in t], prob,
            f"simultaneous {OUTAGE_DAYS}-day loss of {a} and {b}", evs, evidence,
            f"Each failure alone is absorbed, but together {a} and {b} lose {units(p['unmet'])} units over {OUTAGE_DAYS} days, "
            f"{units(p['synergy'])} more than the sum of their separate losses (Chaos Finder).",
            "They back each other up: the redundancy is only one level deep." + (" Both sit in the same region, so one storm can hit both." if same else ""),
            fixes))
    return out


# ---------------------------------------------------------------- health score
def health(G: nx.DiGraph) -> dict:
    if G.number_of_nodes() == 0 or total_demand(G) <= 0:
        return {"score": None, "breakdown": []}
    ctx = features.context(G)
    base = solve_flow(G)
    sites = [n for n, d in G.nodes(data=True) if not is_demand(d["kind"]) and not d.get("backup") and (d.get("capacity") or 0) > 0]
    flow = {n: base["throughput"].get(n, 0.0) for n in sites}
    tot = sum(flow.values()) or 1.0
    ok_flow = sum(f for n, f in flow.items() if f / G.nodes[n]["capacity"] <= SATURATION_UTIL)
    dem = [(n, d["demand"]) for n, d in G.nodes(data=True) if is_demand(d["kind"]) and (d.get("demand") or 0) > 0]
    good = 0.0
    for n, q in dem:
        r = ctx.nrec[n]
        lead = max(1.0, r["replenish_lead"])
        target = SAFETY_FACTOR * lead * (1 + (r["lead_cv_in"] or features.DEFAULT_LEAD_CV))
        if target <= r["cover_days"] <= max(OVERSTOCK_DAYS, OVERSTOCK_X * target):
            good += q
    dsum = sum(q for _, q in dem) or 1.0
    lanes = [(base["flow"].get((u, v), 0.0), ctx.erec[f"{u}->{v}"]["lead_cv"]) for u, v in G.edges]
    lf = sum(f for f, _ in lanes) or 1.0
    wcv = sum(f * cv for f, cv in lanes) / lf
    parts = {
        "resilience": (chaos.resilience_score(G), "Chaos Finder resilience (worst failure pairs)"),
        "capacity_headroom": (100 * ok_flow / tot, f"share of flow through sites at or below {100 * SATURATION_UTIL:.0f}% utilisation"),
        "inventory_health": (100 * good / dsum, "demand-weighted share of demand nodes with cover between the thin and overstock thresholds"),
        "concentration": (100 * (1 - ctx.network["supplier_hhi"]), "100 x (1 - supplier HHI)"),
        "lead_time_risk": (100 * max(0.0, 1 - wcv / 0.5), "100 x (1 - flow-weighted lead-time CV / 0.5)"),
    }
    breakdown = [{"key": k, "label": k.replace("_", " ").capitalize(), "score": _r(v, 1), "weight": HEALTH_WEIGHTS[k], "detail": d}
                 for k, (v, d) in parts.items()]
    return {"score": _r(sum(b["score"] * b["weight"] for b in breakdown), 1), "breakdown": breakdown}


# ---------------------------------------------------------------- orchestration
def build_sections(result: dict) -> list[dict]:
    """Template narration for the summary and every finding (rendered from their evidence only)."""
    h = result["health"]
    counts = result["counts"]["by_level"]
    lvl = ", ".join(f"{v} {k}" for k, v in counts.items() if v)
    top = result["findings"][0] if result["findings"] else None
    summary = (f"Supply chain health {h['score']:.1f} / 100 (simulated); {len(result['findings'])} finding(s): {lvl or 'none'}."
               + (f" Most severe: {top['title']} (severity {top['severity']:.1f})." if top else "")
               + (f" Applying the top fix of every finding lifts the health score to {h['after_fixes']['score']:.1f}."
                  if h.get("after_fixes") and h["after_fixes"].get("score") is not None else ""))
    sections = [{"key": "summary", "title": "Summary", "paragraphs": [summary], "bullets": [],
                 "evidence": {"health": h, "counts": result["counts"]}}]
    for f in result["findings"]:
        sections.append({"key": f["id"], "title": f["title"], "paragraphs": [f["why"], f["root_cause"]], "bullets": [f["business"]],
                         "evidence": {"impact": f["impact"], "evidence": f["evidence"], "fixes": f["fixes"], "stress": f["stress"],
                                      "severity": f["severity"], "probability": f["probability"], "model_constants": result["constants"]}})
    return sections


def analyze(G: nx.DiGraph, horizon: int = HORIZON, weather: dict | None = None, narrator: Callable | None = None,
            progress: Callable[[str, int, int], None] | None = None) -> dict:
    """Run every detector on G. Never raises on small or empty networks."""
    t0 = time.perf_counter()
    constants = {"saturation_util_pct": 100 * SATURATION_UTIL, "spof_loss_pct": 100 * SPOF_LOSS, "safety_factor": SAFETY_FACTOR,
                 "hhi_flag": HHI_FLAG, "outage_days": OUTAGE_DAYS, "supplier_outage_days": SUPPLIER_OUTAGE_DAYS, "surge_days": SURGE_DAYS,
                 "horizon_days": horizon, "overstock_days": OVERSTOCK_DAYS, "overstock_x": OVERSTOCK_X, "health_scale_max": 100,
                 "lead_flag_days": LEAD_FLAG_DAYS, "high_cv": HIGH_CV}
    formula = ("severity = 100 x [0.45 x min(1, impact share / 0.10) + 0.35 x min(1, probability x revenue at risk / 1 day of "
               "revenue) + 0.20 x share of demand nodes affected]; levels critical >= 70, high >= 45, medium >= 25")
    if G.number_of_nodes() == 0 or total_demand(G) <= 0 or not any(d.get("kind") == "supplier" for _, d in G.nodes(data=True)):
        note = "The network is empty." if G.number_of_nodes() == 0 else "The network needs at least one supplier and some demand to analyse."
        return {"status": "empty", "note": note, "findings": [], "health": {"score": None, "breakdown": []},
                "counts": {"by_type": {}, "by_level": {}}, "severity_formula": formula, "sections": [], "constants": constants}
    cx = Ctx(G, horizon, weather)
    steps: list[tuple[str, Callable[[], list[dict]]]] = []
    flagged: dict[str, set] = {"conc": set(), "spof": set()}

    def conc():
        out, fl = detect_concentration(cx)
        flagged["conc"] = fl
        return out

    def spof():
        out, fl = detect_spof(cx, flagged["conc"])
        flagged["spof"] = fl
        return out

    steps = [("Capacity saturation and shadow prices", lambda: detect_saturation(cx)), ("Supplier concentration", conc),
             ("Single points of failure", spof), ("Inventory risk", lambda: detect_inventory(cx)),
             ("Lead-time chain", lambda: detect_lead_time(cx)),
             ("Route fragility", lambda: detect_routes(cx, flagged["spof"] | flagged["conc"])),
             ("Regional imbalance", lambda: detect_regional(cx)), ("Bullwhip", lambda: detect_bullwhip(cx)),
             ("Hidden failure pairs", lambda: detect_pairs(cx))]
    findings: list[dict] = []
    errors = []
    for i, (label, fn) in enumerate(steps):
        if progress:
            progress(label, i, len(steps) + 1)
        try:
            findings.extend(fn())
        except Exception as exc:  # noqa: BLE001 - one detector failing must not hide the others
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
    findings.sort(key=lambda f: (-f["severity"], f["type"], f["title"]))
    for i, f in enumerate(findings, start=1):
        f["id"] = f"F{i:02d}"
        for fx in f["fixes"]:
            fx["finding"] = f["id"]
    if progress:
        progress("Health score before and after fixes", len(steps), len(steps) + 1)
    h = health(G)
    fixed = G.copy()
    applied = []
    for f in findings:  # replay the top fix of every finding on one copy
        fx = f.get("_fix_objs", {}).get(f["fixes"][0]["id"]) if f["fixes"] else None
        if fx:
            try:
                fx.apply(fixed)
                applied.append(f"{f['id']}: {f['fixes'][0]['label']}")
            except Exception:  # noqa: BLE001
                continue
    for f in findings:
        f.pop("_fix_objs", None)
    after = health(fixed) if applied else dict(h)
    h["after_fixes"] = {**after, "fixes_applied": applied}
    by_type: dict[str, int] = {}
    by_level = {name: 0 for _, name in LEVELS}
    for f in findings:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
        by_level[f["severity_level"]] += 1
    result = {"status": "ok", "findings": findings, "health": h, "counts": {"by_type": by_type, "by_level": by_level},
              "severity_formula": formula, "constants": constants, "errors": errors, "surge_pct": _r(100 * cx.surge, 0),
              "elapsed_s": _r(time.perf_counter() - t0, 2), "label": "simulated"}
    template = build_sections(result)
    if narrator is None:
        from llm.parser import narrate_sections

        narrator = narrate_sections
    narr = narrative.narrate({"health": h, "counts": result["counts"], "findings": [{k: f[k] for k in ("id", "title", "impact", "evidence", "fixes", "why", "root_cause", "business", "severity")} for f in findings], "constants": constants},
                             template, narrator)
    sec = {s["key"]: s for s in narr["sections"]}
    for f in findings:
        s = sec.get(f["id"])
        if s and narr["source"] == "llm":
            f["why"], f["root_cause"] = (s["paragraphs"] + [f["why"], f["root_cause"]])[:2]
            f["business"] = (s["bullets"] or [f["business"]])[0]
    result.update(summary=sec["summary"]["paragraphs"][0], sections=narr["sections"], narrative_source=narr["source"],
                  narrative_rejected=narr["rejected"])
    return result
