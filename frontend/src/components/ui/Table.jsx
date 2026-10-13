import { cn } from './cn.js'

/** Scrollable table with a sticky header. Pass `maxHeight` classes (e.g. "max-h-96") to make the body scroll. */
export function Table({ className, children, label }) {
  return (
    <div className={cn('overflow-auto', className)}>
      <table className="w-full border-separate border-spacing-0 text-sm" aria-label={label}>
        {children}
      </table>
    </div>
  )
}

export function Th({ numeric, className, children, ...props }) {
  return (
    <th
      scope="col"
      className={cn(
        'sticky top-0 z-[1] border-b border-border bg-surface px-3 py-2 text-xs font-medium text-fg-muted first:pl-5 last:pr-5',
        numeric ? 'text-right' : 'text-left',
        className,
      )}
      {...props}
    >
      {children}
    </th>
  )
}

export function Tr({ className, selected, children, ...props }) {
  return (
    <tr
      className={cn(
        'group transition-colors duration-150 hover:bg-surface-2/70',
        selected && 'bg-accent/5 hover:bg-accent/10',
        props.onClick && 'cursor-pointer',
        className,
      )}
      aria-selected={selected || undefined}
      {...props}
    >
      {children}
    </tr>
  )
}

export function Td({ numeric, className, children, ...props }) {
  return (
    <td
      className={cn(
        'border-b border-border/70 px-3 py-2.5 align-top first:pl-5 last:pr-5 group-last:border-b-0',
        numeric && 'tabular whitespace-nowrap text-right',
        className,
      )}
      {...props}
    >
      {children}
    </td>
  )
}
