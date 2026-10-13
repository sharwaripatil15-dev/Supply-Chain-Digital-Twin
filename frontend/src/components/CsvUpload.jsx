import { useState } from 'react'
import { CircleCheck, Download, FileSpreadsheet, TriangleAlert, Upload } from 'lucide-react'
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
  const { upload, uploadCsv, clearUpload, loading, errors, setTab } = useStore()
  const toast = useToast()
  const [nodes, setNodes] = useState(null)
  const [edges, setEdges] = useState(null)
  const [activate, setActivate] = useState(false)

  const submit = async () => {
    const res = await uploadCsv(nodes, edges, activate)
    if (res) toast('Network uploaded', { description: `${res.summary.n_nodes} nodes · ${res.summary.n_edges} lanes${res.warnings.length ? ` · ${res.warnings.length} warning(s)` : ''}` })
  }

  return (
    <Card>
      <CardHeader title="Load your network" description="Upload nodes.csv and edges.csv; files are validated before anything changes." icon={FileSpreadsheet} />
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
        </div>
        <label className="flex items-start gap-2 text-xs text-fg-2">
          <input type="checkbox" className="mt-0.5" checked={activate} onChange={(e) => setActivate(e.target.checked)} />
          Use for the live engine (routers with USE_MOCK_*=false). Mock routers always use the demo network.
        </label>
        <Button variant="primary" icon={Upload} disabled={!nodes || !edges || loading.upload} onClick={submit}>
          {loading.upload ? 'Validating…' : 'Upload and preview'}
        </Button>
        <InlineError message={errors.upload} />
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
              {upload.activated && <Badge tone="accent">Live engine</Badge>}
            </div>
            {upload.warnings.map((w) => (
              <div key={w} className="flex items-start gap-2 text-fg-2">
                <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" aria-hidden />
                {w}
              </div>
            ))}
            <div className="flex gap-2 pt-1">
              <Button size="sm" onClick={() => setTab('twin')}>
                Preview on Twin
              </Button>
              <Button size="sm" variant="ghost" onClick={clearUpload}>
                Back to demo network
              </Button>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
