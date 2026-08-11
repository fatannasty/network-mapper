import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getReport, exportReport, type Report, type ScanHistoryEntry } from '../api'
import Badge from './ui/Badge'
import Button from './ui/Button'
import Card from './ui/Card'
import PageHeader from './ui/PageHeader'
import PageState from './ui/PageState'
import Select from './ui/Select'
import Tooltip from './ui/Tooltip'
import GaugeBar from './ui/GaugeBar'

type Health = 'healthy' | 'warning' | 'critical'

const typeColors: Record<string, string> = {
  switch: '#38bdf8',
  'core-switch': '#a78bfa',
  router: '#fbbf24',
  firewall: '#f87171',
  accesspoint: '#34d399',
  'access-point': '#34d399',
  'sd-wan': '#4ade80',
  'velocloud-edge': '#2dd4bf',
  'wireless-controller': '#22d3ee',
  'load-balancer': '#f472b6',
  unknown: '#6b7280',
}

function interfaceDownCount(report: Report): number {
  return Object.entries(report.interface_status)
    .filter(([status]) => status.toLowerCase() === 'down')
    .reduce((sum, [, count]) => sum + count, 0)
}

function latestScan(report: Report): ScanHistoryEntry | undefined {
  return report.recent_scans[0] || report.scan_history[0]
}

function scanAge(scan?: ScanHistoryEntry): string {
  if (!scan?.finished_at && !scan?.started_at) return 'No completed scan'
  const value = scan.finished_at || scan.started_at
  if (!value) return 'Unknown'
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000))
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`
  return `${Math.floor(minutes / 1440)}d ago`
}

function healthFor(report: Report): { state: Health; title: string; message: string } {
  const down = interfaceDownCount(report)
  const scan = latestScan(report)
  const scanFailed = Boolean(scan && scan.status !== 'completed')
  const scanTime = scan?.finished_at || scan?.started_at
  const staleScan = !scanTime || Date.now() - new Date(scanTime).getTime() > 60 * 60 * 1000
  if (scanFailed || down > 0) {
    return {
      state: 'critical',
      title: 'Attention required',
      message: down > 0
        ? `${down} interface${down === 1 ? '' : 's'} reported down.`
        : 'The latest discovery scan did not complete successfully.',
    }
  }
  if (report.stale_devices_90d > 0 || staleScan) {
    return {
      state: 'warning',
      title: 'Network needs review',
      message: report.stale_devices_90d > 0
        ? `${report.stale_devices_90d} device${report.stale_devices_90d === 1 ? '' : 's'} have not been seen recently.`
        : 'The latest discovery data is more than one hour old.',
    }
  }
  return { state: 'healthy', title: 'Network appears healthy', message: 'No current outage indicators were found in the latest data.' }
}

const healthColors: Record<Health, { bg: string; border: string; text: string; dot: string }> = {
  healthy: { bg: 'bg-green-500/10', border: 'border-green-500/30', text: 'text-green-300', dot: 'bg-green-400' },
  warning: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-300', dot: 'bg-amber-400' },
  critical: { bg: 'bg-red-500/10', border: 'border-red-500/30', text: 'text-red-300', dot: 'bg-red-400' },
}

const healthIcon: Record<Health, string[]> = {
  healthy: ['M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z'],
  warning: ['M12 9v2m0 4h.01M10.29 3.86l-8.6 14.87A1 1 0 002.55 20h16.9a1 1 0 00.86-1.27l-8.6-14.87a1 1 0 00-1.72 0z'],
  critical: ['M12 8v4m0 4h.01M10.29 3.86l-8.6 14.87A1 1 0 002.55 20h16.9a1 1 0 00.86-1.27l-8.6-14.87a1 1 0 00-1.72 0z'],
}

function Sparkline({ values, color = 'currentColor', width = 80, height = 28 }: { values: number[]; color?: string; width?: number; height?: number }) {
  if (values.length < 2) return null
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const points = values.map((v, i) => `${(i / (values.length - 1)) * width},${height - ((v - min) / range) * (height - 4) - 2}`).join(' ')
  const area = `0,${height} ${points} ${width},${height}`
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
      <polygon points={area} fill={color} opacity="0.15" />
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function DonutChart({ data, size = 140, strokeWidth = 22 }: { data: Record<string, number>; size?: number; strokeWidth?: number }) {
  const entries = Object.entries(data).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
  const total = entries.reduce((sum, [, v]) => sum + v, 0)
  if (total === 0) return <p className="text-xs text-muted">No data.</p>
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  let offset = 0
  return (
    <div className="flex items-center gap-4">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgb(var(--surface-3))" strokeWidth={strokeWidth} />
          {entries.map(([key, value]) => {
            const pct = value / total
            const dash = circumference * pct
            const gap = circumference - dash
            const el = (
              <Tooltip key={key} content={`${key}: ${value.toLocaleString()} (${(pct * 100).toFixed(1)}%)`} position="top">
                <circle
                  cx={size / 2}
                  cy={size / 2}
                  r={radius}
                  fill="none"
                  stroke={typeColors[key] || typeColors.unknown}
                  strokeWidth={strokeWidth}
                  strokeDasharray={`${dash} ${gap}`}
                  strokeDashoffset={-offset}
                  className="transition-all duration-300 cursor-pointer hover:opacity-80"
                >
                  <title>{`${key}: ${value.toLocaleString()} (${(pct * 100).toFixed(1)}%)`}</title>
                </circle>
              </Tooltip>
            )
            offset += dash
            return el
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold text-text-primary tabular-nums">{total.toLocaleString()}</span>
          <span className="text-[10px] text-muted uppercase">total</span>
        </div>
      </div>
      <div className="space-y-1 min-w-0">
        {entries.slice(0, 6).map(([key, value]) => (
          <div key={key} className="flex items-center gap-2 text-xs">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: typeColors[key] || typeColors.unknown }} />
            <span className="text-text-secondary capitalize truncate">{key}</span>
            <span className="ml-auto text-muted tabular-nums shrink-0">{value.toLocaleString()}</span>
          </div>
        ))}
        {entries.length > 6 && <p className="text-[10px] text-muted">+{entries.length - 6} more</p>}
      </div>
    </div>
  )
}

function KpiCard({ label, value, sub, accent, tooltip, href, sparkData, sparkColor }: {
  label: string
  value: number
  sub: string
  accent: 'blue' | 'green' | 'red' | 'amber'
  tooltip: string
  href: string
  sparkData?: number[]
  sparkColor?: string
}) {
  const colors = {
    blue: 'border-l-blue-500',
    green: 'border-l-green-500',
    red: 'border-l-red-500',
    amber: 'border-l-amber-500',
  }
  return (
    <Tooltip content={tooltip} position="bottom">
      <Link to={href} className={`block bg-surface-2 border border-border border-l-4 ${colors[accent]} rounded-xl p-4 hover:bg-surface-3 transition-colors group`}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-xs font-medium text-muted uppercase tracking-wider mb-1">{label}</div>
            <div className="text-2xl font-bold text-text-primary tabular-nums">{value.toLocaleString()}</div>
            <div className="text-xs text-muted mt-1">{sub}</div>
          </div>
          {sparkData && sparkData.length >= 2 && <Sparkline values={sparkData} color={sparkColor} />}
        </div>
        <div className="mt-2 text-[11px] text-accent opacity-0 group-hover:opacity-100 transition-opacity">View details &rarr;</div>
      </Link>
    </Tooltip>
  )
}

function AlertItem({ severity, title, message, href }: { severity: 'critical' | 'warning' | 'info'; title: string; message: string; href: string }) {
  const colors = {
    critical: 'bg-red-500/10 border-red-500/30 text-red-300',
    warning: 'bg-amber-500/10 border-amber-500/30 text-amber-300',
    info: 'bg-blue-500/10 border-blue-500/30 text-blue-300',
  }
  return (
    <Link to={href} className={`flex items-start gap-3 rounded-lg border px-3 py-3 ${colors[severity]} hover:opacity-90 transition-opacity`}>
      <Badge label={severity} />
      <div className="min-w-0">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs opacity-80 mt-0.5">{message}</p>
      </div>
      <span className="ml-auto text-xs opacity-60 shrink-0">&rarr;</span>
    </Link>
  )
}

function ScanTimeline({ scans }: { scans: ScanHistoryEntry[] }) {
  const visible = scans.slice(0, 8)
  if (visible.length === 0) return <p className="text-xs text-muted">No scans recorded yet.</p>
  return (
    <div className="space-y-0">
      {visible.map((scan, index) => (
        <Link key={scan.id} to={`/topology?scan_id=${scan.id}`} className="flex items-start gap-3 group">
          <div className="flex flex-col items-center">
            <div className={`w-2.5 h-2.5 rounded-full shrink-0 mt-1 ${scan.status === 'completed' ? 'bg-green-400' : 'bg-red-400'}`} />
            {index < visible.length - 1 && <div className="w-px h-8 bg-border" />}
          </div>
          <div className="pb-3 min-w-0">
            <p className="text-xs font-medium text-text-primary truncate group-hover:text-accent transition-colors">{scan.subnet}</p>
            <p className="text-[11px] text-muted">{scan.device_count} devices &middot; {scan.started_at?.slice(0, 16).replace('T', ' ') || 'Unknown'}</p>
          </div>
        </Link>
      ))}
    </div>
  )
}

export default function OperationsDashboard() {
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [typeFilter, setTypeFilter] = useState('')
  const [siteFilter, setSiteFilter] = useState('')
  const [refreshMs, setRefreshMs] = useState(30_000)

  const refresh = useCallback(async (initial = false) => {
    if (initial) setLoading(true)
    else setRefreshing(true)
    try {
      setReport(await getReport())
      setUpdatedAt(new Date())
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load operations dashboard')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    void refresh(true)
    const timer = window.setInterval(() => void refresh(), refreshMs)
    return () => window.clearInterval(timer)
  }, [refresh, refreshMs])

  if (loading) return <PageState type="loading" title="Loading operations dashboard..." className="h-full" />
  if (error && !report) {
    return <PageState type="error" title="Dashboard unavailable" message={error} className="h-full" action={<Button variant="danger" size="sm" onClick={() => void refresh(true)}>Retry</Button>} />
  }
  if (!report) return null

  const health = healthFor(report)
  const down = interfaceDownCount(report)
  const scan = latestScan(report)
  const filteredDevices = siteFilter
    ? report.by_site[siteFilter] || 0
    : typeFilter
      ? report.by_device_type[typeFilter] || 0
      : report.total_devices
  const visibleTypes = typeFilter ? { [typeFilter]: report.by_device_type[typeFilter] || 0 } : report.by_device_type
  const visibleSites = siteFilter ? { [siteFilter]: report.by_site[siteFilter] || 0 } : report.by_site
  const hasFilters = Boolean(typeFilter || siteFilter)
  const scanHistoryValues = [...report.scan_history].reverse().map((s) => s.device_count)
  const hc = healthColors[health.state]

  const alerts: { severity: 'critical' | 'warning' | 'info'; title: string; message: string; href: string }[] = []
  if (down > 0) alerts.push({ severity: 'critical', title: 'Interfaces down', message: `${down} interface${down === 1 ? '' : 's'} reported down.`, href: '/dashboard' })
  if (scan?.status !== 'completed') alerts.push({ severity: 'critical', title: 'Latest scan failed', message: `Scan "${scan?.subnet || 'unknown'}" did not complete.`, href: '/dashboard' })
  if (report.stale_devices_90d > 0) alerts.push({ severity: 'warning', title: 'Stale devices', message: `${report.stale_devices_90d} devices not seen in 90 days.`, href: '/quality' })
  if (!scan?.finished_at || Date.now() - new Date(scan.finished_at).getTime() > 60 * 60 * 1000) alerts.push({ severity: 'info', title: 'Data may be stale', message: 'Latest discovery is more than one hour old.', href: '/discover' })

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <PageHeader
          title="Operations Dashboard"
          description="A live, interactive view of network health and potential outages."
          actions={
            <div className="flex items-center gap-3">
              <Select value={String(refreshMs)} onChange={(e) => setRefreshMs(Number(e.target.value))} className="text-xs w-36">
                <option value="10000">Every 10s</option>
                <option value="30000">Every 30s</option>
                <option value="60000">Every 1m</option>
                <option value="300000">Every 5m</option>
              </Select>
              <span className="text-xs text-muted whitespace-nowrap">{refreshing ? 'Refreshing...' : updatedAt ? `Updated ${updatedAt.toLocaleTimeString()}` : 'Waiting for data'}</span>
              <Button variant="secondary" size="sm" onClick={() => void refresh()} disabled={refreshing}>Refresh</Button>
              <div className="h-5 w-px bg-border" />
              <Tooltip content="Export inventory data as CSV" position="bottom">
                <Button variant="ghost" size="sm" onClick={() => void exportReport('devices')}>Export</Button>
              </Tooltip>
            </div>
          }
        />

        <Card padding={false}>
          <div className="flex flex-wrap items-center gap-2 px-4 py-2.5">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted mr-1">Quick actions</span>
            <Link to="/discover" className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface-2 text-text-secondary hover:bg-surface-3 hover:text-text-primary transition-colors">Run Discovery</Link>
            <Link to="/catalyst" className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface-2 text-text-secondary hover:bg-surface-3 hover:text-text-primary transition-colors">Import Catalyst</Link>
            <Link to="/topology" className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface-2 text-text-secondary hover:bg-surface-3 hover:text-text-primary transition-colors">View Topology</Link>
            <Link to="/configs" className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface-2 text-text-secondary hover:bg-surface-3 hover:text-text-primary transition-colors">Collect Configs</Link>
            <div className="flex-1" />
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-muted">Type</span>
              <Select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="min-w-36 text-xs">
                <option value="">All types</option>
                {Object.keys(report.by_device_type).filter(Boolean).sort().map((t) => <option key={t} value={t}>{t}</option>)}
              </Select>
              <span className="text-[11px] text-muted">Site</span>
              <Select value={siteFilter} onChange={(e) => setSiteFilter(e.target.value)} className="min-w-40 text-xs">
                <option value="">All sites</option>
                {Object.keys(report.by_site).filter(Boolean).sort().map((s) => <option key={s} value={s}>{s}</option>)}
              </Select>
              {hasFilters && <Button variant="ghost" size="sm" onClick={() => { setTypeFilter(''); setSiteFilter('') }}>Clear</Button>}
            </div>
          </div>
        </Card>

        <div className={`rounded-xl border px-4 py-3 flex items-center justify-between gap-4 ${hc.bg} ${hc.border} ${hc.text}`}>
          <div className="flex items-center gap-3">
            <span className={`w-3 h-3 rounded-full ${hc.dot} animate-pulse`} />
            <div>
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
                  {healthIcon[health.state].map((d, i) => <path key={i} d={d} />)}
                </svg>
                <h2 className="font-semibold">{health.title}</h2>
              </div>
              <p className="text-xs opacity-80 mt-0.5">{health.message}</p>
            </div>
          </div>
          {health.state !== 'healthy' && <Link className="text-xs font-semibold underline shrink-0" to="/quality">Review details &rarr;</Link>}
        </div>

        {error && <div className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">Refresh warning: {error}</div>}

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard label={hasFilters ? 'Filtered devices' : 'Devices'} value={filteredDevices} sub={hasFilters ? 'matching filters' : 'known network devices'} accent="blue" tooltip="Total known devices in inventory. Click to open Inventory." href="/inventory" sparkData={scanHistoryValues} sparkColor="#3b82f6" />
          <KpiCard label="Connections" value={report.total_links} sub="topology links" accent="green" tooltip="Total topology links. Click to open Topology." href="/topology" />
          <KpiCard label="Interfaces down" value={down} sub="current persisted status" accent={down > 0 ? 'red' : 'green'} tooltip="Interfaces reporting operational down. Click to open Quality." href="/quality" />
          <KpiCard label="Stale devices" value={report.stale_devices_90d} sub="not seen in 90 days" accent={report.stale_devices_90d > 0 ? 'amber' : 'green'} tooltip="Devices missing from recent scans. Click to open Quality." href="/quality" />
        </div>

        <div className="grid lg:grid-cols-3 gap-4">
          <Card>
            <div className="flex items-start justify-between gap-3 mb-4">
              <div>
                <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Latest scan</h2>
                <p className="text-xs text-muted mt-1">How fresh is the network view?</p>
              </div>
              <Badge label={scan?.status || 'unknown'} dot />
            </div>
            <div className="text-3xl font-bold text-text-primary tabular-nums">{scanAge(scan)}</div>
            <p className="text-xs text-muted mt-1 truncate">{scan?.subnet || 'No scan recorded'}</p>
            <div className="grid grid-cols-2 gap-3 mt-5 text-xs">
              <div className="bg-surface-3/50 rounded-lg p-3"><span className="text-muted block">Devices found</span><strong className="text-text-primary text-lg">{scan?.device_count ?? 0}</strong></div>
              <div className="bg-surface-3/50 rounded-lg p-3"><span className="text-muted block">Links found</span><strong className="text-text-primary text-lg">{scan?.links ?? 0}</strong></div>
            </div>
          </Card>
          <Card>
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Devices by type</h2>
            <DonutChart data={visibleTypes} />
          </Card>
          <Card>
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Devices by site</h2>
            <DonutChart data={visibleSites} />
          </Card>
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <Card>
            <div className="flex items-start justify-between gap-3 mb-4">
              <div><h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Discovery trend</h2><p className="text-xs text-muted mt-1">Devices found in recent scans</p></div>
              <Tooltip content="Hover a point for scan name and device count."><span className="text-xs text-muted cursor-help">What is this?</span></Tooltip>
            </div>
            <ScanTrend scans={report.recent_scans} />
          </Card>
          <Card>
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Interfaces by status</h2>
            <DonutChart data={report.interface_status} />
          </Card>
        </div>

        <div className="grid lg:grid-cols-3 gap-4">
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Scan timeline</h2>
              <span className="text-[11px] text-muted">{report.recent_scans.length} recent</span>
            </div>
            <ScanTimeline scans={report.recent_scans} />
          </Card>
          <Card>
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Alerts</h2>
            {alerts.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <svg className="w-8 h-8 text-green-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                <p className="text-sm text-text-secondary font-medium">All clear</p>
                <p className="text-xs text-muted mt-0.5">No alerts at this time.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {alerts.map((alert, i) => <AlertItem key={i} {...alert} />)}
              </div>
            )}
          </Card>
          <Card>
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Config coverage</h2>
            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-text-secondary">Devices with configs</span>
                  <span className="text-muted tabular-nums">{report.config_coverage.devices_with_config} / {report.total_devices}</span>
                </div>
                <div className="h-3 rounded-full bg-surface-3 overflow-hidden">
                  <div className="h-full rounded-full bg-green-500 transition-all duration-500" style={{ width: `${report.total_devices > 0 ? (report.config_coverage.devices_with_config / report.total_devices) * 100 : 0}%` }} />
                </div>
              </div>
              {Object.entries(report.config_coverage.by_device_type || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([type, count]) => (
                <div key={type}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-text-secondary capitalize">{type}</span>
                    <span className="text-muted tabular-nums">{count}</span>
                  </div>
                  <div className="h-2 rounded-full bg-surface-3 overflow-hidden">
                    <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${Math.min(100, (count / (report.by_device_type[type] || 1)) * 100)}%` }} />
                  </div>
                </div>
              ))}
              {Object.keys(report.config_coverage.by_device_type || {}).length === 0 && <p className="text-xs text-muted">No configs collected yet.</p>}
              <Link to="/configs" className="inline-block text-xs text-accent hover:text-accent-hover">Collect configs &rarr;</Link>
            </div>
          </Card>
        </div>

        {report.dod_gates && Object.keys(report.dod_gates).length > 0 && (
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Definition of Done</h2>
              <span className="text-[11px] text-muted">Sprint 13 targets</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              {Object.entries(report.dod_gates).map(([key, gate]) => (
                <div key={key} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted capitalize">{key}</span>
                    <Badge label={gate.met ? 'met' : 'gap'} />
                  </div>
                  <div className="text-3xl font-bold text-text-primary tabular-nums">{gate.actual}%</div>
                  <GaugeBar label="target" actual={gate.actual} target={gate.target} />
                </div>
              ))}
            </div>
          </Card>
        )}

        <div className="grid lg:grid-cols-2 gap-4">
          <Card>
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Devices by vendor</h2>
            <div className="space-y-2">
              {Object.entries(report.by_vendor).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 8).map(([k, v]) => {
                const max = Math.max(...Object.values(report.by_vendor), 1)
                return (
                  <div key={k} className="flex items-center gap-3 text-xs">
                    <span className="w-36 shrink-0 truncate text-muted">{k}</span>
                    <div className="flex-1 h-2.5 bg-surface-3 rounded-full overflow-hidden">
                      <div className="h-full rounded-full bg-purple-500 transition-all" style={{ width: `${(v / max) * 100}%` }} />
                    </div>
                    <span className="w-12 text-right text-muted tabular-nums font-medium">{v}</span>
                  </div>
                )
              })}
              {Object.keys(report.by_vendor).length === 0 && <p className="text-xs text-muted">No vendor data available.</p>}
            </div>
          </Card>
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Export data</h2>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Button variant="secondary" size="sm" onClick={() => void exportReport('devices')} className="w-full">Export Devices</Button>
              <Button variant="secondary" size="sm" onClick={() => void exportReport('links')} className="w-full">Export Links</Button>
              <Button variant="secondary" size="sm" onClick={() => void exportReport('configs')} className="w-full">Export Configs</Button>
              <Button variant="secondary" size="sm" onClick={() => void exportReport('scans')} className="w-full">Export Scans</Button>
            </div>
          </Card>
        </div>

        <Card padding={false}>
          <div className="p-5 pb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Scan History</h2>
            <span className="text-[11px] text-muted">{report.scan_history.length} scans</span>
          </div>
          <div className="overflow-auto max-h-80">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-2 z-10">
                <tr className="text-left text-muted text-[11px] uppercase tracking-wider">
                  <th className="px-5 py-2 font-medium">Scan</th>
                  <th className="px-5 py-2 font-medium">Status</th>
                  <th className="px-5 py-2 font-medium text-right">Devices</th>
                  <th className="px-5 py-2 font-medium text-right">Links</th>
                  <th className="px-5 py-2 font-medium">Started</th>
                  <th className="px-5 py-2 font-medium">Finished</th>
                </tr>
              </thead>
              <tbody>
                {report.scan_history.map((s) => (
                  <tr key={s.id} className="border-t border-border hover:bg-surface-3/50 transition-colors">
                    <td className="px-5 py-2">
                      <span className="font-mono text-xs">{s.subnet}</span>
                      <span className="text-muted ml-2 font-mono text-[10px]">{s.id.slice(0, 8)}</span>
                    </td>
                    <td className="px-5 py-2"><Badge label={s.status} /></td>
                    <td className="px-5 py-2 text-right tabular-nums text-xs">{s.device_count}</td>
                    <td className="px-5 py-2 text-right tabular-nums text-xs text-muted">{s.links}</td>
                    <td className="px-5 py-2 text-xs text-muted">{s.started_at?.slice(0, 16) || '\u2014'}</td>
                    <td className="px-5 py-2 text-xs text-muted">{s.finished_at?.slice(0, 16) || '\u2014'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  )
}

function ScanTrend({ scans }: { scans: ScanHistoryEntry[] }) {
  const points = [...scans].reverse().slice(-12)
  if (points.length < 2) return <p className="text-xs text-muted py-8">Run more scans to see the device-count trend.</p>
  const max = Math.max(...points.map((scan) => scan.device_count), 1)
  const min = Math.min(...points.map((scan) => scan.device_count), 0)
  const range = Math.max(max - min, 1)
  const coords = points.map((scan, index) => ({
    scan,
    x: (index / (points.length - 1)) * 100,
    y: 90 - ((scan.device_count - min) / range) * 78,
  }))
  const line = coords.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')
  const area = `M ${coords[0].x} 90 ${coords.map((p) => `L ${p.x} ${p.y}`).join(' ')} L ${coords[coords.length - 1].x} 90 Z`
  return (
    <div className="relative h-44">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full overflow-visible">
        <path d="M 0 90 L 100 90" stroke="rgb(var(--border))" strokeWidth="0.5" strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />
        <path d="M 0 45 L 100 45" stroke="rgb(var(--border))" strokeWidth="0.3" strokeDasharray="2 4" vectorEffect="non-scaling-stroke" />
        <path d={area} fill="rgb(var(--accent))" opacity="0.12" />
        <path d={line} fill="none" stroke="rgb(var(--accent))" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        {coords.map((point) => (
          <Tooltip key={point.scan.id} content={`${point.scan.subnet}: ${point.scan.device_count} devices`} position="top">
            <circle cx={point.x} cy={point.y} r="3" fill="rgb(var(--surface-1))" stroke="rgb(var(--accent))" strokeWidth="1.5" className="cursor-pointer hover:r-4 transition-all" vectorEffect="non-scaling-stroke" />
          </Tooltip>
        ))}
      </svg>
      <div className="absolute inset-x-0 bottom-0 flex justify-between text-[10px] text-muted">
        <span>{points[0].started_at?.slice(5, 10) || ''}</span>
        <span>{points[points.length - 1].started_at?.slice(5, 10) || ''}</span>
      </div>
    </div>
  )
}
