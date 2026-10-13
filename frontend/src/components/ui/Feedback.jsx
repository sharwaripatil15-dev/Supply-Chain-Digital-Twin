import { AlertCircle } from 'lucide-react'
import { cn } from './cn.js'

/** Concise empty state: one line, an optional short description, at most one action. */
export function EmptyState({ title, description, action, className }) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 py-10 text-center', className)}>
      <p className="text-sm font-medium text-fg">{title}</p>
      {description && <p className="mt-1 max-w-sm text-xs text-fg-muted">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

/** Inline error text with an optional retry link. */
export function InlineError({ message, onRetry, className }) {
  if (!message) return null
  return (
    <p role="alert" className={cn('flex items-start gap-1.5 text-xs leading-5 text-bad', className)}>
      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1">
        {message}
        {onRetry && (
          <>
            {' '}
            <button type="button" onClick={onRetry} className="font-medium underline underline-offset-2 hover:text-fg">
              Retry
            </button>
          </>
        )}
      </span>
    </p>
  )
}

/** One-line notice bar (e.g. "previewing an upload"). */
export function Notice({ children, action, className }) {
  return (
    <div className={cn('flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-xs text-fg-2', className)}>
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
      <span className="min-w-0 flex-1">{children}</span>
      {action}
    </div>
  )
}
