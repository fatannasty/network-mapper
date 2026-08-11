import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  applySiteMappings, backfillInterfaces, backfillLinks, classifyBlanks,
  createCredential, createSiteMapping, deleteCredential, deleteSiteMapping,
  getCredentials, getReport, getSiteMappings, seedSiteMappings,
  type BackfillSummary, type Credential, type SiteMapping,
} from '../api'
import PageHeader from './ui/PageHeader'
import Card, { CardHeader } from './ui/Card'
import Badge from './ui/Badge'
import GaugeBar from './ui/GaugeBar'
import Button from './ui/Button'
import Input from './ui/Input'

function fmtError(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

function ResultTable({ summary }: { summary: BackfillSummary }) {
  if (!summary) return null
  return (
    <div className="overflow-auto max-h-64 mt-2 rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface-2">
          <tr className="text-left text-muted text-[11px] uppercase tracking-wider">
            <th className="px-3 py-2 font-medium">Host</th>
            <th className="px-3 py-2 font-medium">Type</th>
            <th className="px-3 py-2 font-medium text-right">Count</th>
            <th className="px-3 py-2 font-medium">Error</th>
          </tr>
        </thead>
        <tbody>
          {summary.results.slice(0, 200).map((r, i) => (
            <tr key={i} className="border-t border-border hover:bg-surface-3/50 transition-colors">
              <td className="px-3 py-1.5">
                <span className="font-mono text-xs">{r.ip}</span>
                {r.hostname && <span className="text-muted ml-2 text-xs">{r.hostname}</span>}
              </td>
              <td className="px-3 py-1.5"><Badge label={r.device_type || 'unknown'} /></td>
              <td className="px-3 py-1.5 text-right tabular-nums text-xs">{r.interface_count ?? r.neighbor_count ?? r.interfaces ?? 0}</td>
              <td className="px-3 py-1.5 text-xs text-red-400">{r.error}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function DataQuality() {
  const [gates, setGates] = useState<Record<string, { target: number; actual: number; met: boolean }> | null>(null)
  const [mappings, setMappings] = useState<SiteMapping[]>([])
  const [mappingPrefix, setMappingPrefix] = useState('')
  const [mappingSite, setMappingSite] = useState('')
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [credName, setCredName] = useState('')
  const [credType, setCredType] = useState('snmp')
  const [credUsername, setCredUsername] = useState('')
  const [credPassword, setCredPassword] = useState('')
  const [credCommunity, setCredCommunity] = useState('')
  const [credSite, setCredSite] = useState('')
  const [interfaceSummary, setInterfaceSummary] = useState<BackfillSummary | null>(null)
  const [linkSummary, setLinkSummary] = useState<BackfillSummary | null>(null)
  const [running, setRunning] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const refresh = useCallback(async () => {
    setError('')
    try {
      const [g, m, c] = await Promise.all([getReport(), getSiteMappings(), getCredentials()])
      setGates(g.dod_gates || null)
      setMappings(m.mappings || [])
      setCredentials(c.credentials || [])
    } catch (err) { setError(fmtError(err)) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const run = async (name: string, fn: () => Promise<unknown>) => {
    setRunning(name); setError(''); setNotice('')
    try { await fn(); await refresh() }
    catch (err) { setError(fmtError(err)) }
    finally { setRunning('') }
  }

  const handleAddMapping = async (e: FormEvent) => {
    e.preventDefault()
    if (!mappingPrefix || !mappingSite) return
    await run('mapping', async () => {
      await createSiteMapping(mappingPrefix.trim(), mappingSite.trim())
      setMappingPrefix(''); setMappingSite('')
    })
  }

  const handleAddCredential = async (e: FormEvent) => {
    e.preventDefault()
    if (!credName) return
    await run('credential', async () => {
      await createCredential({ name: credName.trim(), credential_type: credType, username: credUsername, password: credPassword, snmp_community: credCommunity, site: credSite })
      setCredName(''); setCredPassword(''); setCredCommunity('')
    })
  }

  return (
    <div className="h-full overflow-auto p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <PageHeader
          title="Data Quality"
          description="Site attribution, interfaces, link validation, and config coverage."
        />

        {error && <div className="bg-red-900/40 border border-red-800 rounded-lg p-4 text-sm text-red-300">{error}</div>}
        {notice && <div className="bg-green-900/40 border border-green-800 rounded-lg p-4 text-sm text-green-300">{notice}</div>}

        {/* DoD Gates */}
        <Card>
          <CardHeader title="Definition of Done" />
          {gates ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              {Object.entries(gates).map(([key, gate]) => (
                <div key={key} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted capitalize">{key}</span>
                    <Badge label={gate.met ? 'met' : 'gap'} />
                  </div>
                  <div className="text-3xl font-bold text-text-primary tabular-nums">{gate.actual}%</div>
                  <GaugeBar label={`≥ ${gate.target}%`} actual={gate.actual} target={gate.target} />
                </div>
              ))}
            </div>
          ) : <p className="text-xs text-muted">No gate data yet.</p>}
        </Card>

        {/* Site Mappings */}
        <Card>
          <CardHeader title="Site Mappings" />
          <p className="text-xs text-muted mb-4">
            Hostname-prefix → site rules. Blank-site devices are backfilled from these after Catalyst imports.
          </p>
          <form onSubmit={handleAddMapping} className="flex gap-2 mb-4">
            <Input value={mappingPrefix} onChange={(e) => setMappingPrefix(e.target.value)} placeholder="Prefix, e.g. AMTRCHIIL" className="flex-1" />
            <Input value={mappingSite} onChange={(e) => setMappingSite(e.target.value)} placeholder="Site name" className="flex-1" />
            <Button type="submit" disabled={running !== ''} size="sm">Add</Button>
          </form>
          <div className="flex gap-2 mb-3">
            <Button variant="secondary" size="sm" onClick={() => run('seed', async () => { const r = await seedSiteMappings(); setNotice(`Seeded ${r.created} new of ${r.discovered} discovered`) })} disabled={running !== ''}>Seed from devices</Button>
            <Button variant="secondary" size="sm" onClick={() => run('apply', async () => { const r = await applySiteMappings(); setNotice(`Updated ${r.updated}, matched ${r.matched}`) })} disabled={running !== ''}>Apply to blanks</Button>
          </div>
          {mappings.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {mappings.map((m) => (
                <span key={m.id} className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-surface-3 border border-border rounded-lg text-xs">
                  <span className="font-mono font-medium">{m.prefix}</span>
                  <span className="text-muted">→</span>
                  <span>{m.site}</span>
                  <button onClick={() => run('del', async () => { await deleteSiteMapping(m.id); setMappings(mappings.filter((x) => x.id !== m.id)) })} className="text-muted hover:text-red-400 ml-0.5">×</button>
                </span>
              ))}
            </div>
          )}
        </Card>

        {/* Credential Vault */}
        <Card>
          <CardHeader title="Credential Vault" />
          <p className="text-xs text-muted mb-4">
            Encrypted at rest (Fernet). Used as default communities for interface walks and link validation.
          </p>
          <form onSubmit={handleAddCredential} className="grid md:grid-cols-3 gap-2 mb-4">
            <Input value={credName} onChange={(e) => setCredName(e.target.value)} placeholder="Name" />
            <select value={credType} onChange={(e) => setCredType(e.target.value)} className="px-3 py-2 bg-surface-3 border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent">
              <option value="snmp">SNMP</option>
              <option value="ssh">SSH</option>
            </select>
            <Input value={credSite} onChange={(e) => setCredSite(e.target.value)} placeholder="Site (optional)" />
            {credType === 'ssh' && <Input value={credUsername} onChange={(e) => setCredUsername(e.target.value)} placeholder="SSH username" />}
            <Input type="password" value={credPassword} onChange={(e) => setCredPassword(e.target.value)} placeholder={credType === 'snmp' ? 'Password (optional)' : 'SSH password'} />
            <Input value={credCommunity} onChange={(e) => setCredCommunity(e.target.value)} placeholder="SNMP community" />
            <Button type="submit" disabled={running !== ''} size="sm">Add credential</Button>
          </form>
          {credentials.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {credentials.map((c) => (
                <span key={c.id} className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-surface-3 border border-border rounded-lg text-xs">
                  <span className="font-medium">{c.name}</span>
                  <Badge label={c.credential_type} />
                  {c.site && <span className="text-muted">{c.site}</span>}
                  <button onClick={() => run('cdel', async () => { await deleteCredential(c.id); setCredentials(credentials.filter((x) => x.id !== c.id)) })} className="text-muted hover:text-red-400 ml-0.5">×</button>
                </span>
              ))}
            </div>
          )}
        </Card>

        {/* Backfill Jobs */}
        <Card>
          <CardHeader title="Backfill Jobs" />
          <div className="grid md:grid-cols-3 gap-4">
            {[
              { title: 'Interface walks', desc: 'SNMP IF-MIB on switch/router/core-switch.', runKey: 'interfaces', action: async () => setInterfaceSummary(await backfillInterfaces()), summary: interfaceSummary, count: interfaceSummary?.persisted_interfaces },
              { title: 'Link validation', desc: 'SNMP LLDP/CDP on core-switch and router.', runKey: 'links', action: async () => setLinkSummary(await backfillLinks()), summary: linkSummary, count: linkSummary?.neighbors_discovered },
              { title: 'Classify blanks', desc: 'AP hostnames → accesspoint; port 9100 → printer.', runKey: 'blanks', action: async () => { const r = await classifyBlanks(); setNotice(`Classified ${r.changed} devices`) }, count: undefined },
            ].map((job) => (
              <div key={job.runKey} className="bg-surface-3 rounded-lg p-4 border border-border">
                <h4 className="text-sm font-medium text-text-primary mb-1">{job.title}</h4>
                <p className="text-xs text-muted mb-3">{job.desc}</p>
                <Button size="sm" className="w-full" onClick={() => run(job.runKey, job.action)} disabled={running !== ''}>
                  {running === job.runKey ? 'Running...' : job.title}
                </Button>
                {job.summary && (
                  <div className="mt-3 text-xs text-muted space-y-1">
                    <p>OK {job.summary.successful} / {job.summary.total}{job.count != null ? ` · ${job.count} results` : ''}</p>
                    <ResultTable summary={job.summary} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
