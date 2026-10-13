import { useMemo } from 'react'
import { Activity } from 'lucide-react'
import { useStore } from '../store.js'
import { disruptionForDay } from '../lib/disruption.js'
import { PageHeader } from '../components/ui/index.js'
import KpiCards from '../components/KpiCards.jsx'
import ScenarioPanel from '../components/ScenarioPanel.jsx'
import GraphPanel from '../components/GraphPanel.jsx'
import DaySlider from '../components/DaySlider.jsx'
import UtilizationBars from '../components/UtilizationBars.jsx'
import DelayChart from '../components/DelayChart.jsx'
import EventLog from '../components/EventLog.jsx'
import MonteCarloChart from '../components/MonteCarloChart.jsx'
import RiskPredictPanel from '../components/RiskPredictPanel.jsx'

export default function SimulatePage() {
  const { sim, day, events, network } = useStore()
  const row = sim ? sim.timeline[day] || sim.timeline[0] : null
  const statuses = row?.node_status ?? null
  const disrupted = useMemo(() => (sim ? disruptionForDay(network, events, day, statuses) : null), [sim, network, events, day, statuses])

  return (
    <>
      <PageHeader title="Disruption simulator" description="Throw disruptions at the network and watch the ripple travel day by day." />
      <KpiCards />
      <div className="mt-6 grid gap-6 xl:grid-cols-12">
        <div className="xl:col-span-4 2xl:col-span-3 space-y-6">
          <ScenarioPanel />
          <RiskPredictPanel />
        </div>
        <div className="space-y-6 xl:col-span-8 2xl:col-span-9">
          <GraphPanel
            title="Network state"
            description={sim ? `Day ${row.day} of ${sim.timeline.length - 1}` : 'Run a scenario to color nodes by status'}
            icon={Activity}
            statuses={statuses}
            utilization={row?.utilization ?? null}
            disrupted={disrupted}
            heightClass="h-[520px]"
            footer={sim && <DaySlider />}
          />
          <div className="grid gap-6 2xl:grid-cols-2">
            <UtilizationBars />
            <DelayChart />
          </div>
          <div className="grid gap-6 2xl:grid-cols-2">
            <EventLog />
            <MonteCarloChart />
          </div>
        </div>
      </div>
    </>
  )
}

