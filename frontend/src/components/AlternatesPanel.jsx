import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  CheckCircle2,
  Clock,
  Coins,
  Factory,
  RefreshCw,
  Route,
  ShieldCheck,
  Sparkles,
  Truck,
} from 'lucide-react'
import { useStore } from '../store.js'
import { fmtNum, fmtPct, fmtSigned } from '../format.js'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  InlineError,
  Meter,
  SegmentedControl,
  SkeletonBlock,
  Table,
  Td,
  Th,
  Tr,
  cn,
  useToast,
} from './ui/index.js'
import { NodeTag } from './NodeTypeIcon.jsx'

const ACTION_LABEL = {
  'pre-position': 'Pre-position',
  transfer: 'Transfer',
  raise_safety_stock: 'Raise safety stock',
  hold: 'Hold (do not drain)',
}

function PathDisplay({ waypoints, nodes, isDisrupted = false }) {
  const list = waypoints && waypoints.length ? waypoints : (nodes || []).map((id) => ({ id, name: id }))

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {list.map((item, idx) => (
        <span key={`${item.id}-${idx}`} className="inline-flex items-center gap-1">
          {idx > 0 && (
            <ArrowRight
              className={cn('h-3.5 w-3.5', isDisrupted ? 'text-bad/50' : 'text-accent/60')}
              aria-hidden
            />
          )}
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium border transition-colors',
              isDisrupted
                ? 'border-bad/30 bg-bad/10 text-bad line-through decoration-bad/70'
                : 'border-ok/30 bg-ok/10 text-ok font-semibold'
            )}
          >
            <span className="font-mono">{item.id}</span>
            {item.city && <span className="opacity-75 font-normal">({item.city})</span>}
          </span>
        </span>
      ))}
    </div>
  )
}

export default function AlternatesPanel() {
  const { recover, alternates, loadAlternates, events, loading, errors, setEvents, runSimulation, setTab } =
    useStore()
  const toast = useToast()
  const [activeTab, setActiveTab] = useState('suppliers')

  useEffect(() => {
    if (!alternates && !recover && !loading.alternates) {
      loadAlternates(events)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const data = recover || alternates
  const suppliers = data?.alternate_suppliers ?? []
  const routes = data?.alternate_routes ?? []
  const inventory = recover?.inventory_actions ?? []
  const production = recover?.production_actions ?? []

  const tabOptions = [
    { value: 'suppliers', label: `Alternate Suppliers (${suppliers.length})`, icon: Truck },
    { value: 'routes', label: `Alternate Routes (${routes.length})`, icon: Route },
    ...(inventory.length || production.length
      ? [{ value: 'actions', label: `Inventory & Production Moves (${inventory.length + production.length})`, icon: Boxes }]
      : []),
  ]

  const handleSimulateSupplier = (s) => {
    // Add event switching to this alternate or simulating the disruption
    const ev = { type: 'node', target: s.replaces, start: 1, duration: 10, severity: 1.0 }
    setEvents([ev])
    runSimulation([ev])
    toast(`Simulating Alternate Supplier`, {
      description: `${s.name} (${s.supplier}) engaged to cover ${s.replaces} with ${fmtNum(s.spare_capacity)} units/day spare capacity.`,
    })
    setTab('simulate')
  }

  return (
    <Card className="overflow-hidden border-border/80 shadow-md">
      {/* Header */}
      <div className="border-b border-border bg-gradient-to-r from-surface to-surface-2 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-fg shadow-md shadow-accent/20">
              <Truck className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold tracking-tight text-fg">
                  Alternate Supplier & Route Recommendations
                </h2>
                <Badge tone="accent">Feature 2 (PS 04)</Badge>
                <Badge tone="ok" dot>
                  Optimization Engine Active
                </Badge>
              </div>
              <p className="mt-0.5 text-xs text-fg-muted">
                Multi-criteria supplier ranking (cost, lead time, spare cushion) and graph pathfinding bypassing blocked lanes & bottlenecks.
              </p>
            </div>
          </div>

          <Button
            variant="ghost"
            size="sm"
            icon={RefreshCw}
            disabled={loading.alternates}
            onClick={() => loadAlternates(events)}
          >
            {loading.alternates ? 'Re-ranking…' : 'Refresh Recommendations'}
          </Button>
        </div>

        {/* Tab Selector */}
        <div className="mt-4">
          <SegmentedControl
            size="sm"
            label="Recommendation Category"
            value={activeTab}
            onChange={setActiveTab}
            options={tabOptions}
            className="w-full sm:w-auto"
          />
        </div>
      </div>

      <CardBody className="p-5">
        <InlineError message={errors.alternates} onRetry={() => loadAlternates(events)} />
        {loading.alternates && !data && <SkeletonBlock lines={4} label="Calculating recommendations" />}

        {/* TAB 1: ALTERNATE SUPPLIERS */}
        {activeTab === 'suppliers' && (
          <div className="space-y-4">
            {suppliers.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-fg-muted">
                <Truck className="mx-auto h-8 w-8 text-fg-muted/40 mb-2" />
                No disrupted suppliers detected in the current scenario. Trigger a disruption in the Simulator to inspect ranked supplier alternatives.
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {suppliers.map((s, idx) => (
                  <div
                    key={`${s.replaces}-${s.supplier}-${idx}`}
                    className="flex flex-col justify-between rounded-xl border border-border bg-surface-2/40 p-4 transition-all hover:border-border-strong hover:bg-surface-2/70 shadow-sm"
                  >
                    <div>
                      {/* Card Top Pill Row */}
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5">
                          <Badge tone={idx === 0 ? 'accent' : 'neutral'} dot={idx === 0}>
                            Rank #{idx + 1} Recommendation
                          </Badge>
                          {s.is_backup && <Badge tone="warn">Contracted Backup</Badge>}
                        </div>
                        <span className="text-[11px] font-mono text-fg-muted">
                          Replaces <strong className="text-fg">{s.replaces}</strong>
                        </span>
                      </div>

                      {/* Supplier Identity */}
                      <div className="mt-3 flex items-start justify-between gap-2">
                        <div>
                          <h3 className="text-base font-semibold text-fg flex items-center gap-1.5">
                            {s.name}
                            <span className="text-xs font-normal text-fg-muted">({s.supplier})</span>
                          </h3>
                          <p className="text-xs text-fg-muted">{s.city || 'India Network'}</p>
                        </div>
                        <Badge tone={s.reliability >= 0.9 ? 'ok' : 'neutral'}>
                          <ShieldCheck className="h-3 w-3 mr-1 inline" />
                          {fmtPct(s.reliability)} Uptime
                        </Badge>
                      </div>

                      {/* Operational Metrics Grid */}
                      <div className="mt-4 grid grid-cols-3 gap-2 rounded-lg border border-border/60 bg-surface p-2.5 text-center text-xs">
                        <div>
                          <span className="text-fg-muted block text-[11px]">Spare Capacity</span>
                          <span className="font-semibold text-fg">{fmtNum(s.spare_capacity)}</span>
                          <span className="text-[10px] text-fg-muted block">u/day</span>
                        </div>
                        <div>
                          <span className="text-fg-muted block text-[11px]">Lead Time</span>
                          <span className="font-semibold text-fg flex items-center justify-center gap-0.5">
                            <Clock className="h-3 w-3 text-fg-muted" />
                            {s.lead}d
                          </span>
                          <span className="text-[10px] text-fg-muted block">fastest lane</span>
                        </div>
                        <div>
                          <span className="text-fg-muted block text-[11px]">Cost Premium</span>
                          <span
                            className={cn(
                              'font-semibold',
                              s.cost_premium_pct > 10 ? 'text-warn' : s.cost_premium_pct <= 0 ? 'text-ok' : 'text-fg'
                            )}
                          >
                            {fmtSigned(s.cost_premium_pct)}%
                          </span>
                          <span className="text-[10px] text-fg-muted block">vs original</span>
                        </div>
                      </div>

                      {/* AI Operational Rationale */}
                      {s.reason && (
                        <div className="mt-3 rounded-lg border border-accent/20 bg-accent/5 p-2.5 text-xs text-fg-2">
                          <span className="font-semibold text-accent flex items-center gap-1 mb-1">
                            <Sparkles className="h-3 w-3" />
                            Ranking Rationale:
                          </span>
                          <p className="leading-relaxed">{s.reason}</p>
                        </div>
                      )}
                    </div>

                    <div className="mt-4 pt-3 border-t border-border/60 flex items-center justify-between">
                      <span className="text-[11px] text-fg-muted">
                        Score: {s.score !== null ? s.score : '0.4×cost + 0.3×lead + 0.3×spare'}
                      </span>
                      <Button
                        variant="secondary"
                        size="sm"
                        iconRight={ArrowRight}
                        onClick={() => handleSimulateSupplier(s)}
                      >
                        Simulate with this Supplier
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: ALTERNATE ROUTES */}
        {activeTab === 'routes' && (
          <div className="space-y-4">
            {routes.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-fg-muted">
                <Route className="mx-auto h-8 w-8 text-fg-muted/40 mb-2" />
                No disrupted lanes or path bottlenecks detected. Throw a lane disruption (e.g. F1→W3) in the Simulator to inspect dynamic graph rerouting.
              </div>
            ) : (
              <div className="space-y-4">
                {routes.map((r, idx) => (
                  <div
                    key={`${r.destination}-${r.replaces}-${idx}`}
                    className="rounded-xl border border-border bg-surface-2/40 p-4 transition-all hover:border-border-strong shadow-sm"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
                      <div className="flex items-center gap-2">
                        <Badge tone="ok">
                          <CheckCircle2 className="h-3 w-3 mr-1 inline" />
                          Recommended Alternate Route #{idx + 1}
                        </Badge>
                        <span className="text-xs font-semibold text-fg">
                          Target: Demand Point <NodeTag id={r.destination} showName={false} />
                        </span>
                      </div>
                      <Badge tone="warn">
                        <AlertTriangle className="h-3 w-3 mr-1 inline" />
                        Bypasses Blocked Lane: {r.replaces}
                      </Badge>
                    </div>

                    {/* Path Comparison Visualization */}
                    <div className="mt-4 space-y-3">
                      {r.old_via && (
                        <div className="rounded-lg border border-border bg-surface/80 p-3">
                          <span className="text-[11px] font-semibold text-fg-muted uppercase tracking-wider block mb-1.5">
                            Original Baseline Route (Disrupted / Obstructed):
                          </span>
                          <PathDisplay
                            waypoints={r.old_waypoints}
                            nodes={r.old_via}
                            isDisrupted={true}
                          />
                        </div>
                      )}

                      <div className="rounded-lg border border-ok/30 bg-ok/5 p-3">
                        <span className="text-[11px] font-semibold text-ok uppercase tracking-wider block mb-1.5 flex items-center gap-1">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          AI Optimized Alternate Route (Verified Open Capacity):
                        </span>
                        <PathDisplay
                          waypoints={r.waypoints}
                          nodes={r.via}
                          isDisrupted={false}
                        />
                      </div>
                    </div>

                    {/* Operational Impact Metrics */}
                    <div className="mt-4 grid grid-cols-3 gap-3 rounded-lg border border-border/60 bg-surface p-3 text-center text-xs">
                      <div>
                        <span className="text-fg-muted block text-[11px]">Extra Transit Lead</span>
                        <span
                          className={cn(
                            'font-semibold text-sm',
                            r.extra_lead_days > 2 ? 'text-warn' : 'text-fg'
                          )}
                        >
                          {fmtSigned(r.extra_lead_days, 1)} days
                        </span>
                        <span className="text-[10px] text-fg-muted block">vs old route</span>
                      </div>
                      <div>
                        <span className="text-fg-muted block text-[11px]">Extra Freight Cost</span>
                        <span
                          className={cn(
                            'font-semibold text-sm',
                            r.extra_cost_per_unit > 20 ? 'text-warn' : 'text-fg'
                          )}
                        >
                          {fmtSigned(r.extra_cost_per_unit, 1, '₹')} / unit
                        </span>
                        <span className="text-[10px] text-fg-muted block">freight delta</span>
                      </div>
                      <div>
                        <span className="text-fg-muted block text-[11px]">Spare Route Capacity</span>
                        <span className="font-semibold text-sm text-ok">
                          {fmtNum(r.spare_capacity)} units/day
                        </span>
                        <span className="text-[10px] text-fg-muted block">bottleneck limit</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: INVENTORY & PRODUCTION MOVES */}
        {activeTab === 'actions' && (
          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold text-fg flex items-center gap-1.5 mb-3">
                <Boxes className="h-4 w-4 text-accent" />
                Inventory Buffers & Transfers ({inventory.length})
              </h3>
              {inventory.length === 0 ? (
                <p className="text-xs text-fg-muted">No inventory shifts necessary for this plan.</p>
              ) : (
                <Table label="Inventory actions">
                  <thead>
                    <tr>
                      <Th>Day</Th>
                      <Th>Action</Th>
                      <Th numeric>Units</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {inventory.map((a, i) => (
                      <Tr key={i}>
                        <Td className="tabular text-fg-muted">Day {a.day}</Td>
                        <Td>
                          <div className="font-medium text-fg">
                            {ACTION_LABEL[a.action] || a.action} at <NodeTag id={a.node} showName={false} />
                            {a.source && (
                              <span className="font-normal text-fg-muted ml-1">
                                from <NodeTag id={a.source} showName={false} />
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-fg-muted mt-0.5">{a.reason}</p>
                        </Td>
                        <Td numeric className="font-semibold">{fmtNum(a.units)}</Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </div>

            <div>
              <h3 className="text-sm font-semibold text-fg flex items-center gap-1.5 mb-3">
                <Factory className="h-4 w-4 text-accent" />
                Production Line Balancing ({production.length})
              </h3>
              {production.length === 0 ? (
                <p className="text-xs text-fg-muted">No plant shifts necessary for this plan.</p>
              ) : (
                <Table label="Production actions">
                  <thead>
                    <tr>
                      <Th>Day</Th>
                      <Th>Shift</Th>
                      <Th numeric>Units/day</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {production.map((p, i) => (
                      <Tr key={i}>
                        <Td className="tabular text-fg-muted">Day {p.start_day}</Td>
                        <Td>
                          <div className="font-medium text-fg">
                            <NodeTag id={p.from_factory} showName={false} /> → <NodeTag id={p.to_factory} showName={false} />
                            <span className="text-fg-muted font-normal text-xs ml-1">({p.duration}d)</span>
                          </div>
                          <p className="text-[11px] text-fg-muted mt-0.5">{p.reason}</p>
                        </Td>
                        <Td numeric className="font-semibold">{fmtNum(p.units_per_day)}</Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
