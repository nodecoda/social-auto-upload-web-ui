"""测试 init_db 版本化迁移（schema_migrations）行为。

覆盖：版本表创建与版本记录 / 幂等重跑 / 存量库无版本记录时按序应用 /
迁移失败回滚（不记录版本）。

隔离策略：不在模块级设置 SAU_DATA_DIR / 覆盖 init_db.DB_PATH（会污染
pytest 收集阶段其它测试模块）；每个用例创建独立 DB 文件，仅在用例内
临时替换 init_db.DB_PATH，tearDown 恢复 conftest 共享库路径。
"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import init_db as init_db_module

_ORIGINAL_DB_PATH = init_db_module.DB_PATH


def _versions(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    finally:
        conn.close()


class TestVersionedMigrations(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix='sau_migrate_case_')
        self.db_path = Path(self._tmp) / "db" / "database.db"
        self.db_path.parent.mkdir(parents=True)
        init_db_module.DB_PATH = self.db_path
        init_db_module.init_database()
        # 全新用例库无版本记录（等价「存量库首次升级」状态），迁移按序全量重放

    def tearDown(self):
        init_db_module.DB_PATH = _ORIGINAL_DB_PATH

    def test_migrate_records_all_versions(self):
        init_db_module.migrate_database()
        versions = _versions(self.db_path)
        self.assertEqual(versions, {v for v, _, _ in init_db_module.MIGRATIONS})
        self.assertGreaterEqual(len(versions), 8)

    def test_migrate_is_idempotent(self):
        init_db_module.migrate_database()
        init_db_module.migrate_database()
        # 重跑后版本数不变（不重复记录）
        self.assertEqual(len(_versions(self.db_path)), len(init_db_module.MIGRATIONS))

    def test_migrate_preserves_columns_after_reapply(self):
        # 模拟存量库：清空版本记录重跑全部迁移（各迁移幂等跳过已存在列）
        init_db_module.migrate_database()
        conn = sqlite3.connect(str(self.db_path))
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(user_info)")}
        finally:
            conn.close()
        for col in ('avatar', 'fans', 'likes', 'follows', 'stats'):
            self.assertIn(col, cols, f"user_info.{col} 列应存在")

    def test_migration_failure_rolls_back_and_skips_version(self):
        def _boom(conn):
            raise RuntimeError("boom")

        init_db_module.MIGRATIONS.append((999, "boom", _boom))
        try:
            with self.assertRaises(RuntimeError):
                init_db_module.migrate_database()
        finally:
            init_db_module.MIGRATIONS.pop()
        versions = _versions(self.db_path)
        self.assertNotIn(999, versions)
        self.assertGreaterEqual(len(versions), len(init_db_module.MIGRATIONS) - 1)

    def test_migrations_table_exists(self):
        init_db_module.migrate_database()
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)


if __name__ == "__main__":
    unittest.main()
