"""测试可选访问令牌（access_token）鉴权中间件。

覆盖：未配置时全放行（默认行为不变）/ 配置后 /api/* 需 token /
settings 与 health 豁免 / Bearer 与 ?token= 两种携带方式。
隔离：独立临时库 + patch app._get_db_path / ext_api.DB_PATH，
不依赖共享 conftest 库，也不受其它测试模块覆盖 SAU_DATA_DIR 影响。
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import app


class TestAccessTokenAuth(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix='sau_auth_')
        self.db_path = Path(self._tmp) / "db" / "database.db"
        self.db_path.parent.mkdir(parents=True)
        # 完整 schema（get_tasks 等需要 publish_details 系列表）；临时替换 init_db.DB_PATH 后立即恢复
        import init_db as init_db_module
        orig_db_path = init_db_module.DB_PATH
        init_db_module.DB_PATH = self.db_path
        try:
            init_db_module.init_database()
            init_db_module.migrate_database()
        finally:
            init_db_module.DB_PATH = orig_db_path
        # auth guard 读 app._get_db_path；ext_api settings 读 ext_api.DB_PATH —— 统一指向独立库
        self._patch_app = mock.patch('app._get_db_path', return_value=self.db_path)
        self._patch_ext = mock.patch('ext_api.DB_PATH', self.db_path)
        self._patch_app.start()
        self._patch_ext.start()
        self.client = app.test_client()
        self._set_token(None)  # 默认未启用

    def tearDown(self):
        self._patch_app.stop()
        self._patch_ext.stop()

    def _set_token(self, value: str | None) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            if value is None:
                conn.execute("DELETE FROM settings WHERE key='access_token'")
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('access_token', ?)",
                    (value,),
                )
            conn.commit()
        finally:
            conn.close()

    def test_no_token_configured_allows_all(self):
        resp = self.client.get('/api/v2/tasks')
        self.assertEqual(resp.status_code, 200)

    def test_configured_requires_token(self):
        self._set_token('secret-token')
        resp = self.client.get('/api/v2/tasks')
        self.assertEqual(resp.status_code, 401)
        resp = self.client.get('/api/v2/tasks', headers={'Authorization': 'Bearer wrong'})
        self.assertEqual(resp.status_code, 401)

    def test_configured_accepts_bearer(self):
        self._set_token('secret-token')
        resp = self.client.get('/api/v2/tasks', headers={'Authorization': 'Bearer secret-token'})
        self.assertEqual(resp.status_code, 200)

    def test_configured_accepts_query_token(self):
        self._set_token('secret-token')
        resp = self.client.get('/api/v2/tasks?token=secret-token')
        self.assertEqual(resp.status_code, 200)

    def test_settings_and_health_exempt(self):
        self._set_token('secret-token')
        resp = self.client.get('/api/v2/settings')
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get('/api/health')
        self.assertEqual(resp.status_code, 200)

    def test_settings_returns_flag_not_plaintext(self):
        self._set_token('secret-token')
        data = self.client.get('/api/v2/settings').get_json()['data']
        self.assertIs(data.get('access_token_set'), True)
        self.assertNotIn('access_token', data)  # 明文不返回
        self._set_token(None)
        data = self.client.get('/api/v2/settings').get_json()['data']
        self.assertIs(data.get('access_token_set'), False)

    def test_static_assets_not_blocked(self):
        self._set_token('secret-token')
        resp = self.client.get('/assets/foo.js')
        self.assertNotEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
