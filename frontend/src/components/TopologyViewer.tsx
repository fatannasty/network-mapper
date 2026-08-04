import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useSearchParams } from 'react-router-dom'

import DeviceNode from './DeviceNode'
import DeviceDetail from './DeviceDetail'
import { getTopology, getDevices, type TopologyData, type Device } from '../api'

const nodeTypes = { device: DeviceNode }

function layoutNodes(nodes: { id: string }[], links: { source: string; target: string }[]) {
  const adjacency = new Map<string, string[]>()
  for (const n of nodes) adjacency.set(n.id, [])
  for (const l of links) {
    adjacency.get(l.source)?.push(l.target)
    adjacency.get(l.target)?.push(l.source)
  }

  const positions = new Map<string, { x: number; y: number }>()
  const visited = new Set<string>()
  const SPACING_X = 260
  const SPACING_Y = 220

  let col = 0

  function dfs(id: string, row: number) {
    if (visited.has(id)) return
    visited.add(id)
    positions.set(id, { x: col * SPACING_X, y: row * SPACING_Y })
    col++
    for (const neighbor of adjacency.get(id) || []) {
      if (!visited.has(neighbor)) dfs(neighbor, row + 1)
    }
  }

  for (const n of nodes) {
    if (!visited.has(n.id)) dfs(n.id, 0)
  }

  return positions
}

export default function TopologyViewer() {
  const [searchParams] = useSearchParams()
  const scanId = searchParams.get('scan_id') || undefined

  const [topology, setTopology] = useState<TopologyData | null>(null)
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null)
  const reactFlowKey = useRef(0)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [topo, devResp] = await Promise.all([
        getTopology(scanId),
        getDevices({ limit: '500' }),
      ])
      setTopology(topo)
      setDevices(devResp.devices || [])
      reactFlowKey.current++
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load topology')
    } finally {
      setLoading(false)
    }
  }, [scanId])

  useEffect(() => { fetchData() }, [fetchData])

  const { initialNodes, initialEdges } = useMemo(() => {
    if (!topology) return { initialNodes: [], initialEdges: [] }

    const positions = layoutNodes(topology.nodes, topology.links)

    const rn: Node[] = topology.nodes.map((n) => {
      const pos = positions.get(n.id) || { x: 0, y: 0 }
      return {
        id: n.id,
        type: 'device',
        position: pos,
        data: {
          id: n.id,
          ip: n.ip,
          hostname: n.hostname,
          vendor: n.vendor,
          model: n.model,
          device_type: n.device_type,
        },
      }
    })

    const re: Edge[] = topology.links.map((l, i) => {
      const srcIface = l.source_interface || ''
      const tgtIface = l.target_interface || ''
      const ifaceLabel = srcIface && tgtIface
        ? `${srcIface} → ${tgtIface}`
        : srcIface || tgtIface || ''
      const label = ifaceLabel
        ? `${ifaceLabel}\n${l.protocol.toUpperCase()}`
        : l.protocol.toUpperCase()

      return {
        id: `e-${l.source}-${l.target}-${i}`,
        source: l.source,
        target: l.target,
        label,
        labelStyle: { fill: '#9ca3af', fontSize: 9, fontWeight: 500 },
        labelBgStyle: { fill: '#1f2937', fillOpacity: 0.85 },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 4,
        style: { stroke: l.protocol === 'cdp' ? '#f59e0b' : '#3b82f6', strokeWidth: 2 },
        animated: true,
        type: 'smoothstep',
      }
    })

    return { initialNodes: rn, initialEdges: re }
  }, [topology])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  const flowRef = useRef<ReactFlowInstance | null>(null)

  useEffect(() => {
    if (initialNodes.length > 0 && flowRef.current) {
      setTimeout(() => flowRef.current?.fitView({ duration: 300, padding: 0.3 }), 50)
    }
  }, [initialNodes, reactFlowKey.current])

  const selectedDeviceData = useMemo(() => {
    if (!selectedDevice) return null
    const device = devices.find((d) => d.ip === selectedDevice)
    if (!device) return null
    const connectedLinks = (topology?.links || []).filter(
      (l) => l.source === selectedDevice || l.target === selectedDevice,
    )
    return { device, connectedLinks }
  }, [selectedDevice, devices, topology])

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400">
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-2" />
          Loading topology...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="bg-red-900/50 border border-red-800 rounded p-6 text-red-300 max-w-md text-center">
          <p className="font-semibold mb-2">Error</p>
          <p className="text-sm">{error}</p>
          <button onClick={fetchData} className="mt-4 px-4 py-1.5 bg-red-800 hover:bg-red-700 rounded text-sm transition-colors">
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (!topology || topology.nodes.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <div className="text-center">
          <p className="text-lg mb-2">No topology data</p>
          <p className="text-sm">Run a discovery scan to populate the topology graph.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex">
      <div className="flex-1">
        <ReactFlow
          key={reactFlowKey.current}
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onInit={(instance) => { flowRef.current = instance }}
          nodeTypes={nodeTypes}
          onNodeClick={(_e, node) => setSelectedDevice(node.id)}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          attributionPosition="bottom-left"
        >
          <Background color="#374151" gap={20} />
          <Controls className="!bg-gray-900 !border-gray-700 !fill-gray-400" />
          <MiniMap
            nodeColor={(n) => {
              const type = (n.data?.device_type as string) || 'unknown'
              const colors: Record<string, string> = {
                switch: '#3b82f6',
                router: '#f59e0b',
                firewall: '#ef4444',
                'core-switch': '#a855f7',
                'sd-wan': '#22c55e',
                unknown: '#6b7280',
              }
              return colors[type] || '#6b7280'
            }}
            className="!bg-gray-900 !border-gray-700"
          />
        </ReactFlow>
      </div>

      {selectedDeviceData && (
        <DeviceDetail
          device={selectedDeviceData.device}
          connectedLinks={selectedDeviceData.connectedLinks}
          onClose={() => setSelectedDevice(null)}
        />
      )}
    </div>
  )
}
