export const fmtNum = (v, digits = 0) =>
  v == null ? '-' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: digits })

export function fmtINR(v) {
  if (v == null) return '-'
  const a = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(2)} Cr`
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(1)} L`
  return `${sign}₹${a.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

export const fmtPct = (v) => (v == null ? '-' : `${Math.round(v * 100)}%`)

/** "+3", "-9.7", "+₹17": deltas that can go either way. */
export const fmtSigned = (v, digits = 0, prefix = '') => `${v < 0 ? '-' : '+'}${prefix}${fmtNum(Math.abs(v), digits)}`

/** Tier metadata. Colors come from tokens (tier-*); shapes are used by the 2D graph, disk resolution by 3D. */
export const KIND = {
  supplier: { token: 'tierSupplier', shape: 'round-rectangle', label: 'Supplier', plural: 'Suppliers', swatch: 'bg-tier-supplier' },
  factory: { token: 'tierFactory', shape: 'round-hexagon', label: 'Factory', plural: 'Factories', swatch: 'bg-tier-factory' },
  warehouse: { token: 'tierWarehouse', shape: 'round-diamond', label: 'Warehouse', plural: 'Warehouses', swatch: 'bg-tier-warehouse' },
  customer: { token: 'tierCustomer', shape: 'ellipse', label: 'Customer', plural: 'Customers', swatch: 'bg-tier-customer' },
}

/** Node status -> token key + Badge tone. */
export const STATUS = {
  ok: { token: 'ok', tone: 'ok', label: 'OK' },
  stressed: { token: 'warn', tone: 'warn', label: 'Stressed' },
  down: { token: 'bad', tone: 'bad', label: 'Down' },
}

export const BOTTLENECK = { threshold: 0.9 }

/** Human label for an event, e.g. "S2 outage", "F1->W3 blocked", "C3 demand +50%". */
export function eventLabel(e) {
  if (e.type === 'node') return `${e.target} ${e.severity >= 1 ? 'outage' : `−${Math.round(e.severity * 100)}%`}`
  if (e.type === 'edge') return `${e.target.replace('->', ' → ')} ${e.severity >= 1 ? 'blocked' : `−${Math.round(e.severity * 100)}%`}`
  return `${e.target} demand +${Math.round(e.severity * 100)}%`
}
