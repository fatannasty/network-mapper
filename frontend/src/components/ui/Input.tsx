import type { InputHTMLAttributes } from 'react'

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  error?: boolean
}

export default function Input({ className = '', error, ...props }: Props) {
  return (
    <input
      className={`px-3.5 py-2.5 bg-surface-2/50 backdrop-blur border border-border/40 rounded-xl text-sm
        text-text-primary placeholder:text-muted/60
        focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 focus:bg-surface-2/70
        transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed
        ${error ? 'border-red-500/60 focus:border-red-500 focus:ring-red-500/20' : ''}
        ${className}`}
      {...props}
    />
  )
}
