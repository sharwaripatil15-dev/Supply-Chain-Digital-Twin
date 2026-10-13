import { useEffect } from 'react'
import { useStore } from '../store.js'
import { fmtNum } from '../format.js'
import { InlineError, Meter, Panel, PanelHeader, SectionLabel, SkeletonBlock } from './ui/index.js'

function Metric({ label, value }) {
  return (
    <div className="min-w-0 px-3 py-2">
      <dt className="text-xs text-fg-muted">{label}</dt>
      <dd className="num mt-0.5 text-base text-fg">{value}</dd>
    </div>
  )
}

export default function SurrogateAccuracy() {
  const { surrogate, loading, errors, loadSurrogate } = useStore()
  useEffect(() => {
    if (!surrogate && !loading.surrogate) loadSurrogate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const max = Math.max(...(surrogate?.top_features.map((f) => f.importance) || [1]))
  return (
    <Panel>
      <PanelHeader title="Risk model accuracy" meta="Held-out networks, never seen in training" />
      <div className="space-y-4 px-4 py-3">
        <InlineError message={errors.surrogate} onRetry={loadSurrogate} />
        {loading.surrogate && !surrogate && <SkeletonBlock lines={5} label="Loading model metrics" />}
        {surrogate && (
          <>
            <p className="text-xs text-fg-2">
              Predicts {surrogate.target}, <span className="num">{fmtNum(surrogate.speedup)}×</span> faster than running the engine.
            </p>
            <dl className="grid grid-cols-4 divide-x divide-border rounded-md border border-border">
              <Metric label="R²" value={surrogate.r2.toFixed(2)} />
              {/* the live model predicts a share of demand (0..1); older mocks reported units */}
              <Metric label="MAE" value={surrogate.mae < 1 ? `${(surrogate.mae * 100).toFixed(1)}%` : `${fmtNum(surrogate.mae)} u`} />
              <Metric label="Train rows" value={fmtNum(surrogate.n_train)} />
              <Metric label="Test rows" value={fmtNum(surrogate.n_test)} />
            </dl>
            <div>
              <SectionLabel className="mb-2">Top features (gain)</SectionLabel>
              <ul className="space-y-2">
                {surrogate.top_features.map((f, i) => (
                  <li key={f.feature} className="grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)_2.5rem] items-center gap-3 text-xs">
                    <span className="truncate text-fg-2" title={f.feature}>
                      {f.feature.replaceAll('_', ' ')}
                    </span>
                    <Meter value={f.importance} max={max} tone={i === 0 ? 'accent' : 'muted'} label={`${f.feature} importance`} />
                    <span className="num text-right text-fg-2">{Math.round(f.importance * 100)}%</span>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </div>
    </Panel>
  )
}
