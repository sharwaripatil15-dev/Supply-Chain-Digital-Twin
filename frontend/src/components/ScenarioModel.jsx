import { useStore } from '../store.js'
import { fmtNum } from '../format.js'
import { Panel, PanelHeader, SectionLabel, Table, Td, Th, Tr } from './ui/index.js'

const TARGETS = [
  ['unmet_pct', 'Unmet demand', '% pts'],
  ['avg_delay', 'Avg delay', 'days'],
  ['stockout_day', 'Stock-out day', 'days'],
  ['recovery_days', 'Recovery', 'days'],
]
const f = (v, d = 2) => (v == null ? '-' : Number(v).toFixed(d))

/** Held-out metrics of the scenario surrogate (GET /surrogate -> scenario, i.e. models/metrics.json). */
export default function ScenarioModel() {
  const { surrogate } = useStore()
  const m = surrogate?.scenario
  if (!surrogate) return null
  if (!m) {
    return (
      <Panel>
        <PanelHeader title="Scenario surrogate" meta="Not trained yet" />
        <p className="px-4 py-3 text-xs text-fg-2">
          Train it with <span className="num">python -m core.synth.build</span> then <span className="num">python -m core.risk_ml --scenario</span>. Until then the
          app uses the exact simulator everywhere.
        </p>
      </Panel>
    )
  }
  const d = m.dataset
  return (
    <Panel className="xl:col-span-2">
      <PanelHeader
        title="Scenario surrogate"
        meta={`v${m.version} · ${m.mode} · ${fmtNum(d.rows)} simulated scenarios · ${d.train_networks} train / ${d.test_networks} test networks`}
      />
      <div className="space-y-4 px-4 py-3">
        <p className="text-xs text-fg-2">
          Gradient-boosted model of the exact simulator, scored on networks it never saw. It screens scenarios{' '}
          <span className="num">{fmtNum(m.timing.speedup_batch)}×</span> faster than simulating them; every number shown elsewhere in the app still comes from
          the simulator.
        </p>
        <div className="overflow-x-auto">
          <Table label="Held-out accuracy versus baselines">
            <thead>
              <tr>
                <Th>Target</Th>
                <Th numeric>MAE</Th>
                <Th numeric>MAE mean</Th>
                <Th numeric>MAE centrality</Th>
                <Th numeric>RMSE</Th>
                <Th numeric>R²</Th>
                <Th numeric>Spearman</Th>
                <Th numeric>Top-10 recall</Th>
                <Th numeric>80% coverage</Th>
              </tr>
            </thead>
            <tbody>
              {TARGETS.map(([k, label, unit]) => {
                const r = m.targets[k]
                if (!r) return null
                return (
                  <Tr key={k}>
                    <Td>
                      {label} <span className="text-fg-muted">({unit})</span>
                    </Td>
                    <Td numeric>{f(r.model.mae)}</Td>
                    <Td numeric className="text-fg-muted">{f(r.baseline_mean.mae)}</Td>
                    <Td numeric className="text-fg-muted">{f(r.baseline_centrality.mae)}</Td>
                    <Td numeric>{f(r.model.rmse)}</Td>
                    <Td numeric>{f(r.model.r2)}</Td>
                    <Td numeric>{f(r.model.spearman)}</Td>
                    <Td numeric>{f(r.model.top10_recall)}</Td>
                    <Td numeric>{`${Math.round(r.model.interval_coverage * 100)}%`}</Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <SectionLabel className="mb-1.5">Timing</SectionLabel>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <dt className="text-fg-muted">Surrogate, per scenario</dt>
              <dd className="num text-fg">{f(m.timing.inference_ms_per_scenario_batch + m.timing.features_ms_per_scenario, 3)} ms</dd>
              <dt className="text-fg-muted">Exact simulator, per scenario</dt>
              <dd className="num text-fg">{f(m.timing.exact_sim_ms_per_scenario, 1)} ms</dd>
              <dt className="text-fg-muted">Single prediction (8 models)</dt>
              <dd className="num text-fg">{f(m.timing.inference_ms_single, 1)} ms</dd>
            </dl>
          </div>
          <div>
            <SectionLabel className="mb-1.5">Strongest drivers (unmet demand)</SectionLabel>
            <ul className="space-y-0.5 text-xs">
              {(m.targets.unmet_pct?.top_features ?? []).slice(0, 5).map((t) => (
                <li key={t.feature} className="flex justify-between gap-2">
                  <span className="truncate text-fg-2">{t.feature.replaceAll('_', ' ')}</span>
                  <span className="num text-fg-muted">{Math.round(t.importance * 100)}%</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <p className="text-2xs text-fg-muted">{m.note} Intervals: {m.interval?.method}.</p>
      </div>
    </Panel>
  )
}
