import { useEffect, useState } from 'react'
import { Dices, Download } from 'lucide-react'
import { api, errorMessage } from '../api.js'
import { useStore } from '../store.js'
import { Button, Field, InlineError, Input, Panel, PanelHeader, SectionLabel, Select, useToast } from './ui/index.js'

/**
 * Ready-made demo networks and the random network generator. Both load through the Manual Builder import path
 * (POST /network/import?activate=true), so the result is an ordinary, editable manual network.
 */
export default function SyntheticNetworks({ onLoaded }) {
  const { importManual, loading } = useStore()
  const toast = useToast()
  const [opts, setOpts] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)
  const [form, setForm] = useState({ archetype: 'multi_source', industry: 'fmcg', n_nodes: 24, seed: '' })

  useEffect(() => {
    api.networkDemos().then(setOpts).catch((err) => setError(errorMessage(err)))
  }, [])

  const load = async (key, fetcher, what) => {
    setBusy(key)
    setError(null)
    try {
      const net = await fetcher()
      const res = await importManual(net, true)
      if (res.ok) {
        toast(`${what} is active`, { description: `${net.meta?.n_nodes ?? net.nodes.length} nodes · ${net.meta?.n_edges ?? net.edges.length} lanes, editable in the builder` })
        onLoaded?.()
      } else setError(res.error)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  const generate = () => {
    const body = { archetype: form.archetype, industry: form.industry, n_nodes: Number(form.n_nodes) || 24 }
    if (form.seed !== '') body.seed = Number(form.seed)
    load('generate', () => api.generateNetwork(body), 'Generated network')
  }
  const disabled = Boolean(busy) || loading.builder

  return (
    <Panel className="max-w-4xl">
      <PanelHeader title="Demo and synthetic networks" meta="Loaded through the Manual Builder" />
      <div className="space-y-5 px-4 py-3">
        <section>
          <SectionLabel className="mb-2">Ready-made demos</SectionLabel>
          <ul className="grid gap-2 md:grid-cols-3">
            {(opts?.demos ?? []).map((d) => (
              <li key={d.id} className="flex flex-col gap-2 rounded-md border border-border p-3">
                <div className="text-sm font-medium text-fg">{d.label}</div>
                <p className="flex-1 text-xs text-fg-2">{d.blurb}</p>
                <div className="flex items-center justify-between gap-2">
                  <span className="num text-2xs text-fg-muted">{d.n_nodes} nodes</span>
                  <Button size="sm" icon={Download} disabled={disabled} onClick={() => load(d.id, () => api.networkDemo(d.id), d.label)}>
                    {busy === d.id ? 'Loading…' : 'Load'}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <SectionLabel className="mb-2">Generate random network</SectionLabel>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1.4fr_1.2fr_0.7fr_0.7fr_auto] lg:items-end">
            <Field label="Archetype" htmlFor="gen-arch">
              <Select id="gen-arch" size="sm" value={form.archetype} onChange={(e) => setForm({ ...form, archetype: e.target.value })}>
                {(opts?.archetypes ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Industry" htmlFor="gen-ind">
              <Select id="gen-ind" size="sm" value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })}>
                {(opts?.industries ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Size" htmlFor="gen-size" hint="10-60 nodes">
              <Input id="gen-size" size="sm" type="number" min={10} max={60} value={form.n_nodes} onChange={(e) => setForm({ ...form, n_nodes: e.target.value })} />
            </Field>
            <Field label="Seed" htmlFor="gen-seed" hint="blank = random">
              <Input id="gen-seed" size="sm" type="number" min={0} value={form.seed} onChange={(e) => setForm({ ...form, seed: e.target.value })} />
            </Field>
            <Button variant="primary" icon={Dices} disabled={disabled || !opts} onClick={generate} className="lg:mb-5">
              {busy === 'generate' ? 'Generating…' : 'Generate'}
            </Button>
          </div>
          <p className="mt-2 text-xs text-fg-muted">
            Seeded generator with Indian cities, mode-based lead times, 55-85% baseline utilisation and industry stock cover. Loading replaces the
            manual network and makes it active.
          </p>
        </section>
        <InlineError message={error} />
      </div>
    </Panel>
  )
}
