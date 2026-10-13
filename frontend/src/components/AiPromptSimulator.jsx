import { useState, useMemo } from 'react'
import {
  Sparkles,
  Play,
  RotateCcw,
  Lightbulb,
  CheckCircle2,
  AlertTriangle,
  Activity,
  ArrowRight,
  Clock,
  ShieldAlert,
  Zap,
  Sliders,
  Plus,
  Trash2,
  ChevronRight,
  TrendingUp,
  Truck,
  Building2,
  HelpCircle,
} from 'lucide-react'
import { useStore } from '../store.js'
import { eventLabel, fmtNum, fmtPct, fmtINR } from '../format.js'
import { Button, Card, CardBody, CardHeader, InlineError, Badge, cn, useToast } from './ui/index.js'

const INSPIRATION_PROMPTS = [
  {
    title: 'Monsoon Flood & E-Commerce Surge',
    badge: 'Flagship Scenario',
    prompt:
      'Heavy monsoon flooding in Chennai halts chip supplies for 10 days, while Mumbai e-commerce festival surges consumer demand by 45%.',
  },
  {
    title: 'Warehouse Transport Strike',
    badge: 'Logistics Freeze',
    prompt: 'Transport strike blocks Bhiwandi warehouse for 5 days.',
  },
  {
    title: 'Factory Machinery Bottleneck',
    badge: 'Capacity Drop',
    prompt: 'Bengaluru assembly plant operates at only 20% capacity from day 3 for 8 days.',
  },
  {
    title: 'Corridor Landslide & Retail Surge',
    badge: 'Multi-Echelon Shock',
    prompt: 'Nashik to Bhiwandi highway corridor blocked due to landslides for 5 days, while Hyderabad demand surges by 30%.',
  },
]

const NODE_OPTIONS = [
  { id: 'S1', label: 'S1 · Pune Steel Coils (Supplier)' },
  { id: 'S2', label: 'S2 · Chennai Electronics (Supplier)' },
  { id: 'S3', label: 'S3 · Gujarat Polymers (Supplier)' },
  { id: 'S4', label: 'S4 · Kolkata Backup (Supplier)' },
  { id: 'S5', label: 'S5 · Jamshedpur Castings (Supplier)' },
  { id: 'F1', label: 'F1 · Bengaluru Assembly (Factory)' },
  { id: 'F2', label: 'F2 · Hyderabad Plant (Factory)' },
  { id: 'F3', label: 'F3 · Nashik Works (Factory)' },
  { id: 'W1', label: 'W1 · Bhiwandi DC (Warehouse)' },
  { id: 'W2', label: 'W2 · Gurugram DC (Warehouse)' },
  { id: 'W3', label: 'W3 · Sriperumbudur DC (Warehouse)' },
  { id: 'W4', label: 'W4 · Nagpur Hub (Warehouse)' },
  { id: 'C1', label: 'C1 · Mumbai Retail (Customer)' },
  { id: 'C2', label: 'C2 · Delhi Retail (Customer)' },
  { id: 'C3', label: 'C3 · Bengaluru Retail (Customer)' },
  { id: 'C4', label: 'C4 · Hyderabad Retail (Customer)' },
]

export default function AiPromptSimulator() {
  const { parseText, runSimulation, sim, loading, errors, setEvents, events: storeEvents } = useStore()
  const toast = useToast()

  const [text, setText] = useState(INSPIRATION_PROMPTS[0].prompt)
  const [parseResponse, setParseResponse] = useState(null)
  const [editableEvents, setEditableEvents] = useState([])
  const [activeStep, setActiveStep] = useState('input') // 'input' | 'review' | 'simulated'

  // Step 1: Human triggers AI / Rule parsing (no simulation yet)
  const handleParse = async (overrideText) => {
    const query = (typeof overrideText === 'string' ? overrideText : text).trim()
    if (!query || loading.parse) return
    const res = await parseText(query)
    if (res && res.events) {
      setParseResponse(res)
      setEditableEvents(res.events)
      setActiveStep('review')
      toast('Scenario Parsed!', {
        description: `Identified ${res.events.length} disruption event(s). Review parameters below before running solver.`,
      })
    }
  }

  // Event editing handlers (Human-in-the-loop)
  const updateEventField = (index, field, value) => {
    setEditableEvents((prev) => {
      const copy = [...prev]
      copy[index] = { ...copy[index], [field]: value }
      return copy
    })
  }

  const removeEvent = (index) => {
    setEditableEvents((prev) => prev.filter((_, i) => i !== index))
  }

  const addEvent = () => {
    setEditableEvents((prev) => [
      ...prev,
      {
        type: 'capacity_drop',
        target: 'S2',
        start: 0,
        duration: 7,
        severity: 0.85,
        justification: 'Manual user-added disruption event',
      },
    ])
  }

  // Step 2: Human confirms reviewed/edited events and triggers 30-day LP simulation
  const handleConfirmAndSimulate = async () => {
    if (!editableEvents.length || loading.sim) return
    setEvents(editableEvents)
    const simRes = await runSimulation(editableEvents)
    if (simRes) {
      setActiveStep('simulated')
      toast('Simulation Complete!', {
        description: `Physics LP solver completed. Survival Clock: Day ${simRes.survival_clock_days}.`,
      })
    }
  }

  // Resolving Ambiguities with one click
  const resolveAmbiguity = (resolvedTarget) => {
    if (!editableEvents.length) return
    setEditableEvents((prev) => {
      const copy = [...prev]
      copy[0] = { ...copy[0], target: resolvedTarget }
      return copy
    })
    toast('Ambiguity Resolved', {
      description: `Target set to ${resolvedTarget}.`,
    })
  }

  // Instant Surrogate Risk Data
  const quickRisk = parseResponse?.ml_quick_risk
  const cascadePreview = parseResponse?.cascade_preview || []
  const followups = parseResponse?.suggested_followups || []
  const ambiguities = parseResponse?.ambiguities || []

  // Simulated comparison from engine
  const surrogateComp = sim?.surrogate_comparison
  const cascadeSimulated = sim?.cascade_simulated || []
  const recoveryOptions = sim?.top_recovery_options || []

  return (
    <Card className="overflow-hidden border-accent/40 bg-gradient-to-b from-surface to-surface-2/60 shadow-xl ring-1 ring-accent/25">
      {/* Top Banner Header */}
      <div className="border-b border-border bg-gradient-to-r from-accent/15 via-surface to-surface-2 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-fg shadow-md shadow-accent/30">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold tracking-tight text-fg">
                  AI What-If Disruption Simulator
                </h2>
                <Badge tone="accent">Dual-Engine (Gemini / Rules)</Badge>
                <Badge tone="ok" dot>
                  Human-in-the-Loop
                </Badge>
              </div>
              <p className="mt-0.5 text-xs text-fg-muted">
                Describe natural language disruptions — AI extracts parameters, XGBoost forecasts risk in &lt;5ms, and the LP solver simulates exact cascade losses.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5 text-xs">
            <span className={cn('rounded px-2 py-0.5 font-medium transition-colors', activeStep === 'input' ? 'bg-accent text-accent-fg' : 'text-fg-muted')}>
              1. Prompt
            </span>
            <ChevronRight className="h-3 w-3 text-fg-muted" />
            <span className={cn('rounded px-2 py-0.5 font-medium transition-colors', activeStep === 'review' ? 'bg-accent text-accent-fg' : 'text-fg-muted')}>
              2. Review &amp; ML Foresight
            </span>
            <ChevronRight className="h-3 w-3 text-fg-muted" />
            <span className={cn('rounded px-2 py-0.5 font-medium transition-colors', activeStep === 'simulated' ? 'bg-accent text-accent-fg' : 'text-fg-muted')}>
              3. Simulated Ground Truth
            </span>
          </div>
        </div>
      </div>

      <CardBody className="space-y-5 p-5">
        {/* Prompt Input Box */}
        <div className="space-y-2">
          <div className="relative rounded-xl border border-border bg-surface shadow-inner focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20 transition-all">
            <textarea
              id="ai-scenario-hero-text"
              rows={3}
              maxLength={500}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type your scenario in plain English (e.g. 'Heavy monsoon flooding in Chennai halts chip supplies for 10 days, while Mumbai e-commerce festival surges consumer demand by 45%...')"
              className="w-full resize-y rounded-t-xl bg-transparent p-4 text-sm leading-relaxed text-fg placeholder:text-fg-muted/60 focus:outline-none min-h-[90px]"
            />

            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/60 bg-surface-2/50 px-3 py-2 rounded-b-lg">
              <div className="flex items-center gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  icon={Sparkles}
                  disabled={loading.parse || text.trim().length < 3}
                  onClick={handleParse}
                  className="shadow-sm font-semibold"
                >
                  {loading.parse ? 'Analyzing Scenario…' : 'Parse Disruption Scenario'}
                </Button>

                {text && (
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={RotateCcw}
                    onClick={() => {
                      setText('')
                      setParseResponse(null)
                      setEditableEvents([])
                      setActiveStep('input')
                    }}
                  >
                    Clear
                  </Button>
                )}
              </div>

              <div className="flex items-center gap-3 text-[11px] text-fg-muted">
                <span>{text.length}/500 chars</span>
                <span>•</span>
                <span>Calibrated Indian SC assumptions</span>
              </div>
            </div>
          </div>

          <InlineError message={errors.parse} />

          {/* Quick Inspiration Prompts */}
          <div className="pt-1">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-fg-muted">
              <Lightbulb className="h-3.5 w-3.5 text-warn" />
              Benchmark Indian Supply Chain Scenarios (Click to test):
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {INSPIRATION_PROMPTS.map((item, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    setText(item.prompt)
                    handleParse(item.prompt)
                  }}
                  className={cn(
                    'group flex flex-col justify-between rounded-lg border p-2.5 text-left text-xs transition-all',
                    text === item.prompt
                      ? 'border-accent bg-accent/15 text-accent shadow-sm'
                      : 'border-border bg-surface hover:border-border-strong hover:bg-surface-2 text-fg-2 hover:text-fg'
                  )}
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="font-semibold text-fg">{item.title}</span>
                    <Badge tone="muted" className="text-[10px]">{item.badge}</Badge>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[11px] text-fg-muted group-hover:text-fg-2">
                    {item.prompt}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Step 2: Ambiguity Clarification Prompt (if any) */}
        {ambiguities.length > 0 && (
          <div className="rounded-xl border border-warn/40 bg-warn/10 p-3.5 text-xs text-fg">
            <div className="flex items-center gap-2 font-semibold text-warn">
              <AlertTriangle className="h-4 w-4" />
              Ambiguity Flagged: Human Confirmation Required
            </div>
            <ul className="mt-1.5 space-y-1 pl-6 list-disc text-fg-2">
              {ambiguities.map((amb, i) => (
                <li key={i}>{amb}</li>
              ))}
            </ul>
            <div className="mt-2.5 flex items-center gap-2">
              <span className="text-[11px] font-medium text-fg-muted">Quick Disambiguation:</span>
              <Button size="xs" variant="secondary" onClick={() => resolveAmbiguity('C1')}>
                Select C1 (Mumbai Retail)
              </Button>
              <Button size="xs" variant="secondary" onClick={() => resolveAmbiguity('W1')}>
                Select W1 (Bhiwandi DC)
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Human-in-the-Loop "What I Understood" & Editable Parameter Review */}
        {parseResponse && editableEvents.length > 0 && (
          <div className="space-y-4 rounded-xl border border-border bg-surface-2/40 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/80 pb-3">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-ok" />
                <h3 className="text-sm font-bold text-fg">
                  What The AI Understood (Human Review &amp; Edit)
                </h3>
                <Badge tone={parseResponse.source === 'llm' ? 'accent' : 'ok'}>
                  Source: {parseResponse.source.toUpperCase()} Engine
                </Badge>
                <Badge tone="muted">
                  Confidence: {Math.round((parseResponse.confidence || 0.9) * 100)}%
                </Badge>
              </div>

              <span className="text-xs text-fg-muted">
                Review &amp; adjust values before executing physical flow simulation.
              </span>
            </div>

            {/* Narrative Explanation */}
            {parseResponse.interpreted_narrative && (
              <p className="text-xs text-fg-2 leading-relaxed bg-surface rounded-lg p-2.5 border border-border/60">
                <span className="font-semibold text-fg">Interpreted Narrative:</span>{' '}
                {parseResponse.interpreted_narrative}
              </p>
            )}

            {/* Editable Disruption Event Cards */}
            <div className="space-y-2.5">
              <div className="flex items-center justify-between text-xs font-semibold text-fg-muted">
                <span>Active Disruption Events ({editableEvents.length}):</span>
                <Button size="xs" variant="ghost" icon={Plus} onClick={addEvent}>
                  Add Event
                </Button>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                {editableEvents.map((ev, idx) => (
                  <div
                    key={idx}
                    className="relative rounded-xl border border-border bg-surface p-3 shadow-sm space-y-3"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-bold text-accent">Event #{idx + 1}</span>
                      <button
                        type="button"
                        onClick={() => removeEvent(idx)}
                        className="text-fg-muted hover:text-bad transition-colors"
                        title="Remove event"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {/* Target Node */}
                      <div>
                        <label className="text-[11px] font-medium text-fg-muted">Target Site / Lane</label>
                        <select
                          value={ev.target}
                          onChange={(e) => updateEventField(idx, 'target', e.target.value)}
                          className="mt-1 w-full rounded-md border border-border bg-surface-2 px-2 py-1 text-xs text-fg focus:outline-none focus:border-accent"
                        >
                          {NODE_OPTIONS.map((opt) => (
                            <option key={opt.id} value={opt.id}>
                              {opt.label}
                            </option>
                          ))}
                          {Boolean(ev.target && typeof ev.target === 'string' && ev.target.includes('->')) && (
                            <option value={ev.target}>{ev.target} (Corridor Lane)</option>
                          )}
                          {Boolean(
                            ev.target &&
                              typeof ev.target === 'string' &&
                              !NODE_OPTIONS.some((o) => o.id === ev.target) &&
                              !ev.target.includes('->')
                          ) && (
                            <option value={ev.target}>{ev.target}</option>
                          )}
                        </select>
                      </div>

                      {/* Disruption Type */}
                      <div>
                        <label className="text-[11px] font-medium text-fg-muted">Disruption Type</label>
                        <select
                          value={ev.type}
                          onChange={(e) => updateEventField(idx, 'type', e.target.value)}
                          className="mt-1 w-full rounded-md border border-border bg-surface-2 px-2 py-1 text-xs text-fg focus:outline-none focus:border-accent"
                        >
                          <option value="capacity_drop">Capacity Drop</option>
                          <option value="node_freeze">Complete Freeze (100%)</option>
                          <option value="route_block">Corridor Block</option>
                          <option value="demand_surge">Demand Surge (+%)</option>
                        </select>
                      </div>

                      {/* Start Day */}
                      <div>
                        <label className="text-[11px] font-medium text-fg-muted">Start Day (0-30)</label>
                        <input
                          type="number"
                          min="0"
                          max="30"
                          value={ev.start ?? 0}
                          onChange={(e) => updateEventField(idx, 'start', parseInt(e.target.value) || 0)}
                          className="mt-1 w-full rounded-md border border-border bg-surface-2 px-2 py-1 text-xs text-fg focus:outline-none focus:border-accent"
                        />
                      </div>

                      {/* Duration Days */}
                      <div>
                        <label className="text-[11px] font-medium text-fg-muted">Duration (Days)</label>
                        <input
                          type="number"
                          min="1"
                          max="60"
                          value={ev.duration ?? 7}
                          onChange={(e) => updateEventField(idx, 'duration', parseInt(e.target.value) || 1)}
                          className="mt-1 w-full rounded-md border border-border bg-surface-2 px-2 py-1 text-xs text-fg focus:outline-none focus:border-accent"
                        />
                      </div>
                    </div>

                    {/* Severity Slider */}
                    <div>
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="font-medium text-fg-muted">
                          {ev.type === 'demand_surge' ? 'Demand Multiplier' : 'Capacity Reduction'}
                        </span>
                        <span className="font-semibold text-accent font-mono">
                          {ev.type === 'demand_surge'
                            ? `${Math.round(((ev.severity >= 1.0 ? ev.severity : 1.0 + ev.severity) - 1.0) * 100)}% surge (${(ev.severity >= 1.0 ? ev.severity : 1.0 + ev.severity).toFixed(2)}x)`
                            : `${Math.round(Math.min(ev.severity, 1.0) * 100)}% outage`}
                        </span>
                      </div>
                      <input
                        type="range"
                        min="0"
                        max={ev.type === 'demand_surge' ? '300' : '100'}
                        value={
                          ev.type === 'demand_surge'
                            ? Math.round((ev.severity >= 1.0 ? ev.severity : 1.0 + ev.severity) * 100)
                            : Math.round(ev.severity * 100)
                        }
                        onChange={(e) => {
                          const val = parseFloat(e.target.value) / 100.0
                          updateEventField(idx, 'severity', val)
                        }}
                        className="mt-1 w-full accent-accent"
                      />
                    </div>

                    {ev.justification && (
                      <p className="text-[11px] text-fg-muted italic border-t border-border/50 pt-1.5">
                        {ev.justification}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Instant Surrogate ML Risk Foresight Card */}
            {quickRisk && (
              <div className="rounded-xl border border-accent/30 bg-surface p-4 shadow-sm space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2.5">
                  <div className="flex items-center gap-2">
                    <Zap className="h-4 w-4 text-accent" />
                    <span className="text-xs font-bold text-fg">
                      Instant Surrogate ML Foresight
                    </span>
                    <Badge tone="muted" className="text-[10px]">
                      XGBoost Regressor
                    </Badge>
                  </div>

                  <div className="flex items-center gap-2">
                    <Badge
                      tone={
                        quickRisk.risk_level === 'High'
                          ? 'bad'
                          : quickRisk.risk_level === 'Moderate'
                          ? 'warn'
                          : 'ok'
                      }
                      dot
                    >
                      {quickRisk.risk_level} Criticality Risk
                    </Badge>
                    <span className="text-[11px] text-fg-muted font-mono">
                      (Inference: {quickRisk.latency_ms || 1.2} ms)
                    </span>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 items-center text-xs">
                  <div>
                    <span className="text-fg-muted">Projected Baseline Unmet Demand:</span>
                    <div className="mt-1 text-2xl font-black text-fg font-mono">
                      {Math.round((quickRisk.predicted_unmet_share ?? 0) * 100)}%
                    </div>
                    <p className="text-[11px] text-fg-muted">
                      Predicted by ML surrogate prior to full physical solver.
                    </p>
                  </div>

                  <div>
                    <span className="text-fg-muted font-semibold">Top SHAP Risk Drivers:</span>
                    <div className="mt-1.5 space-y-1">
                      {quickRisk.top_factors?.map((f, i) => (
                        <div key={i} className="flex items-center justify-between text-[11px] bg-surface-2 rounded px-2 py-0.5">
                          <span className="font-mono text-fg-2">{f.feature}</span>
                          <span className={cn('font-mono font-semibold', (f.impact || 0) > 0 ? 'text-bad' : 'text-ok')}>
                            {(f.impact || 0) > 0 ? '+' : ''}{Number(f.impact || 0).toFixed(3)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Deterministic Cascade Preview: TTS vs TTR (Quick Estimate) */}
            {cascadePreview.length > 0 && (
              <div className="rounded-xl border border-border bg-surface p-4 shadow-sm space-y-3">
                <div className="flex items-center justify-between gap-2 border-b border-border pb-2.5">
                  <div className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-accent" />
                    <span className="text-xs font-bold text-fg">
                      Deterministic Cascade Ripple (TTS vs TTR)
                    </span>
                    <Badge tone="muted" className="text-[10px]">
                      Quick Estimate
                    </Badge>
                  </div>
                  <span className="text-[11px] text-fg-muted font-mono">
                    Formula: TTS = t_impact + stock / depletion_rate
                  </span>
                </div>

                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {cascadePreview.map((item, idx) => (
                    <div
                      key={idx}
                      className={cn(
                        'rounded-lg border p-2.5 text-xs space-y-1.5 transition-all',
                        item.status === 'fails'
                          ? 'border-bad/40 bg-bad/5'
                          : 'border-ok/40 bg-ok/5'
                      )}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className="font-bold text-fg">
                          {item.node} · {item.name}
                        </span>
                        <Badge tone={item.status === 'fails' ? 'bad' : 'ok'}>
                          {item.status === 'fails' ? 'Stockout Risk' : 'Survives'}
                        </Badge>
                      </div>

                      <div className="grid grid-cols-2 gap-1 text-[11px] text-fg-2">
                        <div>
                          Impact: <span className="font-semibold text-fg font-mono">Day {item.first_impact_day}</span>
                        </div>
                        <div>
                          TTS: <span className="font-semibold text-fg font-mono">{item.tts_days}d</span>
                        </div>
                        <div>
                          TTR: <span className="font-semibold text-fg font-mono">{item.ttr_days}d</span>
                        </div>
                        <div>
                          City: <span className="font-semibold text-fg">{item.city || '-'}</span>
                        </div>
                      </div>

                      <p className="text-[10px] text-fg-muted line-clamp-2 italic pt-1 border-t border-border/40">
                        {item.reason}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Primary Action Button: Confirm & Run 30-Day LP Simulation */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <div className="flex items-center gap-2 text-xs text-fg-muted">
                <ShieldAlert className="h-4 w-4 text-accent" />
                <span>Human-in-the-Loop: Review above parameters, then trigger the 30-day min-cost flow engine.</span>
              </div>

              <Button
                variant="primary"
                size="md"
                icon={Play}
                disabled={loading.sim || editableEvents.length === 0}
                onClick={handleConfirmAndSimulate}
                className="shadow-md shadow-accent/25 font-bold px-6"
              >
                {loading.sim ? 'Solving 30-Day Flow Network…' : 'Confirm & Run Simulation'}
              </Button>
            </div>
          </div>
        )}

        {/* Step 4: Post-Simulation Ground Truth & Comparison (Directive 2 & 3) */}
        {sim && activeStep === 'simulated' && (
          <div className="space-y-4 rounded-xl border border-ok/40 bg-ok/5 p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ok/20 pb-3">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-ok" />
                <h3 className="text-sm font-bold text-fg">
                  Simulation Ground Truth &amp; Model Accuracy Verification
                </h3>
                <Badge tone="ok">LP Engine Solved</Badge>
              </div>
              <span className="text-xs font-mono font-semibold text-fg">
                Survival Clock: Day {sim.survival_clock_days} · Total Unmet: {fmtNum(sim.total_unmet)} units
              </span>
            </div>

            {/* Surrogate Predicted vs Actual Comparison Card (Directive 3) */}
            {surrogateComp && (
              <div className="rounded-xl border border-border bg-surface p-3.5 text-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-fg flex items-center gap-1.5">
                    <TrendingUp className="h-4 w-4 text-accent" />
                    Surrogate Accuracy: Predicted vs. Actual LP Unmet Demand
                  </span>
                  <Badge tone="muted">{surrogateComp.label}</Badge>
                </div>

                <div className="grid grid-cols-3 gap-3 text-center pt-1">
                  <div className="bg-surface-2 rounded-lg p-2">
                    <div className="text-[11px] text-fg-muted">Surrogate Predicted Share</div>
                    <div className="text-base font-bold text-accent font-mono mt-0.5">
                      {Math.round((surrogateComp.predicted_unmet_share ?? 0) * 100)}%
                    </div>
                  </div>
                  <div className="bg-surface-2 rounded-lg p-2">
                    <div className="text-[11px] text-fg-muted">Actual Simulated LP Share</div>
                    <div className="text-base font-bold text-fg font-mono mt-0.5">
                      {Math.round((surrogateComp.actual_unmet_share ?? 0) * 100)}%
                    </div>
                  </div>
                  <div className="bg-surface-2 rounded-lg p-2">
                    <div className="text-[11px] text-fg-muted">Absolute Surrogate Error</div>
                    <div className="text-base font-bold text-ok font-mono mt-0.5">
                      {((surrogateComp.absolute_error ?? 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Simulated Cascade vs Quick Estimate (Directive 2) */}
            {cascadeSimulated.length > 0 && (
              <div className="rounded-xl border border-border bg-surface p-3.5 text-xs space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-fg flex items-center gap-1.5">
                    <Activity className="h-4 w-4 text-accent" />
                    Simulated Node Degradation Timeline
                  </span>
                  <Badge tone="ok">Simulated Ground Truth</Badge>
                </div>

                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {cascadeSimulated.map((item, i) => (
                    <div key={i} className="rounded-lg border border-border bg-surface-2 p-2.5 text-xs space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-fg">{item.node} ({item.name})</span>
                        <Badge tone={item.status === 'fails' ? 'bad' : 'ok'}>
                          Day {item.tts_days} Stockout
                        </Badge>
                      </div>
                      <p className="text-[11px] text-fg-muted">{item.reason}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Top Recovery Options (Directive F) */}
            {recoveryOptions.length > 0 && (
              <div className="rounded-xl border border-border bg-surface p-3.5 text-xs space-y-2">
                <span className="font-bold text-fg flex items-center gap-1.5">
                  <Truck className="h-4 w-4 text-accent" />
                  Top Instant Recovery Options (Optimizer Candidates)
                </span>

                <div className="grid gap-2 sm:grid-cols-2">
                  {recoveryOptions.map((opt, i) => (
                    <div key={i} className="rounded-lg border border-border bg-surface-2 p-2.5 text-xs space-y-1">
                      {opt.supplier ? (
                        <>
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-fg">
                              Alternate Supplier: {opt.name} ({opt.supplier})
                            </span>
                            <Badge tone="accent">Spare: {opt.spare_capacity} u/d</Badge>
                          </div>
                          <div className="text-[11px] text-fg-2">
                            Replaces: {opt.replaces} · Lead Time: {opt.lead}d · Premium: +{opt.cost_premium_pct}%
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-fg">
                              Alternate Route: {opt.via?.join(' → ')}
                            </span>
                            <Badge tone="accent">Spare: {opt.spare_capacity} u/d</Badge>
                          </div>
                          <div className="text-[11px] text-fg-2">
                            Replaces: {opt.replaces} · Extra Delay: +{opt.extra_lead_days}d · Cost: +₹{opt.extra_cost_per_unit}/u
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Data-Driven Follow-Up Suggestions (Directive E) */}
        {followups.length > 0 && (
          <div className="rounded-xl border border-border/80 bg-surface p-3 text-xs space-y-2">
            <div className="flex items-center gap-1.5 font-semibold text-fg-muted">
              <HelpCircle className="h-3.5 w-3.5 text-accent" />
              Data-Driven Follow-Up Suggestions (Directly from network state):
            </div>
            <div className="flex flex-wrap gap-2">
              {followups.map((fol, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setText(fol)}
                  className="rounded-lg border border-accent/20 bg-accent/5 px-2.5 py-1 text-left text-xs text-accent hover:bg-accent/10 transition-colors"
                >
                  → {fol}
                </button>
              ))}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
