import { MOD_LABEL, useUi } from '../../ui.jsx'
import { Button, Dialog, Kbd } from '../ui/index.js'

const GROUPS = [
  ['Navigation', [['Command palette', `${MOD_LABEL} K`], ['Twin · Simulate · Chaos · Recover · Data', '1 – 5'], ['Pin or unpin the sidebar', '['], ['Show or hide the inspector', 'I']]],
  ['Canvas', [['Fit the network in view', 'F'], ['Clear the selection / stop a replay', 'Esc'], ['Play or pause the timeline (Simulate)', 'Space']]],
  ['Network builder', [['Undo', `${MOD_LABEL} Z`], ['Redo', `${MOD_LABEL} ⇧ Z`]]],
]

export default function ShortcutsDialog() {
  const { shortcutsOpen, setShortcutsOpen } = useUi()
  const close = () => setShortcutsOpen(false)
  return (
    <Dialog open={shortcutsOpen} onClose={close} title="Keyboard shortcuts" className="max-w-lg" footer={<Button onClick={close}>Close</Button>}>
      <div className="space-y-4 px-5 py-3">
        {GROUPS.map(([group, rows]) => (
          <section key={group}>
            <h3 className="section-label mb-1.5">{group}</h3>
            <dl className="divide-y divide-border rounded-md border border-border">
              {rows.map(([label, keys]) => (
                <div key={label} className="flex items-center justify-between gap-4 px-3 py-1.5 text-sm">
                  <dt className="text-fg-2">{label}</dt>
                  <dd>
                    <Kbd>{keys}</Kbd>
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </Dialog>
  )
}
