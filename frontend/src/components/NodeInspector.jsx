import { useState } from 'react'
import { ChevronRight, Play, X } from 'lucide-react'
import { useStore } from '../store.js'
import { STATUS, fmtNum, fmtPct } from '../format.js'
import { fieldsFor, isDemand, typeOf } from '../lib/nodeTypes.js'
import { Button, IconButton, Meter, SectionLabel, StatusDot, cn } from './ui/index.js'
import { TypeIcon } from './NodeTypeIcon.jsx'

const TONE = { ok: 'ok', stressed: 'warn', down: 'bad' }

/** Diverging SHAP bars: right = raises predicted impact, left = lowers it. */
function ShapBars({ factors }) {
  if (!factors?.length) return <p className="text-xs text-fg-muted">No explanation available.</p>
  const max = Math.max(...factors.map((f) => Math.abs(f.impact)), 1e-9)
  return (
    <ul className="space-y-2">
      {factors.map((f) => {
        const pct = (Math.abs(f.impact) / max) * 50
        const up = f.impact > 0
        return (
          <li key={f.feature}>
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span className="truncate text-fg-2">{f.feature.replaceAll('_', ' ')}</span>
              <span className={cn('num', up ? 'text-bad' : 'text-ok')}>
                {up ? '+' : '−'}
                {Math.abs(f.impact).toFixed(3)}
              </span>
            </div>
            <div className="relative mt-1 h-1 rounded-full bg-raised" aria-hidden>
              <span className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
              <span
                className={cn('absolute inset-y-0 rounded-full', up ? 'bg-bad/60' : 'bg-ok/60')}
                style={up ? { left: '50%', width: `${pct}%` } : { right: '50%', width: `${pct}%` }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function Metric({ label, value, unit }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-fg-muted">{label}</dt>
      <dd className="mt-0.5 flex items-baseline gap-1 whitespace-nowrap">
        <span className="num text-sm text-fg">{value}</span>
        {unit && <span className="text-xs text-fg-muted">{unit}</span>}
      </dd>
    </div>
  )
}

/** Collapsible section (progressive disclosure for secondary detail). */
function Disclosure({ title, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="border-t border-border pt-3">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-center gap-1.5 text-left">
        <ChevronRight className={cn('h-3.5 w-3.5 text-fg-muted transition-transform duration-150', open && 'rotate-90')} aria-hidden />
        <SectionLabel as="span">{title}</SectionLabel>
      </button>
      {open && <div className="mt-2.5">{children}</div>}
    </section>
  )
}

/** Builder fields (material, priority, ...) with the form's labels and units. */
function Details({ node }) {
  const details = node.details || {}
  const { common, specific } = fieldsFor(node.kind)
  const defs = Object.fromEntries([...common, ...specific].map((f) => [f.key, f]))
  const rows = Object.entries(details).filter(([k, v]) => k !== 'status' && v !== null && v !== '' && v !== false)
  if (!rows.length) return null
  return (
    <Disclosure title="Site details">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5">
        {rows.map(([k, v]) => (
          <Metric key={k} label={defs[k]?.label || k.replaceAll('_', ' ')} value={typeof v === 'number' ? fmtNum(v, 2) : String(v)} unit={defs[k]?.unit} />
        ))}
      </dl>
    </Disclosure>
  )
}

/** Details of the selected node, shared by every page's inspector (2D or 3D selection). */
export default function NodeInspector() {
  const { selectedNode, selectNode, network, upload, tab, sim, day, runSimulation, setTab, source } = useStore()
  const pool = tab === 'twin' && upload?.network && !upload.activated ? upload.network : network
  const node = pool?.nodes?.find((n) => n.id === selectedNode)
  if (!node) return null
  const row = sim && tab !== 'twin' ? sim.timeline[day] : null
  const status = row?.node_status?.[node.id]
  const util = row?.utilization?.[node.id] ?? node.utilization
  const type = typeOf(node.kind)
  const demand = isDemand(node.kind)
  const canSimulate = !demand && (!source || source.runnable) && pool === network
  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-start gap-2.5 border-b border-border px-4 py-3">
        <TypeIcon kind={node.kind} size="md" />
        <div className="min-w-0 flex-1">
          <p className="flex min-w-0 items-baseline gap-2">
            <span className="num shrink-0 text-sm text-fg">{node.id}</span>
            <span className="truncate text-sm font-medium text-fg">{node.name || node.city}</span>
          </p>
          <p className="truncate text-xs text-fg-muted">
            {type.label}
            {node.city ? ` · ${node.city}` : ''}
            {node.backup ? ' · backup supplier' : ''}
          </p>
        </div>
        <IconButton icon={X} label="Clear selection" shortcut="Esc" size="sm" tooltipSide="left" onClick={() => selectNode(null)} />
      </header>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-3">
        {status && <StatusDot status={TONE[status]} label={`${STATUS[status].label} on day ${day}`} textClassName="text-fg" />}
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
          <Metric label="Criticality" value={node.risk == null ? 'n/a' : fmtPct(node.risk)} />
          <Metric label="Reliability" value={fmtPct(node.reliability)} />
          <Metric label={demand ? 'Demand' : 'Capacity'} value={fmtNum(demand ? node.demand : node.capacity)} unit="units/day" />
          <Metric label="Stock" value={fmtNum(node.stock)} unit="units" />
        </dl>
        {(!demand || node.capacity > 0) && (
          <div>
            <div className="mb-1.5 flex justify-between text-xs">
              <span className="text-fg-muted">Utilization{row ? `, day ${day}` : ', baseline'}</span>
              <span className="num text-fg">{fmtPct(util)}</span>
            </div>
            <Meter value={util ?? 0} max={1.2} threshold={0.9} label="Utilization" />
          </div>
        )}
        {canSimulate && (
          <Button
            size="sm"
            icon={Play}
            className="w-full"
            onClick={() => {
              runSimulation([{ type: 'node', target: node.id, start: 2, duration: 10, severity: 1 }])
              setTab('simulate')
            }}
          >
            Simulate a 10-day outage
          </Button>
        )}
        <Details node={node} />
        <Disclosure title="Why this criticality" defaultOpen>
          {node.risk == null ? (
            <p className="text-xs text-fg-muted">{node.risk_note || 'The risk model has not scored this node.'}</p>
          ) : (
            <>
              <p className="mb-2.5 text-xs text-fg-muted">SHAP contribution to the predicted share of demand lost if this site fails.</p>
              <ShapBars factors={node.top_factors} />
            </>
          )}
        </Disclosure>
      </div>
    </div>
  )
}
