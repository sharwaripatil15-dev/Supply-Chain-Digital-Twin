import { useMemo, useState } from 'react'
import { Route, Save, Trash2, X } from 'lucide-react'
import { MODES, NODE_KINDS, allowedTargets, suggestCo2, suggestCost, suggestLead, typeOf } from '../../lib/nodeTypes.js'
import { distanceBetween, edgePayload, legalTargets, validateEdge } from '../../lib/nodeForm.js'
import { Button, InlineError, cn } from '../ui/index.js'
import { NodeTag } from '../NodeTypeIcon.jsx'
import { useDebounced } from './NodeForm.jsx'

const toDraft = (e) => ({
  source: e?.source ?? '', target: e?.target ?? '', mode: e?.mode ?? 'road', capacity: e?.capacity ?? '',
  distance_km: e?.distance_km ?? '', lead: e?.lead ?? '', cost: e?.cost ?? '', co2: e?.co2 ?? '', status: e?.status ?? 'active', id: e?.id,
})

function NodeSelect({ label, value, nodes, onChange, error, placeholder }) {
  const groups = NODE_KINDS.map((k) => [k, nodes.filter((n) => n.kind === k)]).filter(([, list]) => list.length)
  return (
    <label className="block">
      <span className="label">{label}</span>
      <select className={cn('input mt-1', error && 'border-bad')} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{placeholder}</option>
        {groups.map(([k, list]) => (
          <optgroup key={k} label={typeOf(k).plural}>
            {list.map((n) => (
              <option key={n.id} value={n.id}>
                {n.id} · {n.name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      {error && <span className="mt-1 block text-xs text-bad">{error}</span>}
    </label>
  )
}

function NumberField({ label, unit, value, suggestion, error, onChange, required }) {
  return (
    <label className="block">
      <span className="label flex items-baseline justify-between gap-2">
        <span>
          {label}
          {required && <span className="text-bad"> *</span>}
        </span>
        <span className="font-normal text-fg-muted">{unit}</span>
      </span>
      <input
        className={cn('input mt-1 tabular', error && 'border-bad')}
        type="number"
        min={0}
        step="any"
        inputMode="decimal"
        value={value}
        placeholder={suggestion != null ? `${suggestion} (auto)` : ''}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={Boolean(error)}
      />
      {error ? (
        <span className="mt-1 block text-xs text-bad">{error}</span>
      ) : (
        suggestion != null && value !== '' && Number(value) !== suggestion && <span className="mt-1 block text-xs text-fg-muted">Suggested {suggestion}</span>
      )}
    </label>
  )
}

/** Create or edit a lane. Only legal tier directions are offered as targets. */
export default function EdgeForm({ edge, nodes, edges, busy, defaultSource, onSave, onCancel, onDelete }) {
  const isNew = !edge
  const [draft, setDraft] = useState(() => ({ ...toDraft(edge), source: edge?.source ?? defaultSource ?? '' }))
  const [touched, setTouched] = useState({})
  const [serverErrors, setServerErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes])
  const sources = nodes.filter((n) => allowedTargets(n.kind).length > 0)
  const targets = legalTargets(draft.source, nodes)
  const km = distanceBetween(byId[draft.source], byId[draft.target])
  const kmUsed = draft.distance_km !== '' ? Number(draft.distance_km) : km
  const suggestions = kmUsed == null ? {} : { lead: suggestLead(draft.mode, kmUsed), cost: suggestCost(draft.mode, kmUsed), co2: suggestCo2(draft.mode, kmUsed) }

  const debounced = useDebounced(draft, 200)
  const errors = useMemo(() => validateEdge(debounced, nodes, edges), [debounced, nodes, edges])
  const live = useMemo(() => validateEdge(draft, nodes, edges), [draft, nodes, edges])
  const valid = Object.keys(live).length === 0
  const errorFor = (k) => serverErrors[k] || (touched[k] ? errors[k] : null)
  const set = (k, v) => {
    setDraft((d) => {
      const next = { ...d, [k]: v }
      if (k === 'source' && !legalTargets(v, nodes).some((n) => n.id === d.target)) next.target = ''
      return next
    })
    setTouched((t) => ({ ...t, [k]: true }))
    setServerErrors((e) => ({ ...e, [k]: null }))
  }

  const submit = async (e) => {
    e?.preventDefault()
    setTouched({ source: true, target: true, capacity: true })
    if (!valid || busy) return
    const res = await onSave(edgePayload(draft))
    if (res && !res.ok) {
      setServerErrors(res.fields || {})
      setFormError(Object.keys(res.fields || {}).length ? null : res.error)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface-2 text-fg-muted">
          <Route className="h-4 w-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-fg">{isNew ? 'New lane' : `Lane ${edge.id}`}</p>
          {draft.source && draft.target ? (
            <NodeTag id={`${draft.source}->${draft.target}`} />
          ) : (
            <p className="text-xs text-fg-muted">Choose where goods ship from, then where they go.</p>
          )}
        </div>
        <Button variant="ghost" size="icon" icon={X} aria-label="Close form" onClick={onCancel} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <NodeSelect label="From (source)" value={draft.source} nodes={sources} onChange={(v) => set('source', v)} error={errorFor('source')} placeholder="Choose source…" />
        <NodeSelect
          label="To (target)"
          value={draft.target}
          nodes={targets}
          onChange={(v) => set('target', v)}
          error={errorFor('target')}
          placeholder={draft.source ? (targets.length ? 'Choose target…' : 'No legal targets yet') : 'Pick a source first'}
        />
        {draft.source && byId[draft.source] && (
          <p className="col-span-2 -mt-1 text-xs text-fg-muted">
            A {typeOf(byId[draft.source].kind).label.toLowerCase()} can ship to:{' '}
            {allowedTargets(byId[draft.source].kind).map((k) => typeOf(k).plural.toLowerCase()).join(', ')}.
          </p>
        )}
        <label className="block">
          <span className="label">Transport mode</span>
          <select className="input mt-1" value={draft.mode} onChange={(e) => set('mode', e.target.value)}>
            {Object.entries(MODES).map(([k, m]) => (
              <option key={k} value={k}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="label">Status</span>
          <select className="input mt-1" value={draft.status} onChange={(e) => set('status', e.target.value)}>
            <option value="active">Active</option>
            <option value="inactive">Inactive (ignored)</option>
          </select>
        </label>
        <NumberField label="Capacity" unit="units/day" value={draft.capacity} error={errorFor('capacity')} onChange={(v) => set('capacity', v)} required />
        <NumberField label="Distance" unit="km" value={draft.distance_km} suggestion={km} error={errorFor('distance_km')} onChange={(v) => set('distance_km', v)} />
        <NumberField label="Lead time" unit="days" value={draft.lead} suggestion={suggestions.lead} error={errorFor('lead')} onChange={(v) => set('lead', v)} />
        <NumberField label="Cost" unit="₹/unit" value={draft.cost} suggestion={suggestions.cost} error={errorFor('cost')} onChange={(v) => set('cost', v)} />
        <NumberField label="CO₂" unit="kg/unit" value={draft.co2} suggestion={suggestions.co2} error={errorFor('co2')} onChange={(v) => set('co2', v)} />
      </div>
      <p className="text-xs text-fg-muted">Leave distance, lead time, cost or CO₂ empty to use the suggestion from the map distance and mode.</p>

      <InlineError message={formError} />
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <Button type="submit" variant="primary" icon={Save} disabled={!valid || busy}>
          {busy ? 'Saving…' : isNew ? 'Add lane' : 'Save changes'}
        </Button>
        <Button onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        {!isNew && (
          <Button variant="danger" icon={Trash2} onClick={onDelete} disabled={busy} className="ml-auto">
            Delete
          </Button>
        )}
      </div>
    </form>
  )
}
