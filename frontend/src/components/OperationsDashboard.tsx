import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getReport, exportReport, type Report, type ScanHistoryEntry } from '../api'
import Badge from './ui/Badge'
import Button from './ui/Button'
import Card from './ui/Card'
import PageHeader from './ui/PageHeader'
import PageState from './ui/PageState'
import Select from './ui/Select'
import Tooltip from './ui/Tooltip'
import Skeleton from './ui/Skeleton'
import ExecutiveDashboard from './ExecutiveDashboard'

function DashboardSkeleton() {
  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Skeleton className="h-7 w-56 mb-2" />
            <Skeleton className="h-4 w-72" />
          </div>
          <div className="flex gap-3">
            <Skeleton className="h-8 w-36" />
            <Skeleton className="h-8 w-20" />
          </div>
        </div>
        <Skeleton className="h-14 w-full" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
        <div className="grid lg:grid-cols-3 gap-4">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
        <div className="grid lg:grid-cols-2 gap-4">
          <Skeleton className="h-56" />
          <Skeleton className="h-56" />
        </div>
      </div>
    </div>
  )
}

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

const siteColors = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4', '#f43f5e', '#84cc16', '#6366f1', '#14b8a6']

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

function formatTimestamp(value?: string | null): string {
  if (!value) return '\u2014'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
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

const healthColors: Record<Health, { bg: string; border: string; text: string; dot: string; glow: string }> = {
  healthy: { bg: 'bg-green-500/10', border: 'border-green-500/30', text: 'text-green-300', dot: 'bg-green-400', glow: 'shadow-green-500/50' },
  warning: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-300', dot: 'bg-amber-400', glow: 'shadow-amber-500/50' },
  critical: { bg: 'bg-red-500/10', border: 'border-red-500/30', text: 'text-red-300', dot: 'bg-red-400', glow: 'shadow-red-500/50' },
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
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible" role="img" aria-label={`Trend of ${values.length} points from ${values[0]} to ${values[values.length - 1]}`}>
      <polygon points={area} fill={color} opacity="0.15" />
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function DonutChart({ data, size = 120, strokeWidth = 20, colorFor }: { data: Record<string, number>; size?: number; strokeWidth?: number; colorFor: (key: string) => string }) {
  const entries = Object.entries(data).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
  const total = entries.reduce((sum, [, v]) => sum + v, 0)
  if (total === 0) return <p className="text-xs text-muted">No data.</p>
  const summary = `${total.toLocaleString()} total — ${entries.slice(0, 6).map(([k, v]) => `${k} ${v.toLocaleString()}`).join(', ')}${entries.length > 6 ? `, +${entries.length - 6} more` : ''}`
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  let offset = 0
  return (
    <div className="flex items-center gap-5">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90" role="img" aria-label={summary}>
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgb(var(--surface-3))" strokeWidth={strokeWidth} />
          {entries.map(([key, value]) => {
            const pct = value / total
            const dash = circumference * pct
            const gap = circumference - dash
            return (
              <Tooltip key={key} content={`${key}: ${value.toLocaleString()} (${(pct * 100).toFixed(1)}%)`} position="top">
                <circle
                  cx={size / 2}
                  cy={size / 2}
                  r={radius}
                  fill="none"
                  stroke={colorFor(key)}
                  strokeWidth={strokeWidth}
                  strokeDasharray={`${dash} ${gap}`}
                  strokeDashoffset={-offset}
                  className="transition-all duration-300 cursor-pointer hover:opacity-80"
                >
                  <title>{`${key}: ${value.toLocaleString()} (${(pct * 100).toFixed(1)}%)`}</title>
                </circle>
              </Tooltip>
            )
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-lg font-bold text-text-primary tabular-nums">{total.toLocaleString()}</span>
          <span className="text-[10px] text-muted uppercase">total</span>
        </div>
      </div>
      <div className="space-y-1 min-w-0">
        {entries.slice(0, 6).map(([key, value]) => (
          <div key={key} className="flex items-center gap-2 text-xs">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: colorFor(key) }} />
            <span className="text-text-secondary capitalize truncate">{key}</span>
            <span className="ml-auto text-muted tabular-nums shrink-0">{value.toLocaleString()}</span>
          </div>
        ))}
        {entries.length > 6 && <p className="text-[10px] text-muted">+{entries.length - 6} more</p>}
      </div>
    </div>
  )
}

function DistributionCard({ report }: { report: Report }) {
  const [dimension, setDimension] = useState<'type' | 'site' | 'vendor'>('type')
  const data = dimension === 'type' ? report.by_device_type
    : dimension === 'site' ? report.by_site
    : report.by_vendor
  const colorFor = (key: string) => dimension === 'type'
    ? (typeColors[key] || typeColors.unknown)
    : siteColors[Math.abs(hashString(key)) % siteColors.length]
  return (
    <Card>
      <div className="flex items-center justify-between gap-3 mb-4">
        <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Devices by</h2>
        <div className="flex items-center gap-0.5 bg-surface-2/70 backdrop-blur rounded-xl p-0.5">
          {(['type', 'site', 'vendor'] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDimension(d)}
              className={`px-3 py-1 rounded-lg text-xs font-medium capitalize transition-all duration-150 ${
                dimension === d ? 'bg-accent/15 text-accent' : 'text-muted hover:text-text-secondary'
              }`}
            >
              {d}
            </button>
          ))}
        </div>
      </div>
      <DonutChart data={data} colorFor={colorFor} />
    </Card>
  )
}

function hashString(input: string): number {
  let hash = 0
  for (let i = 0; i < input.length; i++) hash = (hash * 31 + input.charCodeAt(i)) | 0
  return Math.abs(hash)
}

function KpiCard({ label, value, sub, accent, tooltip, href, sparkData, sparkColor }: {
  label: string
  value: number
  sub: string
  accent: 'blue' | 'green' | 'red' | 'amber' | 'violet' | 'cyan'
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
    violet: 'border-l-violet-500',
    cyan: 'border-l-cyan-500',
  }
  return (
    <Tooltip content={tooltip} position="bottom">
      <Link to={href} className={`block bg-surface-2/80 backdrop-blur border border-border/40 border-l-4 ${colors[accent]} rounded-2xl p-4 hover:shadow-lg hover:border-border/60 hover:-translate-y-px transition-all duration-200 group`}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-xs font-medium text-muted uppercase tracking-wider mb-1">{label}</div>
            <div className="text-2xl font-bold text-text-primary tabular-nums">{value.toLocaleString()}</div>
            <div className="text-xs text-muted mt-1">{sub}</div>
          </div>
          {sparkData && sparkData.length >= 2 && <Sparkline values={sparkData} color={sparkColor} />}
        </div>
        <div className="mt-2 text-[11px] text-accent">View details &rarr;</div>
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
    <Link to={href} className={`flex items-start gap-3 rounded-xl border px-3 py-3 ${colors[severity]} hover:opacity-90 transition-opacity`}>
      <Badge label={severity} />
      <div className="min-w-0">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs opacity-80 mt-0.5">{message}</p>
      </div>
      <span className="ml-auto text-xs opacity-60 shrink-0">&rarr;</span>
    </Link>
  )
}

function ExportMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    document.addEventListener('keydown', keyHandler)
    return () => {
      document.removeEventListener('mousedown', handler)
      document.removeEventListener('keydown', keyHandler)
    }
  }, [open])

  const items = [
    { label: 'Export Devices', key: 'devices', handler: () => exportReport('devices') },
    { label: 'Export Links', key: 'links', handler: () => exportReport('links') },
    { label: 'Export Scans', key: 'scans', handler: () => exportReport('scans') },
  ]

  return (
    <div className="relative" ref={ref}>
      <Button variant="secondary" size="sm" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <svg className="w-3.5 h-3.5 mr-1.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
        </svg>
        Export
      </Button>
      {open && (
        <div className="absolute right-0 top-full mt-2 w-48 bg-surface-1/90 backdrop-blur-2xl border border-border/40 rounded-2xl shadow-popover p-1.5 z-50">
          {items.map((item) => (
            <button
              key={item.key}
              onClick={() => { setOpen(false); void item.handler() }}
              className="flex items-center gap-2 w-full px-3 py-2 rounded-xl text-sm text-muted hover:text-text-secondary hover:bg-surface-2/60 transition-all duration-150"
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
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
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full overflow-visible" role="img" aria-label={`Device count trend across ${points.length} scans, latest ${points[points.length - 1].device_count} devices`}>
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

export default function OperationsDashboard() {
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [refreshMs, setRefreshMs] = useState(30_000)
  const [view, setView] = useState<'ops' | 'exec'>('ops')

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
    const timer = window.setInterval(() => {
      if (!document.hidden) void refresh()
    }, refreshMs)
    return () => window.clearInterval(timer)
  }, [refresh, refreshMs])

  if (loading) return <DashboardSkeleton />
  if (error && !report) {
    return <PageState type="error" title="Dashboard unavailable" message={error} className="h-full" action={<Button variant="danger" size="sm" onClick={() => void refresh(true)}>Retry</Button>} />
  }
  if (!report) return null

  if (report.total_devices === 0) {
    return (
      <div className="h-full overflow-auto">
        <div className="p-6 max-w-7xl mx-auto">
          <PageHeader
            title="Operations Dashboard"
            description="A live, interactive view of network health and potential outages."
            actions={<Button variant="secondary" size="sm" onClick={() => void refresh()} disabled={refreshing}>Refresh</Button>}
          />
          <PageState
            type="empty"
            title="No devices discovered yet"
            message="Run your first discovery scan to populate the network inventory and this dashboard."
            className="min-h-[50vh]"
            action={<Link to="/topology" className="text-accent text-sm font-medium hover:underline">Open Topology &rarr;</Link>}
          />
        </div>
      </div>
    )
  }

  const health = healthFor(report)
  const down = interfaceDownCount(report)
  const scan = latestScan(report)
  const scanHistoryValues = [...report.scan_history].reverse().map((s) => s.device_count)
  const hc = healthColors[health.state]

  const alerts: { severity: 'critical' | 'warning' | 'info'; title: string; message: string; href: string }[] = []
  if (down > 0) alerts.push({ severity: 'critical', title: 'Interfaces down', message: `${down} interface${down === 1 ? '' : 's'} reported down.`, href: '/dashboard' })
  if (scan?.status !== 'completed') alerts.push({ severity: 'critical', title: 'Latest scan failed', message: `Scan "${scan?.subnet || 'unknown'}" did not complete.`, href: '/dashboard' })

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <PageHeader
          title={view === 'exec' ? 'Executive Dashboard' : 'Operations Dashboard'}
          description={view === 'exec'
            ? 'A management scorecard of network health, site freshness, and risk.'
            : 'A live, interactive view of network health and potential outages.'}
          actions={
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-0.5 bg-surface-2/70 backdrop-blur rounded-xl p-0.5">
                <button onClick={() => setView('ops')} className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-150 ${view === 'ops' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'}`}>Operations</button>
                <button onClick={() => setView('exec')} className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-150 ${view === 'exec' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'}`}>Executive</button>
              </div>
              {view === 'ops' && (
                <>
                  <Select value={String(refreshMs)} onChange={(e) => setRefreshMs(Number(e.target.value))} className="text-xs w-36">
                    <option value="10000">Every 10s</option>
                    <option value="30000">Every 30s</option>
                    <option value="60000">Every 1m</option>
                    <option value="300000">Every 5m</option>
                  </Select>
                  <span className="text-xs text-muted whitespace-nowrap">{refreshing ? 'Refreshing...' : updatedAt ? `Updated ${updatedAt.toLocaleTimeString()}` : 'Waiting for data'}</span>
                  <Button variant="secondary" size="sm" onClick={() => void refresh()} disabled={refreshing}>Refresh</Button>
                  <div className="h-5 w-px bg-border" />
                  <ExportMenu />
                </>
              )}
            </div>
          }
        />

        {view === 'exec' ? (
          <ExecutiveDashboard />
        ) : (
        <>

        <div className={`rounded-2xl border px-4 py-3.5 flex items-center justify-between gap-4 backdrop-blur-xl ${hc.bg} ${hc.border} ${hc.text}`}>
          <div className="flex items-center gap-3">
            <div className="relative">
              <span className={`w-3 h-3 rounded-full ${hc.dot} animate-pulse motion-safe:animate-pulse`} />
              <span className={`absolute inset-0 w-3 h-3 rounded-full ${hc.dot} ${hc.glow} shadow-lg animate-ping motion-safe:animate-ping opacity-75`} />
            </div>
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

        {error && <div className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-xl px-3 py-2 backdrop-blur">Refresh warning: {error}</div>}

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard label="Devices" value={report.total_devices} sub="known network devices" accent="blue" tooltip="Total known devices in inventory. Click to open Inventory." href="/inventory" sparkData={scanHistoryValues} sparkColor="#3b82f6" />
          <KpiCard label="Connections" value={report.total_links} sub="topology links" accent="green" tooltip="Total topology links. Click to open Topology." href="/topology" />
          <KpiCard label="Sites" value={Object.keys(report.by_site).length} sub="network locations" accent="violet" tooltip="Distinct sites across the inventory. Click to open Inventory." href="/inventory" />
          <KpiCard label="Interfaces" value={report.total_interfaces} sub="discovered interfaces" accent="cyan" tooltip="Total interfaces discovered across devices. Click to open Inventory." href="/inventory" />
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <DistributionCard report={report} />
          <Card>
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Interfaces by status</h2>
            <DonutChart data={report.interface_status} colorFor={(key) => key === 'up' ? '#34d399' : key === 'down' ? '#f87171' : '#6b7280'} />
          </Card>
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <Card>
            <div className="flex items-start justify-between gap-3 mb-4">
              <div><h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Discovery trend</h2><p className="text-xs text-muted mt-1">Devices found in recent scans</p></div>
              <span className="text-[11px] text-muted">{scanAge(scan)}</span>
            </div>
            <ScanTrend scans={report.recent_scans} />
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
        </div>

        <Card padding={false}>
          <div className="p-5 pb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Scan History</h2>
            <span className="text-[11px] text-muted">{report.scan_history.length} scans</span>
          </div>
          <div className="overflow-auto max-h-80">
            <table className="w-full text-sm">
              <caption className="sr-only">Recent network discovery scans</caption>
              <thead className="sticky top-0 bg-surface-2/80 backdrop-blur-xl z-10">
                <tr className="text-left text-muted text-[11px] uppercase tracking-wider">
                  <th scope="col" className="px-5 py-2 font-medium">Scan</th>
                  <th scope="col" className="px-5 py-2 font-medium">Status</th>
                  <th scope="col" className="px-5 py-2 font-medium text-right">Devices</th>
                  <th scope="col" className="px-5 py-2 font-medium text-right">Links</th>
                  <th scope="col" className="px-5 py-2 font-medium">Started</th>
                  <th scope="col" className="px-5 py-2 font-medium">Finished</th>
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
                    <td className="px-5 py-2 text-xs text-muted">{formatTimestamp(s.started_at)}</td>
                    <td className="px-5 py-2 text-xs text-muted">{formatTimestamp(s.finished_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        </>
        )}
      </div>
    </div>
  )
}
