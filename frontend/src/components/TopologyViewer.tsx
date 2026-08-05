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
import { getTopology, getDevices, type TopologyData, type Device, type TopoLink } from '../api'

const nodeTypes = { device: DeviceNode }

type ProtocolFilter = 'all' | 'lldp' | 'cdp'
type LayoutMode = 'tree' | 'free'

function freeLayout(nodes: { id: string }[], links: { source: string; target: string }[]) {
  const adjacency = new Map<string, string[]>()
  for (const n of nodes) adjacency.set(n.id, [])
  for (const l of links) {
    adjacency.get(l.source)?.push(l.target)
    adjacency.get(l.target)?.push(l.source)
  }

  const positions = new Map<string, { x: number; y: number }>()
  const visited = new Set<string>()
  const SX = 260
  const SY = 220
  let col = 0

  function dfs(id: string, row: number) {
    if (visited.has(id)) return
    visited.add(id)
    positions.set(id, { x: col * SX, y: row * SY })
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

function treeLayout(nodes: { id: string }[], links: { source: string; target: string }[]) {
  const adjacency = new Map<string, string[]>()
  for (const n of nodes) adjacency.set(n.id, [])
  for (const l of links) {
    adjacency.get(l.source)?.push(l.target)
    adjacency.get(l.target)?.push(l.source)
  }

  // Find root: node with most connections, or first node
  let root = nodes[0]?.id || ''
  let maxDeg = 0
  for (const [id, neighbors] of adjacency) {
    if (neighbors.length > maxDeg) {
      maxDeg = neighbors.length
      root = id
    }
  }

  const positions = new Map<string, { x: number; y: number }>()
  const visited = new Set<string>()
  const SX = 260
  const SY = 200

  // BFS from root, track children per level
  const levelNodes: Map<number, string[]> = new Map()
  const queue: { id: string; level: number }[] = [{ id: root, level: 0 }]
  visited.add(root)

  while (queue.length > 0) {
    const { id, level } = queue.shift()!
    const children = levelNodes.get(level) || []
    children.push(id)
    levelNodes.set(level, children)

    for (const neighbor of adjacency.get(id) || []) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor)
        queue.push({ id: neighbor, level: level + 1 })
      }
    }
  }

  // Position each level centered
  for (const [level, ids] of levelNodes) {
    const totalWidth = (ids.length - 1) * SX
    const startX = -totalWidth / 2
    ids.forEach((id, i) => {
      positions.set(id, { x: startX + i * SX, y: level * SY })
    })
  }

  // Unvisited nodes (disconnected) go below
  let row = levelNodes.size
  let col = -(nodes.length * SX) / 4
  for (const n of nodes) {
    if (!positions.has(n.id)) {
      positions.set(n.id, { x: col, y: row * SY })
      col += SX
      if (col > (nodes.length * SX) / 4) {
        col = -(nodes.length * SX) / 4
        row++
      }
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
  const [protocolFilter, setProtocolFilter] = useState<ProtocolFilter>('all')
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('tree')

  const deviceByIp = useMemo(() => {
    const map = new Map<string, Device>()
    for (const d of devices) map.set(d.ip, d)
    return map
  }, [devices])

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

  const filteredLinks: TopoLink[] = useMemo(() => {
    const all = topology?.links || []
    if (protocolFilter === 'all') return all
    return all.filter((l) => l.protocol === protocolFilter)
  }, [topology, protocolFilter])

  const { initialNodes, initialEdges } = useMemo(() => {
    if (!topology) return { initialNodes: [], initialEdges: [] }

    const layoutFn = layoutMode === 'tree' ? treeLayout : freeLayout
    const positions = layoutFn(topology.nodes, filteredLinks)

    const rn: Node[] = topology.nodes.map((n) => {
      const pos = positions.get(n.id) || { x: 0, y: 0 }
      const dev = deviceByIp.get(n.id)
      return {
        id: n.id,
        type: 'device',
        position: pos,
        data: {
          id: n.id,
          ip: n.ip,
          hostname: n.hostname || dev?.hostname || '',
          vendor: n.vendor || dev?.vendor || '',
          model: n.model || dev?.model || '',
          device_type: n.device_type || dev?.device_type || '',
        },
      }
    })

    const re: Edge[] = filteredLinks.map((l, i) => {
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
  }, [topology, filteredLinks, deviceByIp, layoutMode])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  const selectedDeviceData = useMemo(() => {
    if (!selectedDevice) return null
    const device = deviceByIp.get(selectedDevice)
    if (!device) return null
    const connectedLinks = filteredLinks.filter(
      (l) => l.source === selectedDevice || l.target === selectedDevice,
    )
    return { device, connectedLinks }
  }, [selectedDevice, deviceByIp, filteredLinks])

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

  const linkCounts = { lldp: 0, cdp: 0 }
  for (const l of topology.links) {
    if (l.protocol === 'lldp') linkCounts.lldp++
    else if (l.protocol === 'cdp') linkCounts.cdp++
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-900 border-b border-gray-800 shrink-0 text-sm">
        <span className="text-gray-500">
          {topology.nodes.length} devices
          {topology.links.length > 0 && (
            <span className="ml-2">
              &middot; {topology.links.length} links
              {linkCounts.lldp > 0 && (
                <span className="text-blue-400 ml-1">{linkCounts.lldp} LLDP</span>
              )}
              {linkCounts.cdp > 0 && (
                <span className="text-amber-400 ml-1">{linkCounts.cdp} CDP</span>
              )}
            </span>
          )}
        </span>

        <div className="flex-1" />

        <div className="flex items-center gap-1 bg-gray-800 rounded p-0.5">
          <button
            onClick={() => setLayoutMode('tree')}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
              layoutMode === 'tree' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            Tree
          </button>
          <button
            onClick={() => setLayoutMode('free')}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
              layoutMode === 'free' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            Free
          </button>
        </div>

        {topology.links.length > 0 && (
          <select
            value={protocolFilter}
            onChange={(e) => setProtocolFilter(e.target.value as ProtocolFilter)}
            className="px-3 py-1 bg-gray-800 border border-gray-700 rounded text-gray-300 text-xs focus:outline-none focus:border-blue-500"
          >
            <option value="all">All Links</option>
            <option value="lldp">LLDP Only</option>
            <option value="cdp">CDP Only</option>
          </select>
        )}

        {topology.links.length === 0 && (
          <span className="text-gray-600 text-xs">
            No auto-discovered links — run SNMP discovery on switches with LLDP/CDP enabled
          </span>
        )}
      </div>

      <div className="flex-1 flex">
        <div className="flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
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
                'access-point': '#10b981',
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
    </div>
  )
}
