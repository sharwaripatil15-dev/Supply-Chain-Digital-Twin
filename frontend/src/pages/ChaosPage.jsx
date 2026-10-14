import { useEffect, useMemo, useState } from 'react'
import { Play, Sparkles } from 'lucide-react'
import { api, errorMessage } from '../api.js'
import { useStore } from '../store.js'
import { fmtNum } from '../format.js'
import { targetNodes } from '../lib/disruption.js'
import { useUi } from '../ui.jsx'
import { Button, DataTable, EmptyState, IconButton, InlineError, KpiStrip, Meter, Panel, SkeletonRows, TabPanel, Tabs, useToast } from '../components/ui/index.js'
import Workspace, { InspectorPanel } from '../components/layout/Workspace.jsx'
import NetworkCanvas from '../components/canvas/NetworkCanvas.jsx'
import { NodeTag } from '../components/NodeTypeIcon.jsx'

// Chaos targets are node ids or lanes ("U->V").
const outage = (target) => ({ type: target.includes('->') ? 'edge' : 'node', target, start: 2, duration: 10, severity: 1 })
const resilienceTone = (r) => (r == null ? null : r >= 70 ? 'ok' : r >= 40 ? 'warn' : 'bad')
const resilienceWord = (r) => (r >= 70 ? 'Strong' : r >= 40 ? 'Moderate' : 'Fragile')

function Selection({ selected, onSimulate, runnable }) {
  if (!selected) {
    return (
      <InspectorPanel title="Selection">
        <div className="space-y-3 px-4 py-3 text-xs text-fg-2">
          <p>Select a row to locate it on the map.</p>
          <dl className="space-y-2 text-fg-muted">
            <div>
              <dt className="font-medium text-fg-2">Units lost</dt>
              <dd>Demand left unmet over a 10-day outage, beyond what the network already misses.</dd>
            </div>
            <div>
              <dt className="font-medium text-fg-2">Hidden pair</dt>
              <dd>Two failures that lose more together than the sum of each alone (synergy).</dd>
            </div>
          </dl>
        </div>
      </InspectorPanel>
    )
  }
  const { row, kind } = selected
  return (
    <InspectorPanel title={kind === 'pair' ? 'Hidden pair' : 'Single point of failure'} meta={`Rank ${row.rank}`}>
      <div className="space-y-4 px-4 py-3">
        <ul className="space-y-1.5">
          {selected.targets.map((tg) => (
            <li key={tg}>
              <NodeTag id={tg} />
            </li>
          ))}
        </ul>
        <dl className="grid grid-cols-2 gap-3">
          <div>
            <dt className="text-xs text-fg-muted">Units lost</dt>
            <dd className="num mt-0.5 text-base text-fg">{fmtNum(row.unmet)}</dd>
          </div>
          {kind === 'pair' && (
            <div>
              <dt className="text-xs text-fg-muted">Synergy</dt>
              <dd className="num mt-0.5 text-base text-bad">+{fmtNum(row.synergy)}</dd>
            </div>
          )}
        </dl>
        <p className="text-xs text-fg-muted">
          {kind === 'pair'
            ? 'Together these failures lose more than the sum of each one alone.'
            : 'Losing this target alone for 10 days leaves this much demand unmet.'}
        </p>
        <Button variant="primary" icon={Play} className="w-full" disabled={!runnable} onClick={() => onSimulate(selected.targets)}>
          Simulate this failure
        </Button>
      </div>
    </InspectorPanel>
  )
}

export default function ChaosPage() {
  const { chaos, loading, errors, loadChaos, runSimulation, setTab, source } = useStore()
  const ui = useUi()
  const toast = useToast()
  const runnable = !source || source.runnable
  const [view, setView] = useState('spof')
  const [selected, setSelected] = useState(null) // { kind, targets, key, row }
  const [screen, setScreen] = useState({ data: null, loading: false, error: null, version: null })
  const version = source?.version
  const screenData = screen.version === version ? screen.data : null
  const runScreen = async () => {
    setScreen({ data: null, loading: true, error: null, version })
    try {
      setScreen({ data: await api.chaosPrescreen(2000, 15), loading: false, error: null, version })
    } catch (err) {
      setScreen({ data: null, loading: false, error: errorMessage(err), version })
    }
  }
  const screenRows = useMemo(() => (screenData?.candidates ?? []).map((c, i) => ({ ...c, rank: i + 1, id: c.label })), [screenData])

  useEffect(() => {
    if (runnable && !chaos && !loading.chaos && !errors.chaos) loadChaos() // also reloads after the network changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chaos, runnable])

  const simulate = (targets) => {
    runSimulation(targets.map(outage)).then((res) => {
      if (res) toast(`Simulated ${targets.join(' + ')}`, { description: `${fmtNum(res.total_unmet)} units unmet · stock-out in ${res.survival_clock_days} days` })
    })
    setTab('simulate')
  }
  const spof = useMemo(() => (chaos?.spof ?? []).map((s, i) => ({ ...s, rank: i + 1, id: s.target })), [chaos])
  const pairs = useMemo(() => (chaos?.hidden_pairs ?? []).map((p, i) => ({ ...p, rank: i + 1, id: p.pair.join('+') })), [chaos])
  const maxSpof = Math.max(1, ...spof.map((s) => s.unmet))
  const maxPair = Math.max(1, ...pairs.map((p) => p.unmet))
  const highlight = useMemo(() => {
    if (selected) return targetNodes(selected.targets)
    return chaos ? targetNodes([...spof.map((s) => s.target), ...pairs.flatMap((p) => p.pair)]) : null
  }, [chaos, selected, spof, pairs])
  const select = (kind, row) => {
    const targets = kind === 'pair' ? row.pair : kind === 'screen' ? row.targets : [row.target]
    setSelected((cur) => (cur && cur.kind === kind && cur.row.id === row.id ? null : { kind, targets, row, key: Date.now() }))
  }
  const simulateButton = (targets) => (
    <span className="row-actions inline-flex">
      <IconButton
        icon={Play}
        label="Simulate this failure"
        size="xs"
        tooltipSide="left"
        disabled={!runnable}
        onClick={(e) => {
          e.stopPropagation()
          simulate(targets)
        }}
      />
    </span>
  )

  const r = chaos?.resilience_score
  const kpis = [
    { key: 'res', label: 'Resilience score', value: r != null ? r.toFixed(1) : null, unit: '/ 100', sub: r != null ? resilienceWord(r) : loading.chaos ? 'Stress-testing…' : '', status: resilienceTone(r) },
    { key: 'worst', label: 'Worst single failure', value: spof[0] ? fmtNum(spof[0].unmet) : null, unit: 'units', sub: spof[0] ? `${spof[0].target}, 10-day outage` : chaos ? 'No single failure loses demand' : '' },
    { key: 'spof', label: 'Single points of failure', value: chaos ? spof.length : null, sub: chaos ? 'Ranked by units lost' : '' },
    { key: 'pairs', label: 'Hidden pairs', value: chaos ? pairs.length : null, sub: chaos ? 'Worse together than apart' : '' },
  ]

  let body
  if (!runnable) {
    body = (
      <EmptyState
        title="The active network can't be stress-tested"
        description="Fix its validation errors first."
        action={<Button onClick={() => (ui.setDataView(source?.source === 'csv' ? 'csv' : 'manual'), setTab('data'))}>Open the Data page</Button>}
      />
    )
  } else if (errors.chaos) {
    body = <InlineError className="m-4" message={errors.chaos} onRetry={loadChaos} />
  } else if (loading.chaos && !chaos) {
    body = <SkeletonRows rows={6} label="Stress-testing every site and lane" />
  } else if (view === 'screen') {
    const a = screenData?.agreement
    const t = screenData?.timing
    body = (
      <div className="space-y-3 py-3">
        <div className="flex items-center gap-2 px-4">
          <Button size="sm" variant={screenData ? 'secondary' : 'primary'} icon={Sparkles} disabled={screen.loading} onClick={runScreen}>
            {screen.loading ? 'Screening 2,000 scenarios…' : screenData ? 'Re-run pre-screen' : 'Pre-screen 2,000 scenarios'}
          </Button>
        </div>
        {screen.error && <InlineError className="mx-4" message={screen.error} onRetry={runScreen} />}
        {screen.loading && <SkeletonRows rows={5} label="Surrogate screening, then exact re-runs" />}
        {!screenData && !screen.loading && !screen.error && (
          <p className="px-4 text-xs text-fg-muted">
            The ML surrogate scores thousands of random single and paired failures; the exact simulator then re-runs the worst {15} and a random control
            sample. Outcomes shown are exact (simulated).
          </p>
        )}
        {screenData?.note && !screenRows.length && <p className="px-4 text-xs text-fg-muted">{screenData.note}</p>}
        {screenRows.length > 0 && (
          <>
            <dl className="mx-4 grid grid-cols-3 gap-2 rounded-md border border-border p-2 text-xs">
              <div>
                <dt className="text-fg-muted">Speedup</dt>
                <dd className="num text-fg">{fmtNum(t.speedup, 1)}×</dd>
              </div>
              <div>
                <dt className="text-fg-muted">Rank agreement</dt>
                <dd className="num text-fg">ρ {a.spearman.toFixed(2)}</dd>
              </div>
              <div>
                <dt className="text-fg-muted">Precision@{screenData.top_k}</dt>
                <dd className="num text-fg">{Math.round(a.precision_at_k * 100)}%</dd>
              </div>
            </dl>
            <p className="px-4 text-2xs text-fg-muted">
              {fmtNum(screenData.n_scenarios)} scenarios in {t.surrogate_s.toFixed(2)} s (exact would take ~{fmtNum(t.exact_all_estimate_s)} s). Top picks lose{' '}
              {a.top_mean_exact_unmet_pct.toFixed(2)}% of demand on average vs {a.control_mean_exact_unmet_pct.toFixed(2)}% for random scenarios (exact).
            </p>
            <DataTable
              label="Surrogate pre-screen"
              rows={screenRows}
              selectedKey={selected?.kind === 'screen' ? selected.row.id : null}
              onRowClick={(row) => select('screen', row)}
              columnMenu={false}
              columns={[
                { key: 'rank', header: '#', align: 'right', mono: true, width: 'w-8', render: (row) => <span className="text-fg-muted">{row.rank}</span> },
                { key: 'label', header: 'Scenario', render: (row) => <span className="text-xs">{row.label}</span> },
                { key: 'pred', header: 'Predicted', align: 'right', value: (row) => row.predicted_unmet_pct.point, render: (row) => `${row.predicted_unmet_pct.point.toFixed(2)}%` },
                { key: 'exact', header: 'Exact', align: 'right', value: (row) => row.exact.unmet_pct, render: (row) => `${row.exact.unmet_pct.toFixed(2)}%` },
                { key: 'act', header: '', sortable: false, width: 'w-10', render: (row) => simulateButton(row.targets) },
              ]}
            />
          </>
        )}
      </div>
    )
  } else if (view === 'spof') {
    body = (
      <DataTable
        label="Single points of failure"
        rows={spof}
        selectedKey={selected?.kind === 'spof' ? selected.row.id : null}
        onRowClick={(row) => select('spof', row)}
        empty="No single failure loses demand beyond what this network already misses."
        columnMenu={false}
        columns={[
          { key: 'rank', header: '#', align: 'right', mono: true, width: 'w-10', render: (row) => <span className="text-fg-muted">{row.rank}</span> },
          { key: 'target', header: 'Target', render: (row) => <NodeTag id={row.target} nameClassName="max-w-[9rem]" /> },
          { key: 'bar', header: 'Impact', sortable: false, width: 'w-28', render: (row) => <Meter value={row.unmet} max={maxSpof} tone={selected?.row.id === row.id ? 'accent' : 'muted'} label={`${row.target} impact`} /> },
          { key: 'unmet', header: 'Units lost', align: 'right', render: (row) => fmtNum(row.unmet) },
          { key: 'act', header: '', sortable: false, width: 'w-10', render: (row) => simulateButton([row.target]) },
        ]}
      />
    )
  } else {
    body = (
      <DataTable
        label="Hidden pairs"
        rows={pairs}
        selectedKey={selected?.kind === 'pair' ? selected.row.id : null}
        onRowClick={(row) => select('pair', row)}
        empty="No hidden pairs: no two failures interact badly."
        columnMenu={false}
        columns={[
          { key: 'rank', header: '#', align: 'right', mono: true, width: 'w-10', render: (row) => <span className="text-fg-muted">{row.rank}</span> },
          {
            key: 'pair', header: 'Pair', value: (row) => row.pair.join(' '),
            render: (row) => (
              <span className="flex items-center gap-1.5">
                <NodeTag id={row.pair[0]} showName={false} />
                <span className="text-fg-muted">+</span>
                <NodeTag id={row.pair[1]} showName={false} />
              </span>
            ),
          },
          { key: 'bar', header: 'Impact', sortable: false, width: 'w-24', render: (row) => <Meter value={row.unmet} max={maxPair} tone={selected?.row.id === row.id ? 'accent' : 'muted'} label="Pair impact" /> },
          { key: 'unmet', header: 'Units lost', align: 'right', render: (row) => fmtNum(row.unmet) },
          { key: 'synergy', header: 'Synergy', align: 'right', render: (row) => <span className="text-bad">+{fmtNum(row.synergy)}</span> },
          { key: 'act', header: '', sortable: false, width: 'w-10', render: (row) => simulateButton(row.pair) },
        ]}
      />
    )
  }

  return (
    <div className="flex h-full min-h-[600px] flex-col gap-3 p-4">
      <KpiStrip items={kpis} loading={Boolean(loading.chaos && !chaos)} label="Chaos Finder results" />
      <div className="flex min-h-0 flex-1 gap-3">
        <Panel className="flex w-[400px] shrink-0 flex-col overflow-hidden xl:w-[460px]">
          <Tabs
            idBase="chaos"
            label="Ranking"
            value={view}
            onChange={setView}
            className="px-4"
            tabs={[
              { value: 'spof', label: 'Single points of failure', count: chaos ? spof.length : null },
              { value: 'pairs', label: 'Hidden pairs', count: chaos ? pairs.length : null },
              { value: 'screen', label: 'ML pre-screen', count: screenData ? screenRows.length : null },
            ]}
          />
          <TabPanel idBase="chaos" value={view} className="min-h-0 flex-1 overflow-y-auto">
            {body}
          </TabPanel>
          <p className="border-t border-border px-4 py-2 text-xs text-fg-muted">
            {view === 'screen' ? 'Unmet % of 30-day demand; predicted by the surrogate, exact from the simulator.' : 'Units lost over a 10-day outage of each target.'}
          </p>
        </Panel>
        <Workspace className="min-w-0 flex-1" inspector={<Selection selected={selected} onSimulate={simulate} runnable={runnable} />} inspectorLabel="Selection">
          <NetworkCanvas highlight={highlight} view3d={{ focus: selected ? targetNodes(selected.targets) : null, focusKey: selected?.key }} />
        </Workspace>
      </div>
    </div>
  )
}
