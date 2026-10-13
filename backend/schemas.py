"""Pydantic v2 models for every request and response in the AEGIS API contract."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NodeKind = Literal["supplier", "factory", "warehouse", "customer"]
NodeStatus = Literal["ok", "stressed", "down"]
EventType = Literal["node", "edge", "demand"]


# ---------------------------------------------------------------- network
class RiskFactor(BaseModel):
    feature: str
    impact: float = Field(description="SHAP value; positive pushes risk up")


class Node(BaseModel):
    id: str
    kind: NodeKind
    city: str
    lat: float
    lon: float
    capacity: float = Field(ge=0, description="units/day (production or throughput)")
    stock: float = Field(ge=0, description="on-hand inventory, units")
    demand: float = Field(ge=0, description="units/day (customers only, else 0)")
    risk: float = Field(ge=0, le=1, description="ML-predicted share of demand lost if this node fails alone (criticality, 0..1)")
    reliability: float = Field(default=1.0, ge=0, le=1, description="historical on-time-in-full rate")
    utilization: float = Field(default=0.0, ge=0, description="baseline load / capacity (0 for customers)")
    top_factors: list[RiskFactor] = []
    name: str | None = None
    backup: bool = False


class Edge(BaseModel):
    source: str
    target: str
    capacity: float = Field(ge=0, description="units/day")
    lead: float = Field(ge=0, description="lead time, days")
    cost: float = Field(ge=0, description="INR per unit")
    co2: float = Field(ge=0, description="kg CO2 per unit")


class NetworkResponse(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
    resilience_score: float | None = Field(
        default=None, ge=0, le=100, description="null until Chaos Finder has run on this network (e.g. a fresh upload)"
    )


# ---------------------------------------------------------------- scenario
class Event(BaseModel):
    type: EventType
    target: str = Field(description='node id, or "SRC->DST" for an edge event')
    start: int = Field(ge=0, description="day the disruption begins")
    duration: int = Field(ge=1, le=365, description="days")
    severity: float = Field(ge=0, le=1, description="0 = no effect, 1 = total outage / +100% demand")


class SimulateRequest(BaseModel):
    events: list[Event] = Field(min_length=1)
    horizon: int = Field(default=30, ge=1, le=365)


class TimelineDay(BaseModel):
    day: int
    unmet: float
    down: list[str]
    node_status: dict[str, NodeStatus]
    utilization: dict[str, float] = Field(description="node id -> load / capacity that day (>0.9 = bottleneck)")


class Delay(BaseModel):
    avg_days: float = Field(description="mean extra delivery delay across customers")
    p90_days: float
    per_customer: dict[str, float]


class Bottleneck(BaseModel):
    node: str
    utilization: float = Field(description="peak load / capacity over the horizon")
    day: int | None = Field(default=None, description="day the peak occurs")


class SimulateResponse(BaseModel):
    timeline: list[TimelineDay]
    log: list[str]
    stockout_day: dict[str, int]
    total_unmet: float
    survival_clock_days: int = Field(description="days until the first customer stockout")
    revenue_at_risk: float = Field(description="INR")
    delay: Delay
    bottlenecks: list[Bottleneck] = Field(description="nodes whose utilization exceeds 90%")


class MonteCarloRequest(BaseModel):
    events: list[Event] = Field(min_length=1)
    n: int = Field(default=200, ge=10, le=5000)


class HistogramBin(BaseModel):
    bin: float = Field(description="lower edge of the unmet-units bin")
    count: int


class MonteCarloResponse(BaseModel):
    p50: float
    p90: float
    p_shortage: float = Field(ge=0, le=1)
    histogram: list[HistogramBin]


# ---------------------------------------------------------------- chaos
class Spof(BaseModel):
    target: str
    unmet: float


class HiddenPair(BaseModel):
    pair: list[str] = Field(min_length=2, max_length=2)
    unmet: float
    synergy: float = Field(description="unmet(a,b) - unmet(a) - unmet(b); >0 means the pair is worse together")


class ChaosResponse(BaseModel):
    spof: list[Spof]
    hidden_pairs: list[HiddenPair]
    resilience_score: float = Field(ge=0, le=100)


# ---------------------------------------------------------------- recover
class RecoverRequest(BaseModel):
    events: list[Event] = Field(min_length=1)


class SafetyCheck(BaseModel):
    passed: bool
    warning: str | None = None


class Strategy(BaseModel):
    name: str
    cost: float = Field(description="INR")
    unmet: float
    recovery_days: int
    delay_avg_days: float = Field(description="mean extra delivery delay with this strategy applied")
    co2: float = Field(description="tonnes CO2")
    resilience_after: float = Field(ge=0, le=100)
    safety_check: SafetyCheck
    recommended: bool = False
    description: str | None = None


class Roi(BaseModel):
    inaction_loss: float
    fix_cost: float
    net_saving: float


class AlternateSupplier(BaseModel):
    replaces: str = Field(description="disrupted supplier id")
    supplier: str
    name: str
    city: str
    spare_capacity: float = Field(description="units/day available")
    lead: float = Field(description="days")
    cost_premium_pct: float
    reliability: float = Field(ge=0, le=1)
    reason: str | None = Field(default=None, description="why this alternate ranks where it does")


class AlternateRoute(BaseModel):
    origin: str
    destination: str
    via: list[str] = Field(description="full node path, origin..destination")
    replaces: str = Field(description='blocked lane or node, e.g. "F1->W3"')
    old_via: list[str] | None = Field(default=None, description="the main path this route replaces")
    spare_capacity: float
    extra_lead_days: float = Field(description="delay delta: new path lead - old path lead (days)")
    extra_cost_per_unit: float = Field(description="cost delta: new path - old path (INR/unit)")


class InventoryAction(BaseModel):
    node: str
    action: Literal["pre-position", "transfer", "raise_safety_stock", "hold"]
    units: float
    source: str | None = None
    day: int
    reason: str


class ProductionAction(BaseModel):
    from_factory: str
    to_factory: str
    units_per_day: float
    start_day: int
    duration: int
    reason: str


class RecoverResponse(BaseModel):
    strategies: list[Strategy]
    roi: Roi
    playbook: list[str]
    alternate_suppliers: list[AlternateSupplier]
    alternate_routes: list[AlternateRoute]
    inventory_actions: list[InventoryAction]
    production_actions: list[ProductionAction]


# ---------------------------------------------------------------- parse
class ParseRequest(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class ParseResponse(BaseModel):
    events: list[Event]


# ---------------------------------------------------------------- forecast / surrogate
class ForecastPoint(BaseModel):
    day: int
    mean: float
    p10: float
    p90: float


class HistoryPoint(BaseModel):
    day: int = Field(description="negative = past days, 0 = today")
    demand: float


class CustomerForecast(BaseModel):
    id: str
    history: list[HistoryPoint]
    forecast: list[ForecastPoint]


class ForecastResponse(BaseModel):
    horizon_days: int
    method: str
    mape: float = Field(description="backtest mean absolute percentage error, 0..1")
    customers: list[CustomerForecast]


class FeatureImportance(BaseModel):
    feature: str
    importance: float


class SurrogateResponse(BaseModel):
    target: str = Field(description="what the surrogate predicts, e.g. total unmet units")
    mae: float
    r2: float
    n_train: int
    n_test: int
    speedup: float = Field(description="simulator runtime / surrogate runtime")
    top_features: list[FeatureImportance]


# ---------------------------------------------------------------- upload
class UploadSummary(BaseModel):
    n_nodes: int
    n_edges: int
    by_kind: dict[str, int]


class UploadResponse(BaseModel):
    network: NetworkResponse
    summary: UploadSummary
    warnings: list[str]
    activated: bool = Field(description="true if the uploaded network replaced the live graph for core/ routers")


# ---------------------------------------------------------------- risk / scenario prediction
class RiskPredictRequest(BaseModel):
    events: list[Event] = Field(min_length=1)
    horizon: int = Field(default=30, ge=1, le=365, description="Simulation horizon (days) used as denominator for the unmet fraction")


class RiskShapFactor(BaseModel):
    feature: str = Field(description="Scenario feature name")
    impact: float = Field(description="SHAP value: positive pushes the predicted fraction up, negative down")


class RiskModelMetrics(BaseModel):
    mae: float = Field(description="Mean absolute error on held-out test scenarios")
    r2: float = Field(description="R² on held-out test scenarios (0 = baseline, 1 = perfect)")
    n_train: int
    n_test: int


class RiskPredictResponse(BaseModel):
    unmet_demand_fraction: float = Field(ge=0, le=1, description="Predicted share of total demand unmet over the horizon (0 = no disruption, 1 = total failure)")
    predicted_unmet_units: float = Field(default=0.0, description="Estimated unmet demand in physical units over 30 days")
    risk_score: int = Field(default=0, ge=0, le=100, description="Calibrated scenario risk score from 0 (negligible) to 100 (critical)")
    risk_level: Literal["low", "moderate", "high", "critical"] = Field(default="low", description="Risk tier: low | moderate | high | critical")
    confidence: Literal["model", "no_model"] = Field(description="'model' = XGBoost prediction; 'no_model' = model not trained")
    top_factors: list[RiskShapFactor] = Field(description="Top SHAP contributors (feature-level, not causal)")
    model_metrics: RiskModelMetrics | None = Field(default=None, description="Evaluation metrics from training; null if no model")
    note: str | None = Field(default=None, description="Informational note, e.g. about model status")


class RiskModelStatusResponse(BaseModel):
    trained: bool
    path: str
    metrics: RiskModelMetrics | None = None
