const SHORTHAND: [RegExp, string][] = [
  [/^AppGigabitEthernet/i, 'AppGi'],
  [/^TwentyFiveGigE/i, '25G'],
  [/^FortyGigabitEthernet/i, 'Fo'],
  [/^HundredGigE/i, '100G'],
  [/^TenGigabitEthernet/i, 'Te'],
  [/^GigabitEthernet/i, 'Gi'],
  [/^FastEthernet/i, 'Fa'],
  [/^Port-channel/i, 'Po'],
  [/^Loopback/i, 'Lo'],
  [/^Tunnel/i, 'Tu'],
  [/^Serial/i, 'Se'],
  [/^Bluetooth/i, 'BT'],
  [/^Management/i, 'Mgmt'],
  [/^Vlan/i, 'Vl'],
  [/^Ethernet/i, 'Eth'],
]

export function shortenInterface(name: string): string {
  if (!name) return ''
  for (const [re, abbr] of SHORTHAND) {
    if (re.test(name)) {
      return name.replace(re, abbr)
    }
  }
  return name
}
