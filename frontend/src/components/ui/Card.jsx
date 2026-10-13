import { cn } from './cn.js'

export function Card({ className, children, as: Tag = 'section', ...props }) {
  return (
    <Tag className={cn('rounded-card border border-border bg-surface shadow-card', className)} {...props}>
      {children}
    </Tag>
  )
}

/** Card header: title + optional description, icon and right-aligned actions. */
export function CardHeader({ title, description, icon: Icon, actions, className }) {
  return (
    <header className={cn('flex flex-wrap items-start gap-x-3 gap-y-2 px-5 pt-4', className)}>
      <div className="min-w-0 flex-1">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-fg">
          {Icon && <Icon className="h-4 w-4 text-fg-muted" aria-hidden />}
          {title}
        </h2>
        {description && <p className="mt-0.5 text-xs text-fg-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  )
}

export function CardBody({ className, children }) {
  return <div className={cn('px-5 pb-5 pt-4', className)}>{children}</div>
}
