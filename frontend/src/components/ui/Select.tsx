import type { SelectHTMLAttributes, ReactNode } from 'react'

interface Props extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  children: ReactNode
  error?: boolean
}

export default function Select({ className = '', children, error, ...props }: Props) {
  return (
    <select
      className={`px-3 py-2 bg-surface-2/40 border border-border/50 rounded-lg text-sm
        text-text-primary focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20
        transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed
        ${error ? 'border-red-500/60 focus:border-red-500 focus:ring-red-500/20' : ''}
        ${className}`}
      {...props}
    >
      {children}
    </select>
  )
}
