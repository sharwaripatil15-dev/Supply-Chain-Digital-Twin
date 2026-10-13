import { useState } from 'react'
import { CheckCircle2, Copy, Database, FileSpreadsheet, PencilRuler, Sparkles } from 'lucide-react'
import { api, errorMessage } from '../api.js'
import { SOURCE_LABEL, useStore } from '../store.js'
import { NODE_KINDS, typeOf } from '../lib/nodeTypes.js'
import { Badge, Button, Card, CardBody, CardHeader, InlineError, PageHeader, SegmentedControl, useToast } from '../components/ui/index.js'
import CsvUpload from '../components/CsvUpload.jsx'
import SurrogateAccuracy from '../components/SurrogateAccuracy.jsx'
import ForecastChart from '../components/ForecastChart.jsx'
import ManualBuilder from '../components/builder/ManualBuilder.jsx'
import { ShapeThumb, TypeIcon } from '../components/NodeTypeIcon.jsx'

function PresetPanel({ onCopied }) {
  const { source, setSource, importManual, loading } = useStore()
  const toast = useToast()
  const [error, setError] = useState(null)
  const active = source?.source === 'preset'
  const use = async () => {
    const res = await setSource('preset')
    if (res.ok) toast('Preset demo is active', { description: 'Every tab now uses the 16-site demo network' })
    else setError(res.error)
  }
  const copy = async () => {
    try {
      const preset = await api.exportNetwork('preset')
      const res = await importManual(preset)
      if (res.ok) {
        toast('Preset copied into the builder', { description: 'Edit it, then press Apply network' })
        onCopied()
      } else setError(res.error)
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <Card>
      <CardHeader title="Preset demo" description="A 16-site Indian electronics network: suppliers, plants, DCs and customers." icon={Sparkles} />
      <CardBody className="space-y-4">
        <p className="text-sm text-fg-2">
          The curated demo behind the quick-start scenarios (supplier failure, flooded lane, cascading failure). While the{' '}
          <code className="rounded bg-surface-2 px-1 text-xs">USE_MOCK_*</code> flags are on, its results come from the scripted demo
          layer; your own networks always run on the real engine.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon={CheckCircle2} disabled={active || loading.source} onClick={use}>
            {active ? 'Preset is active' : 'Use the preset demo'}
          </Button>
          <Button icon={Copy} onClick={copy} disabled={loading.builder}>
            Copy into the builder
          </Button>
        </div>
        <InlineError message={error} />
      </CardBody>
    </Card>
  )
}

/** Field reference for the five node types (what each one adds to the common fields). */
function TypeReference() {
  return (
    <Card>
      <CardHeader title="Node types" description="Shape + color + icon = type everywhere. Status shows as a ring, never the fill." icon={Database} />
      <CardBody>
        <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
          {NODE_KINDS.map((k) => {
            const t = typeOf(k)
            return (
              <li key={k} className="flex items-start gap-2 rounded-lg border border-border p-2.5">
                <TypeIcon kind={k} size="md" />
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 text-sm font-medium text-fg">
                    {t.label} <ShapeThumb kind={k} className="h-3.5 w-3.5" />
                  </p>
                  <p className="text-xs text-fg-muted">{t.blurb}</p>
                  {t.demand && (
                    <Badge className="mt-1" tone="neutral">
                      demand point
                    </Badge>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </CardBody>
    </Card>
  )
}

export default function DataPage() {
  const { source } = useStore()
  const [view, setView] = useState(() => source?.source || 'preset')
  return (
    <>
      <PageHeader
        title="Data & models"
        description="Choose the network every tab uses (the preset demo, your CSV files, or one you build by hand) and check the models."
      />
      <div className="mb-6 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <SegmentedControl
            label="Network source"
            value={view}
            onChange={setView}
            options={[
              { value: 'preset', label: 'Preset demo', icon: Sparkles },
              { value: 'csv', label: 'CSV upload', icon: FileSpreadsheet },
              { value: 'manual', label: 'Manual builder', icon: PencilRuler },
            ]}
          />
          {source && (
            <span className="flex items-center gap-2 text-xs text-fg-muted">
              Active network:
              <Badge tone={source.runnable ? 'accent' : 'warn'} icon={Database}>
                {SOURCE_LABEL[source.source]}
              </Badge>
              <span className="tabular">v{source.version}</span>
            </span>
          )}
        </div>
        {source?.note && <InlineError message={source.note} />}
        {view === 'preset' && <PresetPanel onCopied={() => setView('manual')} />}
        {view === 'csv' && <CsvUpload />}
        {view === 'manual' && <ManualBuilder />}
      </div>
      <div className="space-y-6">
        <TypeReference />
        <div className="grid gap-6 xl:grid-cols-2">
          <SurrogateAccuracy />
          <ForecastChart />
        </div>
      </div>
    </>
  )
}
