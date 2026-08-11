import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { navItems } from './navItems'

interface Props {
  collapsed?: boolean
  children?: ReactNode
}

export default function Navigation({ collapsed, children }: Props) {
  const { pathname } = useLocation()

  const isActive = (to: string) =>
    pathname === to || (to === '/topology' && pathname === '/')

  return (
    <nav className="flex-1 overflow-y-auto py-3 px-3" aria-label="Main navigation">
      {!collapsed && (
        <div className="text-[11px] font-semibold text-muted uppercase tracking-widest mb-2 px-2">
          Navigation
        </div>
      )}
      {navItems.map((item) => {
        const active = isActive(item.to)
        return (
          <Link
            key={item.to}
            to={item.to}
            title={collapsed ? item.label : undefined}
            className={`relative flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all mb-0.5 ${
              active
                ? 'bg-accent-subtle text-text-primary'
                : 'text-muted hover:text-text-secondary hover:bg-surface-2'
            } ${collapsed ? 'justify-center' : ''}`}
          >
            {active && !collapsed && (
              <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-r-full bg-accent" />
            )}
            <svg
              className={`w-4 h-4 shrink-0 ${active ? 'text-accent' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={item.icon} />
            </svg>
            {!collapsed && item.label}
          </Link>
        )
      })}
      {children}
    </nav>
  )
}
