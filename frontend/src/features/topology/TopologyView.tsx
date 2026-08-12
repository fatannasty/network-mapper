import { useMemo, useState, useEffect } from 'react'
import {
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from '@xyflow/react'
import { useSearchParams } from 'react-router-dom'

import { useTopology } from './hooks/useTopology'
import { treeLayout, freeLayout, circleLayout, radialLayout } from './services/layout'
import { normalizeType, pluralLabel } from './services/friendly'
import TopologyToolbar from './components/TopologyToolbar'
import TopologyCanvas from './components/TopologyCanvas'
import TopologyGroupDetail from './components/TopologyGroupDetail'
import DeviceDetail from '../../components/DeviceDetail'
import { shortenInterface } from '../../components/ui/iface'
import PageState from '../../components/ui/PageState'
import Button from '../../components/ui/Button'

type IdNode = { id: string }
type IdLink = { source: string; target: string }

export default function TopologyView() {
  const [searchParams, setSearchParams] = useSearchParams()
  const scanId = searchParams.get('scan_id') || undefined
  const focusIp = searchParams.get('device') || undefined
  const siteFilter = searchParams.get('site') || undefined

  const {
    topology,
    devices,
    deviceByIp,
    scans,
    sites,
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
    runPath,
    fetchData,
  } = useTopology(scanId, focusIp, siteFilter)

  const [selectedDevice, setSelectedDevice] = useState<string | null>(null)
  const [simplified, setSimplified] = useState(true)
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)

  // A focused device view should always show individual devices so the
  // connections around the selected device are visible.
  const showSimple = simplified && !focusIp

  // Auto-select the focused device when arriving from inventory
  useEffect(() => {
    if (focusIp) {
      setSelectedDevice(focusIp)
    }
  }, [focusIp])

  const handleScanChange = (id: string) => {
    setSearchParams(id ? { scan_id: id } : {}, { replace: true })
    setSelectedDevice(null)
    setExpandedGroup(null)
    setPathSource('')
    setPathTarget('')
    setPathResult(null)
  }

  const clearFocus = () => {
    setSearchParams(scanId ? { scan_id: scanId } : {}, { replace: true })
    setSelectedDevice(null)
    setExpandedGroup(null)
  }

  const viewGroupDevice = (ip: string) => {
    setExpandedGroup(null)
    setSelectedDevice(null)
    setSimplified(false)
    setSearchParams({ ...(scanId ? { scan_id: scanId } : {}), device: ip }, { replace: true })
  }

  const focusedDevice = useMemo(() => {
    if (!focusIp) return null
    return deviceByIp.get(focusIp) ?? null
  }, [focusIp, deviceByIp])

  const typeByIp = useMemo(() => {
    const m = new Map<string, string>()
    for (const n of topology?.nodes || []) m.set(n.id, n.device_type || 'unknown')
    return m
  }, [topology])

  const { initialNodes, initialEdges } = useMemo(() => {
    if (!topology) return { initialNodes: [], initialEdges: [] }

    if (showSimple) {
      const groups = new Map<string, { count: number; internal: number }>()
      for (const n of topology.nodes) {
        const t = normalizeType(n.device_type || 'unknown')
        const g = groups.get(t) || { count: 0, internal: 0 }
        g.count++
        groups.set(t, g)
      }

      const between = new Map<string, { src: string; tgt: string; count: number }>()
      for (const l of filteredLinks) {
        const st = normalizeType(typeByIp.get(l.source) || 'unknown')
        const tt = normalizeType(typeByIp.get(l.target) || 'unknown')
        if (st === tt) {
          const g = groups.get(st)
          if (g) g.internal++
          continue
        }
        const [a, b] = [st, tt].sort()
        const key = `${a}|${b}`
        const e = between.get(key) || { src: a, tgt: b, count: 0 }
        e.count++
        between.set(key, e)
      }

      const clusterNodes: Node[] = [...groups.entries()].map(([t, g]) => ({
        id: `group:${t}`,
        type: 'device',
        position: { x: 0, y: 0 },
        data: {
          id: `group:${t}`,
          ip: '',
          hostname: pluralLabel(t),
          device_type: t,
          group: true,
          count: g.count,
          internalLinks: g.internal,
        },
      }))

      const clusterLinks: (IdLink & { count: number })[] = [...between.values()].map((e) => ({
        source: `group:${e.src}`,
        target: `group:${e.tgt}`,
        count: e.count,
      }))

      const positions = freeLayout(clusterNodes as IdNode[], clusterLinks)
      const posNodes = clusterNodes.map((n) => ({
        ...n,
        position: positions.get(n.id) || { x: 0, y: 0 },
      }))
      const posEdges: Edge[] = clusterLinks.map((e, i) => ({
        id: `cg-${i}`,
        source: e.source,
        target: e.target,
        label: `${e.count}`,
        labelStyle: { fill: '#9ca3af', fontSize: 11, fontWeight: 600 },
        labelBgStyle: { fill: '#1f2937', fillOpacity: 0.85 },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 4,
        style: { stroke: '#64748b', strokeWidth: Math.min(6, 1 + Math.log2(e.count + 1)) },
        type: 'smoothstep',
      }))

      return { initialNodes: posNodes, initialEdges: posEdges }
    }

    const layoutFn = layoutMode === 'tree' ? treeLayout
      : layoutMode === 'circle' ? circleLayout
      : layoutMode === 'radial' ? radialLayout
      : freeLayout
    const positions = layoutFn(topology.nodes as IdNode[], filteredLinks as IdLink[])

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
          device_type: n.device_type || dev?.device_type || '',
          focus: !!focusIp && n.id === focusIp,
        },
      }
    })

    const re: Edge[] = filteredLinks.map((l, i) => {
      const protocolLabel = l.protocol === 'cdp-lldp' ? 'CDP/LLDP'
        : l.protocol === 'catalyst' ? 'Catalyst'
        : l.protocol === 'lldp' ? 'LLDP'
        : l.protocol === 'cdp' ? 'CDP'
        : l.protocol === 'poe' ? 'PoE'
        : l.protocol.toUpperCase()
      const pathKey = `${l.source}->${l.target}-${i}`
      const isPath = pathEdgeIds.has(pathKey)

      return {
        id: `e-${l.source}-${l.target}-${i}`,
        source: l.source,
        target: l.target,
        label: protocolLabel,
        labelStyle: { fill: isPath ? '#22c55e' : '#9ca3af', fontSize: 10, fontWeight: 500 },
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
  }, [topology, filteredLinks, deviceByIp, layoutMode, pathEdgeIds, showSimple, typeByIp, focusIp])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  const selectedDeviceData = useMemo(() => {
    if (!selectedDevice || showSimple) return null
    const device = deviceByIp.get(selectedDevice)
    if (!device) return null
    const connectedLinks = filteredLinks.filter(
      (l) => l.source === selectedDevice || l.target === selectedDevice,
    )
    return { device, connectedLinks }
  }, [selectedDevice, deviceByIp, filteredLinks, showSimple])

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

  return (
    <div className="h-full flex flex-col">
      <TopologyToolbar
        topology={topology}
        scans={scans}
        scanId={scanId}
        onScanChange={handleScanChange}
        site={siteFilter}
        onSiteChange={(v) => {
          setSearchParams(v ? { ...Object.fromEntries(searchParams), site: v } : (() => { const p = new URLSearchParams(searchParams); p.delete('site'); return p.toString() ? Object.fromEntries(p) : {} })(), { replace: true })
        }}
        sites={sites}
        simplified={showSimple}
        onSimplifiedChange={setSimplified}
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
        onClearPath={() => {
          setPathSource('')
          setPathTarget('')
          setPathResult(null)
        }}
      />

      {focusIp && (
        <div className="flex items-center justify-between gap-3 px-4 py-2 bg-accent-subtle border-b border-accent/30 text-xs">
          <span className="text-text-secondary">
            Showing direct connections for{' '}
            <strong className="text-text-primary">
              {focusedDevice?.hostname?.split('.')[0] || focusIp}
            </strong>{' '}
            <span className="text-muted font-mono">({focusIp})</span>
          </span>
          <Button variant="secondary" size="sm" onClick={clearFocus}>
            Show full scan
          </Button>
        </div>
      )}

      {pathResult && !showSimple && (
        <div className={`px-4 py-2 border-b text-xs ${
          pathResult.error ? 'bg-red-900/30 border-red-800 text-red-300' : 'bg-green-900/30 border-green-800 text-green-300'
        }`}>
          {pathResult.error ? (
            <span>{pathResult.error}</span>
          ) : (
            <span>
              <strong>Path found:</strong>{' '}
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

      <div className="flex-1 flex min-h-0">
        {!topology || topology.nodes.length === 0 ? (
          <div className="flex-1">
            <PageState
              type="empty"
              title="No topology data"
              message="Run a discovery scan or pick a scan from the selector to populate the topology graph."
              className="h-full"
            />
          </div>
        ) : (
          <>
            <TopologyCanvas
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
          onNodeClick={(_e, node) => {
                if (showSimple && node.data?.group) {
                  setSelectedDevice(null)
                  setExpandedGroup(node.data.device_type as string)
                  return
                }
                if (showSimple) return
                setSelectedDevice(node.id)
              }}
            />

            {selectedDeviceData && (
              <DeviceDetail
                device={selectedDeviceData.device}
                connectedLinks={selectedDeviceData.connectedLinks}
                allDevices={devices}
                allLinks={filteredLinks}
                onClose={() => setSelectedDevice(null)}
              />
            )}

            {expandedGroup && topology && (
              <TopologyGroupDetail
                type={expandedGroup}
                nodes={topology.nodes}
                devices={devices}
                onClose={() => setExpandedGroup(null)}
                onViewConnections={viewGroupDevice}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}
