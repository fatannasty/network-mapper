import { type Device } from '../api'

interface Props {
  device: Device
  onClose: () => void
}

const statusColors: Record<string, string> = {
  up: 'text-green-400',
  down: 'text-red-400',
}

export default function DeviceDetail({ device, onClose }: Props) {
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
            <p className="text-white">{device.ip}</p>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Type</span>
            <p className="text-white capitalize">{device.device_type || 'unknown'}</p>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Vendor</span>
            <p className="text-white">{device.vendor || '—'}</p>
          </div>
          <div>
            <span className="text-gray-500 text-xs">Model</span>
            <p className="text-white">{device.model || '—'}</p>
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
