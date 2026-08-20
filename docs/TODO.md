# TODO — 挂起事项清单

> 维护说明：完成一项后把状态改为 `done` 并补一行处置说明；新增事项按格式追加。
> 相关规范见 `.cursorrules` 与 `docs/frontend-coding-standards.md`（治理清单/例外）。

---

## 前端（当前阶段挂起）

### F1. 选项式 `defineProps` 批量泛型化
- **状态**：pending
- **范围**：`frontend/src` 下 40+ 处选项式 `defineProps({ ... })`（约 47 个组件）
- **目标**：迁移为 `defineProps<{...}>()` + `withDefaults()`，对齐规范 Rule 3 默认写法
- **风险**：中 —— 模板绑定/类型推断可能连锁；建议按组件分多批 PR，每批 vue-tsc 0 错 + vitest + build 全绿
- **备注**：带运行时校验（validator/PropType）的组件可保留选项式（已接受变体）；"触碰时顺手迁移"亦可

### F2. 超长模板 view 拆分
- **状态**：pending
- **范围**：6 个模板超 100 行的视图
  - `views/Settings.vue`（192 行）
  - `views/AccountManagement.vue`（132 行）
  - `views/Feedback.vue`（131 行）
  - `views/PublishHistoryDetail.vue`（129 行）
  - `views/Sponsor.vue`（117 行）
  - `views/PublishHistory.vue`（104 行）
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
