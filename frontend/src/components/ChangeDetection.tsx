import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getScans, getChanges, type ChangeResult, type ScanInfo } from '../api'

export default function ChangeDetection() {
  const [scans, setScans] = useState<ScanInfo[]>([])
  const [scanA, setScanA] = useState('')
  const [scanB, setScanB] = useState('')
  const [result, setResult] = useState<ChangeResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    getScans(100).then((r) => setScans(r.scans || [])).catch(() => {})
  }, [])

  const handleCompare = useCallback(async () => {
    if (!scanA || !scanB) return
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const r = await getChanges(scanA, scanB)
      setResult(r)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [scanA, scanB])

  return (
    <div className="h-full overflow-auto p-6 flex justify-center">
      <div className="w-full max-w-3xl">
        <h2 className="text-xl font-bold mb-2">Change Detection</h2>
        <p className="text-gray-400 text-sm mb-4">
          Compare two scans to see what devices and links were added or removed.
        </p>

        <div className="flex items-end gap-3 mb-6">
          <div className="flex-1">
            <label className="block text-gray-400 text-xs mb-1">Baseline (before)</label>
            <select
              value={scanA}
              onChange={(e) => setScanA(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
            >
              <option value="">Select scan…</option>
              {scans.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.subnet} — {s.device_count} devices — {s.id.slice(0, 8)} — {s.started_at?.slice(0, 16) || ''}
                </option>
              ))}
            </select>
          </div>
          <span className="text-gray-500 pb-2">vs</span>
          <div className="flex-1">
            <label className="block text-gray-400 text-xs mb-1">Current (after)</label>
            <select
              value={scanB}
              onChange={(e) => setScanB(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:outline-none focus:border-blue-500"
            >
              <option value="">Select scan…</option>
              {scans.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.subnet} — {s.device_count} devices — {s.id.slice(0, 8)} — {s.started_at?.slice(0, 16) || ''}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={handleCompare}
            disabled={!scanA || !scanB || loading}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded font-medium text-sm transition-colors"
          >
            {loading ? 'Comparing…' : 'Compare'}
          </button>
        </div>

        {error && (
          <div className="bg-red-900/50 border border-red-800 rounded p-4 text-red-300 text-sm mb-4">
            {error}
          </div>
        )}

        {result && (
          <div className="space-y-6">
            {/* Summary */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-800 border border-gray-700 rounded p-4">
                <span className="text-gray-500 text-xs block mb-1">Baseline</span>
                <p className="text-white text-sm">{result.scan_a.subnet}</p>
                <p className="text-gray-400 text-xs">
                  {result.devices.count_a} devices &middot; {result.links.count_a} links
                  <br />
                  <span className="text-gray-600">{result.scan_a.started_at?.slice(0, 16)}</span>
                </p>
                <button
                  onClick={() => navigate(`/topology?scan_id=${result.scan_a.id}`)}
                  className="mt-2 px-3 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs transition-colors"
                >
                  View Topology
                </button>
              </div>
              <div className="bg-gray-800 border border-gray-700 rounded p-4">
                <span className="text-gray-500 text-xs block mb-1">Current</span>
                <p className="text-white text-sm">{result.scan_b.subnet}</p>
                <p className="text-gray-400 text-xs">
                  {result.devices.count_b} devices &middot; {result.links.count_b} links
                  <br />
                  <span className="text-gray-600">{result.scan_b.started_at?.slice(0, 16)}</span>
                </p>
                <button
                  onClick={() => navigate(`/topology?scan_id=${result.scan_b.id}`)}
                  className="mt-2 px-3 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs transition-colors"
                >
                  View Topology
                </button>
              </div>
            </div>

            {/* Device changes */}
            <div className="bg-gray-800 border border-gray-700 rounded p-4">
              <h3 className="text-sm font-semibold text-white mb-3">Device Changes</h3>

              {result.devices.added.length > 0 && (
                <div className="mb-4">
                  <span className="text-green-400 text-xs font-medium">
                    +{result.devices.added.length} Added
                  </span>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {result.devices.added.map((ip) => (
                      <span key={ip} className="px-2 py-0.5 bg-green-900/30 border border-green-800 rounded text-xs text-green-300 font-mono">
                        {ip}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {result.devices.removed.length > 0 && (
                <div className="mb-4">
                  <span className="text-red-400 text-xs font-medium">
                    -{result.devices.removed.length} Removed
                  </span>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {result.devices.removed.map((ip) => (
                      <span key={ip} className="px-2 py-0.5 bg-red-900/30 border border-red-800 rounded text-xs text-red-300 font-mono">
                        {ip}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {result.devices.changed.length > 0 && (
                <div>
                  <span className="text-amber-400 text-xs font-medium">
                    ~{result.devices.changed.length} Changed
                  </span>
                  <div className="mt-1 space-y-1 max-h-60 overflow-auto">
                    {result.devices.changed.map((d) => (
                      <div key={d.ip} className="bg-gray-900 rounded px-3 py-2 text-xs">
                        <span className="text-white font-mono mr-2">{d.ip}</span>
                        {Object.entries(d.changes).map(([key, val]) => (
                          <span key={key} className="mr-3">
                            <span className="text-gray-500">{key}: </span>
                            <span className="text-red-400">{val.from || '—'}</span>
                            <span className="text-gray-600"> → </span>
                            <span className="text-green-400">{val.to || '—'}</span>
                          </span>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {result.devices.added.length === 0 && result.devices.removed.length === 0 && result.devices.changed.length === 0 && (
                <p className="text-gray-500 text-xs">No device changes between these scans</p>
              )}
            </div>

            {/* Link changes */}
            <div className="bg-gray-800 border border-gray-700 rounded p-4">
              <h3 className="text-sm font-semibold text-white mb-3">Link Changes</h3>

              {result.links.added.length > 0 && (
                <div className="mb-4">
                  <span className="text-green-400 text-xs font-medium">
                    +{result.links.added.length} Added
                  </span>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {result.links.added.slice(0, 50).map((l, i) => (
                      <span key={i} className="px-2 py-0.5 bg-green-900/30 border border-green-800 rounded text-xs text-green-300 font-mono">
                        {l.source} ↔ {l.target}
                      </span>
                    ))}
                    {result.links.added.length > 50 && (
                      <span className="text-gray-500 text-xs">+{result.links.added.length - 50} more</span>
                    )}
                  </div>
                </div>
              )}

              {result.links.removed.length > 0 && (
                <div>
                  <span className="text-red-400 text-xs font-medium">
                    -{result.links.removed.length} Removed
                  </span>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {result.links.removed.slice(0, 50).map((l, i) => (
                      <span key={i} className="px-2 py-0.5 bg-red-900/30 border border-red-800 rounded text-xs text-red-300 font-mono">
                        {l.source} ↔ {l.target}
                      </span>
                    ))}
                    {result.links.removed.length > 50 && (
                      <span className="text-gray-500 text-xs">+{result.links.removed.length - 50} more</span>
                    )}
                  </div>
                </div>
              )}

              {result.links.added.length === 0 && result.links.removed.length === 0 && (
                <p className="text-gray-500 text-xs">No link changes between these scans</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
