import { test, expect } from '@playwright/test'

const DEVICES = [
  { id: 1, ip: '10.0.1.1', hostname: 'SW-1', vendor: 'Cisco', model: 'C9300', device_type: 'switch', confidence: 5, open_ports: [161], snmp_community: '', snmp_identified: true, interfaces: [], site: '', vlan_90: null },
  { id: 2, ip: '10.0.1.2', hostname: 'SW-2', vendor: 'Cisco', model: 'C9300', device_type: 'switch', confidence: 5, open_ports: [161], snmp_community: '', snmp_identified: true, interfaces: [], site: '', vlan_90: null },
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
      return authed ? json(200, { username: 'admin', role: 'admin' }) : json(401, { detail: 'x' })
    }
    if (url.includes('/api/inventory/devices')) {
      return json(200, { devices: DEVICES, links: [] })
    }
    if (url.includes('/api/inventory/links')) return json(200, [])
    if (url.includes('/api/inventory/collect-config')) {
      return json(200, { total: 2, success: 2, failed: 0, results: [] })
    }
    if (url.includes('/api/backfill/interfaces')) {
      return json(200, { total: 2, successful: 2, failed: 0, interfaces_walked: 10, persisted_interfaces: 10, sample_errors: [], results: [] })
    }
    if (url.includes('/api/inventory/bulk-set-site')) {
      return json(200, { updated: 2, total: 2 })
    }
    return json(200, {})
  })
}

test('bulk selection runs bulk operations', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByLabel('Username', { exact: true }).fill('admin')
  await page.getByLabel('Password', { exact: true }).fill('admin')
  await page.getByRole('button', { name: /sign in/i }).click()

  await page.goto('/inventory')
  const cb1 = page.getByLabel('Select 10.0.1.1')
  const cb2 = page.getByLabel('Select 10.0.1.2')
  await cb1.check()
  await cb2.check()

  await expect(page.getByText('2 selected', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Collect configs', exact: true }).click()
  await expect(page.getByText(/Configs collected: 2 ok/).first()).toBeVisible()

  await cb1.check()
  page.on('dialog', (d) => d.accept('Chicago'))
  await page.getByRole('button', { name: 'Assign site', exact: true }).click()
  await expect(page.getByText(/Site assigned on 2 devices/).first()).toBeVisible({ timeout: 5000 })
})