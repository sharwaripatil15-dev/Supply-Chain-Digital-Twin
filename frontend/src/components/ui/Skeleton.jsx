import { cn } from './cn.js'

export function Skeleton({ className }) {
  return <div className={cn('animate-pulse-soft rounded-sm bg-raised', className)} aria-hidden />
}

/** A labelled loading placeholder: several lines, announced to screen readers. */
export function SkeletonBlock({ lines = 3, label = 'Loading', className }) {
  return (
    <div role="status" aria-label={label} className={cn('space-y-2.5', className)}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={cn('h-3.5', i === lines - 1 ? 'w-2/3' : 'w-full')} />
      ))}
    </div>
  )
}

/** Table-shaped placeholder: header + rows at the real row height. */
export function SkeletonRows({ rows = 6, label = 'Loading', className }) {
  return (
    <div role="status" aria-label={label} className={cn('px-4', className)}>
      <Skeleton className="mb-3 mt-2 h-3 w-1/3" />
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex h-[34px] items-center gap-4 border-b border-border/70 last:border-b-0">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-3 flex-1" />
          <Skeleton className="h-3 w-12" />
        </div>
      ))}
    </div>
  )
}
