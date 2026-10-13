import { useEffect } from 'react'
import { CloudLightning, Eraser, Route } from 'lucide-react'
import { useStore } from '../../store.js'
import { useWeather } from '../../weather.jsx'
import { LEVEL_LABEL, LEVEL_RANK, LEVEL_TONE, fmtDay, rowLevel, weatherEvents } from '../../lib/weather.js'
import { Button, InlineError, SectionLabel, SkeletonBlock, StatusDot, TabPanel, Tabs, Toggle, cn, useToast } from '../ui/index.js'
import { InspectorPanel } from '../layout/Workspace.jsx'
import { ATTRIBUTION, DayStrip, QualityChip, RiskCells, WeatherControls } from './WeatherParts.jsx'

function Notes({ risk }) {
  const notes = [
    ...(risk.data_quality === 'cached' ? ['Showing the last good forecast: the providers could not be reached.'] : []),
    ...(risk.data_quality === 'simulated' && risk.scenario ? [`Simulated scenario, not a forecast: ${risk.scenario.description}`] : []),
    ...(risk.warnings || []),
  ]
  if (!notes.length && !risk.mapping?.length) return null
  return (
    <div className="space-y-1.5 rounded-md border border-border bg-raised/50 px-3 py-2 text-xs text-fg-2">
      {notes.map((n) => (
        <p key={n}>{n}</p>
      ))}
      {risk.mapping?.length > 0 && (
        <ul className="space-y-0.5 text-fg-muted">
          {risk.mapping.map((m) => (
            <li key={m.anchor}>
              {m.wanted} → {(m.matched || ['fixture coordinates']).join(', ')}
              <span className="text-fg-muted"> ({m.how})</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * "Weather & hazards" inspector: data mode, horizon, quality, the day's lanes at risk, and the actions that put the
 * forecast into the scenario (reversibly) or open the re-routing plan.
 */
export default function WeatherPanel({ day, onDay }) {
  const w = useWeather()
  const { events, source, setTab, network } = useStore()
  const toast = useToast()
  const runnable = !source || source.runnable
  const { ensure } = w
  useEffect(() => ensure(), [ensure])
  const risk = w.risk
  const inScenario = weatherEvents(events).length
  const byId = Object.fromEntries((network?.nodes ?? []).map((n) => [n.id, n]))

  const lanes = (risk?.edges ?? [])
    .filter((e) => LEVEL_RANK[e.max_level] >= 2)
    .sort((a, b) => b.max_risk - a.max_risk)
  const sites = (risk?.nodes ?? []).filter((n) => !n.demand_node && LEVEL_RANK[n.max_level] >= 2)

  const add = async () => {
    const res = await w.applyToScenario()
    if (res) toast(`Added ${res.events.length} weather event${res.events.length === 1 ? '' : 's'}`, { description: 'Simulated with the rest of the scenario. Clear them to restore it.' })
  }
  const clear = async () => {
    await w.clearFromScenario()
    toast('Weather events cleared', { description: 'The scenario is back to how it was.' })
  }

  let body
  if (w.errors.risk && !risk) {
    body = <InlineError className="px-4 py-3" message={w.errors.risk} onRetry={w.load} />
  } else if (!risk) {
    body = <SkeletonBlock lines={6} label="Loading the weather forecast" className="px-4 py-3" />
  } else {
    const s = risk.summary
    body = (
      <div className="space-y-4 px-4 py-3">
        <Notes risk={risk} />
        <dl className="grid grid-cols-3 gap-2">
          {[
            ['High-risk lanes', s.high_risk_edges, s.high_risk_edges ? 'warn' : 'ok'],
            ['Closed', s.closed_edges, s.closed_edges ? 'bad' : 'ok'],
            ['Sites hit', s.affected_nodes, s.affected_nodes ? 'warn' : 'ok'],
          ].map(([label, v, tone]) => (
            <div key={label}>
              <dt className="text-xs text-fg-muted">{label}</dt>
              <dd className="mt-0.5 flex items-center gap-1.5">
                <StatusDot status={v ? tone : 'neutral'} />
                <span className="num text-base text-fg">{v}</span>
              </dd>
            </div>
          ))}
        </dl>
        <section>
          <div className="mb-1.5 flex items-baseline justify-between">
            <SectionLabel>Day {day}</SectionLabel>
            <span className="text-2xs text-fg-muted">{fmtDay(risk.dates[day])}</span>
          </div>
          <DayStrip risk={risk} day={day} onDay={onDay} />
        </section>
        <section>
          <SectionLabel className="mb-1.5">Lanes at risk</SectionLabel>
          {lanes.length === 0 ? (
            <p className="text-xs text-fg-muted">No lane reaches high risk in the next {risk.horizon} days.</p>
          ) : (
            <ul className="-mx-2 space-y-0.5">
              {lanes.slice(0, 8).map((e) => {
                const row = e.daily[Math.min(day, e.daily.length - 1)]
                const lvl = rowLevel(row)
                return (
                  <li key={e.id} className="rounded-md px-2 py-1.5 hover:bg-raised">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="num min-w-0 flex-1 truncate text-fg">{e.id.replace('->', ' → ')}</span>
                      <span className="text-2xs text-fg-muted">{e.mode}</span>
                      <StatusDot status={LEVEL_TONE[lvl]} label={LEVEL_LABEL[lvl]} />
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <RiskCells daily={e.daily} size="xs" />
                      <span className="min-w-0 flex-1 truncate text-2xs text-fg-muted" title={e.daily[e.worst_day]?.reason}>
                        {e.daily[e.worst_day]?.reason}
                      </span>
                    </div>
                  </li>
                )
              })}
              {lanes.length > 8 && <li className="px-2 text-2xs text-fg-muted">+{lanes.length - 8} more in the route risk table</li>}
            </ul>
          )}
        </section>
        {sites.length > 0 && (
          <section>
            <SectionLabel className="mb-1.5">Sites at risk</SectionLabel>
            <ul className="space-y-1 text-xs">
              {sites.map((n) => (
                <li key={n.id} className="flex items-center gap-2">
                  <span className="num text-fg">{n.id}</span>
                  <span className="min-w-0 flex-1 truncate text-fg-2">{byId[n.id]?.name || n.city}</span>
                  <StatusDot status={LEVEL_TONE[n.max_level]} label={LEVEL_LABEL[n.max_level]} />
                </li>
              ))}
            </ul>
          </section>
        )}
        <div className="space-y-2">
          <Button variant="primary" icon={CloudLightning} className="w-full" disabled={!runnable || w.loading.apply || (!s.high_risk_edges && !s.affected_nodes)} onClick={add}>
            {w.loading.apply ? 'Adding…' : inScenario ? 'Update weather events and simulate' : 'Add to scenario and simulate'}
          </Button>
          <div className="flex gap-2">
            <Button size="sm" icon={Route} className="flex-1" disabled={!runnable} onClick={() => (w.openReroute(), setTab('recover'))}>
              Plan re-routing
            </Button>
            {inScenario > 0 && (
              <Button size="sm" variant="ghost" icon={Eraser} onClick={clear} disabled={w.loading.clear}>
                Clear {inScenario}
              </Button>
            )}
          </div>
          <InlineError message={w.errors.apply || w.errors.scenario} />
        </div>
      </div>
    )
  }

  return (
    <InspectorPanel
      title="Weather & hazards"
      meta={risk ? `${risk.scenario ? risk.scenario.label : 'Live forecast'} · next ${risk.horizon} days` : 'Forecast for every lane and site'}
      actions={<QualityChip risk={risk} />}
    >
      <div className="space-y-3 border-b border-border px-4 py-3">
        <WeatherControls />
        <Toggle pressed={w.layerOn} onChange={w.setLayer} icon={CloudLightning} title="Color lanes by weather risk and draw hazards on the map">
          Show hazards on the map
        </Toggle>
      </div>
      {body}
      <p className={cn('border-t border-border px-4 py-2 text-2xs text-fg-muted')}>{ATTRIBUTION}</p>
    </InspectorPanel>
  )
}

/** Inspector with tabs: the page's own panel plus "Weather" (keyboard-navigable, like every tab set). */
export function InspectorTabs({ tabs, value, onChange, idBase = 'inspector' }) {
  const current = tabs.find((t) => t.value === value) || tabs[0]
  return (
    <div className="flex h-full min-h-0 flex-col">
      <Tabs idBase={idBase} label="Inspector" size="sm" value={current.value} onChange={onChange} className="shrink-0 px-4 pr-10" tabs={tabs.map(({ value: v, label }) => ({ value: v, label }))} />
      <TabPanel idBase={idBase} value={current.value} className="min-h-0 flex-1">
        {current.content}
      </TabPanel>
    </div>
  )
}
