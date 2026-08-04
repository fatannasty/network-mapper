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
    <div className="w-80 bg-gray-900 border-l border-gray-800 overflow-y-auto shrink-0">
      <div className="sticky top-0 bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between">
        <h3 className="font-semibold text-white text-sm truncate">
          {device.hostname || device.ip}
        </h3>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-white text-lg leading-none"
        >
          &times;
        </button>
      </div>

      <div className="p-4 space-y-4">
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <span className="text-gray-500 text-xs">IP</span>
            <p className="text-white font-mono">{device.ip}</p>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Type</span>
            <p className="text-white capitalize">{device.device_type || 'unknown'}</p>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Vendor</span>
            <p className="text-white">{device.vendor || '\u2014'}</p>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Model</span>
            <p className="text-white">{device.model || '\u2014'}</p>
          </div>
        </div>

        {device.snmp_identified && (
          <div className="bg-blue-900/30 border border-blue-800 rounded px-3 py-2 text-xs">
            <span className="text-blue-400 font-medium">SNMP identified</span>
            {device.snmp_community && (
              <span className="text-gray-400 ml-2">({device.snmp_community})</span>
            )}
          </div>
        )}

        {connectedLinks.length > 0 && (
          <div>
            <span className="text-gray-500 text-xs block mb-2">
              Connections ({connectedLinks.length})
            </span>
            <div className="space-y-1">
              {connectedLinks.map((link, i) => {
                const isSource = link.source === device.ip
                const localIface = isSource ? link.source_interface : link.target_interface
                const remoteIface = isSource ? link.target_interface : link.source_interface
                const remote = isSource ? link.target : link.source
                const remoteName = isSource ? link.target_hostname : link.source_hostname

                return (
                  <div key={i} className="bg-gray-800 rounded px-3 py-2 text-xs">
                    <div className="flex items-center gap-1 text-gray-400">
                      <span className="px-1 py-0.5 rounded text-[10px] font-bold uppercase bg-gray-700">
                        {link.protocol}
                      </span>
                      <span className="text-white font-mono">{localIface || '\u2014'}</span>
                      <span className="text-gray-600">\u2194</span>
                      <span className="text-white font-mono">{remoteIface || '\u2014'}</span>
                    </div>
                    <div className="text-gray-500 mt-1">
                      to{' '}
                      <span className="text-gray-300">{remoteName || remote}</span>
                      {remoteName && remote !== remoteName && (
                        <span className="text-gray-500 ml-1 font-mono">({remote})</span>
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
            <span className="text-gray-500 text-xs block mb-1">Open Ports</span>
            <div className="flex flex-wrap gap-1">
              {device.open_ports.map((p) => (
                <span key={p} className="px-2 py-0.5 bg-gray-800 rounded text-xs text-gray-300">
                  {p}
                </span>
              ))}
            </div>
          </div>
        )}

        {device.interfaces.length > 0 && (
          <div>
            <span className="text-gray-500 text-xs block mb-2">
              Interfaces ({device.interfaces.length})
            </span>
            <div className="space-y-1">
              {device.interfaces.map((iface) => (
                <div
                  key={iface.ifIndex}
                  className="bg-gray-800 rounded px-3 py-2 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-white font-medium truncate">
                      {iface.ifDescr || iface.ifName || `if${iface.ifIndex}`}
                    </span>
                    <span className={statusColors[iface.ifOperStatus] || 'text-gray-400'}>
                      {iface.ifOperStatus}
                    </span>
                  </div>
                  <div className="text-gray-500 mt-0.5 flex gap-3">
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
