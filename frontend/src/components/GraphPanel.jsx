import { Component, Suspense, lazy, useState } from 'react'
import { Box, Map as MapIcon } from 'lucide-react'
import { KIND, STATUS } from '../format.js'
import { hasWebGL } from '../lib/disruption.js'
import { useStore } from '../store.js'
import { Card, CardHeader, InlineError, SegmentedControl, Skeleton, cn } from './ui/index.js'
import NetworkGraph from './NetworkGraph.jsx'

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

export function Legend({ statuses, extra = [] }) {
  const items = statuses
    ? Object.entries(STATUS).map(([k, s]) => ({ key: k, swatch: `bg-${s.token}`, label: s.label, round: true }))
    : Object.entries(KIND).map(([k, s]) => ({ key: k, swatch: s.swatch, label: s.label }))
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-fg-muted">
      {items.map((i) => (
        <li key={i.key} className="flex items-center gap-1.5">
          <span className={cn('h-2.5 w-2.5', i.round ? 'rounded-full' : 'rounded-sm', i.swatch)} aria-hidden />
          {i.label}
        </li>
      ))}
      {extra.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          {i.mark}
          {i.label}
        </li>
      ))}
    </ul>
  )
}

const LEGEND_2D = [
  { label: 'ring = criticality', mark: <span className="h-2.5 w-2.5 rounded-full border-2 border-accent/50" aria-hidden /> },
  { label: 'disrupted lane', mark: <span className="w-4 border-t-2 border-dashed border-bad" aria-hidden /> },
  { label: 'bottleneck >90%', mark: <span className="h-2.5 w-2.5 rounded-full bg-warn/40" aria-hidden /> },
]

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
  const showing3d = allow3d && webgl && view === '3d'
  return (
    <Card className="flex flex-col">
      <CardHeader
        icon={icon}
        title={title}
        description={description}
        actions={
          <>
            {actions}
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
                <InlineError className="m-3" message={`3D view unavailable (${err.message}). Showing the 2D view.`} />
                <div className="flex-1">
                  <NetworkGraph network={network} statuses={statuses} utilization={utilization} disrupted={disrupted} highlight={highlight} />
                </div>
              </div>
            )}
          >
            <Suspense fallback={<Skeleton className="h-full w-full rounded-none" />}>
              <Network3D network={network} statuses={statuses} utilization={utilization} disrupted={disrupted} highlight={highlight} {...view3d} />
            </Suspense>
          </ViewErrorBoundary>
        ) : (
          <NetworkGraph network={network} statuses={statuses} utilization={utilization} disrupted={disrupted} highlight={highlight} />
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3 px-5 py-3">
        {!showing3d && <Legend statuses={statuses} extra={LEGEND_2D} />}
        {showing3d && <span className="text-xs text-fg-muted">Drag to pan · right-drag or Ctrl-drag to orbit · scroll to zoom</span>}
        <span className="ml-auto text-xs text-fg-muted">Click a node for details</span>
      </div>
      {footer && <div className="border-t border-border">{footer}</div>}
    </Card>
  )
}
