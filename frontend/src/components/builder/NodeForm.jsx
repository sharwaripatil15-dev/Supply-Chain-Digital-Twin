import { useEffect, useId, useMemo, useState } from 'react'
import { Copy, Crosshair, Search, Trash2, X } from 'lucide-react'
import { NODE_KINDS, fieldsFor, typeOf } from '../../lib/nodeTypes.js'
import { blankNode, nodeDraft, nodePayload, nextId, validateNode } from '../../lib/nodeForm.js'
import { searchCities } from '../../lib/indianCities.js'
import { Button, Checkbox, Field, IconButton, InlineError, Input, SectionLabel, Select, cn } from '../ui/index.js'
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

/** The five node types: icon, color, one-line description. */
export function TypePicker({ onPick }) {
  return (
    <ul className="-mx-2 space-y-0.5">
      {NODE_KINDS.map((k) => {
        const t = typeOf(k)
        return (
          <li key={k}>
            <button type="button" onClick={() => onPick(k)} className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors duration-150 hover:bg-raised">
              <TypeIcon kind={k} size="md" />
              <span className="min-w-0">
                <span className="block text-sm text-fg">{t.label}</span>
                <span className="block truncate text-xs text-fg-muted">{t.blurb}</span>
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

/** A field from the node-type definitions: label above, unit as a suffix, inline error below. */
function DefField({ def, value, error, onChange }) {
  const id = useId()
  if (def.type === 'checkbox') {
    return <Checkbox className="col-span-2" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} label={def.label} />
  }
  return (
    <Field label={def.label} htmlFor={id} error={error} required={def.required} className={def.type === 'text' ? 'col-span-2' : ''}>
      {def.type === 'select' ? (
        <Select id={id} value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
          {def.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </Select>
      ) : (
        <Input
          id={id}
          type={def.type === 'number' ? 'number' : 'text'}
          inputMode={def.type === 'number' ? 'decimal' : undefined}
          min={def.min}
          max={def.max}
          step={def.step ?? 'any'}
          maxLength={def.maxLength}
          placeholder={def.placeholder}
          suffix={def.unit}
          invalid={Boolean(error)}
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </Field>
  )
}

/** City combobox: search ~45 Indian cities; choosing one fills latitude, longitude (and the address if empty). */
function CitySearch({ onPick }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const results = useMemo(() => searchCities(q, 8), [q])
  const listId = useId()
  const pick = (c) => {
    onPick(c)
    setQ(c.name)
    setOpen(false)
  }
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-2 h-4 w-4 text-fg-muted" aria-hidden />
      <Input
        className="pl-8"
        placeholder="Search a city (Pune, Nagpur…)"
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
          setActive(0)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') (e.preventDefault(), setOpen(true), setActive((a) => Math.min(results.length - 1, a + 1)))
          else if (e.key === 'ArrowUp') (e.preventDefault(), setActive((a) => Math.max(0, a - 1)))
          else if (e.key === 'Enter' && open && results[active]) (e.preventDefault(), pick(results[active]))
          else if (e.key === 'Escape') setOpen(false)
        }}
        aria-label="Search Indian cities"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && results[active] ? `${listId}-${active}` : undefined}
      />
      {open && results.length > 0 && (
        <ul id={listId} role="listbox" className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border border-border bg-surface p-1 shadow-float">
          {results.map((c, i) => (
            <li
              key={c.name}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setActive(i)}
              onClick={() => pick(c)}
              className={cn('flex cursor-pointer items-center justify-between rounded-sm px-2 py-1.5 text-sm', i === active ? 'bg-raised text-fg' : 'text-fg-2')}
            >
              <span>{c.name}</span>
              <span className="num text-2xs text-fg-muted">
                {c.lat.toFixed(2)}, {c.lon.toFixed(2)}
              </span>
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
  const idField = useId()

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
  const byKey = Object.fromEntries(common.map((f) => [f.key, f]))

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
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col" noValidate aria-label={isNew ? `New ${type.label.toLowerCase()}` : `Edit ${node.id}`}>
      <div className="flex items-center gap-2.5 border-b border-border px-4 py-2.5">
        <TypeIcon kind={draft.kind} size="md" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-fg">{isNew ? `New ${type.label.toLowerCase()}` : node.name}</p>
          <p className="truncate text-xs text-fg-muted">{isNew ? type.blurb : <span className="num">{node.id}</span>}</p>
        </div>
        <IconButton icon={X} label="Close" shortcut="Esc" size="sm" tooltipSide="left" onClick={onCancel} />
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-3">
        <section className="space-y-3">
          <SectionLabel>Identity</SectionLabel>
          <div className="grid grid-cols-2 gap-3">
            <Field label="ID" htmlFor={idField} error={errorFor('id')} hint={isNew ? 'Leave empty for an automatic id' : 'Set when the node is created'}>
              <Input
                id={idField}
                className="num"
                value={isNew ? draft.id ?? '' : node.id}
                placeholder={suggestedId}
                disabled={!isNew}
                maxLength={24}
                invalid={Boolean(errorFor('id'))}
                onChange={(e) => set('id', e.target.value.trim())}
              />
            </Field>
            <Field label="Status" htmlFor={`${idField}-status`}>
              <Select id={`${idField}-status`} value={draft.status || 'active'} onChange={(e) => set('status', e.target.value)}>
                <option value="active">Active</option>
                <option value="inactive">Inactive (left out of runs)</option>
              </Select>
            </Field>
            <DefField def={byKey.name} value={draft.name} error={errorFor('name')} onChange={(v) => set('name', v)} />
          </div>
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <SectionLabel>Location</SectionLabel>
            <Button size="xs" variant={picking ? 'primary' : 'ghost'} icon={Crosshair} onClick={onTogglePick} aria-pressed={picking}>
              {picking ? 'Click the map…' : 'Pick on map'}
            </Button>
          </div>
          <CitySearch
            onPick={(c) => {
              setDraft((d) => ({ ...d, lat: c.lat, lon: c.lon, city: d.city || c.name }))
              setTouched((t) => ({ ...t, lat: true, lon: true }))
            }}
          />
          <div className="grid grid-cols-2 gap-3">
            <DefField def={{ key: 'lat', label: 'Latitude', type: 'number', min: -90, max: 90, placeholder: '18.520', unit: '°' }} value={draft.lat} error={errorFor('lat')} onChange={(v) => set('lat', v)} />
            <DefField def={{ key: 'lon', label: 'Longitude', type: 'number', min: -180, max: 180, placeholder: '73.857', unit: '°' }} value={draft.lon} error={errorFor('lon')} onChange={(v) => set('lon', v)} />
            <DefField def={byKey.city} value={draft.city} error={errorFor('city')} onChange={(v) => set('city', v)} />
          </div>
        </section>

        <section className="space-y-3">
          <SectionLabel>Capacity and stock</SectionLabel>
          <div className="grid grid-cols-2 gap-3">
            {common
              .filter((f) => !['name', 'city'].includes(f.key))
              .map((f) => (
                <DefField key={f.key} def={f} value={draft[f.key]} error={errorFor(f.key)} onChange={(v) => set(f.key, v)} />
              ))}
          </div>
        </section>

        <section className="space-y-3">
          <SectionLabel>{type.label} details</SectionLabel>
          <div className="grid grid-cols-2 gap-3">
            {specific.map((f) => (
              <DefField key={f.key} def={f} value={draft[f.key]} error={errorFor(f.key)} onChange={(v) => set(f.key, v)} />
            ))}
          </div>
        </section>
        <InlineError message={formError} />
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-border bg-surface px-4 py-2.5">
        {!isNew && (
          <>
            <IconButton icon={Copy} label="Duplicate" size="md" tooltipSide="top" onClick={onDuplicate} disabled={busy} />
            <IconButton icon={Trash2} label="Delete" variant="ghost-danger" size="md" tooltipSide="top" onClick={onDelete} disabled={busy} />
          </>
        )}
        <div className="ml-auto flex gap-2">
          <Button onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" disabled={!valid || busy} title={valid ? undefined : 'Fix the highlighted fields first'}>
            {busy ? 'Saving…' : isNew ? 'Add node' : 'Save'}
          </Button>
        </div>
      </div>
    </form>
  )
}
