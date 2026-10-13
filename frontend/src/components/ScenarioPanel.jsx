import { useEffect, useState } from 'react'
import { Building2, Play, Plus, Route, Sparkles, TrendingUp, X } from 'lucide-react'
import { DEMO_SCENARIOS, useStore } from '../store.js'
import { eventLabel, fmtNum } from '../format.js'
import { Button, Card, CardBody, CardHeader, InlineError, SegmentedControl, cn, useToast } from './ui/index.js'

const BLANK = { type: 'node', target: 'S1', start: 1, duration: 7, severity: 1 }
const TYPE_ICON = { node: Building2, edge: Route, demand: TrendingUp }

function targetOptions(network, type) {
  if (!network) return []
  if (type === 'edge') return network.edges.map((e) => ({ value: `${e.source}->${e.target}`, label: `${e.source} → ${e.target}` }))
  const nodes = type === 'demand' ? network.nodes.filter((n) => n.kind === 'customer') : network.nodes
  return nodes.map((n) => ({ value: n.id, label: `${n.id} · ${n.name || n.city}` }))
}

function EventEditor({ ev, network, onChange }) {
  const opts = targetOptions(network, ev.type)
  const set = (k, v) => {
    const next = { ...ev, [k]: v }
    if (k === 'type') next.target = targetOptions(network, v)[0]?.value || ''
    onChange(next)
  }
  return (
    <div className="space-y-3 rounded-lg border border-border bg-surface-2/50 p-3">
      <SegmentedControl
        size="sm"
        label="Event type"
        value={ev.type}
        onChange={(v) => set('type', v)}
        className="w-full [&>button]:flex-1"
        options={[
          { value: 'node', label: 'Site', icon: Building2 },
          { value: 'edge', label: 'Lane', icon: Route },
          { value: 'demand', label: 'Demand', icon: TrendingUp },
        ]}
      />
      <label className="block">
        <span className="label">Target</span>
        <select className="input mt-1" value={ev.target} onChange={(e) => set('target', e.target.value)} aria-label="Target">
          {opts.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label>
          <span className="label">Start day</span>
          <input className="input mt-1 tabular" type="number" min={0} max={29} value={ev.start} onChange={(e) => set('start', Math.max(0, Number(e.target.value)))} />
        </label>
        <label>
          <span className="label">Duration (days)</span>
          <input className="input mt-1 tabular" type="number" min={1} max={30} value={ev.duration} onChange={(e) => set('duration', Math.max(1, Number(e.target.value)))} />
        </label>
      </div>
      <label className="block">
        <span className="flex justify-between">
          <span className="label">{ev.type === 'demand' ? 'Demand increase' : 'Severity'}</span>
          <span className="tabular text-xs font-medium text-fg">{Math.round(ev.severity * 100)}%</span>
        </span>
        <input type="range" min={0} max={1} step={0.05} value={ev.severity} onChange={(e) => set('severity', Number(e.target.value))} className="mt-1 w-full" aria-label="Severity" />
      </label>
    </div>
  )
}

export default function ScenarioPanel() {
  const { network, events, setEvents, runSimulation, parseText, loading, errors } = useStore()
  const toast = useToast()
  const [selected, setSelected] = useState(0)
  const [text, setText] = useState('Chennai electronics supplier floods from day 2 for about 10 days, and Bengaluru demand jumps 40%.')
  const busy = Boolean(loading.sim)
  useEffect(() => {
    if (selected >= events.length) setSelected(Math.max(0, events.length - 1))
  }, [events.length, selected])

  const run = async (evs, label) => {
    const res = await runSimulation(evs)
    if (res) toast(label ? `Simulated: ${label}` : 'Simulation complete', { description: `${fmtNum(res.total_unmet)} units unmet · Survival Clock ${res.survival_clock_days} days` })
  }
  const parse = async () => {
    const res = await parseText(text)
    if (res) {
      setSelected(0)
      toast(`Parsed ${res.events.length} event${res.events.length === 1 ? '' : 's'}`, { description: res.events.map(eventLabel).join(' · ') })
    }
  }

  return (
    <Card>
      <CardHeader title="Scenario" description="Stack disruptions, then run the simulation." />
      <CardBody className="space-y-5">
        <section aria-label="Demo scenarios">
          <h3 className="label mb-1.5">Quick start</h3>
          <div className="flex flex-col gap-0.5">
            {DEMO_SCENARIOS.map((d) => (
              <Button key={d.id} variant="ghost" disabled={busy} onClick={() => run(d.events, d.label)} className="h-auto justify-start px-2 py-1.5 text-left">
                <span className="flex flex-col">
                  <span className="text-sm font-medium text-fg">{d.label}</span>
                  <span className="text-xs font-normal text-fg-muted">{d.blurb}</span>
                </span>
              </Button>
            ))}
          </div>
        </section>

        <section aria-label="Plain-English scenario">
          <label className="label" htmlFor="scenario-text">
            Describe it in plain English
          </label>
          <textarea id="scenario-text" className="input mt-1.5 h-20 resize-none" value={text} onChange={(e) => setText(e.target.value)} />
          <Button size="sm" icon={Sparkles} className="mt-2 whitespace-nowrap" disabled={loading.parse || text.trim().length < 3} onClick={parse}>
            {loading.parse ? 'Parsing…' : 'Parse into events'}
          </Button>
          <p className="mt-1.5 text-xs text-fg-muted">The LLM only extracts events; the engine computes every number.</p>
          <InlineError className="mt-2" message={errors.parse} />
        </section>

        <section aria-label="Scenario events">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="label">Events</h3>
            <Button
              variant="ghost"
              size="sm"
              icon={Plus}
              onClick={() => {
                setEvents([...events, { ...BLANK }])
                setSelected(events.length)
              }}
            >
              Add event
            </Button>
          </div>
          {events.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-fg-muted">No events yet. Add one or pick a quick start.</p>
          ) : (
            <ul className="mb-3 flex flex-wrap gap-1.5">
              {events.map((e, i) => {
                const Icon = TYPE_ICON[e.type]
                return (
                  <li key={i}>
                    <span
                      className={cn(
                        'inline-flex h-7 items-center gap-1 rounded-md border pl-2 pr-1 text-xs font-medium transition-colors duration-150',
                        i === selected ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-surface text-fg-2 hover:border-border-strong',
                      )}
                    >
                      <button type="button" onClick={() => setSelected(i)} className="inline-flex items-center gap-1" aria-pressed={i === selected}>
                        <Icon className="h-3.5 w-3.5" aria-hidden />
                        {eventLabel(e)}
                        <span className="tabular text-fg-muted">
                          · d{e.start} +{e.duration}
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setEvents(events.filter((_, j) => j !== i))}
                        className="ml-0.5 rounded p-0.5 text-fg-muted hover:bg-surface-3 hover:text-fg"
                        aria-label={`Remove ${eventLabel(e)}`}
                      >
                        <X className="h-3 w-3" aria-hidden />
                      </button>
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
          {events[selected] && (
            <EventEditor ev={events[selected]} network={network} onChange={(next) => setEvents(events.map((e, j) => (j === selected ? next : e)))} />
          )}
        </section>

        <div className="space-y-2">
          <Button variant="primary" icon={Play} className="w-full justify-center" disabled={busy || !events.length} onClick={() => run(events)}>
            {busy ? 'Simulating…' : 'Run simulation'}
          </Button>
          <InlineError message={errors.sim} onRetry={() => run(events)} />
        </div>
      </CardBody>
    </Card>
  )
}
