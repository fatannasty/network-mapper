/** Beginner-friendly labels, descriptions and icons for device types.
    Centralised so the node cards, legend and detail panel all speak the
    same plain English. */

export interface DeviceTypeInfo {
  label: string
  description: string
  icon: string[]
}

export const DEVICE_TYPE_INFO: Record<string, DeviceTypeInfo> = {
  switch: {
    label: 'Switch',
    description: 'Connects computers, printers and other devices together on the same network.',
    icon: [
      'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z',
      'M8 9h.01M8 13h.01M12 9h.01M12 13h.01M16 9h.01M16 13h.01',
    ],
  },
  'core-switch': {
    label: 'Core Switch',
    description: 'The main switch at the centre of the network that links everything together.',
    icon: [
      'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z',
      'M8 9h.01M8 13h.01M12 9h.01M12 13h.01M16 9h.01M16 13h.01',
    ],
  },
  router: {
    label: 'Router',
    description: 'Connects your network to other networks and the internet.',
    icon: [
      'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z',
      'M3.6 9h16.8M3.6 15h16.8',
      'M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
    ],
  },
  firewall: {
    label: 'Firewall',
    description: 'A security barrier that checks traffic and blocks threats.',
    icon: [
      'M12 3l7 3v5c0 4.6-3 8.3-7 10-4-1.7-7-5.4-7-10V6l7-3Z',
      'M9 12l2 2 4-4',
    ],
  },
  accesspoint: {
    label: 'Access Point',
    description: 'Provides wireless (Wi-Fi) access for phones, laptops and tablets.',
    icon: [
      'M5 12a7 7 0 0 1 14 0',
      'M8.5 15a3.5 3.5 0 0 1 7 0',
      'M12 18.5h.01',
    ],
  },
  'access-point': {
    label: 'Access Point',
    description: 'Provides wireless (Wi-Fi) access for phones, laptops and tablets.',
    icon: [
      'M5 12a7 7 0 0 1 14 0',
      'M8.5 15a3.5 3.5 0 0 1 7 0',
      'M12 18.5h.01',
    ],
  },
  'sd-wan': {
    label: 'SD-WAN',
    description: 'Smartly routes traffic between office locations over the internet.',
    icon: [
      'M20 17.6A4 4 0 0 0 18 10h-1.3A7 7 0 1 0 4 14.4',
      'M12 13v6M8 16l4 3 4-3',
    ],
  },
  'velocloud-edge': {
    label: 'SD-WAN Edge',
    description: 'Connects a remote office to the rest of the network over the internet.',
    icon: [
      'M20 17.6A4 4 0 0 0 18 10h-1.3A7 7 0 1 0 4 14.4',
      'M12 13v6M8 16l4 3 4-3',
    ],
  },
  'wireless-controller': {
    label: 'Wireless Controller',
    description: 'The manager that coordinates all of the Wi-Fi access points.',
    icon: [
      'M5 12a7 7 0 0 1 14 0',
      'M8.5 15a3.5 3.5 0 0 1 7 0',
      'M12 18.5h.01',
    ],
  },
  'load-balancer': {
    label: 'Load Balancer',
    description: 'Spreads incoming traffic evenly across several servers.',
    icon: [
      'M12 4v16',
      'M5 8h14',
      'M7 8l5-4 5 4',
      'M7 16l5 4 5-4',
    ],
  },
  unknown: {
    label: 'Network Device',
    description: 'A device we could not identify yet.',
    icon: [
      'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z',
      'M9.5 9a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.1 1-1.1 1.8',
      'M12 16.5h.01',
    ],
  },
  subnet: {
    label: 'Subnet Block',
    description: 'A group of devices on the same subnet, collapsed for readability.',
    icon: [
      'M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5Z',
      'M8 9h8M8 13h8M8 17h4',
    ],
  },
}

const BLANK_ALIASES: Record<string, string> = {
  'access point': 'accesspoint',
  'access-point': 'accesspoint',
  ap: 'accesspoint',
  wap: 'accesspoint',
  'core switch': 'core-switch',
  'core-switch': 'core-switch',
  switch: 'switch',
  router: 'router',
  firewall: 'firewall',
  'sd-wan': 'sd-wan',
  sdwan: 'sd-wan',
  'velocloud edge': 'velocloud-edge',
  velocloud: 'velocloud-edge',
  subnet: 'subnet',
}

export function normalizeType(t: string): string {
  const key = (t || '').trim().toLowerCase()
  return BLANK_ALIASES[key] || key || 'unknown'
}

export function friendlyType(t: string): string {
  return DEVICE_TYPE_INFO[normalizeType(t)]?.label ?? 'Network Device'
}

export function typeDescription(t: string): string {
  return DEVICE_TYPE_INFO[normalizeType(t)]?.description
    ?? DEVICE_TYPE_INFO.unknown.description
}

export function typeIcon(t: string): string[] {
  return DEVICE_TYPE_INFO[normalizeType(t)]?.icon ?? DEVICE_TYPE_INFO.unknown.icon
}

/** Plural of a friendly type label: Switch -> Switches, Access Point -> Access Points. */
export function pluralLabel(t: string): string {
  const label = friendlyType(t)
  if (label.endsWith('y')) return `${label.slice(0, -1)}ies`
  if (label.endsWith('s')) return `${label}es`
  return `${label}s`
}

/** Strip the domain suffix off a hostname so it reads like a plain name:
    AMTRMIAFL09S.amtrak.ad.nrpc  ->  AMTRMIAFL09S */
export function shortName(hostname: string): string {
  if (!hostname) return ''
  return hostname.split('.')[0]
}
