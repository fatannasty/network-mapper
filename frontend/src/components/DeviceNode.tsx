import { Handle, Position, type Node } from '@xyflow/react'
import type { NodeProps } from '@xyflow/react'

type DeviceData = {
  id: string
  ip: string
  hostname: string
  vendor: string
  model: string
  device_type: string
}

const colors: Record<string, string> = {
  switch: 'border-blue-400 bg-blue-950',
  router: 'border-amber-400 bg-amber-950',
  firewall: 'border-red-400 bg-red-950',
  'core-switch': 'border-purple-400 bg-purple-950',
  'sd-wan': 'border-green-400 bg-green-950',
  'wireless-controller': 'border-cyan-400 bg-cyan-950',
  'access-point': 'border-emerald-400 bg-emerald-950',
  'load-balancer': 'border-pink-400 bg-pink-950',
  unknown: 'border-gray-500 bg-gray-900',
}

export default function DeviceNode({ data }: NodeProps<Node<DeviceData>>) {
  const deviceData = data as unknown as DeviceData
  const color = colors[deviceData.device_type] || colors.unknown
  const label = deviceData.hostname || deviceData.ip || deviceData.id

  return (
    <div className={`px-3 py-2 rounded-lg border-2 ${color} text-white text-sm min-w-[160px] cursor-pointer shadow-lg`}>
      <Handle type="target" position={Position.Top} className="!bg-gray-500" />
      <div className="font-semibold truncate max-w-[200px]">{label}</div>
      {deviceData.ip && deviceData.ip !== label && (
        <div className="text-blue-400 text-[11px] font-mono mt-0.5">{deviceData.ip}</div>
      )}
      <div className="text-gray-400 text-xs mt-0.5">
        {deviceData.vendor && <span>{deviceData.vendor}</span>}
        {deviceData.model && <span> {deviceData.model}</span>}
      </div>
      {deviceData.device_type && deviceData.device_type !== 'unknown' && (
        <span className="inline-block mt-1 px-1.5 py-0.5 rounded text-[10px] font-medium uppercase bg-white/10 text-gray-300">
          {deviceData.device_type}
        </span>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-gray-500" />
    </div>
  )
}
