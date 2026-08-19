import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      include: ['src/**'],
      exclude: ['src/sql.js.d.ts', '**/*.test.ts', '**/tests/**'],
      reporter: ['text', 'text-summary'],
      // 基线 58.25% (2026-08-20 实测) → 按计划设 30% 地板，保留扩展裕量
      thresholds: {
        lines: 30,
      },
    },
  },
});
