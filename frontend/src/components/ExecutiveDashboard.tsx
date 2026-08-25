import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getExecHealth, listExecReports, generateExecReport, execReportUrl, type ExecHealth, type ExecRisk, type ExecReportMeta } from '../api'
import Card, { CardHeader } from './ui/Card'
import Button from './ui/Button'
import PageState from './ui/PageState'
import Skeleton from './ui/Skeleton'

const stateStyle: Record<string, { bg: string; border: string; text: string; label: string; ring: string }> = {
  healthy: { bg: 'bg-green-500/10', border: 'border-green-500/30', text: 'text-green-300', label: 'Healthy', ring: 'stroke-green-400' },
  warning: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-300', label: 'Needs review', ring: 'stroke-amber-400' },
  critical: { bg: 'bg-red-500/10', border: 'border-red-500/30', text: 'text-red-300', label: 'Attention required', ring: 'stroke-red-400' },
}

function ScoreRing({ score }: { score: number }) {
  const r = 34
  const c = 2 * Math.PI * r
  const offset = c * (1 - score / 100)
  return (
    <svg viewBox="0 0 84 84" className="w-20 h-20">
      <circle cx="42" cy="42" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="7" />
      <circle
        cx="42" cy="42" r={r} fill="none"
        strokeWidth="7" strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={offset}
        className={stateStyle[score >= 80 ? 'healthy' : score >= 60 ? 'warning' : 'critical'].ring}
        transform="rotate(-90 42 42)"
      />
      <text x="42" y="47" textAnchor="middle" className="fill-white font-semibold text-[15px]">{score}</text>
    </svg>
  )
}

function KpiTile({ label, value, sub, href, tone }: { label: string; value: string | number; sub?: string; href: string; tone?: 'ok' | 'warn' | 'bad' }) {
  const color = tone === 'bad' ? 'text-red-300' : tone === 'warn' ? 'text-amber-300' : 'text-text-primary'
  return (
    <Link to={href} className="block bg-surface-3/50 backdrop-blur border border-border/40 rounded-xl p-3.5 hover:border-accent/40 hover:bg-surface-3/80 transition-all duration-150">
      <div className="text-[11px] uppercase tracking-wide text-muted mb-1">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      {sub && <div className="text-[11px] text-muted mt-0.5">{sub}</div>}
    </Link>
  )
}

function RiskTable({ title, rows, empty }: { title: string; rows: ExecRisk[]; empty: string }) {
  return (
    <Card>
      <CardHeader title={title} />
      {rows.length === 0 ? (
        <p className="text-xs text-muted">{empty}</p>
      ) : (
        <div className="overflow-auto max-h-72 rounded-xl border border-border/40">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface-2/80 backdrop-blur-xl">
              <tr className="text-left text-muted text-[11px] uppercase tracking-wider">
                <th className="px-3 py-2 font-medium">Device</th>
                <th className="px-3 py-2 font-medium">Site</th>
                <th className="px-3 py-2 font-medium text-right">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.ip}-${r.status}`} className="border-t border-border/30 hover:bg-surface-3/50 transition-colors">
                  <td className="px-3 py-1.5">
                    <Link to={`/inventory?focus=${encodeURIComponent(r.ip)}`} className="text-accent hover:underline">
                      <span className="font-mono text-xs">{r.ip}</span>
                    </Link>
                    {r.hostname && <span className="text-muted ml-2 text-xs">{r.hostname.split('.')[0]}</span>}
                  </td>
                  <td className="px-3 py-1.5 text-xs text-muted">{r.site || '\u2014'}</td>
                  <td className="px-3 py-1.5 text-right">
                    <span className={`text-[10px] uppercase px-1.5 py-0.5 rounded ${
                      r.status === 'down' ? 'bg-red-500/20 text-red-300' : r.status === 'flapping' ? 'bg-orange-500/20 text-orange-300' : r.status === 'spof' ? 'bg-amber-500/20 text-amber-300' : 'bg-amber-500/20 text-amber-300'
                    }`}>{r.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function freshnessTone(days: number | null): 'ok' | 'warn' | 'bad' {
  if (days === null) return 'bad'
  if (days <= 7) return 'ok'
  if (days <= 30) return 'warn'
  return 'bad'
}

export default function ExecutiveDashboard() {
  const [data, setData] = useState<ExecHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reports, setReports] = useState<ExecReportMeta[]>([])
  const [schedule, setSchedule] = useState('off')
  const [generating, setGenerating] = useState(false)

  const refresh = useCallback(async (initial = false) => {
    if (initial) setLoading(true)
    try {
      setData(await getExecHealth())
      const r = await listExecReports()
      setReports(r.reports || [])
      setSchedule(r.schedule || 'off')
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load executive health')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh(true) }, [refresh])

  const generate = async () => {
    setGenerating(true)
    try {
      await generateExecReport()
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate report')
    } finally {
      setGenerating(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-24 w-full" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">{[...Array(8)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
        <div className="grid lg:grid-cols-2 gap-4"><Skeleton className="h-64" /><Skeleton className="h-64" /></div>
      </div>
    )
  }
  if (error || !data) {
    return <PageState type="error" title="Executive dashboard unavailable" message={error || 'No data'} className="min-h-[50vh]" action={<Button variant="danger" size="sm" onClick={() => void refresh(true)}>Retry</Button>} />
  }

  const st = stateStyle[data.state]
  const k = data.kpis

  return (
    <div className="space-y-6">
      {/* Health banner + score */}
      <div className={`flex items-center justify-between gap-4 rounded-2xl border ${st.border} ${st.bg} backdrop-blur px-5 py-4`}>
        <div>
          <div className={`text-lg font-semibold ${st.text}`}>{st.label}</div>
          <p className="text-xs text-muted mt-0.5">
            {data.total_devices} devices · {k.devices_up} up · {k.devices_down} down · {k.devices_flapping} flapping · {k.spof_count} single points of failure
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-[11px] uppercase tracking-wide text-muted">Health score</div>
            <div className={`text-sm font-semibold ${st.text}`}>{st.label}</div>
          </div>
          <ScoreRing score={data.score} />
        </div>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        <KpiTile label="Devices" value={k.total_devices} href="/inventory" />
        <KpiTile label="Operational" value={`${k.up_pct}%`} sub={`${k.devices_up + k.devices_degraded} of ${k.total_devices}`} href="/topology" tone={k.up_pct >= 95 ? 'ok' : k.up_pct >= 85 ? 'warn' : 'bad'} />
        <KpiTile label="Down" value={k.devices_down} href="/inventory" tone={k.devices_down > 0 ? 'bad' : 'ok'} />
        <KpiTile label="Flapping" value={k.devices_flapping} href="/topology" tone={k.devices_flapping > 0 ? 'warn' : 'ok'} />
        <KpiTile label="SPOF" value={k.spof_count} sub="single points of failure" href="/topology" tone={k.spof_count > 0 ? 'warn' : 'ok'} />
        <KpiTile label="Config coverage" value={`${k.config_coverage}%`} href="/inventory" tone={k.config_coverage >= 90 ? 'ok' : k.config_coverage >= 70 ? 'warn' : 'bad'} />
        <KpiTile label="Site coverage" value={`${k.site_coverage}%`} sub="devices tagged to a site" href="/inventory" tone={k.site_coverage >= 90 ? 'ok' : k.site_coverage >= 70 ? 'warn' : 'bad'} />
        <KpiTile label="VLAN 90" value={k.vlan90_count} sub="switches flagged" href="/inventory" />
      </div>

      {/* Per-site freshness */}
      <Card>
        <CardHeader title="Site freshness" />
        <div className="overflow-auto rounded-xl border border-border/40 max-h-80">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface-2/80 backdrop-blur-xl">
              <tr className="text-left text-muted text-[11px] uppercase tracking-wider">
                <th className="px-3 py-2 font-medium">Site</th>
                <th className="px-3 py-2 font-medium text-right">Devices</th>
                <th className="px-3 py-2 font-medium text-right">Up</th>
                <th className="px-3 py-2 font-medium text-right">Down</th>
                <th className="px-3 py-2 font-medium text-right">Flap</th>
                <th className="px-3 py-2 font-medium text-right">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {data.sites.map((s) => {
                const tone = freshnessTone(s.freshness_days)
                return (
                  <tr key={s.site} className="border-t border-border/30 hover:bg-surface-3/50 transition-colors">
                    <td className="px-3 py-1.5">
                      <Link to={`/topology?site=${encodeURIComponent(s.site)}`} className="text-accent hover:underline">{s.site}</Link>
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-xs">{s.devices}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-xs text-green-300">{s.up}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-xs text-red-300">{s.down}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-xs text-orange-300">{s.flapping}</td>
                    <td className={`px-3 py-1.5 text-right tabular-nums text-xs ${tone === 'bad' ? 'text-red-300' : tone === 'warn' ? 'text-amber-300' : 'text-muted'}`}>
                      {s.freshness_days === null ? 'no data' : s.freshness_days === 0 ? 'today' : `${s.freshness_days}d ago`}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Risks */}
      <div className="grid lg:grid-cols-2 gap-4">
        <RiskTable title="Risks & issues" rows={data.risks} empty="No down, flapping, or degraded devices." />
        <RiskTable title="Single points of failure" rows={data.spof_devices.map((s) => ({ ...s, status: 'spof' }))} empty="No single points of failure detected." />
      </div>

      {/* Reports */}
      <Card>
        <CardHeader title="Executive reports" />
        <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
          <p className="text-xs text-muted">
            {schedule === 'off'
              ? 'Reporting is off. Set EXEC_REPORT_SCHEDULE=daily|weekly to auto-generate.'
              : `Auto-generates ${schedule} (${scheduleLabel(schedule)}).`}
          </p>
          <Button size="sm" onClick={generate} disabled={generating}>
            {generating ? 'Generating…' : 'Generate now'}
          </Button>
        </div>
        {reports.length === 0 ? (
          <p className="text-xs text-muted">No reports generated yet.</p>
        ) : (
          <div className="overflow-auto rounded-xl border border-border/40">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-2/80 backdrop-blur-xl">
                <tr className="text-left text-muted text-[11px] uppercase tracking-wider">
                  <th className="px-3 py-2 font-medium">Report</th>
                  <th className="px-3 py-2 font-medium">Generated</th>
                  <th className="px-3 py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.id} className="border-t border-border/30 hover:bg-surface-3/50 transition-colors">
                    <td className="px-3 py-1.5 text-xs text-text-primary">{r.title}</td>
                    <td className="px-3 py-1.5 text-xs text-muted">
                      {r.created_at ? new Date(r.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '\u2014'}
                      {r.emailed && <span className="ml-2 text-[10px] uppercase text-green-300">emailed</span>}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      <a href={execReportUrl(r.id, 'html')} target="_blank" rel="noreferrer" className="text-accent hover:underline text-xs mr-3">Open</a>
                      <a href={execReportUrl(r.id, 'pdf')} className="text-accent hover:underline text-xs">PDF</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

function scheduleLabel(schedule: string) {
  return schedule === 'weekly' ? 'every 7 days' : schedule === 'daily' ? 'every 24 hours' : 'every 60 minutes'
}