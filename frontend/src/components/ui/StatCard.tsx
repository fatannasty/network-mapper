import type { ReactNode } from 'react'

interface Props {
  label: string
  value: ReactNode
  sub?: string
  accent?: 'default' | 'green' | 'amber' | 'red' | 'blue'
}

const accentColors: Record<string, string> = {
  default: 'border-border/30',
  green: 'border-l-green-500',
  amber: 'border-l-amber-500',
  red: 'border-l-red-500',
  blue: 'border-l-blue-500',
}

export default function StatCard({ label, value, sub, accent = 'default' }: Props) {
  return (
    <div className={`bg-surface-1/80 backdrop-blur-xl border border-border/40 border-l-4 ${accentColors[accent]} rounded-2xl p-4 transition-all duration-200 hover:shadow-lg hover:border-border/60 hover:-translate-y-px`}>
      <div className="text-xs font-medium text-muted uppercase tracking-wider mb-1">{label}</div>
      <div className="text-2xl font-bold text-text-primary tabular-nums">{value}</div>
      {sub && <div className="text-xs text-muted mt-1">{sub}</div>}
    </div>
  )
}
