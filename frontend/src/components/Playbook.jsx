import { ClipboardList } from 'lucide-react'
import { useStore } from '../store.js'
import { Card, CardBody, CardHeader } from './ui/index.js'

export default function Playbook() {
  const { recover } = useStore()
  if (!recover?.playbook?.length) return null
  return (
    <Card>
      <CardHeader title="Action playbook" description="Narrated from engine output only: no number is computed by the LLM" icon={ClipboardList} />
      <CardBody>
        <ol className="space-y-3">
          {recover.playbook.map((step, i) => {
            const m = /^(Day \d+[^:]*|Post-incident):\s*(.*)$/.exec(step)
            return (
              <li key={i} className="flex gap-3">
                <span className="tabular flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/10 text-xs font-semibold text-accent">
                  {i + 1}
                </span>
                <p className="pt-0.5 text-sm text-fg-2">
                  {m ? (
                    <>
                      <span className="font-medium text-fg">{m[1]}</span> · {m[2]}
                    </>
                  ) : (
                    step
                  )}
                </p>
              </li>
            )
          })}
        </ol>
      </CardBody>
    </Card>
  )
}
