import { shortenInterface } from "./ui/iface"
import type { Device, TopoLink } from '../api'

interface Props {
  device: Device
  connectedLinks: TopoLink[]
  onClose: () => void
}

const statusColors: Record<string, string> = {
  up: 'text-green-400',
  down: 'text-red-400',
}

export default function DeviceDetail({ device, connectedLinks, onClose }: Props) {
  return (
    <div className="w-80 bg-surface-1 border-l border-border overflow-y-auto shrink-0">
      <div className="sticky top-0 bg-surface-1 border-b border-border px-4 py-3 flex items-center justify-between">
        <h3 className="font-semibold text-text-primary text-sm truncate">
          {device.hostname || device.ip}
        </h3>
        <button
          onClick={onClose}
          className="text-muted hover:text-text-primary text-lg leading-none"
        >
          &times;
        </button>
      </div>

      <div className="p-4 space-y-4">
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="text-muted text-xs">IP</span>
            <p className="text-text-primary font-mono">{device.ip}</p>
          </div>
          <div>
            <span className="text-muted text-xs">Type</span>
            <p className="text-text-primary capitalize">{device.device_type || 'unknown'}</p>
          </div>
          <div>
            <span className="text-muted text-xs">Vendor</span>
            <p className="text-text-primary">{device.vendor || '\u2014'}</p>
          </div>
          <div>
            <span className="text-muted text-xs">Model</span>
            <p className="text-text-primary">{device.model || '\u2014'}</p>
          </div>
        </div>

        {device.snmp_identified && (
          <div className="bg-blue-900/30 border border-blue-800 rounded px-3 py-2 text-xs">
            <span className="text-blue-400 font-medium">SNMP identified</span>
            {device.snmp_community && (
              <span className="text-muted ml-2">({device.snmp_community})</span>
            )}
          </div>
        )}

        {connectedLinks.length > 0 && (
          <div>
            <span className="text-muted text-xs block mb-2">
              Connections ({connectedLinks.length})
            </span>
            <div className="space-y-1">
              {connectedLinks.map((link, i) => {
                const isSource = link.source === device.ip
                const localIface = shortenInterface(isSource ? link.source_interface : link.target_interface)
                const remoteIface = shortenInterface(isSource ? link.target_interface : link.source_interface)
                const remote = isSource ? link.target : link.source
                const remoteName = isSource ? link.target_hostname : link.source_hostname

                return (
                  <div key={i} className="bg-surface-2 rounded px-3 py-2 text-xs">
                    <div className="flex items-center gap-1 text-muted">
                      <span className="px-1 py-0.5 rounded text-[10px] font-bold uppercase bg-surface-3">
                        {link.protocol}
                      </span>
                      <span className="text-text-primary font-mono">{localIface || '\u2014'}</span>
                      <span className="text-gray-600">\u2194</span>
                      <span className="text-text-primary font-mono">{remoteIface || '\u2014'}</span>
                    </div>
                    <div className="text-muted mt-1">
                      to{' '}
                      <span className="text-text-secondary">{remoteName || remote}</span>
                      {remoteName && remote !== remoteName && (
                        <span className="text-muted ml-1 font-mono">({remote})</span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {device.open_ports.length > 0 && (
          <div>
            <span className="text-muted text-xs block mb-1">Open Ports</span>
            <div className="flex flex-wrap gap-1">
              {device.open_ports.map((p) => (
                <span key={p} className="px-2 py-0.5 bg-surface-2 rounded text-xs text-text-secondary">
                  {p}
                </span>
              ))}
            </div>
          </div>
        )}

        {device.interfaces.length > 0 && (
          <div>
            <span className="text-muted text-xs block mb-2">
              Interfaces ({device.interfaces.length})
            </span>
            <div className="space-y-1">
              {device.interfaces.map((iface) => (
                <div
                  key={iface.ifIndex}
                  className="bg-surface-2 rounded px-3 py-2 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-text-primary font-medium truncate">
                      {shortenInterface(iface.ifDescr || iface.ifName || `if${iface.ifIndex}`)}
                    </span>
                    <span className={statusColors[iface.ifOperStatus] || 'text-muted'}>
                      {iface.ifOperStatus}
                    </span>
                  </div>
                  <div className="text-muted mt-0.5 flex gap-3">
                    {iface.ifPhysAddress && <span>MAC: {iface.ifPhysAddress}</span>}
                    {iface.ifSpeed && <span>{iface.ifSpeed} bps</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
