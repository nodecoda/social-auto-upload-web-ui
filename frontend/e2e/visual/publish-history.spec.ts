import { test, expect } from '@playwright/test'

/** 发布历史页视觉基线 —— mock 后端数据保证截图可复现（V2 扩展） */

// /api/v2/history: data.items = HistoryBatch[]（id/type/title/status/items[]）
// /api/v2/stats:    data = { total, successRate, monthlyTotal, tasks }
const BATCHES = [
  {
    id: 'b-1001', type: 'video', title: '桂林山水延时摄影 4K', status: 'success',
    created_at: '2026-08-22 10:00:00',
    items: [
      { id: 'd-1', account_id: 1, account_name: '抖音测试号', platform: '抖音', status: 'success' },
      { id: 'd-2', account_id: 2, account_name: 'B站测试号', platform: '哔哩哔哩', status: 'success' },
    ],
  },
  {
    id: 'b-1002', type: 'image', title: '夏日甜品九宫格', status: 'failed',
    created_at: '2026-08-22 09:00:00',
    items: [
      { id: 'd-3', account_id: 1, account_name: '抖音测试号', platform: '抖音', status: 'failed' },
    ],
  },
]

const STATS = { total: 2, successRate: 50, monthlyTotal: 2, tasks: { total: 2, successRate: 50 } }

test('发布历史页视觉基线', async ({ page }) => {
  await page.route('**/api/v2/history*', route =>
    route.fulfill({ json: { code: 200, msg: null, data: { items: BATCHES, total: 2 } } }))
  await page.route('**/api/v2/stats', route =>
    route.fulfill({ json: { code: 200, msg: null, data: STATS } }))

  await page.goto('/#/publish-history')
  await expect(page.getByRole('heading', { name: '发布历史' })).toBeVisible()
  await expect(page.getByText('桂林山水延时摄影 4K')).toBeVisible()
  await expect(page.getByText('夏日甜品九宫格')).toBeVisible()
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400) // 等 Element Plus 过渡动画/图标稳定

  await expect(page).toHaveScreenshot('publish-history.png')
})
