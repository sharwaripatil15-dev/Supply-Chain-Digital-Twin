import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { cn } from './cn.js'
import { Button, IconButton } from './Button.jsx'

const FOCUSABLE = 'button:not([disabled]),[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

/** Move focus in on open, keep Tab inside, close on Escape, restore focus on close. */
export function useFocusTrap(ref, open, onEscape, { focusContainer = false } = {}) {
  const escRef = useRef(onEscape)
  escRef.current = onEscape
  useEffect(() => {
    if (!open) return undefined
    const el = ref.current
    if (!el) return undefined
    const prev = document.activeElement
    const items = () => [...el.querySelectorAll(FOCUSABLE)].filter((x) => x.offsetParent !== null)
    ;(focusContainer ? el : el.querySelector('[data-autofocus]') || items()[0] || el).focus()
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        escRef.current?.()
      } else if (e.key === 'Tab') {
        const f = items()
        if (!f.length) return
        if (e.shiftKey && document.activeElement === f[0]) {
          e.preventDefault()
          f[f.length - 1].focus()
        } else if (!e.shiftKey && document.activeElement === f[f.length - 1]) {
          e.preventDefault()
          f[0].focus()
        }
      }
    }
    el.addEventListener('keydown', onKey)
    return () => {
      el.removeEventListener('keydown', onKey)
      if (prev && document.contains(prev)) prev.focus?.()
    }
  }, [open, ref])
}

/** Modal dialog. */
export function Dialog({ open, onClose, title, description, children, footer, className, position = 'center', labelledBy }) {
  const ref = useRef(null)
  useFocusTrap(ref, open, onClose)
  if (!open) return null
  return (
    <div className={cn('fixed inset-0 z-50 flex justify-center p-4', position === 'top' ? 'items-start pt-[12vh]' : 'items-center')}>
      <div className="absolute inset-0 animate-fade-in bg-fg/25 dark:bg-bg/70" onClick={onClose} aria-hidden />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={labelledBy ? undefined : title}
        aria-labelledby={labelledBy}
        tabIndex={-1}
        className={cn('relative w-full max-w-md animate-rise-in rounded-lg border border-border bg-surface shadow-float outline-none', className)}
      >
        {title && (
          <div className="px-5 pt-4">
            <h2 className="text-base font-medium text-fg">{title}</h2>
            {description && <p className="mt-1 text-sm text-fg-2">{description}</p>}
          </div>
        )}
        {children}
        {footer && <div className="flex justify-end gap-2 px-5 pb-4 pt-2">{footer}</div>}
      </div>
    </div>
  )
}

/** Destructive confirmation. Focus starts on Cancel. */
export function ConfirmDialog({ open, title, children, confirmLabel = 'Confirm', tone = 'danger', busy = false, onConfirm, onCancel }) {
  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : onCancel}
      title={title}
      footer={
        <>
          <Button onClick={onCancel} disabled={busy} data-autofocus>
            Cancel
          </Button>
          <Button variant={tone === 'danger' ? 'danger-solid' : 'primary'} onClick={onConfirm} disabled={busy}>
            {busy ? 'Working…' : confirmLabel}
          </Button>
        </>
      }
    >
      <div className="px-5 py-3 text-sm text-fg-2">{children}</div>
    </Dialog>
  )
}

/** Right-side overlay drawer (used for the inspector on narrow screens). */
export function Drawer({ open, onClose, title, children, className, width = 'w-[360px]', showClose = true }) {
  const ref = useRef(null)
  useFocusTrap(ref, open, onClose, { focusContainer: true }) // focus the panel itself, so no button tooltip pops up
  if (!open) return null
  return (
    <aside
      ref={ref}
      tabIndex={-1}
      role="dialog"
      aria-label={typeof title === 'string' ? title : 'Details'}
      className={cn('fixed bottom-0 right-0 top-12 z-40 flex max-w-full animate-slide-in flex-col border-l border-border bg-surface shadow-float outline-none', width, className)}
    >
      {showClose && (
        <div className="absolute right-2 top-2.5 z-10">
          <IconButton icon={X} label="Close" shortcut="Esc" size="sm" onClick={onClose} tooltipSide="left" />
        </div>
      )}
      {children}
    </aside>
  )
}
