import { useState } from 'react'
import { shortenInterface } from './ui/iface'
import type { Device, TopoLink } from '../api'
import { friendlyType, typeDescription, shortName } from '../features/topology/services/friendly'

interface Props {
  device: Device
  connectedLinks: TopoLink[]
  onClose: () => void
}

export default function DeviceDetail({ device, connectedLinks, onClose }: Props) {
  const [showTech, setShowTech] = useState(false)
  const type = friendlyType(device.device_type)
  const name = shortName(device.hostname) || device.ip

  return (
    <div className="w-80 bg-surface-1 border-l border-border overflow-y-auto shrink-0">
      <div className="sticky top-0 bg-surface-1 border-b border-border px-4 py-3 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold text-text-primary text-sm truncate">{name}</h3>
          <p className="text-muted text-[11px] capitalize">{type}</p>
        </div>
        <button
          onClick={onClose}
          className="text-muted hover:text-text-primary text-lg leading-none"
          aria-label="Close"
        >
          &times;
        </button>
      </div>

      <div className="p-4 space-y-4">
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="text-muted text-xs">IP address</span>
            <p className="text-text-primary font-mono">{device.ip}</p>
          </div>
          <div>
            <span className="text-muted text-xs">Vendor</span>
            <p className="text-text-primary">{device.vendor || '\u2014'}</p>
          </div>
          <div>
            <span className="text-muted text-xs">Model</span>
            <p className="text-text-primary">{device.model || '\u2014'}</p>
          </div>
          {device.site && (
            <div>
              <span className="text-muted text-xs">Location</span>
              <p className="text-text-primary truncate">{device.site}</p>
            </div>
          )}
        </div>

        <div className="bg-surface-2 rounded-lg px-3 py-2.5">
          <p className="text-xs text-text-secondary leading-relaxed">
            <span className="text-text-primary font-semibold">{type}:</span>{' '}
            {typeDescription(device.device_type)}
          </p>
        </div>

        <div>
          <span className="text-muted text-xs block mb-2">
            Connections ({connectedLinks.length})
          </span>
          {connectedLinks.length === 0 ? (
            <p className="text-muted text-xs">No links recorded for this device.</p>
          ) : (
            <div className="space-y-1">
              {connectedLinks.map((link, i) => {
                const isSource = link.source === device.ip
                const remote = isSource ? link.target : link.source
                const remoteName = shortName(isSource ? link.target_hostname : link.source_hostname) || remote
                const localIface = shortenInterface(isSource ? link.source_interface : link.target_interface)
                const remoteIface = shortenInterface(isSource ? link.target_interface : link.source_interface)

                return (
                  <div key={i} className="bg-surface-2 rounded px-3 py-2">
                    <p className="text-text-primary text-xs">
                      Connected to <span className="font-semibold">{remoteName}</span>
                    </p>
                    {localIface && remoteIface && (
                      <p className="text-muted text-[11px] font-mono mt-0.5">
                        {localIface} &harr; {remoteIface}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="border-t border-border pt-3">
          <button
            onClick={() => setShowTech((s) => !s)}
            className="flex items-center gap-2 text-xs font-medium text-muted hover:text-text-primary transition-colors w-full text-left"
          >
            <span className={`inline-block transition-transform ${showTech ? 'rotate-90' : ''}`}>&#9656;</span>
            Technical details
          </button>
          {showTech && (
            <div className="mt-3 space-y-1.5 text-xs">
              {device.snmp_identified && (
                <div className="flex justify-between">
                  <span className="text-muted">SNMP identified</span>
                  <span className="text-text-secondary">yes</span>
                </div>
              )}
              {device.snmp_community && (
                <div className="flex justify-between">
                  <span className="text-muted">SNMP community</span>
                  <span className="text-text-secondary font-mono">{device.snmp_community}</span>
                </div>
              )}
              {device.snmp_debug?.error && (
                <div className="flex justify-between">
                  <span className="text-muted">SNMP error</span>
                  <span className="text-text-secondary">{device.snmp_debug.error}</span>
                </div>
              )}
              {connectedLinks.map((link, i) => (
                <div key={i} className="flex justify-between gap-2">
                  <span className="text-muted">Protocol</span>
                  <span className="text-text-secondary uppercase">{link.protocol}</span>
                </div>
              ))}
              {device.catalyst_id && (
                <div className="flex justify-between gap-2">
                  <span className="text-muted">Catalyst ID</span>
                  <span className="text-text-secondary font-mono truncate">{device.catalyst_id}</span>
                </div>
              )}
              {device.first_seen && (
                <div className="flex justify-between gap-2">
                  <span className="text-muted">First seen</span>
                  <span className="text-text-secondary">{device.first_seen.slice(0, 16).replace('T', ' ')}</span>
                </div>
              )}
              {device.last_seen && (
                <div className="flex justify-between gap-2">
                  <span className="text-muted">Last seen</span>
                  <span className="text-text-secondary">{device.last_seen.slice(0, 16).replace('T', ' ')}</span>
                </div>
              )}
              {device.interfaces && device.interfaces.length > 0 && (
                <div>
                  <span className="text-muted block mb-1">Interfaces ({device.interfaces.length})</span>
                  <ul className="text-text-secondary font-mono space-y-0.5 max-h-28 overflow-y-auto">
                    {device.interfaces.map((itf, i) => (
                      <li key={i}>{itf.ifName || itf.ifDescr}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
