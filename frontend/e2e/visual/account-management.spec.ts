import { test, expect } from '@playwright/test'

/** 账号管理页视觉基线 —— mock 后端数据保证截图可复现（不依赖真实 DB/浏览器自动化） */

// 后端 /getAccounts 返回 user_info 行: [id, type, filePath, userName, status, avatar, fans, likes, follows, stats, tags]
const ACCOUNTS = [
  [1, 3, 'cookies/douyin_1.json', '抖音测试号', 1, '', 12345, 678, 90,
    JSON.stringify([{ ICON: 'user', COUNT: '1.2万', NAME: '粉丝', SORT: 1 }]),
    [{ id: 1, name: '美食', color: '#f56c6c' }]],
  [2, 5, 'cookies/bili_1.json', 'B站测试号', 0, '', 998, 200, 33,
    JSON.stringify([]), []],
]

const TAGS = [
  { id: 1, name: '美食', color: '#f56c6c' },
  { id: 2, name: '科技', color: '#409eff' },
]

test('账号管理页视觉基线', async ({ page }) => {
  await page.route('**/getAccounts', route =>
    route.fulfill({ json: { code: 200, msg: null, data: ACCOUNTS } }))
  await page.route('**/getValidAccounts', route =>
    route.fulfill({ json: { code: 200, msg: null, data: ACCOUNTS } }))
  await page.route('**/api/tags', route =>
    route.fulfill({ json: { code: 200, msg: null, data: TAGS } }))
  // 逐账号标签查询与批量操作一律空响应（避免意外 404/500 打断渲染）
  await page.route('**/api/accounts/**/tags', route =>
    route.fulfill({ json: { code: 200, msg: null, data: [] } }))

  await page.goto('/#/account-management')
  // 等待账号卡片渲染（以 mock 账号名出现为准）
  await expect(page.getByText('抖音测试号')).toBeVisible()
  await expect(page.getByText('B站测试号')).toBeVisible()
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400) // 等 Element Plus 过渡动画/图标稳定

  await expect(page).toHaveScreenshot('account-management.png')
})
