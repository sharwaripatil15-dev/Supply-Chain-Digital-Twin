import { useState } from 'react'
import { Upload } from 'lucide-react'
import { useStore } from '../store.js'
import { Button, Checkbox, InlineError, Panel, PanelHeader, StatusDot, useToast } from './ui/index.js'

function FilePick({ id, label, file, onChange }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-fg-2">
        {label}
      </label>
      <input
        id={id}
        type="file"
        accept=".csv,text/csv"
        onChange={(e) => onChange(e.target.files?.[0] || null)}
        className="block w-full text-xs text-fg-2 file:mr-3 file:h-8 file:cursor-pointer file:rounded-md file:border file:border-solid file:border-border-strong file:bg-surface file:px-3 file:text-xs file:font-medium file:text-fg hover:file:bg-raised"
      />
      {file && <span className="num mt-1 block text-2xs text-fg-muted">{(file.size / 1024).toFixed(1)} KB</span>}
    </div>
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
      toast(res.activated ? 'Uploaded network is active' : 'Network uploaded for preview', {
        description: `${res.summary.n_nodes} nodes · ${res.summary.n_edges} lanes${res.warnings.length ? ` · ${res.warnings.length} warning(s)` : ''}`,
      })
    }
  }
  const activateLoaded = async () => {
    const res = await setSource('csv')
    if (res.ok) toast('Uploaded network is active', { description: 'Every page now uses it' })
  }

  return (
    <Panel className="max-w-4xl">
      <PanelHeader title="Upload CSV" meta="nodes.csv + edges.csv, validated before anything changes" actions={csvActive && <StatusDot status="ok" label="Active" />} />
      <div className="space-y-4 px-4 py-3">
        <div className="grid max-w-3xl gap-4 sm:grid-cols-2">
          <FilePick id="csv-nodes" label="nodes.csv" file={nodes} onChange={setNodes} />
          <FilePick id="csv-edges" label="edges.csv" file={edges} onChange={setEdges} />
        </div>
        <p className="text-xs text-fg-muted">
          Templates:{' '}
          <a className="text-fg underline underline-offset-2 hover:text-accent" href="/samples/sample_nodes.csv" download>
            sample_nodes.csv
          </a>
          ,{' '}
          <a className="text-fg underline underline-offset-2 hover:text-accent" href="/samples/sample_edges.csv" download>
            sample_edges.csv
          </a>
          . <span className="num">kind</span> is supplier, factory, warehouse, retailer or customer.
        </p>
        <Checkbox checked={activate} onChange={(e) => setActivate(e.target.checked)} label="Make it the active network for every page (unchecked: preview on the Twin only)" />
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon={Upload} disabled={!nodes || !edges || loading.upload} onClick={submit}>
            {loading.upload ? 'Validating…' : activate ? 'Upload and activate' : 'Upload and preview'}
          </Button>
          {source?.csv_loaded && !csvActive && (
            <Button onClick={activateLoaded} disabled={loading.source}>
              Activate the last upload
            </Button>
          )}
        </div>
        <InlineError message={errors.upload || errors.source} />
        {upload && (
          <div className="space-y-1.5 border-t border-border pt-3 text-xs">
            <StatusDot
              status="ok"
              textClassName="text-fg"
              label={`Loaded ${upload.summary.n_nodes} nodes and ${upload.summary.n_edges} lanes (${Object.entries(upload.summary.by_kind)
                .map(([k, v]) => `${v} ${k}`)
                .join(', ')})${upload.activated ? ', active' : ''}.`}
            />
            {upload.warnings.map((w) => (
              <p key={w} className="flex items-start gap-1.5 text-fg-2">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warn" aria-hidden />
                {w}
              </p>
            ))}
            <div className="flex gap-2 pt-1.5">
              <Button size="sm" onClick={() => setTab('twin')}>
                {upload.activated ? 'Open the Twin' : 'Preview on the Twin'}
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
      </div>
    </Panel>
  )
}
