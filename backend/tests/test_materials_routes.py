"""materials_bp 路由契约测试（mock 存储后端与 DB，只测 HTTP 层）。

覆盖：upload / covers/upload / batch-delete / list / get / delete /
file 服务 / test-s3 的参数校验、成功、404、异常路径。
"""
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from app import app


class FakeRow:
    """模拟 sqlite3.Row: 支持 dict(row) 与 row['col'] 访问。"""

    def __init__(self, d):
        self._d = d

    def __getitem__(self, k):
        return self._d[k]

    def keys(self):
        return self._d.keys()


def _client():
    app.config['TESTING'] = True
    return app.test_client()


def _fake_storage(**kwargs):
    s = MagicMock()
    s.type = kwargs.get('type', 'local')
    s.get_url.return_value = kwargs.get('url', '/files/x.png')
    s.save_stream.return_value = None
    s.delete.return_value = None
    s.serve.return_value = kwargs.get('serve', 'file-bytes')
    return s


def _fake_conn(**kwargs):
    """MagicMock conn: execute(...).fetchone/fetchall 按需配置。"""
    conn = MagicMock()
    cur = MagicMock()
    if 'fetchone' in kwargs:
        cur.fetchone.side_effect = kwargs['fetchone']
    if 'fetchall' in kwargs:
        cur.fetchall.return_value = kwargs['fetchall']
    conn.execute.return_value = cur
    return conn


# ── upload ──

def test_upload_missing_file_400():
    # API 约定: HTTP 200 + body.code 业务码(前端 axios 拦截器按 code 判断)
    r = _client().post('/api/materials/upload', data={})
    assert r.get_json()['code'] == 400
    assert '未找到文件' in r.get_json()['msg']


def test_upload_image_success():
    with patch('storage.get_storage', return_value=_fake_storage()), \
         patch('blueprints.materials_bp._get_db', return_value=_fake_conn()):
        r = _client().post('/api/materials/upload', data={
            'file': (io.BytesIO(b'\x89PNG fake'), 'cat.png', 'image/png')
        }, content_type='multipart/form-data')
    assert r.status_code == 200
    body = r.get_json()
    assert body['code'] == 200
    assert body['data']['file_type'] == 'image'
    assert body['data']['url'] == '/files/x.png'
    assert body['data']['id']


def test_upload_video_success_spawns_bg_threads():
    """视频上传: 触发抽帧/时长/宽高三个后台线程(mock 掉避免真实执行)。"""
    with patch('storage.get_storage', return_value=_fake_storage()), \
         patch('blueprints.materials_bp._get_db', return_value=_fake_conn()), \
         patch('blueprints.materials_bp._async_extract_thumb'), \
         patch('blueprints.materials_bp._async_probe_duration'), \
         patch('blueprints.materials_bp._async_probe_dimensions'):
        r = _client().post('/api/materials/upload', data={
            'file': (io.BytesIO(b'fake-mp4'), 'a.mp4', 'video/mp4')
        }, content_type='multipart/form-data')
    assert r.status_code == 200
    assert r.get_json()['data']['file_type'] == 'video'


def test_covers_upload_missing_file_400():
    r = _client().post('/api/materials/covers/upload', data={})
    assert r.get_json()['code'] == 400


def test_covers_upload_success_writes_covers_dir():
    with patch('storage.get_storage', return_value=_fake_storage()):
        r = _client().post('/api/materials/covers/upload', data={
            'file': (io.BytesIO(b'jpg'), 'cover.jpg', 'image/jpeg')
        }, content_type='multipart/form-data')
    assert r.status_code == 200
    body = r.get_json()
    assert body['code'] == 200
    assert body['data']['file_type'] == 'image'
    assert body['data']['stored_path'].startswith('covers/')


# ── batch-delete ──

def test_batch_delete_missing_ids_400():
    r = _client().post('/api/materials/batch-delete', json={})
    assert r.get_json()['code'] == 400
    assert '缺少 ids' in r.get_json()['msg']


def test_batch_delete_mixed_exists_and_missing():
    """存在 + 不存在的混合: 存在被删, 不存在进 failed 明细。"""
    exists = FakeRow({'id': 'm1', 'stored_path': 'materials/m1.png',
                      'thumbnail_path': '', 'storage_type': 'local'})
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.side_effect = [exists, None]  # m1 存在, m2 不存在
    conn.execute.return_value = cur
    with patch('blueprints.materials_bp._get_db', return_value=conn), \
         patch('storage.get_storage_by_type', return_value=_fake_storage()):
        r = _client().post('/api/materials/batch-delete', json={'ids': ['m1', 'm2']})
    assert r.status_code == 200
    body = r.get_json()
    assert body['data']['deleted'] == 1
    assert body['data']['failed'][0]['reason'] == '不存在'


def test_batch_delete_storage_error_not_fatal():
    """删文件失败仅告警, 不中断删除。"""
    row = FakeRow({'id': 'm1', 'stored_path': 'materials/m1.png',
                   'thumbnail_path': 'thumb/t1.png', 'storage_type': 's3'})
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = row
    storage = _fake_storage()
    storage.delete.side_effect = RuntimeError('s3 down')
    with patch('blueprints.materials_bp._get_db', return_value=conn), \
         patch('storage.get_storage_by_type', return_value=storage):
        r = _client().post('/api/materials/batch-delete', json={'ids': ['m1']})
    assert r.status_code == 200
    assert r.get_json()['data']['deleted'] == 1
    assert r.get_json()['data']['failed'] == []


# ── list ──

def _list_conn(total=1, row=None):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = FakeRow({'n': total})
    cur.fetchall.return_value = row if row is not None else []
    conn.execute.return_value = cur
    return conn


def test_list_default():
    row = FakeRow({'id': 'm1', 'stored_path': 'materials/m1.png', 'file_type': 'image',
                   'thumbnail_path': '', 'storage_type': 'local', 'original_filename': 'a.png'})
    with patch('blueprints.materials_bp._get_db', return_value=_list_conn(total=1, row=[row])), \
         patch('storage.get_storage_by_type', return_value=_fake_storage()):
        r = _client().get('/api/materials/list')
    assert r.status_code == 200
    body = r.get_json()['data']
    assert body['total'] == 1
    assert body['page'] == 1
    assert body['page_size'] == 24
    assert body['total_pages'] == 1
    assert body['items'][0]['url'] == '/files/x.png'


def test_list_type_and_keyword_filter():
    with patch('blueprints.materials_bp._get_db', return_value=_list_conn(total=0)), \
         patch('storage.get_storage_by_type', return_value=_fake_storage()):
        r = _client().get('/api/materials/list?type=video&keyword=test')
    assert r.status_code == 200
    assert r.get_json()['data']['total'] == 0


def test_list_page_size_capped_at_96():
    with patch('blueprints.materials_bp._get_db', return_value=_list_conn(total=0)), \
         patch('storage.get_storage_by_type', return_value=_fake_storage()):
        r = _client().get('/api/materials/list?page_size=999')
    assert r.status_code == 200
    assert r.get_json()['data']['page_size'] == 96


# ── get ──

def test_get_material_404():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None
    with patch('blueprints.materials_bp._get_db', return_value=conn):
        r = _client().get('/api/materials/nope')
    assert r.status_code == 404
    assert '素材不存在' in r.get_json()['msg']


def test_get_material_200():
    row = FakeRow({'id': 'm1', 'stored_path': 'materials/m1.png', 'file_type': 'image',
                   'thumbnail_path': 'thumb/t1.png', 'storage_type': 'local'})
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = row
    with patch('blueprints.materials_bp._get_db', return_value=conn), \
         patch('storage.get_storage_by_type', return_value=_fake_storage()):
        r = _client().get('/api/materials/m1')
    assert r.status_code == 200
    body = r.get_json()['data']
    assert body['url'] == '/files/x.png'
    assert body['thumbnail_url'] == '/files/x.png'


# ── delete ──

def test_delete_404():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None
    with patch('blueprints.materials_bp._get_db', return_value=conn):
        r = _client().delete('/api/materials/nope')
    assert r.get_json()['code'] == 404


def test_delete_200_removes_storage():
    row = FakeRow({'id': 'm1', 'stored_path': 'materials/m1.png',
                   'thumbnail_path': 'thumb/t1.png', 'storage_type': 'local'})
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = row
    storage = _fake_storage()
    with patch('blueprints.materials_bp._get_db', return_value=conn), \
         patch('storage.get_storage', return_value=storage):
        r = _client().delete('/api/materials/m1')
    assert r.status_code == 200
    assert r.get_json()['msg'] == '删除成功'
    assert storage.delete.call_count == 2  # stored_path + thumbnail_path


# ── serve_file ──

def test_serve_file_uses_storage_backend():
    row = FakeRow({'storage_type': 's3'})
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = row
    with patch('blueprints.materials_bp._get_db', return_value=conn), \
         patch('storage.get_storage_by_type', return_value=_fake_storage(serve='s3-bytes')):
        r = _client().get('/api/materials/file/materials/m1.png')
    assert r.status_code == 200
    assert r.data == b's3-bytes'


# ── test-s3 ──

def test_s3_connection_success():
    with patch('boto3.client') as boto_mock:
        boto_mock.return_value.head_bucket.return_value = None
        r = _client().post('/api/materials/test-s3', json={'bucket': 'b1'})
    assert r.status_code == 200
    assert '连接成功' in r.get_json()['msg']


def test_s3_connection_failure_400():
    with patch('boto3.client') as boto_mock:
        boto_mock.return_value.head_bucket.side_effect = RuntimeError('bucket not found')
        r = _client().post('/api/materials/test-s3', json={'bucket': 'b1'})
    assert r.get_json()['code'] == 400
    assert '连接失败' in r.get_json()['msg']
