"""Phase D1 测试：发布遥测埋点（选择器失败/页面变更事件落 SQLite）。

覆盖：
- 错误分类 classify_error：selector_timeout / browser_closed / other
- 事件写入/查询/过滤 roundtrip（临时 DB 隔离）
- failure_stats 分组统计（D2 门槛输入）
- worker 失败分支集成：发布异常 → telemetry 表记录（唯一埋点切面）
"""
import asyncio
import contextlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
import services.telemetry as telemetry
from ext_api.task_queue import PublishTask, TaskQueue
from services.telemetry import (
    ERR_BROWSER_CLOSED,
    ERR_OTHER,
    ERR_SELECTOR_TIMEOUT,
    classify_error,
    failure_stats,
    query_events,
    record_event,
)


def _make_task(task_id='t1'):
    return PublishTask(id=task_id, platform='抖音', account_name='账号A',
                       title='标题A', status=1)  # status=1 占位, worker 会重设


class TestClassifyError:
    def test_selector_timeout(self):
        exc = TimeoutError('locator.wait_for: Timeout 30000ms exceeded.')
        assert classify_error(exc) == ERR_SELECTOR_TIMEOUT

    def test_wait_for_selector_timeout(self):
        exc = TimeoutError('page.wait_for_selector: Timeout 30000ms exceeded.')
        assert classify_error(exc) == ERR_SELECTOR_TIMEOUT

    def test_browser_closed(self):
        exc = RuntimeError('Target page, context or browser has been closed')
        assert classify_error(exc) == ERR_BROWSER_CLOSED

    def test_other(self):
        exc = ValueError('unknown error')
        assert classify_error(exc) == ERR_OTHER


class TestTelemetryDB:
    def test_record_and_query_roundtrip(self, tmp_path):
        with patch.object(telemetry, 'DB_PATH', tmp_path / 'database.db'):
            record_event('抖音', 'publish', ERR_SELECTOR_TIMEOUT, 'locator.wait_for: Timeout')
            record_event('小红书', 'publish', ERR_OTHER, 'boom')
            rows = query_events()
            assert len(rows) == 2
            newest = rows[0]
            assert newest['platform'] == '小红书'
            assert newest['step'] == 'publish'
            assert newest['error_type'] == ERR_OTHER
            assert newest['occurred_at']
            assert newest['id'] > 0

    def test_query_filters(self, tmp_path):
        with patch.object(telemetry, 'DB_PATH', tmp_path / 'database.db'):
            record_event('抖音', 'publish', ERR_SELECTOR_TIMEOUT, 'm1')
            record_event('抖音', 'publish', ERR_OTHER, 'm2')
            record_event('小红书', 'publish', ERR_OTHER, 'm3')
            assert len(query_events(platform='抖音')) == 2
            assert len(query_events(error_type=ERR_OTHER)) == 2
            assert len(query_events(platform='抖音', error_type=ERR_OTHER)) == 1
            assert len(query_events(step='publish', limit=2)) == 2
            assert len(query_events(since='2999-01-01')) == 0  # 未来时间无事件

    def test_record_event_never_raises(self, tmp_path, monkeypatch):
        """遥测失败兜底：DB 异常不向上抛（不影响发布主流程）。"""
        with patch.object(telemetry, 'DB_PATH', tmp_path / 'no-such-dir' / 'x.db'):
            # 目录不存在 → 连接失败 → 内部兜底
            record_event('抖音', 'publish', ERR_OTHER, 'm')  # 不应抛异常

    def test_failure_stats_grouping(self, tmp_path):
        with patch.object(telemetry, 'DB_PATH', tmp_path / 'database.db'):
            record_event('抖音', 'publish', ERR_SELECTOR_TIMEOUT, 'm')
            record_event('抖音', 'publish', ERR_SELECTOR_TIMEOUT, 'm')
            record_event('抖音', 'publish', ERR_OTHER, 'm')
            record_event('小红书', 'publish', ERR_OTHER, 'm')
            stats = failure_stats()
            assert len(stats) == 3
            # cnt DESC 保证：最多的在前；并列(1)顺序未定义 → 排序后比较
            assert stats[0] == {'platform': '抖音', 'error_type': ERR_SELECTOR_TIMEOUT, 'cnt': 2}
            tail = sorted(stats[1:], key=lambda r: (r['platform'], r['error_type']))
            assert tail == [
                {'platform': '小红书', 'error_type': ERR_OTHER, 'cnt': 1},
                {'platform': '抖音', 'error_type': ERR_OTHER, 'cnt': 1},
            ]
            # 平台过滤
            assert len(failure_stats(platform='抖音')) == 2


class TestWorkerTelemetryHook:
    def test_worker_failure_records_telemetry(self, tmp_path):
        """D1 切面集成：worker 失败分支 → telemetry 表有 selector_timeout 记录。"""
        q = TaskQueue(max_concurrent=1)
        task = PublishTask(id='t-err', platform='抖音', account_name='账号A',
                           title='标题A', status=0)
        boom = TimeoutError('locator.wait_for: Timeout 30000ms exceeded.')

        async def scenario():
            q.queue = asyncio.Queue()
            await q.queue.put(task)
            worker = asyncio.create_task(q._worker('w'))
            # 等待失败处理完成（task 进入 completed）
            for _ in range(200):
                if task in q.completed:
                    break
                await asyncio.sleep(0.01)
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker

        with patch.object(q, '_execute', AsyncMock(side_effect=boom)), \
             patch.object(q, '_update_db'), \
             patch.object(q, '_notify_status'), \
             patch.object(telemetry, 'DB_PATH', tmp_path / 'database.db'):
            asyncio.run(scenario())

            assert task in q.completed
            assert task.status.name == 'FAILED'
            rows = query_events()
            assert len(rows) == 1
            assert rows[0]['platform'] == '抖音'
            assert rows[0]['error_type'] == ERR_SELECTOR_TIMEOUT
            assert 'locator.wait_for' in rows[0]['message']

    def test_worker_cancelled_not_recorded(self, tmp_path):
        """用户关闭浏览器（CancelledError）不埋点：非页面漂移信号。"""
        q = TaskQueue(max_concurrent=1)
        task = PublishTask(id='t-cancel', platform='抖音', account_name='账号A',
                           title='标题A', status=0)

        async def scenario():
            q.queue = asyncio.Queue()
            await q.queue.put(task)
            worker = asyncio.create_task(q._worker('w'))
            for _ in range(200):
                if task in q.completed:
                    break
                await asyncio.sleep(0.01)
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker

        with patch.object(q, '_execute', AsyncMock(side_effect=asyncio.CancelledError())), \
             patch.object(q, '_update_db'), \
             patch.object(q, '_notify_status'), \
             patch.object(telemetry, 'DB_PATH', tmp_path / 'database.db'):
            asyncio.run(scenario())

            assert len(query_events()) == 0
