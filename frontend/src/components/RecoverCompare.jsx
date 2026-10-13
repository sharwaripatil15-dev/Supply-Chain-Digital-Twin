import { Fragment } from 'react'
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { AlertTriangle, CircleCheck, CircleX, Coins, LifeBuoy, PiggyBank, ScatterChart as ScatterIcon, Star, TrendingDown } from 'lucide-react'
import { useStore } from '../store.js'
import { useTokens } from '../theme.jsx'
import { fmtINR, fmtNum } from '../format.js'
import { ChartTooltip, axisProps } from '../lib/chart.jsx'
import { Badge, Card, CardBody, CardHeader, EmptyState, InlineError, SkeletonBlock, Stat, Table, Td, Th, Tr } from './ui/index.js'

function RoiStats({ roi }) {
  const ratio = roi.inaction_loss > 0 ? roi.inaction_loss / Math.max(roi.fix_cost, 1) : null
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Stat label="Do nothing" icon={TrendingDown} value={fmtINR(roi.inaction_loss)} sub="Lost sales if no action is taken" />
      <Stat label="Recommended fix" icon={Coins} value={fmtINR(roi.fix_cost)} sub="Plan cost + residual lost sales" />
      <Stat
        label="Net saving"
        icon={PiggyBank}
        emphasis
        value={fmtINR(roi.net_saving)}
        chip={<Badge tone={roi.net_saving >= 0 ? 'ok' : 'bad'} dot>{roi.net_saving >= 0 ? 'Act' : 'Not worth it'}</Badge>}
        sub={ratio ? `Every ₹1 spent avoids ₹${ratio.toFixed(1)} of losses` : 'No inaction loss in this scenario'}
      />
    </div>
  )
}

function StrategyTable({ strategies }) {
  const cheapest = strategies.reduce((a, b) => (b.cost < a.cost ? b : a))
  return (
    <Card>
      <CardHeader title="Strategy comparison" description="Each strategy is optimised, then re-stress-tested by the fix-safety check" icon={LifeBuoy} />
      <CardBody className="px-0 pb-2">
        <Table label="Strategy comparison" className="max-h-[520px]">
          <thead>
            <tr>
              <Th>Strategy</Th>
              <Th numeric>Cost</Th>
              <Th numeric>Unmet</Th>
              <Th numeric>Recovery</Th>
              <Th numeric>Delay</Th>
              <Th numeric>CO₂ t</Th>
              <Th numeric>Resilience</Th>
              <Th>Safety</Th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((s) => (
              <Fragment key={s.name}>
                <Tr selected={s.recommended}>
                  <Td>
                    <div className="flex flex-wrap items-center gap-1.5 font-medium text-fg">
                      {s.name}
                      {s.recommended && (
                        <Badge tone="accent" icon={Star}>
                          Recommended
                        </Badge>
                      )}
                      {s === cheapest && <Badge>Cheapest</Badge>}
                    </div>
                    {s.description && <p className="mt-0.5 max-w-md text-xs text-fg-muted">{s.description}</p>}
                  </Td>
                  <Td numeric>{fmtINR(s.cost)}</Td>
                  <Td numeric>{fmtNum(s.unmet)}</Td>
                  <Td numeric>{s.recovery_days} d</Td>
                  <Td numeric>{fmtNum(s.delay_avg_days, 1)} d</Td>
                  <Td numeric>{fmtNum(s.co2, 1)}</Td>
                  <Td numeric>{fmtNum(s.resilience_after, 0)}</Td>
                  <Td>
                    {s.safety_check.passed ? (
                      <Badge tone="ok" icon={CircleCheck}>
                        Pass
                      </Badge>
                    ) : (
                      <Badge tone="bad" icon={CircleX}>
                        Fail
                      </Badge>
                    )}
                  </Td>
                </Tr>
                {!s.safety_check.passed && s.safety_check.warning && (
                  <tr>
                    <td colSpan={8} className="border-b border-border/70 px-5 pb-3 pt-0">
                      <div className="flex items-start gap-2 rounded-md bg-bad/5 px-3 py-2 text-xs text-bad">
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                        <span>
                          <b className="font-semibold">Fix-safety check failed.</b> {s.safety_check.warning}
                        </span>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </Table>
      </CardBody>
    </Card>
  )
}

function CostScatter({ strategies }) {
  const t = useTokens()
  const series = [
    { key: 'other', data: strategies.filter((s) => !s.recommended && s.safety_check.passed), fill: t.alpha('fgMuted', 0.55), shape: 'circle', label: 'Passes safety check' },
    { key: 'unsafe', data: strategies.filter((s) => !s.recommended && !s.safety_check.passed), fill: t.color.bad, shape: 'cross', label: 'Fails safety check' },
    { key: 'rec', data: strategies.filter((s) => s.recommended), fill: t.color.accent, shape: 'star', label: 'Recommended' },
  ].filter((s) => s.data.length)
  const rec = strategies.find((s) => s.recommended)
  return (
    <Card className="h-full">
      <CardHeader title="Cost vs unmet demand" description="Lower-left is better" icon={ScatterIcon} />
      <CardBody>
        <ResponsiveContainer width="100%" height={280}>
          <ScatterChart margin={{ top: 8, right: 12, bottom: 4, left: -4 }}>
            <CartesianGrid stroke={t.color.border} strokeDasharray="2 4" />
            <XAxis type="number" dataKey="cost" name="Cost" tickFormatter={fmtINR} {...axisProps(t)} />
            <YAxis type="number" dataKey="unmet" name="Unmet" tickFormatter={(v) => fmtNum(v)} {...axisProps(t)} axisLine={false} />
            <ZAxis range={[90, 90]} />
            <Tooltip
              cursor={{ stroke: t.color.border }}
              content={
                <ChartTooltip
                  render={(s) => (
                    <>
                      <div className="font-medium text-fg">{s.name}</div>
                      <div className="tabular text-fg-muted">
                        {fmtINR(s.cost)} · {fmtNum(s.unmet)} units unmet
                      </div>
                    </>
                  )}
                />
              }
            />
            {series.map((s) => (
              <Scatter key={s.key} name={s.label} data={s.data} fill={s.fill} shape={s.shape} isAnimationActive={false} />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-muted">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span className={s.key === 'rec' ? 'text-accent' : s.key === 'unsafe' ? 'text-bad' : 'text-fg-muted'} aria-hidden>
                {s.key === 'rec' ? '★' : s.key === 'unsafe' ? '✕' : '●'}
              </span>
              {s.label}
            </li>
          ))}
        </ul>
        {rec && (
          <p className="mt-3 text-xs text-fg-2">
            <b className="font-medium text-fg">{rec.name}</b> has the lowest cost plus lost sales among strategies that pass the fix-safety check.
          </p>
        )}
      </CardBody>
    </Card>
  )
}

export default function RecoverCompare() {
  const { recover, loading, errors, events, runRecover } = useStore()
  if (loading.recover) {
    return (
      <Card>
        <CardBody>
          <SkeletonBlock lines={6} label="Optimising recovery strategies" />
        </CardBody>
      </Card>
    )
  }
  if (errors.recover) return <InlineError message={errors.recover} onRetry={() => runRecover(events)} />
  if (!recover) {
    return (
      <Card>
        <EmptyState icon={LifeBuoy} title="No recovery plan yet" description="Build a scenario on the Simulate page, then compute a plan." />
      </Card>
    )
  }
  return (
    <div className="space-y-6">
      <RoiStats roi={recover.roi} />
      <div className="grid gap-6 2xl:grid-cols-5">
        <div className="2xl:col-span-3">
          <StrategyTable strategies={recover.strategies} />
        </div>
        <div className="2xl:col-span-2">
          <CostScatter strategies={recover.strategies} />
        </div>
      </div>
    </div>
  )
}
