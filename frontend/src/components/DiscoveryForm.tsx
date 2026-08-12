import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { discover, getCredentials, type ScanResult, type Credential } from '../api'
import PageHeader from './ui/PageHeader'
import Input from './ui/Input'
import Button from './ui/Button'

const COMMON_COMMUNITIES = ['public', 'private', 'cisco', 'admin', 'snmp', 'read', 'write', 'monitor']

export default function DiscoveryForm() {
  const [subnet, setSubnet] = useState('127.0.0.1/32')
  const [communitiesText, setCommunitiesText] = useState('public')
  const [snmpPort, setSnmpPort] = useState('161')
  const [snmpv3, setSnmpv3] = useState(false)
  const [username, setUsername] = useState('')
  const [authPass, setAuthPass] = useState('')
  const [privPass, setPrivPass] = useState('')
  const [loading, setLoading] = useState(false)
  const [verbose, setVerbose] = useState(false)
  const [excludePcs, setExcludePcs] = useState(true)
  const [result, setResult] = useState<ScanResult | null>(null)
  const [error, setError] = useState('')
  const [credNotice, setCredNotice] = useState('')
  const [credentials, setCredentials] = useState<Credential[]>([])
  const navigate = useNavigate()

  useEffect(() => {
    getCredentials().then((d) => setCredentials(d.credentials || [])).catch(() => {})
  }, [])

  const communities = communitiesText
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean)

  const applyCredentials = (cred: Credential) => {
    if (cred.credential_type === 'snmp' && cred.snmp_community) {
      setCommunitiesText(cred.snmp_community)
      setSnmpv3(false)
    } else if (cred.credential_type === 'snmpv3') {
      setUsername(cred.username || '')
      setSnmpv3(true)
    }
    setCredNotice(`Applied ${cred.name}${cred.site ? ` · Site: ${cred.site}` : ''}`)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const v3 = snmpv3
        ? { username, auth_protocol: 'sha', auth_password: authPass, privacy_protocol: 'aes', privacy_password: privPass || authPass }
        : undefined
      const data = await discover(subnet, communities, parseInt(snmpPort) || 161, v3, verbose, excludePcs)
      setResult(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Discovery failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full overflow-auto p-6 flex justify-center">
      <div className="w-full max-w-lg">
        <PageHeader
          title="Discover Network"
          description="SNMP scan a subnet to discover devices and topology links."
        />
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-muted text-sm mb-1">Subnet (CIDR)</label>
            <Input
              value={subnet}
              onChange={(e) => setSubnet(e.target.value)}
              className="w-full"
              placeholder="10.0.0.0/24"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-muted text-sm mb-1">SNMP Port</label>
              <Input
                value={snmpPort}
                onChange={(e) => setSnmpPort(e.target.value)}
                type="number"
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-muted text-sm mb-1">&nbsp;</label>
              <Button
                type="button"
                variant="secondary"
                size="md"
                onClick={() => setCommunitiesText(COMMON_COMMUNITIES.join('\n'))}
                className="w-full"
              >
                Try Common Communities
              </Button>
            </div>
          </div>

          <div>
            <label className="block text-muted text-sm mb-1">
              SNMP Communities (one per line or comma-separated)
            </label>
            <textarea
              value={communitiesText}
              onChange={(e) => setCommunitiesText(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-text-primary focus:outline-none focus:border-accent font-mono text-sm resize-y"
              placeholder="public&#10;private&#10;cisco"
            />
          </div>

          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 text-sm text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={snmpv3}
                onChange={(e) => setSnmpv3(e.target.checked)}
                className="rounded"
              />
              Use SNMPv3
            </label>
            <label className="flex items-center gap-2 text-sm text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={verbose}
                onChange={(e) => setVerbose(e.target.checked)}
                className="rounded"
              />
              Verbose logging
            </label>
            <label className="flex items-center gap-2 text-sm text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={excludePcs}
                onChange={(e) => setExcludePcs(e.target.checked)}
                className="rounded"
              />
              Exclude PCs/printers
            </label>
          </div>

          {snmpv3 && (
            <div className="space-y-3 pl-2 border-l-2 border-border">
              <input
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-text-primary focus:outline-none focus:border-accent"
              />
              <input
                type="password"
                placeholder="Auth password"
                value={authPass}
                onChange={(e) => setAuthPass(e.target.value)}
                className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-text-primary focus:outline-none focus:border-accent"
              />
              <input
                type="password"
                placeholder="Privacy password (optional)"
                value={privPass}
                onChange={(e) => setPrivPass(e.target.value)}
                className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-text-primary focus:outline-none focus:border-accent"
              />
            </div>
          )}

          {credentials.length > 0 && (
            <div>
              <label className="block text-muted text-sm mb-1">Saved Credentials</label>
              <div className="flex flex-wrap gap-1">
                {credentials.map((cred) => (
                  <button
                    key={cred.id}
                    type="button"
                    onClick={() => applyCredentials(cred)}
                    className="px-2 py-1 bg-surface-2 border border-border rounded text-xs text-text-secondary hover:bg-surface-3 transition-colors"
                    title={cred.credential_type === 'snmpv3' ? `SNMPv3 user: ${cred.username}` : `Community: ${cred.snmp_community}`}
                  >
                    {cred.name}
                  </button>
                ))}
              </div>
              {credNotice && <p className="text-xs text-accent mt-1.5">{credNotice}</p>}
            </div>
          )}

          <Button
            type="submit"
            disabled={loading}
            className="w-full"
          >
            {loading ? 'Scanning...' : 'Start Discovery'}
          </Button>

          {error && (
            <div className="bg-red-950/60 backdrop-blur border border-red-800/50 rounded-xl p-4">
              <p className="text-red-300">{error}</p>
            </div>
          )}

          {result && (
            <div className="bg-surface-2/60 backdrop-blur border border-border/40 rounded-2xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-green-400 font-medium text-sm">Scan Complete</span>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => navigate(`/topology?scan_id=${result.scan_id}`)}
                >
                  View Topology
                </Button>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-surface-1 rounded p-2">
                  <span className="text-muted">Subnet</span>
                  <p className="text-text-primary font-mono">{result.subnet}</p>
                </div>
                <div className="bg-surface-1 rounded p-2">
                  <span className="text-muted">Hosts Scanned</span>
                  <p className="text-text-primary">{result.scanned_hosts}</p>
                </div>
                <div className="bg-surface-1 rounded p-2">
                  <span className="text-muted">Alive</span>
                  <p className="text-green-400">{result.alive_hosts}</p>
                </div>
                <div className="bg-surface-1 rounded p-2">
                  <span className="text-muted">Devices Found</span>
                  <p className="text-text-primary">{result.device_count}</p>
                </div>
                <div className={`bg-surface-1 rounded p-2 ${result.snmp_identified > 0 ? 'border border-blue-800' : ''}`}>
                  <span className="text-muted">SNMP Identified</span>
                  <p className={result.snmp_identified > 0 ? 'text-blue-400' : 'text-gray-600'}>
                    {result.snmp_identified}
                  </p>
                </div>
                <div className={`bg-surface-1 rounded p-2 ${result.connections.length > 0 ? 'border border-amber-800' : ''}`}>
                  <span className="text-muted">Links Found</span>
                  <p className={result.connections.length > 0 ? 'text-amber-400' : 'text-gray-600'}>
                    {result.connections.length}
                  </p>
                </div>
              </div>

              {result.snmp_identified > 0 && (
                <div>
                  <span className="text-muted text-xs block mb-1">SNMP Devices</span>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {result.devices
                      .filter((d) => d.snmp_identified)
                      .map((d) => (
                        <div key={d.ip} className="bg-surface-1 rounded px-2 py-1 text-xs flex items-center gap-2">
                          <span className="text-blue-400 font-mono">{d.ip}</span>
                          <span className="text-text-primary">{d.hostname || '\u2014'}</span>
                          {d.snmp_community && (
                            <span className="text-muted">({d.snmp_community})</span>
                          )}
                          {d.vendor && (
                            <span className="text-muted ml-auto">{d.vendor}</span>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {result.snmp_identified === 0 && result.alive_hosts > 0 && (
                <div className="bg-amber-900/30 border border-amber-800 rounded p-3 text-xs text-amber-300">
                  No devices responded to SNMP with the provided communities.
                  Try adding more community strings or check SNMP credentials.
                </div>
              )}

              {verbose && (
                <div>
                  <span className="text-muted text-xs block mb-1">SNMP Debug Log</span>
                  <div className="space-y-1 max-h-60 overflow-y-auto">
                    {result.devices.map((d) => {
                      const dbg = d.snmp_debug
                      if (!dbg) return null
                      return (
                        <div key={d.ip} className="bg-surface-1 rounded px-2 py-1.5 text-xs font-mono">
                          <div className="flex items-center gap-2">
                            <span className="text-text-secondary">{d.ip}</span>
                            <span className={dbg.port_open ? 'text-green-400' : 'text-red-400'}>
                              port {dbg.port_open ? 'open' : 'closed'}
                            </span>
                            {dbg.community_used && (
                              <span className="text-blue-400">{dbg.community_used}</span>
                            )}
                          </div>
                          {dbg.hostname && (
                            <div className="text-muted mt-0.5">
                              hostname: {dbg.hostname}
                              {dbg.hostname_source && <span className="text-gray-600 ml-1">({dbg.hostname_source})</span>}
                            </div>
                          )}
                          {dbg.error && (
                            <div className="text-red-400 mt-0.5">{dbg.error}</div>
                          )}
                          {dbg.vendor && (
                            <div className="text-gray-600 mt-0.5 truncate">{dbg.vendor}</div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
