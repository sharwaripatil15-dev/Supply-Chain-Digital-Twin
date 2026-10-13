import { useStore } from '../store.js'
import { EmptyState } from './ui/index.js'
import { InspectorPanel } from './layout/Workspace.jsx'

/** The action playbook as a numbered list (narrated from engine output only). */
export default function Playbook() {
  const { recover, loading } = useStore()
  const steps = recover?.playbook ?? []
  return (
    <InspectorPanel title="Playbook" meta="Narrated from engine output; no number comes from the LLM">
      {steps.length === 0 ? (
        <EmptyState title={loading.recover ? 'Planning…' : 'No playbook yet'} description={loading.recover ? undefined : 'Compute a recovery plan first.'} />
      ) : (
        <ol className="space-y-3 px-4 py-3">
          {steps.map((step, i) => {
            const m = /^(Day \d+[^:]*|Post-incident):\s*(.*)$/.exec(step)
            return (
              <li key={i} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2 text-sm">
                <span className="num pt-px text-xs text-fg-muted">{String(i + 1).padStart(2, '0')}</span>
                <p className="text-fg-2">
                  {m ? (
                    <>
                      <span className="font-medium text-fg">{m[1]}</span>
                      <span className="block">{m[2]}</span>
                    </>
                  ) : (
                    step
                  )}
                </p>
              </li>
            )
          })}
        </ol>
      )}
    </InspectorPanel>
  )
}
