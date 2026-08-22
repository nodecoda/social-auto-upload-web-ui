"""Phase C1-C3 测试：失败注册表 + 健康计数/heartbeat + 重启恢复幂等。

C1: FailedJobRegistry 语义（入册 / requeue / TTL 清理 / 观测快照）
C2: 健康计数 j_complete/j_failed/j_retried/j_ongoing + heartbeat
C3: 重启恢复（in-flight 标记可重跑，不自动入队）+ 幂等核对（detail 已成功跳过）
"""
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from ext_api.task_queue import PublishTask, TaskQueue, TaskStatus

_ISO = lambda dt: dt.replace(tzinfo=None).isoformat()  # noqa: E731


def _make_task(task_id='t1', status=TaskStatus.FAILED):
    return PublishTask(id=task_id, platform='抖音', account_name='账号A',
                       title='标题A', status=status, error_message='boom')


class TestC1FailedRegistry:
    def test_failed_task_enters_registry(self):
        q = TaskQueue(max_concurrent=1)
        task = _make_task()
        # 模拟 _worker finally 分支（跳过真实线程）
        q.completed.append(task)
        q.failed_registry[task.id] = {"task": task, "failed_at": _ISO(datetime.now(UTC))}
        assert task.id in q.failed_registry
        assert q.get_failed_tasks()[0]['error_message'] == 'boom'

    def test_requeue_removes_from_registry(self):
        q = TaskQueue(max_concurrent=1)
        task = _make_task()
        q.completed.append(task)
        q.failed_registry[task.id] = {"task": task, "failed_at": _ISO(datetime.now(UTC))}
        q.queue = MagicMock()
        q._loop = MagicMock()
        with patch.object(q, '_update_db'), \
             patch('ext_api.task_queue.asyncio.run_coroutine_threadsafe'):
            ok = q.retry_task('t1')
        assert ok is True
        assert task.id not in q.failed_registry  # requeue 后移出注册表
        assert task.status == TaskStatus.QUEUED
        assert task.retry_count == 0

    def test_retry_unknown_task_false(self):
        q = TaskQueue(max_concurrent=1)
        q.queue = MagicMock()
        q._loop = MagicMock()
        assert q.retry_task('nope') is False

    def test_retry_fallback_completed_path(self):
        """注册表为空时回退旧 completed 路径（向后兼容）。"""
        q = TaskQueue(max_concurrent=1)
        task = _make_task()
        q.completed.append(task)
        q.queue = MagicMock()
        q._loop = MagicMock()
        with patch.object(q, '_update_db'), \
             patch('ext_api.task_queue.asyncio.run_coroutine_threadsafe'):
            ok = q.retry_task('t1')
        assert ok is True
        assert task not in q.completed
        assert task.status == TaskStatus.QUEUED

    def test_ttl_cleanup_expired(self):
        q = TaskQueue(max_concurrent=1)
        old = _make_task('old')
        fresh = _make_task('fresh')
        q.failed_registry['old'] = {
            "task": old,
            "failed_at": _ISO(datetime.now(UTC) - timedelta(days=8)),  # 超 TTL
        }
        q.failed_registry['fresh'] = {
            "task": fresh,
            "failed_at": _ISO(datetime.now(UTC)),
        }
        q._cleanup_failed_registry()
        assert 'old' not in q.failed_registry
        assert 'fresh' in q.failed_registry

    def test_ttl_cleanup_bad_timestamp(self):
        q = TaskQueue(max_concurrent=1)
        q.failed_registry['bad'] = {"task": _make_task('bad'), "failed_at": "not-a-date"}
        q._cleanup_failed_registry()
        assert 'bad' not in q.failed_registry


class TestC2HealthCounts:
    def test_health_counts_snapshot(self):
        q = TaskQueue(max_concurrent=2)
        q.queue = MagicMock()
        q.queue.qsize.return_value = 2
        q.running = {'r1': PublishTask(id='r1', status=TaskStatus.RUNNING)}
        q.completed = [
            PublishTask(id='s1', status=TaskStatus.SUCCESS),
            PublishTask(id='s2', status=TaskStatus.SUCCESS, retry_count=1),
            PublishTask(id='f1', status=TaskStatus.FAILED),
            PublishTask(id='c1', status=TaskStatus.CANCELLED),
        ]
        status = q.get_status()
        assert status['j_complete'] == 2
        assert status['j_failed'] == 1
        assert status['j_cancelled'] == 1
        assert status['j_retried'] == 1
        assert status['j_ongoing'] == 3  # pending 2 + running 1
        assert status['failed_count'] == 0

    def test_heartbeat_touch_updates(self):
        q = TaskQueue(max_concurrent=1)
        q._touch_heartbeat()
        assert q.heartbeat != ''
        before = q.heartbeat
        q._touch_heartbeat()
        assert q.heartbeat != before  # iso 秒级精度，两次调用通常不同；仅验证非空时序
        assert q.heartbeat >= before

    def test_start_records_started_at_and_heartbeat(self):
        q = TaskQueue(max_concurrent=1)
        with patch.object(TaskQueue, '_run_loop'), \
             patch.object(TaskQueue, '_worker'):
            q._started = False
            q._ready = MagicMock()
            q._ready.wait.return_value = True
            q._thread = MagicMock()
            q.start()
        assert q.started_at != ''
        assert q.heartbeat != ''


class TestC3RecoverAndIdempotency:
    def test_recover_marks_inflight_failed(self):
        q = TaskQueue(max_concurrent=1)
        fake_rows = [('d1',), ('d2',)]
        with patch('ext_api.task_queue._sqlite3') as fake_sqlite:
            conn = MagicMock()
            conn.execute.return_value.fetchall.return_value = fake_rows
            fake_sqlite.connect.return_value = conn
            with patch('services.publish_history._update_publish_result') as upd:
                n = q.recover_interrupted_tasks()
        assert n == 2
        assert upd.call_count == 2
        assert upd.call_args_list[0].kwargs['status'] == TaskStatus.FAILED

    def test_recover_none_returns_zero(self):
        q = TaskQueue(max_concurrent=1)
        with patch('ext_api.task_queue._sqlite3') as fake_sqlite:
            conn = MagicMock()
            conn.execute.return_value.fetchall.return_value = []
            fake_sqlite.connect.return_value = conn
            with patch('services.publish_history._update_publish_result'):
                assert q.recover_interrupted_tasks() == 0

    def test_recover_does_not_auto_requeue(self):
        """C4: 恢复仅标记，不自动入队。"""
        q = TaskQueue(max_concurrent=1)
        with patch('ext_api.task_queue._sqlite3') as fake_sqlite:
            conn = MagicMock()
            conn.execute.return_value.fetchall.return_value = [('d1',)]
            fake_sqlite.connect.return_value = conn
            with patch('services.publish_history._update_publish_result'):
                n = q.recover_interrupted_tasks()
        assert n == 1
        assert q.queue is None  # 不触队列

    def test_idempotency_skip_already_success(self):
        """C3: detail 已成功 → _execute 直接返回 True，不调平台发布。"""
        q = TaskQueue(max_concurrent=1)
        task = PublishTask(id='d-succ', detail_id='d-succ', platform_type=3,
                           payload={'title': 't'}, publish_kind='video')
        with patch.object(q, '_detail_already_success', return_value=True) as probe, \
             patch('ext_api.task_queue.get_platform') as gp:
            result = asyncio.run(q._execute(task))
        assert result is True
        probe.assert_called_once_with('d-succ')
        gp.assert_not_called()

    def test_idempotency_probe_not_success_executes(self):
        q = TaskQueue(max_concurrent=1)
        task = PublishTask(id='d-fresh', detail_id='d-fresh', platform_type=3,
                           payload={'title': 't'}, publish_kind='video')
        fake = MagicMock()
        fake.publish_video = AsyncMock(return_value=True)
        with patch.object(q, '_detail_already_success', return_value=False), \
             patch('ext_api.task_queue.get_platform', return_value=fake):
            result = asyncio.run(q._execute(task))
        assert result is True
        fake.publish_video.assert_awaited_once()

    def test_detail_already_success_db_probe(self):
        q = TaskQueue(max_concurrent=1)
        with patch('ext_api.task_queue._sqlite3') as fake_sqlite:
            conn = MagicMock()
            conn.execute.return_value.fetchone.return_value = ('success',)
            fake_sqlite.connect.return_value = conn
            assert q._detail_already_success('d1') is True

    def test_detail_already_success_db_probe_miss(self):
        q = TaskQueue(max_concurrent=1)
        with patch('ext_api.task_queue._sqlite3') as fake_sqlite:
            conn = MagicMock()
            conn.execute.return_value.fetchone.return_value = None
            fake_sqlite.connect.return_value = conn
            assert q._detail_already_success('d1') is False
