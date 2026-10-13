"""Weather-aware route planning: for every flow-carrying lane the forecast blocks, rank what to do instead.

Weighted view of the graph (one per risk window): every lane's effective cost per unit is
    cost + LAMBDA_TIME x effective lead + LAMBDA_RISK x risk + LAMBDA_CO2 x CO2
where effective lead = lead x the weather lead factor and risk is the lane's worst risk in the window; closed lanes are
removed. A lane is "blocked" when it carries flow at baseline (min-cost flow, no disruption) and reaches high or
severe risk (or closes) inside the horizon, or when it is the target of a given weather event with severity >= 0.4 or
lead factor >= 1.6.

For each blocked lane (largest flows first, at most MAX_BLOCKED):
    original path   the baseline path through the lane: largest inbound flow upstream to a supplier, largest outbound
                    flow downstream to a demand node
    alternatives    up to K = 3 loop-free paths from any supplier to that demand node that avoid the lane (Yen's
                    k-shortest paths: networkx.shortest_simple_paths on the weighted view)
    mode switch     the same path with the blocked hop moved to another mode (road -> rail; road -> air when the unit
                    value is high and the hop is long; sea -> road / rail). Lead, cost and CO2 come from
                    node_types.MODE_DEFAULTS; its weather risk is the same samples scored with that mode's
                    sensitivities (scoring.MODE_SENSITIVITY); capacity is assumed equal to the lane's (contracted)
    wait it out     when the window is <= WAIT_MAX_DAYS days: hold shipments until the lane reopens; viable if the
                    demand node's stock covers the wait
    pre-position    move the window's volume to the lane's downstream site the day before the window opens (feeds
                    the optimizer's inventory lever); viable if the window starts on day 1 or later
    dispatch window the lowest-risk day in the horizon to ship on the original path, and the last safe day before
                    the window opens
Each alternative reports ETA (days), cost and CO2 per unit with deltas against the original path in normal weather,
residual weather risk, spare capacity, and a safety check:
    * utilization: moving the lane's baseline flow onto the path must not push any site on it above 90% of its
      (weather-reduced) capacity
    * single point of failure: in the weather-degraded network, losing a site on the path must not cost more than 30%
      of demand when it would not in normal weather
The recommended alternative is the lowest scored option that passes the safety check (the lowest overall if none
does). Score = effective cost + a capacity-shortfall penalty. "Wait" becomes the recommended action when it is viable
and cheaper per unit than the recommended reroute.
"""
from __future__ import annotations

from itertools import islice

import networkx as nx

from core import chaos
from core.hazards.impact_mapping import impact
from core.optimizer import lane_cost
from core.sim import solve_flow
from node_types import MODE_DEFAULTS, haversine_km, is_demand, suggest_co2, suggest_cost, suggest_lead

K_ALTERNATIVES = 3
MAX_BLOCKED = 8
LAMBDA_TIME = 40.0  # INR per unit per day in transit (holding, service level)
LAMBDA_RISK = 250.0  # INR per unit at risk 1 (expected loss and handling of weather damage)
LAMBDA_CO2 = 4.0  # INR per kg CO2 (same price as the optimizer)
SHORTFALL_PENALTY = 400.0  # INR per unit when the path cannot carry the whole flow (scaled by the missing share)
WAIT_MAX_DAYS = 3
UTIL_LIMIT = 0.9
SPOF_THRESHOLD = 0.30
HIGH_VALUE_INR = 3000.0
AIR_MIN_KM = 500.0
PREPO_COST = 35.0
HOLDING_PER_DAY = 1.5
SRC = "__SRC__"

MODE_SWITCH = {"road": ("rail", "air"), "rail": ("road",), "sea": ("rail", "road"), "air": ("road",)}


def _blocking(row: dict) -> bool:
    return row["closed"] or row["level"] in ("high", "severe")


def _window(daily: list[dict]) -> tuple[int, int] | None:
    """First contiguous run of blocking days."""
    start = next((r["day"] for r in daily if _blocking(r)), None)
    if start is None:
        return None
    end = start
    while end + 1 < len(daily) and _blocking(daily[end + 1]):
        end += 1
    return start, end


def _label(G: nx.DiGraph, n: str) -> str:
    d = G.nodes[n]
    return f"{n} {d.get('name') or ''}".strip()


def _city(G: nx.DiGraph, n: str) -> str:
    return G.nodes[n].get("city") or n


def _km(G: nx.DiGraph, u: str, v: str) -> float:
    d = G.edges[u, v]
    if d.get("distance_km"):
        return float(d["distance_km"])
    a, b = G.nodes[u], G.nodes[v]
    try:
        return haversine_km((float(a["lat"]), float(a["lon"])), (float(b["lat"]), float(b["lon"])))
    except (KeyError, TypeError, ValueError):
        return 0.0


def _main_path(G: nx.DiGraph, flow: dict, u: str, v: str) -> list[str]:
    up = [u]
    node = u
    while G.nodes[node].get("kind") != "supplier":
        preds = [p for p in G.predecessors(node) if p not in up]
        if not preds:
            break
        node = max(preds, key=lambda p: flow.get((p, node), 0.0))
        up.append(node)
    down = [v]
    node = v
    while not is_demand(G.nodes[node].get("kind")) or (G.out_degree(node) and any(flow.get((node, q), 0) > 0 for q in G.successors(node))):
        succ = [q for q in G.successors(node) if q not in down and q not in up]
        if not succ:
            break
        node = max(succ, key=lambda q: flow.get((node, q), 0.0))
        down.append(node)
    return up[::-1] + down


class Planner:
    def __init__(self, G: nx.DiGraph, risk: dict, score_as=None):
        self.G = G
        self.risk = risk
        self.score_as = score_as
        self.days = risk.get("horizon", len(risk.get("dates", [])))
        self.edge_daily = {tuple(e["id"].split("->")): e["daily"] for e in risk.get("edges", [])}
        self.node_daily = {n["id"]: n["daily"] for n in risk.get("nodes", [])}
        self.base = solve_flow(G)
        self.unit_price = float(G.graph.get("unit_price", 4200))
        self._spof_cache: dict = {}
        self._peak_graph = None

    # ------------------------------------------------ per-window view
    def edge_state(self, e: tuple[str, str], window: tuple[int, int]) -> dict:
        daily = self.edge_daily.get(e) or []
        rows = daily[window[0]:window[1] + 1] or [{"risk": 0.0, "closed": False, "lead_multiplier": 1.0, "capacity_multiplier": 1.0, "level": "low"}]
        worst = max(rows, key=lambda r: r["risk"])
        return {"risk": worst["risk"], "closed": any(r["closed"] for r in rows),
                "lead_mult": max(r["lead_multiplier"] for r in rows), "cap_mult": min(r["capacity_multiplier"] for r in rows),
                "level": worst["level"]}

    def node_state(self, n: str, window: tuple[int, int]) -> dict:
        rows = (self.node_daily.get(n) or [])[window[0]:window[1] + 1]
        if not rows:
            return {"risk": 0.0, "cap_mult": 1.0, "closed": False}
        return {"risk": max(r["risk"] for r in rows), "cap_mult": min(r["capacity_multiplier"] for r in rows),
                "closed": any(r["closed"] for r in rows)}

    def weighted_view(self, window: tuple[int, int], drop: tuple[str, str] | None = None) -> nx.DiGraph:
        H = nx.DiGraph()
        for n, d in self.G.nodes(data=True):
            if self.node_state(n, window)["closed"] and not is_demand(d.get("kind")):
                continue
            H.add_node(n)
        for u, v, d in self.G.edges(data=True):
            if (u, v) == drop or u not in H or v not in H:
                continue
            st = self.edge_state((u, v), window)
            if st["closed"]:
                continue
            lead = d["lead"] * st["lead_mult"]
            H.add_edge(u, v, w=lane_cost(self.G, u, v) + LAMBDA_TIME * lead + LAMBDA_RISK * st["risk"] + LAMBDA_CO2 * d.get("co2", 0.0))
        H.add_node(SRC)
        for n, d in self.G.nodes(data=True):
            if d.get("kind") == "supplier" and n in H:
                H.add_edge(SRC, n, w=0.0)
        return H

    # ------------------------------------------------ path metrics
    def path_metrics(self, path: list[str], window: tuple[int, int], weather: bool = True, override: dict | None = None) -> dict:
        override = override or {}
        eta = cost = co2 = 0.0
        risk = 0.0
        spare = float("inf")
        for a, b in zip(path, path[1:]):
            d = self.G.edges[a, b]
            o = override.get((a, b))
            if o:
                eta += o["lead"] * (o["lead_mult"] if weather else 1.0)
                cost += o["cost"]
                co2 += o["co2"]
                risk = max(risk, o["risk"] if weather else 0.0)
                continue
            st = self.edge_state((a, b), window) if weather else {"lead_mult": 1.0, "risk": 0.0, "cap_mult": 1.0}
            eta += d["lead"] * st["lead_mult"]
            cost += lane_cost(self.G, a, b)
            co2 += d.get("co2", 0.0)
            risk = max(risk, st["risk"])
            spare = min(spare, d["capacity"] * st["cap_mult"] - self.base["flow"].get((a, b), 0.0))
        for n in path:
            nd = self.G.nodes[n]
            if is_demand(nd.get("kind")):
                continue
            ns = self.node_state(n, window) if weather else {"risk": 0.0, "cap_mult": 1.0}
            risk = max(risk, ns["risk"])
            cap = (nd.get("capacity") or 0.0) * ns["cap_mult"]
            if not nd.get("backup"):
                spare = min(spare, cap - self.base["throughput"].get(n, 0.0))
            else:
                spare = min(spare, cap)
        return {"eta": round(eta, 2), "cost": round(cost, 2), "co2": round(co2, 3), "risk": round(risk, 3),
                "spare": round(max(0.0, spare if spare != float("inf") else 0.0), 1)}

    def safety(self, path: list[str], flow: float, window: tuple[int, int], new_path: bool = True) -> dict:
        problems = []
        worst_util = 0.0
        if new_path:
            for n in path:
                nd = self.G.nodes[n]
                if is_demand(nd.get("kind")) or not nd.get("capacity"):
                    continue
                cap = nd["capacity"] * self.node_state(n, window)["cap_mult"]
                if cap <= 0:
                    continue
                util = (self.base["throughput"].get(n, 0.0) + flow) / cap
                worst_util = max(worst_util, util)
                if util > UTIL_LIMIT:
                    problems.append(f"pushes {_label(self.G, n)} to {util:.0%} of its capacity (limit {UTIL_LIMIT:.0%})")
        for n in path:
            nd = self.G.nodes[n]
            if is_demand(nd.get("kind")) or nd.get("backup"):
                continue
            normal, degraded = self._spof(n)
            if degraded > SPOF_THRESHOLD and normal <= SPOF_THRESHOLD:
                problems.append(f"leans on {_label(self.G, n)}: with this weather, losing it too would leave {degraded:.0%} of demand unmet "
                                f"(vs {normal:.0%} normally)")
                break
        warning = None
        if problems:
            text = "; ".join(problems[:2])
            warning = text[0].upper() + text[1:] + "."
        return {"passed": not problems, "warning": warning, "peak_utilization": round(worst_util, 3)}

    def _peak(self) -> nx.DiGraph:
        if self._peak_graph is None:
            H = self.G.copy()
            for e, daily in self.edge_daily.items():
                if daily and e in H.edges:
                    H.edges[e]["capacity"] *= min(r["capacity_multiplier"] for r in daily)
            for n, daily in self.node_daily.items():
                if daily and n in H and not is_demand(H.nodes[n].get("kind")):
                    H.nodes[n]["capacity"] = (H.nodes[n].get("capacity") or 0.0) * min(r["capacity_multiplier"] for r in daily)
            self._peak_graph = H
        return self._peak_graph

    def _spof(self, n: str) -> tuple[float, float]:
        if n not in self._spof_cache:
            try:
                self._spof_cache[n] = (chaos.failure_loss(self.G, (n,)), chaos.failure_loss(self._peak(), (n,)))
            except Exception:  # noqa: BLE001 - a failed check must not sink the whole answer
                self._spof_cache[n] = (0.0, 0.0)
        return self._spof_cache[n]

    # ------------------------------------------------ one blocked lane
    def plan_lane(self, u: str, v: str, window: tuple[int, int], reason: str) -> dict:
        G = self.G
        flow = self.base["flow"].get((u, v), 0.0)
        orig = _main_path(G, self.base["flow"], u, v)
        dest = orig[-1]
        normal = self.path_metrics(orig, window, weather=False)
        under = self.path_metrics(orig, window)
        lane = self.edge_state((u, v), window)
        reopen = window[1] + 1
        wait_days = reopen - window[0]
        eta_orig_weather = (wait_days + normal["eta"]) if lane["closed"] else under["eta"]

        def make(path, metrics, kind, mode, extra_expl=""):
            check = self.safety(path, flow, window, new_path=kind == "reroute")
            shortfall = 0.0 if flow <= 0 else max(0.0, 1.0 - metrics["spare"] / flow) if kind == "reroute" else 0.0
            score = (metrics["cost"] + LAMBDA_TIME * metrics["eta"] + LAMBDA_RISK * metrics["risk"] + LAMBDA_CO2 * metrics["co2"]
                     + SHORTFALL_PENALTY * shortfall)
            return {
                "kind": kind, "path": path, "mode": mode,
                "modes": [mode if (a, b) == (u, v) and kind == "mode_switch" else (G.edges[a, b].get("mode") or "road")
                          for a, b in zip(path, path[1:])],
                "eta_days": metrics["eta"], "eta_delta": round(metrics["eta"] - normal["eta"], 2),
                "cost": metrics["cost"], "cost_delta": round(metrics["cost"] - normal["cost"], 2),
                "co2": metrics["co2"], "co2_delta": round(metrics["co2"] - normal["co2"], 3),
                "residual_risk": metrics["risk"], "capacity_available": metrics["spare"],
                "safety_check": {"passed": check["passed"], "warning": check["warning"]},
                "peak_utilization": check["peak_utilization"],
                "recommended": False, "_score": round(score, 2), "_extra": extra_expl,
            }

        alts = []
        H = self.weighted_view(window, drop=(u, v))
        if dest in H and nx.has_path(H, SRC, dest):
            for p in islice(nx.shortest_simple_paths(H, SRC, dest, weight="w"), K_ALTERNATIVES):
                path = p[1:]
                if path == orig:
                    continue
                alts.append(make(path, self.path_metrics(path, window), "reroute", G.edges[path[0], path[1]].get("mode") or "road"))

        cur_mode = G.edges[u, v].get("mode") or "road"
        km = _km(G, u, v)
        # a mode switch only helps if the rest of the path is open: no closed site, no other closed hop
        path_closed = any(self.node_state(n, window)["closed"] for n in orig if not is_demand(G.nodes[n].get("kind"))) or any(
            self.edge_state(e, window)["closed"] for e in zip(orig, orig[1:]) if e != (u, v))
        for m in ([] if path_closed else MODE_SWITCH.get(cur_mode, ())):
            if m == "air" and (self.unit_price < HIGH_VALUE_INR or km < AIR_MIN_KM):
                continue
            if km <= 0:
                continue
            rows = [self.score_as(f"{u}->{v}", m, d) for d in range(window[0], window[1] + 1)] if self.score_as else []
            r = max((x["risk"] for x in rows), default=0.0)
            imp = impact(r)
            if imp["closed"]:
                continue
            o = {"lead": suggest_lead(m, km), "lead_mult": imp["lead_multiplier"], "cost": suggest_cost(m, km), "co2": suggest_co2(m, km),
                 "risk": r, "capacity": G.edges[u, v]["capacity"] * imp["capacity_multiplier"], "cap_mult": imp["capacity_multiplier"]}
            metrics = self.path_metrics(orig, window, override={(u, v): o})
            metrics["spare"] = round(o["capacity"], 1)  # the lane's own volume moves to the new mode
            alt = make(orig, metrics, "mode_switch", m)
            alt["switch"] = {"edge": f"{u}->{v}", "from": cur_mode, "to": m, "lead_days": o["lead"], "lead_multiplier": o["lead_mult"],
                             "capacity_multiplier": o["cap_mult"], "risk": round(r, 3), "base_lead": G.edges[u, v]["lead"]}
            alts.append(alt)

        best = None
        if alts:
            passing = [a for a in alts if a["safety_check"]["passed"]] or alts
            best = min(passing, key=lambda a: a["_score"])
            best["recommended"] = True
        for a in alts:
            a["explanation"] = self._explain(a, normal, eta_orig_weather, best)
        alts.sort(key=lambda a: (not a["recommended"], a["_score"]))

        # wait it out
        dest_d = G.nodes[dest]
        cover_days = (dest_d.get("stock") or 0.0) / dest_d["demand"] if dest_d.get("demand") else float("inf")
        wait_cost = normal["cost"] + LAMBDA_TIME * eta_orig_weather + LAMBDA_CO2 * normal["co2"]
        wait_viable = wait_days <= WAIT_MAX_DAYS and cover_days >= wait_days
        wait = {
            "viable": wait_viable, "days": wait_days, "resume_day": reopen, "eta_days": round(eta_orig_weather, 2),
            "delay_days": round(eta_orig_weather - normal["eta"], 2), "stock_cover_days": None if cover_days == float("inf") else round(cover_days, 1),
            "cost_per_unit": round(wait_cost, 1), "recommended": False,
        }
        if wait_viable and (not best or wait_cost < best["_score"]):
            wait["recommended"] = True
        wait["explanation"] = (
            f"Hold shipments on {u}→{v} for {wait_days} day(s) and resume on day {reopen}; {_label(G, dest)} has "
            f"{wait['stock_cover_days'] if wait['stock_cover_days'] is not None else 'enough'} days of stock."
            if wait_viable else
            f"Waiting is not advised: the window lasts {wait_days} day(s)" + (f" and {_label(G, dest)} has only {cover_days:.1f} days of stock." if cover_days < wait_days else
                                                                              f", longer than the {WAIT_MAX_DAYS}-day limit.")
        )

        # pre-position
        stage = v
        units = round(flow * (window[1] - window[0] + 1))
        pre_viable = window[0] >= 1 and units > 0 and not self.node_state(stage, window)["closed"]
        pre = {
            "viable": pre_viable, "node": stage, "units": units, "by_day": max(0, window[0] - 1),
            "cost": round(units * (PREPO_COST + HOLDING_PER_DAY * (window[1] - window[0] + 1))),
            "explanation": (f"Move {units:,} units to {_label(G, stage)} by day {max(0, window[0] - 1)}, before {u}→{v} is hit on day {window[0]}; "
                            "this is the optimizer's inventory buffer lever." if pre_viable else
                            "Too late to pre-position: the risk window starts today." if window[0] < 1 else
                            f"{_label(G, stage)} is itself in the hazard zone." if units > 0 else "No baseline flow to cover."),
            "also_recommended": pre_viable and lane["closed"],
        }

        # dispatch window on the original path
        path_edges = list(zip(orig, orig[1:]))
        horizon = min(self.days, window[1] + 4)
        day_risk = []
        for d in range(horizon):
            r = max([(self.edge_daily.get(e) or [{}] * self.days)[d].get("risk", 0.0) if d < len(self.edge_daily.get(e) or []) else 0.0
                     for e in path_edges] + [0.0])
            day_risk.append(round(r, 3))
        best_day = min(range(len(day_risk)), key=lambda d: (day_risk[d], d)) if day_risk else 0
        latest_safe = window[0] - 1 if window[0] >= 1 else None
        if latest_safe is not None:
            text = f"Dispatch by day {latest_safe} (before the risk window opens on day {window[0]}), or from day {reopen} once it reopens."
        else:
            text = f"The window is already open; the safest day to dispatch on the original route is day {best_day} (risk {day_risk[best_day]:.2f})."
        dispatch = {"best_day": best_day, "best_day_risk": day_risk[best_day] if day_risk else 0.0, "latest_safe_day": latest_safe,
                    "reopen_day": reopen, "risk_by_day": day_risk, "text": text}

        # an alternative that is no faster than riding out the window on the hit lane is not worth switching to
        if best and best["eta_days"] >= eta_orig_weather and best["residual_risk"] >= 0.5:
            best["recommended"] = False
            best = None
        action = ("wait" if wait["recommended"] else best["kind"] if best else "preposition" if pre_viable
                  else "dispatch_early" if latest_safe is not None else "none")
        rec_eta = wait["eta_days"] if wait["recommended"] else best["eta_days"] if best else eta_orig_weather
        for a in alts:
            a.pop("_extra", None)
            a["score"] = a.pop("_score")
        return {
            "blocked_edge": f"{u}->{v}", "mode": cur_mode, "flow_per_day": round(flow, 1),
            "window": list(window), "closed": lane["closed"], "level": lane["level"], "risk": lane["risk"], "reason": reason,
            "original": {"path": orig, "eta_days": normal["eta"], "eta_weather": round(eta_orig_weather, 2), "cost": normal["cost"],
                         "co2": normal["co2"], "residual_risk": under["risk"]},
            "alternatives": alts, "wait_option": wait, "preposition_option": pre, "dispatch_window": dispatch,
            "recommended_action": action,
            "action_text": self._action_text(action, best, wait, pre, dispatch, u, v),
            "delay_saved_days": round(max(0.0, eta_orig_weather - rec_eta), 2),
            "scenario_patch": self._patch(u, v, window, action, best, reason),
        }

    def _explain(self, a: dict, normal: dict, eta_orig_weather: float, best: dict | None) -> str:
        G = self.G
        via = " → ".join(_city(G, n) for n in a["path"])
        eta = f"{a['eta_days']:.1f} days ({a['eta_delta']:+.1f} vs normal)"
        cost = f"₹{a['cost']:.0f}/unit ({a['cost_delta']:+.0f})"
        risk = f"residual risk {a['residual_risk']:.2f}"
        if a["kind"] == "mode_switch":
            s = a["switch"]
            head = f"Switch {s['edge'].replace('->', '→')} from {s['from']} to {s['to']}"
        else:
            head = f"Reroute via {via}"
        tail = ""
        if not a["safety_check"]["passed"]:
            tail = f" Fails the safety check: {a['safety_check']['warning']}"
        elif a is best:
            saved = eta_orig_weather - a["eta_days"]
            tail = f" Recommended: saves ~{saved:.1f} days against shipping on the hit lane." if saved > 0.05 else " Recommended: lowest risk-adjusted cost."
        return f"{head}: {eta}, {cost}, {risk}.{tail}"

    def _action_text(self, action, best, wait, pre, dispatch, u, v) -> str:
        lane = f"{u}→{v}"
        if action in ("reroute", "mode_switch") and best:
            return best["explanation"]
        if action == "wait":
            return wait["explanation"]
        if action == "preposition":
            return pre["explanation"]
        if action == "dispatch_early":
            return (f"No safe alternative and nowhere safe to stage stock while {lane} is hit: {dispatch['text']} "
                    "Expect lost sales at the cut-off sites until it reopens.")
        return f"No safe option for {lane} inside the window; expect lost sales until it reopens."

    def _patch(self, u: str, v: str, window: tuple[int, int], action: str, best: dict | None, reason: str) -> dict:
        """How applying the recommendation changes the scenario's weather events for this lane (window only)."""
        target = f"{u}->{v}"
        start, duration = window[0], window[1] - window[0] + 1
        if action == "mode_switch" and best:
            s = best["switch"]
            lead_mult = (s["lead_days"] * s["lead_multiplier"]) / max(0.1, s["base_lead"])
            return {"remove_targets": [target], "window": list(window), "add": [{
                "type": "edge", "target": target, "start": start, "duration": duration,
                "severity": round(1 - s["capacity_multiplier"], 2), "source": "weather", "confidence": None,
                "lead_multiplier": round(lead_mult, 2) if lead_mult > 1.0 else None,
                "reason": f"Switched to {s['to']} (planned). {reason}"[:300],
            }], "summary": f"{target.replace('->', '→')} moves to {s['to']} on days {window[0]}-{window[1]}"}
        if action == "reroute" and best:
            via = " → ".join(best["path"])
            return {"remove_targets": [target], "window": list(window), "add": [{
                "type": "edge", "target": target, "start": start, "duration": duration, "severity": 1.0, "source": "weather",
                "confidence": None, "lead_multiplier": None, "reason": f"Avoided (planned reroute via {via}). {reason}"[:300],
            }], "summary": f"{target.replace('->', '→')} is avoided on days {window[0]}-{window[1]}; volume goes via {via}"}
        return {"remove_targets": [], "window": list(window), "add": [],
                "summary": "No scenario change: shipments wait for the lane to reopen." if action == "wait" else "No scenario change."}

    # ------------------------------------------------ whole network
    def blocked(self, events: list | None = None) -> list[tuple[str, str, tuple[int, int], str]]:
        out = []
        flow = self.base["flow"]
        if events:
            for ev in events:
                if ev.type != "edge" or not (ev.severity >= 0.4 or (ev.lead_multiplier or 1.0) >= 1.6):
                    continue
                u, v = (p.strip() for p in ev.target.split("->"))
                if flow.get((u, v), 0.0) <= 0:
                    continue
                out.append((u, v, (ev.start, min(self.days - 1, ev.start + ev.duration - 1)), ev.reason or "Weather event."))
            merged: dict = {}
            for u, v, w, r in out:  # one entry per lane: the union of its windows
                if (u, v) in merged:
                    a, b = merged[(u, v)][0]
                    merged[(u, v)] = ((min(a, w[0]), max(b, w[1])), merged[(u, v)][1])
                else:
                    merged[(u, v)] = (w, r)
            out = [(u, v, w, r) for (u, v), (w, r) in merged.items()]
        else:
            for (u, v), daily in self.edge_daily.items():
                if flow.get((u, v), 0.0) <= 0 or not daily:
                    continue
                w = _window(daily)
                if w:
                    worst = max(daily[w[0]:w[1] + 1], key=lambda r: r["risk"])
                    out.append((u, v, w, worst["reason"]))
        out.sort(key=lambda t: -flow.get((t[0], t[1]), 0.0))
        return out[:MAX_BLOCKED]

    def node_actions(self) -> list[dict]:
        from core import recommend

        actions = []
        G = self.G
        for n, daily in self.node_daily.items():
            d = G.nodes[n]
            if is_demand(d.get("kind")) or not daily:
                continue
            w = _window(daily)
            if not w:
                continue
            ns = self.node_state(n, w)
            loss = 1 - ns["cap_mult"]
            worst = max(daily[w[0]:w[1] + 1], key=lambda r: r["risk"])
            if d.get("kind") == "factory":
                spare = []
                for f, fd in G.nodes(data=True):
                    if f == n or fd.get("kind") != "factory":
                        continue
                    fs = self.node_state(f, w)
                    room = (fd.get("capacity") or 0.0) * fs["cap_mult"] - self.base["throughput"].get(f, 0.0)
                    if room > 1 and fs["risk"] < 0.5:
                        spare.append((room, f))
                if spare:
                    room, f = max(spare)
                    units = round(min(room, (d.get("capacity") or 0.0) * loss))
                    actions.append({"node": n, "action": "production_shift", "to": f, "units_per_day": units, "window": list(w),
                                    "explanation": f"{_label(G, n)} loses {loss:.0%} of capacity on days {w[0]}-{w[1]} ({worst['reason'].rstrip('.')}); "
                                                   f"shift {units:,}/day to {_label(G, f)}, which has spare capacity and low weather risk."})
            elif d.get("kind") == "supplier":
                alts = recommend.rank_alternate_suppliers(G, [n], top=1)
                if alts:
                    a = alts[0]
                    actions.append({"node": n, "action": "alternate_supplier", "to": a["supplier"], "window": list(w),
                                    "explanation": f"{_label(G, n)} is hit on days {w[0]}-{w[1]} ({worst['reason'].rstrip('.')}); "
                                                   f"source from {a['supplier']} {a['name']}: {a['reason']}."})
            elif d.get("kind") == "warehouse" and w[0] >= 1:
                actions.append({"node": n, "action": "preposition", "window": list(w),
                                "explanation": f"{_label(G, n)} is in the hazard zone on days {w[0]}-{w[1]}; draw down its stock early "
                                               f"and stage cover at a neighbouring site by day {w[0] - 1}."})
        return actions


def plan_reroutes(G: nx.DiGraph, risk: dict, events: list | None = None, score_as=None) -> dict:
    """POST /weather/reroute body (without applied_strategy_summary, which the router adds)."""
    planner = Planner(G, risk, score_as)
    blocked = planner.blocked(events)
    options = [planner.plan_lane(u, v, w, r) for u, v, w, r in blocked]
    recs = [o for o in options if o["recommended_action"] in ("reroute", "mode_switch")]
    saved = round(sum(o["delay_saved_days"] for o in options), 1)
    headline = None
    if options:
        top = max(options, key=lambda o: o["delay_saved_days"])
        best = next((a for a in top["alternatives"] if a["recommended"]), None)
        if top["recommended_action"] == "mode_switch" and best:
            what = f"move {top['blocked_edge'].replace('->', '→')} to {best['switch']['to']}"
        elif top["recommended_action"] == "reroute" and best:
            what = "reroute via " + ", ".join(_city(G, n) for n in best["path"][1:-1] or best["path"])
        elif top["recommended_action"] == "wait":
            what = f"hold {top['blocked_edge'].replace('->', '→')} until day {top['wait_option']['resume_day']}"
        else:
            what = "pre-position stock"
        headline = what
    return {
        "blocked_routes": [{"edge": o["blocked_edge"], "window": o["window"], "reason": o["reason"], "closed": o["closed"],
                            "level": o["level"]} for o in options],
        "options": options,
        "node_actions": planner.node_actions(),
        "summary": {"blocked": len(options), "closed": sum(1 for o in options if o["closed"]), "rerouted": len(recs),
                    "delay_saved_days": saved, "headline": headline},
    }
