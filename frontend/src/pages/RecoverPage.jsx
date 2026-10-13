import { useEffect, useMemo, useState } from 'react'
import { Pencil, RefreshCw } from 'lucide-react'
import { useStore } from '../store.js'
import { eventLabel } from '../format.js'
import { peakDisruption, recoveryLanes, targetNodes } from '../lib/disruption.js'
import { useUi } from '../ui.jsx'
import { Badge, Button, EmptyState, InlineError, Panel, SegmentedControl, SkeletonRows, TabPanel, Tabs, useToast } from '../components/ui/index.js'
import Workspace from '../components/layout/Workspace.jsx'
import NetworkCanvas from '../components/canvas/NetworkCanvas.jsx'
import Playbook from '../components/Playbook.jsx'
import { CostScatter, RoiLine, StrategyTable } from '../components/RecoverCompare.jsx'
import { AlternateRoutes, AlternateSuppliers, InventoryActions, ProductionActions } from '../components/AlternatesPanel.jsx'

export default function RecoverPage() {
  const { events, recover, recoverFor, runRecover, loading, errors, setTab, network, source } = useStore()
  const ui = useUi()
  const toast = useToast()
  const runnable = !source || source.runnable
  const [view, setView] = useState('after')
  const [tab, setTabLocal] = useState('map')
  const [picked, setPicked] = useState(null)
  const stale = recover && JSON.stringify(recoverFor) !== JSON.stringify(events)

  useEffect(() => {
    // first visit, a changed scenario, or results dropped because the network changed
    if (runnable && events.length && (!recover || stale) && !loading.recover && !errors.recover) runRecover(events)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recover, runnable])

  const recompute = async () => {
    const res = await runRecover(events)
    if (res) {
      const rec = res.strategies.find((s) => s.recommended)
      toast('Recovery plan updated', { description: rec ? `Recommended: ${rec.name}` : undefined })
    }
  }

  const after = view === 'after'
  const peak = useMemo(() => peakDisruption(network, events), [network, events])
  const rerouted = useMemo(() => recoveryLanes(recover), [recover])
  const planNodes = useMemo(() => (after && recover ? targetNodes([...rerouted]) : null), [after, recover, rerouted])
  const strategies = recover?.strategies ?? []
  const selectedName = picked && strategies.some((s) => s.name === picked) ? picked : strategies.find((s) => s.recommended)?.name
  const selected = strategies.find((s) => s.name === selectedName)

  let content
  if (!runnable) {
    content = (
      <Panel>
        <EmptyState
          title="The active network can't be planned for"
          description="Fix its validation errors first."
          action={<Button onClick={() => (ui.setDataView(source?.source === 'csv' ? 'csv' : 'manual'), setTab('data'))}>Open the Data page</Button>}
        />
      </Panel>
    )
  } else if (errors.recover) {
    content = <InlineError message={errors.recover} onRetry={() => runRecover(events)} />
  } else if (loading.recover && !recover) {
    content = (
      <Panel>
        <SkeletonRows rows={7} label="Optimising recovery strategies" />
      </Panel>
    )
  } else if (!recover) {
    content = (
      <Panel>
        <EmptyState title="No recovery plan yet" description="Build a scenario on the Simulate page, then compute a plan." action={<Button onClick={() => setTab('simulate')}>Open Simulate</Button>} />
      </Panel>
    )
  } else {
    const tabs = [
      { value: 'map', label: 'Plan on the map' },
      { value: 'suppliers', label: 'Alternate suppliers', count: recover.alternate_suppliers.length },
      { value: 'routes', label: 'Alternate routes', count: recover.alternate_routes.length },
      { value: 'inventory', label: 'Inventory', count: recover.inventory_actions.length },
      { value: 'production', label: 'Production', count: recover.production_actions.length },
      { value: 'scatter', label: 'Cost vs unmet' },
    ]
    content = (
      <>
        <RoiLine roi={recover.roi} />
        <Panel className="overflow-hidden">
          <StrategyTable strategies={strategies} selected={selectedName} onSelect={setPicked} />
          {selected && (
            <p className="border-t border-border px-4 py-2.5 text-xs text-fg-2">
              <span className="font-medium text-fg">{selected.name}.</span> {selected.description}
              {!selected.safety_check.passed && <span className="mt-1 block text-bad">Fails the fix-safety check: {selected.safety_check.warning}</span>}
            </p>
          )}
        </Panel>
        <Panel className="overflow-hidden">
          <Tabs idBase="recover" label="Plan details" value={tab} onChange={setTabLocal} className="overflow-x-auto px-4" tabs={tabs} />
          <TabPanel idBase="recover" value={tab}>
            {tab === 'map' && (
              <>
                <div className="flex items-center gap-3 border-b border-border px-4 py-2">
                  <SegmentedControl
                    size="xs"
                    label="Before or after the recovery plan"
                    value={view}
                    onChange={setView}
                    options={[
                      { value: 'before', label: 'Before' },
                      { value: 'after', label: 'After' },
                    ]}
                  />
                  <span className="text-xs text-fg-muted">
                    {after ? 'Disruption at full effect; recovery lanes in the accent color.' : 'Normal operations, before the disruption.'}
                  </span>
                </div>
                <div className="relative h-[460px]">
                  <NetworkCanvas
                    disrupted={after ? peak : null}
                    highlight={planNodes}
                    view3d={{ mode: after ? 'after' : 'baseline', rerouted, disruptedAll: peak }}
                  />
                </div>
              </>
            )}
            {tab === 'suppliers' && <AlternateSuppliers rows={recover.alternate_suppliers} />}
            {tab === 'routes' && <AlternateRoutes rows={recover.alternate_routes} />}
            {tab === 'inventory' && <InventoryActions rows={recover.inventory_actions} />}
            {tab === 'production' && <ProductionActions rows={recover.production_actions} />}
            {tab === 'scatter' && (
              <div className="px-4 py-3">
                <CostScatter strategies={strategies} />
              </div>
            )}
          </TabPanel>
        </Panel>
      </>
    )
  }

  return (
    <div className="flex h-full min-h-[640px] flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-fg-muted">Planning for</span>
        {events.length ? (
          events.map((e, i) => (
            <Badge key={i}>
              {eventLabel(e)} <span className="num text-fg-muted">d{e.start}+{e.duration}</span>
            </Badge>
          ))
        ) : (
          <Badge>No events</Badge>
        )}
        {stale && <span className="text-xs text-warn">Scenario changed since this plan</span>}
        <div className="ml-auto flex items-center gap-2">
          <Button variant="ghost" icon={Pencil} onClick={() => setTab('simulate')}>
            Edit scenario
          </Button>
          <Button variant="primary" icon={RefreshCw} disabled={!runnable || loading.recover || !events.length} onClick={recompute}>
            {loading.recover ? 'Planning…' : stale ? 'Recompute for this scenario' : 'Recompute'}
          </Button>
        </div>
      </div>
      <Workspace className="min-h-0 flex-1" framed={false} inspector={<Playbook />} inspectorLabel="Playbook" mainClassName="overflow-y-auto">
        <div className="space-y-3">{content}</div>
      </Workspace>
    </div>
  )
}
