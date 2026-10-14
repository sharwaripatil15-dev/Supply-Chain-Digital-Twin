import { GLOSSARY } from '../lib/glossary.js'
import { Tooltip, cn } from './ui/index.js'

/** A metric name with its canonical definition in a tooltip (keyboard-focusable). */
export function Term({ id, children, className }) {
  const g = GLOSSARY[id]
  if (!g) return children ?? null
  return (
    <Tooltip content={g.text} wide>
      <button type="button" className={cn('cursor-help text-left underline decoration-fg-muted/50 decoration-dotted underline-offset-2', className)}>
        {children ?? g.label}
      </button>
    </Tooltip>
  )
}
