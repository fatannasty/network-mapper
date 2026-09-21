import { useEffect, useMemo, useRef, useState } from 'react'

interface Props {
  value: string
  onChange: (site: string) => void
  sites: string[]
}

export default function SiteSelect({ value, onChange, sites }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return sites
    return sites.filter((s) => s.toLowerCase().includes(q))
  }, [sites, query])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const pick = (site: string) => {
    onChange(site)
    setOpen(false)
    setQuery('')
  }

  return (
    <div className="relative" ref={ref}>
      <input
        value={open ? query : value || 'All sites'}
        onFocus={() => { setOpen(true); setQuery('') }}
        onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
        onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false) }}
        placeholder="All sites"
        aria-label="Filter by site"
        className="w-52 px-3 py-1.5 bg-surface-2/50 backdrop-blur border border-border/40 rounded-xl text-xs text-text-primary placeholder:text-muted/60 focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all duration-150"
      />
      {open && (
        <div className="absolute left-0 right-0 top-9 max-h-64 overflow-y-auto rounded-xl border border-border/40 bg-surface-1 shadow-2xl backdrop-blur-2xl z-30">
          <button
            onClick={() => pick('')}
            className={`w-full text-left px-3 py-1.5 text-xs hover:bg-surface-2/60 ${!value ? 'font-semibold text-accent' : 'text-text-primary'}`}
          >
            All sites
          </button>
          {filtered.slice(0, 300).map((s) => (
            <button
              key={s}
              onClick={() => pick(s)}
              className={`w-full text-left px-3 py-1.5 text-xs truncate hover:bg-surface-2/60 ${value === s ? 'font-semibold text-accent' : 'text-text-primary'}`}
            >
              {s}
            </button>
          ))}
          {filtered.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted">No sites match &ldquo;{query}&rdquo;.</p>
          )}
        </div>
      )}
    </div>
  )
}