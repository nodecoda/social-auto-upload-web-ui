"""发布状态枚举 + batch 聚合（R7 唯一真源）。

从 ext_api/task_queue.py 提取：状态字面量与聚合逻辑曾散落在
task_queue（6 态）/ publish_history（4 态，缺 in-flight）/ image_publish_bp
（行内 INSERT）三处，语义漂移的根源。R7 后本模块是全仓唯一定义点，
task_queue / publish_history / blueprints 统一引用。

依赖面：仅标准库，无任何项目 import，可安全被 services/ext_api/blueprints 引用。
"""
from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


def aggregate_batch_status(*, succ: int, fail: int, in_flight: int, total: int) -> str:
    """根据 detail 状态聚合 batch 状态。

    优先级：
      1. total == 0        -> 'pending'    （无 detail，理论不该发生）
      2. in_flight > 0     -> 'running'    （仍有 queued/running detail 未结束）
      3. fail == 0         -> 'success'    （全部成功）
      4. succ == 0         -> 'failed'     （全部失败）
      5. 其余              -> 'partial'    （混合成功+失败）
    """
    if total == 0:
        return 'pending'
    if in_flight > 0:
        return 'running'
    if fail == 0:
        return 'success'
    if succ == 0:
        return 'failed'
    return 'partial'
