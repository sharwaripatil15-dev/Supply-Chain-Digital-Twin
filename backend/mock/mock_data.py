"""Realistic MOCK payloads for every endpoint (served when USE_MOCK=true).

Nothing here is the real simulator. /simulate uses a tiny deterministic "ripple"
heuristic (severity propagated downstream by inbound-capacity share, 2 days per tier)
so the demo buttons produce different-but-plausible timelines. The real engine lives
in core/sim.py (min-cost flow per day) and replaces this once USE_MOCK=false.
"""
from __future__ import annotations

import copy
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from core.delay import find_bottlenecks, summarize_delays
from node_types import KINDS, is_demand

_NET: dict[str, Any] = json.loads((Path(__file__).parent / "demo_network.json").read_text(encoding="utf-8"))
NODES: dict[str, dict] = {n["id"]: n for n in _NET["nodes"]}
EDGES: list[dict] = _NET["edges"]
TIER_ORDER = KINDS
UNIT_PRICE_INR = 4200  # average selling price per finished unit

_OUT: dict[str, list[dict]] = defaultdict(list)
_IN: dict[str, list[dict]] = defaultdict(list)
for _e in EDGES:
    _OUT[_e["source"]].append(_e)
    _IN[_e["target"]].append(_e)
_TOPO = sorted(NODES, key=lambda nid: (TIER_ORDER.index(NODES[nid]["kind"]), nid))

_AMPLIFY = 1.2  # bullwhip-ish amplification per hop
_DOWN, _STRESSED = 0.7, 0.2  # severity thresholds
_LEVEL_NAME = {0: "ok", 1: "stressed", 2: "down"}


def _ev(e: Any) -> dict:
    return e.model_dump() if hasattr(e, "model_dump") else dict(e)


# ------------------------------------------------------------------ /network
def network() -> dict:
    return copy.deepcopy(_NET)


# ------------------------------------------------------------------ /simulate
def _propagate(event: dict) -> dict[str, tuple[float, int]]:
    """Return {node_id: (severity, hop)} for nodes affected by one event."""
    sev, target, kind = float(event["severity"]), event["target"], event["type"]
    seeds: dict[str, float] = {}
    if kind == "node":
        seeds[target] = sev
    elif kind == "edge":
        src, dst = target.split("->")
        cap = next(e["capacity"] for e in _IN[dst] if e["source"] == src)
        seeds[dst] = min(1.0, sev * cap / sum(e["capacity"] for e in _IN[dst]) * _AMPLIFY)
    else:  # demand spike: the customer, plus pressure on the warehouses that feed it
        seeds[target] = sev
        for e in _IN[target]:
            seeds.setdefault(e["source"], sev * 0.5)

    out: dict[str, tuple[float, int]] = {nid: (s, 0) for nid, s in seeds.items()}
    if kind == "demand":
        return out
    for nid in _TOPO:
        if nid in out:
            continue
        inbound = _IN[nid]
        total = sum(e["capacity"] for e in inbound) or 1
        hit = [(out[e["source"]], e["capacity"]) for e in inbound if e["source"] in out]
        if not hit:
            continue
        s = min(1.0, _AMPLIFY * sum(ps * cap / total for (ps, _), cap in hit))
        if s >= _STRESSED:
            out[nid] = (s, max(h for (_, h), _ in hit) + 1)
    return out


def simulate(events: list, horizon: int = 30) -> dict:
    events = [_ev(e) for e in events]
    level = [defaultdict(int) for _ in range(horizon)]
    sev_at = [defaultdict(float) for _ in range(horizon)]

    for ev in events:
        start, end = ev["start"], ev["start"] + ev["duration"] - 1
        for nid, (s, hop) in _propagate(ev).items():
            lvl = 2 if s >= _DOWN else 1
            onset = start + 2 * hop
            down_from = onset if hop == 0 else onset + 1
            for d in range(onset, min(horizon, end + 2 * hop + 1)):
                cur = 1 if (lvl == 2 and d < down_from) else lvl
                level[d][nid] = max(level[d][nid], cur)
                sev_at[d][nid] = max(sev_at[d][nid], s)

    # Mock utilization: stressed nodes run hot to compensate; down nodes drop to 0 and push load
    # onto same-tier siblings that share a downstream node.
    siblings = {
        nid: {e["source"] for t in _OUT[nid] for e in _IN[t["target"]] if e["source"] != nid}
        for nid in NODES
    }
    delay_acc: dict[str, float] = defaultdict(float)

    timeline, stockout_day, total_unmet = [], {}, 0.0
    for d in range(horizon):
        util = {}
        for nid, node in NODES.items():
            lvl = level[d][nid]
            if is_demand(node["kind"]):
                util[nid] = 0.0
                if lvl:
                    delay_acc[nid] += (0.6 if lvl == 2 else 0.35) * sev_at[d][nid]
                continue
            if lvl == 2:
                u = 0.0
            else:
                u = node.get("utilization", 0.0) + (0.25 * sev_at[d][nid] if lvl == 1 else 0.0)
                u += 0.22 * sum(1 for s in siblings[nid] if level[d][s] == 2)
            util[nid] = round(min(u, 1.4), 3)

        unmet = 0.0
        for nid, node in NODES.items():
            if not is_demand(node["kind"]) or not level[d][nid]:
                continue
            factor = 1.0 if level[d][nid] == 2 else 0.35
            unmet += node["demand"] * sev_at[d][nid] * factor
            if level[d][nid] == 2:
                stockout_day.setdefault(nid, d)
        unmet = round(unmet, 1)
        total_unmet += unmet
        timeline.append({
            "day": d,
            "unmet": unmet,
            "down": sorted(n for n in NODES if level[d][n] == 2),
            "node_status": {n: _LEVEL_NAME[level[d][n]] for n in NODES},
            "utilization": util,
        })

    log = _narrate(events, timeline)
    survival = min(stockout_day.values()) if stockout_day else horizon
    return {
        "timeline": timeline,
        "log": log,
        "stockout_day": stockout_day,
        "total_unmet": round(total_unmet, 1),
        "survival_clock_days": survival,
        "revenue_at_risk": round(total_unmet * UNIT_PRICE_INR, 0),
        "delay": summarize_delays({c: delay_acc.get(c, 0.0) for c, n in NODES.items() if is_demand(n["kind"])}),
        "bottlenecks": find_bottlenecks(timeline),
    }


def _label(nid: str) -> str:
    n = NODES[nid]
    return f"{nid} {n.get('name', '')} ({n['city']})"


def _narrate(events: list[dict], timeline: list[dict]) -> list[str]:
    log = []
    for ev in events:
        what = {"node": "outage at", "edge": "lane blocked:", "demand": "demand spike at"}[ev["type"]]
        log.append(f"Day {ev['start']}: EVENT {what} {ev['target']} for {ev['duration']}d (severity {ev['severity']:.2f})")
    prev = {n: "ok" for n in NODES}
    for row in timeline:
        for nid, st in row["node_status"].items():
            if st == prev[nid]:
                continue
            if st == "down":
                tag = "STOCKOUT" if is_demand(NODES[nid]["kind"]) else "DOWN"
                log.append(f"Day {row['day']}: {_label(nid)} {tag}")
            elif st == "stressed" and prev[nid] == "ok":
                log.append(f"Day {row['day']}: {_label(nid)} stressed - inbound supply short, drawing down stock")
            elif st == "ok":
                log.append(f"Day {row['day']}: {_label(nid)} recovered")
            prev[nid] = st
    if any(r["unmet"] for r in timeline):
        last = max(r["day"] for r in timeline if r["unmet"])
        log.append(f"Day {last + 1}: all customer demand served again")
    return sorted(log, key=lambda s: int(s.split(":")[0].split()[1]))


# ------------------------------------------------------------------ /montecarlo
def montecarlo(events: list, n: int = 200) -> dict:
    base = simulate(events)["total_unmet"] or 400.0
    rng = np.random.default_rng(42)
    # Mock: lognormal spread around the deterministic run, ~12% of draws see no shortage.
    samples = base * rng.lognormal(mean=0.0, sigma=0.45, size=n)
    samples[rng.random(n) < 0.12] = 0.0
    counts, edges = np.histogram(samples, bins=15)
    return {
        "p50": round(float(np.percentile(samples, 50)), 1),
        "p90": round(float(np.percentile(samples, 90)), 1),
        "p_shortage": round(float((samples > 0).mean()), 3),
        "histogram": [{"bin": round(float(edges[i]), 1), "count": int(c)} for i, c in enumerate(counts)],
    }


# ------------------------------------------------------------------ /chaos
def chaos() -> dict:
    return {
        "spof": [
            {"target": "S2", "unmet": 3120.0},
            {"target": "W4", "unmet": 2860.0},
            {"target": "F1", "unmet": 2410.0},
            {"target": "W3", "unmet": 1980.0},
            {"target": "S1", "unmet": 1450.0},
        ],
        "hidden_pairs": [
            {"pair": ["W3", "W4"], "unmet": 6900.0, "synergy": 2060.0},
            {"pair": ["S2", "S3"], "unmet": 5400.0, "synergy": 1630.0},
            {"pair": ["F2", "W1"], "unmet": 3900.0, "synergy": 1180.0},
            {"pair": ["S1", "S4"], "unmet": 3100.0, "synergy": 940.0},
            {"pair": ["F3", "W2"], "unmet": 2650.0, "synergy": 610.0},
        ],
        "resilience_score": _NET["resilience_score"],
    }


# ------------------------------------------------------------------ /recover
_STRATEGIES = [
    # name, cost INR, unmet as fraction of inaction, recovery days, delay as fraction of inaction, tCO2,
    # resilience_after, (safety passed, warning), description
    ("Drain safety stock (W1 + W2)", 180_000, 0.35, 9, 0.55, 0.4, 48.0,
     (False, "Pulls W1 Bhiwandi below 2 days of cover. A 3-day monsoon closure in Mumbai in the next 30 days "
             "(p=0.31) would create a ~3,400-unit stockout at C1/C5, larger than the disruption being fixed."),
     "Ship existing buffer inventory to the shortfall region."),
    ("Inventory buffer (pre-position W1 -> W3)", 260_000, 0.30, 8, 0.50, 1.9, 66.0, (True, None),
     "Move 900 units from Bhiwandi to Sriperumbudur before day 6, keeping W1 above 4 days of cover."),
    ("Reroute via Nagpur hub", 320_000, 0.45, 8, 0.70, 6.1, 58.0, (True, None),
     "Push F2 output through W4 Nagpur to C2/C4; adds 1 day of lead time."),
    ("Production shift (F1 -> F2 + F3)", 450_000, 0.28, 7, 0.45, 3.2, 69.0, (True, None),
     "Move 240 units/day of F1's plan to F2 Hyderabad and F3 Nashik, which run on S1/S3 inputs."),
    ("Activate Kolkata backup (S4)", 690_000, 0.25, 7, 0.40, 9.8, 71.0, (True, None),
     "Switch S4 Kolkata to full capacity on S4->F1 and S4->F2 lanes."),
    ("LP-optimal mix: S4 + Nagpur reroute + 2-day air bridge", 840_000, 0.07, 5, 0.15, 12.3, 76.0, (True, None),
     "PuLP plan: activate S4, reroute F2 via W4, air-freight 600 units BLR for days 4-5."),
    ("Air-freight expedite (Bengaluru)", 2_150_000, 0.035, 3, 0.08, 41.0, 63.0, (True, None),
     "Daily charter from Chennai to Bengaluru until S2 recovers."),
]
_RECOMMENDED = "LP-optimal mix: S4 + Nagpur reroute + 2-day air bridge"


def recover(events: list) -> dict:
    sim = simulate(events)
    base_unmet = sim["total_unmet"] or 400.0
    base_delay = sim["delay"]["avg_days"] or 1.0
    inaction_loss = round(base_unmet * UNIT_PRICE_INR, 0)
    strategies = []
    for name, cost, frac, days, dfrac, co2, res, (passed, warning), desc in _STRATEGIES:
        strategies.append({
            "name": name,
            "cost": float(cost),
            "unmet": round(base_unmet * frac, 1),
            "recovery_days": days,
            "delay_avg_days": round(base_delay * dfrac, 2),
            "co2": co2,
            "resilience_after": res,
            "safety_check": {"passed": passed, "warning": warning},
            "recommended": name == _RECOMMENDED,
            "description": desc,
        })
    rec = next(s for s in strategies if s["recommended"])
    fix_cost = rec["cost"] + rec["unmet"] * UNIT_PRICE_INR
    return {
        "strategies": strategies,
        "roi": {"inaction_loss": inaction_loss, "fix_cost": fix_cost, "net_saving": round(inaction_loss - fix_cost, 0)},
        "playbook": playbook(),
        **_alternates(events),
    }


def _alternates(events: list) -> dict:
    """Mock recommendations. Alternate suppliers are listed for each disrupted supplier in `events`."""
    events = [_ev(e) for e in events]
    down = {e["target"] for e in events if e["type"] == "node" and NODES[e["target"]]["kind"] == "supplier"}
    lead = {"S1": 2, "S2": 1, "S3": 3, "S4": 4}
    premium = {"S1": 12.0, "S2": 0.0, "S3": 21.0, "S4": 38.0}
    suppliers = []
    for sid in sorted(down):
        for alt in ("S4", "S1", "S3", "S2"):
            if alt in down:
                continue
            n = NODES[alt]
            suppliers.append({
                "replaces": sid, "supplier": alt, "name": n["name"], "city": n["city"],
                "spare_capacity": round(n["capacity"] * (1 - n["utilization"])),
                "lead": lead[alt], "cost_premium_pct": premium[alt], "reliability": n["reliability"],
            })
    return {
        "alternate_suppliers": suppliers,
        "alternate_routes": [
            {"origin": "F2", "destination": "C4", "via": ["F2", "W4", "C4"], "replaces": "W3->C4",
             "spare_capacity": 120, "extra_lead_days": 0.5, "extra_cost_per_unit": 6.0},
            {"origin": "F3", "destination": "C2", "via": ["F3", "W2", "C2"], "replaces": "W4->C2",
             "spare_capacity": 150, "extra_lead_days": 2.0, "extra_cost_per_unit": 41.0},
            {"origin": "F1", "destination": "C3", "via": ["F1", "C3"], "replaces": "W3",
             "spare_capacity": 200, "extra_lead_days": 0.0, "extra_cost_per_unit": 22.0},
        ],
        "inventory_actions": [
            {"node": "W3", "action": "pre-position", "units": 900, "source": "W1", "day": 0,
             "reason": "Covers C3 Bengaluru through the projected day 9-17 gap."},
            {"node": "C3", "action": "transfer", "units": 300, "source": "W4", "day": 1,
             "reason": "Bridge stock until the pre-positioned units land at W3."},
            {"node": "W1", "action": "hold", "units": 1200, "source": None, "day": 0,
             "reason": "Keep Bhiwandi above 4 days of cover (monsoon closure risk; fix-safety check)."},
            {"node": "W3", "action": "raise_safety_stock", "units": 600, "source": None, "day": 14,
             "reason": "Post-incident: Sriperumbudur is a top-5 single point of failure."},
        ],
        "production_actions": [
            {"from_factory": "F1", "to_factory": "F2", "units_per_day": 150, "start_day": 3, "duration": 9,
             "reason": "F1 loses S2 components; F2 has headroom and draws on S3/S4."},
            {"from_factory": "F1", "to_factory": "F3", "units_per_day": 90, "start_day": 4, "duration": 8,
             "reason": "F3 runs on S1 steel and S3 polymers, unaffected by the Chennai outage."},
        ],
    }


def playbook() -> list[str]:
    return [
        "Day 0 (now): Raise PO with S4 Kolkata Backup Components for 250 units/day on both lanes; confirm in 4h.",
        "Day 0: Pre-position 900 units W1 Bhiwandi to W3 Sriperumbudur; keep W1 above 4 days of cover.",
        "Day 0: Re-route F2 Hyderabad Plant output to W4 Nagpur Hub; notify carrier of +1 day lead time.",
        "Day 1: Book a 2-day air bridge Chennai to Bengaluru (600 units) to protect C3 Bengaluru Retail before day 4.",
        "Day 3: Shift 150 units/day of F1 production to F2 Hyderabad; day 4: 90 units/day to F3 Nashik.",
        "Day 3: Review S2 Chennai Electronics recovery ETA; release the air bridge if the ETA is before day 7.",
        "Day 7: Ramp S4 back to 30% standby; keep the Nagpur reroute until W3 Sriperumbudur stock is above 3 days of cover.",
        "Post-incident: dual-source S2 components (target: no supplier above 45% of F1 inbound).",
    ]


# ------------------------------------------------------------------ /parse
def parse(text: str) -> dict:
    # Mock: a fixed, sensible scenario regardless of the input text.
    return {"events": [
        {"type": "node", "target": "S2", "start": 2, "duration": 10, "severity": 1.0},
        {"type": "demand", "target": "C3", "start": 5, "duration": 7, "severity": 0.4},
    ]}


# ------------------------------------------------------------------ /forecast
def forecast(horizon: int = 14) -> dict:
    """Mock: weekly-seasonal demand history plus a forecast with a widening P10-P90 band."""
    rng = np.random.default_rng(11)

    def season(d: int) -> float:
        return 1 + 0.12 * np.sin(2 * np.pi * (d % 7) / 7)

    customers = []
    for nid, node in NODES.items():
        if not is_demand(node["kind"]):
            continue
        base, sigma, trend = node["demand"], node["demand"] * 0.07, node["demand"] * 0.002
        history = [{"day": d, "demand": round(float(base * season(d) + trend * d + rng.normal(0, sigma)), 1)}
                   for d in range(-27, 1)]
        fc = []
        for d in range(1, horizon + 1):
            mean = base * season(d) + trend * d
            band = 1.28 * sigma * np.sqrt(1 + d / 7)
            fc.append({"day": d, "mean": round(float(mean), 1), "p10": round(float(mean - band), 1),
                       "p90": round(float(mean + band), 1)})
        customers.append({"id": nid, "history": history, "forecast": fc})
    return {"horizon_days": horizon, "method": "Holt-Winters additive, weekly season (MOCK)", "mape": 0.084,
            "customers": customers}


# ------------------------------------------------------------------ /surrogate
def surrogate() -> dict:
    return {
        "target": "total unmet units over a 30-day horizon",
        "mae": 112.4,
        "r2": 0.93,
        "n_train": 4000,
        "n_test": 1000,
        "speedup": 850.0,
        "top_features": [
            {"feature": "failed_node_betweenness", "importance": 0.27},
            {"feature": "outage_duration_days", "importance": 0.21},
            {"feature": "severity", "importance": 0.18},
            {"feature": "downstream_demand_share", "importance": 0.14},
            {"feature": "backup_capacity_ratio", "importance": 0.09},
            {"feature": "min_days_of_cover", "importance": 0.06},
        ],
    }
