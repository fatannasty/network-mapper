const colors: Record<string, string> = {
  switch: 'bg-blue-900/40 text-blue-300 border-blue-800',
  router: 'bg-amber-900/40 text-amber-300 border-amber-800',
  firewall: 'bg-red-900/40 text-red-300 border-red-800',
  'core-switch': 'bg-purple-900/40 text-purple-300 border-purple-800',
  accesspoint: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
  'access-point': 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
  'wireless-controller': 'bg-cyan-900/40 text-cyan-300 border-cyan-800',
  'load-balancer': 'bg-pink-900/40 text-pink-300 border-pink-800',
  'sd-wan': 'bg-teal-900/40 text-teal-300 border-teal-800',
  'velocloud-lan': 'bg-teal-900/40 text-teal-300 border-teal-800',
  'velocloud': 'bg-teal-900/40 text-teal-300 border-teal-800',
  unknown: 'bg-gray-800 text-gray-400 border-gray-700',
  printer: 'bg-zinc-900/40 text-zinc-300 border-zinc-700',
  lldp: 'bg-blue-900/40 text-blue-300 border-blue-800',
  cdp: 'bg-amber-900/40 text-amber-300 border-amber-800',
  'cdp-lldp': 'bg-green-900/40 text-green-300 border-green-800',
  catalyst: 'bg-purple-900/40 text-purple-300 border-purple-800',
  up: 'bg-green-900/40 text-green-300 border-green-800',
  down: 'bg-red-900/40 text-red-300 border-red-800',
  met: 'bg-green-900/40 text-green-300 border-green-800',
  gap: 'bg-amber-900/40 text-amber-300 border-amber-800',
}

interface Props {
  label: string
  className?: string
  dot?: boolean
  size?: 'sm' | 'md'
}

const sizes = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-sm',
}

export default function Badge({ label, className = '', dot, size = 'sm' }: Props) {
  const color = colors[label] || colors.unknown
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md font-medium border transition-all duration-200 ${sizes[size]} ${color} ${className}`}>
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80 shadow-sm shadow-current/50" />}
      {label}
    </span>
  )
}
