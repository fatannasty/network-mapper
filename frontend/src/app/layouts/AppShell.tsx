import { useState, type ReactNode } from 'react'
import Header from './Header'
import Sidebar from './Sidebar'

interface Props {
  children: ReactNode
  onLogout: () => void
}

export default function AppShell({ children, onLogout }: Props) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="h-screen flex flex-col text-fg">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3
          focus:z-50 focus:px-4 focus:py-2 focus:bg-accent focus:text-white
          focus:rounded-lg focus:outline-none"
      >
        Skip to content
      </a>
      <Header
        onLogout={onLogout}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((c) => !c)}
      />
      <div className="flex flex-1 min-h-0">
        <Sidebar onLogout={onLogout} collapsed={collapsed} />
        <main id="main-content" className="flex-1 overflow-hidden" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  )
}
