// Settings and API helpers shared by the background worker and the side panel.
export const DEFAULTS = { apiUrl: 'http://localhost:8000', appUrl: 'http://localhost:5173' }
export const MAX_QUESTION = 2000 // POST /whatif/run accepts up to 2,000 characters

export async function settings() {
  const s = await chrome.storage.sync.get(DEFAULTS)
  return { apiUrl: s.apiUrl.replace(/\/+$/, ''), appUrl: s.appUrl.replace(/\/+$/, '') }
}

export async function api(path, { method = 'GET', body, timeout = 180000 } = {}) {
  const { apiUrl } = await settings()
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeout)
  try {
    const res = await fetch(apiUrl + path, {
      method,
      headers: body ? { 'content-type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      const d = data.detail
      throw new Error(typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => x.msg).join('; ') : `HTTP ${res.status}`)
    }
    return data
  } catch (err) {
    if (err.name === 'AbortError') throw new Error('AEGIS took too long to answer.')
    if (err instanceof TypeError) throw new Error(`Cannot reach AEGIS at ${apiUrl}. Is the backend running?`)
    throw err
  } finally {
    clearTimeout(timer)
  }
}

/** Alerts shown on the toolbar badge: high/critical findings + lanes at high/severe weather risk. */
export async function countAlerts() {
  const [analysis, weather] = await Promise.allSettled([api('/analysis/latest', { timeout: 15000 }), api('/weather/risk?horizon=7', { timeout: 20000 })])
  let n = 0
  if (analysis.status === 'fulfilled' && analysis.value.status === 'ok') {
    n += analysis.value.findings.filter((f) => ['critical', 'high'].includes(f.severity_level)).length
  }
  if (weather.status === 'fulfilled') {
    n += (weather.value.edges || []).filter((e) => ['high', 'severe'].includes(e.max_level)).length
  }
  return { n, ok: analysis.status === 'fulfilled' || weather.status === 'fulfilled' }
}
