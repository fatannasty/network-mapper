import { test, expect } from '@playwright/test'

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
    if (url.includes('/api/health/exec')) {
      return json(200, {
        total_devices: 120, state: 'warning', score: 72,
        kpis: { total_devices: 120, devices_up: 100, devices_down: 5, devices_degraded: 3, devices_flapping: 2, devices_unknown: 10, spof_count: 7, vlan90_count: 4, stale_devices: 1, up_pct: 85.8, config_coverage: 88, site_coverage: 92, interface_coverage: 95, link_validation: 70 },
        sites: [{ site: 'Chicago', devices: 60, up: 55, down: 2, degraded: 1, flapping: 1, unknown: 1, freshness_days: 0 }, { site: 'Denver', devices: 40, up: 40, down: 0, degraded: 0, flapping: 0, unknown: 0, freshness_days: 12 }],
        risks: [{ ip: '10.0.0.9', hostname: 'SW-DOWN', site: 'Chicago', status: 'down' }],
        spof_devices: [{ ip: '10.0.0.1', hostname: 'CORE-1', site: 'Chicago' }],
      })
    }
    if (url.includes('/api/inventory/report')) {
      return json(200, {
        total_devices: 120, total_links: 30, total_interfaces: 400,
        by_device_type: {}, by_vendor: {}, by_site: {}, link_protocols: {},
        interface_status: {}, config_coverage: {}, stale_devices_90d: 0,
        dod_gates: {}, scan_history: [], recent_scans: [],
      })
    }
    return json(200, {})
  })
}

test('executive dashboard renders scorecard and risks', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByLabel('Username', { exact: true }).fill('admin')
  await page.getByLabel('Password', { exact: true }).fill('admin')
  await page.getByRole('button', { name: /sign in/i }).click()

  await page.goto('/dashboard')
  await page.getByText('Executive', { exact: true }).click()
  await expect(page.getByText('Needs review', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Health score', { exact: true })).toBeVisible()
  await expect(page.getByText('Site freshness', { exact: true })).toBeVisible()
  await expect(page.getByText('Risks & issues', { exact: true })).toBeVisible()
  await expect(page.getByText('SW-DOWN', { exact: true })).toBeVisible()
  await expect(page.getByText('Single points of failure', { exact: true })).toBeVisible()
})