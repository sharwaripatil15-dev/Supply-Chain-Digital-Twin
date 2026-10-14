import { useEffect, useMemo, useState } from 'react'
import { Lightbulb, RefreshCw, ScanSearch } from 'lucide-react'
import { useStore } from '../store.js'
import { fmtNum } from '../format.js'
import { Badge, Button, EmptyState, InlineError, Meter, Panel, SectionLabel, Select, StatusDot, cn } from '../components/ui/index.js'
import Workspace, { InspectorPanel } from '../components/layout/Workspace.jsx'
import NetworkCanvas from '../components/canvas/NetworkCanvas.jsx'
import Evidence from '../components/reasoning/Evidence.jsx'

const LEVEL_TONE = { critical: 'bad', high: 'bad', medium: 'warn', low: 'neutral' }
const LEVELS = ['critical', 'high', 'medium', 'low']

function HealthCard({ health }) {
  if (!health || health.score == null) return null
  const after = health.after_fixes
  return (
    <Panel className="space-y-2 px-4 py-3">
      <div className="flex items-baseline gap-2">
        <SectionLabel>Supply chain health</SectionLabel>
        <span className="num ml-auto text-lg text-fg">{health.score.toFixed(1)}</span>
        <span className="text-xs text-fg-muted">/ 100</span>
        {after?.score != null && (
          <span className="num text-xs text-ok" title={`After: ${(after.fixes_applied || []).join('; ')}`}>
            → {after.score.toFixed(1)} after fixes
          </span>
        )}
      </div>
      <ul className="space-y-1.5">
        {health.breakdown.map((b) => {
          const a = after?.breakdown?.find((x) => x.key === b.key)
          return (
            <li key={b.key} className="grid grid-cols-[8.5rem_minmax(0,1fr)_4.5rem] items-center gap-2 text-xs" title={b.detail}>
              <span className="truncate text-fg-2">
                {b.label} <span className="text-fg-muted">×{b.weight}</span>
              </span>
              <Meter value={b.score} max={100} tone={b.score >= 70 ? 'muted' : 'accent'} label={`${b.label} score`} />
              <span className="num text-right text-fg">
                {b.score.toFixed(0)}
                {a && Math.round(a.score) !== Math.round(b.score) && <span className="text-ok"> → {a.score.toFixed(0)}</span>}
              </span>
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}

function FindingDetail({ finding, onApply }) {
  if (!finding) {
    return (
      <InspectorPanel title="Finding">
        <p className="px-4 py-3 text-xs text-fg-muted">Select a finding to see its evidence, root cause and tested fixes, and to locate it on the map.</p>
      </InspectorPanel>
    )
  }
  const imp = finding.impact
  return (
    <InspectorPanel title={finding.title} meta={`${finding.id} · ${finding.type_label} · severity ${finding.severity.toFixed(1)}`}>
      <div className="space-y-4 px-4 py-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <StatusDot status={LEVEL_TONE[finding.severity_level]} label={finding.severity_level} />
          <Badge>confidence {Math.round(finding.confidence * 100)}%</Badge>
          <Badge>p = {finding.probability}</Badge>
        </div>
        <section>
          <SectionLabel className="mb-1">Why this is a problem</SectionLabel>
          <p className="text-fg-2">{finding.why}</p>
        </section>
        <section>
          <SectionLabel className="mb-1">Root cause</SectionLabel>
          <p className="text-fg-2">{finding.root_cause}</p>
        </section>
        <section>
          <SectionLabel className="mb-1">Stress test (simulated)</SectionLabel>
          <p className="text-xs text-fg-2">{finding.stress.label}</p>
          <dl className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <dt className="text-fg-muted">Unmet demand</dt>
            <dd className="num text-fg">{imp.unmet_display} units</dd>
            <dt className="text-fg-muted">Revenue at risk</dt>
            <dd className="num text-fg">{imp.revenue_at_risk_display}</dd>
            <dt className="text-fg-muted">Demand nodes hit</dt>
            <dd className="num text-fg">{imp.customers_affected_count}</dd>
            <dt className="text-fg-muted">Expected loss</dt>
            <dd className="num text-fg">{imp.expected_loss_display}</dd>
            {imp.capital_tied_display && (
              <>
                <dt className="text-fg-muted">Capital tied up</dt>
                <dd className="num text-fg">{imp.capital_tied_display}</dd>
              </>
            )}
          </dl>
        </section>
        <section>
          <SectionLabel className="mb-1.5">Fixes, tested in the simulator</SectionLabel>
          {!finding.fixes.length && <p className="text-xs text-fg-muted">No automatic fix applies to this finding.</p>}
          <ol className="space-y-2">
            {finding.fixes.map((fx) => (
              <li key={fx.id} className={cn('space-y-1 rounded-md border p-2.5', fx.rank === 1 ? 'border-accent/50' : 'border-border')}>
                <div className="flex items-start gap-2">
                  <span className="num text-2xs text-fg-muted">#{fx.rank}</span>
                  <span className="flex-1 text-xs font-medium text-fg">{fx.label}</span>
                </div>
                <p className="text-2xs text-fg-muted">{fx.description}</p>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-2xs">
                  <dt className="text-fg-muted">Cost</dt>
                  <dd className="num text-fg">{fx.cost_display}</dd>
                  <dt className="text-fg-muted">Unmet after</dt>
                  <dd className="num text-fg">{fx.result.unmet_display} units</dd>
                  <dt className="text-fg-muted">Avg delay after</dt>
                  <dd className="num text-fg">{fx.result.delay_avg_days.toFixed(2)} d</dd>
                  {fx.result.resilience != null && (
                    <>
                      <dt className="text-fg-muted">Resilience after</dt>
                      <dd className="num text-fg">{fx.result.resilience.toFixed(1)}</dd>
                    </>
                  )}
                  <dt className="text-fg-muted">Net benefit</dt>
                  <dd className={cn('num', fx.net_inr > 0 ? 'text-ok' : 'text-fg-2')}>{fx.net_display}</dd>
                </dl>
                <Button size="xs" variant={fx.rank === 1 ? 'primary' : 'secondary'} icon={Lightbulb} className="mt-1" onClick={() => onApply(finding, fx)}>
                  Apply fix in What-if
                </Button>
              </li>
            ))}
          </ol>
        </section>
        <p className="text-xs text-fg-2">{finding.business}</p>
        <Evidence data={{ evidence: finding.evidence, impact: finding.impact, stress: finding.stress, fixes: finding.fixes }} />
      </div>
    </InspectorPanel>
  )
}

export default function InsightsPage() {
  const { analysis, runAnalysis, loadAnalysis, loading, errors, selectedFinding, selectFinding, setWhatIfDraft, source, setTab } = useStore()
  const runnable = !source || source.runnable
  const [type, setType] = useState('all')
  const [minLevel, setMinLevel] = useState('all')

  useEffect(() => {
    if (!analysis && !loading.analysis) loadAnalysis()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis])
  useEffect(() => {
    if (analysis?.status !== 'running') return undefined
    const t = setTimeout(loadAnalysis, 1000) // poll progress until the job finishes
    return () => clearTimeout(t)
  }, [analysis, loadAnalysis])

  const done = analysis?.status === 'ok' ? analysis : null
  const findings = useMemo(() => {
    const all = done?.findings ?? []
    const cut = minLevel === 'all' ? LEVELS.length : LEVELS.indexOf(minLevel) + 1
    return all.filter((f) => (type === 'all' || f.type === type) && LEVELS.indexOf(f.severity_level) < cut)
  }, [done, type, minLevel])
  const selected = done?.findings.find((f) => f.id === selectedFinding) || null
  const highlight = useMemo(() => (selected ? selected.locations.nodes : findings.slice(0, 5).flatMap((f) => f.locations.nodes)), [selected, findings])
  const disrupted = useMemo(() => (selected ? { nodes: new Set(), edges: new Set(selected.locations.edges) } : null), [selected])
  const types = Object.keys(done?.counts.by_type ?? {})

  const apply = (finding, fx) =>
    setWhatIfDraft({
      events: finding.whatif.events,
      text: finding.whatif.text,
      note: `From ${finding.id} (${finding.title}): the tested fix "${fx.label}" cuts unmet demand in this stress test to ${fx.result.unmet_display} units for ${fx.cost_display}. Run the what-if to plan recovery for the same disruption.`,
    })

  const progress = analysis?.status === 'running' ? analysis.progress : null
  let list
  if (!runnable) {
    list = <EmptyState title="The active network can't be analysed" description="Fix its validation errors first." action={<Button onClick={() => setTab('data')}>Open the Data page</Button>} />
  } else if (errors.analysis || analysis?.status === 'error') {
    list = <InlineError className="m-4" message={errors.analysis || analysis.detail} onRetry={runAnalysis} />
  } else if (progress) {
    list = (
      <div className="space-y-2 p-4" role="status" aria-live="polite">
        <p className="text-sm text-fg">Analysing the network…</p>
        <Meter value={progress.done} max={Math.max(1, progress.total)} tone="accent" label="Analysis progress" />
        <p className="text-xs text-fg-muted">
          {progress.done}/{progress.total} · {progress.step}
        </p>
      </div>
    )
  } else if (!done) {
    list = (
      <EmptyState
        title="Run your first analysis"
        description="Runs every detector, stress-tests each finding in the simulator and tests the fixes."
        action={<Button variant="primary" icon={ScanSearch} disabled={loading.analysis} onClick={runAnalysis}>Analyze supply chain</Button>}
      />
    )
  } else if (!findings.length) {
    list = <p className="p-4 text-sm text-fg-2">{done.findings.length ? 'No findings match the filters.' : 'No pain points found: the network passes every check.'}</p>
  } else {
    list = (
      <ol className="divide-y divide-border">
        {findings.map((f) => (
          <li key={f.id}>
            <button
              type="button"
              onClick={() => selectFinding(f.id === selectedFinding ? null : f.id)}
              aria-pressed={f.id === selectedFinding}
              className={cn('flex w-full gap-3 px-4 py-2.5 text-left transition-colors duration-150 hover:bg-raised', f.id === selectedFinding && 'bg-raised')}
            >
              <span className={cn('mt-1 h-8 w-1 shrink-0 rounded-full', { critical: 'bg-bad', high: 'bg-bad/70', medium: 'bg-warn', low: 'bg-fg-muted/40' }[f.severity_level])} aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="truncate text-sm text-fg">{f.title}</span>
                  <span className="num ml-auto shrink-0 text-xs text-fg-muted">{f.severity.toFixed(0)}</span>
                </span>
                <span className="mt-0.5 flex items-center gap-2 text-2xs text-fg-muted">
                  <span className="uppercase tracking-wide">{f.severity_level}</span>·<span>{f.type_label}</span>·<span className="num">{f.impact.unmet_display} u at risk</span>
                </span>
              </span>
            </button>
          </li>
        ))}
      </ol>
    )
  }

  return (
    <div className="flex h-full min-h-[640px] flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" icon={done ? RefreshCw : ScanSearch} disabled={!runnable || loading.analysis || Boolean(progress)} onClick={runAnalysis}>
          {progress ? 'Analysing…' : done ? 'Re-run analysis' : 'Analyze supply chain'}
        </Button>
        {done && (
          <span className="text-xs text-fg-muted">
            {done.findings.length} finding(s) · {LEVELS.filter((l) => done.counts.by_level[l]).map((l) => `${done.counts.by_level[l]} ${l}`).join(', ')} · {done.elapsed_s}s · all
            figures simulated
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <Select size="sm" value={type} onChange={(e) => setType(e.target.value)} aria-label="Filter by type" className="w-48">
            <option value="all">All types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {done.findings.find((f) => f.type === t)?.type_label} ({done.counts.by_type[t]})
              </option>
            ))}
          </Select>
          <Select size="sm" value={minLevel} onChange={(e) => setMinLevel(e.target.value)} aria-label="Minimum severity" className="w-40">
            <option value="all">Any severity</option>
            {LEVELS.slice(0, 3).map((l) => (
              <option key={l} value={l}>
                {l} and above
              </option>
            ))}
          </Select>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 gap-3">
        <div className="flex w-[380px] shrink-0 flex-col gap-3 xl:w-[440px]">
          <HealthCard health={done?.health} />
          <Panel className="min-h-0 flex-1 overflow-y-auto">{list}</Panel>
          {done?.summary && <p className="text-2xs text-fg-muted">{done.summary} {done.severity_formula}.</p>}
        </div>
        <Workspace className="min-w-0 flex-1" inspector={<FindingDetail finding={selected} onApply={apply} />} inspectorLabel="Finding">
          <NetworkCanvas highlight={highlight} disrupted={disrupted} view3d={{ focus: selected?.locations.nodes ?? null, focusKey: selected?.id }} />
        </Workspace>
      </div>
      {done && <p className="sr-only">{fmtNum(done.findings.length)} findings</p>}
    </div>
  )
}
