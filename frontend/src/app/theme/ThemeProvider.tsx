import { useState, useEffect, useMemo, useCallback, type ReactNode } from 'react'
import { ThemeContext, type ThemeId } from './ThemeContext'
import { light } from './themes/light'
import { dark } from './themes/dark'
import { noc } from './themes/noc'

const STORAGE_KEY = 'app-theme'
const themes = [light, dark, noc] as const

function resolveInitial(): ThemeId {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'noc') return stored
  } catch { /* localStorage blocked */ }
  if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches) {
    return 'dark'
  }
  return 'light'
}

function applyTheme(id: ThemeId) {
  const root = document.documentElement
  root.classList.remove('light', 'dark', 'noc')
  root.classList.add(id)
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(resolveInitial)

  const setTheme = useCallback((id: ThemeId) => {
    setThemeState(id)
    applyTheme(id)
    try { localStorage.setItem(STORAGE_KEY, id) } catch { /* noop */ }
  }, [])

  useEffect(() => { applyTheme(theme) }, [theme])

  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!mq) return
    const listener = (e: MediaQueryListEvent) => {
      const stored = (() => {
        try { return localStorage.getItem(STORAGE_KEY) } catch { return null }
      })()
      if (!stored) setTheme(e.matches ? 'dark' : 'light')
    }
    mq.addEventListener('change', listener)
    return () => mq.removeEventListener('change', listener)
  }, [setTheme])

  const value = useMemo(() => ({ theme, themes, setTheme }), [theme, setTheme])

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  )
}
