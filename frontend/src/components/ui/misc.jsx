import { cn } from './cn.js'

/** Horizontal meter. `value` 0..max; optional threshold tick; `tone` = 'muted' | 'accent' | 'warn'. */
export function Meter({ value, max = 1, threshold, tone = 'muted', className, label }) {
  const pct = Math.max(0, Math.min(1, (value || 0) / (max || 1))) * 100
  const hot = threshold != null && value > threshold
  const bar = hot ? 'bg-warn' : tone === 'accent' ? 'bg-accent' : tone === 'warn' ? 'bg-warn' : 'bg-fg-muted/55'
  return (
    <div
      className={cn('relative h-1 w-full rounded-full bg-raised', className)}
      role="meter"
      aria-label={label}
      aria-valuenow={Math.round((value || 0) * 100) / 100}
      aria-valuemin={0}
      aria-valuemax={max}
    >
      <div className={cn('h-full rounded-full transition-[width] duration-150', bar)} style={{ width: `${pct}%` }} />
      {threshold != null && <span className="absolute -top-0.5 h-2 w-px bg-fg-muted" style={{ left: `${(threshold / max) * 100}%` }} aria-hidden />}
    </div>
  )
}

/** Pressed-state toggle (layer switches on the canvas). */
export function Toggle({ pressed, onChange, children, icon: Icon, disabled, title }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      disabled={disabled}
      title={title}
      onClick={() => onChange(!pressed)}
      className={cn(
        'inline-flex h-6 items-center gap-1.5 rounded-sm px-2 text-xs font-medium transition-colors duration-150 disabled:opacity-40',
        pressed ? 'bg-raised text-fg' : 'text-fg-muted hover:text-fg',
      )}
    >
      {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
      {children}
    </button>
  )
}

/** Hairline vertical divider for toolbars. */
export function Divider({ className }) {
  return <span className={cn('h-5 w-px shrink-0 bg-border', className)} aria-hidden />
}
