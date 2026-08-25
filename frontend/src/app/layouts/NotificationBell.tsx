import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { listNotifications, markNotificationSeen, runAlertCheck, type NotificationItem } from '../../api'

const severityColor: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-300',
  warning: 'bg-amber-500/20 text-amber-300',
  info: 'bg-blue-500/20 text-blue-300',
}

const kindLabel: Record<string, string> = {
  flapping: 'Flapping',
  down: 'Down',
  spof: 'SPOF',
  config_change: 'Config change',
  report: 'Report',
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [unseen, setUnseen] = useState(0)
  const [running, setRunning] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => {
    try {
      const r = await listNotifications(50)
      setNotifications(r.notifications || [])
      setUnseen(r.unseen || 0)
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!document.hidden) void refresh()
    }, 60_000)
    return () => window.clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const markSeen = async (n: NotificationItem) => {
    if (n.seen) return
    await markNotificationSeen(n.id)
    setNotifications((prev) => prev.map((x) => (x.id === n.id ? { ...x, seen: true } : x)))
    setUnseen((u) => Math.max(0, u - 1))
  }

  const check = async () => {
    setRunning(true)
    try {
      await runAlertCheck()
      await refresh()
    } catch {
      /* ignore */
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => { setOpen((o) => !o); if (!open) void refresh() }}
        className="relative flex items-center justify-center w-9 h-9 rounded-xl text-muted hover:text-text-primary hover:bg-surface-2/60 transition-all duration-150"
        aria-label={`Notifications${unseen ? ` (${unseen} unread)` : ''}`}
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
        </svg>
        {unseen > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
            {unseen > 99 ? '99+' : unseen}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 w-96 max-h-[70vh] flex flex-col rounded-2xl border border-border/40 bg-surface-1 shadow-2xl backdrop-blur-2xl overflow-hidden z-30">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/30">
            <span className="text-sm font-semibold text-text-primary">Notifications</span>
            <button
              onClick={check}
              disabled={running}
              className="text-xs text-accent hover:underline disabled:opacity-50"
            >
              {running ? 'Checking…' : 'Run check'}
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="text-xs text-muted text-center py-8">No notifications yet.</p>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  className={`px-4 py-2.5 border-b border-border/20 hover:bg-surface-2/50 transition-colors cursor-pointer ${n.seen ? 'opacity-60' : ''}`}
                  onClick={() => void markSeen(n)}
                >
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] uppercase px-1.5 py-0.5 rounded ${severityColor[n.severity] || severityColor.info}`}>
                      {kindLabel[n.kind] || n.kind}
                    </span>
                    <span className="text-xs font-medium text-text-primary truncate">{n.title}</span>
                  </div>
                  <p className="text-[11px] text-muted mt-0.5 line-clamp-2">{n.message}</p>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-[10px] text-muted/70">
                      {n.created_at ? new Date(n.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : ''}
                      {n.emailed ? ' · emailed' : ''}
                    </span>
                    {n.device_ip && (
                      <Link
                        to={`/inventory?focus=${encodeURIComponent(n.device_ip)}`}
                        className="text-[10px] text-accent hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {n.device_ip}
                      </Link>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}