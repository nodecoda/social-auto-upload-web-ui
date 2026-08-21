"""测试 /api/image-publish/publish 写入新表的行为"""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

_tmpdir = tempfile.mkdtemp()
os.environ['SAU_DATA_DIR'] = _tmpdir
DB_PATH = Path(_tmpdir) / "db" / "database.db"

# 测试用 DB 的 schema（与 init_db.py 一致）
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS publish_batches (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    video_material_id TEXT DEFAULT '',
    image_material_ids TEXT DEFAULT '[]',
    landscape_cover_material_id TEXT DEFAULT '',
    portrait_cover_material_id TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    account_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    schedule_time TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
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
    finished_at TIMESTAMP,
    FOREIGN KEY (batch_id) REFERENCES publish_batches(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL DEFAULT '',
    stored_path TEXT DEFAULT '',
    file_type TEXT DEFAULT ''
);
"""


def _setup():
    """在测试自己的 DB_PATH 建好 schema"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()


class TestImagePublishEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _setup()
        from app import app
        cls.app = app

    def setUp(self):
        # mock 掉真实 platform publish_image，避免启动 Chromium（每次 3 分钟）
        # get_platform 在 image_publish_bp 中是函数内 import，
        # 所以 patch 它在 impl.registry 模块里的位置
        self._fake_platform = MagicMock()
        self._fake_platform.publish_image = MagicMock(return_value=True)
        self._fake_platform.platform_name = '微博'  # R6 入队后 detail.platform 取 platform_name
        self._patches = [
            patch("impl.registry.get_platform", return_value=self._fake_platform),
            patch("blueprints.image_publish_bp.DB_PATH", DB_PATH),
            patch("blueprints.image_publish_bp.resolve_material_path",
                  side_effect=lambda p: p or "/tmp/fake.jpg"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_creates_batch_and_detail(self):
        """单次 /api/image-publish/publish 应插 1 batch + 1 detail（type='image'）"""
        client = self.app.test_client()
        # account_configs 是单个 dict（不是 list），按 spec §3.4
        client.post('/api/image-publish/publish', json={
            'image_ids': [],
            'account_configs': {
                'account_id': 1,
                'platform': 'douyin',
                'filePath': '/tmp/fake_cookie.json',
                'title': '测试图文',
                'description': '描述',
                'tags': ['标签1'],
            },
            'batchId': 'batch-img-1',
            'landscapeCoverMaterialId': '',
            'portraitCoverMaterialId': 'mat-cover-p-1',
        })
        # 不在意 200 还是 4xx，关键是数据写入
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        batch = conn.execute("SELECT * FROM publish_batches WHERE id = 'batch-img-1'").fetchone()
        details = conn.execute("SELECT * FROM publish_details WHERE batch_id = 'batch-img-1'").fetchall()
        conn.close()
        self.assertIsNotNone(batch)
        self.assertEqual(batch['type'], 'image')
        self.assertEqual(batch['portrait_cover_material_id'], 'mat-cover-p-1')
        self.assertEqual(len(details), 1)

    def test_publish_endpoint_enqueues_image_task(self):
        """R6 入队化：POST /api/image-publish/publish 带 platform='weibo'/'微博' 时,
        构造 publish_kind='image' 的 PublishTask 入队 task_queue（platform_type=11）,
        payload 携带完整 kwargs；不再请求线程内同步调 publish_image。

        间接验证 platform_map 含 'weibo': 11 / '微博': 11
        （platform_map 是 publish_images() 内局部变量,模块导入不可见）。
        """
        # 准备 materials 表里的一张图片,让 image_files 非空,从而走入队分支
        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute("ALTER TABLE materials ADD COLUMN stored_path TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # 本测试类的其它用例可能已加过列
        conn.execute(
            "INSERT OR REPLACE INTO materials (id, original_filename, stored_path, file_type) "
            "VALUES (?, ?, ?, ?)",
            ('img1', 'fake_img1.jpg', '/tmp/fake_img1.jpg', 'image'),
        )
        conn.commit()
        conn.close()

        # patch storage.get_local_path,确保返回本地路径
        from storage import local as storage_local
        fake_queue = MagicMock()
        with patch.object(storage_local.LocalStorage, 'get_local_path',
                          return_value='/tmp/fake_img1.jpg'),              patch('ext_api.task_queue.get_task_queue', return_value=fake_queue):
            client = self.app.test_client()

            # Case 1: platform='weibo' → platform_id=11
            client.post('/api/image-publish/publish', json={
                'image_ids': ['img1'],
                'account_configs': {
                    'account_id': 1,
                    'platform': 'weibo',
                    'filePath': '/tmp/fake_cookie.json',
                    'title': '测试微博图集',
                    'description': '测试描述',
                    'tags': ['测试'],
                    'aiContent': '内容由AI生成',
                },
                'batchId': 'batch-weibo-1',
            })
            # Case 2: platform='微博' (中文) → platform_id=11
            client.post('/api/image-publish/publish', json={
                'image_ids': ['img1'],
                'account_configs': {
                    'account_id': 1,
                    'platform': '微博',
                    'filePath': '/tmp/fake_cookie.json',
                    'title': '测试微博图集中文',
                    'description': '测试描述',
                    'tags': ['测试'],
                    'aiContent': '内容由AI生成',
                },
                'batchId': 'batch-weibo-2',
            })

        # 入队化后：不直接调 publish_image，而是 add_task 入队 2 个 image 任务
        self.assertEqual(self._fake_platform.publish_image.call_count, 0)
        self.assertEqual(fake_queue.add_task.call_count, 2)

        # 验证入队 task 的 kind / 平台路由 / payload 透传
        task1 = fake_queue.add_task.call_args_list[0].args[0]
        self.assertEqual(task1.publish_kind, 'image')
        self.assertEqual(task1.platform_type, 11)
        self.assertEqual(task1.platform, '微博')
        self.assertEqual(task1.payload['title'], '测试微博图集')
        self.assertEqual(task1.payload['desc'], '测试描述')
        self.assertEqual(task1.payload['ai_content'], '内容由AI生成')
        self.assertEqual(task1.payload['files'], ['/tmp/fake_img1.jpg'])
        self.assertEqual(task1.payload['account_file'], ['/tmp/fake_cookie.json'])

        task2 = fake_queue.add_task.call_args_list[1].args[0]
        self.assertEqual(task2.platform_type, 11)
        self.assertEqual(task2.payload['title'], '测试微博图集中文')


if __name__ == '__main__':
    unittest.main()
