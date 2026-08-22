# 多平台架构 Review v2（整改后复评 · 2026-08-22）

> 分析对象：`/home/dev/social-auto-upload-web-ui`（master @ 4c8e94d，R1-R4/R8 整改后）
> 方式：只读静态分析（源码 + AST + 契约测试全量断言），未跑重型 DOM 测试（本机内存限制）
> 前置：v1 review（`docs/multiplatform-architecture-review-20260822.md`）+ ROI 清单（`docs/architecture-rectification-roi.md`）
> 定位：评估整改成效，复核剩余变味点，补充 v1 未覆盖的新发现。

---

## 1. 架构特点（设计意图，未变味部分）

多平台支持的**主干设计依然健康**，且整改后收敛度显著提升：

| 层 | 机制 | 现状 |
|---|---|---|
| 平台抽象 | `BasePlatform` ABC + 统一浏览器工厂（CloakBrowser + watchdog 防误 cancel） | ✅ 完整，`close_browser` 统一入口已被 100% 使用 |
| 注册表 | `registry.py` 19 平台注册 + `get_platform(id)` 泛化 | ✅ 契约测试强制结构/元数据/唯一 key |
| HTTP 主链 | account_bp/publish_bp 全走 `get_platform(type)` | ✅ 无 per-platform 第二实现 |
| 元数据 | registry 类属性为唯一真源，conf/ext_api/image_publish_bp 派生 | ✅ R4 落地，契约测试锁定一致 |
| 契约治理 | `test_platform_contracts.py` 7 断言（结构/红线/吞失败） | ✅ 新增，漂移即 CI 失败 |
| 前端配置 | `platforms.ts` 19 平台集中配置 | ✅ 单源 |

**整改成效（v1 → v2）**：
- `browser.close()` 直调 78 → **0**；`asyncio.get_event_loop()` 73 → **0**
- sync 平台吞失败反模式 14 处 → **0**（全部 try/except 包裹返回 False）
- `run_async` 9 处重复 → **1** 处共享实现
- image_publish_bp 平台映射缺口 8/9/17 → **19 全量**

---

## 2. 剩余变味点（按严重度排序）

### 🔴 V-A：发布执行仍是「一主二辅」三套活跃路径（R6 未做）

| 路径 | 入口 | 现状 |
|---|---|---|
| 主 | `/postVideo` → `ext_api.task_queue` | ✅ 已统一（Batch E），持久化 6 态 + SSE |
| 辅 1 | `/api/image-publish/publish` → `image_publish_bp` | ⚠️ 仍含 `asyncio.run` 请求线程内同步执行（2 处），不入 task_queue |
| 辅 2 | `/postVideoBatch`（`publish_bp.py:404` 附近） | ⚠️ 同步循环、不写历史（数据完整性缺口仍在） |

前端三路都活跃（`draft.ts:22` / `imagePublish.ts:15` / `PublishCenter.vue`）。**三份状态机、三份超时/取消语义**是新增平台成本飙升的头号根源。

### 🟠 V-B：publish_video 契约仍双轨（R5 未做）

- 基类声明 sync `def publish_video`，**6 async / 14 sync**（当前实测）
- task_queue 被迫 `iscoroutinefunction` 双分支（`task_queue.py:252-261`）
- 14 个 sync 平台各自 `asyncio.run` 桥接（R2 已修复吞失败，但桥接结构仍在）
- kuaishou 等仍在方法内 `import asyncio` 局部使用

### 🟠 V-C：历史写入三份独立 writer + 状态语义分叉（R7 未做）

- `publish_history.py`（4 态：pending/success/failed + 聚合）vs `task_queue._insert_db/_update_db`（6 态含 queued/running/cancelled）vs `image_publish_bp` 行内 INSERT
- `postVideoBatch` 不写历史 → 该路径发布记录永久缺失

### 🟠 V-D：_utils.py 上帝模块 + 平台专属逻辑仍集中

- 1472 行，14 个平台专属 `scrape_*`（csdn/weixin_gzh/taobao_guanghe/jingmai 等）仍在 _utils
- 16 个平台 `_parse_cookie_to_storage_state` 逐字节重复（未上移基类）
- 20/20 平台仍直接从 `.._browser import create_browser_sync`（绕过 `self.create_browser`，虽 close 已统一，create 入口未统一）

### 🟡 V-E：平台目录体量悬殊

- 最大 `weixin_gzh/platform.py` 2240 行 / `weibo` 2084 / `alipay` 2026 / `douyin` 1895，19 平台合计 27316 行
- 单文件 2000+ 行 = 单一职责原则失效，review 难度高

---

## 3. 改进建议（按 ROI，承接 ROI 清单未完成项）

### P0（决策先行，阻塞其他）
**S1 = R5：publish_video 契约统一 async** —— 基类改 `async def publish_video` + 提供 `run_publish_sync()` 同步包装模板；14 个 sync 平台方法体去掉 `asyncio.run` 桥接改直接 `await`；删 task_queue `iscoroutinefunction` 双分支。成本 3-5 人日，是 V-B 根治且 R6 前置。

**S2 = R6：发布执行三合一** —— 以 task_queue 为唯一内核：image_publish 入队化、删 postVideoBatch 残留（顺带补历史写入）。成本 8-12 人日，V-A + V-C 双根治。

### P1（低风险高收益）
**S3 = R7：历史唯一 writer** —— `publish_history.py` 补 in-flight 态对齐 task_queue，删其他两处重复 SQL。成本 2-3 人日。

**S4 = R9-1：create 入口统一** —— 20/20 平台 `create_browser_sync` 改走基类 `self.create_browser`（sync 包装），与 close 侧对齐。成本 1-2 人日，机械。

### P2（治理补强）
**S5 = R9-2：cookie 解析上移基类** —— 16 平台 `_parse_cookie_to_storage_state` 收敛为基类实现 + 平台声明 cookie 域列表。成本 2 人日。

**S6 = R9-3：_utils 拆分** —— 14 个 `scrape_*` 迁回各自平台目录，_utils 只留通用工具。成本 3 人日。

**S7（新增）平台目录瘦身** —— 2000+ 行平台文件拆「表单构造 / DOM 交互 / 数据抓取」子模块（参照 F2 前端拆分经验）。成本 5-8 人日，可分批。

---

## 4. 证据与推断边界

- **证据（直接可查）**：V-A 三路径入口 `publish_bp.py:151,166,404` + `imagePublish.ts:15` + `draft.ts:22`；V-B 6/14 实测 AST；V-C 三文件 INSERT/UPDATE + 状态枚举对比；V-D `_utils.py:938-1112` 14 个 scrape + 16 处 cookie 解析。
- **推断**：postVideoBatch 不写历史的实际影响取决于该路径使用量（无埋点，静态无法量化）。
- **未验证**：重型 DOM 测试未跑（内存限制），S1-S7 改动需 CI 全量兜底。

---

## 5. 结论

整改后架构的**主干与红线层已达标**（生命周期/元数据/契约测试/吞失败），剩余变味高度集中在**执行层**：三套发布路径（V-A）与双轨契约（V-B）是同一根因的两面——契约不统一导致执行路径无法合并。建议严格按 **S1(R5) → S2(R6) → S3(R7)** 顺序推进：先统一契约形态，再并队列，最后收敛写入器；S4-S7 为机械项可穿插。新增平台仍受 V-A/V-B 制约，是当前扩展成本飙升的核心。
