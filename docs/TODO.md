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
- T25 CI 覆盖率门槛 28%→30%（PR #125）：T1-T24 批次覆盖全部 19 平台, 总覆盖率 36.49%（1138 passed）, 硬门槛收紧锁住成果防回退, 裕度 8pp→6pp
- T26 impl/_utils 共享工具（PR #126，28 用例）：parse_schedule_time 18 用例（全平台调度核心：UTC ISO 毫秒/秒/+00:00→转东八 +8h、+08:00 剥离本地标注、本地格式、[dt]*total 重复、解析失败→自动生成、strptime 异常兜底、enableTimer=False→[0]*n、空串→自动生成）；_parse_vivo_count 10 用例（万/w/W/亿、trim、大小写、空/非法→0）；get_account_name_by_cookie_file 5 用例（DB 命中/未命中/异常）；注入 fake utils.files_times（运行时外部依赖）→ impl/_utils.py 12%→18%；全量 1166 passed + 12 skipped、总覆盖率 36.5%→37%（CI 门槛 30%，裕度 7pp）
- T27 impl/jd/_jd_link_ops 链接操作契约（PR #127，28 用例）：纯函数（trace_signature/_page_of Page 直返·frame.page property·callable 兜底/LocateResult）；商品抓取（scrape_total "共 N 条"解析·空态→0、scrape_products skuId 优先级 图片URL→checkbox value→data-sku-id）；抽屉与 radio（switch_radio product=1/novel=3 selector、click_add_card JS click False→RuntimeError、wait_panel_ready）；发布 iframe 识别（wait_publish_frame URL 含 /n/publish-video.html 且无 #、跳过 main_frame、超时 raise）；小说链路（scrape_novels "|" 拆分·坏 option 跳过、search_novels 展开/清空/输入/抓候选、select_novel 精确+模糊匹配点击）；等待工具 wait_for_selector visible → impl/jd/_jd_link_ops.py 21%→52%；全量 1194 passed + 12 skipped、总覆盖率 37%（CI 门槛 30%，裕度 7pp）
- T28 CloakBrowser 工厂契约（PR #128，25 用例）：二进制预下载（_download_binary/init 成功失败日志兜底）；create_browser 启动参数（headless conf 解析 login→LOGIN_HEADLESS/普通→LOCAL_CHROME_HEADLESS、humanize/preset 透传、launch_async 参数契约）；登录关闭监听（disconnected 回调 cancel 当前 task 且 is_close_by_code=True 不 cancel、safe_close 先置标志再关、on 注册失败降级轮询、watchdog 三态 用户关闭 cancel/代码收尾退出/is_connected 异常视为断开 + 自身 CancelledError 静默）；context/关闭（create_context/create_persistent_context 参数契约、close_browser 标志+异常兜底+只读对象 fallback）；同步入口（create_browser_sync/create_context_sync）→ impl/_browser.py 16%→100%；全量 1219 passed + 12 skipped、总覆盖率 37%（CI 门槛 30%，裕度 7pp）
- T28b CI 覆盖率门槛 30%→32%（PR #129）：T28 批次后总覆盖率 37.5%（1219 passed），硬门槛收紧锁住成果防回退，裕度 7pp→5pp
- T29 京东/光合 picker 会话池 + 光合链接操作契约（PR #130，91 用例）：cookie 路径解析（DB 命中/未命中/空 id）；JdPickerSession 全生命周期（_init_browser_and_frame cookie 存在/缺失/double-init/cookie 失效 URL 检测/iframe 失败页面+frame tree dump 诊断、open、novel_search 复用/首启、_dismiss_help_dialog 文案/Esc/异常忽略、search/go_page 未打开报错、close 清理+异常兜底）；GuanghePickerSession（open type 校验/cookie 失效/失败即 teardown、switch_type 同型快照/Esc 失败兜底、switch_tab/apply_filter 模式校验、search strip/店铺跳过 filters、_find_publish_frame 命中/超时兜底 main/异常跳过、_open_picker_panel product 切 preferred、_teardown）；会话池（get_or_create 单例、create 异步销毁旧会话 running loop/无 loop 兜底、release/has/remove）；光合 _link_ops（scrape 四件套 evaluate 驱动+异常兜底、switch_radio/click_add_card/wait_panel_ready 商品 tab·店铺搜索框、switch_tab 四态、click_filter、search 填词/仅清空、load_more 按钮/滚动/scroll 异常、_click_item_by_id）→ jd/picker.py 19%→100%、gh/picker.py 20%→100%、gh/_link_ops.py 32%→98%；全量 1310 passed + 12 skipped、总覆盖率 37%→39%（CI 门槛 32%，裕度 7pp）
- T30 impl/jd/platform.py DOM 交互层契约（PR #131，62 用例）：登录/校验/同步（login 全流程 URL 轮询回创作中心·二次导航超时忽略·close 异常吞掉、check_cookie 缺失/有效/失效 marker、sync_profile、open_creator_center 线程启动+goto 异常兜底）；_upload_single_video 全流程（happy path 上传→封面→标题→发布→清理引用、cookie 失效报错、product 挂件、novel+声明+定时、封面 tmp 生成+删除、unlink 失败吞掉、dry-run 跳过、截图失败、context/close 异常吞掉+引用清理）；DOM 辅助（_upload_video attached 等待+set_input_files、_wait_upload_complete、_set_cover、_fill_title 27 字截断、_link_products 翻页/缺 id/sku 报错、_select_novel、_set_declaration、_set_schedule_time datetime/str/非法、_click_publish、_check_publish_success URL/toast/超时）；模块级（_ensure_cover_min_size 达标/放大/失败、_scrape_jd_profile 提取/兜底/异常）→ jd/platform.py 26%→97%（残留 14 行异常兜底分支）；全量 1372 passed + 12 skipped、总覆盖率 39%→41%（CI 门槛 32%，裕度 9pp）
- T31 CI 覆盖率门槛 32%→34%（PR #132）：T30 批次后总覆盖率 40.71%（1372 passed），硬门槛收紧锁住 T28-T30 成果防回退，裕度 9pp→7pp
- T35-13 bilibili platform DOM 交互层契约（PR #148，127 用例）：纯函数（_sanitize_title emoji/HTML 标签/全角空格过滤、_truncate_desc_by_length emoji=3 宽度截断、cookie 解析）；登录/校验/同步（login QR 多选择器+get_by_role 回退/500 响应与 framenavigated 双分支、check_cookie 判定、sync_profile、_scrape_bilibili_stats 8 项 label_map、open_creator_center）；发布编排（_upload_single_video 全流程：passport 过期 raise/表单轮询超时/提交按钮 10 次重试/按钮消失/URL 跳转/dry_run 提前 return/截图异常/回写异常/合集/定时三策略）；DOM 辅助（上传文件 iframe 回退、等待上传成功/失败 raise/进度日志、标题、分区 int/str 中文/未知/容器兜底、标签、简介、封面三档点击+6 弹窗选择器回退+双 file input+同步勾选、创作声明直选/scoped 回退/下拉超时/转载来源、合集、定时）；坑规避（未 patch 全局 time.time、超时轮询 patch _UPLOAD_WAIT_POLLS 缩至 60 次、asyncio.Event 用 _FakeEvent 替身、page.url 用 _ChangedUrl 驱动 framenavigated）→ bilibili/platform.py 14%→100%；全量 2901 passed + 12 skipped、总覆盖率 78%→81%（CI 门槛 34%，裕度 47pp）
- T35-12 微信公众号 platform DOM 交互层契约（PR #147，113 用例）：登录/校验/同步（login QR 轮询 6 分支(命中/未找到 error JSON/探测异常继续/超时保留浏览器/URL 读取异常/跳首页异常吞掉)、check_cookie 双失效 marker/有效/其他、sync_profile 3 分支、_scrape_stats span 解析/float/int/空/非法数字/未知标题/result None/超时/url 异常/evaluate 异常、_login_stats_fn、open_creator_center 线程+双重异常吞掉、_extract_token/_build_home_url/_resolve_token）；发布编排（_upload_one_video 5 流程(token 失败/全流程定时/解析 0 改立即/truthy int 定时/最小流)、_upload_one_image 4 流程、_upload_all_images、publish_image、_build_publish_datetime）；阶段① DOM（_upload_video_file、_wait_for_video_uploaded 补丁分支/进度日志去重、_set_cover、_fill_material_title、_set_original、_check_service_rule 4 分支、_click_save_and_send 8 分支(handler 捕获/url 异常/弹窗处理/for-else 轮询/兜底扫描捕获/耗尽 raise/force click/wait_for_url 超时)）；阶段② DOM（_fill_publish_title 5 分支含 ProseMirror、_fill_description 5 分支、_set_collection、_set_claim_source 直接/模糊/未知/回退/未找到、_click_dialog_primary、_publish_immediate、_publish_scheduled 开关校验成功/失败仍继续、_select_schedule_date、_select_schedule_time 首查已开/点击后开/展开失败/鼠标异常补 Escape/Escape 异常、_click_time_wheel_item 5 分支、_is_wheel_item_selected、_wait_for_home）；图集（_click_image_menu 5 分支、_upload_images 6 分支）；纯函数（_find_visible_picker_dl_js、_wheel_items_js_body、_parse_cookie_to_storage_state）→ weixin_gzh/platform.py 23%→100%；全量 2774 passed + 12 skipped、总覆盖率 74%→78%（CI 门槛 34%，裕度 44pp）
- T35-11 知乎 platform DOM 交互层契约（PR #146，135 用例）：纯函数（_parse_cookie_to_storage_state、_extract_year、_extract_month、_get_video_orientation id 查询/stored_path 兜底/无结果/异常）；生命周期（login 头像 wait_for 成功/超时保留浏览器/close 异常吞掉/create_browser·context 异常传播、check_cookie 有效/失效/load_state 异常、sync_profile name+stats/抓取异常兜底/外层 except 兜底、_scrape_zhihu_stats 两阶段/累计按钮/未匹配 label/%值 parse_int/去重排序/goto·evaluate 异常、_login_stats_fn、open_creator_center 真实线程+事件断言）；编排（publish_video RAW 参数 100 字符截断、_upload_single_video 定向封面/类别/定时/发布成功失败/截图异常/cookie 回写/dry_run 保留浏览器/cookie 失效 raise/步骤异常不写 cookie/资源清理异常吞掉）；DOM 辅助（_upload_video_file iframe→video→任意 input→上传按钮四策略/全失败 RuntimeError、_wait_upload_complete 成功/失败 raise/轮询异常继续/进度日志、_set_thumbnail file_chooser/Modal input/排除编辑区/预览轮询/确认多策略/弹窗关闭/Escape 兜底/外层异常、_fill_title、_fill_desc_and_tags 2000 截断/标签切分/粘贴回退、_set_video_mark、_ensure_original_checked、_set_category force 重试/双失败 raise、_set_schedule_time int/None 早退/开关探测/日历年月导航/时/分兜底、_click_submit code=0/超时/解析失败/点击失败/dry-run、_dump_form_state）→ zhihu/platform.py 15%→100%；全量 2661 passed + 12 skipped、总覆盖率 71%→74%（CI 门槛 34%，裕度 40pp）
- T35-10 微博 platform DOM 交互层契约（PR #145，130 用例）：纯函数（_parse_cookie_to_storage_state 域/expires 窗口/httpOnly/跳过无效对/空白清理）；生命周期（login 全流程/save_login_result+stats_fn/异常时保留浏览器、check_cookie 文件缺失/valid/expired/异常兜底、open_creator_center 线程启动/两类异常吞掉、sync_profile stats 组装/int 解析异常/空抓取告警/异常兜底、_login_stats_fn）；编排（_upload_one_image 创作卡片未渲染 RuntimeError、_upload_images 直接 set_input_files/expect_file_chooser/patched input 双兜底/30s+5min 超时/trigger 缺失、_click_send、_wait_for_image_publish_success、_upload_one_video 合集选择/跳过/请求响应监听器直接调用、_upload_video_file 主选择器/role 回退/force click/JS click/超时/按钮缺失、_wait_for_upload_form 4 种命中分支/上传失败 RuntimeError/进度日志/超时含 URL/URL 读取失败）；DOM 辅助（_set_video_type、_set_title 30 字截断、_pick_cover_by_aspect 横/竖/正方形/无 aspect/evaluate 异常/等待告警、_set_cover 全流程/4 类缺失/完成失败/关闭超时 ESC×2、_set_category list/str/格式错误/无法识别/未命中表/级联失败 ESC、_set_collection 开关命中/缺失/探测异常/列表未展开/空值跳过/未匹配/勾选失败继续、_set_description desc+tags/title 回落/tags 仅有/空跳过、_set_content_statement v2 探测/异常兜底、_set_content_statement_v1/v2 必选默认/btn 直点兜底/失败 ESC/确定按钮/面板缺失、_click_publish、_wait_for_publish_success）→ weibo/platform.py 19%→100%；全量 2526 passed + 12 skipped、总覆盖率 71%（CI 门槛 34%，裕度 37pp）
- T35-9 小红书 platform DOM 交互层契约（PR #144，147 用例）：纯函数（cookie 解析、_scrape_xhs_stats 抓取组装）；登录/校验/同步（login QR/页面轮询/异常兜底、check_cookie 有效/失效/load_state 异常、sync_profile profile+stats/抓取异常兜底、_login_stats_fn、open_creator_center 真实线程+事件驱动）；编排（publish_video/publish_image 参数解析/文件×账号矩阵、_publish_single_video/_publish_single_image _PUBLISH_DRY_RUN 轮询/双层异常兜底/CDP 扁平化 DOM 探测/cookie 失效 raise/dry_run 保留浏览器/资源清理）；DOM 辅助（页面就绪轮询 submit-disabled 判定/进度节流/超时截图、上传轮询非 button 节点 continue/超时 warning 继续/成功/失败、封面 file_chooser/Modal input/排除编辑区/预览轮询/确认多策略/Escape 兜底、合集/定时/声明/自拍/转发/原创弹窗、标签/简介/标题填写）→ xiaohongshu/platform.py 15%→100%；全量 2531 passed + 12 skipped、总覆盖率 65%→71%（CI 门槛 34%，裕度 37pp）
- T35-8 今日头条 platform DOM 交互层契约（PR #143，94 用例）：纯函数（_parse_cookie_to_storage_state k=v 解析/跳过无效/expires 7 天/.toutiao.com 域）；登录/校验/同步（login 7 选择器 QR 探测(src 无效继续/探测异常跳过)/URL 跳转判定/user-panel 判定/轮询异常吞掉继续/二维码缺失 put error/超时仍保存/save_login_result+stats_fn 挂载/create_browser·context 异常传播、check_cookie 资料面板判定、sync_profile goto 异常吞掉/stats 组装(千分位/元/小数/非法→0)/等待超时/空结果、_login_stats_fn 同 stats 逻辑、open_creator_center 线程启动/事件+close 异常吞掉）；编排（_upload_one_video 全流程：双 file input 选择器/上传成功+进度日志去重/轮询异常继续/4h 超时 return/竖版检测+异常默认横版/标题双选择器/简介 5 选择器+选择器异常 debug 继续+placeholder 兜底+placeholder 异常+未找到 warning/无简介/标签/封面/声明/生成图文/合集横竖/扩展链接横竖/定时/提交按钮双选择器+get_by_role 兜底/URL 跳转两分支/storage_state 回写/close）；DOM 辅助（_fill_tags 输入框缺失/空 tag 跳过/下拉匹配/无匹配点 first/无下拉 Enter/下拉异常 Enter 兜底/外层异常、_set_thumbnail 全空 return/编辑器缺失/本地上传 tab/双 input/横 16:9→4:3 回退/竖 9:16→3:4 回退/完成裁剪+确定按钮/wait 异常回退 role 候选/确定缺失 warning/二次确认弹窗+wait 异常仍点击+xpath 异常 warning/外层异常、_set_creation_declaration 勾选/已勾选/无 checkbox 点 label/无 label/无选项/空项跳过/异常、_toggle_generate_image 启用/禁用/已是目标/checkbox 缺失/label 缺失/异常、_set_collection by ID/by text/未找到/无按钮/confirm 缺失/异常、_toggle_extend_link section 缺失/checkbox 缺失/勾选+填 URL/已勾选无 URL/三级输入框回退/未找到/异常、_set_schedule_time 日/时/分选择/各缺失跳过/无定时按钮/异常）→ toutiao/platform.py 18%→100%；全量 2249 passed + 12 skipped、总覆盖率 62%→65%（CI 门槛 34%，裕度 31pp）
- T35-7 VIVO platform DOM 交互层契约（PR #142，73 用例）：登录/校验/同步（login QR 轮询 .user-info-area/超时 failed+保留浏览器现场/轮询异常继续/save_login_result+stats_fn 挂载/外层异常 traceback+failed/context close 异常吞掉、check_cookie 资料卡判定/无效 False、sync_profile goto 异常吞掉/3 项 stats 组装、_login_stats_fn goto 异常吞掉/抓取异常空、open_creator_center 线程启动/事件+close 异常吞掉）；编排（_upload_one_video 全流程：双 file input 选择器/上传成功文案+进度日志去重/轮询异常吞掉继续/上传 4h 超时 return/desc+tags 拼接 500 截断/双 contenteditable 选择器/无描述跳过/封面/位置/作品同步/自主声明/双 radio/定时/提交按钮双选择器+get_by_role 兜底/URL 跳转判定/60s 提交超时 warning+仍回写 cookie/dry_run 填完字段停在发布界面/close）；DOM 辅助（_set_cover 封面图入口/弹窗容器/上传 tab 激活判定+#tab-2 兜底/双 input 选择器+弹窗内缺失 warning/裁剪区轮询/确定按钮/异常吞掉、_set_location 入口/键盘输入/下拉轮询/精确匹配/无匹配第一项兜底/无下拉 warning/异常吞掉、_toggle_distribution 勾选/取消/已是目标/checkbox 缺失/异常吞掉、_set_declaration 触发器双选择器/选项匹配/Escape 关闭/异常吞掉、_set_radio_by_label 字段区块/选项/aria-checked+is-checked/异常吞掉、_set_schedule_time 定时 radio/日期编辑器/双 input fill/确定按钮双选择器/各缺失告警/异常吞掉）→ vivo/platform.py 19%→100%；全量 2155 passed + 12 skipped、总覆盖率 60%→62%（CI 门槛 34%，裕度 28pp）
- T35-6 YouTube platform DOM 交互层契约（PR #141，63 用例）：模块级+纯函数（_msg 透传、_parse_cookie_to_storage_state .youtube.com 域/expires 7 天/跳过无效对）；登录/校验/同步（login persistent_context+URL 轮询退出/轮询异常吞掉/studio 导航失败仍保存/账号查无回退 uuid1/UPDATE 与 INSERT 两分支/空 profile 回退 YouTube{ts}/500 兜底/close 异常吞掉、check_cookie accounts/signin 判定/外层异常 False/close 异常吞掉、sync_profile 异常空值、open_creator_center 线程/事件+close 异常吞掉）；编排（_upload_one 全流程：tags str 逗号/井号/中文逗号解析+list 透传+非 str 空/上传入口/上传完成 timeout=0/封面组件缺失继续/upload failed raise/desc 填写/封面存在才设置/audience kids/高级设置已折叠跳过+展开点击/altered content/逐标签失败继续/标签输入框缺失继续/[:15] 截断/三步 Next/可见性/完成/回写异常吞掉/异常重抛/close 异常吞掉）；DOM 辅助（_clear_and_type Ctrl+A+Backspace+press_sequentially、_click_radio 已选跳过/首点成功/重试/异常吞掉、_open_upload_dialog 上传按钮+文件选择器、_set_visibility PUBLIC 三策略 evaluate/force/offRadio+offRadio 异常吞掉+定时触发判断、_set_scheduled_publish datetime+int 时间戳/日期输入+Escape 兜底 dropdown/展开按钮可见与异常/时间输入/时区 GMT+8 成功与失败+Escape 二次异常吞掉/外层异常吞掉）→ youtube/platform.py 20%→100%；全量 2082 passed + 12 skipped、总覆盖率 59%→60%（CI 门槛 34%，裕度 26pp）
- T35-5 腾讯视频 platform DOM 交互层契约（PR #140，86 用例）：模块级+纯函数（_scrape_tencent_video_profile 昵称+头像/等待超时仍抓取/缺失/探测异常兜底、_parse_cookie_to_storage_state .qq.com 域/expires 7 天/跳过无效对）；登录/校验/同步（login framenavigated 事件驱动置位/非主 frame 忽略/URL 无 homepage 不置位(无超时留现场)、check_cookie userInfo 判定/外层异常 False、sync_profile profile+stats/networkidle 超时仍抓取/stats 失败保留头像昵称/外层异常兜底、_scrape_tencent_video_stats data-name map 8 项/SORT 排序/千分位/非法数字→0/超时 title+body 诊断/诊断异常吞掉/空结果日志、_login_stats_fn 超时继续/goto 异常仍抓取、open_creator_center 线程/事件+close 异常吞掉）；编排（_upload_one_video 全流程：request 监听 UploadNotify 置位/上传入口 30s 超时 raise+DEBUG dump/dump 异常仍 raise/4h 超时继续/desc 回退标题/封面+声明透传/定时 0 与非 0/发布失败传播/关闭+cookie 回写）；DOM 辅助（_fill_title 双选择器/80 截断/双缺失告警、_upload_cover 上传区+替换兜底/ReactModal/display:block+set_input_files/使用按钮双兜底/异常非阻断、_upload_extra_landscape_cover filter 选填/使用兜底/入口缺失跳过、_upload_extra_portrait_cover 对称流程、_set_creation_declarations 白名单/已勾选跳过/未知/checkbox 缺失/异常吞掉、_set_schedule_time switch 开关(已启用跳过)/dateTimeSelect/popupWrap/itemWrap 三列选择/确定/各缺失告警/异常吞掉、_click_publish 成功文本/URL 跳转/disabled 等待启用/5s 重试点击/重试块异常忽略/URL 探测异常兜底/60s 超时 raise）→ tencent_video/platform.py 22%→100%；全量 2019 passed + 12 skipped、总覆盖率 55%→59%（CI 门槛 34%，裕度 25pp）
- T35-4 爱奇艺 platform DOM 交互层契约（PR #139，86 用例）：模块级+纯函数（_scrape_iqiyi_profile 昵称+头像/超时仍抓取/缺失/探测异常兜底、_parse_cookie_to_storage_state .iqiyi.com 域/expires 7 天/跳过无效对）；登录/校验/同步（login framenavigated 事件驱动置位/300s 超时 put 500/handler 探测异常/非主 frame 忽略/stats_fn 挂载、check_cookie user-info 判定/外层异常 False、sync_profile profile+stats 抓取/异常兜底、_scrape_iqiyi_stats label_map 排序/千分位/非法数字→0/超时仍抓取/JS 异常、_login_stats_fn、open_creator_center 线程/事件+close 异常吞掉）；编排（_upload_one_video 全流程：upload/record 监听注册/表单等待/标题回退 desc/简介+tags 拼接/现金活动/声明/风险/封面三路径/定时/发布成功失败/回写/关闭）；DOM 辅助（_wait_video_upload_complete 事件/4h 超时继续、_fill_title 双选择器/30 截断/双缺失告警、_fill_description 450 截断、_set_creation_declaration map 值/文本兜底/未知/异常吞掉、_set_risk_warning 白名单/下拉/异常、_click_cash_activity、_upload_cover 竖/4:3/16:9 三 tab+file_chooser+完成/trigger 缺失/各 tab 缺失/legacy kwargs、_set_schedule_time fill 日期+Enter/缺失/异常、_click_publish 上传卡轮询+百分比日志+30min 超时+探测异常/URL 成功路径/文本关键词/无成功标志 False/点击异常 raise）→ iqiyi/platform.py 21%→100%；全量 1933 passed + 12 skipped、总覆盖率 55%→57%（CI 门槛 34%，裕度 23pp）

- T35-3 TikTok platform DOM 交互层契约（PR #138，80 用例）：纯函数（_parse_cookie_to_storage_state .tiktok.com 域/expires 7 天/httpOnly/sameSite Lax/跳过无效对/去空白）；登录/校验/同步（login URL 正则 /(foryou|following|upload|@)/ timeout=0+失败留浏览器现场、check_cookie select class 判定/异常兜底 True、sync_profile 昵称+头像抓取/超时/探测异常兜底/外层异常、open_creator_center 线程启动/事件+close 异常吞掉）；编排（_upload_single 全流程：iframe/main 双文件输入/上传失败 raise/input 等待超时继续/caption 等待/封面/AI 声明 truthy-falsy/定时 0 与非 0/cookie 回写/浏览器关闭/父目录样本日志）；DOM 辅助（_dismiss_tutorial_tooltip/_dismiss_content_check_modal/_dismiss_ai_label_modal 可见点击+不可见 noop+异常吞掉、_dismiss_publish_confirm_modal page+frame 遍历/force click/外层异常兜底、_add_title_tags DraftEditor 键盘输入/空 tag 跳过/rstrip 语义、_set_cover 弹窗上传+保存、_set_ai_declaration 显示更多展开/Switch__root 点击/确认弹窗/诊断异常继续/容器不可见 raise、_set_schedule_time CN/EN/未知月份/跨月右箭头/日选择/分钟取整/Escape、_click_publish disabled/页面关闭/轮询耗尽/点击异常重试、_get_last_video_id href 解析/兜底）→ tiktok/platform.py 20%→100%；全量 1847 passed + 12 skipped、总覆盖率 53%→55%（CI 门槛 34%，裕度 21pp）

- T35-2 CSDN platform DOM 交互层契约（PR #137，57 用例）：纯函数（_parse_cookie_to_storage_state 多子域映射 passport/.blog/i.csdn.net+secure/httpOnly 白名单+SESSION 复制 msg.csdn.net+跳过无效对）；登录/校验/同步（login 用户信息卡 wait_for+失败留浏览器、check_cookie 卡片 count 有效/失效/load_state 超时吞掉、sync_profile evaluate 抓取+label_map 组装+¥/千分位/float 解析+未知丢弃+空结果、_login_stats_fn 超时继续、open_creator_center 线程/close 异常吞掉）；编排（publish_video 文件×账号矩阵/横版优先/竖版兜底/非 list 排期、_upload_single_video cookie 失效 raise/提交失败仍回写/无封面跳过）；DOM 辅助（_upload_video_file 双策略/无 input raise/截图异常继续、_wait_upload_complete 成功/失败 raise/轮询/异常继续、_set_thumbnail 双策略/确认多策略+JS 兜底/无弹窗/兜底失败非致命+Escape/弹窗关闭轮询、_fill_title 30 截断、_fill_desc 150 截断、_fill_tags 解析/#剥离/上限 3/逐 tag 失败继续、_set_recommend、_click_submit URL 跳转判定/JS 兜底/双失败 False/不跳转按成功/异常 False）→ csdn/platform.py 22%→94%；全量 1760 passed + 12 skipped、总覆盖率 52%→53%（CI 门槛 34%，裕度 19pp）
- T35-1 百家号 platform DOM 交互层契约（PR #136，71 用例）：纯函数（_parse_cookie_to_storage_state 解析/跳过无效对/expires 未来、_count_chars emoji=3、_validate_publish_params ≤10 标签/≤50 字符/emoji 计数）；登录/校验/同步（login QR 流程+失败留浏览器现场、check_cookie 缺失/失效 marker/业务域兜底/页面异常、sync_profile profile+stats+storage_state 回写/统计失败兜底/写回失败吞掉、_scrape_baijiahao_stats label_map 排序/千分位/+/非法数字/等待超时仍抓取、_login_stats_fn goto 超时继续/抓取失败空、open_creator_center 线程启动/事件异常吞掉）；编排（publish_video 前置校验 ValueError、_upload_all 文件×账号矩阵/封面声明透传）；单视频（_upload_one_video 全流程：请求监听置位/上传失败 raise/封面就绪轮询/人机校验 hidden/超时 raise/成功跳转失败 raise）；DOM 辅助（_wait_for_upload、_add_title_tags Lexical+placeholder 兜底+下拉超时跳过、_publish_video 定时/直接分派、_direct_publish 双选择器+异常冒泡、_set_schedule_publish 过去/>7 天/当天小时三校验+happy、_pick_schedule_option aria-activedescendant ArrowDown/Up/expanded 超时兜底/无 active id、_set_cover 双 cover-container/缺失/不存在/不足/无确认按钮/点击异常不阻塞、_set_creation_declaration 空跳/未找到输入框/双选 radio/未匹配仍确认/异常不阻塞）→ baijiahao/platform.py 26%→98%；全量 1703 passed + 12 skipped、总覆盖率 50%→52%（CI 门槛 34%，裕度 18pp）
- T34 快手 platform DOM 交互层契约（PR #135，67 用例）：登录/校验/同步（login QR 流程+URL 轮询+过期刷新/close 异常冒泡、check_cookie、sync_profile、_parse_cookie_to_storage_state、open_creator_center 线程启动）；数据抓取（_scrape_kuaishou_stats 排序/千分位/缺失/异常、_login_stats_fn 3 分支）；图集编排（publish_image 标签上限/单多账号/封面缺失/ai_content 别名、_upload_image_note dry_run/正式/全可选/声明 NONE/file_chooser 异常冒泡+清理）；单视频（_upload_single 全流程：文件选择器/上传轮询/发布循环 wait_for_url 失败重试/确认发布/know_btn/定时+声明 NONE、dry_run 不关 context/browser）；DOM 辅助（_close_guide_overlay new/old/no、_input_tags CDP 打字机+下拉 _active_+空格兜底、_set_thumbnail 横竖比例/active 跳过/失败不阻塞、_set_image_cover、_set_image_music 精确/首卡兜底/无卡片关抽屉、_set_author_declaration 三策略/无匹配 Esc、_set_schedule_time radio+picker）；编排边界（_publish_video_async 封面优先级竖>横>通用/ai_content 透传/标签上限/多文件多账号日期）→ kuaishou/platform.py 15%→94%；全量 1632 passed + 12 skipped、总覆盖率 47%→50%（CI 门槛 34%，裕度 16pp）
- T33 抖音 platform DOM 交互层契约（PR #134，89 用例）：登录/校验/同步（login URL 变化事件/子 frame 忽略/挂起、check_cookie 有效/失效/登录提示/close 异常冒泡、sync_profile 成功/空日志/计数兜底、open_creator_center 线程启动）；数据抓取+纯函数（_login_stats_fn 超时/JS 异常、_parse_cookie_to_storage_state、_count_hashtags、_validate_publish_params）；单视频编排（_upload_one_video 全流程：第三方开关开/已勾选、合集、活动拼接、定时、dry_run 浏览器循环、上传失败重试、发布循环 wait_for_url 失败→自动封面→重试、context.close 异常冒泡）；图集链路（_upload_image_note 全流程 dry_run/正式/全可选/上传超时/跳转超时、publish_image 单/多账号/封面缺失）；DOM 辅助（_fill_title_and_description 30 截断/空 tag 跳过、_set_schedule_time 8 步全量/缺项告警/Enter 兜底/异常、_set_product_link 正常/无下拉/错误弹窗/disabled 关闭/短标题缺失/异常、_set_thumbnail 双 tab/默认分支/探测异常、_handle_auto_video_cover 四分支、_set_image_cover 正常/fallback 输入/异常、_set_image_mix 正常/无下拉/Esc、_select_music xpath/文本兜底/首卡兜底、_set_hotspot 精确/兜底选择器/Enter、_set_tag 5 类型+未知类型文本默认+无下拉/无类型 Esc/首选项兜底、_set_location_tag 正常/placeholder 兜底/Esc、_set_declaration 正常/未找到关闭/异常）→ douyin/platform.py 15%→87%；全量 1565 passed + 12 skipped、总覆盖率 44%→47%（CI 门槛 34%，裕度 13pp）
- T32 支付宝 platform DOM 交互层契约（PR #133，104 用例）：登录/校验/同步（login 等待容器/异常冒泡、check_cookie 缺失/有效/失效/异常、open_creator_center 线程启动/异常兜底、sync_profile 成功/失败兜底）；数据抓取+纯函数（_scrape_alipay_stats 映射/排序/千分位/超时/JS 异常、_parse_cookie_to_storage_state、_parse_schedule_dt 6 格式时区语义）；编排层（_upload_one_video 横竖封面/合集/转载/定时、_upload_one_image_set 音乐链路）；DOM 辅助（_set_title 30 截断、_set_description_and_tags 话题联想精确/自定义/无下拉/异常 Esc、_set_cover 四策略、_set_compilation 响应拦截/exact/fuzzy、_set_author_statement value radio/label 兜底、_set_reprint_url id/placeholder、_set_schedule_time radio/picker/Enter 兜底、_click_publish disabled 轮询、_wait_for_publish_success URL/文案/双弹窗/超时）；上传链路（_upload_video_file 三重策略、_wait_for_upload_form 失败检测/可见/超时、_upload_images 成功/失败重试/错误 DOM/超时/fallback 遍历、_set_music 翻页/Esc 兜底）→ alipay/platform.py 15%→88%；全量 1476 passed + 12 skipped、总覆盖率 41%→44%（CI 门槛 34%，裕度 10pp）
