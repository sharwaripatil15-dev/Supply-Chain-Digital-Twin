import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, Copy, Eraser, FileJson, FileSpreadsheet, MoreHorizontal, Plus, Redo2, RotateCcw, Route, Trash2, Undo2, Upload } from 'lucide-react'
import { api, errorMessage } from '../../api.js'
import { useStore } from '../../store.js'
import { fmtNum } from '../../format.js'
import { NODE_KINDS, isDemand, typeOf } from '../../lib/nodeTypes.js'
import { duplicateNode } from '../../lib/nodeForm.js'
import { downloadText, readFileText } from '../../lib/download.js'
import { MOD_LABEL, useHotkeys } from '../../ui.jsx'
import {
  Button, ConfirmDialog, DataTable, Divider, EmptyState, IconButton, InlineError, Input, Menu, Panel, PanelHeader, Select, Skeleton,
  StatusDot, TabPanel, Tabs, useToast,
} from '../ui/index.js'
import { NodeTag } from '../NodeTypeIcon.jsx'
import BuilderMap from './BuilderMap.jsx'
import NodeForm, { TypePicker } from './NodeForm.jsx'
import EdgeForm from './EdgeForm.jsx'
import ValidationPanel from './ValidationPanel.jsx'

const lanesOf = (edges, ids) => edges.filter((e) => ids.includes(e.source) || ids.includes(e.target))

/**
 * Manual network builder. The server holds the manual network (every edit is saved and validated there); undo/redo
 * restore snapshots through the import endpoint. "Apply network" makes it the active source for every page.
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

  const q = query.trim().toLowerCase()
  const filteredNodes = nodes.filter((n) => (kindFilter === 'all' || n.kind === kindFilter) && (!q || [n.id, n.name, n.city].some((v) => String(v || '').toLowerCase().includes(q))))
  const filteredEdges = edges.filter((e) => {
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
          <div className="flex flex-wrap gap-x-3 gap-y-1.5">
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
                    <span className="num w-8 text-fg-muted">{e.id}</span>
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
                <span className="num w-8 text-fg-muted">{id}</span>
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
      toast('Manual network applied', { description: `${nodes.length} nodes · ${edges.length} lanes are now used on every page` })
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
  const lastUndo = history.past[history.past.length - 1]
  const lastRedo = history.future[history.future.length - 1]

  useHotkeys({
    'mod+z': () => (busy || !lastUndo ? false : travel('undo')),
    'mod+shift+z': () => (busy || !lastRedo ? false : travel('redo')),
    'mod+y': () => (busy || !lastRedo ? false : travel('redo')),
    escape: () => (panel ? close() : false),
  })

  // ------------------------------------------------ render
  if (!manual) {
    return <Panel className="p-4">{errors.manual ? <InlineError message={errors.manual} onRetry={loadManual} /> : <Skeleton className="h-64 w-full" />}</Panel>
  }

  const checkedList = [...checked].filter((id) => (table === 'nodes' ? nodes.some((n) => n.id === id) : edgeIds.has(id)))
  const toggleCheck = (id, on) =>
    setChecked((s) => {
      const next = new Set(s)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })
  const rowsShown = table === 'nodes' ? filteredNodes : filteredEdges
  const allChecked = rowsShown.length > 0 && rowsShown.every((r) => checked.has(r.id))
  const checkColumn = {
    key: 'check', sortable: false, hideable: false, width: 'w-8',
    header: (
      <input type="checkbox" aria-label={`Select all ${table}`} checked={allChecked} onChange={(e) => setChecked(e.target.checked ? new Set(rowsShown.map((r) => r.id)) : new Set())} />
    ),
    render: (r) => (
      <input type="checkbox" aria-label={`Select ${r.id}`} checked={checked.has(r.id)} onClick={(e) => e.stopPropagation()} onChange={(e) => toggleCheck(r.id, e.target.checked)} />
    ),
  }
  const nodeColumns = [
    checkColumn,
    {
      key: 'name', header: 'Node', hideable: false, value: (n) => n.name,
      render: (n) => (
        <span className="flex items-center gap-2">
          <NodeTag node={n} nameClassName="max-w-[12rem]" />
          {n.is_backup && <span className="text-2xs text-fg-muted">backup</span>}
          {n.status === 'inactive' && <span className="text-2xs text-fg-muted">inactive</span>}
        </span>
      ),
    },
    { key: 'kind', header: 'Type', value: (n) => typeOf(n.kind).tier, render: (n) => <span className="text-fg-2">{typeOf(n.kind).label}</span> },
    { key: 'city', header: 'City', render: (n) => <span className="block max-w-[9rem] truncate text-fg-2">{n.city || '–'}</span> },
    { key: 'capacity', header: 'Capacity', align: 'right', value: (n) => (n.kind === 'factory' && n.production_capacity ? n.production_capacity : n.capacity), render: (n) => fmtNum(n.kind === 'factory' && n.production_capacity ? n.production_capacity : n.capacity) },
    { key: 'daily_demand', header: 'Demand', align: 'right', value: (n) => (isDemand(n.kind) ? n.daily_demand : null), render: (n) => (isDemand(n.kind) ? fmtNum(n.daily_demand) : '–') },
    { key: 'stock', header: 'Stock', align: 'right', value: (n) => (n.stock || 0) + (n.kind === 'retailer' ? n.shelf_stock || 0 : 0), render: (n) => fmtNum((n.stock || 0) + (n.kind === 'retailer' ? n.shelf_stock || 0 : 0)) },
    {
      key: 'act', header: '', sortable: false, hideable: false, width: 'w-16',
      render: (n) => (
        <span className="row-actions flex justify-end" onClick={(e) => e.stopPropagation()}>
          <IconButton icon={Copy} label={`Duplicate ${n.id}`} size="xs" tooltipSide="left" onClick={() => duplicate(n)} />
          <IconButton icon={Trash2} label={`Delete ${n.id}`} size="xs" tooltipSide="left" onClick={() => askDeleteNodes([n.id])} />
        </span>
      ),
    },
  ]
  const laneColumns = [
    checkColumn,
    { key: 'lane', header: 'Lane', hideable: false, value: (e) => `${e.source}${e.target}`, render: (e) => <NodeTag id={`${e.source}->${e.target}`} /> },
    { key: 'id', header: 'ID', mono: true, render: (e) => <span className="text-fg-muted">{e.id}</span> },
    { key: 'mode', header: 'Mode', render: (e) => <span className="capitalize text-fg-2">{e.mode}</span> },
    { key: 'distance_km', header: 'km', align: 'right', render: (e) => fmtNum(e.distance_km) },
    { key: 'lead', header: 'Lead', align: 'right', render: (e) => `${fmtNum(e.lead, 1)} d` },
    { key: 'capacity', header: 'Cap/day', align: 'right', render: (e) => fmtNum(e.capacity) },
    { key: 'cost', header: '₹/unit', align: 'right', render: (e) => fmtNum(e.cost, 1) },
    { key: 'co2', header: 'CO₂ kg', align: 'right', defaultHidden: true, render: (e) => fmtNum(e.co2, 2) },
    {
      key: 'act', header: '', sortable: false, hideable: false, width: 'w-10',
      render: (e) => (
        <span className="row-actions flex justify-end" onClick={(ev) => ev.stopPropagation()}>
          <IconButton icon={Trash2} label={`Delete lane ${e.id}`} size="xs" tooltipSide="left" onClick={() => askDeleteEdges([e.id])} />
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {nodes.length > 0 && (
          <>
            <Button variant="primary" icon={CheckCircle2} disabled={!canApply || busy} onClick={apply} title={canApply ? 'Use this network on every page' : 'Fix the errors first'}>
              {isActive ? 'Re-apply network' : 'Apply network'}
            </Button>
            <StatusDot status={isActive ? 'ok' : 'neutral'} label={isActive ? 'Active on every page' : 'Not active'} />
            <Divider className="mx-1" />
          </>
        )}
        <Button icon={Plus} onClick={() => open({ type: 'pick' })} disabled={busy}>
          Add node
        </Button>
        <Button icon={Route} onClick={() => open({ type: 'edge' })} disabled={busy || nodes.length < 2}>
          Add lane
        </Button>
        <Divider className="mx-1" />
        <IconButton icon={Undo2} label={lastUndo ? `Undo: ${lastUndo.label}` : 'Nothing to undo'} shortcut={`${MOD_LABEL} Z`} onClick={() => travel('undo')} disabled={busy || !lastUndo} />
        <IconButton icon={Redo2} label={lastRedo ? `Redo: ${lastRedo.label}` : 'Nothing to redo'} shortcut={`${MOD_LABEL} ⇧ Z`} onClick={() => travel('redo')} disabled={busy || !lastRedo} />
        <Menu
          icon={MoreHorizontal}
          label="More"
          variant="ghost"
          size="md"
          items={[
            { key: 'import', label: 'Import JSON…', icon: Upload, onSelect: () => fileRef.current?.click(), disabled: busy },
            { key: 'json', label: 'Export JSON', icon: FileJson, onSelect: exportJson, disabled: !nodes.length },
            { key: 'csv', label: 'Export CSV (nodes + edges)', icon: FileSpreadsheet, onSelect: exportCsv, disabled: !nodes.length },
            { key: 'sep', separator: true },
            {
              key: 'reset', label: 'Reset to the preset', icon: RotateCcw, disabled: busy,
              onSelect: () =>
                setConfirm({
                  title: 'Reset to the preset?',
                  confirmLabel: 'Reset to preset',
                  body: 'The builder is replaced by a copy of the preset demo network, and the preset becomes the active network again. You can undo this.',
                  onConfirm: async () => {
                    const res = await store.resetManual('preset')
                    setConfirm(null)
                    after(res, 'Builder reset to the preset', 'The preset demo is active again')
                  },
                }),
            },
            {
              key: 'clear', label: 'Clear all', icon: Eraser, danger: true, disabled: busy || !nodes.length,
              onSelect: () =>
                setConfirm({
                  title: 'Clear the manual network?',
                  confirmLabel: `Remove ${nodes.length} nodes and ${edges.length} lanes`,
                  body: isActive
                    ? 'The manual network is active, so every page will show an empty network until you add nodes or switch source. You can undo this.'
                    : 'Every node and lane in the builder is removed. You can undo this.',
                  onConfirm: async () => {
                    const res = await store.resetManual('empty')
                    setConfirm(null)
                    after(res, 'Manual network cleared')
                    close()
                  },
                }),
            },
          ]}
        />
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
      </div>
      <ValidationPanel validation={validation} onGoTo={goTo} edgeIds={edgeIds} />
      <InlineError message={actionError || errors.builder || errors.source} />

      {nodes.length === 0 && !panel ? (
        <Panel>
          <EmptyState
            title="Build a network by hand"
            description="Start from a copy of the preset demo, or add sites one by one: at least one supplier and one retailer or customer, connected by lanes."
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
        </Panel>
      ) : (
        <div className="grid items-start gap-3 xl:grid-cols-[minmax(0,1fr)_400px]">
          <Panel className="flex min-h-[460px] min-w-0 flex-col overflow-hidden">
            <Tabs
              idBase="builder"
              label="Builder tables"
              value={table}
              onChange={(v) => {
                setTable(v)
                setChecked(new Set())
              }}
              className="px-4"
              tabs={[
                { value: 'nodes', label: 'Nodes', count: nodes.length },
                { value: 'lanes', label: 'Lanes', count: edges.length },
              ]}
            />
            <TabPanel idBase="builder" value={table} className="flex min-h-0 flex-1 flex-col">
              <DataTable
                key={table}
                label={table === 'nodes' ? 'Nodes' : 'Lanes'}
                rows={rowsShown}
                columns={table === 'nodes' ? nodeColumns : laneColumns}
                selectedKey={selection?.type === (table === 'nodes' ? 'node' : 'edge') ? selection.id : null}
                onRowClick={(r) => open(table === 'nodes' ? { type: 'node', node: r } : { type: 'edge', edge: r })}
                empty={table === 'lanes' && !edges.length ? 'No lanes yet. Use "Add lane" to connect two nodes.' : 'Nothing matches the search or filter.'}
                className="min-h-0 flex-1"
                toolbar={
                  <>
                    <Input size="sm" className="max-w-[16rem]" placeholder="Search id, name, city" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search" />
                    <Select size="sm" className="w-36" value={kindFilter} onChange={(e) => setKindFilter(e.target.value)} aria-label="Filter by type">
                      <option value="all">All types</option>
                      {NODE_KINDS.map((k) => (
                        <option key={k} value={k}>
                          {typeOf(k).plural}
                        </option>
                      ))}
                    </Select>
                    {checkedList.length > 0 && (
                      <Button size="sm" variant="danger" icon={Trash2} onClick={() => (table === 'nodes' ? askDeleteNodes(checkedList) : askDeleteEdges(checkedList))}>
                        Delete {checkedList.length}
                      </Button>
                    )}
                  </>
                }
              />
            </TabPanel>
          </Panel>

          <div className="space-y-3 xl:sticky xl:top-0">
            <Panel className="overflow-hidden">
              <BuilderMap
                className="h-[240px]"
                framed={false}
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
            </Panel>
            <Panel className="flex max-h-[calc(100vh-22rem)] min-h-[300px] flex-col overflow-hidden">
              {(!panel || panel.type === 'pick') && (
                <>
                  <PanelHeader title="Add a node" actions={panel?.type === 'pick' && <Button size="sm" variant="ghost" onClick={close}>Cancel</Button>} />
                  <div className="min-h-0 flex-1 overflow-y-auto px-4 py-2">
                    <TypePicker onPick={(kind) => open({ type: 'node', kind })} />
                    <p className="mt-2 text-xs text-fg-muted">Or select a row or a map marker to edit it.</p>
                  </div>
                </>
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
            </Panel>
          </div>
        </div>
      )}

      <ConfirmDialog open={Boolean(confirm)} title={confirm?.title} confirmLabel={confirm?.confirmLabel} busy={busy} onConfirm={() => confirm?.onConfirm()} onCancel={cancelConfirm}>
        {confirm?.body}
      </ConfirmDialog>
    </div>
  )
}
