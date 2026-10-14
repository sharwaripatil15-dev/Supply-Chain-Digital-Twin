"""Pydantic v2 models for every request and response in the AEGIS API contract."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from node_types import ALL_TYPE_FIELDS, TYPE_FIELDS, NodeKind, TransportMode, is_demand

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
    demand: float = Field(ge=0, description="units/day (demand nodes only: retailers and customers, else 0)")
    risk: float | None = Field(
        ge=0, le=1, description="ML-predicted share of demand lost if this node fails alone (criticality, 0..1); "
        "null when the network is too small or the model cannot score it (see risk_note)"
    )
    risk_note: str | None = Field(default=None, description="why risk is null")
    reliability: float = Field(default=1.0, ge=0, le=1, description="historical on-time-in-full rate")
    utilization: float = Field(default=0.0, ge=0, description="baseline load / capacity (0 for leaf demand nodes)")
    top_factors: list[RiskFactor] = []
    name: str | None = None
    backup: bool = False
    details: dict[str, Any] = Field(default_factory=dict, description="extra builder fields (material, priority, ...)")


class Edge(BaseModel):
    source: str
    target: str
    capacity: float = Field(ge=0, description="units/day")
    lead: float = Field(ge=0, description="lead time, days")
    cost: float = Field(ge=0, description="INR per unit")
    co2: float = Field(ge=0, description="kg CO2 per unit")
    id: str | None = Field(default=None, description="builder lane id (manual networks)")
    mode: TransportMode | None = None
    distance_km: float | None = None


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
    # Optional provenance, set on events derived from the weather forecast (POST /weather/apply). Older clients omit them.
    source: Literal["user", "weather"] | None = Field(default=None, description='"weather" for forecast-derived events')
    confidence: float | None = Field(default=None, ge=0, le=1, description="forecast confidence (lower further out)")
    lead_multiplier: float | None = Field(
        default=None, ge=1, le=10, description="edge events: lead time x this factor while active (weather slowdowns)"
    )
    reason: str | None = Field(default=None, max_length=300, description="plain-English cause, e.g. the weather drivers")
    direction: Literal["up", "down"] | None = Field(
        default=None, description='demand events: "down" = demand falls by severity (default "up": rises by severity)'
    )


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
    scenario: dict[str, Any] | None = Field(
        default=None, description="scenario surrogate held-out metrics (models/metrics.json): per target MAE, RMSE, R2, "
        "Spearman, top-10 recall, interval coverage, baselines, timing; null if no model has been trained"
    )


# ---------------------------------------------------------------- upload
class UploadSummary(BaseModel):
    n_nodes: int
    n_edges: int
    by_kind: dict[str, int]


class UploadResponse(BaseModel):
    network: NetworkResponse
    summary: UploadSummary
    warnings: list[str]
    activated: bool = Field(description="true if the uploaded network became the active network (source = csv)")


# ---------------------------------------------------------------- manual network builder
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,23}$"
NetworkSource = Literal["preset", "csv", "manual"]
ActiveState = Literal["active", "inactive"]
MAX_NODES = 60
MAX_EDGES = 400

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class BuilderNode(BaseModel):
    """A node as the builder edits it. Common fields first; type-specific ones must be null for other kinds."""
    model_config = _STRICT

    id: str | None = Field(default=None, pattern=ID_PATTERN, description="auto-generated (S1, F2, ...) when omitted")
    name: str = Field(min_length=1, max_length=80)
    kind: NodeKind
    city: str = Field(default="", max_length=120, description="address or city")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    capacity: float = Field(default=0.0, ge=0, description="throughput, units/day")
    stock: float = Field(default=0.0, ge=0, description="current stock, units")
    reliability: float = Field(default=0.95, ge=0, le=1)
    op_cost: float = Field(default=0.0, ge=0, description="operating cost, INR per unit")
    status: ActiveState = "active"
    # supplier
    material: str | None = Field(default=None, max_length=80)
    lead_time_days: float | None = Field(default=None, ge=0, le=365)
    min_order_qty: float | None = Field(default=None, ge=0)
    is_backup: bool = False
    price_per_unit: float | None = Field(default=None, ge=0)
    # factory
    production_capacity: float | None = Field(default=None, ge=0, description="units/day; overrides capacity in the engine")
    production_cost: float | None = Field(default=None, ge=0)
    overtime_limit_pct: float | None = Field(default=None, ge=0, le=100)
    shifts_per_day: int | None = Field(default=None, ge=1, le=4)
    # warehouse
    storage_capacity: float | None = Field(default=None, ge=0, description="units")
    safety_stock: float | None = Field(default=None, ge=0)
    holding_cost: float | None = Field(default=None, ge=0, description="INR per unit per day")
    handling_time_days: float | None = Field(default=None, ge=0, le=60)
    # retailer / customer
    daily_demand: float | None = Field(default=None, ge=0, validate_default=True, description="units/day")
    demand_variability_pct: float | None = Field(default=None, ge=0, le=100)
    service_level_pct: float | None = Field(default=None, ge=0, le=100)
    shelf_stock: float | None = Field(default=None, ge=0)
    priority: Literal["low", "medium", "high"] | None = None
    penalty_per_unit: float | None = Field(default=None, ge=0, description="INR per unmet unit")

    @field_validator("daily_demand", mode="after")
    @classmethod
    def _demand_required(cls, v: float | None, info: ValidationInfo) -> float | None:
        kind = info.data.get("kind")
        if v is None and is_demand(kind):
            raise ValueError(f"daily demand is required for a {kind}")
        return v

    @model_validator(mode="after")
    def _only_own_type_fields(self) -> "BuilderNode":
        allowed = set(TYPE_FIELDS[self.kind])
        stray = [f for f in ALL_TYPE_FIELDS if f not in allowed and getattr(self, f) not in (None, False)]
        if stray:
            raise ValueError(f"field(s) not used by a {self.kind}: {', '.join(stray)}")
        return self


class BuilderEdge(BaseModel):
    """A lane. distance_km, lead, cost and co2 are suggested from the endpoints and mode when left empty."""
    model_config = _STRICT

    id: str | None = Field(default=None, pattern=ID_PATTERN, description="auto-generated (E1, E2, ...) when omitted")
    source: str = Field(pattern=ID_PATTERN)
    target: str = Field(pattern=ID_PATTERN)
    mode: TransportMode = "road"
    distance_km: float | None = Field(default=None, ge=0, le=25000)
    lead: float | None = Field(default=None, ge=0, le=365, description="days")
    capacity: float = Field(ge=0, description="units/day")
    cost: float | None = Field(default=None, ge=0, description="INR per unit")
    co2: float | None = Field(default=None, ge=0, description="kg CO2 per unit")
    status: ActiveState = "active"

    @model_validator(mode="after")
    def _no_self_loop(self) -> "BuilderEdge":
        if self.source == self.target:
            raise ValueError(f"a lane cannot start and end at the same node ({self.source})")
        return self


class BuilderNetwork(BaseModel):
    """Body of POST /network/import and /network/validate (an export file is accepted as-is)."""
    model_config = ConfigDict(extra="ignore")

    nodes: list[BuilderNode] = Field(default_factory=list, max_length=MAX_NODES)
    edges: list[BuilderEdge] = Field(default_factory=list, max_length=MAX_EDGES)


class ValidationIssue(BaseModel):
    code: str
    message: str
    refs: list[str] = Field(default_factory=list, description="node or lane ids the issue is about")


class ValidationReport(BaseModel):
    errors: list[ValidationIssue] = Field(description="block Apply and every engine endpoint")
    warnings: list[ValidationIssue] = Field(description="shown, but the network can still run")
    runnable: bool


class NetworkSourceInfo(BaseModel):
    source: NetworkSource
    version: int = Field(description="bumped on every change to any network or the active source")
    node_count: int = Field(description="active network")
    edge_count: int
    runnable: bool = Field(description="false if the active network has blocking validation errors")
    manual_node_count: int
    manual_edge_count: int
    csv_loaded: bool
    note: str | None = Field(default=None, description="e.g. the persisted network could not be read at startup")


class SetSourceRequest(BaseModel):
    source: NetworkSource


class ManualNetworkResponse(BaseModel):
    source: NetworkSource
    version: int
    nodes: list[BuilderNode]
    edges: list[BuilderEdge]
    validation: ValidationReport


class NodeMutationResponse(BaseModel):
    node: BuilderNode | None
    removed_edges: list[BuilderEdge] = []
    version: int
    validation: ValidationReport


class EdgeMutationResponse(BaseModel):
    edge: BuilderEdge | None
    version: int
    validation: ValidationReport


class SynthNetwork(BuilderNetwork):
    """A generated network as builder JSON (import it with POST /network/import)."""
    meta: dict[str, Any] = Field(default_factory=dict, description="archetype, industry, seed, size, unit price ...")


class GenerateNetworkRequest(BaseModel):
    archetype: Literal["linear", "multi_source", "hub_spoke", "two_region_port", "backup_supplier", "concentrated", "long_tail"]
    industry: Literal["fmcg", "pharma", "electronics", "automotive", "apparel", "agri"]
    n_nodes: int = Field(default=24, ge=10, le=60)
    seed: int | None = Field(default=None, ge=0, description="omit for a fresh random network")


class ExportedNetwork(BuilderNetwork):
    format: Literal["aegis-network"] = "aegis-network"
    schema_version: int = 1
    source: NetworkSource
    version: int


# ---------------------------------------------------------------- what-if (/whatif/*)
class WhatIfRunRequest(BaseModel):
    text: str | None = Field(default=None, min_length=3, max_length=2000, description='e.g. "What if Supplier S2 fails for 10 days?"')
    events: list[Event] | None = Field(default=None, description="structured scenario (overrides text)")
    horizon: int = Field(default=30, ge=5, le=90)
    mc_runs: int = Field(default=100, ge=10, le=1000, description="Monte Carlo runs of the exact simulator")
    robustness_runs: int = Field(default=10, ge=0, le=50, description="Monte Carlo realisations re-planned for robustness")
    seed: int = 7

    @model_validator(mode="after")
    def _need_input(self) -> "WhatIfRunRequest":
        if not self.events and not self.text:
            raise ValueError("give either a question (text) or events")
        return self


class WhatIfAskRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=40)
    question: str = Field(min_length=2, max_length=500)


class WhatIfCompareRequest(BaseModel):
    ids: list[str] = Field(min_length=2, max_length=4)


# ---------------------------------------------------------------- weather (/weather/*)
class WeatherApplyRequest(BaseModel):
    horizon: int = Field(default=7, ge=1, le=16, description="forecast days to convert")
    min_level: Literal["moderate", "high", "severe"] = Field(default="high", description="lowest risk level that becomes an event")
    include_nodes: bool = Field(default=True, description="also create site events (flooded plant, closed port)")


class WeatherRerouteRequest(BaseModel):
    events: list[Event] | None = Field(default=None, description="weather events to plan for; default: derived from the forecast")
    horizon: int = Field(default=7, ge=1, le=16)


class WeatherScenarioRequest(BaseModel):
    id: str | None = Field(default=None, description="scenario id to activate; null returns to live data")
