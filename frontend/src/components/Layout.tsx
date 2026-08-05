import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'

interface Props {
  children: ReactNode
  onLogout: () => void
}

const links = [
  { to: '/topology', label: 'Topology' },
  { to: '/discover', label: 'Discover' },
  { to: '/catalyst', label: 'Catalyst' },
]

export default function Layout({ children, onLogout }: Props) {
  const { pathname } = useLocation()

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white">
      <nav className="flex items-center gap-1 px-4 py-2 border-b border-gray-800 bg-gray-900 shrink-0">
        <span className="text-lg font-bold text-blue-400 mr-4">Network Mapper</span>
        {links.map((l) => (
          <Link
            key={l.to}
            to={l.to}
            className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
              pathname === l.to || (l.to === '/topology' && pathname === '/')
                ? 'bg-gray-800 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
            }`}
          >
            {l.label}
          </Link>
        ))}
        <div className="flex-1" />
        <button
          onClick={onLogout}
          className="px-4 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors"
        >
          Logout
        </button>
      </nav>
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  )
}
