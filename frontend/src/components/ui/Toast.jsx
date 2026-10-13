import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react'
import { cn } from './cn.js'

const ToastContext = createContext(null)
const ICONS = { success: CheckCircle2, error: AlertCircle, info: Info }
const TONE = { success: 'text-ok', error: 'text-bad', info: 'text-accent' }

/** Lightweight toasts for completed actions. Announced politely; auto-dismiss after 4 s. */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const nextId = useRef(1)
  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), [])
  const toast = useCallback(
    (title, { tone = 'success', description } = {}) => {
      const id = nextId.current++
      setToasts((t) => [...t.slice(-3), { id, title, tone, description }])
      setTimeout(() => dismiss(id), 4000)
    },
    [dismiss],
  )
  const value = useMemo(() => ({ toast }), [toast])
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {toasts.map((t) => {
          const Icon = ICONS[t.tone]
          return (
            <div
              key={t.id}
              role="status"
              className="pointer-events-auto flex animate-slide-in items-start gap-2.5 rounded-card border border-border bg-surface p-3 shadow-card"
            >
              <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', TONE[t.tone])} aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-fg">{t.title}</p>
                {t.description && <p className="mt-0.5 text-xs text-fg-muted">{t.description}</p>}
              </div>
              <button type="button" onClick={() => dismiss(t.id)} className="text-fg-muted hover:text-fg" aria-label="Dismiss notification">
                <X className="h-4 w-4" aria-hidden />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx.toast
}
