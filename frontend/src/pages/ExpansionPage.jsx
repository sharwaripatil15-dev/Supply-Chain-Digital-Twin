import { useEffect, useMemo, useState } from 'react'
import { CircleHelp, Lightbulb, Play, Plus, Sparkles, Square, Waypoints } from 'lucide-react'
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip as ChartTip, XAxis, YAxis, ZAxis } from 'recharts'
import { api, errorMessage } from '../api.js'
import { useStore } from '../store.js'
import { useTokens } from '../theme.jsx'
import { fmtINR, fmtNum } from '../format.js'
import { ChartTooltip, axisProps, gridProps } from '../lib/chart.jsx'
import { downloadText } from '../lib/download.js'
import { toCsv } from '../lib/csv.js'
import {
  Badge, Button, Checkbox, Dialog, EmptyState, Field, InlineError, Input, Meter, Panel, PanelHeader, SectionLabel, SegmentedControl,
  Select, TabPanel, Tabs, useToast,
} from '../components/ui/index.js'
import NetworkCanvas from '../components/canvas/NetworkCanvas.jsx'
import Evidence from '../components/reasoning/Evidence.jsx'
import { Term } from '../components/Glossary.jsx'

const GOALS = [
  { value: 'cost', label: 'Cost' },
  { value: 'service', label: 'Service' },
  { value: 'resilience', label: 'Resilience' },
  { value: 'balanced', label: 'Balanced' },
]
const delta = (a, b, digits = 1, unit = '') => `${fmtNum(a, digits)}${unit} → ${fmtNum(b, digits)}${unit}`

function HowItWorks({ open, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} title="How the expansion planner works" className="max-w-lg"
      footer={<Button variant="primary" onClick={onClose}>Got it</Button>}>
      <div className="space-y-3 px-5 py-3 text-sm text-fg-2">
        <p>
          <span className="font-medium text-fg">1. Dijkstra finds routes, not locations.</span> We build a transport graph over your sites and every
          candidate city (each point linked to its nearest neighbours by the best of road, rail, sea or air) and run Dijkstra from every candidate. That gives
          the cheapest path, its lead time and CO₂ from each candidate to each customer and from your suppliers and plants to the candidate.
        </p>
        <p>
          <span className="font-medium text-fg">2. An optimiser chooses the sites.</span> A facility-location model (mixed-integer program) picks which candidates
          to open and which customers each serves, minimising yearly fixed cost + freight + holding + lost sales (+ CO₂), within your budget, lead-time limit and
          site counts. A greedy heuristic double-checks the answer.
        </p>
        <p>
          <span className="font-medium text-fg">3. The digital twin checks every plan.</span> Each plan is added to a copy of your network; the simulator recomputes
          service, lead time and cost, and Chaos Finder recomputes resilience. Your live network is not changed until you press Add to network.
        </p>
        <p className="text-xs text-fg-muted">Site costs use illustrative indices; replace them with your own data. All results are simulated.</p>
      </div>
    </Dialog>
  )
}

function ParetoChart({ plans }) {
  const t = useTokens()
  const rows = plans.map((p) => ({ name: p.label, cost: p.total_cost_change_inr, service: p.service_level_after_pct, res: p.resilience_after }))
  return (
    <div>
      <p className="mb-1 text-xs text-fg-muted">Cost change per year vs service level; bubble size = resilience. Up and left is better.</p>
      <ResponsiveContainer width="100%" height={200}>
        <ScatterChart margin={{ top: 10, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid {...gridProps(t)} />
          <XAxis type="number" dataKey="cost" name="Cost change" tickFormatter={fmtINR} {...axisProps(t)} />
          <YAxis type="number" dataKey="service" name="Service" domain={['auto', 100]} tickFormatter={(v) => `${fmtNum(v, 1)}%`} {...axisProps(t)} />
          <ZAxis type="number" dataKey="res" range={[60, 260]} />
          <ChartTip content={<ChartTooltip render={(r) => <><div className="text-fg">{r.name}</div><div className="num text-fg-muted">{fmtINR(r.cost)}/yr · {fmtNum(r.service, 1)}% service · resilience {fmtNum(r.res, 1)}</div></>} />} />
          <Scatter data={rows} fill={t.color.accent} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

function PlanDetail({ plan, onApply, onWhatIf, busy, stale }) {
  return (
    <div className="space-y-4 px-4 py-3 text-sm">
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" icon={Plus} disabled={busy || stale} onClick={() => onApply(plan)} title={stale ? 'The network changed since this run' : 'Adds the sites and lanes; undo with Ctrl+Z'}>
          Add to network
        </Button>
        <Button icon={Lightbulb} disabled={busy || stale} onClick={() => onWhatIf(plan)}>
          Run what-if on this plan
        </Button>
      </div>
      <ol className="space-y-2">
        {plan.sites.map((s, i) => (
          <li key={s.node_id} className="rounded-md border border-border p-2.5">
            <div className="flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent text-2xs font-semibold text-accent-fg">{i + 1}</span>
              <span className="font-medium text-fg">{s.name}</span>
              <Badge>{s.kind}</Badge>
              <span className="num ml-auto text-xs text-fg-muted">{s.build_cost_display}</span>
            </div>
            <p className="mt-1.5 text-xs text-fg-2">{s.rationale}</p>
          </li>
        ))}
      </ol>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
        <dt className="text-fg-muted">Build cost</dt>
        <dd className="num text-fg">{plan.build_cost_display}</dd>
        <dt className="text-fg-muted">Annual savings</dt>
        <dd className="num text-fg">{plan.annual_savings_display}</dd>
        <dt className="text-fg-muted">Payback</dt>
        <dd className="num text-fg">{plan.payback_years ? `${fmtNum(plan.payback_years, 1)} years` : 'does not pay back'}</dd>
        <dt className="text-fg-muted">Total cost change / year</dt>
        <dd className="num text-fg">{plan.total_cost_change_display}</dd>
        <dt className="text-fg-muted"><Term id="service_level">Service level</Term></dt>
        <dd className="num text-fg">{delta(plan.service_level_before_pct, plan.service_level_after_pct, 1, '%')}</dd>
        <dt className="text-fg-muted">Avg lead time</dt>
        <dd className="num text-fg">{delta(plan.avg_lead_before_days, plan.avg_lead_after_days, 1, ' d')}</dd>
        <dt className="text-fg-muted">CO₂ per year</dt>
        <dd className="num text-fg">{delta(plan.co2_before_t_per_year, plan.co2_after_t_per_year, 0, ' t')}</dd>
        <dt className="text-fg-muted"><Term id="resilience">Resilience</Term></dt>
        <dd className="num text-fg">{delta(plan.resilience_before, plan.resilience_after)}</dd>
        <dt className="text-fg-muted"><Term id="health">Health Score</Term></dt>
        <dd className="num text-fg">{delta(plan.health_before, plan.health_after)}</dd>
        <dt className="text-fg-muted"><Term id="spof">Single points of failure</Term> removed</dt>
        <dd className="num text-fg">{plan.spof_removed.length ? plan.spof_removed.join(', ') : 'none'}</dd>
      </dl>
      <section>
        <SectionLabel className="mb-1">Sensitivity</SectionLabel>
        <ul className="space-y-0.5 text-xs text-fg-2">
          {plan.sensitivity.map((s) => (
            <li key={s.variant}>
              {s.variant}: savings {s.annual_savings_display}/yr, payback {s.payback_years ? `${fmtNum(s.payback_years, 1)} y` : 'none'}, service{' '}
              {fmtNum(s.service_level_before_pct, 1)}% → {fmtNum(s.service_level_pct, 1)}%
            </li>
          ))}
        </ul>
      </section>
      <section>
        <SectionLabel className="mb-1">Example routes (Dijkstra)</SectionLabel>
        <ul className="space-y-1 text-xs text-fg-2">
          {plan.sites.flatMap((s) => s.example_paths).map((p) => (
            <li key={p.lane}>
              <span className="font-medium text-fg">{p.lane}</span>:{' '}
              {p.hops[0]?.from}
              {p.hops.map((h, i) => (
                <span key={i}>
                  {' → '}
                  {h.to} <span className="text-fg-muted">({h.mode}, {fmtNum(h.km)} km, {fmtNum(h.lead_days, 1)} d)</span>
                </span>
              ))}
            </li>
          ))}
        </ul>
      </section>
      <Evidence data={{ plan }} />
    </div>
  )
}

export default function ExpansionPage() {
  const { expansion, runExpansion, cancelExpansion, loadExpansionLatest, applyExpansion, setWhatIfDraft, loading, errors, source, network, setTab } = useStore()
  const toast = useToast()
  const runnable = !source || source.runnable
  const [help, setHelp] = useState(false)
  const [form, setForm] = useState({ goal: 'balanced', types: ['warehouse', 'factory'], n_add: 1, budget: '', max_lead_days: 7, weather: false, co2: false, growth: 15, redundancy: false })
  const [cands, setCands] = useState(null)
  const [custom, setCustom] = useState({ name: '', lat: '', lon: '', cost: '', capacity: '' })
  const [candErr, setCandErr] = useState(null)
  const [planTab, setPlanTab] = useState(null)
  const [busy, setBusy] = useState(false)
  const [focusSite, setFocusSite] = useState(null)

  const loadCands = () => api.expansionCandidates().then(setCands).catch((e) => setCandErr(errorMessage(e)))
  useEffect(() => {
    loadCands()
    if (!expansion) loadExpansionLatest()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const editCands = async (body) => {
    setCandErr(null)
    try {
      setCands(await api.expansionEditCandidates(body))
    } catch (e) {
      setCandErr(errorMessage(e))
    }
  }

  const done = expansion?.status === 'ok' ? expansion : null
  const running = expansion?.status === 'running'
  const plans = done?.plans ?? []
  const plan = plans.find((p) => p.id === planTab) || plans[0]
  const stale = done && source && (done.network?.version !== source.version || done.network?.source !== source.source)

  const ghost = useMemo(() => {
    const kind = form.types[0] || 'warehouse'
    const picked = new Map((plan?.sites ?? []).map((s, i) => [s.candidate, { ...s, rank: i + 1 }]))
    const nodes = (cands?.sites ?? []).filter((s) => !s.excluded && !picked.has(s.id)).map((s) => ({ id: `cand:${s.id}`, kind, name: s.name, lat: s.lat, lon: s.lon }))
    for (const [cid, s] of picked) nodes.push({ id: s.node_id, kind: s.kind, name: s.name, lat: s.lat, lon: s.lon, rank: s.rank, candidate: cid })
    const edges = stale ? [] : (plan?.additions.edges ?? []).map((e) => ({ source: e.source, target: e.target, capacity: e.capacity }))
    return { nodes, edges }
  }, [cands, plan, form.types, stale])

  const run = () => {
    const body = {
      goal: form.goal, types: form.types, n_add: Number(form.n_add), max_lead_days: Number(form.max_lead_days) || 7, weather: form.weather,
      co2: form.co2, growth: (Number(form.growth) || 0) / 100, redundancy: form.redundancy,
      budget: form.budget === '' ? null : Number(form.budget) * 1e7,
    }
    setPlanTab(null)
    runExpansion(body).then((res) => {
      if (res?.status === 'ok') toast('Expansion plans ready', { description: `${res.plans.length} plans in ${res.elapsed_s}s · top: ${res.plans[0].sites.map((s) => s.name).join(', ')}` })
    })
  }
  const apply = async (p) => {
    setBusy(true)
    const res = await applyExpansion(p.id, `Add ${p.label.toLowerCase()} expansion plan`)
    setBusy(false)
    if (res.ok) toast('Plan added to the network', { description: `${res.data.added_nodes.length} site(s), ${res.data.added_edges.length} lane(s). Undo with Ctrl+Z on the Data page.` })
    else toast('Could not add the plan', { tone: 'error', description: res.error })
    return res
  }
  const whatIf = async (p) => {
    const res = await apply(p)
    if (!res.ok) return
    const target = p.spof_after[0] || p.spof_before[0]
    setWhatIfDraft({
      text: target ? `What if ${target} fails for 7 days?` : 'What if demand rises 20% for 10 days?',
      note: `The ${p.label.toLowerCase()} plan (${p.sites.map((s) => s.name).join(', ')}) was added to the network. This what-if tests how it copes with its biggest remaining risk; undo the plan on the Data page if you only wanted a preview.`,
    })
  }
  const set = (k) => (e) => setForm({ ...form, [k]: e?.target ? (e.target.type === 'checkbox' ? e.target.checked : e.target.value) : e })
  const toggleType = (t) => setForm((f) => ({ ...f, types: f.types.includes(t) ? f.types.filter((x) => x !== t) : [...f.types, t] }))
  const active = (cands?.sites ?? []).filter((s) => !s.excluded)

  return (
    <div className="flex h-full min-h-[680px] gap-3 p-4">
      <HowItWorks open={help} onClose={() => setHelp(false)} />
      <Panel className="flex w-[300px] shrink-0 flex-col overflow-hidden">
        <PanelHeader title="Plan inputs" actions={<Button size="xs" variant="ghost" icon={CircleHelp} onClick={() => setHelp(true)}>How this works</Button>} />
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          <Field label="Goal">
            <SegmentedControl size="xs" label="Goal" value={form.goal} onChange={set('goal')} options={GOALS} />
          </Field>
          <Field label="Facility types">
            <div className="flex gap-3">
              <Checkbox label="Warehouse" checked={form.types.includes('warehouse')} onChange={() => toggleType('warehouse')} />
              <Checkbox label="Factory" checked={form.types.includes('factory')} onChange={() => toggleType('factory')} />
            </div>
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Sites to add" htmlFor="x-n">
              <Select id="x-n" size="sm" value={form.n_add} onChange={set('n_add')}>
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </Select>
            </Field>
            <Field label="Budget (₹ Cr)" htmlFor="x-b" hint="blank = no limit">
              <Input id="x-b" size="sm" type="number" min={0} value={form.budget} onChange={set('budget')} />
            </Field>
            <Field label="Max lead (days)" htmlFor="x-l">
              <Input id="x-l" size="sm" type="number" min={1} max={60} value={form.max_lead_days} onChange={set('max_lead_days')} />
            </Field>
            <Field label="Demand growth (%)" htmlFor="x-g">
              <Input id="x-g" size="sm" type="number" min={-50} max={200} value={form.growth} onChange={set('growth')} />
            </Field>
          </div>
          <div className="flex flex-col gap-1.5">
            <Checkbox label="Penalise weather / flood exposure" checked={form.weather} onChange={set('weather')} />
            <Checkbox label="Put a price on CO₂" checked={form.co2} onChange={set('co2')} />
            <Checkbox label="Require 2 sources per customer" checked={form.redundancy} onChange={set('redundancy')} />
          </div>
          <section className="space-y-1.5">
            <SectionLabel>Candidate sites ({active.length})</SectionLabel>
            <div className="flex gap-2">
              <Button size="xs" icon={Sparkles} disabled={!runnable} onClick={() => editCands({ action: 'auto', n: 4 })} title="Cluster underserved, costly-to-serve demand and snap to the nearest library city">
                Auto-generate
              </Button>
              <Button size="xs" variant="ghost" onClick={() => editCands({ action: 'reset' })}>Reset</Button>
            </div>
            <details className="rounded-md border border-border px-2 py-1.5 text-xs">
              <summary className="cursor-pointer text-fg-2">Add a custom site</summary>
              <div className="mt-2 grid grid-cols-2 gap-1.5">
                <Input size="sm" placeholder="Name" aria-label="Site name" value={custom.name} onChange={(e) => setCustom({ ...custom, name: e.target.value })} className="col-span-2" />
                <Input size="sm" type="number" placeholder="Latitude" aria-label="Latitude" value={custom.lat} onChange={(e) => setCustom({ ...custom, lat: e.target.value })} />
                <Input size="sm" type="number" placeholder="Longitude" aria-label="Longitude" value={custom.lon} onChange={(e) => setCustom({ ...custom, lon: e.target.value })} />
                <Input size="sm" type="number" placeholder="Build cost ₹ Cr" aria-label="Build cost in crore" value={custom.cost} onChange={(e) => setCustom({ ...custom, cost: e.target.value })} />
                <Input size="sm" type="number" placeholder="Capacity /day" aria-label="Capacity units per day" value={custom.capacity} onChange={(e) => setCustom({ ...custom, capacity: e.target.value })} />
                <Button
                  size="xs"
                  className="col-span-2"
                  disabled={!custom.name || custom.lat === '' || custom.lon === ''}
                  onClick={() =>
                    editCands({ action: 'add', name: custom.name, lat: Number(custom.lat), lon: Number(custom.lon), fixed_cost: custom.cost ? Number(custom.cost) * 1e7 : null, capacity: custom.capacity ? Number(custom.capacity) : null }).then(() =>
                      setCustom({ name: '', lat: '', lon: '', cost: '', capacity: '' }),
                    )
                  }
                >
                  Add site
                </Button>
              </div>
            </details>
            <ul className="max-h-48 space-y-0.5 overflow-y-auto text-xs" aria-label="Candidate sites">
              {(cands?.sites ?? []).map((s) => (
                <li key={s.id} className="flex items-center gap-2">
                  <Checkbox
                    checked={!s.excluded}
                    onChange={() => editCands({ action: s.excluded ? 'include' : 'exclude', id: s.id })}
                    aria-label={`${s.excluded ? 'Include' : 'Exclude'} ${s.name}`}
                  />
                  <span className={s.excluded ? 'text-fg-muted line-through' : 'text-fg-2'}>{s.name}</span>
                  {s.source !== 'library' && <Badge>{s.source}</Badge>}
                </li>
              ))}
            </ul>
            <p className="text-2xs text-fg-muted">{cands?.note}</p>
            <InlineError message={candErr} />
          </section>
        </div>
        <div className="space-y-2 border-t border-border p-3">
          {running ? (
            <>
              <Meter value={expansion.progress.done} max={expansion.progress.total} tone="accent" label="Planner progress" />
              <p className="text-xs text-fg-muted" role="status">{expansion.progress.step}…</p>
              <Button className="w-full" icon={Square} onClick={cancelExpansion}>Cancel</Button>
            </>
          ) : (
            <Button variant="primary" className="w-full" icon={Play} disabled={!runnable || !form.types.length || loading.expansion} onClick={run}>
              Find the best sites
            </Button>
          )}
          <InlineError message={errors.expansion || (['error', 'cancelled'].includes(expansion?.status) ? expansion.detail : null)} />
        </div>
      </Panel>

      <Panel className="relative min-w-0 flex-1 overflow-hidden">
        <NetworkCanvas
          ghost={ghost}
          onGhost={(id) => setFocusSite(id)}
          highlight={plan && !stale ? plan.sites.map((s) => s.node_id) : null}
        />
        {focusSite && (
          <div className="absolute right-3 top-14 z-10 max-w-[240px] rounded-md border border-border bg-surface p-2.5 text-xs shadow-float">
            {(() => {
              const s = (cands?.sites ?? []).find((c) => `cand:${c.id}` === focusSite) || plan?.sites.find((x) => x.node_id === focusSite)
              const m = done?.marginal_values.find((v) => v.site === (s?.id || s?.candidate))
              return s ? (
                <>
                  <div className="font-medium text-fg">{s.name}</div>
                  {m && <div className="text-fg-2">Value if opened alone: {m.annual_value_display}/yr · build {m.build_cost_display}</div>}
                  {s.flood_exposure != null && <div className="text-fg-muted">Flood {Math.round(s.flood_exposure * 100)}% · seismic {Math.round(s.seismic_exposure * 100)}% · hub {Math.round(s.hub_quality * 100)}%</div>}
                  <button type="button" className="mt-1 text-fg-muted underline" onClick={() => setFocusSite(null)}>Close</button>
                </>
              ) : null
            })()}
          </div>
        )}
        <div className="pointer-events-none absolute bottom-3 right-3 z-10 rounded-md border border-border bg-surface/90 px-2 py-1 text-2xs text-fg-muted">
          <Waypoints className="mr-1 inline h-3 w-3" aria-hidden />
          Faint dashed nodes = candidate sites · numbered = recommended · dashed lanes = proposed
        </div>
      </Panel>

      <Panel className="flex w-[400px] shrink-0 flex-col overflow-hidden xl:w-[440px]">
        <PanelHeader title="Plans" meta={done ? `${done.candidates_considered} candidates · ${done.elapsed_s}s · simulated` : null} />
        <div className="min-h-0 flex-1 overflow-y-auto">
          {!done && !running && (
            <EmptyState title="Find where to expand" description="One click runs Dijkstra routing, a facility-location optimiser and a resilience check on a copy of your network." />
          )}
          {expansion?.status === 'infeasible' && <div className="p-4"><InlineError message={expansion.explanation} /></div>}
          {done && (
            <>
              {stale && <p className="mx-4 mt-3 rounded-md bg-warn/10 px-2 py-1.5 text-xs text-warn">Computed for an earlier version of the network. Run again to refresh.</p>}
              <p className="px-4 pt-3 text-sm text-fg-2">{done.summary}</p>
              <Tabs idBase="xplan" label="Plans" value={plan?.id} onChange={setPlanTab} className="px-4" tabs={plans.map((p, i) => ({ value: p.id, label: i === 0 ? `${p.label} ★` : p.label }))} />
              <TabPanel idBase="xplan" value={plan?.id}>{plan && <PlanDetail plan={plan} onApply={apply} onWhatIf={whatIf} busy={busy || loading.builder} stale={stale} />}</TabPanel>
              <section className="space-y-2 border-t border-border px-4 py-3">
                <div className="flex items-center">
                  <SectionLabel>Comparison</SectionLabel>
                  <Button size="xs" variant="ghost" className="ml-auto" onClick={() => downloadText('expansion-plans.csv', toCsv(plans.map((p) => ({ plan: p.label, sites: p.sites.map((s) => `${s.name} ${s.kind}`).join('; '), build_cost_inr: p.build_cost_inr, annual_savings_inr: p.annual_savings_inr, payback_years: p.payback_years ?? '', service_after_pct: p.service_level_after_pct, avg_lead_after_days: p.avg_lead_after_days, co2_after_t: p.co2_after_t_per_year, resilience_after: p.resilience_after, health_after: p.health_after }))), 'text/csv')}>
                    CSV
                  </Button>
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-fg-muted">
                      <th className="py-1 font-medium">Plan</th>
                      <th className="py-1 text-right font-medium">Build</th>
                      <th className="py-1 text-right font-medium">Payback</th>
                      <th className="py-1 text-right font-medium">Service</th>
                      <th className="py-1 text-right font-medium">Resil.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plans.map((p) => (
                      <tr key={p.id} className="border-t border-border/60">
                        <td className="py-1 text-fg">{p.label}</td>
                        <td className="num py-1 text-right">{p.build_cost_display}</td>
                        <td className="num py-1 text-right">{p.payback_years ? `${fmtNum(p.payback_years, 1)} y` : '–'}</td>
                        <td className="num py-1 text-right">{fmtNum(p.service_level_after_pct, 1)}%</td>
                        <td className="num py-1 text-right">{fmtNum(p.resilience_after, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <ParetoChart plans={plans} />
              </section>
              <section className="space-y-1.5 border-t border-border px-4 py-3">
                <SectionLabel>Value of each candidate opened alone</SectionLabel>
                <ol className="space-y-0.5 text-xs">
                  {done.marginal_values.slice(0, 10).map((m) => (
                    <li key={`${m.site}:${m.kind}`} className="flex gap-2">
                      <span className="flex-1 truncate text-fg-2">{m.name} <span className="text-fg-muted">{m.kind}</span></span>
                      <span className={`num ${m.annual_value_inr > 0 ? 'text-ok' : 'text-fg-muted'}`}>{m.annual_value_display}/yr</span>
                    </li>
                  ))}
                </ol>
                <p className="text-2xs text-fg-muted">
                  MILP vs greedy: {done.cross_check.same_sites ? 'same sites' : `greedy ${fmtNum(done.cross_check.greedy_gap_pct, 2)}% worse`}. Recommendation holds at demand ±20%:{' '}
                  {done.recommendation_stability.map((s) => `${s.variant} ${s.same_as_recommended ? 'yes' : 'no'}`).join(', ')}.
                </p>
              </section>
              <section className="space-y-1 border-t border-border px-4 py-3">
                <SectionLabel>Risks and assumptions</SectionLabel>
                <ul className="list-disc space-y-0.5 pl-4 text-2xs text-fg-2">
                  {done.assumptions.map((a) => <li key={a}>{a}</li>)}
                </ul>
              </section>
            </>
          )}
          {!runnable && <EmptyState title="The active network can't be planned for" description="Fix it on the Data page first." action={<Button onClick={() => setTab('data')}>Open Data</Button>} />}
        </div>
      </Panel>
      {network == null && null}
    </div>
  )
}
