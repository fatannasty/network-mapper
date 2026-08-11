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

type SortField = 'hostname' | 'ip' | 'device_type' | 'vendor'
type LinkSortField = 'source' | 'source_interface' | 'target_interface' | 'target'

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

        <Tabs
          tabs={[
            { id: 'devices', label: 'Devices', count: devices.length },
            { id: 'connections', label: 'Connections', count: rawLinks.length },
          ]}
          active={activeTab}
          onChange={(id) => setActiveTab(id as 'devices' | 'connections')}
        />
      </div>

      <div className="flex-1 flex min-h-0">
        <div className="flex-1 overflow-auto">
          {activeTab === 'devices' ? (
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
            <DeviceDetail device={selectedDevice} connectedLinks={connectedLinks} onClose={() => setSelectedIp(null)} />
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
