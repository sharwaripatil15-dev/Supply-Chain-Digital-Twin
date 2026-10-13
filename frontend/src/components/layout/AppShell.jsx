import { useEffect, useState } from 'react'
import {
  Activity,
  Database,
  FlaskConical,
  LayoutDashboard,
  LifeBuoy,
  Moon,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Radar,
  ShieldCheck,
  Sun,
} from 'lucide-react'
import { SOURCE_LABEL, useStore } from '../../store.js'
import { useTheme } from '../../theme.jsx'
import { API_URL } from '../../api.js'
import { eventLabel } from '../../format.js'
import { Badge, Button, Tooltip, cn } from '../ui/index.js'
import NodeDrawer from '../NodeDrawer.jsx'

export const PAGES = [
  { id: 'twin', label: 'Twin', icon: Network, title: 'Digital twin' },
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, title: 'Disruptions & recovery dashboard' },
  { id: 'simulate', label: 'Simulator', icon: Activity, title: 'Disruption simulator' },
  { id: 'chaos', label: 'Chaos Finder', icon: Radar, title: 'Chaos Finder' },
  { id: 'recover', label: 'Recover', icon: LifeBuoy, title: 'Recovery planner' },
  { id: 'data', label: 'Data', icon: Database, title: 'Data & models' },
]

function useCollapsedSidebar() {
  const [collapsed, setCollapsed] = useState(() => typeof window !== 'undefined' && window.innerWidth < 1024)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 1023px)')
    const onChange = (e) => setCollapsed(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return [collapsed, setCollapsed]
}

function Sidebar({ collapsed, onToggle }) {
  const { tab, setTab } = useStore()
  return (
    <nav
      aria-label="Main"
      className={cn(
        'sticky top-0 flex h-screen shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200',
        collapsed ? 'w-16' : 'w-[220px]',
      )}
    >
      <div className={cn('flex h-14 items-center gap-2.5 px-4', collapsed && 'justify-center px-0')}>
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-accent-fg">
          <ShieldCheck className="h-4 w-4" aria-hidden />
        </span>
        {!collapsed && (
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-wide text-fg">AEGIS</div>
            <div className="text-xs text-fg-muted">Supply chain twin</div>
          </div>
        )}
      </div>
      <ul className="mt-2 flex-1 space-y-0.5 px-2">
        {PAGES.map((p) => {
          const active = tab === p.id || (p.id === 'simulate' && tab === 'whatif')
          const Icon = p.icon
          const item = (
            <button
              type="button"
              onClick={() => setTab(p.id)}
              aria-current={active ? 'page' : undefined}
              aria-label={collapsed ? p.label : undefined}
              className={cn(
                'flex h-9 w-full items-center gap-2.5 rounded-lg px-2.5 text-sm font-medium transition-colors duration-150',
                collapsed && 'justify-center px-0',
                active ? 'bg-accent/10 text-accent' : 'text-fg-2 hover:bg-surface-2 hover:text-fg',
              )}
            >
              <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
              {!collapsed && p.label}
            </button>
          )
          return (
            <li key={p.id}>
              {collapsed ? (
                <Tooltip content={p.label} className="w-full">
                  {item}
                </Tooltip>
              ) : (
                item
              )}
            </li>
          )
        })}
      </ul>
      <div className={cn('border-t border-border p-2', collapsed && 'flex justify-center')}>
        {!collapsed && <p className="truncate px-2 pb-2 text-xs text-fg-muted" title={API_URL}>API · {API_URL.replace(/^https?:\/\//, '')}</p>}
        <Button
          variant="ghost"
          size={collapsed ? 'icon' : 'sm'}
          icon={collapsed ? PanelLeftOpen : PanelLeftClose}
          onClick={onToggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className={collapsed ? '' : 'w-full'}
        >
          {!collapsed && 'Collapse'}
        </Button>
      </div>
    </nav>
  )
}

function TopBar() {
  const { tab, events, sim, network, chaos, source, setTab } = useStore()
  const { theme, toggle } = useTheme()
  const page = PAGES.find((p) => p.id === tab)
  const resilience = chaos?.resilience_score ?? network?.resilience_score
  const scenario = events.length ? `${eventLabel(events[0])}${events.length > 1 ? ` +${events.length - 1}` : ''}` : 'No scenario'
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-bg/85 px-6 backdrop-blur">
      <h1 className="text-sm font-semibold text-fg">{page?.title}</h1>
      <div className="ml-auto flex items-center gap-2">
        {source && (
          <button type="button" onClick={() => setTab('data')} className="rounded-md" title="Active network source: change it on the Data tab">
            <Badge tone={source.runnable ? 'accent' : 'warn'} icon={Database} className="cursor-pointer hover:brightness-95">
              {SOURCE_LABEL[source.source]}
              {!source.runnable && ' · needs fixes'}
            </Badge>
          </button>
        )}
        <Badge tone={sim ? 'accent' : 'neutral'} dot title="Active scenario" className="hidden max-w-[260px] truncate md:inline-flex">
          {scenario}
        </Badge>
        {resilience != null && (
          <Badge tone={resilience >= 70 ? 'ok' : resilience >= 40 ? 'warn' : 'bad'} title="Resilience score (Chaos Finder)">
            Resilience <span className="tabular">{resilience.toFixed(1)}</span>
          </Badge>
        )}
        <Button
          variant="ghost"
          size="icon"
          icon={theme === 'dark' ? Sun : Moon}
          onClick={toggle}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        />
      </div>
    </header>
  )
}

export default function AppShell({ children }) {
  const [collapsed, setCollapsed] = useCollapsedSidebar()
  return (
    <div className="flex min-h-screen bg-bg">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="mx-auto w-full max-w-[1440px] flex-1 px-6 py-6">{children}</main>
      </div>
      <NodeDrawer />
    </div>
  )
}
