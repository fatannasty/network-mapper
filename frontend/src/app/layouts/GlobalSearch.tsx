import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { globalSearch, type SearchResult } from '../../api'

const EMPTY: SearchResult = { devices: [], sites: [], links: [] }

export default function GlobalSearch() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<SearchResult>(EMPTY)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!q.trim()) { setResults(EMPTY); return }
    const t = window.setTimeout(() => {
      globalSearch(q.trim()).then((r) => { setResults(r); setOpen(true) }).catch(() => {})
    }, 250)
    return () => window.clearTimeout(t)
  }, [q])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const goDevice = (ip: string) => { setOpen(false); setQ(''); navigate(`/inventory?focus=${encodeURIComponent(ip)}`) }
  const goSite = (site: string) => { setOpen(false); setQ(''); navigate(`/topology?site=${encodeURIComponent(site)}`) }
  const goTopology = () => { setOpen(false); setQ(''); navigate('/topology') }

  return (
    <div className="relative hidden sm:block" ref={ref}>
      <svg className="w-4 h-4 text-muted absolute left-3 top-1/2 -translate-y-1/2" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35m1.1-4.65a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0z" />
      </svg>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => { if (results.devices.length || results.sites.length || results.links.length) setOpen(true) }}
        onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false) }}
        placeholder="Search devices, sites, ports..."
        aria-label="Global search"
        className="w-56 pl-9 pr-3 py-1.5 bg-surface-2/50 backdrop-blur border border-border/40 rounded-xl text-sm text-text-primary placeholder:text-muted/60 focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all duration-150"
      />
      {open && (q.trim()) && (
        <div className="absolute right-0 top-11 w-96 max-h-[70vh] flex flex-col rounded-2xl border border-border/40 bg-surface-1 shadow-2xl backdrop-blur-2xl overflow-hidden z-30">
          <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
            {results.devices.length === 0 && results.sites.length === 0 && results.links.length === 0 && (
              <p className="text-xs text-muted text-center py-6">No matches for &ldquo;{q}&rdquo;.</p>
            )}
            {results.devices.length > 0 && (
              <div>
                <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted">Devices</div>
                {results.devices.map((d) => (
                  <button key={d.ip} onClick={() => goDevice(d.ip)} className="w-full flex items-center gap-2 px-2 py-1.5 rounded-xl hover:bg-surface-2/60 text-left">
                    <span className="font-mono text-xs text-accent">{d.ip}</span>
                    <span className="text-xs text-text-primary truncate">{d.hostname || '\u2014'}</span>
                    <span className="text-[10px] text-muted capitalize ml-auto">{d.device_type}</span>
                  </button>
                ))}
              </div>
            )}
            {results.sites.length > 0 && (
              <div>
                <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted">Sites</div>
                {results.sites.map((s) => (
                  <button key={s} onClick={() => goSite(s)} className="w-full flex items-center gap-2 px-2 py-1.5 rounded-xl hover:bg-surface-2/60 text-left">
                    <span className="text-xs text-text-primary">{s}</span>
                    <span className="text-[10px] text-muted ml-auto">view site topology</span>
                  </button>
                ))}
              </div>
            )}
            {results.links.length > 0 && (
              <div>
                <div className="px-2 py-1 text-[10px] uppercase tracking-wide text-muted">Links / ports</div>
                {results.links.map((l, i) => (
                  <button key={i} onClick={goTopology} className="w-full flex items-center gap-2 px-2 py-1.5 rounded-xl hover:bg-surface-2/60 text-left">
                    <span className="font-mono text-[11px] text-text-primary truncate">{l.interface_a || l.interface_b}</span>
                    <span className="text-[10px] text-muted ml-auto">{l.source} \u2192 {l.target}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}