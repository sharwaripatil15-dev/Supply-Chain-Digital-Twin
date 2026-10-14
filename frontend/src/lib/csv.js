/** Rows (array of flat objects) -> CSV text; header from the first row's keys. */
export function toCsv(rows) {
  if (!rows?.length) return ''
  const cols = Object.keys(rows[0])
  const cell = (v) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s
  }
  return [cols.join(','), ...rows.map((r) => cols.map((c) => cell(r[c])).join(','))].join('\n')
}
