# AEGIS: AI Supply Chain Digital Twin & Disruption Simulator

> See the disruption coming, find the failure nobody tested for, and pick a fix that doesn't break something else.

AEGIS builds a live digital twin of a multi-tier supply chain (suppliers → factories → warehouses → customers), lets you
throw disruptions at it (a plant fire, a flooded lane, a demand spike), and watch the ripple travel day by day. It then
stress-tests the network on its own and recommends a recovery plan with the trade-offs laid out.

### Three things nobody else shows you

1. **Chaos Finder (reverse stress-test).** Don't wait for someone to ask "what if X fails?". AEGIS knocks out every
   node and **every pair** of nodes and ranks the damage. It surfaces *hidden pairs*: two warehouses that each look
   safe alone but together cut off a whole region (`synergy = unmet(a+b) − unmet(a) − unmet(b)`).
2. **Survival Clock.** One number a COO understands: *days until the first customer runs out of stock*. Below it:
   revenue at risk, and P50/P90 from a Monte Carlo over uncertain outage durations.
3. **Fix-safety check.** The cheapest fix is often a trap: draining safety stock fixes today and creates tomorrow's
   single point of failure. Every candidate strategy is re-stress-tested *after* it's applied; fixes that create a
   worse vulnerability get flagged red, and the recommendation is the cheapest **safe** plan.

The LLM (Claude) is used **only** to turn plain English into structured events and to narrate the playbook. It never
computes a number: parsed events are validated against the graph, and the narration is rejected if it contains any
number the engine didn't produce.

---

## Architecture

```
                         ┌──────────────────────────────────────────────────────────┐
  Browser :5173          │  React 18 + Vite + Tailwind                              │
                         │  Twin │ Simulate │ Chaos Finder │ Recover                │
                         │  Cytoscape graph · DaySlider · Recharts · KPI tiles      │
                         └───────────────┬──────────────────────────────────────────┘
                                         │ axios (VITE_API_URL)
                         ┌───────────────▼──────────────────────────────────────────┐
  FastAPI :8000          │ routers/  network · simulate · chaos · recover · parse   │
                         │           forecast/surrogate · upload (CSV, real)        │
                         │   validation.py (node ids exist, severity 0..1) → 422     │
                         │   cache.py (in-memory TTL, optional Redis) ◄──────────────┼──► Redis :6379
                         │                │ USE_MOCK_*=true        │ USE_MOCK_*=false│
                         │        ┌───────▼───────┐      ┌─────────▼──────────────┐  │
                         │        │ mock/         │      │ core/                   │  │
                         │        │ mock_data.py  │      │  graph.py   (NetworkX)  │  │
                         │        │ demo_network  │      │  sim.py     min-cost flow│ │
                         │        └───────────────┘      │  montecarlo lognormal   │  │
                         │                               │  chaos.py   pair synergy│  │
                         │                               │  optimizer  PuLP LP     │  │
                         │                               │  strategies safety check│  │
                         │                               │  risk_ml    XGB + SHAP  │  │
                         │                               └─────────────────────────┘  │
                         │  llm/parser.py → Claude: parse text→events, narrate only  │
                         └──────────────────────────────────────────────────────────┘
       (optional, commented out in docker-compose: PostgreSQL for run history, Neo4j for huge graphs)
```

## Run it

### Docker (everything)

```bash
cp .env.example .env          # optional: add ANTHROPIC_API_KEY
docker compose up --build
```

- UI: http://localhost:5173
- API + Swagger: http://localhost:8000/docs
- Redis: localhost:6379

### Local

```bash
# backend (Python 3.11+)
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest                        # smoke tests for every endpoint
uvicorn main:app --reload     # http://localhost:8000/docs

# frontend (Node 20+), in another terminal
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

### Mock switches (one per router)

| Flag (default `true`) | Endpoints | When `false` |
|---|---|---|
| `USE_MOCK_NETWORK` | `GET /network`, `/forecast`, `/surrogate` | `core/risk_ml.py`, `core/chaos.py`, `core/forecast.py` |
| `USE_MOCK_SIMULATE` | `POST /simulate`, `/montecarlo` | `core/sim.py`, `core/montecarlo.py`, `core/delay.py` |
| `USE_MOCK_CHAOS` | `GET /chaos` | `core/chaos.py` |
| `USE_MOCK_RECOVER` | `POST /recover` | `core/strategies.py`, `core/optimizer.py`, `core/recommend.py` |
| `USE_MOCK_PARSE` | `POST /parse` | `llm/parser.py` (needs `ANTHROPIC_API_KEY`) |

A router switched to `false` calls `core/`. Unimplemented stubs raise `NotImplementedError`, which the API returns as
**HTTP 501** with a clear message, so each owner can go live independently. `GET /health` reports the current flags.
`POST /upload` is always live: CSV parsing and validation are real code.

## API contract

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/network` | - | `{ nodes:[{id,kind,city,lat,lon,capacity,stock,demand,risk,reliability,utilization,top_factors:[{feature,impact}]}], edges:[{source,target,capacity,lead,cost,co2}], resilience_score }` |
| POST | `/simulate` | `{ events:[Event], horizon=30 }` | `{ timeline:[{day,unmet,down:[id],node_status:{id:"ok\|stressed\|down"},utilization:{id:float}}], log:[str], stockout_day:{customerId:day}, total_unmet, survival_clock_days, revenue_at_risk, delay:{avg_days,p90_days,per_customer:{id:days}}, bottlenecks:[{node,utilization,day}] }` |
| POST | `/montecarlo` | `{ events:[Event], n=200 }` | `{ p50, p90, p_shortage, histogram:[{bin,count}] }` |
| GET | `/chaos` | `?top=5` | `{ spof:[{target,unmet}], hidden_pairs:[{pair:[a,b],unmet,synergy}], resilience_score }` |
| POST | `/recover` | `{ events:[Event] }` | `{ strategies:[{name,cost,unmet,recovery_days,delay_avg_days,co2,resilience_after,safety_check:{passed,warning},recommended}], roi:{inaction_loss,fix_cost,net_saving}, playbook:[str], alternate_suppliers:[{replaces,supplier,name,city,spare_capacity,lead,cost_premium_pct,reliability}], alternate_routes:[{origin,destination,via,replaces,spare_capacity,extra_lead_days,extra_cost_per_unit}], inventory_actions:[{node,action,units,source,day,reason}], production_actions:[{from_factory,to_factory,units_per_day,start_day,duration,reason}] }` |
| POST | `/parse` | `{ text }` | `{ events:[Event] }` |
| GET | `/forecast` | `?horizon=14` | `{ horizon_days, method, mape, customers:[{id, history:[{day,demand}], forecast:[{day,mean,p10,p90}]}] }` |
| GET | `/surrogate` | - | `{ target, mae, r2, n_train, n_test, speedup, top_features:[{feature,importance}] }` |
| POST | `/upload` | multipart `nodes`, `edges` (CSV), `?activate=false` | `{ network:{...as /network, resilience_score:null}, summary:{n_nodes,n_edges,by_kind}, warnings:[str], activated }` |
| GET | `/health` | - | `{ status, mock:{network,simulate,chaos,recover,parse} }` |

CSV templates: [backend/mock/sample_nodes.csv](backend/mock/sample_nodes.csv) and
[backend/mock/sample_edges.csv](backend/mock/sample_edges.csv). The UI also serves them under `/samples/`. Bottleneck =
utilization above 90%.

`Event = { type: "node"|"edge"|"demand", target: nodeId | "SRC->DST", start: day≥0, duration: days≥1, severity: 0..1 }`

Errors: `422` invalid body or unknown node/edge id, `501` core function not implemented yet, `503` LLM unavailable.
All schemas live in [backend/schemas.py](backend/schemas.py).

## PS 04 requirements → features

> This mapping uses the PS 04 requirements as we read them from the brief. Check it against the official problem
> statement before submitting and adjust the left column's wording to match.

| Requirement | Delivered by | Where | Status today |
|---|---|---|---|
| Digital twin of a multi-tier supply network | 16-node, 4-tier network on a map, with capacity, stock, reliability and utilization per node | Twin tab, `GET /network`, `core/graph.py` | Mock data; graph loader real |
| Ingest a company's own network data | CSV upload with validation and warnings, preview on the map, optional activation for the live engine | Twin → *Load your network*, `POST /upload` | **Real** |
| Simulate disruptions (supplier, route, demand) | Event builder (node / edge / demand, start, duration, severity), 3 one-click demos, plain-English input | Simulate tab, `POST /simulate`, `POST /parse` | Mock ripple; LLM parser real behind its flag |
| Show how disruption propagates over time | Day slider recolours nodes ok/stressed/down; event log; ripple timeline | Simulate tab | Mock |
| Estimate delivery delays | Avg / P90 delay KPI, per-customer delay chart | Simulate → KPIs, *Delivery delay by customer* | Mock; summary helpers real |
| Identify bottlenecks | Per-day utilization bars, bottleneck halo on the graph, peak-bottleneck list (>90%) | Simulate → *Utilization*, graph | Mock data; detection real (`core/delay.find_bottlenecks`) |
| Quantify business impact | Unmet units, Survival Clock, revenue at risk, Monte Carlo P50/P90 | Simulate → KPIs, Monte Carlo chart | Mock |
| Predict risk with explainable ML | Node risk score + SHAP factors on click; simulator surrogate with MAE / R² | Twin → node panel, *ML surrogate accuracy*, `GET /surrogate` | Mock (stubs in `core/risk_ml.py`) |
| Forecast demand | 14-day forecast with P10-P90 band and backtest MAPE | Twin → *Demand forecast*, `GET /forecast` | Mock (stub in `core/forecast.py`) |
| Find vulnerabilities proactively | Chaos Finder: single points of failure and hidden failure pairs, resilience score | Chaos Finder tab, `GET /chaos` | Mock |
| Recommend alternate suppliers and routes | Ranked alternate suppliers (spare capacity, lead, premium, reliability), alternate paths | Recover → *Alternate suppliers / routes* | Mock (stubs in `core/recommend.py`) |
| Optimize inventory and production | Inventory buffer and production shift strategies, concrete inventory and production actions | Recover → strategy table, *Inventory / Production actions* | Mock (LP levers stubbed in `core/optimizer.py`) |
| Compare mitigation strategies | Cost vs unmet vs delay vs CO₂ vs resilience, ROI of acting, fix-safety check | Recover tab, `POST /recover` | Mock |
| Actionable output for operators | Day-by-day playbook (LLM narration is guarded against invented numbers) | Recover → *Action playbook* | Mock; guard real |

## Limitations (honest)

- **Synthetic data.** The network, risk factors, demand history and every number in the UI are synthetic and shaped
  to look realistic for Indian logistics. Nothing is calibrated against real suppliers, so treat every output as
  illustrative until it runs on real data.
- **Mostly mocked engine.** In this build the simulator, Monte Carlo, Chaos Finder, optimizer, recommender, risk model,
  forecast and surrogate are documented stubs. The mock layer returns plausible, scenario-dependent numbers from a
  simple heuristic, not from the algorithms described. The table below lists exactly what is real.
- **Small prototype.** 16 nodes and 23 lanes, a single product, a 30-day horizon at daily resolution. No multi-echelon
  inventory policies, BOMs, transport modes, or contracts.
- **In-process state.** An uploaded network lives in memory until the backend restarts; there are no accounts and no
  persistence.
- **Scaling path, not built yet:** Neo4j for graph storage and path queries on 10k+ node networks; Redis (already
  wired as an optional cache) for shared result caching and as a job queue for Monte Carlo and Chaos Finder batches;
  the ML surrogate to pre-screen failure pairs so only the top candidates get full simulations; PostgreSQL for
  scenario and run history. Postgres and Neo4j are commented out in `docker-compose.yml`.
- **LLM scope.** Claude only parses scenarios and narrates the playbook. Parsed events are validated against the graph,
  and narration containing numbers the engine didn't produce is rejected.

## Who owns what

| Owner | Area | Files |
|---|---|---|
| **A** | Simulation engine | `core/graph.py`, `core/sim.py`, `core/montecarlo.py`, `core/delay.py` |
| **B** | Optimizer + Chaos Finder | `core/optimizer.py`, `core/chaos.py`, `core/strategies.py`, `core/recommend.py` |
| **C** | Frontend | `frontend/src/**` |
| **D** | ML + LLM + integration | `core/risk_ml.py`, `core/forecast.py`, `llm/parser.py`, `routers/` (incl. upload), `docker-compose.yml`, tests |

Contract rule: nobody changes `schemas.py` without telling C and D. Mock and live outputs must validate against the same models.

## Build phases / TODO

**Phase 0: Scaffold (done)**
- [x] API contract + Pydantic schemas, mock data for every endpoint
- [x] UI wired to mocks: graph, day slider, KPIs, Monte Carlo, Chaos Finder, Recover, Playbook
- [x] Docker compose, Redis cache hook, pytest smoke tests

**Phase 0.5: Upgrade (done)**
- [x] Per-router `USE_MOCK_*` flags
- [x] Reliability/utilization, delay, bottlenecks, alternates, inventory/production actions in schemas + mocks + UI
- [x] `/forecast`, `/surrogate`, `/upload` (CSV upload is real), tests for all new endpoints

**Phase 1: Simulation core (A)**
- [ ] `sim.solve_flow`: min-cost flow with node splitting (NetworkX / OR-Tools)
- [ ] `sim.simulate`: day loop, stock drawdown, node status, per-day utilization, Survival Clock
- [ ] `delay.customer_delays`: lead-time-aware delay model (SimPy)
- [ ] `montecarlo.monte_carlo`: lognormal durations, P50/P90
- [ ] Set `USE_MOCK_SIMULATE=false` and keep the tests green

**Phase 2: Chaos + recovery (B)**
- [ ] `chaos.chaos_find`: singles + pruned pair-synergy search
- [ ] `chaos.resilience_score`
- [ ] `optimizer.optimize_plan` with the `safety_stock_lever` and `production_shift_lever` levers (PuLP)
- [ ] `recommend.alternate_suppliers` / `alternate_routes`
- [ ] `strategies.run_strategies` + `safety_check` (re-run Chaos Finder on the post-fix graph)

**Phase 3: Intelligence (D)**
- [ ] `risk_ml.train_risk_model` (XGBoost on synthetic disruption history) + `node_risk_with_shap`
- [ ] `risk_ml.train_surrogate` + `surrogate_report` (MAE / R² on held-out scenarios)
- [ ] `forecast.forecast_demand`: Holt-Winters vs XGBoost lag model, backtest MAPE
- [ ] Live `/parse` with `ANTHROPIC_API_KEY`; add eval prompts for tricky phrasing
- [ ] `write_playbook` wired into `/recover` with the number-grounding guard

**Phase 4: Polish and demo (C + all)**
- [ ] Edge disruptions drawn on the graph (dashed red lanes)
- [ ] Before/after resilience comparison on the Recover tab
- [ ] 3-minute demo script: Twin → Supplier failure → Chaos Finder hidden pair → Recover (cheapest fix fails safety check)
