import { useEffect, useRef, useState } from 'react'
import { ThemeSwitcher } from '../theme/ThemeSwitcher'

interface Props {
  onLogout: () => void
}

export default function UserMenu({ onLogout }: Props) {
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

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2.5 pl-1.5 pr-2.5 py-1.5 rounded-xl text-muted hover:text-text-primary hover:bg-surface-2/60 transition-all duration-150"
        aria-label="Account menu"
        aria-expanded={open}
      >
        <span className="flex items-center justify-center w-7 h-7 rounded-full bg-accent/15 text-accent text-xs font-semibold">
          O
        </span>
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-56 bg-surface-1/90 backdrop-blur-2xl border border-border/40 rounded-2xl shadow-popover p-1.5 z-50">
          <div className="px-3 py-2.5 border-b border-border/30 mb-1.5">
            <div className="text-sm font-medium text-text-primary">Operator</div>
            <div className="text-xs text-muted mt-0.5">Network operator</div>
          </div>
          <ThemeSwitcher variant="menu" />
          <button
            onClick={onLogout}
            className="flex items-center gap-2 w-full px-3 py-2 rounded-xl text-sm text-muted hover:text-text-secondary hover:bg-surface-2/60 transition-all duration-150"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
