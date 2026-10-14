import { ScanSearch } from 'lucide-react'
import { useStore } from '../store.js'
import { fmtNum, fmtPct } from '../format.js'
import { NODE_KINDS, isDemand, typeOf } from '../lib/nodeTypes.js'
import { useUi } from '../ui.jsx'
import { Button, EmptyState, KpiStrip, Meter, Notice, Panel, SectionLabel } from '../components/ui/index.js'
import Workspace, { InspectorPanel } from '../components/layout/Workspace.jsx'
import NetworkCanvas from '../components/canvas/NetworkCanvas.jsx'
import { NodeTag, TypeIcon } from '../components/NodeTypeIcon.jsx'

const resilienceTone = (r) => (r == null ? null : r >= 70 ? 'ok' : r >= 40 ? 'warn' : 'bad')
const resilienceWord = (r) => (r == null ? '' : r >= 70 ? 'Strong' : r >= 40 ? 'Moderate' : 'Fragile')

function Overview({ network, counts, critical, unscored }) {
  const { selectNode } = useStore()
  return (
    <InspectorPanel title="Network" meta={`${network.nodes.length} nodes · ${network.edges.length} lanes`}>
      <div className="space-y-5 px-4 py-3">
        <section>
          <SectionLabel className="mb-2">Composition</SectionLabel>
          <ul className="space-y-1.5">
            {NODE_KINDS.filter((k) => counts[k]).map((k) => (
              <li key={k} className="flex items-center gap-2 text-sm">
                <TypeIcon kind={k} size="xs" />
                <span className="flex-1 text-fg-2">{typeOf(k).plural}</span>
                <span className="num text-xs text-fg">{counts[k]}</span>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <SectionLabel>Most critical sites</SectionLabel>
          <p className="mb-2 mt-1 text-xs text-fg-muted">Predicted share of demand lost if the site fails.</p>
          {critical.length === 0 ? (
            <p className="text-xs text-fg-muted">{unscored?.risk_note || 'No supply-side sites to score yet.'}</p>
          ) : (
            <ol className="-mx-2">
              {critical.map((n, i) => (
                <li key={n.id}>
                  <button type="button" onClick={() => selectNode(n.id)} className="w-full rounded-md px-2 py-1.5 text-left transition-colors duration-150 hover:bg-raised">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="num w-4 text-2xs text-fg-muted">{i + 1}</span>
                      <NodeTag node={n} className="min-w-0 flex-1" />
                      <span className="num text-xs text-fg">{fmtPct(n.risk)}</span>
                    </div>
                    <div className="pl-6 pt-1.5">
                      <Meter value={n.risk} max={Math.max(critical[0]?.risk || 1, 0.01)} tone={i === 0 ? 'accent' : 'muted'} label={`${n.id} criticality`} />
                    </div>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </InspectorPanel>
  )
}

export default function TwinPage() {
  const store = useStore()
  const { upload, clearUpload, setTab, source, runAnalysis, loading } = store
  const ui = useUi()
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
  const siteMix = NODE_KINDS.filter((k) => !isDemand(k) && counts[k]).map((k) => `${counts[k]} ${typeOf(k).plural.toLowerCase()}`)
  const openBuilder = () => {
    ui.setDataView('manual')
    setTab('data')
  }

  if (!previewing && nodes.length === 0) {
    return (
      <div className="p-4">
        <Panel className="mx-auto mt-10 max-w-lg">
          <EmptyState
            title="The active network is empty"
            description="Add sites and lanes in the network builder, or switch back to the preset demo on the Data page."
            action={
              <Button variant="primary" onClick={openBuilder}>
                Open the network builder
              </Button>
            }
          />
        </Panel>
      </div>
    )
  }

  const kpis = [
    { key: 'sites', label: 'Sites', value: fmtNum(sites.length), sub: siteMix.join(' · ') || 'No supply-side sites' },
    { key: 'lanes', label: 'Lanes', value: fmtNum(network.edges?.length ?? 0), sub: `${demandPoints} demand point${demandPoints === 1 ? '' : 's'} served` },
    { key: 'demand', label: 'Demand', value: fmtNum(nodes.reduce((s, n) => s + (n.demand || 0), 0)), unit: 'units/day', sub: 'Nominal' },
    {
      key: 'res', label: 'Resilience', value: resilience != null ? resilience.toFixed(1) : null, unit: '/ 100',
      sub: resilience != null ? resilienceWord(resilience) : previewing ? 'Not computed for previews' : 'Not available yet', status: resilienceTone(resilience),
    },
    {
      key: 'crit', label: 'Most critical site', value: critical[0] ? fmtPct(critical[0].risk) : null,
      sub: critical[0] ? `${critical[0].id} ${critical[0].name || ''}` : 'Not scored', title: 'Predicted share of demand lost if this site fails',
    },
  ]

  return (
    <div className="flex h-full min-h-[600px] flex-col gap-3 p-4">
      {previewing && (
        <Notice action={<Button size="sm" variant="ghost" onClick={clearUpload}>Close preview</Button>}>
          Previewing an uploaded network ({upload.summary.n_nodes} nodes). It is not active; activate it on the Data page.
        </Notice>
      )}
      {source && !source.runnable && !previewing && (
        <Notice action={<Button size="sm" variant="ghost" onClick={openBuilder}>Open builder</Button>}>
          The active network has validation errors; simulations are off until they are fixed.
        </Notice>
      )}
      <div className="flex items-start gap-3">
        <KpiStrip items={kpis} className="min-w-0 flex-1" />
        {!previewing && (
          <Button
            variant="primary"
            icon={ScanSearch}
            className="h-auto self-stretch px-4"
            disabled={(source && !source.runnable) || loading.analysis}
            title="Find bottlenecks and pain points, with tested fixes"
            onClick={() => {
              runAnalysis()
              setTab('insights')
            }}
          >
            Analyze
          </Button>
        )}
      </div>
      <Workspace className="min-h-0 flex-1" inspector={<Overview network={network} counts={counts} critical={critical} unscored={unscored} />}>
        <NetworkCanvas network={network} />
      </Workspace>
    </div>
  )
}
