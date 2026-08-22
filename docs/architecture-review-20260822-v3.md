# 多平台架构 Review v3（R5-R7 整改后复评 · 2026-08-22）

> 分析对象：`/home/dev/social-auto-upload-web-ui`（master @ 3a71899，R5/R6/R7 整改后）
> 方式：只读静态分析。3 条并行探测线（执行编排层 / 平台实现层 / 元数据·前端·契约层）+ 主线程对存疑证据二次复核（子代理误报已剔除）。
> 前置：v1（`docs/multiplatform-architecture-review-20260822.md`）、v2（`docs/architecture-review-20260822-v2.md`）、ROI 清单（`docs/architecture-rectification-roi.md`，R1-R8 ✅ / R9 待做）。
> 定位：评估 R5/R6/R7 成效，暴露**整改引入/遗留**的变味点，为 R7 收尾与 R9 提供决策输入。

---

## 1. 多平台架构特点（设计意图与现状）

主干设计意图在整改后更加清晰，多平台支持呈「**单内核 + 契约红线 + 派生元数据**」形态：

| 层 | 设计机制 | 现状 |
|---|---|---|
| 平台抽象 | `BasePlatform` ABC：`publish_video`/`publish_image` 全 `async` + 统一浏览器工厂（CloakBrowser + watchdog） | ✅ 20/20 `publish_video` async；`publish_image` async（6 平台实现，14 平台默认 NotImplementedError） |
| 执行内核 | `ext_api/task_queue.py` 为**唯一发布执行内核**：`add_task` → worker → `_execute` 按 `publish_kind` 分发 | ✅ R6 落地：`/postVideo`、`/publish`、`/execute-publish`、`/drafts/batch-publish` 全部入队化，`publish_bp`/`image_publish_bp` 内 `asyncio.run` 归零 |
| 状态/聚合 | `util/status.py`：`TaskStatus` 6 态枚举 + `aggregate_batch_status` 唯一真源 | ✅ R7 落地：task_queue re-export，publish_history 引用（**但未全员引用，见 V-A**） |
| 历史写入 | `services/publish_history.py` | ⚠️ 部分收敛（见 V-A：仍与 task_queue/image_publish_bp 三处并存） |
| 元数据 | registry 类属性（platform_id/key/name）为逻辑真源 | ⚠️ R4 只加了契约一致性测试，`conf.PLATFORM_MAP`/`PLATFORM_ID_TO_KEY` **仍是独立硬编码**（见 V-B） |
| 契约治理 | `test_platform_contracts.py` 7 断言（结构/元数据/唯一 key/禁 browser.close 直调/禁 get_event_loop/全 async/映射一致） | ✅ 漂移即 CI 失败 |
| 前端 | `platforms.ts` 19 平台集中配置，与 registry 1:1 对齐，无缺口 | ✅ 业务特判仅 8 处（淘宝光合/B站/支付宝/视频号/Toutiao 字段兼容） |
| 服务层方向 | services/ 无 flask app/g/blueprints 反向依赖 | ✅ 方向干净 |

**整改成效（v1/v2 → v3）**：
- 三套发布执行路径 → **一套**（task_queue 唯一内核）✅
- `publish_video` 6 async/14 sync → **20/20 async** ✅；`iscoroutinefunction` 双分支已删（`task_queue.py:235` 直接 await）
- `browser.close()` 直调 78 → **0**；19 处 `asyncio.run` 全部是 `asyncio.run(close_browser(browser))` 同步兜底桥接（异常路径收尾，合理，非契约残留）
- 状态字面量三处定义 → `util/status.py` 单源（task_queue 已 re-export 兼容）✅

---

## 2. 剩余/新增变味点（按严重度排序）

### 🔴 V-A：R7「唯一 writer」只完成了一半——仍有三处独立 SQL 写入器 + 聚合语义分叉

| 写入器 | INSERT/UPDATE 位置 | 聚合逻辑 |
|---|---|---|
| `services/publish_history.py` | `:39,:51,:70,:95`（`_record_publish`/`_update_publish_result`） | `aggregate_batch_status`：failed 归 fail、in-flight 归 running、**cancelled 不计 fail 也不计 in-flight** |
| `ext_api/task_queue.py` `_insert_db/_update_db` | `:318,:335,:351,:377` | **独立聚合**：`failed OR cancelled` 归 fail（`:368`）——cancelled 语义与 publish_history **不一致** |
| `blueprints/image_publish_bp.py` `_update_image_publish_detail` | `:65,:91` | **旧 4 态手写聚合**（`image_publish_bp.py:60-100`）：无 in-flight、无 cancelled——**cancelled 详情 → batch 误判 success**（fail=0 即 success） |

- **证据**：三处 UPDATE publish_batches 的聚合条件互不相同（`task_queue.py:368` vs `publish_history.py:85-86` vs `image_publish_bp.py:80-92`）。
- **影响**：同一批 detail 若含 cancelled，三处 writer 会算出三种 batch 状态；`image_publish_bp` 旧聚合连 in-flight 态都没有，与 R7 补的 running 语义背道而驰。
- **根因**：R7 只收敛了 image_publish_bp 的 **INSERT**（改走 `_record_publish`），但 task_queue 的 `_insert_db/_update_db` 与 image_publish_bp 的 `_update_image_publish_detail` 仍是独立实现。

### 🔴 V-B：平台元数据双源仍是「测试兜底」而非「实现派生」（R4 半程）

- **证据**：`conf.py:23-30` 的 `PLATFORM_MAP`/`PLATFORM_ID_TO_KEY` 仍是**独立硬编码字典**；`test_platform_contracts.py:119-131` 只校验 conf 与 registry 一致。registry 改属性 → conf 不会自动变，靠 CI 兜底。
- **根因**：R4 收敛的是 blueprints 侧派生（`image_publish_bp._derived_platform_map`），conf 公共映射因「防循环依赖」未动。

### 🟠 V-C：publish_image 能力面无门控——14 个平台会抛 NotImplementedError

- **证据**：`publish_image` 仅 6 平台实现（douyin/alipay/xiaohongshu/weibo/kuaishou/weixin_gzh，`platform.py:1073/429/441/396/376/1907`）；`base_platform.py:384-389` 默认抛 NotImplementedError；`task_queue.py:235` 分发无能力检查。
- **推断**：前端若对不支持图集的平台发起 image 任务 → worker 抛 NotImplementedError → detail 记 failed。不是数据损坏，但失败原因不友好、无前置校验。

### 🟠 V-D：平台单文件体量悬殊（v2 遗留，未动）

- weixin_gzh 2240 / weibo 2084 / alipay 2026 / douyin 1895 行，均为「单类单文件」；19 平台合计 27332 行。channels/xiaohongshu 已抽模块级 helper（23/19 个顶级 def），weixin_gzh/weibo/alipay/douyin 仍全在大类内。

### 🟠 V-E：R9 整项未做——样板重复 + 上帝模块依旧

- `_parse_cookie_to_storage_state` **16/20** 平台逐字节重复（`xiaohongshu:76` ≡ `weibo:54` 等）；`_set_schedule_time` 14 平台重复。
- `impl/_utils.py` **1472 行**，13 个平台专属 `scrape_*`（bilibili/tencent/baijiahao/youtube/alipay/weibo/toutiao/vivo/zhihu/csdn/weixin_gzh/taobao_guanghe/jingmai）集中于此，而 **iqiyi/tencent_video/jd 本地保留 `_scrape_*`**——同一职责两种放置（v1 已指出，未收敛）。
- `create_browser_sync` 20/20 平台直调（绕过 `self.create_browser`）：R8 只统一了 **close 侧**，**create 侧入口未统一**（v2 的 S4 未做）。

### 🟡 V-F（本次新发现）：`util/` 层存在 3 个超大「类上帝」模块候选

- `services/_logger.py` 4178 行 / `services/async_utils.py` 1326 行 / `services/video_limits.py` 8536 行（子代理初报，主线程已复核行数：`util/` 下 `_logger.py` 114 行、`video_limits.py` 190 行——**误报剔除**；实际超大体量在 `services/` 下同名文件）。需单独审计是否真有职责混杂，或只是配置/常量堆积。

---

## 3. 改进建议（按 ROI）

### P0（高价值低成本，R7 收尾必做）
**A1. 唯一 writer 收尾（补 R7 缺口）**：把 `task_queue._insert_db/_update_db`（`task_queue.py:305-382`）与 `image_publish_bp._update_image_publish_detail`（`:60-100`）收敛到 `publish_history`（`_record_publish`/`_update_publish_result`），task_queue 只保留「调度 + 状态回写」，删 `_insert_db/_update_db` 重复 SQL。
- 成本：1-2 人日。收益：三处聚合语义立即归一，消除 cancelled 误判。

**A2. 聚合语义定口径**：`aggregate_batch_status` 明确 cancelled 归属（建议：cancelled 计 fail 列，与 task_queue 现状一致；publish_history 的 `failed_n` 补 `OR cancelled`），并加一条单元测试锁定「cancelled → batch failed」。
- 成本：0.5 人日（含测试）。

### P1（结构性，半程项补完）
**A3. conf 平台映射改为真派生**：`conf.PLATFORM_MAP`/`PLATFORM_ID_TO_KEY` 改为从 registry 懒加载派生（复用 image_publish_bp 的防循环依赖模式），删硬编码字典。
- 成本：1 人日。收益：R4 从「测试兜底」升级为「实现单源」。

**A4. publish_image 能力门控**：registry 或 base 增加 `supports_image` 元数据；`task_queue._execute` 分发前校验，不支持 → 任务直接标记 failed 并给出友好错误；前端按能力面禁用图集入口。
- 成本：1 人日。

### P2（机械项，R9 执行）
**A5. create 入口统一（R9-1）**：`create_browser_sync` 收敛到基类 `self.create_browser` 的 sync 包装，20/20 平台改走统一入口。
- 成本：1-2 人日。

**A6. cookie 解析上移（R9-2）**：`_parse_cookie_to_storage_state` 16 平台收敛为基类实现 + 平台声明 cookie 域列表。
- 成本：2 人日。

**A7. _utils 拆分（R9-3）**：13 个 `scrape_*` 迁回各自平台目录（对齐 iqiyi/tencent_video/jd），`impl/_utils.py` 只留通用工具。
- 成本：3 人日。

**A8. 平台文件瘦身（v2 S7）**：weixin_gzh/weibo/alipay/douyin 2000+ 行单文件按「表单构造/DOM 交互/数据抓取」拆子模块。
- 成本：5-8 人日，可分批。

**A9. services/ 大文件审计**：`services/_logger.py`(4178)/`async_utils.py`(1326)/`video_limits.py`(8536) 核实是否职责混杂，决定拆分或确认合理。
- 成本：1 人日（审计）+ 拆分另计。

---

## 4. 证据与推断边界

- **证据（直接可查）**：V-A 三处 UPDATE 聚合条件（`task_queue.py:368` / `publish_history.py:85-86` / `image_publish_bp.py:80-92`）；V-B `conf.py:23-30` 硬编码 + 契约测试仅校验一致；V-C `publish_image` 实现平台列表 + base 默认抛错 + `task_queue.py:235` 无门控；V-D/E 行数与重复函数分布；V-F 行数复核后修正。
- **推断**：V-A cancelled 误判的实际触发频率取决于用户取消 image 任务的活跃度（静态无法量化）；V-C 的 NotImplementedError 是否已真实发生取决于前端图集入口是否对 14 平台开放（需前端配合确认）。
- **已剔除误报**：`util/_logger.py` 4178 行 / `util/video_limits.py` 8536 行 / `util/async_utils.py` 1326 行系子代理路径误读，实际 util 层无上帝模块；`asyncio.run` 19 处全部为 `close_browser` 兜底桥接，非契约残留。

## 5. 未知项 / 限制

- 未跑重型 DOM 测试（本机 3.7GB 内存，OOM 限制）——聚合语义改动需 CI 全量兜底。
- 未确认前端图集能力面对 14 个不支持平台是否已禁用（决定 V-C 严重度）。
- `services/` 三个大文件未逐行审读职责（V-F 只是行数信号）。

## 6. 结论

整改后**执行内核与契约层已达标**（单内核发布、全 async 契约、生命周期红线、状态枚举单源）。剩余变味高度集中在 **R7 收尾**：三处独立 SQL 写入器与聚合语义分叉（含 cancelled 误判）是当前最大的数据完整性风险；其次 R4 的 conf 双源是「测试兜底」而非「实现单源」。建议顺序：**A1 → A2（R7 收尾）→ A3 → A4（半程项补完）→ A5-A9（R9 机械项）**。全部完成前，新增第 20 个平台的成本已从「v1 的三套队列」降到「一处 writer + 一处契约」，但聚合语义分叉会让「取消/重试」类状态路径仍不可靠。
