import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { discover } from '../api'

export default function DiscoveryForm() {
  const [subnet, setSubnet] = useState('127.0.0.1/32')
  const [community, setCommunity] = useState('public')
  const [snmpv3, setSnmpv3] = useState(false)
  const [username, setUsername] = useState('')
  const [authPass, setAuthPass] = useState('')
  const [privPass, setPrivPass] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const navigate = useNavigate()

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResult(null)
    try {
      const v3 = snmpv3
        ? { username, auth_protocol: 'sha', auth_password: authPass, privacy_protocol: 'aes', privacy_password: privPass || authPass }
        : undefined
      const data = await discover(subnet, community ? [community] : [], v3)
      setResult(data.scan_id)
    } catch (err: unknown) {
      setResult(err instanceof Error ? err.message : 'Discovery failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full overflow-auto p-6 flex justify-center">
      <div className="w-full max-w-lg">
        <h2 className="text-xl font-bold mb-4">Discover Network</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-gray-400 text-sm mb-1">Subnet (CIDR)</label>
            <input
              value={subnet}
              onChange={(e) => setSubnet(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
              placeholder="10.0.0.0/24"
            />
          </div>
          <div>
            <label className="block text-gray-400 text-sm mb-1">SNMP Community</label>
            <input
              value={community}
              onChange={(e) => setCommunity(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={snmpv3}
              onChange={(e) => setSnmpv3(e.target.checked)}
              className="rounded"
            />
            Use SNMPv3
          </label>

          {snmpv3 && (
            <div className="space-y-3 pl-2 border-l-2 border-gray-700">
              <input
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
              />
              <input
                type="password"
                placeholder="Auth password"
                value={authPass}
                onChange={(e) => setAuthPass(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
              />
              <input
                type="password"
                placeholder="Privacy password (optional)"
                value={privPass}
                onChange={(e) => setPrivPass(e.target.value)}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-2 rounded font-medium transition-colors"
          >
            {loading ? 'Scanning...' : 'Start Discovery'}
          </button>

          {result && result.length === 12 && (
            <div className="bg-green-900/50 border border-green-800 rounded p-4">
              <p className="text-green-300">Discovery complete.</p>
              <button
                type="button"
                onClick={() => navigate(`/topology?scan_id=${result}`)}
                className="mt-2 px-4 py-1.5 bg-green-700 hover:bg-green-600 text-white rounded text-sm transition-colors"
              >
                View Topology
              </button>
            </div>
          )}

          {result && result.length !== 12 && (
            <div className="bg-red-900/50 border border-red-800 rounded p-4">
              <p className="text-red-300">{result}</p>
            </div>
          )}
        </form>
      </div>
    </div>
  )
}
