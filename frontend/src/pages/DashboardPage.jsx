import { useEffect } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  CheckCircle2,
  Clock,
  Coins,
  Factory,
  Flame,
  LayoutDashboard,
  LifeBuoy,
  Play,
  RefreshCw,
  Route,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Truck,
  Zap,
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
  PageHeader,
  SkeletonBlock,
  Table,
  Td,
  Th,
  Tr,
  cn,
  useToast,
} from '../components/ui/index.js'
import { NodeTag } from '../components/NodeTypeIcon.jsx'

export default function DashboardPage() {
  const { dashboardSummary, loadDashboardSummary, events, loading, errors, setTab } = useStore()
  const toast = useToast()

  useEffect(() => {
    if (!dashboardSummary && !loading.dashboard) {
      loadDashboardSummary(events)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleRefresh = async () => {
    const res = await loadDashboardSummary(events)
    if (res) {
      toast('Dashboard metrics updated', {
        description: `Refreshed real-time disruption status and recovery strategies.`,
      })
    }
  }

  const dis = dashboardSummary?.disruptions
  const imp = dashboardSummary?.impacts
  const rec = dashboardSummary?.recovery
  const regionalData = imp?.regional_impacts || []
  const strategies = rec?.strategies || []

  return (
    <>
      <PageHeader
        title="Disruptions & Recovery Executive Dashboard"
        description="Unified command center: track real-time disruptions, evaluate financial & operational losses, and compare verified recovery strategies."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              icon={RefreshCw}
              disabled={loading.dashboard}
              onClick={handleRefresh}
            >
              {loading.dashboard ? 'Refreshing…' : 'Refresh Metrics'}
            </Button>
            <Button
              variant="secondary"
              iconRight={ArrowRight}
              onClick={() => setTab('simulate')}
            >
              Open Simulator
            </Button>
            <Button
              variant="primary"
              iconRight={ArrowRight}
              onClick={() => setTab('recover')}
            >
              Deploy Recovery Plan
            </Button>
          </div>
        }
      />

      <div className="space-y-6">
        <InlineError message={errors.dashboard} onRetry={handleRefresh} />

        {loading.dashboard && !dashboardSummary && (
          <SkeletonBlock lines={8} label="Loading executive dashboard metrics" />
        )}

        {/* SECTION 1: EXECUTIVE KPI TRIAD CARDS */}
        {dashboardSummary && (
          <div className="grid gap-4 md:grid-cols-3">
            {/* KPI 1: DISRUPTIONS EXPOSURE */}
            <Card className="border-bad/30 bg-gradient-to-b from-surface to-bad/5 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-bad flex items-center gap-1.5 uppercase tracking-wider">
                  <ShieldAlert className="h-4 w-4" />
                  Active Disruptions Exposure
                </span>
                <Badge tone="bad">{dis?.active_events_count || 0} Events Active</Badge>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-fg">
                  {(dis?.affected_nodes?.length || 0) + (dis?.affected_lanes?.length || 0)}
                </span>
                <span className="text-xs text-fg-muted font-medium">sites & lanes affected</span>
              </div>
              <div className="mt-3 flex items-center justify-between text-xs border-t border-border/60 pt-2 text-fg-2">
                <span>Affected Sites: <strong className="text-fg">{dis?.affected_nodes?.join(', ') || 'None'}</strong></span>
                <span>Corridors: <strong className="text-fg">{dis?.affected_lanes?.length || 0} blocked</strong></span>
              </div>
            </Card>

            {/* KPI 2: OPERATIONAL & FINANCIAL IMPACT */}
            <Card className="border-warn/30 bg-gradient-to-b from-surface to-warn/5 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-warn flex items-center gap-1.5 uppercase tracking-wider">
                  <Flame className="h-4 w-4" />
                  Demand Shortage & Inaction Loss
                </span>
                <Badge tone="warn">Survival Clock: {imp?.survival_clock_days ?? 0}d</Badge>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-warn">
                  ₹{fmtNum(imp?.inaction_loss_inr || 0)}
                </span>
                <span className="text-xs text-fg-muted font-medium">inaction cost</span>
              </div>
              <div className="mt-3 flex items-center justify-between text-xs border-t border-border/60 pt-2 text-fg-2">
                <span>Unmet Demand: <strong className="text-bad">{fmtNum(imp?.total_unmet_units || 0)} u</strong></span>
                <span>Fulfillment: <strong className="text-fg">{imp?.fulfillment_rate_pct || 0}%</strong></span>
              </div>
            </Card>

            {/* KPI 3: STRATEGIC RECOVERY PAYBACK */}
            <Card className="border-ok/30 bg-gradient-to-b from-surface to-ok/5 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-ok flex items-center gap-1.5 uppercase tracking-wider">
                  <ShieldCheck className="h-4 w-4" />
                  Recovery Strategy Payback
                </span>
                <Badge tone="ok">{rec?.recommended_strategy || 'Full plan'}</Badge>
              </div>
              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-ok">
                  ₹{fmtNum(rec?.net_savings || 0)}
                </span>
                <span className="text-xs text-ok font-semibold">net savings</span>
              </div>
              <div className="mt-3 flex items-center justify-between text-xs border-t border-border/60 pt-2 text-fg-2">
                <span>Intervention Cost: <strong className="text-fg">₹{fmtNum(rec?.fix_cost || 0)}</strong></span>
                <span>ROI Multiple: <strong className="text-ok font-bold">{rec?.roi_multiple || 0}×</strong></span>
              </div>
            </Card>
          </div>
        )}

        {/* SECTION 2: DISRUPTION THREAT LANDSCAPE VISUALIZER */}
        <Card className="overflow-hidden border-border/80 shadow-sm">
          <CardHeader
            title="Disruption Threat Landscape"
            description="Active disruption events and impact on physical supply chain nodes and transportation corridors."
            icon={AlertTriangle}
          />
          <CardBody className="p-5">
            {!dis?.disruptions?.length ? (
              <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-fg-muted">
                No disruptions currently configured. Open the Simulator to stage a scenario.
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {dis.disruptions.map((item, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col justify-between rounded-xl border border-bad/20 bg-bad/5 p-3.5 shadow-sm"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2">
                        <Badge tone="bad">
                          {item.type.toUpperCase()}: {item.target}
                        </Badge>
                        <span className="text-xs font-mono text-fg-muted">
                          Day {item.start} · {item.duration}d duration
                        </span>
                      </div>
                      <h4 className="mt-2 text-sm font-semibold text-fg">{item.target_name}</h4>
                      <p className="mt-1 text-xs text-fg-2 leading-relaxed">{item.description}</p>
                    </div>

                    <div className="mt-3 pt-2.5 border-t border-border/60 flex items-center justify-between text-xs">
                      <span className="text-fg-muted">Severity Impact:</span>
                      <span className="font-bold text-bad">{Math.round(item.severity * 100)}% Capacity Loss</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>

        {/* SECTION 3: IMPACT ANALYTICS (REGIONAL DEMAND SHORTAGE & DELAYS) */}
        {regionalData.length > 0 && (
          <div className="grid gap-6 lg:grid-cols-12">
            <Card className="lg:col-span-8 overflow-hidden border-border/80 shadow-sm">
              <CardHeader
                title="Customer Demand Fulfillment & Regional Shortages"
                description="30-day baseline demand quota vs unfulfilled customer shortages across metropolitan retail zones."
                icon={TrendingDown}
              />
              <CardBody className="p-5">
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={regionalData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                      <XAxis dataKey="name" fontSize={11} tickLine={false} axisLine={{ opacity: 0.2 }} />
                      <YAxis fontSize={11} tickLine={false} axisLine={{ opacity: 0.2 }} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'var(--color-surface, #1e293b)',
                          borderColor: 'var(--color-border, #334155)',
                          borderRadius: '0.75rem',
                          fontSize: '12px',
                        }}
                        formatter={(val, name) => [`${fmtNum(val)} units`, name]}
                      />
                      <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                      <Bar dataKey="baseline_demand" name="Baseline Demand (u)" fill="var(--color-accent, #6366f1)" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="unmet_units" name="Unfulfilled Shortage (u)" fill="var(--color-bad, #ef4444)" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardBody>
            </Card>

            <Card className="lg:col-span-4 overflow-hidden border-border/80 shadow-sm">
              <CardHeader
                title="Regional Vulnerability"
                description="Customer fulfillment rate and delivery delay."
                icon={Clock}
              />
              <CardBody className="p-4 space-y-3">
                {regionalData.map((reg) => (
                  <div
                    key={reg.customer_id}
                    className="rounded-lg border border-border/70 bg-surface-2/40 p-2.5 text-xs"
                  >
                    <div className="flex items-center justify-between font-semibold text-fg">
                      <span>{reg.name} ({reg.city})</span>
                      <span className={cn(reg.fulfillment_pct < 80 ? 'text-bad' : 'text-ok')}>
                        {reg.fulfillment_pct}% fulfillment
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-fg-muted text-[11px]">
                      <span>Shortage: {fmtNum(reg.unmet_units)} units</span>
                      <span>Delay: +{reg.extra_lead_days}d transit</span>
                    </div>
                  </div>
                ))}
              </CardBody>
            </Card>
          </div>
        )}

        {/* SECTION 4: RECOVERY STRATEGIES COMPARISON & ROI MATRIX */}
        <Card className="overflow-hidden border-border/80 shadow-sm">
          <CardHeader
            title="Recovery Strategies Comparison & ROI Matrix"
            description="Side-by-side evaluation of all 7 recovery strategies re-stress-tested by the MILP solver."
            icon={Zap}
            actions={<Badge tone="ok">Recommended: {rec?.recommended_strategy}</Badge>}
          />
          <CardBody className="p-0">
            <Table label="Recovery strategies comparison">
              <thead>
                <tr>
                  <Th>Strategy</Th>
                  <Th numeric>Intervention Cost</Th>
                  <Th numeric>Unmet Demand</Th>
                  <Th numeric>Avg Delay</Th>
                  <Th numeric>Recovery Time</Th>
                  <Th numeric>CO2 Emissions</Th>
                  <Th>Safety Check</Th>
                </tr>
              </thead>
              <tbody>
                {strategies.map((st) => {
                  const isRec = st.recommended
                  return (
                    <Tr
                      key={st.name}
                      className={cn(
                        isRec && 'bg-accent/5 font-semibold text-fg border-l-4 border-l-accent'
                      )}
                    >
                      <Td>
                        <div className="flex items-center gap-2">
                          <span className={cn('text-sm', isRec ? 'text-accent font-bold' : 'text-fg')}>
                            {st.name}
                          </span>
                          {isRec && (
                            <Badge tone="accent" dot>
                              AI Recommended
                            </Badge>
                          )}
                        </div>
                      </Td>
                      <Td numeric className="font-mono">₹{fmtNum(st.cost)}</Td>
                      <Td numeric className="font-mono text-bad">{fmtNum(st.unmet)} u</Td>
                      <Td numeric className="font-mono">{st.delay_avg_days?.toFixed(1)} d</Td>
                      <Td numeric className="font-mono">{st.recovery_days} days</Td>
                      <Td numeric className="font-mono">{st.co2} t</Td>
                      <Td>
                        {st.safety_check?.passed ? (
                          <Badge tone="ok">Passed</Badge>
                        ) : (
                          <Badge tone="bad">New SPOF Risk</Badge>
                        )}
                      </Td>
                    </Tr>
                  )
                })}
              </tbody>
            </Table>
          </CardBody>
        </Card>

        {/* SECTION 5: EXECUTIVE DIRECTIVES & PLAYBOOK */}
        {rec?.playbook_highlights && rec.playbook_highlights.length > 0 && (
          <Card className="border-accent/30 bg-gradient-to-r from-accent/5 via-surface to-surface-2 p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="h-5 w-5 text-accent" />
              <h3 className="text-base font-bold text-fg">Executive Action Directives (Playbook)</h3>
            </div>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {rec.playbook_highlights.map((item, idx) => (
                <div
                  key={idx}
                  className="rounded-xl border border-border/70 bg-surface p-3 text-xs leading-relaxed text-fg-2 shadow-xs"
                >
                  <span className="font-semibold text-accent block mb-1">Directive #{idx + 1}:</span>
                  {item}
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </>
  )
}
