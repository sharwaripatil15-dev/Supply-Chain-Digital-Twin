/** Pure helpers for the weather layer (presentation only, no API calls). */

export const LEVELS = ['low', 'moderate', 'high', 'severe']
export const LEVEL_RANK = { low: 0, moderate: 1, high: 2, severe: 3 }
export const LEVEL_LABEL = { low: 'Low', moderate: 'Moderate', high: 'High', severe: 'Severe', closed: 'Closed' }
/** Status-dot tone per level (tokens: neutral -> amber -> red). */
export const LEVEL_TONE = { low: 'neutral', moderate: 'warn', high: 'warn', severe: 'bad', closed: 'bad' }

/** Hazard overlay colors: fixed categorical data colors (like the tier colors), readable on both themes. */
export const HAZARD_STYLE = {
  rain: { label: 'Heavy rain', rgb: [59, 130, 246] },
  flood: { label: 'Flood zone', rgb: [13, 148, 136] },
  fog: { label: 'Dense fog', rgb: [148, 163, 184] },
  wind: { label: 'Strong wind', rgb: [139, 92, 246] },
  cyclone: { label: 'Cyclone', rgb: [139, 92, 246] },
  heat: { label: 'Heat', rgb: [234, 88, 12] },
  wave: { label: 'High waves', rgb: [6, 182, 212] },
  quake: { label: 'Earthquake', rgb: [225, 29, 72] },
}
export const hazardStyle = (type) => HAZARD_STYLE[type] || HAZARD_STYLE.rain

export const QUALITY = {
  live: { label: 'Live', tone: 'ok', note: 'Live forecast' },
  cached: { label: 'Cached', tone: 'warn', note: 'Last good forecast (providers unreachable)' },
  simulated: { label: 'Simulated', tone: 'accent', note: 'Built-in hazard scenario, not a forecast' },
  unavailable: { label: 'Unavailable', tone: 'bad', note: 'No forecast available' },
}

/** A day row's display level: "closed" overrides the risk level. */
export const rowLevel = (row) => (!row ? 'low' : row.closed ? 'closed' : row.level)

/** Lane / site rows for one day: { edges: Map(id -> row), nodes: Map(id -> row) }. */
export function rowsForDay(risk, day) {
  const edges = new Map()
  const nodes = new Map()
  if (!risk) return { edges, nodes }
  const d = Math.max(0, Math.min(day, (risk.horizon || 1) - 1))
  for (const e of risk.edges || []) if (e.daily?.[d]) edges.set(e.id, e.daily[d])
  for (const n of risk.nodes || []) if (n.daily?.[d]) nodes.set(n.id, n.daily[d])
  return { edges, nodes }
}

/** Hazard features as they stand on `day`: [{ ...feature, at: { lat, lon, radius_km, intensity, value } }]. */
export function featuresForDay(hazards, day) {
  if (!hazards?.features) return []
  const out = []
  for (const f of hazards.features) {
    const at = f.daily?.[Math.max(0, Math.min(day, f.daily.length - 1))]
    if (!at || at.lat == null || !(at.intensity > 0)) continue
    out.push({ ...f, at })
  }
  return out
}

/** Cyclone tracks: [{ id, path: [[lon, lat], ...] }] from every day the storm has a centre. */
export function cycloneTracks(hazards) {
  return (hazards?.features || [])
    .filter((f) => f.type === 'cyclone')
    .map((f) => ({ id: f.id, path: f.daily.filter((d) => d.lat != null && d.radius_km > 0).map((d) => [d.lon, d.lat]) }))
    .filter((t) => t.path.length > 1)
}

/** Weather events in a scenario. */
export const weatherEvents = (events) => (events || []).filter((e) => e.source === 'weather')
export const userEvents = (events) => (events || []).filter((e) => e.source !== 'weather')

/** Events as the API takes them (drop nulls so older servers never see unknown nulls). */
export const cleanEvent = (e) => Object.fromEntries(Object.entries(e).filter(([, v]) => v != null))

/** Apply a /weather/reroute scenario_patch to a scenario's events. */
export function applyPatch(events, patch) {
  if (!patch) return events
  const [w0, w1] = patch.window || [0, 9999]
  const kept = events.filter(
    (e) => !(e.source === 'weather' && (patch.remove_targets || []).includes(e.target) && e.start <= w1 && e.start + e.duration - 1 >= w0),
  )
  return [...kept, ...(patch.add || []).map(cleanEvent)]
}

const fmtDay = (iso) => {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00`)
  return d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
}
export { fmtDay }

/** The one-line summary shown above the canvas. */
export function summaryLine(risk, reroute) {
  if (!risk) return null
  const s = risk.summary
  const highIds = new Set(s.high_risk_edge_ids)
  const firstDays = (risk.edges || []).filter((e) => highIds.has(e.id)).map((e) => e.daily.findIndex((r) => r.level === 'high' || r.level === 'severe' || r.closed))
  const within = firstDays.length ? Math.max(...firstDays) + 1 : risk.horizon
  if (!s.high_risk_edges && !s.affected_nodes) return `No routes at high weather risk in the next ${risk.horizon} days.`
  let line = `${s.high_risk_edges} route${s.high_risk_edges === 1 ? '' : 's'} at high risk in the next ${Math.min(within, risk.horizon)} days`
  if (s.closed_edges) line += `; ${s.closed_edges} closed`
  if (s.affected_nodes) line += `; ${s.affected_nodes} site${s.affected_nodes === 1 ? '' : 's'} hit`
  if (reroute?.summary?.headline) {
    line += `; recommended: ${reroute.summary.headline}`
    if (reroute.summary.delay_saved_days > 0) line += `, saves ~${reroute.summary.delay_saved_days} days of delay`
  }
  return `${line}.`
}

/** Edge ids along a node path (["S1","F1","W3"] -> ["S1->F1","F1->W3"]). */
export const pathEdges = (path) => (path || []).slice(1).map((n, i) => `${path[i]}->${n}`)
