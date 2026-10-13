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
npm test                      # node --test: node-type mapping + builder form validation
npm run dev                   # http://localhost:5173
```

The active network is saved to `backend/data/active_network.json` (override with `AEGIS_DATA_DIR`; Docker keeps it in
the `aegis-data` volume). Delete the file to start from the preset again; an unreadable file is moved aside to
`active_network.corrupt.json` and the app starts on the preset with a notice on the Data tab.

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

**Mocks only describe the preset.** The flags apply while the preset demo is the active network. An activated CSV
network or a manual network always runs on the real engine (`core/`), whatever the flags say.

## Data tab: three ways to define the network

The Data tab has a **Preset demo | CSV upload | Manual builder** switch. All three produce the same thing, the *active
network*, which Twin, Simulate, Chaos Finder and Recover all use. The top bar shows the active source; click it to
jump to the Data tab.

| Source | How | Notes |
|---|---|---|
| Preset demo | "Use the preset demo" | The curated 16-site network behind the quick-start scenarios. "Copy into the builder" makes an editable copy. |
| CSV upload | `nodes.csv` + `edges.csv` ([templates](backend/mock/sample_nodes.csv)) with "Use it as the active network" checked | Unchecked = preview on the Twin tab only (the old behaviour). `kind` may now also be `retailer`. |
| Manual builder | Add nodes and lanes by hand, then **Apply network** | Saved on the server after every edit; undo/redo (last 20 actions); import/export JSON; export CSV in the upload format. |

**Builder workflow.** "Add node" opens a type picker (5 cards). The form adapts to the type, validates as you type
(Save stays disabled until it is valid) and has three ways to set a location: search ~45 Indian cities, type
latitude/longitude, or "Pick on map" and click the offline map preview (pure SVG: no tiles, works offline). "Add lane"
only offers legal targets for the chosen source and fills in distance (haversine), lead time, cost and CO₂ from the
coordinates and transport mode; every suggestion can be overridden. Click a row or a map marker to edit; deleting a
node asks for confirmation and lists the lanes that go with it. The validation panel is always visible: red errors
block Apply, amber warnings do not, and each item links to the node or lane it is about. Once the manual network is
active, every edit refreshes the other tabs automatically.

**Validation rules.** Errors (block Apply and every engine endpoint, which answers **409** with the reason): no active
supplier, no active retailer/customer, a lane pointing at a missing node, duplicate ids, duplicate lanes, self-loops.
Warnings: a node with no lanes, a demand point unreachable from any supplier, primary supplier capacity below total
demand, no backup supplier, an illegal tier direction (import only; the forms refuse them), zero total demand, a
warehouse holding more than its storage capacity, a lane ignored because one end is inactive. Field values are
checked by Pydantic (422 with the field name): negative numbers, latitude outside -90..90, longitude outside -180..180,
reliability outside 0..1, percentages outside 0..100, and fields that belong to another node type.

### Node types

The type of a node is always **shape + color + icon**. Its status (ok / stressed / down) is a ring, glow and badge in
the status colors (green `#22C55E`, amber `#F59E0B`, red `#EF4444`), never the fill. The definitions live in
[frontend/src/lib/nodeTypes.js](frontend/src/lib/nodeTypes.js), mirrored by [backend/node_types.py](backend/node_types.py).

| Type | Color | 2D shape | 3D column | Icon | Demand point |
|---|---|---|---|---|---|
| Supplier | violet `#8B5CF6` | triangle | tall thin triangular prism | truck | no |
| Factory | blue `#2563EB` | rounded square | wide square block with a stack on top (tallest) | factory | no |
| Warehouse | teal `#0D9488` | hexagon | wide, low hexagonal slab | warehouse | no |
| Retailer | magenta `#DB2777` | octagon | medium octagonal column | storefront | **yes** |
| Customer | slate `#475569` (light outline in dark mode) | circle | short round cylinder | person | **yes** |

Allowed lanes: supplier → factory, factory → warehouse, warehouse → retailer, warehouse → customer,
retailer → customer, plus the optional direct links supplier → warehouse, factory → retailer and factory → customer.

Retailers and customers are both **demand points**: the simulator, flow solver, Survival Clock, Chaos Finder, optimizer,
strategies, delay model, forecast and risk model treat them the same way (`is_demand()` in backend/node_types.py). A
retailer can also ship on to customers, limited by its forwarding capacity (0 = no limit). The pipeline runs on
networks that lack some tiers (for example supplier → warehouse → customer with no factory).

The 2D view (Cytoscape) offers a **Geo** layout (latitude/longitude) and a **Tiers** layout (one column per tier).
The 3D view (deck.gl) uses lit columns whose height follows stock, a billboard icon and a name label (it fades in as you
zoom), a status ring that pulses when a node is down, a ripple when a node newly fails, a criticality glow, lanes
colored by their source type, dashed red disrupted lanes, accent recovery routes, and flow particles whose speed
follows lead time and whose color shows the transport mode. Both views share one legend: click a type to hide it.
3D loads lazily, needs WebGL, and falls back to 2D on any error.

### Node field reference

Common to every type: `id` (auto-generated as S1, F1, W1, R1, C1 ..., editable only on create; letters, digits, `-`,
`_`), `name`, `kind`, `city` (address or city), `lat`, `lon`, `capacity` (units/day), `stock` (units), `reliability`
(0..1), `op_cost` (₹/unit), `status` (`active` | `inactive`; inactive nodes and their lanes are left out of every run).

| Type | Extra fields | Engine mapping |
|---|---|---|
| Supplier | `material`, `lead_time_days`, `min_order_qty`, `is_backup`, `price_per_unit` | `backup = is_backup` (a backup opens only after a shortfall, at 1.5x lane cost) |
| Factory | `production_capacity` (units/day), `production_cost`, `overtime_limit_pct`, `shifts_per_day` | `capacity = production_capacity` when given |
| Warehouse | `storage_capacity`, `safety_stock`, `holding_cost` (₹/unit/day), `handling_time_days` | `capacity` = throughput/day |
| Retailer | `daily_demand` (required), `demand_variability_pct`, `service_level_pct`, `shelf_stock` | `demand = daily_demand`, `stock = stock + shelf_stock`, `capacity` = forwarding limit |
| Customer | `daily_demand` (required), `priority` (low/medium/high), `penalty_per_unit` | `demand = daily_demand` |

Lanes: `source`, `target`, `mode` (road/rail/sea/air), `distance_km`, `lead` (days), `capacity` (units/day), `cost`
(₹/unit), `co2` (kg/unit), `status`. Empty distance/lead/cost/co2 are suggested: distance by haversine, lead =
distance / speed + handling (road 450 km/day + 0.5 d, rail 380 + 1, sea 350 + 2, air 4000 + 0.5; at least 1 day), CO₂
per unit-km (road 0.0026, rail 0.0011, sea 0.0008, air 0.012 kg). Extra fields are kept and shown in the node drawer.

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
| GET | `/health` | - | `{ status, mock:{network,simulate,chaos,recover,parse}, network:{source,version} }` |

**Network builder** ([backend/routers/network_builder.py](backend/routers/network_builder.py)). Every change bumps the
network `version`, rebuilds the graph, clears every graph-dependent cache (API responses incl. Redis keys, chaos scans,
Monte Carlo, forecasts) and saves to disk, under a lock. Mutations return the new `version` and the manual network's
`validation`.

| Method | Path | Body / query | Response |
|---|---|---|---|
| GET | `/network/source` | - | `{ source:"preset"\|"csv"\|"manual", version, node_count, edge_count, runnable, manual_node_count, manual_edge_count, csv_loaded, note }` |
| PUT | `/network/source` | `{ source }` | same as GET; 409 if `manual` has errors or no CSV was uploaded |
| GET | `/network/manual` | - | `{ source, version, nodes:[BuilderNode], edges:[BuilderEdge], validation }` |
| POST / PUT / DELETE | `/network/nodes`, `/network/nodes/{id}` | `BuilderNode` | `{ node, removed_edges, version, validation }` (DELETE also removes the node's lanes and lists them) |
| POST / PUT / DELETE | `/network/edges`, `/network/edges/{id}` | `BuilderEdge` | `{ edge, version, validation }` |
| POST | `/network/validate` | optional `{ nodes, edges }` draft | `{ errors:[{code,message,refs}], warnings:[...], runnable }` |
| POST | `/network/reset` | `?to=preset\|empty` | manual network; `preset` copies the preset into the builder and activates the preset |
| GET | `/network/export` | `?scope=manual\|active\|preset` | `{ format:"aegis-network", schema_version, source, version, nodes, edges }` |
| GET | `/network/export/csv` | `?file=nodes\|edges&scope=manual\|active` | `text/csv` in the `/upload` format |
| POST | `/network/import` | export JSON, `?activate=false` | manual network; 422 (nothing changes) on duplicate ids, unknown endpoints, self-loops, duplicate lanes |

`Node.risk` is `null` (with `risk_note`) when the network is too small or the model cannot score it; `Node.details`
carries the builder's extra fields; `Edge` may carry `id`, `mode`, `distance_km`. Demand events may target a retailer or
a customer. Engine endpoints answer **409** with a readable reason while the active CSV/manual network is not runnable
(for example when it is empty). Unexpected errors come back as JSON (`{"detail": "Internal error ..."}`), never a
stack trace.

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
| Ingest a company's own network data | CSV upload with validation and warnings, preview or activate; manual network builder with validation, undo/redo, JSON/CSV export | Data tab, `POST /upload`, `/network/*` | **Real** |
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
