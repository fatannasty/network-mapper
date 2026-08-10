import { useState, type FormEvent } from 'react'
import { collectConfigs, type CollectResult } from '../api'

export default function ConfigCollect() {
  const [sitePattern, setSitePattern] = useState('')
  const [sshUsername, setSshUsername] = useState('')
  const [sshPassword, setSshPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CollectResult | null>(null)
  const [error, setError] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const data = await collectConfigs(
        sitePattern || undefined, sshUsername, sshPassword)
      setResult(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full overflow-auto p-6 flex justify-center">
      <div className="w-full max-w-lg">
        <h2 className="text-xl font-bold mb-2">Collect Switch Configs</h2>
        <p className="text-gray-400 text-sm mb-4">
          SSH into matching switches and pull their running-config.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-400 text-sm mb-1">
              Site pattern <span className="text-gray-600">(hostname substring)</span>
            </label>
            <input
              value={sitePattern}
              onChange={(e) => setSitePattern(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
              placeholder="e.g. Sanford, Miami, or leave empty for all switches"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-gray-400 text-sm mb-1">SSH Username</label>
              <input
                value={sshUsername}
                onChange={(e) => setSshUsername(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-gray-400 text-sm mb-1">SSH Password</label>
              <input
                type="password"
                value={sshPassword}
                onChange={(e) => setSshPassword(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || !sshUsername}
            className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded font-medium transition-colors"
          >
            {loading ? 'Collecting...' : 'Collect Configs'}
          </button>

          {error && (
            <div className="bg-red-900/50 border border-red-800 rounded p-4">
              <p className="text-red-300 text-sm">{error}</p>
            </div>
          )}

          {result && (
            <div className="bg-gray-800 border border-gray-700 rounded p-4 space-y-3">
              <p className="text-green-400 text-sm">
                {result.success} of {result.total} switches collected ({result.failed} failed)
              </p>
              <div className="max-h-80 overflow-auto space-y-2">
                {result.results.map((r, i) => (
                  <div
                    key={i}
                    className={`flex items-center justify-between px-3 py-1.5 rounded text-xs ${
                      r.status === 'ok'
                        ? 'bg-green-900/30 text-green-300'
                        : 'bg-red-900/30 text-red-300'
                    }`}
                  >
                    <span>
                      {r.hostname || r.ip}
                      {r.status === 'ok' && r.config_id ? ` — config #${r.config_id}` : ''}
                    </span>
                    <span className={r.status === 'ok' ? 'text-green-400' : 'text-red-400'}>
                      {r.status === 'ok' ? '✓' : `✗ ${r.error?.slice(0, 60) || ''}`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
