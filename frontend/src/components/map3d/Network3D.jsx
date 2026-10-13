import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import DeckGL from '@deck.gl/react'
import { AmbientLight, DirectionalLight, FlyToInterpolator, LightingEffect, LinearInterpolator, WebMercatorViewport } from '@deck.gl/core'
import { ArcLayer, ColumnLayer, IconLayer, PathLayer, ScatterplotLayer, SolidPolygonLayer, TextLayer } from '@deck.gl/layers'
import { TripsLayer } from '@deck.gl/geo-layers'
import { Map as BaseMap } from 'react-map-gl/maplibre'
import { setWorkerUrl } from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { Boxes, Crosshair, Navigation2, Pause, Play, Route, Sparkles, Square, Tags, Waves, WifiOff, SlidersHorizontal, Video } from 'lucide-react'
import { useStore } from '../../store.js'
import { useTheme } from '../../theme.jsx'
import { useUi } from '../../ui.jsx'
import { STATUS, fmtNum, fmtPct } from '../../format.js'
import { MODES, NODE_KINDS, STATUS_COLORS, glyphSvg, isDemand, typeOf } from '../../lib/nodeTypes.js'
import { INDIA_OUTLINE } from '../../lib/indianCities.js'
import { nodePosition, prefersReducedMotion } from '../../lib/disruption.js'
import { IconButton, Menu, SegmentedControl, Toggle, Tooltip, cn } from '../ui/index.js'
import { TypeIcon } from '../NodeTypeIcon.jsx'

// Bundling breaks MapLibre's own worker lookup; ship the (self-contained) worker as an asset instead.
setWorkerUrl(maplibreWorkerUrl)

const BASEMAP = {
  light: 'https://basemaps.cartocdn.com/gl/positron-nolabels-gl-style/style.json',
  dark: 'https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json',
}
const PITCH = 55
const BEARING = -12
const START = { longitude: 79.4, latitude: 19.5, zoom: 3.3, pitch: 0, bearing: 0 }
const MIN_COLUMN_M = 9000 // clamped so nothing is invisible...
const MAX_COLUMN_M = 140000 // ...or giant
const ICON_PX = 64
const RIPPLE_S = 1.6
const FLOW_LOOP_S = 10
const SECONDS_PER_LEAD_DAY = 1.8 // slow, sparse particles; speed follows lead time
const STORY_BEARING_STEP = 3
const EMPTY_SET = new Set()
const EMPTY_DIS = { nodes: EMPTY_SET, edges: EMPTY_SET }

const LIGHTING = new LightingEffect({
  ambient: new AmbientLight({ color: [255, 255, 255], intensity: 1.1 }),
  sun: new DirectionalLight({ color: [255, 255, 255], intensity: 1.55, direction: [-2, -6, -7] }),
})
const EFFECTS = [LIGHTING]
const MATERIAL = { ambient: 0.45, diffuse: 0.6, shininess: 24, specularColor: [56, 60, 68] }

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))
const withAlpha = (rgb, a) => [rgb[0], rgb[1], rgb[2], Math.round(clamp(a, 0, 255))]
const lerp = (a, b, k) => a + (b - a) * k
const lerpRgb = (a, b, k) => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)]
const hexRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
const MODE_RGB = Object.fromEntries(Object.entries(MODES).map(([k, m]) => [k, hexRgb(m.color)]))

/** Pixel distance from (px, py) to the segment a-b (hit-testing a column from its base to its top). */
function distToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax
  const dy = by - ay
  const len2 = dx * dx + dy * dy
  const k = len2 ? clamp(((px - ax) * dx + (py - ay) * dy) / len2, 0, 1) : 0
  return Math.hypot(px - (ax + k * dx), py - (ay + k * dy))
}

function distanceMeters([lon1, lat1], [lon2, lat2]) {
  const r = Math.PI / 180
  const x = (lon2 - lon1) * r * Math.cos(((lat1 + lat2) / 2) * r)
  const y = (lat2 - lat1) * r
  return Math.sqrt(x * x + y * y) * 6371000
}

/** Points along deck.gl's ArcLayer curve (z = sqrt(r(1-r)) * distance * height) so particles ride the arcs. */
function arcPath(src, dst, height, steps = 16) {
  const dist = distanceMeters(src, dst)
  return Array.from({ length: steps + 1 }, (_, i) => {
    const r = i / steps
    return [src[0] + (dst[0] - src[0]) * r, src[1] + (dst[1] - src[1]) * r, Math.sqrt(r * (1 - r)) * dist * height]
  })
}

/** Every other piece of an arc: a broken red lane (deck.gl arcs cannot be dashed natively). */
function dashedArc(src, dst, height) {
  const pts = arcPath(src, dst, height, 24)
  const out = []
  for (let i = 0; i < pts.length - 1; i += 2) out.push([pts[i], pts[i + 1]])
  return out
}

/** Wall-clock seconds, ticking every frame only while `enabled` (no loop when nothing animates). */
function useClock(enabled) {
  const [now, setNow] = useState(() => performance.now() / 1000)
  useEffect(() => {
    if (!enabled) return undefined
    let raf
    const tick = (t) => {
      setNow(t / 1000)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [enabled])
  return now
}

/** Eased 0..1 value that follows `target` (used to crossfade Before/After). */
function useTween(target, ms = 320) {
  const [v, setV] = useState(target)
  const cur = useRef(target)
  useEffect(() => {
    if (prefersReducedMotion()) {
      cur.current = target
      setV(target)
      return undefined
    }
    const from = cur.current
    const t0 = performance.now()
    let raf
    const step = (t) => {
      const k = Math.min(1, (t - t0) / ms)
      const val = from + (target - from) * (1 - (1 - k) ** 3)
      cur.current = val
      setV(val)
      if (k < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return v
}

function useSize(ref) {
  const [size, setSize] = useState({ w: 0, h: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const ro = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return size
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
        setAtlas(null) // tainted canvas: columns still render without icons
      }
    })
    return () => {
      cancelled = true
    }
  }, [dark])
  return atlas
}

/** Quiet the basemap: our background color, no roads or buildings, faint boundaries. Cosmetic only. */
function quietBasemap(map, mapBg) {
  try {
    for (const layer of map.getStyle()?.layers ?? []) {
      const { id, type } = layer
      if (type === 'background') map.setPaintProperty(id, 'background-color', mapBg)
      else if (/road|highway|street|bridge|tunnel|rail|aeroway|transportation|building/i.test(id)) map.setLayoutProperty(id, 'visibility', 'none')
      else if (/boundary|admin/i.test(id) && type === 'line') map.setPaintProperty(id, 'line-opacity', 0.5)
      else if (/landcover|landuse|park|wood|grass/i.test(id) && type === 'fill') map.setPaintProperty(id, 'fill-opacity', 0.3)
    }
  } catch {
    /* style tweaks are cosmetic */
  }
}

const GRATICULE = [
  ...Array.from({ length: 9 }, (_, i) => ({ path: [[60 + i * 5, 0], [60 + i * 5, 40]] })),
  ...Array.from({ length: 9 }, (_, i) => ({ path: [[60, i * 5], [100, i * 5]] })),
]
const INDIA_RING = [...INDIA_OUTLINE, INDIA_OUTLINE[0]]

/** BFS both ways from `id`: the nodes and lanes on any upstream or downstream path through it. */
function pathThrough(id, arcs) {
  const out = {}
  const inn = {}
  for (const a of arcs) {
    ;(out[a.source] ||= []).push(a.target)
    ;(inn[a.target] ||= []).push(a.source)
  }
  const reach = (adj) => {
    const seen = new Set([id])
    const queue = [id]
    while (queue.length) {
      const n = queue.shift()
      for (const m of adj[n] || []) {
        if (!seen.has(m)) {
          seen.add(m)
          queue.push(m)
        }
      }
    }
    return seen
  }
  const up = reach(inn)
  const down = reach(out)
  const nodes = new Set([...up, ...down])
  const edges = new Set(arcs.filter((a) => up.has(a.target) || down.has(a.source)).map((a) => a.id))
  return { nodes, edges }
}

const nameOf = (n) => (n ? `${n.name || n.id} (${n.id})` : '')
function listNames(ids, byId) {
  const named = ids.map((id) => nameOf(byId[id])).filter(Boolean)
  return named.length > 2 ? `${named.slice(0, 2).join(', ')} +${named.length - 2} more` : named.join(' and ')
}
function countByType(ids, byId) {
  const c = {}
  for (const id of ids) {
    const k = byId[id]?.kind
    if (k) c[k] = (c[k] || 0) + 1
  }
  return Object.entries(c)
    .map(([k, n]) => `${n} ${n === 1 ? typeOf(k).label.toLowerCase() : typeOf(k).plural.toLowerCase()}`)
    .join(', ')
}

/** One caption line per day for the replay ("Day 3: Chennai Electronics (S2) stops, 2 warehouses lose supply"). */
function captionFor(sim, day, byId) {
  const row = sim?.timeline?.[day]
  if (!row) return ''
  const prev = day > 0 ? sim.timeline[day - 1]?.node_status : null
  const was = (id) => prev?.[id] ?? 'ok'
  const entries = Object.entries(row.node_status || {})
  const down = entries.filter(([id, s]) => s === 'down' && was(id) !== 'down').map(([id]) => id)
  const stops = down.filter((id) => !isDemand(byId[id]?.kind))
  const stockouts = down.filter((id) => isDemand(byId[id]?.kind))
  const stressed = entries.filter(([id, s]) => s === 'stressed' && was(id) === 'ok').map(([id]) => id)
  const recovered = entries.filter(([id, s]) => s === 'ok' && was(id) !== 'ok').map(([id]) => id)
  const parts = []
  if (stops.length) parts.push(`${listNames(stops, byId)} ${stops.length === 1 ? 'stops' : 'stop'}`)
  if (stockouts.length) parts.push(`${listNames(stockouts, byId)} ${stockouts.length === 1 ? 'runs' : 'run'} out of stock`)
  if (stressed.length) parts.push(`${countByType(stressed, byId)} ${stressed.length === 1 ? 'loses' : 'lose'} supply`)
  if (recovered.length) parts.push(`${recovered.length} recovered`)
  if (!parts.length) parts.push(row.unmet > 0 ? `${fmtNum(row.unmet)} units short` : 'no new failures')
  return `Day ${day}: ${parts.join(', ')}`
}

/**
 * 3D geospatial twin (deck.gl + MapLibre). Node TYPE = column geometry + color + glyph icon; STATUS = ring.
 *   mode         'live' (default) | 'baseline' (Before) | 'after' (After): Before/After crossfade
 *   disruptedAll disruption to show in 'after' (kept while fading out); defaults to `disrupted`
 *   rerouted     Set of "U->V" recovery lanes (accent arcs)
 *   focus        node ids to frame (e.g. a Chaos Finder pair); focusKey re-triggers it
 *   leading      element rendered first in the top-left toolbar (the 2D/3D switch)
 */
export default function Network3D({
  network, statuses, utilization, disrupted, disruptedAll, highlight, hiddenKinds, mode = 'live', rerouted, focus, focusKey, leading,
}) {
  const { selectNode, selectedNode, sim, day } = useStore()
  const { theme, tokens } = useTheme()
  const ui = useUi()
  const t = tokens.rgb
  const dark = theme === 'dark'
  const containerRef = useRef(null)
  const size = useSize(containerRef)
  const reduced = prefersReducedMotion()
  const [viewState, setViewState] = useState(START)
  const [preset, setPreset] = useState('overview')
  const [layersOn, setLayersOn] = useState({ nodes: true, labels: true, routes: true, risk: true })
  const flowsOn = ui.animateFlows && !reduced
  const [hoverId, setHoverId] = useState(null)
  const [tilesFailed, setTilesFailed] = useState(() => typeof navigator !== 'undefined' && navigator.onLine === false)
  const tileErrors = useRef(0)
  const mapLoaded = useRef(false)
  const atlas = useIconAtlas(dark)
  // No basemap within a few seconds (offline, blocked, slow): switch to the designed fallback ground.
  useEffect(() => {
    mapLoaded.current = false
    if (tilesFailed) return undefined
    const id = setTimeout(() => !mapLoaded.current && setTilesFailed(true), 6000)
    return () => clearTimeout(id)
  }, [tilesFailed, theme])
  const flyEnd = useRef(0)

  // Before/After crossfade.
  const mix = useTween(mode === 'baseline' ? 0 : 1)
  const dis = disruptedAll || disrupted || EMPTY_DIS
  const rer = rerouted || EMPTY_SET
  const liveStatuses = mode === 'baseline' ? null : statuses

  // ------------------------------------------------------------------ data
  const nodes = useMemo(() => {
    const list = (network?.nodes ?? []).filter((n) => !hiddenKinds?.has(n.kind))
    const maxStock = Math.max(1, ...list.map((n) => n.stock || 0))
    return list.map((n) => {
      const type = typeOf(n.kind)
      const share = clamp((n.stock || 0) / maxStock, 0, 1)
      const elevation = MIN_COLUMN_M + share * (MAX_COLUMN_M - MIN_COLUMN_M) // height = stock, linear and clamped
      const stackH = type.stack ? elevation * 0.3 : 0
      const status = liveStatuses?.[n.id] ?? (dis.nodes.has(n.id) ? 'down' : null)
      return {
        ...n,
        type,
        position: nodePosition(n),
        status,
        eventOnly: !liveStatuses?.[n.id] && dis.nodes.has(n.id), // shown via the crossfade, not a timeline
        util: utilization?.[n.id] ?? n.utilization,
        elevation,
        stackH,
        top: elevation + stackH,
        share,
      }
    })
  }, [network, hiddenKinds, liveStatuses, dis, utilization])
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes])

  const arcs = useMemo(() => {
    const maxCap = Math.max(1, ...(network?.edges ?? []).map((e) => e.capacity || 0))
    return (network?.edges ?? [])
      .filter((e) => byId[e.source] && byId[e.target])
      .map((e) => {
        const id = `${e.source}->${e.target}`
        const share = (e.capacity || 0) / maxCap
        return {
          ...e,
          id,
          disrupted: dis.edges.has(id),
          rerouted: rer.has(id),
          src: byId[e.source].position,
          dst: byId[e.target].position,
          share,
          height: 0.12 + share * 0.28,
          rgb: byId[e.source].type.rgb,
          util: clamp(byId[e.source].util ?? 0.5, 0, 1),
          modeKey: MODES[e.mode] ? e.mode : 'road',
        }
      })
  }, [network, byId, dis, rer])

  const focusId = (hoverId && byId[hoverId] && hoverId) || (selectedNode && byId[selectedNode] && selectedNode) || null
  const related = useMemo(() => (focusId ? pathThrough(focusId, arcs) : null), [focusId, arcs])
  const highlightSet = useMemo(() => new Set(highlight || []), [highlight])
  const affected = useMemo(() => {
    const s = new Set()
    for (const n of nodes) if (n.status === 'down' || n.status === 'stressed') s.add(n.id)
    return s
  }, [nodes])
  const disruptionActive = affected.size > 0 || (dis.edges.size > 0 && mix > 0.01)

  // Focus + context: related path at full strength, everything else dimmed.
  const styledNodes = useMemo(
    () =>
      nodes.map((n) => {
        let alpha = 1
        if (related) alpha = related.nodes.has(n.id) ? 1 : 0.25
        else if (highlightSet.size) alpha = highlightSet.has(n.id) ? 1 : 0.45
        else if (disruptionActive) alpha = affected.has(n.id) ? 1 : 0.6
        return { ...n, alpha, ringAlpha: n.eventOnly ? mix : 1 }
      }),
    [nodes, related, highlightSet, disruptionActive, affected, mix],
  )
  const styledArcs = useMemo(
    () =>
      arcs.map((a) => {
        let alpha = 1
        const onPath = related?.edges.has(a.id)
        if (related) alpha = onPath ? 1 : 0.2
        else if (highlightSet.size) alpha = highlightSet.has(a.source) || highlightSet.has(a.target) ? 1 : 0.4
        else if (disruptionActive) alpha = a.disrupted || a.rerouted || affected.has(a.source) || affected.has(a.target) ? 1 : 0.5
        const base = onPath ? 255 : 70 + 130 * a.util // opacity follows utilization
        const k = a.rerouted ? mix : 0
        const color = lerpRgb(a.rgb, t.accent, k)
        const fadeOut = a.disrupted ? 1 - mix : 1
        return {
          ...a,
          sourceColor: withAlpha(color, lerp(base, 240, k) * alpha * fadeOut),
          targetColor: withAlpha(color, lerp(base * 0.45, 240, k) * alpha * fadeOut),
          width: 1 + a.share * 2.6 + (onPath ? 1.6 : 0) + 1.5 * k,
        }
      }),
    [arcs, related, highlightSet, disruptionActive, affected, mix, t],
  )

  // ------------------------------------------------------------------ camera
  const flyTo = useCallback((vs, duration = 1400, interpolator) => {
    flyEnd.current = performance.now() + duration
    setViewState((cur) => ({
      ...cur,
      ...vs,
      transitionDuration: prefersReducedMotion() ? 0 : duration,
      transitionInterpolator: interpolator || new FlyToInterpolator({ speed: 1.3 }),
    }))
  }, [])
  const boundsView = useCallback(
    (ids, { pitch = PITCH, bearing = BEARING, maxZoom = 6.3, pad = 0.6 } = {}) => {
      const pts = ids.map((id) => byId[id]?.position).filter(Boolean)
      if (!pts.length || !size.w) return null
      const lons = pts.map((p) => p[0])
      const lats = pts.map((p) => p[1])
      const vp = new WebMercatorViewport({ width: size.w, height: size.h })
      const { longitude, latitude, zoom } = vp.fitBounds(
        [[Math.min(...lons) - pad, Math.min(...lats) - pad], [Math.max(...lons) + pad, Math.max(...lats) + pad]],
        { padding: Math.min(90, size.w / 6) },
      )
      return { longitude, latitude, zoom: Math.min(zoom, maxZoom), pitch, bearing }
    },
    [byId, size],
  )
  const overview = useCallback(() => {
    const v = boundsView(nodes.map((n) => n.id), { pad: 1.2 })
    if (v) flyTo(v, 1300)
    setPreset('overview')
  }, [boundsView, nodes, flyTo])
  const applyPreset = (p) => {
    if (p === 'overview') return overview()
    setPreset(p)
    const ease = new LinearInterpolator(['pitch', 'bearing', 'longitude', 'latitude', 'zoom'])
    if (p === 'top') flyTo({ pitch: 0, bearing: 0 }, 600, ease)
    else if (p === 'tilted') flyTo({ pitch: PITCH + 3, bearing: -24 }, 600, ease)
    else if (p === 'focus' && focusId) {
      const v = boundsView([...(related?.nodes ?? [focusId])], { pitch: 52, bearing: -18, pad: 0.8 })
      if (v) flyTo(v, 1100)
    }
  }

  // Fly in once the canvas has a size; re-frame on F / "Fit view".
  const flewIn = useRef(false)
  useEffect(() => {
    if (flewIn.current || !size.w || !nodes.length) return undefined
    flewIn.current = true
    const id = setTimeout(overview, 120)
    return () => clearTimeout(id)
  }, [size.w, nodes.length, overview])
  const fitSeen = useRef(ui.fitSignal)
  useEffect(() => {
    if (ui.fitSignal === fitSeen.current) return
    fitSeen.current = ui.fitSignal
    overview()
  }, [ui.fitSignal, overview])

  // Frame Chaos Finder targets.
  useEffect(() => {
    if (!focus?.length) return
    const v = boundsView(focus, { pitch: 52, bearing: -18, pad: 1 })
    if (v) flyTo(v, 1300)
    setPreset(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusKey])

  // ------------------------------------------------------------------ replay (story mode)
  const storyAnchor = useMemo(() => {
    if (!sim) return null
    for (const row of sim.timeline) {
      const id = (row.down || []).find((d) => byId[d])
      if (id) return id
    }
    return null
  }, [sim, byId])
  useEffect(() => {
    if (!ui.story) return
    const n = byId[storyAnchor]
    if (n) flyTo({ longitude: n.position[0], latitude: n.position[1], zoom: 5.4, pitch: 58, bearing: -20 }, 1600)
    setPreset(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ui.story])
  useEffect(() => {
    if (!ui.story || !ui.playing || reduced || performance.now() < flyEnd.current) return
    setViewState((cur) => ({ ...cur, bearing: cur.bearing + STORY_BEARING_STEP, transitionDuration: 650, transitionInterpolator: new LinearInterpolator(['bearing']) }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day])
  const caption = ui.story && sim ? captionFor(sim, day, byId) : null

  // ------------------------------------------------------------------ ripples (once per failure)
  const prevStatuses = useRef(liveStatuses)
  const [ripples, setRipples] = useState([])
  useEffect(() => {
    const prev = prevStatuses.current
    prevStatuses.current = liveStatuses
    if (!prev || !liveStatuses || reduced) return undefined
    const fresh = Object.entries(liveStatuses).filter(([id, s]) => s === 'down' && prev[id] !== 'down').map(([id]) => id)
    if (!fresh.length) return undefined
    const start = performance.now() / 1000
    setRipples((r) => [...r, ...fresh.map((id) => ({ id, start }))])
    const timer = setTimeout(() => setRipples((r) => r.filter((x) => performance.now() / 1000 - x.start < RIPPLE_S)), RIPPLE_S * 1000 + 50)
    return () => clearTimeout(timer)
  }, [liveStatuses, reduced])

  const animating = !reduced && (flowsOn || Boolean(related) || ripples.length > 0)
  const now = useClock(animating)

  // ------------------------------------------------------------------ labels (priority + collision)
  const viewport = useMemo(() => (size.w ? new WebMercatorViewport({ ...viewState, width: size.w, height: size.h }) : null), [viewState, size])
  const labelData = useMemo(() => {
    if (!layersOn.labels || !layersOn.nodes || !viewport) return []
    const vp = viewport
    const z = viewState.zoom
    const ranked = [...styledNodes].sort((a, b) => (b.stock || 0) + (b.demand || 0) - ((a.stock || 0) + (a.demand || 0)))
    const important = new Set(ranked.slice(0, Math.max(3, Math.ceil(ranked.length / 4))).map((n) => n.id))
    const priority = (n) =>
      n.id === selectedNode ? 100 : n.id === hoverId ? 95 : n.status === 'down' ? 90 : n.status === 'stressed' ? 80
        : highlightSet.has(n.id) ? 75 : related?.nodes.has(n.id) ? 70 : (n.risk ?? 0) >= 0.35 ? 60 : important.has(n.id) ? 50 : 10
    const minPriority = z < 4.6 ? 50 : z < 5.4 ? 40 : 0
    const boxes = []
    const out = []
    for (const n of styledNodes.map((x) => ({ n: x, p: priority(x) })).filter((x) => x.p >= minPriority).sort((a, b) => b.p - a.p).map((x) => x.n)) {
      if (related && !related.nodes.has(n.id)) continue
      const [x, y] = vp.project([n.position[0], n.position[1], n.top + 4000])
      if (!Number.isFinite(x) || x < -40 || y < -40 || x > size.w + 40 || y > size.h + 40) continue
      const label = n.name && n.name.length > 22 ? `${n.name.slice(0, 21)}…` : n.name || n.id
      const w = label.length * 6.4 + 10
      const box = [x - w / 2, y - 38, x + w / 2, y - 22]
      if (boxes.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) continue
      boxes.push(box)
      out.push({ id: n.id, label, position: [n.position[0], n.position[1], n.top + 4000], alpha: n.alpha })
    }
    return out
  }, [layersOn.labels, layersOn.nodes, size, viewport, viewState.zoom, styledNodes, selectedNode, hoverId, highlightSet, related])
  const labelKey = labelData.map((l) => `${l.id}:${l.alpha}`).join('|')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableLabels = useMemo(() => labelData, [labelKey])

  // ------------------------------------------------------------------ static layers (memoized)
  const ringNodes = useMemo(() => styledNodes.filter((n) => n.status), [styledNodes])
  const staticLayers = useMemo(() => {
    const shadowAlpha = dark ? 80 : 34
    return [
      tilesFailed &&
        new SolidPolygonLayer({ id: 'ground', data: [{ polygon: INDIA_RING }], getPolygon: (d) => d.polygon, getFillColor: withAlpha(t.raised, 170), extruded: false }),
      tilesFailed &&
        new PathLayer({
          id: 'graticule',
          data: [...GRATICULE, { path: INDIA_RING, outline: true }],
          getPath: (d) => d.path,
          getColor: (d) => withAlpha(d.outline ? t.borderStrong : t.border, d.outline ? 220 : 160),
          getWidth: 1,
          widthUnits: 'pixels',
        }),
      layersOn.nodes &&
        new ScatterplotLayer({
          id: 'shadows',
          data: styledNodes,
          getPosition: (n) => [n.position[0] - 0.05 - 0.14 * (n.elevation / MAX_COLUMN_M), n.position[1] - 0.08 - 0.2 * (n.elevation / MAX_COLUMN_M)],
          getRadius: (n) => n.type.radius * 1.35,
          getFillColor: (n) => [0, 0, 0, shadowAlpha * n.alpha],
          radiusUnits: 'meters',
          transitions: { getFillColor: 150 },
        }),
      layersOn.risk &&
        new ScatterplotLayer({
          id: 'risk-glow',
          data: styledNodes.filter((n) => !isDemand(n.kind) && n.risk != null),
          getPosition: (n) => n.position,
          getRadius: (n) => n.type.radius * 1.4 + (n.risk || 0) * 110000,
          getFillColor: (n) => withAlpha(t.accent, (10 + (n.risk || 0) * 60) * n.alpha),
          radiusUnits: 'meters',
          transitions: { getFillColor: 150 },
        }),
      ringNodes.length > 0 &&
      new ScatterplotLayer({
        id: 'status-ring',
        data: ringNodes,
        getPosition: (n) => n.position,
        getRadius: (n) => n.type.radius * 1.6,
        getLineColor: (n) => withAlpha(STATUS_COLORS[n.status].rgb, 235 * n.ringAlpha * Math.max(0.4, n.alpha)),
        getFillColor: (n) => withAlpha(STATUS_COLORS[n.status].rgb, (n.status === 'ok' ? 0 : 34) * n.ringAlpha * n.alpha),
        stroked: true,
        filled: true,
        lineWidthUnits: 'pixels',
        getLineWidth: (n) => (n.status === 'ok' ? 2 : 3),
        radiusUnits: 'meters',
      }),
      highlightSet.size > 0 &&
        new ScatterplotLayer({
          id: 'highlight',
          data: styledNodes.filter((n) => highlightSet.has(n.id)),
          getPosition: (n) => n.position,
          getRadius: (n) => n.type.radius * 2.1,
          getLineColor: withAlpha(t.accent, 230),
          getFillColor: withAlpha(t.accent, 22),
          stroked: true,
          lineWidthUnits: 'pixels',
          getLineWidth: 2,
          radiusUnits: 'meters',
        }),
      selectedNode &&
        byId[selectedNode] &&
        new ScatterplotLayer({
          id: 'selected',
          data: [byId[selectedNode]],
          getPosition: (n) => n.position,
          getRadius: (n) => n.type.radius * 1.95,
          getLineColor: withAlpha(t.accent, 255),
          filled: false,
          stroked: true,
          lineWidthUnits: 'pixels',
          getLineWidth: 3,
          radiusUnits: 'meters',
        }),
      layersOn.routes &&
        new ArcLayer({
          id: 'routes',
          data: styledArcs,
          getSourcePosition: (a) => a.src,
          getTargetPosition: (a) => a.dst,
          getSourceColor: (a) => a.sourceColor,
          getTargetColor: (a) => a.targetColor,
          getWidth: (a) => a.width,
          getHeight: (a) => a.height,
          widthUnits: 'pixels',
          transitions: { getSourceColor: 150, getTargetColor: 150, getWidth: 150 },
        }),
      layersOn.routes &&
        mix > 0.01 &&
        new PathLayer({
          id: 'routes-disrupted',
          data: styledArcs.filter((a) => a.disrupted).flatMap((a) => dashedArc(a.src, a.dst, a.height).map((path) => ({ path }))),
          getPath: (d) => d.path,
          getColor: withAlpha(STATUS_COLORS.down.rgb, 235 * mix),
          getWidth: 2.5,
          widthUnits: 'pixels',
          capRounded: true,
          updateTriggers: { getColor: mix },
        }),
      ...(layersOn.nodes
        ? NODE_KINDS.map((kind) => {
            const type = typeOf(kind)
            const data = styledNodes.filter((n) => n.kind === kind)
            if (!data.length) return null
            return new ColumnLayer({
              id: `nodes-${kind}`,
              data,
              diskResolution: type.disk,
              angle: type.angle,
              radius: type.radius,
              extruded: true,
              material: MATERIAL,
              getPosition: (n) => n.position,
              getElevation: (n) => n.elevation,
              getFillColor: (n) => withAlpha(type.rgb, 248 * n.alpha),
              // no attribute transitions on ColumnLayer: in deck.gl 9 they swap the buffer layout and luma.gl warns
            })
          })
        : []),
      layersOn.nodes &&
        styledNodes.some((n) => n.type.stack) &&
        new ColumnLayer({
          id: 'nodes-factory-stack',
          data: styledNodes.filter((n) => n.type.stack),
          diskResolution: 4,
          angle: 45,
          radius: typeOf('factory').radius * 0.42,
          extruded: true,
          material: MATERIAL,
          getPosition: (n) => [n.position[0] + 0.05, n.position[1] + 0.05, n.elevation],
          getElevation: (n) => n.stackH,
          getFillColor: (n) => withAlpha(typeOf('factory').rgb.map((c) => Math.min(255, c + 40)), 250 * n.alpha),
        }),
      layersOn.nodes &&
        atlas &&
        new IconLayer({
          id: 'node-icons',
          data: styledNodes,
          iconAtlas: atlas.url,
          iconMapping: atlas.mapping,
          getIcon: (n) => (atlas.mapping[n.kind] ? n.kind : 'customer'),
          getPosition: (n) => [n.position[0], n.position[1], n.top + 4000],
          getColor: (n) => [255, 255, 255, 255 * n.alpha],
          getSize: 20,
          sizeUnits: 'pixels',
          billboard: true,
          alphaCutoff: 0.05,
          parameters: { depthCompare: 'always' },
          transitions: { getColor: 150 },
        }),
      stableLabels.length > 0 &&
        new TextLayer({
          id: 'node-labels',
          data: stableLabels,
          getText: (d) => d.label,
          getPosition: (d) => d.position,
          getPixelOffset: [0, -16],
          getSize: 12,
          getColor: (d) => withAlpha(t.fg, 235 * d.alpha),
          fontFamily: 'Inter Variable, system-ui, sans-serif',
          fontWeight: 500,
          characterSet: 'auto',
          fontSettings: { sdf: true, fontSize: 48, buffer: 6 },
          outlineWidth: 4,
          outlineColor: withAlpha(t.surface, 230),
          getTextAnchor: 'middle',
          getAlignmentBaseline: 'bottom',
          billboard: true,
          parameters: { depthCompare: 'always' },
        }),
    ].filter(Boolean)
  }, [tilesFailed, t, dark, layersOn, styledNodes, ringNodes, highlightSet, selectedNode, byId, styledArcs, mix, atlas, stableLabels])

  // ------------------------------------------------------------------ animated layers (only while animating)
  const flowTrips = useMemo(() => {
    if (!flowsOn) return []
    const out = []
    for (const a of styledArcs) {
      if (a.disrupted || a.util <= 0.01) continue // particles only on active, unblocked lanes
      const path = arcPath(a.src, a.dst, a.height)
      const travel = Math.max(0.6, a.lead || 1) * SECONDS_PER_LEAD_DAY
      const count = a.share > 0.6 ? 2 : 1
      const color = a.rerouted && mix > 0.5 ? t.accent : MODE_RGB[a.modeKey]
      for (let k = 0; k < count; k++) {
        const start = (k / count) * FLOW_LOOP_S + (a.id.length % 7) * 0.45
        for (const shift of [0, FLOW_LOOP_S]) {
          out.push({ path, timestamps: path.map((_, i) => start + shift + (i / (path.length - 1)) * travel), color, alpha: a.sourceColor[3] / 255 })
        }
      }
    }
    return out
  }, [flowsOn, styledArcs, mix, t])
  const focusTrips = useMemo(() => {
    if (!related || reduced) return []
    const out = []
    for (const a of styledArcs) {
      if (!related.edges.has(a.id) || a.disrupted) continue
      const path = arcPath(a.src, a.dst, a.height)
      const travel = Math.max(0.6, a.lead || 1) * 1.2
      for (const shift of [0, FLOW_LOOP_S]) out.push({ path, timestamps: path.map((_, i) => shift + (a.id.length % 5) * 0.6 + (i / (path.length - 1)) * travel) })
    }
    return out
  }, [related, styledArcs, reduced])

  const time = (now % FLOW_LOOP_S) + FLOW_LOOP_S
  const animatedLayers = [
    flowTrips.length > 0 &&
      layersOn.routes &&
      new TripsLayer({
        id: 'flow',
        data: flowTrips,
        getPath: (d) => d.path,
        getTimestamps: (d) => d.timestamps,
        getColor: (d) => withAlpha(d.color, 230 * d.alpha),
        widthMinPixels: 2.5,
        capRounded: true,
        jointRounded: true,
        fadeTrail: true,
        trailLength: 0.8,
        currentTime: time,
      }),
    focusTrips.length > 0 &&
      new TripsLayer({
        id: 'focus-flow',
        data: focusTrips,
        getPath: (d) => d.path,
        getTimestamps: (d) => d.timestamps,
        getColor: withAlpha(t.accent, 255),
        widthMinPixels: 3,
        capRounded: true,
        jointRounded: true,
        fadeTrail: true,
        trailLength: 1,
        currentTime: time,
      }),
    ripples.length > 0 &&
      new ScatterplotLayer({
        id: 'ripples',
        data: ripples.filter((r) => byId[r.id] && now - r.start < RIPPLE_S),
        getPosition: (r) => byId[r.id].position,
        getRadius: (r) => 20000 + ((now - r.start) / RIPPLE_S) * 150000,
        getLineColor: (r) => withAlpha(STATUS_COLORS.down.rgb, 210 * (1 - (now - r.start) / RIPPLE_S)),
        stroked: true,
        filled: false,
        lineWidthMinPixels: 2,
        radiusUnits: 'meters',
        updateTriggers: { getRadius: now, getLineColor: now },
      }),
  ].filter(Boolean)

  // ------------------------------------------------------------------ interaction (JS hit-testing, no GPU picking)
  const pointer = useRef({ x: 0, y: 0, down: null })
  const [cursor, setCursor] = useState(null) // { x, y } of the hovered node card
  const hitTest = (x, y) => {
    if (!viewport || !layersOn.nodes) return null
    const ppm = 1 / viewport.metersPerPixel // pixels per meter at the current zoom
    let best = null
    let bestD = Infinity
    for (const n of styledNodes) {
      const [bx, by] = viewport.project([n.position[0], n.position[1], 0])
      const [tx, ty] = viewport.project([n.position[0], n.position[1], n.top + 4000])
      const d = distToSegment(x, y, bx, by, tx, ty)
      const reach = Math.max(10, n.type.radius * ppm + 4)
      if (d < reach && d < bestD) {
        best = n
        bestD = d
      }
    }
    return best
  }
  const localXY = (e) => {
    const r = containerRef.current.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }
  const onPointerMove = (e) => {
    const { x, y } = localXY(e)
    pointer.current.x = x
    pointer.current.y = y
    if (pointer.current.down) return
    const n = hitTest(x, y)
    const id = n?.id ?? null
    setHoverId((cur) => (cur === id ? cur : id))
    setCursor(n ? { x, y } : null)
  }
  const onPointerDown = (e) => {
    pointer.current.down = localXY(e)
  }
  const onPointerUp = (e) => {
    const start = pointer.current.down
    pointer.current.down = null
    if (!start || e.button !== 0) return
    const { x, y } = localXY(e)
    if (Math.hypot(x - start.x, y - start.y) > 4) return // a drag, not a click
    const n = hitTest(x, y)
    selectNode(n ? n.id : null)
  }
  const hovered = hoverId ? byId[hoverId] : null
  const compact = size.w > 0 && size.w < 900
  const layerItems = [
    { key: 'nodes', label: 'Nodes', icon: Boxes },
    { key: 'routes', label: 'Routes', icon: Route },
    { key: 'labels', label: 'Labels', icon: Tags },
    { key: 'risk', label: 'Risk', icon: Sparkles },
  ]
  const presetOptions = [
    { value: 'overview', label: 'Overview' },
    { value: 'top', label: 'Top' },
    { value: 'tilted', label: 'Tilted' },
    { value: 'focus', label: 'Focus', disabled: !focusId, title: focusId ? 'Frame the selection and its paths' : 'Select a node first' },
  ]

  return (
    <div
      ref={containerRef}
      className={cn('relative h-full w-full', tilesFailed && 'bg-map')}
      onPointerMove={onPointerMove}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerLeave={() => {
        pointer.current.down = null
        setHoverId(null)
        setCursor(null)
      }}
    >
      <DeckGL
        viewState={viewState}
        onViewStateChange={({ viewState: vs, interactionState }) => {
          setViewState(vs)
          if (interactionState?.isDragging || interactionState?.isZooming || interactionState?.isRotating) setPreset(null)
        }}
        controller={{ dragRotate: true, touchRotate: true, keyboard: true }}
        layers={[...staticLayers, ...animatedLayers]}
        effects={EFFECTS}
        getCursor={({ isDragging }) => (isDragging ? 'grabbing' : hoverId ? 'pointer' : 'grab')}
      >
        {!tilesFailed && (
          <BaseMap
            key={theme}
            mapStyle={BASEMAP[theme]}
            attributionControl={{ compact: true }}
            onLoad={(e) => {
              mapLoaded.current = true
              quietBasemap(e.target, tokens.color.mapBg)
            }}
            onError={() => {
              // the style itself failed: no basemap at all. Otherwise tolerate a few missing tiles.
              tileErrors.current += 1
              if (!mapLoaded.current || tileErrors.current >= 3) setTilesFailed(true)
            }}
          />
        )}
      </DeckGL>
      <div className="map-vignette pointer-events-none absolute inset-0" aria-hidden />
      {hovered && cursor && (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-20 w-60 rounded-md border border-border bg-surface px-2.5 py-2 text-xs shadow-float"
          style={{ left: Math.min(cursor.x + 14, size.w - 250), top: Math.min(cursor.y + 14, size.h - 96) }}
        >
          <div className="flex items-center gap-1.5">
            <TypeIcon kind={hovered.kind} size="xs" />
            <span className="num text-fg">{hovered.id}</span>
            <span className="truncate text-fg-2">{hovered.name || hovered.city}</span>
          </div>
          <div className="mt-0.5 flex items-center gap-1.5 text-fg-muted">
            {hovered.type.label}
            {hovered.city && ` · ${hovered.city}`}
            {hovered.status && (
              <span className="ml-auto inline-flex items-center gap-1 text-fg-2">
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: STATUS_COLORS[hovered.status].color }} aria-hidden />
                {STATUS[hovered.status].label}
              </span>
            )}
          </div>
          <dl className="mt-1.5 grid grid-cols-3 gap-1">
            <div>
              <dt className="text-fg-muted">Stock</dt>
              <dd className="num text-fg">{fmtNum(hovered.stock)}</dd>
            </div>
            <div>
              <dt className="text-fg-muted">Util</dt>
              <dd className="num text-fg">{isDemand(hovered.kind) && !hovered.capacity ? '–' : fmtPct(hovered.util)}</dd>
            </div>
            <div>
              <dt className="text-fg-muted">Critical</dt>
              <dd className="num text-fg">{hovered.risk == null ? 'n/a' : fmtPct(hovered.risk)}</dd>
            </div>
          </dl>
        </div>
      )}

      {/* top-left: view switch + layers */}
      <div className="absolute left-3 top-3 z-10 flex items-center gap-2">
        {leading}
        {compact ? (
          <Menu
            icon={SlidersHorizontal}
            label="Layers"
            size="sm"
            align="start"
            items={[
              ...layerItems.map((l) => ({ key: l.key, label: l.label, checked: layersOn[l.key], onSelect: () => setLayersOn((s) => ({ ...s, [l.key]: !s[l.key] })) })),
              { key: 'flow', label: reduced ? 'Animate flows (reduced motion)' : 'Animate flows', checked: flowsOn, disabled: reduced, onSelect: () => ui.setPref('animateFlows', (v) => !v) },
            ]}
          />
        ) : (
          <div className="flex items-center gap-0.5 rounded-md border border-border bg-surface/95 p-0.5" role="group" aria-label="Layers">
            {layerItems.map((l) => (
              <Toggle key={l.key} pressed={layersOn[l.key]} onChange={(v) => setLayersOn((s) => ({ ...s, [l.key]: v }))} icon={l.icon}>
                {l.label}
              </Toggle>
            ))}
            <Toggle pressed={flowsOn} disabled={reduced} title={reduced ? 'Off because reduced motion is on' : 'Animated particles on active lanes'} onChange={(v) => ui.setPref('animateFlows', v)} icon={Waves}>
              Animate flows
            </Toggle>
          </div>
        )}
      </div>

      {/* top-right: camera */}
      <div className="absolute right-3 top-3 z-10 flex items-center gap-1.5">
        {tilesFailed && (
          <Tooltip content="Basemap tiles could not load; the network still renders" side="bottom-end">
            <span className="flex h-7 items-center gap-1 rounded-md border border-border bg-surface/95 px-2 text-xs text-fg-muted">
              <WifiOff className="h-3.5 w-3.5" aria-hidden />
              Offline map
            </span>
          </Tooltip>
        )}
        {compact ? (
          <Menu icon={Video} label="Camera" size="sm" items={presetOptions.map((o) => ({ key: o.value, label: o.label, disabled: o.disabled, onSelect: () => applyPreset(o.value) }))} />
        ) : (
          <SegmentedControl size="xs" label="Camera" value={preset} onChange={applyPreset} options={presetOptions} />
        )}
        <IconButton
          icon={Navigation2}
          label="Reset bearing to north"
          variant="secondary"
          size="sm"
          tooltipSide="bottom-end"
          onClick={() => flyTo({ bearing: 0 }, 500, new LinearInterpolator(['bearing']))}
          style={{ transform: `rotate(${-viewState.bearing}deg)` }}
        />
        <IconButton icon={Crosshair} label="Reset view" shortcut="F" variant="secondary" size="sm" tooltipSide="bottom-end" onClick={overview} />
      </div>

      {/* replay caption */}
      {caption && (
        <div className="absolute left-1/2 top-14 z-10 flex max-w-[min(640px,calc(100%-24px))] -translate-x-1/2 animate-rise-in items-center gap-2 rounded-md border border-border bg-surface/95 py-1 pl-3 pr-1 shadow-float">
          <span className="truncate text-sm text-fg" aria-live="polite">
            {caption}
          </span>
          <IconButton icon={ui.playing ? Pause : Play} label={ui.playing ? 'Pause replay' : 'Resume replay'} size="sm" onClick={ui.playing ? ui.pause : ui.play} />
          <IconButton icon={Square} label="Stop replay" shortcut="Esc" size="sm" onClick={ui.stopStory} />
        </div>
      )}
    </div>
  )
}
