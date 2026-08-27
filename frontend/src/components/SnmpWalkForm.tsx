import { useEffect, useState } from 'react'
import { AxiosError } from 'axios'
import { getDevices, backfillInterfaces, backfillLinks, cdpReport, type BackfillSummary, type CdpReport, type CdpRow } from '../api'
import Input from './ui/Input'
import Select from './ui/Select'
import Button from './ui/Button'
import Card, { CardHeader } from './ui/Card'

function errDetail(err: unknown): string {
  if (err instanceof AxiosError && err.response?.data) {
    const d = err.response.data as Record<string, unknown>
    if (typeof d.detail === 'string') return d.detail
    return JSON.stringify(d).slice(0, 2000)
  }
  return err instanceof Error ? err.message : String(err)
}

function JobResult({ summary }: { summary: BackfillSummary | null }) {
  if (!summary) return null
  const ok = summary.successful ?? 0
  const total = summary.total ?? 0
  const results = summary.interfaces_walked ?? summary.neighbors_discovered ?? 0
  return (
    <div className="mt-3 text-xs text-muted space-y-1">
      <p className={summary.failed ? 'text-amber-300' : 'text-green-300'}>
        OK {ok} / {total} devices · {results} results{summary.failed ? ` · ${summary.failed} failed` : ''}
      </p>
      {(summary.sample_errors?.length ?? 0) > 0 && (
        <div className="text-red-400">
          {summary.sample_errors!.slice(0, 5).map((e, i) => <p key={i}>{e}</p>)}
        </div>
      )}
    </div>
  )
}

export default function SnmpWalkForm() {
  const [sites, setSites] = useState<string[]>([])
  const [site, setSite] = useState('')
  const [v3Mode, setV3Mode] = useState(false)
  const [v3Username, setV3Username] = useState('')
  const [v3AuthProto, setV3AuthProto] = useState('sha')
  const [v3AuthPassword, setV3AuthPassword] = useState('')
  const [v3PrivProto, setV3PrivProto] = useState('aes')
  const [v3PrivPassword, setV3PrivPassword] = useState('')
  const [walkInterfaces, setWalkInterfaces] = useState(true)
  const [walkLinks, setWalkLinks] = useState(false)
  const [running, setRunning] = useState('')
  const [ifaceSummary, setIfaceSummary] = useState<BackfillSummary | null>(null)
  const [linkSummary, setLinkSummary] = useState<BackfillSummary | null>(null)
  const [cdpResult, setCdpResult] = useState<CdpReport | null>(null)
  const [runningCdp, setRunningCdp] = useState(false)
  const [cdpMethod, setCdpMethod] = useState<'snmp' | 'ssh'>('snmp')
  const [sshUsername, setSshUsername] = useState('')
  const [sshPassword, setSshPassword] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    getDevices({ limit: '5000' })
      .then((r) => {
        const set = new Set<string>()
        for (const d of r.devices || []) if (d.site) set.add(d.site)
        setSites([...set].sort())
      })
      .catch(() => {})
  }, [])

  const scope = {
    site: site || undefined,
    ...(v3Mode ? {
      snmpv3: {
        username: v3Username,
        auth_protocol: v3AuthProto,
        auth_password: v3AuthPassword,
        privacy_protocol: v3PrivProto,
        privacy_password: v3PrivPassword || v3AuthPassword,
      },
    } : {}),
  }

  const run = async () => {
    setError('')
    setIfaceSummary(null)
    setLinkSummary(null)
    const jobs: { key: string; fn: () => Promise<BackfillSummary> }[] = []
    if (walkInterfaces) jobs.push({ key: 'interfaces', fn: () => backfillInterfaces(scope) })
    if (walkLinks) jobs.push({ key: 'links', fn: () => backfillLinks(scope) })
    if (!jobs.length) return
    for (const job of jobs) {
      setRunning(job.key)
      try {
        const s = await job.fn()
        if (job.key === 'interfaces') setIfaceSummary(s)
        else setLinkSummary(s)
      } catch (e) {
        setError(`SNMP walk (${job.key}) failed: ${errDetail(e)}`)
      }
    }
    setRunning('')
  }

  const runCdp = async () => {
    setRunningCdp(true)
    setCdpResult(null)
    setError('')
    try {
      setCdpResult(await cdpReport({
        site: site || undefined,
        method: cdpMethod,
        ...(v3Mode ? { snmpv3: scope.snmpv3 } : {}),
        ...(cdpMethod === 'ssh' ? { ssh_username: sshUsername, ssh_password: sshPassword } : {}),
      }))
    } catch (e) {
      setError(`CDP report failed: ${errDetail(e)}`)
    } finally {
      setRunningCdp(false)
    }
  }

  const downloadCdpCsv = () => {
    if (!cdpResult) return
    const cols = ['switch_hostname', 'switch_ip', 'switch_site', 'neighbor_hostname', 'neighbor_ip', 'neighbor_port', 'local_port', 'neighbor_platform', 'neighbor_type']
    const esc = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)
    const text = [cols.join(','), ...cdpResult.rows.map((r) => cols.map((c) => esc(r[c as keyof CdpRow])).join(','))].join('\n')
    const blob = new Blob([text], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `cdp-neighbors${site ? `-${site.toLowerCase().replace(/[^a-z0-9]+/g, '-')}` : '-all'}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Card>
      <CardHeader title="SNMP Walk" />
      <p className="text-xs text-muted mb-4">
        Walk interfaces (+ VLANs) and/or LLDP/CDP links across the whole network or a single
        site via SNMPv3 or vaulted v2c communities. Results land in the inventory and topology,
        then can be exported from the Topology page.
      </p>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-2 mb-3">
        <Select value={site} onChange={(e) => setSite(e.target.value)}>
          <option value="">Whole network (all devices)</option>
          {sites.map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>

        <div className="flex items-center gap-1 bg-surface-2/70 backdrop-blur rounded-xl p-0.5">
          <button type="button" onClick={() => setV3Mode(false)} className={`flex-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-150 ${!v3Mode ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'}`}>v2c (vault)</button>
          <button type="button" onClick={() => setV3Mode(true)} className={`flex-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-all duration-150 ${v3Mode ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'}`}>v3</button>
        </div>
      </div>

      {v3Mode && (
        <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-2 mb-3">
          <Input value={v3Username} onChange={(e) => setV3Username(e.target.value)} placeholder="v3 username" />
          <Input type="password" value={v3AuthPassword} onChange={(e) => setV3AuthPassword(e.target.value)} placeholder="v3 auth password" />
          <Select value={v3AuthProto} onChange={(e) => setV3AuthProto(e.target.value)}>
            <option value="sha">Auth SHA</option>
            <option value="md5">Auth MD5</option>
            <option value="none">Auth none</option>
          </Select>
          <Select value={v3PrivProto} onChange={(e) => setV3PrivProto(e.target.value)}>
            <option value="aes">Priv AES</option>
            <option value="des">Priv DES</option>
            <option value="none">Priv none</option>
          </Select>
          <Input type="password" value={v3PrivPassword} onChange={(e) => setV3PrivPassword(e.target.value)} placeholder="v3 priv password (optional)" />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-4 mb-3">
        <label className="flex items-center gap-2 text-sm text-muted cursor-pointer">
          <input type="checkbox" checked={walkInterfaces} onChange={(e) => setWalkInterfaces(e.target.checked)} className="rounded" />
          Walk interfaces + VLANs
        </label>
        <label className="flex items-center gap-2 text-sm text-muted cursor-pointer">
          <input type="checkbox" checked={walkLinks} onChange={(e) => setWalkLinks(e.target.checked)} className="rounded" />
          Walk links (LLDP/CDP)
        </label>
        <Button onClick={run} disabled={running !== '' || (!walkInterfaces && !walkLinks)}>
          {running ? 'Walking…' : 'Run SNMP Walk'}
        </Button>
      </div>

      {error && <p className="text-sm text-red-400 mb-2">{error}</p>}
      {walkInterfaces && <JobResult summary={ifaceSummary} />}
      {walkLinks && <JobResult summary={linkSummary} />}

      <div className="border-t border-border/30 pt-4 mt-4">
        <h4 className="text-sm font-medium text-text-primary mb-1">CDP neighbor report</h4>
        <p className="text-xs text-muted mb-3">
          Switch-to-switch visibility via CDP (same data as &ldquo;show cdp neighbors detail&rdquo;).
          Access points and non-network neighbors are excluded. Uses the scope above
          (site = one network, blank = entire network).
        </p>
        <div className="flex items-center gap-2 flex-wrap mb-3">
          <div className="flex items-center gap-1 bg-surface-2/70 backdrop-blur rounded-xl p-0.5">
            <button type="button" onClick={() => setCdpMethod('snmp')} className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${cdpMethod === 'snmp' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'}`}>SNMP</button>
            <button type="button" onClick={() => setCdpMethod('ssh')} className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${cdpMethod === 'ssh' ? 'bg-blue-600 text-white' : 'text-muted hover:text-text-primary'}`}>SSH (CLI)</button>
          </div>
          {cdpMethod === 'ssh' && (
            <>
              <Input value={sshUsername} onChange={(e) => setSshUsername(e.target.value)} placeholder="SSH username (blank = vault)" className="w-44" />
              <Input type="password" value={sshPassword} onChange={(e) => setSshPassword(e.target.value)} placeholder="SSH password" className="w-44" />
            </>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button onClick={runCdp} disabled={runningCdp}>
            {runningCdp ? 'Collecting CDP…' : 'Generate CDP neighbor report'}
          </Button>
          {cdpResult && cdpResult.rows.length > 0 && (
            <Button variant="secondary" onClick={downloadCdpCsv}>Download CSV</Button>
          )}
        </div>
        {cdpResult && (
          <div className="mt-3 text-xs text-muted space-y-1">
            <p className="text-green-300">
              {cdpResult.switches_checked} switches checked · {cdpResult.row_count} switch-to-switch neighbors
              ({cdpResult.neighbors_found} found, {cdpResult.excluded} excluded — APs/other).
            </p>
            {(cdpResult.sample_errors?.length ?? 0) > 0 && (
              <div className="text-red-400">{cdpResult.sample_errors!.slice(0, 5).map((e, i) => <p key={i}>{e}</p>)}</div>
            )}
            {cdpResult.rows.length > 0 && (
              <div className="overflow-auto max-h-72 rounded-xl border border-border/40 mt-2">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-surface-2/80">
                    <tr className="text-left text-muted uppercase tracking-wider">
                      <th className="px-2 py-1.5">Switch</th>
                      <th className="px-2 py-1.5">Neighbor</th>
                      <th className="px-2 py-1.5">Neighbor IP</th>
                      <th className="px-2 py-1.5">Port</th>
                      <th className="px-2 py-1.5">Platform</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cdpResult.rows.slice(0, 100).map((r, i) => (
                      <tr key={i} className="border-t border-border/30">
                        <td className="px-2 py-1 font-mono">{r.switch_hostname || r.switch_ip}</td>
                        <td className="px-2 py-1 font-mono">{r.neighbor_hostname}</td>
                        <td className="px-2 py-1 font-mono text-muted">{r.neighbor_ip}</td>
                        <td className="px-2 py-1 font-mono text-muted">{r.local_port} → {r.neighbor_port}</td>
                        <td className="px-2 py-1 text-muted">{r.neighbor_platform}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}