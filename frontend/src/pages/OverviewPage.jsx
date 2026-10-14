import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, Bell, Download, FileText, MapPinPlus, ScanSearch, Send } from 'lucide-react'
import { api } from '../api.js'
import { SOURCE_LABEL, useStore } from '../store.js'
import { fmtINR, fmtNum } from '../format.js'
import { useUi } from '../ui.jsx'
import { downloadText } from '../lib/download.js'
import { toCsv } from '../lib/csv.js'
import { printBrief } from '../lib/brief.js'
import { Badge, Button, Checkbox, EmptyState, InlineError, Input, Meter, Panel, PanelHeader, Skeleton, StatusDot, Toggle, cn, useToast } from '../components/ui/index.js'
import NetworkCanvas from '../components/canvas/NetworkCanvas.jsx'
import { Term } from '../components/Glossary.jsx'

const LEVEL_TONE = { critical: 'bad', high: 'bad', medium: 'warn', low: 'neutral' }
const healthWord = (s) => (s == null ? '' : s >= 70 ? 'Healthy' : s >= 50 ? 'Fair' : 'At risk')
const effortOf = (inr) => (inr == null ? '–' : inr < 5e5 ? 'Low' : inr < 5e6 ? 'Medium' : 'High')
const HISTORY_KEY = 'aegis-overview-history'
const PLANNED_KEY = 'aegis-planned-actions'

function readStore(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback
  } catch {
    return fallback
  }
}
function writeStore(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage unavailable: trends and planned marks last for this session */
  }
}

/** Quiet delta vs the previous analysis: "▲ 2.1" / "▼ 0.4" with a tone that knows whether up is good. */
function Delta({ now, prev, digits = 1, goodUp = true, unit = '' }) {
  if (now == null || prev == null) return null // first analysis of this network: nothing to compare with
  if (Math.abs(now - prev) < 10 ** -digits / 2) return <span className="text-2xs text-fg-muted">no change vs last analysis</span>
  const up = now > prev
  const good = up === goodUp
  return (
    <span className={cn('num text-2xs', good ? 'text-ok' : 'text-bad')}>
      {up ? '▲' : '▼'} {fmtNum(Math.abs(now - prev), digits)}
      {unit} vs last analysis
    </span>
  )
}

function Kpi({ term, label, value, unit, meaning, delta, loading, onClick }) {
  return (
    <div className="min-w-0 px-4 py-3">
      <dt className="truncate text-xs text-fg-muted"><Term id={term}>{label}</Term></dt>
      <dd className="mt-0.5 flex items-baseline gap-1">
        {loading ? <Skeleton className="my-1 h-6 w-20" /> : (
          <button type="button" className="num text-xl text-fg hover:underline disabled:no-underline" onClick={onClick} disabled={!onClick}>
            {value ?? '–'}
          </button>
        )}
        {unit && value != null && <span className="text-xs text-fg-muted">{unit}</span>}
      </dd>
      <dd className="mt-0.5 line-clamp-2 text-2xs text-fg-muted">{meaning}</dd>
      <dd className="h-4">{delta}</dd>
    </div>
  )
}

export default function OverviewPage() {
  const store = useStore()
  const {
    network, source, analysis, baseline, expansion, whatifHistory, whatif, loading, errors, events, selectedNode,
    loadAnalysis, runAnalysis, loadBaseline, loadExpansionLatest, loadWhatIfHistory, setWhatIfDraft, setTab, selectFinding, openWhatIf,
  } = store
  const ui = useUi()
  const toast = useToast()
  const [ask, setAsk] = useState('')
  const [showBreakdown, setShowBreakdown] = useState(false)
  const [layers, setLayers] = useState({ risk: true, weather: false })
  const [weather, setWeather] = useState(null)
  const [planned, setPlanned] = useState(() => readStore(PLANNED_KEY, {}))
  const runnable = !source || source.runnable
  const empty = !network?.nodes?.length
  const netKey = source?.source ?? 'preset'

  useEffect(() => {
    if (empty || !runnable) return
    if (!analysis && !loading.analysis) loadAnalysis()
    if (!baseline && !loading.baseline) loadBaseline()
    if (!expansion) loadExpansionLatest()
    if (!whatifHistory) loadWhatIfHistory()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis, baseline, empty, runnable, source?.version])
  useEffect(() => {
    if (analysis?.status !== 'running') return undefined
    const t = setTimeout(loadAnalysis, 1000)
    return () => clearTimeout(t)
  }, [analysis, loadAnalysis])
  useEffect(() => {
    if (empty || !runnable) return
    api.weatherRisk(7).then(setWeather).catch(() => setWeather(null))
  }, [empty, runnable, source?.version])

  // A click on the compact map opens the Network page focused on that site.
  const firstSel = useRef(selectedNode)
  useEffect(() => {
    if (selectedNode && selectedNode !== firstSel.current) setTab('twin')
  }, [selectedNode, setTab])

  const done = analysis?.status === 'ok' ? analysis : null
  const findings = done?.findings ?? []
  const health = done?.health
  const revenueAtRisk = done ? findings.reduce((s, f) => s + (f.impact.expected_loss_inr || 0), 0) : null

  // trend: one snapshot per analysis, per data source
  const current = useMemo(() => (done && baseline?.status === 'ok' ? {
    at: done.generated_at, health: health?.score, service: baseline.service_level_pct, rar: revenueAtRisk, lead: baseline.avg_lead_days,
    cover: baseline.stock_cover_days, resilience: network?.resilience_score,
  } : null), [done, baseline, health, revenueAtRisk, network])
  const [prev, setPrev] = useState(null)
  useEffect(() => {
    if (!current) return
    const all = readStore(HISTORY_KEY, {})
    const list = all[netKey] ?? []
    const before = list.filter((s) => s.at !== current.at)
    setPrev(before[before.length - 1] ?? null)
    if (!list.some((s) => s.at === current.at)) writeStore(HISTORY_KEY, { ...all, [netKey]: [...list, current].slice(-20) })
  }, [current, netKey])

  const actions = useMemo(() => {
    const out = []
    for (const f of findings.slice(0, 8)) {
      const fx = f.fixes[0]
      if (!fx || fx.net_inr <= 0) continue
      out.push({ id: `fix:${f.type}:${f.locations.nodes.join('+')}:${fx.id}`, kind: 'Fix', title: fx.label, why: f.title, value: fx.net_inr,
        benefit: `${fx.net_display} net`, effort: effortOf(fx.cost_inr), open: () => (selectFinding(f.id), setTab('insights')) })
    }
    const w = whatifHistory?.[0]
    if (w && w.net_saving > 0) {
      out.push({ id: `whatif:${w.label}:${w.recommended}`, kind: 'Recovery', title: `Prepare "${w.recommended}" for: ${w.label}`, why: 'From your latest what-if',
        value: w.net_saving, benefit: `${fmtINR(w.net_saving)} saved vs waiting`, effort: effortOf(w.recommended_cost), open: () => (openWhatIf(w.id), setTab('whatif')) })
    }
    const best = expansion?.status === 'ok' ? expansion.plans[0] : null
    if (best?.sites?.length) {
      out.push({ id: `expansion:${best.sites.map((s) => s.candidate).join('+')}`, kind: 'Expansion', title: `Open ${best.sites.map((s) => `${s.name} ${s.kind}`).join(', ')}`,
        why: best.label, value: best.annual_savings_inr, benefit: best.payback_years ? `${best.annual_savings_display}/yr, payback ${fmtNum(best.payback_years, 1)} y` : 'Service and resilience, no payback',
        effort: 'High', open: () => setTab('expansion') })
    }
    return out.sort((a, b) => b.value - a.value).slice(0, 6)
  }, [findings, whatifHistory, expansion, selectFinding, setTab, openWhatIf])

  const alerts = useMemo(() => {
    const out = []
    for (const e of (weather?.edges ?? []).filter((x) => ['high', 'severe'].includes(x.max_level)).sort((a, b) => b.max_risk - a.max_risk).slice(0, 3)) {
      out.push({ id: `wx:${e.id}`, tone: e.max_level === 'severe' ? 'bad' : 'warn', text: `Weather: ${e.max_level} risk on lane ${e.id.replace('->', ' → ')} in the next 7 days`, go: () => setTab('weather') })
    }
    for (const f of findings.filter((x) => x.type === 'inventory_risk' && x.title.startsWith('Thin')).slice(0, 2)) {
      out.push({ id: `inv:${f.id}`, tone: 'warn', text: `Stock-out risk: ${f.title}`, go: () => (selectFinding(f.id), setTab('insights')) })
    }
    const fs = whatif?.evidence?.impact?.first_stockout
    if (fs) out.push({ id: 'whatif-stockout', tone: 'bad', text: `In your latest what-if, ${fs.node} runs out of stock on day ${fs.day} (simulated)`, go: () => setTab('whatif') })
    return out.slice(0, 5)
  }, [weather, findings, whatif, selectFinding, setTab])

  const weatherDisrupted = useMemo(() => {
    if (!layers.weather || !weather) return null
    return { nodes: new Set(), edges: new Set((weather.edges ?? []).filter((e) => ['high', 'severe'].includes(e.max_level)).map((e) => e.id)) }
  }, [layers.weather, weather])
  const riskHighlight = useMemo(() => (layers.risk ? (network?.nodes ?? []).filter((n) => (n.risk ?? 0) >= 0.25 && n.kind !== 'customer' && n.kind !== 'retailer').map((n) => n.id) : null), [layers.risk, network])

  const kpis = [
    { term: 'service_level', label: 'Service level', value: baseline?.status === 'ok' ? fmtNum(baseline.service_level_pct, 1) : null, unit: '%', meaning: 'Demand delivered in full today',
      delta: <Delta now={current?.service} prev={prev?.service} />, onClick: () => setTab('twin') },
    { term: 'revenue_at_risk', label: 'Revenue at risk', value: revenueAtRisk != null ? fmtINR(revenueAtRisk) : null, meaning: 'Expected loss across the risks found',
      delta: <Delta now={current?.rar != null ? current.rar / 1e5 : null} prev={prev?.rar != null ? prev.rar / 1e5 : null} goodUp={false} unit=" L" />, onClick: () => setTab('insights') },
    { term: 'lead_time', label: 'Avg delivery lead time', value: baseline?.status === 'ok' ? fmtNum(baseline.avg_lead_days, 1) : null, unit: 'days', meaning: 'Supplier to customer, today',
      delta: <Delta now={current?.lead} prev={prev?.lead} goodUp={false} />, onClick: () => setTab('twin') },
    { term: 'cover', label: 'Days of stock cover', value: baseline?.status === 'ok' ? fmtNum(baseline.stock_cover_days, 1) : null, unit: 'days', meaning: 'How long customer stock lasts',
      delta: <Delta now={current?.cover} prev={prev?.cover} />, onClick: () => setTab('insights') },
    { term: 'resilience', label: 'Resilience', value: network?.resilience_score != null ? fmtNum(network.resilience_score, 0) : null, unit: '/ 100', meaning: 'Survives the worst failure pairs',
      delta: <Delta now={current?.resilience} prev={prev?.resilience} />, onClick: () => setTab('chaos') },
  ]
  const kpiLoading = loading.baseline && !baseline

  const fixThis = (f) =>
    setWhatIfDraft({ events: f.whatif.events, text: f.whatif.text, note: `From "${f.title}": ${f.business}` })
  const submitAsk = (e) => {
    e.preventDefault()
    setWhatIfDraft(ask.trim().length >= 3 ? { text: ask.trim() } : { text: '' })
    setAsk('')
  }
  const togglePlanned = (id) => {
    const next = { ...planned, [id]: !planned[id] }
    setPlanned(next)
    writeStore(PLANNED_KEY, next)
  }
  const netName = `${SOURCE_LABEL[source?.source] ?? 'Preset demo'} · ${network?.nodes?.length ?? 0} sites`
  const lastUpdated = done?.generated_at ? new Date(done.generated_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : 'not analysed yet'
  const scenarioStatus = whatifHistory?.[0]?.label || (events.length ? `${events.length} event(s) on the Simulate page` : 'none yet')
  const best = expansion?.status === 'ok' ? expansion.plans[0] : null

  const brief = () => {
    const ok = printBrief({
      network: netName, source: `${SOURCE_LABEL[source?.source] ?? 'Preset demo'} (v${source?.version ?? 1})`,
      date: new Date().toLocaleString('en-IN', { dateStyle: 'long', timeStyle: 'short' }), health, healthWord: healthWord(health?.score),
      kpis: kpis.map((k) => ({ label: k.label, value: k.value != null ? `${k.value}${k.unit ? ` ${k.unit}` : ''}` : '–', meaning: k.meaning })),
      risks: findings.slice(0, 3).map((f) => ({ title: f.title, level: f.severity_level, reason: f.why, revenue: f.impact.revenue_at_risk_display })),
      actions: actions.map((a) => ({ kind: a.kind, title: a.title, benefit: a.benefit, effort: a.effort })),
      scenario: whatif?.status === 'ok' ? `${whatif.sections[0]?.paragraphs[0] ?? ''} Recommended: ${whatif.plans.find((p) => p.recommended)?.label} (confidence ${whatif.confidence}).` : whatifHistory?.[0] ? `${whatifHistory[0].label}: ${fmtNum(whatifHistory[0].unmet_units)} units unmet, recommended ${whatifHistory[0].recommended}.` : null,
      expansion: best?.sites?.length ? `${best.label}: ${best.sites.map((s) => `${s.name} ${s.kind}`).join(', ')} for ${best.build_cost_display}; ${best.payback_years ? `payback ${fmtNum(best.payback_years, 1)} years` : 'no payback within the model'}; service ${fmtNum(best.service_level_before_pct, 1)}% → ${fmtNum(best.service_level_after_pct, 1)}%. ${best.sites[0].rationale}` : null,
    })
    if (!ok) toast('Allow pop-ups to open the brief', { tone: 'error' })
  }

  if (empty) {
    return (
      <div className="p-6">
        <Panel className="mx-auto mt-10 max-w-xl">
          <EmptyState title="Your network is empty" description="Load a demo story, or build or upload your network on the Data page."
            action={<div className="flex gap-2"><Button variant="primary" onClick={() => ui.setDemo({ phase: 'start' })}>Start the demo</Button><Button onClick={() => setTab('data')}>Open Data</Button></div>} />
        </Panel>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto grid max-w-[1600px] grid-cols-12 gap-4 p-4 xl:p-6">
        {/* 1. header strip */}
        <Panel className="col-span-12 flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-fg">{netName}</p>
            <p className="text-xs text-fg-muted">
              Source: {SOURCE_LABEL[source?.source] ?? 'Preset demo'} · updated {lastUpdated} · scenario: <span className="text-fg-2">{scenarioStatus}</span>
            </p>
          </div>
          <form onSubmit={submitAsk} className="flex min-w-[280px] flex-1 items-center gap-2">
            <Input size="sm" value={ask} onChange={(e) => setAsk(e.target.value)} placeholder='Ask or simulate, e.g. "What if supplier S2 fails for 10 days?"' aria-label="Ask or simulate" />
            <Button size="sm" type="submit" icon={Send} disabled={!runnable}>Ask</Button>
          </form>
          <div className="flex gap-2">
            <Button size="sm" variant="primary" icon={ScanSearch} disabled={!runnable || analysis?.status === 'running'} onClick={runAnalysis}>
              {analysis?.status === 'running' ? 'Analysing…' : 'Analyze'}
            </Button>
            <Button size="sm" icon={FileText} onClick={brief} title="Two-page brief to print or save as PDF">Executive brief</Button>
          </div>
        </Panel>
        {!runnable && <InlineError className="col-span-12" message="The active network has validation errors; fix them on the Data page to see live figures." />}

        {/* 2. health hero */}
        <Panel data-tour="health" className="col-span-12 px-5 py-4 lg:col-span-4">
          <div className="flex items-center"><Term id="health" className="text-xs text-fg-muted">Supply chain health</Term><span className="ml-auto text-2xs text-fg-muted">simulated</span></div>
          {done && health?.score != null ? (
            <>
              <button type="button" onClick={() => setShowBreakdown((v) => !v)} aria-expanded={showBreakdown} className="mt-1 flex items-baseline gap-2 text-left">
                <span className="num text-[44px] font-semibold leading-none text-fg">{Math.round(health.score)}</span>
                <span className="text-sm text-fg-muted">/ 100</span>
                <StatusDot status={health.score >= 70 ? 'ok' : health.score >= 50 ? 'warn' : 'bad'} label={healthWord(health.score)} className="ml-1" />
              </button>
              <div className="mt-1"><Delta now={current?.health} prev={prev?.health} /></div>
              <p className="mt-2 text-xs text-fg-2">
                {health.after_fixes?.score != null ? <>Applying the top fixes lifts it to <span className="num text-fg">{Math.round(health.after_fixes.score)}</span>. </> : null}
                <button type="button" className="text-fg-muted underline underline-offset-2" onClick={() => setShowBreakdown((v) => !v)}>{showBreakdown ? 'Hide' : 'Show'} how it is built</button>
              </p>
              {showBreakdown && (
                <ul className="mt-3 space-y-1.5">
                  {health.breakdown.map((b) => (
                    <li key={b.key} className="grid grid-cols-[8rem_minmax(0,1fr)_2rem] items-center gap-2 text-xs" title={b.detail}>
                      <span className="truncate text-fg-2">{b.label}</span>
                      <Meter value={b.score} max={100} tone={b.score >= 70 ? 'muted' : 'accent'} label={`${b.label} score`} />
                      <span className="num text-right text-fg">{Math.round(b.score)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : analysis?.status === 'running' ? (
            <div className="mt-3 space-y-2" role="status"><Meter value={analysis.progress.done} max={analysis.progress.total} tone="accent" label="Analysis progress" /><p className="text-xs text-fg-muted">{analysis.progress.step}…</p></div>
          ) : loading.analysis && !analysis ? (
            <Skeleton className="mt-2 h-12 w-32" />
          ) : (
            <EmptyState className="py-4" title="Run your first analysis" description="Finds bottlenecks and scores the network's health."
              action={<Button size="sm" variant="primary" icon={ScanSearch} disabled={!runnable} onClick={runAnalysis}>Analyze</Button>} />
          )}
          <InlineError message={errors.analysis} onRetry={runAnalysis} />
        </Panel>

        {/* 3. KPI row */}
        <Panel className="col-span-12 lg:col-span-8">
          <dl aria-label="Key indicators" className="grid h-full grid-cols-2 divide-border md:grid-cols-5 md:divide-x">
            {kpis.map((k) => <Kpi key={k.term} {...k} loading={kpiLoading} />)}
          </dl>
          <InlineError className="mx-4 mb-3" message={errors.baseline} onRetry={loadBaseline} />
        </Panel>

        {/* 4. what needs attention */}
        <Panel data-tour="attention" className="col-span-12 lg:col-span-7">
          <PanelHeader title="What needs attention" meta={done ? `${findings.length} findings · top 3` : null}
            actions={done && <Button size="xs" variant="ghost" iconRight={ArrowRight} onClick={() => setTab('insights')}>All insights</Button>} />
          {!done ? <p className="px-4 py-4 text-sm text-fg-muted">{analysis?.status === 'running' ? 'Analysing…' : 'Run your first analysis to see the top risks.'}</p> : !findings.length ? (
            <p className="px-4 py-4 text-sm text-fg-2">Nothing needs attention: the network passes every check.</p>
          ) : (
            <ol className="divide-y divide-border">
              {findings.slice(0, 3).map((f) => (
                <li key={f.id} className="flex gap-3 px-4 py-3">
                  <span className={cn('mt-1 h-10 w-1 shrink-0 rounded-full', { critical: 'bg-bad', high: 'bg-bad/70', medium: 'bg-warn', low: 'bg-fg-muted/40' }[f.severity_level])} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <button type="button" className="text-left text-sm font-medium text-fg hover:underline" onClick={() => (selectFinding(f.id), setTab('insights'))}>{f.title}</button>
                    <p className="mt-0.5 line-clamp-2 text-xs text-fg-2">{f.why}</p>
                    <p className="mt-1 flex items-center gap-2 text-2xs text-fg-muted">
                      <StatusDot status={LEVEL_TONE[f.severity_level]} label={f.severity_level} />
                      <span>·</span><Term id="revenue_at_risk">Revenue at risk</Term> <span className="num text-fg-2">{f.impact.revenue_at_risk_display}</span>
                    </p>
                  </div>
                  <Button size="sm" className="self-center" onClick={() => fixThis(f)} disabled={!runnable}>Fix this</Button>
                </li>
              ))}
            </ol>
          )}
        </Panel>

        {/* 5. recommended actions */}
        <Panel data-tour="actions" className="col-span-12 lg:col-span-5">
          <PanelHeader title="Recommended actions" meta="ranked by benefit"
            actions={actions.length > 0 && <Button size="xs" variant="ghost" icon={Download} onClick={() => downloadText('recommended-actions.csv', toCsv(actions.map((a) => ({ type: a.kind, action: a.title, reason: a.why, estimated_benefit: a.benefit, effort: a.effort, planned: planned[a.id] ? 'yes' : 'no' }))), 'text/csv')}>CSV</Button>} />
          {!actions.length ? <p className="px-4 py-4 text-sm text-fg-muted">Actions appear once the analysis, a what-if or the expansion planner has run.</p> : (
            <ol className="divide-y divide-border">
              {actions.map((a) => (
                <li key={a.id} className={cn('flex items-start gap-3 px-4 py-2.5', planned[a.id] && 'opacity-60')}>
                  <Checkbox checked={Boolean(planned[a.id])} onChange={() => togglePlanned(a.id)} aria-label={`Mark "${a.title}" as planned`} className="mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <button type="button" onClick={a.open} className="text-left text-sm text-fg hover:underline">{a.title}</button>
                    <p className="text-2xs text-fg-muted"><Badge className="mr-1">{a.kind}</Badge>{a.why}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="num text-xs text-ok">{a.benefit}</p>
                    <p className="text-2xs text-fg-muted">effort {a.effort}{planned[a.id] ? ' · planned' : ''}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Panel>

        {/* 6. compact map */}
        <Panel className="col-span-12 overflow-hidden lg:col-span-7">
          <PanelHeader title="Network" meta="click a site to open it" actions={
            <div className="flex gap-1.5">
              <Toggle pressed={layers.risk} onChange={() => setLayers((l) => ({ ...l, risk: !l.risk }))} title="Highlight sites whose loss would cost 25%+ of demand">Risk</Toggle>
              <Toggle pressed={layers.weather} onChange={() => setLayers((l) => ({ ...l, weather: !l.weather }))} title="Show lanes with high or severe weather risk this week">Hazards</Toggle>
            </div>} />
          <div className="relative h-[340px]">
            <NetworkCanvas highlight={riskHighlight} disrupted={weatherDisrupted} />
          </div>
        </Panel>

        {/* 7. expansion teaser + alerts */}
        <div className="col-span-12 flex flex-col gap-4 lg:col-span-5">
          <Panel data-tour="expansion" className="px-4 py-3">
            <div className="flex items-center gap-2"><MapPinPlus className="h-4 w-4 text-fg-muted" aria-hidden /><span className="text-sm font-medium text-fg">Where to grow</span><span className="ml-auto text-2xs text-fg-muted">simulated</span></div>
            {best?.sites?.length ? (
              <>
                <p className="mt-2 text-sm text-fg-2"><span className="font-medium text-fg">{best.sites.map((s) => `${s.name} ${s.kind}`).join(', ')}</span> · build {best.build_cost_display} · {best.payback_years ? <>payback <span className="num text-fg">{fmtNum(best.payback_years, 1)} years</span></> : 'no payback, but service and resilience gains'}</p>
                <p className="mt-1 line-clamp-2 text-xs text-fg-muted">{best.sites[0].rationale}</p>
              </>
            ) : <p className="mt-2 text-sm text-fg-muted">Find the best site for a new warehouse or plant.</p>}
            <Button size="sm" className="mt-2" iconRight={ArrowRight} onClick={() => setTab('expansion')}>{best ? 'Open the planner' : 'Find the best site'}</Button>
          </Panel>
          <Panel className="flex-1">
            <PanelHeader title="Alerts" meta={alerts.length ? `${alerts.length}` : null} />
            {!alerts.length ? <p className="px-4 py-3 text-xs text-fg-muted">No weather or stock-out alerts right now.</p> : (
              <ul className="divide-y divide-border">
                {alerts.map((a) => (
                  <li key={a.id}>
                    <button type="button" onClick={a.go} className="flex w-full items-start gap-2 px-4 py-2 text-left text-xs text-fg-2 hover:bg-raised">
                      <Bell className={cn('mt-0.5 h-3.5 w-3.5 shrink-0', a.tone === 'bad' ? 'text-bad' : 'text-warn')} aria-hidden />
                      {a.text}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        {/* 8. scenario comparison */}
        <Panel className="col-span-12">
          <PanelHeader title="Recent scenarios" meta="last what-if runs, side by side · simulated"
            actions={<Button size="xs" variant="ghost" iconRight={ArrowRight} onClick={() => setTab('whatif')}>What-if</Button>} />
          {!whatifHistory?.length ? <p className="px-4 py-3 text-sm text-fg-muted">No what-if runs yet. Ask a question in the header.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-fg-muted">
                    <th className="px-4 py-2 font-medium">Scenario</th>
                    <th className="px-3 py-2 text-right font-medium"><Term id="unmet">Unmet demand</Term></th>
                    <th className="px-3 py-2 text-right font-medium"><Term id="revenue_at_risk">Revenue at risk</Term></th>
                    <th className="px-3 py-2 text-right font-medium"><Term id="survival_clock">Survival Clock</Term></th>
                    <th className="px-3 py-2 font-medium">Recommended plan</th>
                    <th className="px-4 py-2 font-medium">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {whatifHistory.slice(0, 3).map((r) => (
                    <tr key={r.id} className="border-t border-border">
                      <td className="max-w-[22rem] truncate px-4 py-2"><button type="button" className="text-fg hover:underline" onClick={() => (openWhatIf(r.id), setTab('whatif'))} title={r.label}>{r.label}</button>{r.stale && <Badge className="ml-2">older network</Badge>}</td>
                      <td className="num px-3 py-2 text-right">{fmtNum(r.unmet_units)} units</td>
                      <td className="num px-3 py-2 text-right">{fmtINR(r.revenue_at_risk)}</td>
                      <td className="num px-3 py-2 text-right">{r.survival_clock_days} days</td>
                      <td className="px-3 py-2 text-fg-2">{r.recommended}</td>
                      <td className="px-4 py-2 text-fg-2">{r.confidence}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
