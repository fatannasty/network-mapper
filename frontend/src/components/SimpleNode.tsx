import { Handle, Position, type Node } from '@xyflow/react'
import type { NodeProps } from '@xyflow/react'
import { friendlyType, typeIcon, shortName } from '../features/topology/services/friendly'

export type SimpleNodeData = {
  id: string
  ip: string
  hostname: string
  device_type: string
  group?: boolean
  count?: number
  internalLinks?: number
  focus?: boolean
  status?: 'up' | 'down' | 'degraded' | 'flapping' | 'unknown'
  spof?: boolean
}

interface NodeStyle {
  border: string
  bg: string
  glow: string
  iconBg: string
  iconText: string
  bar: string
}

const nodeStyle: Record<string, NodeStyle> = {
  switch: { border: 'border-sky-400/70', bg: 'bg-gradient-to-br from-sky-500/30 via-sky-500/10 to-sky-500/5', glow: 'shadow-sky-500/30', iconBg: 'bg-sky-500/25', iconText: 'text-sky-200', bar: 'bg-sky-400' },
  'core-switch': { border: 'border-violet-400/70', bg: 'bg-gradient-to-br from-violet-500/30 via-violet-500/10 to-violet-500/5', glow: 'shadow-violet-500/30', iconBg: 'bg-violet-500/25', iconText: 'text-violet-200', bar: 'bg-violet-400' },
  router: { border: 'border-amber-400/70', bg: 'bg-gradient-to-br from-amber-500/30 via-amber-500/10 to-amber-500/5', glow: 'shadow-amber-500/30', iconBg: 'bg-amber-500/25', iconText: 'text-amber-200', bar: 'bg-amber-400' },
  firewall: { border: 'border-red-400/70', bg: 'bg-gradient-to-br from-red-500/30 via-red-500/10 to-red-500/5', glow: 'shadow-red-500/30', iconBg: 'bg-red-500/25', iconText: 'text-red-200', bar: 'bg-red-400' },
  accesspoint: { border: 'border-emerald-400/70', bg: 'bg-gradient-to-br from-emerald-500/30 via-emerald-500/10 to-emerald-500/5', glow: 'shadow-emerald-500/30', iconBg: 'bg-emerald-500/25', iconText: 'text-emerald-200', bar: 'bg-emerald-400' },
  'access-point': { border: 'border-emerald-400/70', bg: 'bg-gradient-to-br from-emerald-500/30 via-emerald-500/10 to-emerald-500/5', glow: 'shadow-emerald-500/30', iconBg: 'bg-emerald-500/25', iconText: 'text-emerald-200', bar: 'bg-emerald-400' },
  'sd-wan': { border: 'border-green-400/70', bg: 'bg-gradient-to-br from-green-500/30 via-green-500/10 to-green-500/5', glow: 'shadow-green-500/30', iconBg: 'bg-green-500/25', iconText: 'text-green-200', bar: 'bg-green-400' },
  'velocloud-edge': { border: 'border-teal-400/70', bg: 'bg-gradient-to-br from-teal-500/30 via-teal-500/10 to-teal-500/5', glow: 'shadow-teal-500/30', iconBg: 'bg-teal-500/25', iconText: 'text-teal-200', bar: 'bg-teal-400' },
  'wireless-controller': { border: 'border-cyan-400/70', bg: 'bg-gradient-to-br from-cyan-500/30 via-cyan-500/10 to-cyan-500/5', glow: 'shadow-cyan-500/30', iconBg: 'bg-cyan-500/25', iconText: 'text-cyan-200', bar: 'bg-cyan-400' },
  'load-balancer': { border: 'border-pink-400/70', bg: 'bg-gradient-to-br from-pink-500/30 via-pink-500/10 to-pink-500/5', glow: 'shadow-pink-500/30', iconBg: 'bg-pink-500/25', iconText: 'text-pink-200', bar: 'bg-pink-400' },
  unknown: { border: 'border-gray-500/60', bg: 'bg-gradient-to-br from-gray-500/25 via-gray-500/10 to-gray-500/5', glow: 'shadow-gray-500/15', iconBg: 'bg-gray-500/20', iconText: 'text-gray-200', bar: 'bg-gray-400' },
}

// State glyphs differ (not just color) so the status is readable for colorblind users.
const statusConfig: Record<string, { bg: string; text: string; label: string; dot: string; pulse?: boolean }> = {
  up: { bg: 'bg-green-500', text: 'text-white', label: 'Up', dot: '●' },
  down: { bg: 'bg-red-500', text: 'text-white', label: 'Down', dot: '▼' },
  degraded: { bg: 'bg-amber-500', text: 'text-black', label: 'Degraded', dot: '◐' },
  flapping: { bg: 'bg-orange-500', text: 'text-black', label: 'Flapping', dot: '◍', pulse: true },
  unknown: { bg: 'bg-gray-500', text: 'text-white', label: 'Unknown', dot: '○' },
}

export default function SimpleNode({ data }: NodeProps<Node<SimpleNodeData>>) {
  const d = data as unknown as SimpleNodeData
  const type = d.device_type || 'unknown'
  const s = nodeStyle[type] || nodeStyle.unknown
  const icons = typeIcon(type)
  const name = shortName(d.hostname) || d.ip || d.id
  const status = statusConfig[d.status || 'unknown']

  return (
    <div
      className={`group relative flex items-center gap-4 pl-5 pr-5 py-3.5 rounded-2xl border-2 ${s.border} ${s.bg} ${s.glow}
        shadow-xl backdrop-blur-xl text-white cursor-pointer select-none
        transition-all duration-200 hover:-translate-y-1 hover:scale-[1.03] hover:shadow-2xl hover:border-white/40
        ${d.focus ? 'ring-2 ring-white ring-offset-2 ring-offset-black/40' : ''}`}
    >
      {/* Accent bar */}
      <span className={`absolute left-0 top-3 bottom-3 w-1.5 rounded-full ${s.bar} opacity-90`} />

      {/* Operational status badge */}
      <span
        className={`absolute -top-1.5 -right-1.5 flex items-center justify-center w-5 h-5 rounded-full border border-black/40 text-[11px] leading-none ${status.bg} ${status.text} ${status.pulse ? 'animate-pulse motion-safe:animate-pulse' : ''}`}
        role="img"
        aria-label={`Status: ${d.status || 'unknown'}`}
        title={status.label}
      >
        {status.dot}
      </span>

      {/* Single point of failure badge */}
      {d.spof && (
        <span
          className="absolute -top-1.5 -left-1.5 flex items-center justify-center w-5 h-5 rounded-full bg-amber-500 text-black border border-black/40 text-[11px] leading-none"
          role="img"
          aria-label="Single point of failure"
          title="Single point of failure — removing this device partitions the network"
        >
          ⚠
        </span>
      )}

      <Handle id="target" type="target" position={Position.Left} className="!bg-gray-500 !w-2.5 !h-2.5" />
      <Handle id="source" type="source" position={Position.Right} className="!bg-gray-500 !w-2.5 !h-2.5" />

      <span className={`w-14 h-14 shrink-0 rounded-2xl flex items-center justify-center ring-1 ring-white/20 shadow-inner ${s.iconBg} ${s.iconText}`}>
        <svg className="w-7 h-7 drop-shadow" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
          {icons.map((d2, i) => <path key={i} d={d2} />)}
        </svg>
      </span>

      <span className="flex flex-col min-w-0 leading-tight">
        <span className="font-semibold text-base truncate max-w-[210px]">{name}</span>
        <span className="text-xs text-white/65 mt-0.5">{friendlyType(type)}</span>
        {d.group && (
          <span className="text-xs text-white/85 mt-1 font-semibold">
            {d.count ?? 0} {d.count === 1 ? 'device' : 'devices'}
            {d.internalLinks ? ` \u00b7 ${d.internalLinks} link${d.internalLinks === 1 ? '' : 's'}` : ''}
          </span>
        )}
      </span>
    </div>
  )
}
