# Data card: synthetic disruption outcomes (fast)

* File: `data/synth/dataset_fast.parquet`, 840 rows x 84 columns, 42 networks, seed 42, built in 7 s.
* Labels: the AEGIS exact simulator (core.sim.simulate, 30-day horizon, daily min-cost flow, stock buffers, backup activation lag). They are **simulated outcomes, not real-world observations**.
* Generator: core.synth (assumptions in data/synth_assumptions.md). Features: core.features.SCENARIO_FEATURES.
* Split: grouped by network (no network in two splits).

| split | networks | rows |
|---|---:|---:|
| train | 25 | 500 |
| val | 4 | 80 |
| calib | 4 | 80 |
| test | 9 | 180 |

## Composition

| archetype | rows | | industry | rows | | disruption | rows |
|---|---:|---|---|---:|---|---|---:|
| backup_supplier | 120 | | agri | 140 | | compound | 63 |
| concentrated | 120 | | apparel | 140 | | demand_drop | 68 |
| hub_spoke | 120 | | automotive | 140 | | demand_spike | 64 |
| linear | 120 | | electronics | 140 | | factory_breakdown | 47 |
| long_tail | 120 | | fmcg | 140 | | lead_time_inflation | 62 |
| multi_source | 120 | | pharma | 140 | | port_closure | 57 |
| two_region_port | 120 | |  |  | | quality_recall | 61 |
|  |  | |  |  | | route_blockage | 69 |
|  |  | |  |  | | strike | 65 |
|  |  | |  |  | | supplier_outage | 73 |
|  |  | |  |  | | supplier_partial | 67 |
|  |  | |  |  | | warehouse_shutdown | 69 |
|  |  | |  |  | | weather_closure | 75 |

## Labels

| outcome | mean | P10 | P50 | P90 | max | share > 0 |
|---|---:|---:|---:|---:|---:|---:|
| unmet_units | 2394.29 | 0.00 | 0.00 | 2037.00 | 272803.00 | 22% |
| unmet_pct | 1.25 | 0.00 | 0.00 | 4.08 | 53.27 | 22% |
| avg_delay | 0.38 | 0.00 | 0.06 | 1.03 | 16.09 | 63% |
| p90_delay | 0.76 | 0.00 | 0.09 | 2.44 | 16.09 | 61% |
| stockout_day | 25.81 | 10.00 | 30.00 | 30.00 | 30.00 | 100% |
| recovery_days | 2.83 | 0.00 | 0.00 | 13.00 | 28.00 | 22% |
| peak_util | 0.88 | 0.80 | 0.85 | 1.00 | 1.00 | 100% |
| revenue_at_risk | 782993.29 | 0.00 | 0.00 | 1730070.00 | 31802400.00 | 22% |

Network size: 10-20 nodes. Exact simulator: 15 ms per case on average (P90 20 ms).
