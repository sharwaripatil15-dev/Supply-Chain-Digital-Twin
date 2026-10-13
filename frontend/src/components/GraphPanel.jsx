import { Component, Suspense, lazy, useCallback, useMemo, useState } from 'react'
import { Box, Layers, Map as MapIcon } from 'lucide-react'
import { NODE_KINDS, STATUS_COLORS, typeOf } from '../lib/nodeTypes.js'
import { hasWebGL } from '../lib/disruption.js'
import { useStore } from '../store.js'
import { Card, CardHeader, InlineError, SegmentedControl, Skeleton, cn } from './ui/index.js'
import NetworkGraph from './NetworkGraph.jsx'
import { ShapeThumb, TypeIcon } from './NodeTypeIcon.jsx'

// deck.gl + MapLibre are large: load them only when the 3D view is first opened.
const Network3D = lazy(() => import('./map3d/Network3D.jsx'))

class ViewErrorBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) {
    return { error }
  }
  render() {
    if (this.state.error) return this.props.fallback(this.state.error)
    return this.props.children
  }
}

/**
 * Node-type legend shared by the 2D and 3D views: 3D footprint, glyph and color per type, click to show/hide a type,
 * plus the status-ring key. `counts` hides types that are absent from the network.
 */
export function TypeLegend({ hidden, onToggle, counts, compact = false, extra = null }) {
  const kinds = NODE_KINDS.filter((k) => !counts || counts[k])
  return (
    <ul className={cn('flex flex-wrap items-center gap-1.5 text-xs', compact && 'gap-1')} aria-label="Node types">
      {kinds.map((k) => {
        const t = typeOf(k)
        const off = hidden?.has(k)
        return (
          <li key={k}>
            <button
              type="button"
              onClick={() => onToggle?.(k)}
              aria-pressed={!off}
              title={`${off ? 'Show' : 'Hide'} ${t.plural.toLowerCase()}`}
              className={cn(
                'inline-flex h-7 items-center gap-1.5 rounded-md border px-1.5 font-medium transition-colors duration-150',
                off ? 'border-dashed border-border text-fg-muted opacity-60 hover:opacity-100' : 'border-border bg-surface text-fg-2 hover:border-border-strong',
              )}
            >
              <ShapeThumb kind={k} className="h-3.5 w-3.5" filled={!off} />
              <TypeIcon kind={k} size="xs" />
              {t.plural}
              {counts && <span className="tabular text-fg-muted">{counts[k]}</span>}
            </button>
          </li>
        )
      })}
      <li className="ml-1 flex items-center gap-2 text-fg-muted" aria-label="Status rings">
        {Object.entries(STATUS_COLORS).map(([k, s]) => (
          <span key={k} className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-full border-2 bg-transparent" style={{ borderColor: s.color }} aria-hidden />
            {s.label}
          </span>
        ))}
      </li>
      {extra}
    </ul>
  )
}

const EXTRA_2D = (
  <li className="flex items-center gap-2 text-fg-muted">
    <span className="inline-flex items-center gap-1">
      <span className="h-2.5 w-2.5 rounded-full bg-accent/30" aria-hidden />
      glow = criticality
    </span>
    <span className="inline-flex items-center gap-1">
      <span className="w-4 border-t-2 border-dashed border-bad" aria-hidden />
      disrupted
    </span>
    <span className="inline-flex items-center gap-1">
      <span className="h-2.5 w-2.5 rounded-full bg-warn/40" aria-hidden />
      bottleneck &gt;90%
    </span>
  </li>
)

/** Shared show/hide state for node types. */
export function useTypeFilter() {
  const [hidden, setHidden] = useState(() => new Set())
  const toggle = useCallback(
    (kind) =>
      setHidden((cur) => {
        const next = new Set(cur)
        if (next.has(kind)) next.delete(kind)
        else next.add(kind)
        return next
      }),
    [],
  )
  return [hidden, toggle]
}

/**
 * Network card with a 2D | 3D toggle. 2D (Cytoscape) is the default and the fallback: 3D is offered only when
 * WebGL is available, is lazy-loaded, and drops back to 2D if it fails to initialise.
 * `view3d` carries the extra 3D-only props (mode, rerouted lanes, focus targets...).
 */
export default function GraphPanel({
  title = 'Network',
  icon,
  description,
  actions,
  network: networkProp,
  statuses,
  utilization,
  disrupted,
  highlight,
  view3d = {},
  allow3d = true,
  heightClass = 'h-[560px]',
  footer,
}) {
  const store = useStore()
  const network = networkProp || store.network
  const webgl = hasWebGL()
  const [view, setView] = useState('2d')
  const [layout, setLayout] = useState('geo')
  const [hidden, toggle] = useTypeFilter()
  const showing3d = allow3d && webgl && view === '3d'
  const counts = useMemo(() => {
    const c = {}
    for (const n of network?.nodes ?? []) c[n.kind] = (c[n.kind] || 0) + 1
    return c
  }, [network])

  const graph2d = (
    <NetworkGraph network={network} statuses={statuses} utilization={utilization} disrupted={disrupted} highlight={highlight} hiddenKinds={hidden} layout={layout} />
  )
  return (
    <Card className="flex flex-col">
      <CardHeader
        icon={icon}
        title={title}
        description={description}
        actions={
          <>
            {actions}
            {!showing3d && (
              <SegmentedControl
                size="sm"
                label="2D layout"
                value={layout}
                onChange={setLayout}
                options={[
                  { value: 'geo', label: 'Geo', icon: MapIcon, title: 'Positions follow latitude / longitude' },
                  { value: 'tiers', label: 'Tiers', icon: Layers, title: 'Layered: suppliers → factories → warehouses → retailers → customers' },
                ]}
              />
            )}
            {allow3d && (
              <SegmentedControl
                size="sm"
                label="Network view"
                value={showing3d ? '3d' : '2d'}
                onChange={setView}
                options={[
                  { value: '2d', label: '2D', icon: MapIcon },
                  { value: '3d', label: '3D', icon: Box, disabled: !webgl, title: webgl ? '3D geospatial view' : 'WebGL is not available in this browser' },
                ]}
              />
            )}
          </>
        }
      />
      <div className={cn('relative mx-5 mt-4 overflow-hidden rounded-lg border border-border bg-surface-2/40', heightClass)}>
        {showing3d ? (
          <ViewErrorBoundary
            fallback={(err) => (
              <div className="flex h-full flex-col">
                <InlineError className="m-3" message={`3D view unavailable (${err?.message || 'unknown error'}). Showing the 2D view.`} />
                <div className="flex-1">{graph2d}</div>
              </div>
            )}
          >
            <Suspense fallback={<Skeleton className="h-full w-full rounded-none" />}>
              <Network3D
                network={network}
                statuses={statuses}
                utilization={utilization}
                disrupted={disrupted}
                highlight={highlight}
                hiddenKinds={hidden}
                {...view3d}
              />
            </Suspense>
          </ViewErrorBoundary>
        ) : (
          graph2d
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3 px-5 py-3">
        <TypeLegend hidden={hidden} onToggle={toggle} counts={counts} extra={showing3d ? null : EXTRA_2D} />
        <span className="ml-auto text-xs text-fg-muted">
          {showing3d ? 'Drag to pan · right-drag to orbit · click a node for details' : 'Click a node for details · click a type to hide it'}
        </span>
      </div>
      {footer && <div className="border-t border-border">{footer}</div>}
    </Card>
  )
}
