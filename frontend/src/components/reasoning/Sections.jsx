import { Panel } from '../ui/index.js'
import Evidence from './Evidence.jsx'

/** Narrative sections rendered from engine evidence; every section carries its own Evidence expander. */
export default function Sections({ sections, source, rejected }) {
  return (
    <div className="space-y-3">
      <p className="text-2xs text-fg-muted">
        {source === 'llm'
          ? 'Narrative worded by the LLM from the evidence; every number was checked against the engine output.'
          : 'Narrative rendered by a deterministic template from the engine evidence.'}
        {rejected ? ` An LLM draft was rejected (${rejected}).` : ''}
      </p>
      {sections.map((s) => (
        <Panel key={s.key} as="section" aria-labelledby={`sec-${s.key}`} className="space-y-2 px-4 py-3">
          <h3 id={`sec-${s.key}`} className="text-sm font-medium text-fg">
            {s.title}
          </h3>
          {s.paragraphs?.map((p, i) => (
            <p key={i} className="text-sm text-fg-2">
              {p}
            </p>
          ))}
          {s.bullets?.length > 0 && (
            <ul className="space-y-1 text-sm text-fg-2">
              {s.bullets.map((b, i) => (
                <li key={i} className="flex gap-2">
                  {b.startsWith('[ ]') ? (
                    <>
                      <input type="checkbox" className="mt-1 h-3.5 w-3.5 shrink-0" aria-label={b.slice(4)} />
                      <span>{b.slice(4)}</span>
                    </>
                  ) : (
                    <>
                      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-fg-muted" aria-hidden />
                      <span>{b}</span>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
          <Evidence data={s.evidence} />
        </Panel>
      ))}
    </div>
  )
}
