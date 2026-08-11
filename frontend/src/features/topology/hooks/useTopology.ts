import { useCallback, useEffect, useMemo, useState } from 'react'
import type { TopologyData, Device, PathResult } from '../../../api'
import { getTopology, getDevices, findPath } from '../../../api'

export type ProtocolFilter = 'all' | 'lldp' | 'cdp'
export type LayoutMode = 'tree' | 'free'

export function useTopology(scanId?: string) {
  const [topology, setTopology] = useState<TopologyData | null>(null)
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [protocolFilter, setProtocolFilter] = useState<ProtocolFilter>('all')
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('tree')
  const [pathSource, setPathSource] = useState('')
  const [pathTarget, setPathTarget] = useState('')
  const [pathResult, setPathResult] = useState<PathResult | null>(null)

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

  const filteredLinks = useMemo(() => {
    const all = topology?.links || []
    if (protocolFilter === 'all') return all
    return all.filter((l) => l.protocol === protocolFilter)
  }, [topology, protocolFilter])

  const pathEdgeIds = useMemo(() => {
    if (!pathResult?.path) return new Set<string>()
    return new Set(pathResult.path.map((p, i) => `${p.source}->${p.target}-${i}`))
  }, [pathResult])

  const runPath = useCallback(async () => {
    if (!pathSource || !pathTarget) return
    setPathResult(null)
    try {
      setPathResult(await findPath(pathSource, pathTarget))
    } catch (err) {
      setPathResult({
        source: pathSource,
        target: pathTarget,
        path: [],
        hops: 0,
        error: err instanceof Error ? err.message : String(err),
      })
    }
  }, [pathSource, pathTarget])

  const linkCounts = useMemo(() => {
    const counts = { lldp: 0, cdp: 0 }
    for (const l of topology?.links || []) {
      if (l.protocol === 'lldp') counts.lldp++
      else if (l.protocol === 'cdp') counts.cdp++
    }
    return counts
  }, [topology])

  return {
    topology,
    devices,
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
  }
}
