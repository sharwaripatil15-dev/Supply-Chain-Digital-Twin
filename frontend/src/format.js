import { NODE_TYPES, typeOf } from './lib/nodeTypes.js'

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

/** Node-type metadata for views that only need label + swatch. Defined once in lib/nodeTypes.js. */
const withSwatch = (t) => ({ ...t, shape: t.shape2d, swatch: `bg-tier-${t.kind}` })
export const KIND = Object.fromEntries(Object.values(NODE_TYPES).map((t) => [t.kind, withSwatch(t)]))
/** Like KIND[kind], but never undefined (unknown kinds get a neutral fallback). */
export const kindMeta = (kind) => KIND[kind] || withSwatch(typeOf(kind))

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
