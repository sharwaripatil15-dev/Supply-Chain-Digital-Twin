import { ArrowRight, Boxes, Building2, Database, Gauge, Network as NetworkIcon, ShieldCheck, Upload } from 'lucide-react'
import { SOURCE_LABEL, useStore } from '../store.js'
import { fmtNum, fmtPct } from '../format.js'
import { NODE_KINDS, isDemand, typeOf } from '../lib/nodeTypes.js'
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, InlineError, Meter, PageHeader, Stat } from '../components/ui/index.js'
import GraphPanel from '../components/GraphPanel.jsx'
import { NodeTag } from '../components/NodeTypeIcon.jsx'
import AiAdvisoryPanel from '../components/AiAdvisoryPanel.jsx'

export default function TwinPage() {
  const store = useStore()
  const { upload, clearUpload, setTab, selectNode, source } = store
  const previewing = upload?.network && !upload.activated
  const network = previewing ? upload.network : store.network
  const nodes = network?.nodes ?? []
  const counts = Object.fromEntries(NODE_KINDS.map((k) => [k, nodes.filter((n) => n.kind === k).length]))
  const sites = nodes.filter((n) => !isDemand(n.kind))
  const demandPoints = nodes.length - sites.length
  // Sites only: a demand point's "risk" is mostly its own demand share, which would crowd out supply-side risks.
  const critical = sites.filter((n) => n.risk != null).sort((a, b) => b.risk - a.risk).slice(0, 6)
  const unscored = sites.find((n) => n.risk == null)
  const resilience = network?.resilience_score
  const siteMix = NODE_KINDS.filter((k) => !isDemand(k)).filter((k) => counts[k]).map((k) => `${counts[k]} ${typeOf(k).plural.toLowerCase()}`)
  const demandMix = NODE_KINDS.filter(isDemand).filter((k) => counts[k]).map((k) => `${counts[k]} ${typeOf(k).plural.toLowerCase()}`)

  if (!previewing && nodes.length === 0) {
    return (
      <>
        <PageHeader title="Digital twin" description="Every supplier, plant, warehouse, retailer and customer in the active network." />
        <Card>
          <EmptyState
            icon={NetworkIcon}
            title={`The active ${SOURCE_LABEL[source?.source]?.toLowerCase() || 'network'} is empty`}
            description="Build a network on the Data tab, or switch back to the preset demo."
            action={
              <Button variant="primary" icon={Database} onClick={() => setTab('data')}>
                Open the Data tab
              </Button>
            }
          />
        </Card>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Digital twin"
        description="Every supplier, plant, warehouse, retailer and customer in the network, with ML-predicted criticality."
        actions={
          <Button variant="primary" iconRight={ArrowRight} onClick={() => setTab('simulate')} disabled={source && !source.runnable}>
            Open Disruption Simulator
          </Button>
        }
      />
      {previewing && (
        <Card className="mb-6 flex flex-wrap items-center gap-3 border-accent/30 bg-accent/5 px-4 py-3">
          <Upload className="h-4 w-4 text-accent" aria-hidden />
          <p className="flex-1 text-sm text-fg-2">
            Previewing your uploaded network ({upload.summary.n_nodes} nodes). It is not active: Simulate, Chaos Finder and Recover still use
            the {SOURCE_LABEL[source?.source]?.toLowerCase() || 'active network'}. Activate it on the Data tab.
          </p>
          <Button size="sm" variant="ghost" onClick={clearUpload}>
            Close preview
          </Button>
        </Card>
      )}
      {source && !source.runnable && !previewing && (
        <InlineError className="mb-6" message="The active network has validation errors, so simulations are disabled. Fix them on the Data tab." />
      )}

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Sites" icon={Building2} value={fmtNum(sites.length)} sub={siteMix.join(' · ') || 'No supply-side sites'} />
        <Stat label="Lanes" icon={NetworkIcon} value={fmtNum(network.edges?.length ?? 0)} sub={demandMix.length ? `${demandMix.join(' · ')} served` : 'No demand points'} />
        <Stat
          label="Demand"
          icon={Boxes}
          value={fmtNum(nodes.reduce((s, n) => s + (n.demand || 0), 0))}
          unit="units/day"
          sub={`Nominal, across ${demandPoints} demand point${demandPoints === 1 ? '' : 's'}`}
        />
        <Stat
          label="Resilience"
          icon={ShieldCheck}
          value={resilience != null ? resilience.toFixed(1) : '-'}
          unit={resilience != null ? '/ 100' : undefined}
          sub={resilience != null ? 'Chaos Finder stress test' : previewing ? 'Not computed for previews' : 'Not available for this network yet'}
          chip={resilience != null && <Badge tone={resilience >= 70 ? 'ok' : resilience >= 40 ? 'warn' : 'bad'} dot>{resilience >= 70 ? 'Strong' : resilience >= 40 ? 'Moderate' : 'Fragile'}</Badge>}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-12">
        <div className="xl:col-span-8">
          <GraphPanel title="Network map" description="Shape, color and icon = node type · ring = status" icon={NetworkIcon} network={network} heightClass="h-[600px]" />
        </div>
        <Card className="xl:col-span-4">
          <CardHeader title="Most critical sites" description="ML-predicted share of demand lost if the site fails" icon={Gauge} />
          <CardBody>
            {critical.length === 0 ? (
              <EmptyState
                icon={Gauge}
                title="No criticality scores"
                description={unscored?.risk_note || 'Add suppliers, plants or warehouses to see which sites matter most.'}
              />
            ) : (
              <ul className="space-y-1">
                {critical.map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => selectNode(n.id)}
                      className="w-full rounded-lg px-2 py-2 text-left transition-colors duration-150 hover:bg-surface-2"
                    >
                      <div className="flex items-center justify-between gap-2 text-sm">
                        <NodeTag node={n} size="sm" />
                        <span className="tabular font-medium text-fg">{fmtPct(n.risk)}</span>
                      </div>
                      <Meter className="mt-2" value={n.risk} max={Math.max(critical[0]?.risk || 1, 0.01)} label={`${n.id} criticality`} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {critical.length > 0 && <p className="mt-3 text-xs text-fg-muted">Select a site to see why (SHAP).</p>}
          </CardBody>
        </Card>
      </div>

      <div className="mt-6">
        <AiAdvisoryPanel />
      </div>
    </>
  )
}
