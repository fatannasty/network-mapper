import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
type Size = 'sm' | 'md' | 'lg'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  children: ReactNode
  icon?: ReactNode
}

const base = `inline-flex items-center justify-center font-medium rounded-lg
  transition-all duration-150 active:scale-[0.98] select-none
  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-1
  disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100`

const variantClasses: Record<Variant, string> = {
  primary: 'bg-accent hover:bg-accent-hover text-white shadow-sm hover:shadow-md',
  secondary: 'bg-surface-2 hover:bg-surface-3 text-text-primary border border-border shadow-sm',
  danger: 'bg-red-900/40 hover:bg-red-900/60 text-red-300 border border-red-800',
  ghost: 'text-muted hover:text-text-secondary hover:bg-surface-2',
}

const sizeClasses: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
  lg: 'px-5 py-2.5 text-sm gap-2',
}

export default function Button({ variant = 'primary', size = 'md', className = '', children, icon, ...props }: Props) {
  return (
    <button className={`${base} ${variantClasses[variant]} ${sizeClasses[size]} ${className}`} {...props}>
      {icon}
      {children}
    </button>
  )
}
