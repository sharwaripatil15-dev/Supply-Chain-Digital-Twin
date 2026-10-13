import { useEffect, useMemo, useRef, useState } from 'react'
import CytoscapeComponent from 'react-cytoscapejs'
import { useStore } from '../store.js'
import { useTokens } from '../theme.jsx'
import { BOTTLENECK, KIND, STATUS, fmtNum, fmtPct } from '../format.js'
import { nodePosition, prefersReducedMotion } from '../lib/disruption.js'

const SCALE_X = 95 // px per degree of longitude (India is taller than wide, so stretch x)
const SCALE_Y = 60

function buildElements(network, { statuses, utilization, disrupted, highlight, tokens }) {
  const nodes = network.nodes.map((n) => {
    const [lon, lat] = nodePosition(n)
    const status = statuses?.[n.id]
    const classes = [
      highlight?.includes(n.id) && 'highlight',
      (utilization?.[n.id] ?? 0) > BOTTLENECK.threshold && 'bottleneck',
      disrupted?.nodes.has(n.id) && 'down',
    ].filter(Boolean)
    return {
      data: {
        id: n.id,
        label: n.id,
        color: tokens.color[status ? STATUS[status].token : KIND[n.kind].token],
        shape: KIND[n.kind].shape,
        ring: 1.5 + (n.risk || 0) * 5,
      },
      position: { x: lon * SCALE_X, y: -lat * SCALE_Y },
      classes: classes.join(' '),
    }
  })
  const edges = network.edges.map((e) => {
    const id = `${e.source}->${e.target}`
    return { data: { id, source: e.source, target: e.target, capacity: e.capacity }, classes: disrupted?.edges.has(id) ? 'disrupted' : '' }
  })
  return [...nodes, ...edges]
}

function stylesheet(t) {
  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        shape: 'data(shape)',
        width: 22,
        height: 22,
        label: 'data(label)',
        'font-family': 'Inter Variable, system-ui, sans-serif',
        'font-size': 10,
        'font-weight': 500,
        color: t.color.fg2,
        'text-valign': 'bottom',
        'text-margin-y': 5,
        'text-outline-color': t.color.surface,
        'text-outline-width': 2,
        'border-width': 'data(ring)',
        'border-color': t.alpha('accent', 0.35),
        'transition-property': 'background-color, border-color',
        'transition-duration': '200ms',
      },
    },
    { selector: 'node.down', style: { width: 26, height: 26 } },
    {
      selector: 'node.bottleneck',
      style: { 'underlay-color': t.color.warn, 'underlay-opacity': 0.22, 'underlay-padding': 7, 'underlay-shape': 'ellipse' },
    },
    {
      selector: 'node.highlight',
      style: { 'underlay-color': t.color.accent, 'underlay-opacity': 0.2, 'underlay-padding': 10, 'underlay-shape': 'ellipse' },
    },
    { selector: 'node:selected', style: { 'border-color': t.color.accent, 'border-width': 3 } },
    { selector: 'node:active', style: { 'overlay-opacity': 0 } },
    {
      selector: 'edge',
      style: {
        width: 'mapData(capacity, 100, 600, 0.75, 3)',
        'line-color': t.color.borderStrong,
        'target-arrow-color': t.color.borderStrong,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.55,
        'curve-style': 'unbundled-bezier',
        'control-point-distances': 18,
        'control-point-weights': 0.5,
        opacity: 0.9,
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

/** 2D Cytoscape network. Click a node to open the details drawer; hover for a quick tooltip. */
export default function NetworkGraph({ network: override, statuses = null, utilization = null, disrupted = null, highlight = null }) {
  const store = useStore()
  const tokens = useTokens()
  const network = override || store.network
  const { selectNode, sim, day } = store
  const cyRef = useRef(null)
  const [hover, setHover] = useState(null)

  const elements = useMemo(
    () => (network ? buildElements(network, { statuses, utilization, disrupted, highlight, tokens }) : []),
    [network, statuses, utilization, disrupted, highlight, tokens],
  )
  const styles = useMemo(() => stylesheet(tokens), [tokens])
  const layout = useMemo(() => ({ name: 'preset', fit: true, padding: 36 }), [])

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

  return (
    <div className="relative h-full w-full">
      {network && (
        <CytoscapeComponent
          elements={elements}
          stylesheet={styles}
          layout={layout}
          className="h-full w-full"
          cy={(cy) => {
            if (cyRef.current !== cy) {
              cyRef.current = cy
              if (import.meta.env.DEV) window.__aegisCy = cy // test/debug hook, dev builds only
            }
          }}
          minZoom={0.3}
          maxZoom={3}
          wheelSensitivity={0.2}
          boxSelectionEnabled={false}
        />
      )}
      {node && (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-10 w-52 -translate-x-1/2 -translate-y-full animate-fade-in rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-card"
          style={{ left: hover.x, top: hover.y - 16 }}
        >
          <div className="font-semibold text-fg">
            {node.id} · {node.name || node.city}
          </div>
          <div className="text-fg-muted">
            {KIND[node.kind].label} · {node.city}
            {status && ` · ${STATUS[status].label}`}
          </div>
          <div className="mt-1.5 grid grid-cols-3 gap-1 text-fg-2">
            <span>
              Stock <b className="tabular text-fg">{fmtNum(node.stock)}</b>
            </span>
            <span>
              Util <b className="tabular text-fg">{node.kind === 'customer' ? '-' : fmtPct(util)}</b>
            </span>
            <span>
              Crit <b className="tabular text-fg">{fmtPct(node.risk)}</b>
            </span>
          </div>
          {sim && statuses && <div className="mt-1 text-fg-muted">Day {day}</div>}
        </div>
      )}
    </div>
  )
}
