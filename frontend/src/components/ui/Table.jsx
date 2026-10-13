import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, Columns3 } from 'lucide-react'
import { cn } from './cn.js'
import { Menu } from './Menu.jsx'

/** Scrollable table with a sticky header. Pass max-height classes (e.g. "max-h-96") to scroll the body. */
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
        'sticky top-0 z-[1] h-8 whitespace-nowrap border-b border-border bg-surface px-3 text-xs font-medium text-fg-muted first:pl-4 last:pr-4',
        numeric ? 'text-right' : 'text-left',
        className,
      )}
      {...props}
    >
      {children}
    </th>
  )
}

export function Tr({ className, selected, children, onClick, ...props }) {
  const interactive = Boolean(onClick)
  return (
    <tr
      onClick={onClick}
      onKeyDown={
        interactive
          ? (e) => {
              if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) {
                e.preventDefault()
                onClick(e)
              }
            }
          : undefined
      }
      tabIndex={interactive ? 0 : undefined}
      aria-selected={interactive ? Boolean(selected) : undefined}
      data-selected={selected || undefined}
      className={cn(
        'group transition-colors duration-100',
        interactive && 'cursor-pointer hover:bg-raised/70 focus-visible:bg-raised focus-visible:outline-none',
        selected && 'bg-accent/[0.07] hover:bg-accent/10',
        className,
      )}
      {...props}
    >
      {children}
    </tr>
  )
}

export function Td({ numeric, mono, className, children, ...props }) {
  return (
    <td
      className={cn(
        'h-[34px] whitespace-nowrap border-b border-border/70 px-3 align-middle first:pl-4 last:pr-4 group-last:border-b-0',
        numeric && 'num text-right text-xs text-fg',
        mono && 'num text-xs',
        className,
      )}
      {...props}
    >
      {children}
    </td>
  )
}

const valueOf = (col, row) => (col.sortValue ? col.sortValue(row) : col.value ? col.value(row) : row[col.key])

function compare(a, b) {
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b), undefined, { numeric: true })
}

/**
 * Compact data table: sortable columns, a column-visibility menu, row hover/selection, right-aligned mono numbers.
 * columns: [{ key, header, align?: 'right', render?(row), value?(row), sortValue?(row), sortable?, hideable?,
 *             defaultHidden?, mono?, className?, headerClassName?, width? }]
 * toolbar: optional node rendered left of the "Columns" menu (search, filters...).
 */
export function DataTable({
  columns,
  rows,
  rowKey = (r) => r.id,
  label,
  selectedKey,
  onRowClick,
  defaultSort = null,
  toolbar,
  columnMenu = true,
  empty = 'No rows.',
  className,
  bodyClassName,
}) {
  const [sort, setSort] = useState(defaultSort) // { key, dir: 'asc' | 'desc' }
  const [hidden, setHidden] = useState(() => new Set(columns.filter((c) => c.defaultHidden).map((c) => c.key)))
  const visible = columns.filter((c) => !hidden.has(c.key))
  const hideable = columns.filter((c) => c.hideable !== false && c.header)

  const sorted = useMemo(() => {
    if (!sort) return rows
    const col = columns.find((c) => c.key === sort.key)
    if (!col) return rows
    const out = [...rows].sort((a, b) => compare(valueOf(col, a), valueOf(col, b)))
    return sort.dir === 'desc' ? out.reverse() : out
  }, [rows, sort, columns])

  const toggleSort = (col) => {
    if (col.sortable === false) return
    // first click: natural direction (largest first for numbers); second: reverse; third: back to the default order
    const first = col.align === 'right' ? 'desc' : 'asc'
    setSort((s) => {
      if (!s || s.key !== col.key) return { key: col.key, dir: first }
      if (s.dir === first) return { key: col.key, dir: first === 'asc' ? 'desc' : 'asc' }
      return defaultSort
    })
  }

  return (
    <div className={cn('flex min-h-0 flex-col', className)}>
      {(toolbar || (columnMenu && hideable.length > 1)) && (
        <div className="flex items-center gap-2 px-4 py-2">
          <div className="flex min-w-0 flex-1 items-center gap-2">{toolbar}</div>
          {columnMenu && hideable.length > 1 && (
            <Menu
              icon={Columns3}
              iconOnly
              label="Columns"
              triggerLabel="Show or hide columns"
              variant="ghost"
              size="sm"
              items={hideable.map((c) => ({
                key: c.key,
                label: typeof c.header === 'string' ? c.header : c.key,
                checked: !hidden.has(c.key),
                onSelect: () =>
                  setHidden((h) => {
                    const next = new Set(h)
                    if (next.has(c.key)) next.delete(c.key)
                    else if (visible.length > 1) next.add(c.key)
                    return next
                  }),
              }))}
            />
          )}
        </div>
      )}
      <Table label={label} className={cn('min-h-0 flex-1', bodyClassName)}>
        <thead>
          <tr>
            {visible.map((c) => {
              const active = sort?.key === c.key
              const sortable = c.sortable !== false && c.header
              return (
                <Th
                  key={c.key}
                  numeric={c.align === 'right'}
                  className={cn(c.width, c.headerClassName)}
                  aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : sortable ? 'none' : undefined}
                >
                  {sortable ? (
                    <button
                      type="button"
                      onClick={() => toggleSort(c)}
                      className={cn('inline-flex items-center gap-1 rounded-sm hover:text-fg', active && 'text-fg', c.align === 'right' && 'flex-row-reverse')}
                    >
                      {c.header}
                      {active ? (
                        sort.dir === 'asc' ? <ArrowUp className="h-3 w-3" aria-hidden /> : <ArrowDown className="h-3 w-3" aria-hidden />
                      ) : (
                        <span className="h-3 w-3" aria-hidden />
                      )}
                    </button>
                  ) : (
                    c.header
                  )}
                </Th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={visible.length} className="px-4 py-6 text-center text-xs text-fg-muted">
                {empty}
              </td>
            </tr>
          ) : (
            sorted.map((row) => {
              const key = rowKey(row)
              return (
                <Tr key={key} selected={selectedKey != null && key === selectedKey} onClick={onRowClick ? () => onRowClick(row) : undefined}>
                  {visible.map((c) => (
                    <Td key={c.key} numeric={c.align === 'right'} mono={c.mono} className={c.className}>
                      {c.render ? c.render(row) : valueOf(c, row)}
                    </Td>
                  ))}
                </Tr>
              )
            })
          )}
        </tbody>
      </Table>
    </div>
  )
}
