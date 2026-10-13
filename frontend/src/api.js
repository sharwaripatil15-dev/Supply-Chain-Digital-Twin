import axios from 'axios'

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const client = axios.create({ baseURL: API_URL, timeout: 60000 })

const data = (p) => p.then((r) => r.data)

export const api = {
  network: () => data(client.get('/network')),
  simulate: (events, horizon = 30) => data(client.post('/simulate', { events, horizon })),
  monteCarlo: (events, n = 200) => data(client.post('/montecarlo', { events, n })),
  chaos: (top = 5) => data(client.get('/chaos', { params: { top } })),
  recover: (events) => data(client.post('/recover', { events })),
  parse: (text) => data(client.post('/parse', { text })),
  forecast: (horizon = 14) => data(client.get('/forecast', { params: { horizon } })),
  surrogate: () => data(client.get('/surrogate')),
  riskStatus: () => data(client.get('/risk/status')),
  predictRisk: (events, horizon = 30) => data(client.post('/risk/predict', { events, horizon })),
  upload: (nodesFile, edgesFile, activate = false) => {
    const form = new FormData()
    form.append('nodes', nodesFile)
    form.append('edges', edgesFile)
    return data(client.post('/upload', form, { params: { activate } }))
  },
}

export function errorMessage(err) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc?.slice(1).join('.')}: ${d.msg}`).join('; ')
  if (err?.code === 'ERR_NETWORK') return `Cannot reach the API at ${API_URL}. Is the backend running?`
  return err?.message || 'Unknown error'
}
