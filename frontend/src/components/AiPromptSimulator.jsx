import { useState } from 'react'
import { Sparkles, Play, RotateCcw, Lightbulb, CheckCircle2 } from 'lucide-react'
import { useStore } from '../store.js'
import { eventLabel, fmtNum } from '../format.js'
import { Button, Card, CardBody, CardHeader, InlineError, Badge, cn, useToast } from './ui/index.js'

const INSPIRATION_PROMPTS = [
  {
    title: 'Supplier Flood & Demand Surge',
    prompt: 'Chennai electronics supplier floods from day 2 for about 10 days, and Bengaluru demand jumps 40%.',
  },
  {
    title: 'Central Warehouse Outage',
    prompt: 'Bhiwandi warehouse goes offline for 7 days, cutting off inventory to Mumbai and Jaipur retailers.',
  },
  {
    title: 'Assembly Plant Bottleneck',
    prompt: 'Bengaluru assembly plant operates at only 20% capacity from day 3 for 8 days.',
  },
  {
    title: 'Highway Closure & Retail Surge',
    prompt: 'Bengaluru to Sriperumbudur lane is completely blocked for 8 days, while Hyderabad demand surges by 50%.',
  },
]

export default function AiPromptSimulator() {
  const { parseText, runSimulation, loading, errors } = useStore()
  const toast = useToast()
  const [text, setText] = useState(INSPIRATION_PROMPTS[0].prompt)
  const [lastParsed, setLastParsed] = useState(null)

  const handleParseAndSimulate = async () => {
    if (!text.trim() || loading.parse || loading.sim) return
    const res = await parseText(text)
    if (res && res.events?.length) {
      setLastParsed(res.events)
      const simRes = await runSimulation(res.events)
      toast(`AI Disruption Simulated!`, {
        description: `Parsed ${res.events.length} event(s): ${res.events.map(eventLabel).join(' · ')}`,
      })
    }
  }

  return (
    <Card className="overflow-hidden border-accent/40 bg-gradient-to-b from-surface to-surface-2/60 shadow-lg ring-1 ring-accent/20">
      {/* Hero Header */}
      <div className="border-b border-border bg-gradient-to-r from-accent/10 via-surface to-surface-2 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-accent-fg shadow-md shadow-accent/25">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold tracking-tight text-fg">
                  AI Natural Language Disruption Simulator
                </h2>
                <Badge tone="accent">Gemini AI Powered</Badge>
                <Badge tone="ok" dot>
                  Zero Manual Setup
                </Badge>
              </div>
              <p className="mt-0.5 text-xs text-fg-muted">
                Describe any disruption in plain English — the AI extracts affected sites, routes, and severities to simulate the exact ripple effect.
              </p>
            </div>
          </div>
        </div>
      </div>

      <CardBody className="space-y-4 p-5">
        {/* Large Spacious Textarea */}
        <div className="relative rounded-xl border border-border bg-surface shadow-inner focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20 transition-all">
          <textarea
            id="ai-scenario-hero-text"
            rows={4}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type your scenario in plain English (e.g. 'Chennai electronics supplier floods from day 2 for about 10 days, and Bengaluru demand jumps 40%...')"
            className="w-full resize-y rounded-t-xl bg-transparent p-4 text-base leading-relaxed text-fg placeholder:text-fg-muted/60 focus:outline-none min-h-[110px]"
          />

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/60 bg-surface-2/50 px-3 py-2.5 rounded-b-lg">
            <div className="flex items-center gap-2">
              <Button
                variant="primary"
                size="md"
                icon={Sparkles}
                disabled={loading.parse || loading.sim || text.trim().length < 3}
                onClick={handleParseAndSimulate}
                className="shadow-md shadow-accent/20 font-semibold"
              >
                {loading.parse ? 'AI Parsing Events…' : loading.sim ? 'Simulating Engine…' : 'Parse & Simulate with AI'}
              </Button>

              {text && (
                <Button
                  variant="ghost"
                  size="sm"
                  icon={RotateCcw}
                  onClick={() => setText('')}
                >
                  Clear
                </Button>
              )}
            </div>

            <span className="text-[11px] text-fg-muted">
              LLM extracts parameters · Physics flow solver computes exact losses
            </span>
          </div>
        </div>

        <InlineError message={errors.parse} />

        {/* Quick Inspiration Prompts (One-Click Testing) */}
        <div>
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-fg-muted">
            <Lightbulb className="h-3.5 w-3.5 text-warn" />
            Quick Inspiration Prompts (Click to test):
          </div>
          <div className="flex flex-wrap gap-2">
            {INSPIRATION_PROMPTS.map((item, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => setText(item.prompt)}
                className={cn(
                  'rounded-lg border px-3 py-1.5 text-xs text-left transition-all',
                  text === item.prompt
                    ? 'border-accent bg-accent/15 text-accent font-semibold shadow-sm'
                    : 'border-border bg-surface hover:border-border-strong hover:bg-surface-2 text-fg-2 hover:text-fg'
                )}
              >
                <span className="font-medium text-fg">{item.title}:</span>{' '}
                <span className="text-fg-muted text-[11px] line-clamp-1">{item.prompt}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Parsed Events Pill Preview */}
        {lastParsed && lastParsed.length > 0 && (
          <div className="rounded-xl border border-ok/30 bg-ok/5 p-3 text-xs">
            <div className="flex items-center gap-2 font-semibold text-ok">
              <CheckCircle2 className="h-4 w-4" />
              Active AI Extracted Disruption Events:
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {lastParsed.map((ev, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 rounded-md border border-ok/20 bg-surface px-2.5 py-1 font-mono text-fg"
                >
                  <span className="font-semibold text-accent">{ev.type.toUpperCase()}:</span>{' '}
                  {ev.target} · Day {ev.start} (+{ev.duration}d) · {Math.round(ev.severity * 100)}% severity
                </span>
              ))}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
