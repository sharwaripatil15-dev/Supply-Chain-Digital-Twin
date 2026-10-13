import { CloudLightning, RefreshCw } from 'lucide-react'
import { HORIZONS, useWeather } from '../../weather.jsx'
import { LEVEL_LABEL, QUALITY, fmtDay, rowLevel, summaryLine } from '../../lib/weather.js'
import { IconButton, SegmentedControl, Select, StatusDot, Tooltip, cn } from '../ui/index.js'

const DOT_TONE = { ok: 'ok', warn: 'warn', bad: 'bad', accent: 'accent' }

const timeOf = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
}

/** Data quality (live / cached / simulated / unavailable) with the last refresh time. */
export function QualityChip({ risk, className }) {
  if (!risk) return null
  const q = QUALITY[risk.data_quality] || QUALITY.unavailable
  return (
    <Tooltip content={`${q.note}${risk.generated_at ? ` · updated ${timeOf(risk.generated_at)}` : ''}`} side="bottom">
      <span className={cn('inline-flex h-6 items-center rounded-sm border border-border bg-surface/95 px-1.5', className)}>
        <StatusDot status={DOT_TONE[q.tone] || 'neutral'} label={`${q.label}${risk.generated_at ? ` · ${timeOf(risk.generated_at)}` : ''}`} textClassName="num text-2xs text-fg-2" />
      </span>
    </Tooltip>
  )
}

/** Cell color for a 0..1 risk: neutral -> amber -> red (tokens). */
export const riskCellClass = (risk, closed) =>
  closed ? 'bg-bad' : risk >= 0.7 ? 'bg-bad/80' : risk >= 0.5 ? 'bg-warn' : risk >= 0.3 ? 'bg-warn/45' : 'bg-fg-muted/15'

/** Tiny per-day risk cells (a sparkline as colored blocks). */
export function RiskCells({ daily, className, size = 'sm' }) {
  return (
    <span className={cn('inline-flex items-center gap-px', className)} aria-label={`Risk by day: ${daily.map((d) => `${d.day} ${LEVEL_LABEL[rowLevel(d)]}`).join(', ')}`}>
      {daily.map((d) => (
        <span key={d.day} title={`Day ${d.day}: ${LEVEL_LABEL[rowLevel(d)]} (${d.risk.toFixed(2)})`} className={cn('rounded-[1px]', size === 'sm' ? 'h-3 w-2' : 'h-2 w-1.5', riskCellClass(d.risk, d.closed))} />
      ))}
    </span>
  )
}

/** Forecast days as clickable cells colored by the day's worst risk. */
export function DayStrip({ risk, day, onDay, className }) {
  if (!risk) return null
  const max = risk.summary.max_risk_by_day || []
  return (
    <div role="radiogroup" aria-label="Forecast day" className={cn('grid gap-1', className)} style={{ gridTemplateColumns: `repeat(${Math.min(max.length, 14)}, minmax(0, 1fr))` }}>
      {max.map((r, d) => (
        <button
          key={d}
          type="button"
          role="radio"
          aria-checked={d === day}
          aria-label={`Day ${d}, ${fmtDay(risk.dates[d])}: worst risk ${r.toFixed(2)}`}
          onClick={() => onDay(d)}
          className={cn('flex flex-col items-center gap-1 rounded-sm px-0.5 py-1 text-2xs transition-colors duration-150 hover:bg-raised', d === day ? 'bg-raised text-fg ring-1 ring-border-strong' : 'text-fg-muted')}
        >
          <span className={cn('h-2 w-full rounded-[2px]', riskCellClass(r, r >= 0.85))} aria-hidden />
          <span className="num">{d}</span>
        </button>
      ))}
    </div>
  )
}

/** Data mode (live / one of the simulated scenarios), horizon and refresh. */
export function WeatherControls({ className }) {
  const w = useWeather()
  const busy = Boolean(w.loading.risk || w.loading.scenario)
  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <Select
        size="sm"
        aria-label="Weather data"
        className="min-w-0 flex-1"
        value={w.active || 'live'}
        disabled={busy}
        onChange={(e) => w.setScenario(e.target.value === 'live' ? null : e.target.value)}
      >
        <option value="live">Live forecast</option>
        <optgroup label="Simulated scenarios">
          {(w.scenarios || []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </optgroup>
      </Select>
      <SegmentedControl
        size="xs"
        label="Forecast horizon"
        value={w.horizon}
        onChange={w.setHorizon}
        options={HORIZONS.map((h) => ({ value: h, label: `${h}d`, title: `${h}-day horizon` }))}
      />
      <IconButton
        icon={RefreshCw}
        label={w.active ? 'Reload the scenario' : 'Refresh the forecast (at most every 10 minutes)'}
        size="sm"
        tooltipSide="bottom-end"
        disabled={busy}
        onClick={w.refresh}
        className={busy ? '[&_svg]:animate-spin' : undefined}
      />
    </div>
  )
}

/** One-line weather summary above the canvas (only while the hazard layer is on). */
export function WeatherBar({ day, className }) {
  const w = useWeather()
  if (!w.layerOn) return null
  const line = w.loading.risk && !w.risk ? 'Loading the weather forecast…' : w.errors.risk ? `Weather unavailable: ${w.errors.risk}` : summaryLine(w.risk, w.reroute)
  return (
    <div className={cn('flex h-9 shrink-0 items-center gap-2 border-b border-border bg-surface px-3 text-xs', className)}>
      <CloudLightning className="h-3.5 w-3.5 shrink-0 text-fg-muted" aria-hidden />
      <span className="min-w-0 flex-1 truncate text-fg-2" aria-live="polite" title={line || ''}>
        {line}
      </span>
      {w.risk && day != null && <span className="num hidden shrink-0 text-fg-muted md:inline">Day {day} · {fmtDay(w.risk.dates[Math.min(day, w.risk.dates.length - 1)])}</span>}
      {w.risk?.scenario && <span className="hidden shrink-0 text-2xs uppercase tracking-wide text-accent lg:inline">Simulated</span>}
      <QualityChip risk={w.risk} />
    </div>
  )
}

export const ATTRIBUTION = 'Weather data by Open-Meteo.com (CC BY 4.0); earthquakes: USGS'
