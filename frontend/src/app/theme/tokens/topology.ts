/** Topology-graph colour references driven by CSS variables so React Flow
    nodes, edges and backgrounds follow the active theme automatically. */
export const topologyTokens = {
  background: 'rgb(var(--topo-bg))',
  nodeFill: 'rgb(var(--topo-node-fill))',
  nodeBorder: 'rgb(var(--topo-node-border))',
  nodeSelected: 'rgb(var(--topo-node-selected))',
  edgeColor: 'rgb(var(--topo-edge))',
  edgeActive: 'rgb(var(--topo-edge-active))',
  dotColor: 'rgb(var(--topo-dot))',
} as const
