interface Props {
  label: string
  className?: string
  dot?: boolean
  size?: 'sm' | 'md'
}

const colors: Record<string, string> = {
  switch: 'bg-blue-900/50 text-blue-300 border-blue-700/40',
  router: 'bg-amber-900/50 text-amber-300 border-amber-700/40',
  firewall: 'bg-red-900/50 text-red-300 border-red-700/40',
  'core-switch': 'bg-violet-900/50 text-violet-300 border-violet-700/40',
  accesspoint: 'bg-emerald-900/50 text-emerald-300 border-emerald-700/40',
  'access-point': 'bg-emerald-900/50 text-emerald-300 border-emerald-700/40',
  'wireless-controller': 'bg-cyan-900/50 text-cyan-300 border-cyan-700/40',
  'load-balancer': 'bg-pink-900/50 text-pink-300 border-pink-700/40',
  'sd-wan': 'bg-teal-900/50 text-teal-300 border-teal-700/40',
  'velocloud-lan': 'bg-teal-900/50 text-teal-300 border-teal-700/40',
  'velocloud': 'bg-teal-900/50 text-teal-300 border-teal-700/40',
  unknown: 'bg-gray-800/60 text-gray-400 border-gray-700/40',
  printer: 'bg-zinc-900/50 text-zinc-300 border-zinc-700/40',
  lldp: 'bg-blue-900/50 text-blue-300 border-blue-700/40',
  cdp: 'bg-amber-900/50 text-amber-300 border-amber-700/40',
  'cdp-lldp': 'bg-green-900/50 text-green-300 border-green-700/40',
  catalyst: 'bg-violet-900/50 text-violet-300 border-violet-700/40',
  up: 'bg-green-900/50 text-green-300 border-green-700/40',
  down: 'bg-red-900/50 text-red-300 border-red-700/40',
  met: 'bg-green-900/50 text-green-300 border-green-700/40',
  gap: 'bg-amber-900/50 text-amber-300 border-amber-700/40',
  completed: 'bg-green-900/50 text-green-300 border-green-700/40',
  active: 'bg-green-900/50 text-green-300 border-green-700/40',
}

const sizes = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-sm',
}

export default function Badge({ label, className = '', dot, size = 'sm' }: Props) {
  const color = colors[label] || colors.unknown
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-lg font-medium border backdrop-blur transition-all duration-200 ${sizes[size]} ${color} ${className}`}>
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-current opacity-90 shadow-sm shadow-current/40" />}
      {label}
    </span>
  )
}
