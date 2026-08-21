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

### V1. Playwright 视觉基线（账号管理页闭环）— ✅ done（2026-08-21，PR #95）
- @playwright/test + playwright.config.ts（vite dev server + route mock 后端数据 + 固定 viewport/禁用动画/1% 阈值）
- e2e/visual/account-management.spec.ts：基线经人工审核入库（e2e/__snapshots__）
- npm scripts：test:visual / test:visual:update；CI 新增 frontend-visual job（48s 通过，失败上传 diff artifact）
- 检测能力实测：sidebar 突变触发失败；单行文案 <1% 阈值属预期
- **V2 待做**：覆盖 F2 其余 5 视图（Feedback/PublishHistory/Sponsor/PublishHistoryDetail/Settings）；若 CI 字体差异误报则装字体或调阈值

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

### B2. 反馈 + image-proxy — ✅ done（2026-08-21，PR #91）
- `blueprints/feedback_bp.py`：反馈 3 路由（list/submit/vote）+ 4 helper（`_feedback_configured` / `_feedback_sign` / `_feedback_headers` / `_get_feedback_email`）随迁；FEEDBACK_* 常量在 conf
- `blueprints/image_proxy_bp.py`：/api/image-proxy（头像防盗链代理）
- app.py 清理迁移死 import（time/_requests/Response/FEEDBACK_API_*/read_settings）
- 验证：401 passed / 3 skipped；ruff 无净增（RUF013×2 随 _feedback_sign 平移）

### B3. 发布域 — ✅ done（2026-08-21，PR #92）
- `blueprints/publish_bp.py`：postVideo / postVideo/status / postVideoBatch + `_validate_publish_video` / `_enqueue_publish` / `_finish_publish_failed` / `_resolve_material_path` / `_resolve_video_format_from_db`
- `services/publish_history.py`：`_record_publish` / `_update_publish_result`（app.py 钩子与发布 job 共用，避免循环导入）
- `_before_publish/_after_publish` 钩子与 g.publish_detail_id 机制保留在 app.py（conftest 钩子兼容）
- 验证：401 passed / 3 skipped；ruff 无新增（app.py E402 存量 7→4）

### B4. 静态页 / api/health / 启动段 — ✅ done（2026-08-21，按计划保留装配层）
- 静态页 / api/health / `_check_all_accounts` / threads=16 启动段按计划保留在 app.py
- app.py 终态 470 行 = 纯装配层（注册 20 个蓝图 + 钩子 + 静态页 + health + 启动）
- 全仓残留 `from app import` 仅 3 处 `_get_db_path`（合法保留）

### N1. blueprints 一致性 + lint 纯垃圾清理 — ✅ done（2026-08-21，PR #93）
- jd_bp 导出名统一（bp → jd_bp）；B007×2 / RUF059×5 / E741×1 未用变量清零
- 验证：401 passed / 3 skipped

### N2. API 参考文档 — ✅ done（2026-08-21，PR #94）
- `backend/scripts/gen_api_docs.py` 从 Flask 路由表自动生成 `docs/api-reference.md`（116 条路由、按域分组、标注前端 api 层）
- 补齐 39 条路由 docstring，待补清单清零；路由变更后重跑脚本刷新

### T1-T3b. 路由层契约测试补强 — ✅ done（2026-08-21，PR #96-99）
- T1 jd/taobao picker 路由契约（PR #96，32 用例）：jd 23→82%、taobao 22→76%
- T2 materials 路由契约（PR #97，18 用例）：material 24→72%
- T3a 平台薄代理契约（PR #98，41+7skip）：8 个 bp 9-19%→22-36%
- T3b 图片发布域代理契约（PR #99，39+2skip）：douyin_image_bp 0→49%、kuaishou_image_bp 0→20%
- 关键契约沉淀：业务错误 = HTTP 4xx/5xx + body.code（部分域例外需实测）；统一路径 = cookie 404 → run_async 成功 200 / 失败 500
- 全量：492→531 passed；总覆盖率 21.8%→23.0%（CI 门槛 19%）
- T4 账号管理域业务路由契约（PR #100，39 用例）：account_bp 39%→87%；顺带修 conftest 缺 `migrate_database()`（测试库与生产启动对齐，stats 列）；全量 570 passed
- T5 图片发布域业务路由契约（PR #101，26 用例）：image_publish_bp 44%→74%（纯函数 helper + save/delete draft + execute-publish 校验）；钉扎 ipb.DB_PATH 到 conftest 会话库，屏蔽收集顺序污染；全量 596 passed
- T6 残余契约收尾（PR #102，32 用例）：image_proxy_bp 47%→100%、uploads_bp 85%→94%、publish_bp 55%→65%（含 _enqueue_publish job 全路径）；全量 628 passed
- CI 门槛锁定（PR #103）：cov-fail-under 19%→22%，锁住 T1-T6 测试批次成果
- T7 浏览器 helper 深度测试（PR #104，13 用例）：fake Playwright page 驱动 douyin/kuaishou 音乐搜索
  全流程，kuaishou_image_bp 20%→82%、douyin_image_bp 49%→76%；全量 641 passed；方案已验证可行，
  可扩展到 alipay/xiaohongshu/channels 等同构 helper（ROI #2 下一批）
