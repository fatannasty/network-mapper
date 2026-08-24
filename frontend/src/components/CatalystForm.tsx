import { useState, useEffect, useMemo, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { AxiosError } from 'axios'
import { importFromCatalyst, testCatalyst, fetchSites, debugSiteMembership, backfillVlan90, collectConfigs, type SiteInfo } from '../api'
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

interface LocationEntry { name: string; site_id: string; full_path: string }
interface CityGroup { name: string; site_id: string; locations: LocationEntry[] }
interface StateGroup { name: string; site_id: string; cities: CityGroup[] }

function parseSiteTree(sites: SiteInfo[]): StateGroup[] {
  const states = new Map<string, StateGroup>()

  for (const s of sites) {
    const hier = (s.hierarchy || s.name || '').replace(/^\/+|\/+$/g, '')
    const parts = hier.split('/').map((p) => p.trim()).filter(Boolean)

    // Expect at least Global/United States/State
    if (parts.length < 3) continue

    const stateName = parts[2]
    let stateGrp = states.get(stateName)
    if (!stateGrp) {
      stateGrp = { name: stateName, site_id: '', cities: [] }
      states.set(stateName, stateGrp)
    }

    if (parts.length === 3) {
      // State-level site
      if (!stateGrp.site_id) stateGrp.site_id = s.site_id
      continue
    }

    const cityName = parts[3]
    let cityGrp = stateGrp.cities.find((c) => c.name === cityName)
    if (!cityGrp) {
      // Try to find the city-level site_id
      const cityHier = parts.slice(0, 4).join('/')
      const citySite = sites.find((x) => (x.hierarchy || x.name).replace(/^\/+|\/+$/g, '') === cityHier)
      cityGrp = { name: cityName, site_id: citySite?.site_id || '', locations: [] }
      stateGrp.cities.push(cityGrp)
    }

    if (parts.length >= 5) {
      const locationName = parts.slice(4).join(' / ')
      const existing = cityGrp.locations.find((l) => l.site_id === s.site_id)
      if (!existing) {
        cityGrp.locations.push({
          name: locationName,
          site_id: s.site_id,
          full_path: hier,
        })
      }
    } else if (parts.length === 4 && !cityGrp.site_id) {
      // City-level site (no sub-location)
      cityGrp.site_id = s.site_id
    }
  }

  // Sort everything
  const result = Array.from(states.values())
    .filter((s) => s.name)
    .sort((a, b) => a.name.localeCompare(b.name))

  for (const state of result) {
    if (!state.site_id) {
      const match = sites.find((s) => (s.hierarchy || '').includes(`/${state.name}`) && !s.hierarchy.includes(`/${state.name}/`))
      if (match) state.site_id = match.site_id
    }
    state.cities.sort((a, b) => a.name.localeCompare(b.name))
    for (const city of state.cities) {
      city.locations.sort((a, b) => a.name.localeCompare(b.name))
    }
  }

  return result
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
  const [selectedState, setSelectedState] = useState('')
  const [selectedCity, setSelectedCity] = useState('')
  const [selectedLocation, setSelectedLocation] = useState('')
  const [siteText, setSiteText] = useState('')
  const [skipEnrichment, setSkipEnrichment] = useState(false)
  const [detectVlan90, setDetectVlan90] = useState(false)
  const [syncingVlan90, setSyncingVlan90] = useState(false)
  const [collectingVlan90, setCollectingVlan90] = useState(false)
  const [vlan90SyncResult, setVlan90SyncResult] = useState<{ devices_with_config: number; updated: number; vlan90_detected: number; from_config: number; from_vlan_walk: number } | null>(null)
  const [vlan90Collect, setVlan90Collect] = useState<{ total: number; success: number; failed: number } | null>(null)
  const navigate = useNavigate()

  const siteTree = useMemo(() => parseSiteTree(sites), [sites])

  const stateOptions = siteTree
  const cityOptions = selectedState
    ? (siteTree.find((s) => s.name === selectedState)?.cities || [])
    : []
  const locationOptions = selectedState && selectedCity
    ? (cityOptions.find((c) => c.name === selectedCity)?.locations || [])
    : []

  const selectedSiteId = selectedLocation
    || cityOptions.find((c) => c.name === selectedCity)?.site_id
    || stateOptions.find((s) => s.name === selectedState)?.site_id
    || ''

  const selectedSite = selectedSiteId
    ? sites.find((s) => s.site_id === selectedSiteId) || null
    : null

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
    setSites([]); setSelectedState(''); setSelectedCity(''); setSelectedLocation(''); setSiteText(''); setSkipEnrichment(false)
  }, [baseUrl])

  useEffect(() => {
    setSelectedCity(''); setSelectedLocation('')
  }, [selectedState])

  useEffect(() => {
    setSelectedLocation('')
  }, [selectedCity])

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
        siteFilter || undefined, selectedSiteId || undefined,
        undefined, skipEnrichment, detectVlan90)
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
      const data = await importFromCatalyst(baseUrl, username, password, undefined, undefined, undefined, skipEnrichment, detectVlan90)
      setResult(data)
    } catch (err: unknown) {
      setError(errDetail(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex justify-center">
      <div className="w-full max-w-lg">
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
                      u === baseUrl ? 'bg-blue-600 text-white' : 'bg-surface-3/60 backdrop-blur border border-border/30 text-text-secondary'
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
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <Select
                    value={selectedState}
                    onChange={(e) => setSelectedState(e.target.value)}
                    className="w-full"
                  >
                    <option value="">All States</option>
                    {stateOptions.map((g) => (
                      <option key={g.name} value={g.name}>{g.name}</option>
                    ))}
                  </Select>
                </div>
                <div>
                  <Select
                    value={selectedCity}
                    onChange={(e) => setSelectedCity(e.target.value)}
                    disabled={!selectedState}
                    className="w-full disabled:opacity-50"
                  >
                    <option value="">
                      {selectedState ? `All ${selectedState} cities` : 'State first'}
                    </option>
                    {cityOptions.map((c) => (
                      <option key={c.name} value={c.name}>{c.name}</option>
                    ))}
                  </Select>
                </div>
                <div>
                  <Select
                    value={selectedLocation}
                    onChange={(e) => setSelectedLocation(e.target.value)}
                    disabled={!selectedCity || locationOptions.length === 0}
                    className="w-full disabled:opacity-50"
                  >
                    <option value="">
                      {selectedCity ? (locationOptions.length > 0 ? `All ${selectedCity} locations` : 'No sub-locations') : 'City first'}
                    </option>
                    {locationOptions.map((l) => (
                      <option key={l.site_id} value={l.site_id}>{l.name}</option>
                    ))}
                  </Select>
                </div>
              </div>
            ) : (
              <Input
                value={siteText}
                onChange={(e) => setSiteText(e.target.value)}
                className="w-full"
                placeholder="Type site name or hostname pattern"
              />
            )}
            <p className="text-gray-600 text-[11px] mt-1">
              {sites.length > 0
                ? `Pick a state, city, and location. Choosing a higher level imports all sites under it.`
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

          <label className="flex items-center gap-2 text-sm text-muted cursor-pointer">
            <input
              type="checkbox"
              checked={detectVlan90}
              onChange={(e) => setDetectVlan90(e.target.checked)}
              className="rounded"
            />
            <span>Flag switches with VLAN 90 configured</span>
          </label>
          <p className="text-gray-600 text-[11px] -mt-3 ml-6">
            Fetches each switch's running config and marks those referencing VLAN 90.
            Adds a few seconds per switch, so it's best combined with the fast import.
          </p>

          <div className="ml-6 flex flex-col items-start gap-2">
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={collectingVlan90 || syncingVlan90}
                onClick={async () => {
                  setCollectingVlan90(true)
                  setVlan90Collect(null)
                  setVlan90SyncResult(null)
                  setError('')
                  try {
                    const collected = await collectConfigs(undefined, '', '', 22, undefined, true)
                    setVlan90Collect({
                      total: collected.total, success: collected.success,
                      failed: collected.failed,
                    })
                    setVlan90SyncResult(await backfillVlan90())
                  } catch (e) {
                    setError(`VLAN 90 config collection failed: ${errDetail(e)}`)
                  } finally {
                    setCollectingVlan90(false)
                  }
                }}
              >
                {collectingVlan90 ? 'Collecting configs…' : 'Collect configs for unflagged switches'}
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={syncingVlan90 || collectingVlan90}
                onClick={async () => {
                  setSyncingVlan90(true)
                  setVlan90SyncResult(null)
                  setError('')
                  try {
                    setVlan90SyncResult(await backfillVlan90())
                  } catch (e) {
                    setError(`VLAN 90 sync failed: ${errDetail(e)}`)
                  } finally {
                    setSyncingVlan90(false)
                  }
                }}
              >
                {syncingVlan90 ? 'Syncing…' : 'Sync VLAN 90 from stored data'}
              </Button>
            </div>
            {vlan90Collect && (
              <p className="text-xs text-white/75">
                Collected configs: {vlan90Collect.success} ok / {vlan90Collect.failed} failed (of {vlan90Collect.total}).
              </p>
            )}
            {vlan90SyncResult && (
              <p className="text-xs text-teal-300">
                Scanned {vlan90SyncResult.devices_with_config} devices —{' '}
                <strong>{vlan90SyncResult.vlan90_detected}</strong> with VLAN 90
                ({vlan90SyncResult.updated} flags updated)
                {vlan90SyncResult.from_vlan_walk > 0 &&
                  <>; {vlan90SyncResult.from_vlan_walk} from SNMP VLAN data</>}.
              </p>
            )}
          </div>

          {selectedSiteId && (
            <Button
              type="button"
              variant="secondary"
              disabled={debuggingMembership}
              onClick={async () => {
                setDebuggingMembership(true)
                setMembershipDebug(null)
                setError('')
                try {
                  const data = await debugSiteMembership(baseUrl, username, password, selectedSiteId)
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
            <div className={`rounded-xl p-3 text-xs backdrop-blur ${testResult.startsWith('Connected') ? 'bg-green-900/50 border border-green-800/50 text-green-300' : 'bg-red-900/50 border border-red-800/50 text-red-300'}`}>
              {testResult}
            </div>
          )}

          {error && (
            <div className="bg-red-950/60 backdrop-blur border border-red-800/50 rounded-xl p-4">
              <p className="text-red-300 text-sm">{error}</p>
            </div>
          )}

          {result && (
            <Card className="space-y-3">
              <p className="text-green-300 text-sm">
                Imported {result.device_count} devices, {result.links_found} topology links.
              </p>
              {typeof result.debug?.vlan90_detected === 'number' && (
                <div className="bg-teal-900/40 border border-teal-700 rounded px-3 py-2 text-xs text-teal-200">
                  VLAN 90 configured on <strong>{result.debug.vlan90_detected}</strong> of {result.debug.vlan90_checked as number} switches checked
                  {typeof result.debug?.vlan90_from_stored === 'number' && result.debug.vlan90_from_stored > 0 &&
                    <> ({result.debug.vlan90_from_stored as number} via stored configs)</>}
                  .
                  {typeof result.debug?.vlan90_fetch_errors === 'number' && result.debug.vlan90_fetch_errors > 0 && (
                    <div className="mt-1 text-amber-300">
                      {result.debug.vlan90_fetch_errors as number} switch(es) could not be checked (config fetch failed) — left unflagged.
                    </div>
                  )}
                </div>
              )}
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
                <pre className="text-xs text-muted bg-surface-2/60 backdrop-blur p-2 rounded-xl max-h-60 overflow-auto whitespace-pre-wrap border border-border/30">
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
