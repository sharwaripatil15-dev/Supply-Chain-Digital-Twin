import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useStore } from '../store.js'
import { useTokens } from '../theme.jsx'
import { fmtNum } from '../format.js'
import { ChartTooltip, axisProps, cursorFill, refLabel, series } from '../lib/chart.jsx'
import { EmptyState } from './ui/index.js'

/** Extra delivery days per demand point (retailers and customers), with direct avg / P90 labels. */
export default function DelayChart() {
  const { sim, network } = useStore()
  const t = useTokens()
  if (!sim) return <EmptyState title="No delay estimates yet" description="They appear after a simulation run." />
  const nameOf = Object.fromEntries((network?.nodes ?? []).map((n) => [n.id, n.name || n.city]))
  const data = Object.entries(sim.delay?.per_customer ?? {})
    .map(([id, days]) => ({ id, name: nameOf[id], days }))
    .sort((a, b) => b.days - a.days)
  const max = Math.max(...data.map((d) => d.days), sim.delay.p90_days, 1)
  return (
    <div>
      <p className="mb-1 text-xs text-fg-muted">
        Extra lead time of delivered units vs normal routes. Average <span className="num text-fg">{fmtNum(sim.delay.avg_days, 1)}</span> days, P90{' '}
        <span className="num text-fg">{fmtNum(sim.delay.p90_days, 1)}</span> days.
      </p>
      <ResponsiveContainer width="100%" height={Math.max(120, data.length * 26 + 28)}>
        <BarChart data={data} layout="vertical" margin={{ top: 14, right: 16, left: 0, bottom: 0 }} barCategoryGap={6}>
          <XAxis type="number" domain={[0, Math.ceil(max)]} unit=" d" {...axisProps(t)} />
          <YAxis type="category" dataKey="id" width={40} {...axisProps(t)} />
          <CartesianGrid horizontal={false} vertical stroke={t.color.border} />
          <Tooltip
            cursor={cursorFill(t)}
            content={
              <ChartTooltip
                render={(p) => (
                  <>
                    <div className="text-fg">
                      <span className="num">{p.id}</span> {p.name}
                    </div>
                    <div className="num text-fg-muted">{fmtNum(p.days, 2)} days extra</div>
                  </>
                )}
              />
            }
          />
          <Bar dataKey="days" fill={series(t).muted} isAnimationActive={false} />
          <ReferenceLine x={sim.delay.avg_days} stroke={t.color.fgMuted} strokeDasharray="3 3" label={refLabel(t, 'avg', null, 'top')} />
          <ReferenceLine x={sim.delay.p90_days} stroke={t.color.accent} label={refLabel(t, 'P90', t.color.accent, 'top')} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
