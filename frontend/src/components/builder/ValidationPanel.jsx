import { CircleCheck, CircleX, TriangleAlert } from 'lucide-react'
import { NodeTag } from '../NodeTypeIcon.jsx'
import { cn } from '../ui/index.js'

function Issue({ issue, tone, onGoTo, isEdge }) {
  const Icon = tone === 'bad' ? CircleX : TriangleAlert
  return (
    <li className={cn('flex items-start gap-2 rounded-md px-2 py-1.5 text-xs', tone === 'bad' ? 'bg-bad/10 text-bad' : 'bg-warn/10 text-warn')}>
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="flex-1 leading-5 text-fg">
        {issue.message}
        {issue.refs?.length > 0 && (
          <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
            {issue.refs.slice(0, 6).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => onGoTo?.(r)}
                className="rounded border border-border bg-surface px-1 py-px text-[11px] font-medium text-fg-2 hover:border-accent hover:text-accent"
                title={`Go to ${r}`}
              >
                {isEdge(r) ? `lane ${r}` : <NodeTag id={r} showName={false} className="gap-1" />}
              </button>
            ))}
          </span>
        )}
      </span>
    </li>
  )
}

/** Always-visible validation summary: errors (red) block Apply, warnings (amber) do not. Refs jump to the item. */
export default function ValidationPanel({ validation, onGoTo, edgeIds }) {
  const errors = validation?.errors ?? []
  const warnings = validation?.warnings ?? []
  const isEdge = (r) => edgeIds?.has(r)
  if (!validation) return null
  return (
    <section aria-label="Validation" aria-live="polite" className="rounded-lg border border-border bg-surface-2/40 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-fg">
        {errors.length === 0 ? (
          <>
            <CircleCheck className="h-4 w-4 text-ok" aria-hidden />
            {warnings.length === 0 ? 'Ready to apply: no problems found' : `Ready to apply, with ${warnings.length} warning${warnings.length === 1 ? '' : 's'}`}
          </>
        ) : (
          <>
            <CircleX className="h-4 w-4 text-bad" aria-hidden />
            {errors.length} error{errors.length === 1 ? '' : 's'} to fix before applying
            {warnings.length > 0 && <span className="font-normal text-fg-muted">· {warnings.length} warning{warnings.length === 1 ? '' : 's'}</span>}
          </>
        )}
      </div>
      {(errors.length > 0 || warnings.length > 0) && (
        <ul className="max-h-48 space-y-1 overflow-auto pr-1">
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
