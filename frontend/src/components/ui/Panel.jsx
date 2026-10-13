import { cn } from './cn.js'

/** Flat bordered region (8px radius, hairline border, no shadow). */
export function Panel({ as: Tag = 'section', className, children, ...props }) {
  return (
    <Tag className={cn('rounded-lg border border-border bg-surface', className)} {...props}>
      {children}
    </Tag>
  )
}

/** Quiet panel header: title, optional meta text, right-aligned actions. */
export function PanelHeader({ title, meta, actions, className, as: Heading = 'h2' }) {
  return (
    <div className={cn('flex min-h-10 items-center gap-3 border-b border-border px-4 py-1.5', className)}>
      <div className="flex min-w-0 flex-1 items-baseline gap-2">
        <Heading className="truncate text-sm font-medium text-fg">{title}</Heading>
        {meta && <span className="truncate text-xs text-fg-muted">{meta}</span>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
    </div>
  )
}

/** Tiny caps label for flat sections (the only uppercase text in the app). */
export function SectionLabel({ children, className, as: Tag = 'h3' }) {
  return <Tag className={cn('section-label', className)}>{children}</Tag>
}
