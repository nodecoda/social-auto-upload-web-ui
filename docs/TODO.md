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
- T8a 渠道类合集/POI 浏览器 helper（PR #105，19 用例）：channels _fetch_collections 4 用例 + xiaohongshu
  _fetch_collections 8 用例 + _fetch_poi 7 用例；xiaohongshu_bp 23%→83%、channels_bp 24%→40%；全量 660 passed
- T8b 渠道搜索/支付宝音乐浏览器 helper（PR #106，24 用例）：channels _fetch_activities/_fetch_locations
  10 用例（点卡片→搜索框→等下拉>1→跳 index 0）+ alipay _search_compilation/_fetch_music_list 14 用例
  （空视频/测试图触发表单渲染→拦截 queryCompilationsByPublicId/queryAllMaterial→解析标准化）；
  channels_bp 40%→~75%、alipay_bp 22%→~70%；全量 684 passed、总覆盖率 26%→27%（CI 门槛 22%）
- T9 五平台浏览器 helper 契约测试（PR #107，29 用例）：toutiao _search_compilation(evaluate 直调接口)
  6 用例 → 36%→53%；weixin_gzh _fetch_collections(token 解析+tab+表格) 5 用例 → 27%→61%；
  bilibili _fetch_collections(frame 探测+合集浮层) 5 用例 → 25%→64%；vivo _fetch_positions(上传轮询+位置下拉)
  8 用例 → 26%→66%；weibo _fetch_collections(platform 上传补丁+合集开关+value 解析) 5 用例 → 26%→56%；
  全量 713 passed、总覆盖率 27%→29%（CI 门槛 22%，裕度 7pp）
- T10 CI 门槛锁定（PR #108）：cov-fail-under 22%→24%，锁住 T1-T9 测试批次成果
- T11 服务层单元测试（PR #109，74 用例）：ffmpeg_service 50 用例（stderr 解析/二进制发现三优先序/元数据读取/帧提取全链路，subprocess 全 mock，模块级状态每测重置）31%→93%；duration_repair 24 用例（并发锁/probe 写库/批量补全 ok-fail-skip 计数/提交兜底，fake conn 隔离 DB + resolve mock）48%→90%；全量 780 passed、总覆盖率 29%→30%（CI 门槛 24%）
- T12 frames 路由契约（PR #110，33 用例）：6 路由全路径（extract-frames 状态机 done/processing/404 业务态、frames-status、frames、frame-image send_file+参数校验、clear-cache 四类目标+日志保留期、system-info 版本+缓存统计）+ 4 helper（_resolve_video_path/_resolve_material_video local-s3/_download_s3_to_cache 缓存命中+下载）；routes/frames.py 9%→82%；全量 813 passed（CI 门槛 24%）
- T13 平台基类+发布参数纯函数（PR #111，47 用例）：base_platform 18 用例（浏览器四委托/import_cookie 4 步全路径：解析失败/空 cookies/INSERT/UPDATE/sync 三形态/失效清理/DB 异常）34%→94%；三平台纯函数 29 用例（抖音话题计数边界+≤5 校验/小红书同语义/百家号 emoji=3+标签≤10+字符≤50）；全量 860 passed、总覆盖率 30%→31%（CI 门槛 24%）
- T14 图片尺寸+存储路由小面（PR #112，18 用例）：image_service 4 用例 → 70%→100%（顺带修 loguru 风格 {} 占位残留，标准 logging emit 格式化异常）；storage 14 用例（配置脏数据兜底/get_storage 三分支/get_storage_by_type 四分支/resolve 兜底）→ 66%→100%；全量 878 passed（CI 门槛 24%）
- T15 平台发布编排层（PR #113，45 用例，主测试平台=微信公众号）：weixin_gzh 32 用例（纯函数 _extract_token/_build_home_url/_build_publish_datetime/_resolve_date_label/_parse_cookie_to_storage_state + 发布编排 publish_video/_upload_all 笛卡尔积/封面优先级 169>横版>竖版/enableTimer 驼峰透传 + evaluate 驱动轮询 token 解析/转码失败/超时/通知关闭）→ 14%→23%；douyin 13 用例（话题≤5 前置校验/发布策略 immediate|scheduled/文件×账号调度/参数透传/cookie 路径解析/浏览器异常冒泡）→ 7%→14%；全量 923 passed + 12 skipped、总覆盖率 31%→32%（CI 门槛 24%，裕度 8pp）
- T16a 平台发布编排层（PR #114，25 用例）：baijiahao 14 用例（前置校验 标签>10/字符>50/emoji×3→ValueError+日志、_upload_all 笛卡尔积/parse_schedule_time 按文件索引排期/169 封面+创作声明+补充声明+AI 内容透传/cookie 路径/策略日志）→ 24%；alipay 11 用例（sync wrapper/笛卡尔积/作者声明+合集+转载来源+视频格式透传/enableTimer 无时间→immediate/账号名兜底）→ 14%；全量 948 passed + 12 skipped（CI 门槛 24%，裕度 8pp）
- T16b 平台发布编排层（PR #115，25 用例）：tiktok 13 用例（封面优先级 portrait>landscape>legacy、_upload_single 笛卡尔积、parse_schedule_time 排期+非 list 标量兜底、desc 仅日志不透传锁定）→ 20%；weibo 12 用例（视频 169/916 封面+category+内容声明+合集透传、策略固定 immediate；图集 publish_image dry_run 早返回/>18 张硬上限/单层账号循环非笛卡尔积）→ 19%；全量 973 passed + 12 skipped、总覆盖率 32%→33%（CI 门槛 24%，裕度 9pp）
- T17 平台发布编排层（PR #116，26 用例）：toutiao 13 用例（creation_declaration 字符串→列表解析 逗号/列表/空串/其他类型、封面空串→None 归一化、enable_generate_image 默认 True、collection_id/extend_link 透传、笛卡尔积+排期）→ 18%；vivo 13 用例（平台特有参数 位置/同步/声明/隐私默认公开/下载权限默认允许、dry_run 环境变量 VIVO_DRY_RUN=1 控制、封面归一化、笛卡尔积+排期）→ 19%；全量 999 passed + 12 skipped、总覆盖率 33%（CI 门槛 24%，裕度 9pp）
- T17b 平台发布编排层（PR #117，30 用例）：iqiyi 14 用例（封面优先级 竖版>legacy>横版+cover_path or None 归一化、overall_success 返回值聚合 任一失败→False、enableTimer 原样透传、risk_warning/enable_cash_activity 透传）→ 21%；tencent_video 16 用例（方向感知封面 portrait: 916>竖版 / landscape: 169>横版 + 互补封面规则、creation_declaration 解析、空串透传锁定 仅 primary 做 or None）→ 22%；全量 1029 passed + 12 skipped（破千）、总覆盖率 33%→34%（CI 门槛 24%，裕度 10pp）
- T18 CI 覆盖率门槛 24%→26%（PR #118）：T1-T17 批次后总覆盖率 34%（1029 passed），硬门槛收紧锁住成果防回退，裕度 10pp→8pp
- T19 平台发布编排层（PR #119，25 用例）：youtube 10 用例（_upload_one 方法名契约、排期 list/标量兜底、audience 默认 not_kids/altered_content 默认 False）→ 11%→20%；xiaohongshu 15 用例（话题总数≤10 前置校验 描述 #xxx+标签合并 边界 10 ok、方向感知封面 horizontal→横版/其他→竖版优先、XHS compat 无定时→publish_date=0 且 enableTimer 无时间保持列表、模块级 _publish_single_video+create_browser_fn 注入、xhs_* 特有参数透传）→ 9%→15%；全量 1054 passed + 12 skipped、总覆盖率 34%（CI 门槛 26%，裕度 8pp）
- T20 CI 覆盖率门槛 26%→28%（PR #120）：T1-T19 批次后总覆盖率 34.35%（1054 passed），硬门槛收紧锁住成果防回退，裕度 8pp→6pp
- T21 平台发布编排层（PR #121，23 用例）：bilibili 10 用例（同步 wrapper 内联 _run、_upload_single_video 契约、封面仅横版 portrait 忽略、category/bili_repost_source/bili_collection_name 透传、排期标量兜底）→ 14%；zhihu 13 用例（方向感知封面 素材表 orientation 优先 vertical→916>竖版/horizontal→169>横版 + 无记录兜底前端 videoFormat、creation_declaration 默认「内容无需标注」）→ 15%；全量 1077 passed + 12 skipped、总覆盖率 34.35%→35%（CI 门槛 28%，裕度 7pp）
- T22 平台发布编排层（PR #122，29 用例）：kuaishou 15 用例（标签≤4 前置校验 5→ValueError/4 边界 ok、封面竖版>横版>通用、ai_content 优先于 author_declaration 别名、排期越界兜底 0、_upload_single 契约）→ 15%；jd 14 用例（files/account_file 空→ValueError 京东特有、jd_novel 字符串→{title} 规范化、jd_products 字符串→{title}/最多 10 截断、方向封面 landscape→169>横>916>竖）→ 21%；全量 1106 passed + 12 skipped、总覆盖率 35%（CI 门槛 28%，裕度 7pp）
- T23 平台发布编排层（PR #123，23 用例）：csdn 10 用例（固定横版封面 landscape>portrait 不按方向、recommend 默认 False、排期标量兜底、无封面空串透传锁定）→ 20%；taobao_guanghe 13 用例（link_items 规范化 link_type product/shop 选源/字符串→{title}/最多 6 截断/类型 strip、方向封面 landscape→169>横>916>竖 未知→916 优先、guanghe_claim 透传）→ 13%；jingmai 纯委托 jd 跳过；全量 1129 passed + 12 skipped、总覆盖率 35%→36%（CI 门槛 28%，裕度 8pp）
- T24 视频号 publish_video 编排层（PR #124，9 用例）：channels 无独立 _upload_one_video（DOM 内联+13 个模块级 helper）→ patch 全 helper+browser/context 链测契约：笛卡尔积、参数透传（合集/位置/活动+id/标注/拍摄时间地点/转载）、封面三参数、定时条件调用（enableTimer+publish_date!=0）、is_draft 提交、cookie storage_state 读写路径 → channels/platform.py 18%；全量 1138 passed + 12 skipped、总覆盖率 36%（CI 门槛 28%，裕度 8pp）
