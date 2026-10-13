import { Component, useEffect } from 'react'
import { RefreshCw } from 'lucide-react'
import { useStore } from './store.js'
import AppShell from './components/layout/AppShell.jsx'
import { Button, Card, InlineError, Skeleton } from './components/ui/index.js'
import TwinPage from './pages/TwinPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import WhatIfPage from './pages/WhatIfPage.jsx'
import RecoverPage from './pages/RecoverPage.jsx'
import DataPage from './pages/DataPage.jsx'
import ChaosFinder from './components/ChaosFinder.jsx'

const PAGES = {
  twin: TwinPage,
  dashboard: DashboardPage,
  whatif: WhatIfPage,
  simulate: WhatIfPage,
  chaos: ChaosFinder,
  recover: RecoverPage,
  data: DataPage,
}

class PageErrorBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) {
    return { error }
  }
  componentDidCatch(error, info) {
    console.error('Page render error caught by boundary:', error, info)
  }
  render() {
    if (this.state.error) {
      return (
        <Card className="mx-auto mt-12 max-w-xl p-6 border-bad/30 bg-bad/5">
          <h3 className="text-base font-bold text-fg mb-1">Something went wrong displaying this view</h3>
          <p className="text-xs text-fg-muted mb-4 font-mono">
            {this.state.error.message || String(this.state.error)}
          </p>
          <div className="flex gap-2">
            <Button
              variant="primary"
              size="sm"
              icon={RefreshCw}
              onClick={() => {
                this.setState({ error: null })
                window.location.reload()
              }}
            >
              Reload Page
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                this.setState({ error: null })
              }}
            >
              Try Again
            </Button>
          </div>
        </Card>
      )
    }
    return this.props.children
  }
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
        <PageErrorBoundary key={tab}>
          <Page />
        </PageErrorBoundary>
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
