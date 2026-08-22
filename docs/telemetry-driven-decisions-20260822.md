# 遥测驱动决策评审：DSL 试点 + 自动重试（Phase D2/D3 · 2026-08-22）

> 状态：**初评（数据采集窗口开启）**——正式数据评审于 ≥4 周遥测后触发（2026-09-19 前后）。
> 依据：`docs/multiplatform-architecture-review-20260822.md` 决策门槛 + `.omx/plans/20260822-multiplatform-refactor-prd.md` Phase D。
> 前置：D1 遥测已上线（PR #173，`services/telemetry.py`，发布失败事件落 `telemetry_events` 表）。

---

## 1. 决策门槛回顾

| 决策 | 门槛（数据） | 触发分支 |
|---|---|---|
| **D2 DSL 试点** | 残留流程级重复数 + 选择器失败率/月 + 失败类型分布 | (a) 重复≈0 且失败以漂移为主 → **不做 DSL**，转 AI 修复回路课题；(b) 仍存流程级重复 → 仅 1-2 个高变更平台做声明化试点（单平台 PR） |
| **D3 自动重试** | 重复上传误触发风险 + 可恢复失败占比 | 未过门槛不启用；过门槛且幂等前提成立 → 仅对幂等 detail 的 selector_timeout 做 1 次重试 |

## 2. 现状证据（2026-08-22 初评）

### 2.1 流程级重复：A-C 已大幅收敛（代码级证据，非遥测）

| 阶段 | 收敛动作 | 结果 |
|---|---|---|
| A1 | 原语库（schedule/fill_title/thumbnail/_datetime）+ 参数数据表 | 15 平台 32 条数据表，平台无硬编码重复 |
| A2 | `_set_schedule_time` 收敛到 `primitives/schedule.py` | schedule×14 归零 |
| A3 | `_fill_title` 收敛到 `primitives/fill_title.py` | fill_title×8 归零 |
| A4 | `_set_thumbnail`/cover 收敛到 `primitives/thumbnail.py` | thumbnail×8 + cover×2 归零 |
| B | 会话探针 + 4 态分类器（基类） | check_cookie 20 平台 override 归零 |

**初评**：plan A-D 覆盖的流程级重复原语已全部收敛，「残留流程级重复」当前≈0（按原定义域）。**不满足分支 (b) 的触发前提**。

### 2.2 选择器失败率/月 + 失败类型分布：**数据采集中（0 数据）**

- D1 埋点 2026-08-22 上线（发布失败 = 页面漂移最终信号，唯一汇聚点 `task_queue._worker` 失败分支）
- 错误分类：`selector_timeout`（漂移主信号）/ `browser_closed`（用户关浏览器，剔除）/ `other`
- 统计入口：`failure_stats(platform, since)`（平台×类型计数）——D2 门槛直接输入
- **当前 `telemetry_events` 为空**：无 ≥4 周样本，任何数据驱动结论均不成立

### 2.3 自动重试相关风险（架构级证据）

- 重试自架构整改 #8 起**禁用**（C4 再次确认）：长耗时任务（视频上传）失败立即 FAILED，避免「同一任务再次开浏览器重新上传」误触发
- 任务失败落 C1 失败注册表，requeue 由人工 `retry_task` 显式触发（注册表条目带 TTL 7 天）
- C3 幂等守卫 `_detail_already_success` 已就位（detail 已成功跳过发布）——自动重试的**幂等前提**已具备

## 3. 决策结论（初评）

### D2：不做 DSL 试点，转 AI 修复回路课题

- 流程级重复已由 A-C 收敛（§2.1），不满足分支 (b) 触发前提
- DSL 提案（`docs/dsl-design-proposal.md`）的漂移处置本就走「离线 AI 修复回路」（§11.4），与现状一致
- **结论**：维持「不引入 DSL」；页面漂移问题作为 **AI 修复回路课题**推进（AI 一次性修复 + 编译器门禁 + 探针验证，运行时零 LLM）
- **复核触发点**：≥4 周遥测后，若 `failure_stats` 显示某平台 selector_timeout 占比异常高（漂移集中），对该平台单独评估（仍走单平台 PR，不全局引入）

### D3：自动重试不启用

- 重复上传误触发风险（长耗时任务）> 可恢复失败收益（当前无可恢复失败占比数据）
- **结论**：维持禁用；人工 requeue 回路（C1 注册表）为唯一恢复途径
- **复核触发点**：≥4 周遥测后，若满足「selector_timeout 占比高 ∧ 幂等 detail 无重复上传误触发（C3 守卫生效）∧ 平台失败可安全重试」三条件，再开单议题评审（仅幂等 detail 的 1 次重试上限）

## 4. 数据采集计划

| 项 | 说明 |
|---|---|
| 采集对象 | 发布流程失败事件（平台/步骤/错误类型/时间/消息） |
| 采集起点 | 2026-08-22（D1 上线） |
| 复核时间 | ≥4 周后（2026-09-19 前后），数据量不足则顺延 |
| 触发动作 | `failure_stats()` 查询 → 生成正式评审报告 → 按 §3 结论复核 |
| 数据不足兜底 | 未过门槛 → 维持现状（不引入 DSL、不启用自动重试），AI 修复回路照常推进 |

---

## 附录：如何复核

```bash
cd backend && ./.venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, '.')
from services.telemetry import failure_stats, query_events
# 按平台×错误类型分布（D2 门槛）
print(failure_stats())
# 近 30 天选择器超时事件明细（漂移定位）
print(query_events(error_type='selector_timeout', since='2026-08-22', limit=50))
EOF
```
