import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getDevices, getInventoryLinks, type Device, type TopoLink } from '../api'
import Badge from './ui/Badge'
import Input from './ui/Input'
import LoadingSpinner from './ui/LoadingSpinner'
import DataTable, { type Column, type SortDir } from './ui/Table'
import Button from './ui/Button'
import Tabs from './ui/Tabs'
import DeviceDetail from './DeviceDetail'
import PageState from './ui/PageState'
import { friendlyType, shortName, typeIcon } from '../features/topology/services/friendly'

type SortField = 'hostname' | 'ip' | 'device_type' | 'vendor'
type LinkSortField = 'source' | 'source_interface' | 'target_interface' | 'target'
type ViewMode = 'list' | 'grid'

export default function DeviceInventory() {
  const [devices, setDevices] = useState<Device[]>([])
  const [rawLinks, setRawLinks] = useState<TopoLink[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [sortKey, setSortKey] = useState<SortField>('hostname')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [linkSortKey, setLinkSortKey] = useState<LinkSortField>('source')
  const [linkSortDir, setLinkSortDir] = useState<SortDir>('asc')
  const [selectedIp, setSelectedIp] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'devices' | 'connections'>('devices')
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const initialLoad = useRef(true)
  const navigate = useNavigate()

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  useEffect(() => {
    if (search) return
    setDebouncedSearch('')
  }, [search])

  const fetchData = useCallback(async () => {
    setError('')
    if (initialLoad.current) setLoading(true)
    try {
      const params: Record<string, string> = { limit: '5000' }
      if (typeFilter) params.device_type = typeFilter
      if (debouncedSearch) params.search = debouncedSearch
      const [devResp, lnks] = await Promise.all([getDevices(params), getInventoryLinks()])
      setDevices(devResp.devices || [])
      setRawLinks(Array.isArray(lnks) ? lnks : [])
    } catch (err) { setError(err instanceof Error ? err.message : 'Failed') }
    finally { setLoading(false); initialLoad.current = false }
  }, [debouncedSearch, typeFilter])

  useEffect(() => { fetchData() }, [fetchData])

  const types = useMemo(() => [...new Set(devices.map((d) => d.device_type).filter(Boolean))].sort(), [devices])

  const selectedDevice = useMemo(() => {
    if (!selectedIp) return null
    return devices.find((d) => d.ip === selectedIp) ?? null
  }, [selectedIp, devices])

  const connectedLinks = useMemo(() => {
    if (!selectedIp) return []
    return rawLinks.filter((l) => l.source === selectedIp || l.target === selectedIp)
  }, [selectedIp, rawLinks])

  const columns: Column<Device>[] = useMemo(() => [
    { key: 'ip', label: 'IP', sortable: true, cellClassName: 'font-mono text-xs' },
    { key: 'hostname', label: 'Hostname', sortable: true, cellClassName: 'text-text-primary text-xs' },
    { key: 'device_type', label: 'Type', sortable: true, render: (d) => <Badge label={d.device_type || 'unknown'} /> },
    { key: 'vendor', label: 'Vendor', sortable: true, cellClassName: 'text-muted text-xs' },
    { key: 'model', label: 'Model', cellClassName: 'text-muted text-xs max-w-48 truncate' },
  ], [])

  const sorted = useMemo(() => {
    const arr = [...devices]
    arr.sort((a, b) => {
      const va = String((a as unknown as Record<string, string>)[sortKey] || '').toLowerCase()
      const vb = String((b as unknown as Record<string, string>)[sortKey] || '').toLowerCase()
      return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    })
    return arr
  }, [devices, sortKey, sortDir])

  const linkColumns: Column<TopoLink>[] = useMemo(() => [
    {
      key: 'source', label: 'Source', sortable: true, cellClassName: 'text-xs',
      render: (l) => (
        <span className="flex flex-col">
          <span className="text-text-primary font-mono">{l.source}</span>
          {l.source_hostname && <span className="text-muted text-[11px] truncate max-w-48">{l.source_hostname}</span>}
        </span>
      ),
    },
    {
      key: 'source_interface', label: 'Src Interface', sortable: true, cellClassName: 'font-mono text-xs text-muted',
    },
    { key: 'protocol', label: 'Protocol', render: (l) => <Badge label={l.protocol || 'unknown'} /> },
    {
      key: 'target_interface', label: 'Dst Interface', sortable: true, cellClassName: 'font-mono text-xs text-muted',
    },
    {
      key: 'target', label: 'Target', sortable: true, cellClassName: 'text-xs',
      render: (l) => (
        <span className="flex flex-col">
          <span className="text-text-primary font-mono">{l.target}</span>
          {l.target_hostname && <span className="text-muted text-[11px] truncate max-w-48">{l.target_hostname}</span>}
        </span>
      ),
    },
  ], [])

  const sortedLinks = useMemo(() => {
    const arr = [...rawLinks]
    arr.sort((a, b) => {
      const va = String((a as unknown as Record<string, string>)[linkSortKey] || '').toLowerCase()
      const vb = String((b as unknown as Record<string, string>)[linkSortKey] || '').toLowerCase()
      return linkSortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    })
    return arr
  }, [rawLinks, linkSortKey, linkSortDir])

  if (loading && devices.length === 0) return <LoadingSpinner />
  if (error && devices.length === 0) {
    return (
      <PageState
        type="error"
        title="Failed to load inventory"
        message={error}
        className="h-full"
        action={<Button variant="danger" size="sm" onClick={fetchData}>Retry</Button>}
      />
    )
  }

  const openDevice = (ip: string) => {
    setSelectedIp(selectedIp === ip ? null : ip)
    if (activeTab !== 'devices') setActiveTab('devices')
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="px-5 pt-3 bg-surface-1 border-b border-border shrink-0">
        <div className="flex items-center gap-3 pb-3">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search hostname, IP, model..." className="w-64" />
          <div className="flex-1" />
          <span className="text-xs text-muted tabular-nums">
            {devices.length} devices &middot; {rawLinks.length} links
          </span>
        </div>

        {activeTab === 'devices' && types.length > 0 && (
          <div className="flex items-center gap-1 flex-wrap pb-3">
            <button
              onClick={() => setTypeFilter('')}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                !typeFilter
                  ? 'bg-accent text-white'
                  : 'bg-surface-2 text-muted hover:text-text-secondary hover:bg-surface-3'
              }`}
            >
              All
            </button>
            {types.map((t) => (
              <button
                key={t}
                onClick={() => setTypeFilter(typeFilter === t ? '' : t)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors capitalize ${
                  typeFilter === t
                    ? 'bg-accent text-white'
                    : 'bg-surface-2 text-muted hover:text-text-secondary hover:bg-surface-3'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full inline-block mr-1.5 ${typeFilter === t ? 'bg-white/60' : 'bg-muted'}`} />
                {t}
              </button>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between">
          <Tabs
            tabs={[
              { id: 'devices', label: 'Devices', count: devices.length },
              { id: 'connections', label: 'Connections', count: rawLinks.length },
            ]}
            active={activeTab}
            onChange={(id) => setActiveTab(id as 'devices' | 'connections')}
          />
          {activeTab === 'devices' && (
            <div className="flex items-center gap-0.5 bg-surface-2 rounded-lg p-0.5">
              <button
                onClick={() => setViewMode('list')}
                className={`p-1.5 rounded-md transition-colors ${viewMode === 'list' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'}`}
                title="List view"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z" />
                </svg>
              </button>
              <button
                onClick={() => setViewMode('grid')}
                className={`p-1.5 rounded-md transition-colors ${viewMode === 'grid' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'}`}
                title="Card view"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
                </svg>
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 flex min-h-0">
        <div className="flex-1 overflow-auto">
          {activeTab === 'devices' ? (
            viewMode === 'list' ? (
              <DataTable
                columns={columns}
                data={sorted}
                rowKey={(d) => d.ip}
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={(key) => {
                  if (sortKey === key && sortDir === 'asc') setSortDir('desc')
                  else setSortDir('asc')
                  setSortKey(key as SortField)
                }}
                onRowClick={(d) => openDevice(d.ip)}
                selectedId={selectedIp}
                emptyMessage={debouncedSearch || typeFilter ? 'No devices match the filter' : 'No devices found'}
              />
            ) : (
              <div className="p-4 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                {sorted.map((d) => {
                  const isSelected = selectedIp === d.ip
                  const type = d.device_type || 'unknown'
                  const icons = typeIcon(type)
                  const name = shortName(d.hostname) || d.ip
                  const nodeColors: Record<string, string> = {
                    switch: 'border-sky-400 bg-sky-950/60',
                    'core-switch': 'border-violet-400 bg-violet-950/60',
                    router: 'border-amber-400 bg-amber-950/60',
                    firewall: 'border-red-400 bg-red-950/60',
                    accesspoint: 'border-emerald-400 bg-emerald-950/60',
                    'access-point': 'border-emerald-400 bg-emerald-950/60',
                    'sd-wan': 'border-green-400 bg-green-950/60',
                    'velocloud-edge': 'border-teal-400 bg-teal-950/60',
                    unknown: 'border-gray-500 bg-gray-800/60',
                  }
                  const iconBg: Record<string, string> = {
                    switch: 'bg-sky-500/20 text-sky-300',
                    'core-switch': 'bg-violet-500/20 text-violet-300',
                    router: 'bg-amber-500/20 text-amber-300',
                    firewall: 'bg-red-500/20 text-red-300',
                    accesspoint: 'bg-emerald-500/20 text-emerald-300',
                    'access-point': 'bg-emerald-500/20 text-emerald-300',
                    'sd-wan': 'bg-green-500/20 text-green-300',
                    'velocloud-edge': 'bg-teal-500/20 text-teal-300',
                    unknown: 'bg-gray-500/20 text-gray-300',
                  }
                  return (
                    <button
                      key={d.ip}
                      onClick={() => openDevice(d.ip)}
                      className={`text-left rounded-xl border-2 p-3 transition-all hover:scale-[1.02] cursor-pointer ${
                        nodeColors[type] || nodeColors.unknown
                      } ${isSelected ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-surface-0' : ''}`}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`w-8 h-8 shrink-0 rounded-lg flex items-center justify-center ${iconBg[type] || iconBg.unknown}`}>
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
                            {icons.map((icon, i) => <path key={i} d={icon} />)}
                          </svg>
                        </span>
                        <span className="flex flex-col min-w-0">
                          <span className="text-sm font-semibold text-text-primary truncate">{name}</span>
                          <span className="text-[11px] text-white/70">{friendlyType(type)}</span>
                        </span>
                      </div>
                      <div className="text-[11px] font-mono text-muted truncate">{d.ip}</div>
                      {d.vendor && <div className="text-[11px] text-muted truncate">{d.vendor}{d.model ? ` ${d.model}` : ''}</div>}
                      {d.site && <div className="text-[11px] text-accent/70 truncate">{d.site}</div>}
                    </button>
                  )
                })}
                {sorted.length === 0 && (
                  <div className="col-span-full text-center py-12 text-muted text-sm">
                    {debouncedSearch || typeFilter ? 'No devices match the filter' : 'No devices found'}
                  </div>
                )}
              </div>
            )
          ) : (
            <DataTable
              columns={linkColumns}
              data={sortedLinks}
              rowKey={(l) => `${l.source}-${l.target}-${l.source_interface}-${l.target_interface}`}
              sortKey={linkSortKey}
              sortDir={linkSortDir}
              onSort={(key) => {
                if (linkSortKey === key && linkSortDir === 'asc') setLinkSortDir('desc')
                else setLinkSortDir('asc')
                setLinkSortKey(key as LinkSortField)
              }}
              onRowClick={(l) => openDevice(l.source)}
              emptyMessage="No connections found"
            />
          )}
        </div>

        {selectedDevice && (
          <div className="flex flex-col border-l border-border w-80 shrink-0">
            <DeviceDetail device={selectedDevice} connectedLinks={connectedLinks} allDevices={devices} allLinks={rawLinks} onClose={() => setSelectedIp(null)} />
            <div className="p-3 border-t border-border">
              <Button
                variant="secondary"
                size="sm"
                className="w-full"
                onClick={() => {
                  const scanId = selectedDevice.last_scan_id
                  const url = scanId
                    ? `/topology?scan_id=${scanId}&device=${encodeURIComponent(selectedDevice.ip)}`
                    : '/topology'
                  navigate(url)
                }}
                icon={
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                  </svg>
                }
              >
                View in Topology
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
