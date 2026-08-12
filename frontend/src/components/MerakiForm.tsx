import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { testMeraki, importFromMeraki } from '../api'
import PageHeader from './ui/PageHeader'
import Input from './ui/Input'
import Button from './ui/Button'
import Card from './ui/Card'

export default function MerakiForm() {
  const [baseUrl, setBaseUrl] = useState('https://api.meraki.com')
  const [apiKey, setApiKey] = useState('')
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
      const r = await testMeraki(baseUrl, apiKey)
      setTestResult(`Connected! Found ${r.organizations} org(s) with ${r.device_count} devices.`)
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
      const data = await importFromMeraki(baseUrl, apiKey)
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
          title="Import from Meraki Dashboard"
          description="Pull devices and LLDP/CDP neighbor data from the Meraki cloud dashboard."
        />
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-muted text-sm mb-1">Dashboard URL</label>
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full"
              placeholder="https://api.meraki.com"
            />
            <p className="text-gray-600 text-[11px] mt-0.5">
              Use https://api.meraki.com for the global dashboard, or a regional URL.
            </p>
          </div>

          <div>
            <label className="block text-muted text-sm mb-1">API Key</label>
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="w-full"
              placeholder="Your Meraki Dashboard API key"
            />
            <p className="text-gray-600 text-[11px] mt-0.5">
              Generate from Meraki Dashboard: Organization &gt; Settings &gt; Dashboard API access.
            </p>
          </div>

          <div className="flex gap-3">
            <Button
              type="button"
              variant="secondary"
              disabled={testing || !apiKey}
              onClick={handleTest}
              className="flex-1"
            >
              {testing ? 'Testing...' : 'Test Connection'}
            </Button>
            <Button
              type="submit"
              disabled={loading || !apiKey}
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
                Imported {result.device_count} devices, {result.links_found} topology links.
              </p>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate(`/topology?scan_id=${result.scan_id}`)}
              >
                View Topology
              </Button>
              {result.debug && (
                <pre className="text-xs text-muted bg-surface-2/60 backdrop-blur p-2 rounded-xl max-h-60 overflow-auto whitespace-pre-wrap border border-border/30">
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
