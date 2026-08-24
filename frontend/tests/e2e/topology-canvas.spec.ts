import { test, expect } from '@playwright/test'

const NODES = Array.from({ length: 40 }, (_, i) => ({
  id: `10.0.0.${i + 1}`,
  ip: `10.0.0.${i + 1}`,
  hostname: `SW${i + 1}`,
  vendor: 'Cisco',
  model: 'C9300',
  device_type: i % 5 === 0 ? 'core-switch' : 'switch',
  status: i % 9 === 0 ? 'down' : 'up',
  spof: i === 1,
  vlan_90: i % 7 === 0,
}))
const LINKS = NODES.slice(1).map((n, i) => ({
  source: NODES[0].id,
  target: n.id,
  source_interface: 'Gi1/0/1',
  target_interface: 'Gi1/0/2',
  protocol: 'catalyst',
  source_hostname: NODES[0].hostname,
  target_hostname: n.hostname,
  status: 'up',
}))

function mockApi(page: import('@playwright/test').Page, authed = false) {
  return page.route('**/api/**', (route) => {
    const url = route.request().url()
    const method = route.request().method()
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (url.includes('/api/auth/me')) {
      return authed ? json(200, { username: 'admin', role: 'admin' }) : json(401, { detail: 'unauthenticated' })
    }
    if (url.includes('/api/auth/login') && method === 'POST') {
      return json(200, { token: 'test-token', token_type: 'bearer', username: 'admin', role: 'admin' })
    }
    if (url.includes('/api/topology/summary')) {
      return json(200, { groups: [] })
    }
    if (url.includes('/api/topology')) {
      return json(200, { scan_id: 's1', nodes: NODES, links: LINKS, scan_meta: { subnet: 'Test', device_count: NODES.length, started_at: null, scan_kind: 'catalyst' } })
    }
    if (url.includes('/api/inventory/devices')) {
      return json(200, { devices: [] })
    }
    if (url.includes('/api/inventory/scans')) {
      return json(200, { scans: [] })
    }
    return json(200, {})
  })
}

test('canvas topology mode renders and toggles', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByLabel('Username', { exact: true }).fill('admin')
  await page.getByLabel('Password', { exact: true }).fill('admin')
  await page.getByRole('button', { name: /sign in/i }).click()

  // Switch to the detailed (Technical) view where the Canvas toggle lives.
  await page.getByText('Technical', { exact: true }).click()
  const standard = page.getByRole('button', { name: 'Standard', exact: true })
  const canvas = page.getByRole('button', { name: 'Canvas', exact: true })
  await expect(canvas).toBeVisible()

  await canvas.click()
  await expect(page.locator('canvas').first()).toBeVisible()

  await standard.click()
  await expect(canvas).not.toHaveClass(/bg-purple-600/)

  await canvas.click()
  await expect(page.locator('canvas').first()).toBeVisible()
})