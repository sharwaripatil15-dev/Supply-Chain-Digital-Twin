import { cn } from './cn.js'

const SIDE = {
  top: 'bottom-full left-1/2 mb-1.5 -translate-x-1/2',
  bottom: 'top-full left-1/2 mt-1.5 -translate-x-1/2',
  right: 'left-full top-1/2 ml-2 -translate-y-1/2',
  left: 'right-full top-1/2 mr-2 -translate-y-1/2',
  'bottom-end': 'top-full right-0 mt-1.5',
  'bottom-start': 'top-full left-0 mt-1.5',
  'top-start': 'bottom-full left-0 mb-1.5',
}

/** Keyboard key hint, e.g. <Kbd>Ctrl K</Kbd>. */
export function Kbd({ children, className }) {
  return (
    <kbd className={cn('inline-flex h-4 min-w-4 items-center justify-center rounded-sm border border-border bg-raised px-1 font-mono text-2xs leading-none text-fg-muted', className)}>
      {children}
    </kbd>
  )
}

/**
 * Hover / keyboard-focus tooltip with an optional shortcut. Appears after a short delay on hover, at once on
 * keyboard focus; never on mouse focus. `wide` allows wrapped text (e.g. a safety-check warning).
 */
export function Tooltip({ content, shortcut, children, side = 'top', wide = false, className }) {
  if (!content) return children
  return (
    <span className={cn('group/tt relative inline-flex', className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          'pointer-events-none absolute z-50 flex items-center gap-2 rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg opacity-0 shadow-float transition-opacity duration-150',
          'group-hover/tt:opacity-100 group-hover/tt:delay-300 group-has-[:focus-visible]/tt:opacity-100',
          wide ? 'w-max max-w-xs whitespace-normal leading-4' : 'whitespace-nowrap',
          SIDE[side],
        )}
      >
        {content}
        {shortcut && <Kbd>{shortcut}</Kbd>}
      </span>
    </span>
  )
}
