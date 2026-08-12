import { useSearchParams } from 'react-router-dom'
import PageHeader from './ui/PageHeader'
import Tabs from './ui/Tabs'
import ConfigCollect from './ConfigCollect'
import ChangeDetection from './ChangeDetection'

const TABS = [
  { id: 'collect', label: 'Collect', icon: 'M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4' },
  { id: 'changes', label: 'Changes', icon: 'M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z' },
]

export default function Configs() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'collect'
  const active = TABS.some((t) => t.id === tab) ? tab : 'collect'

  const onChange = (id: string) => {
    const next = new URLSearchParams(params)
    if (id === 'collect') next.delete('tab')
    else next.set('tab', id)
    setParams(next, { replace: true })
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-6 pt-6 pb-0">
        <PageHeader
          title="Configs"
          description="Collect running-configs and compare scans to detect network changes."
        />
        <Tabs tabs={TABS} active={active} onChange={onChange} />
      </div>
      <div className="flex-1 min-h-0 overflow-auto p-6">
        {active === 'collect' && <ConfigCollect />}
        {active === 'changes' && <ChangeDetection />}
      </div>
    </div>
  )
}
