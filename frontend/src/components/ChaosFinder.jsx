import { useEffect, useMemo, useState } from 'react'
import { Play, Radar, ShieldCheck, Target, Unlink } from 'lucide-react'
import { useStore } from '../store.js'
import { fmtNum } from '../format.js'
import { targetNodes } from '../lib/disruption.js'
import { Badge, Button, Card, CardBody, CardHeader, InlineError, Meter, PageHeader, SkeletonBlock, Stat, Table, Td, Th, Tooltip, Tr, useToast } from './ui/index.js'
import GraphPanel from './GraphPanel.jsx'
import { NodeTag } from './NodeTypeIcon.jsx'

// Chaos targets are node ids or lanes ("U->V").
const outage = (target) => ({ type: target.includes('->') ? 'edge' : 'node', target, start: 2, duration: 10, severity: 1 })

export default function ChaosFinder() {
  const { chaos, network, loading, errors, loadChaos, runSimulation, setTab } = useStore()
  const toast = useToast()
  const [selected, setSelected] = useState(null) // { targets: [...], key }

  useEffect(() => {
    if (!chaos && !loading.chaos && !errors.chaos) loadChaos() // also reloads after the network changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chaos])

  const simulate = (targets) => {
    runSimulation(targets.map(outage)).then((res) => {
      if (res) toast(`Simulated ${targets.join(' + ')}`, { description: `${fmtNum(res.total_unmet)} units unmet · Survival Clock ${res.survival_clock_days} days` })
    })
    setTab('simulate')
  }
  const name = (id) => {
    if (id.includes('->')) {
      const [u, v] = id.split('->')
      return `Lane ${name(u)} → ${name(v)}`
    }
    return network?.nodes.find((n) => n.id === id)?.name || id
  }
  const maxSpof = Math.max(1, ...(chaos?.spof ?? []).map((s) => s.unmet))
  const highlight = useMemo(() => {
    if (selected) return targetNodes(selected.targets)
    return chaos ? targetNodes([...chaos.spof.map((s) => s.target), ...chaos.hidden_pairs.flatMap((p) => p.pair)]) : null
  }, [chaos, selected])
  const select = (targets) => setSelected((cur) => (cur && cur.targets.join() === targets.join() ? null : { targets, key: Date.now() }))

  return (
    <>
      <PageHeader
        title="Chaos Finder"
        description="A reverse stress test: knock out every site and lane, then every pair, and rank what hurts most."
      />
      <div className="grid gap-6 xl:grid-cols-12">
        <div className="space-y-6 xl:col-span-5">
          <Stat
            label="Resilience score"
            icon={ShieldCheck}
            loading={loading.chaos && !chaos}
            value={chaos ? chaos.resilience_score.toFixed(1) : '-'}
            unit="/ 100"
            sub="100 × (1 − mean unmet share of the 5 worst failure pairs)"
            chip={chaos && <Badge tone={chaos.resilience_score >= 70 ? 'ok' : chaos.resilience_score >= 40 ? 'warn' : 'bad'} dot>{chaos.resilience_score >= 70 ? 'Strong' : chaos.resilience_score >= 40 ? 'Moderate' : 'Fragile'}</Badge>}
          />
          <InlineError message={errors.chaos} onRetry={loadChaos} />

          <Card>
            <CardHeader title="Single points of failure" description="Units lost over a 10-day outage of each target alone" icon={Target} />
            <CardBody className="px-0 pb-2">
              {loading.chaos && !chaos ? (
                <SkeletonBlock lines={5} className="px-5" label="Stress-testing every site" />
              ) : (
                <Table label="Single points of failure">
                  <thead>
                    <tr>
                      <Th>Target</Th>
                      <Th numeric>Units lost</Th>
                      <Th className="w-24">
                        <span className="sr-only">Actions</span>
                      </Th>
                    </tr>
                  </thead>
                  <tbody>
                    {chaos && chaos.spof.length === 0 && (
                      <tr>
                        <td colSpan={3} className="px-5 py-4 text-sm text-fg-muted">
                          No single failure loses demand beyond what this network already misses.
                        </td>
                      </tr>
                    )}
                    {chaos?.spof.map((s) => (
                      <Tr key={s.target} selected={selected?.targets.join() === s.target} onClick={() => select([s.target])}>
                        <Td>
                          <NodeTag id={s.target} showName={false} />
                          <div className="text-xs text-fg-muted">{name(s.target)}</div>
                          <Meter className="mt-1.5" value={s.unmet} max={maxSpof} label={`${s.target} impact`} />
                        </Td>
                        <Td numeric>{fmtNum(s.unmet)}</Td>
                        <Td className="text-right">
                          <Button size="sm" variant="ghost" icon={Play} onClick={(e) => { e.stopPropagation(); simulate([s.target]) }}>
                            Simulate
                          </Button>
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Hidden pairs" description="Two targets that fail far worse together than apart. Select a row to locate it." icon={Unlink} />
            <CardBody className="px-0 pb-2">
              {loading.chaos && !chaos ? (
                <SkeletonBlock lines={4} className="px-5" label="Testing failure pairs" />
              ) : chaos?.hidden_pairs.length === 0 ? (
                <p className="px-5 py-4 text-sm text-fg-muted">No hidden pairs: no two failures interact badly.</p>
              ) : (
                <Table label="Hidden pairs">
                  <thead>
                    <tr>
                      <Th>Pair</Th>
                      <Th numeric>Units lost</Th>
                      <Th numeric>Synergy</Th>
                      <Th className="w-12">
                        <span className="sr-only">Actions</span>
                      </Th>
                    </tr>
                  </thead>
                  <tbody>
                    {chaos?.hidden_pairs.map((p) => {
                      const key = p.pair.join()
                      return (
                        <Tr key={key} selected={selected?.targets.join() === key} onClick={() => select(p.pair)}>
                          <Td>
                            <div className="flex flex-wrap items-center gap-1">
                              <NodeTag id={p.pair[0]} showName={false} />
                              <span className="text-fg-muted">+</span>
                              <NodeTag id={p.pair[1]} showName={false} />
                            </div>
                            <div className="max-w-[16rem] truncate text-xs text-fg-muted" title={`${name(p.pair[0])} & ${name(p.pair[1])}`}>
                              {name(p.pair[0])} & {name(p.pair[1])}
                            </div>
                          </Td>
                          <Td numeric>{fmtNum(p.unmet)}</Td>
                          <Td numeric>
                            <Badge tone="bad">+{fmtNum(p.synergy)}</Badge>
                          </Td>
                          <Td className="text-right">
                            <Tooltip content="Simulate this pair">
                              <Button
                                size="icon"
                                variant="ghost"
                                icon={Play}
                                aria-label={`Simulate ${p.pair.join(' + ')}`}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  simulate(p.pair)
                                }}
                              />
                            </Tooltip>
                          </Td>
                        </Tr>
                      )
                    })}
                  </tbody>
                </Table>
              )}
            </CardBody>
          </Card>
        </div>

        <div className="xl:col-span-7">
          <GraphPanel
            title="Where it breaks"
            description={selected ? `Selected: ${selected.targets.join(' + ')}` : 'Halo marks every target that appears in a result'}
            icon={Radar}
            heightClass="h-[640px]"
            highlight={highlight}
            view3d={{ focus: selected ? targetNodes(selected.targets) : null, focusKey: selected?.key }}
          />
        </div>
      </div>
    </>
  )
}
