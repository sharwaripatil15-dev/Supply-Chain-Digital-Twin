import { cn } from './cn.js'

const TONES = {
  neutral: 'bg-surface-2 text-fg-2 border-border',
  accent: 'bg-accent/10 text-accent border-accent/20',
  ok: 'bg-ok/10 text-ok border-ok/20',
  warn: 'bg-warn/10 text-warn border-warn/25',
  bad: 'bg-bad/10 text-bad border-bad/20',
}
const DOTS = { neutral: 'bg-fg-muted', accent: 'bg-accent', ok: 'bg-ok', warn: 'bg-warn', bad: 'bg-bad' }

/** Small status pill. `dot` adds a leading status dot so meaning is never color-only alongside the label. */
export function Badge({ tone = 'neutral', dot = false, icon: Icon, className, children, ...props }) {
  return (
    <span
      className={cn(
        'inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-md border px-1.5 text-xs font-medium',
        TONES[tone],
        className,
      )}
      {...props}
    >
      {dot && <span className={cn('h-1.5 w-1.5 rounded-full', DOTS[tone])} aria-hidden />}
      {Icon && <Icon className="h-3 w-3" aria-hidden />}
      {children}
    </span>
  )
}
