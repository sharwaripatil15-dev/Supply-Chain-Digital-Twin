import { createContext, createElement, useCallback, useContext, useMemo, useState } from 'react'
import { api, errorMessage } from './api.js'

const StoreContext = createContext(null)

export const DEMO_SCENARIOS = [
  {
    id: 'supplier',
    label: 'Supplier failure',
    blurb: 'Chennai Electronics (S2) goes dark for 10 days.',
    events: [{ type: 'node', target: 'S2', start: 2, duration: 10, severity: 1 }],
  },
  {
    id: 'route',
    label: 'Chennai route blocked + demand spike',
    blurb: 'Bengaluru to Sriperumbudur lane flooded; Bengaluru demand +50%.',
    events: [
      { type: 'edge', target: 'F1->W3', start: 3, duration: 8, severity: 1 },
      { type: 'demand', target: 'C3', start: 4, duration: 6, severity: 0.5 },
    ],
  },
  {
    id: 'cascade',
    label: 'Cascading failure',
    blurb: 'S2 outage, then Nagpur hub fire, then Pune lane disruption.',
    events: [
      { type: 'node', target: 'S2', start: 1, duration: 12, severity: 1 },
      { type: 'node', target: 'W4', start: 5, duration: 8, severity: 0.9 },
      { type: 'edge', target: 'S1->F1', start: 6, duration: 6, severity: 0.7 },
    ],
  },
]

const initial = {
  tab: 'twin',
  network: null,
  upload: null,
  forecast: null,
  surrogate: null,
  events: DEMO_SCENARIOS[0].events,
  horizon: 30,
  sim: null,
  mc: null,
  chaos: null,
  recover: null,
  recoverFor: null,
  day: 0,
  selectedNode: null,
  loading: {},
  errors: {},
}

export function StoreProvider({ children }) {
  const [state, setState] = useState(initial)
  const patch = useCallback((p) => setState((s) => ({ ...s, ...(typeof p === 'function' ? p(s) : p) })), [])

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

  const actions = useMemo(
    () => ({
      setTab: (tab) => patch({ tab }),
      setEvents: (events) => patch({ events }),
      setDay: (day) => patch({ day }),
      selectNode: (selectedNode) => patch({ selectedNode }),
      loadNetwork: () => request('network', api.network, (network) => ({ network })),
      loadForecast: () => request('forecast', () => api.forecast(14), (forecast) => ({ forecast })),
      loadSurrogate: () => request('surrogate', api.surrogate, (surrogate) => ({ surrogate })),
      uploadCsv: (nodesFile, edgesFile, activate) =>
        request('upload', () => api.upload(nodesFile, edgesFile, activate), (upload) => ({ upload, selectedNode: null })),
      // The uploaded network is previewed on the Twin tab only; mock simulate/chaos/recover know the demo ids.
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
    }),
    [patch, request],
  )

  const value = useMemo(() => ({ ...state, ...actions }), [state, actions])
  return createElement(StoreContext.Provider, { value }, children)
}

export function useStore() {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useStore must be used inside <StoreProvider>')
  return ctx
}
