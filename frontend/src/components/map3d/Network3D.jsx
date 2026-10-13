import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import DeckGL from '@deck.gl/react'
import { FlyToInterpolator, WebMercatorViewport } from '@deck.gl/core'
import { ArcLayer, ColumnLayer, ScatterplotLayer } from '@deck.gl/layers'
import { TripsLayer } from '@deck.gl/geo-layers'
import { Map } from 'react-map-gl/maplibre'
import { setWorkerUrl } from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { Boxes, Crosshair, Route, Sparkles, Waves, WifiOff } from 'lucide-react'
import { useStore } from '../../store.js'
import { useTheme } from '../../theme.jsx'
import { KIND, STATUS, fmtNum, fmtPct } from '../../format.js'
import { nodePosition, prefersReducedMotion } from '../../lib/disruption.js'
import { Badge, Button, Toggle, cn } from '../ui/index.js'

// Bundling breaks MapLibre's own worker lookup; ship the (self-contained) worker as an asset instead.
setWorkerUrl(maplibreWorkerUrl)

const BASEMAP = {
  light: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
  dark: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
}
const INDIA = { longitude: 79.4, latitude: 21.2, zoom: 4.1, pitch: 50, bearing: -12 }
const START = { longitude: 79.4, latitude: 18, zoom: 2.6, pitch: 0, bearing: 0 }
const TIER_COLUMN = {
  supplier: { radius: 26000, disk: 4, angle: 45 },
  factory: { radius: 24000, disk: 6, angle: 0 },
  warehouse: { radius: 22000, disk: 8, angle: 22.5 },
  customer: { radius: 17000, disk: 24, angle: 0 },
}
const MAX_COLUMN_M = 170000
const SECONDS_PER_LEAD_DAY = 1.1
const FLOW_LOOP_S = 8

const withAlpha = (rgb, a) => [rgb[0], rgb[1], rgb[2], a]

function distanceMeters([lon1, lat1], [lon2, lat2]) {
  const r = Math.PI / 180
  const x = (lon2 - lon1) * r * Math.cos(((lat1 + lat2) / 2) * r)
  const y = (lat2 - lat1) * r
  return Math.sqrt(x * x + y * y) * 6371000
}

/** Points along deck.gl's ArcLayer curve (z = sqrt(r(1-r)) * distance * height) so shipments ride the arcs. */
function arcPath(src, dst, height, steps = 16) {
  const dist = distanceMeters(src, dst)
  return Array.from({ length: steps + 1 }, (_, i) => {
    const r = i / steps
    return [src[0] + (dst[0] - src[0]) * r, src[1] + (dst[1] - src[1]) * r, Math.sqrt(r * (1 - r)) * dist * height]
  })
}

function useAnimationTime(enabled) {
  const [time, setTime] = useState(0)
  useEffect(() => {
    if (!enabled) return
    let raf
    const t0 = performance.now()
    const tick = (now) => {
      setTime((now - t0) / 1000)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [enabled])
  return time
}

/**
 * 3D geospatial twin (deck.gl + MapLibre). Same inputs as the 2D view, plus:
 *   mode       'live' (default) | 'baseline' (ignore disruption) | 'after' (disruption + recovery lanes)
 *   rerouted   Set of "U->V" lanes on the recovery plan (accent arcs + flows)
 *   focus      node ids to frame with a fly-to (e.g. a selected Chaos Finder pair); focusKey re-triggers it
 */
export default function Network3D({ network, statuses, utilization, disrupted, highlight, mode = 'live', rerouted, focus, focusKey }) {
  const { selectNode } = useStore()
  const { theme, tokens } = useTheme()
  const t = tokens.rgb
  const containerRef = useRef(null)
  const reduced = prefersReducedMotion()
  const [viewState, setViewState] = useState(START)
  const [layersOn, setLayersOn] = useState({ nodes: true, routes: true, flow: !reduced, risk: true })
  const [tilesFailed, setTilesFailed] = useState(() => typeof navigator !== 'undefined' && navigator.onLine === false)
  const tileErrors = useRef(0)
  const time = useAnimationTime(!reduced)

  const baseline = mode === 'baseline'
  const live = {
    statuses: baseline ? null : statuses,
    disrupted: baseline ? { nodes: new Set(), edges: new Set() } : disrupted || { nodes: new Set(), edges: new Set() },
    rerouted: baseline ? new Set() : rerouted || new Set(),
  }

  const flyTo = useCallback((vs, duration = 1600) => {
    setViewState((cur) => ({ ...cur, ...vs, transitionDuration: duration, transitionInterpolator: new FlyToInterpolator({ speed: 1.4 }) }))
  }, [])
  useEffect(() => {
    const id = setTimeout(() => flyTo(INDIA, 1800), 120)
    return () => clearTimeout(id)
  }, [flyTo])

  // ---------------------------------------------------------------- data
  const nodes = useMemo(() => {
    const maxStock = Math.max(...network.nodes.map((n) => n.stock || 0), 1)
    return network.nodes.map((n) => {
      const status = live.statuses?.[n.id] ?? (live.disrupted.nodes.has(n.id) ? 'down' : null)
      return {
        ...n,
        position: nodePosition(n),
        status,
        util: utilization?.[n.id] ?? n.utilization,
        elevation: ((n.stock || 0) / maxStock) * MAX_COLUMN_M,
        color: t[status ? STATUS[status].token : KIND[n.kind].token],
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [network, live.statuses, live.disrupted, utilization, t])
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes])

  const arcs = useMemo(() => {
    const maxCap = Math.max(...network.edges.map((e) => e.capacity), 1)
    return network.edges
      .filter((e) => byId[e.source] && byId[e.target])
      .map((e) => {
        const id = `${e.source}->${e.target}`
        const state = live.disrupted.edges.has(id) ? 'disrupted' : live.rerouted.has(id) ? 'rerouted' : 'normal'
        return { ...e, id, state, src: byId[e.source].position, dst: byId[e.target].position, share: e.capacity / maxCap }
      })
  }, [network, byId, live.disrupted, live.rerouted])

  const trips = useMemo(() => {
    const out = []
    for (const a of arcs) {
      if (a.state === 'disrupted') continue // shipments stop on blocked lanes
      const path = arcPath(a.src, a.dst, 0.12 + a.share * 0.28)
      const travel = Math.max(1, a.lead) * SECONDS_PER_LEAD_DAY
      const count = a.share > 0.6 ? 3 : 2
      for (let k = 0; k < count; k++) {
        const start = (k / count) * FLOW_LOOP_S + (a.id.length % 5) * 0.3
        for (const shift of [0, FLOW_LOOP_S]) {
          out.push({ path, timestamps: path.map((_, i) => start + shift + (i / (path.length - 1)) * travel), rerouted: a.state === 'rerouted' })
        }
      }
    }
    return out
  }, [arcs])

  // Ripples for nodes that just went down when the day changes.
  const prevStatuses = useRef(live.statuses)
  const [ripples, setRipples] = useState([])
  useEffect(() => {
    const prev = prevStatuses.current
    prevStatuses.current = live.statuses
    if (!prev || !live.statuses) return
    const fresh = Object.entries(live.statuses).filter(([id, s]) => s === 'down' && prev[id] !== 'down').map(([id]) => id)
    if (fresh.length) setRipples((r) => [...r.filter((x) => time - x.start < 2), ...fresh.map((id) => ({ id, start: time }))])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live.statuses])

  // Frame Chaos Finder targets.
  useEffect(() => {
    if (!focus?.length) return
    const pts = focus.map((id) => byId[id]?.position).filter(Boolean)
    if (!pts.length) return
    const el = containerRef.current
    const lons = pts.map((p) => p[0])
    const lats = pts.map((p) => p[1])
    const pad = 1.2
    const vp = new WebMercatorViewport({ width: el?.clientWidth || 800, height: el?.clientHeight || 560 })
    const { longitude, latitude, zoom } = vp.fitBounds(
      [[Math.min(...lons) - pad, Math.min(...lats) - pad], [Math.max(...lons) + pad, Math.max(...lats) + pad]],
      { padding: 60 },
    )
    flyTo({ longitude, latitude, zoom: Math.min(zoom, 6.2), pitch: 52, bearing: -18 }, 1500)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusKey])

  // ---------------------------------------------------------------- layers
  const pulse = 0.5 + 0.5 * Math.sin(time * 3)
  const highlightSet = new Set(highlight || [])
  const flowTime = (time % FLOW_LOOP_S) + FLOW_LOOP_S

  const layers = [
    layersOn.risk &&
      new ScatterplotLayer({
        id: 'risk-glow',
        data: nodes.filter((n) => n.kind !== 'customer'),
        getPosition: (n) => n.position,
        getRadius: (n) => 22000 + (n.risk || 0) * 160000,
        getFillColor: (n) => withAlpha(t.accent, 18 + (n.risk || 0) * 90),
        radiusUnits: 'meters',
        updateTriggers: { getFillColor: [t] },
      }),
    new ScatterplotLayer({
      id: 'down-pulse',
      data: nodes.filter((n) => n.status === 'down'),
      getPosition: (n) => n.position,
      getRadius: 38000 + pulse * 22000,
      getFillColor: withAlpha(t.bad, 40 + pulse * 40),
      radiusUnits: 'meters',
      updateTriggers: { getRadius: pulse, getFillColor: [pulse, t] },
    }),
    new ScatterplotLayer({
      id: 'ripples',
      data: ripples.filter((r) => time - r.start < 1.8 && byId[r.id]),
      getPosition: (r) => byId[r.id].position,
      getRadius: (r) => 20000 + ((time - r.start) / 1.8) * 160000,
      getLineColor: (r) => withAlpha(t.bad, 200 * (1 - (time - r.start) / 1.8)),
      stroked: true,
      filled: false,
      lineWidthMinPixels: 2,
      radiusUnits: 'meters',
      updateTriggers: { getRadius: time, getLineColor: [time, t] },
    }),
    highlightSet.size > 0 &&
      new ScatterplotLayer({
        id: 'highlight',
        data: nodes.filter((n) => highlightSet.has(n.id)),
        getPosition: (n) => n.position,
        getRadius: 52000 + pulse * 8000,
        getLineColor: withAlpha(t.accent, 230),
        getFillColor: withAlpha(t.accent, 30),
        stroked: true,
        lineWidthMinPixels: 2,
        radiusUnits: 'meters',
        updateTriggers: { getRadius: pulse, getLineColor: [t], getFillColor: [t] },
      }),
    layersOn.routes &&
      new ArcLayer({
        id: 'routes',
        data: arcs,
        getSourcePosition: (a) => a.src,
        getTargetPosition: (a) => a.dst,
        getSourceColor: (a) =>
          a.state === 'disrupted' ? withAlpha(t.bad, 90) : a.state === 'rerouted' ? withAlpha(t.accent, 235) : withAlpha(t.fgMuted, 120),
        getTargetColor: (a) =>
          a.state === 'disrupted' ? withAlpha(t.bad, 40) : a.state === 'rerouted' ? withAlpha(t.accent, 235) : withAlpha(t.fgMuted, 70),
        getWidth: (a) => (a.state === 'rerouted' ? 3 : 1) + a.share * 2.5,
        getHeight: (a) => 0.12 + a.share * 0.28,
        widthUnits: 'pixels',
        pickable: true,
        updateTriggers: { getSourceColor: [t], getTargetColor: [t], getWidth: [arcs] },
      }),
    layersOn.flow &&
      !reduced &&
      new TripsLayer({
        id: 'flow',
        data: trips,
        getPath: (d) => d.path,
        getTimestamps: (d) => d.timestamps,
        getColor: (d) => (d.rerouted ? t.accent : t.fg2),
        opacity: 0.85,
        widthMinPixels: 2.5,
        capRounded: true,
        jointRounded: true,
        fadeTrail: true,
        trailLength: 0.9,
        currentTime: flowTime,
        updateTriggers: { getColor: [t] },
      }),
    ...(layersOn.nodes
      ? Object.entries(TIER_COLUMN).map(
          ([kind, cfg]) =>
            new ColumnLayer({
              id: `nodes-${kind}`,
              data: nodes.filter((n) => n.kind === kind),
              diskResolution: cfg.disk,
              angle: cfg.angle,
              radius: cfg.radius,
              extruded: true,
              elevationScale: 1,
              getPosition: (n) => n.position,
              getElevation: (n) => Math.max(8000, n.elevation),
              getFillColor: (n) => withAlpha(n.color, 235),
              getLineColor: withAlpha(t.fg, 60),
              pickable: true,
              autoHighlight: true,
              highlightColor: withAlpha(t.accent, 200),
              transitions: { getFillColor: 200, getElevation: 300 },
              updateTriggers: { getFillColor: [nodes], getElevation: [nodes], highlightColor: [t] },
            }),
        )
      : []),
  ].filter(Boolean)

  const tooltipStyle = {
    backgroundColor: tokens.color.surface,
    color: tokens.color.fg,
    border: `1px solid ${tokens.color.border}`,
    borderRadius: '8px',
    padding: '8px 10px',
    fontSize: '12px',
    fontFamily: 'Inter Variable, system-ui, sans-serif',
    lineHeight: '16px',
  }
  const getTooltip = ({ object, layer }) => {
    if (!object || !layer) return null
    if (layer.id.startsWith('nodes-')) {
      const n = object
      const status = n.status ? ` · ${STATUS[n.status].label}` : ''
      return {
        html: `<b>${n.id} · ${n.name || n.city}</b><br/><span style="color:${tokens.color.fgMuted}">${KIND[n.kind].label} · ${n.city}${status}</span><br/>Stock ${fmtNum(n.stock)} · Util ${n.kind === 'customer' ? '-' : fmtPct(n.util)} · Criticality ${fmtPct(n.risk)}`,
        style: tooltipStyle,
      }
    }
    if (layer.id === 'routes') {
      const label = { normal: 'Normal', disrupted: 'Disrupted', rerouted: 'Recovery route' }[object.state]
      return {
        html: `<b>${object.source} → ${object.target}</b><br/><span style="color:${tokens.color.fgMuted}">${label}</span><br/>Capacity ${fmtNum(object.capacity)}/day · ${object.lead} d lead`,
        style: tooltipStyle,
      }
    }
    return null
  }

  return (
    <div ref={containerRef} className={cn('relative h-full w-full', tilesFailed && 'bg-map')}>
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState: vs }) => setViewState(vs)}
        controller={{ dragRotate: true, touchRotate: true, keyboard: true }}
        layers={layers}
        getTooltip={getTooltip}
        onClick={(info) => info.object && info.layer?.id.startsWith('nodes-') && selectNode(info.object.id)}
        getCursor={({ isHovering, isDragging }) => (isDragging ? 'grabbing' : isHovering ? 'pointer' : 'grab')}
      >
        {!tilesFailed && (
          <Map
            reuseMaps
            mapStyle={BASEMAP[theme]}
            attributionControl={{ compact: true }}
            onError={() => {
              tileErrors.current += 1
              if (tileErrors.current >= 2) setTilesFailed(true)
            }}
          />
        )}
      </DeckGL>

      {/* Layer toggles */}
      <div className="absolute left-3 top-3 flex flex-wrap gap-1.5 rounded-lg border border-border bg-surface/90 p-1.5 backdrop-blur">
        <Toggle pressed={layersOn.nodes} onChange={(v) => setLayersOn((s) => ({ ...s, nodes: v }))} icon={Boxes}>
          Nodes
        </Toggle>
        <Toggle pressed={layersOn.routes} onChange={(v) => setLayersOn((s) => ({ ...s, routes: v }))} icon={Route}>
          Routes
        </Toggle>
        <Toggle pressed={layersOn.flow && !reduced} onChange={(v) => setLayersOn((s) => ({ ...s, flow: v }))} icon={Waves}>
          Flow
        </Toggle>
        <Toggle pressed={layersOn.risk} onChange={(v) => setLayersOn((s) => ({ ...s, risk: v }))} icon={Sparkles}>
          Risk
        </Toggle>
      </div>

      <div className="absolute right-3 top-3 flex items-center gap-1.5">
        {mode !== 'live' && <Badge tone="accent">{mode === 'baseline' ? 'Before: normal operations' : 'After: recovery plan'}</Badge>}
        {tilesFailed && (
          <Badge icon={WifiOff} title="Basemap tiles could not load; layers still render">
            Basemap offline
          </Badge>
        )}
        <Button size="sm" icon={Crosshair} onClick={() => flyTo(INDIA, 1200)} className="bg-surface/90 backdrop-blur">
          Reset view
        </Button>
      </div>

      {/* Compact legend */}
      <ul className="absolute bottom-3 left-3 flex max-w-[calc(100%-1.5rem)] flex-wrap gap-x-3 gap-y-1 rounded-lg border border-border bg-surface/90 px-2.5 py-1.5 text-xs text-fg-muted backdrop-blur">
        {live.statuses || mode === 'after'
          ? Object.values(STATUS).map((s) => (
              <li key={s.label} className="flex items-center gap-1.5">
                <span className={cn('h-2 w-2 rounded-full', `bg-${s.token}`)} aria-hidden />
                {s.label}
              </li>
            ))
          : Object.values(KIND).map((k) => (
              <li key={k.label} className="flex items-center gap-1.5">
                <span className={cn('h-2 w-2 rounded-sm', k.swatch)} aria-hidden />
                {k.label}
              </li>
            ))}
        <li className="flex items-center gap-1.5">
          <span className="w-3 border-t-2 border-fg-muted/60" aria-hidden />
          route
        </li>
        <li className="flex items-center gap-1.5">
          <span className="w-3 border-t-2 border-bad/50" aria-hidden />
          disrupted
        </li>
        <li className="flex items-center gap-1.5">
          <span className="w-3 border-t-2 border-accent" aria-hidden />
          recovery
        </li>
        <li>height = stock · glow = criticality</li>
      </ul>
    </div>
  )
}
