"""Recovery planner: multi-day PuLP linear program over the disruption window. Owner: B.

Decision variables per day t in the window (first event start .. last event end, inside the horizon):
    x[e,t]    units on lane e: <= its baseline flow (today's allocation); with lever "reroute" <= full capacity
              x the lane's remaining-capacity factor
    ot[v,t]   overtime units at factory/warehouse v       (lever "overtime": <= 30% of capacity)
    sh[a,b,t] production moved from factory a to b       (lever "production_shift": <= 25% of either plant)
    pre[w]    units pre-positioned at warehouse w before the window from unaffected factories' finished-goods
              stock, drawn as d[w,t]                     (lever "safety_stock": <= PREPO_DAYS x capacity per
                                                          warehouse, <= PREPO_SOURCE_SHARE of that stock)
    y         backup contract triggered                  (lever "backup": binary, one-off fee; supply opens
                                                          BACKUP_ACTIVATION_DAYS after the disruption starts)
    s[c,t], u[c,t]  demand-node stock drawn / demand unmet (demand nodes = retailers and customers)
Constraints: supplier output <= capacity; factory flow conservation with capacity + overtime + shift-in - shift-out;
warehouse inflow + pre-positioned draws = outflow <= capacity + overtime; a demand node keeps (inflow - outflow) and
forwards the rest (outflow <= its capacity, 0 = no limit): kept + stock + unmet = demand, kept <= demand (no restocking,
as in core.sim); cumulative stock draws <= starting stock.
Variable and constraint names use node indices, never raw ids, so any user-supplied id is safe for PuLP.
Objective (INR):  flow cost (backup lanes x1.5) + overtime + shift + inventory (transfer + holding) + backup fee
                  + W_STOCK_DRAW x stock drawn + w_unmet x unmet + w_co2 x kg CO2.
With no levers this is "do nothing": today's lane allocations, no backup, demand-node stock absorbs the gap.
Solved with CBC through PuLP. A plan reports its incremental cost against normal operations, unmet units,
recovery days, CO2, delay (core.delay) and the capacity changes the fix-safety check needs.
"""
from __future__ import annotations

from typing import Iterable

import networkx as nx
import pulp

from core.delay import arrival_lead, delay_stats
from core.sim import BACKUP_ACTIVATION_DAYS, BACKUP_COST_FACTOR, _active_state, lead_factors, solve_flow, spike_baseline
from node_types import is_demand, total_demand
from schemas import Event

LEVERS = ("reroute", "backup", "overtime", "safety_stock", "production_shift")

W_UNMET = 10_000.0  # INR per unit not delivered (lost margin + goodwill; above the 4,200 list price)
W_STOCK_DRAW = 250.0  # INR per unit of demand-node stock consumed (above any path's freight, so delivery comes first)
W_CO2 = 4.0  # INR per kg CO2 (~ USD 50/t social cost of carbon)

OVERTIME_MAX = 0.30
OVERTIME_COST = 45.0
SHIFT_MAX = 0.25
SHIFT_COST = 20.0
PREPO_DAYS = 2.0  # max pre-positioned stock per warehouse, in days of its capacity
PREPO_COST = 35.0  # transfer + handling per unit
PREPO_SOURCE_SHARE = 0.5  # at most half of the unaffected factories' finished-goods stock can be moved
PREPO_CO2_KG = 2.0  # per unit moved (average lane)
HOLDING_PER_DAY = 1.5
BACKUP_FEE = 150_000.0
EPS = 0.5


def disruption_window(events: Iterable[Event], horizon: int) -> list[int]:
    events = list(events)
    if not events:
        return []
    t0 = min(e.start for e in events)
    t1 = min(horizon - 1, max(e.start + e.duration - 1 for e in events))
    return list(range(t0, t1 + 1)) if t0 < horizon else []


def baseline(G: nx.DiGraph) -> dict:
    """Undisrupted flow, freight cost per delivered unit, and arrival lead times."""
    base = solve_flow(G)
    demand = total_demand(G)
    return {"flow": base, "cost_per_unit": base["cost"] / demand if demand else 0.0, "lead": arrival_lead(G, base["flow"])}


def lane_cost(G: nx.DiGraph, u: str, v: str) -> float:
    return G.edges[u, v]["cost"] * (BACKUP_COST_FACTOR if G.nodes[u].get("backup") else 1.0)


def _ix(G: nx.DiGraph) -> dict[str, int]:
    """Stable node index used in LP names (ids may contain characters PuLP rewrites, causing name clashes)."""
    return {n: i for i, n in enumerate(G)}


def safety_stock_lever(prob: pulp.LpProblem, G: nx.DiGraph, days: list[int], down: set[str]) -> tuple[dict, dict, pulp.LpAffineExpression]:
    """Inventory buffer lever: pre[w] units pre-positioned at warehouse w (<= PREPO_DAYS x capacity), drawn as d[w,t].

    Units come from finished-goods stock at factories that are not hit (<= PREPO_SOURCE_SHARE of it).
    Returns (pre, draw, cost_expr); the caller adds draw[w,t] to warehouse w's supply on day t.
    """
    ix = _ix(G)
    whs = [n for n, d in G.nodes(data=True) if d["kind"] == "warehouse" and n not in down]
    source = PREPO_SOURCE_SHARE * sum(d.get("stock") or 0.0 for n, d in G.nodes(data=True) if d["kind"] == "factory" and n not in down)
    pre = {w: pulp.LpVariable(f"pre_{ix[w]}", 0, PREPO_DAYS * (G.nodes[w].get("capacity") or 0.0)) for w in whs}
    draw = {(w, t): pulp.LpVariable(f"draw_{ix[w]}_{t}", 0) for w in whs for t in days}
    for w in whs:
        prob += pulp.lpSum(draw[w, t] for t in days) <= pre[w], f"prepo_{ix[w]}"
    if pre:  # a network without warehouses has nothing to pre-position into
        prob += pulp.lpSum(pre.values()) <= source, "prepo_source"
    cost = (PREPO_COST + HOLDING_PER_DAY * len(days)) * pulp.lpSum(pre.values())
    return pre, draw, cost


def production_shift_lever(G: nx.DiGraph, days: list[int]) -> tuple[dict, pulp.LpAffineExpression]:
    """Production shift lever: sh[a,b,t] units/day of factory a's plan made at factory b instead.

    Bounds: <= SHIFT_MAX x capacity of a (the plan being moved) and of b (temporary lines). Returns (sh, cost_expr).
    """
    ix = _ix(G)
    facs = [n for n, d in G.nodes(data=True) if d["kind"] == "factory"]
    cap = lambda n: G.nodes[n].get("capacity") or 0.0  # noqa: E731
    sh = {(a, b, t): pulp.LpVariable(f"sh_{ix[a]}_{ix[b]}_{t}", 0, SHIFT_MAX * min(cap(a), cap(b)))
          for a in facs for b in facs if a != b for t in days}
    return sh, SHIFT_COST * pulp.lpSum(sh.values())


def optimize_plan(
    G: nx.DiGraph,
    events: Iterable[Event],
    levers: Iterable[str] = LEVERS,
    horizon: int = 30,
    w_unmet: float = W_UNMET,
    w_co2: float = W_CO2,
) -> dict:
    """Solve the recovery LP with the given levers. Returns the plan (see module docstring for the model):

    {levers, window, status, cost, cost_breakdown, unmet, recovery_days, co2, delay, daily_flows,
     capacity_delta, rerouted_lanes, backup_used, inventory_actions, production_actions}
    """
    events = list(events)
    levers = set(levers)
    unknown = levers - set(LEVERS)
    if unknown:
        raise ValueError(f"unknown levers {sorted(unknown)}")
    days = disruption_window(events, horizon)
    base = baseline(G)
    plan = {"levers": sorted(levers), "window": [days[0], days[-1]] if days else None, "status": "Optimal",
            "cost": 0.0, "cost_breakdown": {}, "unmet": 0.0, "stock_drawn": 0.0, "recovery_days": 0, "co2": 0.0,
            "delay": {"avg_days": 0.0, "p90_days": 0.0, "per_customer": {}}, "daily_flows": [],
            "capacity_delta": {}, "rerouted_lanes": [], "backup_used": False,
            "inventory_actions": [], "production_actions": []}
    if not days:
        return plan

    kind = {n: d["kind"] for n, d in G.nodes(data=True)}
    ix = _ix(G)
    edges = list(G.edges)
    spike = spike_baseline(G, events, horizon)
    states = {t: _active_state(events, t, spike) for t in days}  # (node factor, edge factor, demand multiplier)
    nf = lambda n, t: max(0.0, min(1.0, states[t][0].get(n, 1.0)))  # noqa: E731
    ef = lambda e, t: max(0.0, min(1.0, states[t][1].get(e, 1.0)))  # noqa: E731
    dem = {(c, t): (G.nodes[c].get("demand") or 0.0) * states[t][2].get(c, 1.0) for c in G if is_demand(kind[c]) for t in days}
    contract_day = days[0] + BACKUP_ACTIVATION_DAYS
    reroute = "reroute" in levers

    def lane_cap(e, t):
        cap = G.edges[e]["capacity"] * ef(e, t)
        return cap if reroute else min(cap, base["flow"]["flow"].get(e, 0.0))

    prob = pulp.LpProblem("recovery", pulp.LpMinimize)
    x = {(e, t): pulp.LpVariable(f"x_{ix[e[0]]}_{ix[e[1]]}_{t}", 0, lane_cap(e, t)) for e in edges for t in days}
    ot = {(v, t): pulp.LpVariable(f"ot_{ix[v]}_{t}", 0, OVERTIME_MAX * (G.nodes[v].get("capacity") or 0.0) * nf(v, t))
          for v in G if kind[v] in ("factory", "warehouse") for t in days} if "overtime" in levers else {}
    down_nodes = {e.target for e in events if e.type == "node" and e.severity >= 1}
    pre, draw, prepo_cost = safety_stock_lever(prob, G, days, down_nodes) if "safety_stock" in levers else ({}, {}, 0)
    sh, shift_cost = production_shift_lever(G, days) if "production_shift" in levers else ({}, 0)
    y = pulp.LpVariable("backup_contract", cat="Binary") if "backup" in levers else None
    s = {(c, t): pulp.LpVariable(f"s_{ix[c]}_{t}", 0) for (c, t) in dem}
    u = {(c, t): pulp.LpVariable(f"u_{ix[c]}_{t}", 0) for (c, t) in dem}
    total = sum(dem.values()) or 0.0

    def inflow(n, t):
        return pulp.lpSum(x[(p, n), t] for p in G.predecessors(n))

    def outflow(n, t):
        return pulp.lpSum(x[(n, q), t] for q in G.successors(n))

    for t in days:
        for n, d in G.nodes(data=True):
            cap = (d.get("capacity") or 0.0) * nf(n, t)
            k = kind[n]
            i = ix[n]
            if k == "supplier":
                if d.get("backup"):
                    cap = cap * y if (y is not None and t >= contract_day) else 0
                prob += outflow(n, t) <= cap, f"sup_{i}_{t}"
            elif k == "factory":
                prob += inflow(n, t) == outflow(n, t), f"bal_{i}_{t}"
                extra = ot.get((n, t), 0)
                if sh:
                    shift_in = pulp.lpSum(sh[a, n, t] for a in G if kind[a] == "factory" and a != n)
                    shift_out = pulp.lpSum(sh[n, b, t] for b in G if kind[b] == "factory" and b != n)
                    if nf(n, t) > 0:
                        prob += outflow(n, t) <= cap + extra + shift_in - shift_out, f"cap_{i}_{t}"
                    else:  # a plant that is down can hand its plan over but makes nothing itself
                        prob += outflow(n, t) <= 0, f"cap_{i}_{t}"
                else:
                    prob += outflow(n, t) <= cap + extra, f"cap_{i}_{t}"
            elif k == "warehouse":
                prob += inflow(n, t) + draw.get((n, t), 0) == outflow(n, t), f"bal_{i}_{t}"
                prob += outflow(n, t) <= cap + ot.get((n, t), 0), f"cap_{i}_{t}"
            else:  # demand node (retailer / customer): keeps inflow - outflow, forwards the rest
                kept = inflow(n, t) - outflow(n, t)
                if G.out_degree(n):
                    prob += outflow(n, t) <= (d.get("capacity") or total) * nf(n, t), f"fwd_{i}_{t}"
                    prob += kept >= 0, f"keep_{i}_{t}"
                prob += kept <= dem[n, t], f"recv_{i}_{t}"
                prob += kept + s[n, t] + u[n, t] == dem[n, t], f"dem_{i}_{t}"
                prob += pulp.lpSum(s[n, tt] for tt in days if tt <= t) <= (d.get("stock") or 0.0), f"stock_{i}_{t}"

    transport = pulp.lpSum(lane_cost(G, *e) * x[e, t] for e in edges for t in days)
    overtime = OVERTIME_COST * pulp.lpSum(ot.values())
    co2_kg = pulp.lpSum(G.edges[e]["co2"] * x[e, t] for e in edges for t in days) + PREPO_CO2_KG * pulp.lpSum(pre.values())
    prob += (transport + overtime + prepo_cost + shift_cost + (BACKUP_FEE * y if y is not None else 0)
             + W_STOCK_DRAW * pulp.lpSum(s.values()) + w_unmet * pulp.lpSum(u.values()) + w_co2 * co2_kg)

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=30))
    plan["status"] = pulp.LpStatus[status]
    if plan["status"] != "Optimal":
        raise RuntimeError(f"recovery LP not solved: {plan['status']}")

    val = lambda v: float(pulp.value(v) or 0.0)  # noqa: E731
    daily_flows = [{e: val(x[e, t]) for e in edges} for t in days]
    delivered = sum(val(inflow(c, t)) - val(outflow(c, t)) for (c, t) in dem)
    breakdown = {
        "extra_freight": max(0.0, val(transport) - base["cost_per_unit"] * delivered),
        "overtime": val(overtime),
        "inventory": val(prepo_cost) if pre else 0.0,
        "production_shift": val(shift_cost) if sh else 0.0,
        "backup_fee": BACKUP_FEE * val(y) if y is not None else 0.0,
    }
    shortfall_days = [t for t in days if any(val(s[c, t]) + val(u[c, t]) > EPS for c in G if is_demand(kind[c]))]

    cap_delta: dict[str, float] = {}
    for n in G:
        if kind[n] not in ("factory", "warehouse"):
            continue
        add = max((val(ot.get((n, t), 0)) + sum(val(sh[a, n, t]) for a in G if (a, n, t) in sh) for t in days), default=0.0)
        rem = max((sum(val(sh[n, b, t]) for b in G if (n, b, t) in sh) for t in days), default=0.0)
        if abs(add - rem) > EPS:
            cap_delta[n] = round(add - rem, 1)

    plan.update(
        cost=round(sum(breakdown.values()), 0),
        cost_breakdown={k: round(v, 0) for k, v in breakdown.items()},
        unmet=round(sum(val(v) for v in u.values()), 1),
        stock_drawn=round(sum(val(v) for v in s.values()), 1),
        recovery_days=(shortfall_days[-1] - days[0] + 1) if shortfall_days else 0,
        co2=round(val(co2_kg) / 1000, 2),
        delay=delay_stats(G, daily_flows, base["lead"], [lead_factors(events, t) for t in days]),
        daily_flows=daily_flows,
        capacity_delta=cap_delta,
        rerouted_lanes=sorted(f"{e[0]}->{e[1]}" for e in edges if any(val(x[e, t]) > base["flow"]["flow"].get(e, 0.0) + EPS for t in days)),
        backup_used=any(val(x[(b, q), t]) > EPS for b in G if G.nodes[b].get("backup") for q in G.successors(b) for t in days),
        inventory_actions=_inventory_actions(G, events, days, {w: val(v) for w, v in pre.items()}),
        production_actions=_production_actions(G, days, {k: val(v) for k, v in sh.items()}, nf),
    )
    return plan


def _disrupted_label(events: list[Event]) -> str:
    return ", ".join(sorted({e.target for e in events if e.type != "demand"})) or "the demand spike"


def _inventory_actions(G: nx.DiGraph, events: list[Event], days: list[int], pre: dict[str, float]) -> list[dict]:
    hit = {e.target for e in events if e.type == "node"}
    sources = sorted((n for n, d in G.nodes(data=True) if d["kind"] == "factory" and n not in hit),
                     key=lambda n: -(G.nodes[n].get("stock") or 0.0))
    actions = []
    for w, units in sorted(pre.items(), key=lambda kv: -kv[1]):
        if units <= EPS:
            continue
        actions.append({
            "node": w, "action": "pre-position", "units": round(units), "source": sources[0] if sources else None,
            "day": max(0, days[0] - 1),
            "reason": f"Finished goods staged at {w} cover outbound demand on days {days[0]}-{days[-1]} while "
                      f"{_disrupted_label(events)} is disrupted.",
        })
    return actions


def _production_actions(G: nx.DiGraph, days: list[int], sh: dict, nf) -> list[dict]:
    actions = []
    for a, b in sorted({(a, b) for (a, b, _t) in sh}):
        active = [(t, sh[a, b, t]) for t in days if sh.get((a, b, t), 0) > EPS]
        if not active:
            continue
        why = "is down" if nf(a, active[0][0]) == 0 else "is short of inputs"
        actions.append({
            "from_factory": a, "to_factory": b,
            "units_per_day": round(sum(v for _, v in active) / len(active)),
            "start_day": active[0][0], "duration": len(active),
            "reason": f"{a} {G.nodes[a].get('name', a)} {why}; {b} {G.nodes[b].get('name', b)} has spare capacity and unaffected inbound supply.",
        })
    return actions
