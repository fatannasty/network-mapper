import { useMemo, useState, useEffect } from 'react'
import {
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from '@xyflow/react'
import { useSearchParams } from 'react-router-dom'

import { useTopology } from './hooks/useTopology'
import { treeLayout, freeLayout } from './services/layout'
import TopologyToolbar from './components/TopologyToolbar'
import TopologyCanvas from './components/TopologyCanvas'
import DeviceDetail from '../../components/DeviceDetail'
import { shortenInterface } from '../../components/ui/iface'
import PageState from '../../components/ui/PageState'
import Button from '../../components/ui/Button'

export default function TopologyView() {
  const [searchParams] = useSearchParams()
  const scanId = searchParams.get('scan_id') || undefined

  const {
    topology,
    deviceByIp,
    loading,
    error,
    protocolFilter,
    setProtocolFilter,
    layoutMode,
    setLayoutMode,
    pathSource,
    setPathSource,
    pathTarget,
    setPathTarget,
    pathResult,
    setPathResult,
    pathEdgeIds,
    filteredLinks,
    linkCounts,
    runPath,
    fetchData,
  } = useTopology(scanId)

  const [selectedDevice, setSelectedDevice] = useState<string | null>(null)

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
      const srcIface = shortenInterface(l.source_interface || '')
      const tgtIface = shortenInterface(l.target_interface || '')
      const ifaceLabel = srcIface && tgtIface
        ? `${srcIface} \u2192 ${tgtIface}`
        : srcIface || tgtIface || ''
      const label = ifaceLabel
        ? `${ifaceLabel}\n${l.protocol.toUpperCase()}`
        : l.protocol.toUpperCase()
      const pathKey = `${l.source}->${l.target}-${i}`
      const isPath = pathEdgeIds.has(pathKey)

      return {
        id: `e-${l.source}-${l.target}-${i}`,
        source: l.source,
        target: l.target,
        label,
        labelStyle: { fill: isPath ? '#22c55e' : '#9ca3af', fontSize: 9, fontWeight: 500 },
        labelBgStyle: { fill: isPath ? '#064e3b' : '#1f2937', fillOpacity: 0.85 },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 4,
        style: {
          stroke: isPath ? '#22c55e' : l.protocol === 'cdp' ? '#f59e0b' : '#3b82f6',
          strokeWidth: isPath ? 3 : 2,
        },
        animated: true,
        type: 'smoothstep',
      }
    })

    return { initialNodes: rn, initialEdges: re }
  }, [topology, filteredLinks, deviceByIp, layoutMode, pathEdgeIds])

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
      <PageState
        type="loading"
        title="Loading topology..."
        className="h-full"
      />
    )
  }

  if (error) {
    return (
      <PageState
        type="error"
        title="Failed to load topology"
        message={error}
        className="h-full"
        action={<Button variant="danger" size="sm" onClick={fetchData}>Retry</Button>}
      />
    )
  }

  if (!topology || topology.nodes.length === 0) {
    return (
      <PageState
        type="empty"
        title="No topology data"
        message="Run a discovery scan to populate the topology graph."
        className="h-full"
      />
    )
  }

  return (
    <div className="h-full flex flex-col">
      <TopologyToolbar
        topology={topology}
        linkCounts={linkCounts}
        protocolFilter={protocolFilter}
        onProtocolFilterChange={setProtocolFilter}
        layoutMode={layoutMode}
        onLayoutModeChange={setLayoutMode}
        pathSource={pathSource}
        onPathSourceChange={setPathSource}
        pathTarget={pathTarget}
        onPathTargetChange={setPathTarget}
        pathResult={pathResult}
        onRunPath={runPath}
        onClearPath={() => setPathResult(null)}
      />

      {pathResult && (
        <div className={`px-4 py-2 border-b text-xs ${
          pathResult.error ? 'bg-red-900/30 border-red-800 text-red-300' : 'bg-green-900/30 border-green-800 text-green-300'
        }`}>
          {pathResult.error ? (
            <span>{pathResult.error}</span>
          ) : (
            <span>
              <strong>{pathResult.hops}</strong> hop{pathResult.hops !== 1 ? 's' : ''} from{' '}
              <strong>{pathResult.source}</strong> to{' '}
              <strong>{pathResult.target}</strong>
              {pathResult.path.map((h, i) => (
                <span key={i} className="ml-2 text-muted">
                  {h.source_interface && h.target_interface
                    ? `${shortenInterface(h.source_interface)} \u2192 ${shortenInterface(h.target_interface)}`
                    : `hop ${i + 1}`}
                  {i < pathResult.path.length - 1 ? ' \u2192' : ''}
                </span>
              ))}
            </span>
          )}
        </div>
      )}

      <div className="flex-1 flex">
        <TopologyCanvas
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={(_e, node) => setSelectedDevice(node.id)}
        />

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
