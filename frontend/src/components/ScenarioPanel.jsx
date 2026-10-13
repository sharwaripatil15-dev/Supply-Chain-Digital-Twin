import { useEffect, useState } from 'react'
import { Building2, Play, Plus, Route, TrendingUp, X } from 'lucide-react'
import { useStore } from '../store.js'
import { eventLabel, fmtNum } from '../format.js'
import { isDemand, typeOf } from '../lib/nodeTypes.js'
import { Button, Card, CardBody, CardHeader, InlineError, SegmentedControl, cn, useToast } from './ui/index.js'

const TYPE_ICON = { node: Building2, edge: Route, demand: TrendingUp }

function targetOptions(network, type) {
  if (!network) return []
  if (type === 'edge') return (network.edges ?? []).map((e) => ({ value: `${e.source}->${e.target}`, label: `${e.source} → ${e.target}` }))
  const nodes = type === 'demand' ? (network.nodes ?? []).filter((n) => isDemand(n.kind)) : network.nodes ?? []
  return nodes.map((n) => ({ value: n.id, label: `${n.id} · ${n.name || n.city} (${typeOf(n.kind).label.toLowerCase()})` }))
}

const blankEvent = (network) => ({ type: 'node', target: targetOptions(network, 'node')[0]?.value || '', start: 1, duration: 7, severity: 1 })

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
  const { network, events, setEvents, runSimulation, loading, errors } = useStore()
  const toast = useToast()
  const [selected, setSelected] = useState(0)
  const busy = Boolean(loading.sim)

  useEffect(() => {
    if (selected >= events.length) setSelected(Math.max(0, events.length - 1))
  }, [events.length, selected])

  const run = async (evs) => {
    const res = await runSimulation(evs)
    if (res) toast('Simulation complete', { description: `${fmtNum(res.total_unmet)} units unmet · Survival Clock ${res.survival_clock_days} days` })
  }

  return (
    <Card>
      <CardHeader title="Disruption Events" description="Fine-tune parameters or add custom manual events." />
      <CardBody className="space-y-4">
        <section aria-label="Scenario events">
          <div className="mb-2.5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h3 className="label">Active Events</h3>
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-semibold text-fg-muted">
                {events.length}
              </span>
            </div>
            <Button
              variant="secondary"
              size="sm"
              icon={Plus}
              onClick={() => {
                setEvents([...events, blankEvent(network)])
                setSelected(events.length)
              }}
            >
              Add event
            </Button>
          </div>

          {events.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-fg-muted">
              No events configured yet. Pick a scenario from the library above or enter a prompt in the AI simulator.
            </p>
          ) : (
            <ul className="mb-3 flex flex-wrap gap-1.5">
              {events.map((e, i) => {
                const Icon = TYPE_ICON[e.type]
                return (
                  <li key={i}>
                    <span
                      className={cn(
                        'inline-flex h-7 items-center gap-1 rounded-md border pl-2 pr-1 text-xs font-medium transition-colors duration-150',
                        i === selected ? 'border-accent/40 bg-accent/10 text-accent ring-1 ring-accent/30' : 'border-border bg-surface text-fg-2 hover:border-border-strong',
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

        <div className="space-y-2 pt-1">
          <Button variant="primary" icon={Play} className="w-full justify-center shadow-sm" disabled={busy || !events.length} onClick={() => run(events)}>
            {busy ? 'Simulating…' : 'Run simulation'}
          </Button>
          <InlineError message={errors.sim} onRetry={() => run(events)} />
        </div>
      </CardBody>
    </Card>
  )
}
