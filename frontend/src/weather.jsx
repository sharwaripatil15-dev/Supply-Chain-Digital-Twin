/**
 * Weather & hazards state: forecast risk, hazard overlays, re-routing options and the hazard layer toggle.
 * Nothing loads until a weather view asks for it (`ensure`), and nothing here blocks the rest of the app.
 * Scenario changes go through the store's own actions (setEvents / runSimulation / runRecover): weather events are
 * ordinary events tagged source "weather", and clearing them restores the scenario as it was before they were added.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api, errorMessage } from './api.js'
import { useStore } from './store.js'
import { applyPatch, cleanEvent, cycloneTracks, featuresForDay, rowsForDay, userEvents, weatherEvents } from './lib/weather.js'

const WeatherContext = createContext(null)
export const HORIZONS = [3, 7, 14]

export function WeatherProvider({ children }) {
  const store = useStore()
  const storeRef = useRef(store)
  storeRef.current = store
  const [state, setState] = useState({
    requested: false,
    horizon: 7,
    risk: null,
    hazards: null,
    scenarios: null,
    active: null,
    reroute: null,
    chaos: null,
    layerOn: false,
    day: 0,
    pick: null, // { edge, index } of the alternative highlighted on the map
    applied: {}, // blocked edge -> summary of the recommendation applied to the scenario
    preWeather: null, // the scenario's events before weather events were first added
    wantReroute: 0, // bumped to open Recover > Weather re-routing
    loading: {},
    errors: {},
  })
  const ref = useRef(state)
  ref.current = state
  const patch = useCallback((p) => setState((s) => ({ ...s, ...(typeof p === 'function' ? p(s) : p) })), [])

  const run = useCallback(
    async (key, fn, onOk) => {
      patch((s) => ({ loading: { ...s.loading, [key]: true }, errors: { ...s.errors, [key]: null } }))
      try {
        const res = await fn()
        patch((s) => ({ ...onOk(res, s), loading: { ...s.loading, [key]: false } }))
        return res
      } catch (err) {
        patch((s) => ({ loading: { ...s.loading, [key]: false }, errors: { ...s.errors, [key]: errorMessage(err) } }))
        return null
      }
    },
    [patch],
  )

  const load = useCallback(
    async ({ refresh = false } = {}) => {
      const h = ref.current.horizon
      if (!ref.current.scenarios) run('scenarios', api.weatherScenarios, (r) => ({ scenarios: r.scenarios, active: r.active }))
      await Promise.all([
        run('risk', () => api.weatherRisk(h, refresh), (risk) => ({ risk, reroute: null, chaos: null, pick: null })),
        run('hazards', () => api.weatherHazards(h), (hazards) => ({ hazards })),
      ])
    },
    [run],
  )

  const ensure = useCallback(() => {
    if (ref.current.requested) return
    patch({ requested: true })
    load()
  }, [load, patch])

  // A different network (or edit) changes every lane: reload what was requested.
  const version = `${store.source?.source}:${store.source?.version}`
  const seenVersion = useRef(version)
  useEffect(() => {
    if (seenVersion.current === version) return
    seenVersion.current = version
    if (ref.current.requested) load()
  }, [version, load])

  const actions = useMemo(() => {
    const userOf = () => {
      const { events } = storeRef.current
      return ref.current.preWeather && weatherEvents(events).length ? ref.current.preWeather : userEvents(events)
    }

    /** Forecast -> events, merged into the scenario (user events kept), then simulated. */
    const applyToScenario = async ({ simulate = true } = {}) => {
      const res = await run('apply', () => api.weatherApply({ horizon: ref.current.horizon, min_level: 'high', include_nodes: true }), () => ({}))
      if (!res) return null
      const { events } = storeRef.current
      const pre = weatherEvents(events).length ? ref.current.preWeather : events
      const merged = [...userOf(), ...res.events.map(cleanEvent)]
      patch({ preWeather: pre, applied: {} })
      if (simulate && merged.length) await storeRef.current.runSimulation(merged)
      else storeRef.current.setEvents(merged)
      return res
    }

    /** Remove weather events and restore the scenario as it was before them. */
    const clearFromScenario = async () => {
      await run('clear', api.weatherClear, () => ({}))
      const restored = ref.current.preWeather ?? userEvents(storeRef.current.events)
      patch({ preWeather: null, applied: {} })
      if (storeRef.current.sim && restored.length) await storeRef.current.runSimulation(restored)
      else storeRef.current.setEvents(restored)
    }

    const loadReroute = () =>
      run('reroute', () => api.weatherReroute({ horizon: ref.current.horizon }), (reroute) => ({ reroute, pick: null }))

    /** Apply one blocked route's recommendation to the scenario; refresh the simulation and the recovery plan. */
    const applyRecommendation = async (option) => {
      let events = storeRef.current.events
      if (!weatherEvents(events).length) {
        const res = await run('apply', () => api.weatherApply({ horizon: ref.current.horizon }), () => ({}))
        if (!res) return null
        patch({ preWeather: events })
        events = [...userEvents(events), ...res.events.map(cleanEvent)]
      }
      const next = applyPatch(events, option.scenario_patch)
      patch((s) => ({ applied: { ...s.applied, [option.blocked_edge]: option.scenario_patch?.summary || option.recommended_action } }))
      const sim = await storeRef.current.runSimulation(next)
      storeRef.current.runRecover(next)
      return sim
    }

    return {
      ensure,
      load,
      refresh: () => load({ refresh: true }),
      setHorizon: (horizon) => {
        patch({ horizon, day: 0 })
        ref.current = { ...ref.current, horizon }
        load()
      },
      setScenario: async (id) => {
        const res = await run('scenario', () => api.setWeatherScenario(id), (r) => ({ active: r.active, scenarios: r.scenarios, day: 0 }))
        if (res) await load()
        return res
      },
      setLayer: (on) => {
        patch({ layerOn: on })
        if (on) ensure()
      },
      setDay: (day) => patch({ day }),
      openReroute: () => patch((s) => ({ wantReroute: s.wantReroute + 1 })),
      pickAlternative: (edge, index) => patch((s) => ({ pick: s.pick && s.pick.edge === edge && s.pick.index === index ? null : { edge, index } })),
      applyToScenario,
      clearFromScenario,
      loadReroute,
      applyRecommendation,
      loadChaos: () => run('chaos', () => api.weatherChaos(ref.current.horizon), (chaos) => ({ chaos })),
    }
  }, [ensure, load, patch, run])

  const value = useMemo(() => ({ ...state, ...actions }), [state, actions])
  return <WeatherContext.Provider value={value}>{children}</WeatherContext.Provider>
}

/**
 * What the map draws for `day`: lane / site rows, hazard features and cyclone tracks; null while the hazard layer
 * is off (or `force` is false) or nothing has loaded.
 */
export function useWeatherView(day, { force = false } = {}) {
  const { layerOn, risk, hazards } = useWeather()
  return useMemo(() => {
    if (!(layerOn || force) || !risk) return null
    const { edges, nodes } = rowsForDay(risk, day)
    return { day, edges, nodes, features: featuresForDay(hazards, day), tracks: cycloneTracks(hazards), dates: risk.dates }
  }, [layerOn, force, risk, hazards, day])
}

export function useWeather() {
  const ctx = useContext(WeatherContext)
  if (!ctx) throw new Error('useWeather must be used inside <WeatherProvider>')
  return ctx
}
