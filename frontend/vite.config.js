import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        // 移除自动导入，改用@use语法
      }
    }
  },
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/login': {
        target: 'http://localhost:5409',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/upload': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/uploadSave': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/getFiles': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/getFile': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/deleteFile': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/getAccounts': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/getValidAccounts': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/deleteAccount': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/postVideo': {
        target: 'http://localhost:5409',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/postVideoBatch': {
        target: 'http://localhost:5409',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/updateUserinfo': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/uploadCookie': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/downloadCookie': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/syncProfile': {
        target: 'http://localhost:5409',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/openCreatorCenter': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/checkAccount': {
        target: 'http://localhost:5409',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      // cookie 字符串导入账号（BasePlatform.import_cookie）
      '/importAccount': {
        target: 'http://localhost:5409',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
      '/platforms': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:5409',
        changeOrigin: true,
      },
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.js'],
    coverage: {
      provider: 'v8',
      include: [
        'src/stores/**',
        'src/composables/**',
        'src/components/AccountSidebar.vue',
        'src/components/BatchSetDialog.vue',
        'src/components/OneClickFillDialog.vue',
        'src/components/PublishStats.vue',
      ],
      // 门槛按实测基线留裕量（stores 99.4% / composables 85.8% / 4 组件 90-100% / include 作用域 94.3%）
      // 红 CI 只反映真实回退；Phase 4 迁移时随覆盖增长再抬升
      thresholds: {
        lines: 80,
        'src/stores/**': { lines: 60 },
        'src/composables/**': { lines: 60 },
        'src/components/AccountSidebar.vue': { lines: 55 },
        'src/components/BatchSetDialog.vue': { lines: 55 },
        'src/components/OneClickFillDialog.vue': { lines: 55 },
        'src/components/PublishStats.vue': { lines: 55 },
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          elementPlus: ['element-plus'],
          utils: ['axios']
        }
      }
    }
  }
})
