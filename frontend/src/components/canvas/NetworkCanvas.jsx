import { Component, Suspense, lazy, useCallback, useMemo, useState } from 'react'
import { Clapperboard, Layers, Map as MapIcon, Maximize2, Square } from 'lucide-react'
import { useStore } from '../../store.js'
import { useUi } from '../../ui.jsx'
import { hasWebGL } from '../../lib/disruption.js'
import { Button, IconButton, InlineError, SegmentedControl, Skeleton, cn } from '../ui/index.js'
import NetworkGraph from '../NetworkGraph.jsx'
import LegendChip from './LegendChip.jsx'
import Timeline from './Timeline.jsx'

// deck.gl + MapLibre are large: load them only when the 3D view is first opened.
const Network3D = lazy(() => import('../map3d/Network3D.jsx'))

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

/** Show/hide state for node types (driven by the legend). */
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

function ReplayControl() {
  const { story, startStory, stopStory } = useUi()
  return (
    <Button size="sm" icon={story ? Square : Clapperboard} onClick={story ? stopStory : startStory} title="Replay the disruption with a guided camera">
      {story ? 'Stop replay' : 'Replay'}
    </Button>
  )
}

/**
 * The network workspace canvas: 2D graph (default) or 3D map, a floating toolbar, a collapsed legend and, on
 * Simulate, a docked timeline. 3D is offered only with WebGL, lazy-loaded, and falls back to 2D on any error.
 * `view3d` carries 3D-only props (mode, rerouted lanes, focus targets, disruptedAll...).
 */
export default function NetworkCanvas({ network: networkProp, statuses, utilization, disrupted, highlight, view3d = {}, allow3d = true, timeline = false, className, ghost = null, onGhost = null }) {
  const store = useStore()
  const ui = useUi()
  const network = networkProp || store.network
  const webgl = hasWebGL()
  const [view, setView] = useState('2d')
  const [layout, setLayout] = useState('geo')
  const [hidden, toggle] = useTypeFilter()
  const is3d = allow3d && webgl && view === '3d'
  const counts = useMemo(() => {
    const c = {}
    for (const n of network?.nodes ?? []) c[n.kind] = (c[n.kind] || 0) + 1
    return c
  }, [network])
  // 3D preview of an expansion plan: candidate sites join the network; the recommended ones (and their lanes) stay bright
  const ghost3d = useMemo(() => {
    if (!ghost || !network) return null
    const nodes = ghost.nodes.map((n) => ({ ...n, city: n.name, capacity: 0, stock: 0, demand: 0, risk: null, top_factors: [] }))
    const edges = (ghost.edges || []).map((e) => ({ ...e, lead: 1, cost: 0, co2: 0, capacity: e.capacity || 1 }))
    const picked = ghost.nodes.filter((n) => n.rank).map((n) => n.id)
    return { network: { ...network, nodes: [...network.nodes, ...nodes], edges: [...network.edges, ...edges] }, highlight: picked.length ? [...picked, ...edges.flatMap((e) => [e.source, e.target])] : highlight }
  }, [ghost, network, highlight])
  const maxStock = useMemo(() => Math.max(0, ...(network?.nodes ?? []).filter((n) => !hidden.has(n.kind)).map((n) => n.stock || 0)), [network, hidden])

  const viewToggle = allow3d ? (
    <SegmentedControl
      size="xs"
      label="View"
      value={is3d ? '3d' : '2d'}
      onChange={setView}
      options={[
        { value: '2d', label: '2D', icon: MapIcon },
        { value: '3d', label: '3D', icon: Layers, disabled: !webgl, title: webgl ? '3D map' : 'WebGL is not available in this browser' },
      ]}
    />
  ) : null
  const graph2d = (
    <>
      <NetworkGraph
        network={network}
        statuses={statuses}
        utilization={utilization}
        disrupted={disrupted}
        highlight={highlight}
        hiddenKinds={hidden}
        layout={layout}
        fitSignal={ui.fitSignal}
        ghost={ghost}
        onGhost={onGhost}
      />
      <div className="absolute left-3 top-3 z-10 flex items-center gap-2">
        {viewToggle}
        <SegmentedControl
          size="xs"
          label="2D layout"
          value={layout}
          onChange={setLayout}
          options={[
            { value: 'geo', label: 'Geo', title: 'Positions follow latitude / longitude' },
            { value: 'tiers', label: 'Tiers', title: 'Layered by tier: suppliers to customers' },
          ]}
        />
      </div>
      <div className="absolute right-3 top-3 z-10">
        <IconButton icon={Maximize2} label="Fit view" shortcut="F" variant="secondary" size="sm" tooltipSide="left" onClick={ui.requestFit} />
      </div>
    </>
  )

  return (
    <div className={cn('flex h-full min-h-0 flex-col', className)}>
      <div className={cn('relative min-h-0 flex-1 overflow-hidden', is3d ? 'bg-map' : 'bg-surface')}>
        {is3d ? (
          <ViewErrorBoundary
            fallback={(err) => (
              <>
                {graph2d}
                <InlineError className="absolute left-3 right-3 top-14 z-10" message={`3D view unavailable (${err?.message || 'unknown error'}); showing 2D.`} />
              </>
            )}
          >
            <Suspense fallback={<Skeleton className="h-full w-full rounded-none" />}>
              <Network3D
                network={ghost3d ? ghost3d.network : network}
                statuses={statuses}
                utilization={utilization}
                disrupted={disrupted}
                highlight={ghost3d ? ghost3d.highlight : highlight}
                hiddenKinds={hidden}
                leading={viewToggle}
                {...view3d}
              />
            </Suspense>
          </ViewErrorBoundary>
        ) : (
          graph2d
        )}
        <div className="absolute bottom-3 left-3 z-10">
          <LegendChip view={is3d ? '3d' : '2d'} hidden={hidden} onToggle={toggle} counts={counts} maxStock={maxStock} />
        </div>
      </div>
      {timeline && store.sim && <Timeline extra={is3d && <ReplayControl />} />}
    </div>
  )
}
