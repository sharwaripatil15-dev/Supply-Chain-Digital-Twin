import { useId, useMemo, useState } from 'react'
import { Trash2, X } from 'lucide-react'
import { MODES, NODE_KINDS, allowedTargets, suggestCo2, suggestCost, suggestLead, typeOf } from '../../lib/nodeTypes.js'
import { distanceBetween, edgePayload, legalTargets, validateEdge } from '../../lib/nodeForm.js'
import { Button, Field, IconButton, InlineError, Input, SectionLabel, Select } from '../ui/index.js'
import { NodeTag } from '../NodeTypeIcon.jsx'
import { useDebounced } from './NodeForm.jsx'

const toDraft = (e) => ({
  source: e?.source ?? '', target: e?.target ?? '', mode: e?.mode ?? 'road', capacity: e?.capacity ?? '',
  distance_km: e?.distance_km ?? '', lead: e?.lead ?? '', cost: e?.cost ?? '', co2: e?.co2 ?? '', status: e?.status ?? 'active', id: e?.id,
})

function NodeSelect({ id, label, value, nodes, onChange, error, placeholder }) {
  const groups = NODE_KINDS.map((k) => [k, nodes.filter((n) => n.kind === k)]).filter(([, list]) => list.length)
  return (
    <Field label={label} htmlFor={id} error={error} required>
      <Select id={id} value={value} invalid={Boolean(error)} onChange={(e) => onChange(e.target.value)}>
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
      </Select>
    </Field>
  )
}

/** Number input whose placeholder shows the auto suggestion; empty = use the suggestion. */
function SuggestField({ id, label, unit, value, suggestion, error, onChange, required }) {
  return (
    <Field label={label} htmlFor={id} error={error} required={required} hint={suggestion != null && value !== '' && Number(value) !== suggestion ? `Suggested ${suggestion}` : undefined}>
      <Input
        id={id}
        type="number"
        min={0}
        step="any"
        inputMode="decimal"
        suffix={unit}
        invalid={Boolean(error)}
        value={value}
        placeholder={suggestion != null ? `${suggestion} (auto)` : ''}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  )
}

/** Create or edit a lane. Only legal tier directions are offered as targets. */
export default function EdgeForm({ edge, nodes, edges, busy, defaultSource, onSave, onCancel, onDelete }) {
  const isNew = !edge
  const fid = useId()
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
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col" noValidate aria-label={isNew ? 'New lane' : `Edit lane ${edge.id}`}>
      <div className="flex items-center gap-2.5 border-b border-border px-4 py-2.5">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-fg">{isNew ? 'New lane' : <span className="num">Lane {edge.id}</span>}</p>
          {draft.source && draft.target ? <NodeTag id={`${draft.source}->${draft.target}`} /> : <p className="text-xs text-fg-muted">Choose a source, then a target.</p>}
        </div>
        <IconButton icon={X} label="Close" shortcut="Esc" size="sm" tooltipSide="left" onClick={onCancel} />
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-3">
        <section className="space-y-3">
          <SectionLabel>Route</SectionLabel>
          <div className="grid grid-cols-2 gap-3">
            <NodeSelect id={`${fid}-src`} label="From" value={draft.source} nodes={sources} onChange={(v) => set('source', v)} error={errorFor('source')} placeholder="Choose source…" />
            <NodeSelect
              id={`${fid}-dst`}
              label="To"
              value={draft.target}
              nodes={targets}
              onChange={(v) => set('target', v)}
              error={errorFor('target')}
              placeholder={draft.source ? (targets.length ? 'Choose target…' : 'No legal targets') : 'Pick a source first'}
            />
          </div>
          {draft.source && byId[draft.source] && (
            <p className="text-xs text-fg-muted">
              A {typeOf(byId[draft.source].kind).label.toLowerCase()} ships to {allowedTargets(byId[draft.source].kind).map((k) => typeOf(k).plural.toLowerCase()).join(', ')}.
            </p>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Transport mode" htmlFor={`${fid}-mode`}>
              <Select id={`${fid}-mode`} value={draft.mode} onChange={(e) => set('mode', e.target.value)}>
                {Object.entries(MODES).map(([k, m]) => (
                  <option key={k} value={k}>
                    {m.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Status" htmlFor={`${fid}-status`}>
              <Select id={`${fid}-status`} value={draft.status} onChange={(e) => set('status', e.target.value)}>
                <option value="active">Active</option>
                <option value="inactive">Inactive (ignored)</option>
              </Select>
            </Field>
          </div>
        </section>

        <section className="space-y-3">
          <SectionLabel>Capacity and cost</SectionLabel>
          <p className="text-xs text-fg-muted">Empty fields use the suggestion from the map distance and mode.</p>
          <div className="grid grid-cols-2 gap-3">
            <SuggestField id={`${fid}-cap`} label="Capacity" unit="units/day" value={draft.capacity} error={errorFor('capacity')} onChange={(v) => set('capacity', v)} required />
            <SuggestField id={`${fid}-km`} label="Distance" unit="km" value={draft.distance_km} suggestion={km} error={errorFor('distance_km')} onChange={(v) => set('distance_km', v)} />
            <SuggestField id={`${fid}-lead`} label="Lead time" unit="days" value={draft.lead} suggestion={suggestions.lead} error={errorFor('lead')} onChange={(v) => set('lead', v)} />
            <SuggestField id={`${fid}-cost`} label="Cost" unit="₹/unit" value={draft.cost} suggestion={suggestions.cost} error={errorFor('cost')} onChange={(v) => set('cost', v)} />
            <SuggestField id={`${fid}-co2`} label="CO₂" unit="kg/unit" value={draft.co2} suggestion={suggestions.co2} error={errorFor('co2')} onChange={(v) => set('co2', v)} />
          </div>
        </section>
        <InlineError message={formError} />
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-border bg-surface px-4 py-2.5">
        {!isNew && <IconButton icon={Trash2} label="Delete lane" variant="ghost-danger" tooltipSide="top" onClick={onDelete} disabled={busy} />}
        <div className="ml-auto flex gap-2">
          <Button onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!valid || busy}>
            {busy ? 'Saving…' : isNew ? 'Add lane' : 'Save'}
          </Button>
        </div>
      </div>
    </form>
  )
}
