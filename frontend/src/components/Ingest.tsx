import { useSearchParams } from 'react-router-dom'
import PageHeader from './ui/PageHeader'
import Tabs from './ui/Tabs'
import DiscoveryForm from './DiscoveryForm'
import CatalystForm from './CatalystForm'
import MerakiForm from './MerakiForm'
import VeloCloudForm from './VeloCloudForm'

const TABS = [
  { id: 'discover', label: 'Discover', icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z' },
  { id: 'catalyst', label: 'Catalyst', icon: 'M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7M4 7c0-2 1-3 3-3h10c2 0 3 1 3 3M4 7h16M9 11h6' },
  { id: 'meraki', label: 'Meraki', icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z' },
  { id: 'velocloud', label: 'VeloCloud', icon: 'M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646zM9.5 12.5l3-3 3 3M12 9v6' },
]

export default function Ingest() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'discover'
  const active = TABS.some((t) => t.id === tab) ? tab : 'discover'

  const onChange = (id: string) => {
    const next = new URLSearchParams(params)
    if (id === 'discover') next.delete('tab')
    else next.set('tab', id)
    setParams(next, { replace: true })
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-6 pt-6 pb-0">
        <PageHeader
          title="Ingest"
          description="Import devices and topology into the network model from scans and vendor sources."
        />
        <Tabs tabs={TABS} active={active} onChange={onChange} />
      </div>
      <div className="flex-1 min-h-0 overflow-auto p-6">
        {active === 'discover' && <DiscoveryForm />}
        {active === 'catalyst' && <CatalystForm />}
        {active === 'meraki' && <MerakiForm />}
        {active === 'velocloud' && <VeloCloudForm />}
      </div>
    </div>
  )
}
