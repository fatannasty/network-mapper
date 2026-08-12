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
      {/* Cinematic background */}
      <div className="absolute inset-0 bg-surface-0" />
      {/* Amtrak brand accent orbs */}
      <div className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] rounded-full blur-[120px]" style={{ background: 'rgba(0, 58, 112, 0.15)' }} />
      <div className="absolute bottom-[-15%] right-[-5%] w-[500px] h-[500px] rounded-full blur-[100px]" style={{ background: 'rgba(200, 16, 46, 0.1)' }} />
      <div className="absolute top-[30%] right-[20%] w-[300px] h-[300px] rounded-full blur-[80px]" style={{ background: 'rgba(0, 58, 112, 0.08)' }} />
      {/* Subtle grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: 'linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)',
          backgroundSize: '60px 60px',
        }}
      />

      <div className="relative z-10 w-full max-w-md px-4">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <img src="/amtrak-logo.svg" alt="Amtrak" className="h-12 mb-4" />
          <p className="text-sm text-muted">Network Discovery & Topology Platform</p>
        </div>

        {/* Login card */}
        <form
          onSubmit={handleSubmit}
          className="bg-surface-1/60 backdrop-blur-2xl p-8 rounded-2xl shadow-xl border border-border/40"
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
