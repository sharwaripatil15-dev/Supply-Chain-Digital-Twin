import { DEFAULTS, MAX_QUESTION, api, settings } from './shared.js'

const $ = (id) => document.getElementById(id)
/** Tiny DOM builder: text is always set with textContent, never innerHTML (page text and API text are untrusted). */
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag)
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') node.className = v
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v)
    else if (v != null) node.setAttribute(k, v)
  }
  for (const c of children.flat()) if (c != null && c !== false) node.append(c instanceof Node ? c : document.createTextNode(String(c)))
  return node
}
const fmt = (v, d = 0) => (v == null ? '–' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: d }))
function inr(v) {
  if (v == null) return '–'
  const a = Math.abs(v), s = v < 0 ? '-' : ''
  if (a >= 1e7) return `${s}₹${(a / 1e7).toFixed(2)} Cr`
  if (a >= 1e5) return `${s}₹${(a / 1e5).toFixed(1)} L`
  return `${s}₹${fmt(a)}`
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
function showError(msg) {
  $('error').hidden = !msg
  $('error').textContent = msg || ''
}

// ------------------------------------------------------------ health, KPIs, risks
async function loadNetwork() {
  const [src, base] = await Promise.all([api('/network/source'), api('/expansion/baseline').catch(() => null)])
  const label = { preset: 'Preset demo', csv: 'CSV upload', manual: 'Manual network' }[src.source] || src.source
  $('network').textContent = `${label} · v${src.version}${src.runnable ? '' : ' · needs fixes'}`
  return base
}

function renderHealth(analysis, base) {
  const box = $('health')
  box.replaceChildren()
  if (analysis?.status === 'running') {
    const pct = Math.round((100 * analysis.progress.done) / Math.max(1, analysis.progress.total))
    box.append(el('p', {}, `Analysing… ${analysis.progress.step}`), el('div', { class: 'bar' }, el('span', { style: `width:${pct}%` })))
    return
  }
  if (analysis?.status === 'ok' && analysis.health?.score != null) {
    const s = analysis.health.score
    const word = s >= 70 ? 'Healthy' : s >= 50 ? 'Fair' : 'At risk'
    box.append(
      el('div', {}, el('span', { class: 'score' }, Math.round(s)), el('span', { class: 'unit' }, ' / 100 · '), el('span', { class: s >= 50 ? 'ok' : 'bad' }, word)),
      analysis.health.after_fixes?.score != null ? el('p', { class: 'muted small' }, `Top fixes would lift it to ${Math.round(analysis.health.after_fixes.score)}.`) : null,
    )
  } else {
    box.append(el('p', { class: 'muted' }, 'No analysis for this network yet. Press Analyze.'))
  }
  const rar = analysis?.status === 'ok' ? analysis.findings.reduce((t, f) => t + (f.impact.expected_loss_inr || 0), 0) : null
  if (base?.status === 'ok' || rar != null) {
    const k = (label, value) => el('div', { class: 'kpi' }, el('dt', {}, label), el('dd', {}, value))
    box.append(el('dl', { class: 'kpis' },
      k('Service level', base?.status === 'ok' ? `${fmt(base.service_level_pct, 1)}%` : '–'),
      k('Revenue at risk', rar != null ? inr(rar) : '–'),
      k('Avg lead time', base?.status === 'ok' ? `${fmt(base.avg_lead_days, 1)} days` : '–'),
      k('Stock cover', base?.status === 'ok' ? `${fmt(base.stock_cover_days, 1)} days` : '–'),
    ))
  }
}

function renderRisks(analysis) {
  const list = $('risks')
  list.replaceChildren()
  if (analysis?.status !== 'ok') return list.append(el('li', { class: 'muted' }, 'Run Analyze to see the top risks.'))
  if (!analysis.findings.length) return list.append(el('li', {}, 'Nothing needs attention.'))
  for (const f of analysis.findings.slice(0, 3)) {
    list.append(el('li', {},
      el('div', {}, el('span', { class: `dot ${f.severity_level}`, 'aria-hidden': 'true' }), el('b', {}, f.title)),
      el('p', { class: 'muted small' }, `${f.severity_level} · revenue at risk ${f.impact.revenue_at_risk_display}`),
      f.fixes[0] ? el('p', { class: 'small' }, `Fix: ${f.fixes[0].label} (${f.fixes[0].net_display} net, simulated)`) : null,
    ))
  }
}

async function refresh() {
  showError(null)
  try {
    const [base, analysis] = await Promise.all([loadNetwork(), api('/analysis/latest')])
    renderHealth(analysis, base)
    renderRisks(analysis)
    return analysis
  } catch (err) {
    $('network').textContent = 'Not connected'
    $('health').replaceChildren(el('p', { class: 'muted' }, 'Start the AEGIS backend, then reopen this panel.'))
    $('risks').replaceChildren()
    showError(err.message)
    return null
  }
}

async function analyze() {
  const btn = $('analyze-btn')
  btn.disabled = true
  showError(null)
  try {
    let a = await api('/analysis/run', { method: 'POST' })
    const base = await api('/expansion/baseline').catch(() => null)
    while (a.status === 'running') {
      renderHealth(a, base)
      await sleep(1000)
      a = await api('/analysis/latest')
    }
    if (a.status === 'error') throw new Error(a.detail)
    renderHealth(a, base)
    renderRisks(a)
    chrome.runtime.sendMessage({ type: 'refresh-badge' }).catch(() => {})
  } catch (err) {
    showError(err.message)
  } finally {
    btn.disabled = false
  }
}

// ------------------------------------------------------------ ask what-if
async function ask(text) {
  const q = (text ?? $('question').value).trim().slice(0, MAX_QUESTION)
  if (q.length < 3) return showError('Type or select a disruption to simulate.')
  showError(null)
  const out = $('answer')
  const btn = $('ask-btn')
  btn.disabled = true
  out.replaceChildren(el('div', { class: 'answer' }, el('p', { class: 'muted' }, 'Simulating the scenario, Monte Carlo and every recovery plan… (10-30 s)'), el('div', { class: 'bar' }, el('span', { style: 'width:40%' }))))
  try {
    const r = await api('/whatif/run', { method: 'POST', body: { text: q, mc_runs: 50, robustness_runs: 4 } })
    if (r.status !== 'ok') throw new Error(r.note || 'Nothing to simulate.')
    const imp = r.evidence.impact
    const rec = r.plans.find((p) => p.recommended)
    const sec = Object.fromEntries(r.sections.map((s) => [s.key, s]))
    out.replaceChildren(el('div', { class: 'answer' },
      el('p', { class: 'small muted' }, `Understood as: ${r.evidence.scenario.descriptions.join('; ')}`),
      el('dl', { class: 'kpis' },
        el('div', { class: 'kpi' }, el('dt', {}, 'Unmet demand'), el('dd', {}, `${imp.unmet_units_display} units (${fmt(imp.unmet_pct, 2)}%)`)),
        el('div', { class: 'kpi' }, el('dt', {}, 'Revenue at risk'), el('dd', {}, imp.revenue_at_risk_display)),
        el('div', { class: 'kpi' }, el('dt', {}, 'First stock-out'), el('dd', {}, imp.first_stockout ? `day ${imp.first_stockout.day} at ${imp.first_stockout.node}` : 'none')),
        el('div', { class: 'kpi' }, el('dt', {}, 'Bad case (P90)'), el('dd', {}, `${r.evidence.monte_carlo.p90_display} units`)),
      ),
      el('p', { style: 'margin-top:8px' }, el('b', {}, `Recommended: ${rec.label}`), el('span', { class: 'tag' }, `confidence ${r.confidence}`)),
      el('p', { class: 'small' }, `${rec.objective_display} total cost vs ${r.evidence.do_nothing.objective_display} if you wait it out; saves ${r.evidence.net_saving_display}.`),
      sec.cascade?.bullets?.length ? el('ul', { class: 'small' }, sec.cascade.bullets.slice(0, 3).map((b) => el('li', {}, b))) : null,
      r.evidence.scenario.assumptions.length ? el('p', { class: 'small muted' }, `Assumed: ${r.evidence.scenario.assumptions.join(' ')}`) : null,
      el('button', { class: 'wide', onclick: () => openApp() }, 'Open the full brief in AEGIS ↗'),
    ))
  } catch (err) {
    out.replaceChildren()
    showError(err.message)
  } finally {
    btn.disabled = false
  }
}

async function takePending() {
  const { pendingQuestion } = await chrome.storage.session.get('pendingQuestion')
  if (!pendingQuestion || Date.now() - pendingQuestion.at > 60000) return
  await chrome.storage.session.remove('pendingQuestion')
  $('question').value = pendingQuestion.text
  $('source').textContent = pendingQuestion.source ? `From: ${pendingQuestion.source}` : ''
  ask(pendingQuestion.text)
}

// ------------------------------------------------------------ settings + open app
async function openApp() {
  const { appUrl } = await settings()
  chrome.tabs.create({ url: appUrl })
}

async function initSettings() {
  const s = await settings()
  $('api-url').value = s.apiUrl
  $('app-url').value = s.appUrl
  $('settings-btn').addEventListener('click', () => ($('settings').hidden = !$('settings').hidden))
  $('save-settings').addEventListener('click', async () => {
    const apiUrl = $('api-url').value.trim() || DEFAULTS.apiUrl
    const appUrl = $('app-url').value.trim() || DEFAULTS.appUrl
    try {
      const origin = new URL(apiUrl).origin
      if (!/^https?:\/\/(localhost|127\.0\.0\.1)(:|$)/.test(origin)) {
        const granted = await chrome.permissions.request({ origins: [`${origin}/*`] })
        if (!granted) throw new Error(`Chrome did not grant access to ${origin}.`)
      }
      await chrome.storage.sync.set({ apiUrl, appUrl })
      $('settings-msg').textContent = 'Saved.'
      refresh()
    } catch (err) {
      $('settings-msg').textContent = err.message
    }
  })
}

$('ask-btn').addEventListener('click', () => ask())
$('question').addEventListener('keydown', (e) => (e.key === 'Enter' && (e.ctrlKey || e.metaKey) ? ask() : null))
$('analyze-btn').addEventListener('click', analyze)
$('open-app').addEventListener('click', openApp)
chrome.storage.session.onChanged.addListener((changes) => changes.pendingQuestion?.newValue && takePending())

await initSettings()
await refresh()
await takePending()
