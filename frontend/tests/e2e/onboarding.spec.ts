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
      return authed ? json(200, { username: 'admin', role: 'admin' }) : json(401, { detail: 'x' })
    }
    if (url.includes('/api/topology')) {
      return json(200, { scan_id: null, nodes: [], links: [], scan_meta: null })
    }
    return json(200, {})
  })
}

test('help tour and glossary open from the sidebar', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByLabel('Username', { exact: true }).fill('admin')
  await page.getByLabel('Password', { exact: true }).fill('admin')
  await page.getByRole('button', { name: /sign in/i }).click()

  // Wait for the post-login navigation to settle before interacting.
  await expect(page.getByText('Network Topology')).toBeVisible({ timeout: 10000 })

  // Open Help from the sidebar.
  await page.getByRole('button', { name: 'Help', exact: true }).click()

  // Tour step 1.
  await expect(page.getByText('Welcome', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page.getByText('Bring your network in', { exact: true })).toBeVisible()

  // Glossary tab.
  await page.getByRole('button', { name: 'Glossary', exact: true }).click()
  await expect(page.getByText('Plain-language glossary', { exact: true })).toBeVisible()
  await expect(page.getByText('SPOF (Single Point of Failure)', { exact: true })).toBeVisible()
  await expect(page.getByText('Flapping', { exact: true })).toBeVisible()

  // Close marks the tour as seen.
  await page.getByRole('button', { name: 'Got it', exact: true }).click()
  await expect(page.getByText('Plain-language glossary', { exact: true })).toHaveCount(0)
})