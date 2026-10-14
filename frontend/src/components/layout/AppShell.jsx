import { useRef, useState } from 'react'
import { Activity, CircleHelp, CloudRain, Database, ExternalLink, Keyboard, LayoutDashboard, LifeBuoy, Lightbulb, MapPinPlus, Moon, Network, PanelLeft, PanelRight, Presentation, Radar, ScanSearch, Search, ShieldCheck, Sun } from 'lucide-react'
import { SOURCE_LABEL, useStore } from '../../store.js'
import { useTheme } from '../../theme.jsx'
import { API_URL } from '../../api.js'
import { eventLabel } from '../../format.js'
import { MOD_LABEL, useHotkeys, useMediaQuery, useUi } from '../../ui.jsx'
import { Button, Divider, IconButton, Kbd, Menu, SegmentedControl, StatusDot, Tooltip, cn } from '../ui/index.js'
import DemoMode from '../DemoMode.jsx'
import CommandPalette from './CommandPalette.jsx'
import ShortcutsDialog from './ShortcutsDialog.jsx'

/** Navigation: seven pages for everyone, three analyst tools (shown in Analyst view, or while one is open). */
export const PAGES = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, title: 'Overview', purpose: 'How healthy the supply chain is and what to do next', key: '1', inspector: false, group: 'main' },
  { id: 'twin', label: 'Network', icon: Network, title: 'Network', purpose: 'Your sites and lanes, and how critical each one is', key: '2', inspector: true, group: 'main' },
  { id: 'whatif', label: 'What-if', icon: Lightbulb, title: 'What-if', purpose: 'Ask what happens if something goes wrong, and how to recover', key: '3', inspector: false, group: 'main' },
  { id: 'insights', label: 'Insights', icon: ScanSearch, title: 'Insights', purpose: 'Bottlenecks and pain points, each with a tested fix', key: '4', inspector: true, group: 'main' },
  { id: 'expansion', label: 'Expansion', icon: MapPinPlus, title: 'Expansion', purpose: 'Where to add a warehouse or plant, and what it pays back', key: '5', inspector: false, group: 'main' },
  { id: 'weather', label: 'Weather', icon: CloudRain, title: 'Weather', purpose: 'Weather and disaster risk on your routes, with re-routing', key: '6', inspector: false, group: 'main' },
  { id: 'data', label: 'Data', icon: Database, title: 'Data', purpose: 'Choose, upload or build the network; model accuracy', key: '7', inspector: false, group: 'main' },
  { id: 'simulate', label: 'Simulate', icon: Activity, title: 'Simulate', purpose: 'Play a disruption day by day', key: '8', inspector: true, group: 'tools' },
  { id: 'chaos', label: 'Chaos Finder', icon: Radar, title: 'Chaos Finder', purpose: 'Stress-test every single and paired failure', key: '9', inspector: true, group: 'tools' },
  { id: 'recover', label: 'Recover', icon: LifeBuoy, title: 'Recover', purpose: 'Compare recovery strategies for the current scenario', key: '0', inspector: true, group: 'tools' },
]

function Rail() {
  const { tab, setTab } = useStore()
  const { railPinned, setPref, analyst } = useUi()
  const [hover, setHover] = useState(false)
  const timer = useRef(null)
  const expanded = railPinned || hover
  return (
    <div className={cn('relative z-40 h-full shrink-0 transition-[width] duration-150', railPinned ? 'w-52' : 'w-14')}>
      <nav
        aria-label="Main"
        onMouseEnter={() => {
          clearTimeout(timer.current)
          timer.current = setTimeout(() => setHover(true), 250)
        }}
        onMouseLeave={() => {
          clearTimeout(timer.current)
          setHover(false)
        }}
        className={cn(
          'absolute inset-y-0 left-0 flex flex-col border-r border-border bg-surface transition-[width] duration-150',
          expanded ? 'w-52' : 'w-14',
          expanded && !railPinned && 'shadow-float',
        )}
      >
        <div className="flex h-12 shrink-0 items-center gap-2.5 border-b border-border px-4">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-fg text-bg">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
          </span>
          <span className={cn('text-sm font-semibold tracking-wide text-fg transition-opacity duration-150', expanded ? 'visible opacity-100' : 'invisible opacity-0')}>AEGIS</span>
        </div>
        <ul className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {PAGES.filter((p) => p.group === 'main' || analyst || p.id === tab).map((p, i, arr) => {
            const active = tab === p.id
            const Icon = p.icon
            const firstTool = p.group === 'tools' && arr[i - 1]?.group !== 'tools'
            return (
              <li key={p.id}>
                {firstTool && (
                  <div className="mx-3 mb-1 mt-3 border-t border-border pt-2">
                    <span className={cn('section-label transition-opacity duration-150', expanded ? 'opacity-100' : 'opacity-0')}>Analyst tools</span>
                  </div>
                )}
                <Tooltip content={expanded ? null : p.label} shortcut={p.key} side="right" className="w-full">
                  <button
                    type="button"
                    onClick={() => setTab(p.id)}
                    aria-current={active ? 'page' : undefined}
                    aria-label={p.label}
                    aria-keyshortcuts={p.key}
                    className={cn(
                      'relative flex h-8 w-full items-center gap-3 rounded-md px-3 text-sm transition-colors duration-150',
                      active ? 'bg-raised text-fg' : 'text-fg-2 hover:bg-raised hover:text-fg',
                    )}
                  >
                    {active && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-accent" aria-hidden />}
                    <Icon className={cn('h-4 w-4 shrink-0', active && 'text-accent')} aria-hidden />
                    <span className={cn('flex-1 whitespace-nowrap text-left transition-opacity duration-150', expanded ? 'visible opacity-100' : 'invisible opacity-0')}>{p.label}</span>
                    {expanded && <Kbd>{p.key}</Kbd>}
                  </button>
                </Tooltip>
              </li>
            )
          })}
        </ul>
        <div className="border-t border-border p-2">
          <Tooltip content={expanded && !railPinned ? null : railPinned ? 'Unpin sidebar' : 'Pin sidebar'} shortcut="[" side="right" className="w-full">
            <button
              type="button"
              onClick={() => setPref('railPinned', (v) => !v)}
              aria-pressed={railPinned}
              aria-label={railPinned ? 'Unpin sidebar' : 'Pin sidebar'}
              className="flex h-8 w-full items-center gap-3 rounded-md px-3 text-sm text-fg-2 transition-colors duration-150 hover:bg-raised hover:text-fg"
            >
              <PanelLeft className="h-4 w-4 shrink-0" aria-hidden />
              <span className={cn('whitespace-nowrap transition-opacity duration-150', expanded ? 'visible opacity-100' : 'invisible opacity-0')}>{railPinned ? 'Unpin' : 'Pin'} sidebar</span>
            </button>
          </Tooltip>
        </div>
      </nav>
    </div>
  )
}

function StatusButton({ label, children, onClick, title }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="flex h-8 min-w-0 items-center gap-1.5 rounded-md px-2 text-xs transition-colors duration-150 hover:bg-raised"
    >
      <span className="hidden text-fg-muted xl:inline">{label}</span>
      {children}
    </button>
  )
}

function TopBar() {
  const { tab, events, sim, day, source, setTab } = useStore()
  const { theme, toggle } = useTheme()
  const ui = useUi()
  const docked = useMediaQuery('(min-width: 1280px)')
  const page = PAGES.find((p) => p.id === tab)
  const scenario = events.length ? `${eventLabel(events[0])}${events.length > 1 ? ` +${events.length - 1}` : ''}` : 'None'
  const last = sim ? sim.timeline.length - 1 : 0
  const inspectorShown = docked ? ui.inspectorOpen : ui.overlayOpen
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-surface pl-4 pr-2">
      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-sm">
        <span className="text-fg-muted">AEGIS</span>
        <span className="text-fg-muted" aria-hidden>
          /
        </span>
        <h1 className="shrink-0 text-sm font-semibold text-fg">{page?.title}</h1>
        {page?.purpose && <span className="hidden truncate text-xs text-fg-muted lg:inline">· {page.purpose}</span>}
      </nav>
      <div className="ml-auto flex min-w-0 items-center gap-1">
        {source && (
          <StatusButton label="Network" onClick={() => setTab('data')} title="Active network (change it on the Data page)">
            <StatusDot status={source.runnable ? 'ok' : 'warn'} label={`${SOURCE_LABEL[source.source]}${source.source === 'preset' ? '' : ` · v${source.version}`}${source.runnable ? '' : ' · needs fixes'}`} textClassName="text-fg" />
          </StatusButton>
        )}
        <Divider />
        <StatusButton label="Scenario" onClick={() => setTab('simulate')} title="Current scenario">
          <span className="max-w-[180px] truncate text-fg">{scenario}</span>
          {sim && <span className="num text-fg-muted">d{day}/{last}</span>}
        </StatusButton>
        <Divider />
        <SegmentedControl
          size="xs"
          label="View"
          value={ui.analyst ? 'analyst' : 'executive'}
          onChange={(v) => ui.setPref('view', v)}
          options={[
            { value: 'executive', label: 'Executive', title: 'Plain-language summaries' },
            { value: 'analyst', label: 'Analyst', title: 'Adds evidence, engine details and the analyst tools' },
          ]}
        />
        <Button size="sm" variant="ghost" icon={Presentation} onClick={() => ui.setDemo({ phase: 'start' })} title="Load a demo network and walk through it">
          Demo
        </Button>
        <Divider />
        <button
          type="button"
          onClick={() => ui.setPaletteOpen(true)}
          className="ml-1 flex h-8 items-center gap-2 rounded-md border border-border px-2 text-xs text-fg-muted transition-colors duration-150 hover:bg-raised hover:text-fg"
          aria-label="Open command palette"
          aria-keyshortcuts="Control+K Meta+K"
        >
          <Search className="h-3.5 w-3.5" aria-hidden />
          <span className="hidden lg:inline">Search</span>
          <Kbd>{MOD_LABEL} K</Kbd>
        </button>
        {page?.inspector && (
          <IconButton
            icon={PanelRight}
            label={inspectorShown ? 'Hide inspector' : 'Show inspector'}
            shortcut="I"
            pressed={inspectorShown}
            onClick={() => (docked ? ui.setPref('inspectorOpen', (v) => !v) : ui.setOverlayOpen((v) => !v))}
          />
        )}
        <IconButton icon={theme === 'dark' ? Sun : Moon} label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} onClick={toggle} />
        <Menu
          icon={CircleHelp}
          iconOnly
          label="Help"
          triggerLabel="Help"
          variant="ghost"
          size="md"
          items={[
            { key: 'keys', label: 'Keyboard shortcuts', icon: Keyboard, shortcut: '?', onSelect: () => ui.setShortcutsOpen(true) },
            { key: 'api', label: 'API reference', icon: ExternalLink, onSelect: () => window.open(`${API_URL}/docs`, '_blank', 'noopener') },
          ]}
        />
      </div>
    </header>
  )
}

export default function AppShell({ children }) {
  const store = useStore()
  const ui = useUi()
  const docked = useMediaQuery('(min-width: 1280px)')
  const page = PAGES.find((p) => p.id === store.tab)

  useHotkeys({
    'mod+k': { handler: () => ui.setPaletteOpen((v) => !v), allowInInputs: true },
    ...Object.fromEntries(PAGES.map((p) => [p.key, () => store.setTab(p.id)])),
    '[': () => ui.setPref('railPinned', (v) => !v),
    i: () => {
      if (!page?.inspector) return false
      if (docked) ui.setPref('inspectorOpen', (v) => !v)
      else ui.setOverlayOpen((v) => !v)
    },
    '?': () => ui.setShortcutsOpen(true),
    f: () => ui.requestFit(),
    space: () => {
      if (store.tab !== 'simulate' || !store.sim) return false
      ui.togglePlay()
    },
    escape: () => {
      if (ui.story) return ui.stopStory()
      if (!store.selectedNode) return false
      store.selectNode(null)
    },
  })

  return (
    <div className="flex h-screen overflow-hidden bg-bg text-fg">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <Rail />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main id="main" className="min-h-0 flex-1 overflow-auto">
          {children}
        </main>
      </div>
      <CommandPalette />
      <ShortcutsDialog />
      <DemoMode />
    </div>
  )
}
