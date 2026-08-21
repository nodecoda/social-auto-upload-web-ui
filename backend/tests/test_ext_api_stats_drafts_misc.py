"""测试 ext_api 统计/设置/草稿/杂项域契约（行 641-1054、1077-1199、1365-1406 附近）。

覆盖：get_stats / get_settings / update_settings / _extract_image_channels_from_draft /
get_drafts / create_draft / get_draft / update_draft / delete_draft / 提取 helper 族 /
get_changelog / get_publish_templates / batch_delete_drafts。
独立临时 DB 模式，与 test_tasks_endpoint.py 一致。
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

_tmpdir = tempfile.mkdtemp(prefix='sau_ext_api_sdm_')
os.environ['SAU_DATA_DIR'] = _tmpdir
DB_PATH = Path(_tmpdir) / "db" / "database.db"


def _setup_schema():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    import init_db as init_db_module
    init_db_module.DB_PATH = DB_PATH
    from init_db import init_database, migrate_database
    init_database()
    migrate_database()


def _wipe(conn):
    for table in ('publish_details', 'publish_batches', 'drafts',
                  'settings', 'user_info', 'file_records', 'materials'):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


class _FakeFile:
    def __init__(self, name):
        self.name = name
        self.stem = name.rsplit('.', 1)[0]
        self.suffix = f".{name.rsplit('.', 1)[1]}" if '.' in name else ''

    def is_file(self):
        return True

    def __lt__(self, other):
        return self.name < other.name


class _FakePath:
    """可控 Path 替身：支持 / 链、exists、iterdir。"""

    def __init__(self, exists=True, files=None):
        self._exists = exists
        self._files = files or []
        self.parent = self

    def __call__(self, *args, **kwargs):
        return self

    def exists(self):
        return self._exists

    def iterdir(self):
        return iter(self._files)

    def __truediv__(self, other):
        if not self._exists:
            return _FakePath(exists=False)
        return _FakePath(exists=True, files=self._files)


class TestExtApiStatsDraftsMisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup_schema()
        import ext_api
        ext_api.DB_PATH = DB_PATH
        from ext_api import app
        cls.app = app
        cls.client = app.test_client()

    def setUp(self):
        # 其他测试文件（如 test_history_*_endpoint）会覆盖 SAU_DATA_DIR，
        # 这里在每用例前重置回本模块独立临时库，保证 app._get_db_path() 指向正确。
        os.environ['SAU_DATA_DIR'] = _tmpdir
        with sqlite3.connect(str(DB_PATH)) as conn:
            _wipe(conn)

    # ---------- get_stats ----------

    def test_stats_empty_db(self):
        resp = self.client.get('/api/v2/stats')
        data = resp.get_json()['data']
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['successRate'], 0)
        self.assertEqual(data['monthlyTotal'], 0)
        self.assertEqual(data['tasks'], {'total': 0, 'success': 0, 'failed': 0,
                                         'running': 0, 'successRate': 0})
        self.assertEqual(data['byPlatform'], {})
        self.assertEqual(len(data['trend']), 7)
        self.assertEqual(data['accounts'], {'total': 0, 'normal': 0})
        self.assertEqual(data['materials'], {'total': 0})

    def test_stats_counts_and_by_platform(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        this_month = now.strftime('%Y-%m-01 00:00:00')
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO publish_batches (id, type, title, status, account_count, created_at) "
                "VALUES ('b1', 'video', 'a', 'success', 1, ?)", (this_month,))
            conn.execute(
                "INSERT INTO publish_batches (id, type, title, status, account_count, created_at) "
                "VALUES ('b2', 'video', 'b', 'failed', 1, ?)", (this_month,))
            conn.execute(
                "INSERT INTO publish_batches (id, type, title, status, account_count, created_at) "
                "VALUES ('b3', 'video', 'c', 'queued', 1, ?)", (this_month,))
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) "
                "VALUES ('d1', 'b1', 'A', '抖音', '{}', 'success')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) "
                "VALUES ('d2', 'b2', 'B', '抖音', '{}', 'failed')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) "
                "VALUES ('d3', 'b3', 'C', '小红书', '{}', 'queued')")
            conn.execute(
                "INSERT INTO user_info (type, filePath, userName, status) VALUES (3, '/x', 'U1', 1)")
            conn.execute(
                "INSERT INTO user_info (type, filePath, userName, status) VALUES (5, '/y', 'U2', 0)")
            conn.execute("INSERT INTO file_records (filename, filesize) VALUES ('f.mp4', 100)")
            conn.commit()

        data = self.client.get('/api/v2/stats').get_json()['data']
        self.assertEqual(data['total'], 3)
        self.assertEqual(data['successRate'], round(1 / 3 * 100, 1))
        self.assertEqual(data['tasks'], {'total': 3, 'success': 1, 'failed': 1,
                                         'running': 1, 'successRate': round(1 / 3 * 100, 1)})
        self.assertEqual(data['byPlatform'], {'抖音': 2, '小红书': 1})
        self.assertEqual(data['monthlyTotal'], 3)
        self.assertEqual(data['accounts'], {'total': 2, 'normal': 1})
        self.assertEqual(data['materials'], {'total': 1})

    def test_stats_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.get('/api/v2/stats')
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json()['code'], 500)

    # ---------- get_settings ----------

    def test_settings_defaults_when_empty(self):
        data = self.client.get('/api/v2/settings').get_json()['data']
        self.assertEqual(data['publishInterval'], 30)
        self.assertEqual(data['maxConcurrent'], 2)
        self.assertEqual(data['browserMode'], 'headed')
        self.assertEqual(data['heartbeatInterval'], 3600)
        self.assertIs(data['autoFillTitle'], True)
        self.assertIs(data['autoSaveDraft'], True)
        self.assertEqual(data['autoSaveInterval'], 10)
        self.assertEqual(data['accountCheckMode'], 'pre-publish')
        self.assertEqual(data['storage'], {'type': 'local', 's3': {}})
        self.assertEqual(data['proxyUrl'], '')

    def test_settings_merges_and_type_converts(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('publishInterval', '45')")
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('autoFillTitle', 'false')")
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('autoSaveDraft', 'True')")
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('heartbeatInterval', 'not-a-number')")
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('proxyUrl', 'http://p:1080')")
            conn.commit()

        data = self.client.get('/api/v2/settings').get_json()['data']
        self.assertEqual(data['publishInterval'], 45)
        self.assertIs(data['autoFillTitle'], False)
        self.assertIs(data['autoSaveDraft'], True)
        # 非法数值保持原样
        self.assertEqual(data['heartbeatInterval'], 'not-a-number')
        self.assertEqual(data['proxyUrl'], 'http://p:1080')

    def test_settings_storage_corrupt_json_falls_back(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("INSERT INTO settings (key, value) VALUES ('storage', '{bad')")
            conn.commit()
        data = self.client.get('/api/v2/settings').get_json()['data']
        self.assertEqual(data['storage'], {'type': 'local', 's3': {}})

    def test_settings_storage_valid_json_parsed(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('storage', "
                "'{\"type\": \"s3\", \"s3\": {\"bucket\": \"b\"}}')")
            conn.commit()
        data = self.client.get('/api/v2/settings').get_json()['data']
        self.assertEqual(data['storage'], {'type': 's3', 's3': {'bucket': 'b'}})

    def test_settings_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.get('/api/v2/settings')
        self.assertEqual(resp.status_code, 500)

    # ---------- update_settings ----------

    def test_update_settings_empty_body_400(self):
        resp = self.client.put('/api/v2/settings', json={})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()['msg'], '请求数据不能为空')

    def test_update_settings_scalar_and_json_values(self):
        with mock.patch('storage.reset_storage') as mock_reset:
            resp = self.client.put('/api/v2/settings', json={
                'publishInterval': 60,
                'autoFillTitle': True,
                'storage': {'type': 's3'},
                'proxyList': ['p1', 'p2'],
            })
        self.assertEqual(resp.status_code, 200)
        with sqlite3.connect(str(DB_PATH)) as conn:
            rows = dict(conn.execute("SELECT key, value FROM settings").fetchall())
        self.assertEqual(rows['publishInterval'], '60')
        self.assertEqual(rows['autoFillTitle'], 'True')
        self.assertEqual(json.loads(rows['storage']), {'type': 's3'})
        self.assertEqual(json.loads(rows['proxyList']), ['p1', 'p2'])
        mock_reset.assert_called_once()

    def test_update_settings_without_storage_skips_reset(self):
        with mock.patch('storage.reset_storage') as mock_reset:
            resp = self.client.put('/api/v2/settings', json={'browserMode': 'headless'})
        self.assertEqual(resp.status_code, 200)
        mock_reset.assert_not_called()

    def test_update_settings_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.put('/api/v2/settings', json={'a': 'b'})
        self.assertEqual(resp.status_code, 500)

    # ---------- _extract_image_channels_from_draft ----------

    def test_extract_image_channels_empty_ids(self):
        from ext_api import _db_conn, _extract_image_channels_from_draft
        conn = _db_conn()
        self.assertEqual(_extract_image_channels_from_draft(conn, {}), [])
        self.assertEqual(_extract_image_channels_from_draft(conn, {'publishAccountIds': []}), [])
        conn.close()

    def test_extract_image_channels_aggregates(self):
        from ext_api import _db_conn, _extract_image_channels_from_draft
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("INSERT INTO user_info (id, type, filePath, userName) VALUES (1, 3, '/a', 'A')")
            conn.execute("INSERT INTO user_info (id, type, filePath, userName) VALUES (2, 3, '/b', 'B')")
            conn.execute("INSERT INTO user_info (id, type, filePath, userName) VALUES (3, 999, '/c', 'C')")
            conn.commit()
        conn = _db_conn()
        result = _extract_image_channels_from_draft(conn, {'publishAccountIds': [1, 2, 3]})
        conn.close()
        by_platform = {r['platform']: r['count'] for r in result}
        self.assertEqual(by_platform['douyin'], 2)
        # 未知 type 兜底: (str(type), 平台{type})
        unknown = [r for r in result if r['platform'] == '999']
        self.assertEqual(unknown, [{'platform': '999', 'name': '平台999', 'count': 1}])

    def test_extract_image_channels_db_error(self):
        from ext_api import _extract_image_channels_from_draft
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            self.assertEqual(
                _extract_image_channels_from_draft(None, {'publishAccountIds': [1]}), [])

    # ---------- get_drafts ----------

    def test_get_drafts_empty(self):
        resp = self.client.get('/api/v2/drafts')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['data'], [])

    def test_get_drafts_type_filter_and_time_convert(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, title, draft_data, created_at, updated_at) "
                "VALUES (1, 'video', 'V', '{}', '2026-06-01 00:00:00', '2026-06-02 00:00:00')")
            conn.execute(
                "INSERT INTO drafts (id, type, title, draft_data, created_at, updated_at) "
                "VALUES (2, 'image', 'I', '{}', '2026-06-01 00:00:00', '2026-06-02 00:00:00')")
            conn.commit()

        all_drafts = self.client.get('/api/v2/drafts').get_json()['data']
        self.assertEqual(len(all_drafts), 2)
        videos = self.client.get('/api/v2/drafts?type=video').get_json()['data']
        self.assertEqual([d['id'] for d in videos], [1])
        images = self.client.get('/api/v2/drafts?type=image').get_json()['data']
        self.assertEqual([d['id'] for d in images], [2])
        # 北京时间 +8h ISO
        self.assertEqual(videos[0]['created_at'], '2026-06-01T08:00:00+08:00')
        self.assertEqual(videos[0]['updated_at'], '2026-06-02T08:00:00+08:00')
        # 列表接口不返回 draft_data
        self.assertNotIn('draft_data', videos[0])

    def test_get_drafts_recomputes_channels_summary(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, title, draft_data, channels_summary) "
                "VALUES (1, 'video', 'V', '{\"publishAccountIds\": [1, 2]}', "
                "'[{\"platform\": \"douyin\", \"name\": \"旧\", \"count\": 9}]')")
            conn.execute("INSERT INTO user_info (id, type, filePath, userName) VALUES (1, 3, '/a', 'A')")
            conn.execute("INSERT INTO user_info (id, type, filePath, userName) VALUES (2, 5, '/b', 'B')")
            conn.commit()

        drafts = self.client.get('/api/v2/drafts').get_json()['data']
        by_platform = {d['platform']: d['count'] for d in drafts[0]['channels_summary']}
        self.assertEqual(by_platform, {'douyin': 1, 'bilibili': 1})

    def test_get_drafts_corrupt_channels_summary(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, title, draft_data, channels_summary) "
                "VALUES (1, 'video', 'V', '{}', '{bad json')")
            conn.commit()
        drafts = self.client.get('/api/v2/drafts').get_json()['data']
        self.assertEqual(drafts[0]['channels_summary'], [])

    def test_get_drafts_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.get('/api/v2/drafts')
        self.assertEqual(resp.status_code, 500)

    # ---------- create_draft / get_draft / update_draft / delete_draft ----------

    def test_create_draft_missing_data_400(self):
        resp = self.client.post('/api/v2/drafts', json={})
        self.assertEqual(resp.status_code, 400)
        resp2 = self.client.post('/api/v2/drafts', json={'type': 'video'})
        self.assertEqual(resp2.status_code, 400)

    def test_create_draft_extracts_metadata(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("INSERT INTO user_info (id, type, filePath, userName) VALUES (1, 3, '/a', 'A')")
            conn.commit()
        draft_data = {
            'platformConfigs': {'douyin': {'title': '  测试标题  '}},
            'commonConfig': {
                'coverPortrait': {'path': '/data/materials/c.jpg'},
                'videoPortrait': {'size': 1024},
            },
            'publishAccountIds': [1],
        }
        resp = self.client.post('/api/v2/drafts', json={'type': 'video', 'draft_data': draft_data})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()['data']
        self.assertEqual(body['title'], '测试标题')
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT title, cover_path, channels_summary, video_file_size FROM drafts WHERE id = ?",
                (body['id'],)).fetchone()
        self.assertEqual(row[0], '测试标题')
        self.assertEqual(row[1], '/data/materials/c.jpg')
        self.assertEqual(json.loads(row[2]), [{'platform': 'douyin', 'name': '抖音', 'count': 1}])
        self.assertEqual(row[3], 1024)

    def test_get_draft_not_found_404(self):
        resp = self.client.get('/api/v2/drafts/999')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()['msg'], '草稿不存在')

    def test_get_draft_ok(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, title, draft_data) VALUES (1, 'video', 'V', '{\"a\": 1}')")
            conn.commit()
        resp = self.client.get('/api/v2/drafts/1')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()['data']
        self.assertEqual(data['title'], 'V')
        self.assertEqual(data['draft_data'], {'a': 1})

    def test_update_draft_not_found_404(self):
        resp = self.client.put('/api/v2/drafts/999', json={'draft_data': {'x': 1}})
        self.assertEqual(resp.status_code, 404)

    def test_update_draft_missing_data_400(self):
        resp = self.client.put('/api/v2/drafts/1', json={})
        self.assertEqual(resp.status_code, 400)

    def test_update_draft_ok(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, title, draft_data) VALUES (1, 'video', 'Old', '{}')")
            conn.commit()
        draft_data = {'platformConfigs': {'bilibili': {'title': 'New'}}}
        resp = self.client.put('/api/v2/drafts/1', json={'draft_data': draft_data})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['data']['title'], 'New')
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute("SELECT title, draft_data FROM drafts WHERE id = 1").fetchone()
        self.assertEqual(row[0], 'New')
        self.assertEqual(json.loads(row[1]), draft_data)

    def test_delete_draft_not_found_404(self):
        resp = self.client.delete('/api/v2/drafts/999')
        self.assertEqual(resp.status_code, 404)

    def test_delete_draft_ok(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, title) VALUES (1, 'video', 'V')")
            conn.commit()
        resp = self.client.delete('/api/v2/drafts/1')
        self.assertEqual(resp.status_code, 200)
        with sqlite3.connect(str(DB_PATH)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM drafts WHERE id = 1").fetchone()[0], 0)

    # ---------- 提取 helper ----------

    def test_extract_draft_title_priority_and_fallback(self):
        from ext_api import _extract_draft_title
        self.assertEqual(
            _extract_draft_title({'platformConfigs': {'douyin': {'title': 'D'}}}), 'D')
        # 优先级: douyin > xiaohongshu > ... (取第一个非空)
        self.assertEqual(
            _extract_draft_title({'platformConfigs': {'kuaishou': {'title': 'K'},
                                                      'bilibili': {'title': 'B'}}}), 'K')
        self.assertEqual(
            _extract_draft_title({'platformConfigs': {'douyin': {'title': '   '}}}), '无标题')
        self.assertEqual(_extract_draft_title({}), '无标题')

    def test_extract_draft_title_truncates_100(self):
        from ext_api import _extract_draft_title
        long_title = '长' * 120
        result = _extract_draft_title({'platformConfigs': {'douyin': {'title': long_title}}})
        self.assertEqual(len(result), 100)

    def test_extract_draft_cover(self):
        from ext_api import _extract_draft_cover
        self.assertEqual(
            _extract_draft_cover({'commonConfig': {'coverPortrait': {'path': '/p.jpg'}}}),
            '/p.jpg')
        self.assertEqual(
            _extract_draft_cover({'commonConfig': {'coverPortrait': {'url': 'http://u.jpg'},
                                                   'coverLandscape': {'path': '/l.jpg'}}}),
            'http://u.jpg')
        self.assertEqual(_extract_draft_cover({}), '')

    def test_extract_channels_summary(self):
        from ext_api import _extract_channels_summary
        self.assertEqual(_extract_channels_summary({}), [])
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("INSERT INTO user_info (id, type, filePath, userName) VALUES (1, 3, '/a', 'A')")
            conn.execute("INSERT INTO user_info (id, type, filePath, userName) VALUES (2, 4, '/b', 'B')")
            conn.execute("INSERT INTO user_info (id, type, filePath, userName) VALUES (3, 4, '/c', 'C')")
            conn.commit()
        result = _extract_channels_summary({'publishAccountIds': [1, 2, 3]})
        by_platform = {r['platform']: r['count'] for r in result}
        self.assertEqual(by_platform, {'douyin': 1, 'kuaishou': 2})

    def test_extract_channels_summary_db_error(self):
        from ext_api import _extract_channels_summary
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            self.assertEqual(_extract_channels_summary({'publishAccountIds': [1]}), [])

    def test_extract_video_duration_and_file_size(self):
        from ext_api import _extract_video_duration, _extract_video_file_size
        self.assertEqual(_extract_video_duration({}), 0)
        self.assertEqual(_extract_video_duration({'a': 1}), 0)
        self.assertEqual(
            _extract_video_file_size({'commonConfig': {'videoPortrait': {'size': 99}}}), 99)
        self.assertEqual(
            _extract_video_file_size({'commonConfig': {'videoLandscape': {'size': 77}}}), 77)
        self.assertEqual(_extract_video_file_size({}), 0)

    # ---------- get_changelog ----------

    def test_changelog_dir_missing_returns_empty(self):
        fake = _FakePath(exists=False)
        with mock.patch('ext_api.Path', fake):
            resp = self.client.get('/api/v2/changelog')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['data'], [])

    def test_changelog_parses_filenames_and_sorts_desc(self):
        files = [_FakeFile('20260525.html'), _FakeFile('v2.html'), _FakeFile('readme.txt')]
        fake = _FakePath(exists=True, files=files)
        with mock.patch('ext_api.Path', fake):
            resp = self.client.get('/api/v2/changelog')
        data = resp.get_json()['data']
        self.assertEqual([f['filename'] for f in data], ['v2.html', '20260525.html'])
        by_name = {f['filename']: f for f in data}
        self.assertEqual(by_name['20260525.html']['date'], '2026-05-25')
        self.assertEqual(by_name['20260525.html']['url'], '/changelog/20260525.html')
        self.assertEqual(by_name['v2.html']['date'], 'v2')

    # ---------- get_publish_templates ----------

    def test_publish_templates_type_validation_400(self):
        resp = self.client.get('/api/v2/publish-templates')
        self.assertEqual(resp.status_code, 400)
        resp2 = self.client.get('/api/v2/publish-templates?type=bad')
        self.assertEqual(resp2.status_code, 400)

    def test_publish_templates_bad_page_400(self):
        resp = self.client.get('/api/v2/publish-templates?type=video&page=abc')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()['msg'], 'page / page_size 必须是整数')

    def test_publish_templates_happy_path(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO publish_batches (id, type, title, description, status, "
                "landscape_cover_material_id, portrait_cover_material_id, image_material_ids, created_at) "
                "VALUES ('b1', 'video', 'T', 'D', 'success', 'm1', 'm2', '[\"im1\",\"im2\"]', "
                "'2026-06-01 00:00:00')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status, created_at) "
                "VALUES ('d1', 'b1', 'A', '抖音', '{\"title\": \"x\"}', 'success', '2026-06-01 00:00:00')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status, created_at) "
                "VALUES ('d2', 'b1', 'B', '抖音', '{}', 'success', '2026-06-01 00:00:01')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status, created_at) "
                "VALUES ('d3', 'b1', 'C', '小红书', '{\"title\": \"y\"}', 'success', '2026-06-01 00:00:02')")
            conn.execute(
                "INSERT INTO materials (id, original_filename, stored_path, file_type) VALUES ('m1', 'c.jpg', 'data/materials/c.jpg', 'image')")
            conn.commit()

        resp = self.client.get('/api/v2/publish-templates?type=video')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()['data']
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['page'], 1)
        self.assertEqual(data['page_size'], 20)
        item = data['list'][0]
        self.assertEqual(item['title'], 'T')
        self.assertEqual(item['thumbnail_path'], 'data/materials/c.jpg')
        self.assertEqual(item['first_image_id'], 'im1')
        # channels 去重（两个抖音 detail → 1 个 channel）
        self.assertEqual([c['platform'] for c in item['channels']], ['抖音', '小红书'])
        self.assertEqual(item['account_configs'], {'title': 'x'})

    def test_publish_templates_cover_falls_back_to_portrait(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO publish_batches (id, type, status, portrait_cover_material_id, created_at) "
                "VALUES ('b1', 'video', 'success', 'm9', '2026-06-01 00:00:00')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status, created_at) "
                "VALUES ('d1', 'b1', 'A', '抖音', '{\"a\":1}', 'success', '2026-06-01 00:00:00')")
            conn.execute(
                "INSERT INTO materials (id, original_filename, stored_path, file_type) VALUES ('m9', 'p.jpg', 'data/materials/p.jpg', 'image')")
            conn.commit()
        data = self.client.get('/api/v2/publish-templates?type=video').get_json()['data']
        self.assertEqual(data['list'][0]['thumbnail_path'], 'data/materials/p.jpg')

    def test_publish_templates_page_size_caps_100(self):
        resp = self.client.get('/api/v2/publish-templates?type=video&page_size=999')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['data']['page_size'], 100)

    # ---------- batch_delete_drafts ----------

    def test_batch_delete_invalid_ids_400(self):
        resp = self.client.delete('/api/v2/drafts/batch', json={'draft_ids': 'abc'})
        self.assertEqual(resp.status_code, 400)
        resp2 = self.client.delete('/api/v2/drafts/batch', json={'draft_ids': []})
        self.assertEqual(resp2.status_code, 400)
        resp3 = self.client.delete('/api/v2/drafts/batch', json={})
        self.assertEqual(resp3.status_code, 400)
        too_many = list(range(31))
        resp4 = self.client.delete('/api/v2/drafts/batch', json={'draft_ids': too_many})
        self.assertEqual(resp4.status_code, 400)

    def test_batch_delete_mixed_existing_and_missing(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("INSERT INTO drafts (id, type, title) VALUES (1, 'video', 'A')")
            conn.execute("INSERT INTO drafts (id, type, title) VALUES (2, 'video', 'B')")
            conn.commit()
        resp = self.client.delete('/api/v2/drafts/batch', json={'draft_ids': [1, 3]})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body['deleted'], [1])
        self.assertEqual(body['failed'], [{'draft_id': 3, 'reason': '草稿不存在'}])
        with sqlite3.connect(str(DB_PATH)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM drafts WHERE id IN (1, 2)").fetchone()[0], 1)

    # ---------- 补充：异常/坏 JSON 兜底分支 ----------

    def test_get_drafts_corrupt_draft_data_ignored(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, title, draft_data, channels_summary) "
                "VALUES (1, 'video', 'V', '{bad', '[]')")
            conn.commit()
        resp = self.client.get('/api/v2/drafts')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.get_json()['data']), 1)

    def test_create_draft_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.post('/api/v2/drafts', json={'draft_data': {'a': 1}})
        self.assertEqual(resp.status_code, 500)

    def test_get_draft_corrupt_draft_data_falls_back_empty(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, title, draft_data) VALUES (1, 'video', 'V', '{bad')")
            conn.commit()
        resp = self.client.get('/api/v2/drafts/1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['data']['draft_data'], {})

    def test_get_draft_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.get('/api/v2/drafts/1')
        self.assertEqual(resp.status_code, 500)

    def test_update_draft_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.put('/api/v2/drafts/1', json={'draft_data': {'a': 1}})
        self.assertEqual(resp.status_code, 500)

    def test_delete_draft_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.delete('/api/v2/drafts/1')
        self.assertEqual(resp.status_code, 500)

    def test_publish_templates_corrupt_image_ids(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO publish_batches (id, type, status, image_material_ids, created_at) "
                "VALUES ('b1', 'video', 'success', '{bad', '2026-06-01 00:00:00')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status, created_at) "
                "VALUES ('d1', 'b1', 'A', '抖音', '{\"a\":1}', 'success', '2026-06-01 00:00:00')")
            conn.commit()
        data = self.client.get('/api/v2/publish-templates?type=video').get_json()['data']
        self.assertIsNone(data['list'][0]['first_image_id'])

    def _valid_draft_data(self, account_ids):
        return {
            'commonConfig': {'videoPortrait': {'stored_path': '/abs/v.mp4'},
                             'coverPortrait': {'stored_path': '/abs/c.jpg'}},
            'platformConfigs': {'xiaohongshu': {'title': 'T', 'videoFormat': 'portrait',
                                                'aiContent': 'AI'}},
            'platformOverrides': {},
            'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait'}},
            'publishAccountIds': account_ids,
        }

    def _patch_batch_publish_deps(self):
        deps = [
            mock.patch('app._get_db_path', return_value=DB_PATH),
            mock.patch('services.draft_merge.DB_PATH', DB_PATH),
            mock.patch('ext_api.task_queue.get_task_queue',
                       return_value=mock.MagicMock()),
        ]
        for d in deps:
            d.start()
        self.addCleanup(lambda: [d.stop() for d in deps])

    def test_batch_publish_account_missing(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, draft_data) VALUES (1, 'video', ?)",
                (json.dumps(self._valid_draft_data([99]), ensure_ascii=False),))
            conn.commit()
        self._patch_batch_publish_deps()
        resp = self.client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [1]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['failed'],
                         [{'draft_id': 1, 'reason': '账号 99 不存在'}])
        self.assertEqual(resp.get_json()['task_ids'], [])

    def test_batch_publish_unknown_platform(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, draft_data) VALUES (1, 'video', ?)",
                (json.dumps(self._valid_draft_data([1]), ensure_ascii=False),))
            conn.execute(
                "INSERT INTO user_info (id, type, filePath, userName) VALUES (1, 999, '/c', 'C')")
            conn.commit()
        self._patch_batch_publish_deps()
        resp = self.client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [1]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['failed'],
                         [{'draft_id': 1, 'reason': '未知平台: '}])

    def test_batch_delete_delete_error_reported(self):
        class _FakeConn:
            def execute(self, sql, *args):
                if sql.strip().upper().startswith('DELETE'):
                    raise RuntimeError('delete blocked')
                return self

            def fetchall(self):
                return [(1,)]

            def commit(self):
                pass

            def close(self):
                pass

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("INSERT INTO drafts (id, type, title) VALUES (1, 'video', 'A')")
            conn.commit()
        with mock.patch('ext_api.sqlite3.connect', return_value=_FakeConn()):
            resp = self.client.delete('/api/v2/drafts/batch', json={'draft_ids': [1]})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body['deleted'], [])
        self.assertEqual(body['failed'], [{'draft_id': 1, 'reason': 'delete blocked'}])

    # ---------- 补充：helper 纯函数 / 历史域分支 ----------

    def test_ensure_tables_error_is_silent(self):
        import ext_api
        from ext_api import _ensure_tables
        ext_api._tables_ensured = False
        try:
            class _BadConn:
                def execute(self, *a, **k):
                    raise RuntimeError('db down')

            # 不抛异常（静默兜底），并置位标志
            _ensure_tables(_BadConn())
            self.assertTrue(ext_api._tables_ensured)
            # 幂等：二次调用直接返回
            _ensure_tables(_BadConn())
        finally:
            ext_api._tables_ensured = False

    def test_to_beijing_time_none_and_invalid(self):
        from ext_api import _to_beijing_time
        self.assertIsNone(_to_beijing_time(None))
        self.assertEqual(_to_beijing_time(''), '')
        self.assertEqual(_to_beijing_time('not-a-date'), 'not-a-date')
        self.assertEqual(_to_beijing_time(None), None)
        self.assertEqual(_to_beijing_time('2026-06-01 00:00:00'),
                         '2026-06-01T08:00:00+08:00')

    def test_resolve_cover_url(self):
        from ext_api import _resolve_cover_url
        self.assertEqual(_resolve_cover_url(''), '')
        self.assertEqual(_resolve_cover_url(None), '')
        # DB 无该 material
        self.assertEqual(_resolve_cover_url('no-such-id'), '')
        # DB 命中
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO materials (id, original_filename, stored_path, file_type) "
                "VALUES ('m1', 'c.jpg', 'data/materials/a b/c.jpg', 'image')")
            conn.commit()
        self.assertEqual(_resolve_cover_url('m1'),
                         '/api/materials/file/data%2Fmaterials%2Fa%20b%2Fc.jpg')
        # DB 异常 → 空串
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            self.assertEqual(_resolve_cover_url('m1'), '')

    def test_resolve_cover_from_path(self):
        from ext_api import _resolve_cover_from_path
        # dict 无匹配 key → ''
        self.assertEqual(_resolve_cover_from_path({'foo': 'x'}), '')
        # dict 匹配 stored_path 优先
        self.assertEqual(
            _resolve_cover_from_path({'path': '/p.jpg', 'stored_path': 'data/materials/s.jpg'}),
            '/api/materials/file/materials%2Fs.jpg')
        # None / 非字符串 → ''
        self.assertEqual(_resolve_cover_from_path(None), '')
        self.assertEqual(_resolve_cover_from_path(123), '')
        # Linux 绝对路径
        self.assertEqual(
            _resolve_cover_from_path('/home/x/data/materials/2026/06/13/u.jpg'),
            '/api/materials/file/materials%2F2026%2F06%2F13%2Fu.jpg')
        # Windows 绝对路径
        self.assertEqual(
            _resolve_cover_from_path('D:\\data\\materials\\2026\\06\\13\\u.jpg'),
            '/api/materials/file/materials%2F2026%2F06%2F13%2Fu.jpg')
        # 相对路径 covers/（不带 materials/ 前缀）
        self.assertEqual(
            _resolve_cover_from_path('covers/a.jpg'),
            '/api/materials/file/covers%2Fa.jpg')
        self.assertEqual(
            _resolve_cover_from_path('videos/b.mp4'),
            '/api/materials/file/videos%2Fb.mp4')
        # 纯文件名兜底 basename
        self.assertEqual(
            _resolve_cover_from_path('justname.jpg'),
            '/api/materials/file/justname.jpg')

    def test_compute_personalized(self):
        from ext_api._personalized import compute_personalized
        batch = {'title': 'T', 'description': 'D', 'video_material_id': 'v1',
                 'landscape_cover_material_id': 'l1', 'portrait_cover_material_id': 'p1',
                 'image_material_ids': '["i1"]'}
        # 完全一致 → False
        cfg = {'title': 'T', 'description': 'D',
               'videoLandscape': {'id': 'v1'}, 'coverLandscape': {'id': 'l1'},
               'coverPortrait': {'id': 'p1'}, 'images': [{'id': 'i1'}]}
        self.assertFalse(compute_personalized(cfg, batch))
        # title 不一致
        self.assertTrue(compute_personalized({'title': 'X'}, batch))
        # description 不一致
        self.assertTrue(compute_personalized({'description': 'X'}, batch))
        # video id 不一致
        self.assertTrue(compute_personalized({'videoPortrait': {'id': 'other'}}, batch))
        # coverLandscape 不一致
        self.assertTrue(compute_personalized({'coverLandscape': {'id': 'other'}}, batch))
        # coverPortrait 不一致
        self.assertTrue(compute_personalized({'coverPortrait': {'id': 'other'}}, batch))
        # images 不一致（含坏 JSON batch）
        self.assertTrue(compute_personalized({'images': [{'id': 'x'}]},
                                             {'image_material_ids': '{bad'}))
        self.assertTrue(compute_personalized({'images': [{'id': 'x'}]}, {}))
        # coverImage 与 batch 第一张图不一致
        self.assertTrue(compute_personalized({'coverImage': {'id': 'zzz'}}, batch))
        # coverImage 与第一张一致 → 不算个性化
        self.assertFalse(compute_personalized({'coverImage': {'id': 'i1'}}, batch))
        # 空输入 → False
        self.assertFalse(compute_personalized(None, None))
        self.assertFalse(compute_personalized({}, {}))

    def test_history_time_range_today(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO publish_batches (id, type, status, created_at) "
                "VALUES ('b1', 'video', 'success', datetime('now', 'localtime'))")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) "
                "VALUES ('d1', 'b1', 'A', '抖音', "
                "'{\"coverLandscape\": {\"path\": \"covers/a.jpg\"}}', 'success')")
            conn.commit()
        for tr in ('today', '7days', '30days'):
            resp = self.client.get(f'/api/v2/history?timeRange={tr}')
            self.assertEqual(resp.status_code, 200, tr)
            self.assertGreaterEqual(resp.get_json()['data']['total'], 1, tr)

    def test_history_status_and_date_filters(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO publish_batches (id, type, status, created_at) "
                "VALUES ('b1', 'video', 'success', '2026-08-01 00:00:00')")
            conn.execute(
                "INSERT INTO publish_batches (id, type, status, created_at) "
                "VALUES ('b2', 'video', 'failed', '2026-07-01 00:00:00')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) "
                "VALUES ('d1', 'b1', 'A', '抖音', '{\"videoLandscape\": 1}', 'success')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) "
                "VALUES ('d2', 'b2', 'B', '抖音', '{\"videoLandscape\": 1}', 'failed')")
            conn.commit()
        data = self.client.get('/api/v2/history?status=failed').get_json()['data']
        self.assertEqual([i['id'] for i in data['items']], ['b2'])
        data = self.client.get('/api/v2/history?type=image').get_json()['data']
        self.assertEqual(data['total'], 0)
        data = self.client.get(
            '/api/v2/history?startDate=2026-08-01&endDate=2026-08-31').get_json()['data']
        self.assertEqual([i['id'] for i in data['items']], ['b1'])
        # include_legacy=1 时不过滤
        data = self.client.get('/api/v2/history?include_legacy=1').get_json()['data']
        self.assertEqual(data['total'], 2)

    def test_history_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.get('/api/v2/history')
        self.assertEqual(resp.status_code, 500)

    def test_normalize_detail_row_duration_and_platform(self):
        from ext_api import _normalize_detail_row
        # 无 started/finished → duration None
        d = _normalize_detail_row({'account_configs': '{}', 'platform': '抖音'})
        self.assertIsNone(d['duration'])
        # 正常 duration 计算
        d = _normalize_detail_row({
            'account_configs': '{}', 'platform': '抖音',
            'started_at': '2026-06-01T00:00:00', 'finished_at': '2026-06-01T00:01:30'})
        self.assertEqual(d['duration'], 90)
        # 坏时间 → duration None
        d = _normalize_detail_row({
            'account_configs': '{}', 'platform': '抖音',
            'started_at': 'bad', 'finished_at': 'bad'})
        self.assertIsNone(d['duration'])
        # 坏 account_configs JSON → {}
        d = _normalize_detail_row({'account_configs': '{bad', 'platform': '抖音'})
        self.assertEqual(d['account_configs'], {})
        # 拼音 key → 中文
        d = _normalize_detail_row({'account_configs': '{}', 'platform': 'iqiyi'})
        self.assertEqual(d['platform'], '爱奇艺')
        # platform 未知 + account_id → 查 user_info 校正
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("INSERT INTO user_info (id, type, filePath, userName) VALUES (7, 5, '/c', 'C')")
            conn.commit()
        d = _normalize_detail_row(
            {'account_configs': '{}', 'platform': '未知', 'account_id': 7})
        self.assertEqual(d['platform'], 'B站')

    def test_get_history_batch_not_found_404(self):
        resp = self.client.get('/api/v2/history/no-such')
        self.assertEqual(resp.status_code, 404)

    def test_get_history_batch_ok(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO publish_batches (id, type, status, created_at) "
                "VALUES ('b1', 'video', 'success', '2026-08-01 00:00:00')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) "
                "VALUES ('d1', 'b1', 'A', '抖音', '{}', 'success')")
            conn.commit()
        resp = self.client.get('/api/v2/history/b1')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()['data']
        self.assertEqual(data['id'], 'b1')
        self.assertEqual(len(data['items']), 1)

    def test_get_history_batch_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.get('/api/v2/history/b1')
        self.assertEqual(resp.status_code, 500)

    def test_batch_delete_history_invalid_400(self):
        for body in ({}, {'batch_ids': []}, {'batch_ids': 'x'}, {'batch_ids': list(range(51))}):
            resp = self.client.delete('/api/v2/history/batch', json=body)
            self.assertEqual(resp.status_code, 400)

    def test_batch_delete_history_mixed(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO publish_batches (id, type, status) VALUES ('b1', 'video', 'success')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) "
                "VALUES ('d1', 'b1', 'A', '抖音', '{}', 'success')")
            conn.commit()
        resp = self.client.delete('/api/v2/history/batch', json={'batch_ids': ['b1', 'zzz']})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body['deleted'], ['b1'])
        self.assertEqual(body['failed'], [{'batch_id': 'zzz', 'reason': '记录不存在'}])
        with sqlite3.connect(str(DB_PATH)) as conn:
            # 级联删除明细
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM publish_batches WHERE id='b1'").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM publish_details WHERE batch_id='b1'").fetchone()[0], 0)

    def test_batch_delete_history_delete_error(self):
        class _FakeConn:
            def __init__(self):
                self.calls = []

            def execute(self, sql, *args):
                self.calls.append(sql)
                if 'DELETE FROM publish_batches' in sql:
                    raise RuntimeError('delete blocked')
                return self

            def fetchall(self):
                return [('b1',)]

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        with mock.patch('ext_api._db_conn', return_value=_FakeConn()):
            resp = self.client.delete('/api/v2/history/batch', json={'batch_ids': ['b1']})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['failed'],
                         [{'batch_id': 'b1', 'reason': 'delete blocked'}])

    def test_batch_delete_history_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.delete('/api/v2/history/batch', json={'batch_ids': ['b1']})
        self.assertEqual(resp.status_code, 500)

    def test_delete_history_batch_not_found_404(self):
        resp = self.client.delete('/api/v2/history/no-such')
        self.assertEqual(resp.status_code, 404)

    def test_delete_history_batch_ok(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO publish_batches (id, type, status) VALUES ('b1', 'video', 'success')")
            conn.execute(
                "INSERT INTO publish_details (id, batch_id, account_name, platform, account_configs, status) "
                "VALUES ('d1', 'b1', 'A', '抖音', '{}', 'success')")
            conn.commit()
        resp = self.client.delete('/api/v2/history/b1')
        self.assertEqual(resp.status_code, 200)
        with sqlite3.connect(str(DB_PATH)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM publish_batches WHERE id='b1'").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM publish_details WHERE batch_id='b1'").fetchone()[0], 0)

    def test_delete_history_batch_db_error_500(self):
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            resp = self.client.delete('/api/v2/history/b1')
        self.assertEqual(resp.status_code, 500)

    # ---------- 补充：最终缺口分支 ----------

    def test_ensure_tables_error_path_covered(self):
        import ext_api
        ext_api._tables_ensured = False
        try:
            class _BadConn:
                def execute(self, *a, **k):
                    raise RuntimeError('db down')

            _ensure_tables = ext_api._ensure_tables
            _ensure_tables(_BadConn())  # 静默兜底
            self.assertTrue(ext_api._tables_ensured)
            _ensure_tables(_BadConn())  # 幂等直接 return
        finally:
            ext_api._tables_ensured = False

    def test_normalize_detail_row_platform_correction_db_error(self):
        from ext_api import _normalize_detail_row
        with mock.patch('ext_api._db_conn', side_effect=RuntimeError('boom')):
            d = _normalize_detail_row(
                {'account_configs': '{}', 'platform': '未知', 'account_id': 7})
        # 校正失败 → 保留原 platform
        self.assertEqual(d['platform'], '未知')

    def test_batch_delete_history_top_level_error_500(self):
        class _FakeConn:
            def execute(self, sql, *args):
                raise RuntimeError('query boom')

            def rollback(self):
                pass

            def close(self):
                pass

        with mock.patch('ext_api._db_conn', return_value=_FakeConn()):
            resp = self.client.delete('/api/v2/history/batch', json={'batch_ids': ['b1']})
        self.assertEqual(resp.status_code, 500)

    def test_delete_history_batch_top_level_error_500(self):
        class _FakeConn:
            def execute(self, sql, *args):
                raise RuntimeError('query boom')

            def rollback(self):
                pass

            def close(self):
                pass

        with mock.patch('ext_api._db_conn', return_value=_FakeConn()):
            resp = self.client.delete('/api/v2/history/b1')
        self.assertEqual(resp.status_code, 500)

    def test_get_draft_corrupt_channels_summary_falls_back_empty(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, title, draft_data, channels_summary) "
                "VALUES (1, 'video', 'V', '{}', '{bad')")
            conn.commit()
        resp = self.client.get('/api/v2/drafts/1')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['data']['channels_summary'], [])

    def test_batch_publish_enqueue_failure(self):
        draft_data = {
            'commonConfig': {'videoPortrait': {'stored_path': '/abs/v.mp4'},
                             'coverPortrait': {'stored_path': '/abs/c.jpg'}},
            'platformConfigs': {'xiaohongshu': {'title': 'T', 'videoFormat': 'portrait',
                                                'aiContent': 'AI'}},
            'platformOverrides': {},
            'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait',
                                       'aiContent': 'AI'}},
            'publishAccountIds': [1],
        }
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, draft_data) VALUES (1, 'video', ?)",
                (json.dumps(draft_data, ensure_ascii=False),))
            conn.execute(
                "INSERT INTO user_info (id, type, filePath, userName) VALUES (1, 3, '/c', 'C')")
            conn.commit()
        self._patch_batch_publish_deps()
        import ext_api
        with mock.patch.object(
                ext_api.task_queue.get_task_queue(), 'add_task',
                side_effect=RuntimeError('queue full')):
            resp = self.client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [1]})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('入队失败', resp.get_json()['failed'][0]['reason'])

    def test_batch_publish_validate_error(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO drafts (id, type, draft_data) VALUES (1, 'video', '{}')")
            conn.commit()
        self._patch_batch_publish_deps()
        import ext_api
        with mock.patch.object(ext_api, 'validate_draft_for_publish',
                               side_effect=RuntimeError('validate boom')):
            resp = self.client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [1]})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('validate boom', resp.get_json()['failed'][0]['reason'])


if __name__ == '__main__':
    unittest.main()
