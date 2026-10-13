import { Gauge, TriangleAlert } from 'lucide-react'
import { useStore } from '../store.js'
import { BOTTLENECK, fmtPct } from '../format.js'
import { isDemand } from '../lib/nodeTypes.js'
import { Badge, Card, CardBody, CardHeader, EmptyState, Meter, cn } from './ui/index.js'
import { TypeIcon } from './NodeTypeIcon.jsx'

export default function UtilizationBars() {
  const { sim, day, setDay, network } = useStore()
  if (!sim) {
    return (
      <Card>
        <CardHeader title="Utilization" icon={Gauge} />
        <CardBody>
          <EmptyState icon={Gauge} title="No load data yet" description="Run a scenario to see where capacity runs out." />
        </CardBody>
      </Card>
    )
  }
  const row = sim.timeline[day] || sim.timeline[0]
  const byId = Object.fromEntries((network?.nodes ?? []).map((n) => [n.id, n]))
  const kindOf = (id) => byId[id]?.kind
  // demand points only have a load when they forward stock (a retailer with a capacity)
  const rows = Object.entries(row?.utilization ?? {})
    .filter(([id]) => !isDemand(kindOf(id)) || (byId[id]?.capacity ?? 0) > 0)
    .sort((a, b) => b[1] - a[1])

  return (
    <Card>
      <CardHeader title={`Utilization · day ${row.day}`} description="Tick = 90% bottleneck threshold" icon={Gauge} />
      <CardBody>
        <ul className="space-y-2">
          {rows.map(([id, u]) => {
            const hot = u > BOTTLENECK.threshold
            const down = row.node_status[id] === 'down'
            return (
              <li key={id} className="grid grid-cols-[4.5rem_1fr_3.5rem] items-center gap-3 text-xs">
                <span className="flex min-w-0 items-center gap-1.5 font-medium text-fg" title={byId[id]?.name}>
                  <TypeIcon kind={kindOf(id)} size="xs" />
                  <span className="truncate">{id}</span>
                </span>
                <Meter value={u} max={1.2} threshold={BOTTLENECK.threshold} tone={down ? 'muted' : undefined} label={`${id} utilization`} />
                <span className={cn('tabular text-right', hot ? 'font-semibold text-warn' : 'text-fg-2')}>{down ? 'down' : fmtPct(u)}</span>
              </li>
            )
          })}
        </ul>
        {sim.bottlenecks.length > 0 && (
          <div className="mt-4 border-t border-border pt-3">
            <p className="label mb-2">Peak bottlenecks over the horizon</p>
            <div className="flex flex-wrap gap-1.5">
              {sim.bottlenecks.map((b) => (
                <button key={b.node} type="button" onClick={() => b.day != null && setDay(b.day)} className="rounded-md focus-visible:ring-2">
                  <Badge tone="warn" icon={TriangleAlert} className="cursor-pointer hover:bg-warn/20">
                    {b.node} <span className="tabular">{fmtPct(b.utilization)}</span>
                    {b.day != null && <span className="tabular font-normal opacity-80">· d{b.day}</span>}
                  </Badge>
                </button>
              ))}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
