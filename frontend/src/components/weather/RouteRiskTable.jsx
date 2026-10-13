import { useEffect, useMemo, useState } from 'react'
import { useWeather } from '../../weather.jsx'
import { LEVEL_LABEL, LEVEL_RANK, LEVEL_TONE } from '../../lib/weather.js'
import { DataTable, InlineError, SegmentedControl, SkeletonRows, StatusDot } from '../ui/index.js'
import { QualityChip, RiskCells } from './WeatherParts.jsx'

const FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'moderate', label: 'Moderate+' },
  { value: 'high', label: 'High+' },
  { value: 'closed', label: 'Closed' },
]

const peakLevel = (e) => (e.daily.some((d) => d.closed) ? 'closed' : e.max_level)

/** Every lane with its risk by day, top drivers and reason. Sortable; filter by level. */
export default function RouteRiskTable({ className }) {
  const w = useWeather()
  const { ensure } = w
  useEffect(() => ensure(), [ensure])
  const [filter, setFilter] = useState('high')
  const rows = useMemo(() => {
    const edges = (w.risk?.edges ?? []).filter((e) => e.daily.length)
    return edges
      .filter((e) =>
        filter === 'all' ? true : filter === 'closed' ? e.daily.some((d) => d.closed) : LEVEL_RANK[e.max_level] >= LEVEL_RANK[filter],
      )
      .map((e) => {
        const worst = e.daily[e.worst_day ?? 0]
        return { ...e, peak: peakLevel(e), worst, drivers: worst?.drivers ?? [] }
      })
  }, [w.risk, filter])

  if (w.errors.risk && !w.risk) return <InlineError className="px-4 py-3" message={w.errors.risk} onRetry={w.load} />
  if (!w.risk) return <SkeletonRows rows={5} label="Loading route risk" />
  return (
    <DataTable
      className={className}
      label="Route risk"
      rows={rows}
      defaultSort={{ key: 'risk', dir: 'desc' }}
      empty={filter === 'all' ? 'No lanes with coordinates to assess.' : 'No lanes at this level in the horizon.'}
      toolbar={
        <>
          <SegmentedControl size="xs" label="Filter by level" value={filter} onChange={setFilter} options={FILTERS} />
          <span className="ml-auto" />
          <QualityChip risk={w.risk} />
        </>
      }
      columns={[
        { key: 'id', header: 'Lane', mono: true, render: (r) => r.id.replace('->', ' → ') },
        { key: 'mode', header: 'Mode', render: (r) => <span className="text-fg-2">{r.mode}</span> },
        { key: 'days', header: 'Risk by day', sortable: false, render: (r) => <RiskCells daily={r.daily} /> },
        {
          key: 'risk', header: 'Peak', align: 'right', value: (r) => r.max_risk,
          render: (r) => (
            <span className="inline-flex items-center gap-2">
              <StatusDot status={LEVEL_TONE[r.peak]} label={LEVEL_LABEL[r.peak]} />
              <span className="num text-fg">{r.max_risk.toFixed(2)}</span>
            </span>
          ),
        },
        {
          key: 'drivers', header: 'Top drivers', sortable: false,
          render: (r) => (r.drivers.length ? r.drivers.map((d) => `${d.hazard} ${d.value ?? ''}${d.value != null ? ` ${d.unit}` : ''}`).join(', ') : <span className="text-fg-muted">–</span>),
        },
        { key: 'reason', header: 'Reason', sortable: false, defaultHidden: false, render: (r) => <span className="block max-w-[22rem] truncate text-fg-2" title={r.worst?.reason}>{r.worst?.reason}</span> },
      ]}
    />
  )
}

