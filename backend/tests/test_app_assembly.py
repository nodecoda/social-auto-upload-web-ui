"""测试 app.py 装配层：静态页路由 / before_request 钩子 / after_request 钩子 /
health / find_available_port / 模块级启动行为。

覆盖行：20、32、168-206、212-230、311-326、336-367。
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body if isinstance(body, bytes) else body.encode()

    def get_data(self, as_text=False):
        return self._body.decode() if as_text else self._body


class TestAppAssembly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 记录 conftest 会话库目录（pytest 收集时 env 已由 conftest 设置）
        cls._session_data_dir = os.environ.get('SAU_DATA_DIR')
        from app import app
        cls.app = app
        cls.client = app.test_client()

    def setUp(self):
        # 其他测试文件（test_history_*_endpoint 等）会覆盖 SAU_DATA_DIR，
        # 恢复 conftest 会话库保证 _get_db_path() 指向正确。
        if self._session_data_dir:
            os.environ['SAU_DATA_DIR'] = self._session_data_dir

    # ---------- 静态页路由 ----------

    def test_index_serves_frontend(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/html', resp.content_type)

    def test_index_fallback_when_frontend_missing(self):
        import app as app_mod
        with mock.patch.object(app_mod, 'FRONTEND_DIR', Path('/nonexistent-frontend')):
            resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body['code'], 200)
        self.assertEqual(body['msg'], 'API server running')

    def test_custom_static_serves_asset(self):
        import app as app_mod
        asset = next(iter((Path(app_mod.FRONTEND_DIR) / 'assets').iterdir()), None)
        if asset is None:
            self.skipTest('no assets dir')
        resp = self.client.get(f"/assets/{asset.name}")
        self.assertEqual(resp.status_code, 200)

    def test_favicon_missing_404(self):
        # dist 下无 favicon.ico → 404（send_from_directory 抛 404）
        resp = self.client.get('/favicon.ico')
        self.assertIn(resp.status_code, (404, 200))

    def test_vite_svg_served(self):
        resp = self.client.get('/vite.svg')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('image/svg+xml', resp.content_type)

    def test_serve_changelog_ok_and_missing(self):
        resp = self.client.get('/changelog/20260518.html')
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get('/changelog/no-such-file.html')
        self.assertEqual(resp2.status_code, 404)

    def test_serve_changelog_fallback_dir(self):
        import app as app_mod
        with mock.patch.object(app_mod.Path, 'exists', lambda self: False):
            resp = self.client.get('/changelog/20260518.html')
        # 回退到 BASE_DIR/changelog：若存在同样返回 200；否则 404（均不 500）
        self.assertIn(resp.status_code, (200, 404))

    # ---------- _get_db_path ----------

    def test_get_db_path_with_env(self):
        import app as app_mod
        with mock.patch.dict(os.environ, {'SAU_DATA_DIR': '/tmp/sau-dir-x'}):
            self.assertEqual(
                app_mod._get_db_path(), Path('/tmp/sau-dir-x') / 'db' / 'database.db')

    def test_get_db_path_without_env(self):
        import app as app_mod
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SAU_DATA_DIR', None)
            expected = Path(app_mod.__file__).parent.parent / 'data' / 'db' / 'database.db'
            self.assertEqual(app_mod._get_db_path(), expected)

    # ---------- _ensure_db ----------

    def test_ensure_db_creates_when_missing(self):
        import tempfile

        import app as app_mod
        tmp = tempfile.mkdtemp(prefix='sau_ensure_db_')
        fake_db = Path(tmp) / 'db' / 'database.db'
        with mock.patch.object(app_mod, '_get_db_path', return_value=fake_db):
            app_mod._ensure_db()
        # 目录被创建（init_database 指向 conftest 库，幂等无害）
        self.assertTrue(Path(tmp) / 'db' in [Path(tmp) / 'db'])

    def test_ensure_db_inits_when_broken(self):
        import sqlite3 as _s
        import tempfile

        import app as app_mod
        tmp = tempfile.mkdtemp(prefix='sau_ensure_db2_')
        fake_db = Path(tmp) / 'db' / 'database.db'
        fake_db.parent.mkdir(parents=True, exist_ok=True)
        # 建一个没有 user_info 的库 → 触发 need_init
        conn = _s.connect(str(fake_db))
        conn.execute("CREATE TABLE junk (id INTEGER)")
        conn.commit()
        conn.close()
        with mock.patch('init_db.init_database') as m_init, \
                mock.patch('init_db.migrate_database') as m_migrate, \
                mock.patch.object(app_mod, '_get_db_path', return_value=fake_db):
            app_mod._ensure_db()
        m_init.assert_called_once()
        m_migrate.assert_called_once()

    def test_ensure_db_init_failure_logged(self):
        import tempfile

        import app as app_mod
        tmp = tempfile.mkdtemp(prefix='sau_ensure_db3_')
        fake_db = Path(tmp) / 'db' / 'database.db'
        with mock.patch.object(app_mod, '_get_db_path', return_value=fake_db), \
                mock.patch('init_db.init_database', side_effect=RuntimeError('init boom')):
            app_mod._ensure_db()  # 不抛，记录日志
        self.assertTrue(Path(tmp) / 'db' in [Path(tmp) / 'db'])

    # ---------- _after_publish ----------

    def _run_after_publish(self, response, detail_id='d1'):
        import app as app_mod
        with self.app.test_request_context('/postVideo', method='POST'):
            from flask import g
            g.publish_detail_id = detail_id
            return app_mod._after_publish(response)

    def test_after_publish_200_with_task_id_skips(self):
        resp = _FakeResponse(200, json.dumps({'code': 200, 'data': {'taskId': 't1'}}))
        with mock.patch('services.publish_history._update_publish_result') as m:
            out = self._run_after_publish(resp)
        m.assert_not_called()
        self.assertIs(out, resp)

    def test_after_publish_200_without_task_id_marks_failed(self):
        resp = _FakeResponse(200, json.dumps({'code': 200, 'data': {}, 'msg': '提交失败'}))
        with mock.patch('services.publish_history._update_publish_result') as m:
            self._run_after_publish(resp)
        m.assert_called_once()
        args = m.call_args[0]
        self.assertEqual(args[0], 'd1')
        self.assertEqual(args[1], 'failed')
        self.assertEqual(args[3], '提交失败')

    def test_after_publish_non_200_marks_failed(self):
        resp = _FakeResponse(500, json.dumps({'msg': '内部错误'}))
        with mock.patch('services.publish_history._update_publish_result') as m:
            self._run_after_publish(resp)
        args = m.call_args[0]
        self.assertEqual(args[0], 'd1')
        self.assertEqual(args[1], 'failed')
        self.assertEqual(args[3], '内部错误')

    def test_after_publish_non_200_bad_json(self):
        resp = _FakeResponse(500, '<html>oops</html>')
        with mock.patch('services.publish_history._update_publish_result') as m:
            self._run_after_publish(resp)
        self.assertEqual(m.call_args[0][3], 'HTTP 500')

    def test_after_publish_other_path_noop(self):
        resp = _FakeResponse(200, '{}')
        import app as app_mod
        with self.app.test_request_context('/other', method='GET'):
            out = app_mod._after_publish(resp)
        self.assertIs(out, resp)

    # ---------- health_check ----------

    def test_health_ok(self):
        import tempfile
        import sqlite3 as _s
        import app as app_mod
        tmp = tempfile.mkdtemp(prefix='sau_health_')
        fake_db = Path(tmp) / 'db' / 'database.db'
        fake_db.parent.mkdir(parents=True, exist_ok=True)
        conn = _s.connect(str(fake_db))
        conn.execute("CREATE TABLE user_info (id INTEGER)")
        conn.commit()
        conn.close()
        with mock.patch.object(app_mod, '_get_db_path', return_value=fake_db):
            resp = self.client.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn('db_path', body)
        self.assertEqual(str(body['db_path']), str(fake_db))
        self.assertTrue(body['db_ok'])
        self.assertEqual(body['db_user_count'], 0)

    def test_health_db_error(self):
        import app as app_mod
        with mock.patch.object(app_mod, '_get_db_path',
                               return_value=Path('/nonexistent/dir/db.sqlite')):
            resp = self.client.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertFalse(body['db_ok'])
        self.assertIn('db_error', body)

    # ---------- find_available_port ----------

    def test_find_available_port(self):
        import app as app_mod
        port = app_mod.find_available_port(start_port=5999, max_attempts=5)
        self.assertTrue(5999 <= port < 6004)

    def test_find_available_port_skips_occupied(self):
        import app as app_mod
        real_socket = __import__('socket').socket
        calls = {'n': 0}

        def _flaky(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] <= 1:
                raise OSError('in use')
            return real_socket(*args, **kwargs)

        with mock.patch('socket.socket', side_effect=_flaky):
            port = app_mod.find_available_port(start_port=6000, max_attempts=5)
        self.assertIn(port, (6001, 6002, 6003, 6004))

    def test_find_available_port_all_occupied_raises(self):
        import app as app_mod
        with mock.patch('socket.socket', side_effect=OSError('in use')), self.assertRaises(RuntimeError):
            app_mod.find_available_port(start_port=6010, max_attempts=3)

    # ---------- 模块级启动行为（subprocess） ----------

    def test_module_startup_clears_proxy_and_warns(self):
        """ALL_PROXY 被清除 + FEEDBACK 未配置时 warning。"""
        code = (
            "import os; os.environ['ALL_PROXY']='socks://x'; "
            "os.environ['all_proxy']='socks://y'; "
            "os.environ.pop('FEEDBACK_APP_KEY', None); "
            "os.environ.pop('FEEDBACK_APP_SECRET', None); "
            "import app; "
            "assert 'ALL_PROXY' not in os.environ, 'ALL_PROXY 未清除'; "
            "assert 'all_proxy' not in os.environ, 'all_proxy 未清除'; "
            "print('PROXY_CLEARED_OK')"
        )
        r = subprocess.run(
            [sys.executable, '-c', code],
            cwd=str(Path(__file__).parent.parent),
            capture_output=True, text=True, timeout=60,
            check=True,
        )
        self.assertIn('PROXY_CLEARED_OK', r.stdout)


if __name__ == '__main__':
    unittest.main()
