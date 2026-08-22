"""BasePlatform 公共逻辑契约测试（T13）。

覆盖：统一浏览器入口委托 / cookie 导入 4 步流程全路径
（解析失败、空 cookies、新账号 INSERT、re-import UPDATE、sync 三形态、
sync 失败不阻断、cookie 失效清理、DB 异常）/ 可选 stub 默认 NotImplementedError。
"""
import json
import sys
from pathlib import Path
from queue import Queue
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from impl.base_platform import BasePlatform


class _FakeCursor:
    def __init__(self, lastrowid=321):
        self.executed = []
        self.lastrowid = lastrowid

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


class _FakeConn:
    def __init__(self, cursor=None, raise_on_enter=False):
        self.cursor_ = cursor or _FakeCursor()
        self.raise_on_enter = raise_on_enter
        self.commit_count = 0

    def __enter__(self):
        if self.raise_on_enter:
            raise RuntimeError('db down')
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self.cursor_

    def commit(self):
        self.commit_count += 1


class _FakePlatform(BasePlatform):
    platform_id = 99
    platform_key = 'fake'
    platform_name = 'Fake'
    supports_cookie_import = True

    async def login(self, id, status_queue, account_id=None):
        pass

    async def check_cookie(self, cookie_file):
        return True

    async def open_creator_center(self, cookie_file):
        pass

    async def publish_video(self, **kwargs):
        return True

    def _parse_cookie_to_storage_state(self, cookie_str):
        return ([{'name': 'a', 'value': '1', 'domain': '.fake.com'}], [])

    async def sync_profile(self, cookie_file):
        return {'name': '测试号', 'avatar': 'a.png', 'stats': [{'x': 1}]}


def _drain(q: Queue) -> list[dict]:
    items = []
    while not q.empty():
        items.append(json.loads(q.get()))
    return items


# ── 浏览器入口委托 ──────────────────────────────────────────────────────────

class TestBrowserDelegation:
    @pytest.fixture
    def platform(self):
        return _FakePlatform()

    def test_create_browser_passthrough(self, platform):
        with patch('impl.base_platform._create_browser') as m:
            m.return_value = 'browser'
            result = _run_async(platform.create_browser(
                headless=False, login_mode=True, humanize=True, human_preset='fast'))
        assert result == 'browser'
        m.assert_called_once_with(
            headless=False, login_mode=True, humanize=True, human_preset='fast')

    def test_create_context_passthrough(self, platform):
        with patch('impl.base_platform._create_context') as m:
            m.return_value = 'ctx'
            result = _run_async(platform.create_context('b', storage_state='s.json', user_agent='ua'))
        assert result == 'ctx'
        m.assert_called_once_with('b', storage_state='s.json', user_agent='ua')

    def test_close_browser_default(self, platform):
        with patch('impl.base_platform._close_browser') as m:
            _run_async(platform.close_browser('b'))
        m.assert_called_once_with('b', is_close_by_code=True)

    def test_close_browser_false(self, platform):
        with patch('impl.base_platform._close_browser') as m:
            _run_async(platform.close_browser('b', is_close_by_code=False))
        m.assert_called_once_with('b', is_close_by_code=False)

    def test_create_persistent_context(self, platform):
        with patch('impl.base_platform._create_persistent_context') as m:
            m.return_value = 'pctx'
            result = _run_async(platform.create_persistent_context('/data', headless=True))
        assert result == 'pctx'
        m.assert_called_once_with(user_data_dir='/data', headless=True)


def _run_async(coro):
    import asyncio
    return asyncio.run(coro)


# ── 默认实现 ────────────────────────────────────────────────────────────────

class TestDefaults:
    def test_parse_cookie_uses_base_generic_impl(self):
        """A6/R9-2: 基类提供通用解析实现（不再抛 NotImplementedError）。

        未重写 _parse_cookie_to_storage_state 的平台继承基类逻辑：
        k=v 解析到 platform_cookie_domain（未设置时为 ''）。
        """
        class _Bare(BasePlatform):
            platform_id = 97
            platform_key = 'bare'
            platform_name = 'Bare'
            platform_cookie_domain = '.bare.com'

            async def login(self, id, status_queue, account_id=None):
                pass

            async def check_cookie(self, cookie_file):
                return True

            async def open_creator_center(self, cookie_file):
                pass

            async def publish_video(self, **kwargs):
                return True

            async def sync_profile(self, cookie_file):
                return {}

        cookies, origins = _Bare()._parse_cookie_to_storage_state('a=1; b=2; bad')
        assert origins == []
        assert len(cookies) == 2
        assert cookies[0]['name'] == 'a' and cookies[0]['value'] == '1'
        assert cookies[0]['domain'] == '.bare.com'
        assert cookies[0]['path'] == '/'
        assert cookies[0]['httpOnly'] is True

    @pytest.mark.parametrize('method', ['publish_note', 'publish_image', 'get_statistics'])
    def test_optional_stubs_raise(self, method):
        with pytest.raises(NotImplementedError):
            _run_async(getattr(_FakePlatform(), method)())


# ── import_cookie ───────────────────────────────────────────────────────────

class TestImportCookie:
    def _setup(self, tmp_path, parse=None, sync=None, conn=None):
        platform = _FakePlatform()
        if parse:
            platform._parse_cookie_to_storage_state = parse
        if sync:
            platform.sync_profile = sync
        q = Queue()
        patches = [
            patch('impl.base_platform.BASE_DIR', tmp_path),
            patch('impl.base_platform.sqlite3.connect',
                  return_value=conn if conn is not None else _FakeConn()),
        ]
        return platform, q, patches

    def test_parse_failure_error_step1(self, tmp_path):
        platform, q, patches = self._setup(
            tmp_path,
            parse=lambda s: (_ for _ in ()).throw(RuntimeError('bad cookie')))
        with patches[0], patches[1], pytest.raises(RuntimeError, match='bad cookie'):
            _run_async(platform.import_cookie('k=v', q))
        events = _drain(q)
        assert events[-1]['status'] == 'error'
        assert events[-1]['step'] == 1
        assert '解析失败' in events[-1]['msg']

    def test_empty_cookies_error_step1(self, tmp_path):
        platform, q, patches = self._setup(
            tmp_path, parse=lambda s: ([], []))
        with patches[0], patches[1], pytest.raises(ValueError, match='未解析到任何 cookie'):
            _run_async(platform.import_cookie('k=v', q))
        assert _drain(q)[-1]['step'] == 1

    def test_success_new_account_insert(self, tmp_path):
        conn = _FakeConn(_FakeCursor(lastrowid=321))
        platform, q, patches = self._setup(tmp_path, conn=conn)
        with patches[0], patches[1]:
            result = _run_async(platform.import_cookie('k=v', q))
        assert result['account_id'] == 321
        assert result['userName'] == '测试号'
        assert result['stats'] == [{'x': 1}]
        # step4 INSERT 语句
        sql = conn.cursor_.executed[0][0]
        assert sql.startswith('INSERT INTO user_info')
        assert conn.cursor_.executed[0][1][0] == 99  # platform_id
        # cookie 文件真实写入 tmp
        files = list((tmp_path / 'cookiesFile').glob('*.json'))
        assert len(files) == 1
        storage = json.loads(files[0].read_text(encoding='utf-8'))
        assert storage['cookies'][0]['name'] == 'a'
        # 状态队列: step1..4 running + step4 done
        events = _drain(q)
        assert events[-1]['status'] == 'done'
        assert events[-1]['account_id'] == 321

    def test_reimport_update(self, tmp_path):
        conn = _FakeConn()
        platform, q, patches = self._setup(tmp_path, conn=conn)
        with patches[0], patches[1]:
            result = _run_async(platform.import_cookie('k=v', q, account_id=7))
        assert result['account_id'] == 7
        sql, params = conn.cursor_.executed[0]
        assert sql.startswith('UPDATE user_info')
        assert params[-1] == 7

    def test_sync_tuple_shape_stats_empty(self, tmp_path):
        conn = _FakeConn()

        async def _sync_tuple(cf):
            return ('旧号', 'old.png')

        platform, q, patches = self._setup(tmp_path, conn=conn, sync=_sync_tuple)
        with patches[0], patches[1]:
            result = _run_async(platform.import_cookie('k=v', q))
        assert result['userName'] == '旧号'
        assert result['stats'] == []

    def test_sync_failure_does_not_block_reimport(self, tmp_path):
        """sync 失败 + 已有 account_id → 不阻断,继续 UPDATE(re-import 语义)。"""
        conn = _FakeConn()

        async def _sync_boom(cf):
            raise RuntimeError('net down')

        platform, q, patches = self._setup(tmp_path, conn=conn, sync=_sync_boom)
        with patches[0], patches[1]:
            result = _run_async(platform.import_cookie('k=v', q, account_id=7))
        assert result['account_id'] == 7
        sql = conn.cursor_.executed[0][0]
        assert sql.startswith('UPDATE user_info')
        events = _drain(q)
        assert any(e.get('msg', '').startswith('同步失败') for e in events)

    def test_cookie_invalid_cleans_file(self, tmp_path):
        platform, q, patches = self._setup(tmp_path, sync=lambda cf: {})
        with patches[0], patches[1], pytest.raises(RuntimeError, match='cookie 同步失败'):
            _run_async(platform.import_cookie('k=v', q))
        assert list((tmp_path / 'cookiesFile').glob('*.json')) == []  # 临时文件已删
        events = _drain(q)
        assert events[-1]['status'] == 'error'
        assert events[-1]['step'] == 4
        assert 'cookie 已失效' in events[-1]['msg']

    def test_db_write_failure_error_step4(self, tmp_path):
        conn = _FakeConn(raise_on_enter=True)
        platform, q, patches = self._setup(tmp_path, conn=conn)
        with patches[0], patches[1], pytest.raises(RuntimeError, match='db down'):
            _run_async(platform.import_cookie('k=v', q))
        assert _drain(q)[-1]['msg'].startswith('写入数据库失败')

    def test_import_cookie_parse_uses_base_generic(self, tmp_path):
        """A6/R9-2: 未重写的平台走基类通用解析（不再 step1 报错）。"""
        class _NoImport(BasePlatform):
            platform_id = 98
            platform_key = 'noimport'
            platform_name = 'NoImport'

            async def login(self, id, status_queue, account_id=None):
                pass

            async def check_cookie(self, cookie_file):
                return True

            async def open_creator_center(self, cookie_file):
                pass

            async def publish_video(self, **kwargs):
                return True

            async def sync_profile(self, cookie_file):
                return {'name': 'x', 'avatar': '', 'stats': []}

        platform = _NoImport()
        q = Queue()
        with patch('impl.base_platform.BASE_DIR', tmp_path), \
             patch('impl.base_platform.sqlite3.connect', return_value=_FakeConn()):
            result = _run_async(platform.import_cookie('k=v', q))
        # 通用解析成功（domain 为空串），流程继续到 step2 写文件/校验
        assert result is not None or _drain(q)[-1]['status'] != 'error'
