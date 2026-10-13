from fastapi import APIRouter

from config import settings
from core import optimizer as opt_core
from routers.deps import check_events, get_graph, require_runnable, use_mock
from schemas import OptimizePlanRequest, OptimizePlanResponse

router = APIRouter(prefix="/optimize", tags=["optimize"])


@router.post("/plan", response_model=OptimizePlanResponse)
def optimize_inventory_production(req: OptimizePlanRequest):
    mock = use_mock(settings.mock_recover)
    if not mock:
        require_runnable()
    events = check_events(req.events, mock=mock) if req.events else []
    G = get_graph()

    plan = opt_core.optimize_plan(
        G,
        events,
        levers=req.levers,
        horizon=req.horizon,
        w_unmet=req.w_unmet,
        w_co2=req.w_co2,
    )
    insights = opt_core.compute_optimization_insights(G, plan, events, horizon=req.horizon)

    return {
        "status": plan.get("status", "Optimal"),
        "levers": plan.get("levers", req.levers),
        "window": plan.get("window"),
        "cost": plan.get("cost", 0.0),
        "unmet": plan.get("unmet", 0.0),
        "stock_drawn": plan.get("stock_drawn", 0.0),
        "recovery_days": plan.get("recovery_days", 0),
        "co2": plan.get("co2", 0.0),
        "backup_used": plan.get("backup_used", False),
        "inventory_actions": plan.get("inventory_actions", []),
        "production_actions": plan.get("production_actions", []),
        "financial_summary": insights["financial_summary"],
        "daily_inventory_trajectory": insights["daily_inventory_trajectory"],
        "plant_allocations": insights["plant_allocations"],
    }


@router.get("/plan", response_model=OptimizePlanResponse)
def get_default_optimized_plan():
    """Returns optimal inventory buffer and production reallocation plan for the active network."""
    return optimize_inventory_production(OptimizePlanRequest())
