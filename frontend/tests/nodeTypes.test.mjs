// Run with `npm test` (Node's built-in test runner; no extra dependencies).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  ALL_TYPE_KEYS, MODES, NODE_KINDS, NODE_TYPES, STATUS_COLORS, TYPE_FIELDS, allowedTargets, edgeAllowed, fieldsFor, glyphDataUri,
  glyphSvg, haversineKm, isDemand, suggestCo2, suggestLead, typeOf,
} from '../src/lib/nodeTypes.js'

test('five node types, in tier order, with unique colors and shapes', () => {
  assert.deepEqual(NODE_KINDS, ['supplier', 'factory', 'warehouse', 'retailer', 'customer'])
  assert.deepEqual(NODE_KINDS.map((k) => NODE_TYPES[k].tier), [0, 1, 2, 3, 4])
  const colors = NODE_KINDS.map((k) => NODE_TYPES[k].color)
  assert.equal(new Set(colors).size, 5)
  assert.deepEqual(colors, ['#8B5CF6', '#2563EB', '#0D9488', '#DB2777', '#475569'])
  assert.equal(new Set(NODE_KINDS.map((k) => NODE_TYPES[k].shape2d)).size, 5)
  assert.deepEqual(NODE_KINDS.map((k) => NODE_TYPES[k].disk), [3, 4, 6, 8, 32])
})

test('type colors never reuse a status color', () => {
  const status = new Set(Object.values(STATUS_COLORS).map((s) => s.color.toUpperCase()))
  for (const k of NODE_KINDS) assert.ok(!status.has(NODE_TYPES[k].color.toUpperCase()), k)
})

test('retailers and customers are the demand kinds', () => {
  assert.deepEqual(NODE_KINDS.filter(isDemand), ['retailer', 'customer'])
  assert.equal(isDemand('supplier'), false)
  assert.equal(isDemand(undefined), false)
})

test('typeOf never returns undefined', () => {
  const t = typeOf('spaceship')
  assert.equal(t.label, 'Node')
  assert.ok(t.glyph.length > 0 && t.rgb.length === 3)
})

test('lane directions follow the tiers', () => {
  assert.ok(edgeAllowed('supplier', 'factory'))
  assert.ok(edgeAllowed('warehouse', 'retailer'))
  assert.ok(edgeAllowed('retailer', 'customer'))
  assert.ok(edgeAllowed('factory', 'customer')) // optional direct link
  assert.ok(!edgeAllowed('customer', 'supplier'))
  assert.ok(!edgeAllowed('supplier', 'customer'))
  assert.deepEqual(allowedTargets('supplier'), ['factory', 'warehouse'])
  assert.deepEqual(allowedTargets('customer'), [])
})

test('glyphs render to valid SVG data URIs', () => {
  for (const k of NODE_KINDS) {
    const svg = glyphSvg(k, { badge: true })
    assert.match(svg, /^<svg [^>]*viewBox="0 0 24 24"/)
    assert.ok(svg.includes(NODE_TYPES[k].color))
    assert.match(glyphDataUri(k), /^data:image\/svg\+xml;charset=utf-8,%3Csvg/)
  }
})

test('suggestions match the backend formulas', () => {
  const km = haversineKm([18.52, 73.857], [19.076, 72.878])
  assert.ok(km > 110 && km < 125, `Pune-Mumbai ~118 km, got ${km}`)
  assert.equal(suggestLead('road', 900), 2.5) // 900/450 + 0.5
  assert.equal(suggestLead('air', 100), 1) // never below a day
  assert.equal(suggestCo2('road', 1000), 2.6)
  assert.ok(suggestCo2('rail', 1000) < suggestCo2('road', 1000))
  assert.deepEqual(Object.keys(MODES), ['road', 'rail', 'sea', 'air'])
})

test('form fields per type', () => {
  assert.ok(TYPE_FIELDS.retailer.some((f) => f.key === 'daily_demand' && f.required))
  assert.ok(TYPE_FIELDS.customer.some((f) => f.key === 'priority' && f.type === 'select'))
  assert.ok(TYPE_FIELDS.factory.some((f) => f.key === 'shifts_per_day' && f.integer))
  assert.ok(ALL_TYPE_KEYS.includes('storage_capacity') && ALL_TYPE_KEYS.includes('is_backup'))
  assert.equal(fieldsFor('retailer').common.find((f) => f.key === 'stock').label, 'Back-room stock')
})
