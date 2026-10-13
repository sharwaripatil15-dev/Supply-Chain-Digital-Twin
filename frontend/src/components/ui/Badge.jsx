import { cn } from './cn.js'

const TONES = {
  neutral: 'bg-raised text-fg-2',
  accent: 'bg-accent/10 text-accent',
  bad: 'bg-bad/10 text-bad',
}

/** Small rectangular tag (not a pill). Status uses <StatusDot>, not colored badges. */
export function Badge({ tone = 'neutral', className, children, ...props }) {
  return (
    <span className={cn('inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-sm px-1.5 text-2xs font-medium', TONES[tone] || TONES.neutral, className)} {...props}>
      {children}
    </span>
  )
}

const DOT = { ok: 'bg-ok', warn: 'bg-warn', bad: 'bg-bad', neutral: 'bg-fg-muted', accent: 'bg-accent' }

/** Status as a small colored dot + plain text. */
export function StatusDot({ status = 'neutral', label, className, textClassName }) {
  return (
    <span className={cn('inline-flex min-w-0 items-center gap-1.5 text-xs', className)}>
      <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', DOT[status] || DOT.neutral)} aria-hidden />
      {label != null && <span className={cn('truncate text-fg-2', textClassName)}>{label}</span>}
    </span>
  )
}
