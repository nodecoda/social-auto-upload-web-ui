"""架构整改 #8（队列统一）契约测试。

覆盖：
- 全局任务队列单例强制单并发（max_concurrent=1，替代 publish_executor 单线程语义）；
- _execute payload 透传 + 返回 falsy 判定失败（与旧 /postVideo job 语义一致）；
- worker 异常翻译（浏览器被关 / 通用异常）；
- 浏览器 watchdog cancel 发布子任务时 worker 主循环不被打死（回归测试）；
- _insert_db 对 _before_publish 预插行不重复插入（detail 主键冲突修复）；
- _update_db 聚合时 cancelled 计入失败（避免单条取消误判 batch 成功）；
- /postVideo/status 从 publish_details 读状态（DB 持久化，重启可查）。
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

_tmpdir = tempfile.mkdtemp()
os.environ['SAU_DATA_DIR'] = _tmpdir
DB_PATH = Path(_tmpdir) / "db" / "database.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS publish_batches (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    video_material_id TEXT DEFAULT '',
    image_material_ids TEXT DEFAULT '[]',
    landscape_cover_material_id TEXT DEFAULT '',
    portrait_cover_material_id TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    account_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    schedule_time TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL DEFAULT '',
    draft_id INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS publish_details (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    account_id INTEGER,
    account_name TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    account_configs TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    error_message TEXT NOT NULL DEFAULT '',
    publish_url TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    FOREIGN KEY (batch_id) REFERENCES publish_batches(id) ON DELETE CASCADE
);
"""


def _setup_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()


_setup_db()

from ext_api.task_queue import PublishTask, TaskQueue, TaskStatus, _friendly_error_message


def test_global_singleton_is_single_concurrency():
    """队列统一：全局单例必须单并发，杜绝并发开多个浏览器。"""
    from ext_api import task_queue as tq
    assert tq.task_queue.max_concurrent == 1
    assert tq.get_task_queue() is tq.task_queue


# ---------- _execute payload 路径 ----------

def _make_queue():
    return TaskQueue(max_concurrent=1)


def test_execute_sync_truthy_result_success():
    from ext_api import task_queue as tq

    fake_platform = MagicMock()
    # R5: publish_video 契约已统一为 async
    fake_platform.publish_video = AsyncMock(return_value=True)
    t = PublishTask(platform_type=3, payload={'title': 'X', 'files': ['/a.mp4']})
    with patch.object(tq, 'get_platform', return_value=fake_platform):
        result = asyncio.run(_make_queue()._execute(t))
    assert result is True
    fake_platform.publish_video.assert_called_once_with(title='X', files=['/a.mp4'])


def test_execute_sync_falsy_result_raises_page_not_submitted():
    """返回 falsy = 页面未跳转/校验未通过 → 失败（与旧 publish_executor job 一致）。"""
    from ext_api import task_queue as tq

    fake_platform = MagicMock()
    # R5: publish_video 契约已统一为 async，必须用 AsyncMock
    fake_platform.publish_video = AsyncMock(return_value=False)
    t = PublishTask(platform_type=3, payload={'title': 'X'})
    with patch.object(tq, 'get_platform', return_value=fake_platform):
        try:
            asyncio.run(_make_queue()._execute(t))
        except RuntimeError as e:
            assert '页面未跳转' in str(e)
        else:
            raise AssertionError('falsy 返回值应抛 RuntimeError')


def test_execute_async_falsy_result_raises():
    from ext_api import task_queue as tq

    async def fake_async_publish(**kwargs):
        return None  # falsy

    fake_platform = MagicMock()
    fake_platform.publish_video = fake_async_publish
    t = PublishTask(platform_type=3, payload={'title': 'X'})
    with patch.object(tq, 'get_platform', return_value=fake_platform):
        try:
            asyncio.run(_make_queue()._execute(t))
        except RuntimeError as e:
            assert '页面未跳转' in str(e)
        else:
            raise AssertionError('async falsy 返回值应抛 RuntimeError')


# ---------- worker 异常翻译 ----------

def _run_worker_with_fake_execute(q, tasks, execute_impl):
    """驱动真实 _worker 协程（真实 asyncio.Queue），用 fake _execute 模拟结果。"""
    real_queue = asyncio.Queue()
    for t in tasks:
        real_queue.put_nowait(t)
    q.queue = real_queue
    q.running = {}
    q.completed = []
    q._update_db = MagicMock()
    q._notify_status = MagicMock()
    q._execute = execute_impl

    async def main():
        try:
            await asyncio.wait_for(q._worker('test-worker'), timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            pass  # 正常：无更多任务时 worker 一直阻塞

    asyncio.run(main())


def test_worker_browser_closed_error_translated():
    q = _make_queue()
    t = PublishTask(platform='抖音', platform_type=3)
    t.max_retries = 0

    async def fail_browser_closed(task):
        raise RuntimeError('Target page, context or browser has been closed')

    _run_worker_with_fake_execute(q, [t], fail_browser_closed)
    assert t.status == TaskStatus.FAILED
    assert t.error_message == '用户关闭了浏览器，发布已取消'
    assert q.completed[0] is t


def test_worker_generic_error_prefixed():
    q = _make_queue()
    t = PublishTask(platform='抖音', platform_type=3)
    t.max_retries = 0

    async def fail_generic(task):
        raise RuntimeError('boom')

    _run_worker_with_fake_execute(q, [t], fail_generic)
    assert t.status == TaskStatus.FAILED
    assert t.error_message == '发布失败: boom'


def test_friendly_error_message_helper():
    assert _friendly_error_message(RuntimeError('Browser has been closed')) == '用户关闭了浏览器，发布已取消'
    assert _friendly_error_message(RuntimeError('Target page closed')) == '用户关闭了浏览器，发布已取消'
    assert _friendly_error_message(RuntimeError('boom')) == '发布失败: boom'


# ---------- watchdog 取消子任务不杀 worker（回归） ----------

def _make_watchdog_cancel_publish():
    """模拟 impl/_browser watchdog：第一次发布时 cancel 当前 asyncio task。

    返回 (publish_video, state)；state['cancelled'] 标记第一次已取消。
    """
    state = {'cancelled': False}

    async def publish_video(**kwargs):
        if not state['cancelled']:
            state['cancelled'] = True
            task = asyncio.current_task()
            if task is not None:
                task.cancel()
            await asyncio.sleep(60)  # cancel 是异步投递，此处抛出 CancelledError
        return True

    return publish_video, state


def test_worker_survives_browser_watchdog_cancel():
    """用户关闭浏览器 → watchdog cancel 发布子任务 → 该任务 CANCELLED，
    但 worker 主循环必须存活并继续处理后续任务（防止队列卡死）。"""
    from ext_api import task_queue as tq

    q = _make_queue()
    first = PublishTask(platform='抖音', platform_type=3, payload={'title': 'A'})
    second = PublishTask(platform='抖音', platform_type=3, payload={'title': 'B'})

    real_queue = asyncio.Queue()
    real_queue.put_nowait(first)
    real_queue.put_nowait(second)
    q.queue = real_queue
    q.running = {}
    q.completed = []
    q._update_db = MagicMock()
    q._notify_status = MagicMock()

    fake_platform = MagicMock()
    fake_platform.publish_video, _state = _make_watchdog_cancel_publish()

    async def main():
        with patch.object(tq, 'get_platform', return_value=fake_platform):
            try:
                await asyncio.wait_for(q._worker('test-worker'), timeout=3.0)
            except (TimeoutError, asyncio.CancelledError):
                pass

    asyncio.run(main())

    # 第一个任务被 watchdog cancel → CANCELLED + 友好文案
    assert first.status == TaskStatus.CANCELLED
    assert first.error_message == '用户关闭了浏览器，发布已取消'
    # 第二个任务必须仍被处理成功 —— worker 没有被 cancel 连带打死
    assert second.status == TaskStatus.SUCCESS
    assert real_queue._unfinished_tasks == 0


# ---------- _insert_db 预插行不重复（detail 主键冲突修复） ----------

def test_insert_db_ignores_preexisting_detail_row():
    """_before_publish 已插入 detail 行（id == task.id）时，_insert_db 不得重复/覆盖。"""
    from ext_api import task_queue as tq_module
    # A1: 状态回写收敛到 services.publish_history（唯一 writer），两处 DB_PATH 都要指向测试库
    with patch.object(tq_module, 'DB_PATH', DB_PATH), \
            patch('services.publish_history.DB_PATH', DB_PATH):
        # 预插 batch + detail（模拟 app._before_publish）
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT OR IGNORE INTO publish_batches (id, type, title, status, created_at, updated_at) "
            "VALUES ('qb-1', 'video', '标题', 'running', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status, created_at) "
            "VALUES ('qd-1', 'qb-1', '账号A', '抖音', '{\"title\":\"原标题\"}', 'running', '2026-01-01T00:00:00')"
        )
        conn.commit()
        conn.close()

        task = PublishTask(
            id='qd-1', batch_id='qb-1', platform='抖音', platform_type=3,
            account_name='账号A', title='任务标题', tags=['x'], payload={'title': '任务标题'},
        )
        q = _make_queue()
        q._insert_db(task)

        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        details = conn.execute("SELECT * FROM publish_details WHERE id='qd-1'").fetchall()
        conn.close()
        assert len(details) == 1, '不得重复插入 detail 行'
        # 预插行的 account_configs / status 保持原样（不被 _insert_db 覆盖）
        assert json.loads(details[0]['account_configs']) == {'title': '原标题'}
        assert details[0]['status'] == 'running'


# ---------- _update_db cancelled 计入失败聚合 ----------

def test_update_db_cancelled_counts_as_failed_in_batch():
    """单条 cancelled detail 不应让 batch 误判 success，应聚合为 failed。"""
    from ext_api import task_queue as tq_module
    # A1: 状态回写收敛到 services.publish_history（唯一 writer），两处 DB_PATH 都要指向测试库
    with patch.object(tq_module, 'DB_PATH', DB_PATH), \
            patch('services.publish_history.DB_PATH', DB_PATH):
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT OR IGNORE INTO publish_batches (id, type, title, status, created_at, updated_at) "
            "VALUES ('qb-c', 'video', 'T', 'pending', '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO publish_details (id, batch_id, account_name, platform, status, created_at) "
            "VALUES ('qd-c', 'qb-c', 'A', '抖音', 'cancelled', '2026-01-01T00:00:00')"
        )
        conn.commit()
        conn.close()

        task = PublishTask(id='qd-c', batch_id='qb-c', platform_type=3, status=TaskStatus.CANCELLED)
        q = _make_queue()
        q._update_db(task)

        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute("SELECT status, failed_count FROM publish_batches WHERE id='qb-c'").fetchone()
        conn.close()
        assert row[0] == 'failed', f'cancelled 应聚合为 failed，实际 {row[0]}'
        assert row[1] == 1


# ---------- /postVideo/status DB 查询映射 ----------

_STATUS_DETAILS_DDL = """
CREATE TABLE IF NOT EXISTS publish_details (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    account_id INTEGER,
    account_name TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    account_configs TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    error_message TEXT NOT NULL DEFAULT '',
    publish_url TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);
"""


def _status_client_db():
    """建只含 publish_details 的临时 DB，预插多条状态行，返回 (db, client)。"""
    import tempfile as _tf

    from app import app
    tmp = _tf.mkdtemp(prefix='sau_pq_status_')
    db = Path(tmp) / 'database.db'
    conn = sqlite3.connect(str(db))
    conn.executescript(_STATUS_DETAILS_DDL)
    rows = [
        ('s-ok', 'success', '', '2026-01-01T00:00:00'),
        ('s-fail', 'failed', '发布失败: boom', '2026-01-01T00:00:00'),
        ('s-cancel', 'cancelled', '用户关闭了浏览器，发布已取消', '2026-01-01T00:00:00'),
        ('s-run', 'running', '', '2026-01-01T00:00:00'),
        ('s-queued', 'queued', '', '2026-01-01T00:00:00'),
    ]
    conn.executemany(
        "INSERT INTO publish_details (id, batch_id, status, error_message, created_at) "
        "VALUES (?, 'qb', ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    client = app.test_client()
    return db, client


def _get_status(client, db, task_id):
    with patch('blueprints.publish_bp.DB_PATH', db):
        return client.get(f'/postVideo/status/{task_id}')


def test_status_success_mapping():
    db, client = _status_client_db()
    body = _get_status(client, db, 's-ok').get_json()
    assert body['code'] == 200
    assert body['data']['status'] == 'success'
    assert body['data']['msg'] == '发布成功'
    assert body['data']['submittedAt'] == '2026-01-01T00:00:00'


def test_status_failed_mapping_uses_error_message():
    db, client = _status_client_db()
    body = _get_status(client, db, 's-fail').get_json()
    assert body['data']['status'] == 'failed'
    assert body['data']['msg'] == '发布失败: boom'


def test_status_cancelled_maps_to_failed():
    db, client = _status_client_db()
    body = _get_status(client, db, 's-cancel').get_json()
    assert body['data']['status'] == 'failed'
    assert body['data']['msg'] == '用户关闭了浏览器，发布已取消'


def test_status_running_and_queued_passthrough():
    db, client = _status_client_db()
    assert _get_status(client, db, 's-run').get_json()['data']['status'] == 'running'
    assert _get_status(client, db, 's-queued').get_json()['data']['status'] == 'queued'


def test_status_missing_404():
    db, client = _status_client_db()
    r = _get_status(client, db, 'no-such')
    assert r.status_code == 404
    assert r.get_json()['code'] == 404
