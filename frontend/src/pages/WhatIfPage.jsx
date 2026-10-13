import { useMemo } from 'react'
import { Activity, ArrowRight, CheckCircle2, FlaskConical, Play, Sparkles } from 'lucide-react'
import { DEMO_SCENARIOS, useStore } from '../store.js'
import { disruptionForDay } from '../lib/disruption.js'
import { Badge, Button, Card, CardBody, CardHeader, PageHeader, cn } from '../components/ui/index.js'
import KpiCards from '../components/KpiCards.jsx'
import ScenarioPanel from '../components/ScenarioPanel.jsx'
import GraphPanel from '../components/GraphPanel.jsx'
import DaySlider from '../components/DaySlider.jsx'
import UtilizationBars from '../components/UtilizationBars.jsx'
import DelayChart from '../components/DelayChart.jsx'
import EventLog from '../components/EventLog.jsx'
import MonteCarloChart from '../components/MonteCarloChart.jsx'
import AiPromptSimulator from '../components/AiPromptSimulator.jsx'

export default function WhatIfPage() {
  const { sim, day, events, network, setEvents, runSimulation, setTab } = useStore()
  const row = sim ? sim.timeline[day] || sim.timeline[0] : null
  const statuses = row?.node_status ?? null
  const disrupted = useMemo(() => (sim ? disruptionForDay(network, events, day, statuses) : null), [sim, network, events, day, statuses])

  const currentEventsStr = JSON.stringify(events)

  const handleSelectScenario = (sc) => {
    setEvents(sc.events)
    runSimulation(sc.events)
  }

  return (
    <>
      <PageHeader
        title="Disruption Simulator"
        description="Simulate disruption scenarios, stress-test supply chain bottlenecks, and track operational resilience day by day."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              iconRight={ArrowRight}
              onClick={() => setTab('recover')}
              disabled={!events.length}
            >
              Plan Recovery for this Simulation
            </Button>
            <Button
              variant="primary"
              icon={Play}
              onClick={() => runSimulation(events)}
              disabled={!events.length}
            >
              Run Simulation
            </Button>
          </div>
        }
      />

      {/* Flagship AI Disruption Prompt Hero (Top Prominence) */}
      <div className="mb-6">
        <AiPromptSimulator />
      </div>

      {/* Quick Start Scenario Library Carousel / Grid */}
      <Card className="mb-6 overflow-hidden border-border/80 shadow-sm">
        <CardHeader
          title="Disruption Scenario Library"
          description="Pick a pre-configured disruption or AI bottleneck scenario to simulate instantly."
          icon={FlaskConical}
        />
        <CardBody className="pt-2">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {DEMO_SCENARIOS.map((sc) => {
              const active = JSON.stringify(sc.events) === currentEventsStr

              return (
                <button
                  key={sc.id}
                  type="button"
                  onClick={() => handleSelectScenario(sc)}
                  className={cn(
                    'group relative flex flex-col justify-between rounded-xl border p-3.5 text-left transition-all duration-150',
                    active
                      ? 'border-accent bg-accent/10 shadow-sm ring-1 ring-accent/30'
                      : 'border-border bg-surface-2/50 hover:border-border-strong hover:bg-surface-2'
                  )}
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold text-fg">{sc.label}</span>
                      <div className="flex items-center gap-1.5">
                        {sc.category && <Badge tone={active ? 'accent' : 'muted'}>{sc.category}</Badge>}
                        {active && <CheckCircle2 className="h-3.5 w-3.5 text-accent" />}
                      </div>
                    </div>
                    <p className="mt-1.5 text-xs text-fg-2 leading-relaxed">{sc.blurb}</p>
                  </div>
                  <div className="mt-3 flex items-center justify-between text-[11px] text-fg-muted">
                    <span>{sc.events.length} disruption event{sc.events.length > 1 ? 's' : ''}</span>
                    <span className="font-medium text-accent opacity-0 transition-opacity group-hover:opacity-100">
                      Load Scenario →
                    </span>
                  </div>
                </button>
              )
            })}
          </div>
        </CardBody>
      </Card>

      {/* KPI Impact Summary */}
      <KpiCards />

      {/* Two-Column Simulation Workspace */}
      <div className="mt-6 grid gap-6 xl:grid-cols-12">
        <div className="xl:col-span-4 2xl:col-span-3">
          <ScenarioPanel />
        </div>
        <div className="space-y-6 xl:col-span-8 2xl:col-span-9">
          <GraphPanel
            title="Network State & Disruptions"
            description={sim ? `Day ${row.day} of ${sim.timeline.length - 1} · Color-coded operational status` : 'Run a scenario to color nodes by status'}
            icon={Activity}
            statuses={statuses}
            utilization={row?.utilization ?? null}
            disrupted={disrupted}
            heightClass="h-[520px]"
            footer={sim && <DaySlider />}
          />
          <div className="grid gap-6 2xl:grid-cols-2">
            <UtilizationBars />
            <DelayChart />
          </div>
          <div className="grid gap-6 2xl:grid-cols-2">
            <EventLog />
            <MonteCarloChart />
          </div>
        </div>
      </div>
    </>
  )
}
