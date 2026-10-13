import { forwardRef } from 'react'
import { cn } from './cn.js'

const suffixPad = (suffix) => Math.ceil(String(suffix).length * 6.4) + 18

/** Text / number input. `suffix` renders a unit inside the field ("units/day"). */
export const Input = forwardRef(function Input({ className, suffix, invalid, size = 'md', style, ...props }, ref) {
  const input = (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn('control', size === 'sm' && 'control-sm', invalid && 'control-invalid', props.type === 'number' && 'num', className)}
      style={suffix ? { paddingRight: suffixPad(suffix), ...style } : style}
      {...props}
    />
  )
  if (!suffix) return input
  return (
    <span className="relative block">
      {input}
      <span className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-xs text-fg-muted">{suffix}</span>
    </span>
  )
})

export const Select = forwardRef(function Select({ className, size = 'md', invalid, children, ...props }, ref) {
  return (
    <select ref={ref} aria-invalid={invalid || undefined} className={cn('control pr-7', size === 'sm' && 'control-sm', invalid && 'control-invalid', className)} {...props}>
      {children}
    </select>
  )
})

export const Textarea = forwardRef(function Textarea({ className, invalid, ...props }, ref) {
  return <textarea ref={ref} aria-invalid={invalid || undefined} className={cn('control resize-none', invalid && 'control-invalid', className)} {...props} />
})

/** Label above the control; error (or hint) below it. */
export function Field({ label, htmlFor, hint, error, required, className, children }) {
  return (
    <div className={cn('min-w-0', className)}>
      {label && (
        <label htmlFor={htmlFor} className="mb-1 block text-xs font-medium text-fg-2">
          {label}
          {required && <span className="text-bad"> *</span>}
        </label>
      )}
      {children}
      {error ? <p className="mt-1 text-xs text-bad">{error}</p> : hint ? <p className="mt-1 text-xs text-fg-muted">{hint}</p> : null}
    </div>
  )
}

export function Checkbox({ label, className, ...props }) {
  return (
    <label className={cn('inline-flex cursor-pointer items-center gap-2 text-sm text-fg-2', className)}>
      <input type="checkbox" className="h-3.5 w-3.5 rounded-sm" {...props} />
      {label}
    </label>
  )
}
