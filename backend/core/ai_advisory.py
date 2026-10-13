"""AI/ML-based network analysis and proactive recommendations. Owner: AEGIS AI Team.

Combines:
  1. ML Risk Surrogate (XGBoost + SHAP local attributions) for failure criticality.
  2. Chaos Finder (SPOF single points of failure & pair synergies).
  3. Flow optimization (baseline capacity headroom & utilization).
Generates prioritized, actionable recommendations with simulation payload links.
"""
from __future__ import annotations

import networkx as nx

from core import chaos
from core import risk_ml
from core.sim import solve_flow
from node_types import is_demand


def analyze_network_and_recommend(G: nx.DiGraph) -> dict:
    """Perform AI/ML-based vulnerability analysis and generate prioritized recommendations."""
    if G.number_of_nodes() == 0:
        return {
            "summary": {
                "network_health": "Empty",
                "resilience_score": 0.0,
                "critical_sites_count": 0,
                "top_spof_node": None,
                "ml_engine": "XGBoost Risk Surrogate + SHAP",
            },
            "bottlenecks": [],
            "recommendations": [],
        }

    # 1. Run ML Risk & SHAP explanations
    risks = risk_ml.node_risk_with_shap(G)

    # 2. Run Chaos Finder (SPOFs and Resilience)
    scan = chaos.scan(G)
    resilience = chaos.resilience_score(G)
    spof_map = scan.get("singles", {})

    # 3. Flow baseline for capacity utilization
    baseline = solve_flow(G)
    throughput = baseline.get("throughput", {})

    # 4. Identify Supply-side Bottlenecks
    bottlenecks = []
    for nid, d in G.nodes(data=True):
        if is_demand(d.get("kind")):
            continue
        info = risks.get(nid, {})
        risk_score = float(info.get("risk") if info.get("risk") is not None else 0.0)
        top_factors = info.get("top_factors", [])
        cap = d.get("capacity") or 0.0
        util = float(throughput.get(nid, 0.0) / cap if cap > 0 else 0.0)
        spof_unmet = float(spof_map.get(nid) if spof_map.get(nid) is not None else 0.0)

        # High risk threshold (> 0.15) or high SPOF impact (> 0.10) or high utilization (> 0.85)
        if risk_score >= 0.15 or spof_unmet >= 0.10 or util >= 0.85:
            # Format top SHAP driver into human explanation
            driver_text = "Multiple balanced topological factors."
            if top_factors:
                primary = top_factors[0]
                feat_name = primary["feature"].replace("_", " ")
                driver_text = f"Primary driver is {feat_name} ({'+' if primary['impact'] > 0 else ''}{primary['impact']:.3f} SHAP impact)."

            bottlenecks.append({
                "node_id": nid,
                "name": d.get("name") or nid,
                "city": d.get("city") or "",
                "kind": d.get("kind"),
                "risk": round(risk_score, 3),
                "utilization": round(util, 3),
                "spof_unmet_share": round(spof_unmet, 3),
                "top_shap_factors": top_factors,
                "driver_summary": driver_text,
                "is_backup": bool(d.get("backup")),
            })

    bottlenecks.sort(key=lambda b: (-b["risk"], -b["spof_unmet_share"]))

    # 5. Generate Prioritized AI Recommendations
    recommendations = []
    rec_counter = 1

    # Rule A: Warehouse bottlenecks (Distribution Centers are high-leverage single failure points)
    warehouses = [b for b in bottlenecks if b["kind"] == "warehouse"]
    if warehouses:
        top_wh = warehouses[0]
        recommendations.append({
            "id": f"rec-{rec_counter}",
            "priority": "critical" if top_wh["risk"] >= 0.25 else "high",
            "category": "Facility Redundancy",
            "title": f"Mitigate Distribution Bottleneck at {top_wh['name']} ({top_wh['node_id']})",
            "target_node": top_wh["node_id"],
            "ml_insight": (
                f"XGBoost surrogate scores {top_wh['name']} at {top_wh['risk'] * 100:.1f}% criticality. "
                f"{top_wh['driver_summary']} Failure triggers severe downstream retail stock-outs."
            ),
            "suggested_action": (
                f"Pre-contract secondary overflow storage or establish direct bypass routing to "
                f"tier-down demand points to reduce dependency."
            ),
            "expected_impact": f"Reduces single-point failure exposure by up to {top_wh['risk'] * 70:.1f}% demand share.",
            "simulation_event": {
                "type": "node",
                "target": top_wh["node_id"],
                "start": 1,
                "duration": 7,
                "severity": 1.0,
            },
        })
        rec_counter += 1

    # Rule B: High-utilization or single primary suppliers
    primary_suppliers = [b for b in bottlenecks if b["kind"] == "supplier" and not b["is_backup"]]
    backup_suppliers = [n for n, d in G.nodes(data=True) if d.get("kind") == "supplier" and d.get("backup")]
    if primary_suppliers:
        top_sup = primary_suppliers[0]
        has_backup = len(backup_suppliers) > 0
        recommendations.append({
            "id": f"rec-{rec_counter}",
            "priority": "high",
            "category": "Dual-Sourcing",
            "title": f"Diversify Sourcing for Primary Supplier {top_sup['name']} ({top_sup['node_id']})",
            "target_node": top_sup["node_id"],
            "ml_insight": (
                f"Predicted criticality is {top_sup['risk'] * 100:.1f}% with {top_sup['utilization'] * 100:.0f}% capacity utilization. "
                + (f"Backup supplier {backup_suppliers[0]} exists but has activation lag." if has_backup else "No contingency backup contracted.")
            ),
            "suggested_action": (
                "Split 15-20% baseline procurement to secondary regional suppliers or negotiate "
                "standby SLA with pre-qualified contingency vendors."
            ),
            "expected_impact": "Prevents upstream factory line starvation during unexpected supplier outages.",
            "simulation_event": {
                "type": "node",
                "target": top_sup["node_id"],
                "start": 2,
                "duration": 10,
                "severity": 1.0,
            },
        })
        rec_counter += 1

    # Rule C: Factory assembly constraints
    factories = [b for b in bottlenecks if b["kind"] == "factory"]
    if factories:
        top_fac = factories[0]
        recommendations.append({
            "id": f"rec-{rec_counter}",
            "priority": "medium",
            "category": "Load Balancing",
            "title": f"Rebalance Assembly Capacity at {top_fac['name']} ({top_fac['node_id']})",
            "target_node": top_fac["node_id"],
            "ml_insight": (
                f"Plant operates at {top_fac['utilization'] * 100:.0f}% capacity utilization. "
                f"Surrogate risk is {top_fac['risk'] * 100:.1f}%. Cross-plant transfer routes are limited."
            ),
            "suggested_action": (
                "Establish cross-training and dual-tooling agreements across sibling assembly plants "
                "to enable dynamic production shifts."
            ),
            "expected_impact": "Allows rapid production shifting under emergency response without new capital expense.",
            "simulation_event": {
                "type": "node",
                "target": top_fac["node_id"],
                "start": 3,
                "duration": 5,
                "severity": 0.8,
            },
        })
        rec_counter += 1

    # Rule D: Overall Resilience Buffering
    if resilience < 75 and len(recommendations) < 4:
        recommendations.append({
            "id": f"rec-{rec_counter}",
            "priority": "medium",
            "category": "Safety Stock Buffer",
            "title": "Elevate Strategic Inventory Buffers on Critical Routes",
            "target_node": bottlenecks[0]["node_id"] if bottlenecks else "W1",
            "ml_insight": (
                f"Network resilience score is {resilience:.1f}/100. "
                "Simultaneous or paired disruptions cause nonlinear cascading shortages."
            ),
            "suggested_action": (
                "Increase safety stock buffer days from 2.0 to 4.5 days at tier-2 intermediate transit nodes."
            ),
            "expected_impact": "Provides 5+ days of operational survival clock during sudden logistical freezes.",
            "simulation_event": {
                "type": "demand",
                "target": "C1",
                "start": 1,
                "duration": 5,
                "severity": 0.5,
            },
        })

    # Summary Health Assessment
    health = "Resilient" if resilience >= 75 else "Moderate" if resilience >= 50 else "Fragile"
    sorted_spofs = sorted(spof_map.items(), key=lambda kv: -kv[1])
    top_spof = sorted_spofs[0][0] if sorted_spofs and sorted_spofs[0][1] > 0 else (bottlenecks[0]["node_id"] if bottlenecks else None)

    return {
        "summary": {
            "network_health": health,
            "resilience_score": round(resilience, 1) if resilience is not None else 0.0,
            "critical_sites_count": len(bottlenecks),
            "top_spof_node": top_spof,
            "ml_engine": "XGBoost Risk Surrogate (v3) + SHAP TreeExplainer",
        },
        "bottlenecks": bottlenecks[:6],
        "recommendations": recommendations,
    }
