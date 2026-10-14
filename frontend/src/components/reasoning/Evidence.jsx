import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { cn } from '../ui/index.js'
import { useUi } from '../../ui.jsx'

const isPlain = (v) => v == null || ['string', 'number', 'boolean'].includes(typeof v)
const label = (k) => String(k).replaceAll('_', ' ')
const fmt = (v) => (typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString('en-IN') : Number(v.toFixed(4)).toLocaleString('en-IN')) : v == null ? '–' : String(v))

/** Recursive, compact view of engine evidence: scalars as key/value rows, arrays of flat objects as tables. */
function Value({ value, depth = 0 }) {
  if (isPlain(value)) return <span className="num break-words text-fg">{fmt(value)}</span>
  if (Array.isArray(value)) {
    if (!value.length) return <span className="text-fg-muted">none</span>
    if (value.every(isPlain)) return <span className="num break-words text-fg">{value.map(fmt).join(', ')}</span>
    const flat = value.every((r) => r && typeof r === 'object' && !Array.isArray(r) && Object.values(r).every(isPlain))
    if (flat) {
      const cols = [...new Set(value.flatMap((r) => Object.keys(r)))].slice(0, 9)
      return (
        <div className="overflow-x-auto">
          <table className="w-full text-2xs">
            <thead>
              <tr>
                {cols.map((c) => (
                  <th key={c} className="whitespace-nowrap border-b border-border px-1.5 py-1 text-left font-medium text-fg-muted">
                    {label(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {value.slice(0, 40).map((r, i) => (
                <tr key={i}>
                  {cols.map((c) => (
                    <td key={c} className="num whitespace-nowrap border-b border-border/60 px-1.5 py-0.5 text-fg-2">
                      {fmt(r[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }
    return (
      <ol className="space-y-1">
        {value.slice(0, 30).map((v, i) => (
          <li key={i} className="rounded-sm border border-border/60 p-1.5">
            <Value value={v} depth={depth + 1} />
          </li>
        ))}
      </ol>
    )
  }
  const entries = Object.entries(value)
  if (!entries.length) return <span className="text-fg-muted">none</span>
  return (
    <dl className={cn('grid grid-cols-[minmax(7rem,max-content)_minmax(0,1fr)] gap-x-3 gap-y-0.5', depth > 0 && 'text-2xs')}>
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="truncate text-fg-muted" title={k}>
            {label(k)}
          </dt>
          <dd className="min-w-0">
            <Value value={v} depth={depth + 1} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

/** "Evidence" expander: the exact engine numbers and counterfactuals a section was written from. */
export default function Evidence({ data, title = 'Evidence', defaultOpen = false, className }) {
  const [open, setOpen] = useState(defaultOpen)
  const [raw, setRaw] = useState(false)
  const { analyst } = useUi()
  if (!data || !analyst) return null // Executive view hides the evidence; Analyst view shows it
  return (
    <div className={cn('rounded-md border border-border', className)}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-xs text-fg-2 hover:bg-raised"
      >
        <ChevronRight className={cn('h-3.5 w-3.5 transition-transform duration-150', open && 'rotate-90')} aria-hidden />
        {title}
        <span className="ml-auto text-2xs text-fg-muted">engine output, simulated</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-border px-2.5 py-2 text-xs">
          <div className="flex justify-end">
            <button type="button" className="text-2xs text-fg-muted underline-offset-2 hover:underline" onClick={() => setRaw((v) => !v)}>
              {raw ? 'Formatted view' : 'Raw JSON'}
            </button>
          </div>
          {raw ? (
            <pre className="num max-h-80 overflow-auto whitespace-pre-wrap break-words text-2xs text-fg-2">{JSON.stringify(data, null, 1)}</pre>
          ) : (
            <div className="max-h-96 overflow-auto">
              <Value value={data} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
