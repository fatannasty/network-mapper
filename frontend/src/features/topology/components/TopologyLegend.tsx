import { useMemo, useState } from 'react'
import { DEVICE_TYPE_INFO, normalizeType } from '../services/friendly'

interface Props {
  presentTypes: string[]
}

const swatch: Record<string, string> = {
  switch: 'bg-sky-500',
  'core-switch': 'bg-violet-500',
  router: 'bg-amber-500',
  firewall: 'bg-red-500',
  accesspoint: 'bg-emerald-500',
  'access-point': 'bg-emerald-500',
  'sd-wan': 'bg-green-500',
  'velocloud-edge': 'bg-fuchsia-500',
  'wireless-controller': 'bg-cyan-500',
  'load-balancer': 'bg-pink-500',
  unknown: 'bg-gray-500',
}

export default function TopologyLegend({ presentTypes }: Props) {
  const [open, setOpen] = useState(true)

  const types = useMemo(() => {
    const seen = new Set<string>()
    const out: string[] = []
    for (const t of presentTypes) {
      const k = normalizeType(t)
      if (!seen.has(k)) { seen.add(k); out.push(k) }
    }
    const order = ['router', 'core-switch', 'switch', 'firewall', 'accesspoint', 'velocloud-edge', 'sd-wan', 'wireless-controller', 'load-balancer']
    out.sort((a, b) => {
      const ia = order.indexOf(a); const ib = order.indexOf(b)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    })
    return out
  }, [presentTypes])

  if (types.length === 0) return null

  return (
    <div className="absolute bottom-4 left-4 z-10 w-60 rounded-2xl border border-border/40 bg-surface-1/80 backdrop-blur-2xl shadow-lg text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-text-primary font-semibold hover:bg-surface-2/60 transition-all duration-150 rounded-t-2xl"
      >
        <span>Legend</span>
        <span className="text-muted">{open ? '\u2212' : '+'}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2 border-t border-border">
          {types.map((t) => {
            const info = DEVICE_TYPE_INFO[t] || DEVICE_TYPE_INFO.unknown
            return (
              <div key={t} className="flex gap-2 items-start">
                <span className={`mt-1 w-2.5 h-2.5 rounded-full shrink-0 ${swatch[t] || swatch.unknown}`} />
                <span className="flex flex-col min-w-0">
                  <span className="text-text-secondary font-medium">{info.label}</span>
                  <span className="text-muted leading-snug">{info.description}</span>
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
