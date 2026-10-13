import { AlertCircle, RotateCw } from 'lucide-react'
import { cn } from './cn.js'

/** Friendly empty state: icon, one-line title, optional description and action. */
export function EmptyState({ icon: Icon, title, description, action, className }) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 px-6 py-10 text-center', className)}>
      {Icon && (
        <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-full bg-surface-2 text-fg-muted">
          <Icon className="h-5 w-5" aria-hidden />
        </div>
      )}
      <p className="text-sm font-medium text-fg">{title}</p>
      {description && <p className="max-w-sm text-xs text-fg-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

/** Inline error message (never a full-width banner). */
export function InlineError({ message, onRetry, className }) {
  if (!message) return null
  return (
    <div role="alert" className={cn('flex items-start gap-2 rounded-lg bg-bad/10 px-3 py-2 text-xs text-bad', className)}>
      <AlertCircle className="mt-px h-4 w-4 shrink-0" aria-hidden />
      <span className="flex-1 leading-5">{message}</span>
      {onRetry && (
        <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 font-medium hover:underline">
          <RotateCw className="h-3 w-3" aria-hidden />
          Retry
        </button>
      )}
    </div>
  )
}
