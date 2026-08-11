import { useLocation } from 'react-router-dom'
import { ThemeSwitcher } from '../theme/ThemeSwitcher'
import UserMenu from './UserMenu'
import { pageTitleForPath } from './navItems'

interface Props {
  onLogout: () => void
  collapsed: boolean
  onToggleCollapse: () => void
}

export default function Header({ onLogout, collapsed, onToggleCollapse }: Props) {
  const { pathname } = useLocation()
  const title = pageTitleForPath(pathname)

  return (
    <header className="flex items-center gap-3 h-14 px-3 border-b border-border bg-surface-1/80 backdrop-blur-md shrink-0 z-20">
      <button
        onClick={onToggleCollapse}
        className="flex items-center justify-center w-9 h-9 rounded-lg text-muted hover:text-text-primary hover:bg-surface-2 transition-colors"
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        <svg className="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          {collapsed ? (
            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
          ) : (
            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25H12" />
          )}
        </svg>
      </button>

      <nav className="flex items-center gap-2 text-sm min-w-0" aria-label="Breadcrumb">
        <span className="text-muted">Network Mapper</span>
        <svg className="w-3.5 h-3.5 text-muted/50 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        <span className="font-medium text-text-primary truncate">{title}</span>
      </nav>

      <div className="flex-1" />

      <ThemeSwitcher variant="icon" />
      <UserMenu onLogout={onLogout} />
    </header>
  )
}
