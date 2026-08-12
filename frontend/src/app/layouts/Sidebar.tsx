import Navigation from './Navigation'

interface Props {
  onLogout: () => void
  collapsed?: boolean
}

export default function Sidebar({ onLogout, collapsed }: Props) {
  return (
    <aside className={`flex flex-col bg-surface-1/50 backdrop-blur-2xl border-r border-border/40 shrink-0 transition-all duration-300 ease-out
      ${collapsed ? 'w-14' : 'w-56'}`} aria-label="Sidebar">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-border/40">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-accent to-blue-400 flex items-center justify-center shrink-0 shadow-sm shadow-accent/30">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
          </div>
          {!collapsed && (
            <span className="text-sm font-bold tracking-tight text-text-primary">
              Network<span className="text-accent">Mapper</span>
            </span>
          )}
        </div>
      </div>

      <Navigation collapsed={collapsed} />

      {/* Footer */}
      <div className="p-3 border-t border-border/40">
        <button
          onClick={onLogout}
          className={`flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm text-muted hover:text-text-secondary hover:bg-surface-2/60 transition-all duration-150 ${collapsed ? 'justify-center' : ''}`}
        >
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          {!collapsed && 'Sign out'}
        </button>
        {!collapsed && (
          <div className="px-3 mt-3 pt-3 border-t border-border/40 text-[10px] text-muted/50 font-mono">
            Network Mapper v0.1.0
          </div>
        )}
      </div>
    </aside>
  )
}
