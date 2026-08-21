"""发布历史写入：publish_batches + publish_details 两条聚合表。

从 app.py 单体迁移（域重构），app.py 的 _before_publish/_after_publish 钩子
与 blueprints/publish_bp 的后台 job 共用同一份写入逻辑。
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
                    content_type='video', image_material_ids=''):
    """插 1 行 publish_batches（如果不存在）+ 1 行 publish_details。

    R7: 唯一落库入口。video（app.py 预插 / task_queue 草稿批量）与 image
    （image_publish_bp 预插）统一走本函数；batch 行同时携带
    video_material_id 与 image_material_ids 两列，按 content_type 填其一，
    另一个空串。
    """
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            # batch 用 INSERT OR IGNORE，多次同 batchId 调用只插一次
            conn.execute(
                """INSERT OR IGNORE INTO publish_batches
                   (id, type, title, description, video_material_id,
                    image_material_ids,
                    landscape_cover_material_id, portrait_cover_material_id,
                    account_count, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending', ?, ?)""",
                (batch_id, content_type, title, description, video_material_id,
                 image_material_ids,
                 landscape_cover_material_id, portrait_cover_material_id,
                 started_at, started_at)
            )
            conn.execute(
                """INSERT INTO publish_details
                   (id, batch_id, account_id, account_name, platform, account_configs,
                    status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (detail_id, batch_id, account_id, account_name, platform,
                 json.dumps(account_configs, ensure_ascii=False), status, started_at)
            )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[History] 记录发布失败: {e}")
def _update_publish_result(detail_id, status, finished_at, error_message=""):
    """更新 1 行 publish_details + 聚合 publish_batches 状态。

    R7: 聚合逻辑统一走 util.status.aggregate_batch_status（补 in-flight 态，
    与 task_queue._update_db 语义一致：还有 queued/running detail 时 batch 保持
    'running'，不再被误判为 success/failed）。
    """
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "UPDATE publish_details SET status=?, finished_at=?, error_message=? WHERE id=?",
                (status, finished_at, error_message, detail_id)
            )
            # 拿 batch_id
            row = conn.execute(
                "SELECT batch_id FROM publish_details WHERE id=?", (detail_id,)
            ).fetchone()
            if not row:
                return
            batch_id = row[0]
            # 聚合：success / failed / in-flight（queued+running）
            counts = conn.execute(
                """SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_n,
                    SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_n,
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


