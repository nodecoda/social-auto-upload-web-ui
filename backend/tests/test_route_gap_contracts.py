"""路由层残余契约测试（T6，收尾批次）。

覆盖三个 blueprint 的可测残余面：
- image_proxy_bp：缺参 400 / 成功 200 / 抓取异常 500（→ 100%）
- uploads_bp：_guess_file_type 纯函数 / 磁盘扫描 helper / chunk-merge-status-cancel
  校验分支（缺参、非整数、负数、404、已完成、写盘异常 500）
- publish_bp：postVideo 空 body 与不支持平台 400 / status 404+200 /
  _enqueue_publish 后台 job 全路径（同步/异步成功、失败、取消、浏览器被关、通用异常）

uploads_bp 用 monkeypatch 钉 BASE_DIR/CHUNK_DIR/_get_db 到独立 tmp 目录，
不受 test_image_publish_endpoint 的 SAU_DATA_DIR 覆盖影响。
publish_bp 的 _enqueue_publish 用同步假执行器，job 同步跑完，无线程竞争。
"""
import asyncio
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import blueprints.uploads_bp as ub
from app import app
from blueprints.publish_bp import _enqueue_publish
from blueprints.uploads_bp import _guess_file_type, _list_uploaded_chunks


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ─────────────────────────── image_proxy_bp ───────────────────────────

def test_image_proxy_missing_url_400(client):
    r = client.get('/api/image-proxy')
    body = r.get_json()
    assert r.status_code == 400
    assert body['code'] == 400


def test_image_proxy_success_200(client):
    resp = MagicMock()
    resp.content = b'\x89PNG...'
    resp.headers = {'content-type': 'image/png'}
    with patch('httpx.get', return_value=resp):
        r = client.get('/api/image-proxy?url=https://example.com/a.png')
    assert r.status_code == 200
    assert r.mimetype == 'image/png'
    assert r.data == b'\x89PNG...'


def test_image_proxy_fetch_error_500(client):
    with patch('httpx.get', side_effect=RuntimeError('network down')):
        r = client.get('/api/image-proxy?url=https://example.com/a.png')
    body = r.get_json()
    assert r.status_code == 500
    assert body['code'] == 500
    assert 'network down' in body['msg']


# ─────────────────────────── uploads_bp 纯函数 ─────────────────────────

@pytest.mark.parametrize("mime,filename,expected", [
    ('video/mp4', '', 'video'),
    ('image/jpeg', '', 'image'),
    ('', 'clip.MP4', 'video'),
    ('', 'photo.PNG', 'image'),
    ('application/octet-stream', 'unknown.bin', 'image'),  # 默认按图片
    ('', '', 'image'),
])
def test_guess_file_type(mime, filename, expected):
    assert _guess_file_type(mime, filename) == expected


def test_list_uploaded_chunks_scans_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(ub, 'CHUNK_DIR', tmp_path)
    d = tmp_path / 'sess1'
    d.mkdir()
    (d / '0').write_text('a')
    (d / '2').write_text('b')
    (d / 'junk.txt').write_text('x')
    assert _list_uploaded_chunks('sess1') == [0, 2]
    monkeypatch.setattr(ub, 'CHUNK_DIR', tmp_path / 'not-exist')
    assert _list_uploaded_chunks('sess2') == []


# ─────────────────────────── uploads_bp 路由分支 ────────────────────────

_UPLOAD_SCHEMA = """
CREATE TABLE IF NOT EXISTS upload_sessions (
    upload_id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mime_type TEXT,
    file_type TEXT,
    chunk_size INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    uploaded_chunks INTEGER DEFAULT 0,
    status TEXT DEFAULT 'uploading',
    material_id TEXT,
    error_message TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest.fixture
def uploads_env(tmp_path, monkeypatch):
    db_path = tmp_path / 'db.sqlite'
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_UPLOAD_SCHEMA)
    conn.commit()
    conn.close()

    def _db():
        c = sqlite3.connect(str(db_path))
        c.row_factory = sqlite3.Row
        return c

    monkeypatch.setattr(ub, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(ub, 'CHUNK_DIR', tmp_path / 'upload_chunks')
    monkeypatch.setattr(ub, '_get_db', _db)
    return ub


def _insert_session(uploads_env, upload_id='u1', total_chunks=2, status='uploading', file_size=6):
    conn = uploads_env._get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO upload_sessions (upload_id, original_filename, file_size, chunk_size, total_chunks, status) VALUES (?,?,?,?,?,?)",
            (upload_id, 'v.mp4', file_size, 3, total_chunks, status),
        )
        conn.commit()
    finally:
        conn.close()


def test_upload_chunk_missing_fields_400(client, uploads_env):
    r = client.post('/api/uploads/chunk', data={'upload_id': 'u1'})
    body = r.get_json()
    assert r.status_code == 400
    assert 'upload_id / chunk_index / file' in body['msg']


def test_upload_chunk_non_int_index_400(client, uploads_env):
    r = client.post('/api/uploads/chunk', data={'upload_id': 'u1', 'chunk_index': 'abc', 'file': (b'x', 'c0')})
    assert r.get_json()['code'] == 400


def test_upload_chunk_negative_index_400(client, uploads_env):
    r = client.post('/api/uploads/chunk', data={'upload_id': 'u1', 'chunk_index': '-1', 'file': (b'x', 'c-1')})
    assert r.get_json()['code'] == 400


def test_upload_merge_missing_upload_id_400(client, uploads_env):
    r = client.post('/api/uploads/merge', json={})
    body = r.get_json()
    assert r.status_code == 400
    assert '缺少 upload_id' in body['msg']


def test_upload_merge_session_404(client, uploads_env):
    r = client.post('/api/uploads/merge', json={'upload_id': 'nope'})
    assert r.get_json()['code'] == 404


def test_upload_merge_already_completed_400(client, uploads_env):
    _insert_session(uploads_env, status='completed')
    r = client.post('/api/uploads/merge', json={'upload_id': 'u1'})
    body = r.get_json()
    assert r.status_code == 400
    assert '已经合并过了' in body['msg']


def test_upload_merge_write_error_500(client, uploads_env):
    _insert_session(uploads_env, total_chunks=0, file_size=0)
    (uploads_env.CHUNK_DIR / 'u1').mkdir(parents=True, exist_ok=True)
    real_open = open

    def _raising_open(*args, **kwargs):
        if len(args) >= 2 and args[1] == 'wb':
            raise OSError('disk full')
        return real_open(*args, **kwargs)

    with patch('blueprints.uploads_bp.open', side_effect=_raising_open):
        r = client.post('/api/uploads/merge', json={'upload_id': 'u1'})
    body = r.get_json()
    assert r.status_code == 500
    assert '合并失败' in body['msg']


def test_upload_status_missing_upload_id_400(client, uploads_env):
    r = client.get('/api/uploads/status')
    body = r.get_json()
    assert r.status_code == 400
    assert '缺少 upload_id' in body['msg']


def test_upload_cancel_missing_upload_id_400(client, uploads_env):
    r = client.delete('/api/uploads/')
    assert r.get_json()['code'] == 400


def test_upload_cancel_session_404(client, uploads_env):
    r = client.delete('/api/uploads/?upload_id=nope')
    assert r.get_json()['code'] == 404


def test_upload_cancel_completed_400(client, uploads_env):
    _insert_session(uploads_env, status='completed')
    r = client.delete('/api/uploads/?upload_id=u1')
    body = r.get_json()
    assert r.status_code == 400
    assert '已合并完成' in body['msg']


# ─────────────────────────── publish_bp 路由分支 ────────────────────────

def test_postvideo_empty_data_400(client):
    r = client.post('/postVideo', json={})
    body = r.get_json()
    assert r.status_code == 400
    assert body['code'] == 400


def test_postvideo_unsupported_platform_400(client):
    with patch('blueprints.publish_bp.get_platform', return_value=None):
        r = client.post('/postVideo', json={'type': 99})
    body = r.get_json()
    assert r.status_code == 400
    assert '不支持的平台类型' in body['msg']


def test_postvideo_status_404(client):
    r = client.get('/postVideo/status/no-such-task')
    assert r.get_json()['code'] == 404


def test_postvideo_status_200(client):
    fake = _SyncExec()
    fake.tasks['t6-task'] = {'taskId': 't6-task', 'status': 'success', 'msg': '发布成功'}
    with patch('blueprints.publish_bp._publish_exec', fake):
        r = client.get('/postVideo/status/t6-task')
    body = r.get_json()
    assert body['code'] == 200
    assert body['data']['status'] == 'success'


# ─────────────────────────── publish_bp _enqueue_publish ───────────────

class _SyncExec:
    """同步假执行器：submit 后立刻跑完 job，无线程。"""

    def __init__(self):
        self.tasks = {}

    def submit(self, job):
        tid = f't6-{len(self.tasks) + 1}'
        self.tasks[tid] = {'taskId': tid, 'status': 'queued', 'msg': ''}
        job(tid)
        return tid

    def get(self, tid):
        return dict(self.tasks[tid]) if tid in self.tasks else None

    def mark_running(self, tid):
        self.tasks[tid]['status'] = 'running'

    def mark_finished(self, tid, status, msg=''):
        self.tasks[tid].update(status=status, msg=msg)


class _SyncPlatform:
    def __init__(self, result=True, error=None):
        self._result = result
        self._error = error

    def publish_video(self, **kwargs):
        if self._error is not None:
            raise self._error
        return self._result


class _AsyncPlatform:
    async def publish_video(self, **kwargs):
        return True


def _run_enqueue(platform, detail_id='d1'):
    fake = _SyncExec()
    updater = MagicMock()
    with patch('blueprints.publish_bp._publish_exec', fake), \
         patch('blueprints.publish_bp._update_publish_result', updater):
        _enqueue_publish(platform, {'title': 't'}, detail_id)
    return fake, updater


def test_enqueue_sync_success():
    fake, updater = _run_enqueue(_SyncPlatform(result=True))
    task = next(iter(fake.tasks.values()))
    assert task['status'] == 'success'
    updater.assert_called_once()
    assert updater.call_args[0][1] == 'success'


def test_enqueue_sync_falsy_result_fails():
    fake, updater = _run_enqueue(_SyncPlatform(result=False))
    task = next(iter(fake.tasks.values()))
    assert task['status'] == 'failed'
    assert '页面未跳转' in task['msg']
    assert updater.call_args[0][1] == 'failed'


def test_enqueue_async_success():
    fake, updater = _run_enqueue(_AsyncPlatform())
    task = next(iter(fake.tasks.values()))
    assert task['status'] == 'success'
    assert updater.call_args[0][1] == 'success'


def test_enqueue_no_detail_skips_history_update():
    _fake, updater = _run_enqueue(_SyncPlatform(result=True), detail_id=None)
    updater.assert_not_called()


def test_enqueue_cancelled_error():
    fake, _updater = _run_enqueue(_SyncPlatform(error=asyncio.CancelledError()))
    task = next(iter(fake.tasks.values()))
    assert task['status'] == 'failed'
    assert '用户关闭了浏览器' in task['msg']


def test_enqueue_browser_closed_exception():
    fake, _updater = _run_enqueue(_SyncPlatform(error=RuntimeError('Browser has been closed')))
    task = next(iter(fake.tasks.values()))
    assert task['status'] == 'failed'
    assert '用户关闭了浏览器' in task['msg']


def test_enqueue_generic_exception():
    fake, _updater = _run_enqueue(_SyncPlatform(error=RuntimeError('boom')))
    task = next(iter(fake.tasks.values()))
    assert task['status'] == 'failed'
    assert task['msg'] == '发布失败: boom'
