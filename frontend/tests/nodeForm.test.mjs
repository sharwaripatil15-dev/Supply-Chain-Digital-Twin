import assert from 'node:assert/strict'
import { test } from 'node:test'
import { blankNode, duplicateNode, edgePayload, legalTargets, nextId, nodePayload, validateEdge, validateNode } from '../src/lib/nodeForm.js'
import { eventsFit, scenariosFor } from '../src/lib/scenarios.js'
import { searchCities } from '../src/lib/indianCities.js'

const supplier = { ...blankNode('supplier'), name: 'Pune Steel', lat: 18.52, lon: 73.86, capacity: 500, stock: 100 }

test('ids continue the per-type sequence', () => {
  assert.equal(nextId('S', []), 'S1')
  assert.equal(nextId('S', ['S1', 'S7', 'F3', 'S2x']), 'S8')
})

test('a complete supplier is valid', () => {
  assert.deepEqual(validateNode(supplier), {})
})

test('blank nodes are invalid until required fields are filled', () => {
  const errors = validateNode(blankNode('customer'))
  assert.ok(errors.name && errors.lat && errors.lon && errors.daily_demand)
})

test('bounds and types are enforced like the backend', () => {
  assert.match(validateNode({ ...supplier, lat: 95 }).lat, /between -90 and 90/)
  assert.match(validateNode({ ...supplier, lon: -200 }).lon, /between -180 and 180/)
  assert.match(validateNode({ ...supplier, capacity: -1 }).capacity, /negative/)
  assert.match(validateNode({ ...supplier, reliability: 1.2 }).reliability, /At most 1/)
  assert.match(validateNode({ ...supplier, capacity: 'abc' }).capacity, /number/)
  const factory = { ...blankNode('factory'), name: 'F', lat: 1, lon: 1, shifts_per_day: 2.5 }
  assert.match(validateNode(factory).shifts_per_day, /Whole number/)
})

test('ids are checked only on create', () => {
  assert.match(validateNode({ ...supplier, id: 'S1' }, { taken: ['S1'] }).id, /already used/)
  assert.match(validateNode({ ...supplier, id: 'bad id!' }).id, /Letters, digits/)
  assert.deepEqual(validateNode({ ...supplier, id: 'S1' }, { taken: ['S1'], isNew: false }), {})
})

test('payload drops empty optionals and fields of other types', () => {
  const p = nodePayload({ ...supplier, daily_demand: 50, material: '', price_per_unit: '12.5', is_backup: true })
  assert.equal(p.daily_demand, undefined) // not a supplier field
  assert.equal(p.material, undefined) // empty
  assert.equal(p.price_per_unit, 12.5)
  assert.equal(p.is_backup, true)
  assert.equal(typeof p.lat, 'number')
})

test('duplicate drops the id and nudges the location', () => {
  const d = duplicateNode({ ...supplier, id: 'S1' })
  assert.equal(d.id, undefined)
  assert.ok(d.name.endsWith('(copy)') && d.lat !== supplier.lat)
})

test('lane validation: legal directions, duplicates, capacity', () => {
  const nodes = [
    { id: 'S1', kind: 'supplier', lat: 18.5, lon: 73.8 },
    { id: 'F1', kind: 'factory', lat: 12.9, lon: 77.6 },
    { id: 'C1', kind: 'customer', lat: 28.7, lon: 77.1 },
  ]
  assert.deepEqual(validateEdge({ source: 'S1', target: 'F1', capacity: 10 }, nodes), {})
  assert.match(validateEdge({ source: 'S1', target: 'C1', capacity: 10 }, nodes).target, /cannot ship/)
  assert.match(validateEdge({ source: 'S1', target: 'F1', capacity: '' }, nodes).capacity, /required/)
  assert.match(validateEdge({ source: 'S1', target: 'F1', capacity: 1 }, nodes, [{ id: 'E1', source: 'S1', target: 'F1' }]).target, /already exists/)
  assert.deepEqual(legalTargets('S1', nodes).map((n) => n.id), ['F1'])
  assert.deepEqual(edgePayload({ source: 'S1', target: 'F1', capacity: '5', lead: '', cost: '3' }), { source: 'S1', target: 'F1', mode: 'road', capacity: 5, status: 'active', cost: 3 })
})

test('scenarios adapt to the network', () => {
  const net = {
    nodes: [{ id: 'P1', kind: 'supplier', capacity: 9 }, { id: 'R1', kind: 'retailer', demand: 5 }],
    edges: [{ source: 'P1', target: 'R1', capacity: 3 }],
  }
  const demo = [{ id: 'x', events: [{ type: 'node', target: 'S2', start: 1, duration: 1, severity: 1 }] }]
  const s = scenariosFor(net, demo)
  assert.deepEqual(s.map((x) => x.id), ['gen-supplier', 'gen-lane', 'gen-demand'])
  assert.ok(s.every((x) => eventsFit(net, x.events)))
  assert.equal(eventsFit(net, demo[0].events), false)
})

test('preset demos are never offered on another network, even when ids collide', () => {
  const net = {
    nodes: [{ id: 'S1', kind: 'supplier', capacity: 400 }, { id: 'S2', kind: 'supplier', capacity: 250, backup: true }, { id: 'C1', kind: 'customer', demand: 9 }],
    edges: [{ source: 'S1', target: 'C1', capacity: 3 }],
  }
  const demo = [{ id: 'supplier', events: [{ type: 'node', target: 'S2', start: 2, duration: 10, severity: 1 }] }]
  assert.equal(scenariosFor(net, demo, true)[0].id, 'supplier') // preset: curated demo
  const own = scenariosFor(net, demo, false)
  assert.equal(own[0].id, 'gen-supplier')
  assert.equal(own[0].events[0].target, 'S1') // biggest primary supplier, not the backup
})

test('city search', () => {
  assert.equal(searchCities('pun')[0].name, 'Pune')
  assert.ok(searchCities('').length > 0)
})
