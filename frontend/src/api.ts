import axios from 'axios'

const api = axios.create({ withCredentials: true })

// Auth is primarily an httpOnly cookie set by POST /api/auth/login. We also
// keep the token in memory only (never localStorage) and send it as an
// Authorization header as a fallback, so the session works across environments.
let token: string | null = null

export function setToken(t: string | null) {
  token = t
}

export async function getMe(): Promise<{ username: string; role: string }> {
  const r = await api.get('/api/auth/me')
  return r.data
}

export async function logout() {
  try {
    await api.post('/api/auth/logout')
  } catch {
    // ignore — the cookie is cleared server-side regardless
  }
}

api.interceptors.request.use((config) => {
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Auth endpoints handle their own 401s (App re-renders the login form for
// /api/auth/me; the login form shows an error for /api/auth/login), so a full
// reload is only needed when a *data* endpoint reports an expired session.
const AUTH_ENDPOINTS = ['/api/auth/me', '/api/auth/login', '/api/auth/logout']

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const url = err.config?.url || ''
    if (err.response?.status === 401 && !AUTH_ENDPOINTS.some((e) => url.includes(e))) {
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
  id: number
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
  catalyst_id?: string
  latency_ms?: number
  latency_checked_at?: string
  vlan_90?: boolean | null
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
  vlanId?: number | null
  vlanName?: string
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
  focus?: string | null
}

export interface TopoNode {
  id: string
  ip: string
  hostname: string
  vendor: string
  model: string
  device_type: string
  status?: 'up' | 'down' | 'degraded' | 'flapping' | 'unknown'
  spof?: boolean
  vlan_90?: boolean | null
  subnet?: string
  device_count?: number
  up?: number
  down?: number
  flapping?: number
}

export interface TopoLink {
  source: string
  target: string
  source_interface: string
  target_interface: string
  protocol: string
  source_hostname: string
  target_hostname: string
  status?: 'up' | 'down'
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

export async function importFromCatalyst(baseUrl: string, username: string, password: string, siteName?: string, siteId?: string, deviceFilter?: string, skipEnrichment?: boolean, detectVlan90?: boolean) {
  const r = await api.post('/api/catalyst/import', {
    base_url: baseUrl, username, password,
    site_name: siteName || '', site_id: siteId || '', device_filter: deviceFilter || '',
    skip_enrichment: skipEnrichment ?? false,
    detect_vlan90: detectVlan90 ?? false,
  })
  return r.data as { scan_id: string; device_count: number; links_found: number; debug?: Record<string, unknown> }
}

export async function backfillVlan90() {
  const r = await api.post('/api/backfill/vlan90')
  return r.data as { devices_with_config: number; updated: number; vlan90_detected: number; from_config: number; from_vlan_walk: number; backfilled: boolean }
}

export async function backfillSites(baseUrl: string, username: string, password: string) {
  const r = await api.post('/api/catalyst/backfill-sites', { base_url: baseUrl, username, password })
  return r.data as {
    prefix_apply: { mappings: number; matched: number; updated: number; unchanged: number }
    membership_sites: number
    membership_targets: number
    membership_matched: number
    membership_updated: number
    samples: string[]
    still_blank_sites: number
  }
}

export async function debugSiteMembership(baseUrl: string, username: string, password: string, siteId: string) {
  const r = await api.post('/api/catalyst/site-members-debug', {
    base_url: baseUrl, username, password, site_id: siteId,
  })
  return r.data as { site_id: string; endpoints: { url: string; status: string; error?: string; raw: unknown }[]; parsed: { ids: string[] } }
}

export async function testVeloCloud(baseUrl: string, username: string, password: string, token?: string) {
  const r = await api.post('/api/velocloud/test', { base_url: baseUrl, username, password, token: token || '' })
  return r.data as { connected: boolean; edge_count: number; sample?: Record<string, unknown> | null }
}

export async function importFromVeloCloud(baseUrl: string, username: string, password: string, token?: string) {
  const r = await api.post('/api/velocloud/import', { base_url: baseUrl, username, password, token: token || '' })
  return r.data as { scan_id: string; device_count: number; links_found: number; debug?: Record<string, unknown> }
}

export async function testMeraki(baseUrl: string, apiKey: string) {
  const r = await api.post('/api/meraki/test', { base_url: baseUrl, api_key: apiKey })
  return r.data as { connected: boolean; organizations: number; device_count: number }
}

export async function importFromMeraki(baseUrl: string, apiKey: string) {
  const r = await api.post('/api/meraki/import', { base_url: baseUrl, api_key: apiKey })
  return r.data as { scan_id: string; device_count: number; links_found: number; debug?: Record<string, unknown> }
}

export async function getTopology(scanId?: string, focus?: string, site?: string) {
  const params: Record<string, string> = {}
  if (scanId) params.scan_id = scanId
  if (focus) params.focus = focus
  if (site) params.site = site
  const r = await api.get('/api/topology', { params })
  return r.data as TopologyData
}

export interface TopologySummaryData {
  scan_id: string | null
  nodes: TopoNode[]
  links: (TopoLink & { count?: number })[]
  summary: boolean
}

export async function getTopologySummary(scanId?: string, site?: string) {
  const params: Record<string, string> = {}
  if (scanId) params.scan_id = scanId
  if (site) params.site = site
  const r = await api.get('/api/topology/summary', { params })
  return r.data as TopologySummaryData
}

export async function getDevices(params?: Record<string, string>) {
  const r = await api.get('/api/inventory/devices', { params })
  return r.data
}

export async function measureLatency(site?: string) {
  const r = await api.post('/api/inventory/measure-latency', null, {
    params: site ? { site } : undefined,
  })
  return r.data as { measured: number; updated: number }
}

export async function getDevice(id: number) {
  const r = await api.get(`/api/inventory/devices/${id}`)
  return r.data
}

export async function getScans(limit = 20) {
  const r = await api.get('/api/inventory/scans', { params: { limit } })
  return r.data
}

export async function getUsers() {
  const r = await api.get('/api/auth/users')
  return r.data as { count: number; users: { id: number; username: string; role: string; is_active: boolean; created_at: string | null }[] }
}

export async function createUser(username: string, password: string, role: string) {
  const r = await api.post('/api/auth/users', { username, password, role })
  return r.data
}

export async function updateUser(userId: number, data: { username?: string; password?: string; role?: string; is_active?: boolean }) {
  const r = await api.patch(`/api/auth/users/${userId}`, data)
  return r.data
}

export async function deleteUser(userId: number) {
  const r = await api.delete(`/api/auth/users/${userId}`)
  return r.data
}

export async function getAdminActivity() {
  const r = await api.get('/api/admin/activity')
  return r.data as { activity: { type: string; action: string; timestamp: string | null; status: string; details: Record<string, unknown> }[] }
}

export async function getAdminStatus() {
  const r = await api.get('/api/admin/status')
  return r.data as {
    database_size_bytes: number
    total_devices: number
    total_links: number
    total_interfaces: number
    total_scans: number
    stale_devices_90d: number
    latest_scan: Record<string, unknown> | null
    scan_success_rate: number
  }
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
  collected_by: string | null
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
    collected_by?: string
    user?: string
  }[]
}

export async function collectConfigs(
  sitePattern?: string,
  sshUsername?: string,
  sshPassword?: string,
  sshPort?: number,
  deviceId?: number,
  vlan90Unflagged?: boolean,
  ips?: string[],
) {
  const r = await api.post('/api/inventory/collect-config', {
    site_pattern: sitePattern || '',
    ssh_username: sshUsername || '',
    ssh_password: sshPassword || '',
    ssh_port: sshPort || 22,
    device_id: deviceId,
    vlan90_unflagged: vlan90Unflagged ?? false,
    ips,
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

export interface ExecSite {
  site: string
  devices: number
  up: number
  down: number
  degraded: number
  flapping: number
  unknown: number
  freshness_days: number | null
}

export interface ExecRisk {
  ip: string
  hostname: string
  site: string
  status: string
}

export interface ExecHealth {
  total_devices: number
  state: 'healthy' | 'warning' | 'critical'
  score: number
  kpis: {
    total_devices: number
    devices_up: number
    devices_down: number
    devices_degraded: number
    devices_flapping: number
    devices_unknown: number
    spof_count: number
    vlan90_count: number
    stale_devices: number
    up_pct: number
    config_coverage: number
    site_coverage: number
    interface_coverage: number
    link_validation: number
  }
  sites: ExecSite[]
  risks: ExecRisk[]
  spof_devices: { ip: string; hostname: string; site: string }[]
}

export async function getExecHealth() {
  const r = await api.get('/api/health/exec')
  return r.data as ExecHealth
}

export interface NotificationItem {
  id: number
  created_at: string | null
  kind: string
  severity: string
  title: string
  message: string
  device_ip: string
  seen: boolean
  emailed: boolean
}

export async function listNotifications(limit = 50) {
  const r = await api.get('/api/notifications', { params: { limit } })
  return r.data as { unseen: number; notifications: NotificationItem[] }
}

export async function markNotificationSeen(id: number) {
  const r = await api.post(`/api/notifications/${id}/seen`)
  return r.data as { seen: boolean }
}

export async function runAlertCheck() {
  const r = await api.post('/api/notifications/check')
  return r.data as { created: number; flapping: number; down: number; spof: number }
}

export interface ApiTokenInfo {
  id: number
  name: string
  role: string
  created_by: string
  created_at: string | null
  last_used_at: string | null
  revoked: boolean
}

export async function listApiTokens() {
  const r = await api.get('/api/auth/tokens')
  return r.data as { tokens: ApiTokenInfo[] }
}

export async function createApiToken(name: string, role: string) {
  const r = await api.post('/api/auth/tokens', { name, role })
  return r.data as { token: string; name: string; role: string }
}

export async function revokeApiToken(id: number) {
  const r = await api.delete(`/api/auth/tokens/${id}`)
  return r.data as { revoked: boolean }
}

export interface ExecReportMeta {
  id: number
  created_at: string | null
  title: string
  emailed: boolean
  error: string | null
}

export interface ExecReportsResponse {
  schedule: string
  interval_minutes: number
  reports: ExecReportMeta[]
}

export async function listExecReports() {
  const r = await api.get('/api/report/executive')
  return r.data as ExecReportsResponse
}

export async function generateExecReport() {
  const r = await api.post('/api/report/executive/generate')
  return r.data as ExecReportMeta
}

export function execReportUrl(id: number, format: 'html' | 'pdf' = 'html') {
  return `/api/report/executive/${id}${format === 'pdf' ? '/pdf' : ''}`
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

export interface SnmpV3Request {
  username: string
  auth_protocol?: string // md5 | sha | none
  auth_password?: string
  privacy_protocol?: string // aes | des | none
  privacy_password?: string
}

export interface BackfillRequest {
  communities?: string[]
  max_workers?: number
  timeout?: number
  limit?: number
  device_type?: string
  site?: string
  snmpv3?: SnmpV3Request
  ips?: string[]
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

export async function bulkSetSite(ips: string[], site: string) {
  const r = await api.post('/api/inventory/bulk-set-site', { ips, site })
  return r.data as { updated: number; total: number }
}

export async function collectConfigsCatalyst(
  baseUrl: string, username: string, password: string,
  deviceType = 'switch', sitePattern = '', limit = 50, deviceId?: number,
) {
  const r = await api.post('/api/catalyst/collect-config', {
    base_url: baseUrl, username, password,
    device_type: deviceType, site_pattern: sitePattern, limit, device_id: deviceId,
  })
  return r.data as CollectResult
}

export function apiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const d = err.response?.data as { detail?: unknown } | undefined
    if (d && typeof d.detail === 'string') return d.detail
    if (d && d.detail !== undefined) return JSON.stringify(d.detail).slice(0, 2000)
    if (err.response) return `Request failed with status code ${err.response.status}`
  }
  return err instanceof Error ? err.message : String(err)
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

export async function downloadConfigs() {
  const r = await api.get('/api/configs/download', { responseType: 'blob' })
  const url = URL.createObjectURL(r.data)
  const a = document.createElement('a')
  a.href = url
  a.download = 'configs.txt'
  a.click()
  URL.revokeObjectURL(url)
}

export type DiagramFormat = 'pdf' | 'vsdx' | 'docx'

export interface DiagramLegendEntry {
  key?: string
  label: string
  color: string
}

export interface DiagramExportOptions {
  format: DiagramFormat
  nodes: TopoNode[]
  links: TopoLink[]
  title: string
  drawn_by?: string
  drawn_date?: string
  drawing_title?: string
  document_name?: string
  revision?: string
  rev_date?: string
  rev_time?: string
  color_links?: boolean
  legend?: DiagramLegendEntry[]
  exclude_endpoints?: boolean
  topology?: 'auto' | 'tree' | 'star' | 'ring' | 'bus'
  link_detail?: 'full' | 'backbone' | 'core'
  scale?: number
}

export async function exportTopologyDiagram(opts: DiagramExportOptions) {
  const r = await api.post('/api/topology/diagram', opts, { responseType: 'blob' })
  const url = URL.createObjectURL(r.data)
  const a = document.createElement('a')
  const slug = opts.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'diagram'
  a.href = url
  a.download = `${slug}.${opts.format}`
  a.click()
  URL.revokeObjectURL(url)
}

export async function exportTopologyPackage(opts: DiagramExportOptions) {
  const r = await api.post('/api/topology/package', opts, { responseType: 'blob' })
  const url = URL.createObjectURL(r.data)
  const a = document.createElement('a')
  const slug = opts.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'diagram'
  a.href = url
  a.download = `${slug}-package.zip`
  a.click()
  URL.revokeObjectURL(url)
}

export async function renderTopologyPreview(opts: DiagramExportOptions): Promise<string> {
  const r = await api.post('/api/topology/diagram', { ...opts, format: 'png', scale: 0.5 }, { responseType: 'blob' })
  return URL.createObjectURL(r.data)
}

export interface DiagramPrefs {
  topology: 'auto' | 'tree' | 'star' | 'ring' | 'bus'
  link_detail: 'full' | 'backbone' | 'core'
}

export async function getDiagramPrefs(scanId: string): Promise<DiagramPrefs> {
  const r = await api.get('/api/topology/diagram-prefs', { params: { scan_id: scanId } })
  return r.data
}

export async function downloadPortTable(scanId?: string) {
  const r = await api.get('/api/topology/port-table', {
    params: scanId ? { scan_id: scanId } : undefined,
    responseType: 'blob',
  })
  const url = URL.createObjectURL(r.data)
  const a = document.createElement('a')
  a.href = url
  a.download = 'device-port-table.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export interface WalkReport {
  site: string
  interface_count: number
  link_count: number
  interfaces: {
    device_ip: string
    hostname: string
    interface: string
    if_descr: string
    vlan_id: number | null
    vlan_name: string
    if_oper_status: string
    if_admin_status: string
    if_speed: string
  }[]
  links: {
    source: string
    source_hostname: string
    target: string
    target_hostname: string
    interface_a: string
    interface_b: string
    protocol: string
  }[]
}

export interface ConfigDiffRow { type: 'add' | 'del' | 'ctx' | 'meta'; text: string }

export async function getConfigDiff(deviceId: number, fromId: number, toId: number) {
  const r = await api.get('/api/inventory/config-diff', {
    params: { device_id: deviceId, from_id: fromId, to_id: toId },
  })
  return r.data as { added: number; removed: number; changed: boolean; diff: ConfigDiffRow[] }
}

export interface ConfigChange {
  device_id: number
  ip: string
  hostname: string
  site: string
  changed_at: string | null
  collected_by: string | null
  from_id: number
  to_id: number
  added: number
  removed: number
}

export async function getConfigChanges(site?: string, limit = 20) {
  const r = await api.get('/api/inventory/config-changes', {
    params: { site: site || '', limit },
  })
  return r.data as { count: number; changes: ConfigChange[] }
}

export interface UtilizationPoint { t: string; in_rate: number; out_rate: number }
export interface IfaceUtilization { if_index: string; if_name: string; if_speed: string; series: UtilizationPoint[] }
export interface DeviceUtilization { device_id: number; ip: string; hostname: string; interfaces: IfaceUtilization[] }

export async function getDeviceUtilization(deviceId: number, days = 3) {
  const r = await api.get(`/api/inventory/devices/${deviceId}/utilization`, { params: { days } })
  return r.data as DeviceUtilization
}

export interface TopUtil { ip: string; hostname: string; if_name: string; avg_in_rate: number; avg_out_rate: number; peak_rate: number }

export async function getTopUtilization(days = 1, limit = 10) {
  const r = await api.get('/api/utilization/top', { params: { days, limit } })
  return r.data as { days: number; top: TopUtil[] }
}

export async function getWalkReport(site?: string) {
  const r = await api.get('/api/topology/walk-report', { params: { site: site || '' } })
  return r.data as WalkReport
}

function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return ''
  const cols = Object.keys(rows[0])
  const esc = (v: unknown) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n')
}

function downloadCsv(text: string, filename: string) {
  const blob = new Blob([text], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export async function downloadWalkReport(site?: string) {
  const rep = await getWalkReport(site)
  const suffix = site ? `-${site.toLowerCase().replace(/[^a-z0-9]+/g, '-')}` : '-all'
  downloadCsv(toCsv(rep.interfaces), `walk-report${suffix}-interfaces.csv`)
  downloadCsv(toCsv(rep.links), `walk-report${suffix}-links.csv`)
  return rep
}

export async function saveDiagramPrefs(scanId: string, prefs: DiagramPrefs) {
  await api.post('/api/topology/diagram-prefs', { scan_id: scanId, ...prefs })
}
