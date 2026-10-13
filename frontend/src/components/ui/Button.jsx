import { forwardRef } from 'react'
import { cn } from './cn.js'
import { Tooltip } from './Tooltip.jsx'

const VARIANTS = {
  primary: 'bg-accent text-accent-fg hover:bg-accent-hover',
  secondary: 'border border-border-strong bg-surface text-fg hover:bg-raised',
  ghost: 'text-fg-2 hover:bg-raised hover:text-fg',
  danger: 'border border-border-strong bg-surface text-bad hover:border-bad/40 hover:bg-bad/5',
  'danger-solid': 'bg-bad text-surface hover:bg-bad/90',
  'ghost-danger': 'text-bad hover:bg-bad/10',
}
const SIZES = {
  xs: 'h-6 gap-1 px-2 text-xs',
  sm: 'h-7 gap-1.5 px-2.5 text-xs',
  md: 'h-8 gap-1.5 px-3 text-sm',
}
const SQUARE = { xs: 'h-6 w-6', sm: 'h-7 w-7', md: 'h-8 w-8', icon: 'h-8 w-8' }
// cn() does not resolve Tailwind conflicts, so the pressed look replaces the variant instead of overriding it.
const PRESSED = 'bg-raised text-fg hover:bg-raised'
const BASE =
  'inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap rounded-md font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-45'

/** One filled (primary) button per screen; everything else secondary (outline) or ghost. */
export const Button = forwardRef(function Button(
  { variant = 'secondary', size = 'md', icon: Icon, iconRight: IconRight, className, children, type = 'button', ...props },
  ref,
) {
  const square = !children && Icon
  return (
    <button ref={ref} type={type} className={cn(BASE, VARIANTS[variant], square ? SQUARE[size] : SIZES[size] || SIZES.md, className)} {...props}>
      {Icon && <Icon className="h-4 w-4 shrink-0" aria-hidden />}
      {children}
      {IconRight && <IconRight className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />}
    </button>
  )
})

/** Icon-only button: always labelled, with a tooltip that shows the label and an optional shortcut. */
export const IconButton = forwardRef(function IconButton(
  { icon: Icon, label, shortcut, variant = 'ghost', size = 'md', tooltipSide = 'bottom', pressed, className, ...props },
  ref,
) {
  return (
    <Tooltip content={label} shortcut={shortcut} side={tooltipSide}>
      <button
        ref={ref}
        type="button"
        aria-label={label}
        aria-pressed={pressed}
        className={cn(BASE, pressed ? PRESSED : VARIANTS[variant], SQUARE[size], className)}
        {...props}
      >
        <Icon className="h-4 w-4" aria-hidden />
      </button>
    </Tooltip>
  )
})
