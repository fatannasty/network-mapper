import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { testVeloCloud, importFromVeloCloud } from '../api'
import PageHeader from './ui/PageHeader'
import Input from './ui/Input'
import Button from './ui/Button'
import Card from './ui/Card'

export default function VeloCloudForm() {
  const [baseUrl, setBaseUrl] = useState('https://velocloud.net')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [result, setResult] = useState<{ scan_id: string; device_count: number; links_found: number; debug?: Record<string, unknown> } | null>(null)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const r = await testVeloCloud(baseUrl, username, password)
      setTestResult(`Connected! Found ${r.edge_count} edges.`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setTestResult(msg)
    } finally {
      setTesting(false)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResult(null)
    setError('')
    try {
      const data = await importFromVeloCloud(baseUrl, username, password)
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
        <PageHeader
          title="Import from VeloCloud Orchestra"
          description="Pull SD-WAN edges and link data from VeloCloud Orchestrator."
        />
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-muted text-sm mb-1">Orchestrator URL</label>
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full"
              placeholder="https://velocloud.net or https://vco123.velocloud.net"
            />
            <p className="text-gray-600 text-[11px] mt-0.5">
              Enter your VeloCloud Orchestrator URL (e.g., https://vco123.velocloud.net).
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-muted text-sm mb-1">Username</label>
              <Input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full"
                placeholder="operator"
              />
            </div>
            <div>
              <label className="block text-muted text-sm mb-1">Password</label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full"
              />
            </div>
          </div>

          <div className="flex gap-3">
            <Button
              type="button"
              variant="secondary"
              disabled={testing || !username || !password}
              onClick={handleTest}
              className="flex-1"
            >
              {testing ? 'Testing...' : 'Test Connection'}
            </Button>
            <Button
              type="submit"
              disabled={loading || !username || !password}
              className="flex-1"
            >
              {loading ? 'Importing...' : 'Import'}
            </Button>
          </div>

          {testResult && (
            <div className={`rounded p-3 text-xs ${testResult.startsWith('Connected') ? 'bg-green-900/50 border border-green-800 text-green-300' : 'bg-red-900/50 border border-red-800 text-red-300'}`}>
              {testResult}
            </div>
          )}

          {error && (
            <div className="bg-red-900/50 border border-red-800 rounded p-4">
              <p className="text-red-300 text-sm">{error}</p>
            </div>
          )}

          {result && (
            <Card className="space-y-3">
              <p className="text-green-300 text-sm">
                Imported {result.device_count} edges, {result.links_found} links.
              </p>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate(`/topology?scan_id=${result.scan_id}`)}
              >
                View Topology
              </Button>
              {result.debug && (
                <pre className="text-xs text-muted bg-surface-2 p-2 rounded max-h-60 overflow-auto whitespace-pre-wrap">
                  {JSON.stringify(result.debug, null, 2)}
                </pre>
              )}
            </Card>
          )}
        </form>
      </div>
    </div>
  )
}
