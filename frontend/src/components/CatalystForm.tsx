import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { importFromCatalyst } from '../api'

export default function CatalystForm() {
  const [baseUrl, setBaseUrl] = useState('https://')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ scan_id: string; device_count: number; links_found: number } | null>(null)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const data = await importFromCatalyst(baseUrl, username, password)
      setResult(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full overflow-auto p-6 flex justify-center">
      <div className="w-full max-w-lg">
        <h2 className="text-xl font-bold mb-2">Import from Catalyst Center</h2>
        <p className="text-gray-500 text-sm mb-4">
          Import device inventory and physical topology from Cisco Catalyst Center (DNA Center).
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-400 text-sm mb-1">Catalyst Center URL</label>
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
              placeholder="https://catalyst-center.example.com"
            />
          </div>
          <div>
            <label className="block text-gray-400 text-sm mb-1">Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
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
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-2 rounded font-medium transition-colors"
          >
            {loading ? 'Importing...' : 'Import from Catalyst Center'}
          </button>

          {error && (
            <div className="bg-red-900/50 border border-red-800 rounded p-4">
              <p className="text-red-300 text-sm">{error}</p>
            </div>
          )}

          {result && (
            <div className="bg-green-900/50 border border-green-800 rounded p-4 space-y-3">
              <p className="text-green-300 text-sm">
                Imported {result.device_count} devices, {result.links_found} topology links.
              </p>
              <button
                type="button"
                onClick={() => navigate(`/topology?scan_id=${result.scan_id}`)}
                className="px-4 py-1.5 bg-green-700 hover:bg-green-600 text-white rounded text-sm transition-colors"
              >
                View Topology
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
