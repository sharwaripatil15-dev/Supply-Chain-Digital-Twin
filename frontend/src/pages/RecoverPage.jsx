import { useEffect, useMemo, useState } from 'react'
import { Pencil, RefreshCw, Waypoints } from 'lucide-react'
import { useStore } from '../store.js'
import { eventLabel } from '../format.js'
import { peakDisruption, recoveryLanes, targetNodes } from '../lib/disruption.js'
import { Badge, Button, PageHeader, SegmentedControl, useToast } from '../components/ui/index.js'
import RecoverCompare from '../components/RecoverCompare.jsx'
import AlternatesPanel from '../components/AlternatesPanel.jsx'
import Playbook from '../components/Playbook.jsx'
import GraphPanel from '../components/GraphPanel.jsx'

export default function RecoverPage() {
  const { events, recover, recoverFor, runRecover, loading, errors, setTab, network } = useStore()
  const toast = useToast()
  const [view, setView] = useState('after')
  const stale = recover && JSON.stringify(recoverFor) !== JSON.stringify(events)

  useEffect(() => {
    // first visit, a changed scenario, or results dropped because the network changed
    if (events.length && (!recover || stale) && !loading.recover && !errors.recover) runRecover(events)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recover])

  const recompute = async () => {
    const res = await runRecover(events)
    if (res) {
      const rec = res.strategies.find((s) => s.recommended)
      toast('Recovery plan updated', { description: rec ? `Recommended: ${rec.name}` : undefined })
    }
  }

  const after = view === 'after'
  const disrupted = useMemo(() => (after ? peakDisruption(network, events) : null), [after, network, events])
  const rerouted = useMemo(() => recoveryLanes(recover), [recover])
  const planNodes = useMemo(() => (after && recover ? targetNodes([...rerouted]) : null), [after, recover, rerouted])

  return (
    <>
      <PageHeader
        title="Recovery planner"
        description="Optimised recovery strategies, each re-stress-tested so the fix doesn't create a new weak spot."
        actions={
          <>
            <Button icon={Pencil} onClick={() => setTab('simulate')}>
              Edit scenario
            </Button>
            <Button variant="primary" icon={RefreshCw} disabled={loading.recover || !events.length} onClick={recompute}>
              {stale ? 'Recompute for current scenario' : 'Recompute'}
            </Button>
          </>
        }
      />
      <div className="mb-6 flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs text-fg-muted">Planning for</span>
        {events.length ? events.map((e, i) => <Badge key={i}>{eventLabel(e)} · d{e.start} +{e.duration}</Badge>) : <Badge>No events</Badge>}
        {stale && <Badge tone="warn">Scenario changed since this plan</Badge>}
      </div>

      <div className="space-y-6">
        <RecoverCompare />
        {recover && (
          <GraphPanel
            title="Plan on the map"
            description={after ? 'Disruption at full effect, recovery routes in the accent color' : 'Normal operations, before the disruption'}
            icon={Waypoints}
            heightClass="h-[520px]"
            disrupted={disrupted}
            highlight={planNodes}
            actions={
              <SegmentedControl
                size="sm"
                label="Before or after the recovery plan"
                value={view}
                onChange={setView}
                options={[
                  { value: 'before', label: 'Before' },
                  { value: 'after', label: 'After' },
                ]}
              />
            }
            view3d={{ mode: after ? 'after' : 'baseline', rerouted }}
          />
        )}
        <AlternatesPanel />
        <Playbook />
      </div>
    </>
  )
}
