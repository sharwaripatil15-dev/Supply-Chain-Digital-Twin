import { Fragment, useEffect, useMemo, useState } from 'react'
import { ArrowRight, CalendarClock, Check, CloudLightning, Hourglass, PackageCheck, RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react'
import { useStore } from '../../store.js'
import { fmtNum, fmtSigned } from '../../format.js'
import { useWeather, useWeatherView } from '../../weather.jsx'
import { LEVEL_LABEL, LEVEL_TONE, pathEdges, summaryLine } from '../../lib/weather.js'
import { Button, DataTable, EmptyState, InlineError, SectionLabel, SkeletonRows, StatusDot, Tooltip, cn, useToast } from '../ui/index.js'
import NetworkCanvas from '../canvas/NetworkCanvas.jsx'
import { ATTRIBUTION, QualityChip } from './WeatherParts.jsx'

const ACTION_LABEL = {
  reroute: 'Reroute', mode_switch: 'Switch mode', wait: 'Wait it out', preposition: 'Pre-position stock',
  dispatch_early: 'Dispatch early', none: 'No safe option',
}

function PathChips({ path, modes, byId, className }) {
  return (
    <span className={cn('flex flex-wrap items-center gap-1', className)}>
      {path.map((id, i) => (
        <Fragment key={`${id}-${i}`}>
          {i > 0 && (
            <span className="flex items-center gap-0.5 text-2xs text-fg-muted">
              {modes?.[i - 1] && modes[i - 1] !== 'road' && <span className="text-accent">{modes[i - 1]}</span>}
              <ArrowRight className="h-3 w-3" aria-hidden />
            </span>
          )}
          <Tooltip content={byId[id] ? `${byId[id].name || id} · ${byId[id].city}` : id} side="top">
            <span className="num inline-flex h-5 items-center rounded-sm bg-raised px-1.5 text-2xs text-fg">{id}</span>
          </Tooltip>
        </Fragment>
      ))}
    </span>
  )
}

function Metric({ label, value, delta, tone }) {
  return (
    <div>
      <dt className="text-2xs text-fg-muted">{label}</dt>
      <dd className={cn('num text-sm text-fg', tone === 'bad' && 'text-bad', tone === 'warn' && 'text-warn')}>
        {value}
        {delta && <span className="ml-1 text-2xs text-fg-muted">{delta}</span>}
      </dd>
    </div>
  )
}

function Safety({ check }) {
  return check.passed ? (
    <span className="inline-flex items-center gap-1 text-xs text-ok">
      <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
      Passes the safety check
    </span>
  ) : (
    <span className="flex items-start gap-1 text-xs text-bad">
      <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>{check.warning}</span>
    </span>
  )
}

function Compare({ option, alt, byId }) {
  const o = option.original
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <section className="rounded-md border border-border p-3">
        <SectionLabel className="mb-2">Original route</SectionLabel>
        <PathChips path={o.path} byId={byId} />
        <dl className="mt-3 grid grid-cols-4 gap-2">
          <Metric label="ETA" value={`${fmtNum(o.eta_weather, 1)} d`} delta={`normally ${fmtNum(o.eta_days, 1)}`} tone={o.eta_weather > o.eta_days ? 'warn' : null} />
          <Metric label="Cost" value={`₹${fmtNum(o.cost)}`} delta="/unit" />
          <Metric label="CO₂" value={`${fmtNum(o.co2, 2)} kg`} />
          <Metric label="Risk" value={o.residual_risk.toFixed(2)} tone={o.residual_risk >= 0.7 ? 'bad' : o.residual_risk >= 0.5 ? 'warn' : null} />
        </dl>
        <p className="mt-2 text-xs text-fg-muted">
          {option.closed ? 'Closed' : LEVEL_LABEL[option.level]} on days {option.window[0]}–{option.window[1]}. {option.reason}
        </p>
      </section>
      <section className={cn('rounded-md border p-3', alt ? 'border-accent/50' : 'border-border')}>
        <SectionLabel className="mb-2">{alt ? (alt.recommended ? 'Recommended alternative' : 'Selected alternative') : 'Alternative'}</SectionLabel>
        {alt ? (
          <>
            <PathChips path={alt.path} modes={alt.modes} byId={byId} />
            <dl className="mt-3 grid grid-cols-4 gap-2">
              <Metric label="ETA" value={`${fmtNum(alt.eta_days, 1)} d`} delta={fmtSigned(alt.eta_delta, 1)} />
              <Metric label="Cost" value={`₹${fmtNum(alt.cost)}`} delta={fmtSigned(alt.cost_delta, 0, '₹')} />
              <Metric label="CO₂" value={`${fmtNum(alt.co2, 2)} kg`} delta={fmtSigned(alt.co2_delta, 2)} />
              <Metric label="Risk" value={alt.residual_risk.toFixed(2)} tone={alt.residual_risk >= 0.7 ? 'bad' : alt.residual_risk >= 0.5 ? 'warn' : null} />
            </dl>
            <div className="mt-2">
              <Safety check={alt.safety_check} />
            </div>
          </>
        ) : (
          <p className="text-xs text-fg-muted">No open path avoids this lane in the window. Use the wait, pre-positioning or dispatch options.</p>
        )}
      </section>
    </div>
  )
}

/** Recover > Weather re-routing: blocked routes, ranked alternatives, wait / pre-position, dispatch window, apply. */
export default function ReroutePanel() {
  const w = useWeather()
  const { network, source } = useStore()
  const toast = useToast()
  const runnable = !source || source.runnable
  const { ensure, loadReroute } = w
  useEffect(() => ensure(), [ensure])
  useEffect(() => {
    if (w.risk && !w.reroute && !w.loading.reroute && !w.errors.reroute && runnable) loadReroute()
  }, [w.risk, w.reroute, w.loading.reroute, w.errors.reroute, runnable, loadReroute])
  const [picked, setPicked] = useState(null)
  const options = w.reroute?.options ?? []
  const option = options.find((o) => o.blocked_edge === picked) || options[0]
  const byId = useMemo(() => Object.fromEntries((network?.nodes ?? []).map((n) => [n.id, n])), [network])
  const altIndex = w.pick && option && w.pick.edge === option.blocked_edge ? w.pick.index : null
  const alts = option?.alternatives ?? []
  const shown = altIndex != null ? alts[altIndex] : alts.find((a) => a.recommended) || null
  const view = useWeatherView(option ? option.window[0] : 0, { force: true })
  const paths = useMemo(() => (option ? { alt: shown ? pathEdges(shown.path) : [], orig: pathEdges(option.original.path) } : null), [option, shown])

  if (!runnable) return <EmptyState title="The active network can't be planned for" description="Fix its validation errors first." />
  if (w.errors.risk && !w.risk) return <InlineError className="m-4" message={w.errors.risk} onRetry={w.load} />
  if (w.errors.reroute) return <InlineError className="m-4" message={w.errors.reroute} onRetry={loadReroute} />
  if (!w.reroute) return <SkeletonRows rows={6} label="Planning weather-aware routes" />

  const apply = async () => {
    const res = await w.applyRecommendation(option)
    if (res) toast('Recommendation applied', { description: `${option.scenario_patch?.summary || ACTION_LABEL[option.recommended_action]}. KPIs updated.` })
  }
  const plan = w.reroute.applied_strategy_summary
  const appliedNote = option && w.applied[option.blocked_edge]

  return (
    <div className="space-y-3 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <CloudLightning className="h-4 w-4 text-fg-muted" aria-hidden />
        <p className="min-w-0 flex-1 text-sm text-fg-2">{summaryLine(w.risk, w.reroute)}</p>
        <QualityChip risk={w.risk} />
        <Button size="sm" variant="ghost" icon={RefreshCw} disabled={w.loading.reroute} onClick={loadReroute}>
          {w.loading.reroute ? 'Planning…' : 'Recompute'}
        </Button>
      </div>
      {plan && (
        <p className="rounded-md border border-border bg-raised/50 px-3 py-2 text-xs text-fg-2">
          <span className="font-medium text-fg">{plan.name}</span> (weather-priced lanes + inventory buffer): unmet{' '}
          <span className="num text-fg">{fmtNum(plan.unmet)}</span> units vs <span className="num">{fmtNum(plan.do_nothing.unmet)}</span> doing nothing; avg delay{' '}
          <span className="num">{fmtNum(plan.delay_avg_days, 2)}</span> d vs <span className="num">{fmtNum(plan.do_nothing.delay_avg_days, 2)}</span>;{' '}
          {plan.safety_check.passed ? 'passes the safety check.' : <span className="text-bad">{plan.safety_check.warning}</span>}
        </p>
      )}
      {options.length === 0 ? (
        <EmptyState title="No blocked routes" description={`No lane that carries flow reaches high risk in the next ${w.risk?.horizon ?? 7} days.`} />
      ) : (
        <div className="grid gap-3 xl:grid-cols-[240px_minmax(0,1fr)]">
          <ul className="space-y-0.5" aria-label="Blocked routes">
            {options.map((o) => {
              const active = o === option
              const lvl = o.closed ? 'closed' : o.level
              return (
                <li key={o.blocked_edge}>
                  <button
                    type="button"
                    aria-pressed={active}
                    onClick={() => setPicked(o.blocked_edge)}
                    className={cn('w-full rounded-md px-2.5 py-2 text-left transition-colors duration-150', active ? 'bg-raised ring-1 ring-border-strong' : 'hover:bg-raised')}
                  >
                    <div className="flex items-center gap-2 text-sm">
                      <span className="num min-w-0 flex-1 truncate text-fg">{o.blocked_edge.replace('->', ' → ')}</span>
                      <StatusDot status={LEVEL_TONE[lvl]} label={LEVEL_LABEL[lvl]} />
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-2xs text-fg-muted">
                      <span className="num">days {o.window[0]}–{o.window[1]}</span>
                      <span className="min-w-0 flex-1 truncate">{ACTION_LABEL[o.recommended_action]}</span>
                      {w.applied[o.blocked_edge] && <Check className="h-3 w-3 text-ok" aria-label="Applied" />}
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
          {option && (
            <div className="min-w-0 space-y-3">
              <Compare option={option} alt={shown} byId={byId} />
              <div className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2">
                <p className="min-w-0 flex-1 text-xs text-fg-2">
                  <span className="font-medium text-fg">{ACTION_LABEL[option.recommended_action]}.</span> {option.action_text}
                  {option.delay_saved_days > 0 && <span className="text-fg-muted"> Saves ~{fmtNum(option.delay_saved_days, 1)} days.</span>}
                </p>
                {appliedNote ? (
                  <span className="inline-flex items-center gap-1 text-xs text-ok">
                    <Check className="h-3.5 w-3.5" aria-hidden />
                    Applied
                  </span>
                ) : (
                  <Button variant="primary" size="sm" disabled={option.recommended_action === 'none' || w.loading.apply} onClick={apply}>
                    Apply recommendation
                  </Button>
                )}
              </div>
              {alts.length > 0 && (
                <DataTable
                  label="Alternatives"
                  rows={alts.map((a, i) => ({ ...a, id: i }))}
                  selectedKey={altIndex ?? alts.findIndex((a) => a.recommended)}
                  onRowClick={(r) => w.pickAlternative(option.blocked_edge, r.id)}
                  columnMenu={false}
                  columns={[
                    { key: 'kind', header: 'Option', render: (a) => <span className="whitespace-nowrap">{a.kind === 'mode_switch' ? `Switch to ${a.mode}` : 'Reroute'}{a.recommended && <span className="ml-1.5 text-2xs text-accent">recommended</span>}</span> },
                    { key: 'path', header: 'Path', sortable: false, render: (a) => <PathChips path={a.path} modes={a.modes} byId={byId} /> },
                    { key: 'eta_delta', header: 'ETA Δ', align: 'right', render: (a) => `${fmtSigned(a.eta_delta, 1)} d` },
                    { key: 'cost_delta', header: 'Cost Δ', align: 'right', render: (a) => fmtSigned(a.cost_delta, 0, '₹') },
                    { key: 'co2', header: 'CO₂ kg', align: 'right', render: (a) => fmtNum(a.co2, 2) },
                    { key: 'residual_risk', header: 'Risk', align: 'right', render: (a) => a.residual_risk.toFixed(2) },
                    { key: 'capacity_available', header: 'Spare', align: 'right', render: (a) => fmtNum(a.capacity_available) },
                    {
                      key: 'safe', header: 'Safety', value: (a) => (a.safety_check.passed ? 1 : 0),
                      render: (a) => (a.safety_check.passed ? <StatusDot status="ok" label="Pass" /> : <Tooltip content={a.safety_check.warning} wide><span><StatusDot status="bad" label="Warning" /></span></Tooltip>),
                    },
                  ]}
                />
              )}
              <div className="grid gap-3 md:grid-cols-3">
                {[
                  [Hourglass, 'Wait it out', option.wait_option.explanation, option.wait_option.recommended ? 'recommended' : option.wait_option.viable ? 'viable' : null],
                  [PackageCheck, 'Pre-position', option.preposition_option.explanation, option.preposition_option.also_recommended ? 'recommended' : option.preposition_option.viable ? `₹${fmtNum(option.preposition_option.cost)}` : null],
                  [CalendarClock, 'Dispatch window', option.dispatch_window.text, null],
                ].map(([Icon, title, text, tag]) => (
                  <section key={title} className="rounded-md border border-border p-3">
                    <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-fg">
                      <Icon className="h-3.5 w-3.5 text-fg-muted" aria-hidden />
                      {title}
                      {tag && <span className="ml-auto text-2xs font-normal text-accent">{tag}</span>}
                    </div>
                    <p className="text-xs text-fg-2">{text}</p>
                  </section>
                ))}
              </div>
              <div className="relative h-[380px] overflow-hidden rounded-md border border-border">
                <NetworkCanvas weather={view} paths={paths} highlight={shown?.path ?? null} />
              </div>
            </div>
          )}
        </div>
      )}
      {(w.reroute.node_actions ?? []).length > 0 && (
        <section>
          <SectionLabel className="mb-1.5">Site actions</SectionLabel>
          <ul className="space-y-1 text-xs text-fg-2">
            {w.reroute.node_actions.map((a) => (
              <li key={`${a.node}-${a.action}`}>
                <span className="num font-medium text-fg">{a.node}</span> · {a.action.replace('_', ' ')}: {a.explanation}
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="text-2xs text-fg-muted">{ATTRIBUTION}</p>
    </div>
  )
}
