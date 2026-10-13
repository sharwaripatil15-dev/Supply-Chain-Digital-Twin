"""Day-by-day disruption simulator. Owner: A.

Model:
    Each day is a single-period min-cost flow (`solve_flow`) from suppliers to demand nodes (retailers and
    customers, see node_types.is_demand).
      * Node splitting: every non-demand node v becomes v_in -> v_out with capacity = its effective
        production/throughput capacity, so node limits are ordinary arc limits. A demand node gets v_in -> sink for
        its own demand and, if it ships on (a retailer feeding customers), v_in -> v_out limited by its capacity
        (0 = no limit).
      * Disruptions scale capacities: node/edge events multiply capacity by (1 - severity) (severity 1 = down);
        demand events multiply a demand node's demand by (1 + severity).
      * The backup supplier is closed unless `allow_backup`; its lanes cost 1.5x, so once open it is only used
        when cheaper primary capacity runs out. In `simulate` it opens BACKUP_ACTIVATION_DAYS after the first
        projected shortfall (contract activation lag).
      * A super-source -> super-sink bypass arc priced at `shortage_penalty` keeps the problem feasible; flow on
        it is unmet demand. Solved with OR-Tools SimpleMinCostFlow (integer units, cost in 0.1 INR).
    Day loop: apply active events -> solve flow (memoised per disruption state) -> demand-node stock absorbs any
    shortfall -> once stock is exhausted the remainder is unmet (a stockout). Customer stock is not refilled
    within the horizon (conservative). Flow is same-day: lead times enter through core.delay, not as shipping lag.
    Survival Clock = first day any demand node has unmet demand (its stockout day); horizon if none.
"""
from __future__ import annotations

from typing import Iterable, Mapping, TypedDict

import networkx as nx
from ortools.graph.python import min_cost_flow

from core.delay import arrival_lead, delay_stats, find_bottlenecks
from node_types import is_demand, total_demand
from schemas import Event

SUPER_SOURCE = "__SRC__"
SUPER_SINK = "__SINK__"
BACKUP_COST_FACTOR = 1.5
BACKUP_ACTIVATION_DAYS = 3
STRESS_UTILIZATION = 0.9
COST_SCALE = 10  # OR-Tools needs integer costs


class FlowResult(TypedDict):
    flow: dict[tuple[str, str], float]  # edge -> units shipped
    throughput: dict[str, float]  # non-demand node (or forwarding demand node) -> units processed
    served: dict[str, float]  # demand node -> units delivered to its own demand
    unmet: dict[str, float]  # demand node -> units short (before its stock is used)
    cost: float  # INR


def solve_flow(
    G: nx.DiGraph,
    down_nodes: Iterable[str] = (),
    down_edges: Iterable[tuple[str, str]] = (),
    node_factor: Mapping[str, float] | None = None,
    edge_factor: Mapping[tuple[str, str], float] | None = None,
    demand_multiplier: Mapping[str, float] | float = 1.0,
    allow_backup: bool = False,
    shortage_penalty: float = 1e5,
) -> FlowResult:
    """Single-period min-cost flow with node splitting (see module docstring).

    down_nodes / down_edges: capacity 0. node_factor / edge_factor: remaining capacity share in [0, 1]
    (partial disruption). demand_multiplier: per-demand-node dict or one float for all demand nodes.
    """
    node_factor = dict(node_factor or {})
    edge_factor = dict(edge_factor or {})
    for n in down_nodes:
        node_factor[n] = 0.0
    for e in down_edges:
        edge_factor[tuple(e)] = 0.0

    def mult(c: str) -> float:
        return demand_multiplier.get(c, 1.0) if isinstance(demand_multiplier, Mapping) else float(demand_multiplier)

    nodes = list(G.nodes)
    idx = {n: i for i, n in enumerate(nodes)}
    v_in = lambda n: 2 * idx[n]  # noqa: E731
    v_out = lambda n: 2 * idx[n] + 1  # noqa: E731
    src, sink = 2 * len(nodes), 2 * len(nodes) + 1

    demand = {n: round((d.get("demand") or 0.0) * mult(n)) for n, d in G.nodes(data=True) if is_demand(d["kind"])}
    total = int(sum(demand.values()))

    starts, ends, caps, costs, tags = [], [], [], [], []

    def arc(a: int, b: int, cap: float, cost: float, tag) -> None:
        starts.append(a)
        ends.append(b)
        caps.append(max(0, int(round(cap))))
        costs.append(int(round(cost * COST_SCALE)))
        tags.append(tag)

    for n, d in G.nodes(data=True):
        f = max(0.0, min(1.0, node_factor.get(n, 1.0)))
        if is_demand(d["kind"]):
            arc(v_in(n), sink, demand[n] * f, 0, ("serve", n))
            if G.out_degree(n):  # forwards to downstream demand nodes; capacity 0 means no limit
                arc(v_in(n), v_out(n), (d.get("capacity") or total) * f, 0, ("node", n))
            continue
        cap = (d.get("capacity") or 0.0) * f
        if d.get("backup") and not allow_backup:
            cap = 0
        arc(v_in(n), v_out(n), cap, 0, ("node", n))
        if d["kind"] == "supplier":
            arc(src, v_in(n), total, 0, None)
    for u, v, d in G.edges(data=True):
        f = max(0.0, min(1.0, edge_factor.get((u, v), 1.0)))
        cost = d["cost"] * (BACKUP_COST_FACTOR if G.nodes[u].get("backup") else 1.0)
        arc(v_out(u), v_in(v), d["capacity"] * f, cost, ("edge", (u, v)))
    arc(src, sink, total, shortage_penalty, None)

    smcf = min_cost_flow.SimpleMinCostFlow()
    for a, b, c, k in zip(starts, ends, caps, costs):
        smcf.add_arc_with_capacity_and_unit_cost(a, b, c, k)
    smcf.set_node_supply(src, total)
    smcf.set_node_supply(sink, -total)
    status = smcf.solve()
    if status != smcf.OPTIMAL:
        raise RuntimeError(f"min-cost flow failed with status {status}")

    flow, throughput, served = {}, {}, {}
    cost = 0.0
    for i, tag in enumerate(tags):
        if tag is None:
            continue
        units = float(smcf.flow(i))
        kind, key = tag
        if kind == "edge":
            flow[key] = units
            cost += units * costs[i] / COST_SCALE
        elif kind == "node":
            throughput[key] = units
        else:
            served[key] = units
    unmet = {c: float(demand[c] - served.get(c, 0.0)) for c in demand}
    return {"flow": flow, "throughput": throughput, "served": served, "unmet": unmet, "cost": round(cost, 1)}


def unmet_frac(G: nx.DiGraph, result: FlowResult) -> float:
    """Unmet demand as a fraction of total demand (retailers + customers), in [0, 1]."""
    total = total_demand(G)
    return 0.0 if total <= 0 else min(1.0, sum(result["unmet"].values()) / total)


def _active_state(events: list[Event], day: int, baseline: Mapping[str, list[float]] | None = None) -> tuple[dict, dict, dict]:
    """Remaining-capacity factors and demand multipliers for the events active on `day`.

    baseline: {demand node: [forecast / nominal demand per day]} (core.forecast.demand_ratio). During a demand spike the
    node's demand is forecast(day) x (1 + severity); without a baseline it is nominal demand x (1 + severity).
    """
    node_f: dict[str, float] = {}
    edge_f: dict[tuple[str, str], float] = {}
    mult: dict[str, float] = {}
    for ev in events:
        if not ev.start <= day < ev.start + ev.duration:
            continue
        if ev.type == "node":
            node_f[ev.target] = min(node_f.get(ev.target, 1.0), 1.0 - ev.severity)
        elif ev.type == "edge":
            u, v = (p.strip() for p in ev.target.split("->"))
            edge_f[(u, v)] = min(edge_f.get((u, v), 1.0), 1.0 - ev.severity)
        else:
            series = (baseline or {}).get(ev.target)
            base = series[min(day, len(series) - 1)] if series else 1.0
            mult[ev.target] = max(mult.get(ev.target, 0.0), base * (1.0 + ev.severity))
    return node_f, edge_f, mult


def spike_baseline(G: nx.DiGraph, events: list[Event], horizon: int) -> dict[str, list[float]] | None:
    """Forecast-based demand baseline, computed only when a scenario has a demand spike."""
    if not any(ev.type == "demand" for ev in events):
        return None
    from core.forecast import demand_ratio  # local import: forecast -> chaos -> sim

    return demand_ratio(G, max(horizon, 1))


def _describe(ev: Event) -> str:
    what = {"node": "outage at", "edge": "lane blocked:", "demand": "demand spike at"}[ev.type]
    return f"{what} {ev.target} for {ev.duration}d (severity {ev.severity:.2f})"


def simulate(G: nx.DiGraph, events: Iterable[Event], horizon: int = 30, detail: bool = False) -> dict:
    """Run the day loop described in the module docstring.

    Returns the POST /simulate response shape: {timeline:[{day, unmet, down, node_status, utilization}], log,
    stockout_day, total_unmet, survival_clock_days, revenue_at_risk, delay, bottlenecks}.
    detail=True also returns daily_flows ({(u, v): units} per day) and daily_cost (INR per day) for costing.
    """
    events = list(events)
    kind = {n: d["kind"] for n, d in G.nodes(data=True)}
    customers = [n for n in G if is_demand(kind[n])]  # every demand node (retailers and customers)
    label = {n: f"{n} {G.nodes[n].get('name', '')} ({G.nodes[n].get('city', '')})" for n in G}

    cache: dict[tuple, FlowResult] = {}
    baseline = spike_baseline(G, events, horizon)

    def solve(node_f, edge_f, mult, backup) -> FlowResult:
        key = (tuple(sorted(node_f.items())), tuple(sorted(edge_f.items())), tuple(sorted(mult.items())), backup)
        if key not in cache:
            cache[key] = solve_flow(G, node_factor=node_f, edge_factor=edge_f, demand_multiplier=mult, allow_backup=backup)
        return cache[key]

    baseline = solve({}, {}, {}, False)
    base_lead = arrival_lead(G, baseline["flow"])
    stock = {c: float(G.nodes[c].get("stock") or 0.0) for c in customers}

    timeline: list[dict] = []
    log: list[tuple[int, str]] = []
    daily_flows: list[dict] = []
    daily_cost: list[float] = []
    active_days: list[int] = []
    stockout_day: dict[str, int] = {}
    first_shortfall: int | None = None
    backup_logged = False
    prev_status = {n: "ok" for n in G}
    total_unmet = 0.0

    for ev in events:
        if ev.start < horizon:
            log.append((ev.start, f"Day {ev.start}: EVENT {_describe(ev)}"))
        if ev.start + ev.duration < horizon:
            log.append((ev.start + ev.duration, f"Day {ev.start + ev.duration}: EVENT ended at {ev.target}"))

    for day in range(horizon):
        node_f, edge_f, mult = _active_state(events, day, baseline)
        if node_f or edge_f or mult:
            active_days.append(day)
        backup = first_shortfall is not None and day >= first_shortfall + BACKUP_ACTIVATION_DAYS
        res = solve(node_f, edge_f, mult, backup)
        if first_shortfall is None and sum(res["unmet"].values()) > 0:
            first_shortfall = day
        daily_flows.append(res["flow"])
        daily_cost.append(res["cost"])

        status: dict[str, str] = {}
        util: dict[str, float] = {}
        reasons: dict[str, str] = {}
        day_unmet = 0.0
        for n in G:
            d = G.nodes[n]
            if is_demand(kind[n]):
                cap = d.get("capacity") or 0.0
                util[n] = round(res["throughput"].get(n, 0.0) / cap, 3) if cap and n in res["throughput"] else 0.0
                short = res["unmet"][n]
                draw = min(stock[n], short)
                stock[n] -= draw
                lost = short - draw
                day_unmet += lost
                if lost > 0:
                    status[n] = "down"
                    stockout_day.setdefault(n, day)
                elif short > 0:
                    status[n] = "stressed"
                    reasons[n] = f"short {short:.0f} units, drawing down stock ({stock[n]:.0f} left)"
                else:
                    status[n] = "ok"
                continue
            f = node_f.get(n, 1.0)
            cap = d.get("capacity") or 0.0
            u = res["throughput"].get(n, 0.0) / cap if cap else 0.0
            util[n] = round(u, 3)
            base_tp = baseline["throughput"].get(n, 0.0)
            if f <= 0:
                status[n] = "down"
            elif f < 1:
                status[n], reasons[n] = "stressed", f"capacity reduced to {f:.0%}"
            elif u > STRESS_UTILIZATION and res["throughput"].get(n, 0.0) > base_tp:  # load rose above normal
                status[n], reasons[n] = "stressed", f"running at {u:.0%} of capacity"
            elif base_tp > 0 and res["throughput"].get(n, 0.0) < 0.9 * base_tp:
                drop = 1 - res["throughput"].get(n, 0.0) / base_tp
                why = "output cut, downstream lanes blocked" if kind[n] == "supplier" else "inbound supply short"
                status[n], reasons[n] = "stressed", f"{why} (throughput -{drop:.0%})"
            else:
                status[n] = "ok"
            if d.get("backup") and res["throughput"].get(n, 0.0) > 0 and not backup_logged:
                backup_logged = True
                log.append((day, f"Day {day}: backup supplier {label[n]} activated (lanes cost {BACKUP_COST_FACTOR}x)"))

        for n in G:
            st, was = status[n], prev_status[n]
            if st == was:
                continue
            if st == "down":
                log.append((day, f"Day {day}: {label[n]} {'STOCKOUT' if is_demand(kind[n]) else 'DOWN'}"))
            elif st == "stressed" and was == "ok":
                log.append((day, f"Day {day}: {label[n]} stressed - {reasons.get(n, 'under pressure')}"))
            elif st == "ok":
                log.append((day, f"Day {day}: {label[n]} recovered"))
        if day_unmet == 0 and any(r["unmet"] > 0 for r in timeline[-1:]):
            log.append((day, f"Day {day}: all demand served again"))
        prev_status = status

        day_unmet = round(day_unmet, 1)
        total_unmet += day_unmet
        timeline.append({
            "day": day,
            "unmet": day_unmet,
            "down": sorted(n for n in G if status[n] == "down"),
            "node_status": status,
            "utilization": util,
        })

    delay = delay_stats(G, [daily_flows[d] for d in active_days], base_lead)
    result = {
        "timeline": timeline,
        "log": [line for _, line in sorted(log, key=lambda t: t[0])],
        "stockout_day": stockout_day,
        "total_unmet": round(total_unmet, 1),
        "survival_clock_days": min(stockout_day.values()) if stockout_day else horizon,
        "revenue_at_risk": round(total_unmet * G.graph.get("unit_price", 4200), 0),
        "delay": delay,
        "bottlenecks": find_bottlenecks(timeline),
    }
    if detail:
        result.update(daily_flows=daily_flows, daily_cost=daily_cost)
    return result
