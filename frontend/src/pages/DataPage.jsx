import { useState } from 'react'
import { Copy } from 'lucide-react'
import { api, errorMessage } from '../api.js'
import { SOURCE_LABEL, useStore } from '../store.js'
import { useUi } from '../ui.jsx'
import { Button, InlineError, Panel, PanelHeader, SegmentedControl, StatusDot, TabPanel, Tabs, useToast } from '../components/ui/index.js'
import CsvUpload from '../components/CsvUpload.jsx'
import SurrogateAccuracy from '../components/SurrogateAccuracy.jsx'
import ScenarioModel from '../components/ScenarioModel.jsx'
import SyntheticNetworks from '../components/SyntheticNetworks.jsx'
import ForecastChart from '../components/ForecastChart.jsx'
import ManualBuilder from '../components/builder/ManualBuilder.jsx'

function PresetPanel({ onCopied }) {
  const { source, setSource, importManual, loading } = useStore()
  const toast = useToast()
  const [error, setError] = useState(null)
  const active = source?.source === 'preset'
  const use = async () => {
    const res = await setSource('preset')
    if (res.ok) toast('Preset demo is active', { description: 'Every page now uses the 16-site demo network' })
    else setError(res.error)
  }
  const copy = async () => {
    try {
      const preset = await api.exportNetwork('preset')
      const res = await importManual(preset)
      if (res.ok) {
        toast('Preset copied into the builder', { description: 'Edit it, then apply it' })
        onCopied()
      } else setError(res.error)
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <Panel className="max-w-4xl">
      <PanelHeader title="Preset demo" meta="16 sites · Indian electronics network" />
      <div className="space-y-3 px-4 py-3">
        <p className="max-w-2xl text-sm text-fg-2">
          The curated network behind the demo scenarios. While the <span className="num text-xs">USE_MOCK_*</span> flags are on, its results come from the
          scripted demo layer; uploaded and hand-built networks always run on the real engine.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {active ? (
            <StatusDot status="ok" label="Active on every page" />
          ) : (
            <Button variant="primary" disabled={loading.source} onClick={use}>
              Use the preset demo
            </Button>
          )}
          <Button icon={Copy} onClick={copy} disabled={loading.builder}>
            Copy into the builder
          </Button>
        </div>
        <InlineError message={error} />
      </div>
    </Panel>
  )
}

export default function DataPage() {
  const { source } = useStore()
  const ui = useUi()
  const [section, setSection] = useState('network')
  const view = ui.dataView || source?.source || 'preset'
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1680px] space-y-4 p-4">
        <Tabs
          idBase="data"
          label="Data"
          value={section}
          onChange={setSection}
          tabs={[
            { value: 'network', label: 'Network source' },
            { value: 'models', label: 'Models' },
          ]}
        />
        <TabPanel idBase="data" value={section}>
          {section === 'network' ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <SegmentedControl
                  size="sm"
                  label="Network source"
                  value={view}
                  onChange={ui.setDataView}
                  options={[
                    { value: 'preset', label: 'Preset demo' },
                    { value: 'csv', label: 'CSV upload' },
                    { value: 'manual', label: 'Manual builder' },
                  ]}
                />
                {source && (
                  <span className="flex items-center gap-1.5 text-xs text-fg-muted">
                    Active:
                    <StatusDot status={source.runnable ? 'ok' : 'warn'} label={SOURCE_LABEL[source.source]} textClassName="text-fg" />
                    <span className="num">v{source.version}</span>
                  </span>
                )}
              </div>
              {source?.note && <InlineError message={source.note} />}
              {view === 'preset' && (
                <>
                  <PresetPanel onCopied={() => ui.setDataView('manual')} />
                  <SyntheticNetworks onLoaded={() => ui.setDataView('manual')} />
                </>
              )}
              {view === 'csv' && <CsvUpload />}
              {view === 'manual' && <ManualBuilder />}
            </div>
          ) : (
            <div className="grid gap-3 xl:grid-cols-2">
              <SurrogateAccuracy />
              <ForecastChart />
              <ScenarioModel />
            </div>
          )}
        </TabPanel>
      </div>
    </div>
  )
}
