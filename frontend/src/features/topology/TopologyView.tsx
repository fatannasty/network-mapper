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
import { measureLatency, downloadPortTable, getTopologySummary, type TopologySummaryData } from '../../api'
import TopologyToolbar from './components/TopologyToolbar'
import TopologyCanvas from './components/TopologyCanvas'
import TopologyGroupDetail from './components/TopologyGroupDetail'
import ExportDiagramDialog from './components/ExportDiagramDialog'
import DeviceDetail from '../../components/DeviceDetail'
import { shortenInterface } from '../../components/ui/iface'
import PageState from '../../components/ui/PageState'
import Button from '../../components/ui/Button'

type IdNode = { id: string }
type IdLink = { source: string; target: string }

function StatChip({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col items-center min-w-[88px] px-4 py-2.5 rounded-2xl border border-border/50 bg-surface-2/70 backdrop-blur-xl shadow-lg shadow-accent/5">
      <span className="text-2xl font-bold text-text-primary tabular-nums leading-none bg-gradient-to-b from-text-primary to-accent bg-clip-text text-transparent">{value.toLocaleString()}</span>
      <span className="text-[10px] text-muted uppercase tracking-widest mt-1.5">{label}</span>
    </div>
  )
}

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
  const [clusterMode, setClusterMode] = useState<'type' | 'subnet'>('type')
  const [summary, setSummary] = useState<TopologySummaryData | null>(null)
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)
  const [exportOpen, setExportOpen] = useState(false)
  const [measuringLatency, setMeasuringLatency] = useState(false)

  // A focused device view should always show individual devices so the
  // connections around the selected device are visible.
  const showSimple = simplified && !focusIp

  // Fetch the clustered (subnet block) view when requested.
  useEffect(() => {
    if (!showSimple || clusterMode !== 'subnet') { setSummary(null); return }
    let cancelled = false
    getTopologySummary(scanId, siteFilter)
      .then((s) => { if (!cancelled) setSummary(s) })
      .catch(() => { if (!cancelled) setSummary(null) })
    return () => { cancelled = true }
  }, [showSimple, clusterMode, scanId, siteFilter])

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

  const handleMeasureLatency = async () => {
    setMeasuringLatency(true)
    try {
      await measureLatency(siteFilter)
      await fetchData()
    } catch {
      // measurement failures are non-fatal; the tooltip simply shows "—"
    } finally {
      setMeasuringLatency(false)
    }
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

    if (showSimple && clusterMode === 'subnet' && summary) {
      const positions = freeLayout(summary.nodes as IdNode[], summary.links as IdLink[])
      const sn: Node[] = summary.nodes.map((n) => ({
        id: n.id,
        type: 'device',
        position: positions.get(n.id) || { x: 0, y: 0 },
        data: {
          id: n.id,
          ip: n.ip,
          hostname: n.hostname,
          device_type: n.device_type,
          status: n.status || 'unknown',
          group: n.device_type === 'subnet',
          count: n.device_count ?? 0,
        },
      }))
      const se: Edge[] = summary.links.map((l, i) => ({
        id: `s-${l.source}-${l.target}-${i}`,
        source: l.source,
        target: l.target,
        label: `${l.count ?? 1}`,
        data: { link: l },
        labelStyle: { fill: '#94a3b8', fontSize: 10, fontWeight: 600 },
        labelBgStyle: { fill: '#0f172a', fillOpacity: 0.9 },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 6,
        style: { stroke: l.status === 'down' ? '#ef4444' : '#60a5fa', strokeWidth: 2.25 },
        type: 'smoothstep',
      }))
      return { initialNodes: sn, initialEdges: se }
    }

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
        data: { cluster: { src: pluralLabel(e.source.replace('group:', '')), tgt: pluralLabel(e.target.replace('group:', '')), count: e.count } },
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
          status: n.status || 'unknown',
          spof: !!n.spof,
          vlan90: n.vlan_90 === true,
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
      const isDown = l.status === 'down'

      return {
        id: `e-${l.source}-${l.target}-${i}`,
        source: l.source,
        target: l.target,
        label: protocolLabel,
        data: { link: l },
        labelStyle: { fill: isPath ? '#22c55e' : '#94a3b8', fontSize: 10, fontWeight: 600 },
        labelBgStyle: { fill: isPath ? '#064e3b' : '#0f172a', fillOpacity: 0.9 },
        labelBgPadding: [6, 3] as [number, number],
        labelBgBorderRadius: 6,
        style: {
          stroke: isPath ? '#22c55e'
            : isDown ? '#ef4444'
            : l.protocol === 'cdp' ? '#f59e0b'
            : l.protocol === 'catalyst' ? '#38bdf8'
            : '#60a5fa',
          strokeWidth: isPath ? 3.5 : 2.25,
          strokeDasharray: isDown ? '6 3' : undefined,
        },
        animated: !isDown,
        type: 'smoothstep',
      }
    })

    return { initialNodes: rn, initialEdges: re }
  }, [topology, filteredLinks, deviceByIp, layoutMode, pathEdgeIds, showSimple, clusterMode, summary, typeByIp, focusIp])

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
      {/* Hero header */}
      <div className="relative px-6 pt-6 pb-5 bg-gradient-to-b from-accent/15 via-accent/5 to-transparent border-b border-border/30 shrink-0 overflow-hidden">
        <div className="absolute -top-24 -left-16 w-72 h-72 rounded-full bg-accent/20 blur-3xl pointer-events-none" />
        <div className="absolute -top-16 right-10 w-56 h-56 rounded-full bg-accent/10 blur-3xl pointer-events-none" />
        <div className="relative flex items-end justify-between gap-6 flex-wrap">
          <div>
            <h1 className="text-3xl font-bold text-text-primary tracking-tight">
              Network Topology
              {siteFilter && <span className="ml-2 text-xl font-semibold text-accent">\u00b7 {siteFilter}</span>}
            </h1>
            <p className="text-sm text-muted mt-1.5 max-w-xl">
              An interactive map of your network — see how every device is connected, from edge to core.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatChip label="Devices" value={topology?.nodes.length ?? 0} />
            <StatChip label="Links" value={topology?.links.length ?? 0} />
            <StatChip label="Sites" value={sites.length} />
          </div>
        </div>
      </div>

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
        clusterMode={clusterMode}
        onClusterModeChange={setClusterMode}
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
        onExportDiagram={() => setExportOpen(true)}
        onExportTable={() => downloadPortTable(scanId)}
        onMeasureLatency={handleMeasureLatency}
        measuringLatency={measuringLatency}
      />

      {focusIp && (
        <div className="flex items-center justify-between gap-3 px-4 py-2.5 bg-accent-subtle/40 backdrop-blur border-b border-accent/20 text-xs">
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
        <div className={`px-4 py-2.5 border-b text-xs backdrop-blur ${
          pathResult.error ? 'bg-red-900/30 border-red-800/50 text-red-300' : 'bg-green-900/30 border-green-800/50 text-green-300'
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
              deviceByIp={deviceByIp}
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

      {topology && (
        <ExportDiagramDialog
          open={exportOpen}
          onClose={() => setExportOpen(false)}
          topology={topology}
          defaultTitle={siteFilter ? `AMTRAK ${siteFilter.toUpperCase()}` : 'AMTRAK NETWORK DIAGRAM'}
          scanId={scanId}
        />
      )}
    </div>
  )
}
