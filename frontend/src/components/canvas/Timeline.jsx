import { useEffect, useRef, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { useStore } from '../../store.js'
import { eventLabel, fmtNum } from '../../format.js'
import { useUi } from '../../ui.jsx'
import { IconButton, Tooltip, cn } from '../ui/index.js'

/**
 * Slim simulation timeline shared by the 2D and 3D canvases: play/pause, speed, day slider with disruption
 * start/end markers and a tiny unmet-demand histogram. Slider updates are throttled to one per frame.
 */
export default function Timeline({ extra, className }) {
  const { sim, day, setDay, events } = useStore()
  const { playing, togglePlay, speed, cycleSpeed } = useUi()
  const [scrub, setScrub] = useState(null)
  const frame = useRef(0)
  const pending = useRef(0)
  useEffect(() => () => cancelAnimationFrame(frame.current), [])

  if (!sim) return null
  const last = Math.max(0, sim.timeline.length - 1)
  const shown = scrub ?? day
  const row = sim.timeline[Math.min(shown, last)] || sim.timeline[0]
  const max = Math.max(1, ...sim.timeline.map((d) => d.unmet))
  const pct = (d) => (last ? (Math.min(d, last) / last) * 100 : 0)
  const spans = (events || [])
    .filter((e) => e.start <= last)
    .map((e, i) => ({ i, from: pct(e.start), to: pct(Math.min(last, e.start + e.duration - 1)), label: `${eventLabel(e)}: day ${e.start}-${Math.min(last, e.start + e.duration - 1)}` }))

  const onScrub = (v) => {
    setScrub(v)
    pending.current = v
    if (!frame.current) {
      frame.current = requestAnimationFrame(() => {
        frame.current = 0
        setDay(pending.current)
      })
    }
  }

  return (
    <div className={cn('flex h-12 shrink-0 items-center gap-3 border-t border-border bg-surface px-3', className)}>
      <IconButton icon={playing ? Pause : Play} label={playing ? 'Pause' : 'Play'} shortcut="Space" variant="secondary" size="sm" tooltipSide="top" onClick={togglePlay} />
      <Tooltip content="Playback speed" side="top">
        <button type="button" onClick={cycleSpeed} aria-label={`Playback speed ${speed}x`} className="num h-7 w-9 rounded-md text-xs text-fg-2 hover:bg-raised hover:text-fg">
          {speed}×
        </button>
      </Tooltip>
      <span className="num w-[78px] shrink-0 text-xs text-fg-2">
        Day {row.day}
        <span className="text-fg-muted"> / {last}</span>
      </span>
      <div className="relative h-9 min-w-[120px] flex-1">
        {/* disruption windows */}
        <div className="pointer-events-none absolute inset-x-[7px] top-0.5 h-2" aria-hidden>
          {spans.map((s) => (
            <span key={s.i} className="absolute top-0 flex h-2 items-stretch" style={{ left: `${s.from}%`, width: `${Math.max(0.6, s.to - s.from)}%` }} title={s.label}>
              <span className="w-px bg-bad" />
              <span className="flex-1 bg-bad/15" />
              <span className="w-px bg-bad" />
            </span>
          ))}
        </div>
        {/* unmet per day */}
        <div className="pointer-events-none absolute inset-x-[7px] bottom-0.5 flex h-2.5 items-end gap-px" aria-hidden>
          {sim.timeline.map((d) => (
            <span key={d.day} className={cn('flex-1 rounded-t-[1px]', d.day === row.day ? 'bg-accent' : d.unmet > 0 ? 'bg-fg-muted/45' : 'bg-transparent')} style={{ height: `${Math.max(d.unmet > 0 ? 18 : 0, (d.unmet / max) * 100)}%` }} />
          ))}
        </div>
        <input
          type="range"
          min={0}
          max={last}
          value={shown}
          onChange={(e) => onScrub(Number(e.target.value))}
          onPointerUp={() => setScrub(null)}
          onBlur={() => setScrub(null)}
          onKeyUp={() => setScrub(null)}
          className="range absolute inset-x-0 top-1/2 -translate-y-1/2"
          aria-label="Simulation day"
          aria-valuetext={`Day ${row.day} of ${last}`}
        />
      </div>
      <span className="hidden shrink-0 whitespace-nowrap text-xs text-fg-muted lg:inline">
        Unmet <span className="num text-fg">{fmtNum(row.unmet)}</span> units
      </span>
      {extra}
    </div>
  )
}
