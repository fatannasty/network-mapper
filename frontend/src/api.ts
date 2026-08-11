import axios from 'axios'

const api = axios.create()

let token: string | null = localStorage.getItem('token')

export function setToken(t: string | null) {
  token = t
  if (t) localStorage.setItem('token', t)
  else localStorage.removeItem('token')
}

api.interceptors.request.use((config) => {
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      setToken(null)
      window.location.reload()
    }
    return Promise.reject(err)
  },
)

export interface ScanResult {
  scan_id: string
  subnet: string
  scanned_hosts: number
  alive_hosts: number
  device_count: number
  snmp_identified: number
  devices: Device[]
  connections: Link[]
}

export interface SnmpDebug {
  port_open: boolean
  communities_tried: string[]
  community_used: string
  vendor: string
  sys_name: string
  error: string
  hostname: string
  hostname_source?: string
}

export interface Device {
  ip: string
  hostname: string
  vendor: string
  model: string
  device_type: string
  confidence: number
  open_ports: number[]
  snmp_community: string
  snmp_identified: boolean
  interfaces: Interface[]
  site?: string
  snmp_debug?: SnmpDebug
  last_scan_id?: string
  first_seen?: string
  last_seen?: string
}

export interface Interface {
  ifIndex: string
  ifDescr: string
  ifName: string
  ifType: string
  ifSpeed: string
  ifPhysAddress: string
  ifAdminStatus: string
  ifOperStatus: string
  ifHighSpeed: string
  ifAlias: string
}

export interface Link {
  source: string
  target: string
  source_interface: string
  target_interface: string
  protocol: string
  source_hostname: string
  target_hostname: string
}

export interface TopologyData {
  scan_id: string | null
  nodes: TopoNode[]
  links: TopoLink[]
  scan_meta?: {
    subnet: string
    device_count: number
    started_at: string | null
    scan_kind: string | null
  }
}

export interface TopoNode {
  id: string
  ip: string
  hostname: string
  vendor: string
  model: string
  device_type: string
}

export interface TopoLink {
  source: string
  target: string
  source_interface: string
  target_interface: string
  protocol: string
  source_hostname: string
  target_hostname: string
}

export async function login(username: string, password: string) {
  const r = await api.post('/api/auth/login', { username, password })
  return r.data
}

export interface Credential {
  id: number
  name: string
  credential_type: string
  snmp_community: string
  username: string
  site: string
}

export async function discover(subnet: string, communities: string[], snmpPort?: number, snmpv3?: object, verbose?: boolean, excludePcs?: boolean) {
  const r = await api.post('/api/discover', {
    subnet,
    communities: communities.length > 0 ? communities : ['public'],
    exclude_pcs: excludePcs ?? true,
    snmp_port: snmpPort || 161,
    snmpv3,
    verbose: verbose || false,
  })
  return r.data as ScanResult
}

export async function getCredentials() {
  const r = await api.get('/api/inventory/credentials')
  return r.data as { count: number; credentials: Credential[] }
}

export async function createCredential(data: {
  name: string
  credential_type?: string
  username?: string
  password?: string
  snmp_community?: string
  site?: string
}) {
  const r = await api.post('/api/inventory/credentials', data)
  return r.data as Credential
}

export async function deleteCredential(id: number) {
  const r = await api.delete(`/api/inventory/credentials/${id}`)
  return r.data as { deleted: boolean }
}

export async function testCatalyst(baseUrl: string, username: string, password: string) {
  const r = await api.post('/api/catalyst/test', { base_url: baseUrl, username, password })
  return r.data as { connected: boolean; device_count: number; sample: Record<string, unknown> | null }
}

export interface SiteInfo {
  name: string
  hierarchy: string
  site_id: string
}

export async function fetchSites(baseUrl: string, username: string, password: string) {
  const r = await api.post('/api/catalyst/sites', { base_url: baseUrl, username, password })
  return r.data as { states: string[]; cities: string[]; sites: SiteInfo[]; debug?: { raw_count?: number; parsed?: number; samples?: unknown[] } }
}

export async function importFromCatalyst(baseUrl: string, username: string, password: string, siteName?: string, siteId?: string, deviceFilter?: string) {
  const r = await api.post('/api/catalyst/import', {
    base_url: baseUrl, username, password,
    site_name: siteName || '', site_id: siteId || '', device_filter: deviceFilter || '',
  })
  return r.data as { scan_id: string; device_count: number; links_found: number; debug?: Record<string, unknown> }
}

export async function debugSiteMembership(baseUrl: string, username: string, password: string, siteId: string) {
  const r = await api.post('/api/catalyst/site-members-debug', {
    base_url: baseUrl, username, password, site_id: siteId,
  })
  return r.data as { site_id: string; endpoints: { url: string; status: string; error?: string; raw: unknown }[]; parsed: { ids: string[] } }
}

export async function getTopology(scanId?: string) {
  const r = await api.get('/api/topology', {
    params: scanId ? { scan_id: scanId } : {},
  })
  return r.data as TopologyData
}

export async function getDevices(params?: Record<string, string>) {
  const r = await api.get('/api/inventory/devices', { params })
  return r.data
}

export async function getDevice(id: number) {
  const r = await api.get(`/api/inventory/devices/${id}`)
  return r.data
}

export async function getScans(limit = 20) {
  const r = await api.get('/api/inventory/scans', { params: { limit } })
  return r.data
}

// ── Sprint 9: Configuration Collection ───────────────────────────────────────

export interface ConfigEntry {
  id: number
  device_id: number
  ip: string
  hostname: string
  config_type: string
  collected_at: string
  error: string | null
  config_text: string
}

export interface CollectResult {
  total: number
  success: number
  failed: number
  results: {
    device_id: number
    ip: string
    hostname: string
    status: string
    config_id?: number
    error?: string
  }[]
}

export async function collectConfigs(
  sitePattern?: string,
  sshUsername?: string,
  sshPassword?: string,
  sshPort?: number,
) {
  const r = await api.post('/api/inventory/collect-config', {
    site_pattern: sitePattern || '',
    ssh_username: sshUsername || '',
    ssh_password: sshPassword || '',
    ssh_port: sshPort || 22,
  })
  return r.data as CollectResult
}

export async function getDeviceConfigs(deviceId: number) {
  const r = await api.get(`/api/inventory/devices/${deviceId}/configs`)
  return r.data as ConfigEntry[]
}

// ── Sprint 10: Layer 3 Path Analysis ─────────────────────────────────────────

export interface PathHop {
  source: string
  target: string
  source_hostname: string
  target_hostname: string
  source_interface: string
  target_interface: string
  protocol: string
}

export interface PathResult {
  source: string
  target: string
  path: PathHop[]
  hops: number
  error?: string
}

export async function findPath(source: string, target: string) {
  const r = await api.get('/api/topology/path', { params: { source, target } })
  return r.data as PathResult
}

export async function getInventoryLinks() {
  const r = await api.get('/api/inventory/links')
  return r.data.links as TopoLink[]
}

// ── Sprint 11: Change Detection ──────────────────────────────────────────────

export interface ScanInfo {
  id: string
  subnet: string
  device_count: number
  started_at: string | null
}

export interface ChangeResult {
  scan_a: ScanInfo
  scan_b: ScanInfo
  devices: {
    added: string[]
    removed: string[]
    changed: { ip: string; changes: Record<string, { from: string; to: string }> }[]
    count_a: number
    count_b: number
  }
  links: {
    added: { source: string; target: string }[]
    removed: { source: string; target: string }[]
    count_a: number
    count_b: number
  }
  error?: string
}

export async function getChanges(scanA: string, scanB: string) {
  const r = await api.get('/api/topology/changes', { params: { scan_a: scanA, scan_b: scanB } })
  return r.data as ChangeResult
}

// ── Sprint 12: Reporting ─────────────────────────────────────────────────────

export interface ConfigCoverage {
  total_configs: number
  devices_with_config: number
  by_device_type: Record<string, number>
}

export interface ScanHistoryEntry {
  id: string
  subnet: string
  status: string
  device_count: number
  links: number
  started_at: string | null
  finished_at: string | null
}

export interface Report {
  total_devices: number
  total_links: number
  total_interfaces: number
  by_device_type: Record<string, number>
  by_vendor: Record<string, number>
  by_site: Record<string, number>
  link_protocols: Record<string, number>
  interface_status: Record<string, number>
  config_coverage: ConfigCoverage
  stale_devices_90d: number
  dod_gates: Record<string, DodGate>
  scan_history: ScanHistoryEntry[]
  recent_scans: ScanHistoryEntry[]
}

export async function getReport() {
  const r = await api.get('/api/inventory/report')
  return r.data as Report
}

// ── Sprint 13: Data Quality ──────────────────────────────────────────────────

export interface SiteMapping {
  id: number
  prefix: string
  site: string
  created_at: string | null
}

export interface DodGate {
  target: number
  actual: number
  met: boolean
}

export interface BackfillSummary {
  total: number
  successful: number
  failed: number
  interfaces_walked?: number
  neighbors_discovered?: number
  persisted_devices?: number
  persisted_interfaces?: number
  validation_links?: number
  sample_errors?: string[]
  results: {
    ip: string
    hostname: string
    device_type: string
    interfaces?: number
    interface_count?: number
    neighbor_count?: number
    error: string
  }[]
}

export async function getSiteMappings() {
  const r = await api.get('/api/inventory/site-mappings')
  return r.data as { count: number; mappings: SiteMapping[] }
}

export async function createSiteMapping(prefix: string, site: string) {
  const r = await api.post('/api/inventory/site-mappings', { prefix, site })
  return r.data as SiteMapping
}

export async function deleteSiteMapping(id: number) {
  const r = await api.delete(`/api/inventory/site-mappings/${id}`)
  return r.data as { deleted: boolean }
}

export async function seedSiteMappings() {
  const r = await api.post('/api/inventory/site-mappings/seed')
  return r.data as { discovered: number; created: number; skipped: number }
}

export async function applySiteMappings(limit = 0) {
  const r = await api.post('/api/inventory/site-mappings/apply', null, { params: { limit } })
  return r.data as { mappings: number; matched: number; updated: number; unchanged: number }
}

export interface BackfillRequest {
  communities?: string[]
  max_workers?: number
  timeout?: number
  limit?: number
  device_type?: string
}

export async function backfillInterfaces(req?: BackfillRequest) {
  const r = await api.post('/api/backfill/interfaces', req || {})
  return r.data as BackfillSummary
}

export async function backfillLinks(req?: BackfillRequest) {
  const r = await api.post('/api/backfill/links', req || {})
  return r.data as BackfillSummary & { scan_id: string; validation_links: number }
}

export async function classifyBlanks(limit = 0) {
  const r = await api.post('/api/backfill/classify-blanks', null, { params: { limit } })
  return r.data as { changed: number; total_scanned: number }
}

export async function collectConfigsCatalyst(
  baseUrl: string, username: string, password: string,
  deviceType = 'switch', sitePattern = '', limit = 50,
) {
  const r = await api.post('/api/catalyst/collect-config', {
    base_url: baseUrl, username, password,
    device_type: deviceType, site_pattern: sitePattern, limit,
  })
  return r.data as CollectResult
}

export async function exportReport(report: 'devices' | 'links' | 'scans' | 'configs') {
  const r = await api.get('/api/inventory/report/export', { params: { report }, responseType: 'blob' })
  const url = URL.createObjectURL(r.data)
  const a = document.createElement('a')
  a.href = url
  a.download = `${report}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
