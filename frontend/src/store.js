import { createContext, createElement, useCallback, useContext, useMemo, useRef, useState } from 'react'
import { api, errorMessage, fieldErrors } from './api.js'
import { eventsForNetwork } from './lib/scenarios.js'

const StoreContext = createContext(null)
const HISTORY_LIMIT = 20

export const DEMO_SCENARIOS = [
  {
    id: 'supplier',
    label: 'Supplier failure',
    blurb: 'Chennai Electronics (S2) goes dark for 10 days.',
    category: 'Node Outage',
    events: [{ type: 'node', target: 'S2', start: 2, duration: 10, severity: 1 }],
  },
  {
    id: 'route',
    label: 'Chennai route blocked + demand spike',
    blurb: 'Bengaluru to Sriperumbudur lane flooded; Bengaluru demand +50%.',
    category: 'Multi-Disruption',
    events: [
      { type: 'edge', target: 'F1->W3', start: 3, duration: 8, severity: 1 },
      { type: 'demand', target: 'C3', start: 4, duration: 6, severity: 0.5 },
    ],
  },
  {
    id: 'cascade',
    label: 'Cascading failure',
    blurb: 'S2 outage, then Nagpur hub fire, then Pune lane disruption.',
    category: 'Cascading Chain',
    events: [
      { type: 'node', target: 'S2', start: 1, duration: 12, severity: 1 },
      { type: 'node', target: 'W4', start: 5, duration: 8, severity: 0.9 },
      { type: 'edge', target: 'S1->F1', start: 6, duration: 6, severity: 0.7 },
    ],
  },
  {
    id: 'warehouse-spof',
    label: 'Warehouse SPOF bottleneck',
    blurb: 'Bhiwandi DC (W1) total outage for 7 days.',
    category: 'AI Bottleneck SPOF',
    events: [{ type: 'node', target: 'W1', start: 1, duration: 7, severity: 1 }],
  },
  {
    id: 'factory-shift',
    label: 'Factory assembly breakdown',
    blurb: 'Bengaluru Assembly (F1) goes down at 80% loss for 8 days.',
    category: 'Production Constraint',
    events: [{ type: 'node', target: 'F1', start: 2, duration: 8, severity: 0.8 }],
  },
  {
    id: 'demand-surge',
    label: 'Regional demand surge',
    blurb: 'Mumbai (C1) and Bengaluru (C3) demand +60% for 6 days.',
    category: 'Demand Shock',
    events: [
      { type: 'demand', target: 'C1', start: 2, duration: 6, severity: 0.6 },
      { type: 'demand', target: 'C3', start: 3, duration: 6, severity: 0.6 },
    ],
  },
]

export const SOURCE_LABEL = { preset: 'Preset demo', csv: 'CSV upload', manual: 'Manual network' }

const initial = {
  tab: 'twin',
  network: null,
  source: null, // GET /network/source: { source, version, runnable, ... }
  upload: null,
  forecast: null,
  surrogate: null,
  riskPrediction: null,
  riskStatus: null,
  advisory: null,
  alternates: null,
  optimizedPlan: null,
  dashboardSummary: null,
  events: DEMO_SCENARIOS[0].events,
  horizon: 30,
  sim: null,
  mc: null,
  chaos: null,
  recover: null,
  recoverFor: null,
  day: 0,
  selectedNode: null,
  manual: null, // GET /network/manual: { source, version, nodes, edges, validation }
  history: { past: [], future: [] }, // builder undo/redo: { label, nodes, edges } snapshots
  builderSelection: null, // { type: 'node' | 'edge', id } shared by the builder tables and its map
  loading: {},
  errors: {},
}

const snapshot = (manual, label) => ({ label, nodes: manual?.nodes ?? [], edges: manual?.edges ?? [] })

/** Results computed for an older network version are dropped; events are kept only if they still fit. */
function forNewNetwork(s, network, source) {
  const ids = new Set((network?.nodes ?? []).map((n) => n.id))
  return {
    sim: null,
    mc: null,
    chaos: null,
    recover: null,
    recoverFor: null,
    forecast: null,
    day: 0,
    selectedNode: ids.has(s.selectedNode) ? s.selectedNode : null,
    // a different source (or first load) gets scenarios for that network; an edit keeps the scenario if it still fits
    events: eventsForNetwork(network, s.events, DEMO_SCENARIOS, source?.source === 'preset', s.source?.source === source?.source),
    errors: { ...s.errors, sim: null, mc: null, chaos: null, recover: null, forecast: null },
  }
}

export function StoreProvider({ children }) {
  const [state, setState] = useState(initial)
  const stateRef = useRef(state)
  stateRef.current = state
  const patch = useCallback(
    (p) =>
      setState((s) => {
        const next = { ...s, ...(typeof p === 'function' ? p(s) : p) }
        stateRef.current = next
        return next
      }),
    [],
  )

  // Runs an API call with per-key loading + error tracking.
  const request = useCallback(
    async (key, fn, onOk) => {
      patch((s) => ({ loading: { ...s.loading, [key]: true }, errors: { ...s.errors, [key]: null } }))
      try {
        const result = await fn()
        patch((s) => ({ ...onOk(result, s), loading: { ...s.loading, [key]: false } }))
        return result
      } catch (err) {
        patch((s) => ({ loading: { ...s.loading, [key]: false }, errors: { ...s.errors, [key]: errorMessage(err) } }))
        return null
      }
    },
    [patch],
  )

  const actions = useMemo(() => {
    /** /network + /network/source together; a new version resets every result computed for the old network. */
    const loadNetwork = () =>
      request(
        'network',
        async () => {
          const [network, source] = await Promise.all([api.network(), api.networkSource()])
          return { network, source }
        },
        ({ network, source }, s) => {
          const changed = !s.network || s.source?.version !== source.version
          return { network, source, ...(changed ? forNewNetwork(s, network, source) : {}) }
        },
      )

    const loadManual = () => request('manual', api.manual, (manual) => ({ manual }))

    /**
     * Run one builder change. Records an undo snapshot, re-reads the manual network, and refreshes the active
     * network when the manual one is live so every tab updates. Resolves { ok, data } or { ok: false, error, fields }.
     */
    const mutate = async (label, fn, { record = true } = {}) => {
      const before = snapshot(stateRef.current.manual, label)
      patch((s) => ({ loading: { ...s.loading, builder: true }, errors: { ...s.errors, builder: null } }))
      try {
        const res = await fn()
        const manual = await api.manual()
        patch((s) => ({
          manual,
          history: record ? { past: [...s.history.past, before].slice(-HISTORY_LIMIT), future: [] } : s.history,
          loading: { ...s.loading, builder: false },
        }))
        await loadNetwork()
        return { ok: true, data: res }
      } catch (err) {
        patch((s) => ({ loading: { ...s.loading, builder: false }, errors: { ...s.errors, builder: errorMessage(err) } }))
        return { ok: false, error: errorMessage(err), fields: fieldErrors(err) }
      }
    }

    /** Undo/redo restore a snapshot through POST /network/import (the server stays the source of truth). */
    const travel = async (dir) => {
      const { history, manual } = stateRef.current
      const stack = dir === 'undo' ? history.past : history.future
      if (!stack.length) return null
      const target = stack[stack.length - 1]
      const current = snapshot(manual, target.label)
      const res = await mutate(target.label, () => api.importNetwork({ nodes: target.nodes, edges: target.edges }), { record: false })
      if (res.ok) {
        patch((s) =>
          dir === 'undo'
            ? { history: { past: s.history.past.slice(0, -1), future: [...s.history.future, current].slice(-HISTORY_LIMIT) } }
            : { history: { past: [...s.history.past, current].slice(-HISTORY_LIMIT), future: s.history.future.slice(0, -1) } },
        )
      }
      return { ...res, label: target.label }
    }

    return {
      setTab: (tab) => patch({ tab }),
      setEvents: (events) => patch({ events }),
      setDay: (day) => patch({ day }),
      selectNode: (selectedNode) => patch({ selectedNode }),
      loadNetwork,
      loadForecast: () => request('forecast', () => api.forecast(14), (forecast) => ({ forecast })),
      loadSurrogate: () => request('surrogate', api.surrogate, (surrogate) => ({ surrogate })),
      loadRiskStatus: () => request('riskStatus', api.riskStatus, (riskStatus) => ({ riskStatus })),
      predictRisk: (events) =>
        request('riskPredict', () => api.predictRisk(events), (riskPrediction) => ({ riskPrediction })),
      loadAdvisory: () => request('advisory', api.advisory, (advisory) => ({ advisory })),
      loadAlternates: (events = []) => request('alternates', () => api.alternates(events), (alternates) => ({ alternates })),
      runOptimizePlan: (events = [], levers = ['reroute', 'backup', 'overtime', 'safety_stock', 'production_shift']) =>
        request('optimize', () => api.optimizePlan(events, levers), (optimizedPlan) => ({ optimizedPlan })),
      loadDashboardSummary: (events = []) =>
        request('dashboard', () => api.dashboardSummary(events), (dashboardSummary) => ({ dashboardSummary })),
      uploadCsv: async (nodesFile, edgesFile, activate) => {
        const res = await request('upload', () => api.upload(nodesFile, edgesFile, activate), (upload) => ({ upload, selectedNode: null }))
        if (res?.activated) await loadNetwork()
        return res
      },
      clearUpload: () => patch({ upload: null, selectedNode: null }),
      loadChaos: () => request('chaos', () => api.chaos(5), (chaos) => ({ chaos })),
      runSimulation: (events, horizon = 30) => {
        patch({ events, horizon })
        request('mc', () => api.monteCarlo(events, 200), (mc) => ({ mc }))
        return request('sim', () => api.simulate(events, horizon), (sim) => {
          const first = sim.timeline.find((d) => d.down.length || d.unmet > 0)
          return { sim, day: first ? first.day : 0, recover: null }
        })
      },
      runRecover: (events) =>
        request('recover', () => api.recover(events), (recover) => ({ recover, recoverFor: events })),
      parseText: (text) => request('parse', () => api.parse(text), (res) => ({ events: res.events })),

      // ---------------------------------------------- active source + builder
      setSource: async (source) => {
        patch((s) => ({ loading: { ...s.loading, source: true }, errors: { ...s.errors, source: null } }))
        try {
          await api.setSource(source)
          await loadNetwork()
          patch((s) => ({ loading: { ...s.loading, source: false } }))
          return { ok: true }
        } catch (err) {
          patch((s) => ({ loading: { ...s.loading, source: false }, errors: { ...s.errors, source: errorMessage(err) } }))
          return { ok: false, error: errorMessage(err) }
        }
      },
      loadManual,
      selectBuilder: (builderSelection) => patch({ builderSelection }),
      createNode: (node) => mutate(`Add ${node.name || node.kind}`, () => api.createNode(node)),
      updateNode: (id, node) => mutate(`Edit ${id}`, () => api.updateNode(id, node)),
      deleteNodes: (ids) =>
        mutate(ids.length === 1 ? `Delete ${ids[0]}` : `Delete ${ids.length} nodes`, async () => {
          const removed = []
          for (const id of ids) removed.push(await api.deleteNode(id))
          return removed
        }),
      createEdge: (edge) => mutate(`Add lane ${edge.source} → ${edge.target}`, () => api.createEdge(edge)),
      updateEdge: (id, edge) => mutate(`Edit lane ${id}`, () => api.updateEdge(id, edge)),
      deleteEdges: (ids) =>
        mutate(ids.length === 1 ? `Delete lane ${ids[0]}` : `Delete ${ids.length} lanes`, async () => {
          for (const id of ids) await api.deleteEdge(id)
        }),
      importManual: (network, activate = false) => mutate('Import network', () => api.importNetwork(network, activate)),
      resetManual: (to) => mutate(to === 'preset' ? 'Reset to preset' : 'Clear all', () => api.resetNetwork(to)),
      undo: () => travel('undo'),
      redo: () => travel('redo'),
    }
  }, [patch, request])

  const value = useMemo(() => ({ ...state, ...actions }), [state, actions])
  return createElement(StoreContext.Provider, { value }, children)
}

export function useStore() {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useStore must be used inside <StoreProvider>')
  return ctx
}
