import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { shortenInterface } from './ui/iface'
import Button from './ui/Button'
import { getDeviceConfigs, getConfigDiff, type Device, type ConfigEntry, type ConfigDiffRow, type TopoLink } from '../api'
import { friendlyType, typeDescription, shortName } from '../features/topology/services/friendly'

function fmtTs(value?: string | null): string {
  if (!value) return '\u2014'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

interface Props {
  device: Device
  connectedLinks: TopoLink[]
  allDevices?: Device[]
  allLinks?: TopoLink[]
  onClose: () => void
}

export default function DeviceDetail({ device, connectedLinks, allDevices, allLinks, onClose }: Props) {
  const [showTech, setShowTech] = useState(false)
  const [configs, setConfigs] = useState<ConfigEntry[]>([])
  const [configsOpen, setConfigsOpen] = useState(false)
  const [diff, setDiff] = useState<{ added: number; removed: number; changed: boolean; diff: ConfigDiffRow[] } | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [fromId, setFromId] = useState(0)
  const [toId, setToId] = useState(0)
  const navigate = useNavigate()
  const type = friendlyType(device.device_type)
  const name = shortName(device.hostname) || device.ip

  useEffect(() => {
    setConfigs([])
    setDiff(null)
    setConfigsOpen(false)
    if (!device.id) return
    let cancelled = false
    getDeviceConfigs(device.id)
      .then((cs) => {
        if (cancelled) return
        setConfigs(cs)
        if (cs.length >= 2) {
          setFromId(cs[1].id)
          setToId(cs[0].id)
        }
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [device.id])

  useEffect(() => {
    if (!configsOpen || fromId === 0 || toId === 0 || !device.id) return
    let cancelled = false
    setDiffLoading(true)
    getConfigDiff(device.id, fromId, toId)
      .then((d) => { if (!cancelled) setDiff(d) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setDiffLoading(false) })
    return () => { cancelled = true }
  }, [configsOpen, fromId, toId, device.id])

  // Deduplicate connected devices
  const connectedDevices = connectedLinks.reduce<{ ip: string; hostname: string; protocol: string; iface: string }[]>((acc, link) => {
    const isSource = link.source === device.ip
    const remote = isSource ? link.target : link.source
    if (acc.some((d) => d.ip === remote)) return acc
    const remoteName = shortName(isSource ? link.target_hostname : link.source_hostname) || remote
    const localIface = shortenInterface(isSource ? link.source_interface : link.target_interface)
    acc.push({ ip: remote, hostname: remoteName, protocol: link.protocol, iface: localIface })
    return acc
  }, [])

  // Same-site devices with topology status
  const sameSiteDevices = useMemo(() => {
    if (!device.site || !allDevices) return []
    const linkSet = new Set<string>()
    if (allLinks) {
      for (const l of allLinks) {
        linkSet.add(l.source)
        linkSet.add(l.target)
      }
    }
    return allDevices
      .filter((d) => d.site === device.site && d.ip !== device.ip)
      .slice(0, 20)
      .map((d) => ({
        ...d,
        hasTopology: linkSet.has(d.ip),
      }))
  }, [device.site, device.ip, allDevices, allLinks])

  return (
    <div className="w-80 bg-surface-1/80 backdrop-blur-2xl border-l border-border/30 overflow-y-auto shrink-0">
      <div className="sticky top-0 bg-surface-1/80 backdrop-blur-2xl border-b border-border/30 px-4 py-3 flex items-center justify-between gap-2 z-10">
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
        {/* Core info */}
        <div className="grid grid-cols-2 gap-3 text-sm">
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
          <div>
            <span className="text-muted text-xs">Hostname</span>
            <p className="text-text-primary truncate">{device.hostname || '\u2014'}</p>
          </div>
        </div>

        {/* Location / Site */}
        {device.site && (
          <div className="bg-accent-subtle/40 rounded-xl px-3 py-2">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-accent shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 0115 0z" />
              </svg>
              <span className="text-xs text-text-primary font-medium">{device.site}</span>
            </div>
          </div>
        )}

        {/* Type description */}
        <div className="bg-surface-2/60 backdrop-blur-xl rounded-xl px-3 py-2.5">
          <p className="text-xs text-text-secondary leading-relaxed">
            <span className="text-text-primary font-semibold">{type}:</span>{' '}
            {typeDescription(device.device_type)}
          </p>
        </div>

        {/* VLAN 90 flag */}
        {device.vlan_90 === true && (
          <div className="bg-teal-500/15 border border-teal-500/30 rounded-xl px-3 py-2">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-teal-300 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 5a2 2 0 012-2h12a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V5zM8 9h8M8 13h8M8 17h4" />
              </svg>
              <span className="text-xs text-teal-200 font-medium">VLAN 90 configured</span>
            </div>
          </div>
        )}

        {/* Topology connections */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-muted text-xs">
              Connections ({connectedDevices.length})
            </span>
            {connectedDevices.length > 0 && (
              <button
                onClick={() => {
                  const scanId = device.last_scan_id
                  const url = scanId
                    ? `/topology?scan_id=${scanId}&device=${encodeURIComponent(device.ip)}`
                    : '/topology'
                  navigate(url)
                }}
                className="text-[11px] text-accent hover:text-accent-hover transition-colors"
              >
                View in Topology &rarr;
              </button>
            )}
          </div>

          {connectedDevices.length === 0 ? (
            <div className="bg-surface-2/60 backdrop-blur-xl rounded-xl px-3 py-3 text-center">
              <svg className="w-8 h-8 text-muted/40 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              <p className="text-xs text-muted">No link connections recorded yet.</p>
              <p className="text-[11px] text-muted/70 mt-1">
                Run a backfill scan or import with neighbor enrichment to discover connections.
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {connectedDevices.map((conn) => (
                <button
                  key={conn.ip}
                  onClick={() => navigate(`/topology?scan_id=${device.last_scan_id || ''}&device=${encodeURIComponent(conn.ip)}`)}
                  className="w-full bg-surface-2/60 backdrop-blur-xl rounded-xl px-3 py-2 text-left hover:bg-surface-3/60 border border-border/30 transition-all duration-150 group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-text-primary text-xs font-medium truncate">{conn.hostname}</span>
                    <span className="text-muted text-[11px] font-mono">{conn.ip}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="px-1.5 py-0.5 rounded-xl text-[10px] font-bold uppercase bg-surface-3/60 backdrop-blur text-muted">
                      {conn.protocol}
                    </span>
                    {conn.iface && (
                      <span className="text-[11px] text-muted font-mono">{conn.iface}</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Topology status */}
        <div className="bg-surface-2/60 backdrop-blur-xl rounded-xl px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted">Topology status</span>
            <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${connectedDevices.length > 0 ? 'text-green-400' : 'text-amber-400'}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${connectedDevices.length > 0 ? 'bg-green-400' : 'bg-amber-400'}`} />
              {connectedDevices.length > 0 ? 'Integrated' : 'No connections'}
            </span>
          </div>
          {device.last_scan_id && (
            <div className="flex items-center justify-between mt-1.5">
              <span className="text-xs text-muted">Scan ID</span>
              <span className="text-[11px] text-text-secondary font-mono">{device.last_scan_id.slice(0, 12)}</span>
            </div>
          )}
          {device.first_seen && (
            <div className="flex items-center justify-between mt-1">
              <span className="text-xs text-muted">First seen</span>
              <span className="text-[11px] text-text-secondary">{device.first_seen.slice(0, 16).replace('T', ' ')}</span>
            </div>
          )}
          {device.last_seen && (
            <div className="flex items-center justify-between mt-1">
              <span className="text-xs text-muted">Last seen</span>
              <span className="text-[11px] text-text-secondary">{device.last_seen.slice(0, 16).replace('T', ' ')}</span>
            </div>
          )}
        </div>

        {/* Prominent topology button when no connections but device is in a scan */}
        {connectedDevices.length === 0 && device.last_scan_id && (
          <Button
            variant="secondary"
            size="sm"
            className="w-full"
            onClick={() => navigate(`/topology?scan_id=${device.last_scan_id}`)}
          >
            View in Topology
          </Button>
        )}

        {/* Same-site devices with topology status */}
        {sameSiteDevices.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-muted text-xs">
                Same site ({device.site}) &middot; {sameSiteDevices.length} devices
              </span>
              <span className="text-[11px] text-muted/70">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block mr-1 align-middle" />
                in topology
              </span>
            </div>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {sameSiteDevices.map((d) => (
                <button
                  key={d.ip}
                  onClick={() => {
                    const scanId = d.last_scan_id || device.last_scan_id
                    navigate(scanId ? `/topology?scan_id=${scanId}&device=${encodeURIComponent(d.ip)}` : `/topology`)
                  }}
                  className="w-full flex items-center justify-between gap-2 bg-surface-2/60 backdrop-blur-xl rounded-xl px-3 py-1.5 text-xs hover:bg-surface-3/60 border border-border/30 transition-all duration-150 text-left"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${d.hasTopology ? 'bg-green-400' : 'bg-gray-600'}`} />
                    <span className="text-text-primary font-mono truncate">{shortName(d.hostname) || d.ip}</span>
                  </div>
                  <span className="text-muted text-[11px] shrink-0">{d.ip}</span>
                </button>
              ))}
              {sameSiteDevices.length >= 20 && (
                <p className="text-[11px] text-muted text-center py-1">Showing first 20</p>
              )}
            </div>
          </div>
        )}

        {/* Technical details */}
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
              {device.catalyst_id && (
                <div className="flex justify-between">
                  <span className="text-muted">Catalyst ID</span>
                  <span className="text-text-secondary font-mono truncate">{device.catalyst_id}</span>
                </div>
              )}
              {device.confidence > 0 && (
                <div className="flex justify-between">
                  <span className="text-muted">Confidence</span>
                  <span className="text-text-secondary">{device.confidence}/5</span>
                </div>
              )}
              {connectedLinks.length > 0 && (
                <div>
                  <span className="text-muted block mb-1">Link protocols</span>
                  <div className="flex flex-wrap gap-1">
                    {[...new Set(connectedLinks.map((l) => l.protocol))].map((proto) => (
                      <span key={proto} className="px-1.5 py-0.5 rounded-xl text-[10px] font-bold uppercase bg-surface-3/60 backdrop-blur border border-border/30 text-muted">
                        {proto}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {device.interfaces && device.interfaces.length > 0 && (
                <div>
                  <span className="text-muted block mb-1">Interfaces ({device.interfaces.length})</span>
                  <ul className="text-text-secondary font-mono space-y-0.5 max-h-28 overflow-y-auto">
                    {device.interfaces.map((itf, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <span>{itf.ifName || itf.ifDescr}</span>
                        {itf.vlanId != null && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-teal-500/15 text-teal-300">
                            VLAN {itf.vlanId}{itf.vlanName ? ` · ${itf.vlanName}` : ''}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Config history + diff */}
        <div>
          <button
            onClick={() => setConfigsOpen(!configsOpen)}
            className="w-full flex items-center justify-between text-xs text-muted hover:text-text-primary"
          >
            <span>Config history ({configs.length})</span>
            <span className="text-muted">{configsOpen ? '\u25be' : '\u25b8'}</span>
          </button>
          {configsOpen && (
            <div className="mt-2 space-y-2">
              {configs.length === 0 && (
                <p className="text-xs text-muted">No configs collected yet. Use Inventory &rarr; Collect Configs.</p>
              )}
              {configs.length >= 2 && (
                <div className="flex items-center gap-2 text-xs">
                  <select
                    value={fromId}
                    onChange={(e) => setFromId(Number(e.target.value))}
                    className="flex-1 px-2 py-1 bg-surface-2/60 border border-border/40 rounded-lg text-text-primary text-xs"
                    aria-label="Older config"
                  >
                    {configs.map((c) => <option key={c.id} value={c.id}>{fmtTs(c.collected_at)}</option>)}
                  </select>
                  <span className="text-muted shrink-0">&rarr;</span>
                  <select
                    value={toId}
                    onChange={(e) => setToId(Number(e.target.value))}
                    className="flex-1 px-2 py-1 bg-surface-2/60 border border-border/40 rounded-lg text-text-primary text-xs"
                    aria-label="Newer config"
                  >
                    {configs.map((c) => <option key={c.id} value={c.id}>{fmtTs(c.collected_at)}</option>)}
                  </select>
                </div>
              )}
              {diffLoading && <p className="text-xs text-muted">Comparing&hellip;</p>}
              {!diffLoading && diff && (
                <>
                  <div className="text-[11px] font-mono leading-snug rounded-xl border border-border/30 bg-black/30 max-h-64 overflow-auto">
                    {diff.diff.map((row, i) => (
                      <div key={i} className={`px-2 py-0.5 whitespace-pre-wrap ${
                        row.type === 'add' ? 'bg-green-500/15 text-green-300'
                          : row.type === 'del' ? 'bg-red-500/15 text-red-300'
                            : row.type === 'meta' ? 'text-muted' : 'text-text-secondary'
                      }`}>{row.text}</div>
                    ))}
                  </div>
                  <p className="text-xs text-muted">
                    {diff.changed ? `+${diff.added} \u2212${diff.removed} lines changed` : 'No differences between these configs.'}
                  </p>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
