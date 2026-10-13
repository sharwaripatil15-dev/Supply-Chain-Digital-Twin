import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import DeckGL from '@deck.gl/react'
import { AmbientLight, DirectionalLight, FlyToInterpolator, LightingEffect, WebMercatorViewport } from '@deck.gl/core'
import { ArcLayer, ColumnLayer, IconLayer, PathLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers'
import { TripsLayer } from '@deck.gl/geo-layers'
import { Map } from 'react-map-gl/maplibre'
import { setWorkerUrl } from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { Boxes, Crosshair, Route, Sparkles, Tags, Waves, WifiOff } from 'lucide-react'
import { useStore } from '../../store.js'
import { useTheme } from '../../theme.jsx'
import { STATUS, fmtNum, fmtPct } from '../../format.js'
import { MODES, NODE_KINDS, STATUS_COLORS, glyphSvg, isDemand, typeOf } from '../../lib/nodeTypes.js'
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
const MIN_COLUMN_M = 14000
const MAX_COLUMN_M = 150000
const SECONDS_PER_LEAD_DAY = 1.1
const FLOW_LOOP_S = 8
const ICON_PX = 64
const RIPPLE_S = 1.8

const withAlpha = (rgb, a) => [rgb[0], rgb[1], rgb[2], a]
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))
const hexRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
const MODE_RGB = Object.fromEntries(Object.entries(MODES).map(([k, m]) => [k, hexRgb(m.color)]))

const LIGHTING = new LightingEffect({
  ambient: new AmbientLight({ color: [255, 255, 255], intensity: 1.05 }),
  key: new DirectionalLight({ color: [255, 255, 255], intensity: 1.4, direction: [-3, -8, -6] }),
  fill: new DirectionalLight({ color: [210, 220, 255], intensity: 0.45, direction: [4, 6, -2] }),
})
const MATERIAL = { ambient: 0.42, diffuse: 0.62, shininess: 36, specularColor: [70, 74, 82] }

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

/** Every other piece of an arc: a dashed-looking lane (deck.gl arcs cannot be dashed natively). */
function dashedArc(src, dst, height) {
  const pts = arcPath(src, dst, height, 24)
  const out = []
  for (let i = 0; i < pts.length - 1; i += 2) out.push([pts[i], pts[i + 1]])
  return out
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

/** Rasterise the per-type badge glyphs into one PNG atlas (SVG data URIs are not reliable as WebGL textures). */
function useIconAtlas(dark) {
  const [atlas, setAtlas] = useState(null)
  useEffect(() => {
    let cancelled = false
    const canvas = document.createElement('canvas')
    canvas.width = ICON_PX * NODE_KINDS.length
    canvas.height = ICON_PX
    const ctx = canvas.getContext('2d')
    if (!ctx) return undefined
    Promise.all(
      NODE_KINDS.map(
        (kind, i) =>
          new Promise((resolve) => {
            const img = new Image()
            img.onload = () => {
              ctx.drawImage(img, i * ICON_PX, 0, ICON_PX, ICON_PX)
              resolve()
            }
            img.onerror = () => resolve()
            const outline = (dark && typeOf(kind).outlineDark) || '#FFFFFF'
            img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(glyphSvg(kind, { badge: true, size: ICON_PX, outline }))}`
          }),
      ),
    ).then(() => {
      if (cancelled) return
      try {
        setAtlas({
          url: canvas.toDataURL('image/png'),
          mapping: Object.fromEntries(NODE_KINDS.map((k, i) => [k, { x: i * ICON_PX, y: 0, width: ICON_PX, height: ICON_PX, mask: false }])),
        })
      } catch {
        setAtlas(null) // tainted canvas or no 2D context: the columns still render without icons
      }
    })
    return () => {
      cancelled = true
    }
  }, [dark])
  return atlas
}

/**
 * 3D geospatial twin (deck.gl + MapLibre). Node TYPE = column geometry + color + glyph icon; STATUS = ring + pulse.
 *   mode       'live' (default) | 'baseline' (ignore disruption) | 'after' (disruption + recovery lanes)
 *   rerouted   Set of "U->V" lanes on the recovery plan (accent arcs + flows)
 *   focus      node ids to frame with a fly-to (e.g. a selected Chaos Finder pair); focusKey re-triggers it
 *   hiddenKinds  Set of node kinds hidden by the legend filter
 */
export default function Network3D({ network, statuses, utilization, disrupted, highlight, hiddenKinds, mode = 'live', rerouted, focus, focusKey }) {
  const { selectNode, selectedNode } = useStore()
  const { theme, tokens } = useTheme()
  const t = tokens.rgb
  const dark = theme === 'dark'
  const containerRef = useRef(null)
  const reduced = prefersReducedMotion()
  const [viewState, setViewState] = useState(START)
  const [layersOn, setLayersOn] = useState({ nodes: true, labels: true, routes: true, flow: !reduced, risk: true })
  const [tilesFailed, setTilesFailed] = useState(() => typeof navigator !== 'undefined' && navigator.onLine === false)
  const tileErrors = useRef(0)
  const time = useAnimationTime(!reduced)
  const atlas = useIconAtlas(dark)

  const baseline = mode === 'baseline'
  const live = useMemo(
    () => ({
      statuses: baseline ? null : statuses,
      disrupted: baseline ? { nodes: new Set(), edges: new Set() } : disrupted || { nodes: new Set(), edges: new Set() },
      rerouted: baseline ? new Set() : rerouted || new Set(),
    }),
    [baseline, statuses, disrupted, rerouted],
  )

  const flyTo = useCallback((vs, duration = 1600) => {
    setViewState((cur) => ({ ...cur, ...vs, transitionDuration: duration, transitionInterpolator: new FlyToInterpolator({ speed: 1.4 }) }))
  }, [])
  useEffect(() => {
    const id = setTimeout(() => flyTo(INDIA, 1800), 120)
    return () => clearTimeout(id)
  }, [flyTo])

  // ---------------------------------------------------------------- data
  const nodes = useMemo(() => {
    const list = (network?.nodes ?? []).filter((n) => !hiddenKinds?.has(n.kind))
    const maxStock = Math.max(1, ...list.map((n) => n.stock || 0))
    return list.map((n) => {
      const type = typeOf(n.kind)
      const status = live.statuses?.[n.id] ?? (live.disrupted.nodes.has(n.id) ? 'down' : null)
      const share = Math.sqrt(clamp((n.stock || 0) / maxStock, 0, 1))
      const elevation = clamp((MIN_COLUMN_M + share * (MAX_COLUMN_M - MIN_COLUMN_M)) * type.height, MIN_COLUMN_M * 0.8, MAX_COLUMN_M * 1.3)
      const stackH = type.stack ? elevation * 0.32 : 0
      const position = nodePosition(n)
      return { ...n, type, position, status, util: utilization?.[n.id] ?? n.utilization, elevation, stackH, top: elevation + stackH }
    })
  }, [network, hiddenKinds, live, utilization])
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes])

  const arcs = useMemo(() => {
    const maxCap = Math.max(1, ...(network?.edges ?? []).map((e) => e.capacity || 0))
    return (network?.edges ?? [])
      .filter((e) => byId[e.source] && byId[e.target])
      .map((e) => {
        const id = `${e.source}->${e.target}`
        const state = live.disrupted.edges.has(id) ? 'disrupted' : live.rerouted.has(id) ? 'rerouted' : 'normal'
        const share = (e.capacity || 0) / maxCap
        return { ...e, id, state, src: byId[e.source].position, dst: byId[e.target].position, share, height: 0.12 + share * 0.28,
          rgb: byId[e.source].type.rgb, modeKey: MODES[e.mode] ? e.mode : 'road' }
      })
  }, [network, byId, live])

  const dashes = useMemo(
    () => arcs.filter((a) => a.state === 'disrupted').flatMap((a) => dashedArc(a.src, a.dst, a.height).map((path) => ({ path, id: a.id }))),
    [arcs],
  )

  const trips = useMemo(() => {
    const out = []
    for (const a of arcs) {
      if (a.state === 'disrupted') continue // shipments stop on blocked lanes
      const path = arcPath(a.src, a.dst, a.height)
      const travel = Math.max(0.4, a.lead || 1) * SECONDS_PER_LEAD_DAY // speed follows lead time
      const count = a.share > 0.6 ? 3 : 2
      for (let k = 0; k < count; k++) {
        const start = (k / count) * FLOW_LOOP_S + (a.id.length % 5) * 0.3
        for (const shift of [0, FLOW_LOOP_S]) {
          out.push({ path, timestamps: path.map((_, i) => start + shift + (i / (path.length - 1)) * travel), rerouted: a.state === 'rerouted', mode: a.modeKey })
        }
      }
    }
    return out
  }, [arcs])

  // Expanding ripple for nodes that just went down when the day changes.
  const prevStatuses = useRef(live.statuses)
  const [ripples, setRipples] = useState([])
  useEffect(() => {
    const prev = prevStatuses.current
    prevStatuses.current = live.statuses
    if (!prev || !live.statuses) return
    const fresh = Object.entries(live.statuses).filter(([id, s]) => s === 'down' && prev[id] !== 'down').map(([id]) => id)
    if (fresh.length) setRipples((r) => [...r.filter((x) => time - x.start < RIPPLE_S), ...fresh.map((id) => ({ id, start: time }))])
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
  const labelAlpha = Math.round(clamp((viewState.zoom - 4.3) / 1.2, 0, 1) * 255)
  const selected = selectedNode && byId[selectedNode]
  const statusNodes = nodes.filter((n) => n.status)

  const layers = [
    layersOn.risk &&
      new ScatterplotLayer({
        id: 'risk-glow',
        data: nodes.filter((n) => !isDemand(n.kind) && n.risk != null),
        getPosition: (n) => n.position,
        getRadius: (n) => n.type.radius * 1.4 + (n.risk || 0) * 120000,
        getFillColor: (n) => withAlpha(t.accent, 14 + (n.risk || 0) * 70),
        radiusUnits: 'meters',
        updateTriggers: { getFillColor: [t] },
      }),
    new ScatterplotLayer({
      id: 'status-ring',
      data: statusNodes,
      getPosition: (n) => n.position,
      getRadius: (n) => n.type.radius * 1.55 + (n.status === 'down' ? pulse * 14000 : 0),
      getLineColor: (n) => withAlpha(STATUS_COLORS[n.status].rgb, n.status === 'down' ? 150 + pulse * 105 : 230),
      getFillColor: (n) => withAlpha(STATUS_COLORS[n.status].rgb, n.status === 'ok' ? 0 : 38),
      stroked: true,
      filled: true,
      lineWidthUnits: 'pixels',
      getLineWidth: (n) => (n.status === 'ok' ? 2 : 3),
      radiusUnits: 'meters',
      updateTriggers: { getRadius: pulse, getLineColor: pulse },
    }),
    new ScatterplotLayer({
      id: 'ripples',
      data: ripples.filter((r) => time - r.start < RIPPLE_S && byId[r.id]),
      getPosition: (r) => byId[r.id].position,
      getRadius: (r) => 20000 + ((time - r.start) / RIPPLE_S) * 160000,
      getLineColor: (r) => withAlpha(STATUS_COLORS.down.rgb, 200 * (1 - (time - r.start) / RIPPLE_S)),
      stroked: true,
      filled: false,
      lineWidthMinPixels: 2,
      radiusUnits: 'meters',
      updateTriggers: { getRadius: time, getLineColor: time },
    }),
    highlightSet.size > 0 &&
      new ScatterplotLayer({
        id: 'highlight',
        data: nodes.filter((n) => highlightSet.has(n.id)),
        getPosition: (n) => n.position,
        getRadius: (n) => n.type.radius * 2 + pulse * 8000,
        getLineColor: withAlpha(t.accent, 230),
        getFillColor: withAlpha(t.accent, 26),
        stroked: true,
        lineWidthMinPixels: 2,
        radiusUnits: 'meters',
        updateTriggers: { getRadius: pulse, getLineColor: [t], getFillColor: [t] },
      }),
    selected &&
      new ScatterplotLayer({
        id: 'selected',
        data: [selected],
        getPosition: (n) => n.position,
        getRadius: (n) => n.type.radius * 1.9,
        getLineColor: withAlpha(t.accent, 255),
        filled: false,
        stroked: true,
        lineWidthUnits: 'pixels',
        getLineWidth: 3.5,
        radiusUnits: 'meters',
        updateTriggers: { getLineColor: [t] },
      }),
    layersOn.routes &&
      new ArcLayer({
        id: 'routes',
        data: arcs.filter((a) => a.state !== 'disrupted'),
        getSourcePosition: (a) => a.src,
        getTargetPosition: (a) => a.dst,
        getSourceColor: (a) => (a.state === 'rerouted' ? withAlpha(t.accent, 240) : withAlpha(a.rgb, 150)),
        getTargetColor: (a) => (a.state === 'rerouted' ? withAlpha(t.accent, 240) : withAlpha(a.rgb, 60)),
        getWidth: (a) => (a.state === 'rerouted' ? 3 : 1) + a.share * 2.2,
        getHeight: (a) => a.height,
        widthUnits: 'pixels',
        pickable: true,
        updateTriggers: { getSourceColor: [t], getTargetColor: [t] },
      }),
    layersOn.routes &&
      dashes.length > 0 &&
      new PathLayer({
        id: 'routes-disrupted',
        data: dashes,
        getPath: (d) => d.path,
        getColor: withAlpha(STATUS_COLORS.down.rgb, 230),
        getWidth: 2.5,
        widthUnits: 'pixels',
        capRounded: true,
      }),
    layersOn.flow &&
      !reduced &&
      new TripsLayer({
        id: 'flow',
        data: trips,
        getPath: (d) => d.path,
        getTimestamps: (d) => d.timestamps,
        getColor: (d) => (d.rerouted ? t.accent : MODE_RGB[d.mode]),
        opacity: 0.9,
        widthMinPixels: 2.5,
        capRounded: true,
        jointRounded: true,
        fadeTrail: true,
        trailLength: 0.9,
        currentTime: flowTime,
        updateTriggers: { getColor: [t] },
      }),
    ...(layersOn.nodes
      ? NODE_KINDS.map((kind) => {
          const type = typeOf(kind)
          return new ColumnLayer({
            id: `nodes-${kind}`,
            data: nodes.filter((n) => n.kind === kind),
            diskResolution: type.disk,
            angle: type.angle,
            radius: type.radius,
            extruded: true,
            elevationScale: 1,
            material: MATERIAL,
            getPosition: (n) => n.position,
            getElevation: (n) => n.elevation,
            getFillColor: withAlpha(type.rgb, 245),
            pickable: true,
            autoHighlight: true,
            highlightColor: withAlpha(t.accent, 160),
            transitions: { getElevation: 300 },
            updateTriggers: { highlightColor: [t] },
          })
        })
      : []),
    layersOn.nodes &&
      new ColumnLayer({
        id: 'nodes-factory-stack',
        data: nodes.filter((n) => n.type.stack),
        diskResolution: 4,
        angle: 45,
        radius: typeOf('factory').radius * 0.42,
        extruded: true,
        material: MATERIAL,
        getPosition: (n) => [n.position[0] + 0.05, n.position[1] + 0.05, n.elevation],
        getElevation: (n) => n.stackH,
        getFillColor: withAlpha(typeOf('factory').rgb.map((c) => Math.min(255, c + 40)), 250),
        pickable: true,
      }),
    layersOn.nodes &&
      atlas &&
      new IconLayer({
        id: 'node-icons',
        data: nodes,
        iconAtlas: atlas.url,
        iconMapping: atlas.mapping,
        getIcon: (n) => (atlas.mapping[n.kind] ? n.kind : 'customer'),
        getPosition: (n) => [n.position[0], n.position[1], n.top + 4000],
        getSize: 22,
        sizeUnits: 'pixels',
        billboard: true,
        pickable: true,
        alphaCutoff: 0.05,
      }),
    layersOn.nodes &&
      layersOn.labels &&
      labelAlpha > 0 &&
      new TextLayer({
        id: 'node-labels',
        data: nodes,
        getText: (n) => (n.name && n.name.length > 22 ? `${n.name.slice(0, 21)}…` : n.name || n.id),
        getPosition: (n) => [n.position[0], n.position[1], n.top + 4000],
        getPixelOffset: [0, -22],
        getSize: 12,
        getColor: withAlpha(t.fg, labelAlpha),
        fontFamily: 'Inter Variable, system-ui, sans-serif',
        fontWeight: 600,
        characterSet: 'auto',
        fontSettings: { sdf: true },
        outlineWidth: 3,
        outlineColor: withAlpha(t.surface, labelAlpha),
        getTextAnchor: 'middle',
        getAlignmentBaseline: 'bottom',
        billboard: true,
        updateTriggers: { getColor: [labelAlpha, t] },
      }),
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
  const nodeOf = (layer, object) => (layer.id.startsWith('nodes-') || layer.id === 'node-icons' ? object : null)
  const getTooltip = ({ object, layer }) => {
    if (!object || !layer) return null
    const n = nodeOf(layer, object)
    if (n) {
      const icon = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(glyphSvg(n.kind, { badge: true, size: 16 }))}`
      const status = n.status ? ` · <b style="color:${STATUS_COLORS[n.status].color}">${STATUS[n.status].label}</b>` : ''
      const util = isDemand(n.kind) && !n.capacity ? '-' : fmtPct(n.util)
      return {
        html: `<div style="display:flex;align-items:center;gap:6px"><img src="${icon}" width="16" height="16" alt=""/><b>${n.id} · ${n.name || n.city || ''}</b></div><span style="color:${tokens.color.fgMuted}">${n.type.label}${n.city ? ` · ${n.city}` : ''}${status}</span><br/>Stock ${fmtNum(n.stock)} · Util ${util} · Criticality ${n.risk == null ? 'n/a' : fmtPct(n.risk)}`,
        style: tooltipStyle,
      }
    }
    if (layer.id === 'routes') {
      const label = { normal: 'Normal', disrupted: 'Disrupted', rerouted: 'Recovery route' }[object.state]
      const modeLabel = MODES[object.modeKey]?.label || 'Road'
      return {
        html: `<b>${object.source} → ${object.target}</b><br/><span style="color:${tokens.color.fgMuted}">${label} · ${modeLabel}</span><br/>Capacity ${fmtNum(object.capacity)}/day · ${object.lead} d lead`,
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
        effects={[LIGHTING]}
        getTooltip={getTooltip}
        onClick={(info) => {
          const n = info.object && info.layer && nodeOf(info.layer, info.object)
          if (n) selectNode(n.id)
        }}
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
        <Toggle pressed={layersOn.labels} onChange={(v) => setLayersOn((s) => ({ ...s, labels: v }))} icon={Tags}>
          Labels
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

      {/* Compact lane/flow key (node types and status rings are in the card legend below) */}
      <ul className="absolute bottom-3 left-3 flex max-w-[calc(100%-1.5rem)] flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-border bg-surface/90 px-2.5 py-1.5 text-xs text-fg-muted backdrop-blur">
        <li className="flex items-center gap-1.5">
          <span className="w-3 border-t-2 border-fg-muted/60" aria-hidden />
          lane (source color)
        </li>
        <li className="flex items-center gap-1.5">
          <span className="w-3 border-t-2 border-dashed border-bad" aria-hidden />
          disrupted
        </li>
        <li className="flex items-center gap-1.5">
          <span className="w-3 border-t-2 border-accent" aria-hidden />
          recovery
        </li>
        {Object.entries(MODES).map(([k, m]) => (
          <li key={k} className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full ring-1 ring-fg-muted/40" style={{ backgroundColor: m.color }} aria-hidden />
            {m.label}
          </li>
        ))}
        <li>height = stock · glow = criticality</li>
      </ul>
    </div>
  )
}
