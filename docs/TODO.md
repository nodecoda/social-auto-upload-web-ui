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
- **状态**：进行中（2/6 完成）
- **范围**：6 个模板超 100 行的视图
  - ✅ `views/Feedback.vue`（131→95 行，PR #79 + #80：FeedbackCard / FeedbackSubmitDialog / feedbackShared）
  - ✅ `views/PublishHistory.vue`（104→67 行，PR #79）
  - ⬜ `views/Settings.vue`（192 行）
  - ⬜ `views/AccountManagement.vue`（132 行）
  - ⬜ `views/PublishHistoryDetail.vue`（129 行）
  - ⬜ `views/Sponsor.vue`（117 行）
- **目标**：拆子组件至模板 ≤100 行，对齐规范 Rule 7
- **风险**：高 —— 无视觉回归测试，建议触碰该视图时顺手拆，或引入组件级测试后处理

### F3. 唯一 `any` 边界消除（SettingFieldControl `modelValue`）
- **状态**：pending（有意保留）
- **范围**：`src/components/SettingFieldControl.vue` 的 `modelValue: any`（5 种字段类型多态）
- **目标**：改为判别联合（discriminated union）按 `field.type` 收窄
- **风险**：低-中；**ROI 低** —— 收益仅是消灭最后 1 处 any，改动面包含动态表单渲染
- **备注**：规范 Rule 9 已记录为有意保留边界；若未来重构 SettingFieldControl 可一并处理

---

## 历史（已完成的收尾里程碑，勿重复排期）

- ✅ 前端 js→ts 迁移（src 下 `.js` = 0，strict）
- ✅ 业务代码 `any` 128 → 1（ts 收尾批 1-13）
- ✅ 规范落盘（.cursorrules + docs/frontend-coding-standards.md）
- ✅ 治理轮 G1：错误处理收敛 / composable 显式返回类型
- ✅ 治理轮 G2：规范更新 + 治理报告
- ✅ 验证基线：vue-tsc 0 错 / vitest 261 用例 / vite build
