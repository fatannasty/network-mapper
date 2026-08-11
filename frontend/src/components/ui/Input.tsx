import type { InputHTMLAttributes } from 'react'

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  error?: boolean
}

export default function Input({ className = '', error, ...props }: Props) {
  return (
    <input
      className={`px-3 py-2 bg-surface-2/50 border border-border rounded-lg text-sm
        text-text-primary placeholder:text-muted
        focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/25
        transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed
        ${error ? 'border-red-500/60 focus:border-red-500 focus:ring-red-500/25' : ''}
        ${className}`}
      {...props}
    />
  )
}
