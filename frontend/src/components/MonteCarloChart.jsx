import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useStore } from '../store.js'
import { useTokens } from '../theme.jsx'
import { fmtNum, fmtPct } from '../format.js'
import { ChartTooltip, axisProps, cursorFill, gridProps, refLabel, series } from '../lib/chart.jsx'
import { EmptyState, InlineError, Skeleton } from './ui/index.js'

// ReferenceLine on a category axis must hit an existing category: snap to the bin containing v.
const binFor = (hist, v) => hist.reduce((acc, b) => (b.bin <= v ? b.bin : acc), hist[0]?.bin)

/** Distribution of unmet units across 200 runs with uncertain durations and severities. */
export default function MonteCarloChart() {
  const { mc, loading, errors, events, runSimulation, source } = useStore()
  const t = useTokens()
  const hist = mc?.histogram || []
  const width = hist.length > 1 ? hist[1].bin - hist[0].bin : 0
  if (errors.mc) return <InlineError message={errors.mc} onRetry={!source || source.runnable ? () => runSimulation(events) : undefined} />
  if (loading.mc) return <Skeleton className="h-[200px] w-full" />
  if (!mc) return <EmptyState title="No uncertainty bands yet" description="They appear after a simulation run." />
  return (
    <div>
      <p className="mb-1 text-xs text-fg-muted">
        200 runs with uncertain durations and severities. Half lose fewer than <span className="num text-fg">{fmtNum(mc.p50)}</span> units; 1 in 10 loses more than{' '}
        <span className="num text-fg">{fmtNum(mc.p90)}</span>. Shortage in <span className="num text-fg">{fmtPct(mc.p_shortage)}</span> of runs.
      </p>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={hist} margin={{ top: 16, right: 8, left: -12, bottom: 0 }} barCategoryGap={1}>
          <CartesianGrid {...gridProps(t)} />
          <XAxis dataKey="bin" tickFormatter={(v) => fmtNum(v)} interval="preserveStartEnd" {...axisProps(t)} />
          <YAxis allowDecimals={false} {...axisProps(t)} />
          <Tooltip
            cursor={cursorFill(t)}
            content={
              <ChartTooltip
                render={(p) => (
                  <>
                    <div className="num text-fg-muted">
                      {fmtNum(p.bin)}–{fmtNum(p.bin + width)} units
                    </div>
                    <div className="num text-fg">{p.count} runs</div>
                  </>
                )}
              />
            }
          />
          <Bar dataKey="count" fill={series(t).muted} isAnimationActive={false} />
          <ReferenceLine x={binFor(hist, mc.p50)} stroke={t.color.fgMuted} strokeDasharray="3 3" label={refLabel(t, `P50 ${fmtNum(mc.p50)}`, null, 'top')} />
          <ReferenceLine x={binFor(hist, mc.p90)} stroke={t.color.accent} label={refLabel(t, `P90 ${fmtNum(mc.p90)}`, t.color.accent, 'top')} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
