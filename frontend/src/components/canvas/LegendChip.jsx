import { useEffect, useRef, useState } from 'react'
import { ChevronUp } from 'lucide-react'
import { fmtNum } from '../../format.js'
import { MODES, NODE_KINDS, STATUS_COLORS, typeOf } from '../../lib/nodeTypes.js'
import { cn } from '../ui/index.js'
import { ShapeThumb, TypeIcon } from '../NodeTypeIcon.jsx'

function Row({ children }) {
  return <li className="flex items-center gap-2 text-xs text-fg-2">{children}</li>
}

/**
 * Collapsed legend chip (bottom-left of a canvas) that expands into the full key. Node types are toggles:
 * click one to hide or show it on the canvas.
 */
export default function LegendChip({ view = '2d', hidden, onToggle, counts, maxStock }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => !ref.current?.contains(e.target) && setOpen(false)
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  const kinds = NODE_KINDS.filter((k) => !counts || counts[k])
  const hiddenCount = kinds.filter((k) => hidden?.has(k)).length

  return (
    <div ref={ref} className="relative">
      {open && (
        <div role="dialog" aria-label="Legend" className="absolute bottom-full left-0 mb-2 w-64 animate-rise-in rounded-lg border border-border bg-surface p-3 shadow-float">
          <h3 className="section-label mb-1.5">Node types</h3>
          <ul className="-mx-1 space-y-0.5">
            {kinds.map((k) => {
              const off = hidden?.has(k)
              return (
                <li key={k}>
                  <button
                    type="button"
                    onClick={() => onToggle?.(k)}
                    aria-pressed={!off}
                    className={cn('flex h-7 w-full items-center gap-2 rounded-md px-1 text-left text-xs transition-colors duration-150 hover:bg-raised', off ? 'text-fg-muted' : 'text-fg')}
                  >
                    <ShapeThumb kind={k} className={cn('h-3.5 w-3.5', off && 'opacity-30')} filled={!off} />
                    <TypeIcon kind={k} size="xs" className={off ? 'opacity-30' : ''} />
                    <span className={cn('flex-1', off && 'line-through')}>{typeOf(k).plural}</span>
                    {counts && <span className="num text-fg-muted">{counts[k]}</span>}
                  </button>
                </li>
              )
            })}
          </ul>
          <h3 className="section-label mb-1.5 mt-3">Status</h3>
          <ul className="flex gap-3">
            {Object.entries(STATUS_COLORS).map(([k, s]) => (
              <Row key={k}>
                <span className="h-2.5 w-2.5 rounded-full border-2" style={{ borderColor: s.color }} aria-hidden />
                {s.label}
              </Row>
            ))}
          </ul>
          <h3 className="section-label mb-1.5 mt-3">Lanes</h3>
          <ul className="space-y-1">
            <Row>
              <span className="w-4 border-t-2 border-fg-muted/60" aria-hidden />
              Lane, colored by its source type{view === '3d' ? '; width = capacity' : ''}
            </Row>
            <Row>
              <span className="w-4 border-t-2 border-dashed border-bad" aria-hidden />
              Disrupted
            </Row>
            <Row>
              <span className="w-4 border-t-2 border-accent" aria-hidden />
              Recovery route
            </Row>
            {view === '3d' && (
              <Row>
                <span className="flex gap-1" aria-hidden>
                  {Object.values(MODES).map((m) => (
                    <span key={m.label} className="h-2 w-2 rounded-full ring-1 ring-border-strong" style={{ backgroundColor: m.color }} />
                  ))}
                </span>
                Flow: {Object.values(MODES).map((m) => m.label.toLowerCase()).join(', ')}
              </Row>
            )}
          </ul>
          {view === '3d' && maxStock > 0 && (
            <>
              <h3 className="section-label mb-1.5 mt-3">Height = stock</h3>
              <div className="flex items-end gap-2" aria-label={`Column height shows stock; the tallest is ${fmtNum(maxStock)} units`}>
                <div className="flex h-10 items-end gap-0.5" aria-hidden>
                  {[0.15, 0.35, 0.6, 1].map((h) => (
                    <span key={h} className="w-1.5 rounded-t-sm bg-fg-muted/50" style={{ height: `${h * 100}%` }} />
                  ))}
                </div>
                <div className="num text-2xs leading-4 text-fg-muted">
                  <div>{fmtNum(maxStock)} units</div>
                  <div>0</div>
                </div>
              </div>
            </>
          )}
          <p className="mt-3 text-2xs text-fg-muted">Glow = criticality (ML-predicted).</p>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex h-7 items-center gap-2 rounded-md border border-border bg-surface/95 px-2 text-xs text-fg-2 transition-colors duration-150 hover:bg-raised hover:text-fg"
      >
        <span className="flex -space-x-0.5" aria-hidden>
          {kinds.map((k) => (
            <span key={k} className="h-2 w-2 rounded-full ring-1 ring-surface" style={{ backgroundColor: typeOf(k).color }} />
          ))}
        </span>
        Legend
        {hiddenCount > 0 && <span className="num text-fg-muted">{hiddenCount} hidden</span>}
        <ChevronUp className={cn('h-3.5 w-3.5 text-fg-muted transition-transform duration-150', !open && 'rotate-180')} aria-hidden />
      </button>
    </div>
  )
}
