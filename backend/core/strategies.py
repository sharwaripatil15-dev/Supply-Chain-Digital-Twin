"""Strategy comparison, fix-safety check, recommendation and ROI. Owner: B.

Strategies (each a core.optimizer plan with a lever set; "Do nothing" is the plan with no levers):
    Do nothing        today's lane allocations, no backup; stock at demand nodes absorbs what it can
    Reroute only      re-plan flows across all existing lanes
    Reroute + backup  ... and trigger the backup supplier contract (fee, opens after the activation lag)
    Inventory buffer  pre-position finished goods at warehouses (no rerouting)
    Production shift  move production between plants, with the rerouting it needs
    Full plan         every lever, standard CO2 price
    Green plan        every lever with a 15x CO2 price (trades cost for emissions)
    Weather-aware reroute   (only when the scenario has weather events) reroute + inventory buffer, planned on lane
                      costs that price weather: + WEATHER_RISK_INR x severity and + WEATHER_DAY_INR per extra day of lead
                      time (lead x (lead_multiplier - 1)), so flows leave storm-hit lanes before they fail and stock is
                      staged ahead of the window. Costs are reported at real lane prices.

Fix-safety check (the USP): a fix must not leave the network more fragile than it was.
    Apply the plan to a copy of the graph *as it runs during the disruption*: every event at full effect, the plan's
    capacity changes (overtime, production moved between plants), and the backup supplier only if the plan
    contracts it. Re-run core.chaos on that copy and on the same disrupted copy without the plan ("before"). Fail if
      * a single additional failure would leave > NEW_SPOF_THRESHOLD of demand unmet with the plan, while it would not
        without it (the fix created a new single point of failure), or
      * the resilience score with the plan is lower than without it.
    Because the check is capacity-based, only levers that take capacity away (production shift) can fail it;
    levers that add capacity (overtime, backup) or move stock/flows cannot make a single failure worse.
Recommendation: the passing strategy with the lowest cost + unmet x unit price (fewer levers breaks ties).
ROI: inaction loss = Do nothing unmet x unit price; fix cost = recommended cost + its residual unmet x unit price.
"""
from __future__ import annotations

from typing import Iterable

import networkx as nx

from core import chaos
from core.optimizer import LEVERS, W_CO2, baseline, lane_cost, optimize_plan
from core.sim import _active_state, spike_baseline
from schemas import Event

NEW_SPOF_THRESHOLD = 0.30
RESILIENCE_TOLERANCE = 0.5
GREEN_CO2_MULTIPLIER = 15
WEATHER_STRATEGY = "Weather-aware reroute"
WEATHER_LEVERS = ("reroute", "safety_stock")
WEATHER_RISK_INR = 250.0  # per unit shipped on a lane at full weather severity
WEATHER_DAY_INR = 40.0  # per unit per extra day of weather lead time

STRATEGIES = [
    ("Do nothing", (), W_CO2),
    ("Reroute only", ("reroute",), W_CO2),
    ("Reroute + backup", ("reroute", "backup"), W_CO2),
    ("Inventory buffer", ("safety_stock",), W_CO2),
    ("Production shift", ("reroute", "production_shift"), W_CO2),
    ("Full plan", LEVERS, W_CO2),
    ("Green plan", LEVERS, W_CO2 * GREEN_CO2_MULTIPLIER),
]


def _peak_state(events: list[Event], baseline: dict | None = None) -> tuple[dict, dict, dict]:
    """Every event at full effect at once (worst factor per target; peak forecast-based spike per customer)."""
    node_f: dict = {}
    edge_f: dict = {}
    mult: dict = {}
    for ev in events:
        for day in range(ev.start, ev.start + ev.duration):
            nf, ef, m = _active_state([ev], day, baseline)
            for k, v in nf.items():
                node_f[k] = min(node_f.get(k, 1.0), v)
            for k, v in ef.items():
                edge_f[k] = min(edge_f.get(k, 1.0), v)
            for k, v in m.items():
                mult[k] = max(mult.get(k, 1.0), v)
            if ev.type != "demand":
                break  # capacity events are constant over their duration
    return node_f, edge_f, mult


def plan_graph(G: nx.DiGraph, events: Iterable[Event], plan: dict | None = None) -> nx.DiGraph:
    """Copy of G as it runs during the disruption under `plan` (None = do nothing)."""
    H = G.copy()
    events = list(events)
    node_f, edge_f, mult = _peak_state(events, spike_baseline(G, events, 30))
    for n, f in node_f.items():
        H.nodes[n]["capacity"] *= max(0.0, f)
    for e, f in edge_f.items():
        H.edges[e]["capacity"] *= max(0.0, f)
    for c, m in mult.items():
        H.nodes[c]["demand"] *= m
    for n, delta in (plan or {}).get("capacity_delta", {}).items():
        if H.nodes[n]["capacity"] > 0:
            H.nodes[n]["capacity"] = max(0.0, H.nodes[n]["capacity"] + delta)
    if not (plan or {}).get("backup_used"):
        for n, d in H.nodes(data=True):
            if d.get("backup"):
                d["capacity"] = 0.0  # no contract triggered: the backup cannot help with the next failure either
    return H


def safety_check(G: nx.DiGraph, events: Iterable[Event], plan: dict | None) -> dict:
    """Return {passed, warning, resilience_after}. See the module docstring for the rules.

    "Before" is the same disrupted network with no plan applied (doing nothing); "after" has the plan applied.
    """
    events = list(events)
    before_graph = plan_graph(G, events, None)
    after_graph = plan_graph(G, events, plan)
    before = chaos.scan(before_graph)["singles"]
    after = chaos.scan(after_graph)["singles"]
    resilience_before = chaos.resilience_score(before_graph)
    resilience_after = chaos.resilience_score(after_graph)
    problems = []
    new_spofs = sorted(((t, u) for t, u in after.items() if u > NEW_SPOF_THRESHOLD and before.get(t, 0.0) <= NEW_SPOF_THRESHOLD),
                       key=lambda kv: -kv[1])
    if new_spofs:
        t, u = new_spofs[0]
        more = f" (and {len(new_spofs) - 1} more)" if len(new_spofs) > 1 else ""
        problems.append(f"Creates a new single point of failure: with this plan running, losing {_label(G, t)} would leave "
                        f"{u:.0%} of demand unmet, versus {before.get(t, 0.0):.0%} without the plan{more}.")
    if resilience_after < resilience_before - RESILIENCE_TOLERANCE:
        problems.append(f"Resilience falls from {resilience_before:.1f} to {resilience_after:.1f}.")
    return {"passed": not problems, "warning": " ".join(problems) or None, "resilience_after": resilience_after}


def _label(G: nx.DiGraph, target: str) -> str:
    if "->" in target:
        u, v = target.split("->")
        return f"lane {u}->{v}"
    return f"{target} {G.nodes[target].get('name', '')}".strip()


def _describe(name: str, plan: dict) -> str:
    bits = []
    if plan["rerouted_lanes"]:
        bits.append(f"reroutes {len(plan['rerouted_lanes'])} lane(s)")
    if plan["backup_used"]:
        bits.append("triggers the backup supplier")
    if plan["inventory_actions"]:
        bits.append(f"pre-positions {sum(a['units'] for a in plan['inventory_actions']):,} units")
    if plan["production_actions"]:
        bits.append(f"shifts production {', '.join(a['from_factory'] + '->' + a['to_factory'] for a in plan['production_actions'])}")
    if plan["cost_breakdown"].get("overtime"):
        bits.append("adds overtime")
    stock = f" Uses {plan['stock_drawn']:,.0f} units of retailer/customer stock." if plan["stock_drawn"] else ""
    if name == "Do nothing":
        return "Keep today's lane allocations; retailer/customer stock absorbs what it can." + stock
    if not bits:
        return "No lever in this strategy helps here; same outcome as re-planning alone." + stock
    prefix = {"Green plan": "Prices CO2 15x higher: ", WEATHER_STRATEGY: "Prices weather risk into lane costs: "}.get(name, "")
    text = "; ".join(bits)
    return prefix + text[0].upper() + text[1:] + "." + stock


def has_weather(events: Iterable[Event]) -> bool:
    return any(getattr(e, "source", None) == "weather" for e in events)


def weather_priced_graph(G: nx.DiGraph, events: Iterable[Event]) -> nx.DiGraph:
    """Copy of G whose lane costs include the weather price of the (worst) weather event on each lane."""
    H = G.copy()
    worst: dict[tuple[str, str], tuple[float, float]] = {}
    for ev in events:
        if ev.type != "edge" or getattr(ev, "source", None) != "weather":
            continue
        u, v = (p.strip() for p in ev.target.split("->"))
        sev, lead = worst.get((u, v), (0.0, 1.0))
        worst[(u, v)] = (max(sev, ev.severity), max(lead, ev.lead_multiplier or 1.0))
    for (u, v), (sev, lead) in worst.items():
        if (u, v) in H.edges:
            d = H.edges[u, v]
            d["cost"] = d["cost"] + WEATHER_RISK_INR * sev + WEATHER_DAY_INR * d["lead"] * (lead - 1.0)
    return H


def weather_plan(G: nx.DiGraph, events: list[Event], horizon: int = 30) -> dict:
    """The weather-aware plan, optimised on weather-priced lanes, then costed at real lane prices."""
    plan = optimize_plan(weather_priced_graph(G, events), events, WEATHER_LEVERS, horizon=horizon)
    if plan["daily_flows"]:
        base = baseline(G)
        transport = sum(lane_cost(G, *e) * f for flows in plan["daily_flows"] for e, f in flows.items())
        delivered = sum(base["flow"]["served"].values()) * len(plan["daily_flows"]) - plan["unmet"] - plan["stock_drawn"]
        plan["cost_breakdown"]["extra_freight"] = round(max(0.0, transport - base["cost_per_unit"] * max(0.0, delivered)), 0)
        plan["cost"] = round(sum(plan["cost_breakdown"].values()), 0)
    return plan


def run_strategies(G: nx.DiGraph, events: Iterable[Event], horizon: int = 30) -> list[dict]:
    """Strategy rows in the RecoverResponse shape, plus a private "_plan" per row (stripped by the API)."""
    events = list(events)
    unit_price = G.graph.get("unit_price", 4200)
    strategies = list(STRATEGIES)
    plans = {name: optimize_plan(G, events, levers, horizon=horizon, w_co2=w_co2) for name, levers, w_co2 in strategies}
    if has_weather(events):
        strategies.append((WEATHER_STRATEGY, WEATHER_LEVERS, W_CO2))
        plans[WEATHER_STRATEGY] = weather_plan(G, events, horizon)
    rows = []
    for name, levers, _ in strategies:
        plan = plans[name]
        check = safety_check(G, events, plan)
        rows.append({
            "name": name,
            "cost": float(plan["cost"]),
            "unmet": float(plan["unmet"]),
            "recovery_days": int(plan["recovery_days"]),
            "delay_avg_days": float(plan["delay"]["avg_days"]),
            "co2": float(plan["co2"]),
            "resilience_after": check["resilience_after"],
            "safety_check": {"passed": check["passed"], "warning": check["warning"]},
            "recommended": False,
            "description": _describe(name, plan),
            "_levers": len(levers),
            "_plan": plan,
        })
    passing = [r for r in rows if r["safety_check"]["passed"]] or rows
    best = min(passing, key=lambda r: (r["cost"] + r["unmet"] * unit_price, r["_levers"]))
    best["recommended"] = True
    return rows


def roi(G: nx.DiGraph, rows: list[dict]) -> dict:
    unit_price = G.graph.get("unit_price", 4200)
    nothing = next(r for r in rows if r["name"] == "Do nothing")
    rec = next((r for r in rows if r["recommended"]), nothing)
    inaction = round(nothing["unmet"] * unit_price, 0)
    fix = round(rec["cost"] + rec["unmet"] * unit_price, 0)
    return {"inaction_loss": inaction, "fix_cost": fix, "net_saving": round(inaction - fix, 0)}


def fmt_inr(v: float) -> str:
    """₹ in lakh/crore, matching the UI's formatting."""
    a, sign = abs(v), "-" if v < 0 else ""
    if a >= 1e7:
        return f"{sign}₹{a / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a / 1e5:.1f} L"
    return f"{sign}₹{a:,.0f}"


def playbook_facts(G: nx.DiGraph, rows: list[dict], roi_: dict) -> dict:
    """The only material the LLM narrator sees: engine numbers plus preformatted strings it may copy verbatim."""
    rec = next(r for r in rows if r["recommended"])
    plan = rec["_plan"]
    return {
        "recommended_strategy": {
            "name": rec["name"], "cost": rec["cost"], "cost_display": fmt_inr(rec["cost"]), "unmet_units": rec["unmet"],
            "recovery_days": rec["recovery_days"], "co2_tonnes": rec["co2"], "description": rec["description"],
            "window_days": plan["window"], "backup_supplier_triggered": plan["backup_used"],
            "rerouted_lanes": plan["rerouted_lanes"], "inventory_actions": plan["inventory_actions"],
            "production_actions": plan["production_actions"],
        },
        "rejected_cheaper_options": [
            {"name": r["name"], "cost_display": fmt_inr(r["cost"]), "unmet_units": r["unmet"], "safety_warning": r["safety_check"]["warning"]}
            for r in rows if r["cost"] < rec["cost"] and not r["recommended"]
        ],
        "roi": {**roi_, "inaction_loss_display": fmt_inr(roi_["inaction_loss"]), "fix_cost_display": fmt_inr(roi_["fix_cost"]),
                "net_saving_display": fmt_inr(roi_["net_saving"])},
    }


def template_playbook(G: nx.DiGraph, events: list[Event], rows: list[dict]) -> list[str]:
    """Deterministic playbook built only from engine output (used when the LLM narrator is unavailable)."""
    rec = next(r for r in rows if r["recommended"])
    plan = rec["_plan"]
    window = plan["window"] or [0, 0]
    steps = [f"Day {window[0]}: adopt '{rec['name']}' - expected unmet {rec['unmet']:,.0f} units, cost ₹{rec['cost']:,.0f}."]
    for a in plan["inventory_actions"]:
        steps.append(f"Day {a['day']}: move {a['units']:,} units from {a['source']} to {a['node']} (pre-position).")
    if plan["backup_used"]:
        steps.append(f"Day {window[0]}: trigger the backup supplier contract; supply opens after the activation lag.")
    if plan["rerouted_lanes"]:
        steps.append(f"Day {window[0]}: re-plan lanes {', '.join(plan['rerouted_lanes'][:6])}.")
    for p in plan["production_actions"]:
        steps.append(f"Day {p['start_day']}: shift {p['units_per_day']:,}/day from {p['from_factory']} to {p['to_factory']} for {p['duration']} days.")
    for r in rows:
        if not r["safety_check"]["passed"] and r["cost"] < rec["cost"]:
            steps.append(f"Avoid '{r['name']}' even though it is cheaper: {r['safety_check']['warning']}")
            break
    steps.append(f"Day {window[1] + 1}: stand down extra measures once lanes recover; review stock levels.")
    day = lambda s: int(s.split(":")[0].split()[1]) if s.startswith("Day ") else window[0]  # noqa: E731
    return sorted(steps, key=day)  # stable: same-day steps keep their order
