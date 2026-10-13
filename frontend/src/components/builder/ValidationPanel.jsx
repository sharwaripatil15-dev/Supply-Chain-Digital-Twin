import { useEffect, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { NodeTag } from '../NodeTypeIcon.jsx'
import { cn } from '../ui/index.js'

function Issue({ issue, tone, onGoTo, isEdge }) {
  return (
    <li className="flex items-start gap-2 py-1 text-xs">
      <span className={cn('mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full', tone === 'bad' ? 'bg-bad' : 'bg-warn')} aria-hidden />
      <span className={cn('min-w-0 flex-1 leading-5', tone === 'bad' ? 'text-bad' : 'text-fg-2')}>
        {issue.message}
        {issue.refs?.length > 0 && (
          <span className="ml-1.5 inline-flex flex-wrap gap-1 align-middle">
            {issue.refs.slice(0, 6).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => onGoTo?.(r)}
                className="inline-flex h-5 items-center rounded-sm border border-border bg-surface px-1 text-2xs text-fg-2 hover:border-border-strong hover:text-fg"
                title={`Go to ${r}`}
              >
                {isEdge(r) ? <span className="num">lane {r}</span> : <NodeTag id={r} showName={false} className="gap-1" />}
              </button>
            ))}
          </span>
        )}
      </span>
    </li>
  )
}

/** Always-visible validation summary. Errors (red) block Apply; warnings (amber) do not. Refs jump to the item. */
export default function ValidationPanel({ validation, onGoTo, edgeIds }) {
  const errors = validation?.errors ?? []
  const warnings = validation?.warnings ?? []
  const [open, setOpen] = useState(errors.length > 0)
  useEffect(() => {
    if (errors.length > 0) setOpen(true)
  }, [errors.length])
  if (!validation) return null
  const isEdge = (r) => edgeIds?.has(r)
  const total = errors.length + warnings.length
  return (
    <section aria-label="Validation" aria-live="polite" className="rounded-lg border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={total === 0}
        aria-expanded={total ? open : undefined}
        className="flex h-9 w-full items-center gap-2 px-3 text-left text-xs"
      >
        {total > 0 && <ChevronRight className={cn('h-3.5 w-3.5 text-fg-muted transition-transform duration-150', open && 'rotate-90')} aria-hidden />}
        <span className={cn('h-1.5 w-1.5 rounded-full', errors.length ? 'bg-bad' : warnings.length ? 'bg-warn' : 'bg-ok')} aria-hidden />
        <span className="text-fg">
          {errors.length ? `${errors.length} error${errors.length === 1 ? '' : 's'} to fix before applying` : 'Ready to apply'}
        </span>
        {warnings.length > 0 && (
          <span className="text-fg-muted">
            · {warnings.length} warning{warnings.length === 1 ? '' : 's'}
          </span>
        )}
      </button>
      {open && total > 0 && (
        <ul className="max-h-48 overflow-y-auto border-t border-border px-3 py-1.5">
          {errors.map((i, k) => (
            <Issue key={`e${k}-${i.code}`} issue={i} tone="bad" onGoTo={onGoTo} isEdge={isEdge} />
          ))}
          {warnings.map((i, k) => (
            <Issue key={`w${k}-${i.code}`} issue={i} tone="warn" onGoTo={onGoTo} isEdge={isEdge} />
          ))}
        </ul>
      )}
    </section>
  )
}
