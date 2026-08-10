import { useCallback, useEffect, useMemo, useState } from 'react'
import { getReport, exportReport, type Report } from '../api'

function DistributionTable({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = useMemo(() => {
    return Object.entries(data)
      .filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1])
  }, [data])
  const max = entries.length ? entries[0][1] : 0

  if (entries.length === 0) {
    return (
      <div className="bg-gray-800 border border-gray-700 rounded p-4">
        <h3 className="text-sm font-semibold text-white mb-1">{title}</h3>
        <p className="text-gray-600 text-xs">No data</p>
      </div>
    )
  }

  return (
    <div className="bg-gray-800 border border-gray-700 rounded p-4">
      <h3 className="text-sm font-semibold text-white mb-3">{title}</h3>
      <div className="space-y-1.5">
        {entries.slice(0, 12).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2 text-xs">
            <span className="w-40 truncate text-gray-300">{k || 'unknown'}</span>
            <div className="flex-1 h-4 bg-gray-900 rounded overflow-hidden">
              <div
                className="h-full bg-blue-600 rounded"
                style={{ width: `${(v / max) * 100}%` }}
              />
            </div>
            <span className="w-12 text-right text-gray-400 tabular-nums">{v}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function StatCard({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded p-4">
      <span className="text-gray-500 text-xs block mb-1">{label}</span>
      <span className="text-3xl font-bold text-white tabular-nums">{value}</span>
      {sub && <span className="block text-gray-500 text-xs mt-1">{sub}</span>}
    </div>
  )
}

export default function Reports() {
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const r = await getReport()
      setReport(r)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load report')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const configTypes = useMemo(() => {
    if (!report) return []
    return Object.entries(report.config_coverage.by_device_type)
      .filter(([, v]) => v > 0)
      .sort((a, b) => b[1] - a[1])
  }, [report])

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-gray-400">
        <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (error || !report) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="bg-red-900/50 border border-red-800 rounded p-6 text-red-300">
          <p>{error}</p>
          <button onClick={fetchData} className="mt-3 px-4 py-1 bg-red-800 hover:bg-red-700 rounded text-sm">Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold">Reporting</h2>
            <p className="text-gray-400 text-sm">Inventory, topology, config collection and scan history.</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => exportReport('devices')} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-xs font-medium transition-colors">Export devices</button>
            <button onClick={() => exportReport('links')} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-xs font-medium transition-colors">Export links</button>
            <button onClick={() => exportReport('scans')} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-xs font-medium transition-colors">Export scans</button>
            <button onClick={() => exportReport('configs')} className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded text-xs font-medium transition-colors">Export configs</button>
          </div>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Devices" value={report.total_devices} sub={`${report.total_interfaces} interfaces`} />
          <StatCard label="Topology Links" value={report.total_links} sub={
            Object.entries(report.link_protocols).map(([p, c]) => `${p}: ${c}`).join(' · ')
          } />
          <StatCard label="Configs Collected" value={report.config_coverage.total_configs} sub={`${report.config_coverage.devices_with_config} devices`} />
          <StatCard label="Stale 90d" value={report.stale_devices_90d} sub="devices not seen in 90 days" />
        </div>

        {/* Interface status strip */}
        {Object.keys(report.interface_status).length > 0 && (
          <div className="bg-gray-800 border border-gray-700 rounded p-4">
            <h3 className="text-sm font-semibold text-white mb-2">Interface Status</h3>
            <div className="flex flex-wrap gap-2 text-xs">
              {Object.entries(report.interface_status)
                .filter(([, v]) => v > 0)
                .sort((a, b) => b[1] - a[1])
                .map(([s, c]) => (
                  <span key={s} className={`px-2.5 py-1 rounded-full font-medium ${
                    s === 'up' ? 'bg-green-900/50 text-green-300'
                    : s === 'down' ? 'bg-red-900/50 text-red-300'
                    : 'bg-gray-700 text-gray-300'
                  }`}>
                    {s}: {c}
                  </span>
                ))}
            </div>
          </div>
        )}

        {/* Distributions */}
        <div className="grid md:grid-cols-2 gap-4">
          <DistributionTable title="Devices by Type" data={report.by_device_type} />
          <DistributionTable title="Devices by Vendor" data={report.by_vendor} />
          <DistributionTable title="Devices by Site" data={report.by_site} />
          <div className="bg-gray-800 border border-gray-700 rounded p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Config Coverage by Type</h3>
            {configTypes.length > 0 ? (
              <div className="space-y-1.5">
                {configTypes.map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2 text-xs">
                    <span className="w-40 truncate text-gray-300">{k || 'unknown'}</span>
                    <div className="flex-1 h-4 bg-gray-900 rounded overflow-hidden">
                      <div className="h-full bg-green-600 rounded" style={{ width: `${(v / report.total_devices) * 100}%` }} />
                    </div>
                    <span className="w-12 text-right text-gray-400 tabular-nums">{v}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-600 text-xs">No configs collected yet</p>
            )}
          </div>
        </div>

        {/* Scan history */}
        <div className="bg-gray-800 border border-gray-700 rounded p-4">
          <h3 className="text-sm font-semibold text-white mb-3">Scan History</h3>
          <div className="overflow-auto max-h-96">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-gray-800">
                <tr className="text-left text-gray-500 text-xs uppercase tracking-wider">
                  <th className="px-3 py-2">Scan</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2 text-right">Devices</th>
                  <th className="px-3 py-2 text-right">Links</th>
                  <th className="px-3 py-2">Started</th>
                  <th className="px-3 py-2">Finished</th>
                </tr>
              </thead>
              <tbody>
                {report.scan_history.map((s) => (
                  <tr key={s.id} className="border-t border-gray-700/50 hover:bg-gray-700/30">
                    <td className="px-3 py-1.5 text-gray-300">
                      <span className="font-mono">{s.subnet}</span>
                      <span className="text-gray-600 ml-2 font-mono text-xs">{s.id.slice(0, 8)}</span>
                    </td>
                    <td className="px-3 py-1.5">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                        s.status === 'completed' ? 'bg-green-900/50 text-green-300'
                        : s.status === 'failed' ? 'bg-red-900/50 text-red-300'
                        : 'bg-amber-900/50 text-amber-300'
                      }`}>
                        {s.status}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-right text-gray-300 tabular-nums">{s.device_count}</td>
                    <td className="px-3 py-1.5 text-right text-gray-400 tabular-nums">{s.links}</td>
                    <td className="px-3 py-1.5 text-gray-400 text-xs">{s.started_at?.slice(0, 16) || '—'}</td>
                    <td className="px-3 py-1.5 text-gray-500 text-xs">{s.finished_at?.slice(0, 16) || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
