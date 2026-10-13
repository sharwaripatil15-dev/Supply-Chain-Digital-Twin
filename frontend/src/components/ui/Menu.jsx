import { useEffect, useId, useRef, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import { cn } from './cn.js'
import { Button, IconButton } from './Button.jsx'
import { Kbd } from './Tooltip.jsx'

/**
 * Dropdown menu with keyboard support (arrows, Home/End, Enter/Space, Escape, Tab closes).
 * items: [{ key, label, icon?, onSelect, shortcut?, danger?, disabled?, checked? (checkbox item), separator? }]
 * Trigger: a text button (label + chevron), or icon-only with `iconOnly`.
 */
export function Menu({ label, icon, iconOnly = false, items, align = 'end', side = 'bottom', variant = 'secondary', size = 'sm', className, menuClassName, triggerLabel }) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const rootRef = useRef(null)
  const itemRefs = useRef([])
  const triggerRef = useRef(null)
  const id = useId()
  const selectable = items.map((it, i) => (!it.separator && !it.disabled ? i : null)).filter((i) => i != null)

  useEffect(() => {
    if (!open) return undefined
    const onDown = (e) => !rootRef.current?.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])
  useEffect(() => {
    if (open && active >= 0) itemRefs.current[active]?.focus()
  }, [open, active])

  const openAt = (index) => {
    setOpen(true)
    setActive(index)
  }
  const close = (refocus = true) => {
    setOpen(false)
    setActive(-1)
    if (refocus) triggerRef.current?.focus()
  }
  const move = (dir) => {
    const pos = selectable.indexOf(active)
    const next = selectable[(pos + dir + selectable.length) % selectable.length]
    setActive(next)
  }
  const choose = (it) => {
    if (it.disabled) return
    it.onSelect?.()
    if (it.checked == null) close()
  }
  const onMenuKey = (e) => {
    if (e.key === 'ArrowDown') (e.preventDefault(), move(1))
    else if (e.key === 'ArrowUp') (e.preventDefault(), move(-1))
    else if (e.key === 'Home') (e.preventDefault(), setActive(selectable[0]))
    else if (e.key === 'End') (e.preventDefault(), setActive(selectable[selectable.length - 1]))
    else if (e.key === 'Escape') (e.preventDefault(), e.stopPropagation(), close())
    else if (e.key === 'Tab') close(false)
  }
  const triggerProps = {
    ref: triggerRef,
    'aria-haspopup': 'menu',
    'aria-expanded': open,
    'aria-controls': open ? id : undefined,
    onClick: () => (open ? close(false) : openAt(-1)),
    onKeyDown: (e) => {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        openAt(selectable[0])
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        openAt(selectable[selectable.length - 1])
      }
    },
  }

  return (
    <div ref={rootRef} className={cn('relative inline-flex', className)}>
      {iconOnly ? (
        <IconButton icon={icon} label={triggerLabel || label} variant={variant} size={size} {...triggerProps} />
      ) : (
        <Button icon={icon} iconRight={ChevronDown} variant={variant} size={size} {...triggerProps}>
          {label}
        </Button>
      )}
      {open && (
        <div
          id={id}
          role="menu"
          aria-label={triggerLabel || label}
          onKeyDown={onMenuKey}
          className={cn(
            'absolute z-50 min-w-[200px] animate-rise-in rounded-md border border-border bg-surface p-1 shadow-float',
            side === 'bottom' ? 'top-full mt-1' : 'bottom-full mb-1',
            align === 'end' ? 'right-0' : 'left-0',
            menuClassName,
          )}
        >
          {items.map((it, i) =>
            it.separator ? (
              <div key={it.key || `sep${i}`} role="separator" className="my-1 h-px bg-border" />
            ) : (
              <button
                key={it.key}
                ref={(el) => (itemRefs.current[i] = el)}
                type="button"
                role={it.checked == null ? 'menuitem' : 'menuitemcheckbox'}
                aria-checked={it.checked == null ? undefined : it.checked}
                aria-disabled={it.disabled || undefined}
                tabIndex={-1}
                onClick={() => choose(it)}
                onMouseEnter={() => setActive(i)}
                className={cn(
                  'flex h-8 w-full items-center gap-2 rounded-sm px-2 text-left text-sm outline-none transition-colors duration-100',
                  it.disabled ? 'cursor-not-allowed text-fg-muted opacity-60' : it.danger ? 'text-bad focus:bg-bad/10' : 'text-fg focus:bg-raised',
                )}
              >
                {it.checked != null ? (
                  <span className="flex h-4 w-4 items-center justify-center">{it.checked && <Check className="h-3.5 w-3.5" aria-hidden />}</span>
                ) : (
                  it.icon && <it.icon className="h-4 w-4 shrink-0 text-fg-muted" aria-hidden />
                )}
                <span className="flex-1 truncate">{it.label}</span>
                {it.shortcut && <Kbd>{it.shortcut}</Kbd>}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  )
}
