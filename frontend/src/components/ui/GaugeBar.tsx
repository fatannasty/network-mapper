interface Props {
  label: string
  actual: number
  target: number
}

export default function GaugeBar({ label, actual, target }: Props) {
  const pct = Math.min(actual / target, 1) * 100
  const met = actual >= target
  const barColor = met ? 'bg-green-500' : actual >= target * 0.6 ? 'bg-amber-500' : 'bg-red-500'
  const bgColor = met ? 'bg-green-900/30' : actual >= target * 0.6 ? 'bg-amber-900/30' : 'bg-red-900/30'

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted font-medium">{label}</span>
        <span className="tabular-nums">
          <span className={met ? 'text-green-400' : 'text-amber-400'}>{actual.toFixed(1)}%</span>
          <span className="text-muted"> / {target}%</span>
        </span>
      </div>
      <div className={`h-2 rounded-full ${bgColor} overflow-hidden`}>
        <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
