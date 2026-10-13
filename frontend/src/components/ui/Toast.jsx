import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { cn } from './cn.js'

const ToastContext = createContext(null)
const DOT = { success: 'bg-ok', error: 'bg-bad', info: 'bg-accent' }

/** Small, dismissible toasts, bottom-right. Announced politely; auto-dismiss after 4 s. */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const nextId = useRef(1)
  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), [])
  const toast = useCallback(
    (title, { tone = 'success', description } = {}) => {
      const id = nextId.current++
      setToasts((t) => [...t.slice(-2), { id, title, tone, description }])
      setTimeout(() => dismiss(id), 4000)
    },
    [dismiss],
  )
  const value = useMemo(() => ({ toast }), [toast])
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className="pointer-events-auto flex animate-rise-in items-start gap-2.5 rounded-lg border border-border bg-surface px-3 py-2.5 shadow-float"
          >
            <span className={cn('mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full', DOT[t.tone] || DOT.info)} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-fg">{t.title}</p>
              {t.description && <p className="mt-0.5 text-xs text-fg-muted">{t.description}</p>}
            </div>
            <button type="button" onClick={() => dismiss(t.id)} className="-mr-1 rounded-sm p-0.5 text-fg-muted hover:text-fg" aria-label="Dismiss notification">
              <X className="h-3.5 w-3.5" aria-hidden />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx.toast
}
