/**
 * Builder form logic: blank drafts, validation (same bounds as the backend's Pydantic models) and payload cleanup.
 * Pure JS so `node --test` can exercise it without a browser.
 */
import { ALL_TYPE_KEYS, NODE_TYPES, allowedTargets, edgeAllowed, fieldsFor, haversineKm, isDemand, typeOf } from './nodeTypes.js'

export const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,23}$/

/** Smallest unused `${prefix}<n>` above every existing one (matches the backend's id generator). */
export function nextId(prefix, taken) {
  let max = 0
  for (const id of taken) {
    const m = new RegExp(`^${prefix}(\\d+)$`).exec(String(id))
    if (m) max = Math.max(max, Number(m[1]))
  }
  return `${prefix}${max + 1}`
}

/** A blank node of `kind` with sensible defaults (lat/lon empty until a location is chosen). */
export function blankNode(kind) {
  const base = { name: '', kind, city: '', lat: '', lon: '', capacity: '', stock: '', reliability: 0.95, op_cost: '', status: 'active' }
  if (kind === 'supplier') base.is_backup = false
  if (isDemand(kind)) base.daily_demand = ''
  if (kind === 'customer') base.priority = 'medium'
  return base
}

const num = (v) => (v === '' || v == null ? null : Number(v))

/**
 * Validate a node draft. Returns { field: message }; empty object = valid.
 * `taken` = ids already in use (only checked when `isNew`).
 */
export function validateNode(draft, { taken = [], isNew = true } = {}) {
  const errors = {}
  if (!draft || !NODE_TYPES[draft.kind]) return { kind: 'Choose a node type' }
  if (isNew && draft.id) {
    if (!ID_PATTERN.test(draft.id)) errors.id = 'Letters, digits, - and _ only (max 24)'
    else if (taken.includes(draft.id)) errors.id = `${draft.id} is already used`
  }
  if (!String(draft.name ?? '').trim()) errors.name = 'Name is required'
  else if (String(draft.name).length > 80) errors.name = 'At most 80 characters'
  const lat = num(draft.lat)
  const lon = num(draft.lon)
  if (lat == null || Number.isNaN(lat)) errors.lat = 'Pick a city, type a latitude or click the map'
  else if (lat < -90 || lat > 90) errors.lat = 'Latitude must be between -90 and 90'
  if (lon == null || Number.isNaN(lon)) errors.lon = 'Longitude is required'
  else if (lon < -180 || lon > 180) errors.lon = 'Longitude must be between -180 and 180'
  const { common, specific } = fieldsFor(draft.kind)
  for (const f of [...common, ...specific]) {
    if (f.type !== 'number' || ['lat', 'lon'].includes(f.key)) continue
    const v = num(draft[f.key])
    if (v == null) {
      if (f.required) errors[f.key] = `${f.label} is required`
      continue
    }
    if (Number.isNaN(v)) errors[f.key] = 'Must be a number'
    else if (f.min != null && v < f.min) errors[f.key] = f.min === 0 ? 'Cannot be negative' : `At least ${f.min}`
    else if (f.max != null && v > f.max) errors[f.key] = `At most ${f.max}`
    else if (f.integer && !Number.isInteger(v)) errors[f.key] = 'Whole number'
  }
  return errors
}

/** Draft -> API payload: numbers parsed, empty optional values dropped, fields of other kinds removed. */
export function nodePayload(draft) {
  const { common, specific } = fieldsFor(draft.kind)
  const out = { kind: draft.kind, name: String(draft.name ?? '').trim(), city: String(draft.city ?? '').trim(),
    lat: Number(draft.lat), lon: Number(draft.lon), status: draft.status === 'inactive' ? 'inactive' : 'active' }
  if (draft.id) out.id = draft.id
  for (const f of [...common, ...specific]) {
    if (['name', 'city'].includes(f.key)) continue
    const v = draft[f.key]
    if (f.type === 'checkbox') out[f.key] = Boolean(v)
    else if (f.type === 'number') {
      if (v !== '' && v != null) out[f.key] = Number(v)
    } else if (v !== '' && v != null) out[f.key] = v
  }
  for (const k of ALL_TYPE_KEYS) if (!specific.some((f) => f.key === k)) delete out[k]
  return out
}

/** API node -> editable draft (nulls become empty inputs). */
export function nodeDraft(node) {
  const d = { ...blankNode(node.kind) }
  for (const [k, v] of Object.entries(node)) d[k] = v == null ? '' : v
  return d
}

/** Copy of a node for "Duplicate": new name, no id (the server assigns one), nudged so it does not overlap. */
export function duplicateNode(node) {
  const { id: _id, ...rest } = node
  return { ...rest, name: `${node.name} (copy)`.slice(0, 80), lat: Number(node.lat) + 0.15, lon: Number(node.lon) + 0.15 }
}

/** Validate a lane draft against the current nodes and lanes. */
export function validateEdge(draft, nodes, edges = []) {
  const errors = {}
  const byId = Object.fromEntries((nodes || []).map((n) => [n.id, n]))
  const src = byId[draft.source]
  const dst = byId[draft.target]
  if (!src) errors.source = 'Choose a source node'
  if (!dst) errors.target = 'Choose a target node'
  if (src && dst) {
    if (src.id === dst.id) errors.target = 'A lane needs two different nodes'
    else if (!edgeAllowed(src.kind, dst.kind)) errors.target = `A ${typeOf(src.kind).label.toLowerCase()} cannot ship to a ${typeOf(dst.kind).label.toLowerCase()}`
    else if (edges.some((e) => e.id !== draft.id && e.source === src.id && e.target === dst.id)) errors.target = 'This lane already exists'
  }
  const cap = num(draft.capacity)
  if (cap == null || Number.isNaN(cap)) errors.capacity = 'Capacity is required'
  else if (cap < 0) errors.capacity = 'Cannot be negative'
  for (const k of ['distance_km', 'lead', 'cost', 'co2']) {
    const v = num(draft[k])
    if (v != null && (Number.isNaN(v) || v < 0)) errors[k] = 'Must be 0 or more'
  }
  return errors
}

/** Lane payload: empty distance/lead/cost/co2 are left out so the server fills its suggestion. */
export function edgePayload(draft) {
  const out = { source: draft.source, target: draft.target, mode: draft.mode || 'road', capacity: Number(draft.capacity),
    status: draft.status === 'inactive' ? 'inactive' : 'active' }
  for (const k of ['distance_km', 'lead', 'cost', 'co2']) if (draft[k] !== '' && draft[k] != null) out[k] = Number(draft[k])
  return out
}

/** Nodes a lane from `sourceId` may point to (legal tier direction, not itself). */
export function legalTargets(sourceId, nodes) {
  const src = nodes.find((n) => n.id === sourceId)
  if (!src) return []
  const kinds = allowedTargets(src.kind)
  return nodes.filter((n) => n.id !== src.id && kinds.includes(n.kind))
}

export function distanceBetween(a, b) {
  if (!a || !b) return null
  return Math.round(haversineKm([Number(a.lat), Number(a.lon)], [Number(b.lat), Number(b.lon)]) * 10) / 10
}
