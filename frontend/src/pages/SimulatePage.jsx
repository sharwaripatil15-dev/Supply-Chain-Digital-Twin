import { useMemo } from 'react'
import { useStore } from '../store.js'
import { STATUS, fmtINR, fmtNum, fmtPct } from '../format.js'
import { disruptionForDay } from '../lib/disruption.js'
import { EmptyState, KpiStrip, SectionLabel, StatusDot } from '../components/ui/index.js'
import Workspace, { InspectorPanel } from '../components/layout/Workspace.jsx'
import NetworkCanvas from '../components/canvas/NetworkCanvas.jsx'
import ScenarioBuilder from '../components/simulate/ScenarioBuilder.jsx'
import SimResults from '../components/simulate/SimResults.jsx'
import { NodeTag } from '../components/NodeTypeIcon.jsx'

const TONE = { ok: 'ok', stressed: 'warn', down: 'bad' }

function SimKpis() {
  const { sim, mc, loading } = useStore()
  const firstOut = sim && Object.entries(sim.stockout_day).sort((a, b) => a[1] - b[1])[0]
  const items = [
    {
      key: 'clock', label: 'Days to stock-out', value: sim ? sim.survival_clock_days : null, unit: 'days',
      sub: !sim ? 'Run a scenario' : firstOut ? `${firstOut[0]} runs out first` : 'No stock-out in the horizon',
      status: sim ? (!firstOut ? 'ok' : sim.survival_clock_days <= 7 ? 'bad' : 'warn') : null,
    },
    { key: 'unmet', label: 'Unmet demand', value: sim ? fmtNum(sim.total_unmet) : null, unit: 'units', sub: sim ? `Over ${sim.timeline.length} days` : '' },
    { key: 'rev', label: 'Revenue at risk', value: sim ? fmtINR(sim.revenue_at_risk) : null, sub: sim ? 'At list price' : '' },
    { key: 'delay', label: 'Avg delivery delay', value: sim ? fmtNum(sim.delay.avg_days, 1) : null, unit: 'days', sub: sim ? `P90 ${fmtNum(sim.delay.p90_days, 1)} days` : '' },
    {
      key: 'mc', label: 'Shortage probability', value: mc ? fmtPct(mc.p_shortage) : null,
      sub: mc ? `P90 ${fmtNum(mc.p90)} units unmet` : loading.mc ? 'Monte Carlo running…' : '',
    },
  ]
  return <KpiStrip items={items} loading={Boolean(loading.sim)} label="Simulation results" />
}

/** Default inspector: what is happening on the selected day. */
function DayInspector() {
  const { sim, day, network, selectNode } = useStore()
  if (!sim) {
    return (
      <InspectorPanel title="Day">
        <EmptyState title="No run yet" description="Run a scenario; each day's failures appear here." />
      </InspectorPanel>
    )
  }
  const row = sim.timeline[day] || sim.timeline[0]
  const byId = Object.fromEntries((network?.nodes ?? []).map((n) => [n.id, n]))
  const counts = Object.values(row.node_status).reduce((acc, s) => ({ ...acc, [s]: (acc[s] || 0) + 1 }), {})
  const affected = Object.entries(row.node_status)
    .filter(([, s]) => s !== 'ok')
    .sort((a, b) => (a[1] === b[1] ? a[0].localeCompare(b[0]) : a[1] === 'down' ? -1 : 1))
  return (
    <InspectorPanel title={`Day ${row.day}`} meta={`of ${sim.timeline.length - 1}`}>
      <div className="space-y-4 px-4 py-3">
        <dl className="grid grid-cols-3 gap-2">
          {['down', 'stressed', 'ok'].map((k) => (
            <div key={k}>
              <dt>
                <StatusDot status={TONE[k]} label={STATUS[k].label} textClassName="text-fg-muted" />
              </dt>
              <dd className="num mt-0.5 text-base text-fg">{counts[k] || 0}</dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-fg-muted">
          Unmet today <span className="num text-fg">{fmtNum(row.unmet)}</span> units
        </p>
        <section>
          <SectionLabel className="mb-1.5">Affected sites</SectionLabel>
          {affected.length === 0 ? (
            <p className="text-xs text-fg-muted">Everything is running normally on this day.</p>
          ) : (
            <ul className="-mx-2">
              {affected.map(([id, s]) => (
                <li key={id}>
                  <button type="button" onClick={() => selectNode(id)} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-raised">
                    <NodeTag id={id} node={byId[id]} className="min-w-0 flex-1" />
                    <StatusDot status={TONE[s]} label={STATUS[s].label} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </InspectorPanel>
  )
}

export default function SimulatePage() {
  const { sim, day, events, network } = useStore()
  const row = sim ? sim.timeline[day] || sim.timeline[0] : null
  const statuses = row?.node_status ?? null
  const disrupted = useMemo(() => (sim ? disruptionForDay(network, events, day, statuses) : null), [sim, network, events, day, statuses])
  return (
    <div className="flex h-full min-h-[720px] flex-col gap-3 p-4">
      <SimKpis />
      <div className="flex min-h-0 flex-1 gap-3">
        <ScenarioBuilder className="w-[272px] shrink-0 xl:w-[296px]" />
        <Workspace className="min-w-0 flex-1" inspector={<DayInspector />} inspectorLabel="Day details">
          <div className="flex h-full min-h-0 flex-col">
            <NetworkCanvas className="min-h-[300px] flex-1" statuses={statuses} utilization={row?.utilization ?? null} disrupted={disrupted} timeline />
            <SimResults className="h-[248px] shrink-0 border-t border-border" />
          </div>
        </Workspace>
      </div>
    </div>
  )
}
