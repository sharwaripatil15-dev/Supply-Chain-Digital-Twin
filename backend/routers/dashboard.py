from fastapi import APIRouter

from config import settings
from core import delay as delay_core
from core import sim as sim_core
from core import strategies as strat_core
from node_types import is_demand, total_demand
from routers.deps import check_events, get_graph, require_runnable, use_mock
from schemas import DashboardSummaryResponse, Event

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def compute_dashboard_summary(G, events: list[Event], horizon: int = 30) -> dict:
    unit_price = float(G.graph.get("unit_price", 4200.0))
    total_dem = float(total_demand(G) * horizon) if total_demand(G) else 1.0

    # 1. Disruptions
    disruption_items = []
    affected_nodes = set()
    affected_lanes = set()

    for e in events:
        if e.type == "node":
            affected_nodes.add(e.target)
            node_data = G.nodes.get(e.target, {})
            name = node_data.get("name") or e.target
            city = node_data.get("city") or "India"
            desc = f"{name} ({e.target}) down at {int(e.severity * 100)}% severity for {e.duration} days from Day {e.start}"
        elif e.type == "edge":
            affected_lanes.add(e.target)
            u, v = e.target.split("->") if "->" in e.target else (e.target, "")
            name = f"{G.nodes.get(u, {}).get('name', u)} → {G.nodes.get(v, {}).get('name', v)}"
            city = f"{G.nodes.get(u, {}).get('city', '')} - {G.nodes.get(v, {}).get('city', '')}"
            desc = f"Transportation corridor {e.target} obstructed at {int(e.severity * 100)}% capacity for {e.duration} days"
        else:
            name = f"Demand surge at {e.target}"
            city = G.nodes.get(e.target, {}).get("city") or ""
            desc = f"Spike of +{int(e.severity * 100)}% surge for {e.duration} days from Day {e.start}"

        disruption_items.append({
            "type": e.type,
            "target": e.target,
            "target_name": name,
            "city": city,
            "start": e.start,
            "duration": e.duration,
            "severity": float(e.severity),
            "description": desc,
        })

    # 2. Impacts
    sim_res = sim_core.simulate(G, events, horizon=horizon)
    total_unmet = float(sim_res.get("total_unmet", 0.0))
    survival_clock = int(sim_res.get("survival_clock_days", horizon))
    inaction_loss = round(total_unmet * unit_price, 0)
    fulfillment_rate = round(max(0.0, 100.0 * (1.0 - (total_unmet / total_dem))), 1)

    # Regional demand impacts
    customer_nodes = [n for n, d in G.nodes(data=True) if is_demand(d.get("kind"))]
    regional_impacts = []
    for c in customer_nodes:
        d = G.nodes[c]
        c_demand = float(d.get("demand") or 0.0) * horizon
        # Customer unmet proportion
        c_unmet = round(total_unmet * (float(d.get("demand") or 0.0) / max(1.0, total_demand(G))), 1)
        c_fulfillment = round(max(0.0, 100.0 * (1.0 - (c_unmet / max(1.0, c_demand)))), 1)

        regional_impacts.append({
            "customer_id": c,
            "name": d.get("name") or c,
            "city": d.get("city") or "",
            "baseline_demand": round(c_demand, 0),
            "unmet_units": c_unmet,
            "fulfillment_pct": c_fulfillment,
            "extra_lead_days": round(float(e.severity * 2.5 if any(e.target == c for e in events) else 0.8), 1),
        })

    # 3. Recovery Strategies
    rows = strat_core.run_strategies(G, events)
    rec = next(r for r in rows if r["recommended"])
    roi = strat_core.roi(G, rows)
    strategies = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]

    try:
        from llm.parser import write_playbook
        playbook = write_playbook(strat_core.playbook_facts(G, rows, roi))
    except Exception:
        playbook = strat_core.template_playbook(G, list(events), rows)

    return {
        "disruptions": {
            "active_events_count": len(events),
            "affected_nodes": sorted(affected_nodes),
            "affected_lanes": sorted(affected_lanes),
            "disruptions": disruption_items,
        },
        "impacts": {
            "total_demand": round(total_dem, 0),
            "total_unmet_units": round(total_unmet, 1),
            "fulfillment_rate_pct": fulfillment_rate,
            "inaction_loss_inr": inaction_loss,
            "survival_clock_days": survival_clock,
            "avg_delay_days": round(float(rec.get("delay_avg_days", 1.2)), 1),
            "regional_impacts": regional_impacts,
        },
        "recovery": {
            "recommended_strategy": rec["name"],
            "inaction_loss": round(float(roi.get("inaction_loss", inaction_loss)), 0),
            "fix_cost": round(float(roi.get("fix_cost", rec["cost"])), 0),
            "net_savings": round(float(roi.get("net_saving", max(0.0, inaction_loss - rec["cost"]))), 0),
            "roi_multiple": round(float(roi.get("roi_ratio", 2.5)), 2),
            "safety_check_passed": bool(rec.get("safety_check", {}).get("passed", True)),
            "strategies": strategies,
            "playbook_highlights": playbook[:4] if isinstance(playbook, list) else [str(playbook)],
        },
    }


@router.post("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(events: list[Event] = []):
    mock = use_mock(settings.mock_recover)
    if not mock:
        require_runnable()
    valid_events = check_events(events, mock=mock) if events else []
    G = get_graph()
    return compute_dashboard_summary(G, valid_events)


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_default_dashboard_summary():
    """Returns the unified disruptions, impacts, and recovery dashboard summary for the active network."""
    G = get_graph()
    suppliers = [n for n, d in G.nodes(data=True) if d.get("kind") == "supplier"]
    default_target = suppliers[0] if suppliers else "S2"
    events = [Event(type="node", target=default_target, start=2, duration=10, severity=1.0)]
    return compute_dashboard_summary(G, events)
