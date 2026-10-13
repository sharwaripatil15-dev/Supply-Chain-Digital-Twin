import { useEffect, useMemo, useState } from 'react'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useStore } from '../store.js'
import { useTokens } from '../theme.jsx'
import { fmtNum } from '../format.js'
import { ChartTooltip, axisProps, gridProps, refLabel } from '../lib/chart.jsx'
import { InlineError, Panel, PanelHeader, Select, Skeleton } from './ui/index.js'

/** Direct label at the end of a series, instead of a legend. */
const endLabel = (text, color, lastIndex) =>
  function EndLabel({ x, y, index }) {
    if (index !== lastIndex || x == null || y == null) return null
    return (
      <text x={x + 6} y={y} dy={4} fill={color} fontSize={11}>
        {text}
      </text>
    )
  }

export default function ForecastChart() {
  const { forecast, network, loading, errors, loadForecast } = useStore()
  const t = useTokens()
  const [cust, setCust] = useState(null)
  useEffect(() => {
    if (!forecast && !loading.forecast && !errors.forecast) loadForecast() // reloads after the network changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forecast])

  const selected = forecast?.customers?.find((c) => c.id === cust) || forecast?.customers?.[0]
  const data = useMemo(() => {
    if (!selected) return []
    return [
      ...selected.history.map((h) => ({ day: h.day, demand: h.demand })),
      ...selected.forecast.map((f) => ({ day: f.day, mean: f.mean, band: [f.p10, f.p90] })),
    ]
  }, [selected])
  const nameOf = (id) => network?.nodes.find((n) => n.id === id)?.name || id
  const last = data.length - 1
  const lastActual = selected ? selected.history.length - 1 : -1

  return (
    <Panel>
      <PanelHeader
        title="Demand forecast"
        meta={forecast ? `${forecast.method}` : 'Per demand point'}
        actions={
          forecast?.customers?.length > 0 && (
            <>
              <span className="num whitespace-nowrap text-xs text-fg-muted">MAPE {(forecast.mape * 100).toFixed(1)}%</span>
              <Select size="sm" className="w-44" value={selected?.id} onChange={(e) => setCust(e.target.value)} aria-label="Demand point">
                {forecast.customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.id} · {nameOf(c.id)}
                  </option>
                ))}
              </Select>
            </>
          )
        }
      />
      <div className="px-4 py-3">
        <InlineError message={errors.forecast} onRetry={loadForecast} />
        {loading.forecast && !forecast && <Skeleton className="h-[220px] w-full" />}
        {forecast && !forecast.customers?.length && <p className="py-8 text-center text-sm text-fg-muted">No demand points with demand in this network.</p>}
        {forecast?.customers?.length > 0 && (
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={data} margin={{ top: 16, right: 64, left: -14, bottom: 0 }}>
              <CartesianGrid {...gridProps(t)} />
              <XAxis dataKey="day" type="number" domain={['dataMin', 'dataMax']} {...axisProps(t)} />
              <YAxis domain={['auto', 'auto']} {...axisProps(t)} />
              <Tooltip
                cursor={{ stroke: t.color.border }}
                content={
                  <ChartTooltip
                    render={(p) => (
                      <div className="num">
                        <div className="text-fg-muted">Day {p.day > 0 ? `+${p.day}` : p.day}</div>
                        {p.demand != null && <div className="text-fg">Actual {fmtNum(p.demand)}</div>}
                        {p.mean != null && (
                          <div className="text-fg">
                            Forecast {fmtNum(p.mean)} <span className="text-fg-muted">({fmtNum(p.band[0])}–{fmtNum(p.band[1])})</span>
                          </div>
                        )}
                      </div>
                    )}
                  />
                }
              />
              <Area dataKey="band" stroke="none" fill={t.alpha('accent', 0.1)} isAnimationActive={false} />
              <Line dataKey="demand" stroke={t.color.fgMuted} strokeWidth={1.25} dot={false} isAnimationActive={false} label={endLabel('actual', t.color.fgMuted, lastActual)} />
              <Line dataKey="mean" stroke={t.color.accent} strokeWidth={1.75} dot={false} isAnimationActive={false} label={endLabel('forecast', t.color.accent, last)} />
              <ReferenceLine x={0} stroke={t.color.borderStrong} label={refLabel(t, 'today', null, 'top')} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </Panel>
  )
}
