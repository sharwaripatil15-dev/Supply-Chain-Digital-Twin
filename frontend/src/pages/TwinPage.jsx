import { ArrowRight, Boxes, Building2, Gauge, Network as NetworkIcon, ShieldCheck, Upload } from 'lucide-react'
import { useStore } from '../store.js'
import { KIND, fmtNum, fmtPct } from '../format.js'
import { Badge, Button, Card, CardBody, CardHeader, Meter, PageHeader, Stat, cn } from '../components/ui/index.js'
import GraphPanel from '../components/GraphPanel.jsx'

export default function TwinPage() {
  const store = useStore()
  const { upload, clearUpload, setTab, selectNode } = store
  const network = upload?.network || store.network
  const counts = Object.fromEntries(Object.keys(KIND).map((k) => [k, network.nodes.filter((n) => n.kind === k).length]))
  // Sites only: a customer's "risk" is just its own demand share, which would crowd out supply-side risks.
  const critical = network.nodes.filter((n) => n.kind !== 'customer').sort((a, b) => b.risk - a.risk).slice(0, 6)
  const resilience = network.resilience_score

  return (
    <>
      <PageHeader
        title="Digital twin"
        description="Every supplier, plant, warehouse and customer in the network, with ML-predicted criticality."
        actions={
          <Button variant="primary" iconRight={ArrowRight} onClick={() => setTab('simulate')}>
            Simulate a disruption
          </Button>
        }
      />
      {upload && (
        <Card className="mb-6 flex flex-wrap items-center gap-3 border-accent/30 bg-accent/5 px-4 py-3">
          <Upload className="h-4 w-4 text-accent" aria-hidden />
          <p className="flex-1 text-sm text-fg-2">
            Previewing your uploaded network ({upload.summary.n_nodes} nodes). Simulate, Chaos Finder and Recover use the demo network
            while their routers are mocked.
          </p>
          <Button size="sm" variant="ghost" onClick={clearUpload}>
            Back to demo
          </Button>
        </Card>
      )}

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Sites" icon={Building2} value={fmtNum(network.nodes.length - counts.customer)} sub={`${counts.supplier} suppliers · ${counts.factory} plants · ${counts.warehouse} DCs`} />
        <Stat label="Lanes" icon={NetworkIcon} value={fmtNum(network.edges.length)} sub={`${counts.customer} customers served`} />
        <Stat label="Customer demand" icon={Boxes} value={fmtNum(network.nodes.reduce((s, n) => s + n.demand, 0))} unit="units/day" sub="Nominal daily demand" />
        <Stat
          label="Resilience"
          icon={ShieldCheck}
          value={resilience != null ? resilience.toFixed(1) : '-'}
          unit={resilience != null ? '/ 100' : undefined}
          sub={resilience != null ? 'Chaos Finder stress test' : 'Not computed for uploads yet'}
          chip={resilience != null && <Badge tone={resilience >= 70 ? 'ok' : resilience >= 40 ? 'warn' : 'bad'} dot>{resilience >= 70 ? 'Strong' : resilience >= 40 ? 'Moderate' : 'Fragile'}</Badge>}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-12">
        <div className="xl:col-span-8">
          <GraphPanel title="Network map" description="Positions follow real geography" icon={NetworkIcon} network={network} heightClass="h-[600px]" />
        </div>
        <Card className="xl:col-span-4">
          <CardHeader title="Most critical sites" description="ML-predicted share of demand lost if the site fails" icon={Gauge} />
          <CardBody>
            <ul className="space-y-1">
              {critical.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => selectNode(n.id)}
                    className="w-full rounded-lg px-2 py-2 text-left transition-colors duration-150 hover:bg-surface-2"
                  >
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className={cn('h-2 w-2 shrink-0 rounded-sm', KIND[n.kind].swatch)} aria-hidden />
                        <span className="font-medium text-fg">{n.id}</span>
                        <span className="truncate text-fg-muted">{n.name}</span>
                      </span>
                      <span className="tabular font-medium text-fg">{fmtPct(n.risk)}</span>
                    </div>
                    <Meter className="mt-2" value={n.risk} max={Math.max(critical[0]?.risk || 1, 0.01)} label={`${n.id} criticality`} />
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-fg-muted">Select a site to see why (SHAP).</p>
          </CardBody>
        </Card>
      </div>
    </>
  )
}
