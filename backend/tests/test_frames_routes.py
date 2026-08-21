"""routes/frames.py 路由契约测试（T12）。

覆盖 6 个路由 + 4 个内部 helper：素材解析 / S3 缓存下载 / 抽帧状态机 /
帧图片 / 缓存清理 / system-info。BASE_DIR 用模块级 patch 钉到 tmp 目录。
"""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR as REAL_BASE_DIR
from routes.frames import _download_s3_to_cache, _resolve_material_video, _resolve_video_path


@pytest.fixture
def client():
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def tmp_bp(tmp_path, monkeypatch):
    """把 frames 模块的 BASE_DIR 钉到 tmp 目录(不影响 conf.BASE_DIR)。"""
    monkeypatch.setattr('routes.frames.BASE_DIR', tmp_path)
    monkeypatch.setattr('routes.frames._s3_cache_dir', tmp_path / 's3_video_cache')
    return tmp_path


# ── helper: _resolve_video_path ───────────────────────────────────────────

class TestResolveVideoPath:
    def test_storage_resolves(self, tmp_path):
        f = tmp_path / 'v.mp4'
        f.write_bytes(b'x')
        with patch('storage.resolve_material_path', return_value=str(f)):
            assert _resolve_video_path('old/path.mp4') == str(f)

    def test_fallback_isfile(self, tmp_path):
        f = tmp_path / 'v.mp4'
        f.write_bytes(b'x')
        with patch('storage.resolve_material_path', return_value=None):
            assert _resolve_video_path(str(f)) == str(f)

    def test_none(self):
        with patch('storage.resolve_material_path', return_value=None):
            assert _resolve_video_path('/nonexistent/x.mp4') is None


# ── helper: _resolve_material_video / _download_s3_to_cache ────────────────

class TestResolveMaterialVideo:
    @pytest.fixture
    def _insert(self):
        conn = sqlite3.connect(str(REAL_BASE_DIR / "db" / "database.db"))
        conn.execute("INSERT INTO materials (id, stored_path, storage_type, file_type, original_filename) "
                     "VALUES ('t-frame-local', 'uploads/t.mp4', 'local', 'video', 't.mp4')")
        conn.execute("INSERT INTO materials (id, stored_path, storage_type, file_type, original_filename) "
                     "VALUES ('t-frame-s3', 's3/key/v.mp4', 's3', 'video', 't.mp4')")
        conn.commit()
        conn.close()
        yield
        conn = sqlite3.connect(str(REAL_BASE_DIR / "db" / "database.db"))
        conn.execute("DELETE FROM materials WHERE id IN ('t-frame-local','t-frame-s3')")
        conn.commit()
        conn.close()

    def test_no_row(self):
        assert _resolve_material_video('t-frame-nonexistent') is None

    def test_local(self, _insert):
        with patch('storage.local.LocalStorage.get_local_path', return_value='/local/t.mp4'):
            assert _resolve_material_video('t-frame-local') == '/local/t.mp4'

    def test_s3(self, _insert):
        with patch('routes.frames._download_s3_to_cache', return_value='/cache/t.mp4'):
            assert _resolve_material_video('t-frame-s3') == '/cache/t.mp4'


class TestDownloadS3ToCache:
    def test_cache_hit(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / 'cache'
        cache_dir.mkdir()
        (cache_dir / 'm1.mp4').write_bytes(b'old')
        monkeypatch.setattr('routes.frames._s3_cache_dir', cache_dir)
        with patch('storage.get_storage_by_type') as m:
            assert _download_s3_to_cache('m1', 's3/x.mp4') == str(cache_dir / 'm1.mp4')
            m.assert_not_called()

    def test_download(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / 'cache'
        monkeypatch.setattr('routes.frames._s3_cache_dir', cache_dir)
        fake = MagicMock()
        fake.get.return_value = b'videodata'
        with patch('storage.get_storage_by_type', return_value=fake):
            p = _download_s3_to_cache('m2', 's3/y.mp4')
        assert p == str(cache_dir / 'm2.mp4')
        assert Path(p).read_bytes() == b'videodata'
        fake.get.assert_called_once_with('s3/y.mp4')

    def test_download_extension_from_path(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / 'cache'
        monkeypatch.setattr('routes.frames._s3_cache_dir', cache_dir)
        fake = MagicMock()
        fake.get.return_value = b'x'
        with patch('storage.get_storage_by_type', return_value=fake):
            p = _download_s3_to_cache('m3', 's3/z')
        assert p.endswith('.mp4')


# ── POST /api/extract-frames ───────────────────────────────────────────────

class TestExtractFrames:
    def test_missing_params_400(self, client):
        r = client.post('/api/extract-frames', json={})
        assert r.status_code == 400
        assert r.get_json()['code'] == 400

    def test_material_not_found_404_body(self, client):
        r = client.post('/api/extract-frames', json={'material_id': 't-frame-nonexistent'})
        body = r.get_json()
        assert body['code'] == 404
        assert '已失效' in body['msg']

    def test_video_path_invalid_404_body(self, client):
        with patch('routes.frames._resolve_video_path', return_value=None):
            r = client.post('/api/extract-frames', json={'video_path': '/nonexistent/x.mp4'})
        assert r.get_json()['code'] == 404

    def test_done_returns_cached(self, client, tmp_bp):
        with patch('routes.frames._resolve_video_path', return_value='/data/v.mp4'), \
             patch('routes.frames.get_extraction_status',
                   return_value={'status': 'done', 'total_frames': 2, 'duration': 2.0}), \
             patch('routes.frames.get_frame_list',
                   return_value={'frames': [{'seconds': 0}, {'seconds': 1}], 'duration': 2.0}):
            r = client.post('/api/extract-frames', json={'video_path': 'v.mp4'})
        body = r.get_json()
        assert r.status_code == 200
        assert body['data']['status'] == 'done'
        assert body['data']['duration'] == 2.0

    def test_starts_extraction_when_new(self, client, tmp_bp):
        with patch('routes.frames._resolve_video_path', return_value='/data/v.mp4'), \
             patch('routes.frames.get_extraction_status', return_value={}), \
             patch('routes.frames.start_frame_extraction') as start, \
             patch('routes.frames.get_frame_list', return_value={'frames': [], 'duration': 0.0}):
            r = client.post('/api/extract-frames', json={'video_path': 'v.mp4'})
        start.assert_called_once()
        body = r.get_json()
        assert body['data']['status'] == 'processing'


# ── GET /api/frames-status ─────────────────────────────────────────────────

class TestFramesStatus:
    def test_missing_params_400(self, client):
        r = client.get('/api/frames-status')
        assert r.status_code == 400

    def test_not_found_404_body(self, client):
        r = client.get('/api/frames-status?material_id=t-frame-nonexistent')
        assert r.get_json()['code'] == 404

    def test_ok(self, client):
        with patch('routes.frames._resolve_video_path', return_value='/data/v.mp4'), \
             patch('routes.frames.get_extraction_status',
                   return_value={'status': 'processing', 'total_frames': 0, 'duration': 0.0}):
            r = client.get('/api/frames-status?video_path=v.mp4')
        assert r.status_code == 200
        assert r.get_json()['data']['status'] == 'processing'


# ── GET /api/frames ────────────────────────────────────────────────────────

class TestGetFrames:
    def test_missing_params_400(self, client):
        r = client.get('/api/frames')
        assert r.status_code == 400

    def test_not_found_404_body(self, client):
        with patch('routes.frames._resolve_video_path', return_value=None):
            r = client.get('/api/frames?video_path=nonexistent.mp4')
        assert r.get_json()['code'] == 404

    def test_ok(self, client):
        with patch('routes.frames._resolve_video_path', return_value='/data/v.mp4'), \
             patch('routes.frames.get_frame_list',
                   return_value={'frames': [{'seconds': 0, 'url': '/u'}], 'duration': 1.0}):
            r = client.get('/api/frames?video_path=v.mp4')
        assert r.status_code == 200
        assert len(r.get_json()['data']['frames']) == 1


# ── GET /api/frame-image ───────────────────────────────────────────────────

class TestFrameImage:
    def test_missing_params_400(self, client):
        r = client.get('/api/frame-image')
        assert r.status_code == 400

    def test_bad_seconds_400(self, client):
        with patch('routes.frames._resolve_video_path', return_value='/data/v.mp4'):
            r = client.get('/api/frame-image?video_path=v.mp4&seconds=abc')
        assert r.status_code == 400
        assert 'integer' in r.get_json()['msg']

    def test_material_not_found_404(self, client):
        r = client.get('/api/frame-image?material_id=nonexistent')
        assert r.status_code == 404

    def test_frame_file_missing_404(self, client):
        with patch('routes.frames._resolve_video_path', return_value='/data/v.mp4'), \
             patch('routes.frames.get_frame_image_path', return_value=None):
            r = client.get('/api/frame-image?video_path=v.mp4&seconds=1')
        assert r.status_code == 404

    def test_success_send_file(self, client, tmp_path):
        img = tmp_path / 'frame_1.jpg'
        img.write_bytes(b'\xff\xd8\xff')
        with patch('routes.frames._resolve_video_path', return_value='/data/v.mp4'), \
             patch('routes.frames.get_frame_image_path', return_value=str(img)):
            r = client.get('/api/frame-image?video_path=v.mp4&seconds=0')
        assert r.status_code == 200
        assert r.data == b'\xff\xd8\xff'


# ── POST /api/clear-cache ──────────────────────────────────────────────────

class TestClearCache:
    def test_frames_cleared(self, client, tmp_bp):
        frames_dir = tmp_bp / 'frames'
        (frames_dir / 'a' / 'sub').mkdir(parents=True)
        (frames_dir / 'a' / 'sub' / 'frame_1.jpg').write_bytes(b'x')
        (frames_dir / 'a' / 'frame_2.jpg').write_bytes(b'x')
        r = client.post('/api/clear-cache', json={'targets': ['frames']})
        body = r.get_json()
        assert body['data']['frames'] == {'cleared': 2, 'unit': 'files'}
        assert frames_dir.is_dir()  # 清空后重建

    def test_frames_missing_dir(self, client, tmp_bp):
        r = client.post('/api/clear-cache', json={'targets': ['frames']})
        assert r.get_json()['data']['frames']['cleared'] == 0

    def test_logs_old_cleared_new_kept(self, client, tmp_bp):
        logs_dir = tmp_bp / 'logs'
        old_dir = logs_dir / (datetime.now(ZoneInfo('Asia/Shanghai')) - timedelta(days=30)).strftime('%Y-%m-%d')
        new_dir = logs_dir / datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
        old_dir.mkdir(parents=True)
        new_dir.mkdir(parents=True)
        (old_dir / 'a.log').write_bytes(b'x')
        (new_dir / 'b.log').write_bytes(b'x')
        r = client.post('/api/clear-cache', json={'targets': ['logs']})
        body = r.get_json()
        assert body['data']['logs']['cleared'] == 1
        assert new_dir.exists()
        assert not old_dir.exists()

    def test_s3_and_covers(self, client, tmp_bp):
        (tmp_bp / 's3_video_cache').mkdir(parents=True)
        (tmp_bp / 's3_video_cache' / 'v1.mp4').write_bytes(b'x')
        (tmp_bp / 'covers').mkdir(parents=True)
        (tmp_bp / 'covers' / 'c1.jpg').write_bytes(b'x')
        r = client.post('/api/clear-cache', json={'targets': ['s3_videos', 'covers']})
        body = r.get_json()
        assert body['data']['s3_videos']['cleared'] == 1
        assert body['data']['covers']['cleared'] == 1

    def test_empty_targets_default_frames(self, client, tmp_bp):
        (tmp_bp / 'frames').mkdir()
        r = client.post('/api/clear-cache', json={})
        assert 'frames' in r.get_json()['data']


# ── GET /api/system-info ───────────────────────────────────────────────────

class TestSystemInfo:
    def test_unknown_version_without_file(self, client, tmp_bp):
        r = client.get('/api/system-info')
        body = r.get_json()
        assert body['data']['version'] == 'unknown'

    def test_version_from_parent(self, client, tmp_bp):
        (tmp_bp / '..' ).resolve()
        parent_versions = tmp_bp.parent / 'versions'
        parent_versions.write_text('1.2.3\n')
        try:
            r = client.get('/api/system-info')
            assert r.get_json()['data']['version'] == '1.2.3'
        finally:
            parent_versions.unlink()

    def test_cache_sizes(self, client, tmp_bp):
        frames = tmp_bp / 'frames'
        frames.mkdir(parents=True)
        (frames / 'frame_1.jpg').write_bytes(b'12345')
        r = client.get('/api/system-info')
        cache = r.get_json()['data']['cache']
        assert cache['frames']['count'] == 1
        assert cache['frames']['size'] == 5
        assert cache['logs']['count'] == 0
        assert cache['s3_videos']['count'] == 0
        assert cache['covers']['count'] == 0
