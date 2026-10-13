import { CartesianGrid, LabelList, ResponsiveContainer, Scatter, ScatterChart, Tooltip as ChartTip, XAxis, YAxis, ZAxis } from 'recharts'

/** Direct point label: one line, UI font (Recharts' default label wraps word by word inside the point's box). */
const pointLabel = (fill) =>
  function PointLabel({ x, y, value }) {
    if (!value || x == null || y == null) return null
    return (
      <text x={x + 12} y={y + 4} fill={fill} fontSize={11}>
        {value}
      </text>
    )
  }
import { Info } from 'lucide-react'
import { useTokens } from '../theme.jsx'
import { fmtINR, fmtNum } from '../format.js'
import { ChartTooltip, axisProps, gridProps } from '../lib/chart.jsx'
import { Badge, DataTable, StatusDot, Tooltip } from './ui/index.js'

/** ROI as one sentence. */
export function RoiLine({ roi }) {
  const ratio = roi.inaction_loss > 0 ? roi.inaction_loss / Math.max(roi.fix_cost, 1) : null
  const v = (x) => <span className="num text-fg">{fmtINR(x)}</span>
  if (roi.inaction_loss <= 0) return <p className="text-sm text-fg-2">Doing nothing loses no sales in this scenario, so no plan pays for itself.</p>
  return (
    <p className="text-sm text-fg-2">
      {roi.net_saving >= 0 ? (
        <>
          Acting saves {v(roi.net_saving)}.
        </>
      ) : (
        <>
          Acting costs {v(-roi.net_saving)} more than it saves.
        </>
      )}{' '}
      Doing nothing loses {v(roi.inaction_loss)}; the recommended plan costs {v(roi.fix_cost)} including residual lost sales
      {ratio ? (
        <>
          {' '}
          (every ₹1 avoids <span className="num text-fg">₹{ratio.toFixed(1)}</span> of losses)
        </>
      ) : null}
      .
    </p>
  )
}

/** Strategy comparison. Recommended row = small accent tag; failed safety checks = red note + info tooltip. */
export function StrategyTable({ strategies, selected, onSelect }) {
  const cheapest = strategies.reduce((a, b) => (b.cost < a.cost ? b : a))
  return (
    <DataTable
      label="Strategy comparison"
      rows={strategies}
      rowKey={(s) => s.name}
      selectedKey={selected}
      onRowClick={(s) => onSelect(s.name)}
      toolbar={<h2 className="text-sm font-medium text-fg">Strategies</h2>}
      columns={[
        {
          key: 'name', header: 'Strategy', hideable: false,
          render: (s) => (
            <span className="flex items-center gap-1.5">
              <span className="max-w-[9rem] truncate text-fg min-[1400px]:max-w-[16rem] 2xl:max-w-[22rem]" title={s.name}>
                {s.name}
              </span>
              {s.recommended && <Badge tone="accent">Recommended</Badge>}
              {s === cheapest && !s.recommended && <Badge>Cheapest</Badge>}
            </span>
          ),
        },
        { key: 'cost', header: 'Cost', align: 'right', render: (s) => fmtINR(s.cost) },
        { key: 'unmet', header: 'Unmet', align: 'right', render: (s) => fmtNum(s.unmet) },
        { key: 'recovery_days', header: 'Recovers', align: 'right', render: (s) => `${s.recovery_days} d` },
        { key: 'delay_avg_days', header: 'Delay', align: 'right', render: (s) => `${fmtNum(s.delay_avg_days, 1)} d` },
        { key: 'co2', header: 'CO₂ t', align: 'right', defaultHidden: true, render: (s) => fmtNum(s.co2, 1) },
        { key: 'resilience_after', header: 'Resilience', align: 'right', render: (s) => fmtNum(s.resilience_after, 0) },
        {
          key: 'safety', header: 'Safety', value: (s) => (s.safety_check.passed ? 1 : 0),
          render: (s) =>
            s.safety_check.passed ? (
              <StatusDot status="ok" label="Pass" />
            ) : (
              <span className="inline-flex items-center gap-1 text-xs text-bad">
                Fails
                <Tooltip content={s.safety_check.warning} wide side="left">
                  <button type="button" aria-label={`Why ${s.name} fails the safety check`} className="rounded-sm text-bad" onClick={(e) => e.stopPropagation()}>
                    <Info className="h-3.5 w-3.5" aria-hidden />
                  </button>
                </Tooltip>
              </span>
            ),
        },
      ]}
    />
  )
}

/** Cost vs unmet scatter with direct labels on the points that matter (no legend). */
export function CostScatter({ strategies }) {
  const t = useTokens()
  const rows = strategies.map((s) => ({ ...s, tag: s.recommended ? 'Recommended' : !s.safety_check.passed ? 'Fails safety check' : '' }))
  const groups = [
    { key: 'other', data: rows.filter((s) => !s.recommended && s.safety_check.passed), fill: t.alpha('fgMuted', 0.55) },
    { key: 'unsafe', data: rows.filter((s) => !s.recommended && !s.safety_check.passed), fill: t.color.bad },
    { key: 'rec', data: rows.filter((s) => s.recommended), fill: t.color.accent },
  ].filter((g) => g.data.length)
  return (
    <div>
      <p className="mb-1 text-xs text-fg-muted">Lower-left is better. Labels mark the recommended plan and plans that fail the safety check.</p>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 16, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid {...gridProps(t)} />
          <XAxis type="number" dataKey="cost" name="Cost" tickFormatter={fmtINR} {...axisProps(t)} />
          <YAxis type="number" dataKey="unmet" name="Unmet" tickFormatter={(v) => fmtNum(v)} {...axisProps(t)} />
          <ZAxis range={[70, 70]} />
          <ChartTip
            cursor={{ stroke: t.color.border }}
            content={
              <ChartTooltip
                render={(s) => (
                  <>
                    <div className="text-fg">{s.name}</div>
                    <div className="num text-fg-muted">
                      {fmtINR(s.cost)} · {fmtNum(s.unmet)} units unmet
                    </div>
                  </>
                )}
              />
            }
          />
          {groups.map((g) => (
            <Scatter key={g.key} data={g.data} fill={g.fill} isAnimationActive={false}>
              {g.key !== 'other' && <LabelList dataKey="tag" content={pointLabel(g.fill)} />}
            </Scatter>
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}
