/**
 * Presentation state only (no API calls, no business logic): rail pin, inspector visibility, flow animation,
 * timeline playback and replay, command palette, fit requests, Executive/Analyst view, demo tour. Preferences persist per browser.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from './store.js'

const UiContext = createContext(null)
const STORAGE_KEY = 'aegis-ui'
const PERSISTED = ['railPinned', 'inspectorOpen', 'animateFlows', 'view']
export const SPEEDS = [1, 2, 4]
const DAY_MS = 700

function readPrefs() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {}
    return Object.fromEntries(Object.entries(raw).filter(([k]) => PERSISTED.includes(k)))
  } catch {
    return {}
  }
}

export function UiProvider({ children }) {
  const { sim, day, setDay } = useStore()
  const [prefs, setPrefs] = useState(() => ({ railPinned: false, inspectorOpen: true, animateFlows: false, view: 'executive', ...readPrefs() }))
  const [overlayOpen, setOverlayOpen] = useState(false) // inspector as an overlay drawer below 1280px
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [story, setStory] = useState(false)
  const [fitSignal, setFitSignal] = useState(0)
  const [dataView, setDataView] = useState(null)
  const [tourStep, setTourStep] = useState(null) // coach-mark index while the demo tour runs
  const [demo, setDemo] = useState(null) // { step, steps, error } while demo mode loads its story

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
    } catch {
      /* storage unavailable: preferences last for this session only */
    }
  }, [prefs])

  // Timeline playback: one day per tick, stops on the last day.
  const last = sim ? sim.timeline.length - 1 : 0
  useEffect(() => {
    if (!playing) return undefined
    if (!sim || day >= last) {
      setPlaying(false)
      return undefined
    }
    const id = setTimeout(() => setDay(day + 1), DAY_MS / speed)
    return () => clearTimeout(id)
  }, [playing, day, last, sim, speed, setDay])

  // A replay ends a moment after the last day; a new simulation cancels playback and replay.
  useEffect(() => {
    if (!story || playing || day < last) return undefined
    const id = setTimeout(() => setStory(false), 2500)
    return () => clearTimeout(id)
  }, [story, playing, day, last])
  useEffect(() => {
    setPlaying(false)
    setStory(false)
  }, [sim])

  const setPref = useCallback((key, v) => setPrefs((p) => ({ ...p, [key]: typeof v === 'function' ? v(p[key]) : v })), [])
  const dayRef = useRef(day)
  dayRef.current = day

  const value = useMemo(
    () => ({
      ...prefs,
      setPref,
      overlayOpen,
      setOverlayOpen,
      paletteOpen,
      setPaletteOpen,
      shortcutsOpen,
      setShortcutsOpen,
      playing,
      speed,
      cycleSpeed: () => setSpeed((s) => SPEEDS[(SPEEDS.indexOf(s) + 1) % SPEEDS.length]),
      play: () => {
        if (!sim) return
        if (dayRef.current >= last) setDay(0)
        setPlaying(true)
      },
      pause: () => setPlaying(false),
      togglePlay: () => {
        if (!sim) return
        if (playing) return setPlaying(false)
        if (dayRef.current >= last) setDay(0)
        setPlaying(true)
      },
      story,
      startStory: () => {
        if (!sim) return
        setDay(0)
        setStory(true)
        setPlaying(true)
      },
      stopStory: () => {
        setStory(false)
        setPlaying(false)
      },
      fitSignal,
      requestFit: () => setFitSignal((n) => n + 1),
      dataView,
      setDataView,
      analyst: prefs.view === 'analyst',
      tourStep,
      setTourStep,
      demo,
      setDemo,
    }),
    [prefs, setPref, overlayOpen, paletteOpen, shortcutsOpen, playing, speed, story, fitSignal, dataView, sim, last, setDay, tourStep, demo],
  )
  return <UiContext.Provider value={value}>{children}</UiContext.Provider>
}

export function useUi() {
  const ctx = useContext(UiContext)
  if (!ctx) throw new Error('useUi must be used inside <UiProvider>')
  return ctx
}

export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = (e) => setMatches(e.matches)
    setMatches(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [query])
  return matches
}

export const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
export const MOD_LABEL = isMac ? '⌘' : 'Ctrl'

const isEditable = (el) => Boolean(el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)))

/** "mod+k", "shift+?" ... from a keyboard event. Shift is only part of the combo for letters and named keys. */
function comboOf(e) {
  const key = e.key === ' ' ? 'space' : e.key.toLowerCase()
  const parts = []
  if (e.metaKey || e.ctrlKey) parts.push('mod')
  if (e.altKey) parts.push('alt')
  if (e.shiftKey && (/^[a-z]$/.test(key) || key.length > 1)) parts.push('shift')
  parts.push(key)
  return parts.join('+')
}

/**
 * Global keyboard shortcuts. bindings: { combo: handler | { handler, allowInInputs } }.
 * Shortcuts never fire while typing in a field unless allowInInputs is set (e.g. mod+k, escape).
 */
export function useHotkeys(bindings) {
  const ref = useRef(bindings)
  ref.current = bindings
  useEffect(() => {
    const onKey = (e) => {
      const entry = ref.current[comboOf(e)]
      if (!entry) return
      const { handler, allowInInputs } = typeof entry === 'function' ? { handler: entry } : entry
      if (!allowInInputs && isEditable(e.target)) return
      if (e.defaultPrevented) return
      if (handler(e) !== false) e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
