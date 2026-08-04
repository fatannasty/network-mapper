import { useState, type FormEvent } from 'react'
import { login, setToken } from '../api'

interface Props {
  onSuccess: () => void
}

export default function LoginForm({ onSuccess }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const data = await login(username, password)
      setToken(data.token)
      onSuccess()
    } catch {
      setError('Invalid credentials')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <form onSubmit={handleSubmit} className="bg-gray-900 p-8 rounded-lg shadow-lg w-96 border border-gray-800">
        <h1 className="text-2xl font-bold text-white mb-6 text-center">
          Network Mapper
        </h1>
        {error && (
          <div className="bg-red-900/50 text-red-300 px-4 py-2 rounded mb-4 text-sm">
            {error}
          </div>
        )}
        <div className="mb-4">
          <label className="block text-gray-400 text-sm mb-1">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
            autoFocus
          />
        </div>
        <div className="mb-6">
          <label className="block text-gray-400 text-sm mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
          />
        </div>
        <button
          type="submit"
          className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded font-medium transition-colors"
        >
          Sign In
        </button>
      </form>
    </div>
  )
}
