import { useStore } from '../store.js'
import { BOTTLENECK, fmtPct } from '../format.js'
import { isDemand } from '../lib/nodeTypes.js'
import { EmptyState, Meter, cn } from './ui/index.js'
import { TypeIcon } from './NodeTypeIcon.jsx'

/** Per-site load on the current day, highest first; peak bottlenecks over the horizon below. */
export default function UtilizationBars() {
  const { sim, day, setDay, network, selectNode } = useStore()
  if (!sim) return <EmptyState title="No load data yet" description="Run a scenario to see where capacity runs out." />
  const row = sim.timeline[day] || sim.timeline[0]
  const byId = Object.fromEntries((network?.nodes ?? []).map((n) => [n.id, n]))
  // demand points only carry a load when they forward stock (a retailer with a capacity)
  const rows = Object.entries(row?.utilization ?? {})
    .filter(([id]) => !isDemand(byId[id]?.kind) || (byId[id]?.capacity ?? 0) > 0)
    .sort((a, b) => b[1] - a[1])
  return (
    <div className="space-y-3">
      <ul className="space-y-1">
        {rows.map(([id, u]) => {
          const hot = u > BOTTLENECK.threshold
          const down = row.node_status[id] === 'down'
          return (
            <li key={id}>
              <button
                type="button"
                onClick={() => selectNode(id)}
                className="grid w-full grid-cols-[5.5rem_minmax(0,1fr)_3rem] items-center gap-3 rounded-sm px-1 py-1 text-left text-xs hover:bg-raised"
                title={byId[id]?.name}
              >
                <span className="flex min-w-0 items-center gap-1.5">
                  <TypeIcon kind={byId[id]?.kind} size="xs" />
                  <span className="num truncate text-fg">{id}</span>
                </span>
                <Meter value={u} max={1.2} threshold={BOTTLENECK.threshold} tone={down ? 'muted' : 'muted'} label={`${id} utilization`} />
                <span className={cn('num text-right', down ? 'text-fg-muted' : hot ? 'text-warn' : 'text-fg-2')}>{down ? 'down' : fmtPct(u)}</span>
              </button>
            </li>
          )
        })}
      </ul>
      {sim.bottlenecks.length > 0 && (
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-border pt-2 text-xs text-fg-muted">
          <span>Peaks above 90%:</span>
          {sim.bottlenecks.map((b) => (
            <button key={b.node} type="button" onClick={() => b.day != null && setDay(b.day)} className="rounded-sm px-1 text-fg-2 hover:bg-raised hover:text-fg">
              <span className="num">{b.node}</span> <span className="num text-warn">{fmtPct(b.utilization)}</span>
              {b.day != null && <span className="num text-fg-muted"> d{b.day}</span>}
            </button>
          ))}
        </p>
      )}
    </div>
  )
}
