import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getReport, type Report, type ScanHistoryEntry } from '../api'
import Badge from './ui/Badge'
import Button from './ui/Button'
import Card from './ui/Card'
import PageHeader from './ui/PageHeader'
import PageState from './ui/PageState'
import StatCard from './ui/StatCard'
import Select from './ui/Select'
import Tooltip from './ui/Tooltip'

type Health = 'healthy' | 'warning' | 'critical'

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
      message: down > 0 ? `${down} interface${down === 1 ? '' : 's'} reported down.` : 'The latest discovery scan did not complete successfully.',
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

const healthStyles: Record<Health, string> = {
  healthy: 'border-green-500/30 bg-green-500/10 text-green-300',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  critical: 'border-red-500/30 bg-red-500/10 text-red-300',
}

function Distribution({
  title,
  values,
  selected,
  onSelect,
}: {
  title: string
  values: Record<string, number>
  selected?: string
  onSelect?: (value: string) => void
}) {
  const rows = Object.entries(values).filter(([, value]) => value > 0).sort((a, b) => b[1] - a[1]).slice(0, 8)
  const maximum = Math.max(...rows.map(([, value]) => value), 1)
  return (
    <Card>
      <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">{title}</h2>
      <div className="space-y-3">
        {rows.map(([label, value]) => (
          <Tooltip key={label} content={`${label || 'unknown'}: ${value.toLocaleString()} devices`} position="top">
            <button
              type="button"
              onClick={() => onSelect?.(label)}
              className={`block w-full text-left rounded-lg p-1.5 -m-1.5 transition-colors ${onSelect ? 'hover:bg-surface-2' : ''} ${selected === label ? 'bg-accent-subtle' : ''}`}
            >
            <div className="flex justify-between gap-3 text-xs mb-1">
              <span className="text-text-secondary truncate capitalize">{label || 'unknown'}</span>
              <span className="text-muted tabular-nums">{value.toLocaleString()}</span>
            </div>
            <div className="h-2 rounded-full bg-surface-3 overflow-hidden">
              <div className="h-full rounded-full bg-accent" style={{ width: `${(value / maximum) * 100}%` }} />
            </div>
            </button>
          </Tooltip>
        ))}
        {rows.length === 0 && <p className="text-xs text-muted">No data available.</p>}
      </div>
    </Card>
  )
}

function ScanTrend({ scans }: { scans: ScanHistoryEntry[] }) {
  const points = [...scans].reverse().slice(-10)
  if (points.length < 2) {
    return <p className="text-xs text-muted py-8">Run more scans to see the device-count trend.</p>
  }
  const max = Math.max(...points.map((scan) => scan.device_count), 1)
  const min = Math.min(...points.map((scan) => scan.device_count), 0)
  const range = Math.max(max - min, 1)
  const coords = points.map((scan, index) => ({
    scan,
    x: (index / (points.length - 1)) * 100,
    y: 92 - ((scan.device_count - min) / range) * 78,
  }))
  const line = coords.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ')

  return (
    <div className="relative h-40">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full overflow-visible">
        <path d="M 0 92 L 100 92" stroke="rgb(var(--border))" strokeWidth="0.5" vectorEffect="non-scaling-stroke" />
        <path d={line} fill="none" stroke="rgb(var(--accent))" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {coords.map((point) => (
          <circle key={point.scan.id} cx={point.x} cy={point.y} r="2.5" fill="rgb(var(--accent))" vectorEffect="non-scaling-stroke">
            <title>{`${point.scan.subnet}: ${point.scan.device_count} devices`}</title>
          </circle>
        ))}
      </svg>
      <div className="absolute inset-x-0 bottom-0 flex justify-between text-[10px] text-muted">
        <span>{points[0].started_at?.slice(0, 10) || ''}</span>
        <span>{points[points.length - 1].started_at?.slice(0, 10) || ''}</span>
      </div>
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
    const timer = window.setInterval(() => void refresh(), 30_000)
    return () => window.clearInterval(timer)
  }, [refresh])

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

  const clearFilters = () => {
    setTypeFilter('')
    setSiteFilter('')
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <PageHeader
          title="Operations Dashboard"
          description="A live, beginner-friendly view of network health and potential outages."
          actions={
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted">{refreshing ? 'Refreshing...' : updatedAt ? `Updated ${updatedAt.toLocaleTimeString()}` : 'Waiting for data'}</span>
              <Button variant="secondary" size="sm" onClick={() => void refresh()} disabled={refreshing}>Refresh</Button>
            </div>
          }
        />

        <Card padding={false}>
          <div className="flex flex-wrap items-center gap-3 px-4 py-3">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Explore</span>
            <Select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} className="min-w-44 text-xs">
              <option value="">All device types</option>
              {Object.keys(report.by_device_type).filter(Boolean).sort().map((type) => <option key={type} value={type}>{type}</option>)}
            </Select>
            <Select value={siteFilter} onChange={(event) => setSiteFilter(event.target.value)} className="min-w-52 text-xs">
              <option value="">All sites</option>
              {Object.keys(report.by_site).filter(Boolean).sort().map((site) => <option key={site} value={site}>{site}</option>)}
            </Select>
            {hasFilters && <Button variant="ghost" size="sm" onClick={clearFilters}>Clear filters</Button>}
            <span className="ml-auto text-xs text-muted">Click a chart bar to filter.</span>
          </div>
        </Card>

        <div className={`rounded-xl border px-4 py-3 flex items-center justify-between gap-4 ${healthStyles[health.state]}`}>
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-current" />
              <h2 className="font-semibold">{health.title}</h2>
            </div>
            <p className="text-xs opacity-80 mt-1">{health.message}</p>
          </div>
          {health.state !== 'healthy' && <Link className="text-xs font-semibold underline shrink-0" to="/quality">Review details</Link>}
        </div>

        {error && <div className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">Refresh warning: {error}</div>}

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Tooltip content="Known devices, narrowed by the selected site or device type." position="bottom"><div><StatCard label={hasFilters ? 'Filtered devices' : 'Devices'} value={filteredDevices.toLocaleString()} sub={hasFilters ? 'matching current filters' : 'known network devices'} accent="blue" /></div></Tooltip>
          <StatCard label="Connections" value={report.total_links.toLocaleString()} sub="topology links" accent="green" />
          <StatCard label="Interfaces down" value={down.toLocaleString()} sub="current persisted status" accent={down > 0 ? 'red' : 'green'} />
          <StatCard label="Stale devices" value={report.stale_devices_90d.toLocaleString()} sub="not seen in 90 days" accent={report.stale_devices_90d > 0 ? 'amber' : 'green'} />
        </div>

        <div className="grid lg:grid-cols-3 gap-4">
          <Card>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Latest scan</h2>
                <p className="text-xs text-muted mt-1">How fresh is the network view?</p>
              </div>
              <Badge label={scan?.status || 'unknown'} dot />
            </div>
            <div className="mt-5 text-3xl font-bold text-text-primary tabular-nums">{scanAge(scan)}</div>
            <p className="text-xs text-muted mt-1 truncate">{scan?.subnet || 'No scan recorded'}</p>
            <div className="grid grid-cols-2 gap-3 mt-5 text-xs">
              <div className="bg-surface-2 rounded-lg p-3"><span className="text-muted block">Devices found</span><strong className="text-text-primary text-lg">{scan?.device_count ?? 0}</strong></div>
              <div className="bg-surface-2 rounded-lg p-3"><span className="text-muted block">Links found</span><strong className="text-text-primary text-lg">{scan?.links ?? 0}</strong></div>
            </div>
          </Card>
          <Distribution title="Devices by type" values={visibleTypes} selected={typeFilter} onSelect={(value) => setTypeFilter(typeFilter === value ? '' : value)} />
          <Distribution title="Interfaces by status" values={report.interface_status} />
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <Card>
            <div className="flex items-start justify-between gap-3 mb-4">
              <div><h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Discovery trend</h2><p className="text-xs text-muted mt-1">Devices found in recent scans</p></div>
              <Tooltip content="Hover a point for scan name and device count."><span className="text-xs text-muted cursor-help">What is this?</span></Tooltip>
            </div>
            <ScanTrend scans={report.recent_scans} />
          </Card>
          <Distribution title="Devices by site" values={visibleSites} selected={siteFilter} onSelect={(value) => setSiteFilter(siteFilter === value ? '' : value)} />
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Recent scans</h2>
              <Link to="/reports" className="text-xs text-accent hover:text-accent-hover">View reports</Link>
            </div>
            <div className="space-y-2">
              {report.recent_scans.slice(0, 6).map((item) => (
                <div key={item.id} className="flex items-center justify-between gap-3 rounded-lg bg-surface-2 px-3 py-2 text-xs">
                  <div className="min-w-0"><p className="text-text-secondary truncate">{item.subnet}</p><p className="text-muted">{item.started_at?.slice(0, 16).replace('T', ' ') || 'Unknown time'}</p></div>
                  <div className="flex items-center gap-3 shrink-0"><span className="text-muted tabular-nums">{item.device_count} devices</span><Badge label={item.status} dot /></div>
                </div>
              ))}
              {report.recent_scans.length === 0 && <p className="text-xs text-muted">No scans recorded yet.</p>}
            </div>
          </Card>
          <Card>
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">What needs attention?</h2>
            <div className="space-y-3 text-sm">
              <div className={`flex items-start gap-3 rounded-lg p-3 ${down > 0 ? 'bg-red-500/10' : 'bg-surface-2'}`}><span className={down > 0 ? 'text-red-300' : 'text-green-300'}>{down > 0 ? '!' : 'OK'}</span><div><strong className="text-text-primary">Interface status</strong><p className="text-xs text-muted mt-0.5">{down > 0 ? `${down} interface${down === 1 ? '' : 's'} reported down.` : 'No interfaces are currently marked down.'}</p></div></div>
              <div className={`flex items-start gap-3 rounded-lg p-3 ${report.stale_devices_90d > 0 ? 'bg-amber-500/10' : 'bg-surface-2'}`}><span className={report.stale_devices_90d > 0 ? 'text-amber-300' : 'text-green-300'}>{report.stale_devices_90d > 0 ? '!' : 'OK'}</span><div><strong className="text-text-primary">Device freshness</strong><p className="text-xs text-muted mt-0.5">{report.stale_devices_90d > 0 ? `${report.stale_devices_90d} devices need a recent discovery check.` : 'All devices are within the freshness threshold.'}</p></div></div>
              <div className="flex items-start gap-3 rounded-lg p-3 bg-surface-2"><span className="text-accent">i</span><div><strong className="text-text-primary">Need deeper analysis?</strong><p className="text-xs text-muted mt-0.5">Use Topology for relationships, Inventory for device detail, or Grafana for historical metrics.</p></div></div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
