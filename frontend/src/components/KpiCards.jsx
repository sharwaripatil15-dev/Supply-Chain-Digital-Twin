import { Clock, IndianRupee, PackageX, ShieldCheck, Timer } from 'lucide-react'
import { useStore } from '../store.js'
import { fmtINR, fmtNum } from '../format.js'
import { Badge, Stat } from './ui/index.js'

/** Simulation KPIs. The Survival Clock gets the prominent card. */
export default function KpiCards() {
  const { sim, network, chaos, loading } = useStore()
  const resilience = chaos?.resilience_score ?? network?.resilience_score
  const firstOut = sim && Object.entries(sim.stockout_day).sort((a, b) => a[1] - b[1])[0]
  const unmetSeries = sim?.timeline.map((d) => d.unmet)
  const busy = Boolean(loading.sim)
  const empty = !sim && !busy
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-5">
      <Stat
        label="Survival Clock"
        icon={Clock}
        emphasis
        loading={busy}
        value={sim ? sim.survival_clock_days : '-'}
        unit={sim ? 'days' : undefined}
        sub={empty ? 'Days until the first customer stocks out' : firstOut ? `until ${firstOut[0]} stocks out` : 'No customer stocks out'}
        chip={sim && <Badge tone={!firstOut ? 'ok' : sim.survival_clock_days <= 7 ? 'bad' : 'warn'} dot>{!firstOut ? 'Safe' : sim.survival_clock_days <= 7 ? 'Critical' : 'At risk'}</Badge>}
        className="col-span-2 lg:col-span-1"
      />
      <Stat
        label="Unmet demand"
        icon={PackageX}
        loading={busy}
        value={sim ? fmtNum(sim.total_unmet) : '-'}
        unit={sim ? 'units' : undefined}
        sub={empty ? 'Run a scenario' : 'over the horizon'}
        spark={unmetSeries}
      />
      <Stat
        label="Revenue at risk"
        icon={IndianRupee}
        loading={busy}
        value={sim ? fmtINR(sim.revenue_at_risk) : '-'}
        sub="Lost sales at list price"
        chip={sim && sim.revenue_at_risk > 0 && <Badge tone="bad">loss</Badge>}
      />
      <Stat
        label="Delivery delay"
        icon={Timer}
        loading={busy}
        value={sim ? fmtNum(sim.delay.avg_days, 1) : '-'}
        unit={sim ? 'd avg' : undefined}
        sub={sim ? `${sim.bottlenecks.length} bottleneck(s)` : 'Extra days vs normal lead time'}
        chip={sim && <Badge>P90 {fmtNum(sim.delay.p90_days, 1)} d</Badge>}
      />
      <Stat
        label="Resilience"
        icon={ShieldCheck}
        value={resilience != null ? resilience.toFixed(1) : '-'}
        unit={resilience != null ? '/ 100' : undefined}
        sub="From Chaos Finder stress tests"
        chip={resilience != null && <Badge tone={resilience >= 70 ? 'ok' : resilience >= 40 ? 'warn' : 'bad'} dot>{resilience >= 70 ? 'Strong' : resilience >= 40 ? 'Moderate' : 'Fragile'}</Badge>}
      />
    </div>
  )
}
