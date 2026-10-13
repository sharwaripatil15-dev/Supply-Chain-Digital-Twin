import { cn } from './cn.js'
import { Card } from './Card.jsx'
import { Skeleton } from './Skeleton.jsx'

/** Tiny inline sparkline (no axes); inherits color from the `className` text color. */
export function Sparkline({ data, className, height = 28 }) {
  if (!data || data.length < 2) return null
  const max = Math.max(...data, 1e-9)
  const min = Math.min(...data, 0)
  const span = max - min || 1
  const w = 100
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${height - 2 - ((v - min) / span) * (height - 4)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className={cn('h-7 w-full', className)} aria-hidden>
      <polyline points={`0,${height} ${pts} ${w},${height}`} className="fill-current opacity-10" stroke="none" />
      <polyline points={pts} fill="none" className="stroke-current" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

/**
 * KPI tile: small label, large tabular number, optional chip and sparkline.
 * `emphasis` gives the Survival Clock its prominent treatment.
 */
export function Stat({ label, value, unit, sub, chip, spark, sparkClass = 'text-accent', icon: Icon, emphasis, loading, className }) {
  return (
    <Card className={cn('flex flex-col gap-2 p-4', emphasis && 'border-accent/40 ring-1 ring-accent/15', className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-xs font-medium text-fg-muted">
          {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
          {label}
        </span>
        {chip}
      </div>
      {loading ? (
        <Skeleton className="h-8 w-28" />
      ) : (
        <div className="flex items-baseline gap-1.5">
          <span className={cn('tabular font-semibold tracking-tight text-fg', emphasis ? 'text-xl' : 'text-lg')}>{value}</span>
          {unit && <span className="text-sm text-fg-muted">{unit}</span>}
        </div>
      )}
      {sub && <span className="text-xs text-fg-muted">{sub}</span>}
      {spark && !loading && <Sparkline data={spark} className={sparkClass} />}
    </Card>
  )
}
