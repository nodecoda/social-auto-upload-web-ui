"""发布历史写入：publish_batches + publish_details 两条聚合表。

从 app.py 单体迁移（域重构），app.py 的 _before_publish/_after_publish 钩子
与 blueprints/publish_bp 的后台 job 共用同一份写入逻辑。

R7/A1: 全仓唯一落库入口。task_queue._insert_db/_update_db 与
image_publish_bp._update_image_publish_detail 均已收敛到本模块，
不存在第二份 INSERT/UPDATE publish_batches|publish_details 的实现。
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger

# R7: 状态枚举/聚合唯一真源（task_queue / publish_history / image_publish_bp 共用）
from util.status import aggregate_batch_status

logger = get_channel_logger("publish-history")

DB_PATH = BASE_DIR / "db" / "database.db"

def _record_publish(batch_id, detail_id, platform, account_name, account_id,
                    video_path, title, description, tags, status, started_at,
                    account_configs, video_material_id='',
                    landscape_cover_material_id='',
                    portrait_cover_material_id='',
                    content_type='video', image_material_ids='',
                    source='', draft_id=0):
    """插 1 行 publish_batches（如果不存在）+ 1 行 publish_details。

    R7: 唯一落库入口。video（app.py 预插 / task_queue 草稿批量）与 image
    （image_publish_bp 预插）统一走本函数；batch 行同时携带
    video_material_id 与 image_material_ids 两列，按 content_type 填其一，
    另一个空串。A1: 补充 source/draft_id（草稿批量溯源），detail 用
    INSERT OR IGNORE 保证幂等——/postVideo 链路 app 预插 + 入队双插安全。
    """
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            # batch 用 INSERT OR IGNORE，多次同 batchId 调用只插一次
            conn.execute(
                """INSERT OR IGNORE INTO publish_batches
                   (id, type, title, description, video_material_id,
                    image_material_ids,
                    landscape_cover_material_id, portrait_cover_material_id,
                    account_count, status, created_at, updated_at,
                    source, draft_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending', ?, ?,
                           ?, ?)""",
                (batch_id, content_type, title, description, video_material_id,
                 image_material_ids,
                 landscape_cover_material_id, portrait_cover_material_id,
                 started_at, started_at, source, draft_id)
            )
            conn.execute(
                """INSERT OR IGNORE INTO publish_details
                   (id, batch_id, account_id, account_name, platform, account_configs,
                    status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (detail_id, batch_id, account_id, account_name, platform,
                 json.dumps(account_configs, ensure_ascii=False), status, started_at)
            )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[History] 记录发布失败: {e}")

def _update_publish_result(detail_id, status, finished_at, error_message="",
                           retry_count=None, publish_url=None, started_at=None):
    """更新 1 行 publish_details + 聚合 publish_batches 状态。

    R7/A1: 唯一状态回写入口。聚合逻辑统一走 util.status.aggregate_batch_status；
    A2 定口径：cancelled 归 fail（与 task_queue 旧语义一致），in-flight 保持
    'running'——不再出现 image 旧 4 态聚合的 cancelled→误判 success。
    retry_count/publish_url/started_at 为可选列，None 表示不更新该列。
    """
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            # 动态 SET：只有显式传入的列才更新（默认 None 跳过）
            sets = ["status=?", "finished_at=?", "error_message=?"]
            args = [status, finished_at, error_message]
            if retry_count is not None:
                sets.append("retry_count=?")
                args.append(retry_count)
            if publish_url is not None:
                sets.append("publish_url=?")
                args.append(publish_url)
            if started_at is not None:
                sets.append("started_at=?")
                args.append(started_at)
            args.append(detail_id)
            conn.execute(
                f"UPDATE publish_details SET {', '.join(sets)} WHERE id=?",
                args
            )
            # 拿 batch_id
            row = conn.execute(
                "SELECT batch_id FROM publish_details WHERE id=?", (detail_id,)
            ).fetchone()
            if not row:
                return
            batch_id = row[0]
            # 聚合：success / failed(+cancelled) / in-flight（queued+running）
            counts = conn.execute(
                """SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_n,
                    SUM(CASE WHEN status IN ('failed', 'cancelled') THEN 1 ELSE 0 END) AS failed_n,
                    SUM(CASE WHEN status IN ('queued', 'running') THEN 1 ELSE 0 END) AS in_flight_n
                   FROM publish_details WHERE batch_id=?""",
                (batch_id,)
            ).fetchone()
            total, succ, fail, in_flight = counts[0], counts[1] or 0, counts[2] or 0, counts[3] or 0
            batch_status = aggregate_batch_status(
                succ=succ, fail=fail, in_flight=in_flight, total=total
            )
            conn.execute(
                """UPDATE publish_batches
                   SET status=?, success_count=?, failed_count=?, account_count=?,
                       finished_at=?, updated_at=?
                   WHERE id=?""",
                (batch_status, succ, fail, total, finished_at, finished_at, batch_id)
            )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[History] 更新发布结果失败: {e}")
