import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, FolderOpen, Play, Plus, Sparkles, X } from 'lucide-react'
import { DEMO_SCENARIOS, useStore } from '../../store.js'
import { eventLabel, fmtNum } from '../../format.js'
import { isDemand, typeOf } from '../../lib/nodeTypes.js'
import { scenariosFor } from '../../lib/scenarios.js'
import { useUi } from '../../ui.jsx'
import { Button, Field, IconButton, InlineError, Input, Menu, Panel, PanelHeader, SegmentedControl, Select, Textarea, cn, useToast } from '../ui/index.js'

const TYPE_LABEL = { node: 'Site', edge: 'Lane', demand: 'Demand' }

function targetOptions(network, type) {
  if (!network) return []
  if (type === 'edge') return (network.edges ?? []).map((e) => ({ value: `${e.source}->${e.target}`, label: `${e.source} → ${e.target}` }))
  const nodes = type === 'demand' ? (network.nodes ?? []).filter((n) => isDemand(n.kind)) : network.nodes ?? []
  return nodes.map((n) => ({ value: n.id, label: `${n.id} · ${n.name || n.city} (${typeOf(n.kind).label.toLowerCase()})` }))
}

const blankEvent = (network) => ({ type: 'node', target: targetOptions(network, 'node')[0]?.value || '', start: 1, duration: 7, severity: 1 })

function EventEditor({ ev, network, onChange, idBase }) {
  const opts = targetOptions(network, ev.type)
  const set = (k, v) => {
    const next = { ...ev, [k]: v }
    if (k === 'type') next.target = targetOptions(network, v)[0]?.value || ''
    onChange(next)
  }
  return (
    <div className="space-y-2.5 px-3 pb-3 pt-1">
      <SegmentedControl
        size="xs"
        label="Event type"
        value={ev.type}
        onChange={(v) => set('type', v)}
        className="w-full [&>button]:flex-1"
        options={[
          { value: 'node', label: 'Site' },
          { value: 'edge', label: 'Lane' },
          { value: 'demand', label: 'Demand' },
        ]}
      />
      <Field label="Target" htmlFor={`${idBase}-target`}>
        <Select id={`${idBase}-target`} size="sm" value={ev.target} onChange={(e) => set('target', e.target.value)}>
          {opts.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Start" htmlFor={`${idBase}-start`}>
          <Input id={`${idBase}-start`} size="sm" type="number" min={0} max={29} suffix="day" value={ev.start} onChange={(e) => set('start', Math.max(0, Number(e.target.value)))} />
        </Field>
        <Field label="Duration" htmlFor={`${idBase}-dur`}>
          <Input id={`${idBase}-dur`} size="sm" type="number" min={1} max={30} suffix="days" value={ev.duration} onChange={(e) => set('duration', Math.max(1, Number(e.target.value)))} />
        </Field>
      </div>
      <div>
        <div className="mb-1 flex items-baseline justify-between text-xs">
          <label htmlFor={`${idBase}-sev`} className="font-medium text-fg-2">
            {ev.type === 'demand' ? 'Demand increase' : 'Severity'}
          </label>
          <span className="num text-fg">{Math.round(ev.severity * 100)}%</span>
        </div>
        <input id={`${idBase}-sev`} type="range" min={0} max={1} step={0.05} value={ev.severity} onChange={(e) => set('severity', Number(e.target.value))} className="range" />
      </div>
    </div>
  )
}

/** Compact scenario builder: event list with inline edit, a "Load scenario" menu, plain-English input, one Run button. */
export default function ScenarioBuilder({ className }) {
  const { network, source, events, setEvents, runSimulation, parseText, loading, errors, setTab, setWhatIfDraft } = useStore()
  const ui = useUi()
  const toast = useToast()
  const [open, setOpen] = useState(0)
  const [showParse, setShowParse] = useState(false)
  const [text, setText] = useState('Chennai electronics supplier floods from day 2 for about 10 days, and Bengaluru demand jumps 40%.')
  const isPreset = !source || source.source === 'preset'
  const runnable = !source || source.runnable
  const scenarios = useMemo(() => scenariosFor(network, DEMO_SCENARIOS, isPreset), [network, isPreset])
  const busy = Boolean(loading.sim)
  useEffect(() => {
    if (open != null && open >= events.length) setOpen(events.length ? events.length - 1 : null)
  }, [events.length, open])

  const run = async (evs, label) => {
    const res = await runSimulation(evs)
    if (res) toast(label ? `Simulated: ${label}` : 'Simulation complete', { description: `${fmtNum(res.total_unmet)} units unmet · stock-out in ${res.survival_clock_days} days` })
  }
  const parse = async () => {
    const res = await parseText(text)
    if (res) {
      setOpen(0)
      toast(`Parsed ${res.events.length} event${res.events.length === 1 ? '' : 's'}`, { description: res.events.map(eventLabel).join(' · ') })
    }
  }

  return (
    <Panel className={cn('flex min-h-0 flex-col', className)}>
      <PanelHeader
        title="Scenario"
        meta={`${events.length} event${events.length === 1 ? '' : 's'}`}
        actions={
          <Menu
            icon={FolderOpen}
            label="Load"
            variant="ghost"
            size="sm"
            items={
              scenarios.length
                ? scenarios.map((d) => ({ key: d.id, label: d.label, onSelect: () => (setEvents(d.events), setOpen(0)) }))
                : [{ key: 'none', label: 'No suggestions for this network', disabled: true }]
            }
          />
        }
      />
      <div className="min-h-0 flex-1 overflow-y-auto">
        {events.length === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-fg-muted">No events. Add one or load a scenario.</p>
        ) : (
          <ol className="divide-y divide-border">
            {events.map((e, i) => {
              const expanded = open === i
              return (
                <li key={i} className={cn(expanded && 'bg-raised/40')}>
                  <div className="flex items-center gap-1 pl-2 pr-1">
                    <button
                      type="button"
                      onClick={() => setOpen(expanded ? null : i)}
                      aria-expanded={expanded}
                      className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-sm px-1 text-left text-sm"
                    >
                      <ChevronRight className={cn('h-3.5 w-3.5 shrink-0 text-fg-muted transition-transform duration-150', expanded && 'rotate-90')} aria-hidden />
                      <span className="w-12 shrink-0 text-2xs text-fg-muted">{TYPE_LABEL[e.type]}</span>
                      <span className="min-w-0 flex-1 truncate text-fg">{eventLabel(e)}</span>
                      <span className="num shrink-0 text-2xs text-fg-muted">
                        d{e.start}+{e.duration}
                      </span>
                    </button>
                    <IconButton icon={X} label={`Remove ${eventLabel(e)}`} size="xs" tooltipSide="left" onClick={() => setEvents(events.filter((_, j) => j !== i))} />
                  </div>
                  {expanded && <EventEditor ev={e} network={network} idBase={`ev${i}`} onChange={(next) => setEvents(events.map((x, j) => (j === i ? next : x)))} />}
                </li>
              )
            })}
          </ol>
        )}
        <div className="flex items-center gap-1 border-t border-border px-2 py-2">
          <Button
            variant="ghost"
            size="sm"
            icon={Plus}
            onClick={() => {
              setEvents([...events, blankEvent(network)])
              setOpen(events.length)
            }}
          >
            Add event
          </Button>
          <Button variant="ghost" size="sm" icon={Sparkles} onClick={() => setShowParse((s) => !s)} aria-expanded={showParse}>
            Describe in words
          </Button>
        </div>
        {showParse && (
          <div className="space-y-2 border-t border-border px-3 py-3">
            <Textarea aria-label="Scenario in plain English" className="h-20" value={text} onChange={(e) => setText(e.target.value)} />
            <div className="flex items-center gap-2">
              <Button size="sm" disabled={loading.parse || text.trim().length < 3} onClick={parse}>
                {loading.parse ? 'Parsing…' : 'Parse into events'}
              </Button>
              <span className="text-2xs text-fg-muted">The model only extracts events.</span>
            </div>
            <InlineError message={errors.parse} />
          </div>
        )}
      </div>
      <div className="space-y-2 border-t border-border p-3">
        <Button variant="primary" icon={Play} className="w-full" disabled={busy || !events.length || !runnable} onClick={() => run(events)}>
          {busy ? 'Simulating…' : 'Run simulation'}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="w-full"
          disabled={!events.length || !runnable}
          onClick={() => setWhatIfDraft({ events, note: 'Planning recovery for the scenario built on the Simulate page.' })}
        >
          Plan recovery in What-if
        </Button>
        {!runnable && (
          <p className="text-xs text-fg-muted">
            The active network has errors.{' '}
            <button
              type="button"
              className="font-medium text-fg underline underline-offset-2"
              onClick={() => {
                ui.setDataView(source?.source === 'csv' ? 'csv' : 'manual')
                setTab('data')
              }}
            >
              Fix it on the Data page
            </button>
          </p>
        )}
        <InlineError message={errors.sim} onRetry={runnable ? () => run(events) : undefined} />
      </div>
    </Panel>
  )
}
