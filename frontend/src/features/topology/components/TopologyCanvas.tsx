import { useState } from 'react'
import type { Node, Edge } from '@xyflow/react'
import type { OnNodesChange, OnEdgesChange, NodeMouseHandler, EdgeMouseHandler } from '@xyflow/react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
} from '@xyflow/react'

import type { Device } from '../../../api'
import SimpleNode from '../../../components/SimpleNode'
import TopologyLegend from './TopologyLegend'
import TopologyLinkTooltip from './TopologyLinkTooltip'
import { topologyTokens } from '../../../app/theme/tokens/topology'

const nodeTypes = { device: SimpleNode }

interface Props {
  nodes: Node[]
  edges: Edge[]
  onNodesChange: OnNodesChange
  onEdgesChange: OnEdgesChange
  onNodeClick: NodeMouseHandler
  deviceByIp: Map<string, Device>
  showLegend?: boolean
}

const nodeColors: Record<string, string> = {
  switch: '#3b82f6',
  router: '#f59e0b',
  firewall: '#ef4444',
  'core-switch': '#a855f7',
  'sd-wan': '#22c55e',
  'access-point': '#10b981',
  accesspoint: '#10b981',
  'velocloud-edge': '#d946ef',
  unknown: '#6b7280',
}

export default function TopologyCanvas({ nodes, edges, onNodesChange, onEdgesChange, onNodeClick, deviceByIp, showLegend = true }: Props) {
  const [hover, setHover] = useState<{ edge: Edge; x: number; y: number } | null>(null)
  const onEdgeHover: EdgeMouseHandler = (event, edge) => {
    setHover({ edge, x: event.clientX, y: event.clientY })
  }
  const onEdgeLeave: EdgeMouseHandler = () => setHover(null)

  const presentTypes = [...new Set(nodes.map((n) => (n.data?.device_type as string) || 'unknown'))]
  const smallGraph = nodes.length <= 1500
  return (
    <div className="flex-1 relative overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onEdgeMouseEnter={onEdgeHover}
        onEdgeMouseMove={onEdgeHover}
        onEdgeMouseLeave={onEdgeLeave}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        onlyRenderVisibleElements
        attributionPosition="bottom-left"
        connectionRadius={20}
        elevateEdgesOnSelect
        style={{
          background:
            'radial-gradient(1100px 720px at 12% -5%, rgb(var(--accent) / 0.10), transparent 60%),' +
            'radial-gradient(900px 640px at 100% 105%, rgb(var(--accent) / 0.07), transparent 55%),' +
            'rgb(var(--topo-bg))',
        }}
      >
        <Background color={topologyTokens.dotColor} gap={20} />
        <Controls className="!bg-surface-1 !border-border !fill-current !text-muted" />
        {smallGraph && (
          <MiniMap
            nodeColor={(n) => {
              const type = (n.data?.device_type as string) || 'unknown'
              return nodeColors[type] || '#6b7280'
            }}
            className="!bg-surface-1 !border-border"
          />
        )}
      </ReactFlow>
      {showLegend && <TopologyLegend presentTypes={presentTypes} />}
      <TopologyLinkTooltip
        edge={hover?.edge ?? null}
        deviceByIp={deviceByIp}
        x={hover?.x ?? 0}
        y={hover?.y ?? 0}
      />
    </div>
  )
}
