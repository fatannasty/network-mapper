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
}

const nodeColor: Record<string, string> = {
  switch: 'border-sky-400 bg-sky-950',
  'core-switch': 'border-violet-400 bg-violet-950',
  router: 'border-amber-400 bg-amber-950',
  firewall: 'border-red-400 bg-red-950',
  accesspoint: 'border-emerald-400 bg-emerald-950',
  'access-point': 'border-emerald-400 bg-emerald-950',
  'sd-wan': 'border-green-400 bg-green-950',
  'velocloud-edge': 'border-teal-400 bg-teal-950',
  'wireless-controller': 'border-cyan-400 bg-cyan-950',
  'load-balancer': 'border-pink-400 bg-pink-950',
  unknown: 'border-gray-500 bg-gray-800',
}

const iconBg: Record<string, string> = {
  switch: 'bg-sky-500/20 text-sky-300',
  'core-switch': 'bg-violet-500/20 text-violet-300',
  router: 'bg-amber-500/20 text-amber-300',
  firewall: 'bg-red-500/20 text-red-300',
  accesspoint: 'bg-emerald-500/20 text-emerald-300',
  'access-point': 'bg-emerald-500/20 text-emerald-300',
  'sd-wan': 'bg-green-500/20 text-green-300',
  'velocloud-edge': 'bg-teal-500/20 text-teal-300',
  'wireless-controller': 'bg-cyan-500/20 text-cyan-300',
  'load-balancer': 'bg-pink-500/20 text-pink-300',
  unknown: 'bg-gray-500/20 text-gray-300',
}

export default function SimpleNode({ data }: NodeProps<Node<SimpleNodeData>>) {
  const d = data as unknown as SimpleNodeData
  const type = d.device_type || 'unknown'
  const icons = typeIcon(type)
  const name = shortName(d.hostname) || d.ip || d.id

  return (
    <div
      className={`flex items-center gap-2.5 px-3 py-2 rounded-xl border-2 ${nodeColor[type] || nodeColor.unknown}
        text-white shadow-lg cursor-pointer select-none`}
    >
      <Handle id="target" type="target" position={Position.Left} className="!bg-gray-500" />
      <Handle id="source" type="source" position={Position.Right} className="!bg-gray-500" />

      <span className={`w-9 h-9 shrink-0 rounded-lg flex items-center justify-center ${iconBg[type] || iconBg.unknown}`}>
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
          {icons.map((d2, i) => <path key={i} d={d2} />)}
        </svg>
      </span>

      <span className="flex flex-col min-w-0 leading-tight">
        <span className="font-semibold text-sm truncate max-w-[170px]">{name}</span>
        <span className="text-[11px] text-white/70">{friendlyType(type)}</span>
        {d.group && (
          <span className="text-[11px] text-white/85 mt-0.5">
            {d.count ?? 0} {d.count === 1 ? 'device' : 'devices'}
            {d.internalLinks ? ` \u00b7 ${d.internalLinks} link${d.internalLinks === 1 ? '' : 's'}` : ''}
          </span>
        )}
      </span>
    </div>
  )
}
