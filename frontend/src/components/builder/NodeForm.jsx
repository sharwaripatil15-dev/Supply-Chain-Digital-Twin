import { useEffect, useId, useMemo, useState } from 'react'
import { Copy, Crosshair, MapPin, Save, Search, Trash2, X } from 'lucide-react'
import { NODE_KINDS, fieldsFor, typeOf } from '../../lib/nodeTypes.js'
import { blankNode, nodeDraft, nodePayload, nextId, validateNode } from '../../lib/nodeForm.js'
import { searchCities } from '../../lib/indianCities.js'
import { Badge, Button, InlineError, cn } from '../ui/index.js'
import { TypeIcon } from '../NodeTypeIcon.jsx'

/** Debounced copy of a value (validation runs on this, not on every keystroke). */
export function useDebounced(value, ms = 200) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return v
}

/** Five type cards: icon, color, one-line description. */
export function TypePicker({ onPick, compact = false }) {
  return (
    <div className={cn('grid gap-2', compact ? 'grid-cols-5' : 'grid-cols-1 sm:grid-cols-2')}>
      {NODE_KINDS.map((k) => {
        const t = typeOf(k)
        return (
          <button
            key={k}
            type="button"
            onClick={() => onPick(k)}
            className={cn(
              'group flex items-center gap-3 rounded-lg border border-border bg-surface text-left transition-colors duration-150 hover:border-border-strong hover:bg-surface-2',
              compact ? 'flex-col justify-center p-2 text-center' : 'p-3',
            )}
            style={{ boxShadow: `inset 3px 0 0 ${t.color}` }}
          >
            <TypeIcon kind={k} size={compact ? 'md' : 'lg'} />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-fg">{t.label}</span>
              {!compact && <span className="block text-xs text-fg-muted">{t.blurb}</span>}
            </span>
          </button>
        )
      })}
    </div>
  )
}

function Field({ def, value, error, onChange }) {
  const id = useId()
  if (def.type === 'checkbox') {
    return (
      <label className="col-span-2 flex items-center gap-2 text-xs text-fg-2">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        {def.label}
      </label>
    )
  }
  return (
    <label htmlFor={id} className={cn('block', def.type === 'text' && 'col-span-2')}>
      <span className="label flex items-baseline justify-between gap-2">
        <span>
          {def.label}
          {def.required && <span className="text-bad"> *</span>}
        </span>
        {def.unit && <span className="font-normal text-fg-muted">{def.unit}</span>}
      </span>
      {def.type === 'select' ? (
        <select id={id} className="input mt-1" value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
          {def.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          className={cn('input mt-1', def.type === 'number' && 'tabular', error && 'border-bad focus:border-bad focus:ring-bad/20')}
          type={def.type === 'number' ? 'number' : 'text'}
          inputMode={def.type === 'number' ? 'decimal' : undefined}
          min={def.min}
          max={def.max}
          step={def.step ?? 'any'}
          maxLength={def.maxLength}
          placeholder={def.placeholder}
          value={value ?? ''}
          aria-invalid={Boolean(error)}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {error && <span className="mt-1 block text-xs text-bad">{error}</span>}
    </label>
  )
}

/** City combobox: type to search ~45 Indian cities; picking one fills address, lat and lon. */
function CitySearch({ onPick }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const results = useMemo(() => searchCities(q, 8), [q])
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-fg-muted" aria-hidden />
      <input
        className="input pl-8"
        placeholder="Search a city (e.g. Pune, Nagpur)…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && results[0]) {
            e.preventDefault()
            onPick(results[0])
            setQ(results[0].name)
            setOpen(false)
          }
        }}
        aria-label="Search Indian cities"
        role="combobox"
        aria-expanded={open}
      />
      {open && results.length > 0 && (
        <ul role="listbox" className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-border bg-surface py-1 shadow-card">
          {results.map((c) => (
            <li key={c.name}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                className="flex w-full items-center justify-between px-3 py-1.5 text-left text-sm hover:bg-surface-2"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onPick(c)
                  setQ(c.name)
                  setOpen(false)
                }}
              >
                <span className="text-fg">{c.name}</span>
                <span className="tabular text-xs text-fg-muted">
                  {c.lat.toFixed(2)}, {c.lon.toFixed(2)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * Create or edit one node. `node` = existing node (edit) or null (create, with `kind`).
 * `pickedLocation` arrives from a map click while `picking` is on. onSave(payload) resolves { ok, fields }.
 */
export default function NodeForm({ node, kind, takenIds, busy, picking, onTogglePick, pickedLocation, onDraftChange, onSave, onCancel, onDelete, onDuplicate }) {
  const isNew = !node
  const [draft, setDraft] = useState(() => (node ? nodeDraft(node) : blankNode(kind)))
  const [serverErrors, setServerErrors] = useState({})
  const [touched, setTouched] = useState({})
  const [formError, setFormError] = useState(null)
  const type = typeOf(draft.kind)
  const suggestedId = useMemo(() => nextId(type.prefix, takenIds || []), [type.prefix, takenIds])

  // A map click fills the location.
  useEffect(() => {
    if (!pickedLocation) return
    setDraft((d) => ({ ...d, lat: pickedLocation.lat, lon: pickedLocation.lon }))
    setTouched((t) => ({ ...t, lat: true, lon: true }))
  }, [pickedLocation])
  useEffect(() => onDraftChange?.(draft), [draft, onDraftChange])

  const debounced = useDebounced(draft, 200)
  const errors = useMemo(() => validateNode(debounced, { taken: takenIds || [], isNew }), [debounced, takenIds, isNew])
  const liveErrors = useMemo(() => validateNode(draft, { taken: takenIds || [], isNew }), [draft, takenIds, isNew])
  const valid = Object.keys(liveErrors).length === 0
  const errorFor = (k) => serverErrors[k] || (touched[k] ? errors[k] : null)
  const set = (k, v) => {
    setDraft((d) => ({ ...d, [k]: v }))
    setTouched((t) => ({ ...t, [k]: true }))
    setServerErrors((e) => ({ ...e, [k]: null }))
  }
  const { common, specific } = fieldsFor(draft.kind)

  const submit = async (e) => {
    e?.preventDefault()
    setTouched(Object.fromEntries(Object.keys({ ...draft, lat: 1, lon: 1 }).map((k) => [k, true])))
    if (!valid || busy) return
    const res = await onSave(nodePayload(draft))
    if (res && !res.ok) {
      setServerErrors(res.fields || {})
      setFormError(Object.keys(res.fields || {}).length ? null : res.error)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <div className="flex items-center gap-2">
        <TypeIcon kind={draft.kind} size="md" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-fg">{isNew ? `New ${type.label.toLowerCase()}` : `${node.id} · ${node.name}`}</p>
          <p className="text-xs text-fg-muted">{type.blurb}</p>
        </div>
        <Button variant="ghost" size="icon" icon={X} aria-label="Close form" onClick={onCancel} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className="label">ID</span>
          <input
            className={cn('input mt-1 tabular', errorFor('id') && 'border-bad')}
            value={isNew ? draft.id ?? '' : node.id}
            placeholder={`${suggestedId} (auto)`}
            disabled={!isNew}
            maxLength={24}
            onChange={(e) => set('id', e.target.value.trim())}
            title={isNew ? 'Optional. Leave empty for an automatic id' : 'IDs can only be set when a node is created'}
          />
          {errorFor('id') && <span className="mt-1 block text-xs text-bad">{errorFor('id')}</span>}
        </label>
        <label className="block">
          <span className="label">Status</span>
          <select className="input mt-1" value={draft.status || 'active'} onChange={(e) => set('status', e.target.value)}>
            <option value="active">Active</option>
            <option value="inactive">Inactive (excluded from runs)</option>
          </select>
        </label>
        <Field def={common[0]} value={draft.name} error={errorFor('name')} onChange={(v) => set('name', v)} />
      </div>

      <fieldset className="space-y-2 rounded-lg border border-border p-3">
        <legend className="label flex items-center gap-1 px-1">
          <MapPin className="h-3.5 w-3.5" aria-hidden /> Location
        </legend>
        <CitySearch
          onPick={(c) => {
            setDraft((d) => ({ ...d, lat: c.lat, lon: c.lon, city: d.city || c.name }))
            setTouched((t) => ({ ...t, lat: true, lon: true }))
          }}
        />
        <div className="grid grid-cols-2 gap-2">
          <Field def={{ key: 'lat', label: 'Latitude', type: 'number', min: -90, max: 90, placeholder: '18.520', unit: '°' }} value={draft.lat} error={errorFor('lat')} onChange={(v) => set('lat', v)} />
          <Field def={{ key: 'lon', label: 'Longitude', type: 'number', min: -180, max: 180, placeholder: '73.857', unit: '°' }} value={draft.lon} error={errorFor('lon')} onChange={(v) => set('lon', v)} />
        </div>
        <Button size="sm" variant={picking ? 'primary' : 'secondary'} icon={Crosshair} onClick={onTogglePick} aria-pressed={picking}>
          {picking ? 'Click the map below…' : 'Pick on map'}
        </Button>
        <Field def={common[1]} value={draft.city} error={errorFor('city')} onChange={(v) => set('city', v)} />
      </fieldset>

      <div className="grid grid-cols-2 gap-3">
        {common.slice(2).map((f) => (
          <Field key={f.key} def={f} value={draft[f.key]} error={errorFor(f.key)} onChange={(v) => set(f.key, v)} />
        ))}
      </div>

      <div>
        <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-fg">
          {type.label} details <Badge>{specific.length}</Badge>
        </p>
        <div className="grid grid-cols-2 gap-3">
          {specific.map((f) => (
            <Field key={f.key} def={f} value={draft[f.key]} error={errorFor(f.key)} onChange={(v) => set(f.key, v)} />
          ))}
        </div>
      </div>

      <InlineError message={formError} />
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <Button type="submit" variant="primary" icon={Save} disabled={!valid || busy} title={valid ? undefined : 'Fix the highlighted fields first'}>
          {busy ? 'Saving…' : isNew ? 'Add node' : 'Save changes'}
        </Button>
        <Button onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        {!isNew && (
          <>
            <Button variant="ghost" icon={Copy} onClick={onDuplicate} disabled={busy} className="ml-auto">
              Duplicate
            </Button>
            <Button variant="danger" icon={Trash2} onClick={onDelete} disabled={busy}>
              Delete
            </Button>
          </>
        )}
      </div>
    </form>
  )
}
