import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  CheckCircle2, Copy, Download, Eraser, FileJson, FileSpreadsheet, Plus, Redo2, RotateCcw, Route, Search, Trash2, Undo2, Upload, Wand2,
} from 'lucide-react'
import { api, errorMessage } from '../../api.js'
import { useStore } from '../../store.js'
import { fmtNum } from '../../format.js'
import { NODE_KINDS, isDemand, typeOf } from '../../lib/nodeTypes.js'
import { duplicateNode } from '../../lib/nodeForm.js'
import { downloadText, readFileText } from '../../lib/download.js'
import { Badge, Button, Card, CardBody, ConfirmDialog, EmptyState, InlineError, SegmentedControl, Skeleton, Table, Td, Th, Tr, cn, useToast } from '../ui/index.js'
import { NodeTag, TypeIcon } from '../NodeTypeIcon.jsx'
import BuilderMap from './BuilderMap.jsx'
import NodeForm, { TypePicker } from './NodeForm.jsx'
import EdgeForm from './EdgeForm.jsx'
import ValidationPanel from './ValidationPanel.jsx'

const lanesOf = (edges, ids) => edges.filter((e) => ids.includes(e.source) || ids.includes(e.target))

function Toolbar({ children }) {
  return <div className="flex flex-wrap items-center gap-1.5">{children}</div>
}

function Divider() {
  return <span className="mx-1 h-5 w-px bg-border" aria-hidden />
}

function NodeTable({ nodes, selection, checked, onCheck, onCheckAll, onOpen, onDuplicate, onDelete }) {
  const allChecked = nodes.length > 0 && nodes.every((n) => checked.has(n.id))
  return (
    <Table label="Nodes" className="max-h-[440px]">
      <thead>
        <tr>
          <Th className="w-8">
            <input type="checkbox" aria-label="Select all nodes" checked={allChecked} onChange={(e) => onCheckAll(e.target.checked)} />
          </Th>
          <Th>Node</Th>
          <Th>City</Th>
          <Th numeric>Capacity</Th>
          <Th numeric>Demand</Th>
          <Th numeric>Stock</Th>
          <Th className="w-20">
            <span className="sr-only">Actions</span>
          </Th>
        </tr>
      </thead>
      <tbody>
        {nodes.map((n) => (
          <Tr key={n.id} selected={selection?.type === 'node' && selection.id === n.id} onClick={() => onOpen(n)} className={n.status === 'inactive' ? 'opacity-60' : ''}>
            <Td onClick={(e) => e.stopPropagation()}>
              <input type="checkbox" aria-label={`Select ${n.id}`} checked={checked.has(n.id)} onChange={(e) => onCheck(n.id, e.target.checked)} />
            </Td>
            <Td>
              <NodeTag node={n} nameClassName="max-w-[11rem]" />
              <div className="mt-0.5 flex gap-1 text-xs text-fg-muted">
                {typeOf(n.kind).label}
                {n.is_backup && <Badge tone="accent">backup</Badge>}
                {n.status === 'inactive' && <Badge>inactive</Badge>}
              </div>
            </Td>
            <Td className="max-w-[9rem] truncate text-fg-2">{n.city || '-'}</Td>
            <Td numeric>{fmtNum(n.kind === 'factory' && n.production_capacity ? n.production_capacity : n.capacity)}</Td>
            <Td numeric>{isDemand(n.kind) ? fmtNum(n.daily_demand) : '-'}</Td>
            <Td numeric>{fmtNum((n.stock || 0) + (n.kind === 'retailer' ? n.shelf_stock || 0 : 0))}</Td>
            <Td className="text-right" onClick={(e) => e.stopPropagation()}>
              <span className="inline-flex">
                <Button size="icon" variant="ghost" icon={Copy} aria-label={`Duplicate ${n.id}`} title="Duplicate" onClick={() => onDuplicate(n)} />
                <Button size="icon" variant="danger" icon={Trash2} aria-label={`Delete ${n.id}`} title="Delete" onClick={() => onDelete([n.id])} />
              </span>
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

function EdgeTable({ edges, selection, checked, onCheck, onCheckAll, onOpen, onDelete }) {
  const allChecked = edges.length > 0 && edges.every((e) => checked.has(e.id))
  return (
    <Table label="Lanes" className="max-h-[440px]">
      <thead>
        <tr>
          <Th className="w-8">
            <input type="checkbox" aria-label="Select all lanes" checked={allChecked} onChange={(e) => onCheckAll(e.target.checked)} />
          </Th>
          <Th>Lane</Th>
          <Th>Mode</Th>
          <Th numeric>km</Th>
          <Th numeric>Lead</Th>
          <Th numeric>Cap/day</Th>
          <Th numeric>₹/unit</Th>
          <Th numeric>CO₂</Th>
          <Th className="w-12">
            <span className="sr-only">Actions</span>
          </Th>
        </tr>
      </thead>
      <tbody>
        {edges.map((e) => (
          <Tr key={e.id} selected={selection?.type === 'edge' && selection.id === e.id} onClick={() => onOpen(e)} className={e.status === 'inactive' ? 'opacity-60' : ''}>
            <Td onClick={(ev) => ev.stopPropagation()}>
              <input type="checkbox" aria-label={`Select lane ${e.id}`} checked={checked.has(e.id)} onChange={(ev) => onCheck(e.id, ev.target.checked)} />
            </Td>
            <Td>
              <NodeTag id={`${e.source}->${e.target}`} />
              <div className="text-xs text-fg-muted">{e.id}</div>
            </Td>
            <Td className="capitalize text-fg-2">{e.mode}</Td>
            <Td numeric>{fmtNum(e.distance_km)}</Td>
            <Td numeric>{fmtNum(e.lead, 1)} d</Td>
            <Td numeric>{fmtNum(e.capacity)}</Td>
            <Td numeric>{fmtNum(e.cost, 1)}</Td>
            <Td numeric>{fmtNum(e.co2, 2)}</Td>
            <Td className="text-right" onClick={(ev) => ev.stopPropagation()}>
              <Button size="icon" variant="danger" icon={Trash2} aria-label={`Delete lane ${e.id}`} title="Delete" onClick={() => onDelete([e.id])} />
            </Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

/**
 * Manual network builder. The server holds the manual network (every edit is saved and validated there); undo/redo
 * restore snapshots through the import endpoint. "Apply network" makes it the active source for every tab.
 */
export default function ManualBuilder() {
  const store = useStore()
  const { manual, loadManual, loading, errors, source, builderSelection: selection, selectBuilder, history } = store
  const toast = useToast()
  const [panel, setPanel] = useState(null) // { type: 'pick' } | { type: 'node', node?, kind? } | { type: 'edge', edge?, source? }
  const [panelKey, setPanelKey] = useState(0)
  const [table, setTable] = useState('nodes')
  const [query, setQuery] = useState('')
  const [kindFilter, setKindFilter] = useState('all')
  const [checked, setChecked] = useState(() => new Set())
  const [confirm, setConfirm] = useState(null)
  const [picking, setPicking] = useState(false)
  const [picked, setPicked] = useState(null)
  const [pin, setPin] = useState(null)
  const [actionError, setActionError] = useState(null)
  const fileRef = useRef(null)
  const busy = Boolean(loading.builder || loading.source)
  const cancelConfirm = useCallback(() => setConfirm(null), [])

  useEffect(() => {
    if (!manual && !loading.manual) loadManual()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const nodes = useMemo(() => manual?.nodes ?? [], [manual])
  const edges = useMemo(() => manual?.edges ?? [], [manual])
  const edgeIds = useMemo(() => new Set(edges.map((e) => e.id)), [edges])
  const takenIds = useMemo(() => nodes.map((n) => n.id), [nodes])
  const validation = manual?.validation
  const isActive = source?.source === 'manual'
  const canApply = Boolean(validation?.runnable) && nodes.length > 0

  const open = useCallback(
    (next) => {
      setPanel(next)
      setPanelKey((k) => k + 1)
      setPicking(false)
      setPicked(null)
      setPin(null)
      if (next?.node) selectBuilder({ type: 'node', id: next.node.id })
      else if (next?.edge) selectBuilder({ type: 'edge', id: next.edge.id })
    },
    [selectBuilder],
  )
  const close = () => {
    setPanel(null)
    setPicking(false)
    setPin(null)
  }

  // Map or validation link -> open that item.
  const goTo = useCallback(
    (ref) => {
      const node = nodes.find((n) => n.id === ref)
      if (node) {
        setTable('nodes')
        return open({ type: 'node', node })
      }
      const edge = edges.find((e) => e.id === ref)
      if (edge) {
        setTable('lanes')
        open({ type: 'edge', edge })
      }
    },
    [nodes, edges, open],
  )
  const onMapSelect = (sel) => {
    if (!sel) return selectBuilder(null)
    goTo(sel.id)
  }

  const filteredNodes = nodes.filter((n) => {
    if (kindFilter !== 'all' && n.kind !== kindFilter) return false
    const q = query.trim().toLowerCase()
    return !q || [n.id, n.name, n.city].some((v) => String(v || '').toLowerCase().includes(q))
  })
  const filteredEdges = edges.filter((e) => {
    const q = query.trim().toLowerCase()
    const kinds = [nodes.find((n) => n.id === e.source)?.kind, nodes.find((n) => n.id === e.target)?.kind]
    if (kindFilter !== 'all' && !kinds.includes(kindFilter)) return false
    return !q || [e.id, e.source, e.target, e.mode].some((v) => String(v || '').toLowerCase().includes(q))
  })

  const after = (res, okMessage, description) => {
    if (res?.ok) {
      setActionError(null)
      if (okMessage) toast(okMessage, { description })
    } else if (res) setActionError(res.error)
    return res
  }

  // ------------------------------------------------ actions
  const saveNode = async (payload) => {
    const editing = panel?.node
    const res = editing ? await store.updateNode(editing.id, payload) : await store.createNode(payload)
    if (res.ok) {
      const saved = res.data?.node
      toast(editing ? `Saved ${editing.id}` : `Added ${saved?.id ?? 'node'}`, { description: saved?.name })
      if (saved) selectBuilder({ type: 'node', id: saved.id })
      close()
    }
    return res
  }
  const saveEdge = async (payload) => {
    const editing = panel?.edge
    const res = editing ? await store.updateEdge(editing.id, payload) : await store.createEdge(payload)
    if (res.ok) {
      const saved = res.data?.edge
      toast(editing ? `Saved lane ${editing.id}` : `Added lane ${saved?.id ?? ''}`, { description: saved ? `${saved.source} → ${saved.target}` : undefined })
      if (saved) selectBuilder({ type: 'edge', id: saved.id })
      close()
    }
    return res
  }
  const duplicate = async (node) => {
    const res = await store.createNode(duplicateNode(node))
    if (after(res, `Duplicated ${node.id}`, res?.data?.node ? `New node ${res.data.node.id}` : undefined)?.ok && res.data?.node) {
      open({ type: 'node', node: res.data.node })
    }
  }
  const askDeleteNodes = (ids) => {
    const lanes = lanesOf(edges, ids)
    setConfirm({
      title: ids.length === 1 ? `Delete ${ids[0]}?` : `Delete ${ids.length} nodes?`,
      confirmLabel: lanes.length ? `Delete node${ids.length > 1 ? 's' : ''} and ${lanes.length} lane${lanes.length === 1 ? '' : 's'}` : 'Delete',
      body: (
        <>
          <div className="flex flex-wrap gap-1.5">
            {ids.map((id) => (
              <NodeTag key={id} id={id} node={nodes.find((n) => n.id === id)} />
            ))}
          </div>
          {lanes.length > 0 ? (
            <>
              <p className="mt-3">These lanes will also be removed:</p>
              <ul className="mt-1.5 max-h-40 space-y-1 overflow-auto">
                {lanes.map((e) => (
                  <li key={e.id} className="flex items-center gap-2 text-xs">
                    <span className="tabular text-fg-muted">{e.id}</span>
                    <NodeTag id={`${e.source}->${e.target}`} />
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mt-3 text-fg-muted">No lanes are connected.</p>
          )}
          <p className="mt-3 text-xs text-fg-muted">You can undo this.</p>
        </>
      ),
      onConfirm: async () => {
        const res = await store.deleteNodes(ids)
        setConfirm(null)
        if (after(res, ids.length === 1 ? `Deleted ${ids[0]}` : `Deleted ${ids.length} nodes`, lanes.length ? `${lanes.length} connected lane(s) removed` : undefined)?.ok) {
          setChecked(new Set())
          if (panel?.node && ids.includes(panel.node.id)) close()
          selectBuilder(null)
        }
      },
    })
  }
  const askDeleteEdges = (ids) =>
    setConfirm({
      title: ids.length === 1 ? `Delete lane ${ids[0]}?` : `Delete ${ids.length} lanes?`,
      confirmLabel: 'Delete',
      body: (
        <ul className="space-y-1">
          {ids.map((id) => {
            const e = edges.find((x) => x.id === id)
            return (
              <li key={id} className="flex items-center gap-2 text-xs">
                <span className="tabular text-fg-muted">{id}</span>
                {e && <NodeTag id={`${e.source}->${e.target}`} />}
              </li>
            )
          })}
        </ul>
      ),
      onConfirm: async () => {
        const res = await store.deleteEdges(ids)
        setConfirm(null)
        if (after(res, ids.length === 1 ? `Deleted lane ${ids[0]}` : `Deleted ${ids.length} lanes`)?.ok) {
          setChecked(new Set())
          if (panel?.edge && ids.includes(panel.edge.id)) close()
        }
      },
    })

  const apply = async () => {
    const res = await store.setSource('manual')
    if (res.ok) {
      setActionError(null)
      toast('Manual network applied', { description: `${nodes.length} nodes · ${edges.length} lanes are now used by every tab` })
    } else setActionError(res.error)
  }
  const startFromPreset = async () => {
    try {
      const preset = await api.exportNetwork('preset')
      after(await store.importManual(preset), 'Preset copied into the builder', `${preset.nodes.length} nodes · ${preset.edges.length} lanes`)
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  const exportJson = async () => {
    try {
      const data = await api.exportNetwork('manual')
      downloadText(`aegis-network-v${data.version}.json`, JSON.stringify(data, null, 2), 'application/json')
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  const exportCsv = async () => {
    try {
      const [nodesCsv, edgesCsv] = await Promise.all([api.exportCsv('nodes'), api.exportCsv('edges')])
      downloadText('nodes.csv', nodesCsv, 'text/csv')
      setTimeout(() => downloadText('edges.csv', edgesCsv, 'text/csv'), 300)
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  const importJson = async (file) => {
    if (!file) return
    try {
      const parsed = JSON.parse(await readFileText(file))
      if (!Array.isArray(parsed?.nodes) || !Array.isArray(parsed?.edges)) throw new Error('This file has no "nodes" and "edges" lists.')
      after(await store.importManual({ nodes: parsed.nodes, edges: parsed.edges }), `Imported ${file.name}`, `${parsed.nodes.length} nodes · ${parsed.edges.length} lanes`)
    } catch (err) {
      setActionError(err instanceof SyntaxError ? `${file.name} is not valid JSON.` : err.message || errorMessage(err))
    }
  }
  const travel = async (dir) => {
    const res = await store[dir]()
    if (res) after(res, dir === 'undo' ? `Undid: ${res.label}` : `Redid: ${res.label}`)
  }

  // ------------------------------------------------ render
  if (!manual) {
    return (
      <Card>
        <CardBody>
          {errors.manual ? <InlineError message={errors.manual} onRetry={loadManual} /> : <Skeleton className="h-64 w-full" />}
        </CardBody>
      </Card>
    )
  }

  const checkedList = [...checked].filter((id) => (table === 'nodes' ? nodes.some((n) => n.id === id) : edgeIds.has(id)))
  const lastUndo = history.past[history.past.length - 1]
  const lastRedo = history.future[history.future.length - 1]

  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="space-y-3">
          <Toolbar>
            <Button variant="primary" icon={CheckCircle2} disabled={!canApply || busy} onClick={apply} title={canApply ? 'Use this network on every tab' : 'Fix the errors first'}>
              {isActive ? 'Re-apply network' : 'Apply network'}
            </Button>
            {isActive ? <Badge tone="ok" dot>Active on every tab</Badge> : <Badge>Not active</Badge>}
            <Divider />
            <Button size="sm" icon={Plus} onClick={() => open({ type: 'pick' })} disabled={busy}>
              Add node
            </Button>
            <Button size="sm" icon={Route} onClick={() => open({ type: 'edge' })} disabled={busy || nodes.length < 2}>
              Add lane
            </Button>
            <Divider />
            <Button size="sm" variant="ghost" icon={Undo2} onClick={() => travel('undo')} disabled={busy || !lastUndo} title={lastUndo ? `Undo: ${lastUndo.label}` : 'Nothing to undo'}>
              Undo
            </Button>
            <Button size="sm" variant="ghost" icon={Redo2} onClick={() => travel('redo')} disabled={busy || !lastRedo} title={lastRedo ? `Redo: ${lastRedo.label}` : 'Nothing to redo'}>
              Redo
            </Button>
            <Divider />
            <Button size="sm" variant="ghost" icon={Upload} onClick={() => fileRef.current?.click()} disabled={busy}>
              Import JSON
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".json,application/json"
              className="hidden"
              onChange={(e) => {
                importJson(e.target.files?.[0])
                e.target.value = ''
              }}
            />
            <Button size="sm" variant="ghost" icon={FileJson} onClick={exportJson} disabled={busy || !nodes.length}>
              Export JSON
            </Button>
            <Button size="sm" variant="ghost" icon={FileSpreadsheet} onClick={exportCsv} disabled={busy || !nodes.length}>
              Export CSV
            </Button>
            <Divider />
            <Button
              size="sm"
              variant="ghost"
              icon={RotateCcw}
              disabled={busy}
              onClick={() =>
                setConfirm({
                  title: 'Reset to the preset?',
                  confirmLabel: 'Reset to preset',
                  body: 'The builder is replaced by a copy of the preset demo network, and the preset becomes the active network again. You can undo this.',
                  onConfirm: async () => {
                    const res = await store.resetManual('preset')
                    setConfirm(null)
                    after(res, 'Builder reset to the preset', 'The preset demo is active again')
                  },
                })
              }
            >
              Reset to preset
            </Button>
            <Button
              size="sm"
              variant="danger"
              icon={Eraser}
              disabled={busy || !nodes.length}
              onClick={() =>
                setConfirm({
                  title: 'Clear the manual network?',
                  confirmLabel: `Remove ${nodes.length} nodes and ${edges.length} lanes`,
                  body: isActive
                    ? 'The manual network is active, so every tab will show an empty network until you add nodes or switch source. You can undo this.'
                    : 'Every node and lane in the builder is removed. You can undo this.',
                  onConfirm: async () => {
                    const res = await store.resetManual('empty')
                    setConfirm(null)
                    after(res, 'Manual network cleared')
                    close()
                  },
                })
              }
            >
              Clear all
            </Button>
          </Toolbar>
          <ValidationPanel validation={validation} onGoTo={goTo} edgeIds={edgeIds} />
          <InlineError message={actionError || errors.builder || errors.source} />
        </CardBody>
      </Card>

      {nodes.length === 0 && !panel ? (
        <Card>
          <EmptyState
            icon={Wand2}
            title="Build a network by hand"
            description="Start from a copy of the preset demo and edit it, or add sites one by one: at least one supplier and one retailer or customer, connected by lanes."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Button variant="primary" icon={Copy} onClick={startFromPreset} disabled={busy}>
                  Start from preset
                </Button>
                <Button icon={Plus} onClick={() => open({ type: 'node', kind: 'supplier' })} disabled={busy}>
                  Add your first supplier
                </Button>
              </div>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-4 xl:grid-cols-12">
          <Card className="min-w-0 xl:col-span-7">
            <div className="flex flex-wrap items-center gap-2 px-5 pt-4">
              <SegmentedControl
                size="sm"
                label="Table"
                value={table}
                onChange={(v) => {
                  setTable(v)
                  setChecked(new Set())
                }}
                options={[
                  { value: 'nodes', label: `Nodes (${nodes.length})` },
                  { value: 'lanes', label: `Lanes (${edges.length})` },
                ]}
              />
              <div className="relative min-w-[10rem] flex-1">
                <Search className="pointer-events-none absolute left-2.5 top-2 h-4 w-4 text-fg-muted" aria-hidden />
                <input className="input h-8 pl-8 text-xs" placeholder="Search id, name, city…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search" />
              </div>
              <select className="input h-8 w-auto py-0 text-xs" value={kindFilter} onChange={(e) => setKindFilter(e.target.value)} aria-label="Filter by type">
                <option value="all">All types</option>
                {NODE_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {typeOf(k).plural}
                  </option>
                ))}
              </select>
              {checkedList.length > 0 && (
                <Button size="sm" variant="danger" icon={Trash2} onClick={() => (table === 'nodes' ? askDeleteNodes(checkedList) : askDeleteEdges(checkedList))}>
                  Delete {checkedList.length}
                </Button>
              )}
            </div>
            <CardBody className="px-0 pb-2">
              {(table === 'nodes' ? filteredNodes : filteredEdges).length === 0 ? (
                <p className="px-5 py-6 text-center text-sm text-fg-muted">
                  {table === 'lanes' && !edges.length ? 'No lanes yet. Use "Add lane" to connect two nodes.' : 'Nothing matches the search or filter.'}
                </p>
              ) : table === 'nodes' ? (
                <NodeTable
                  nodes={filteredNodes}
                  selection={selection}
                  checked={checked}
                  onCheck={(id, on) => setChecked((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n })}
                  onCheckAll={(on) => setChecked(on ? new Set(filteredNodes.map((n) => n.id)) : new Set())}
                  onOpen={(n) => open({ type: 'node', node: n })}
                  onDuplicate={duplicate}
                  onDelete={askDeleteNodes}
                />
              ) : (
                <EdgeTable
                  edges={filteredEdges}
                  selection={selection}
                  checked={checked}
                  onCheck={(id, on) => setChecked((s) => { const n = new Set(s); if (on) n.add(id); else n.delete(id); return n })}
                  onCheckAll={(on) => setChecked(on ? new Set(filteredEdges.map((e) => e.id)) : new Set())}
                  onOpen={(e) => open({ type: 'edge', edge: e })}
                  onDelete={askDeleteEdges}
                />
              )}
            </CardBody>
          </Card>

          <Card className="min-w-0 xl:col-span-5 xl:self-start">
            <CardBody>
              {!panel && (
                <div className="space-y-3">
                  <p className="text-sm font-medium text-fg">Add a node</p>
                  <TypePicker onPick={(kind) => open({ type: 'node', kind })} />
                  <p className="text-xs text-fg-muted">Or click a row, or a marker on the map, to edit it.</p>
                </div>
              )}
              {panel?.type === 'pick' && (
                <div className="space-y-3">
                  <p className="text-sm font-medium text-fg">What are you adding?</p>
                  <TypePicker onPick={(kind) => open({ type: 'node', kind })} />
                  <Button size="sm" onClick={close}>
                    Cancel
                  </Button>
                </div>
              )}
              {panel?.type === 'node' && (
                <NodeForm
                  key={panelKey}
                  node={panel.node}
                  kind={panel.kind}
                  takenIds={takenIds}
                  busy={busy}
                  picking={picking}
                  onTogglePick={() => setPicking((p) => !p)}
                  pickedLocation={picked}
                  onDraftChange={setPin}
                  onSave={saveNode}
                  onCancel={close}
                  onDelete={() => askDeleteNodes([panel.node.id])}
                  onDuplicate={() => duplicate(panel.node)}
                />
              )}
              {panel?.type === 'edge' && (
                <EdgeForm
                  key={panelKey}
                  edge={panel.edge}
                  nodes={nodes}
                  edges={edges}
                  busy={busy}
                  defaultSource={selection?.type === 'node' ? selection.id : undefined}
                  onSave={saveEdge}
                  onCancel={close}
                  onDelete={() => askDeleteEdges([panel.edge.id])}
                />
              )}
            </CardBody>
          </Card>
        </div>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-2 px-5 pt-4">
          <h3 className="text-sm font-semibold text-fg">Live map preview</h3>
          <span className="text-xs text-fg-muted">Works offline · click a marker or lane to edit it · scroll to zoom, drag to pan</span>
          <span className="ml-auto flex flex-wrap gap-2 text-xs text-fg-muted">
            {NODE_KINDS.map((k) => (
              <span key={k} className="inline-flex items-center gap-1">
                <TypeIcon kind={k} size="xs" />
                {typeOf(k).label}
              </span>
            ))}
          </span>
        </div>
        <CardBody>
          <BuilderMap
            className={cn('h-[460px]', picking && 'ring-2 ring-accent')}
            nodes={nodes}
            edges={edges}
            selection={selection}
            onSelect={onMapSelect}
            pickMode={picking}
            onPick={(loc) => {
              setPicked(loc)
              setPicking(false)
            }}
            pin={panel?.type === 'node' ? pin : null}
          />
        </CardBody>
      </Card>

      <ConfirmDialog
        open={Boolean(confirm)}
        title={confirm?.title}
        confirmLabel={confirm?.confirmLabel}
        busy={busy}
        onConfirm={() => confirm?.onConfirm()}
        onCancel={cancelConfirm}
      >
        {confirm?.body}
      </ConfirmDialog>
    </div>
  )
}
