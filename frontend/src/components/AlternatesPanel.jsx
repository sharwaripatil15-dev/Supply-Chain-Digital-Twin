import { ArrowRight } from 'lucide-react'
import { fmtNum, fmtPct, fmtSigned } from '../format.js'
import { DataTable } from './ui/index.js'
import { NodeTag } from './NodeTypeIcon.jsx'

const ACTION_LABEL = {
  'pre-position': 'Pre-position',
  transfer: 'Transfer',
  raise_safety_stock: 'Raise safety stock',
  hold: 'Hold (do not drain)',
}

function Path({ nodes }) {
  return (
    <span className="inline-flex items-center">
      {nodes.map((n, i) => (
        <span key={`${n}-${i}`} className="inline-flex items-center">
          {i > 0 && <ArrowRight className="mx-0.5 h-3 w-3 text-fg-muted" aria-hidden />}
          <NodeTag id={n} showName={false} />
        </span>
      ))}
    </span>
  )
}

const Reason = ({ text }) => (
  <span className="block max-w-[22rem] truncate text-xs text-fg-muted" title={text}>
    {text}
  </span>
)

export function AlternateSuppliers({ rows }) {
  return (
    <DataTable
      label="Alternate suppliers"
      rows={rows}
      rowKey={(s) => `${s.replaces}-${s.supplier}`}
      empty="No alternate supplier is needed for this scenario."
      columns={[
        { key: 'supplier', header: 'Supplier', hideable: false, render: (s) => <NodeTag id={s.supplier} nameClassName="max-w-[11rem]" /> },
        { key: 'replaces', header: 'Replaces', render: (s) => <NodeTag id={s.replaces} showName={false} /> },
        { key: 'spare_capacity', header: 'Spare/day', align: 'right', render: (s) => fmtNum(s.spare_capacity) },
        { key: 'lead', header: 'Lead', align: 'right', render: (s) => `${s.lead} d` },
        { key: 'cost_premium_pct', header: 'Premium', align: 'right', render: (s) => `${fmtSigned(s.cost_premium_pct)}%` },
        { key: 'reliability', header: 'Reliability', align: 'right', render: (s) => fmtPct(s.reliability) },
        { key: 'reason', header: 'Why', sortable: false, render: (s) => <Reason text={s.reason} /> },
      ]}
    />
  )
}

export function AlternateRoutes({ rows }) {
  return (
    <DataTable
      label="Alternate routes"
      rows={rows}
      rowKey={(r) => `${r.destination}:${r.via.join('>')}`}
      empty="No rerouting is needed for this scenario."
      columns={[
        { key: 'via', header: 'New route', hideable: false, value: (r) => r.via.join(' '), render: (r) => <Path nodes={r.via} /> },
        { key: 'replaces', header: 'Replaces', render: (r) => <span className="num text-xs text-fg-2">{r.replaces}</span> },
        { key: 'spare_capacity', header: 'Spare', align: 'right', render: (r) => fmtNum(r.spare_capacity) },
        { key: 'extra_lead_days', header: 'Δ lead', align: 'right', render: (r) => `${fmtSigned(r.extra_lead_days, 1)} d` },
        { key: 'extra_cost_per_unit', header: 'Δ cost/unit', align: 'right', render: (r) => fmtSigned(r.extra_cost_per_unit, 1, '₹') },
      ]}
    />
  )
}

export function InventoryActions({ rows }) {
  return (
    <DataTable
      label="Inventory actions"
      rows={rows.map((a, i) => ({ ...a, id: i }))}
      empty="No inventory moves are needed for this scenario."
      defaultSort={{ key: 'day', dir: 'asc' }}
      columns={[
        { key: 'day', header: 'Day', align: 'right', width: 'w-14', render: (a) => a.day },
        { key: 'action', header: 'Action', render: (a) => <span className="text-fg">{ACTION_LABEL[a.action] || a.action}</span> },
        { key: 'node', header: 'At', render: (a) => <NodeTag id={a.node} showName={false} /> },
        { key: 'source', header: 'From', render: (a) => (a.source ? <NodeTag id={a.source} showName={false} /> : <span className="text-fg-muted">–</span>) },
        { key: 'units', header: 'Units', align: 'right', render: (a) => fmtNum(a.units) },
        { key: 'reason', header: 'Why', sortable: false, render: (a) => <Reason text={a.reason} /> },
      ]}
    />
  )
}

export function ProductionActions({ rows }) {
  return (
    <DataTable
      label="Production actions"
      rows={rows.map((p, i) => ({ ...p, id: i }))}
      empty="No production shift is needed for this scenario."
      defaultSort={{ key: 'start_day', dir: 'asc' }}
      columns={[
        { key: 'start_day', header: 'Day', align: 'right', width: 'w-14', render: (p) => p.start_day },
        {
          key: 'shift', header: 'Shift', value: (p) => `${p.from_factory}${p.to_factory}`,
          render: (p) => (
            <span className="inline-flex items-center gap-1">
              <NodeTag id={p.from_factory} showName={false} />
              <ArrowRight className="h-3 w-3 text-fg-muted" aria-hidden />
              <NodeTag id={p.to_factory} showName={false} />
            </span>
          ),
        },
        { key: 'units_per_day', header: 'Units/day', align: 'right', render: (p) => fmtNum(p.units_per_day) },
        { key: 'duration', header: 'Days', align: 'right', render: (p) => p.duration },
        { key: 'reason', header: 'Why', sortable: false, render: (p) => <Reason text={p.reason} /> },
      ]}
    />
  )
}
