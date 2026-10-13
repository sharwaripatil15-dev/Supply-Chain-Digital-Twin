import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Timer } from 'lucide-react'
import { useStore } from '../store.js'
import { useTokens } from '../theme.jsx'
import { fmtNum } from '../format.js'
import { ChartTooltip, axisProps, cursorFill, refLabel } from '../lib/chart.jsx'
import { Card, CardBody, CardHeader, EmptyState } from './ui/index.js'

export default function DelayChart() {
  const { sim, network } = useStore()
  const t = useTokens()
  if (!sim) {
    return (
      <Card>
        <CardHeader title="Delivery delay by customer" icon={Timer} />
        <CardBody>
          <EmptyState icon={Timer} title="No delay estimates yet" description="They appear after a simulation run." />
        </CardBody>
      </Card>
    )
  }
  const nameOf = Object.fromEntries(network.nodes.map((n) => [n.id, n.name || n.city]))
  const data = Object.entries(sim.delay.per_customer)
    .map(([id, days]) => ({ id, name: nameOf[id], days }))
    .sort((a, b) => b.days - a.days)
  const max = Math.max(...data.map((d) => d.days), sim.delay.p90_days, 1)
  return (
    <Card>
      <CardHeader
        title="Delivery delay by customer"
        description="Extra lead time of delivered units vs their normal routes"
        icon={Timer}
        actions={
          <span className="tabular text-xs text-fg-muted">
            avg <b className="text-fg">{fmtNum(sim.delay.avg_days, 1)} d</b> · P90 <b className="text-accent">{fmtNum(sim.delay.p90_days, 1)} d</b>
          </span>
        }
      />
      <CardBody>
        <ResponsiveContainer width="100%" height={data.length * 36 + 32}>
          <BarChart data={data} layout="vertical" margin={{ top: 16, right: 16, left: 0, bottom: 0 }} barCategoryGap={8}>
            <XAxis type="number" domain={[0, Math.ceil(max)]} unit=" d" {...axisProps(t)} />
            <YAxis type="category" dataKey="id" width={34} {...axisProps(t)} axisLine={false} />
            <CartesianGrid horizontal={false} stroke={t.color.border} strokeDasharray="2 4" />
            <Tooltip
              cursor={cursorFill(t)}
              content={
                <ChartTooltip
                  render={(p) => (
                    <>
                      <div className="font-medium text-fg">
                        {p.id} · {p.name}
                      </div>
                      <div className="tabular text-fg-muted">{fmtNum(p.days, 2)} days extra</div>
                    </>
                  )}
                />
              }
            />
            <Bar dataKey="days" fill={t.alpha('fgMuted', 0.35)} radius={[0, 3, 3, 0]} isAnimationActive={false} />
            <ReferenceLine x={sim.delay.avg_days} stroke={t.color.fg2} strokeDasharray="4 3" label={refLabel(t, 'avg')} />
            <ReferenceLine x={sim.delay.p90_days} stroke={t.color.accent} strokeWidth={2} label={refLabel(t, 'P90', t.color.accent)} />
          </BarChart>
        </ResponsiveContainer>
        <p className="mt-2 text-xs text-fg-muted">Units never delivered count as unmet demand, not delay.</p>
      </CardBody>
    </Card>
  )
}
