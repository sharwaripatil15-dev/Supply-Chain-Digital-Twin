import { forwardRef } from 'react'
import { cn } from './cn.js'

const VARIANTS = {
  primary: 'bg-accent text-accent-fg hover:bg-accent-hover',
  secondary: 'border border-border bg-surface text-fg hover:bg-surface-2 hover:border-border-strong',
  ghost: 'text-fg-2 hover:bg-surface-2 hover:text-fg',
  danger: 'text-bad hover:bg-bad/10',
}
const SIZES = {
  sm: 'h-8 px-2.5 text-xs gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-2',
  icon: 'h-8 w-8 justify-center',
}

export const Button = forwardRef(function Button(
  { variant = 'secondary', size = 'md', icon: Icon, iconRight: IconRight, className, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      className={cn(
        'inline-flex select-none items-center rounded-lg font-medium transition-colors duration-150',
        'disabled:pointer-events-none disabled:opacity-50',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {Icon && <Icon className="h-4 w-4 shrink-0" aria-hidden />}
      {children}
      {IconRight && <IconRight className="h-4 w-4 shrink-0" aria-hidden />}
    </button>
  )
})
