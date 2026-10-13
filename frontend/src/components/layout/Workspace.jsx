import { useEffect, useRef } from 'react'
import { useStore } from '../../store.js'
import { useMediaQuery, useUi } from '../../ui.jsx'
import { Drawer, cn } from '../ui/index.js'
import NodeInspector from '../NodeInspector.jsx'

/**
 * Master/detail workspace: the primary content (canvas, tables) plus a collapsible right inspector.
 * The inspector shows the selected node, or the page's own `inspector` content when nothing is selected.
 * At >= 1280px it is docked; below that it becomes an overlay drawer.
 */
export default function Workspace({ children, inspector, inspectorLabel = 'Inspector', className, mainClassName, framed = true }) {
  const { selectedNode, network, upload, tab } = useStore()
  const { inspectorOpen, setPref, overlayOpen, setOverlayOpen } = useUi()
  const docked = useMediaQuery('(min-width: 1280px)')
  const pool = tab === 'twin' && upload?.network && !upload.activated ? upload.network : network
  const nodeSelected = Boolean(selectedNode && pool?.nodes?.some((n) => n.id === selectedNode))

  // Selecting a node always reveals the inspector.
  const prev = useRef(selectedNode)
  useEffect(() => {
    if (nodeSelected && selectedNode !== prev.current) {
      if (docked) setPref('inspectorOpen', true)
      else setOverlayOpen(true)
    }
    prev.current = selectedNode
  }, [nodeSelected, selectedNode, docked, setPref, setOverlayOpen])

  const content = nodeSelected ? <NodeInspector key={selectedNode} /> : inspector
  return (
    <div className={cn('flex min-h-0 overflow-hidden', framed && 'rounded-lg border border-border bg-surface', className)}>
      <div className={cn('relative min-w-0 flex-1', mainClassName)}>{children}</div>
      {docked && inspectorOpen && content && (
        <aside
          aria-label={inspectorLabel}
          className={cn('flex w-[320px] shrink-0 animate-fade-in flex-col overflow-hidden bg-surface', framed ? 'border-l border-border' : 'ml-3 rounded-lg border border-border')}
        >
          {content}
        </aside>
      )}
      {!docked && (
        <Drawer open={overlayOpen && Boolean(content)} onClose={() => setOverlayOpen(false)} title={inspectorLabel} showClose={!nodeSelected}>
          {content}
        </Drawer>
      )}
    </div>
  )
}

/** Standard inspector header + scrollable body. */
export function InspectorPanel({ title, meta, actions, children }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex min-h-12 items-center gap-2 border-b border-border px-4 py-2 pr-10">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-medium text-fg">{title}</h2>
          {meta && <p className="truncate text-xs text-fg-muted">{meta}</p>}
        </div>
        {actions}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
    </div>
  )
}
