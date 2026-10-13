import { typeOf } from '../lib/nodeTypes.js'
import { useStore } from '../store.js'
import { cn } from './ui/index.js'

/** The type glyph, drawn from the same paths the 2D graph and 3D map use. */
export function TypeGlyph({ kind, className, strokeWidth = 2.2 }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {typeOf(kind).glyph.map(([Tag, attrs], i) => (
        <Tag key={i} {...attrs} />
      ))}
    </svg>
  )
}

const SIZES = { xs: 'h-4 w-4 rounded', sm: 'h-5 w-5 rounded-md', md: 'h-7 w-7 rounded-lg', lg: 'h-9 w-9 rounded-lg' }
const GLYPH = { xs: 'h-2.5 w-2.5', sm: 'h-3 w-3', md: 'h-4 w-4', lg: 'h-5 w-5' }

/** Small type chip: white glyph on the type color. */
export function TypeIcon({ kind, size = 'sm', className, title }) {
  const t = typeOf(kind)
  return (
    <span
      className={cn('inline-flex shrink-0 items-center justify-center text-white ring-1 ring-inset ring-black/10 dark:ring-white/25', SIZES[size], className)}
      style={{ backgroundColor: t.color }}
      title={title ?? t.label}
      role="img"
      aria-label={t.label}
    >
      <TypeGlyph kind={kind} className={GLYPH[size]} />
    </span>
  )
}

/** Outline of a type's 3D footprint (triangle, square, hexagon, octagon, circle) for legends. */
export function ShapeThumb({ kind, className = 'h-4 w-4', filled = true }) {
  const t = typeOf(kind)
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path d={t.thumb} fill={filled ? t.color : 'none'} fillOpacity={filled ? 0.9 : 0} stroke={t.color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}

/**
 * "[icon] S2 Chennai Electronics": the standard way to name a node anywhere in the UI.
 * Looks the node up in the active network when only an id is given; lanes ("U->V") render both ends.
 */
export function NodeTag({ id, node: nodeProp, showName = true, size = 'xs', className, nameClassName }) {
  const { network } = useStore()
  if (id && id.includes('->')) {
    const [u, v] = id.split('->')
    return (
      <span className={cn('inline-flex flex-wrap items-center gap-1', className)}>
        <NodeTag id={u} showName={false} size={size} />
        <span className="text-fg-muted">→</span>
        <NodeTag id={v} showName={false} size={size} />
      </span>
    )
  }
  const node = nodeProp || network?.nodes?.find((n) => n.id === id)
  const nid = node?.id ?? id
  return (
    <span className={cn('inline-flex min-w-0 items-center gap-1.5', className)}>
      <TypeIcon kind={node?.kind} size={size} />
      <span className="font-medium text-fg">{nid}</span>
      {showName && node?.name && node.name !== nid && <span className={cn('truncate font-normal text-fg-2', nameClassName)}>{node.name}</span>}
    </span>
  )
}
