/** Shared Recharts styling: minimal axes, no heavy grid, one accent, token colors only. */

export function axisProps(t) {
  return {
    tick: { fill: t.color.fgMuted, fontSize: 12 },
    tickLine: false,
    axisLine: { stroke: t.color.border },
  }
}

export function gridProps(t) {
  return { stroke: t.color.border, strokeDasharray: '2 4', vertical: false }
}

export const refLabel = (t, value, color) => ({ value, position: 'top', fill: color || t.color.fg2, fontSize: 12, fontWeight: 500 })

/** Tooltip shell matching the Card style. Usage: <Tooltip content={<ChartTooltip render={(payload) => ...} />} /> */
export function ChartTooltip({ active, payload, render }) {
  if (!active || !payload?.length) return null
  return <div className="rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs shadow-card">{render(payload[0].payload, payload)}</div>
}

export const cursorFill = (t) => ({ fill: t.alpha('fg', 0.04) })
