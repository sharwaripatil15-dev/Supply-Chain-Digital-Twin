import { useEffect, useMemo, useState } from 'react'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { LineChart } from 'lucide-react'
import { useStore } from '../store.js'
import { useTokens } from '../theme.jsx'
import { fmtNum } from '../format.js'
import { ChartTooltip, axisProps, gridProps, refLabel } from '../lib/chart.jsx'
import { Badge, Card, CardBody, CardHeader, InlineError, Skeleton } from './ui/index.js'

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

  return (
    <Card>
      <CardHeader
        title="Demand forecast"
        description={forecast ? forecast.method : 'Per demand point (retailers and customers): history and forecast'}
        icon={LineChart}
        actions={
          forecast?.customers?.length > 0 && (
            <>
              <select className="input h-8 w-auto py-0 text-xs" value={selected?.id} onChange={(e) => setCust(e.target.value)} aria-label="Demand point">
                {forecast.customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.id} · {nameOf(c.id)}
                  </option>
                ))}
              </select>
              <Badge>MAPE {(forecast.mape * 100).toFixed(1)}%</Badge>
            </>
          )
        }
      />
      <CardBody>
        <InlineError message={errors.forecast} onRetry={loadForecast} />
        {loading.forecast && !forecast && <Skeleton className="h-[220px] w-full" />}
        {forecast && !forecast.customers?.length && <p className="py-8 text-center text-sm text-fg-muted">No demand points with demand in this network.</p>}
        {forecast?.customers?.length > 0 && (
          <>
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={data} margin={{ top: 16, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid {...gridProps(t)} />
                <XAxis dataKey="day" type="number" domain={['dataMin', 'dataMax']} {...axisProps(t)} />
                <YAxis domain={['auto', 'auto']} {...axisProps(t)} axisLine={false} />
                <Tooltip
                  cursor={{ stroke: t.color.border }}
                  content={
                    <ChartTooltip
                      render={(p) => (
                        <div className="tabular">
                          <div className="text-fg-muted">Day {p.day > 0 ? `+${p.day}` : p.day}</div>
                          {p.demand != null && <div className="text-fg">Actual {fmtNum(p.demand)}</div>}
                          {p.mean != null && (
                            <div className="text-fg">
                              Forecast {fmtNum(p.mean)} <span className="text-fg-muted">({fmtNum(p.band[0])}-{fmtNum(p.band[1])})</span>
                            </div>
                          )}
                        </div>
                      )}
                    />
                  }
                />
                <Area dataKey="band" stroke="none" fill={t.alpha('accent', 0.12)} isAnimationActive={false} />
                <Line dataKey="demand" stroke={t.color.fgMuted} strokeWidth={1.5} dot={false} isAnimationActive={false} />
                <Line dataKey="mean" stroke={t.color.accent} strokeWidth={2} dot={false} isAnimationActive={false} />
                <ReferenceLine x={0} stroke={t.color.borderStrong} label={refLabel(t, 'today')} />
              </ComposedChart>
            </ResponsiveContainer>
            <ul className="mt-2 flex flex-wrap gap-x-4 text-xs text-fg-muted">
              <li className="flex items-center gap-1.5">
                <span className="w-4 border-t-2 border-fg-muted" aria-hidden /> actual
              </li>
              <li className="flex items-center gap-1.5">
                <span className="w-4 border-t-2 border-accent" aria-hidden /> forecast
              </li>
              <li className="flex items-center gap-1.5">
                <span className="h-2.5 w-4 rounded-sm bg-accent/15" aria-hidden /> P10-P90
              </li>
            </ul>
          </>
        )}
      </CardBody>
    </Card>
  )
}
