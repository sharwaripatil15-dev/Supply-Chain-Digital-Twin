import { useStore } from '../store.js'
import { EmptyState, cn } from './ui/index.js'

const parseDay = (line) => {
  const m = /^Day (\d+)/.exec(line)
  return m ? Number(m[1]) : null
}

function tone(line) {
  if (/STOCKOUT|DOWN/.test(line)) return 'bg-bad'
  if (/stressed/.test(line)) return 'bg-warn'
  if (/recovered|served again/.test(line)) return 'bg-ok'
  return 'bg-fg-muted'
}

/** The engine's day-by-day log. Click a line to jump to that day. */
export default function EventLog() {
  const { sim, day, setDay } = useStore()
  if (!sim) return <EmptyState title="No events yet" description="Run a scenario to see the ripple, day by day." />
  return (
    <ol className="space-y-px">
      {sim.log.map((line, i) => {
        const d = parseDay(line)
        const text = line.replace(/^Day \d+:\s*/, '')
        return (
          <li key={i}>
            <button
              type="button"
              onClick={() => d != null && setDay(d)}
              className={cn(
                'grid w-full grid-cols-[2.5rem_0.5rem_minmax(0,1fr)] items-start gap-2 rounded-sm px-1 py-1 text-left text-xs transition-colors duration-100 hover:bg-raised',
                d === day && 'bg-raised',
                d != null && d > day ? 'text-fg-muted' : 'text-fg-2',
              )}
            >
              <span className="num text-fg-muted">{d != null ? `d${d}` : ''}</span>
              <span className={cn('mt-1.5 h-1.5 w-1.5 rounded-full', tone(line))} aria-hidden />
              <span className="leading-5">{text}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}
