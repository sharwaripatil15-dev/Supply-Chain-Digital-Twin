import { useEffect } from 'react'
import { useStore } from './store.js'
import AppShell from './components/layout/AppShell.jsx'
import { Card, InlineError, Skeleton } from './components/ui/index.js'
import TwinPage from './pages/TwinPage.jsx'
import WhatIfPage from './pages/WhatIfPage.jsx'
import RecoverPage from './pages/RecoverPage.jsx'
import DataPage from './pages/DataPage.jsx'
import ChaosFinder from './components/ChaosFinder.jsx'

const PAGES = {
  twin: TwinPage,
  whatif: WhatIfPage,
  simulate: WhatIfPage,
  chaos: ChaosFinder,
  recover: RecoverPage,
  data: DataPage,
}

function LoadingShell() {
  return (
    <div role="status" aria-label="Loading digital twin" className="space-y-6">
      <Skeleton className="h-7 w-56" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-[520px]" />
    </div>
  )
}

export default function App() {
  const { tab, network, errors, loadNetwork } = useStore()

  useEffect(() => {
    loadNetwork()
  }, [loadNetwork])

  const Page = PAGES[tab] || TwinPage
  return (
    <AppShell>
      {network ? (
        <Page />
      ) : errors.network ? (
        <Card className="mx-auto mt-16 max-w-xl p-5">
          <p className="mb-3 text-sm font-medium text-fg">Couldn't load the digital twin</p>
          <InlineError message={errors.network} onRetry={loadNetwork} />
        </Card>
      ) : (
        <LoadingShell />
      )}
    </AppShell>
  )
}
