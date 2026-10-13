/**
 * Shared Recharts styling: no chart borders, a light horizontal grid only, 11px neutral axis text (mono via CSS),
 * muted neutral series with the accent reserved for the focus series, and a minimal tooltip.
 */

export function axisProps(t) {
  return {
    tick: { fill: t.color.fgMuted, fontSize: 11 },
    tickLine: false,
    axisLine: false,
  }
}

export function gridProps(t) {
  return { stroke: t.color.border, vertical: false }
}

/** Direct label for a reference line (instead of a legend). */
export const refLabel = (t, value, color, position = 'insideTopRight') => ({ value, position, fill: color || t.color.fg2, fontSize: 11 })

export const series = (t) => ({ muted: t.alpha('fgMuted', 0.38), mutedStrong: t.alpha('fgMuted', 0.7), focus: t.color.accent })

/** Minimal tooltip shell. Usage: <Tooltip content={<ChartTooltip render={(row, payload) => ...} />} /> */
export function ChartTooltip({ active, payload, render }) {
  if (!active || !payload?.length) return null
  return <div className="rounded-md border border-border bg-surface px-2 py-1.5 text-xs shadow-float">{render(payload[0].payload, payload)}</div>
}

export const cursorFill = (t) => ({ fill: t.alpha('fg', 0.04) })
