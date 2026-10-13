import { cn } from './cn.js'

/**
 * Segmented control (single choice). options: [{ value, label, icon?, disabled?, title? }].
 * Rendered as a radiogroup so it works with arrow keys via native tab order and is announced correctly.
 */
export function SegmentedControl({ value, onChange, options, label, size = 'md', className }) {
  return (
    <div role="radiogroup" aria-label={label} className={cn('inline-flex rounded-lg border border-border bg-surface-2 p-0.5', className)}>
      {options.map((o) => {
        const active = o.value === value
        const Icon = o.icon
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={o.disabled}
            title={o.title}
            onClick={() => onChange(o.value)}
            className={cn(
              'inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors duration-150',
              size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-8 px-3 text-sm',
              active ? 'bg-surface text-fg shadow-card ring-1 ring-border' : 'text-fg-muted hover:text-fg',
              'disabled:cursor-not-allowed disabled:opacity-40',
            )}
          >
            {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
