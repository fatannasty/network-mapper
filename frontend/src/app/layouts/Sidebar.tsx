import Navigation from './Navigation'

interface Props {
  onLogout: () => void
  collapsed?: boolean
  onOpenHelp?: () => void
}

export default function Sidebar({ onLogout, collapsed, onOpenHelp }: Props) {
  return (
    <aside className={`flex flex-col bg-surface-1/60 backdrop-blur-2xl border-r border-border/30 shrink-0 transition-all duration-300 ease-out
      ${collapsed ? 'w-14' : 'w-56'}`} aria-label="Sidebar">
      {/* Logo */}
      <div className="px-3 py-3 border-b border-border/30">
        <div className="flex items-center gap-2.5">
          {collapsed ? (
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#003A70] to-[#C8102E] flex items-center justify-center shrink-0 shadow-md shadow-accent/20">
              <span className="text-white text-base font-bold">A</span>
            </div>
          ) : (
            <img src="/amtrak-logo.png" alt="Amtrak" className="h-11 w-auto" />
          )}
        </div>
      </div>

      <Navigation collapsed={collapsed}>
        <button
          onClick={onOpenHelp}
          className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 mb-0.5 w-full text-muted hover:text-text-primary hover:bg-surface-2/50 ${collapsed ? 'justify-center' : ''}`}
          title={collapsed ? 'Help' : undefined}
        >
          <svg className="w-[18px] h-[18px] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" />
          </svg>
          {!collapsed && 'Help'}
        </button>
      </Navigation>

      {/* Footer */}
      <div className="p-3 border-t border-border/30">
        <button
          onClick={onLogout}
          className={`flex items-center gap-2.5 w-full px-3 py-2 rounded-xl text-sm text-muted hover:text-text-secondary hover:bg-surface-2/60 transition-all duration-150 ${collapsed ? 'justify-center' : ''}`}
        >
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          {!collapsed && 'Sign out'}
        </button>
        {!collapsed && (
          <div className="px-3 mt-3 pt-3 border-t border-border/30 text-[10px] text-muted/50 font-mono">
            Network Mapper v0.2.0
          </div>
        )}
      </div>
    </aside>
  )
}
