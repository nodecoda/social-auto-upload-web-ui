# 多平台架构 Review 报告（2026-08-22）

> 分析对象：`/home/dev/social-auto-upload-web-ui`（千帆云递 v1.2.5）
> 分析分支：`feature/20260821-arch-batch-e`（分析期间从 batch-c 切换，工作区当前干净）
> 分析方式：只读。3 条并行探测线（平台实现层 / HTTP 编排层 / 测试文档前端佐证）+ 主线程二次复核交叉验证。
> 用途：作为后续架构收敛（发布链路三合一、契约统一）的决策输入。本文件为快照，不保证随代码演进。

---

## 1. 多平台架构特点（设计意图与现状）

现状是「主干泛化 + 外围分叉」的混合体，主干设计意图清晰，且近期 Batch A–D 重构正在收敛。

| 层 | 设计机制 | 证据 |
|---|---|---|
| 平台抽象 | `BasePlatform` ABC（login/check_cookie/sync_profile/publish_video 抽象方法）+ 统一浏览器工厂 `_browser.py`（CloakBrowser 隐身 + watchdog 防误 cancel） | `backend/impl/base_platform.py:1-381` |
| 注册表 | `registry.py` 按 platform_id 注册 20 平台类，`get_platform(id)` 泛化实例化 | `backend/impl/registry.py:24-59` |
| HTTP 主链 | account_bp 登录/导入/校验、publish_bp 发布全部走 `get_platform(type)`，无 per-platform 登录/发布第二实现 | `backend/blueprints/account_bp.py:455,541`；`publish_bp.py:189` |
| 跨平台服务层 | services/ 无 flask/app/g 反向依赖，方向干净 | grep 确认无命中 |
| 前端 | `platforms.ts` 集中 19 平台配置 + `settingsFields` 通用字段渲染模型；`platformId ===` 特判仅 1 处 | `frontend/src/config/platforms.ts:42-758` |
| 测试治理 | 通用契约测试（test_registry 7 + test_base_platform 16）+ 逐平台 DOM 契约测试（20 个 `*_platform_dom.py`）+ CI 4 道检查 | `backend/tests/test_registry.py:24-59`、`test_base_platform.py:88-272` |

**结构层契约遵守度 20/20**：所有平台均为 `class XxxPlatform(BasePlatform)` 类实现，无模块级整体绕过。

---

## 2. 变味点分级（Ranked）

| # | 变味点 | 严重度 | 置信度 | 关键证据 |
|---|---|---|---|---|
| 1 | **发布执行存在三套并行架构，且全部是活跃生产路径** | 🔴 高 | 高 | 主链 `publish_bp.py:176 /postVideo` → `services/publish_executor.py`（单线程串行/内存态/2h TTL）；第二套 `ext_api/__init__.py:219 /api/v2/tasks` + `:1219 /drafts/batch-publish` → `ext_api/task_queue.py`（asyncio 双 worker/持久化 6 态/SSE）；第三套 `image_publish_bp.py:266-271,442`（请求线程内同步 `asyncio.run`）+ `publish_bp.py:373 /postVideoBatch`（同步循环且不写历史）。前端三路都在用：`frontend/src/views/PublishCenter.vue:3153`、`frontend/src/api/draft.ts:22`、`frontend/src/api/imagePublish.ts:15` |
| 2 | **publish_video 同步/异步契约分裂** | 🔴 高 | 高 | 基类声明同步 `def publish_video`（`base_platform.py:158`），6 平台实现为 async（douyin:349、youtube:286、tencent_video:361、iqiyi:350、toutiao:373、vivo:277）；调用方被迫 `asyncio.iscoroutinefunction` 双分支（`task_queue.py:251-261`）；13 个同步平台各自 `asyncio.run` 桥接，kuaishou 桥接后**无条件 return True**（`kuaishou/platform.py:601-603`，有吞失败风险） |
| 3 | **publish_batches/publish_details 三份独立写入器 + 状态机语义分叉** | 🔴 高 | 高 | `services/publish_history.py:19-89`（4 态，无 in-flight）vs `ext_api/task_queue.py:337-440 _insert_db/_update_db`（6 态含 in-flight）vs `image_publish_bp.py:55-141,497-518`（行内 INSERT）；`publish_batches.type` 主链 'video'、图集 'image' |
| 4 | **统一浏览器关闭入口形同虚设** | 🟠 中高 | 高 | 19/19 平台直接 `browser.close()`（如 `xiaohongshu/platform.py:158,194,226`），基类文档明令改走 `self.close_browser`（`base_platform.py:97-107`）；仅 6 个平台部分使用统一入口，13 个平台从未用；且 19/19 直接 `from .._browser import create_browser_sync` 绕过 `self.create_browser`，login 走 async、publish 走 sync 双轨混用 |
| 5 | **_utils.py 上帝工具模块 + 平台专属逻辑随机分布** | 🟠 中高 | 高 | 1472 行、19/19 平台 import；13 个平台专属爬虫集中于此（`_utils.py:255-1112` scrape_bilibili/tencent/baijiahao/youtube/alipay/weibo/toutiao/vivo/zhihu/csdn/weixin_gzh/taobao_guanghe/jingmai_profile），而 iqiyi/tencent_video/jd 又把爬虫留在本地——同一职责两种放置 |
| 6 | **跨平台样板重复** | 🟠 中 | 高 | `_parse_cookie_to_storage_state` 16 平台逐字节重复（`xiaohongshu:76-90` ≡ `weibo:54-68`）；`_set_schedule_time` 13 平台同名 + 3 变体名（`xiaohongshu:1348` 等）；封面处理 9-10 处（`_set_thumbnail`/`_upload_cover`）；`_get_account_cookie_file` 10 个 blueprint 复制；taobao_guanghe 与 jd 各一套 picker 会话 |
| 7 | **平台元数据双源真相扩散** | 🟠 中 | 高 | `conf.PLATFORM_MAP`（19 平台）vs `PLATFORM_ID_TO_KEY`（含 20:jd）vs registry（注册 1-19，jingmai 委托 jd）vs `image_publish_bp.py:171-183` 平台名→id 映射（**仅 8 平台，与 registry 子集不一致**）vs `ext_api/__init__.py:232-243` id→名映射；前端 platforms.ts 是第 6 份 |
| 8 | **g 对象承载持久化编排（HTTP 层耦合）** | 🟡 中 | 中 | `app.py:90-187` 按 path 字符串 `/postVideo` 硬匹配 → `_record_publish` → `g.publish_detail_id` → after_request 回写；只覆盖视频单发链路，其余链路全部绕过 |
| 9 | **契约细节漂移** | 🟡 中 | 高 | youtube:230、tiktok:145 的 sync_profile 返回旧式 tuple；jd:170 无注解、返回缺 stats 键或 None；jd/platform.py:53,134 留 NotImplementedError 占位；`asyncio.get_event_loop()` 在 async 上下文大量使用（3.12 弃用风险，推断） |
| 10 | **特判下沉到 services 层 + 历史命名残留** | 🟡 低中 | 高 | `services/draft_merge.py:218,231` `if platform == 'douyin'/'xiaohongshu'`；`task_queue.py:261-298` match platform_type case 1-5；ext_api 内联第二张 `drafts` 表与 `init_db.py:56` 双源建表；`routes/frames.py` 平级命名空间残留（仅此一文件） |

**变味本质一句话**：结构层（类继承、注册表、登录泛化）收敛到位，**行为层（发布契约、状态机、浏览器生命周期、平台元数据）大面积分叉**——「结构正确、行为漂移」的典型形态：抽象建起来了，但新平台接入时按最省事路径（复制粘贴 + 各自桥接）演化，抽象约束被逐步架空。

---

## 3. 改进建议（按优先级）

### P0 — 契约收敛（决策先行，阻塞其他项）

**S1. 统一 `publish_video` 契约为单一形态（async）**
- 浏览器自动化本质是 async，推荐全 async：基类改 `async def publish_video`，基类提供 `run_publish_sync()` 同步包装模板方法供旧调用方使用；删掉 `task_queue.py:251-261` 的 `iscoroutinefunction` 分支。
- 同时修复 kuaishou「桥接后无条件 `return True`」的吞失败风险（`kuaishou/platform.py:601-603`），异常改为捕获记录后返回 False。
- 成本：中（20 平台签名 + 3 个调用方）。收益：消除最大契约破坏点，后续所有发布链路共用一份调用语义。

**S2. 发布执行架构三合一（最高杠杆项）**
- 三套队列全部活跃（前端 PublishCenter/草稿批量/图集分别打三套 API），是当前最大的架构负债。建议以能力最完整的 `ext_api/task_queue.py`（持久化 6 态 + SSE + 取消/重试）为唯一执行内核：
  - `/postVideo` 与 `/postVideo/status` 改为 task_queue 的薄适配（保留前端契约）；
  - `/api/image-publish/publish` 与 `/execute-publish` 去掉请求线程内 `asyncio.run`（`image_publish_bp.py:234,561`），入队化；
  - 删除 `/postVideoBatch` 同步循环残留（`publish_bp.py:373-507`，且不写历史——数据完整性缺口）；
  - task_queue 内部旧路径 `myUtils.postVideo.*` 遗留模块（`task_queue.py:248-298`）移除。
- 成本：高（涉及全部发布入口 + 前端联调）。收益：消灭三份状态机、三份写入器、三份超时/取消语义。

### P1 — 状态与元数据单源化

**S3. 历史写入收敛为唯一 writer**：以 `services/publish_history.py` 为唯一落库入口（补 in-flight 状态以对齐 task_queue 语义），删除 task_queue 与 image_publish_bp 的重复 SQL；状态枚举升为共享常量。成本：中。

**S4. 平台元数据单源**：以 registry 类属性（platform_id/key/name）为唯一真源，`conf.PLATFORM_MAP`/`image_publish_bp` 映射/ext_api 映射改为派生（或共享 `platforms` 常量表），补 `image_publish_bp` 8 平台映射与 19 平台 registry 的缺口；前端 platforms.ts 通过接口对齐。成本：低-中。

### P2 — 消除样板与入口绕过

**S5. 浏览器生命周期强制统一**：`browser.close()`/`create_browser_sync` 收敛到基类唯一入口；用一条 AST/正则 lint 规则（或契约单测扫描平台目录）禁止直接调用，CI 门禁。成本：低-中，收益：消除 watchdog 误 cancel 的隐患面。

**S6. 样板上移基类/共享服务**：`_parse_cookie_to_storage_state` 提到基类（平台只需声明 cookie 域列表）；`_set_schedule_time`/`_set_thumbnail`/`_get_account_cookie_file`/`run_async` 收敛为共享函数（参数化平台差异）。成本：中，机械。

**S7. _utils 拆分**：13 个平台专属 `scrape_*` 迁回各自平台目录（对齐 iqiyi/tencent_video/jd 现状），_utils 只保留通用工具（`clear_and_type`/`parse_schedule_time` 等）。成本：中，机械。

### P3 — 治理补强（防再漂移）

**S8. 契约测试升级**：在 `test_base_platform.py` 增加**注册表全量契约断言**——遍历 registry 所有平台类，断言 `publish_video` 全部 async、`sync_profile` 返回 3 键 dict、无 `browser.close()` 直接调用、无 `asyncio.get_event_loop()`。成本：低，收益：把本次发现的行为层漂移变成 CI 红线，成本收益比最高。

**S9. 平台接入清单化**：把 `docs/backend-coding-standards.md:39` 的「新增平台 = impl + bp + registry」扩展为 checklist（含发布契约形态、浏览器生命周期、cookie 域、元数据注册），对齐 P0/P1 收敛后的新契约。

---

## 4. 证据与推断边界

- **证据（直接可查）**：上文所有 `file:line` 引用均为本次实际读取/grep 结果；三套发布路径经前端调用点（`PublishCenter.vue:3153`、`draft.ts:22`、`imagePublish.ts:15`）证实均在生产使用。
- **推断**：`asyncio.get_event_loop()` 在 async 上下文使用属 3.12 弃用风险（未实际运行 3.12 验证）；kuaishou「无条件 return True」是否会真实吞失败取决于其内部是否已自行捕获（未逐行追完该方法）。
- **已消解差异**：分析期间分支从 batch-c 切到 batch-e，先前观察到的 `backend/app.py` 未提交改动属旧检出状态，当前工作区干净。

## 5. 未知项 / 限制

- 未评估：`douyin_image_bp.py:78-160` 的 CloakBrowser fetch API 代理形态是否与 DOM 发布存在能力重叠（第三种交互形态，建议后续单独 review）。
- 未量化：三套发布链路各自的线上使用占比（无法从代码静态判断，需日志/埋点）。
- 未追查：`ext_api` 内联 `drafts` 表与 `init_db.py` 的迁移关系是否已由 Batch D 收敛（Batch D 只覆盖 `init_db` 本身）。

---

## 6. 结论

项目多平台架构的**主干设计是健康的**（抽象基类 + 注册表 + 泛化登录/发布入口 + 前端配置收敛），且团队已在主动做 Batch 式收敛。真正的变味集中在**行为层契约分叉**——尤其是「三套发布执行架构并存且都在生产使用」和「publish_video 同步/异步双轨」，这两项是后续任何多平台扩展（加第 20 个平台）成本飙升的根源。建议按 **S1 → S2 → S8** 的顺序推进：先定契约、再并队列、最后用契约测试把漂移关进 CI。
