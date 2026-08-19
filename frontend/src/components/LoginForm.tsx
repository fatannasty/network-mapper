import { useId, useState, type FormEvent } from 'react'
import { login } from '../api'
import Input from './ui/Input'
import Button from './ui/Button'

interface Props { onSuccess: () => void }

export default function LoginForm({ onSuccess }: Props) {
  const usernameId = useId()
  const passwordId = useId()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [capsLock, setCapsLock] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (pending) return
    setError('')
    setPending(true)
    try {
      await login(username.trim(), password)
      onSuccess()
    } catch {
      setError('Invalid username or password')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden">
      {/* Train background image */}
      <img
        src="/login-bg.jpg"
        alt=""
        aria-hidden="true"
        className="absolute inset-0 w-full h-full object-cover opacity-70 dark:opacity-45"
      />
      {/* Soft gradient overlays for readability */}
      <div className="absolute inset-0 bg-gradient-to-t from-surface-0 via-surface-0/25 to-surface-0/10" />
      <div className="absolute inset-0 bg-gradient-to-r from-surface-0/40 to-transparent" />

      <div className="relative z-10 w-full max-w-md px-4">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <img src="/amtrak-logo.png" alt="Amtrak" className="h-16 mb-4" />
          <p className="text-sm text-muted">Network Discovery & Topology Platform</p>
        </div>

        {/* Login card */}
        <form
          onSubmit={handleSubmit}
          noValidate
          className="bg-surface-1/80 backdrop-blur-xl p-8 rounded-2xl shadow-xl border border-border/40"
        >
          <h1 className="sr-only">Sign in</h1>
          {error && (
            <div
              role="alert"
              className="bg-red-950/50 border border-red-800/50 rounded-xl px-4 py-2.5 mb-4 text-sm text-red-300 backdrop-blur"
            >
              {error}
            </div>
          )}
          <div className="space-y-4">
            <div>
              <label htmlFor={usernameId} className="block text-xs text-muted mb-1.5">Username</label>
              <Input
                id={usernameId}
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full"
                autoFocus
              />
            </div>
            <div>
              <label htmlFor={passwordId} className="block text-xs text-muted mb-1.5">Password</label>
              <div className="relative">
                <Input
                  id={passwordId}
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyUp={(e) => setCapsLock(e.getModifierState('CapsLock'))}
                  className="w-full pr-10"
                  aria-describedby={capsLock ? 'capslock-hint' : undefined}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute inset-y-0 right-0 px-3 flex items-center text-muted hover:text-text-secondary transition-colors"
                >
                  {showPassword ? <EyeOffIcon /> : <EyeIcon />}
                </button>
              </div>
              {capsLock && (
                <p id="capslock-hint" role="status" className="text-[11px] text-amber-300 mt-1.5">
                  Caps Lock is on
                </p>
              )}
            </div>
            <Button type="submit" className="w-full" disabled={pending}>
              {pending ? (
                <>
                  <SpinnerIcon /> Signing in…
                </>
              ) : (
                'Sign In'
              )}
            </Button>
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

function EyeIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  )
}

function EyeOffIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
    </svg>
  )
}

function SpinnerIcon() {
  return (
    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}
