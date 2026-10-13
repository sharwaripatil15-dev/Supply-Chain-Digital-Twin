import { useEffect, useState } from 'react'
import {
  Sparkles,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  BrainCircuit,
  ArrowRight,
  RefreshCw,
  Activity,
  Layers,
  Sliders,
  ChevronRight,
  Flame,
} from 'lucide-react'
import { useStore } from '../store.js'
import { fmtPct, fmtNum } from '../format.js'
import { NodeTag } from './NodeTypeIcon.jsx'
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
  cn,
} from './ui/index.js'

export default function AiAdvisoryPanel() {
  const { advisory, loading, errors, loadAdvisory, setEvents, runSimulation, setTab, selectNode } = useStore()
  const [activeTab, setActiveTab] = useState('recommendations')

  useEffect(() => {
    if (!advisory && !loading.advisory) {
      loadAdvisory()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSimulate = (event) => {
    if (!event) return
    setEvents([event])
    runSimulation([event])
    setTab('simulate')
  }

  const summary = advisory?.summary
  const recs = advisory?.recommendations || []
  const bottlenecks = advisory?.bottlenecks || []

  const tabOptions = [
    { value: 'recommendations', label: `Strategic Recommendations (${recs.length})`, icon: Sparkles },
    { value: 'bottlenecks', label: `ML Bottlenecks & SPOFs (${bottlenecks.length})`, icon: Activity },
  ]

  const healthColor =
    summary?.network_health === 'Resilient'
      ? 'text-ok border-ok/30 bg-ok/5'
      : summary?.network_health === 'Moderate'
      ? 'text-warn border-warn/30 bg-warn/5'
      : 'text-bad border-bad/30 bg-bad/5'

  return (
    <Card className="overflow-hidden border-border/80 shadow-md">
      {/* Top Banner */}
      <div className="border-b border-border bg-gradient-to-r from-surface to-surface-2 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent/10 text-accent ring-1 ring-accent/25">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-fg">AI/ML Supply Chain Intelligence & Recommendations</h2>
                {summary && (
                  <span
                    className={cn(
                      'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold',
                      healthColor
                    )}
                  >
                    {summary.network_health === 'Resilient' ? (
                      <ShieldCheck className="h-3.5 w-3.5" />
                    ) : (
                      <ShieldAlert className="h-3.5 w-3.5" />
                    )}
                    {summary.network_health} Health
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-xs text-fg-muted">
                Actionable strategic guidance powered by XGBoost Surrogate (v3), SHAP tree explainers, and steady-state stress testing.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              icon={RefreshCw}
              disabled={loading.advisory}
              onClick={loadAdvisory}
            >
              {loading.advisory ? 'Analyzing…' : 'Refresh Analysis'}
            </Button>
          </div>
        </div>
      </div>

      <CardBody className="space-y-5 p-5">
        <InlineError message={errors.advisory} onRetry={loadAdvisory} />

        {loading.advisory && !advisory && (
          <div className="space-y-3">
            <SkeletonBlock lines={4} label="Running AI network analysis..." />
          </div>
        )}

        {advisory && (
          <>
            {/* Health & Engine Metrics Strip */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-xl border border-border bg-surface-2/50 p-3">
                <span className="text-[11px] font-medium text-fg-muted">Resilience Rating</span>
                <p className="mt-1 text-lg font-bold font-mono text-fg">
                  {summary.resilience_score.toFixed(1)} <span className="text-xs font-normal text-fg-muted">/ 100</span>
                </p>
              </div>
              <div className="rounded-xl border border-border bg-surface-2/50 p-3">
                <span className="text-[11px] font-medium text-fg-muted">High-Criticality Sites</span>
                <p className="mt-1 text-lg font-bold font-mono text-fg">
                  {summary.critical_sites_count}{' '}
                  <span className="text-xs font-normal text-fg-muted">sites flagged</span>
                </p>
              </div>
              <div className="rounded-xl border border-border bg-surface-2/50 p-3">
                <span className="text-[11px] font-medium text-fg-muted">Primary Single Point of Failure</span>
                <p className="mt-1 flex items-center gap-1.5 text-sm font-bold text-fg">
                  {summary.top_spof_node ? (
                    <NodeTag id={summary.top_spof_node} size="sm" />
                  ) : (
                    <span className="text-ok font-normal text-xs">None Detected</span>
                  )}
                </p>
              </div>
              <div className="rounded-xl border border-border bg-surface-2/50 p-3">
                <span className="text-[11px] font-medium text-fg-muted">Intelligence Engine</span>
                <p className="mt-1 text-xs font-medium text-fg-2 truncate" title={summary.ml_engine}>
                  XGBoost + SHAP
                </p>
              </div>
            </div>

            {/* Sub-Tab Selector */}
            <div className="border-b border-border pb-3">
              <SegmentedControl
                label="Advisory Views"
                value={activeTab}
                onChange={setActiveTab}
                options={tabOptions}
                size="sm"
              />
            </div>

            {/* TAB 1: AI Strategic Recommendations */}
            {activeTab === 'recommendations' && (
              <div className="space-y-3.5">
                {recs.length === 0 ? (
                  <p className="text-center py-6 text-sm text-fg-muted">
                    No critical vulnerabilities identified. Network operates with sufficient redundancy.
                  </p>
                ) : (
                  recs.map((r, idx) => {
                    const isCritical = r.priority === 'critical'
                    const isHigh = r.priority === 'high'

                    return (
                      <div
                        key={r.id || idx}
                        className={cn(
                          'rounded-xl border p-4 transition-all hover:shadow-sm',
                          isCritical
                            ? 'border-bad/30 bg-bad/5'
                            : isHigh
                            ? 'border-warn/30 bg-warn/5'
                            : 'border-border bg-surface-2/40'
                        )}
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <Badge tone={isCritical ? 'bad' : isHigh ? 'warn' : 'accent'}>
                                {r.priority.toUpperCase()} PRIORITY
                              </Badge>
                              <Badge tone="muted">{r.category}</Badge>
                              {r.target_node && (
                                <span className="inline-flex items-center gap-1 text-xs text-fg-muted">
                                  Target: <NodeTag id={r.target_node} size="sm" />
                                </span>
                              )}
                            </div>
                            <h3 className="text-sm font-semibold text-fg">{r.title}</h3>
                          </div>

                          {r.simulation_event && (
                            <Button
                              size="sm"
                              variant={isCritical ? 'primary' : 'secondary'}
                              iconRight={ArrowRight}
                              onClick={() => handleSimulate(r.simulation_event)}
                            >
                              Simulate Disruption
                            </Button>
                          )}
                        </div>

                        {/* ML Insight & Action Grid */}
                        <div className="mt-3.5 grid gap-3 sm:grid-cols-2 text-xs">
                          <div className="rounded-lg border border-border/60 bg-surface/70 p-3">
                            <span className="font-semibold text-fg flex items-center gap-1.5">
                              <BrainCircuit className="h-3.5 w-3.5 text-accent" />
                              AI/ML Diagnosis
                            </span>
                            <p className="mt-1 leading-relaxed text-fg-2">{r.ml_insight}</p>
                          </div>
                          <div className="rounded-lg border border-border/60 bg-surface/70 p-3">
                            <span className="font-semibold text-fg flex items-center gap-1.5">
                              <TrendingUp className="h-3.5 w-3.5 text-ok" />
                              Recommended Action & Expected Impact
                            </span>
                            <p className="mt-1 leading-relaxed text-fg-2">
                              <span className="font-medium text-fg">{r.suggested_action}</span>
                            </p>
                            <p className="mt-1 font-medium text-ok">{r.expected_impact}</p>
                          </div>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            )}

            {/* TAB 2: ML Bottlenecks & SPOFs */}
            {activeTab === 'bottlenecks' && (
              <div className="space-y-3">
                <div className="overflow-hidden rounded-xl border border-border bg-surface">
                  <div className="divide-y divide-border/60">
                    {bottlenecks.map((b) => (
                      <div
                        key={b.node_id}
                        className="flex flex-wrap items-center justify-between gap-4 p-4 text-xs transition-colors hover:bg-surface-2/50"
                      >
                        <div className="flex items-center gap-3">
                          <NodeTag id={b.node_id} />
                          <div>
                            <span className="font-semibold text-fg text-sm">{b.name}</span>
                            <span className="ml-2 text-fg-muted font-mono">{b.city}</span>
                            <p className="mt-1 text-fg-2">{b.driver_summary}</p>
                          </div>
                        </div>

                        <div className="flex items-center gap-6">
                          <div className="text-right">
                            <span className="text-[11px] text-fg-muted block">ML Predicted Criticality</span>
                            <span
                              className={cn(
                                'font-mono text-sm font-bold',
                                b.risk > 0.25 ? 'text-bad' : b.risk > 0.12 ? 'text-warn' : 'text-ok'
                              )}
                            >
                              {(b.risk * 100).toFixed(1)}%
                            </span>
                          </div>

                          <div className="text-right">
                            <span className="text-[11px] text-fg-muted block">Capacity Util</span>
                            <span className="font-mono text-sm font-medium text-fg">
                              {(b.utilization * 100).toFixed(0)}%
                            </span>
                          </div>

                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => selectNode(b.node_id)}
                          >
                            Inspect Node
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </CardBody>
    </Card>
  )
}
