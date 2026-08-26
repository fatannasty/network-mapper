import { test } from '@playwright/test'

test('capture login backgrounds', async ({ page }) => {
  await page.route('**/api/**', (route) => route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"x"}' }))
  // Light
  await page.goto('/')
  await page.waitForTimeout(1200)
  await page.screenshot({ path: '/tmp/login-light.png' })
  // Dark
  await page.evaluate(() => { localStorage.setItem('app-theme', 'dark'); document.documentElement.classList.add('dark') })
  await page.waitForTimeout(800)
  await page.screenshot({ path: '/tmp/login-dark.png' })
})
