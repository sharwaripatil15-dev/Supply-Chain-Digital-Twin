import { useState } from 'react'
import { CheckCircle2, CircleCheck, Download, FileSpreadsheet, TriangleAlert, Upload } from 'lucide-react'
import { useStore } from '../store.js'
import { Badge, Button, Card, CardBody, CardHeader, InlineError, useToast } from './ui/index.js'

function FilePick({ label, file, onChange }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input
        type="file"
        accept=".csv,text/csv"
        onChange={(e) => onChange(e.target.files?.[0] || null)}
        className="mt-1.5 block w-full text-xs text-fg-2 file:mr-3 file:h-8 file:rounded-md file:border file:border-border file:bg-surface file:px-3 file:text-xs file:font-medium file:text-fg hover:file:bg-surface-2"
      />
      {file && <span className="mt-1 block text-xs text-fg-muted">{(file.size / 1024).toFixed(1)} KB</span>}
    </label>
  )
}

export default function CsvUpload() {
  const { upload, uploadCsv, clearUpload, loading, errors, setTab, source, setSource } = useStore()
  const toast = useToast()
  const [nodes, setNodes] = useState(null)
  const [edges, setEdges] = useState(null)
  const [activate, setActivate] = useState(true)
  const csvActive = source?.source === 'csv'

  const submit = async () => {
    const res = await uploadCsv(nodes, edges, activate)
    if (res) {
      toast(res.activated ? 'Uploaded network is now active' : 'Network uploaded for preview', {
        description: `${res.summary.n_nodes} nodes · ${res.summary.n_edges} lanes${res.warnings.length ? ` · ${res.warnings.length} warning(s)` : ''}`,
      })
    }
  }
  const activateLoaded = async () => {
    const res = await setSource('csv')
    if (res.ok) toast('Uploaded network is now active', { description: 'Every tab now uses it' })
  }

  return (
    <Card>
      <CardHeader
        title="Load your network from CSV"
        description="Upload nodes.csv and edges.csv; files are validated before anything changes."
        icon={FileSpreadsheet}
        actions={csvActive && <Badge tone="ok" dot>Active on every tab</Badge>}
      />
      <CardBody className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <FilePick label="nodes.csv" file={nodes} onChange={setNodes} />
          <FilePick label="edges.csv" file={edges} onChange={setEdges} />
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-fg-muted">
          <Download className="h-3.5 w-3.5" aria-hidden />
          Templates:
          <a className="font-medium text-accent hover:underline" href="/samples/sample_nodes.csv" download>
            sample_nodes.csv
          </a>
          <a className="font-medium text-accent hover:underline" href="/samples/sample_edges.csv" download>
            sample_edges.csv
          </a>
          <span>· kind is one of supplier, factory, warehouse, retailer, customer</span>
        </div>
        <label className="flex items-start gap-2 text-xs text-fg-2">
          <input type="checkbox" className="mt-0.5" checked={activate} onChange={(e) => setActivate(e.target.checked)} />
          Use it as the active network (Twin, Simulate, Chaos Finder and Recover all switch to it). Unchecked = preview on the Twin tab only.
        </label>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon={Upload} disabled={!nodes || !edges || loading.upload} onClick={submit}>
            {loading.upload ? 'Validating…' : activate ? 'Upload and activate' : 'Upload and preview'}
          </Button>
          {source?.csv_loaded && !csvActive && (
            <Button icon={CheckCircle2} onClick={activateLoaded} disabled={loading.source}>
              Activate the last upload
            </Button>
          )}
        </div>
        <InlineError message={errors.upload || errors.source} />
        {upload && (
          <div className="space-y-2 rounded-lg border border-border bg-surface-2/50 p-3 text-xs">
            <div className="flex items-start gap-2 text-fg">
              <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-hidden />
              <span>
                Loaded {upload.summary.n_nodes} nodes and {upload.summary.n_edges} lanes (
                {Object.entries(upload.summary.by_kind)
                  .map(([k, v]) => `${v} ${k}`)
                  .join(', ')}
                ).
              </span>
              {upload.activated && <Badge tone="accent">Active</Badge>}
            </div>
            {upload.warnings.map((w) => (
              <div key={w} className="flex items-start gap-2 text-fg-2">
                <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" aria-hidden />
                {w}
              </div>
            ))}
            <div className="flex gap-2 pt-1">
              <Button size="sm" onClick={() => setTab('twin')}>
                {upload.activated ? 'Open the Twin' : 'Preview on Twin'}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  clearUpload()
                  if (csvActive) await setSource('preset')
                }}
              >
                Back to the preset demo
              </Button>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
