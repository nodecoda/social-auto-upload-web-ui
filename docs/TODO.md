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

---

## 后端（域重构/路由迁移，进行中）

> 目标：app.py 瘦身（1520 → 装配层），路由按域拆入 `blueprints/`，行为等价、前端无感知。
> 迁移纪律：路由路径/响应/SSE 协议不变；每批一个 PR，全量 pytest 绿 + ruff 无新增才合并。

### B1. 账号管理域（P1）— ✅ done（2026-08-21，PR #90）
- 7 路由迁入 `blueprints/account_bp.py`：checkAccount / syncProfile / openCreatorCenter / login / platforms/import-supported / importAccount / importAccount/stream
- 同步迁出 `sse_stream` / `_is_terminal_login_sse_message` / `_get_account_record`
- PLATFORM_MAP / PLATFORM_ID_TO_KEY → `conf.py`（ext_api / draft_merge / tests 改从 conf 导入）
- 验证：pytest 401 passed / 3 skipped；ruff 无新增（3 处 I001 顺带消除）；app.py 1520→1171 行

### B2. 反馈 + image-proxy（PR-2，待做）
- `blueprints/feedback_bp.py`：反馈 3 路由 + helper（`_feedback_configured` / `_feedback_headers` / `_get_feedback_email`）随迁；FEEDBACK_* 常量已在 conf
- 画像：反馈 API 透传，无 DB

### B3. 发布域（PR-3，待做）
- `blueprints/publish_bp.py`：postVideo / postVideo/status / postVideoBatch + `_validate_publish_video` / `_enqueue_publish` / `_finish_publish_failed`
- 注意：`_resolve_material_path` / `_resolve_video_format_from_db` 仍在 app.py 被引用 → 共享放 util/；`_before_publish/_after_publish` 的 g.publish_detail_id 机制（conftest 钩子保留）

### B4. 静态页 / api/health / 启动段（PR-4，待做）
- 建议保留在 app.py（装配层）：`_check_all_accounts` / threads=16 启动逻辑属于 app 装配
