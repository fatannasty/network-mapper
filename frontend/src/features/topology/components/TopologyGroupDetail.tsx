import { useMemo, useState } from 'react'
import type { Device, TopoNode } from '../../../api'
import Button from '../../../components/ui/Button'
import Input from '../../../components/ui/Input'
import Badge from '../../../components/ui/Badge'
import { friendlyType, normalizeType, shortName } from '../services/friendly'

interface Props {
  type: string
  nodes: TopoNode[]
  devices: Device[]
  onClose: () => void
  onViewConnections: (ip: string) => void
}

export default function TopologyGroupDetail({ type, nodes, devices, onClose, onViewConnections }: Props) {
  const [search, setSearch] = useState('')
  const members = useMemo(() => {
    const ips = new Set(
      nodes.filter((n) => normalizeType(n.device_type) === type).map((n) => n.ip),
    )
    const deviceByIp = new Map(devices.map((device) => [device.ip, device]))
    return [...ips]
      .map((ip) => deviceByIp.get(ip) || nodes.find((node) => node.ip === ip))
      .filter((item): item is Device | TopoNode => Boolean(item))
      .filter((item) => {
        const value = `${item.ip} ${'hostname' in item ? item.hostname : ''} ${'vendor' in item ? item.vendor : ''}`.toLowerCase()
        return value.includes(search.toLowerCase())
      })
      .sort((a, b) => (a.hostname || a.ip).localeCompare(b.hostname || b.ip))
  }, [devices, nodes, search, type])

  return (
    <aside className="w-96 bg-surface-1/80 backdrop-blur-2xl border-l border-border/30 overflow-hidden shrink-0 flex flex-col">
      <div className="px-4 py-3 border-b border-border/30 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-text-primary">{friendlyType(type)} devices</h2>
          <p className="text-xs text-muted mt-0.5">Select a device to view its connections.</p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close device group">
          Close
        </Button>
      </div>
      <div className="p-3 border-b border-border/30 space-y-2">
        <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find a device..." className="w-full" />
        <p className="text-[11px] text-muted">{members.length} matching devices</p>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {members.map((item) => (
          <button
            key={item.ip}
            onClick={() => onViewConnections(item.ip)}
            className="w-full text-left rounded-xl px-3 py-2.5 hover:bg-surface-2/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent transition-all duration-150"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-text-primary truncate">{shortName(item.hostname) || item.ip}</span>
              <Badge label={friendlyType(item.device_type || type)} />
            </div>
            <div className="flex items-center justify-between gap-2 mt-1 text-[11px]">
              <span className="font-mono text-muted truncate">{item.ip}</span>
              <span className="text-accent shrink-0">View connections</span>
            </div>
          </button>
        ))}
        {members.length === 0 && <p className="text-xs text-muted text-center py-8">No matching devices.</p>}
      </div>
    </aside>
  )
}
