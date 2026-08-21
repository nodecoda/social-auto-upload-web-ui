# 架构整改清单（按 ROI 排序 · 2026-08-22）

> 输入：`docs/multiplatform-architecture-review-20260822.md`（架构审查 S1-S9）+ `docs/dsl-design-proposal.md`（review 后补充：DSL 为长期演进，非近期必做）。
> 排序口径：**风险消除 × 扩展性收益 ÷ 成本（人日）**。证据已按当前代码（Batch E 合并后）复核，见 §4。
> 全部 9 项均源自 review 结论，未新增范围；DSL 提案单独列在 §3 作为受此清单治理的前置依赖。

---

## 0. 速览

| 序 | 项 | 对应 review 建议 | 成本 | 主要收益 | 阻塞谁 |
|---|---|---|---|---|---|
| R1 | 注册表全量契约测试 | S8 | 0.5 人日 | 漂移变 CI 红线 | 全后端扩展 |
| R2 | kuaishou 吞失败修复 | S1 子项 | 0.5 人日 | 消除静默发布失败 | — |
| R3 | 平台接入 checklist 落盘 | S9 | 0.5 人日 | 新平台接入规范化 | 未来第 20+ 平台 |
| R4 | 平台元数据单源 | S4 | 2 人日 | 消灭 19 vs 8 映射缺口 | DSL 元数据层 |
| R5 | publish_video 契约定为全 async | S1 主体 | 3-5 人日 | 消除最大契约分叉 | R6 队列合并 |
| R6 | 发布执行三套合一（task_queue 为核） | S2 | 8-12 人日 | 消灭三份状态机/写入器/超时语义 | DSL 落地 |
| R7 | 历史写入唯一 writer | S3 | 2-3 人日 | 状态语义统一 + 数据完整性 | R6 之后才无冲突 |
| R8 | 浏览器生命周期强制统一 | S5 | 2-3 人日 | 消除 watchdog 误 cancel 隐患 | — |
| R9 | 样板上移 + _utils 拆分 | S6+S7 | 5-8 人日 | 机械去重，接入成本下降 | R5 之后（少返工） |

---

## 1.5 执行进度（2026-08-22 更新）

| 项 | 状态 | 提交/说明 |
|---|---|---|
| R1 契约测试 | ✅ done | `e454576`：test_platform_contracts.py 全量断言（结构/元数据/browser.close 直调/get_event_loop/吞失败），现 7 用例全绿 |
| R2 吞失败修复 | ✅ done | `e454576`：12 个 sync 平台 publish_video 的 asyncio.run 加 try/except 返回 False（含 jd 补漏） |
| R3 平台接入 checklist | ✅ done | `6edcc75`：backend-coding-standards.md 新增 7 项 checklist |
| R4 元数据单源 | ✅ done | `c334f2f`：conf/ext_api/image_publish_bp 映射收敛 registry 派生（懒加载防循环依赖），image_publish_bp 补齐 19 平台 |
| R5 publish_video 全 async | ✅ done | `434ac23`：14 平台 async 化 + 契约红线(注册表全 async) + task_queue 统一 create_task；修复 R2 回归(jd/kuaishou 校验被吞)；13 publish + 9 DOM 测试同步 asyncio.run（轻量 299 passed，DOM 留 CI） |
| R6 队列三合一 | ✅ done | `bf26ac8`：image_publish 2 路由入队化(publish_images/execute_publish)、删 postVideoBatch(132 行)、task_queue 按 publish_kind 分发 + 清 myUtils 旧路径、create_task payload 化(registry 真源校验)、3 平台 publish_image async 化（轻量 332 passed，DOM 留 CI） |
| R7 历史唯一 writer | ⏳ 待做 | 依赖 R6 |
| R8 浏览器生命周期 | ✅ done | `e454576`：impl 59 处 → self.close_browser、19 处 _launch → asyncio.run(close_browser)、blueprint 16 处 → close_browser、全仓 get_event_loop 清零 |
| R9 样板上移 + _utils 拆分 | ⏳ 待做 | 依赖 R5 防返工 |

> 验证限制：本机内存 3.7GB，重型 DOM 测试（20 个 `*_platform_dom.py`）多次 OOM 未跑全；
> kuaishou/xiaohongshu/bilibili 三个代表性 DOM 已通过。全量验证在 CI 进行。
> 未跑重型 DOM 测试为明确验证缺口，合并前需 CI 4 checks 全绿兜底。

## 1. 明细（按 ROI 降序）

### R1 🔥 注册表全量契约测试（0.5 人日 · ROI 最高）
- **做什么**：`test_base_platform.py` 增加遍历 registry 的断言——`publish_video` 全部 async（R5 后）、`sync_profile` 返回 3 键 dict、平台目录无 `browser.close()` 直调（R8 后）、无 `asyncio.get_event_loop()`。
- **为什么最高**：成本半天，把本次 review 发现的全部行为层漂移变成 CI 红线；后端 CI 4 道已有，加一个文件即生效。
- **顺序**：先行——R2/R5/R8 做完一步，此测试锁一步，防止下一批 Batch 再漂移。

### R2 🔧 kuaishou 吞失败修复（0.5 人日）
- **证据**：`backend/impl/kuaishou/platform.py:600-625` —— `asyncio.run(self._publish_video_async(**kwargs))` 后**无条件 `return True`**，`_publish_video_async` 内部异常若已自行捕获（未逐行追完）则失败被静默吞掉，发布结果假成功。
- **改法**：异常捕获后记录并 `return False`，与其余平台对齐；补 1 条单测锁定「async 异常 → 返回 False」。

### R3 📋 平台接入 checklist 落盘（0.5 人日）
- **做什么**：把 `docs/backend-coding-standards.md:39` 的「新增平台 = impl + bp + registry」扩展为 checklist：契约形态（async/sync）、浏览器生命周期入口、cookie 域声明、元数据注册（R4 后为派生）、必要单测。
- **为什么靠前**：成本半天，直接决定第 20+ 个平台的接入成本；与 R1 互为表里（checklist 管人、契约测试管 CI）。

### R4 🎯 平台元数据单源（2 人日）
- **证据**：`conf.PLATFORM_MAP`（19）vs registry（20）vs `image_publish_bp` 映射（8）三处独立维护，已出现缺口；前端 `platforms.ts` 再一份。
- **改法**：以 registry 类属性（platform_id/key/name）为唯一真源，其余全部派生；补 image_publish_bp 缺口。
- **收益**：元数据类缺陷（平台列表漂移）从此不可能；是 DSL（§3）元数据层的前置。

### R5 🔩 publish_video 契约统一为 async（3-5 人日）
- **证据**：基类同步声明 `base_platform.py:158`，6 平台 async、14 平台 sync（13 个各自 `asyncio.run` 桥接 + kuaishou 无条件 True）；调用方被迫 `iscoroutinefunction` 双分支（`task_queue.py:251-261`）。
- **改法**：基类改 `async def publish_video`，提供 `run_publish_sync()` 同步包装模板方法；删双分支。
- **依赖**：R1 契约测试先建（锁当前形态防误伤），R2 顺带修掉。
- **位置**：在 R6 队列合并**之前**——队列合一是最大重构，不能让三套队列带着分裂契约合并。

### R6 🏗️ 发布执行三套合一（8-12 人日 · 最大杠杆）
- **证据**：三套活跃生产路径——`publish_bp.postVideo`（已接入 task_queue，Batch E 完成一半）、`image_publish_bp`（请求线程内 `asyncio.run`，8 处路由/asyncio.run 仍活跃）、`publish_bp.postVideoBatch`（`publish_bp.py:404`，同步循环且不写历史）。
- **改法**：以能力最完整的 `ext_api/task_queue.py`（持久化 6 态 + SSE + 取消/重试）为唯一执行内核：image_publish 入队化、删 postVideoBatch 残留、清 task_queue 内 `myUtils.postVideo.*` 遗留。
- **收益**：消灭三份状态机/写入器/超时/取消语义；是「加第 20 个平台」成本飙升的根治项。
- **依赖**：R5 先行（契约统一后再合队列）；R7 紧随（合并后只剩一个 writer）。

### R7 🗄️ 历史写入唯一 writer（2-3 人日）
- **证据**：`publish_history.py`（4 态）vs `task_queue._insert_db/_update_db`（6 态含 in-flight）vs `image_publish_bp` 行内 INSERT——三份独立 SQL 与状态语义；postVideoBatch 甚至不写历史（数据完整性缺口）。
- **改法**：以 `services/publish_history.py` 为唯一落库入口，补 in-flight 态对齐 task_queue；状态枚举升共享常量。
- **顺序**：R6 之后做最顺（合并后只剩两条写入路径可收敛）；也可并行做常量抽取部分。

### R8 🧹 浏览器生命周期强制统一（2-3 人日）
- **证据**：20/20 平台直连 `create_browser_sync`（绕过 `self.create_browser`）、20/20 直连 `browser.close()`（绕过基类 `self.close_browser`，`base_platform.py:97-107` 文档明令）——统一关闭入口形同虚设，watchdog 防误 cancel 的链路被绕开。
- **改法**：收敛到基类唯一入口；R1 契约测试加「禁止直调」断言（或 AST lint 规则）做 CI 门禁。
- **独立**：不依赖 R5/R6，可任意时间插入；建议紧跟 R1 后做（同属生命周期收敛域）。

### R9 🧩 样板上移 + _utils 拆分（5-8 人日 · 机械）
- **证据**：`_parse_cookie_to_storage_state` 16 平台逐字节重复；`_set_schedule_time` 13 同名 + 3 变体；封面处理 9-10 处；`_get_account_cookie_file` 10 个 blueprint 复制；`_utils.py` 1472 行含 13 个平台专属 `scrape_*`（iqiyi/tencent_video/jd 却留在本地，同一职责两种放置）。
- **改法**：cookie 解析/定时/封面/账号路径上移基类或共享服务；13 个 `scrape_*` 迁回各自平台目录。
- **为什么排最后**：纯机械、无风险消除价值，且若在 R5 前做，async 化时会二次返工；等契约收敛后一次性做。

---

## 2. 建议执行顺序（与 Batch 节奏对齐）

```
Phase 1（防漂移，≈1.5 人日）   R1 契约测试骨架 → R3 checklist → R2 吞失败修复
Phase 2（契约收敛，≈5 人日）   R5 async 统一（R1 同步加严）→ R8 浏览器生命周期
Phase 3（结构性合并，≈12 人日） R6 队列三合一 → R7 唯一 writer
Phase 4（机械去重，≈7 人日）   R4 元数据单源（可在 P2 并行）→ R9 样板上移 + _utils 拆分
```

每个 Phase 独立成批 PR，验证基线沿用仓库约定（后端 pytest 3391 + ruff 0 错 + pip-audit 0 漏洞；前端 vitest + 覆盖率 90% + build）。

---

## 3. 与 DSL 提案的关系（review 产物之二）

- `docs/dsl-design-proposal.md`（v0.2）定位为**长期演进方向**，非近期必做；其 §2 明确「不替代发布队列架构，队列合并必须先行」。
- DSL 落地的前置依赖正是本清单：**R4（元数据单源）→ R5（契约形态统一）→ R6（唯一执行内核）**——DSL 是「把动作级 encoding 变成数据」，前提是契约层先稳定。
- **建议**：R1-R9 全部完成后，再评估 DSL 决策点（§13 的 EDSL vs 文本 DSL），届时以 R1 契约测试为回归基线验证 DSL 生成代码等价性。

---

## 4. 复核记录（2026-08-22，Batch E 合并后）

| review 断言 | 复核结果 |
|---|---|
| 20 平台类注册 | ✅ `grep -c "class.*Platform(BasePlatform)" backend/impl/` = 20 |
| publish_video 6 async / 14 sync | ✅ R5 后 20/20 async（契约测试红线锁定） |
| image_publish_bp 仍活跃 | ✅ R6 后 2 处 asyncio.run 全入队化，0 残留 |
| postVideoBatch 残留 | ✅ R6 后已删除（132 行），路由/文档同步清理 |
| 浏览器直连 | ✅ 20/20 直连 `create_browser_sync` 与 `browser.close()` |
| Batch E 半程：postVideo 已入 task_queue | ✅ `publish_bp.py:123-151` 注释与代码一致（单并发承接 publish_executor） |

## 5. 已知限制

- 成本估算为相对人日（单人全栈），未经实际执行校准；Phase 3 是唯一可能超期项，建议单独立项。
- 三套发布链路的线上使用占比无法静态判断，若想给 R6 排优先级可先加一行埋点统计（成本 0.5 人日，未列入清单）。
- kuaishou「无条件 return True」是否真实吞失败取决于 `_publish_video_async` 内部是否已自行捕获异常——已列入 R2 现场确认项。
