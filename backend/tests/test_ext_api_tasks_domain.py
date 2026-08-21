"""ext_api 任务/队列域契约测试（T35-14）。

覆盖 backend/ext_api/__init__.py 任务域（get_tasks / create_task / get_task /
cancel_task / retry_task / task_stream / queue_status）与
backend/ext_api/task_queue.py 剩余缺口（_build_account_configs /
add_task 自动 start / get_status / on_status_change + _notify_status）。

数据策略：
- 自建独立临时 DB（不污染 conftest 共享库），每个用例结束后清空两张表；
- 线程类行为（TaskQueue.add_task 自动 start）用 mock 短路，避免真实线程/超时等待；
- SSE 直接调用路由函数拿原始 generator 控制迭代与 GeneratorExit。
"""

import json
import queue
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ext_api
from ext_api import _sse_subscribers, app
from ext_api import task_queue as tq_module
from ext_api.task_queue import PublishTask, TaskQueue, TaskStatus

_TMPDIR = tempfile.mkdtemp(prefix='sau_ext_api_tasks_')
DB_PATH = Path(_TMPDIR) / 'db' / 'database.db'

# create_task 合法载荷（各必填字段齐全）
VALID_PAYLOAD = {
    'platformType': 1,
    'accountName': '账号A',
    'accountCookiePath': '/ck.txt',
    'videoPath': '/v.mp4',
    'title': '标题',
}


@pytest.fixture(scope='module', autouse=True)
def _setup_temp_db():
    """自建任务域专用临时库（只建本域需要的两张表）。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS publish_batches (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                account_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                finished_at TIMESTAMP
            );
            """
        )
    yield


@pytest.fixture(autouse=True)
def _redirect_ext_api_db():
    """把 ext_api.DB_PATH 重定向到本文件自建临时库（_db_conn 调用时读取模块全局）。"""
    import ext_api

    original = ext_api.DB_PATH
    ext_api.DB_PATH = DB_PATH
    yield
    ext_api.DB_PATH = original


@pytest.fixture(autouse=True)
def _clean_tables():
    """每个用例结束后清空数据，保证用例间隔离。"""
    yield
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute('DELETE FROM publish_details')
        conn.execute('DELETE FROM publish_batches')


def _insert_batch(batch_id='tb1', title='批次1', btype='video', status='running',
                  created_at='2026-06-01 00:00:00'):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            'INSERT INTO publish_batches (id, type, title, status, account_count, created_at, updated_at)'
            ' VALUES (?, ?, ?, ?, 0, ?, ?)',
            (batch_id, btype, title, status, created_at, created_at),
        )


def _insert_detail(detail_id, batch_id='tb1', account_name='账号A', platform='抖音',
                   account_configs='{}', status='pending', created_at='2026-06-01 10:00:00'):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(
            'INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status, created_at)'
            ' VALUES (?, ?, ?, ?, ?, ?, ?)',
            (detail_id, batch_id, account_name, platform, account_configs, status, created_at),
        )


class _FakeSSEQueue:
    """task_stream 内部 queue.Queue 的可控替身：get 立即返回/抛 Empty，put_nowait 可抛 Full。"""

    def __init__(self, items=None, put_nowait_error=None):
        self.items = list(items or [])
        self.put_nowait_error = put_nowait_error

    def put_nowait(self, item):
        if self.put_nowait_error is not None:
            raise self.put_nowait_error
        self.items.append(item)

    def get(self, timeout=None):
        if not self.items:
            raise queue.Empty
        return self.items.pop(0)


class TestGetTasks:
    """GET /api/v2/tasks：列表/过滤/分页/坏 JSON 兜底/DB 异常"""

    def test_list_default_pagination_meta(self):
        _insert_batch('tb1', '批次1')
        for i in range(1, 6):
            _insert_detail(f'd{i}', batch_id='tb1', status='running' if i <= 3 else 'pending',
                           created_at=f'2026-06-01 10:00:0{i}')

        resp = app.test_client().get('/api/v2/tasks')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['code'] == 200
        assert data['data']['total'] == 5
        assert data['data']['page'] == 1
        assert data['data']['pageSize'] == 20
        items = data['data']['list']
        assert len(items) == 5
        for it in items:
            assert 'batch_id' in it
            assert 'batch_title' in it
            assert 'account_name' in it
            assert it['account_configs'] == {}

    def test_status_filter(self):
        for i in range(1, 6):
            _insert_detail(f'd{i}', status='running' if i <= 3 else 'pending')

        resp = app.test_client().get('/api/v2/tasks?status=running')
        data = resp.get_json()['data']
        assert data['total'] == 3
        assert all(it['status'] == 'running' for it in data['list'])

    def test_status_all_means_no_filter(self):
        for i in range(1, 4):
            _insert_detail(f'd{i}', status='success' if i == 1 else 'failed')
        resp = app.test_client().get('/api/v2/tasks?status=all')
        data = resp.get_json()['data']
        assert data['total'] == 3
        assert len(data['list']) == 3

    def test_pagination_offset(self):
        for i in range(1, 6):
            _insert_detail(f'd{i}', created_at=f'2026-06-01 10:00:0{i}')
        client = app.test_client()
        # created_at DESC：d5, d4, d3, d2, d1
        page1 = client.get('/api/v2/tasks?page=1&pageSize=2').get_json()['data']['list']
        assert [it['id'] for it in page1] == ['d5', 'd4']
        page2 = client.get('/api/v2/tasks?page=2&pageSize=2').get_json()['data']['list']
        assert [it['id'] for it in page2] == ['d3', 'd2']
        page3 = client.get('/api/v2/tasks?page=3&pageSize=2').get_json()['data']['list']
        assert [it['id'] for it in page3] == ['d1']
        # 超界页返回空列表
        page4 = client.get('/api/v2/tasks?page=4&pageSize=2').get_json()['data']['list']
        assert page4 == []

    def test_bad_account_configs_fallback_to_empty_dict(self):
        _insert_detail('d1', account_configs='{broken json')
        resp = app.test_client().get('/api/v2/tasks')
        items = resp.get_json()['data']['list']
        assert len(items) == 1
        assert items[0]['account_configs'] == {}

    def test_db_error_returns_500(self):
        with patch('ext_api._db_conn', side_effect=sqlite3.OperationalError('boom')):
            resp = app.test_client().get('/api/v2/tasks')
        assert resp.status_code == 500
        assert resp.get_json()['code'] == 500
        assert 'boom' in resp.get_json()['msg']


class TestCreateTask:
    """POST /api/v2/tasks：参数校验 / 平台名映射 / PublishTask 构造"""

    def test_no_body_returns_400(self):
        # JSON body 为 'null' 时 get_json() 返回 None，命中 `if not data:` 分支
        resp = app.test_client().post('/api/v2/tasks', data='null', content_type='application/json')
        assert resp.status_code == 400
        assert '不能为空' in resp.get_json()['msg']

    def test_empty_json_body_returns_400(self):
        resp = app.test_client().post('/api/v2/tasks', json={})
        assert resp.status_code == 400
        assert '不能为空' in resp.get_json()['msg']

    @pytest.mark.parametrize('field', ['platformType', 'accountName', 'accountCookiePath', 'videoPath', 'title'])
    def test_missing_required_field_returns_400(self, field):
        payload = dict(VALID_PAYLOAD)
        del payload[field]
        resp = app.test_client().post('/api/v2/tasks', json=payload)
        assert resp.status_code == 400
        assert field in resp.get_json()['msg']

    def test_unknown_platform_type_maps_to_unknown(self):
        fake_tq = MagicMock()
        payload = dict(VALID_PAYLOAD, platformType=999)
        with patch('ext_api.get_task_queue', return_value=fake_tq):
            resp = app.test_client().post('/api/v2/tasks', json=payload)
        assert resp.status_code == 200
        task = fake_tq.add_task.call_args[0][0]
        assert task.platform == '未知'
        assert task.platform_type == 999

    def test_normal_creation_maps_fields_and_defaults(self):
        fake_tq = MagicMock()
        payload = dict(VALID_PAYLOAD, description='描述', thumbnailPath='/th.jpg', tags=['a', 'b'])
        with patch('ext_api.get_task_queue', return_value=fake_tq):
            resp = app.test_client().post('/api/v2/tasks', json=payload)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        task = fake_tq.add_task.call_args[0][0]
        assert data['id'] == task.id
        assert data['status'] == 'pending'
        assert isinstance(task, PublishTask)
        assert task.platform == '小红书'
        assert task.platform_type == 1
        assert task.account_name == '账号A'
        assert task.account_cookie_path == '/ck.txt'
        assert task.video_path == '/v.mp4'
        assert task.title == '标题'
        assert task.description == '描述'
        assert task.thumbnail_path == '/th.jpg'
        assert task.tags == ['a', 'b']

    def test_optional_fields_default_to_empty(self):
        fake_tq = MagicMock()
        with patch('ext_api.get_task_queue', return_value=fake_tq):
            resp = app.test_client().post('/api/v2/tasks', json=VALID_PAYLOAD)
        assert resp.status_code == 200
        task = fake_tq.add_task.call_args[0][0]
        assert task.description == ''
        assert task.thumbnail_path == ''
        assert task.tags == []


class TestGetTask:
    """GET /api/v2/tasks/<detail_id>：404 / 解析 / 兜底 / DB 异常"""

    def test_not_found_returns_404(self):
        resp = app.test_client().get('/api/v2/tasks/not-exist')
        assert resp.status_code == 404
        assert resp.get_json()['msg'] == '任务不存在'

    def test_ok_parses_configs_and_batch_join(self):
        _insert_batch('tb1', '批次A', status='running')
        _insert_detail('d1', batch_id='tb1', account_configs='{"videoLandscape":{"title":"x"}}')

        resp = app.test_client().get('/api/v2/tasks/d1')
        assert resp.status_code == 200
        d = resp.get_json()['data']
        assert d['account_configs'] == {'videoLandscape': {'title': 'x'}}
        assert d['batch_title'] == '批次A'
        assert d['batch_type'] == 'video'

    def test_bad_json_account_configs_fallback(self):
        _insert_detail('d2', account_configs='{broken json')
        resp = app.test_client().get('/api/v2/tasks/d2')
        assert resp.status_code == 200
        assert resp.get_json()['data']['account_configs'] == {}

    def test_db_error_returns_500(self):
        with patch('ext_api._db_conn', side_effect=sqlite3.OperationalError('boom')):
            resp = app.test_client().get('/api/v2/tasks/d1')
        assert resp.status_code == 500
        assert resp.get_json()['code'] == 500


class TestCancelRetryTask:
    """POST /tasks/<id>/cancel、/tasks/<id>/retry：mock get_task_queue 的 True/False 分支"""

    def test_cancel_true_returns_200(self):
        fake_tq = MagicMock()
        fake_tq.cancel_task.return_value = True
        with patch('ext_api.get_task_queue', return_value=fake_tq):
            resp = app.test_client().post('/api/v2/tasks/t1/cancel')
        assert resp.status_code == 200
        assert '已取消' in resp.get_json()['msg']
        fake_tq.cancel_task.assert_called_once_with('t1')

    def test_cancel_false_returns_400(self):
        fake_tq = MagicMock()
        fake_tq.cancel_task.return_value = False
        with patch('ext_api.get_task_queue', return_value=fake_tq):
            resp = app.test_client().post('/api/v2/tasks/t1/cancel')
        assert resp.status_code == 400
        assert '无法取消' in resp.get_json()['msg']

    def test_retry_true_returns_200(self):
        fake_tq = MagicMock()
        fake_tq.retry_task.return_value = True
        with patch('ext_api.get_task_queue', return_value=fake_tq):
            resp = app.test_client().post('/api/v2/tasks/t1/retry')
        assert resp.status_code == 200
        assert '重新入队' in resp.get_json()['msg']
        fake_tq.retry_task.assert_called_once_with('t1')

    def test_retry_false_returns_400(self):
        fake_tq = MagicMock()
        fake_tq.retry_task.return_value = False
        with patch('ext_api.get_task_queue', return_value=fake_tq):
            resp = app.test_client().post('/api/v2/tasks/t1/retry')
        assert resp.status_code == 400
        assert '无法重试' in resp.get_json()['msg']


class TestTaskStream:
    """GET /api/v2/tasks/stream：SSE data 事件 / heartbeat / GeneratorExit 清理 / Full 吞掉"""

    @staticmethod
    def _enter_stream(fake_q):
        """调用路由函数拿原始 generator + 注册的状态回调。"""
        fake_tq = MagicMock()
        with patch('ext_api.queue.Queue', return_value=fake_q), \
                patch('ext_api.get_task_queue', return_value=fake_tq), \
                app.test_request_context():
            resp = ext_api.task_stream()
            return resp.response, fake_tq

    def test_data_event_then_heartbeat(self):
        fake_q = _FakeSSEQueue()
        gen, fake_tq = self._enter_stream(fake_q)
        callback = fake_tq.on_status_change.call_args[0][0]
        callback(PublishTask(id='t-1', status=TaskStatus.RUNNING, platform='抖音',
                             account_name='账号A', title='标题'))
        first = next(gen)
        assert first.startswith('data: ')
        payload = json.loads(first[len('data: '):].strip())
        assert payload['id'] == 't-1'
        assert payload['status'] == 'running'
        assert payload['platform'] == '抖音'
        assert payload['account'] == '账号A'
        assert payload['title'] == '标题'
        assert next(gen) == ': heartbeat\n\n'
        gen.close()
        assert fake_q not in _sse_subscribers

    def test_heartbeat_when_queue_empty(self):
        fake_q = _FakeSSEQueue()
        gen, _ = self._enter_stream(fake_q)
        assert next(gen) == ': heartbeat\n\n'
        gen.close()

    def test_generator_exit_removes_subscriber(self):
        fake_q = _FakeSSEQueue()
        before = len(_sse_subscribers)
        gen, _ = self._enter_stream(fake_q)
        try:
            assert fake_q in _sse_subscribers
            assert len(_sse_subscribers) == before + 1
            next(gen)  # 推进到 yield 点，close 时才能触发 GeneratorExit 清理分支
        finally:
            gen.close()
        assert fake_q not in _sse_subscribers
        assert len(_sse_subscribers) == before

    def test_queue_full_is_swallowed(self):
        fake_q = _FakeSSEQueue(put_nowait_error=queue.Full())
        gen, fake_tq = self._enter_stream(fake_q)
        callback = fake_tq.on_status_change.call_args[0][0]
        callback(PublishTask(id='t-full'))  # put_nowait 抛 Full，不应外泄
        assert fake_q.items == []
        gen.close()


class TestQueueStatus:
    """GET /api/v2/queue/status：pending/running/completed/running_tasks 结构"""

    def test_status_structure(self):
        fake_tq = MagicMock()
        expected = {
            'pending': 2,
            'running': 1,
            'completed': 3,
            'running_tasks': [{'id': 'a', 'platform': '抖音', 'account': 'A', 'title': 'T'}],
        }
        fake_tq.get_status.return_value = expected
        with patch('ext_api.get_task_queue', return_value=fake_tq):
            resp = app.test_client().get('/api/v2/queue/status')
        assert resp.status_code == 200
        assert resp.get_json() == {'code': 200, 'data': expected}


def _sync_start(self):
    """TaskQueue.start 的同步替身：只置状态，不启动真实线程/事件循环。"""
    self._started = True
    self._loop = MagicMock()
    self.queue = MagicMock()


class TestTaskQueueDomain:
    """ext_api/task_queue.py 剩余缺口：_build_account_configs / add_task / get_status / 回调"""

    def test_build_account_configs_full_mapping(self):
        task = PublishTask(
            title='标题', description='描述', tags=['a', 'b'], thumbnail_path='/th.jpg',
            platform_type=3, video_landscape={'a': 1}, video_portrait={'b': 2},
            cover_landscape={'c': 3}, cover_portrait={'d': 4}, video_format='mp4',
            enable_timer=1, schedule_time='2026-06-01 10:00:00', ai_content='AI内容',
            is_original=True,
        )
        cfg = tq_module._build_account_configs(task)
        assert cfg == {
            'title': '标题', 'description': '描述', 'tags': ['a', 'b'],
            'thumbnail_path': '/th.jpg', 'platform_type': 3,
            'videoLandscape': {'a': 1}, 'videoPortrait': {'b': 2},
            'coverLandscape': {'c': 3}, 'coverPortrait': {'d': 4},
            'videoFormat': 'mp4', 'enableTimer': 1,
            'scheduleTime': '2026-06-01 10:00:00', 'aiContent': 'AI内容',
            'isOriginal': True,
        }

    def test_build_account_configs_none_passthrough(self):
        task = PublishTask(platform='抖音', platform_type=3)
        cfg = tq_module._build_account_configs(task)
        assert cfg['title'] == ''
        assert cfg['description'] == ''
        assert cfg['tags'] == []
        assert cfg['thumbnail_path'] == ''
        assert cfg['platform_type'] == 3
        for key in ('videoLandscape', 'videoPortrait', 'coverLandscape', 'coverPortrait',
                    'videoFormat', 'enableTimer', 'scheduleTime', 'aiContent', 'isOriginal'):
            assert cfg[key] is None

    def test_add_task_auto_starts_when_not_started(self):
        q = TaskQueue(max_concurrent=1)
        task = PublishTask(platform='抖音', platform_type=3)
        with patch.object(TaskQueue, 'start', _sync_start), \
                patch.object(q, '_insert_db') as insert, \
                patch.object(tq_module.asyncio, 'run_coroutine_threadsafe') as rct:
            q.add_task(task)
        assert q._started is True
        assert task.status == TaskStatus.QUEUED
        insert.assert_called_once_with(task)
        rct.assert_called_once()

    def test_add_task_skips_start_when_already_started(self):
        q = TaskQueue(max_concurrent=1)
        q._started = True
        q._loop = MagicMock()
        q.queue = MagicMock()
        task = PublishTask(platform='抖音', platform_type=3)
        with patch.object(TaskQueue, 'start', side_effect=AssertionError('不应再调用 start')) as start, \
                patch.object(q, '_insert_db'), \
                patch.object(tq_module.asyncio, 'run_coroutine_threadsafe') as rct:
            q.add_task(task)
        start.assert_not_called()
        assert task.status == TaskStatus.QUEUED
        rct.assert_called_once()

    def test_get_status_initial_empty(self):
        q = TaskQueue(max_concurrent=2)
        assert q.get_status() == {'pending': 0, 'running': 0, 'completed': 0, 'running_tasks': []}

    def test_get_status_with_running_tasks(self):
        q = TaskQueue(max_concurrent=2)
        q.queue = MagicMock()
        q.queue.qsize.return_value = 3
        q.running = {
            'a': PublishTask(id='a', platform='抖音', account_name='账号A', title='标题A'),
            'b': PublishTask(id='b', platform='小红书', account_name='账号B', title='标题B'),
        }
        q.completed = [PublishTask(id='c')]
        status = q.get_status()
        assert status['pending'] == 3
        assert status['running'] == 2
        assert status['completed'] == 1
        assert status['running_tasks'] == [
            {'id': 'a', 'platform': '抖音', 'account': '账号A', 'title': '标题A'},
            {'id': 'b', 'platform': '小红书', 'account': '账号B', 'title': '标题B'},
        ]

    def test_on_status_change_and_notify_swallows_errors(self):
        q = TaskQueue(max_concurrent=1)
        seen = []

        def ok_cb(task):
            seen.append(task.id)

        def bad_cb(task):
            raise RuntimeError('回调爆炸')

        q.on_status_change(ok_cb)
        q.on_status_change(bad_cb)
        task = PublishTask(id='t-cb')
        with patch.object(tq_module.logger, 'info') as log_info:
            q._notify_status(task)  # 不应抛出
        assert seen == ['t-cb']
        assert log_info.call_count == 1
        assert '回调错误' in log_info.call_args[0][0]
