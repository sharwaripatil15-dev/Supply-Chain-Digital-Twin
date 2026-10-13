import { ArrowRight, Boxes, Factory, Route, Truck } from 'lucide-react'
import { useStore } from '../store.js'
import { fmtNum, fmtPct, fmtSigned } from '../format.js'
import { Badge, Card, CardBody, CardHeader, Table, Td, Th, Tr } from './ui/index.js'

const ACTION_LABEL = {
  'pre-position': 'Pre-position',
  transfer: 'Transfer',
  raise_safety_stock: 'Raise safety stock',
  hold: 'Hold (do not drain)',
}

function Section({ title, description, icon, count, children }) {
  return (
    <Card>
      <CardHeader title={title} description={description} icon={icon} actions={<Badge>{count}</Badge>} />
      <CardBody className={count ? 'px-0 pb-2' : ''}>{count ? children : <p className="text-sm text-fg-muted">None needed for this scenario.</p>}</CardBody>
    </Card>
  )
}

function Path({ nodes, muted }) {
  return (
    <span className={muted ? 'text-fg-muted line-through decoration-fg-muted/60' : 'text-fg'}>
      {nodes.map((n, i) => (
        <span key={`${n}-${i}`} className="inline-flex items-center">
          {i > 0 && <ArrowRight className="mx-0.5 h-3 w-3 text-fg-muted" aria-hidden />}
          <span className={muted ? '' : 'font-medium'}>{n}</span>
        </span>
      ))}
    </span>
  )
}

export default function AlternatesPanel() {
  const { recover } = useStore()
  if (!recover) return null
  const { alternate_suppliers: sup, alternate_routes: routes, inventory_actions: inv, production_actions: prod } = recover

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Section title="Alternate suppliers" description="Ranked by cost, lead time and spare capacity" icon={Truck} count={sup.length}>
        <Table label="Alternate suppliers">
          <thead>
            <tr>
              <Th>Supplier</Th>
              <Th numeric>Spare/day</Th>
              <Th numeric>Lead</Th>
              <Th numeric>Premium</Th>
              <Th numeric>Reliability</Th>
            </tr>
          </thead>
          <tbody>
            {sup.map((s) => (
              <Tr key={`${s.replaces}-${s.supplier}`}>
                <Td>
                  <div className="font-medium text-fg">
                    {s.supplier} <span className="font-normal text-fg-2">{s.name}</span>
                  </div>
                  <div className="text-xs text-fg-muted">
                    replaces {s.replaces} · {s.city}
                  </div>
                  {s.reason && <p className="mt-1 max-w-sm text-xs text-fg-2">{s.reason}</p>}
                </Td>
                <Td numeric>{fmtNum(s.spare_capacity)}</Td>
                <Td numeric>{s.lead} d</Td>
                <Td numeric>{fmtSigned(s.cost_premium_pct)}%</Td>
                <Td numeric>{fmtPct(s.reliability)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Section>

      <Section title="Alternate routes" description="Old path → new path, with the change in lead time and cost" icon={Route} count={routes.length}>
        <Table label="Alternate routes">
          <thead>
            <tr>
              <Th>Route</Th>
              <Th numeric>Spare</Th>
              <Th numeric>Δ lead</Th>
              <Th numeric>Δ cost/unit</Th>
            </tr>
          </thead>
          <tbody>
            {routes.map((r) => (
              <Tr key={`${r.destination}:${r.via.join('>')}`}>
                <Td>
                  {r.old_via && (
                    <div className="text-xs">
                      <Path nodes={r.old_via} muted />
                    </div>
                  )}
                  <div className="mt-0.5 text-sm">
                    <Path nodes={r.via} />
                  </div>
                  <div className="mt-0.5 text-xs text-fg-muted">replaces {r.replaces}</div>
                </Td>
                <Td numeric>{fmtNum(r.spare_capacity)}</Td>
                <Td numeric>{fmtSigned(r.extra_lead_days, 1)} d</Td>
                <Td numeric>{fmtSigned(r.extra_cost_per_unit, 1, '₹')}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Section>

      <Section title="Inventory actions" icon={Boxes} count={inv.length}>
        <Table label="Inventory actions">
          <thead>
            <tr>
              <Th>Day</Th>
              <Th>Action</Th>
              <Th numeric>Units</Th>
            </tr>
          </thead>
          <tbody>
            {inv.map((a, i) => (
              <Tr key={i}>
                <Td className="tabular text-fg-muted">{a.day}</Td>
                <Td>
                  <div className="font-medium text-fg">
                    {ACTION_LABEL[a.action] || a.action} at {a.node}
                    {a.source && <span className="font-normal text-fg-2"> from {a.source}</span>}
                  </div>
                  <p className="text-xs text-fg-muted">{a.reason}</p>
                </Td>
                <Td numeric>{fmtNum(a.units)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Section>

      <Section title="Production actions" icon={Factory} count={prod.length}>
        <Table label="Production actions">
          <thead>
            <tr>
              <Th>Day</Th>
              <Th>Shift</Th>
              <Th numeric>Units/day</Th>
            </tr>
          </thead>
          <tbody>
            {prod.map((p, i) => (
              <Tr key={i}>
                <Td className="tabular text-fg-muted">{p.start_day}</Td>
                <Td>
                  <div className="font-medium text-fg">
                    {p.from_factory} → {p.to_factory} <span className="font-normal text-fg-2">for {p.duration} days</span>
                  </div>
                  <p className="text-xs text-fg-muted">{p.reason}</p>
                </Td>
                <Td numeric>{fmtNum(p.units_per_day)}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Section>
    </div>
  )
}
