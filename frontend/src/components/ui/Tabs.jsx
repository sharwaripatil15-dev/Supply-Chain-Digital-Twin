import { useRef } from 'react'
import { cn } from './cn.js'

/** Roving focus for a horizontal group: arrows / Home / End move focus and select. */
function useRoving(values, value, onChange) {
  const refs = useRef({})
  const onKeyDown = (e) => {
    const enabled = values.filter((v) => !v.disabled).map((v) => v.value)
    const i = enabled.indexOf(value)
    let next = null
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = enabled[(i + 1) % enabled.length]
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = enabled[(i - 1 + enabled.length) % enabled.length]
    else if (e.key === 'Home') next = enabled[0]
    else if (e.key === 'End') next = enabled[enabled.length - 1]
    if (next == null) return
    e.preventDefault()
    onChange(next)
    refs.current[next]?.focus()
  }
  return { refs, onKeyDown }
}

/**
 * Underlined tabs. tabs: [{ value, label, count?, disabled? }]. Pair each panel with <TabPanel idBase value>.
 */
export function Tabs({ tabs, value, onChange, label, idBase = 'tabs', className, size = 'md' }) {
  const { refs, onKeyDown } = useRoving(tabs, value, onChange)
  return (
    <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className={cn('flex items-end gap-5 border-b border-border', className)}>
      {tabs.map((t) => {
        const active = t.value === value
        return (
          <button
            key={t.value}
            ref={(el) => (refs.current[t.value] = el)}
            type="button"
            role="tab"
            id={`${idBase}-tab-${t.value}`}
            aria-selected={active}
            aria-controls={`${idBase}-panel`}
            tabIndex={active ? 0 : -1}
            disabled={t.disabled}
            onClick={() => onChange(t.value)}
            className={cn(
              '-mb-px flex items-center gap-1.5 border-b-2 font-medium transition-colors duration-150 disabled:opacity-45',
              size === 'sm' ? 'h-8 text-xs' : 'h-9 text-sm',
              active ? 'border-accent text-fg' : 'border-transparent text-fg-muted hover:text-fg',
            )}
          >
            {t.label}
            {t.count != null && <span className="num text-2xs text-fg-muted">{t.count}</span>}
          </button>
        )
      })}
    </div>
  )
}

export function TabPanel({ idBase = 'tabs', value, className, children }) {
  return (
    <div role="tabpanel" id={`${idBase}-panel`} aria-labelledby={`${idBase}-tab-${value}`} className={className}>
      {children}
    </div>
  )
}

/** Segmented control (single choice, radiogroup). options: [{ value, label, icon?, disabled?, title? }]. */
export function SegmentedControl({ value, onChange, options, label, size = 'sm', className }) {
  const { refs, onKeyDown } = useRoving(options, value, onChange)
  return (
    <div
      role="radiogroup"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={cn('inline-flex items-center rounded-md border border-border bg-raised p-0.5', size === 'xs' ? 'h-7' : size === 'sm' ? 'h-8' : 'h-9', className)}
    >
      {options.map((o) => {
        const active = o.value === value
        const Icon = o.icon
        return (
          <button
            key={o.value}
            ref={(el) => (refs.current[o.value] = el)}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            disabled={o.disabled}
            title={o.title}
            onClick={() => onChange(o.value)}
            className={cn(
              'inline-flex h-full items-center justify-center gap-1.5 whitespace-nowrap rounded-[5px] px-2.5 font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-40',
              size === 'md' ? 'text-sm' : 'text-xs',
              active ? 'bg-surface text-fg ring-1 ring-border' : 'text-fg-muted hover:text-fg',
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
