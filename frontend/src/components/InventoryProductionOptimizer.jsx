import { useEffect, useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  ArrowRight,
  Boxes,
  CheckCircle2,
  Clock,
  Coins,
  Cpu,
  Factory,
  Flame,
  Layers,
  Play,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { useStore } from '../store.js'
import { fmtNum, fmtPct } from '../format.js'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  InlineError,
  Meter,
  SkeletonBlock,
  Table,
  Td,
  Th,
  Tr,
  cn,
  useToast,
} from './ui/index.js'
import { NodeTag } from './NodeTypeIcon.jsx'

const LEVER_OPTIONS = [
  {
    id: 'safety_stock',
    label: 'Safety Stock Buffers',
    description: 'Pre-position finished goods at distribution centers before disruption',
    icon: Boxes,
  },
  {
    id: 'production_shift',
    label: 'Production Shift Balancing',
    description: 'Reallocate assembly lines between plants (up to 25% quota transfer)',
    icon: Factory,
  },
  {
    id: 'overtime',
    label: 'Overtime Capacity Bursts',
    description: 'Authorize up to +30% overtime surge at operational manufacturing plants',
    icon: Clock,
  },
  {
    id: 'reroute',
    label: 'Dynamic Lane Rerouting',
    description: 'Allow flows to use remaining capacity on all working transportation lanes',
    icon: Layers,
  },
  {
    id: 'backup',
    label: 'Contracted Backup Facility',
    description: 'Trigger emergency backup contract (fixed fee, activates after lead lag)',
    icon: ShieldCheck,
  },
]

export default function InventoryProductionOptimizer() {
  const { optimizedPlan, runOptimizePlan, events, loading, errors } = useStore()
  const toast = useToast()

  const [selectedLevers, setSelectedLevers] = useState([
    'safety_stock',
    'production_shift',
    'overtime',
    'reroute',
  ])

  useEffect(() => {
    if (!optimizedPlan && !loading.optimize) {
      runOptimizePlan(events, selectedLevers)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleToggleLever = (id) => {
    setSelectedLevers((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    )
  }

  const handleRunOptimization = async () => {
    const res = await runOptimizePlan(events, selectedLevers)
    if (res) {
      toast('Inventory & Production Optimization Solved', {
        description: `Plan status: ${res.status} · Net Savings: ₹${fmtNum(
          res.financial_summary?.net_savings || 0
        )}`,
      })
    }
  }

  const fin = optimizedPlan?.financial_summary
  const trajectory = optimizedPlan?.daily_inventory_trajectory || []
  const plants = optimizedPlan?.plant_allocations || []
  const invActions = optimizedPlan?.inventory_actions || []
  const prodActions = optimizedPlan?.production_actions || []

  return (
    <Card className="overflow-hidden border-border/80 shadow-md">
      {/* Header */}
      <div className="border-b border-border bg-gradient-to-r from-surface to-surface-2 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-fg shadow-md shadow-accent/20">
              <SlidersHorizontal className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold tracking-tight text-fg">
                  Inventory & Production Plan Optimization
                </h2>
                <Badge tone="accent">Feature 3 (PS 04)</Badge>
                <Badge tone="ok" dot>
                  MILP Linear Solver
                </Badge>
              </div>
              <p className="mt-0.5 text-xs text-fg-muted">
                Multi-period linear programming optimization for warehouse safety stock staging, assembly line balancing, and overtime surges.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              icon={Play}
              disabled={loading.optimize || selectedLevers.length === 0}
              onClick={handleRunOptimization}
              className="shadow-sm font-semibold"
            >
              {loading.optimize ? 'Solving Linear Program…' : 'Optimize Plan'}
            </Button>
          </div>
        </div>
      </div>

      <CardBody className="space-y-6 p-5">
        <InlineError message={errors.optimize} onRetry={handleRunOptimization} />

        {/* SECTION 1: INTERACTIVE OPTIMIZATION LEVERS SELECTOR */}
        <div className="rounded-xl border border-border bg-surface-2/40 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-accent" />
              <span className="text-xs font-semibold text-fg">Active Decision Levers (Customize & Re-solve):</span>
            </div>
            <span className="text-[11px] text-fg-muted">
              {selectedLevers.length} of {LEVER_OPTIONS.length} levers active
            </span>
          </div>

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {LEVER_OPTIONS.map((opt) => {
              const active = selectedLevers.includes(opt.id)
              const Icon = opt.icon
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => handleToggleLever(opt.id)}
                  className={cn(
                    'flex items-start gap-2.5 rounded-lg border p-2.5 text-left transition-all',
                    active
                      ? 'border-accent bg-accent/10 shadow-sm ring-1 ring-accent/30'
                      : 'border-border bg-surface hover:border-border-strong hover:bg-surface-2 opacity-75'
                  )}
                >
                  <div
                    className={cn(
                      'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs font-semibold',
                      active ? 'bg-accent text-accent-fg' : 'bg-surface-3 text-fg-muted'
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold text-fg">{opt.label}</span>
                      {active && <CheckCircle2 className="h-3 w-3 text-accent" />}
                    </div>
                    <p className="mt-0.5 text-[11px] text-fg-muted leading-tight line-clamp-2">
                      {opt.description}
                    </p>
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* SECTION 2: FINANCIAL & RESILIENCY IMPACT SUMMARY */}
        {fin && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-border bg-surface p-3.5 shadow-sm">
              <span className="text-xs text-fg-muted font-medium block">Customer Units Protected</span>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-xl font-bold text-fg">{fmtNum(fin.units_saved)}</span>
                <span className="text-xs font-semibold text-ok">
                  +{fin.unmet_reduction_pct}% fulfillment
                </span>
              </div>
              <span className="mt-1 text-[11px] text-fg-muted block">Shortage prevented by optimization</span>
            </div>

            <div className="rounded-xl border border-border bg-surface p-3.5 shadow-sm">
              <span className="text-xs text-fg-muted font-medium block">Net Financial Savings</span>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-xl font-bold text-ok">₹{fmtNum(fin.net_savings)}</span>
                <span className="text-xs text-fg-muted">saved</span>
              </div>
              <span className="mt-1 text-[11px] text-fg-muted block">Against inaction stockout penalties</span>
            </div>

            <div className="rounded-xl border border-border bg-surface p-3.5 shadow-sm">
              <span className="text-xs text-fg-muted font-medium block">Optimization Fix Cost</span>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-xl font-bold text-fg">₹{fmtNum(fin.fix_cost)}</span>
                <span className="text-xs text-fg-muted">operating cost</span>
              </div>
              <span className="mt-1 text-[11px] text-fg-muted block">Holding, transfers, overtime premiums</span>
            </div>

            <div className="rounded-xl border border-border bg-surface p-3.5 shadow-sm">
              <span className="text-xs text-fg-muted font-medium block">Intervention ROI Multiple</span>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-xl font-bold text-accent">{fin.roi_multiple}×</span>
                <span className="text-xs text-ok font-semibold">Payback</span>
              </div>
              <span className="mt-1 text-[11px] text-fg-muted block">Return on each Rupee invested</span>
            </div>
          </div>
        )}

        {/* SECTION 3: 30-DAY INVENTORY CUSHION & STOCK TRAJECTORY CHART */}
        {trajectory.length > 0 && (
          <div className="rounded-xl border border-border bg-surface p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold text-fg flex items-center gap-1.5">
                  <Boxes className="h-4 w-4 text-accent" />
                  Multi-Period Inventory Cushion & Stock Trajectory (30-Day Horizon)
                </h3>
                <p className="text-xs text-fg-muted">
                  Warehouse stock staging, factory finished goods, safety buffers, and unmet demand gaps day by day.
                </p>
              </div>
              <div className="flex items-center gap-3 text-xs text-fg-muted">
                <span className="inline-flex items-center gap-1">
                  <span className="h-2.5 w-2.5 rounded-full bg-accent" /> Warehouse Stock
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="h-2.5 w-2.5 rounded-full bg-ok" /> Safety Buffer
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="h-2.5 w-2.5 rounded-full bg-bad" /> Unmet Gap
                </span>
              </div>
            </div>

            <div className="h-64 w-full pt-2">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trajectory} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="whGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--color-accent, #6366f1)" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="var(--color-accent, #6366f1)" stopOpacity={0.0} />
                    </linearGradient>
                    <linearGradient id="bufferGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--color-ok, #10b981)" stopOpacity={0.45} />
                      <stop offset="95%" stopColor="var(--color-ok, #10b981)" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis
                    dataKey="day"
                    tickFormatter={(d) => `D${d}`}
                    fontSize={11}
                    tickLine={false}
                    axisLine={{ opacity: 0.2 }}
                  />
                  <YAxis fontSize={11} tickLine={false} axisLine={{ opacity: 0.2 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-surface, #1e293b)',
                      borderColor: 'var(--color-border, #334155)',
                      borderRadius: '0.75rem',
                      fontSize: '12px',
                    }}
                    formatter={(val, name) => [`${fmtNum(val)} units`, name]}
                    labelFormatter={(d) => `Day ${d}`}
                  />
                  <Area
                    type="monotone"
                    dataKey="warehouse_stock"
                    name="Warehouse Stock"
                    stroke="var(--color-accent, #6366f1)"
                    fillOpacity={1}
                    fill="url(#whGrad)"
                    strokeWidth={2}
                  />
                  <Area
                    type="monotone"
                    dataKey="safety_buffer"
                    name="Safety Buffer Staged"
                    stroke="var(--color-ok, #10b981)"
                    fillOpacity={1}
                    fill="url(#bufferGrad)"
                    strokeWidth={2}
                  />
                  <Line
                    type="monotone"
                    dataKey="unmet_demand"
                    name="Unmet Demand"
                    stroke="var(--color-bad, #ef4444)"
                    strokeWidth={2}
                    dot={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* SECTION 4: PLANT PRODUCTION BALANCING MATRIX */}
        {plants.length > 0 && (
          <div>
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-fg flex items-center gap-1.5">
                  <Factory className="h-4 w-4 text-accent" />
                  Cross-Plant Production Line Balancing Matrix
                </h3>
                <p className="text-xs text-fg-muted">
                  Baseline quota vs. disruption impact vs. overtime surge vs. inter-facility shift transfers.
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {plants.map((p) => {
                const isOverUtilized = p.utilization_pct > 100
                const isDisrupted = p.disrupted_capacity < p.baseline_capacity
                return (
                  <div
                    key={p.factory_id}
                    className="flex flex-col justify-between rounded-xl border border-border bg-surface p-4 shadow-sm"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5">
                          <NodeTag id={p.factory_id} showName={false} />
                          <span className="font-semibold text-sm text-fg">{p.name}</span>
                        </div>
                        <span className="text-xs text-fg-muted">{p.city}</span>
                      </div>

                      <div className="mt-3 space-y-1.5 text-xs">
                        <div className="flex justify-between text-fg-muted">
                          <span>Baseline Capacity:</span>
                          <span className="font-mono text-fg">{fmtNum(p.baseline_capacity)} u/d</span>
                        </div>

                        {isDisrupted && (
                          <div className="flex justify-between text-bad">
                            <span>Disrupted Capacity:</span>
                            <span className="font-mono font-semibold">
                              {fmtNum(p.disrupted_capacity)} u/d
                            </span>
                          </div>
                        )}

                        {p.overtime_units > 0 && (
                          <div className="flex justify-between text-accent">
                            <span>Overtime Burst (+30%):</span>
                            <span className="font-mono font-semibold">
                              +{fmtNum(p.overtime_units)} u/d
                            </span>
                          </div>
                        )}

                        {p.shifted_in > 0 && (
                          <div className="flex justify-between text-ok">
                            <span>Production Shift Received:</span>
                            <span className="font-mono font-semibold">
                              +{fmtNum(p.shifted_in)} u/d
                            </span>
                          </div>
                        )}

                        {p.shifted_out > 0 && (
                          <div className="flex justify-between text-warn">
                            <span>Production Shift Transferred:</span>
                            <span className="font-mono font-semibold">
                              -{fmtNum(p.shifted_out)} u/d
                            </span>
                          </div>
                        )}

                        <div className="border-t border-border/60 pt-2 flex justify-between font-semibold text-fg">
                          <span>Net Production Output:</span>
                          <span className="font-mono text-accent">
                            {fmtNum(p.net_output)} u/d
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 pt-2">
                      <div className="mb-1 flex justify-between text-[11px] text-fg-muted">
                        <span>Plant Capacity Utilization</span>
                        <span
                          className={cn(
                            'font-semibold',
                            isOverUtilized ? 'text-warn' : 'text-fg'
                          )}
                        >
                          {p.utilization_pct}%
                        </span>
                      </div>
                      <Meter
                        value={p.utilization_pct}
                        max={130}
                        label={`${p.name} utilization`}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* SECTION 5: ACTIONABLE INVENTORY & PRODUCTION TIMETABLE */}
        {(invActions.length > 0 || prodActions.length > 0) && (
          <div className="grid gap-4 md:grid-cols-2">
            {/* Inventory Action Directives */}
            <div className="rounded-xl border border-border bg-surface p-4">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-fg-muted mb-3 flex items-center gap-1.5">
                <Boxes className="h-4 w-4 text-accent" />
                Pre-Positioning Inventory Directives ({invActions.length})
              </h4>
              {invActions.length === 0 ? (
                <p className="text-xs text-fg-muted">No buffer pre-positioning needed.</p>
              ) : (
                <div className="space-y-2">
                  {invActions.map((act, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-border/60 bg-surface-2/40 p-2.5 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2 font-medium text-fg">
                        <span className="flex items-center gap-1">
                          Stage at <NodeTag id={act.node} showName={false} />
                          {act.source && (
                            <span className="font-normal text-fg-muted">
                              (from <NodeTag id={act.source} showName={false} />)
                            </span>
                          )}
                        </span>
                        <Badge tone="ok">{fmtNum(act.units)} units</Badge>
                      </div>
                      <p className="mt-1 text-[11px] text-fg-muted leading-relaxed">{act.reason}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Production Line Shift Directives */}
            <div className="rounded-xl border border-border bg-surface p-4">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-fg-muted mb-3 flex items-center gap-1.5">
                <Factory className="h-4 w-4 text-accent" />
                Assembly Line Reallocation Directives ({prodActions.length})
              </h4>
              {prodActions.length === 0 ? (
                <p className="text-xs text-fg-muted">No inter-plant line shifts needed.</p>
              ) : (
                <div className="space-y-2">
                  {prodActions.map((act, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-border/60 bg-surface-2/40 p-2.5 text-xs"
                    >
                      <div className="flex items-center justify-between gap-2 font-medium text-fg">
                        <span className="flex items-center gap-1">
                          <NodeTag id={act.from_factory} showName={false} /> →{' '}
                          <NodeTag id={act.to_factory} showName={false} />
                          <span className="font-normal text-fg-muted ml-1">
                            ({act.duration} days from Day {act.start_day})
                          </span>
                        </span>
                        <Badge tone="accent">{fmtNum(act.units_per_day)} u/d</Badge>
                      </div>
                      <p className="mt-1 text-[11px] text-fg-muted leading-relaxed">{act.reason}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
