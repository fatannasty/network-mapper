import { useCallback, useEffect, useMemo, useState } from 'react'
import { getDevices, getTopology, type Device, type TopoLink } from '../api'

type SortField = 'hostname' | 'ip' | 'device_type' | 'vendor'
type SortDir = 'asc' | 'desc'

interface ExpandedDevice {
  device: Device
  connectedLinks: TopoLink[]
}

export default function DeviceInventory() {
  const [devices, setDevices] = useState<Device[]>([])
  const [links, setLinks] = useState<TopoLink[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [sortField, setSortField] = useState<SortField>('hostname')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [expandedIp, setExpandedIp] = useState<string | null>(null)
  const [expandedData, setExpandedData] = useState<ExpandedDevice | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params: Record<string, string> = { limit: '5000' }
      if (typeFilter) params.device_type = typeFilter
      if (search) params.search = search

      const [devResp, topoResp] = await Promise.all([
        getDevices(params),
        getTopology(),
      ])
      setDevices(devResp.devices || [])

      const lnks = topoResp?.links || []
      setLinks(lnks)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load devices')
    } finally {
      setLoading(false)
    }
  }, [search, typeFilter])

  useEffect(() => { fetchData() }, [fetchData])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const sorted = useMemo(() => {
    const arr = [...devices]
    arr.sort((a, b) => {
      const va = (a[sortField] || '').toLowerCase()
      const vb = (b[sortField] || '').toLowerCase()
      return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    })
    return arr
  }, [devices, sortField, sortDir])

  const handleExpand = useCallback(async (device: Device) => {
    if (expandedIp === device.ip) {
      setExpandedIp(null)
      setExpandedData(null)
      return
    }
    setExpandedIp(device.ip)
    // Find links connected to this device
    const connected = links.filter(
      (l) => l.source === device.ip || l.target === device.ip,
    )
    setExpandedData({ device, connectedLinks: connected })
  }, [expandedIp, links])

  const types = useMemo(() => {
    const s = new Set(devices.map((d) => d.device_type).filter(Boolean))
    return Array.from(s).sort()
  }, [devices])

  const sortArrow = (field: SortField) =>
    sortField === field ? (sortDir === 'asc' ? ' ▴' : ' ▾') : ''

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400">
        <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="bg-red-900/50 border border-red-800 rounded p-6 text-red-300">
          <p>{error}</p>
          <button onClick={fetchData} className="mt-3 px-4 py-1 bg-red-800 hover:bg-red-700 rounded text-sm">Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-3 bg-gray-900 border-b border-gray-800 shrink-0">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search hostname / IP / model..."
          className="w-64 px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
        />
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-gray-300 text-sm focus:outline-none focus:border-blue-500"
        >
          <option value="">All types</option>
          {types.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <span className="text-gray-600 text-sm">
          {sorted.length} devices &middot; {links.length} topology links
        </span>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-900 border-b border-gray-800">
            <tr className="text-left text-gray-400 text-xs uppercase tracking-wider">
              <th className="px-4 py-2 cursor-pointer hover:text-white" onClick={() => handleSort('ip')}>
                IP{sortArrow('ip')}
              </th>
              <th className="px-4 py-2 cursor-pointer hover:text-white" onClick={() => handleSort('hostname')}>
                Hostname{sortArrow('hostname')}
              </th>
              <th className="px-4 py-2 cursor-pointer hover:text-white" onClick={() => handleSort('device_type')}>
                Type{sortArrow('device_type')}
              </th>
              <th className="px-4 py-2 cursor-pointer hover:text-white" onClick={() => handleSort('vendor')}>
                Vendor{sortArrow('vendor')}
              </th>
              <th className="px-4 py-2 text-gray-500">Model</th>
              <th className="px-4 py-2 text-gray-500">Details</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((d) => (
              <>
                <tr
                  key={d.ip}
                  className={`border-b border-gray-800/50 hover:bg-gray-800/50 cursor-pointer transition-colors ${
                    expandedIp === d.ip ? 'bg-gray-800' : ''
                  }`}
                  onClick={() => handleExpand(d)}
                >
                  <td className="px-4 py-2 font-mono text-gray-300">{d.ip}</td>
                  <td className="px-4 py-2 text-white">{d.hostname || '\u2014'}</td>
                  <td className="px-4 py-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      d.device_type.includes('switch') ? 'bg-blue-900/50 text-blue-300'
                      : d.device_type === 'accesspoint' ? 'bg-green-900/50 text-green-300'
                      : d.device_type === 'router' ? 'bg-amber-900/50 text-amber-300'
                      : d.device_type === 'firewall' ? 'bg-red-900/50 text-red-300'
                      : 'bg-gray-700 text-gray-400'
                    }`}>
                      {d.device_type || 'unknown'}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-400">{d.vendor || '\u2014'}</td>
                  <td className="px-4 py-2 text-gray-500 max-w-48 truncate">{d.model || '\u2014'}</td>
                  <td className="px-4 py-2 text-gray-500 text-xs">
                    {d.interfaces?.length ? `${d.interfaces.length} ports` : ''}
                    {expandedIp === d.ip ? ' ▾' : ' ▸'}
                  </td>
                </tr>
                {expandedIp === d.ip && expandedData && (
                  <tr key={`${d.ip}-expanded`}>
                    <td colSpan={6} className="px-4 py-3 bg-gray-850 border-b border-gray-700">
                      <div className="grid grid-cols-2 gap-4">
                        {/* Interfaces */}
                        <div>
                          <span className="text-gray-500 text-xs block mb-2">
                            {expandedData.device.interfaces?.length ? `Interfaces (${expandedData.device.interfaces.length})` : 'No interface data'}
                          </span>
                          {expandedData.device.interfaces?.length > 0 ? (
                            <div className="space-y-1 max-h-60 overflow-auto">
                              {expandedData.device.interfaces.map((iface) => (
                                <div key={iface.ifIndex} className="flex items-center justify-between bg-gray-800 rounded px-3 py-1.5 text-xs">
                                  <div>
                                    <span className="text-white font-mono">
                                      {iface.ifDescr || iface.ifName || `if${iface.ifIndex}`}
                                    </span>
                                    {iface.ifAlias && (
                                      <span className="text-gray-500 ml-2">{iface.ifAlias}</span>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-3 text-gray-500">
                                    {iface.ifPhysAddress && <span>MAC: {iface.ifPhysAddress}</span>}
                                    {iface.ifSpeed && <span>{iface.ifSpeed}</span>}
                                    <span className={iface.ifOperStatus === 'up' ? 'text-green-400' : 'text-red-400'}>
                                      {iface.ifOperStatus}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="text-gray-600 text-xs">Interfaces are only populated after SNMP discovery</p>
                          )}
                        </div>
                        {/* Connections */}
                        <div>
                          <span className="text-gray-500 text-xs block mb-2">
                            Connections ({expandedData.connectedLinks.length})
                          </span>
                          {expandedData.connectedLinks.length > 0 ? (
                            <div className="space-y-1 max-h-60 overflow-auto">
                              {expandedData.connectedLinks.map((link, i) => {
                                const isSrc = link.source === d.ip
                                const localPort = isSrc ? link.source_interface : link.target_interface
                                const remotePort = isSrc ? link.target_interface : link.source_interface
                                const remoteName = isSrc ? link.target_hostname : link.source_hostname
                                const remoteIp = isSrc ? link.target : link.source
                                return (
                                  <div key={i} className="bg-gray-800 rounded px-3 py-1.5 text-xs flex items-center justify-between">
                                    <div>
                                      <span className="font-mono text-white">{localPort || '\u2014'}</span>
                                      <span className="text-gray-600 mx-1.5">→</span>
                                      <span className="font-mono text-white">{remotePort || '\u2014'}</span>
                                    </div>
                                    <div className="text-gray-400">
                                      <span>{remoteName || remoteIp}</span>
                                      <span className="ml-2 px-1.5 py-0.5 rounded bg-gray-700 text-[10px] uppercase font-bold">
                                        {link.protocol}
                                      </span>
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          ) : (
                            <p className="text-gray-600 text-xs">No links found for this device</p>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
