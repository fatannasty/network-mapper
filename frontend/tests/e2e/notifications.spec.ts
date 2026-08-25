import { test, expect } from '@playwright/test'

function mockApi(page: import('@playwright/test').Page) {
  let authed = false
  let seenIds = new Set<number>()
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
    if (url.includes('/api/notifications') && method === 'POST') {
      const id = Number(url.match(/\/api\/notifications\/(\d+)\/seen/)?.[1] ?? 0)
      if (id) seenIds.add(id)
      return json(200, { seen: true })
    }
    if (url.includes('/api/notifications')) {
      const now = new Date().toISOString()
      const all = [
        { id: 1, created_at: now, kind: 'flapping', severity: 'warning', title: 'Flapping: SW-1', message: 'SW-1 (10.0.0.1) is flapping', device_ip: '10.0.0.1', seen: seenIds.has(1), emailed: false },
        { id: 2, created_at: now, kind: 'down', severity: 'critical', title: 'Device down: SW-2', message: 'SW-2 (10.0.0.2) is unreachable', device_ip: '10.0.0.2', seen: seenIds.has(2), emailed: false },
      ]
      const unseen = all.filter((n) => !n.seen).length
      return json(200, { unseen, notifications: all })
    }
    if (url.includes('/api/topology')) {
      return json(200, { scan_id: null, nodes: [], links: [], scan_meta: null })
    }
    return json(200, {})
  })
}

test('notification bell shows unread count and marks seen', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByLabel('Username', { exact: true }).fill('admin')
  await page.getByLabel('Password', { exact: true }).fill('admin')
  await page.getByRole('button', { name: /sign in/i }).click()

  const bell = page.getByLabel(/Notifications/)
  await expect(bell.getByText('2')).toBeVisible({ timeout: 10000 })

  await bell.click()
  await expect(page.getByText('Flapping: SW-1', { exact: true })).toBeVisible()
  await expect(page.getByText('Device down: SW-2', { exact: true })).toBeVisible()

  await page.getByText('Flapping: SW-1', { exact: true }).click()
  await expect(page.getByText('1', { exact: true })).toBeVisible()
})