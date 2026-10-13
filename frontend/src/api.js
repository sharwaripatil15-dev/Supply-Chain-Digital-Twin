import axios from 'axios'

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const client = axios.create({ baseURL: API_URL, timeout: 60000 })

const data = (p) => p.then((r) => r.data)
const enc = encodeURIComponent

export const api = {
  network: () => data(client.get('/network')),
  simulate: (events, horizon = 30) => data(client.post('/simulate', { events, horizon })),
  monteCarlo: (events, n = 200) => data(client.post('/montecarlo', { events, n })),
  chaos: (top = 5) => data(client.get('/chaos', { params: { top } })),
  recover: (events) => data(client.post('/recover', { events })),
  parse: (text) => data(client.post('/parse', { text })),
  forecast: (horizon = 14) => data(client.get('/forecast', { params: { horizon } })),
  surrogate: () => data(client.get('/surrogate')),
  upload: (nodesFile, edgesFile, activate = false) => {
    const form = new FormData()
    form.append('nodes', nodesFile)
    form.append('edges', edgesFile)
    return data(client.post('/upload', form, { params: { activate } }))
  },

  // ------------------------------------------------ active source + manual builder
  networkSource: () => data(client.get('/network/source')),
  setSource: (source) => data(client.put('/network/source', { source })),
  manual: () => data(client.get('/network/manual')),
  createNode: (node) => data(client.post('/network/nodes', node)),
  updateNode: (id, node) => data(client.put(`/network/nodes/${enc(id)}`, node)),
  deleteNode: (id) => data(client.delete(`/network/nodes/${enc(id)}`)),
  createEdge: (edge) => data(client.post('/network/edges', edge)),
  updateEdge: (id, edge) => data(client.put(`/network/edges/${enc(id)}`, edge)),
  deleteEdge: (id) => data(client.delete(`/network/edges/${enc(id)}`)),
  validate: (network) => data(client.post('/network/validate', network ?? null)),
  resetNetwork: (to) => data(client.post('/network/reset', null, { params: { to } })),
  exportNetwork: (scope = 'manual') => data(client.get('/network/export', { params: { scope } })),
  exportCsv: (file, scope = 'manual') => data(client.get('/network/export/csv', { params: { file, scope }, responseType: 'text' })),
  importNetwork: (network, activate = false) => data(client.post('/network/import', network, { params: { activate } })),

  // ------------------------------------------------ weather- and hazard-aware routing
  weatherRisk: (horizon = 7, refresh = false) => data(client.get('/weather/risk', { params: { horizon, refresh } })),
  weatherHazards: (horizon = 7) => data(client.get('/weather/hazards', { params: { horizon } })),
  weatherApply: (body) => data(client.post('/weather/apply', body)),
  weatherClear: () => data(client.delete('/weather/apply')),
  weatherReroute: (body) => data(client.post('/weather/reroute', body)),
  weatherScenarios: () => data(client.get('/weather/simulated-scenarios')),
  setWeatherScenario: (id) => data(client.post('/weather/simulated-scenarios', { id })),
  weatherStatus: () => data(client.get('/weather/status')),
  weatherChaos: (horizon = 7) => data(client.get('/weather/chaos', { params: { horizon } })),
}

export function errorMessage(err) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => `${(d.loc || []).slice(1).join('.') || 'request'}: ${d.msg}`).join('; ')
  if (err?.code === 'ERR_NETWORK') return `Cannot reach the API at ${API_URL}. Is the backend running?`
  if (err?.code === 'ECONNABORTED') return 'The API took too long to answer. Try again in a moment.'
  return err?.message || 'Unknown error'
}

/** Field-level messages from a FastAPI 422 ({ field: message }), for inline form errors. */
export function fieldErrors(err) {
  const detail = err?.response?.data?.detail
  if (!Array.isArray(detail)) return {}
  const out = {}
  for (const d of detail) {
    const field = d.loc?.length > 1 ? d.loc[d.loc.length - 1] : null
    if (field && typeof field === 'string' && !out[field]) out[field] = String(d.msg || '').replace(/^Value error, /, '')
  }
  return out
}
