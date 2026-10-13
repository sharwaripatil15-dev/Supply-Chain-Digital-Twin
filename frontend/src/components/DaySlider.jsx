import { useEffect, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { useStore } from '../store.js'
import { STATUS, fmtNum } from '../format.js'
import { Badge, Button, cn } from './ui/index.js'

/** Timeline scrubber. Drives store.day, so the 2D and 3D views stay in sync. */
export default function DaySlider() {
  const { sim, day, setDay } = useStore()
  const [playing, setPlaying] = useState(false)
  const last = sim ? sim.timeline.length - 1 : 0

  useEffect(() => {
    if (!playing) return
    if (day >= last) {
      setPlaying(false)
      return
    }
    const id = setTimeout(() => setDay(day + 1), 450)
    return () => clearTimeout(id)
  }, [playing, day, last, setDay])

  if (!sim) return null
  const row = sim.timeline[day] || sim.timeline[0]
  const counts = Object.values(row.node_status).reduce((acc, s) => ({ ...acc, [s]: (acc[s] || 0) + 1 }), {})
  const max = Math.max(...sim.timeline.map((x) => x.unmet), 1)

  return (
    <div className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="secondary"
          size="sm"
          icon={playing ? Pause : Play}
          onClick={() => {
            if (day >= last) setDay(0)
            setPlaying((p) => !p)
          }}
          aria-label={playing ? 'Pause timeline' : 'Play timeline'}
        >
          {playing ? 'Pause' : 'Play'}
        </Button>
        <div className="text-sm text-fg-muted">
          Day <span className="tabular text-base font-semibold text-fg">{row.day}</span> / {last}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(STATUS).map(([k, s]) => (
            <Badge key={k} tone={s.tone} dot>
              <span className="tabular">{counts[k] || 0}</span> {s.label.toLowerCase()}
            </Badge>
          ))}
        </div>
        <div className="ml-auto text-sm text-fg-muted">
          Unmet today <span className="tabular font-semibold text-fg">{fmtNum(row.unmet)}</span>
        </div>
      </div>
      <input
        type="range"
        min={0}
        max={last}
        value={day}
        onChange={(e) => {
          setPlaying(false)
          setDay(Number(e.target.value))
        }}
        className="mt-3 w-full"
        aria-label="Simulation day"
      />
      <div className="mt-1 flex h-8 items-end gap-px" aria-hidden>
        {sim.timeline.map((d) => (
          <button
            key={d.day}
            type="button"
            tabIndex={-1}
            title={`Day ${d.day}: ${fmtNum(d.unmet)} unmet`}
            onClick={() => setDay(d.day)}
            className={cn(
              'flex-1 rounded-t-sm transition-colors duration-150',
              d.day === day ? 'bg-fg' : d.unmet > 0 ? 'bg-accent/70 hover:bg-accent' : 'bg-surface-3 hover:bg-border-strong',
            )}
            style={{ height: `${Math.max(8, (d.unmet / max) * 100)}%` }}
          />
        ))}
      </div>
      {row.down.length > 0 && <p className="mt-2 text-xs text-fg-muted">Down: {row.down.join(', ')}</p>}
    </div>
  )
}
