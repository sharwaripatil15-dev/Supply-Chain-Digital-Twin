import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Dices } from 'lucide-react'
import { useStore } from '../store.js'
import { useTokens } from '../theme.jsx'
import { fmtNum } from '../format.js'
import { ChartTooltip, axisProps, cursorFill, gridProps, refLabel } from '../lib/chart.jsx'
import { Badge, Card, CardBody, CardHeader, EmptyState, InlineError, Skeleton } from './ui/index.js'

// ReferenceLine on a category axis must hit an existing category: snap to the bin containing v.
const binFor = (hist, v) => hist.reduce((acc, b) => (b.bin <= v ? b.bin : acc), hist[0]?.bin)

export default function MonteCarloChart() {
  const { mc, loading, errors, events, runSimulation } = useStore()
  const t = useTokens()
  const hist = mc?.histogram || []
  const width = hist.length > 1 ? hist[1].bin - hist[0].bin : 0
  return (
    <Card>
      <CardHeader
        title="Monte Carlo"
        description="Unmet units across 200 runs with uncertain durations and severities"
        icon={Dices}
        actions={mc && <Badge tone={mc.p_shortage > 0.5 ? 'bad' : mc.p_shortage > 0 ? 'warn' : 'ok'}>P(shortage) {Math.round(mc.p_shortage * 100)}%</Badge>}
      />
      <CardBody>
        <InlineError message={errors.mc} onRetry={() => runSimulation(events)} />
        {loading.mc ? (
          <Skeleton className="h-[220px] w-full" />
        ) : !mc ? (
          <EmptyState icon={Dices} title="No uncertainty bands yet" description="They appear after a simulation run." />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={hist} margin={{ top: 20, right: 8, left: -12, bottom: 0 }} barCategoryGap={2}>
                <CartesianGrid {...gridProps(t)} />
                <XAxis dataKey="bin" tickFormatter={(v) => fmtNum(v)} interval="preserveStartEnd" {...axisProps(t)} />
                <YAxis allowDecimals={false} {...axisProps(t)} axisLine={false} />
                <Tooltip
                  cursor={cursorFill(t)}
                  content={
                    <ChartTooltip
                      render={(p) => (
                        <>
                          <div className="tabular text-fg-muted">
                            {fmtNum(p.bin)}-{fmtNum(p.bin + width)} units
                          </div>
                          <div className="font-medium text-fg">{p.count} runs</div>
                        </>
                      )}
                    />
                  }
                />
                <Bar dataKey="count" fill={t.alpha('fgMuted', 0.35)} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                <ReferenceLine x={binFor(hist, mc.p50)} stroke={t.color.fg2} strokeDasharray="4 3" label={refLabel(t, `P50 ${fmtNum(mc.p50)}`)} />
                <ReferenceLine x={binFor(hist, mc.p90)} stroke={t.color.accent} strokeWidth={2} label={refLabel(t, `P90 ${fmtNum(mc.p90)}`, t.color.accent)} />
              </BarChart>
            </ResponsiveContainer>
            <p className="mt-2 text-xs text-fg-muted">
              Half of runs lose fewer than {fmtNum(mc.p50)} units; 1 in 10 loses more than {fmtNum(mc.p90)}.
            </p>
          </>
        )}
      </CardBody>
    </Card>
  )
}
