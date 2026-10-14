"""What-if recovery planner with grounded reasoning. Owner: D.

Pipeline for one question ("What if Supplier S2 fails for 10 days?"):
    0. Scenario: plain English -> events (llm.parser.parse_scenario when an API key is set, else `rule_parse`, a
       deterministic parser; its assumptions are listed), or structured events from the scenario builder.
    1. Exact runs: baseline (no events) and scenario with core.sim.simulate; Monte Carlo (core.montecarlo: P50/P90
       unmet, shortage probability); a fast surrogate preview (core.risk_ml) with plain-English SHAP drivers.
    2. Impact: unmet by demand node, delay avg/P90, stock-out day, utilisation shifts, revenue at risk, and a causal
       cascade timeline built from the simulated day-by-day node states along the network's lanes (`cascade`).
    3. Candidate plans (CANDIDATES): the existing optimizer/strategy levers (reroute, backup supplier, safety stock,
       production shift, overtime) plus "Expedite by air" (the reroute+overtime+buffer plan with its rerouted lanes
       switched to air: air freight premium and CO2, air lead times) and the weather-aware reroute when the scenario
       has weather events; "Do nothing" is the wait-it-out option. Each plan: cost, unmet, delay, recovery days, CO2,
       residual risk (1 - resilience after / 100), fix-safety check (core.strategies.safety_check), Pareto flag.
       RECOMMENDATION RULE: lowest total cost of the disruption = plan cost + unmet units x unit price, among plans
       that pass the fix-safety check; ties go to the plan with fewer levers.
    4. Counterfactual attribution: re-solve the recommended plan without each of its levers; marginal benefit =
       unmet without the lever - unmet with it (units and INR), marginal cost = cost with - cost without. The
       interaction term = total benefit (vs doing nothing) - sum of marginal benefits.
    5. Sensitivity: duration x0.7 / x1.3 and demand x0.8 / x1.2; robustness: the share of Monte Carlo realisations of
       the scenario in which the recommendation still has the lowest total cost among the shortlist (recommended +
       the next best SHORTLIST - 1 plans). Re-solves skip the fix-safety check (stated in the assumptions).
    6. Evidence -> narrative (core.narrative): every section is rendered from the evidence; an LLM may only re-word it
       and is rejected if it adds a number that is not in the evidence.
Follow-up questions (`ask`) are routed to a WHITELIST of engine functions (run_scenario, run_strategy, compare_plans)
and answered from their evidence; anything else is politely declined.
All figures are simulated: they come from the AEGIS engine, not from observed operations.
"""
from __future__ import annotations

import math
import re
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable

import networkx as nx
import numpy as np

from core import narrative, risk_ml
from core import strategies as strat
from core.delay import arrival_lead, delay_stats
from core.montecarlo import monte_carlo, sample_events
from core.optimizer import LEVERS, W_CO2, optimize_plan
from core.sim import BACKUP_ACTIVATION_DAYS, BACKUP_COST_FACTOR, lead_factors, simulate
from core.synth.profiles import CITY
from node_types import MODE_DEFAULTS, haversine_km, is_demand, total_demand
from schemas import Event

HORIZON = 30
SHORTLIST = 4
ROBUST_TOL = 0.005  # a plan within 0.5% (or INR 1,000) of the best total cost counts as "still best"
LP_WORKERS = 6
MAX_HISTORY = 30

LEVER_LABEL = {
    "reroute": "Reroute flows", "backup": "Trigger backup supplier", "overtime": "Overtime",
    "safety_stock": "Pre-position safety stock", "production_shift": "Shift production", "expedite": "Expedite by air",
}
# name, levers, CO2 price, expedite by air
CANDIDATES: list[tuple[str, tuple[str, ...], float, bool]] = [
    ("Do nothing", (), W_CO2, False),
    ("Reroute only", ("reroute",), W_CO2, False),
    ("Reroute + backup", ("reroute", "backup"), W_CO2, False),
    ("Inventory buffer", ("safety_stock",), W_CO2, False),
    ("Production shift", ("reroute", "production_shift"), W_CO2, False),
    ("Overtime", ("reroute", "overtime"), W_CO2, False),
    ("Expedite by air", ("reroute", "overtime", "safety_stock"), W_CO2, True),
    ("Full plan", LEVERS, W_CO2, False),
    ("Green plan", LEVERS, W_CO2 * strat.GREEN_CO2_MULTIPLIER, False),
]
DISPLAY_NAME = {"Do nothing": "Wait it out (do nothing)"}
PLAN_KEYWORDS = [  # question keyword -> plan (first match wins)
    (("air", "expedite", "fly", "flight"), "Expedite by air"),
    (("backup", "second source", "alternate supplier"), "Reroute + backup"),
    (("overtime", "extra shift"), "Overtime"),
    (("inventory", "buffer", "safety stock", "stock up", "pre-position", "preposition"), "Inventory buffer"),
    (("production shift", "shift production", "move production", "other plant", "other factory"), "Production shift"),
    (("green", "co2", "carbon", "emission"), "Green plan"),
    (("full plan", "everything", "all levers"), "Full plan"),
    (("weather",), strat.WEATHER_STRATEGY),
    (("reroute", "re-route", "rerouting", "other route", "alternate route"), "Reroute only"),
    (("nothing", "wait", "do nothing", "wait it out"), "Do nothing"),
]


class WhatIfError(ValueError):
    """A question the planner cannot turn into a scenario (shown to the user)."""


# ---------------------------------------------------------------- formatting (shared with the evidence)
def inr(v: float) -> str:
    return strat.fmt_inr(v)


def units(v: float) -> str:
    return f"{v:,.0f}"


def _r(v: float, d: int = 2) -> float:
    return round(float(v), d)


# ---------------------------------------------------------------- 0. scenario parsing
_DUR = re.compile(r"(\d+(?:\.\d+)?)\s*(days?|d\b|weeks?|wks?)", re.I)
_START = re.compile(r"(?:from|starting(?:\s+on)?|on|after)\s+day\s+(\d+)|in\s+(\d+)\s+days?\s+(?:time|from now)", re.I)
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent|per cent)", re.I)
_LANE = re.compile(r"([A-Za-z][A-Za-z0-9_-]*)\s*(?:->|→|=>)\s*([A-Za-z][A-Za-z0-9_-]*)")
FAIL_WORDS = ("fail", "down", "outage", "shut", "close", "strike", "breakdown", "offline", "stop", "disrupt", "flood",
              "fire", "lost", "unavailable", "blocked", "halt", "recall", "cyclone", "storm")
UP_WORDS = ("rise", "rises", "increase", "spike", "surge", "jump", "grow", "higher", "up ", "boom", "peak", "festival", "diwali")
DOWN_WORDS = ("drop", "fall", "decline", "lower", "slump", "dip", "decrease", "shrink")
SLOW_WORDS = ("delay", "late", "slow", "congest")


def _mentions(text: str, G: nx.DiGraph) -> tuple[list[str], list[str]]:
    """(node ids mentioned by id or name, city names mentioned)."""
    low = f" {text.lower()} "
    ids = [n for n in G if re.search(rf"(?<![a-z0-9_]){re.escape(str(n).lower())}(?![a-z0-9_])", low)]
    for n, d in G.nodes(data=True):
        name = str(d.get("name") or "").lower().strip()
        if len(name) >= 5 and name in low and n not in ids:
            ids.append(n)
    cities = sorted({str(d.get("city") or "") for _, d in G.nodes(data=True) if d.get("city")} | set(CITY), key=len, reverse=True)
    found = []
    for c in cities:
        if c and re.search(rf"(?<![a-z]){re.escape(c.lower())}(?![a-z])", low) and not any(c.lower() in f.lower() for f in found):
            found.append(c)
    return ids, found


def _city_point(G: nx.DiGraph, city: str) -> tuple[float, float] | None:
    for _, d in G.nodes(data=True):
        if str(d.get("city") or "").lower() == city.lower():
            return d["lat"], d["lon"]
    if city in CITY:
        return CITY[city]["lat"], CITY[city]["lon"]
    return None


def rule_parse(text: str, G: nx.DiGraph, horizon: int = HORIZON) -> tuple[list[Event], list[str]]:
    """Deterministic plain-English parser (used without an API key). Returns (events, assumptions)."""
    notes: list[str] = []
    low = text.lower()
    m = _DUR.search(text)
    if m:
        duration = int(round(float(m.group(1)) * (7 if m.group(2).lower().startswith("w") else 1)))
    else:
        duration = 7
        notes.append("No duration given: assumed 7 days.")
    duration = int(np.clip(duration, 1, 365))
    s = _START.search(text)
    start = int(next(g for g in s.groups() if g)) if s else 1
    if not s:
        notes.append("No start day given: assumed day 1.")
    start = min(start, max(0, horizon - 1))
    pct = _PCT.search(text)
    share = float(pct.group(1)) / 100 if pct else None
    events: list[Event] = []
    ids, cities = _mentions(text, G)

    for a, b in _LANE.findall(text):
        a, b = next((n for n in G if str(n).lower() == a.lower()), a), next((n for n in G if str(n).lower() == b.lower()), b)
        if G.has_edge(a, b):
            sev = min(1.0, share) if share and any(w in low for w in ("reduc", "partial", "capacity", "slow")) else 1.0
            events.append(Event(type="edge", target=f"{a}->{b}", start=start, duration=duration, severity=sev))
            ids = [n for n in ids if n not in (a, b)]

    is_demand_q = "demand" in low or "orders" in low or "sales" in low
    if is_demand_q:
        down = any(w in low for w in DOWN_WORDS)
        sev = min(1.0, share) if share is not None else 0.3
        if share is None:
            notes.append(f"No size given for the demand change: assumed {'-' if down else '+'}30%.")
        targets = [n for n in ids if is_demand(G.nodes[n]["kind"])]
        for c in cities:
            local = [n for n, d in G.nodes(data=True) if is_demand(d["kind"]) and str(d.get("city", "")).lower() == c.lower()]
            if not local and (pt := _city_point(G, c)):
                dem = [n for n, d in G.nodes(data=True) if is_demand(d["kind"])]
                if dem:
                    near = min(dem, key=lambda n: haversine_km(pt, (G.nodes[n]["lat"], G.nodes[n]["lon"])))
                    km = haversine_km(pt, (G.nodes[near]["lat"], G.nodes[near]["lon"]))
                    local = [near]
                    notes.append(f"No demand node in {c}: applied to the nearest one, {near} ({G.nodes[near].get('city', '')}, {km:,.0f} km away).")
            targets += [n for n in local if n not in targets]
        if not targets:
            targets = [n for n, d in G.nodes(data=True) if is_demand(d["kind"]) and (d.get("demand") or 0) > 0]
            notes.append("No place given for the demand change: applied to every demand node.")
        if "festival" in low or "diwali" in low:
            notes.append("Festival season is modelled as the stated demand change over the scenario window.")
        for c in targets:
            events.append(Event(type="demand", target=c, start=start, duration=duration, severity=sev,
                                direction="down" if down else None))
    supply = [n for n in ids if not is_demand(G.nodes[n]["kind"])]
    if not supply and not events and cities and any(w in low for w in FAIL_WORDS):
        supply = [n for n, d in G.nodes(data=True) if not is_demand(d["kind"]) and not d.get("backup")
                  and str(d.get("city", "")).lower() in {c.lower() for c in cities}]
        if supply:
            notes.append(f"Applied to every supply-side site in {', '.join(cities)}.")
    if supply and (any(w in low for w in FAIL_WORDS) or any(w in low for w in SLOW_WORDS) or not is_demand_q):
        partial = share is not None and any(w in low for w in ("capacity", "reduc", "partial", "output", "by "))
        sev = min(1.0, share) if partial else 1.0
        if any(w in low for w in SLOW_WORDS) and not any(w in low for w in FAIL_WORDS):
            notes.append("A delayed site is modelled as unavailable for the stated period.")
        for n in supply:
            events.append(Event(type="node", target=n, start=start, duration=duration, severity=sev))
    if not events:
        raise WhatIfError("Couldn't map that question to this network. Name a site (e.g. S2), a lane (F1->W3) or a demand "
                          "change (\"demand rises 40% in Chennai\"), or use the scenario builder.")
    return events, notes


def parse_question(text: str, G: nx.DiGraph, horizon: int = HORIZON) -> tuple[list[Event], list[str], str]:
    """(events, assumptions, parser): the LLM parser when available, else the deterministic rule parser."""
    from llm.parser import LLMUnavailable, ScenarioParseError, parse_scenario

    try:
        return parse_scenario(text, G, horizon), [], "llm"
    except (LLMUnavailable, ScenarioParseError):
        events, notes = rule_parse(text, G, horizon)
        return events, notes, "rules"


def describe_event(G: nx.DiGraph, e: Event) -> str:
    name = lambda n: f"{n} ({G.nodes[n].get('name') or n})" if n in G else n  # noqa: E731
    span = f"days {e.start}-{e.start + e.duration - 1}"
    if e.type == "node":
        what = "down" if e.severity >= 1 else f"at {1 - e.severity:.0%} capacity"
        return f"{name(e.target)} {what}, {span}"
    if e.type == "edge":
        what = "blocked" if e.severity >= 1 else f"at {1 - e.severity:.0%} capacity"
        slow = f", lead time x{e.lead_multiplier:g}" if e.lead_multiplier else ""
        return f"lane {e.target} {what}{slow}, {span}"
    sign = "-" if getattr(e, "direction", None) == "down" else "+"
    return f"demand {sign}{e.severity:.0%} at {name(e.target)}, {span}"


# ---------------------------------------------------------------- 2. impact + cascade
def _util_by_node(timeline: list[dict]) -> dict[str, float]:
    peak: dict[str, float] = {}
    for row in timeline:
        for n, u in row["utilization"].items():
            peak[n] = max(peak.get(n, 0.0), u)
    return peak


def impact(G: nx.DiGraph, base: dict, scen: dict, horizon: int) -> dict:
    total = total_demand(G) * horizon
    unit_price = G.graph.get("unit_price", 4200)
    by_node = sorted(((n, v) for n, v in scen.get("unmet_by_node", {}).items() if v > 0), key=lambda kv: -kv[1])
    base_peak, scen_peak = _util_by_node(base["timeline"]), _util_by_node(scen["timeline"])
    shifts = sorted(((n, base_peak.get(n, 0.0), scen_peak.get(n, 0.0)) for n in G
                     if not is_demand(G.nodes[n]["kind"]) and abs(scen_peak.get(n, 0.0) - base_peak.get(n, 0.0)) >= 0.05),
                    key=lambda t: -abs(t[2] - t[1]))[:6]
    first = min(scen["stockout_day"].items(), key=lambda kv: kv[1]) if scen["stockout_day"] else None
    return {
        "unmet_units": _r(scen["total_unmet"], 1), "unmet_units_display": units(scen["total_unmet"]),
        "unmet_pct": _r(100 * scen["total_unmet"] / total, 2) if total else 0.0,
        "baseline_unmet_units": _r(base["total_unmet"], 1),
        "revenue_at_risk": _r(scen["revenue_at_risk"], 0), "revenue_at_risk_display": inr(scen["revenue_at_risk"]),
        "unit_price": unit_price, "horizon_days": horizon, "total_demand_units": _r(total, 0),
        "first_stockout": {"node": first[0], "day": first[1]} if first else None,
        "survival_clock_days": scen["survival_clock_days"],
        "stockout_day_by_node": scen["stockout_day"],
        "delay": {"avg_days": scen["delay"]["avg_days"], "p90_days": scen["delay"]["p90_days"]},
        "unmet_by_customer": [{"node": n, "units": _r(v, 1), "units_display": units(v),
                               "share_of_its_demand_pct": _r(100 * v / ((G.nodes[n].get("demand") or 1) * horizon), 1)}
                              for n, v in by_node],
        "utilization_shifts": [{"node": n, "baseline_peak_pct": _r(100 * b, 0), "scenario_peak_pct": _r(100 * s, 0)} for n, b, s in shifts],
        "bottlenecks": scen["bottlenecks"][:5],
        "last_unmet_day": scen.get("last_unmet_day"),
    }


def _node_word(G: nx.DiGraph, n: str, status: str, util: float, base_util: float) -> str:
    kind = G.nodes[n]["kind"]
    if is_demand(kind):
        return "STOCK-OUT" if status == "down" else "drawing down safety stock"
    if status == "down":
        return "down"
    if util > base_util + 0.02 and util >= 0.85:
        return f"overloaded ({util:.0%})"
    return "starved of supply" if kind != "supplier" else "output cut"


def cascade(G: nx.DiGraph, events: list[Event], scen: dict, base: dict, max_items: int = 10) -> list[dict]:
    """Causal timeline: each event's root, then the downstream nodes it pushed out of 'ok', in lane order and by the
    day they first changed state, e.g. 'Day 2: S2 down -> F1 starved of supply -> W3 starved of supply'."""
    tl = scen["timeline"]
    base_util = {n: u for n, u in (base["timeline"][0]["utilization"].items() if base["timeline"] else [])}
    first_bad: dict[str, tuple[int, str]] = {}
    for row in tl:
        for n, st in row["node_status"].items():
            if st != "ok" and n not in first_bad:
                first_bad[n] = (row["day"], st)
    worst: dict[str, tuple[int, str]] = {}
    for row in tl:  # first day a node reached its worst state (down beats stressed)
        for n, st in row["node_status"].items():
            if st == "down" and (n not in worst or worst[n][1] != "down"):
                worst[n] = (row["day"], st)
    items: list[dict] = []
    roots = []
    for e in sorted(events, key=lambda e: e.start):
        root = e.target.split("->")[1].strip() if e.type == "edge" else e.target
        roots.append((e, root))
    seen_chain: set = set()
    for e, root in roots:
        if root not in G:
            continue
        chain_nodes = [root]
        frontier = root
        visited = {root}
        while True:  # follow the most affected successor (earliest change, then most downstream demand)
            nxt = [s for s in G.successors(frontier) if s in first_bad and s not in visited and first_bad[s][0] >= e.start]
            if not nxt:
                break
            frontier = min(nxt, key=lambda s: (first_bad[s][0], -len(nx.descendants(G, s))))
            visited.add(frontier)
            chain_nodes.append(frontier)
        start_txt = describe_event(G, e).split(",")[0]
        parts = [start_txt if e.type != "edge" else f"lane {e.target} {'blocked' if e.severity >= 1 else 'reduced'}"]
        days = [e.start]
        for n in chain_nodes[0 if e.type == "edge" else 1:]:
            day, st = worst.get(n) or first_bad.get(n, (None, None))
            if day is None:
                continue
            u = tl[day]["utilization"].get(n, 0.0)
            parts.append(f"{n} {_node_word(G, n, st, u, base_util.get(n, 0.0))}" + (f" (day {day})" if day != e.start else ""))
            days.append(day)
        key = tuple(parts)
        if key in seen_chain:
            continue
        seen_chain.add(key)
        items.append({"day": e.start, "text": f"Day {e.start}: " + " -> ".join(parts), "nodes": chain_nodes, "days": days})
    for n, (day, st) in sorted(worst.items(), key=lambda kv: kv[1][0]):
        if is_demand(G.nodes[n]["kind"]) and not any(n in it["nodes"] for it in items):
            items.append({"day": day, "text": f"Day {day}: {n} ({G.nodes[n].get('name') or n}) STOCK-OUT", "nodes": [n], "days": [day]})
    last = scen.get("last_unmet_day")
    if last is not None and last + 1 < len(tl):
        items.append({"day": last + 1, "text": f"Day {last + 1}: all demand served again", "nodes": [], "days": [last + 1]})
    items.sort(key=lambda it: it["day"])
    return items[:max_items]


# ---------------------------------------------------------------- 3. plans
def _cand(name: str) -> tuple[str, tuple[str, ...], float, bool]:
    for c in CANDIDATES:
        if c[0] == name:
            return c
    if name == strat.WEATHER_STRATEGY:
        return (name, strat.WEATHER_LEVERS, W_CO2, False)
    raise KeyError(name)


def candidate_names(events: list[Event]) -> list[str]:
    names = [c[0] for c in CANDIDATES]
    if strat.has_weather(events):
        names.append(strat.WEATHER_STRATEGY)
    return names


def expedite(G: nx.DiGraph, events: list[Event], plan: dict) -> dict:
    """Switch the plan's rerouted lanes (else its lanes into demand nodes) to air for the disruption window."""
    plan = {**plan, "cost_breakdown": dict(plan["cost_breakdown"])}
    if not plan["daily_flows"]:
        plan["expedited_lanes"] = []
        return plan
    lanes = [tuple(x.split("->")) for x in plan["rerouted_lanes"]] or [
        (u, v) for u, v in G.edges if is_demand(G.nodes[v]["kind"]) and any(f.get((u, v), 0) > 0 for f in plan["daily_flows"])]
    air = MODE_DEFAULTS["air"]
    premium, co2_extra = 0.0, 0.0
    factor: dict[tuple[str, str], float] = {}
    for u, v in lanes:
        d = G.edges[u, v]
        km = d.get("distance_km") or haversine_km((G.nodes[u]["lat"], G.nodes[u]["lon"]), (G.nodes[v]["lat"], G.nodes[v]["lon"]))
        shipped = sum(f.get((u, v), 0.0) for f in plan["daily_flows"])
        premium += shipped * max(0.0, air["base_cost"] + km * air["cost_per_km"] - d["cost"])
        co2_extra += shipped * max(0.0, km * air["co2_per_km"] - (d.get("co2") or 0.0))
        air_lead = max(0.5, km / air["speed"] + air["handling"])
        factor[(u, v)] = min(1.0, air_lead / max(d["lead"], 0.5))
    window = list(range(plan["window"][0], plan["window"][1] + 1))
    base_lead = arrival_lead(G, strat.baseline(G)["flow"]["flow"])
    daily = [{**lead_factors(events, t), **factor} for t in window]
    plan["delay"] = delay_stats(G, plan["daily_flows"], base_lead, daily)
    plan["cost_breakdown"]["expedite_air"] = round(premium, 0)
    plan["cost"] = round(plan["cost"] + premium, 0)
    plan["co2"] = round(plan["co2"] + co2_extra / 1000, 2)
    plan["expedited_lanes"] = [f"{u}->{v}" for u, v in lanes]
    return plan


def solve_candidate(G: nx.DiGraph, events: list[Event], name: str, levers: Iterable[str] | None = None,
                    horizon: int = HORIZON, use_expedite: bool | None = None) -> dict:
    """One candidate plan (optionally with a lever subset, for attribution)."""
    cname, clevers, w_co2, exp = _cand(name)
    levers = tuple(clevers if levers is None else levers)
    exp = exp if use_expedite is None else use_expedite
    if cname == strat.WEATHER_STRATEGY and levers == tuple(strat.WEATHER_LEVERS):
        plan = strat.weather_plan(G, events, horizon)
    else:
        plan = optimize_plan(G, events, levers, horizon=horizon, w_co2=w_co2)
    plan = expedite(G, events, plan) if exp else {**plan, "expedited_lanes": []}
    plan["_levers"] = list(levers) + (["expedite"] if exp else [])
    return plan


def _row(G: nx.DiGraph, name: str, plan: dict, check: dict | None) -> dict:
    unit_price = G.graph.get("unit_price", 4200)
    objective = plan["cost"] + plan["unmet"] * unit_price
    res = check["resilience_after"] if check else None
    return {
        "name": name, "label": DISPLAY_NAME.get(name, name), "levers": plan["_levers"],
        "cost": float(plan["cost"]), "cost_display": inr(plan["cost"]),
        "unmet": float(plan["unmet"]), "unmet_display": units(plan["unmet"]),
        "stock_drawn": float(plan.get("stock_drawn", 0.0)),
        "delay_avg_days": float(plan["delay"]["avg_days"]), "delay_p90_days": float(plan["delay"]["p90_days"]),
        "recovery_days": int(plan["recovery_days"]), "co2_t": float(plan["co2"]),
        "resilience_after": res, "residual_risk": _r(1 - res / 100, 3) if res is not None else None,
        "safety": {"passed": check["passed"], "warning": check["warning"]} if check else {"passed": True, "warning": None},
        "objective": float(round(objective, 0)), "objective_display": inr(objective),
        "cost_breakdown": plan["cost_breakdown"], "description": strat._describe(name, plan),
        "actions": {"rerouted_lanes": plan["rerouted_lanes"], "backup_used": plan["backup_used"],
                    "inventory_actions": plan["inventory_actions"], "production_actions": plan["production_actions"],
                    "capacity_delta": plan["capacity_delta"], "expedited_lanes": plan.get("expedited_lanes", [])},
        "pareto": False, "recommended": False,
    }


def _pool(fn: Callable, args: list) -> list:
    if len(args) <= 1:
        return [fn(*a) for a in args]
    with ThreadPoolExecutor(max_workers=min(LP_WORKERS, len(args))) as ex:  # CBC runs as a subprocess per solve
        return list(ex.map(lambda a: fn(*a), args))


def evaluate_plans(G: nx.DiGraph, events: list[Event], horizon: int = HORIZON, names: list[str] | None = None,
                   safety: bool = True) -> tuple[list[dict], dict[str, dict]]:
    """Rows for every candidate (with the fix-safety check), the Pareto flags and the recommendation."""
    names = names or candidate_names(events)
    plans = dict(zip(names, _pool(lambda n: solve_candidate(G, events, n, horizon=horizon), [(n,) for n in names])))
    rows = [_row(G, n, plans[n], strat.safety_check(G, events, plans[n]) if safety else None) for n in names]
    for r in rows:
        r["pareto"] = not any(o is not r and o["cost"] <= r["cost"] and o["unmet"] <= r["unmet"]
                              and (o["cost"] < r["cost"] or o["unmet"] < r["unmet"]) for o in rows)
    passing = [r for r in rows if r["safety"]["passed"]] or rows
    best = min(passing, key=lambda r: (r["objective"], len(r["levers"]), r["name"]))
    best["recommended"] = True
    return rows, plans


def _rejection(rec: dict, r: dict) -> str:
    bits = []
    if not r["safety"]["passed"]:
        return f"Fails the fix-safety check: {r['safety']['warning']}"
    extra = r["objective"] - rec["objective"]
    if r["unmet"] > rec["unmet"]:
        bits.append(f"leaves {units(r['unmet'] - rec['unmet'])} more units unmet")
    if r["cost"] > rec["cost"]:
        bits.append(f"costs {inr(r['cost'] - rec['cost'])} more to run")
    if r["co2_t"] < rec["co2_t"] and r["cost"] >= rec["cost"]:
        bits.append(f"emits {rec['co2_t'] - r['co2_t']:.2f} t less CO2, which does not offset the extra cost")
    head = f"Total cost of the disruption {inr(r['objective'])} vs {inr(rec['objective'])} ({inr(extra)} more)"
    if extra <= 0:
        head = f"Same total cost ({inr(r['objective'])}) but more levers to run"
    return head + ("; " + "; ".join(bits) if bits else "") + "."


# ---------------------------------------------------------------- 4-5. attribution, sensitivity, robustness
def attribution(G: nx.DiGraph, events: list[Event], rec: dict, nothing: dict, horizon: int) -> dict:
    unit_price = G.graph.get("unit_price", 4200)
    levers = [lv for lv in rec["levers"]]
    total_units = nothing["unmet"] - rec["unmet"]
    if not levers:
        return {"rows": [], "total_benefit_units": _r(total_units, 1), "sum_marginal_units": 0.0, "interaction_units": _r(total_units, 1),
                "note": "The recommended plan uses no levers, so there is nothing to attribute."}

    def without(lv):
        rest = [x for x in levers if x not in (lv, "expedite")]
        return solve_candidate(G, events, rec["name"], levers=rest, horizon=horizon, use_expedite=("expedite" in levers and lv != "expedite"))

    plans = _pool(without, [(lv,) for lv in levers])
    rows = []
    for lv, p in zip(levers, plans):
        benefit = p["unmet"] - rec["unmet"]
        cost = rec["cost"] - p["cost"]
        rows.append({
            "lever": lv, "label": LEVER_LABEL.get(lv, lv),
            "unmet_without": _r(p["unmet"], 1), "cost_without": _r(p["cost"], 0),
            "marginal_benefit_units": _r(benefit, 1), "marginal_benefit_inr": _r(benefit * unit_price, 0),
            "marginal_benefit_display": inr(benefit * unit_price),
            "marginal_cost_inr": _r(cost, 0), "marginal_cost_display": inr(cost), "marginal_cost_abs_display": inr(abs(cost)),
            "net_value_inr": _r(benefit * unit_price - cost, 0), "net_value_display": inr(benefit * unit_price - cost),
        })
    s = sum(r["marginal_benefit_units"] for r in rows)
    return {"rows": sorted(rows, key=lambda r: -r["net_value_inr"]), "total_benefit_units": _r(total_units, 1),
            "total_benefit_inr": _r(total_units * unit_price, 0), "sum_marginal_units": _r(s, 1),
            "interaction_units": _r(total_units - s, 1),
            "note": "Marginal = re-solved without that lever, everything else unchanged. Interaction = total benefit "
                    "versus doing nothing minus the sum of the marginal benefits (levers that substitute for each other "
                    "make it negative, levers that only work together make it positive)."}


def _objective(G: nx.DiGraph, plan: dict) -> float:
    return plan["cost"] + plan["unmet"] * G.graph.get("unit_price", 4200)


def _best_of(G: nx.DiGraph, events: list[Event], names: list[str], horizon: int) -> dict[str, dict]:
    plans = _pool(lambda n: solve_candidate(G, events, n, horizon=horizon), [(n,) for n in names])
    return dict(zip(names, plans))


def sensitivity(G: nx.DiGraph, events: list[Event], shortlist: list[str], rec_name: str, horizon: int) -> list[dict]:
    variants = [
        ("Duration -30%", G, [e.model_copy(update={"duration": max(1, round(e.duration * 0.7))}) for e in events]),
        ("Duration +30%", G, [e.model_copy(update={"duration": min(365, max(1, round(e.duration * 1.3)))}) for e in events]),
    ]
    for label, f in (("Demand -20%", 0.8), ("Demand +20%", 1.2)):
        H = G.copy()
        for n, d in H.nodes(data=True):
            if is_demand(d["kind"]):
                d["demand"] = (d.get("demand") or 0.0) * f
        variants.append((label, H, events))
    out = []
    for label, H, ev in variants:
        plans = _best_of(H, ev, shortlist, horizon)
        obj = {n: _objective(H, p) for n, p in plans.items()}
        best = min(obj, key=lambda n: (obj[n], len(plans[n]["_levers"])))
        rec_obj = obj[rec_name]
        out.append({
            "variant": label, "best_plan": best, "recommended_still_best": rec_obj <= obj[best] * (1 + ROBUST_TOL) + 1000,
            "recommended_total_cost": _r(rec_obj, 0), "recommended_total_cost_display": inr(rec_obj),
            "best_total_cost": _r(obj[best], 0), "best_total_cost_display": inr(obj[best]),
            "regret_inr": _r(rec_obj - obj[best], 0), "regret_display": inr(rec_obj - obj[best]),
            "recommended_unmet": _r(plans[rec_name]["unmet"], 1),
        })
    return out


def robustness(G: nx.DiGraph, events: list[Event], shortlist: list[str], rec_name: str, horizon: int, runs: int, seed: int) -> dict:
    if runs <= 0 or not events:
        return {"runs": 0, "share_best": None, "wins": {}}
    rng = np.random.default_rng(seed)
    draws = [sample_events(events, rng) for _ in range(runs)]
    jobs = [(i, n) for i in range(runs) for n in shortlist]
    plans = _pool(lambda i, n: solve_candidate(G, draws[i], n, horizon=horizon), jobs)
    obj: dict[int, dict[str, float]] = {}
    for (i, n), p in zip(jobs, plans):
        obj.setdefault(i, {})[n] = _objective(G, p)
    wins: dict[str, int] = {}
    stays = 0
    for i, o in obj.items():
        best = min(o.values())
        winner = min(o, key=lambda n: (o[n], shortlist.index(n)))
        wins[winner] = wins.get(winner, 0) + 1
        stays += o[rec_name] <= best * (1 + ROBUST_TOL) + 1000
    return {"runs": runs, "share_best": _r(stays / runs, 3), "share_best_pct": _r(100 * stays / runs, 0), "wins": wins,
            "shortlist": shortlist,
            "method": "Monte Carlo realisations of the scenario (duration lognormal, severity beta, start +-2 days); "
                      "each realisation re-solves the shortlisted plans and checks whether the recommendation still has the "
                      "lowest total cost (within 0.5%)."}


# ---------------------------------------------------------------- evidence + narrative
def confidence(rob: dict, sens: list[dict], mc: dict, preview: dict | None) -> dict:
    share = rob.get("share_best")
    stable = sum(1 for s in sens if s["recommended_still_best"])
    if share is None:
        level = "Medium" if stable == len(sens) else "Low"
    elif share >= 0.8 and stable == len(sens):
        level = "High"
    elif share >= 0.5 and stable >= len(sens) - 1:
        level = "Medium"
    else:
        level = "Low"
    reasons = []
    if share is not None:
        reasons.append(f"The recommendation stays best in {rob['share_best_pct']:.0f}% of {rob['runs']} Monte Carlo realisations.")
    reasons.append(f"It stays best in {stable} of {len(sens)} sensitivity variants (duration +-30%, demand +-20%).")
    reasons.append(f"Shortage probability across {mc.get('runs', 0)} Monte Carlo runs: {mc['p_shortage_pct']:.0f}%.")
    if preview and preview.get("agreement"):
        a = preview["agreement"]
        reasons.append(f"The ML surrogate predicted {a['predicted_unmet_pct']:.2f}% unmet vs {a['exact_unmet_pct']:.2f}% simulated "
                       f"({'inside' if a['within_interval'] else 'outside'} its 80% interval).")
    return {"level": level, "share_best": share, "sensitivity_stable": stable, "sensitivity_total": len(sens), "reasons": reasons}


def build_sections(ev: dict) -> list[dict]:
    """Deterministic narrative, rendered only from the evidence object `ev`."""
    imp, rec, sc = ev["impact"], ev["recommended"], ev["scenario"]
    mc = ev["monte_carlo"]
    first = imp["first_stockout"]
    stock_txt = (f"the first stock-out hits {first['node']} on day {first['day']}" if first
                 else f"no demand node runs out of stock within {imp['horizon_days']} days")
    situation = (f"Simulated scenario: {'; '.join(sc['descriptions'])}. With its automatic response (daily re-routing, backup "
                 f"supplier after the activation lag), over the {imp['horizon_days']}-day horizon the network would leave {imp['unmet_units_display']} units unmet ({imp['unmet_pct']:.2f}% of demand), {stock_txt}, with "
                 f"{imp['revenue_at_risk_display']} of revenue at risk (simulated).")
    impact_bullets = [
        f"Unmet demand: {imp['unmet_units_display']} units ({imp['unmet_pct']:.2f}% of {imp['horizon_days']}-day demand), simulated.",
        f"Monte Carlo ({mc['runs']} runs): P50 {mc['p50_display']} units, P90 {mc['p90_display']} units unmet; shortage probability {mc['p_shortage_pct']:.0f}%.",
        f"Extra delivery delay: {imp['delay']['avg_days']:.2f} days on average, {imp['delay']['p90_days']:.2f} days at P90 (simulated).",
        f"Revenue at risk: {imp['revenue_at_risk_display']} at {inr(imp['unit_price'])} per unit (simulated).",
    ]
    for c in imp["unmet_by_customer"][:4]:
        impact_bullets.append(f"{c['node']}: {c['units_display']} units unmet ({c['share_of_its_demand_pct']:.1f}% of its demand).")
    for u in imp["utilization_shifts"][:3]:
        impact_bullets.append(f"{u['node']} peak utilisation {u['baseline_peak_pct']:.0f}% -> {u['scenario_peak_pct']:.0f}%.")
    rec_row = rec["row"]
    why = [f"Selection rule: {ev['selection_rule']}",
           f"Total cost of the disruption with this plan: {rec_row['objective_display']} (plan cost {rec_row['cost_display']} + "
           f"{rec_row['unmet_display']} units unmet), versus {ev['do_nothing']['objective_display']} if the team waits it out "
           f"(today's lane allocations frozen, no backup: {ev['do_nothing']['unmet_display']} units unmet).",
           f"Simulated outcome: {rec_row['unmet_display']} units unmet, {rec_row['delay_avg_days']:.2f} days average extra delay, "
           f"recovery in {rec_row['recovery_days']} days, {rec_row['co2_t']:.2f} t CO2.",
           f"Fix-safety check: {'passed' if rec_row['safety']['passed'] else 'FAILED - ' + str(rec_row['safety']['warning'])}"
           + (f"; resilience after the fix {rec_row['resilience_after']:.1f} / 100." if rec_row["resilience_after"] is not None else ".")]
    for a in ev["attribution"]["rows"]:
        price = (f"for {a['marginal_cost_abs_display']}" if a["marginal_cost_inr"] >= 0
                 else f"and lowers the plan cost by {a['marginal_cost_abs_display']}")
        why.append(f"{a['label']}: recovers {units(a['marginal_benefit_units'])} units ({a['marginal_benefit_display']}) {price} "
                   f"(counterfactual without it: {units(a['unmet_without'])} units unmet).")
    alts = [f"{a['label']}: {a['reason']}" for a in ev["alternatives"]]
    risks = list(sc["assumptions"]) + [
        "All figures are simulated by the AEGIS engine (daily min-cost flow); they are not observed outcomes.",
        f"Demand-node stock is not replenished within the horizon; the backup supplier opens "
        f"{ev['model_constants']['backup_activation_days']} days after it is triggered.",
        "Sensitivity and robustness re-solves skip the fix-safety check.",
        "Impact figures simulate the network's automatic response (daily re-optimised routing, backup after the lag); the "
        "plans are planned by the recovery optimiser, where 'wait it out' freezes today's lane allocations, so it loses more.",
    ]
    for s in ev["sensitivity"]:
        if not s["recommended_still_best"]:
            risks.append(f"{s['variant']}: {s['best_plan']} becomes cheaper (the recommendation costs {s['regret_display']} more).")
    if mc["p90"] > imp["unmet_units"]:
        risks.append(f"Downside: in 10% of Monte Carlo runs unmet demand exceeds {mc['p90_display']} units.")
    conf = ev["confidence"]
    steps = [f"[ ] Day {s['day']}: {s['text']}" for s in ev["next_steps"]]
    return [
        {"key": "situation", "title": "Situation summary", "paragraphs": [situation], "bullets": [],
         "evidence": {"scenario": sc, "impact_headline": {k: imp[k] for k in ("unmet_units", "unmet_pct", "revenue_at_risk", "first_stockout")}}},
        {"key": "impact", "title": "Impact", "paragraphs": [], "bullets": impact_bullets,
         "evidence": {"impact": imp, "monte_carlo": mc, "baseline": ev["baseline"], "surrogate_preview": ev["surrogate_preview"]}},
        {"key": "cascade", "title": "Cascade timeline", "paragraphs": [], "bullets": [c["text"] for c in ev["cascade"]],
         "evidence": {"cascade": ev["cascade"]}},
        {"key": "recommended", "title": f"Recommended plan: {rec_row['label']}", "paragraphs": [rec_row["description"]], "bullets": why,
         "evidence": {"recommended": rec_row, "attribution": ev["attribution"], "do_nothing": ev["do_nothing"]}},
        {"key": "alternatives", "title": "Alternatives considered and why they were rejected", "paragraphs": [], "bullets": alts,
         "evidence": {"plans": ev["plans"], "pareto": [p["name"] for p in ev["plans"] if p["pareto"]]}},
        {"key": "risks", "title": "Risks and assumptions", "paragraphs": [], "bullets": risks,
         "evidence": {"sensitivity": ev["sensitivity"], "assumptions": sc["assumptions"]}},
        {"key": "confidence", "title": f"Confidence: {conf['level']}", "paragraphs": [], "bullets": conf["reasons"],
         "evidence": {"confidence": conf, "robustness": ev["robustness"], "sensitivity": ev["sensitivity"]}},
        {"key": "next_steps", "title": "Next steps checklist", "paragraphs": [], "bullets": steps,
         "evidence": {"next_steps": ev["next_steps"]}},
    ]


def next_steps(G: nx.DiGraph, rec_row: dict, plan: dict, events: list[Event], impact_: dict) -> list[dict]:
    w = plan.get("window") or [min((e.start for e in events), default=0)] * 2
    steps = [{"day": w[0], "text": f"Adopt '{rec_row['label']}' and brief the control tower."}]
    for a in rec_row["actions"]["inventory_actions"]:
        steps.append({"day": a["day"], "text": f"Move {units(a['units'])} units from {a['source']} to {a['node']} (pre-position)."})
    if rec_row["actions"]["backup_used"]:
        steps.append({"day": w[0], "text": "Trigger the backup supplier contract (supply opens after the activation lag)."})
    if rec_row["actions"]["rerouted_lanes"]:
        steps.append({"day": w[0], "text": f"Re-plan lanes {', '.join(rec_row['actions']['rerouted_lanes'][:6])}."})
    if rec_row["actions"]["expedited_lanes"]:
        steps.append({"day": w[0], "text": f"Book air capacity on {', '.join(rec_row['actions']['expedited_lanes'][:4])}."})
    for p in rec_row["actions"]["production_actions"]:
        steps.append({"day": p["start_day"], "text": f"Shift {units(p['units_per_day'])} units/day from {p['from_factory']} to {p['to_factory']} for {p['duration']} days."})
    for n, dlt in rec_row["actions"]["capacity_delta"].items():
        if dlt > 0 and not rec_row["actions"]["production_actions"]:
            steps.append({"day": w[0], "text": f"Authorise overtime at {n} (+{units(dlt)} units/day)."})
    if impact_["first_stockout"]:
        fs = impact_["first_stockout"]
        steps.append({"day": max(0, fs["day"] - 1), "text": f"Check stock at {fs['node']} (simulated stock-out day {fs['day']} without action)."})
    steps.append({"day": w[1] + 1, "text": "Stand down the extra measures once the disruption clears; review stock levels."})
    return sorted(steps, key=lambda s: s["day"])


# ---------------------------------------------------------------- 1-6 together
def run_whatif(G: nx.DiGraph, events: list[Event], horizon: int = HORIZON, mc_runs: int = 100, robustness_runs: int = 10,
               seed: int = 7, assumptions: list[str] | None = None, question: str | None = None, parser: str = "builder",
               narrator: Callable | None = None) -> dict:
    """The full what-if result: evidence, narrative sections and a Markdown brief. Never raises on small networks."""
    t0 = time.perf_counter()
    events = list(events)
    unit_price = G.graph.get("unit_price", 4200)
    if G.number_of_nodes() == 0 or total_demand(G) <= 0 or not events:
        why = "The network is empty." if G.number_of_nodes() == 0 else "The network has no demand." if total_demand(G) <= 0 else "The scenario has no events."
        return {"status": "empty", "note": why, "question": question, "events": [e.model_dump(exclude_none=True) for e in events],
                "sections": [], "evidence": {}, "plans": [], "brief_markdown": f"# What-if brief\n\n{why}\n"}
    base = simulate(G, [], horizon)
    scen = simulate(G, events, horizon)
    mc_raw = monte_carlo(G, events, n=mc_runs, seed=seed, horizon=horizon)
    mc = {**mc_raw, "runs": mc_runs, "p50_display": units(mc_raw["p50"]), "p90_display": units(mc_raw["p90"]),
          "p_shortage_pct": _r(100 * mc_raw["p_shortage"], 0)}
    imp = impact(G, base, scen, horizon)

    preview = None
    try:
        t = time.perf_counter()
        pred = risk_ml.predict_scenarios(G, [events], horizon=horizon)
        if pred:
            p = pred[0]
            preview = {"predicted": p, "ms": _r((time.perf_counter() - t) * 1000, 1),
                       "drivers": risk_ml.explain_scenario(G, events),
                       "agreement": {"predicted_unmet_pct": p["unmet_pct"]["point"], "exact_unmet_pct": imp["unmet_pct"],
                                     "within_interval": p["unmet_pct"]["low"] - 0.01 <= imp["unmet_pct"] <= p["unmet_pct"]["high"] + 0.01},
                       "note": "Fast ML preview; the exact simulator above is the source of truth."}
    except Exception as exc:  # noqa: BLE001 - the preview is optional
        preview = {"error": f"surrogate unavailable ({type(exc).__name__})"}

    rows, plans = evaluate_plans(G, events, horizon)
    rec = next(r for r in rows if r["recommended"])
    nothing = next(r for r in rows if r["name"] == "Do nothing")
    alternatives = [{"name": r["name"], "label": r["label"], "reason": _rejection(rec, r)} for r in rows if not r["recommended"]]
    attr = attribution(G, events, rec, nothing, horizon)
    others = sorted((r for r in rows if not r["recommended"] and r["safety"]["passed"]), key=lambda r: r["objective"])
    shortlist = [rec["name"]] + [r["name"] for r in others[:SHORTLIST - 1]]
    sens = sensitivity(G, events, shortlist, rec["name"], horizon)
    rob = robustness(G, events, shortlist, rec["name"], horizon, robustness_runs, seed)
    conf = confidence(rob, sens, mc, preview if preview and "agreement" in (preview or {}) else None)
    steps = next_steps(G, rec, plans[rec["name"]], events, imp)

    ev = {
        "label": "simulated",
        "scenario": {"question": question, "parser": parser, "events": [e.model_dump(exclude_none=True) for e in events],
                     "descriptions": [describe_event(G, e) for e in events], "assumptions": list(assumptions or []),
                     "horizon_days": horizon},
        "baseline": {"unmet_units": _r(base["total_unmet"], 1), "survival_clock_days": base["survival_clock_days"],
                     "delay_avg_days": base["delay"]["avg_days"]},
        "impact": imp, "monte_carlo": mc, "surrogate_preview": preview, "cascade": cascade(G, events, scen, base),
        "plans": rows, "recommended": {"name": rec["name"], "row": rec},
        "do_nothing": {"objective": nothing["objective"], "objective_display": nothing["objective_display"],
                       "unmet": nothing["unmet"], "unmet_display": nothing["unmet_display"]},
        "net_saving": _r(nothing["objective"] - rec["objective"], 0), "net_saving_display": inr(nothing["objective"] - rec["objective"]),
        "selection_rule": "lowest total cost of the disruption (plan cost + unmet units x unit price) among plans that "
                          "pass the fix-safety check; ties go to the plan with fewer levers.",
        "alternatives": alternatives, "attribution": attr, "sensitivity": sens, "robustness": rob, "confidence": conf,
        "next_steps": steps, "unit_price": unit_price,
        "model_constants": {"backup_activation_days": BACKUP_ACTIVATION_DAYS, "backup_cost_factor": BACKUP_COST_FACTOR,
                            "robust_tolerance_pct": ROBUST_TOL * 100, "resilience_scale_max": 100},
    }
    if narrator is None:
        from llm.parser import narrate_sections

        narrator = narrate_sections
    narr = narrative.narrate(ev, build_sections(ev), narrator)
    result = {
        "status": "ok", "question": question, "events": ev["scenario"]["events"], "horizon": horizon,
        "sections": narr["sections"], "narrative_source": narr["source"], "narrative_rejected": narr["rejected"],
        "evidence": ev, "plans": rows, "recommended": rec["name"], "confidence": conf["level"],
        "timeline": [{"day": r["day"], "unmet": r["unmet"]} for r in scen["timeline"]],
        "baseline_timeline": [{"day": r["day"], "unmet": r["unmet"]} for r in base["timeline"]],
        "elapsed_s": _r(time.perf_counter() - t0, 2),
    }
    result["brief_markdown"] = brief_markdown(result)
    return result


def brief_markdown(result: dict) -> str:
    """Exportable brief (Markdown). The UI prints the same content to PDF."""
    if result.get("status") != "ok":
        return f"# What-if brief\n\n{result.get('note', '')}\n"
    ev = result["evidence"]
    lines = [f"# What-if brief: {result.get('question') or '; '.join(ev['scenario']['descriptions'])}", "",
             f"*All figures simulated by the AEGIS engine ({ev['impact']['horizon_days']}-day horizon). "
             f"Narrative: {result['narrative_source']}. Confidence: {result['confidence']}.*", ""]
    for s in result["sections"]:
        lines.append(f"## {s['title']}")
        lines.append("")
        lines += [p for p in s.get("paragraphs", [])]
        if s.get("paragraphs"):
            lines.append("")
        lines += [f"- {b}" if not b.startswith("[ ]") else f"- {b}" for b in s.get("bullets", [])]
        lines.append("")
    lines += ["## Evidence: candidate plans", "", "| plan | cost | unmet units | avg delay (d) | recovery (d) | CO2 (t) | safety | total cost |",
              "|---|---:|---:|---:|---:|---:|---|---:|"]
    for p in ev["plans"]:
        lines.append(f"| {p['label']}{' (recommended)' if p['recommended'] else ''} | {p['cost_display']} | {p['unmet_display']} | "
                     f"{p['delay_avg_days']:.2f} | {p['recovery_days']} | {p['co2_t']:.2f} | {'pass' if p['safety']['passed'] else 'FAIL'} | "
                     f"{p['objective_display']} |")
    if ev["attribution"]["rows"]:
        lines += ["", "## Evidence: counterfactual attribution", "", "| lever | unmet without it | benefit | cost | net |", "|---|---:|---:|---:|---:|"]
        for a in ev["attribution"]["rows"]:
            lines.append(f"| {a['label']} | {units(a['unmet_without'])} | {a['marginal_benefit_display']} | {a['marginal_cost_display']} | {a['net_value_display']} |")
    lines += ["", "## Evidence: sensitivity", "", "| variant | best plan | recommended still best | regret |", "|---|---|---|---:|"]
    for s in ev["sensitivity"]:
        lines.append(f"| {s['variant']} | {s['best_plan']} | {'yes' if s['recommended_still_best'] else 'no'} | {s['regret_display']} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- history
class History:
    def __init__(self, limit: int = MAX_HISTORY):
        self._runs: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()
        self.limit = limit

    def add(self, result: dict, network: dict) -> str:
        rid = uuid.uuid4().hex[:10]
        with self._lock:
            result["id"] = rid
            result["network"] = network
            result["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            self._runs[rid] = result
            while len(self._runs) > self.limit:
                self._runs.popitem(last=False)
        return rid

    def get(self, rid: str) -> dict | None:
        return self._runs.get(rid)

    def list(self) -> list[dict]:
        with self._lock:
            return [summary(r) for r in reversed(self._runs.values())]

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()


def summary(r: dict) -> dict:
    ev = r.get("evidence") or {}
    imp = ev.get("impact") or {}
    rec = (ev.get("recommended") or {}).get("row") or {}
    return {
        "id": r.get("id"), "created": r.get("created"), "question": r.get("question"),
        "label": r.get("question") or "; ".join((ev.get("scenario") or {}).get("descriptions", [])) or r.get("note"),
        "network": r.get("network"), "status": r.get("status"),
        "unmet_units": imp.get("unmet_units"), "unmet_pct": imp.get("unmet_pct"),
        "survival_clock_days": imp.get("survival_clock_days"), "delay_avg_days": (imp.get("delay") or {}).get("avg_days"),
        "revenue_at_risk": imp.get("revenue_at_risk"), "mc_p90": (ev.get("monte_carlo") or {}).get("p90"),
        "p_shortage": (ev.get("monte_carlo") or {}).get("p_shortage"),
        "recommended": rec.get("label"), "recommended_cost": rec.get("cost"), "recommended_unmet": rec.get("unmet"),
        "net_saving": ev.get("net_saving"), "confidence": r.get("confidence"),
    }


history = History()


def compare(ids: list[str]) -> dict:
    runs = [history.get(i) for i in ids]
    missing = [i for i, r in zip(ids, runs) if r is None]
    if missing:
        raise KeyError(f"unknown what-if run(s): {', '.join(missing)}")
    rows = [summary(r) for r in runs]
    metrics = [("unmet_units", "Unmet demand (units, simulated)"), ("unmet_pct", "Unmet demand (% of demand)"),
               ("survival_clock_days", "First stock-out (day)"), ("delay_avg_days", "Avg extra delay (days)"),
               ("revenue_at_risk", "Revenue at risk (INR)"), ("mc_p90", "Monte Carlo P90 unmet (units)"),
               ("p_shortage", "Shortage probability"), ("recommended", "Recommended plan"),
               ("recommended_cost", "Plan cost (INR)"), ("recommended_unmet", "Unmet with plan (units)"),
               ("net_saving", "Net saving vs doing nothing (INR)"), ("confidence", "Confidence")]
    return {"runs": rows, "metrics": [{"key": k, "label": label, "values": [r.get(k) for r in rows]} for k, label in metrics]}


# ---------------------------------------------------------------- follow-up Q&A (whitelisted tools)
TOOLS = ("run_scenario", "run_strategy", "compare_plans")
DECLINE = ("I can only answer questions the engine can test: comparing plans (\"Why not air freight?\"), running one "
           "plan (\"Try the inventory buffer\"), or changing the scenario (\"What if the backup supplier is also delayed?\").")


def _plan_from_text(q: str) -> str | None:
    low = q.lower()
    for words, plan in PLAN_KEYWORDS:
        if any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low) for w in words):
            return plan
    for name in candidate_names([]) + [strat.WEATHER_STRATEGY]:
        if name.lower() in low:
            return name
    return None


def route(question: str, run: dict, G: nx.DiGraph) -> dict:
    """Deterministic router: {"tool": name, "args": {...}} or {"decline": reason}."""
    q = question.strip()
    low = q.lower()
    rec = run["recommended"]
    plan = _plan_from_text(q)
    if re.search(r"\b(what if|suppose|and if|also|as well|too|additionally)\b", low):
        backup_q = "backup" in low and any(w in low for w in SLOW_WORDS + FAIL_WORDS)
        if backup_q:
            backups = [n for n, d in G.nodes(data=True) if d.get("backup")]
            if not backups:
                return {"decline": "This network has no backup supplier, so there is nothing to delay."}
            m = _DUR.search(q)
            days = int(float(m.group(1)) * (7 if m.group(2).lower().startswith("w") else 1)) if m else 5
            start = min(e["start"] for e in run["events"])
            add = [{"type": "node", "target": b, "start": start, "duration": days, "severity": 1.0} for b in backups]
            return {"tool": "run_scenario", "args": {"add_events": add,
                                                     "assumption": f"Backup supplier delayed: modelled as unavailable for the first {days} days of the disruption."}}
        try:
            events, notes = rule_parse(q, G, run.get("horizon", HORIZON))
            return {"tool": "run_scenario", "args": {"add_events": [e.model_dump(exclude_none=True) for e in events],
                                                     "assumption": " ".join(notes) or None}}
        except WhatIfError:
            pass
    if plan and re.search(r"\b(why not|why didn't|why did not|why no|what about|instead|rather than|vs|versus|compare|better than)\b", low):
        if plan == rec:
            return {"tool": "run_strategy", "args": {"name": plan}}
        return {"tool": "compare_plans", "args": {"names": [rec, plan]}}
    if plan and re.search(r"\b(try|run|apply|use|simulate|show|what does|what would|how much)\b", low):
        return {"tool": "run_strategy", "args": {"name": plan}}
    if plan:
        return {"tool": "compare_plans", "args": {"names": [rec, plan]}}
    return {"decline": DECLINE}


def tool_run_scenario(G: nx.DiGraph, run: dict, add_events: list[dict], assumption: str | None = None) -> dict:
    from validation import validate_events

    from core.graph import node_index

    base_events = [Event.model_validate(e) for e in run["events"]]
    extra = validate_events([Event.model_validate(e) for e in add_events], *node_index(G))
    events = base_events + extra
    horizon = run.get("horizon", HORIZON)
    scen = simulate(G, events, horizon)
    base = simulate(G, [], horizon)
    imp = impact(G, base, scen, horizon)
    rows, _ = evaluate_plans(G, events, horizon)
    rec = next(r for r in rows if r["recommended"])
    old = run["evidence"]["impact"]
    old_rec = run["evidence"]["recommended"]["row"]
    return {
        "tool": "run_scenario", "label": "simulated", "added_events": [describe_event(G, e) for e in extra],
        "assumption": assumption,
        "before": {"unmet_units": old["unmet_units"], "unmet_display": old["unmet_units_display"], "survival_clock_days": old["survival_clock_days"],
                   "revenue_at_risk_display": old["revenue_at_risk_display"], "recommended": old_rec["label"],
                   "recommended_unmet_display": old_rec["unmet_display"], "recommended_cost_display": old_rec["cost_display"]},
        "after": {"unmet_units": imp["unmet_units"], "unmet_display": imp["unmet_units_display"], "survival_clock_days": imp["survival_clock_days"],
                  "revenue_at_risk_display": imp["revenue_at_risk_display"], "recommended": rec["label"],
                  "recommended_unmet_display": rec["unmet_display"], "recommended_cost_display": rec["cost_display"],
                  "recommended_objective_display": rec["objective_display"]},
        "extra_unmet_units": _r(imp["unmet_units"] - old["unmet_units"], 1),
        "extra_unmet_display": units(imp["unmet_units"] - old["unmet_units"]),
        "plans": [{k: r[k] for k in ("label", "cost_display", "unmet_display", "objective_display", "recommended")} for r in rows],
    }


def _plan_row(G: nx.DiGraph, run: dict, name: str) -> dict:
    for r in run["plans"]:
        if r["name"] == name:
            return r
    events = [Event.model_validate(e) for e in run["events"]]
    plan = solve_candidate(G, events, name, horizon=run.get("horizon", HORIZON))
    return _row(G, name, plan, strat.safety_check(G, events, plan))


def tool_run_strategy(G: nx.DiGraph, run: dict, name: str) -> dict:
    if name not in candidate_names([Event.model_validate(e) for e in run["events"]]):
        raise WhatIfError(f"Unknown plan {name!r}.")
    r = _plan_row(G, run, name)
    rec = run["evidence"]["recommended"]["row"]
    return {"tool": "run_strategy", "label": "simulated", "plan": {k: r[k] for k in (
        "label", "cost_display", "unmet_display", "delay_avg_days", "recovery_days", "co2_t", "objective_display", "description")},
        "safety": r["safety"], "is_recommended": r["name"] == rec["name"],
        "recommended": {k: rec[k] for k in ("label", "objective_display", "unmet_display", "cost_display")},
        "difference_display": inr(r["objective"] - rec["objective"])}


def tool_compare_plans(G: nx.DiGraph, run: dict, names: list[str]) -> dict:
    valid = candidate_names([Event.model_validate(e) for e in run["events"]])
    bad = [n for n in names if n not in valid]
    if bad:
        raise WhatIfError(f"Unknown plan(s): {', '.join(bad)}.")
    rows = [_plan_row(G, run, n) for n in names[:4]]
    keep = ("name", "label", "cost", "cost_display", "unmet", "unmet_display", "delay_avg_days", "recovery_days", "co2_t",
            "objective", "objective_display", "safety", "recommended")
    out = {"tool": "compare_plans", "label": "simulated", "rows": [{k: r[k] for k in keep} for r in rows]}
    if len(rows) >= 2:
        a, b = rows[0], rows[1]
        out["difference"] = {"objective_display": inr(b["objective"] - a["objective"]), "cost_display": inr(b["cost"] - a["cost"]),
                             "unmet_units": _r(b["unmet"] - a["unmet"], 1), "unmet_display": units(abs(b["unmet"] - a["unmet"])),
                             "delay_days": _r(b["delay_avg_days"] - a["delay_avg_days"], 2), "co2_t": _r(b["co2_t"] - a["co2_t"], 2),
                             "reason": _rejection(a, b) if a["recommended"] else None}
    return out


def answer_text(ev: dict) -> list[str]:
    """Deterministic answer from a tool's evidence."""
    t = ev["tool"]
    if t == "compare_plans":
        rows = ev["rows"]
        out = [f"{r['label']}: plan cost {r['cost_display']}, {r['unmet_display']} units unmet, {r['delay_avg_days']:.2f} days avg delay, "
               f"total cost of the disruption {r['objective_display']}{'' if r['safety']['passed'] else ' (fails the fix-safety check)'} (simulated)."
               for r in rows]
        d = ev.get("difference")
        if d and d.get("reason"):
            out.insert(0, f"Why not {rows[1]['label']}? {d['reason']}")
        elif d:
            out.insert(0, f"{rows[1]['label']} vs {rows[0]['label']}: total cost difference {d['objective_display']}.")
        return out
    if t == "run_strategy":
        p = ev["plan"]
        head = (f"{p['label']} is the recommended plan." if ev["is_recommended"] else
                f"{p['label']} would cost {ev['difference_display']} more in total than {ev['recommended']['label']} ({p['objective_display']} vs "
                f"{ev['recommended']['objective_display']}).")
        return [head, f"Simulated outcome: plan cost {p['cost_display']}, {p['unmet_display']} units unmet, {p['delay_avg_days']:.2f} days average "
                      f"extra delay, recovery in {p['recovery_days']} days, {p['co2_t']:.2f} t CO2.",
                f"Fix-safety check: {'passed' if ev['safety']['passed'] else 'failed - ' + str(ev['safety']['warning'])}."]
    b, a = ev["before"], ev["after"]
    out = [f"Adding {'; '.join(ev['added_events'])}: unmet demand goes from {b['unmet_display']} to {a['unmet_display']} units "
           f"({ev['extra_unmet_display']} more), first stock-out day {b['survival_clock_days']} -> {a['survival_clock_days']}, revenue at risk "
           f"{b['revenue_at_risk_display']} -> {a['revenue_at_risk_display']} (simulated).",
           f"Recommended plan: {b['recommended']} -> {a['recommended']} ({a['recommended_unmet_display']} units unmet, plan cost "
           f"{a['recommended_cost_display']}, total {a['recommended_objective_display']})."]
    if ev.get("assumption"):
        out.append(f"Assumption: {ev['assumption']}")
    return out


def ask(G: nx.DiGraph, run: dict, question: str, router: Callable | None = None, narrator: Callable | None = None) -> dict:
    """Route a follow-up question to ONE whitelisted engine tool, run it, and narrate its evidence."""
    call = None
    source = "rules"
    if router is not None:
        try:
            call = router(question, run, G)
            source = "llm"
        except Exception:  # noqa: BLE001 - no key / API trouble: deterministic routing
            call = None
    if call is None:
        call = route(question, run, G)
    if "decline" in call:
        return {"question": question, "declined": True, "answer": [call["decline"]], "tool": None, "evidence": None, "router": source}
    name, args = call.get("tool"), dict(call.get("args") or {})
    if name not in TOOLS:
        return {"question": question, "declined": True, "tool": None, "evidence": None, "router": source,
                "answer": [f"'{name}' is not one of the engine functions I may call ({', '.join(TOOLS)}). {DECLINE}"]}
    fn = {"run_scenario": tool_run_scenario, "run_strategy": tool_run_strategy, "compare_plans": tool_compare_plans}[name]
    allowed = {"run_scenario": {"add_events", "assumption"}, "run_strategy": {"name"}, "compare_plans": {"names"}}[name]
    args = {k: v for k, v in args.items() if k in allowed}
    try:
        ev = fn(G, run, **args)
    except (WhatIfError, ValueError, KeyError, TypeError) as exc:
        return {"question": question, "declined": True, "tool": {"name": name, "args": args}, "evidence": None, "router": source,
                "answer": [f"The engine could not run that: {exc}"]}
    template = [{"key": "answer", "title": "Answer", "paragraphs": [], "bullets": answer_text(ev)}]
    if narrator is None:
        from llm.parser import narrate_sections

        narrator = narrate_sections
    narr = narrative.narrate(ev, template, narrator)
    return {"question": question, "declined": False, "tool": {"name": name, "args": args}, "evidence": ev, "router": source,
            "answer": narr["sections"][0]["bullets"], "narrative_source": narr["source"], "narrative_rejected": narr["rejected"]}
