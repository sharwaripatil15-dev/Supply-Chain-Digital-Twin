import { useMemo, useState } from 'react'
import { WeatherProvider, useWeather } from '../weather.jsx'
import { rowsForDay } from '../lib/weather.js'
import { Panel, TabPanel, Tabs } from '../components/ui/index.js'
import NetworkCanvas from '../components/canvas/NetworkCanvas.jsx'
import WeatherPanel from '../components/weather/WeatherPanel.jsx'
import ReroutePanel from '../components/weather/ReroutePanel.jsx'

const AT_RISK = new Set(['high', 'severe'])

function WeatherBody() {
  const w = useWeather()
  const [day, setDay] = useState(0)
  const [tab, setTab] = useState('forecast')
  // lanes and sites at high or severe risk on the chosen day are drawn as disrupted (same encoding as the simulator)
  const disrupted = useMemo(() => {
    const { edges, nodes } = rowsForDay(w.risk, day)
    const pick = (m) => new Set([...m].filter(([, r]) => AT_RISK.has(r.level)).map(([id]) => id))
    return w.risk ? { edges: pick(edges), nodes: pick(nodes) } : null
  }, [w.risk, day])
  return (
    <div className="flex h-full min-h-[640px] gap-3 p-4">
      <Panel className="relative min-w-0 flex-1 overflow-hidden">
        <NetworkCanvas disrupted={disrupted} highlight={disrupted ? [...disrupted.nodes] : null} />
      </Panel>
      <Panel className="flex w-[400px] shrink-0 flex-col overflow-hidden xl:w-[440px]">
        <Tabs idBase="weather" label="Weather" value={tab} onChange={setTab} className="px-4"
          tabs={[{ value: 'forecast', label: 'Route risk' }, { value: 'reroute', label: 'Re-routing' }]} />
        <TabPanel idBase="weather" value={tab} className="min-h-0 flex-1 overflow-y-auto">
          {tab === 'forecast' ? <WeatherPanel day={day} onDay={setDay} /> : <ReroutePanel />}
        </TabPanel>
      </Panel>
    </div>
  )
}

/** Weather and disaster risk on the routes, with re-routing options (the existing weather panels). */
export default function WeatherPage() {
  return (
    <WeatherProvider>
      <WeatherBody />
    </WeatherProvider>
  )
}
