import { use } from 'react'
import { ThemeContext } from './ThemeContext'

interface Props {
  /** 'menu' = full-width row (sidebar footer), 'icon' = compact header button */
  variant?: 'menu' | 'icon'
}

export function ThemeSwitcher({ variant = 'menu' }: Props) {
  const ctx = use(ThemeContext)
  if (!ctx) return null

  const { theme, themes, setTheme } = ctx
  const current = themes.find((t) => t.id === theme) ?? themes[0]
  const next = themes[(themes.indexOf(current) + 1) % themes.length]

  if (variant === 'icon') {
    return (
      <button
        onClick={() => setTheme(next.id)}
        className="flex items-center justify-center w-9 h-9 rounded-lg text-muted hover:text-text-primary hover:bg-surface-2 transition-colors"
        title={`Theme: ${current.label} — click for ${next.label}`}
        aria-label={`Switch theme from ${current.label} to ${next.label}`}
      >
        <svg className="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d={current.icon} />
        </svg>
      </button>
    )
  }

  return (
    <button
      onClick={() => setTheme(next.id)}
      className="flex items-center gap-2 w-full px-3 py-1.5 rounded-lg text-sm text-muted hover:text-text-secondary hover:bg-surface-2 transition-colors"
      title={`Theme: ${current.label}  —  click for ${next.label}`}
    >
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d={current.icon} />
      </svg>
      <span>{current.label}</span>
    </button>
  )
}
