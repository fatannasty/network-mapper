import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from './ui/Button'

export const ONBOARDED_KEY = 'nm_onboarded'

interface Step {
  title: string
  body: string
  route?: string
  actionLabel?: string
}

const STEPS: Step[] = [
  {
    title: 'Welcome',
    body: 'Welcome to the Amtrak Network Mapper. It maps your network devices and how they connect, tracks their health, and turns all of that into reports. This 2-minute tour covers the essentials — skip anytime.',
  },
  {
    title: 'Bring your network in',
    body: 'The Import page is where you load your network. Choose the source that fits: Discover scans a subnet, SNMP Walk samples your whole network or a single site, Catalyst pulls from Cisco Catalyst Center, and Meraki/VeloCloud from their dashboards. Start with just one.',
    route: '/ingest',
    actionLabel: 'Open Import',
  },
  {
    title: 'Read the map',
    body: 'Topology is your network as a diagram — devices are icons colored by type, connected by links. Zoom in to read labels. Each node carries health badges: the status dot (up/down), an amber ⚠ for a Single Point of Failure, and a teal V90 for switches on VLAN 90.',
    route: '/topology',
    actionLabel: 'Open Topology',
  },
  {
    title: 'Share what you find',
    body: 'The Topology toolbar can Export a Diagram (Visio/PDF), a Port Table CSV, or a Walk Report CSV of every interface and VLAN. Dashboards and Data Quality pages add executive and engineering views.',
    route: '/topology',
    actionLabel: 'See exports',
  },
  {
    title: 'Health at a glance',
    body: 'The Dashboard has two views: Executive — a management scorecard with health score, site freshness, and top risks — and Operations — a live engineering view. Use the toggle in the top-right to switch.',
    route: '/dashboard',
    actionLabel: 'Open Dashboard',
  },
]

interface GlossaryEntry { term: string; def: string }

const GLOSSARY: GlossaryEntry[] = [
  { term: 'Device', def: 'Any piece of network hardware — switch, router, firewall, access point.' },
  { term: 'Switch', def: 'Connects devices on a network and forwards traffic between them.' },
  { term: 'Core switch / Router', def: 'The backbone that carries traffic between buildings, sites, and networks.' },
  { term: 'Access point (AP)', def: 'A Wi-Fi access point that lets wireless clients join the network.' },
  { term: 'SNMP', def: 'A standard protocol devices expose so tools can read their status — the \u201ceyes\u201d into the network.' },
  { term: 'SNMP walk', def: 'Fetching a device\u2019s full details over SNMP — interfaces, links, and VLANs.' },
  { term: 'VLAN', def: 'Splits one physical switch into separate virtual networks. VLAN 90 is the one tracked here.' },
  { term: 'LLDP / CDP', def: 'Protocols switches use to tell neighbors who they are — how links between devices are discovered.' },
  { term: 'SPOF (Single Point of Failure)', def: 'A device whose loss would split the network into disconnected pieces — a risk to watch.' },
  { term: 'Flapping', def: 'A link or device repeatedly going up and down — often a failing port or cable.' },
  { term: 'Latency', def: 'How long a packet takes to reach a device, measured in milliseconds.' },
  { term: 'Config coverage', def: 'The percentage of switches that have a saved running configuration — a quality score.' },
  { term: 'Topology', def: 'The map of how your devices are connected to each other.' },
  { term: 'DoD gates', def: 'Quality targets (Definition of Done) — site, interface, link, and config coverage.' },
]

interface Props {
  open: boolean
  onClose: () => void
}

export default function HelpModal({ open, onClose }: Props) {
  const [mode, setMode] = useState<'tour' | 'glossary'>('tour')
  const [step, setStep] = useState(0)
  const navigate = useNavigate()

  useEffect(() => {
    if (open) { setMode('tour'); setStep(0) }
  }, [open])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const close = () => {
    localStorage.setItem(ONBOARDED_KEY, '1')
    onClose()
  }

  const stepData = STEPS[step]
  const last = step === STEPS.length - 1

  const go = (route?: string) => {
    if (route) navigate(route)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Help">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={close} />
      <div className="relative w-full max-w-lg rounded-2xl border border-border/40 bg-surface-1 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-4">
          <div className="flex items-center gap-1 bg-surface-2/70 rounded-xl p-0.5">
            <button
              onClick={() => setMode('tour')}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${mode === 'tour' ? 'bg-accent text-white' : 'text-muted hover:text-text-primary'}`}
            >
              Tour
            </button>
            <button
              onClick={() => setMode('glossary')}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${mode === 'glossary' ? 'bg-accent text-white' : 'text-muted hover:text-text-primary'}`}
            >
              Glossary
            </button>
          </div>
          <button onClick={close} aria-label="Close help" className="text-muted hover:text-text-primary text-lg leading-none px-1">&times;</button>
        </div>

        {mode === 'tour' ? (
          <div className="px-5 py-4">
            {/* Step indicator */}
            <div className="flex items-center gap-1.5 mb-4">
              {STEPS.map((_, i) => (
                <span key={i} className={`h-1.5 rounded-full transition-all ${i === step ? 'w-6 bg-accent' : i < step ? 'w-1.5 bg-accent/50' : 'w-1.5 bg-surface-3'}`} />
              ))}
            </div>

            <h2 className="text-lg font-semibold text-text-primary">{stepData.title}</h2>
            <p className="text-sm text-text-secondary leading-relaxed mt-2">{stepData.body}</p>

            <div className="flex items-center justify-between gap-3 mt-6">
              <Button variant="secondary" size="sm" onClick={close}>
                {last ? 'Finish' : 'Skip tour'}
              </Button>
              <div className="flex items-center gap-2">
                {step > 0 && (
                  <Button variant="secondary" size="sm" onClick={() => setStep(step - 1)}>Back</Button>
                )}
                {!last && stepData.actionLabel && (
                  <Button variant="secondary" size="sm" onClick={() => go(stepData.route)}>{stepData.actionLabel}</Button>
                )}
                <Button size="sm" onClick={() => (last ? close() : setStep(step + 1))}>
                  {last ? 'Done' : 'Next'}
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="px-5 py-4">
            <h2 className="text-lg font-semibold text-text-primary mb-3">Plain-language glossary</h2>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {GLOSSARY.map((g) => (
                <div key={g.term} className="bg-surface-2/60 rounded-xl px-3 py-2">
                  <div className="text-xs font-semibold text-text-primary">{g.term}</div>
                  <div className="text-xs text-text-secondary mt-0.5 leading-relaxed">{g.def}</div>
                </div>
              ))}
            </div>
            <div className="mt-5 flex justify-end">
              <Button size="sm" onClick={close}>Got it</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}