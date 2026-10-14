import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../api.js'
import { useStore } from '../store.js'
import { useUi } from '../ui.jsx'
import { Button, Meter } from './ui/index.js'

const STORY = [
  'Loading the FMCG demo network',
  'Finding bottlenecks and pain points',
  'Asking: what if the biggest supplier fails?',
  'Finding the best site to expand',
]
export const TOUR = [
  { target: 'health', title: 'One number for health', body: 'The Health Score summarises resilience, capacity, stock, supplier concentration and lead-time risk. Click it to see how it is built.' },
  { target: 'attention', title: 'What needs attention', body: 'The three most severe problems, each with the revenue at risk and a "Fix this" that opens a what-if.' },
  { target: 'actions', title: 'Recommended actions', body: 'Fixes, recovery plans and expansion, ranked by benefit. Mark the ones you plan to do.' },
  { target: 'expansion', title: 'Where to grow', body: 'The best new site and its payback, from the expansion planner. Download the executive brief from the header.' },
]
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

/** Coach mark: a ring around the target element and a short explanation next to it. */
function CoachMark({ step, onNext, onBack, onClose }) {
  const t = TOUR[step]
  const [rect, setRect] = useState(null)
  const nextRef = useRef(null)
  useLayoutEffect(() => {
    const el = document.querySelector(`[data-tour="${t.target}"]`)
    if (!el) return undefined
    el.scrollIntoView({ block: 'center', behavior: 'instant' })
    const measure = () => setRect(el.getBoundingClientRect())
    measure()
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [t.target])
  useEffect(() => nextRef.current?.focus(), [step])
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  if (!rect) return null
  const below = rect.bottom + 180 < window.innerHeight
  const left = Math.min(Math.max(12, rect.left), window.innerWidth - 340)
  return (
    <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="false" aria-label={`Tour step ${step + 1} of ${TOUR.length}: ${t.title}`}>
      <div className="pointer-events-none absolute rounded-lg ring-2 ring-accent ring-offset-2 ring-offset-bg transition-all duration-150"
        style={{ top: rect.top - 4, left: rect.left - 4, width: rect.width + 8, height: rect.height + 8 }} />
      <div className="absolute w-[320px] rounded-lg border border-border bg-surface p-4 shadow-float"
        style={below ? { top: rect.bottom + 12, left } : { top: Math.max(12, rect.top - 172), left }}>
        <p className="text-2xs text-fg-muted">Step {step + 1} of {TOUR.length}</p>
        <h2 className="mt-0.5 text-sm font-medium text-fg">{t.title}</h2>
        <p className="mt-1 text-sm text-fg-2">{t.body}</p>
        <div className="mt-3 flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={onClose}>Skip tour</Button>
          <span className="flex-1" />
          {step > 0 && <Button size="sm" onClick={onBack}>Back</Button>}
          <Button ref={nextRef} size="sm" variant="primary" onClick={onNext}>{step === TOUR.length - 1 ? 'Done' : 'Next'}</Button>
        </div>
      </div>
    </div>
  )
}

/** Demo mode: loads a preset story (industry network + analysis + scenario + expansion), then the coach-mark tour. */
export default function DemoMode() {
  const ui = useUi()
  const store = useStore()
  const cancelled = useRef(false)
  const { demo, setDemo, tourStep, setTourStep } = ui

  const run = useCallback(async () => {
    cancelled.current = false
    const step = async (i, fn) => {
      if (cancelled.current) throw new Error('cancelled')
      setDemo({ phase: 'running', step: i })
      return fn()
    }
    try {
      await step(0, async () => {
        const net = await api.networkDemo('fmcg')
        const res = await store.importManual(net, true)
        if (!res.ok) throw new Error(res.error)
      })
      await step(1, async () => {
        let a = await store.runAnalysis()
        for (let i = 0; i < 180 && a && a.status === 'running' && !cancelled.current; i++) {
          await wait(1000)
          a = await store.loadAnalysis()
        }
      })
      await step(2, async () => {
        const net = await api.network()
        const sup = net.nodes.filter((n) => n.kind === 'supplier' && !n.backup).sort((a, b) => (b.capacity || 0) - (a.capacity || 0))[0]
        if (sup) await store.runWhatIf({ text: `What if ${sup.id} fails for 10 days?`, mc_runs: 50, robustness_runs: 4 })
      })
      await step(3, () => store.runExpansion({ n_add: 1 }))
      if (cancelled.current) throw new Error('cancelled')
      setDemo(null)
      store.setTab('overview')
      await wait(400)
      setTourStep(0)
    } catch (err) {
      setDemo(err.message === 'cancelled' ? null : { phase: 'error', error: errorMessage(err) })
    }
  }, [store, setDemo, setTourStep])

  useEffect(() => {
    if (demo?.phase === 'start') run()
  }, [demo, run])

  return (
    <>
      {demo && demo.phase !== 'start' && (
        <div className="fixed bottom-4 left-1/2 z-[60] w-[360px] -translate-x-1/2 rounded-lg border border-border bg-surface p-4 shadow-float" role="status" aria-live="polite">
          <p className="text-sm font-medium text-fg">Demo mode</p>
          {demo.phase === 'error' ? (
            <p className="mt-1 text-sm text-bad">{demo.error}</p>
          ) : (
            <>
              <p className="mt-1 text-sm text-fg-2">{STORY[demo.step]}…</p>
              <Meter className="mt-2" value={(demo.step ?? 0) + 1} max={STORY.length + 1} tone="accent" label="Demo progress" />
            </>
          )}
          <div className="mt-3 flex justify-end">
            <Button size="sm" onClick={() => ((cancelled.current = true), setDemo(null))}>{demo.phase === 'error' ? 'Close' : 'Skip demo'}</Button>
          </div>
        </div>
      )}
      {tourStep != null && store.tab === 'overview' && (
        <CoachMark
          step={tourStep}
          onNext={() => setTourStep(tourStep + 1 < TOUR.length ? tourStep + 1 : null)}
          onBack={() => setTourStep(Math.max(0, tourStep - 1))}
          onClose={() => setTourStep(null)}
        />
      )}
    </>
  )
}
