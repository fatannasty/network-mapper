import { useEffect, useRef } from 'react'
import cytoscape, { type ElementDefinition } from 'cytoscape'
import type { TopoNode, TopoLink } from '../../../api'
import { treeLayout, freeLayout, circleLayout, radialLayout } from '../services/layout'
import type { LayoutMode } from '../hooks/useTopology'

const TYPE_COLORS: Record<string, string> = {
  switch: '#3b82f6',
  router: '#f59e0b',
  firewall: '#ef4444',
  'core-switch': '#a855f7',
  'sd-wan': '#22c55e',
  'access-point': '#10b981',
  accesspoint: '#10b981',
  unknown: '#6b7280',
}

const STATUS_BORDER: Record<string, string> = {
  up: '#22c55e',
  down: '#ef4444',
  degraded: '#f59e0b',
  flapping: '#f97316',
  unknown: '#64748b',
}

const PROTOCOL_COLOR: Record<string, string> = {
  catalyst: '#38bdf8',
  'cdp-lldp': '#60a5fa',
  lldp: '#60a5fa',
  cdp: '#f59e0b',
  poe: '#22d3ee',
}

interface Props {
  nodes: TopoNode[]
  links: TopoLink[]
  layoutMode: LayoutMode
  onNodeSelect: (id: string) => void
}

export default function CanvasTopology({ nodes, links, layoutMode, onNodeSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const onSelectRef = useRef(onNodeSelect)
  onSelectRef.current = onNodeSelect

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const layoutFn = layoutMode === 'tree' ? treeLayout
      : layoutMode === 'circle' ? circleLayout
      : layoutMode === 'radial' ? radialLayout
      : freeLayout
    const positions = layoutFn(
      nodes as { id: string }[],
      links as { source: string; target: string }[],
    )

    const elements: ElementDefinition[] = [
      ...nodes.map((n) => {
        const status = n.status || 'unknown'
        return {
          data: {
            id: n.id,
            label: (n.hostname || n.ip || n.id).split('.')[0],
            color: TYPE_COLORS[n.device_type || 'unknown'] || TYPE_COLORS.unknown,
            border: !!n.spof ? '#fbbf24' : n.vlan_90 === true ? '#2dd4bf' : (STATUS_BORDER[status] || STATUS_BORDER.unknown),
          },
          position: positions.get(n.id) || { x: 0, y: 0 },
        }
      }),
      ...links.map((l, i) => ({
        data: {
          id: `e-${i}`,
          source: l.source,
          target: l.target,
          color: PROTOCOL_COLOR[l.protocol || ''] || '#60a5fa',
          down: l.status === 'down',
        },
      })),
    ]

    const style: cytoscape.StylesheetStyle[] = [
      {
        selector: 'node',
        style: {
          'background-color': 'data(color)',
          'background-opacity': 0.92,
          'border-width': 3,
          'border-color': 'data(border)',
          width: 150,
          height: 80,
          shape: 'round-rectangle',
          'label': 'data(label)',
          'font-size': 12,
          'font-weight': 600,
          'min-zoomed-font-size': 10,
          'text-valign': 'center',
          'text-halign': 'center',
          'text-wrap': 'wrap',
          'text-max-width': '140px',
          'color': '#ffffff',
          'text-outline-width': 2,
          'text-outline-color': '#0b1220',
          'text-outline-opacity': 0.85,
        },
      },
      {
        selector: 'edge',
        style: {
          width: 1.5,
          'line-color': 'data(color)',
          'curve-style': 'haystack',
          'haystack-radius': 0.5,
          opacity: 0.55,
        },
      },
      {
        selector: 'edge[?down]',
        style: {
          'line-style': 'dashed',
          'line-color': '#ef4444',
          opacity: 0.7,
        },
      },
    ]

    const cy = cytoscape({
      container,
      elements,
      style,
      layout: { name: 'preset' },
      minZoom: 0.005,
      maxZoom: 6,
      wheelSensitivity: 0.2,
      boxSelectionEnabled: true,
      autoungrabify: false,
      textureOnViewport: true,
      motionBlur: true,
      hideEdgesOnViewport: true,
    })

    cy.on('tap', 'node', (evt) => {
      onSelectRef.current(evt.target.id())
    })

    // Level-of-detail: hide node labels until zoomed in enough to read them,
    // so the overview stays clean instead of a wall of overlapping text.
    const updateLod = () => {
      const z = cy.zoom()
      cy.style()
        .selector('node')
        .style('label', z >= 0.2 ? 'data(label)' : '')
        .update()
    }
    cy.on('zoom', updateLod)

    try {
      cy.fit(undefined, 48)
    } catch {
      /* empty graph */
    }
    updateLod()
    cyRef.current = cy

    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [nodes, links, layoutMode])

  return <div ref={containerRef} className="w-full h-full" />
}