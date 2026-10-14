/**
 * Executive brief: a clean two-page A4 print view (the browser's "Save as PDF" makes the PDF). Content is capped
 * (3 risks, 5 actions, one scenario, one expansion) so nothing is clipped across the page break.
 */
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

export function briefHtml(d) {
  const kpis = d.kpis.map((k) => `<tr><td>${esc(k.label)}</td><td class="n">${esc(k.value)}</td><td class="m">${esc(k.meaning)}</td></tr>`).join('')
  const breakdown = (d.health?.breakdown ?? []).map((b) => `<tr><td>${esc(b.label)}</td><td class="n">${Math.round(b.score)}</td><td class="m">weight ${b.weight}</td></tr>`).join('')
  const risks = d.risks.slice(0, 3).map((f, i) => `<li><b>${i + 1}. ${esc(f.title)}</b> <span class="tag">${esc(f.level)}</span><br>${esc(f.reason)}<br><span class="m">Revenue at risk: ${esc(f.revenue)}</span></li>`).join('')
  const actions = d.actions.slice(0, 5).map((a) => `<tr><td>${esc(a.kind)}</td><td>${esc(a.title)}</td><td class="n">${esc(a.benefit)}</td><td>${esc(a.effort)}</td></tr>`).join('')
  return `<!doctype html><html><head><meta charset="utf-8"><title>Executive brief</title><style>
  @page { size: A4; margin: 14mm }
  * { box-sizing: border-box }
  body { font: 11.5px/1.45 Inter, system-ui, -apple-system, 'Segoe UI', sans-serif; color: #16191f; margin: 0 }
  .page { min-height: 268mm; display: flex; flex-direction: column; gap: 10px }
  .page + .page { break-before: page }
  h1 { font-size: 20px; margin: 0 } h2 { font-size: 13px; margin: 6px 0 4px; border-bottom: 1px solid #dfe3e8; padding-bottom: 3px }
  .meta, .m { color: #5d6573 } .n { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums }
  table { width: 100%; border-collapse: collapse } td, th { padding: 4px 6px; border-bottom: 1px solid #eef0f3; vertical-align: top; text-align: left }
  .hero { display: flex; align-items: baseline; gap: 10px } .score { font-size: 40px; font-weight: 600 }
  ul { margin: 0; padding-left: 0; list-style: none } li { margin-bottom: 8px; break-inside: avoid }
  .tag { border: 1px solid #c9ced6; border-radius: 3px; padding: 0 4px; font-size: 10px; text-transform: uppercase }
  .foot { margin-top: auto; color: #5d6573; font-size: 10px; border-top: 1px solid #dfe3e8; padding-top: 6px }
  p { margin: 0 }
  </style></head><body>
  <section class="page">
    <div><h1>Supply chain executive brief</h1><p class="meta">${esc(d.network)} · ${esc(d.date)} · all figures simulated by the AEGIS digital twin</p></div>
    <h2>Health</h2>
    <div class="hero"><span class="score">${d.health?.score != null ? Math.round(d.health.score) : '–'}</span><span>/ 100 · ${esc(d.healthWord)}${d.health?.after_fixes?.score != null ? ` · ${Math.round(d.health.after_fixes.score)} after the recommended fixes` : ''}</span></div>
    <table>${breakdown}</table>
    <h2>Key indicators</h2>
    <table>${kpis}</table>
    <h2>Top risks</h2>
    <ul>${risks || '<li class="m">No analysis yet.</li>'}</ul>
    <p class="foot">Page 1 of 2 · Data source: ${esc(d.source)}. Site costs use illustrative indices. Generated ${esc(d.date)}.</p>
  </section>
  <section class="page">
    <h2>Recommended actions</h2>
    <table><tr><th>Type</th><th>Action</th><th class="n">Estimated benefit</th><th>Effort</th></tr>${actions || '<tr><td colspan="4" class="m">None yet.</td></tr>'}</table>
    <h2>Scenario</h2>
    <p>${esc(d.scenario || 'No what-if has been run yet.')}</p>
    <h2>Expansion recommendation</h2>
    <p>${esc(d.expansion || 'The expansion planner has not been run yet.')}</p>
    <p class="foot">Page 2 of 2 · Every number comes from the simulator on ${esc(d.source)}; they are not observed outcomes. Generated ${esc(d.date)}.</p>
  </section>
  <script>window.onload = () => window.print()</script>
  </body></html>`
}

export function printBrief(d) {
  const w = window.open('', '_blank', 'width=900,height=1100')
  if (!w) return false
  w.document.write(briefHtml(d))
  w.document.close()
  return true
}
