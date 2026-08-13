import { useState, useEffect, type FormEvent } from 'react'
import {
  collectConfigs, collectConfigsCatalyst, apiErrorMessage,
  getDevices, type CollectResult, type Device,
} from '../api'
import Input from './ui/Input'
import Button from './ui/Button'

export default function ConfigCollect() {
  const [sitePattern, setSitePattern] = useState('')
  const [sshUsername, setSshUsername] = useState('')
  const [sshPassword, setSshPassword] = useState('')
  const [sshPort, setSshPort] = useState(22)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CollectResult | null>(null)
  const [error, setError] = useState('')
  const [useCatalyst, setUseCatalyst] = useState(false)
  const [catUrl, setCatUrl] = useState('')
  const [catUsername, setCatUsername] = useState('')
  const [catPassword, setCatPassword] = useState('')

  const [devices, setDevices] = useState<Device[]>([])
  const [deviceQuery, setDeviceQuery] = useState('')
  const [deviceId, setDeviceId] = useState('')

  useEffect(() => {
    let cancelled = false
    getDevices({ limit: '5000' })
      .then((r) => { if (!cancelled) setDevices(r.devices || []) })
      .catch(() => { if (!cancelled) setDevices([]) })
    return () => { cancelled = true }
  }, [])

  const deviceMatches = deviceQuery
    ? devices.filter((d) => `${d.hostname} ${d.ip} ${d.id}`.toLowerCase().includes(deviceQuery.toLowerCase())).slice(0, 50)
    : []

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault(); setLoading(true); setResult(null); setError('')
    const deviceIdNum = deviceId ? Number(deviceId) : undefined
    try {
      setResult(useCatalyst
        ? await collectConfigsCatalyst(catUrl, catUsername, catPassword, 'switch', sitePattern, 50, deviceIdNum)
        : await collectConfigs(sitePattern || undefined, sshUsername, sshPassword, sshPort, deviceIdNum))
    } catch (err: unknown) { setError(apiErrorMessage(err)) }
    finally { setLoading(false) }
  }

  return (
    <div className="flex justify-center">
      <div className="w-full max-w-lg space-y-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-muted mb-1.5">Site pattern <span className="text-muted/50">(hostname substring)</span></label>
              <Input value={sitePattern} onChange={(e) => setSitePattern(e.target.value)} className="w-full" placeholder="e.g. Sanford, Miami, or empty for all" />
            </div>
            <div>
              <label className="block text-xs text-muted mb-1.5">Single device <span className="text-muted/50">(optional)</span></label>
              <Input value={deviceQuery} onChange={(e) => { setDeviceQuery(e.target.value); setDeviceId('') }} className="w-full" placeholder="search hostname or IP" />
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-surface-2/60 backdrop-blur max-h-40 overflow-auto">
            {deviceId ? (
              <div className="px-3 py-2 text-xs flex items-center justify-between">
                <span className="text-green-300">Collecting: {devices.find((d) => String(d.id) === deviceId)?.hostname || devices.find((d) => String(d.id) === deviceId)?.ip || `device #${deviceId}`}</span>
                <button type="button" onClick={() => setDeviceId('')} className="text-muted hover:text-red-400">×</button>
              </div>
            ) : deviceQuery ? (
              deviceMatches.length > 0 ? (
                deviceMatches.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => { setDeviceId(String(d.id)); setDeviceQuery('') }}
                    className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-surface-3/60 text-left"
                  >
                    <span>{d.hostname || d.ip}</span>
                    <span className="text-muted font-mono">{d.ip}</span>
                  </button>
                ))
              ) : (
                <div className="px-3 py-2 text-xs text-muted">No matching devices.</div>
              )
            ) : (
              <div className="px-3 py-2 text-xs text-muted">Search for a device to collect a single config (or leave empty for the site filter above).</div>
            )}
          </div>

          <label className="flex items-center gap-2 bg-surface-2/60 backdrop-blur border border-border/40 rounded-xl px-4 py-3 cursor-pointer transition-all duration-150 hover:bg-surface-2/80">
            <input type="checkbox" checked={useCatalyst} onChange={(e) => setUseCatalyst(e.target.checked)} className="accent-accent" />
            <span className="text-sm">Use Catalyst Center config API</span>
          </label>

          {useCatalyst ? (
            <div className="space-y-3 border border-accent/30 bg-accent/5 backdrop-blur rounded-xl p-4">
              <Input value={catUrl} onChange={(e) => setCatUrl(e.target.value)} className="w-full" placeholder="Catalyst Center URL" />
              <div className="grid grid-cols-2 gap-3">
                <Input value={catUsername} onChange={(e) => setCatUsername(e.target.value)} placeholder="Username" />
                <Input type="password" value={catPassword} onChange={(e) => setCatPassword(e.target.value)} placeholder="Password" />
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-3">
              <Input value={sshUsername} onChange={(e) => setSshUsername(e.target.value)} placeholder="SSH username" />
              <Input type="password" value={sshPassword} onChange={(e) => setSshPassword(e.target.value)} placeholder="SSH password" />
              <Input type="number" value={sshPort} onChange={(e) => setSshPort(Number(e.target.value))} placeholder="Port" />
            </div>
          )}

          <Button type="submit" disabled={loading || (useCatalyst ? !catUrl : false)} className="w-full">
            {loading ? 'Collecting...' : 'Collect Configs'}
          </Button>

          {error && <div className="bg-red-900/40 backdrop-blur border border-red-800/50 rounded-xl p-4 text-sm text-red-300">{error}</div>}

          {result && (
            <div className="bg-surface-2/60 backdrop-blur border border-border/40 rounded-2xl p-4 space-y-2">
              <p className="text-sm text-green-400">{result.success} of {result.total} collected ({result.failed} failed)</p>
              <div className="max-h-72 overflow-auto space-y-1.5">
                {result.results.map((r, i) => (
                  <div key={i} className={`flex items-center justify-between px-3 py-2 rounded-xl text-xs border ${
                    r.status === 'ok' ? 'bg-green-900/20 text-green-300 border-green-800/40'
                    : r.status === 'skipped' ? 'bg-surface-3/50 text-muted border-border/30'
                    : 'bg-red-900/20 text-red-300 border-red-800/40'
                  }`}>
                    <span className="flex flex-col">
                      <span>{r.hostname || r.ip}{r.status === 'ok' && r.config_id ? ` — #${r.config_id}` : ''}</span>
                      {(r.collected_by || r.user) && <span className="text-[10px] opacity-70">by {r.collected_by || r.user}</span>}
                    </span>
                    <span>{r.status === 'ok' ? '✓' : r.status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
