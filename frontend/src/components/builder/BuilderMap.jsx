import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Crosshair, Maximize2, Minus, Plus } from 'lucide-react'
import { glyphMarkup, typeOf } from '../../lib/nodeTypes.js'
import { INDIAN_CITIES, INDIA_OUTLINE } from '../../lib/indianCities.js'
import { Button, cn } from '../ui/index.js'

const INDIA_BOUNDS = { minLon: 67.5, maxLon: 97.8, minLat: 6, maxLat: 37.2 }
const K = 10 // SVG units per degree
const NODE_R = 0.55 // degrees
const COS = Math.cos((22 * Math.PI) / 180) // equirectangular, true to scale around central India

const project = (lon, lat) => [lon * K * COS, -lat * K]
const unproject = (x, y) => ({ lon: x / (K * COS), lat: -y / K })
const round3 = (v) => Math.round(v * 1000) / 1000

function fitBox(nodes) {
  let { minLon, maxLon, minLat, maxLat } = INDIA_BOUNDS
  for (const n of nodes) {
    if (!Number.isFinite(n.lon) || !Number.isFinite(n.lat)) continue
    minLon = Math.min(minLon, n.lon - 1)
    maxLon = Math.max(maxLon, n.lon + 1)
    minLat = Math.min(minLat, n.lat - 1)
    maxLat = Math.max(maxLat, n.lat + 1)
  }
  const [x0, y1] = project(minLon, minLat)
  const [x1, y0] = project(maxLon, maxLat)
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
}

/** Node marker: the type's footprint shape in the type color with the white glyph inside. */
function Marker({ node, selected, size = NODE_R * K }) {
  const t = typeOf(node.kind)
  const s = (size * 2) / 24
  return (
    <g opacity={node.status === 'inactive' ? 0.4 : 1}>
      {selected && <circle r={size * 1.65} fill="none" stroke="rgb(var(--accent))" strokeWidth={size * 0.28} />}
      <g transform={`translate(${-size} ${-size}) scale(${s})`}>
        <path d={t.thumb} fill={t.color} stroke="rgb(var(--surface))" strokeWidth="1.6" strokeLinejoin="round" />
        <g transform="translate(6 6.4) scale(0.5)" dangerouslySetInnerHTML={{ __html: glyphMarkup(node.kind, '#FFFFFF', 2.6) }} />
      </g>
    </g>
  )
}

/**
 * Offline map preview for the builder (pure SVG: works with no network and no map tiles).
 * Click a marker or lane to select it. In pick mode a click drops a location pin instead (onPick({lat, lon})).
 * Wheel zooms around the cursor, drag pans.
 */
export default function BuilderMap({ nodes = [], edges = [], selection, onSelect, pickMode = false, onPick, pin, className }) {
  const svgRef = useRef(null)
  const home = useMemo(() => fitBox(nodes), [nodes])
  const [view, setView] = useState(home)
  const drag = useRef(null)
  const homeKey = `${nodes.length}`
  useEffect(() => setView(home), [homeKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes])
  const toSvg = useCallback((clientX, clientY) => {
    const svg = svgRef.current
    const ctm = svg?.getScreenCTM()
    if (!ctm) return null
    const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse())
    return [p.x, p.y]
  }, [])

  const zoom = (factor, center) => {
    setView((v) => {
      const [cx, cy] = center || [v.x + v.w / 2, v.y + v.h / 2]
      const w = Math.min(Math.max(v.w * factor, 20), home.w * 2.5)
      const h = (w / v.w) * v.h
      return { x: cx - ((cx - v.x) / v.w) * w, y: cy - ((cy - v.y) / v.h) * h, w, h }
    })
  }

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return undefined
    const onWheel = (e) => {
      e.preventDefault()
      zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15, toSvg(e.clientX, e.clientY))
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }) // re-bind each render so `zoom` sees the current home box

  const onPointerDown = (e) => {
    if (e.button !== 0) return
    drag.current = { x: e.clientX, y: e.clientY, view, moved: false }
  }
  const onPointerMove = (e) => {
    const d = drag.current
    if (!d) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    if (!d.moved && Math.hypot(dx, dy) < 4) return
    d.moved = true
    const rect = svgRef.current.getBoundingClientRect()
    const scale = Math.max(d.view.w / rect.width, d.view.h / rect.height)
    setView({ ...d.view, x: d.view.x - dx * scale, y: d.view.y - dy * scale })
  }
  const onPointerUp = (e) => {
    const d = drag.current
    drag.current = null
    if (!d || d.moved) return
    const target = e.target.closest?.('[data-node],[data-edge]')
    if (pickMode) {
      const p = toSvg(e.clientX, e.clientY)
      if (p) {
        const { lat, lon } = unproject(p[0], p[1])
        onPick?.({ lat: round3(lat), lon: round3(lon) })
      }
      return
    }
    if (target?.dataset.node) onSelect?.({ type: 'node', id: target.dataset.node })
    else if (target?.dataset.edge) onSelect?.({ type: 'edge', id: target.dataset.edge })
    else onSelect?.(null)
  }

  const outline = useMemo(() => INDIA_OUTLINE.map(([lon, lat], i) => `${i ? 'L' : 'M'}${project(lon, lat).join(' ')}`).join(' ') + 'Z', [])
  const grid = []
  for (let lon = 65; lon <= 100; lon += 5) grid.push(['v', lon])
  for (let lat = 5; lat <= 40; lat += 5) grid.push(['h', lat])
  const r = NODE_R * K * Math.min(1.4, Math.max(0.55, view.w / home.w))

  return (
    <div className={cn('relative overflow-hidden rounded-lg border border-border bg-map', className)}>
      <svg
        ref={svgRef}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid meet"
        className={cn('h-full w-full touch-none select-none', pickMode ? 'cursor-crosshair' : 'cursor-grab active:cursor-grabbing')}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => (drag.current = null)}
        role="img"
        aria-label="Network map preview"
      >
        <defs>
          <marker id="bm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 0 10 5 0 10z" fill="rgb(var(--fg-muted))" />
          </marker>
        </defs>
        {grid.map(([dir, v]) => {
          const [x1, y1] = dir === 'v' ? project(v, 0) : project(60, v)
          const [x2, y2] = dir === 'v' ? project(v, 45) : project(105, v)
          return <line key={`${dir}${v}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgb(var(--border))" strokeWidth={0.6} vectorEffect="non-scaling-stroke" />
        })}
        <path d={outline} fill="rgb(var(--surface))" fillOpacity={0.65} stroke="rgb(var(--border-strong))" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        {INDIAN_CITIES.map((c) => {
          const [x, y] = project(c.lon, c.lat)
          return (
            <g key={c.name}>
              <circle cx={x} cy={y} r={0.9} fill="rgb(var(--fg-muted))" fillOpacity={0.45}>
                <title>{c.name}</title>
              </circle>
              {view.w < home.w * 0.6 && (
                <text x={x + 1.4} y={y + 0.9} fontSize={2.6} fill="rgb(var(--fg-muted))" fillOpacity={0.8}>
                  {c.name}
                </text>
              )}
            </g>
          )
        })}
        {edges.map((e) => {
          const a = byId[e.source]
          const b = byId[e.target]
          if (!a || !b) return null
          const [x1, y1] = project(a.lon, a.lat)
          const [x2, y2] = project(b.lon, b.lat)
          const sel = selection?.type === 'edge' && selection.id === e.id
          const len = Math.hypot(x2 - x1, y2 - y1) || 1
          const trim = r * 1.15
          const [ex, ey] = [x2 - ((x2 - x1) / len) * trim, y2 - ((y2 - y1) / len) * trim]
          return (
            <g key={e.id} data-edge={e.id} className="cursor-pointer">
              <line x1={x1} y1={y1} x2={ex} y2={ey} stroke="transparent" strokeWidth={10} vectorEffect="non-scaling-stroke" />
              <line
                x1={x1}
                y1={y1}
                x2={ex}
                y2={ey}
                stroke={sel ? 'rgb(var(--accent))' : typeOf(a.kind).color}
                strokeOpacity={sel ? 1 : 0.55}
                strokeWidth={sel ? 3 : 1.6}
                strokeDasharray={e.status === 'inactive' ? '4 3' : undefined}
                vectorEffect="non-scaling-stroke"
                markerEnd="url(#bm-arrow)"
              >
                <title>{`${e.id}: ${e.source} → ${e.target}`}</title>
              </line>
            </g>
          )
        })}
        {nodes.map((n) => {
          const [x, y] = project(n.lon, n.lat)
          if (!Number.isFinite(x) || !Number.isFinite(y)) return null
          const sel = selection?.type === 'node' && selection.id === n.id
          return (
            <g key={n.id} data-node={n.id} transform={`translate(${x} ${y})`} className="cursor-pointer">
              <title>{`${n.id} · ${n.name} (${typeOf(n.kind).label})`}</title>
              <Marker node={n} selected={sel} size={r} />
              <text y={r * 2.1} textAnchor="middle" fontSize={r * 0.75} fontWeight={600} fill="rgb(var(--fg-2))" stroke="rgb(var(--surface))" strokeWidth={r * 0.18} paintOrder="stroke">
                {n.id}
              </text>
            </g>
          )
        })}
        {pin && Number.isFinite(Number(pin.lat)) && Number.isFinite(Number(pin.lon)) && pin.lat !== '' && pin.lon !== '' && (
          <g transform={`translate(${project(Number(pin.lon), Number(pin.lat)).join(' ')})`} pointerEvents="none">
            <circle r={r * 1.9} fill="rgb(var(--accent))" fillOpacity={0.15} stroke="rgb(var(--accent))" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
            <circle r={r * 0.35} fill="rgb(var(--accent))" />
          </g>
        )}
      </svg>
      <div className="absolute right-2 top-2 flex flex-col gap-1">
        <Button size="icon" variant="secondary" icon={Plus} aria-label="Zoom in" onClick={() => zoom(1 / 1.4)} />
        <Button size="icon" variant="secondary" icon={Minus} aria-label="Zoom out" onClick={() => zoom(1.4)} />
        <Button size="icon" variant="secondary" icon={Maximize2} aria-label="Fit map" onClick={() => setView(home)} />
      </div>
      {pickMode && (
        <div className="pointer-events-none absolute inset-x-0 top-2 flex justify-center">
          <span className="inline-flex items-center gap-1.5 rounded-md bg-accent px-2 py-1 text-xs font-medium text-accent-fg shadow-card">
            <Crosshair className="h-3.5 w-3.5" aria-hidden />
            Click the map to place the node
          </span>
        </div>
      )}
    </div>
  )
}
