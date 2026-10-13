/**
 * Node types: the single definition used by the 2D graph (Cytoscape), the 3D map (deck.gl), legends, tables and
 * the builder forms. Mirror of backend/node_types.py; keep the two in step.
 *
 * Encoding rule: a node's TYPE is shape + fill color + glyph; its STATUS (ok / stressed / down) is a ring, glow and
 * badge in the status colors, never the fill. The type palette avoids red/amber/green so it never reads as a status.
 * Pure JS (no React, no Vite-only APIs) so it can be unit-tested with `node --test`.
 */

export const NODE_KINDS = ['supplier', 'factory', 'warehouse', 'retailer', 'customer']
export const DEMAND_KINDS = new Set(['retailer', 'customer'])

/** True for demand sinks (retailers and customers). */
export const isDemand = (kind) => DEMAND_KINDS.has(kind)

const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))

// 24x24 stroke glyphs (white on the type color). Each entry: [tag, attributes].
const GLYPHS = {
  supplier: [
    ['path', { d: 'M3 6h11v10H3z' }],
    ['path', { d: 'M14 9h4l3 3.5V16h-7' }],
    ['circle', { cx: 7, cy: 17.5, r: 2 }],
    ['circle', { cx: 17, cy: 17.5, r: 2 }],
  ],
  factory: [
    ['path', { d: 'M3 21V10l5 3V10l5 3V10l5 3V4h3v17z' }],
    ['path', { d: 'M7 17h2M12 17h2M17 17h1' }],
  ],
  warehouse: [
    ['path', { d: 'M3 21V9l9-5 9 5v12' }],
    ['path', { d: 'M7 21v-8h10v8' }],
    ['path', { d: 'M7 17h10' }],
  ],
  retailer: [
    ['path', { d: 'M4 10v11h16V10' }],
    ['path', { d: 'M3 10l2-6h14l2 6c0 1.4-1.2 2.4-2.6 2.4S16 11.4 16 10c0 1.4-1.2 2.4-2.6 2.4S11 11.4 11 10c0 1.4-1.2 2.4-2.6 2.4S5.8 11.4 5.8 10' }],
    ['path', { d: 'M10 21v-5h4v5' }],
  ],
  customer: [
    ['circle', { cx: 12, cy: 8, r: 4 }],
    ['path', { d: 'M4.5 21a7.5 7.5 0 0 1 15 0' }],
  ],
}

/**
 * shape2d: Cytoscape shape. disk/radius/stack: deck.gl ColumnLayer geometry (disk = diskResolution, 3 = triangular
 * prism ... 32 = cylinder; radius in meters; height multiplier). thumb: 2D outline of the 3D footprint for legends.
 */
export const NODE_TYPES = {
  supplier: {
    kind: 'supplier', label: 'Supplier', plural: 'Suppliers', prefix: 'S', tier: 0, color: '#8B5CF6',
    shape2d: 'round-triangle', disk: 3, radius: 15000, height: 1.25, angle: 90,
    blurb: 'Raw materials and components', thumb: 'M12 3 21 20H3z',
  },
  factory: {
    kind: 'factory', label: 'Factory', plural: 'Factories', prefix: 'F', tier: 1, color: '#2563EB',
    shape2d: 'round-rectangle', disk: 4, radius: 30000, height: 1.4, angle: 45, stack: true,
    blurb: 'Turns inputs into finished goods', thumb: 'M4 4h16v16H4z',
  },
  warehouse: {
    kind: 'warehouse', label: 'Warehouse', plural: 'Warehouses', prefix: 'W', tier: 2, color: '#0D9488',
    shape2d: 'round-hexagon', disk: 6, radius: 32000, height: 0.45, angle: 0,
    blurb: 'Stores and ships stock', thumb: 'M7 3.5h10l5 8.5-5 8.5H7l-5-8.5z',
  },
  retailer: {
    kind: 'retailer', label: 'Retailer', plural: 'Retailers', prefix: 'R', tier: 3, color: '#DB2777',
    shape2d: 'round-octagon', disk: 8, radius: 21000, height: 0.8, angle: 22.5,
    blurb: 'Sells to end customers; a demand point', thumb: 'M8.3 3h7.4L21 8.3v7.4L15.7 21H8.3L3 15.7V8.3z',
  },
  customer: {
    kind: 'customer', label: 'Customer', plural: 'Customers', prefix: 'C', tier: 4, color: '#475569', outlineDark: '#CBD5E1',
    shape2d: 'ellipse', disk: 32, radius: 17000, height: 0.6, angle: 0,
    blurb: 'Final demand', thumb: 'M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z',
  },
}
for (const t of Object.values(NODE_TYPES)) {
  t.rgb = hexToRgb(t.color)
  t.demand = DEMAND_KINDS.has(t.kind)
  t.glyph = GLYPHS[t.kind]
}

const FALLBACK = { kind: 'unknown', label: 'Node', plural: 'Nodes', prefix: 'N', tier: 9, color: '#71717A', rgb: [113, 113, 122],
  shape2d: 'ellipse', disk: 12, radius: 15000, height: 0.6, angle: 0, blurb: '', thumb: 'M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18z',
  demand: false, glyph: GLYPHS.customer }

/** Type metadata for any kind; unknown kinds get a neutral fallback instead of crashing a view. */
export const typeOf = (kind) => NODE_TYPES[kind] || FALLBACK

/** Status colors: rings, glows and badges only. */
export const STATUS_COLORS = {
  ok: { label: 'OK', color: '#22C55E', rgb: [34, 197, 94] },
  stressed: { label: 'Stressed', color: '#F59E0B', rgb: [245, 158, 11] },
  down: { label: 'Down', color: '#EF4444', rgb: [239, 68, 68] },
}

// ------------------------------------------------------------------ glyph rendering (SVG strings / data URIs)
const attrs = (o) => Object.entries(o).map(([k, v]) => `${k}="${v}"`).join(' ')

/** Inner SVG markup of a type's glyph (24x24 viewBox). */
export function glyphMarkup(kind, stroke = '#FFFFFF', strokeWidth = 2) {
  return typeOf(kind).glyph
    .map(([tag, a]) => `<${tag} ${attrs(a)} fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round"/>`)
    .join('')
}

/** Standalone SVG: the glyph, optionally on a filled badge (circle) in the type color. */
export function glyphSvg(kind, { stroke = '#FFFFFF', badge = false, size = 64, outline = null } = {}) {
  const t = typeOf(kind)
  const bg = badge
    ? `<circle cx="12" cy="12" r="11.2" fill="${t.color}"${outline ? ` stroke="${outline}" stroke-width="0.8"` : ''}/>`
    : ''
  const inner = badge ? `<g transform="translate(5.4 5.4) scale(0.55)">${glyphMarkup(kind, stroke, 2.4)}</g>` : glyphMarkup(kind, stroke)
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24">${bg}${inner}</svg>`
}

export const glyphDataUri = (kind, opts) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(glyphSvg(kind, opts))}`

// ------------------------------------------------------------------ lanes
export const CORE_EDGES = [
  ['supplier', 'factory'], ['factory', 'warehouse'], ['warehouse', 'retailer'], ['warehouse', 'customer'], ['retailer', 'customer'],
]
export const OPTIONAL_EDGES = [['supplier', 'warehouse'], ['factory', 'retailer'], ['factory', 'customer']]
const ALLOWED = new Set([...CORE_EDGES, ...OPTIONAL_EDGES].map(([a, b]) => `${a}>${b}`))

export const edgeAllowed = (srcKind, dstKind) => ALLOWED.has(`${srcKind}>${dstKind}`)
/** Kinds a node of `kind` may ship to, core directions first. */
export const allowedTargets = (kind) =>
  [...CORE_EDGES, ...OPTIONAL_EDGES].filter(([a]) => a === kind).map(([, b]) => b)

/** Transport modes: suggestion constants match backend/node_types.py MODE_DEFAULTS. color = flow particles. */
export const MODES = {
  road: { label: 'Road', speed: 450, handling: 0.5, co2PerKm: 0.0026, baseCost: 5, costPerKm: 0.04, color: '#A1A1AA' },
  rail: { label: 'Rail', speed: 380, handling: 1, co2PerKm: 0.0011, baseCost: 8, costPerKm: 0.025, color: '#38BDF8' },
  sea: { label: 'Sea', speed: 350, handling: 2, co2PerKm: 0.0008, baseCost: 12, costPerKm: 0.015, color: '#818CF8' },
  air: { label: 'Air', speed: 4000, handling: 0.5, co2PerKm: 0.012, baseCost: 20, costPerKm: 0.25, color: '#F0F9FF' },
}
const mode = (m) => MODES[m] || MODES.road
const round = (v, d) => Math.round(v * 10 ** d) / 10 ** d

export function haversineKm(a, b) {
  const r = Math.PI / 180
  const [lat1, lon1, lat2, lon2] = [a[0] * r, a[1] * r, b[0] * r, b[1] * r]
  const h = Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(Math.min(1, h)))
}
export const suggestLead = (m, km) => Math.max(1, round(km / mode(m).speed + mode(m).handling, 1))
export const suggestCo2 = (m, km) => round(km * mode(m).co2PerKm, 2)
export const suggestCost = (m, km) => round(mode(m).baseCost + km * mode(m).costPerKm, 1)

// ------------------------------------------------------------------ builder fields
/**
 * Form fields. type: number | text | select | checkbox. Common fields apply to every kind; TYPE_FIELDS per kind.
 * Bounds mirror the backend's Pydantic models (schemas.BuilderNode).
 */
export const COMMON_FIELDS = [
  { key: 'name', label: 'Name', type: 'text', required: true, maxLength: 80, placeholder: 'e.g. Pune Steel Coils' },
  { key: 'city', label: 'Address / city', type: 'text', maxLength: 120, placeholder: 'e.g. Chakan, Pune' },
  { key: 'capacity', label: 'Capacity', unit: 'units/day', type: 'number', min: 0, placeholder: '500' },
  { key: 'stock', label: 'Current stock', unit: 'units', type: 'number', min: 0, placeholder: '1000' },
  { key: 'reliability', label: 'Reliability', unit: '0-1', type: 'number', min: 0, max: 1, step: 0.01, placeholder: '0.95' },
  { key: 'op_cost', label: 'Operating cost', unit: '₹/unit', type: 'number', min: 0, placeholder: '0' },
]

export const TYPE_FIELDS = {
  supplier: [
    { key: 'material', label: 'Material / product', type: 'text', maxLength: 80, placeholder: 'e.g. steel coils' },
    { key: 'lead_time_days', label: 'Lead time', unit: 'days', type: 'number', min: 0, max: 365, placeholder: '3' },
    { key: 'min_order_qty', label: 'Min order qty', unit: 'units', type: 'number', min: 0, placeholder: '100' },
    { key: 'price_per_unit', label: 'Price per unit', unit: '₹', type: 'number', min: 0, placeholder: '850' },
    { key: 'is_backup', label: 'Backup supplier (opens only after a shortfall)', type: 'checkbox' },
  ],
  factory: [
    { key: 'production_capacity', label: 'Production capacity', unit: 'units/day', type: 'number', min: 0, placeholder: 'overrides capacity' },
    { key: 'production_cost', label: 'Production cost', unit: '₹/unit', type: 'number', min: 0, placeholder: '120' },
    { key: 'overtime_limit_pct', label: 'Overtime limit', unit: '%', type: 'number', min: 0, max: 100, placeholder: '30' },
    { key: 'shifts_per_day', label: 'Shifts per day', type: 'number', min: 1, max: 4, step: 1, integer: true, placeholder: '2' },
  ],
  warehouse: [
    { key: 'storage_capacity', label: 'Storage capacity', unit: 'units', type: 'number', min: 0, placeholder: '20000' },
    { key: 'safety_stock', label: 'Safety stock level', unit: 'units', type: 'number', min: 0, placeholder: '800' },
    { key: 'holding_cost', label: 'Holding cost', unit: '₹/unit/day', type: 'number', min: 0, placeholder: '1.5' },
    { key: 'handling_time_days', label: 'Handling time', unit: 'days', type: 'number', min: 0, max: 60, placeholder: '0.5' },
  ],
  retailer: [
    { key: 'daily_demand', label: 'Daily demand', unit: 'units/day', type: 'number', min: 0, required: true, placeholder: '150' },
    { key: 'demand_variability_pct', label: 'Demand variability', unit: '%', type: 'number', min: 0, max: 100, placeholder: '15' },
    { key: 'service_level_pct', label: 'Service-level target', unit: '%', type: 'number', min: 0, max: 100, placeholder: '95' },
    { key: 'shelf_stock', label: 'Shelf stock', unit: 'units', type: 'number', min: 0, placeholder: '60' },
  ],
  customer: [
    { key: 'daily_demand', label: 'Daily demand', unit: 'units/day', type: 'number', min: 0, required: true, placeholder: '120' },
    { key: 'priority', label: 'Priority', type: 'select', options: ['low', 'medium', 'high'] },
    { key: 'penalty_per_unit', label: 'Contract penalty', unit: '₹/unmet unit', type: 'number', min: 0, placeholder: '500' },
  ],
}

/** Every type-specific key (used to strip fields that do not belong to a kind). */
export const ALL_TYPE_KEYS = [...new Set(Object.values(TYPE_FIELDS).flat().map((f) => f.key))]

/** Field defs for a kind: common + its own, with per-type label tweaks for the shared capacity/stock fields. */
export function fieldsFor(kind) {
  const common = COMMON_FIELDS.map((f) => {
    if (f.key === 'capacity' && isDemand(kind)) return { ...f, label: 'Forwarding capacity', placeholder: '0 = no limit' }
    if (f.key === 'capacity' && kind === 'warehouse') return { ...f, label: 'Throughput capacity' }
    if (f.key === 'stock' && kind === 'retailer') return { ...f, label: 'Back-room stock' }
    return f
  })
  return { common, specific: TYPE_FIELDS[kind] || [] }
}
