import type { Node, Edge } from '@xyflow/react'
import type { OnNodesChange, OnEdgesChange, NodeMouseHandler } from '@xyflow/react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
} from '@xyflow/react'

import SimpleNode from '../../../components/SimpleNode'
import TopologyLegend from './TopologyLegend'
import { topologyTokens } from '../../../app/theme/tokens/topology'

const nodeTypes = { device: SimpleNode }

interface Props {
  nodes: Node[]
  edges: Edge[]
  onNodesChange: OnNodesChange
  onEdgesChange: OnEdgesChange
  onNodeClick: NodeMouseHandler
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
  unknown: '#6b7280',
}

export default function TopologyCanvas({ nodes, edges, onNodesChange, onEdgesChange, onNodeClick, showLegend = true }: Props) {
  const presentTypes = [...new Set(nodes.map((n) => (n.data?.device_type as string) || 'unknown'))]
  return (
    <div className="flex-1 relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        attributionPosition="bottom-left"
      >
        <Background style={{ backgroundColor: 'rgb(var(--topo-bg))' }} color={topologyTokens.dotColor} gap={20} />
        <Controls className="!bg-surface-1 !border-border !fill-current !text-muted" />
        <MiniMap
          nodeColor={(n) => {
            const type = (n.data?.device_type as string) || 'unknown'
            return nodeColors[type] || '#6b7280'
          }}
          className="!bg-surface-1 !border-border"
        />
      </ReactFlow>
      {showLegend && <TopologyLegend presentTypes={presentTypes} />}
    </div>
  )
}
