import { test, expect } from '@playwright/test'

/** 系统设置页视觉基线 —— mock 设置数据 + 系统信息（V2 扩展） */

// /api/v2/settings: data = SettingsData
// /api/system-info: data = { version, cache }
const SETTINGS = {
  proxyUrl: 'http://127.0.0.1:10809',
  autoFillTitle: true,
  autoSaveDraft: true,
  autoSaveInterval: 30,
  accountCheckMode: 'auto',
  storage: { maxAccountFiles: 50 },
  feedbackEmail: 'dev@example.com',
  disabledPlatforms: [],
}

const SYSTEM_INFO = { version: 'v1.0.0', cache: { size: 123456, count: 12 } }

test('系统设置页视觉基线', async ({ page }) => {
  await page.route('**/api/v2/settings*', route =>
    route.fulfill({ json: { code: 200, msg: null, data: SETTINGS } }))
  await page.route('**/api/system-info', route =>
    route.fulfill({ json: { code: 200, msg: null, data: SYSTEM_INFO } }))

  await page.goto('/#/settings')
  await expect(page.getByRole('heading', { name: '系统设置' })).toBeVisible()
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400)

  await expect(page).toHaveScreenshot('settings.png')
})
