import { useState, useEffect, useMemo, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { AxiosError } from 'axios'
import { importFromCatalyst, testCatalyst, fetchSites, debugSiteMembership, type SiteInfo } from '../api'
import PageHeader from './ui/PageHeader'
import Input from './ui/Input'
import Select from './ui/Select'
import Button from './ui/Button'
import Card from './ui/Card'

function errDetail(err: unknown): string {
  if (err instanceof AxiosError && err.response?.data) {
    const d = err.response.data as Record<string, unknown>
    if (typeof d.detail === 'string') return d.detail
    return JSON.stringify(d).slice(0, 2000)
  }
  return err instanceof Error ? err.message : String(err)
}

/** Build a flat list of sites sorted by full hierarchy path. */
function buildSiteList(sites: SiteInfo[]): SiteInfo[] {
  return [...sites]
    .filter((s) => s.hierarchy || s.name)
    .sort((a, b) => (a.hierarchy || a.name).localeCompare(b.hierarchy || b.name))
}

const STORAGE_KEY = 'catalyst.savedUrls'

function loadSavedUrls(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((u): u is string => typeof u === 'string' && u.startsWith('http')) : []
  } catch {
    return []
  }
}

function persistSavedUrls(urls: string[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(urls))
  } catch {
    // storage unavailable; ignore
  }
}

export default function CatalystForm() {
  const [savedUrls, setSavedUrls] = useState<string[]>(loadSavedUrls)
  const [baseUrl, setBaseUrl] = useState(() => loadSavedUrls()[0] || 'https://')
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
  const [selectedSiteId, setSelectedSiteId] = useState('')
  const [siteText, setSiteText] = useState('')
  const [skipEnrichment, setSkipEnrichment] = useState(false)
  const navigate = useNavigate()

  const siteList = useMemo(() => buildSiteList(sites), [sites])

  const selectedSite = useMemo(() => {
    if (!selectedSiteId) return null
    return siteList.find((s) => s.site_id === selectedSiteId) ?? null
  }, [selectedSiteId, siteList])

  const siteFilter = selectedSite
    ? (selectedSite.hierarchy || selectedSite.name)
    : siteText

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

  useEffect(() => {
    setSites([]); setSelectedSiteId(''); setSiteText(''); setSkipEnrichment(false)
  }, [baseUrl])

  const handleSaveUrl = () => {
    const url = baseUrl.trim()
    if (!url) return
    const next = savedUrls.includes(url) ? savedUrls : [...savedUrls, url]
    setSavedUrls(next)
    persistSavedUrls(next)
  }

  const handleRemoveUrl = (url: string) => {
    const next = savedUrls.filter((u) => u !== url)
    setSavedUrls(next)
    persistSavedUrls(next)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const data = await importFromCatalyst(
        baseUrl, username, password,
        siteFilter || undefined, selectedSite?.site_id || undefined,
        undefined, skipEnrichment)
      setResult(data)
    } catch (err: unknown) {
      setError(errDetail(err))
    } finally {
      setLoading(false)
    }
  }

  const handleFullImport = async () => {
    if (!window.confirm(
      'Import the FULL Catalyst Center environment (all sites)?\n\n' +
      'This replaces nothing — devices are upserted by IP — but it can take a while and ' +
      'will pull every network device, not just switches.',
    )) return
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const data = await importFromCatalyst(baseUrl, username, password, undefined, undefined, undefined, skipEnrichment)
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
        <PageHeader
          title="Import from Catalyst Center"
          description="Pull devices and topology from a Catalyst Center environment."
        />
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-muted text-sm mb-1">Catalyst Center URL</label>
            {savedUrls.length > 0 && (
              <Select
                value=""
                onChange={(e) => { if (e.target.value) setBaseUrl(e.target.value) }}
                className="w-full mb-2"
              >
                <option value="">Saved URLs…</option>
                {savedUrls.map((u) => (
                  <option key={u} value={u}>{u}</option>
                ))}
              </Select>
            )}
            <div className="flex gap-2">
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                className="flex-1"
                placeholder="https://catalyst-center.example.com"
              />
              <Button
                type="button"
                variant="secondary"
                onClick={handleSaveUrl}
                disabled={!baseUrl.trim()}
                title="Save this URL for next time"
              >
                Save
              </Button>
            </div>
            {savedUrls.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-2">
                {savedUrls.map((u) => (
                  <span
                    key={u}
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${
                      u === baseUrl ? 'bg-blue-600 text-white' : 'bg-surface-3 text-text-secondary'
                    }`}
                  >
                    <button
                      type="button"
                      className="hover:text-text-primary"
                      onClick={() => setBaseUrl(u)}
                      title="Use this URL"
                    >
                      {u}
                    </button>
                    <button
                      type="button"
                      className="text-muted hover:text-red-400"
                      onClick={() => handleRemoveUrl(u)}
                      title="Remove saved URL"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-muted text-sm mb-1">Username</label>
              <Input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-muted text-sm mb-1">Password</label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-muted text-sm">Site Filter</label>
              <button
                type="button"
                disabled={loadingSites || !baseUrl || !username}
                onClick={loadSites}
                className="text-xs text-blue-400 hover:text-blue-300 disabled:opacity-50"
              >
                {loadingSites ? 'Loading...' : 'Load Sites'}
              </button>
            </div>

            {sites.length > 0 ? (
              <Select
                value={selectedSiteId}
                onChange={(e) => setSelectedSiteId(e.target.value)}
                className="w-full"
              >
                <option value="">All sites</option>
                {siteList.map((s) => (
                  <option key={s.site_id} value={s.site_id}>
                    {s.hierarchy || s.name}
                  </option>
                ))}
              </Select>
            ) : (
              <Input
                value={siteText}
                onChange={(e) => setSiteText(e.target.value)}
                className="w-full"
                placeholder="Type site name or hostname pattern"
              />
            )}
            <p className="text-gray-600 text-[11px] mt-0.5">
              {sites.length > 0
                ? `Pick a site from the hierarchy (e.g. Delaware/Wilmington/15 South Poplar St). Choosing a site imports all sub-sites.`
                : `Click "Load Sites" to fetch from Catalyst Center, or type a hostname pattern.`}
            </p>
          </div>

          <label className="flex items-center gap-2 text-sm text-muted cursor-pointer">
            <input
              type="checkbox"
              checked={skipEnrichment}
              onChange={(e) => setSkipEnrichment(e.target.checked)}
              className="rounded"
            />
            <span>Fast import — skip neighbor enrichment (CDP/LLDP/POE walk)</span>
          </label>
          <p className="text-gray-600 text-[11px] -mt-3 ml-6">
            Skips the per-device SNMP neighbor walk. Cuts import time from minutes to seconds.
            Site imports already have topology from Catalyst; use this for faster results.
          </p>

          {selectedSite && (
            <Button
              type="button"
              variant="secondary"
              disabled={debuggingMembership}
              onClick={async () => {
                setDebuggingMembership(true)
                setMembershipDebug(null)
                setError('')
                try {
                  const data = await debugSiteMembership(baseUrl, username, password, selectedSite.site_id)
                  setMembershipDebug(JSON.stringify(data, null, 2))
                } catch (err: unknown) {
                  setMembershipDebug(null)
                  setError(errDetail(err))
                } finally {
                  setDebuggingMembership(false)
                }
              }}
              className="w-full"
            >
              {debuggingMembership ? 'Querying membership API...' : 'Debug Site Membership'}
            </Button>
          )}
          {membershipDebug && (
            <pre className="bg-surface-0 border border-border rounded p-3 text-[11px] text-text-secondary overflow-auto max-h-96 whitespace-pre-wrap">
              {membershipDebug}
            </pre>
          )}

          <div className="flex gap-3">
            <Button
              type="button"
              variant="secondary"
              disabled={testing || !baseUrl || !username}
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
              className="flex-1"
            >
              {testing ? 'Testing...' : 'Test Connection'}
            </Button>
            <Button
              type="submit"
              disabled={loading || !baseUrl || !username}
              className="flex-1"
            >
              {loading ? 'Importing...' : 'Import'}
            </Button>
          </div>

          <Button
            type="button"
            variant="secondary"
            disabled={loading || !baseUrl || !username}
            onClick={handleFullImport}
            className="w-full"
          >
            Import Full Environment (all sites)
          </Button>

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
            <Card className="space-y-3">
              <p className="text-green-300 text-sm">
                Imported {result.device_count} devices, {result.links_found} topology links.
              </p>
              {result.debug && (result.debug.skipped_no_ip as number) > 0 && (
                <div className="bg-amber-900/30 border border-amber-800 rounded px-3 py-2 text-xs text-amber-300">
                  {result.debug.skipped_no_ip as number} device(s) were skipped — no IP address found.
                </div>
              )}
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate(`/topology?scan_id=${result.scan_id}`)}
              >
                View Topology
              </Button>
              {result.debug && (
                <pre className="text-xs text-muted bg-surface-2 p-2 rounded max-h-60 overflow-auto whitespace-pre-wrap">
                  {JSON.stringify(result.debug, null, 2)}
                </pre>
              )}
            </Card>
          )}
        </form>
      </div>
    </div>
  )
}
