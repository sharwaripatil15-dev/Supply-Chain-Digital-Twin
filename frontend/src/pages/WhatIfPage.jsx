import { useEffect, useMemo, useState } from 'react'
import { FileDown, GitCompare, Play, Printer, Send } from 'lucide-react'
import { api, errorMessage } from '../api.js'
import { useStore } from '../store.js'
import { eventLabel, fmtINR, fmtNum } from '../format.js'
import { downloadText } from '../lib/download.js'
import { peakDisruption } from '../lib/disruption.js'
import {
  Badge, Button, Checkbox, DataTable, EmptyState, InlineError, KpiStrip, Notice, Panel, PanelHeader, SectionLabel, Select,
  SkeletonRows, StatusDot, TabPanel, Tabs, Textarea, useToast,
} from '../components/ui/index.js'
import NetworkCanvas from '../components/canvas/NetworkCanvas.jsx'
import { CostScatter } from '../components/RecoverCompare.jsx'
import Sections from '../components/reasoning/Sections.jsx'
import Evidence from '../components/reasoning/Evidence.jsx'

const EXAMPLES = ['What if Supplier S2 fails for 10 days?', 'What if demand rises 40% in Chennai during the festival season?', 'What if lane F1->W3 is blocked for 2 weeks from day 3?']
const FOLLOW_UPS = ['Why not air freight?', 'What if the backup supplier is also delayed?', 'Try the inventory buffer']
const CONF_TONE = { High: 'ok', Medium: 'warn', Low: 'bad' }

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

/** Print-ready brief in a new window (the browser's "Save as PDF" turns it into a PDF). */
function printBrief(run) {
  const w = window.open('', '_blank', 'noopener=no,width=900,height=1000')
  if (!w) return false
  const plans = run.plans
    .map((p) => `<tr><td>${esc(p.label)}${p.recommended ? ' <b>(recommended)</b>' : ''}</td><td>${esc(p.cost_display)}</td><td>${esc(p.unmet_display)}</td><td>${p.delay_avg_days.toFixed(2)}</td><td>${p.recovery_days}</td><td>${p.co2_t.toFixed(2)}</td><td>${p.safety.passed ? 'pass' : 'FAIL'}</td><td>${esc(p.objective_display)}</td></tr>`)
    .join('')
  const sections = run.sections
    .map((s) => `<h2>${esc(s.title)}</h2>${(s.paragraphs || []).map((p) => `<p>${esc(p)}</p>`).join('')}<ul>${(s.bullets || []).map((b) => `<li>${esc(b.replace(/^\[ \] /, '☐ '))}</li>`).join('')}</ul>`)
    .join('')
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>What-if brief</title><style>
    body{font:13px/1.5 system-ui,sans-serif;color:#111;margin:32px;max-width:820px} h1{font-size:20px} h2{font-size:15px;margin-top:20px;border-bottom:1px solid #ddd;padding-bottom:4px}
    table{border-collapse:collapse;width:100%;font-size:12px} td,th{border:1px solid #ccc;padding:4px 6px;text-align:left} .muted{color:#666}</style></head><body>
    <h1>What-if brief: ${esc(run.question || run.evidence.scenario.descriptions.join('; '))}</h1>
    <p class="muted">All figures simulated by the AEGIS engine. Confidence: ${esc(run.confidence)}. Narrative: ${esc(run.narrative_source)}.</p>
    ${sections}<h2>Candidate plans (evidence)</h2><table><tr><th>Plan</th><th>Cost</th><th>Unmet</th><th>Avg delay (d)</th><th>Recovery (d)</th><th>CO2 (t)</th><th>Safety</th><th>Total cost</th></tr>${plans}</table>
    <script>window.onload=()=>window.print()</script></body></html>`)
  w.document.close()
  return true
}

function PlansTab({ run }) {
  const rows = useMemo(() => run.plans.map((p) => ({ ...p, id: p.name })), [run])
  return (
    <div className="space-y-3 py-3">
      <p className="px-4 text-xs text-fg-2">
        Recommendation rule: {run.evidence.selection_rule} Pareto = no other plan is both cheaper and leaves fewer units unmet.
      </p>
      <DataTable
        label="Candidate recovery plans"
        rows={rows}
        columnMenu={false}
        columns={[
          {
            key: 'label', header: 'Plan',
            render: (p) => (
              <span className="flex items-center gap-1.5">
                <span className="text-fg">{p.label}</span>
                {p.recommended && <Badge tone="accent">Recommended</Badge>}
                {p.pareto && !p.recommended && <Badge>Pareto</Badge>}
              </span>
            ),
          },
          { key: 'cost', header: 'Cost', align: 'right', render: (p) => p.cost_display },
          { key: 'unmet', header: 'Unmet', align: 'right', render: (p) => p.unmet_display },
          { key: 'delay_avg_days', header: 'Delay', align: 'right', render: (p) => `${fmtNum(p.delay_avg_days, 2)} d` },
          { key: 'recovery_days', header: 'Recovers', align: 'right', render: (p) => `${p.recovery_days} d` },
          { key: 'co2_t', header: 'CO₂ t', align: 'right', render: (p) => fmtNum(p.co2_t, 1) },
          { key: 'residual_risk', header: 'Residual risk', align: 'right', render: (p) => (p.residual_risk == null ? '–' : `${Math.round(p.residual_risk * 100)}%`) },
          { key: 'safety', header: 'Fix-safety', value: (p) => (p.safety.passed ? 1 : 0), render: (p) => <StatusDot status={p.safety.passed ? 'ok' : 'bad'} label={p.safety.passed ? 'Pass' : 'Fails'} /> },
          { key: 'objective', header: 'Total cost', align: 'right', render: (p) => p.objective_display },
        ]}
      />
      <div className="px-4">
        <CostScatter strategies={run.plans.map((p) => ({ ...p, name: p.label, safety_check: p.safety }))} />
      </div>
    </div>
  )
}

function AskTab({ run }) {
  const { whatifAsks, askWhatIf, loading, errors } = useStore()
  const [q, setQ] = useState('')
  const send = async (text) => {
    if (!text.trim()) return
    setQ('')
    await askWhatIf(run.id, text.trim())
  }
  return (
    <div className="space-y-3 px-4 py-3">
      <p className="text-xs text-fg-2">
        Follow-up questions are answered by running one of three engine functions (compare plans, run a plan, change the scenario). Anything else is
        declined.
      </p>
      <div className="flex flex-wrap gap-1.5">
        {FOLLOW_UPS.map((f) => (
          <Button key={f} size="xs" variant="secondary" disabled={loading.whatifAsk} onClick={() => send(f)}>
            {f}
          </Button>
        ))}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          send(q)
        }}
      >
        <Textarea rows={1} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a follow-up, e.g. What if S1 also fails for 5 days?" className="h-8 min-h-8 flex-1" aria-label="Follow-up question" />
        <Button type="submit" variant="primary" icon={Send} disabled={loading.whatifAsk || !q.trim()}>
          {loading.whatifAsk ? 'Running…' : 'Ask'}
        </Button>
      </form>
      <InlineError message={errors.whatifAsk} />
      <ol className="space-y-2">
        {[...whatifAsks].reverse().map((a, i) => (
          <li key={i} className="space-y-1.5 rounded-md border border-border p-3">
            <div className="flex items-center gap-2 text-sm font-medium text-fg">
              {a.question}
              <span className="ml-auto">{a.declined ? <Badge tone="bad">Declined</Badge> : <Badge>{a.tool?.name}</Badge>}</span>
            </div>
            <ul className="space-y-1 text-sm text-fg-2">
              {a.answer.map((t, j) => (
                <li key={j}>{t}</li>
              ))}
            </ul>
            {a.evidence && <Evidence data={{ tool_call: a.tool, ...a.evidence }} />}
          </li>
        ))}
      </ol>
    </div>
  )
}

function HistoryTab() {
  const { whatifHistory, loadWhatIfHistory, openWhatIf, whatif } = useStore()
  const [picked, setPicked] = useState([])
  const [cmp, setCmp] = useState({ data: null, error: null, loading: false })
  useEffect(() => {
    loadWhatIfHistory()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const toggle = (id) => setPicked((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : cur.length >= 4 ? cur : [...cur, id]))
  const compare = async () => {
    setCmp({ data: null, error: null, loading: true })
    try {
      setCmp({ data: await api.whatifCompare(picked), error: null, loading: false })
    } catch (err) {
      setCmp({ data: null, error: errorMessage(err), loading: false })
    }
  }
  const runs = whatifHistory ?? []
  const show = (v) => (typeof v === 'number' ? (Math.abs(v) >= 1e5 ? fmtINR(v) : fmtNum(v, 2)) : (v ?? '–'))
  return (
    <div className="space-y-3 px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="text-xs text-fg-muted">Pick 2-4 runs to compare side by side.</span>
        <Button size="sm" icon={GitCompare} className="ml-auto" disabled={picked.length < 2 || cmp.loading} onClick={compare}>
          Compare {picked.length || ''}
        </Button>
      </div>
      {!runs.length && <p className="text-xs text-fg-muted">No runs yet.</p>}
      <ul className="divide-y divide-border rounded-md border border-border">
        {runs.map((r) => (
          <li key={r.id} className="flex items-center gap-3 px-3 py-2 text-sm">
            <Checkbox checked={picked.includes(r.id)} onChange={() => toggle(r.id)} aria-label={`Compare ${r.label}`} />
            <button type="button" className="min-w-0 flex-1 truncate text-left text-fg hover:underline" onClick={() => openWhatIf(r.id)} title={r.label}>
              {r.label}
            </button>
            {r.id === whatif?.id && <Badge tone="accent">Open</Badge>}
            {r.stale && <Badge>Older network</Badge>}
            <span className="num text-xs text-fg-muted">{fmtNum(r.unmet_units)} u</span>
            <span className="text-xs text-fg-muted">{r.recommended}</span>
          </li>
        ))}
      </ul>
      <InlineError message={cmp.error} />
      {cmp.data && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="border-b border-border px-3 py-2 text-left font-medium text-fg-muted">Metric (simulated)</th>
                {cmp.data.runs.map((r) => (
                  <th key={r.id} className="max-w-[14rem] truncate border-b border-border px-3 py-2 text-left font-medium text-fg" title={r.label}>
                    {r.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cmp.data.metrics.map((m) => (
                <tr key={m.key}>
                  <td className="border-b border-border/60 px-3 py-1.5 text-fg-2">{m.label}</td>
                  {m.values.map((v, i) => (
                    <td key={i} className="num border-b border-border/60 px-3 py-1.5 text-fg">
                      {m.key === 'p_shortage' && typeof v === 'number' ? `${Math.round(v * 100)}%` : show(v)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function WhatIfPage() {
  const { whatif, runWhatIf, loading, errors, events, whatifDraft, clearWhatIfDraft, network, source, setTab } = useStore()
  const toast = useToast()
  const runnable = !source || source.runnable
  const [text, setText] = useState(EXAMPLES[0])
  const [useEvents, setUseEvents] = useState(null) // structured events to run instead of text
  const [mcRuns, setMcRuns] = useState('100')
  const [robust, setRobust] = useState('10')
  const [tab, setTab_] = useState('brief')

  useEffect(() => {
    if (!whatifDraft) return
    if (whatifDraft.events) {
      setUseEvents(whatifDraft.events)
      setText(whatifDraft.text || '')
    } else {
      setUseEvents(null)
      setText(whatifDraft.text || '')
    }
  }, [whatifDraft])

  const run = async () => {
    const body = { mc_runs: Number(mcRuns), robustness_runs: Number(robust) }
    if (useEvents?.length) Object.assign(body, { events: useEvents, text: text.trim().length >= 3 ? text.trim() : undefined })
    else body.text = text.trim()
    const res = await runWhatIf(body)
    if (res?.status === 'ok') {
      setTab_('brief')
      toast('What-if analysed', { description: `Recommended: ${res.plans.find((p) => p.recommended)?.label} · confidence ${res.confidence}` })
    }
  }

  const r = whatif?.status === 'ok' ? whatif : null
  const imp = r?.evidence.impact
  const rec = r?.plans.find((p) => p.recommended)
  const peak = useMemo(() => (r ? peakDisruption(network, r.events) : null), [network, r])
  const cascadeNodes = useMemo(() => (r ? [...new Set(r.evidence.cascade.flatMap((c) => c.nodes))] : null), [r])
  const preview = r?.evidence.surrogate_preview

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1400px] space-y-3 p-4">
        <Panel>
          <PanelHeader title="What-if recovery planner" meta="Exact simulator + Monte Carlo + recovery optimiser; every figure is simulated" />
          <div className="space-y-3 px-4 py-3">
            {whatifDraft?.note && (
              <Notice action={<Button size="sm" variant="ghost" onClick={clearWhatIfDraft}>Dismiss</Button>}>{whatifDraft.note}</Notice>
            )}
            <Textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} aria-label="What-if question" placeholder="What if Supplier S2 fails for 10 days?" />
            <div className="flex flex-wrap items-center gap-1.5">
              {EXAMPLES.map((e) => (
                <Button key={e} size="xs" variant="ghost" onClick={() => (setText(e), setUseEvents(null))}>
                  {e}
                </Button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {useEvents ? (
                <span className="flex flex-wrap items-center gap-1.5 text-xs text-fg-2">
                  Structured scenario:
                  {useEvents.map((e, i) => (
                    <Badge key={i}>
                      {eventLabel(e)} <span className="num text-fg-muted">d{e.start}+{e.duration}</span>
                    </Badge>
                  ))}
                  <Button size="xs" variant="ghost" onClick={() => setUseEvents(null)}>
                    Use the question instead
                  </Button>
                </span>
              ) : (
                <Button size="sm" variant="ghost" disabled={!events.length} onClick={() => setUseEvents(events)} title="Use the scenario built on the Simulate page">
                  Use the Simulate scenario ({events.length} event{events.length === 1 ? '' : 's'})
                </Button>
              )}
              <label className="ml-auto flex items-center gap-1.5 text-xs text-fg-muted">
                Monte Carlo
                <Select size="sm" value={mcRuns} onChange={(e) => setMcRuns(e.target.value)} className="w-20">
                  {['50', '100', '200'].map((v) => <option key={v} value={v}>{v}</option>)}
                </Select>
              </label>
              <label className="flex items-center gap-1.5 text-xs text-fg-muted">
                Robustness runs
                <Select size="sm" value={robust} onChange={(e) => setRobust(e.target.value)} className="w-20">
                  {['0', '10', '20'].map((v) => <option key={v} value={v}>{v}</option>)}
                </Select>
              </label>
              <Button variant="primary" icon={Play} disabled={!runnable || loading.whatif || (!useEvents && text.trim().length < 3)} onClick={run}>
                {loading.whatif ? 'Analysing…' : 'Run what-if'}
              </Button>
            </div>
            <InlineError message={errors.whatif} />
          </div>
        </Panel>

        {!runnable && (
          <Panel>
            <EmptyState title="The active network can't be planned for" description="Fix its validation errors on the Data page first." action={<Button onClick={() => setTab('data')}>Open the Data page</Button>} />
          </Panel>
        )}
        {loading.whatif && (
          <Panel>
            <SkeletonRows rows={6} label="Simulating the baseline and scenario, Monte Carlo, every recovery plan, counterfactuals and sensitivity" />
          </Panel>
        )}
        {whatif && whatif.status !== 'ok' && !loading.whatif && <Notice>{whatif.note}</Notice>}

        {r && !loading.whatif && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-medium text-fg">{r.question || r.evidence.scenario.descriptions.join('; ')}</h2>
              <StatusDot status={CONF_TONE[r.confidence]} label={`Confidence: ${r.confidence}`} />
              <span className="text-xs text-fg-muted">parsed by {r.evidence.scenario.parser} · {r.elapsed_s}s</span>
              <div className="ml-auto flex gap-2">
                <Button size="sm" icon={FileDown} onClick={() => downloadText(`whatif-${r.id}.md`, r.brief_markdown, 'text/markdown')}>
                  Markdown
                </Button>
                <Button size="sm" icon={Printer} onClick={() => printBrief(r) || toast('Allow pop-ups to print the brief')}>
                  PDF
                </Button>
              </div>
            </div>
            <KpiStrip
              label="What-if impact (simulated)"
              items={[
                { key: 'unmet', label: 'Unmet demand (simulated)', value: imp.unmet_units_display, unit: 'units', sub: `${imp.unmet_pct.toFixed(2)}% of ${imp.horizon_days}-day demand` },
                { key: 'stock', label: 'First stock-out', value: imp.first_stockout ? `day ${imp.first_stockout.day}` : 'none', sub: imp.first_stockout ? imp.first_stockout.node : `within ${imp.horizon_days} days` },
                { key: 'rev', label: 'Revenue at risk', value: imp.revenue_at_risk_display, sub: `MC P90 ${r.evidence.monte_carlo.p90_display} units` },
                { key: 'delay', label: 'Avg extra delay', value: imp.delay.avg_days.toFixed(2), unit: 'days', sub: `P90 ${imp.delay.p90_days.toFixed(2)} days` },
                { key: 'rec', label: 'Recommended', value: rec?.label, sub: `${rec?.objective_display} total · saves ${r.evidence.net_saving_display}`, status: CONF_TONE[r.confidence] },
              ]}
            />
            <Panel className="overflow-hidden">
              <Tabs
                idBase="whatif"
                label="What-if result"
                value={tab}
                onChange={setTab_}
                className="px-4"
                tabs={[
                  { value: 'brief', label: 'Brief' },
                  { value: 'plans', label: 'Plans', count: r.plans.length },
                  { value: 'ask', label: 'Ask a follow-up' },
                  { value: 'map', label: 'Map' },
                  { value: 'history', label: 'History & compare' },
                ]}
              />
              <TabPanel idBase="whatif" value={tab}>
                {tab === 'brief' && (
                  <div className="grid gap-3 p-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                    <Sections sections={r.sections} source={r.narrative_source} rejected={r.narrative_rejected} />
                    <aside className="space-y-3">
                      <Panel className="space-y-2 px-3 py-3">
                        <SectionLabel>Fast ML preview</SectionLabel>
                        {preview?.predicted ? (
                          <>
                            <p className="text-xs text-fg-2">
                              Surrogate: <span className="num text-fg">{preview.predicted.unmet_pct.point.toFixed(2)}%</span> unmet (80% interval{' '}
                              <span className="num">{preview.predicted.unmet_pct.low.toFixed(2)}–{preview.predicted.unmet_pct.high.toFixed(2)}%</span>) in{' '}
                              <span className="num">{preview.ms} ms</span>; exact simulator <span className="num text-fg">{imp.unmet_pct.toFixed(2)}%</span>.
                            </p>
                            <ul className="space-y-1 text-2xs text-fg-2">
                              {preview.drivers.map((d, i) => (
                                <li key={i}>{d}</li>
                              ))}
                            </ul>
                            <p className="text-2xs text-fg-muted">{preview.note}</p>
                          </>
                        ) : (
                          <p className="text-xs text-fg-muted">{preview?.error || 'Surrogate unavailable; exact results only.'}</p>
                        )}
                      </Panel>
                      <Panel className="space-y-2 px-3 py-3">
                        <SectionLabel>Unmet demand by day (simulated)</SectionLabel>
                        <ol className="flex h-20 items-end gap-px" aria-label="Unmet units per day">
                          {r.timeline.map((d) => {
                            const max = Math.max(1, ...r.timeline.map((x) => x.unmet))
                            return <li key={d.day} title={`Day ${d.day}: ${fmtNum(d.unmet)} units`} className="flex-1 rounded-t-sm bg-bad/70" style={{ height: `${(100 * d.unmet) / max}%` }} />
                          })}
                        </ol>
                        <p className="text-2xs text-fg-muted">With the network's automatic response; plans in the Plans tab reduce this further.</p>
                      </Panel>
                    </aside>
                  </div>
                )}
                {tab === 'plans' && <PlansTab run={r} />}
                {tab === 'ask' && <AskTab run={r} />}
                {tab === 'map' && (
                  <div className="relative h-[520px]">
                    <NetworkCanvas disrupted={peak} highlight={cascadeNodes} view3d={{ mode: 'after', disruptedAll: peak }} />
                  </div>
                )}
                {tab === 'history' && <HistoryTab />}
              </TabPanel>
            </Panel>
          </>
        )}
        {!whatif && !loading.whatif && runnable && (
          <Panel>
            <EmptyState title="Ask a what-if question" description="Plain English or the Simulate scenario. The planner simulates it exactly, compares every recovery plan, and explains the choice from the evidence." />
          </Panel>
        )}
      </div>
    </div>
  )
}
