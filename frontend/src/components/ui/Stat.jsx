import { cn } from './cn.js'
import { Skeleton } from './Skeleton.jsx'
import { StatusDot } from './Badge.jsx'

/**
 * One bordered row of 3-5 metrics separated by dividers: small label, large mono value with unit, quiet sub line.
 * items: [{ key, label, value, unit?, sub?, status? ('ok'|'warn'|'bad'), title? }]
 */
export function KpiStrip({ items, loading = false, label = 'Key metrics', className }) {
  return (
    <dl aria-label={label} className={cn('grid grid-flow-col auto-cols-fr divide-x divide-border rounded-lg border border-border bg-surface', className)}>
      {items.map((it) => (
        <div key={it.key || it.label} className="min-w-0 px-4 py-2.5" title={it.title}>
          <dt className="truncate text-xs text-fg-muted">{it.label}</dt>
          <dd className="mt-0.5 flex items-baseline gap-1 whitespace-nowrap">
            {loading ? (
              <Skeleton className="my-1 h-5 w-20" />
            ) : (
              <>
                <span className="num text-lg text-fg">{it.value ?? '–'}</span>
                {it.unit && it.value != null && it.value !== '–' && <span className="text-xs text-fg-muted">{it.unit}</span>}
              </>
            )}
          </dd>
          <dd className="h-4 truncate text-xs text-fg-muted">
            {!loading && (it.status ? <StatusDot status={it.status} label={it.sub} textClassName="text-fg-muted" /> : it.sub)}
          </dd>
        </div>
      ))}
    </dl>
  )
}
