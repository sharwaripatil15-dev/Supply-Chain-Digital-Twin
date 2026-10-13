import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { cn } from './cn.js'
import { Button } from './Button.jsx'

/** Page header: title + one-line description + actions. */
export function PageHeader({ title, description, actions }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-fg">{title}</h1>
        {description && <p className="mt-1 text-sm text-fg-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** Hover/focus tooltip for icon buttons and truncated text. */
export function Tooltip({ content, children, side = 'top', className }) {
  return (
    <span className={cn('group/tt relative inline-flex', className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          'pointer-events-none absolute left-1/2 z-40 -translate-x-1/2 whitespace-nowrap rounded-md bg-fg px-2 py-1 text-xs font-medium text-bg opacity-0',
          'transition-opacity duration-150 group-hover/tt:opacity-100 group-focus-within/tt:opacity-100',
          side === 'top' ? 'bottom-full mb-1.5' : 'top-full mt-1.5',
        )}
      >
        {content}
      </span>
    </span>
  )
}

/** Horizontal meter. `value` 0..max; optional threshold tick; tone switches to warn above the threshold. */
export function Meter({ value, max = 1, threshold, tone, className, label }) {
  const pct = Math.max(0, Math.min(1, (value || 0) / max)) * 100
  const hot = threshold != null && value > threshold
  const bar = tone === 'muted' ? 'bg-fg-muted/50' : hot ? 'bg-warn' : 'bg-accent'
  return (
    <div
      className={cn('relative h-1.5 w-full rounded-full bg-surface-3', className)}
      role="meter"
      aria-label={label}
      aria-valuenow={Math.round((value || 0) * 100) / 100}
      aria-valuemin={0}
      aria-valuemax={max}
    >
      <div className={cn('h-full rounded-full transition-[width] duration-200', bar)} style={{ width: `${pct}%` }} />
      {threshold != null && (
        <span className="absolute -top-0.5 h-2.5 w-px bg-fg-muted" style={{ left: `${(threshold / max) * 100}%` }} aria-hidden />
      )}
    </div>
  )
}

/** Right-side drawer. Closes on Escape; focus moves into it when opened. */
export function Drawer({ open, onClose, title, subtitle, children }) {
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    ref.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <aside
      ref={ref}
      tabIndex={-1}
      role="dialog"
      aria-label={typeof title === 'string' ? title : 'Details'}
      className="fixed inset-y-0 right-0 z-40 flex w-[360px] max-w-full animate-slide-in flex-col border-l border-border bg-surface shadow-card outline-none"
    >
      <header className="flex items-start gap-3 border-b border-border px-5 py-4">
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-fg">{title}</div>
          {subtitle && <div className="mt-0.5 text-xs text-fg-muted">{subtitle}</div>}
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close details" icon={X} />
      </header>
      <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
    </aside>
  )
}

/** Pressed-state toggle chip (layer toggles etc.). */
export function Toggle({ pressed, onChange, children, icon: Icon }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={() => onChange(!pressed)}
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs font-medium transition-colors duration-150',
        pressed ? 'border-accent/30 bg-accent/10 text-accent' : 'border-border bg-surface text-fg-muted hover:text-fg',
      )}
    >
      {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
      {children}
    </button>
  )
}
