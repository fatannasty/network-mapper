import type { ReactNode } from 'react'

interface Props {
  label: string
  value: ReactNode
  sub?: string
  accent?: 'default' | 'green' | 'amber' | 'red' | 'blue'
}

const accentColors: Record<string, string> = {
  default: 'border-border',
  green: 'border-l-green-500',
  amber: 'border-l-amber-500',
  red: 'border-l-red-500',
  blue: 'border-l-accent',
}

export default function StatCard({ label, value, sub, accent = 'default' }: Props) {
  return (
    <div className={`bg-surface-2 border border-border border-l-4 ${accentColors[accent]} rounded-xl p-4`}>
      <div className="text-xs font-medium text-muted uppercase tracking-wider mb-1">{label}</div>
      <div className="text-2xl font-bold text-text-primary tabular-nums">{value}</div>
      {sub && <div className="text-xs text-muted mt-1">{sub}</div>}
    </div>
  )
}
