import { useState, type FormEvent } from 'react'
import { login, setToken } from '../api'
import Input from './ui/Input'
import Button from './ui/Button'

interface Props { onSuccess: () => void }

export default function LoginForm({ onSuccess }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault(); setError('')
    try { const data = await login(username, password); setToken(data.token); onSuccess() }
    catch { setError('Invalid credentials') }
  }

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden">
      {/* Train background image */}
      <img
        src="/login-bg.jpg"
        alt=""
        aria-hidden="true"
        className="absolute inset-0 w-full h-full object-cover opacity-40 dark:opacity-25"
      />
      {/* Gradient overlays for readability */}
      <div className="absolute inset-0 bg-gradient-to-t from-surface-0 via-surface-0/80 to-surface-0/40" />
      <div className="absolute inset-0 bg-gradient-to-r from-surface-0/60 to-transparent" />

      <div className="relative z-10 w-full max-w-md px-4">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <img src="/amtrak-logo.png" alt="Amtrak" className="h-12 mb-4" />
          <p className="text-sm text-muted">Network Discovery & Topology Platform</p>
        </div>

        {/* Login card */}
        <form
          onSubmit={handleSubmit}
          className="bg-surface-1/80 backdrop-blur-xl p-8 rounded-2xl shadow-xl border border-border/40"
        >
          {error && (
            <div className="bg-red-950/50 border border-red-800/50 rounded-lg px-4 py-2.5 mb-4 text-sm text-red-300 backdrop-blur">
              {error}
            </div>
          )}
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-muted mb-1.5">Username</label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} className="w-full" autoFocus />
            </div>
            <div>
              <label className="block text-xs text-muted mb-1.5">Password</label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full" />
            </div>
            <Button type="submit" className="w-full">Sign In</Button>
          </div>
        </form>

        {/* Footer */}
        <p className="text-center text-[11px] text-muted/50 mt-6">
          Amtrak IT Infrastructure &middot; Network Operations
        </p>
      </div>
    </div>
  )
}
