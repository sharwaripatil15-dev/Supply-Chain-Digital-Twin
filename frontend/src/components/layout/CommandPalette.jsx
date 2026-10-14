import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { CornerDownLeft, Search } from 'lucide-react'
import { DEMO_SCENARIOS, useStore } from '../../store.js'
import { useTheme } from '../../theme.jsx'
import { scenariosFor } from '../../lib/scenarios.js'
import { typeOf } from '../../lib/nodeTypes.js'
import { useUi } from '../../ui.jsx'
import { Kbd, useFocusTrap, cn } from '../ui/index.js'
import { TypeIcon } from '../NodeTypeIcon.jsx'
import { PAGES } from './AppShell.jsx'

const norm = (s) => String(s || '').toLowerCase()

/** Ctrl/Cmd+K: jump to a page, a node or a scenario, or run a quick action. */
export default function CommandPalette() {
  const store = useStore()
  const ui = useUi()
  const { theme, toggle } = useTheme()
  const open = ui.paletteOpen
  const close = () => ui.setPaletteOpen(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const ref = useRef(null)
  const listRef = useRef(null)
  const id = useId()
  useFocusTrap(ref, open, close)

  useEffect(() => {
    if (open) {
      setQuery('')
      setActive(0)
    }
  }, [open])

  const items = useMemo(() => {
    if (!open) return []
    const runnable = !store.source || store.source.runnable
    const isPreset = !store.source || store.source.source === 'preset'
    const pages = PAGES.map((p) => ({
      id: `page-${p.id}`, group: 'Pages', label: p.label, hint: p.key, icon: p.icon, run: () => store.setTab(p.id),
    }))
    const scenarios = runnable
      ? scenariosFor(store.network, DEMO_SCENARIOS, isPreset).map((s) => ({
          id: `scn-${s.id}`, group: 'Scenarios', label: `Run: ${s.label}`, detail: s.blurb,
          run: () => {
            store.setTab('simulate')
            store.runSimulation(s.events)
          },
        }))
      : []
    const nodes = (store.network?.nodes ?? []).map((n) => ({
      id: `node-${n.id}`, group: 'Nodes', label: `${n.id} · ${n.name || n.city}`, detail: typeOf(n.kind).label, kind: n.kind,
      run: () => {
        if (!['twin', 'simulate', 'chaos', 'recover'].includes(store.tab)) store.setTab('twin')
        store.selectNode(n.id)
      },
    }))
    const findings = (store.analysis?.status === 'ok' ? store.analysis.findings : []).map((f) => ({
      id: `finding-${f.id}`, group: 'Findings', label: f.title, detail: `${f.severity_level} · ${f.type_label}`,
      run: () => {
        store.selectFinding(f.id)
        store.setTab('insights')
      },
    }))
    const actions = [
      { id: 'act-theme', group: 'Actions', label: theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme', run: toggle },
      { id: 'act-builder', group: 'Actions', label: 'Open the network builder', run: () => (ui.setDataView('manual'), store.setTab('data')) },
      { id: 'act-keys', group: 'Actions', label: 'Keyboard shortcuts', hint: '?', run: () => ui.setShortcutsOpen(true) },
    ]
    const all = [...pages, ...findings, ...scenarios, ...nodes, ...actions]
    const q = norm(query).trim()
    if (!q) return all.filter((x) => x.group !== 'Nodes' && x.group !== 'Findings').concat(findings.slice(0, 3), nodes.slice(0, 6))
    return all
      .map((x) => {
        const hay = `${norm(x.label)} ${norm(x.detail)}`
        const at = hay.indexOf(q)
        return at < 0 ? null : { ...x, score: (norm(x.label).startsWith(q) ? 0 : 1) + at / 100 }
      })
      .filter(Boolean)
      .sort((a, b) => a.score - b.score)
      .slice(0, 30)
  }, [open, query, store, theme, toggle, ui])

  useEffect(() => setActive(0), [query])
  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [active])

  if (!open) return null
  const choose = (item) => {
    if (!item) return
    close()
    item.run()
  }
  const onKey = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => Math.min(items.length - 1, a + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => Math.max(0, a - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      choose(items[active])
    }
  }

  let lastGroup = null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[14vh]">
      <div className="absolute inset-0 animate-fade-in bg-fg/25 dark:bg-bg/70" onClick={close} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" aria-label="Command palette" className="relative w-full max-w-xl animate-rise-in overflow-hidden rounded-lg border border-border bg-surface shadow-float">
        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search className="h-4 w-4 shrink-0 text-fg-muted" aria-hidden />
          <input
            data-autofocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKey}
            placeholder="Jump to a page, node or scenario…"
            className="h-11 flex-1 bg-transparent text-sm text-fg outline-none placeholder:text-fg-muted"
            role="combobox"
            aria-expanded="true"
            aria-controls={id}
            aria-activedescendant={items[active] ? `${id}-${items[active].id}` : undefined}
            aria-autocomplete="list"
          />
          <Kbd>Esc</Kbd>
        </div>
        <ul ref={listRef} id={id} role="listbox" aria-label="Results" className="max-h-[52vh] overflow-y-auto p-1">
          {items.length === 0 && <li className="px-3 py-6 text-center text-xs text-fg-muted">No matches.</li>}
          {items.map((it, i) => {
            const header = it.group !== lastGroup ? it.group : null
            lastGroup = it.group
            const Icon = it.icon
            return (
              <li key={it.id} role="presentation">
                {header && <div className="section-label px-2 pb-1 pt-2">{header}</div>}
                <div
                  id={`${id}-${it.id}`}
                  role="option"
                  aria-selected={i === active}
                  data-index={i}
                  onMouseMove={() => setActive(i)}
                  onClick={() => choose(it)}
                  className={cn('flex h-9 cursor-pointer items-center gap-2.5 rounded-md px-2 text-sm', i === active ? 'bg-raised text-fg' : 'text-fg-2')}
                >
                  {it.kind ? <TypeIcon kind={it.kind} size="xs" /> : Icon ? <Icon className="h-4 w-4 text-fg-muted" aria-hidden /> : <span className="h-4 w-4" />}
                  <span className="min-w-0 flex-1 truncate">{it.label}</span>
                  {it.detail && <span className="max-w-[45%] truncate text-xs text-fg-muted">{it.detail}</span>}
                  {it.hint && <Kbd>{it.hint}</Kbd>}
                  {i === active && <CornerDownLeft className="h-3.5 w-3.5 text-fg-muted" aria-hidden />}
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
