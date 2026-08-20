# TODO — 挂起事项清单

> 维护说明：完成一项后把状态改为 `done` 并补一行处置说明；新增事项按格式追加。
> 相关规范见 `.cursorrules` 与 `docs/frontend-coding-standards.md`（治理清单/例外）。

---

## 前端（当前阶段挂起）

### F1. 选项式 `defineProps` 批量泛型化
- **状态**：done（2026-08-21）
- **处置**：三批 PR 完成（#76 F1a 17 个 / #77 F1b 12 个 Select / #78 F1c 18 个），全仓 47 处选项式 → 0
- **额外收益**：validator 枚举（AccountSidebar mode、CompilationSelect platform 等 5 处）转字面量联合；顺带清理 40+ 处 unused `PropType` import；SettingsFieldsRenderer/AccountSidebar.test 连锁类型修复
- **验证**：vue-tsc 0 错 / vitest 261 / vite build 全绿

### F2. 超长模板 view 拆分
- **状态**：✅ 完成（6/6）
- **范围**：6 个模板超 100 行的视图
  - ✅ `views/Feedback.vue`（131→95 行，PR #80：FeedbackCard / FeedbackSubmitDialog / feedbackShared）
  - ✅ `views/PublishHistory.vue`（104→67 行，PR #79）
  - ✅ `views/Sponsor.vue`（119→96 行，PR #81：SponsorQrCard）
  - ✅ `views/PublishHistoryDetail.vue`（131→80 行，PR #82：DetailAccountHeader / BatchMetaCard / publishHistoryShared）
  - ✅ `views/Settings.vue`（192→95 行，PR #83：ProxySettingsCard / PublishSettingsCard / BlacklistCard）
  - ✅ `views/AccountManagement.vue`（479→133 行，PR #84 + #85：AccountCard / accountCardShared / ImportAccountDialog）
- **目标**：拆子组件至模板 ≤100 行，对齐规范 Rule 7
- **回归测试**：✅ 已补齐（PR #86 纯函数 37 + PR #87 卡片组件 28 + PR #89 残余组件 24 用例 + El 交互 stubs），F2 全部拆分产物均有组件级用例锁定
- **风险**：低 —— 仅剩视觉/截图回归无基线（playwright 未引入）；如后续引入可一并补

### F3. 唯一 `any` 边界消除（SettingFieldControl `modelValue`）
- **状态**：done（2026-08-21）
- **处置**：PR #88 —— 新增 `src/types/settings-field.ts` 判别联合（10 种 type）+ `SettingsFieldValue` 多形态值；3 处重复接口收敛；platforms.ts 19 处 settingsFields 注解受检
- **验证**：vue-tsc 0 错 / vitest 326 / vite build 绿；业务代码 `: any` **128 → 0**

---

## 历史（已完成的收尾里程碑，勿重复排期）

- ✅ 前端 js→ts 迁移（src 下 `.js` = 0，strict）
- ✅ 业务代码 `any` 128 → 0（ts 收尾批 1-13 → F3 判别联合 PR #88）
- ✅ 规范落盘（.cursorrules + docs/frontend-coding-standards.md）
- ✅ 治理轮 G1：错误处理收敛 / composable 显式返回类型
- ✅ 治理轮 G2：规范更新 + 治理报告
- ✅ 验证基线：vue-tsc 0 错 / vitest 326 用例 / vite build
- ✅ 回归测试基线（2026-08-21）：F2 拆分组件纯函数（PR #86，37）+ 组件级（PR #87，28 + PR #89，24），vitest 326 → 350 用例
