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
    <div className="min-h-screen flex items-center justify-center bg-surface-0">
      <form onSubmit={handleSubmit} className="bg-surface-1 p-8 rounded-2xl shadow-xl w-96 border border-border">
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-accent flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
          </div>
          <h1 className="text-xl font-bold text-text-primary">Network Mapper</h1>
        </div>
        {error && <div className="bg-red-900/40 border border-red-800 rounded-lg px-4 py-2.5 mb-4 text-sm text-red-300">{error}</div>}
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
    </div>
  )
}
