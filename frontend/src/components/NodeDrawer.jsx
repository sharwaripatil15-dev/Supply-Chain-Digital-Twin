import { useStore } from '../store.js'
import { KIND, STATUS, fmtNum, fmtPct } from '../format.js'
import { Badge, Drawer, Meter, cn } from './ui/index.js'

/** Diverging SHAP bars: right = raises predicted impact, left = lowers it. */
function ShapBars({ factors }) {
  if (!factors?.length) return <p className="text-xs text-fg-muted">No explanation available.</p>
  const max = Math.max(...factors.map((f) => Math.abs(f.impact)), 1e-9)
  return (
    <ul className="space-y-2.5">
      {factors.map((f) => {
        const pct = (Math.abs(f.impact) / max) * 50
        const up = f.impact > 0
        return (
          <li key={f.feature}>
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span className="truncate text-fg-2">{f.feature.replaceAll('_', ' ')}</span>
              <span className={cn('tabular font-medium', up ? 'text-bad' : 'text-ok')}>
                {up ? '+' : '−'}
                {Math.abs(f.impact).toFixed(3)}
              </span>
            </div>
            <div className="relative mt-1 h-1.5 rounded-full bg-surface-3" aria-hidden>
              <span className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
              <span
                className={cn('absolute inset-y-0 rounded-full', up ? 'bg-bad/70' : 'bg-ok/70')}
                style={up ? { left: '50%', width: `${pct}%` } : { right: '50%', width: `${pct}%` }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function Metric({ label, value }) {
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2">
      <dt className="text-xs text-fg-muted">{label}</dt>
      <dd className="tabular text-sm font-semibold text-fg">{value}</dd>
    </div>
  )
}

/** Side drawer opened by clicking a node in either the 2D or 3D view. */
export default function NodeDrawer() {
  const { selectedNode, selectNode, network, upload, tab, sim, day } = useStore()
  const source = tab === 'twin' && upload?.network ? upload.network : network
  const node = source?.nodes.find((n) => n.id === selectedNode)
  const row = sim && tab !== 'twin' ? sim.timeline[day] : null
  const status = row?.node_status?.[node?.id]
  const util = row?.utilization?.[node?.id] ?? node?.utilization
  return (
    <Drawer
      open={Boolean(node)}
      onClose={() => selectNode(null)}
      title={node ? `${node.id} · ${node.name || node.city}` : ''}
      subtitle={node ? `${KIND[node.kind].label} · ${node.city}` : ''}
    >
      {node && (
        <div className="space-y-6">
          <div className="flex flex-wrap gap-1.5">
            <Badge>
              <span className={cn('h-2 w-2 rounded-sm', KIND[node.kind].swatch)} aria-hidden />
              {KIND[node.kind].label}
            </Badge>
            {status && (
              <Badge tone={STATUS[status].tone} dot>
                {STATUS[status].label} on day {day}
              </Badge>
            )}
            {node.backup && <Badge tone="accent">Backup supplier</Badge>}
          </div>

          <dl className="grid grid-cols-2 gap-2">
            <Metric label="Criticality" value={fmtPct(node.risk)} />
            <Metric label="Reliability" value={fmtPct(node.reliability)} />
            <Metric label={node.kind === 'customer' ? 'Demand / day' : 'Capacity / day'} value={fmtNum(node.kind === 'customer' ? node.demand : node.capacity)} />
            <Metric label="Stock" value={fmtNum(node.stock)} />
          </dl>

          {node.kind !== 'customer' && (
            <div>
              <div className="mb-1.5 flex justify-between text-xs">
                <span className="text-fg-muted">Utilization{row ? ` · day ${day}` : ' · baseline'}</span>
                <span className="tabular font-medium text-fg">{fmtPct(util)}</span>
              </div>
              <Meter value={util ?? 0} max={1.2} threshold={0.9} label="Utilization" />
              <p className="mt-1 text-xs text-fg-muted">Tick marks the 90% bottleneck threshold.</p>
            </div>
          )}

          <div>
            <h3 className="mb-1 text-xs font-semibold text-fg">Why this criticality score</h3>
            <p className="mb-3 text-xs text-fg-muted">SHAP contributions to the predicted share of demand lost if this site fails.</p>
            <ShapBars factors={node.top_factors} />
          </div>
        </div>
      )}
    </Drawer>
  )
}
