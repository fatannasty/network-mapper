import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  padding?: boolean
}

export default function Card({ children, className = '', padding = true }: CardProps) {
  return (
    <div className={`bg-surface-1 border border-border rounded-xl shadow-card ${padding ? 'p-5' : ''} ${className}`}>
      {children}
    </div>
  )
}

interface CardHeaderProps {
  title: string
  subtitle?: string
  children?: ReactNode
}

export function CardHeader({ title, subtitle, children }: CardHeaderProps) {
  return (
    <div className="flex items-center justify-between gap-3 mb-4">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-text-primary tracking-wide uppercase">{title}</h3>
        {subtitle && <p className="text-xs text-muted mt-0.5 truncate">{subtitle}</p>}
      </div>
      {children && <div className="flex items-center gap-2 shrink-0">{children}</div>}
    </div>
  )
}
