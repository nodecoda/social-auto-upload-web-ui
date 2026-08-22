"""发布遥测埋点：选择器失败/页面变更事件落 SQLite（Phase D1）。

动机：页面在变化 —— 为「AI 修复回路 / DSL 决策」提供数据门槛输入
（D2: 残留流程级重复数 + 选择器失败率/月 + 失败类型分布；D3: 自动重试决策）。

设计：
- 表 telemetry_events：occurred_at / platform / step / error_type / message
- 写入 record_event() 全异常兜底：遥测失败绝不影响发布主流程
- 查询 query_events() / failure_stats()：D2 门槛统计的直接输入
- 唯一埋点切面：task_queue._worker 失败分支（发布失败 = 页面漂移的最终信号）
"""
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger

logger = get_channel_logger("telemetry")

DB_PATH = BASE_DIR / "db" / "database.db"

# 错误类型常量（D2 失败类型分布的维度）
ERR_SELECTOR_TIMEOUT = "selector_timeout"  # Playwright 选择器/元素操作超时（页面漂移主信号）
ERR_BROWSER_CLOSED = "browser_closed"      # 用户手动关闭浏览器（非页面漂移，需排除）
ERR_OTHER = "other"

_DDL = """
CREATE TABLE IF NOT EXISTS telemetry_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT '',
    step TEXT NOT NULL DEFAULT '',
    error_type TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT ''
)
"""


def classify_error(exc: Exception) -> str:
    """把发布失败异常分类为可统计的错误类型。

    Playwright 超时（locator.wait_for / wait_for_selector / click 等）消息
    通常含 "Timeout 30000ms exceeded"，是页面漂移（元素不在预期位置）的最
    直接信号；"Browser has been closed" 是用户主动关闭，须排除在漂移统计外。
    """
    msg = str(exc)
    if "has been closed" in msg or "Target page" in msg:
        return ERR_BROWSER_CLOSED
    if "timeout" in msg.lower():
        return ERR_SELECTOR_TIMEOUT
    return ERR_OTHER


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    """连接 DB 并自举遥测表（CREATE TABLE IF NOT EXISTS 幂等，线程安全）。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)  # 目录缺失时自举（测试隔离/首启场景）
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(_DDL)
    conn.commit()
    return conn


def record_event(platform: str, step: str, error_type: str, message: str = "") -> None:
    """写入一条遥测事件。任何异常都吞掉——遥测绝不影响发布主流程。"""
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO telemetry_events (occurred_at, platform, step, error_type, message)"
                " VALUES (?, ?, ?, ?, ?)",
                (_now_iso(), platform, step, error_type, message[:500]),
            )
    except Exception as e:  # noqa: BLE001 -- 遥测失败兜底,不阻断发布主流程
        logger.info('[Telemetry] 事件写入失败: %s', e)


def query_events(platform: str | None = None, step: str | None = None,
                 error_type: str | None = None, since: str | None = None,
                 limit: int = 200) -> list[dict]:
    """遥测事件查询（按平台/步骤/错误类型/时间过滤，最近优先）。"""
    where, params = [], []
    if platform:
        where.append("platform = ?")
        params.append(platform)
    if step:
        where.append("step = ?")
        params.append(step)
    if error_type:
        where.append("error_type = ?")
        params.append(error_type)
    if since:
        where.append("occurred_at >= ?")
        params.append(since)
    sql = "SELECT id, occurred_at, platform, step, error_type, message FROM telemetry_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    try:
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception as e:  # noqa: BLE001 -- 查询兜底,返回空列表（遥测不可用不阻断）
        logger.info('[Telemetry] 查询失败: %s', e)
        return []


def failure_stats(platform: str | None = None, since: str | None = None) -> list[dict]:
    """D2 门槛统计：按 (platform, error_type) 分组的事件计数。"""
    where, params = [], []
    if platform:
        where.append("platform = ?")
        params.append(platform)
    if since:
        where.append("occurred_at >= ?")
        params.append(since)
    sql = "SELECT platform, error_type, COUNT(*) AS cnt FROM telemetry_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY platform, error_type ORDER BY cnt DESC"
    try:
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception as e:  # noqa: BLE001 -- 查询兜底,返回空列表
        logger.info('[Telemetry] 统计失败: %s', e)
        return []
