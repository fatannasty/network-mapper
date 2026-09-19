import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getMonitor, type MonitorOverview } from '../api'
import PageHeader from './ui/PageHeader'
import Card, { CardHeader } from './ui/Card'
import Select from './ui/Select'
import Skeleton from './ui/Skeleton'
import { friendlyType } from '../features/topology/services/friendly'

const STATUS: Record<string, { label: string; dot: string; text: string }> = {
  up: { label: 'up', dot: 'bg-green-400', text: 'text-green-300' },
  degraded: { label: 'degraded', dot: 'bg-amber-400', text: 'text-amber-300' },
  down: { label: 'down', dot: 'bg-red-400', text: 'text-red-300' },
  flapping: { label: 'flapping', dot: 'bg-orange-400', text: 'text-orange-300' },
  unknown: { label: 'unknown', dot: 'bg-gray-400', text: 'text-gray-400' },
}

function StatusChip({ status, value }: { status: string; value: number }) {
  const s = STATUS[status] || STATUS.unknown
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-surface-2/60 text-xs">
      <span className={`w-2 h-2 rounded-full ${s.dot}`} />
      <span className="text-muted">{s.label}</span>
      <span className={`font-semibold tabular-nums ${s.text}`}>{value}</span>
    </span>
  )
}

export default function MonitorDashboard() {
  const [data, setData] = useState<MonitorOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshMs, setRefreshMs] = useState(30_000)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const timerRef = useRef<number | null>(null)

  const refresh = useCallback(async (initial = false) => {
    if (initial) setLoading(true)
    try {
      setData(await getMonitor())
      setUpdatedAt(new Date())
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load monitor data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh(true)
    return () => { if (timerRef.current) window.clearInterval(timerRef.current) }
  }, [refresh])

  useEffect(() => {
    if (timerRef.current) window.clearInterval(timerRef.current)
    if (refreshMs > 0) {
      timerRef.current = window.setInterval(() => {
        if (!document.hidden) void refresh()
      }, refreshMs)
    }
    return () => { if (timerRef.current) window.clearInterval(timerRef.current) }
  }, [refreshMs, refresh])

  if (loading) {
    return (
      <div className="h-full overflow-auto">
        <div className="p-6 max-w-7xl mx-auto space-y-6">
          <Skeleton className="h-10 w-64 mb-4" />
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-20" />)}
          </div>
          <div className="grid lg:grid-cols-2 gap-4">
            <Skeleton className="h-56" /><Skeleton className="h-56" />
          </div>
        </div>
      </div>
    )
  }
  if (error || !data) {
    return <p className="p-6 text-sm text-red-400">{error || 'No data'}</p>
  }

  const t = data.totals

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <PageHeader
          title="Monitor"
          description="Live operational status of every device type on one page."
          actions={
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted">{updatedAt ? `Updated ${updatedAt.toLocaleTimeString()}` : ''}</span>
              <Select value={String(refreshMs)} onChange={(e) => setRefreshMs(Number(e.target.value))} className="text-xs w-36">
                <option value="10000">Every 10s</option>
                <option value="30000">Every 30s</option>
                <option value="60000">Every 1m</option>
                <option value="300000">Every 5m</option>
                <option value="0">Off</option>
              </Select>
            </div>
          }
        />

        {/* Global KPI tiles */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <div className="bg-surface-3/50 rounded-xl p-3.5 border border-border/40">
            <div className="text-[11px] uppercase tracking-wide text-muted">Devices</div>
            <div className="text-2xl font-semibold tabular-nums">{t.devices.toLocaleString()}</div>
          </div>
          {(['up', 'degraded', 'down', 'flapping', 'unknown'] as const).map((k) => (
            <div key={k} className="bg-surface-3/50 rounded-xl p-3.5 border border-border/40">
              <div className={`flex items-center gap-1.5 text-[11px] uppercase tracking-wide ${STATUS[k].text}`}>
                <span className={`w-2 h-2 rounded-full ${STATUS[k].dot}`} />{STATUS[k].label}
              </div>
              <div className={`text-2xl font-semibold tabular-nums ${STATUS[k].text}`}>{t[k].toLocaleString()}</div>
            </div>
          ))}
        </div>

        {/* Per-type panels */}
        <div className="grid lg:grid-cols-2 gap-4">
          {Object.entries(data.types).map(([typeKey, ty]) => {
            const cfgPct = ty.total ? Math.round((100 * ty.with_config) / ty.total) : 0
            return (
              <Card key={typeKey}>
                <CardHeader title={`${friendlyType(typeKey)} (${ty.total})`}>
                  <span className="text-xs text-muted tabular-nums">{typeKey}</span>
                </CardHeader>
                <div className="flex flex-wrap items-center gap-1.5 mb-3">
                  <StatusChip status="up" value={ty.up} />
                  <StatusChip status="degraded" value={ty.degraded} />
                  <StatusChip status="down" value={ty.down} />
                  <StatusChip status="flapping" value={ty.flapping} />
                  <StatusChip status="unknown" value={ty.unknown} />
                </div>

                <div className="grid grid-cols-4 gap-2 text-center mb-3">
                  <div className="bg-surface-2/60 rounded-xl py-1.5">
                    <div className="text-xs font-semibold">{ty.avg_latency_ms != null ? `${ty.avg_latency_ms}ms` : '\u2014'}</div>
                    <div className="text-[10px] text-muted uppercase">Avg latency</div>
                  </div>
                  <div className="bg-surface-2/60 rounded-xl py-1.5">
                    <div className="text-xs font-semibold text-green-300">{ty.interfaces_up}</div>
                    <div className="text-[10px] text-muted uppercase">Ifaces up</div>
                  </div>
                  <div className="bg-surface-2/60 rounded-xl py-1.5">
                    <div className="text-xs font-semibold text-red-300">{ty.interfaces_down}</div>
                    <div className="text-[10px] text-muted uppercase">Ifaces down</div>
                  </div>
                  <div className="bg-surface-2/60 rounded-xl py-1.5">
                    <div className="text-xs font-semibold">{cfgPct}%</div>
                    <div className="text-[10px] text-muted uppercase">Config</div>
                  </div>
                </div>

                {ty.attention.length === 0 ? (
                  <p className="text-xs text-muted">All devices operational.</p>
                ) : (
                  <div className="overflow-auto max-h-44 rounded-xl border border-border/40">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-surface-2/80">
                        <tr className="text-left text-muted uppercase tracking-wider">
                          <th className="px-2 py-1.5">Device</th>
                          <th className="px-2 py-1.5">Site</th>
                          <th className="px-2 py-1.5 text-right">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ty.attention.map((a) => (
                          <tr key={`${ty.device_type}-${a.ip}`} className="border-t border-border/30">
                            <td className="px-2 py-1">
                              <Link to={`/inventory?focus=${encodeURIComponent(a.ip)}`} className="text-accent hover:underline">
                                <span className="font-mono">{a.hostname || a.ip}</span>
                              </Link>
                            </td>
                            <td className="px-2 py-1 text-muted">{a.site || '\u2014'}</td>
                            <td className="px-2 py-1 text-right">
                              <span className={`text-[10px] uppercase px-1.5 py-0.5 rounded ${STATUS[a.status]?.text || STATUS.unknown.text}`}>
                                {a.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      </div>
    </div>
  )
}