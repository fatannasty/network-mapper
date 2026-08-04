import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useSearchParams } from 'react-router-dom'

import DeviceNode from './DeviceNode'
import DeviceDetail from './DeviceDetail'
import { getTopology, getDevices, type TopologyData, type Device } from '../api'

const nodeTypes = { device: DeviceNode }

function layoutNodes(nodes: Node[], links: { source: string; target: string }[]) {
  const positions = new Map<string, { x: number; y: number }>()
  const adjacency = new Map<string, string[]>()

  for (const n of nodes) adjacency.set(n.id, [])
  for (const l of links) {
    adjacency.get(l.source)?.push(l.target)
    adjacency.get(l.target)?.push(l.source)
  }

  const visited = new Set<string>()
  let x = 0
  const SPACING_X = 220
  const SPACING_Y = 180

  function dfs(id: string, depth: number) {
    if (visited.has(id)) return
    visited.add(id)
    const col = x++
    positions.set(id, { x: col * SPACING_X, y: depth * SPACING_Y })
    for (const neighbor of adjacency.get(id) || []) {
      if (!visited.has(neighbor)) dfs(neighbor, depth + 1)
    }
  }

  for (const n of nodes) {
    if (!visited.has(n.id)) {
      x = 0
      dfs(n.id, 0)
    }
  }

  for (const n of nodes) {
    if (!positions.has(n.id)) {
      positions.set(n.id, { x: Math.random() * 500, y: Math.random() * 500 })
    }
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load topology')
    } finally {
      setLoading(false)
    }
  }, [scanId])

  useEffect(() => { fetchData() }, [fetchData])

  const { initialNodes, initialEdges } = useMemo(() => {
    if (!topology) return { initialNodes: [], initialEdges: [] }

    const rn: Node[] = topology.nodes.map((n) => ({
      id: n.id,
      type: 'device',
      position: { x: 0, y: 0 },
      data: {
        id: n.id,
        ip: n.ip,
        hostname: n.hostname,
        vendor: n.vendor,
        model: n.model,
        device_type: n.device_type,
      },
    }))

    const positions = layoutNodes(rn, topology.links)
    for (const n of rn) {
      const p = positions.get(n.id)
      if (p) n.position = p
    }

    const re: Edge[] = topology.links.map((l, i) => ({
      id: `e-${l.source}-${l.target}-${i}`,
      source: l.source,
      target: l.target,
      label: l.protocol.toUpperCase(),
      labelStyle: { fill: '#6b7280', fontSize: 10, fontWeight: 600 },
      style: { stroke: l.protocol === 'cdp' ? '#f59e0b' : '#3b82f6', strokeWidth: 2 },
      animated: true,
      type: 'smoothstep',
    }))

    return { initialNodes: rn, initialEdges: re }
  }, [topology])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  const selectedDeviceData = useMemo(() => {
    if (!selectedDevice) return null
    return devices.find((d) => d.ip === selectedDevice) || null
  }, [selectedDevice, devices])

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
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          onNodeClick={(_e, node) => setSelectedDevice(node.id)}
          fitView
          attributionPosition="bottom-left"
        >
          <Background color="#374151" gap={20} />
          <Controls className="!bg-gray-900 !border-gray-700 !fill-gray-400" />
          <MiniMap
            nodeColor={(n) => {
              const type = (n.data?.device_type as string) || 'unknown'
              const map: Record<string, string> = {
                switch: '#3b82f6',
                router: '#f59e0b',
                firewall: '#ef4444',
                'core-switch': '#a855f7',
                'sd-wan': '#22c55e',
                unknown: '#6b7280',
              }
              return map[type] || '#6b7280'
            }}
            className="!bg-gray-900 !border-gray-700"
          />
        </ReactFlow>
      </div>

      {selectedDeviceData && (
        <DeviceDetail
          device={selectedDeviceData}
          onClose={() => setSelectedDevice(null)}
        />
      )}
    </div>
  )
}
