import { useCallback, useEffect, useMemo, useState } from 'react'
import { getReport, exportReport, type Report } from '../api'
import PageHeader from './ui/PageHeader'
import StatCard from './ui/StatCard'
import Card from './ui/Card'
import Badge from './ui/Badge'
import GaugeBar from './ui/GaugeBar'
import Button from './ui/Button'
import PageState from './ui/PageState'

function BarRow({ label, value, max, accent = 'bg-accent' }: { label: string; value: number; max: number; accent?: string }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="w-36 shrink-0 truncate text-muted">{label || 'unknown'}</span>
      <div className="flex-1 h-3 bg-surface-3 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${accent}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-12 text-right text-muted tabular-nums font-medium">{value}</span>
    </div>
  )
}

export default function Reports() {
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchData = useCallback(async () => {
    setLoading(true); setError('')
    try { setReport(await getReport()) }
    catch (err) { setError(err instanceof Error ? err.message : 'Failed to load report') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const configTypes = useMemo(() => {
    if (!report) return []
    return Object.entries(report.config_coverage.by_device_type)
      .filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1])
  }, [report])

  if (loading) return <PageState type="loading" title="Loading report..." className="h-full" />
  if (error || !report) {
    return (
      <PageState
        type="error"
        title="Failed to load report"
        message={error || 'No data'}
        className="h-full"
        action={<Button variant="danger" size="sm" onClick={fetchData}>Retry</Button>}
      />
    )
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        <PageHeader
          title="Reports"
          description="Inventory, topology, config collection and scan history."
          actions={
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => exportReport('devices')}>Devices</Button>
              <Button variant="secondary" size="sm" onClick={() => exportReport('links')}>Links</Button>
              <Button variant="secondary" size="sm" onClick={() => exportReport('configs')}>Configs</Button>
              <Button variant="secondary" size="sm" onClick={() => exportReport('scans')}>Scans</Button>
            </div>
          }
        />

        {/* Summary */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Devices" value={report.total_devices} sub={`${report.total_interfaces.toLocaleString()} interfaces`} accent="blue" />
          <StatCard label="Links" value={report.total_links} sub={Object.entries(report.link_protocols).map(([p, c]) => `${p}: ${c}`).join(' · ')} accent="green" />
          <StatCard label="Configs" value={report.config_coverage.total_configs} sub={`${report.config_coverage.devices_with_config} devices`} accent="blue" />
          <StatCard label="Stale 90d" value={report.stale_devices_90d} sub="not seen in 90 days" accent={report.stale_devices_90d > 0 ? 'amber' : 'default'} />
        </div>

        {/* DoD Gates */}
        {report.dod_gates && (
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Definition of Done</h3>
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

        {/* Interface Status */}
        {Object.keys(report.interface_status).length > 0 && (
          <Card>
            <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-3">Interface Status</h3>
            <div className="flex flex-wrap gap-2">
              {Object.entries(report.interface_status)
                .filter(([, v]) => v > 0)
                .sort((a, b) => b[1] - a[1])
                .map(([s, c]) => (
                  <span key={s} className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${
                    s === 'up' ? 'bg-green-900/40 text-green-300'
                    : s === 'down' ? 'bg-red-900/40 text-red-300'
                    : 'bg-surface-3/60 backdrop-blur border border-border/30 text-muted'
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${s === 'up' ? 'bg-green-400' : s === 'down' ? 'bg-red-400' : 'bg-gray-500'}`} />
                    {s}: {c}
                  </span>
                ))}
            </div>
          </Card>
        )}

        {/* Distribution grids */}
        <div className="grid md:grid-cols-2 gap-4">
          <Card>
            <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Devices by Type</h3>
            <div className="space-y-2">
              {Object.entries(report.by_device_type)
                .filter(([, v]) => v > 0)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 10)
                .map(([k, v]) => <BarRow key={k} label={k} value={v} max={report.total_devices} accent="bg-accent" />)
              }
            </div>
          </Card>
          <Card>
            <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Devices by Vendor</h3>
            <div className="space-y-2">
              {Object.entries(report.by_vendor)
                .filter(([, v]) => v > 0)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 10)
                .map(([k, v]) => <BarRow key={k} label={k} value={v} max={report.total_devices} accent="bg-purple-500" />)
              }
            </div>
          </Card>
          <Card>
            <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Devices by Site</h3>
            <div className="space-y-2">
              {Object.entries(report.by_site)
                .filter(([, v]) => v > 0)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 12)
                .map(([k, v]) => <BarRow key={k} label={k} value={v} max={report.by_site ? Math.max(...Object.values(report.by_site)) : 1} accent="bg-emerald-500" />)
              }
            </div>
          </Card>
          <Card>
            <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Config Coverage by Type</h3>
            {configTypes.length > 0 ? (
              <div className="space-y-2">
                {configTypes.map(([k, v]) => <BarRow key={k} label={k} value={v} max={report.total_devices} accent="bg-green-500" />)}
              </div>
            ) : (
              <p className="text-xs text-muted">No configs collected yet</p>
            )}
          </Card>
        </div>

        {/* Scan History */}
        <Card padding={false}>
          <div className="p-5 pb-3">
            <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Scan History</h3>
          </div>
          <div className="overflow-auto max-h-80">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-2/80 backdrop-blur-xl z-10">
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
                    <td className="px-5 py-2">
                      <Badge label={s.status} />
                    </td>
                    <td className="px-5 py-2 text-right tabular-nums text-xs">{s.device_count}</td>
                    <td className="px-5 py-2 text-right tabular-nums text-xs text-muted">{s.links}</td>
                    <td className="px-5 py-2 text-xs text-muted">{s.started_at?.slice(0, 16) || '—'}</td>
                    <td className="px-5 py-2 text-xs text-muted">{s.finished_at?.slice(0, 16) || '—'}</td>
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
