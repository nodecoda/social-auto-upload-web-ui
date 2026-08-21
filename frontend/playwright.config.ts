import { defineConfig } from '@playwright/test'

/**
 * 视觉基线（Visual Baseline）配置。
 * 思路见 docs/playwright-visual-baseline.md：
 * - 真实 Chromium + 真实 dev server（vite）
 * - 后端数据用 page.route() mock，保证截图可复现
 * - 固定 viewport / locale / 禁用动画，降低环境敏感度
 * - 有意改样式时 `npx playwright test --update-snapshots` 换基线
 */
export default defineConfig({
  testDir: './e2e',
  snapshotDir: './e2e/__snapshots__',
  fullyParallel: true,
  timeout: 90_000,
  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01, // 允许 1% 像素差异（抗锯齿/亚像素抖动）
      animations: 'disabled',
    },
  },
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    colorScheme: 'light',
  },
  webServer: {
    // BROWSER=none: 禁用 vite 的自动打开浏览器（server.open: true 只服务开发者）
    command: 'BROWSER=none npm run dev -- --port 5173 --strictPort',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  reporter: process.env.CI ? [['html', { open: 'never' }], ['list']] : 'list',
})
