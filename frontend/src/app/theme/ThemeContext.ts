import { createContext } from 'react'

export type ThemeId = 'light' | 'dark' | 'noc'

export interface ThemeDefinition {
  id: ThemeId
  label: string
  /** SVG path for a 24x24 heroicon-style icon */
  icon: string
}

export interface ThemeContextValue {
  theme: ThemeId
  themes: readonly ThemeDefinition[]
  setTheme: (id: ThemeId) => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)
