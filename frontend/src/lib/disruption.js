/** Pure helpers shared by the 2D and 3D network views (presentation only, no API calls). */

const active = (e, day) => day >= e.start && day < e.start + e.duration

/**
 * What is visibly disrupted on `day`: lanes hit by active edge events, lanes touching a down node,
 * and nodes that are down per the simulation timeline (or per active node events when there is no timeline).
 */
export function disruptionForDay(network, events, day, statuses) {
  const nodes = new Set()
  const edges = new Set()
  if (statuses) {
    for (const [id, s] of Object.entries(statuses)) if (s === 'down') nodes.add(id)
  } else {
    for (const e of events) if (e.type === 'node' && e.severity >= 1 && active(e, day)) nodes.add(e.target)
  }
  for (const e of events) if (e.type === 'edge' && active(e, day)) edges.add(e.target)
  for (const ed of network?.edges ?? []) {
    if (nodes.has(ed.source) || nodes.has(ed.target)) edges.add(`${ed.source}->${ed.target}`)
  }
  return { nodes, edges }
}

/** Every event at full effect (used for "after" views without a timeline). */
export function peakDisruption(network, events) {
  const nodes = new Set(events.filter((e) => e.type === 'node' && e.severity >= 1).map((e) => e.target))
  const edges = new Set(events.filter((e) => e.type === 'edge').map((e) => e.target))
  for (const ed of network?.edges ?? []) {
    if (nodes.has(ed.source) || nodes.has(ed.target)) edges.add(`${ed.source}->${ed.target}`)
  }
  return { nodes, edges }
}

/** Lanes on the recovery plan: alternate route paths and pre-positioning moves from /recover. */
export function recoveryLanes(recover) {
  const lanes = new Set()
  for (const r of recover?.alternate_routes ?? []) {
    for (let i = 0; i < r.via.length - 1; i++) lanes.add(`${r.via[i]}->${r.via[i + 1]}`)
  }
  return lanes
}

/** Expand chaos targets ("S2", "F1->W3") into the node ids they touch. */
export const targetNodes = (targets) => targets.flatMap((t) => t.split('->'))

/** Small per-tier offsets (degrees) so co-located sites (e.g. Bengaluru factory + customer) don't overlap. */
export const TIER_OFFSET = {
  supplier: [-0.35, 0.28],
  factory: [-0.12, 0.1],
  warehouse: [0.12, -0.1],
  customer: [0.35, -0.28],
}

export function nodePosition(n) {
  const [dx, dy] = TIER_OFFSET[n.kind] || [0, 0]
  return [n.lon + dx, n.lat + dy]
}

let webglSupport
export function hasWebGL() {
  if (webglSupport !== undefined) return webglSupport
  try {
    const canvas = document.createElement('canvas')
    webglSupport = Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    webglSupport = false
  }
  return webglSupport
}

export const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
