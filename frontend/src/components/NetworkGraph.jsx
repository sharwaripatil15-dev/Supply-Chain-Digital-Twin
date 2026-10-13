import { useEffect, useMemo, useRef, useState } from 'react'
import CytoscapeComponent from 'react-cytoscapejs'
import { useStore } from '../store.js'
import { useTheme } from '../theme.jsx'
import { BOTTLENECK, STATUS, fmtNum, fmtPct } from '../format.js'
import { NODE_KINDS, STATUS_COLORS, glyphDataUri, isDemand, typeOf } from '../lib/nodeTypes.js'
import { nodePosition, prefersReducedMotion } from '../lib/disruption.js'
import { TypeIcon } from './NodeTypeIcon.jsx'

const SCALE_X = 95 // px per degree of longitude (India is taller than wide, so stretch x)
const SCALE_Y = 60
const TIER_GAP_X = 190
const ROW_GAP_Y = 70
const SIZE = { supplier: 30, factory: 28, warehouse: 30, retailer: 27, customer: 23 }
const BADGE = { stressed: ' ⚠', down: ' ✕' }
const ICONS = Object.fromEntries(NODE_KINDS.map((k) => [k, glyphDataUri(k)]))

const short = (s, n = 18) => (s && s.length > n ? `${s.slice(0, n - 1)}…` : s || '')

/** Layered layout: one column per tier (suppliers -> customers), north-to-south order within a column. */
function tierPositions(nodes) {
  const cols = {}
  for (const n of nodes) (cols[typeOf(n.kind).tier] ||= []).push(n)
  const out = {}
  for (const [tier, list] of Object.entries(cols)) {
    list.sort((a, b) => b.lat - a.lat || String(a.id).localeCompare(String(b.id)))
    list.forEach((n, i) => {
      out[n.id] = { x: Number(tier) * TIER_GAP_X, y: (i - (list.length - 1) / 2) * ROW_GAP_Y }
    })
  }
  return out
}

function buildElements(network, { statuses, utilization, disrupted, highlight, hiddenKinds, layout, dark }) {
  const visible = network.nodes.filter((n) => !hiddenKinds?.has(n.kind))
  const ids = new Set(visible.map((n) => n.id))
  const tiers = layout === 'tiers' ? tierPositions(visible) : null
  const maxCap = Math.max(1, ...network.edges.map((e) => e.capacity || 0))
  const nodes = visible.map((n) => {
    const t = typeOf(n.kind)
    const status = statuses?.[n.id] ?? (disrupted?.nodes.has(n.id) ? 'down' : null)
    const [lon, lat] = nodePosition(n)
    const risk = Math.max(0, Math.min(1, n.risk ?? 0))
    const classes = [
      status && `status-${status}`,
      highlight?.includes(n.id) && 'highlight',
      (utilization?.[n.id] ?? 0) > BOTTLENECK.threshold && 'bottleneck',
    ].filter(Boolean)
    return {
      data: {
        id: n.id,
        label: `${n.id}${status ? BADGE[status] || '' : ''}\n${short(n.name)}`,
        color: t.color,
        shape: t.shape2d,
        icon: ICONS[n.kind] || glyphDataUri(n.kind),
        size: SIZE[n.kind] || 24,
        iconY: n.kind === 'supplier' ? '64%' : '50%',
        outline: dark && t.outlineDark ? t.outlineDark : dark ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.95)',
        glowOpacity: 0.05 + risk * 0.22,
        glowPad: 3 + risk * 10,
      },
      position: tiers ? tiers[n.id] : { x: lon * SCALE_X, y: -lat * SCALE_Y },
      classes: classes.join(' '),
    }
  })
  const kindOf = Object.fromEntries(network.nodes.map((n) => [n.id, n.kind]))
  const edges = network.edges
    .filter((e) => ids.has(e.source) && ids.has(e.target))
    .map((e) => {
      const id = `${e.source}->${e.target}`
      return {
        data: { id, source: e.source, target: e.target, color: typeOf(kindOf[e.source]).color, w: 0.8 + ((e.capacity || 0) / maxCap) * 2.4 },
        classes: disrupted?.edges.has(id) ? 'disrupted' : '',
      }
    })
  return [...nodes, ...edges]
}

function stylesheet(t) {
  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        'background-image': 'data(icon)',
        'background-width': '56%',
        'background-height': '56%',
        'background-position-y': 'data(iconY)',
        'background-clip': 'none',
        'background-image-containment': 'over',
        shape: 'data(shape)',
        width: 'data(size)',
        height: 'data(size)',
        label: 'data(label)',
        'text-wrap': 'wrap',
        'text-max-width': 110,
        'font-family': 'Inter Variable, system-ui, sans-serif',
        'font-size': 9,
        'font-weight': 500,
        'line-height': 1.25,
        color: t.color.fg2,
        'text-valign': 'bottom',
        'text-margin-y': 5,
        'text-outline-color': t.color.surface,
        'text-outline-width': 2,
        'border-width': 1.5,
        'border-color': 'data(outline)',
        'underlay-color': t.color.accent,
        'underlay-opacity': 'data(glowOpacity)',
        'underlay-padding': 'data(glowPad)',
        'underlay-shape': 'ellipse',
        'transition-property': 'border-color, border-width, underlay-opacity',
        'transition-duration': '200ms',
      },
    },
    // status = ring + glow (never the fill)
    { selector: 'node.status-ok', style: { 'border-color': STATUS_COLORS.ok.color, 'border-width': 3 } },
    {
      selector: 'node.status-stressed',
      style: { 'border-color': STATUS_COLORS.stressed.color, 'border-width': 3.5, 'underlay-color': STATUS_COLORS.stressed.color, 'underlay-opacity': 0.22, 'underlay-padding': 7 },
    },
    {
      selector: 'node.status-down',
      style: {
        'border-color': STATUS_COLORS.down.color, 'border-width': 4, 'underlay-color': STATUS_COLORS.down.color, 'underlay-opacity': 0.3,
        'underlay-padding': 9, 'font-weight': 700, color: STATUS_COLORS.down.color,
      },
    },
    {
      selector: 'node.bottleneck',
      style: { 'underlay-color': t.color.warn, 'underlay-opacity': 0.26, 'underlay-padding': 9 },
    },
    {
      selector: 'node.highlight',
      style: { 'underlay-color': t.color.accent, 'underlay-opacity': 0.28, 'underlay-padding': 12 },
    },
    {
      selector: 'node:selected',
      style: { 'overlay-color': t.color.accent, 'overlay-opacity': 0.18, 'overlay-padding': 7, 'overlay-shape': 'ellipse' },
    },
    { selector: 'node:active', style: { 'overlay-opacity': 0 } },
    {
      selector: 'edge',
      style: {
        width: 'data(w)',
        'line-color': 'data(color)',
        'target-arrow-color': 'data(color)',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.6,
        'curve-style': 'unbundled-bezier',
        'control-point-distances': 18,
        'control-point-weights': 0.5,
        opacity: 0.42,
        'transition-property': 'line-color, opacity',
        'transition-duration': '200ms',
      },
    },
    {
      selector: 'edge.disrupted',
      style: {
        'line-color': t.color.bad,
        'target-arrow-color': t.color.bad,
        'line-style': 'dashed',
        'line-dash-pattern': [6, 4],
        opacity: 1,
      },
    },
  ]
}

/**
 * 2D Cytoscape network. Click a node to open the details drawer; hover for a quick tooltip.
 * hiddenKinds: Set of node kinds to hide (legend filter). layout: 'geo' (lat/lon) | 'tiers' (layered by tier).
 */
export default function NetworkGraph({
  network: override, statuses = null, utilization = null, disrupted = null, highlight = null, hiddenKinds = null, layout = 'geo',
}) {
  const store = useStore()
  const { tokens, theme } = useTheme()
  const network = override || store.network
  const { selectNode, selectedNode, sim, day } = store
  const cyRef = useRef(null)
  const [hover, setHover] = useState(null)

  const elements = useMemo(
    () => (network ? buildElements(network, { statuses, utilization, disrupted, highlight, hiddenKinds, layout, dark: theme === 'dark' }) : []),
    [network, statuses, utilization, disrupted, highlight, hiddenKinds, layout, theme],
  )
  const styles = useMemo(() => stylesheet(tokens), [tokens])
  const cyLayout = useMemo(() => ({ name: 'preset', fit: true, padding: 36 }), [])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    const onTap = (e) => selectNode(e.target.id())
    const onBg = (e) => e.target === cy && selectNode(null)
    const onOver = (e) => {
      const p = e.target.renderedPosition()
      setHover({ id: e.target.id(), x: p.x, y: p.y })
    }
    const onOut = () => setHover(null)
    cy.on('tap', 'node', onTap)
    cy.on('tap', onBg)
    cy.on('mouseover', 'node', onOver)
    cy.on('mouseout', 'node', onOut)
    cy.on('viewport', onOut)
    return () => {
      cy.off('tap', 'node', onTap)
      cy.off('tap', onBg)
      cy.off('mouseover', 'node', onOver)
      cy.off('mouseout', 'node', onOut)
      cy.off('viewport', onOut)
    }
  }, [selectNode, network])

  // Keep Cytoscape's selection in step with the store (selection can come from tables, the 3D view or the drawer).
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.nodes(':selected').forEach((n) => {
      if (n.id() !== selectedNode) n.unselect()
    })
    if (selectedNode) cy.$id(selectedNode).select()
  }, [selectedNode, elements])

  // Re-frame when the layout or the set of visible nodes changes.
  const frameKey = `${layout}|${elements.filter((e) => e.position).length}|${network?.nodes?.length ?? 0}`
  useEffect(() => {
    const cy = cyRef.current
    if (cy && cy.nodes().length) cy.fit(undefined, 36)
  }, [frameKey])

  // Marching dashes on disrupted lanes.
  useEffect(() => {
    const cy = cyRef.current
    if (!cy || prefersReducedMotion() || !disrupted?.edges.size) return
    let offset = 0
    const id = setInterval(() => {
      offset = (offset - 1) % 100
      cy.edges('.disrupted').style('line-dash-offset', offset)
    }, 50)
    return () => clearInterval(id)
  }, [disrupted, elements])

  const node = hover && network?.nodes.find((n) => n.id === hover.id)
  const status = statuses?.[hover?.id]
  const util = utilization?.[hover?.id] ?? node?.utilization
  const leafDemand = node && isDemand(node.kind) && !node.capacity

  return (
    <div className="relative h-full w-full">
      {network && (
        <CytoscapeComponent
          elements={elements}
          stylesheet={styles}
          layout={cyLayout}
          className="h-full w-full"
          cy={(cy) => {
            if (cyRef.current !== cy) {
              cyRef.current = cy
              if (import.meta.env.DEV) window.__aegisCy = cy // test/debug hook, dev builds only
            }
          }}
          minZoom={0.3}
          maxZoom={3}
          boxSelectionEnabled={false}
        />
      )}
      {network && network.nodes.length === 0 && (
        <p className="absolute inset-0 flex items-center justify-center text-sm text-fg-muted">This network has no nodes yet.</p>
      )}
      {node && (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-10 w-56 -translate-x-1/2 -translate-y-full animate-fade-in rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-card"
          style={{ left: hover.x, top: hover.y - 18 }}
        >
          <div className="flex items-center gap-1.5 font-semibold text-fg">
            <TypeIcon kind={node.kind} size="xs" />
            <span className="truncate">
              {node.id} · {node.name || node.city}
            </span>
          </div>
          <div className="mt-0.5 text-fg-muted">
            {typeOf(node.kind).label}
            {node.city && ` · ${node.city}`}
            {status && (
              <span className="font-medium" style={{ color: STATUS_COLORS[status].color }}>
                {' '}
                · {STATUS[status].label}
              </span>
            )}
          </div>
          <div className="mt-1.5 grid grid-cols-3 gap-1 text-fg-2">
            <span>
              Stock <b className="tabular text-fg">{fmtNum(node.stock)}</b>
            </span>
            <span>
              Util <b className="tabular text-fg">{leafDemand ? '-' : fmtPct(util)}</b>
            </span>
            <span>
              Crit <b className="tabular text-fg">{node.risk == null ? 'n/a' : fmtPct(node.risk)}</b>
            </span>
          </div>
          {sim && statuses && <div className="mt-1 text-fg-muted">Day {day}</div>}
        </div>
      )}
    </div>
  )
}
