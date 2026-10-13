import { useEffect } from 'react'
import { Brain, ChevronRight, Info } from 'lucide-react'
import { useStore } from '../store.js'
import { fmtPct } from '../format.js'
import { Badge, Card, CardBody, CardHeader, InlineError, Meter, SkeletonBlock, cn } from './ui/index.js'

/** Diverging SHAP bars for scenario-level feature contributions. */
function ScenarioShapBars({ factors }) {
  if (!factors?.length) return <p className="text-xs text-fg-muted">No explanation available.</p>
  const max = Math.max(...factors.map((f) => Math.abs(f.impact)), 1e-9)
  return (
    <ul className="space-y-2.5">
      {factors.map((f) => {
        const pct = (Math.abs(f.impact) / max) * 50
        const up = f.impact > 0
        return (
          <li key={f.feature}>
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span className="truncate text-fg-2">{f.feature.replaceAll('_', ' ')}</span>
              <span className={cn('tabular font-medium', up ? 'text-bad' : 'text-ok')}>
                {up ? '+' : '−'}
                {Math.abs(f.impact).toFixed(4)}
              </span>
            </div>
            <div className="relative mt-1 h-1.5 rounded-full bg-surface-3" aria-hidden>
              <span className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
              <span
                className={cn('absolute inset-y-0 rounded-full', up ? 'bg-bad/70' : 'bg-ok/70')}
                style={up ? { left: '50%', width: `${pct}%` } : { right: '50%', width: `${pct}%` }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

const RISK_TIERS = {
  low: { tone: 'ok', label: 'Low risk', desc: 'Disruption absorbed by safety stock & alternate lanes' },
  moderate: { tone: 'warn', label: 'Moderate risk', desc: 'Localized stockouts; order delays expected' },
  high: { tone: 'bad', label: 'High risk', desc: 'Significant unmet demand across customer hubs' },
  critical: { tone: 'bad', label: 'Critical risk', desc: 'Systemic supply failure; severe stockout crisis' },
}

function RiskGauge({ prediction }) {
  const { unmet_demand_fraction = 0, risk_score, risk_level, predicted_unmet_units } = prediction

  // Calibrated score fallback if not present
  const score =
    risk_score ??
    (unmet_demand_fraction < 0.005
      ? Math.round((unmet_demand_fraction / 0.005) * 29)
      : unmet_demand_fraction < 0.025
      ? Math.round(30 + ((unmet_demand_fraction - 0.005) / 0.02) * 29)
      : unmet_demand_fraction < 0.07
      ? Math.round(60 + ((unmet_demand_fraction - 0.025) / 0.045) * 24)
      : Math.min(100, Math.round(85 + ((unmet_demand_fraction - 0.07) / 0.15) * 15)))

  const tierKey = risk_level || (score < 30 ? 'low' : score < 60 ? 'moderate' : score < 85 ? 'high' : 'critical')
  const tier = RISK_TIERS[tierKey] || RISK_TIERS.low
  const pctStr = (unmet_demand_fraction * 100).toFixed(1)

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold tabular text-fg">{score}</span>
          <span className="text-xs font-medium text-fg-muted">/ 100 Risk Index</span>
        </div>
        <Badge tone={tier.tone} dot>{tier.label}</Badge>
      </div>

      <Meter value={score} max={100} threshold={60} label="Disruption risk score" />

      <div className="rounded-lg bg-surface-2 p-3 text-xs space-y-1.5">
        <div className="flex justify-between text-fg">
          <span className="text-fg-muted">Predicted unmet demand:</span>
          <span className="font-semibold tabular">{pctStr}% of 30-day demand</span>
        </div>
        {predicted_unmet_units != null && predicted_unmet_units > 0 && (
          <div className="flex justify-between text-fg">
            <span className="text-fg-muted">Estimated lost volume:</span>
            <span className="font-semibold tabular">~{Math.round(predicted_unmet_units).toLocaleString()} units</span>
          </div>
        )}
        <p className="pt-0.5 text-[11px] text-fg-muted">{tier.desc}</p>
      </div>
    </div>
  )
}

function MetricChip({ label, value }) {
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2">
      <dt className="text-xs text-fg-muted">{label}</dt>
      <dd className="tabular text-sm font-semibold text-fg">{value}</dd>
    </div>
  )
}

/**
 * RiskPredictPanel — XGBoost scenario-level risk prediction.
 * Shows predicted unmet-demand fraction + SHAP feature contributions.
 * Clearly distinguishes model predictions from exact simulator results.
 */
export default function RiskPredictPanel() {
  const { riskPrediction, riskStatus, loading, errors, loadRiskStatus, predictRisk, events } = useStore()

  // Load model status once on mount
  useEffect(() => {
    if (!riskStatus && !loading.riskStatus) loadRiskStatus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const busy = Boolean(loading.riskPredict)
  const noModel = riskPrediction?.confidence === 'no_model' || (riskStatus && !riskStatus.trained)
  const hasResult = riskPrediction && riskPrediction.confidence === 'model'

  return (
    <Card>
      <CardHeader
        title="XGBoost risk prediction"
        description="Scenario-level unmet-demand forecast — faster than the simulator, not a replacement for it."
        icon={Brain}
      />
      <CardBody className="space-y-5">
        <InlineError message={errors.riskPredict} onRetry={() => predictRisk(events)} />

        {/* Model status badge */}
        {riskStatus && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge tone={riskStatus.trained ? 'ok' : 'warn'} dot>
              {riskStatus.trained ? 'Model trained' : 'Model not trained'}
            </Badge>
            {riskStatus.trained && riskStatus.metrics && (
              <>
                <span className="text-fg-muted">
                  MAE {(riskStatus.metrics.mae * 100).toFixed(2)}% · R² {riskStatus.metrics.r2.toFixed(2)}
                </span>
                <span className="text-fg-muted">
                  ({riskStatus.metrics.n_train} train / {riskStatus.metrics.n_test} test scenarios)
                </span>
              </>
            )}
          </div>
        )}

        {/* No-model state */}
        {noModel && !busy && !hasResult && (
          <div className="rounded-lg border border-dashed border-border bg-surface-2/50 px-4 py-4 text-xs text-fg-muted">
            <p className="font-medium text-fg">Scenario risk model not trained</p>
            <p className="mt-1">
              Run <code className="rounded bg-surface-3 px-1 py-0.5 font-mono">
                python -m core.scenario_ml
              </code>{' '}
              in the backend to train the XGBoost model.
            </p>
          </div>
        )}

        {/* Loading skeleton */}
        {busy && !hasResult && <SkeletonBlock lines={4} label="Predicting risk..." />}

        {/* Prediction result */}
        {hasResult && (
          <>
            {/* Confidence disclaimer */}
            <div className="flex items-start gap-1.5 rounded-md border border-accent/20 bg-accent/5 px-3 py-2 text-xs text-fg-2">
              <Info className="mt-px h-3.5 w-3.5 shrink-0 text-accent" aria-hidden />
              <span>
                <strong>ML prediction</strong> — uses scenario features, not a full simulation.
                Use <strong>Run simulation</strong> for the exact result.
              </span>
            </div>

            <RiskGauge prediction={riskPrediction} />

            {/* Model accuracy metrics */}
            {riskPrediction.model_metrics && (
              <dl className="grid grid-cols-4 gap-2">
                <MetricChip label="MAE" value={`${(riskPrediction.model_metrics.mae * 100).toFixed(2)}%`} />
                <MetricChip label="R²" value={riskPrediction.model_metrics.r2.toFixed(2)} />
                <MetricChip label="Train" value={riskPrediction.model_metrics.n_train} />
                <MetricChip label="Test" value={riskPrediction.model_metrics.n_test} />
              </dl>
            )}

            {/* SHAP contributions */}
            <div>
              <h3 className="mb-1 text-xs font-semibold text-fg">Top contributing features</h3>
              <p className="mb-3 text-xs text-fg-muted">
                SHAP values show which scenario properties push the prediction up (red) or down (green).
                These are <em>feature contributions</em>, not causal explanations.
              </p>
              <ScenarioShapBars factors={riskPrediction.top_factors} />
            </div>

            {riskPrediction.note && (
              <p className="text-xs text-fg-muted italic">{riskPrediction.note}</p>
            )}
          </>
        )}

        {/* Predict button */}
        {riskStatus?.trained && (
          <button
            id="risk-predict-btn"
            type="button"
            disabled={busy || !events?.length}
            onClick={() => predictRisk(events)}
            className={cn(
              'flex w-full items-center justify-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors duration-150',
              busy || !events?.length
                ? 'cursor-not-allowed border-border bg-surface text-fg-muted'
                : 'border-accent/40 bg-accent/10 text-accent hover:bg-accent/20',
            )}
          >
            <Brain className="h-4 w-4" aria-hidden />
            {busy ? 'Predicting...' : 'Predict scenario risk'}
            {!busy && <ChevronRight className="h-3.5 w-3.5" aria-hidden />}
          </button>
        )}
      </CardBody>
    </Card>
  )
}
