import { CircleCheck, CircleX, ListOrdered, TriangleAlert, Zap } from 'lucide-react'
import { useStore } from '../store.js'
import { Card, CardBody, CardHeader, EmptyState, cn } from './ui/index.js'

const parseDay = (line) => {
  const m = /^Day (\d+)/.exec(line)
  return m ? Number(m[1]) : null
}

function kind(line) {
  if (/STOCKOUT|DOWN/.test(line)) return { icon: CircleX, cls: 'text-bad' }
  if (/stressed/.test(line)) return { icon: TriangleAlert, cls: 'text-warn' }
  if (/recovered|served again/.test(line)) return { icon: CircleCheck, cls: 'text-ok' }
  return { icon: Zap, cls: 'text-accent' }
}

export default function EventLog() {
  const { sim, day, setDay } = useStore()
  return (
    <Card>
      <CardHeader title="Event log" description="Click a line to jump to that day." icon={ListOrdered} />
      <CardBody className="pt-2">
        {!sim ? (
          <EmptyState icon={ListOrdered} title="No events yet" description="Run a scenario to see the ripple, day by day." />
        ) : (
          <ol className="max-h-80 space-y-0.5 overflow-y-auto pr-1">
            {sim.log.map((line, i) => {
              const d = parseDay(line)
              const k = kind(line)
              const Icon = k.icon
              return (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => d != null && setDay(d)}
                    className={cn(
                      'flex w-full items-start gap-2 rounded-md px-2 py-1 text-left text-xs transition-colors duration-150 hover:bg-surface-2',
                      d === day && 'bg-accent/5',
                      d != null && d > day ? 'text-fg-muted' : 'text-fg-2',
                    )}
                  >
                    <Icon className={cn('mt-0.5 h-3.5 w-3.5 shrink-0', k.cls)} aria-hidden />
                    <span className="leading-5">{line}</span>
                  </button>
                </li>
              )
            })}
          </ol>
        )}
      </CardBody>
    </Card>
  )
}
