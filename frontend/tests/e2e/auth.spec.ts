import { test, expect } from '@playwright/test'

// The backend is mocked via route interception, so this runs without a live
// API and is safe in CI. It guards the auth flow end-to-end (including the
// StrictMode double-invoke reload loop that previously flickered on login).

function mockUnauthenticated(page: import('@playwright/test').Page) {
  return page.route('**/api/**', (route) => {
    const url = route.request().url()
    if (url.includes('/api/auth/me')) {
      return route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"unauthenticated"}' })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
}

test('shows the login form when unauthenticated (no reload loop)', async ({ page }) => {
  await mockUnauthenticated(page)
  await page.goto('/')
  await expect(page.getByLabel('Username')).toBeVisible()
  // A reload loop (the prior flicker bug) would re-navigate and drop the form.
  await page.waitForTimeout(1500)
  await expect(page.getByLabel('Username')).toBeVisible()
})

test('can log in and reach the topology', async ({ page }) => {
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    const method = route.request().method()
    if (url.includes('/api/auth/me')) {
      return route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"unauthenticated"}' })
    }
    if (url.includes('/api/auth/login') && method === 'POST') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"token":"test-token","token_type":"bearer","username":"admin","role":"admin"}' })
    }
    if (url.includes('/api/topology')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"scan_id":null,"nodes":[],"links":[],"scan_meta":null}' })
    }
    if (url.includes('/api/inventory/devices')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"devices":[]}' })
    }
    if (url.includes('/api/inventory/scans')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"scans":[]}' })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/')
  await page.getByLabel('Username', { exact: true }).fill('admin')
  await page.getByLabel('Password', { exact: true }).fill('admin')
  await page.getByRole('button', { name: /sign in/i }).click()

  await expect(page.getByText('Network Topology')).toBeVisible({ timeout: 10_000 })
})
