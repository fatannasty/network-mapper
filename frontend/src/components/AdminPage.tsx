import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getUsers, createUser, updateUser, deleteUser,
  getAdminActivity, getAdminStatus,
} from '../api'
import PageHeader from './ui/PageHeader'
import PageState from './ui/PageState'
import Card from './ui/Card'
import Badge from './ui/Badge'
import Button from './ui/Button'
import Input from './ui/Input'
import Select from './ui/Select'
import StatCard from './ui/StatCard'

interface User {
  id: number
  username: string
  role: string
  is_active: boolean
  created_at: string | null
}

interface Activity {
  type: string
  action: string
  timestamp: string | null
  status: string
  details: Record<string, unknown>
}

interface SystemStatus {
  database_size_bytes: number
  total_devices: number
  total_links: number
  total_interfaces: number
  total_scans: number
  stale_devices_90d: number
  latest_scan: Record<string, unknown> | null
  scan_success_rate: number
}

export default function AdminPage() {
  const navigate = useNavigate()
  const [users, setUsers] = useState<User[]>([])
  const [activity, setActivity] = useState<Activity[]>([])
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Create user form
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState('viewer')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')

  // Edit user
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editRole, setEditRole] = useState('')
  const [editActive, setEditActive] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [u, a, s] = await Promise.all([getUsers(), getAdminActivity(), getAdminStatus()])
      setUsers(u.users || [])
      setActivity(a.activity || [])
      setStatus(s)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load admin data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault()
    setCreating(true)
    setCreateError('')
    try {
      await createUser(newUsername, newPassword, newRole)
      setNewUsername('')
      setNewPassword('')
      setNewRole('viewer')
      await refresh()
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create user')
    } finally {
      setCreating(false)
    }
  }

  const handleToggleActive = async (user: User) => {
    await updateUser(user.id, { is_active: !user.is_active })
    await refresh()
  }

  const handleSaveRole = async () => {
    if (editingId == null) return
    await updateUser(editingId, { role: editRole, is_active: editActive })
    setEditingId(null)
    await refresh()
  }

  const handleDelete = async (user: User) => {
    if (!confirm(`Delete user "${user.username}"? This cannot be undone.`)) return
    await deleteUser(user.id)
    await refresh()
  }

  if (loading) return <PageState type="loading" title="Loading admin console..." className="h-full" />
  if (error) {
    return <PageState type="error" title="Admin console unavailable" message={error} className="h-full"
      action={<Button variant="danger" size="sm" onClick={refresh}>Retry</Button>} />
  }

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1048576).toFixed(1)} MB`
  }

  const formatTime = (ts: string | null) => {
    if (!ts) return '—'
    return ts.slice(0, 16).replace('T', ' ')
  }

  const roleBadge = (role: string) => {
    return <Badge label={role} size="sm" dot />
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <PageHeader
          title="Admin Console"
          description="User management, system status, and activity monitoring."
          actions={
            <div className="flex items-center gap-2">
              <Button variant="secondary" size="sm" onClick={refresh}>Refresh</Button>
            </div>
          }
        />

        {/* System Status */}
        {status && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard label="Total Devices" value={status.total_devices.toLocaleString()} accent="blue" />
            <StatCard label="Total Links" value={status.total_links.toLocaleString()} accent="green" />
            <StatCard label="Interfaces" value={status.total_interfaces.toLocaleString()} accent="default" />
            <StatCard label="Scan Jobs" value={status.total_scans.toLocaleString()} accent="default" />
            <StatCard label="Stale Devices" value={status.stale_devices_90d.toLocaleString()} accent={status.stale_devices_90d > 0 ? 'amber' : 'green'} sub="not seen in 90 days" />
            <StatCard label="DB Size" value={formatBytes(status.database_size_bytes)} accent="default" />
            <StatCard label="Health" value={`${Math.round(status.scan_success_rate)}%`} accent={status.scan_success_rate >= 95 ? 'green' : status.scan_success_rate >= 80 ? 'amber' : 'red'} sub="scan success rate" />
            {status.latest_scan && (
              <StatCard
                label="Latest Scan"
                value={String(status.latest_scan.subnet || '—')}
                sub={formatTime(status.latest_scan.finished_at as string | null)}
                accent="blue"
              />
            )}
          </div>
        )}

        {/* Create User */}
        <Card>
          <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Create User</h3>
          <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-xs text-muted mb-1">Username</label>
              <Input value={newUsername} onChange={(e) => setNewUsername(e.target.value)} required placeholder="newuser" className="w-48" />
            </div>
            <div>
              <label className="block text-xs text-muted mb-1">Password</label>
              <Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required placeholder="••••••" className="w-48" />
            </div>
            <div>
              <label className="block text-xs text-muted mb-1">Role</label>
              <Select value={newRole} onChange={(e) => setNewRole(e.target.value)} className="w-36">
                <option value="viewer">Viewer (read-only)</option>
                <option value="operator">Operator (scans + views)</option>
                <option value="admin">Admin (full access)</option>
              </Select>
            </div>
            <Button type="submit" disabled={creating}>{creating ? 'Creating...' : 'Create User'}</Button>
            {createError && <span className="text-xs text-red-400">{createError}</span>}
          </form>
          <p className="text-[11px] text-muted mt-2">
            Roles: <strong>Viewer</strong> = read-only inventory, <strong>Operator</strong> = run scans + view everything, <strong>Admin</strong> = full access including user management.
          </p>
        </Card>

        {/* User Accounts */}
          <Card padding={false}>
          <div className="px-5 py-4 border-b border-border/30">
            <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide">User Accounts</h3>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-2 z-10">
                <tr className="text-left text-muted text-[11px] uppercase tracking-wider">
                  <th className="px-5 py-2 font-medium">Username</th>
                  <th className="px-5 py-2 font-medium">Role</th>
                  <th className="px-5 py-2 font-medium">Status</th>
                  <th className="px-5 py-2 font-medium">Created</th>
                  <th className="px-5 py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id} className="border-t border-border/50 hover:bg-surface-3/50 transition-colors">
                    <td className="px-5 py-2 font-medium text-text-primary">{user.username}</td>
                    <td className="px-5 py-2">{roleBadge(user.role)}</td>
                    <td className="px-5 py-2">
                      <Badge label={user.is_active ? 'active' : 'down'} dot />
                    </td>
                    <td className="px-5 py-2 text-xs text-muted">{formatTime(user.created_at)}</td>
                    <td className="px-5 py-2">
                      {editingId === user.id ? (
                        <div className="flex items-center gap-2 justify-end">
                          <Select value={editRole} onChange={(e) => setEditRole(e.target.value)} className="w-28 text-xs">
                            <option value="viewer">Viewer</option>
                            <option value="operator">Operator</option>
                            <option value="admin">Admin</option>
                          </Select>
                          <Button variant="primary" size="sm" onClick={handleSaveRole}>Save</Button>
                          <Button variant="ghost" size="sm" onClick={() => setEditingId(null)}>Cancel</Button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 justify-end">
                          <Button variant="ghost" size="sm" onClick={() => { setEditingId(user.id); setEditRole(user.role); setEditActive(user.is_active) }}>
                            Edit
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => handleToggleActive(user)}>
                            {user.is_active ? 'Disable' : 'Enable'}
                          </Button>
                          <Button variant="danger" size="sm" onClick={() => handleDelete(user)}>
                            Delete
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr><td colSpan={5} className="px-5 py-8 text-center text-muted text-xs">No users found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Quick Links + Activity side by side */}
        <div className="grid lg:grid-cols-3 gap-4">
          {/* Quick Links */}
          <Card>
            <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Quick Links</h3>
            <div className="space-y-2">
              {[
                { label: 'Run Discovery', href: '/discover', icon: '🔍' },
                { label: 'Import Catalyst', href: '/catalyst', icon: '📡' },
                { label: 'Collect Configs', href: '/configs', icon: '⚙️' },
                { label: 'View Inventory', href: '/inventory', icon: '📋' },
                { label: 'View Topology', href: '/topology', icon: '🔗' },
                { label: 'Data Quality', href: '/quality', icon: '✅' },
              ].map((link) => (
                <button
                  key={link.href}
                  onClick={() => navigate(link.href)}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-lg bg-surface-2 hover:bg-surface-3 transition-colors text-left text-sm"
                >
                  <span className="text-base">{link.icon}</span>
                  <span className="text-text-primary">{link.label}</span>
                </button>
              ))}
            </div>
          </Card>

          {/* Activity Feed */}
          <Card className="lg:col-span-2">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wide">Activity Feed</h3>
              <span className="text-[11px] text-muted">{activity.length} events</span>
            </div>
            {activity.length === 0 ? (
              <p className="text-xs text-muted py-4 text-center">No activity recorded yet.</p>
            ) : (
              <div className="space-y-1 max-h-80 overflow-y-auto">
                {activity.slice(0, 15).map((event, i) => (
                  <div key={i} className="flex items-start gap-3 px-3 py-2 rounded-lg bg-surface-2 text-xs">
                    <span className={`w-2 h-2 mt-1 rounded-full shrink-0 ${event.status === 'completed' ? 'bg-green-400' : 'bg-red-400'}`} />
                    <div className="min-w-0 flex-1">
                      <p className="text-text-primary">{event.action}</p>
                      <p className="text-muted mt-0.5">{formatTime(event.timestamp)}</p>
                    </div>
                    {event.details && (
                      <span className="text-muted shrink-0">
                        {typeof event.details.device_count === 'number' ? `${event.details.device_count} devices` : ''}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
