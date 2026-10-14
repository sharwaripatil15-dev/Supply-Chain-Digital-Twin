import { useEffect } from 'react'
import { useStore } from './store.js'
import AppShell from './components/layout/AppShell.jsx'
import { Button, EmptyState, KpiStrip, Panel, Skeleton } from './components/ui/index.js'
import TwinPage from './pages/TwinPage.jsx'
import SimulatePage from './pages/SimulatePage.jsx'
import ChaosPage from './pages/ChaosPage.jsx'
import RecoverPage from './pages/RecoverPage.jsx'
import DataPage from './pages/DataPage.jsx'
import WhatIfPage from './pages/WhatIfPage.jsx'
import InsightsPage from './pages/InsightsPage.jsx'
import ExpansionPage from './pages/ExpansionPage.jsx'
import OverviewPage from './pages/OverviewPage.jsx'
import WeatherPage from './pages/WeatherPage.jsx'

const PAGES = { overview: OverviewPage, weather: WeatherPage, twin: TwinPage, simulate: SimulatePage, chaos: ChaosPage, recover: RecoverPage, whatif: WhatIfPage, insights: InsightsPage, expansion: ExpansionPage, data: DataPage }

/** Placeholder with the same shape as the Twin page (KPI strip + workspace). */
function LoadingShell() {
  return (
    <div role="status" aria-label="Loading the digital twin" className="flex h-full min-h-[560px] flex-col gap-3 p-4">
      <KpiStrip loading items={[{ label: 'Sites' }, { label: 'Lanes' }, { label: 'Demand' }, { label: 'Resilience' }, { label: 'Most critical site' }]} />
      <Panel className="flex min-h-0 flex-1 overflow-hidden">
        <Skeleton className="h-full flex-1 rounded-none" />
        <div className="hidden w-[320px] space-y-3 border-l border-border p-4 xl:block">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      </Panel>
    </div>
  )
}

export default function App() {
  const { tab, network, errors, loadNetwork } = useStore()

  useEffect(() => {
    loadNetwork()
  }, [loadNetwork])

  const Page = PAGES[tab] || OverviewPage
  return (
    <AppShell>
      {network ? (
        <Page />
      ) : errors.network ? (
        <div className="p-4">
          <Panel className="mx-auto mt-16 max-w-md">
            <EmptyState title="Couldn't load the digital twin" description={errors.network} action={<Button variant="primary" onClick={loadNetwork}>Retry</Button>} />
          </Panel>
        </div>
      ) : (
        <LoadingShell />
      )}
    </AppShell>
  )
}
