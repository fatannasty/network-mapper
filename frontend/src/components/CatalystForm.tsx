import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { AxiosError } from 'axios'
import { importFromCatalyst, testCatalyst, fetchSites, debugSiteMembership, type SiteInfo } from '../api'

function errDetail(err: unknown): string {
  if (err instanceof AxiosError && err.response?.data) {
    const d = err.response.data as Record<string, unknown>
    if (typeof d.detail === 'string') return d.detail
    return JSON.stringify(d).slice(0, 2000)
  }
  return err instanceof Error ? err.message : String(err)
}

export default function CatalystForm() {
  const [baseUrl, setBaseUrl] = useState('https://')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState(false)
  const [debuggingMembership, setDebuggingMembership] = useState(false)
  const [membershipDebug, setMembershipDebug] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [result, setResult] = useState<{ scan_id: string; device_count: number; links_found: number; debug?: Record<string, unknown> } | null>(null)
  const [error, setError] = useState('')

  const [sites, setSites] = useState<SiteInfo[]>([])
  const [loadingSites, setLoadingSites] = useState(false)
  const [sitesDebug, setSitesDebug] = useState<string | null>(null)
  const [selectedSite, setSelectedSite] = useState('')
  const [siteText, setSiteText] = useState('')
  const [deviceFilter, setDeviceFilter] = useState('')
  const navigate = useNavigate()

  const loadSites = async () => {
    setLoadingSites(true)
    setSitesDebug(null)
    try {
      const data = await fetchSites(baseUrl, username, password)
      setSites(data.sites || [])
      if (data.debug && data.debug.samples) {
        setSitesDebug(JSON.stringify(data.debug.samples, null, 2))
      }
    } catch {
      setSites([])
    } finally {
      setLoadingSites(false)
    }
  }

  useEffect(() => { setSites([]); setSelectedSite(''); setSiteText('') }, [baseUrl])

  const selectedSiteName = sites.find((s) => s.site_id === selectedSite)?.name || ''
  const siteFilter = selectedSiteName || siteText

  const handleDebugMembership = async () => {
    if (!selectedSite) return
    setDebuggingMembership(true)
    setMembershipDebug(null)
    setError('')
    try {
      const data = await debugSiteMembership(baseUrl, username, password, selectedSite)
      setMembershipDebug(JSON.stringify(data, null, 2))
    } catch (err: unknown) {
      setMembershipDebug(null)
      setError(errDetail(err))
    } finally {
      setDebuggingMembership(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const data = await importFromCatalyst(
        baseUrl, username, password,
        siteFilter || undefined, selectedSite || undefined, deviceFilter || undefined)
      setResult(data)
    } catch (err: unknown) {
      setError(errDetail(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full overflow-auto p-6 flex justify-center">
      <div className="w-full max-w-lg">
        <h2 className="text-xl font-bold mb-2">Import from Catalyst Center</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-400 text-sm mb-1">Catalyst Center URL</label>
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
              placeholder="https://catalyst-center.example.com"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-gray-400 text-sm mb-1">Username</label>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-gray-400 text-sm mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-gray-400 text-sm">Site Filter</label>
              <button
                type="button"
                disabled={loadingSites}
                onClick={loadSites}
                className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50"
              >
                {loadingSites ? 'Loading...' : 'Load Sites'}
              </button>
            </div>

            {sites.length > 0 ? (
              <select
                value={selectedSite}
                onChange={(e) => setSelectedSite(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="">All Sites</option>
                {sites.map((s) => (
                  <option key={s.site_id} value={s.site_id}>
                    {s.hierarchy || s.name}
                  </option>
                ))}
              </select>
            ) : (
              <input
                value={siteText}
                onChange={(e) => setSiteText(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
                placeholder="Type site name or hostname pattern"
              />
            )}
            <p className="text-gray-600 text-[11px] mt-0.5">
              {sites.length > 0
                ? `${sites.length} sites loaded. Filter matches location, hierarchy, or hostname.`
                : `Click "Load Sites" to fetch from Catalyst Center, or type a hostname pattern.`}
            </p>
          </div>

          {sitesDebug && (
            <details className="border border-gray-800 rounded bg-gray-950">
              <summary className="px-3 py-2 text-xs text-gray-400 cursor-pointer hover:text-gray-300">
                Raw site API samples
              </summary>
              <pre className="px-3 pb-3 text-[11px] text-gray-400 overflow-auto max-h-64 whitespace-pre-wrap">
                {sitesDebug}
              </pre>
            </details>
          )}

          <div>
            <label className="block text-gray-400 text-sm mb-1">
              Device filter <span className="text-gray-600">(hostname / model / IP substring)</span>
            </label>
            <input
              value={deviceFilter}
              onChange={(e) => setDeviceFilter(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
              placeholder="e.g. AMT-, 610, or 10.10.1.20"
            />
            <p className="text-gray-600 text-[11px] mt-0.5">
              Imports only matching devices plus all links touching them.
            </p>
          </div>

          {selectedSite && (
            <button
              type="button"
              disabled={debuggingMembership}
              onClick={handleDebugMembership}
              className="w-full px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 border border-gray-700 rounded text-sm transition-colors"
            >
              {debuggingMembership ? 'Querying membership API...' : 'Debug Site Membership'}
            </button>
          )}
          {membershipDebug && (
            <pre className="bg-gray-950 border border-gray-800 rounded p-3 text-[11px] text-gray-300 overflow-auto max-h-96 whitespace-pre-wrap">
              {membershipDebug}
            </pre>
          )}

          <div className="flex gap-3">
            <button
              type="button"
              disabled={testing}
              onClick={async () => {
                setTesting(true)
                setTestResult(null)
                try {
                  const r = await testCatalyst(baseUrl, username, password)
                  setTestResult(`Connected! Found ${r.device_count} devices.`)
                } catch (err: unknown) {
                  setTestResult(errDetail(err))
                } finally {
                  setTesting(false)
                }
              }}
              className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white rounded text-sm transition-colors"
            >
              {testing ? 'Testing...' : 'Test Connection'}
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-2 rounded font-medium transition-colors"
            >
              {loading ? 'Importing...' : 'Import'}
            </button>
          </div>

          {testResult && (
            <div className={`rounded p-3 text-xs ${testResult.startsWith('Connected') ? 'bg-green-900/50 border border-green-800 text-green-300' : 'bg-red-900/50 border border-red-800 text-red-300'}`}>
              {testResult}
            </div>
          )}

          {error && (
            <div className="bg-red-900/50 border border-red-800 rounded p-4">
              <p className="text-red-300 text-sm">{error}</p>
            </div>
          )}

          {result && (
            <div className="bg-green-900/50 border border-green-800 rounded p-4 space-y-3">
              <p className="text-green-300 text-sm">
                Imported {result.device_count} devices, {result.links_found} topology links.
              </p>
              <button
                type="button"
                onClick={() => navigate(`/topology?scan_id=${result.scan_id}`)}
                className="px-4 py-1.5 bg-green-700 hover:bg-green-600 text-white rounded text-sm transition-colors"
              >
                View Topology
              </button>
              {result.debug && (
                <pre className="text-xs text-green-300 bg-black/30 p-2 rounded max-h-60 overflow-auto whitespace-pre-wrap">
                  {JSON.stringify(result.debug, null, 2)}
                </pre>
              )}
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
