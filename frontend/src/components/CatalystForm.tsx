import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { importFromCatalyst, testCatalyst, fetchSites, type SiteInfo } from '../api'

export default function CatalystForm() {
  const [baseUrl, setBaseUrl] = useState('https://')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [result, setResult] = useState<{ scan_id: string; device_count: number; links_found: number; debug?: Record<string, unknown> } | null>(null)
  const [error, setError] = useState('')

  const [sites, setSites] = useState<SiteInfo[]>([])
  const [loadingSites, setLoadingSites] = useState(false)
  const [selectedState, setSelectedState] = useState('')
  const [selectedCity, setSelectedCity] = useState('')
  const navigate = useNavigate()

  const states = [...new Set(sites.map((s) => s.state).filter(Boolean))].sort()
  const cities = (selectedState
    ? [...new Set(sites.filter((s) => s.state === selectedState).map((s) => s.city).filter(Boolean))]
    : [...new Set(sites.map((s) => s.city).filter(Boolean))]
  ).sort()

  const loadSites = async () => {
    setLoadingSites(true)
    try {
      const data = await fetchSites(baseUrl, username, password)
      setSites(data.sites || [])
    } catch {
      setSites([])
    } finally {
      setLoadingSites(false)
    }
  }

  useEffect(() => { setSites([]); setSelectedState(''); setSelectedCity('') }, [baseUrl])

  const siteFilter = selectedCity || selectedState

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const data = await importFromCatalyst(baseUrl, username, password, siteFilter || undefined)
      setResult(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Import failed')
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
              <div className="grid grid-cols-2 gap-3">
                <select
                  value={selectedState}
                  onChange={(e) => { setSelectedState(e.target.value); setSelectedCity('') }}
                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500 text-sm"
                >
                  <option value="">All States</option>
                  {states.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <select
                  value={selectedCity}
                  onChange={(e) => setSelectedCity(e.target.value)}
                  className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500 text-sm"
                  disabled={cities.length === 0}
                >
                  <option value="">All Cities</option>
                  {cities.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            ) : (
              <input
                value={siteFilter}
                onChange={(e) => setSelectedCity(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
                placeholder="Or type a city/state — click Load Sites first"
              />
            )}
            <p className="text-gray-600 text-[11px] mt-0.5">
              {sites.length > 0
                ? `${sites.length} locations loaded. Select state to filter cities.`
                : 'Click "Load Sites" to fetch locations from Catalyst Center.'}
            </p>
          </div>

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
                  setTestResult(err instanceof Error ? err.message : 'Connection failed')
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
