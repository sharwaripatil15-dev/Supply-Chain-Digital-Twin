# Data card: synthetic disruption outcomes

* File: `data/synth/dataset.parquet`, 24,000 rows x 84 columns, 400 networks, seed 42, built in 87 s.
* Labels: the AEGIS exact simulator (core.sim.simulate, 30-day horizon, daily min-cost flow, stock buffers, backup activation lag). They are **simulated outcomes, not real-world observations**.
* Generator: core.synth (assumptions in data/synth_assumptions.md). Features: core.features.SCENARIO_FEATURES.
* Split: grouped by network (no network in two splits).

| split | networks | rows |
|---|---:|---:|
| train | 240 | 14,400 |
| val | 40 | 2,400 |
| calib | 40 | 2,400 |
| test | 80 | 4,800 |

## Composition

| archetype | rows | | industry | rows | | disruption | rows |
|---|---:|---|---|---:|---|---|---:|
| backup_supplier | 3,420 | | agri | 3,780 | | compound | 1,895 |
| concentrated | 3,420 | | apparel | 3,780 | | demand_drop | 1,890 |
| hub_spoke | 3,420 | | automotive | 3,840 | | demand_spike | 1,808 |
| linear | 3,480 | | electronics | 4,200 | | factory_breakdown | 1,816 |
| long_tail | 3,420 | | fmcg | 4,200 | | lead_time_inflation | 1,927 |
| multi_source | 3,420 | | pharma | 4,200 | | port_closure | 1,689 |
| two_region_port | 3,420 | |  |  | | quality_recall | 1,885 |
|  |  | |  |  | | route_blockage | 1,975 |
|  |  | |  |  | | strike | 1,823 |
|  |  | |  |  | | supplier_outage | 1,913 |
|  |  | |  |  | | supplier_partial | 1,844 |
|  |  | |  |  | | warehouse_shutdown | 1,815 |
|  |  | |  |  | | weather_closure | 1,720 |

## Labels

| outcome | mean | P10 | P50 | P90 | max | share > 0 |
|---|---:|---:|---:|---:|---:|---:|
| unmet_units | 2376.28 | 0.00 | 0.00 | 1109.20 | 745009.00 | 18% |
| unmet_pct | 0.54 | 0.00 | 0.00 | 0.85 | 57.26 | 18% |
| avg_delay | 0.20 | 0.00 | 0.03 | 0.51 | 15.68 | 64% |
| p90_delay | 0.48 | 0.00 | 0.04 | 1.43 | 18.05 | 60% |
| stockout_day | 26.55 | 11.00 | 30.00 | 30.00 | 30.00 | 100% |
| recovery_days | 2.18 | 0.00 | 0.00 | 10.00 | 30.00 | 18% |
| peak_util | 0.90 | 0.83 | 0.87 | 1.00 | 1.00 | 100% |
| revenue_at_risk | 647316.18 | 0.00 | 0.00 | 873060.00 | 211516200.00 | 18% |

Network size: 10-60 nodes. Exact simulator: 26 ms per case on average (P90 40 ms).
