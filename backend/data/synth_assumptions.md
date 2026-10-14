# Synthetic data: assumptions

Everything in `core/synth/` is seeded and deterministic: the same arguments always produce the same network,
disruption and dataset. This file documents every modelling assumption. Code: `core/synth/profiles.py` (numbers),
`networks.py` (generator), `disruptions.py` (disruption library), `build.py` (dataset), `demos.py` (demo networks).

> The labels are produced by the AEGIS simulator, not observed in real supply chains. The surrogate trained on them
> is a fast approximation of the simulator, validated on held-out synthetic networks, not a model of real-world
> outcomes.

## 1. Network archetypes (10-60 nodes)

| archetype | structure | what it stresses |
|---|---|---|
| `linear` | each plant / DC / demand node has one upstream source (tree) | single points of failure everywhere |
| `multi_source` | demand <- 2 DCs, DC <- 2 plants, plant <- 3 suppliers | redundancy, rerouting |
| `hub_spoke` | every plant ships to 1-3 hubs; each demand node is served by one hub | hub failure |
| `two_region_port` | two regions; all plants export through one port DC that serves both regions, plus small regional DCs | shared port, regional correlation |
| `backup_supplier` | multi-sourced, plus 1-2 contracted backup suppliers (closed until triggered) | backup activation lag |
| `concentrated` | one dominant supplier ships to every plant and carries 70-85% of each plant's input | high HHI |
| `long_tail` | 40% of nodes are small suppliers, each tied to its nearest plant | many small, cheap-to-lose sources |

Tier shares per archetype are in `networks.TIER_SHARE`; every network has at least one supplier, plant, DC and
two demand nodes. Topology is geographic: a downstream node is fed by its nearest k upstream nodes and every upstream
node ships to at least its nearest downstream node (no orphans). Only lanes in `node_types.ALLOWED_EDGES` are used.

## 2. Industry profiles (`profiles.INDUSTRIES`)

| industry | price (INR) | margin | penalty / unmet unit | holding / unit-day | demand median / node-day (sigma) | demand CV | stock cover (days) | shelf life | lead x | modes | festival peak | monsoon |
|---|---:|---:|---:|---:|---|---:|---|---:|---|---|---:|---:|
| FMCG | 250 | 18% | 120 | 0.4 | 420 (0.55) | 0.25 | 3-12 | 180 d | 1.00-1.15 | road 80%, rail 20% | +35% | -10% |
| Pharma cold-chain | 1,800 | 35% | 5,000 | 6.0 | 60 (0.50) | 0.12 | 10-30 | 90 d | 1.10-1.40 | road 60%, air 30%, rail 10% | +5% | +10% |
| Electronics | 4,200 | 22% | 1,500 | 3.0 | 150 (0.50) | 0.30 | 5-20 | 720 d | 1.00-1.20 | road 60%, rail 15%, sea 15%, air 10% | +45% | -5% |
| Automotive | 9,000 | 15% | 3,500 | 5.0 | 40 (0.45) | 0.15 | 3-10 | 10 y | 1.00-1.10 | road 60%, rail 30%, sea 10% | +30% | -12% |
| Apparel | 900 | 45% | 300 | 0.8 | 200 (0.60) | 0.35 | 10-30 | 120 d | 1.00-1.20 | road 70%, sea 20%, rail 10% | +50% | -15% |
| Agri / perishables | 60 | 12% | 40 | 1.5 | 2,000 (0.60) | 0.30 | 3-6 | 7 d | 1.00-1.10 | road 90%, rail 10% | +20% | -25% |

Pharma lanes cost 30% more (reefer transport). Demand nodes are retailers for FMCG, apparel and agri, customers
(B2B distributors) otherwise.

## 3. Realism rules

* **Places**: 36 Indian cities with real coordinates and a region (north/south/east/west/central); sites are jittered
  +-0.12 degrees so co-located sites do not overlap. Port cities: Mumbai, Mundra, Kolkata, Visakhapatnam, Chennai,
  Kochi, Mangaluru.
* **Lead time** = `node_types.suggest_lead(mode, km)` (distance / mode speed + handling: road 450 km/d, rail 380,
  sea 350, air 4,000) x the industry lead multiplier, at least 1 day. Mode feasibility: rail >= 300 km, air >= 500 km,
  sea only between two port cities >= 300 km apart. Lead-time variability: lane `lead_cv` = mode CV (road 0.20,
  rail 0.25, sea 0.35, air 0.08) x U(0.8, 1.2). Freight cost and CO2 per unit come from `node_types.MODE_DEFAULTS`.
* **Capacities** are lognormal through demand: demand per node ~ LogNormal(ln median, sigma) x seasonal factor;
  site capacity = planned throughput / U(0.55, 0.85), so **baseline utilisation is 55-85%**. The planned split
  across suppliers is Dirichlet(2); after that, capacities are re-calibrated against the exact min-cost flow
  (`_calibrate_utilization`) so the solver's own routing also runs every used site inside the band. Sites the optimum
  leaves idle keep their planned (standby) capacity. Lanes: planned flow / U(0.50, 0.85); idle lanes 30-60% of their
  endpoints' capacity. Backup suppliers hold 15-30% of total demand.
* **Stock cover**: demand nodes U(industry cover range), always within 3-30 days of their demand; DCs 3-10 days of
  throughput; plants 1-3 days and suppliers 2-6 days of capacity (only demand-node stock buffers the simulator;
  upstream stock feeds the safety-stock recovery lever and the inventory detector).
* **Reliability** ~ U(0.85, 0.99) per site.
* **Seasonality**: each network is drawn in a random month; demand x (1 + festival peak x festival weight + monsoon
  dip x monsoon weight), festival weights Sep 0.35 / Oct 1.0 / Nov 0.8 / Dec 0.2 (Diwali), monsoon weights Jun 0.4 /
  Jul 1.0 / Aug 1.0 / Sep 0.6.
* **Demand noise and trend**: day-to-day noise is the profile's demand CV; demand spikes/drops in the disruption
  library carry the regional and volatility-scaled deviations. The forecast baseline used by demand spikes
  (`core.forecast`, Holt-Winters) adds weekly seasonality and trend.
* **Bullwhip**: order variability grows upstream. Each tier's `demand_cv` = the tier below x sqrt(1 + 2L/p + 2L^2/p^2)
  (Chen, Drezner, Ryan & Simchi-Levi 2000; p = 7-day moving-average forecast, L = mean lead time into the tier
  below), capped at 1.5. It feeds the feature set and the analyzer's bullwhip check.
* **Baseline check**: the undisrupted network must serve 100% of demand in the exact flow engine.

## 4. Disruption library (`disruptions.py`)

Start ~ U{0..10}, duration ~ LogNormal(ln median, 0.5) clipped to 1..30 days, severity from a beta distribution.

| type | what happens | median | severity |
|---|---|---:|---|
| supplier_outage | one primary supplier down | 12 d | 1.0 |
| supplier_partial | one supplier at reduced output | 14 d | 0.3 + 0.6 Beta(4,4) |
| factory_breakdown | one plant down or degraded | 8 d | 1.0 (60%) else 0.5-0.9 |
| warehouse_shutdown | one DC down or degraded | 6 d | 1.0 (70%) else 0.4-0.9 |
| route_blockage | one lane blocked | 5 d | 1.0 (70%) else 0.4-0.9 |
| port_closure | port-city sites + all sea lanes closed (a lane if there is no port) | 8 d | 1.0 |
| demand_spike | 1-3 demand nodes in one region | 10 d | 1.2 Beta(2,3) x sqrt(CV / 0.25) |
| demand_drop | every demand node of one region | 12 d | 0.7 Beta(2,5) |
| lead_time_inflation | 1-3 lanes slowed x U(1.3, 3.0) | 10 d | 0.4 Beta(2,8) capacity loss |
| quality_recall | long partial outage at a supplier or plant | 18 d | Beta(5,3) |
| strike | every plant and DC of one region | 6 d | 0.8 Beta(5,2) |
| weather_closure | regional storm: risk ~ Beta(5,2) +-0.1 per site/lane, mapped with the app's hazard impact table (`core.hazards.impact_mapping`) to capacity and lead-time factors | 4 d | from the table |
| compound | 2-3 of the above in one region, starts within 3 days | per part | per part |

Duration medians reflect that supplier and recall events usually run for weeks and lane or weather closures for days.

## 5. Dataset (`build.py`)

400 networks x 60 disruptions = 24,000 exact simulations (30-day horizon), balanced over archetypes and
industries, network size uniform in 10-60. Outcomes: unmet units and %, average and P90 extra delay, stock-out day,
recovery days, peak utilisation, revenue at risk. Splits are by network (train 60 / val 10 / calib 10 / test 20%),
so no test network is ever seen in training. `--fast` builds 42 networks x 20 cases of 10-20 nodes for tests.

## 6. Known limitations

* Lead times enter the simulator as delay, not as shipping lag; demand-node stock is not replenished within the horizon.
* Networks loaded into the app through the Manual Builder keep the standard INR 4,200 list price (the builder has no
  price field), so revenue figures for imported synthetic networks use that price.
* Probabilities (severity, duration, start) are plausible priors, not fitted to incident data.
