import { useEffect } from 'react'
import { BrainCircuit } from 'lucide-react'
import { useStore } from '../store.js'
import { fmtNum } from '../format.js'
import { Card, CardBody, CardHeader, InlineError, Meter, SkeletonBlock } from './ui/index.js'

function Metric({ label, value }) {
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2.5">
      <dt className="text-xs text-fg-muted">{label}</dt>
      <dd className="tabular text-base font-semibold text-fg">{value}</dd>
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
    <Card>
      <CardHeader title="ML surrogate accuracy" description="Held-out networks, never seen in training" icon={BrainCircuit} />
      <CardBody className="space-y-4">
        <InlineError message={errors.surrogate} onRetry={loadSurrogate} />
        {loading.surrogate && !surrogate && <SkeletonBlock lines={5} label="Loading model metrics" />}
        {surrogate && (
          <>
            <p className="text-xs text-fg-2">
              Predicts <i>{surrogate.target}</i>, {fmtNum(surrogate.speedup)}× faster than running the engine.
            </p>
            <dl className="grid grid-cols-4 gap-2">
              <Metric label="R²" value={surrogate.r2.toFixed(2)} />
              {/* the live model predicts a share of demand (0..1); older mocks reported units */}
              <Metric label="MAE" value={surrogate.mae < 1 ? `${(surrogate.mae * 100).toFixed(1)}%` : `${fmtNum(surrogate.mae)} u`} />
              <Metric label="Train" value={fmtNum(surrogate.n_train)} />
              <Metric label="Test" value={fmtNum(surrogate.n_test)} />
            </dl>
            <div>
              <p className="label mb-2">Top features (gain)</p>
              <ul className="space-y-2">
                {surrogate.top_features.map((f) => (
                  <li key={f.feature} className="grid grid-cols-[10rem_1fr_2.5rem] items-center gap-3 text-xs">
                    <span className="truncate text-fg-2" title={f.feature}>
                      {f.feature.replaceAll('_', ' ')}
                    </span>
                    <Meter value={f.importance} max={max} label={`${f.feature} importance`} />
                    <span className="tabular text-right text-fg-2">{Math.round(f.importance * 100)}%</span>
                  </li>
                ))}
              </ul>
            </div>
          </>
        )}
      </CardBody>
    </Card>
  )
}
