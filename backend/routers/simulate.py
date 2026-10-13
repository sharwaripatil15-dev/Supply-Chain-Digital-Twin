from fastapi import APIRouter

from cache import cache
from config import settings
from core import montecarlo as mc_core
from core import sim as sim_core
from mock import mock_data
from routers.deps import cache_scope, check_events, get_graph, require_runnable, use_mock
from schemas import MonteCarloRequest, MonteCarloResponse, SimulateRequest, SimulateResponse

router = APIRouter(tags=["simulate"])


@router.post("/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest):
    mock = use_mock(settings.mock_simulate)
    if not mock:
        require_runnable()
    events = check_events(req.events, mock=mock)
    G = get_graph()
    compute = mock_data.simulate if mock else (lambda ev, h: sim_core.simulate(G, ev, h))
    key = cache.key("simulate", [cache_scope(settings.mock_simulate), req])

    def _run_and_enrich():
        res = compute(events, req.horizon)
        if isinstance(res, dict):
            # 1. Compute simulated cascade (Directive 2)
            sim_impacts = []
            stockout_map = res.get("stockout_day", {})
            timeline = res.get("timeline", [])
            for nid, sday in stockout_map.items():
                ndata = G.nodes[nid] if nid in G else {}
                first_impact = sday
                for t in timeline:
                    if t.get("node_status", {}).get(nid) in ("stressed", "down"):
                        first_impact = t["day"]
                        break
                sim_impacts.append({
                    "node": nid,
                    "name": ndata.get("name", nid),
                    "city": ndata.get("city", ""),
                    "kind": ndata.get("kind", "customer"),
                    "first_impact_day": first_impact,
                    "tts_days": float(sday),
                    "ttr_days": float(req.horizon),
                    "status": "fails" if sday < req.horizon else "survives",
                    "mode": "simulated",
                    "reason": f"LP simulated stockout on Day {sday}" if sday < req.horizon else "Survived full horizon",
                })
            res["cascade_simulated"] = sim_impacts

            # 2. Surrogate Predicted vs Actual comparison (Directive 3)
            try:
                from core.risk_ml import scenario_quick_risk, surrogate_compare
                from node_types import total_demand

                quick = scenario_quick_risk(G, events)
                pred_share = quick.predicted_unmet_share if quick else 0.0
                tot_dem_horizon = total_demand(G) * req.horizon
                actual_share = res.get("total_unmet", 0.0) / max(tot_dem_horizon, 1.0)
                res["surrogate_comparison"] = surrogate_compare(pred_share, actual_share)
            except Exception:
                res["surrogate_comparison"] = None

            # 3. Top recovery options (Directive F)
            try:
                from core.recommend import rank_alternate_routes, rank_alternate_suppliers

                down_supps = [ev.target for ev in events if ev.target in G and G.nodes[ev.target].get("kind") == "supplier"]
                down_nodes = [ev.target for ev in events if "->" not in ev.target]
                down_edges = [tuple(ev.target.split("->")) for ev in events if "->" in ev.target and len(ev.target.split("->")) == 2]

                rec_supps = rank_alternate_suppliers(G, down_supps, top=2) if down_supps else []
                rec_routes = rank_alternate_routes(G, down_nodes, down_edges, k=2) if (down_nodes or down_edges) else []
                res["top_recovery_options"] = rec_supps + rec_routes
            except Exception:
                res["top_recovery_options"] = []

        return res

    return cache.get_or_compute(key, _run_and_enrich)


@router.post("/montecarlo", response_model=MonteCarloResponse)
def montecarlo(req: MonteCarloRequest):
    mock = use_mock(settings.mock_simulate)
    if not mock:
        require_runnable()
    events = check_events(req.events, mock=mock)
    compute = mock_data.montecarlo if mock else (lambda ev, n: mc_core.monte_carlo(get_graph(), ev, n))
    key = cache.key("montecarlo", [cache_scope(settings.mock_simulate), req])
    return cache.get_or_compute(key, lambda: compute(events, req.n))
