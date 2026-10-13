import { cn } from './cn.js'

export function Skeleton({ className }) {
  return <div className={cn('animate-shimmer rounded-md bg-surface-3', className)} aria-hidden />
}

/** A labelled loading placeholder: several skeleton lines, announced to screen readers. */
export function SkeletonBlock({ lines = 3, label = 'Loading', className }) {
  return (
    <div role="status" aria-label={label} className={cn('space-y-2.5', className)}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={cn('h-4', i === lines - 1 ? 'w-2/3' : 'w-full')} />
      ))}
    </div>
  )
}
