import { test, expect } from '@playwright/test'

/** 一键反馈页视觉基线 —— mock 反馈列表（V2 扩展） */

// /api/feedback/list: data = { list: FeedbackItem[], total }
const FEEDBACK_LIST = [
  {
    id: 1, status: 1, content: '视频发布功能很好用，希望支持更多平台！',
    email: 'user@example.com', created_at: '2026-08-20 14:30:00', vote_count: 3,
  },
  {
    id: 2, status: 0, content: '账号导入时提示 cookie 过期，建议加个检测按钮。',
    email: 'dev@example.com', created_at: '2026-08-19 09:00:00', vote_count: 0,
  },
]

test('一键反馈页视觉基线', async ({ page }) => {
  // 预注入邮箱：onMounted 无邮箱会弹对话框阻塞 loadList
  await page.addInitScript(() => {
    localStorage.setItem('global_user_email', 'e2e@example.com')
  })
  await page.route('**/api/feedback/list*', route =>
    route.fulfill({ json: { code: 200, msg: null, data: { list: FEEDBACK_LIST, total: 2 } } }))

  await page.goto('/#/feedback')
  await expect(page.getByRole('heading', { name: '一键反馈' })).toBeVisible()
  await expect(page.getByText('视频发布功能很好用，希望支持更多平台！')).toBeVisible()
  await expect(page.getByText('账号导入时提示 cookie 过期，建议加个检测按钮。')).toBeVisible()
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400)

  await expect(page).toHaveScreenshot('feedback.png')
})
