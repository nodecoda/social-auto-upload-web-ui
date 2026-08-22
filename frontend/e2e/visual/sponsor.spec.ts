import { test, expect } from '@playwright/test'

/** 赞助页视觉基线 —— 纯静态页，无需 mock（V2 扩展） */

test('赞助页视觉基线', async ({ page }) => {
  await page.goto('/#/sponsor')
  await expect(page.getByText('支持一个')).toBeVisible()
  await expect(page.getByText('免费工具')).toBeVisible()
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400)

  await expect(page).toHaveScreenshot('sponsor.png')
})
