import { useState } from 'react'
import { useStore } from '../../store.js'
import { TabPanel, Tabs, cn } from '../ui/index.js'
import UtilizationBars from '../UtilizationBars.jsx'
import DelayChart from '../DelayChart.jsx'
import MonteCarloChart from '../MonteCarloChart.jsx'
import EventLog from '../EventLog.jsx'

const TABS = { utilization: UtilizationBars, delay: DelayChart, montecarlo: MonteCarloChart, log: EventLog }

/** Simulation results in tabs under the canvas (not stacked cards). */
export default function SimResults({ className }) {
  const { sim, mc } = useStore()
  const [tab, setTab] = useState('utilization')
  const Body = TABS[tab]
  return (
    <div className={cn('flex min-h-0 flex-col', className)}>
      <Tabs
        idBase="sim-results"
        label="Simulation results"
        value={tab}
        onChange={setTab}
        size="sm"
        className="px-4"
        tabs={[
          { value: 'utilization', label: 'Utilization', count: sim ? sim.bottlenecks.length || null : null },
          { value: 'delay', label: 'Delivery delay' },
          { value: 'montecarlo', label: 'Monte Carlo', count: mc ? `${Math.round(mc.p_shortage * 100)}%` : null },
          { value: 'log', label: 'Event log', count: sim ? sim.log.length : null },
        ]}
      />
      <TabPanel idBase="sim-results" value={tab} className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        <Body />
      </TabPanel>
    </div>
  )
}
