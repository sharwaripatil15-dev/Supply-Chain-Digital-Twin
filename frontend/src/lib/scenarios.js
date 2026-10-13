/** Quick-start scenarios that always target nodes of the active network. */
import { isDemand } from './nodeTypes.js'

const edgeKey = (e) => `${e.source}->${e.target}`

/** True if every event's target exists in `network` (demand events must hit a demand node). */
export function eventsFit(network, events) {
  if (!network || !events?.length) return false
  const kind = Object.fromEntries((network.nodes || []).map((n) => [n.id, n.kind]))
  const lanes = new Set((network.edges || []).map(edgeKey))
  return events.every((e) => {
    const isEdge = e.type === 'edge' || e.type === 'route_block'
    const isDem = e.type === 'demand' || e.type === 'demand_surge'
    return isEdge ? lanes.has(e.target) : isDem ? isDemand(kind[e.target]) : e.target in kind
  })
}

/**
 * The preset's curated demos (only on the preset: another network may reuse an id like S2 for a different site);
 * otherwise scenarios generated from the network: the biggest primary supplier failing, the busiest lane blocked,
 * and a demand spike at the largest demand node.
 */
export function scenariosFor(network, demos, isPreset = true) {
  const fitting = isPreset ? (demos || []).filter((d) => eventsFit(network, d.events)) : []
  if (fitting.length) return fitting
  const nodes = network?.nodes || []
  const out = []
  const suppliers = nodes.filter((n) => n.kind === 'supplier' && !n.backup).sort((a, b) => (b.capacity || 0) - (a.capacity || 0))
  if (suppliers[0]) {
    const s = suppliers[0]
    out.push({ id: 'gen-supplier', label: 'Supplier failure', blurb: `${s.name || s.id} (${s.id}) goes dark for 10 days.`,
      events: [{ type: 'node', target: s.id, start: 2, duration: 10, severity: 1 }] })
  }
  const lane = [...(network?.edges || [])].sort((a, b) => (b.capacity || 0) - (a.capacity || 0))[0]
  if (lane) {
    out.push({ id: 'gen-lane', label: 'Lane blocked', blurb: `${lane.source} → ${lane.target} is closed for 7 days.`,
      events: [{ type: 'edge', target: edgeKey(lane), start: 3, duration: 7, severity: 1 }] })
  }
  const sink = nodes.filter((n) => isDemand(n.kind)).sort((a, b) => (b.demand || 0) - (a.demand || 0))[0]
  if (sink) {
    out.push({ id: 'gen-demand', label: 'Demand spike', blurb: `${sink.name || sink.id} (${sink.id}) demand +50% for 6 days.`,
      events: [{ type: 'demand', target: sink.id, start: 4, duration: 6, severity: 0.5 }] })
  }
  return out
}

/**
 * Events for a newly loaded network: keep the current ones when the network is unchanged in kind and they still fit,
 * else the first scenario for the network (or none).
 */
export function eventsForNetwork(network, events, demos, isPreset = true, keep = true) {
  if (keep && eventsFit(network, events)) return events
  return scenariosFor(network, demos, isPreset)[0]?.events || []
}
