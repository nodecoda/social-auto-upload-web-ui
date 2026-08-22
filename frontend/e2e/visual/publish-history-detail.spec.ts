import { test, expect } from '@playwright/test'

/** 发布历史详情页视觉基线 —— mock 账号 + 批次详情（V2 扩展） */

// /getAccounts: AccountRow 元组（同 V1）
const ACCOUNTS = [
  [1, 3, 'cookies/douyin_1.json', '抖音测试号', 1, '', 12345, 678, 90,
    JSON.stringify([{ ICON: 'user', COUNT: '1.2万', NAME: '粉丝', SORT: 1 }]),
    [{ id: 1, name: '美食', color: '#f56c6c' }]],
  [2, 5, 'cookies/bili_1.json', 'B站测试号', 0, '', 998, 200, 33,
    JSON.stringify([]), []],
]

const BATCH = {
  id: 'b-1001', type: 'video', title: '桂林山水延时摄影 4K',
  description: '延时摄影精选片段合集', cover_url: '',
  status: 'success', created_at: '2026-08-22 10:00:00',
  items: [
    {
      id: 'd-1', account_id: 1, account_name: '抖音测试号', platform: '抖音',
      status: 'success', created_at: '2026-08-22 10:00:00',
      publish_url: 'https://www.douyin.com/video/1', error_message: '',
      account_configs: { title: '桂林山水延时摄影 4K' },
    },
    {
      id: 'd-2', account_id: 2, account_name: 'B站测试号', platform: '哔哩哔哩',
      status: 'success', created_at: '2026-08-22 10:01:00',
      publish_url: 'https://www.bilibili.com/video/2', error_message: '',
      account_configs: { title: '桂林山水延时摄影 4K' },
    },
  ],
}

test('发布历史详情页视觉基线', async ({ page }) => {
  await page.route('**/getAccounts', route =>
    route.fulfill({ json: { code: 200, msg: null, data: ACCOUNTS } }))
  await page.route('**/getValidAccounts', route =>
    route.fulfill({ json: { code: 200, msg: null, data: ACCOUNTS } }))
  await page.route('**/api/tags', route =>
    route.fulfill({ json: { code: 200, msg: null, data: [] } }))
  await page.route('**/api/v2/history/b-1001*', route =>
    route.fulfill({ json: { code: 200, msg: null, data: BATCH } }))

  await page.goto('/#/publish-history/b-1001')
  await expect(page.getByText('桂林山水延时摄影 4K').first()).toBeVisible()
  await expect(page.getByText('数据统计')).toBeVisible()
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400)

  await expect(page).toHaveScreenshot('publish-history-detail.png')
})
