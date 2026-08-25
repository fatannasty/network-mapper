import { test, expect } from '@playwright/test'

const DEVICES = [
  { id: 1, ip: '10.0.1.1', hostname: 'SW-V90', vendor: 'Cisco', model: 'C9300', device_type: 'switch', confidence: 5, open_ports: [161], snmp_community: '', snmp_identified: true, interfaces: [], site: 'Chicago', vlan_90: true },
  { id: 2, ip: '10.0.1.2', hostname: 'SW-NOV90', vendor: 'Cisco', model: 'C9200', device_type: 'switch', confidence: 5, open_ports: [161], snmp_community: '', snmp_identified: true, interfaces: [], site: 'Chicago', vlan_90: false },
  { id: 3, ip: '10.0.1.3', hostname: 'SW-UNKNOWN', vendor: 'Cisco', model: 'C9300', device_type: 'switch', confidence: 5, open_ports: [161], snmp_community: '', snmp_identified: true, interfaces: [], site: 'Denver', vlan_90: null },
]

function mockApi(page: import('@playwright/test').Page) {
  let authed = false
  return page.route('**/api/**', (route) => {
    const url = route.request().url()
    const method = route.request().method()
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (url.includes('/api/auth/login') && method === 'POST') {
      authed = true
      return json(200, { token: 't', token_type: 'bearer', username: 'admin', role: 'admin' })
    }
    if (url.includes('/api/auth/me')) {
      return authed ? json(200, { username: 'admin', role: 'admin' }) : json(401, { detail: 'unauthenticated' })
    }
    if (url.includes('/api/inventory/devices') && url.includes('/utilization')) {
      return json(200, { device_id: 1, ip: '', hostname: '', interfaces: [] })
    }
    if (url.includes('/api/inventory/devices') && url.includes('/configs')) {
      return json(200, [])
    }
    if (url.includes('/api/inventory/devices')) {
      const params = new URL(url).searchParams
      const vlan = params.get('vlan_90')
      let list = DEVICES
      if (vlan === 'true') list = DEVICES.filter((d) => d.vlan_90 === true)
      else if (vlan === 'false') list = DEVICES.filter((d) => d.vlan_90 === false)
      return json(200, { devices: list, links: [] })
    }
    if (url.includes('/api/inventory/sites')) {
      return json(200, { count: 2, sites: [{ name: 'Chicago', location: '' }, { name: 'Denver', location: '' }] })
    }
    if (url.includes('/api/inventory/scans')) {
      return json(200, { scans: [] })
    }
    if (url.includes('/api/topology/summary')) {
      return json(200, { groups: [] })
    }
    if (url.includes('/api/topology')) {
      return json(200, {
        scan_id: 's1',
        nodes: DEVICES.map((d) => ({
          id: d.ip, ip: d.ip, hostname: d.hostname, vendor: d.vendor, model: d.model,
          device_type: d.device_type, status: 'up', spof: false, vlan_90: d.vlan_90 === true,
        })),
        links: [],
        scan_meta: { subnet: 'Test', device_count: DEVICES.length, started_at: null, scan_kind: 'catalyst' },
      })
    }
    return json(200, {})
  })
}

test('VLAN 90 flows through inventory filter, detail, and topology', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByLabel('Username', { exact: true }).fill('admin')
  await page.getByLabel('Password', { exact: true }).fill('admin')
  await page.getByRole('button', { name: /sign in/i }).click()

  // ── Inventory filter ────────────────────────────────────────────────────
  await page.goto('/inventory')
  const group = page.getByRole('group', { name: 'VLAN 90 filter' })
  await expect(group.getByRole('button', { name: 'All' })).toBeVisible()
  await expect(page.getByText('SW-V90', { exact: true })).toBeVisible()

  await group.getByRole('button', { name: 'VLAN 90', exact: true }).click()
  await expect(page.getByText('SW-V90', { exact: true })).toBeVisible()
  await expect(page.getByText('SW-NOV90', { exact: true })).toHaveCount(0)

  await group.getByRole('button', { name: 'No VLAN 90', exact: true }).click()
  await expect(page.getByText('SW-NOV90', { exact: true })).toBeVisible()
  await expect(page.getByText('SW-V90', { exact: true })).toHaveCount(0)

  // ── Device detail shows the flag ────────────────────────────────────────
  await group.getByRole('button', { name: 'All', exact: true }).click()
  await page.getByText('SW-V90', { exact: true }).first().click()
  await expect(page.getByText('VLAN 90 configured', { exact: true })).toBeVisible({ timeout: 5000 })

  // ── Topology node badge ─────────────────────────────────────────────────
  await page.goto('/topology')
  await page.getByText('Technical', { exact: true }).click()
  await expect(page.getByText('V90', { exact: true })).toBeVisible({ timeout: 10000 })
})