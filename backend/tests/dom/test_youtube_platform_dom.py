"""YouTube platform.py DOM 交互层契约测试（T35 第六期）。

覆盖 impl/youtube/platform.py（440 stmts，基线 20%）:
- 模块级: _msg（日志消息帮助函数）
- 纯函数: _parse_cookie_to_storage_state（.youtube.com 域/expires/httpOnly/跳过无效对）
- 登录/校验/同步: login（persistent_context/URL 轮询退出/轮询异常吞掉/账号查询回退 uuid/
  UPDATE 与 INSERT 分支/500 兜底/close 异常吞掉） / check_cookie（accounts/signin 判定/异常 False/
  close 异常吞掉） / sync_profile（scrape_youtube_profile/异常空值/close 异常吞掉）
  / open_creator_center（线程启动/事件+close 异常吞掉）
- 编排: _upload_one 全流程（tags 三种解析/上传入口/上传完成/封面组件缺失继续/upload failed raise/
  标题 desc/封面存在才设置/受众单选项/高级设置展开判断/变更单选项/标签逐项失败继续/三步 Next/
  可见性/完成/回写/异常重抛/close 兜底）
- DOM 辅助: _clear_and_type（visible+清空+press_sequentially） / _click_radio（已选跳过/设置成功/重试/
  异常吞掉） / _open_upload_dialog（上传按钮+文件选择器） / _set_visibility（PUBLIC 三策略/
  evaluate/force/offRadio/定时触发） / _set_scheduled_publish（datetime+时间戳/日期输入+dropdown 兜底/
  时间/时区 GMT+8/异常吞掉）
"""
import asyncio
import json
import sys
import time as _time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from conf import BASE_DIR
from impl.youtube.platform import (
    YOUTUBE_STUDIO_URL,
    YoutubePlatform,
    _msg,
)


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return YoutubePlatform()


def _mk_leaf():
    loc = MagicMock()
    loc.count = AsyncMock(return_value=0)
    loc.click = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.set_input_files = AsyncMock()
    loc.get_attribute = AsyncMock(return_value=None)
    loc.inner_text = AsyncMock(return_value='')
    loc.text_content = AsyncMock(return_value='')
    loc.is_visible = AsyncMock(return_value=True)
    loc.is_enabled = AsyncMock(return_value=True)
    loc.fill = AsyncMock()
    loc.press = AsyncMock()
    loc.press_sequentially = AsyncMock()
    loc.evaluate = AsyncMock(return_value='')
    loc.scroll_into_view_if_needed = AsyncMock()
    subs = {}
    nth_subs = {}
    loc.locator = MagicMock(side_effect=lambda sel, **kw: subs.setdefault(sel, _mk_locator()))
    loc.subs = subs
    loc.nth = MagicMock(side_effect=lambda i: nth_subs.setdefault(i, _mk_leaf()))
    loc.nth_subs = nth_subs
    loc.filter = MagicMock(side_effect=lambda **kw: _mk_leaf())
    return loc


def _mk_locator():
    loc = _mk_leaf()
    loc.first = _mk_leaf()
    loc.last = _mk_leaf()
    return loc


def _mk_page(url=YOUTUBE_STUDIO_URL):
    page = MagicMock()
    page.url = url
    page.main_frame = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_event = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=[])
    page.frame_locator = MagicMock()
    page.is_closed = MagicMock(return_value=False)
    page.frames = []
    page.evaluate = AsyncMock(return_value=[])
    page.title = AsyncMock(return_value='')
    page.close = AsyncMock()
    page.on = MagicMock()
    page.expect_file_chooser = MagicMock()
    page.get_by_text = MagicMock(return_value=_mk_locator())
    page.locator = MagicMock(side_effect=lambda sel, **kw: page.locators.setdefault(sel, _mk_locator()))
    page.locators = {}
    return page


def _loc(page, sel):
    page.locator(sel)
    return page.locators[sel]


@contextmanager
def _mk_browser_chain(platform):
    page = _mk_page()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.storage_state = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    with patch.object(platform, 'create_browser', AsyncMock(return_value=browser)) as cb, \
         patch.object(platform, 'create_context', AsyncMock(return_value=context)) as cc:
        yield page, context, browser, cb, cc


def _mk_cookie_file(name='t35_yt_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


@contextmanager
def _mk_upload_one_steps(p):
    """把 _upload_one 的内部子步骤全部替换为可断言的 AsyncMock。"""
    mocks = dict(
        open_dialog=AsyncMock(),
        clear_type=AsyncMock(),
        click_radio=AsyncMock(),
        set_visibility=AsyncMock(),
        close_browser=AsyncMock(),
    )
    with patch.object(p, '_open_upload_dialog', mocks['open_dialog']), \
         patch.object(p, '_clear_and_type', mocks['clear_type']), \
         patch.object(p, '_click_radio', mocks['click_radio']), \
         patch.object(p, '_set_visibility', mocks['set_visibility']), \
         patch.object(p, 'close_browser', mocks['close_browser']), \
         patch('asyncio.sleep', AsyncMock()):
        yield mocks


class _FakeConnCM:
    """sqlite3.connect 返回值的上下文管理器:__enter__ 返回配置好的 conn。"""

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        return False


class _PollingPage:
    """login 轮询用:url 属性按序列返回,模拟用户完成登录后的 URL 变化。"""

    def __init__(self, urls):
        self._urls = list(urls)
        self._i = 0
        self.goto = AsyncMock()
        self.title = AsyncMock(return_value='YouTube')

    @property
    def url(self):
        url = self._urls[min(self._i, len(self._urls) - 1)]
        self._i += 1
        return url


class _RaisingUrlPage:
    """login 轮询用:url 访问抛异常 → 走 poll exception 分支。"""

    def __init__(self):
        self.goto = AsyncMock()
        self.title = AsyncMock(return_value='YouTube')

    @property
    def url(self):
        raise RuntimeError('nav fail')


# ── 模块级 / 纯函数 ────────────────────────────────────────────────────────

class TestMsg:
    def test_passthrough(self):
        assert _msg('中文标签') == '中文标签'


class TestParseCookieToStorageState:
    def test_happy_parse(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('a=1; b=2')
        assert origins == []
        assert [c['name'] for c in cookies] == ['a', 'b']
        for c in cookies:
            assert c['domain'] == '.youtube.com'
            assert c['path'] == '/'
            assert c['httpOnly'] is True
            assert c['secure'] is False
            assert c['sameSite'] == 'Lax'
            assert c['expires'] > _time.time()

    def test_skips_invalid_pairs(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('a=1; ; novalue')
        assert [c['name'] for c in cookies] == ['a']

    def test_empty(self):
        p = _mk_platform()
        assert p._parse_cookie_to_storage_state('') == ([], [])

    def test_strips_whitespace_and_expires_window(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('  a = 1 ')
        assert cookies[0]['name'] == 'a'
        assert cookies[0]['value'] == '1'
        delta = cookies[0]['expires'] - _time.time()
        assert 6 * 24 * 3600 < delta < 8 * 24 * 3600


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

def _mk_login_context(page):
    context = MagicMock()
    context.pages = []
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.storage_state = AsyncMock()
    return context


class TestLogin:
    def test_happy_path_with_account(self):
        p = _mk_platform()
        page = _mk_page()
        context = _mk_login_context(page)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = ('yt_cookie.json',)
        conn.commit = MagicMock()
        queue = MagicMock()
        with patch.object(p, 'create_persistent_context',
                          AsyncMock(return_value=context)) as cpc, \
             patch('impl.youtube.platform.scrape_youtube_profile',
                   AsyncMock(return_value=('UP主', 'http://a.png'))) as sp, \
             patch('impl.youtube.platform.sqlite3.connect',
                   return_value=_FakeConnCM(conn)), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.youtube.platform.logger'):
            _run(p.login('u1', queue, account_id='acc1'))
        cpc.assert_awaited_once_with(user_data_dir=str(Path(BASE_DIR) / 'cookiesFile' / 'yt_profiles' / 'u1'),
                                     headless=False)
        assert page.goto.await_args_list[0].args == ('https://accounts.google.com/',)
        assert page.goto.await_args_list[0].kwargs['timeout'] == 30000
        assert page.goto.await_args_list[1].args == (YOUTUBE_STUDIO_URL,)
        sp.assert_awaited_once_with(page)
        context.storage_state.assert_awaited_once_with(
            path=Path(BASE_DIR) / 'cookiesFile' / 'yt_cookie.json',
        )
        # UPDATE 分支:conn.execute 收到 UPDATE user_info SQL
        update_calls = [c for c in conn.execute.call_args_list
                        if str(c.args[0]).strip().startswith('UPDATE user_info')]
        assert len(update_calls) == 1
        conn.commit.assert_called()
        # SSE 200
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['status'] == '200'
        assert payload['name'] == 'UP主'
        context.close.assert_awaited_once()

    def test_no_account_inserts_uuid_cookie(self):
        p = _mk_platform()
        page = _mk_page()
        context = _mk_login_context(page)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        conn.commit = MagicMock()
        queue = MagicMock()
        with patch.object(p, 'create_persistent_context', AsyncMock(return_value=context)), \
             patch('impl.youtube.platform.scrape_youtube_profile',
                   AsyncMock(return_value=('UP主', ''))), \
             patch('impl.youtube.platform.uuid.uuid1', return_value='abc-def'), \
             patch('impl.youtube.platform.sqlite3.connect',
                   return_value=_FakeConnCM(conn)), \
             patch('impl.youtube.platform.logger'):
            _run(p.login('u2', queue))
        context.storage_state.assert_awaited_once_with(
            path=Path(BASE_DIR) / 'cookiesFile' / 'abc-def.json',
        )
        insert_sql = cursor.execute.call_args.args[0]
        assert insert_sql.strip().startswith('INSERT INTO user_info')
        assert cursor.execute.call_args.args[1][0] == 8
        assert cursor.execute.call_args.args[1][1] == 'abc-def.json'
        conn.commit.assert_called()
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['status'] == '200'

    def test_account_not_found_falls_back_to_uuid(self):
        p = _mk_platform()
        page = _mk_page()
        context = _mk_login_context(page)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None  # 账号不存在
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        conn.commit = MagicMock()
        queue = MagicMock()
        with patch.object(p, 'create_persistent_context', AsyncMock(return_value=context)), \
             patch('impl.youtube.platform.scrape_youtube_profile', AsyncMock(return_value=('n', ''))), \
             patch('impl.youtube.platform.uuid.uuid1', return_value='u-1'), \
             patch('impl.youtube.platform.sqlite3.connect', return_value=_FakeConnCM(conn)), \
             patch('impl.youtube.platform.logger'):
            _run(p.login('u3', queue, account_id='missing'))
        # 账号查不到 → account_id 置 None → INSERT 分支
        insert_calls = [c for c in cursor.execute.call_args_list
                        if str(c.args[0]).strip().startswith('INSERT INTO user_info')]
        assert len(insert_calls) == 1
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['status'] == '200'

    def test_empty_profile_falls_back_to_username(self):
        p = _mk_platform()
        page = _mk_page()
        context = _mk_login_context(page)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        conn.cursor.return_value = MagicMock()
        conn.commit = MagicMock()
        fake_loop = MagicMock()
        fake_loop.time.return_value = 1234.56
        queue = MagicMock()
        with patch.object(p, 'create_persistent_context', AsyncMock(return_value=context)), \
             patch('impl.youtube.platform.scrape_youtube_profile', AsyncMock(return_value=('', ''))), \
             patch('impl.youtube.platform.asyncio.get_event_loop', return_value=fake_loop), \
             patch('impl.youtube.platform.uuid.uuid1', return_value='x'), \
             patch('impl.youtube.platform.sqlite3.connect', return_value=_FakeConnCM(conn)), \
             patch('impl.youtube.platform.logger'):
            _run(p.login('u4', queue))
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['name'] == 'YouTube1234'

    def test_poll_loop_continues_until_url_changes(self):
        """URL 仍在 accounts.google.com/signin → sleep 继续轮询;离开后 break。"""
        p = _mk_platform()
        page = _PollingPage([
            'https://accounts.google.com/signin/v2',
            'https://studio.youtube.com/channel',
        ])
        context = _mk_login_context(page)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        conn.cursor.return_value = MagicMock()
        conn.commit = MagicMock()
        queue = MagicMock()
        with patch.object(p, 'create_persistent_context', AsyncMock(return_value=context)), \
             patch('impl.youtube.platform.scrape_youtube_profile', AsyncMock(return_value=('n', ''))), \
             patch('impl.youtube.platform.uuid.uuid1', return_value='x'), \
             patch('impl.youtube.platform.sqlite3.connect', return_value=_FakeConnCM(conn)), \
             patch('asyncio.sleep', AsyncMock()) as sleep, \
             patch('impl.youtube.platform.logger'):
            _run(p.login('u5', queue))
        sleep.assert_awaited()  # 轮询中至少 sleep 一次
        assert page.goto.await_count == 2  # accounts + studio
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['status'] == '200'

    def test_poll_exception_swallowed(self):
        """轮询中 page.url 抛异常 → except 吞掉,继续 studio 验证。"""
        p = _mk_platform()
        page = _RaisingUrlPage()
        context = _mk_login_context(page)
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        conn.cursor.return_value = MagicMock()
        conn.commit = MagicMock()
        queue = MagicMock()
        with patch.object(p, 'create_persistent_context', AsyncMock(return_value=context)), \
             patch('impl.youtube.platform.scrape_youtube_profile', AsyncMock(return_value=('n', ''))), \
             patch('impl.youtube.platform.uuid.uuid1', return_value='x'), \
             patch('impl.youtube.platform.sqlite3.connect', return_value=_FakeConnCM(conn)), \
             patch('impl.youtube.platform.logger'):
            _run(p.login('u6', queue))
        assert page.goto.await_count == 2  # 轮询异常后仍导航 studio
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['status'] == '200'

    def test_studio_navigation_failure_still_saves(self):
        """goto studio 失败 → 吞掉,仍抓取 profile + 保存 cookie。"""
        p = _mk_platform()
        page = _mk_page()
        context = _mk_login_context(page)
        page.goto = AsyncMock(side_effect=[None, RuntimeError('net down')])
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        conn.cursor.return_value = MagicMock()
        conn.commit = MagicMock()
        queue = MagicMock()
        with patch.object(p, 'create_persistent_context', AsyncMock(return_value=context)), \
             patch('impl.youtube.platform.scrape_youtube_profile', AsyncMock(return_value=('n', ''))), \
             patch('impl.youtube.platform.uuid.uuid1', return_value='x'), \
             patch('impl.youtube.platform.sqlite3.connect', return_value=_FakeConnCM(conn)), \
             patch('impl.youtube.platform.logger'):
            _run(p.login('u7', queue))
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['status'] == '200'

    def test_login_failure_puts_500(self):
        p = _mk_platform()
        queue = MagicMock()
        with patch.object(p, 'create_persistent_context',
                          AsyncMock(side_effect=RuntimeError('profile dir locked'))), \
             patch('impl.youtube.platform.logger'):
            _run(p.login('u8', queue))
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['status'] == '500'
        assert 'YouTube login failed' in payload['msg']

    def test_context_close_error_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        context = _mk_login_context(page)
        context.close = AsyncMock(side_effect=RuntimeError('closed'))
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        conn.cursor.return_value = MagicMock()
        conn.commit = MagicMock()
        queue = MagicMock()
        with patch.object(p, 'create_persistent_context', AsyncMock(return_value=context)), \
             patch('impl.youtube.platform.scrape_youtube_profile', AsyncMock(return_value=('n', ''))), \
             patch('impl.youtube.platform.uuid.uuid1', return_value='x'), \
             patch('impl.youtube.platform.sqlite3.connect', return_value=_FakeConnCM(conn)), \
             patch('impl.youtube.platform.logger'):
            _run(p.login('u9', queue))  # 不抛异常
        assert queue.put.called


class TestCheckCookie:
    def test_valid(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.youtube.platform.logger'):
            assert _run(p.check_cookie('ck.json')) is True
        page.goto.assert_awaited_once_with(YOUTUBE_STUDIO_URL, timeout=20000)
        browser.close.assert_awaited_once()

    def test_redirected_to_accounts(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.youtube.platform.logger'):
            page.url = 'https://accounts.google.com/signin/v2'
            assert _run(p.check_cookie('ck.json')) is False

    def test_signin_in_url(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.youtube.platform.logger'):
            page.url = 'https://studio.youtube.com/signin?continue=1'
            assert _run(p.check_cookie('ck.json')) is False

    def test_outer_exception_returns_false(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.youtube.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            assert _run(p.check_cookie('ck.json')) is False

    def test_browser_close_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, browser, _cb, _cc), \
             patch('impl.youtube.platform.logger'):
            browser.close = AsyncMock(side_effect=RuntimeError('boom'))
            assert _run(p.check_cookie('ck.json')) is True  # 不抛异常


class TestSyncProfile:
    def test_happy(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.youtube.platform.scrape_youtube_profile',
                   AsyncMock(return_value=('UP主', 'http://a.png'))) as sp:
            assert _run(p.sync_profile('ck.json')) == ('UP主', 'http://a.png')
        sp.assert_awaited_once_with(page)
        page.goto.assert_awaited_once_with(YOUTUBE_STUDIO_URL, timeout=30000)
        browser.close.assert_awaited_once()

    def test_outer_exception_returns_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.youtube.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            assert _run(p.sync_profile('ck.json')) == ('', '')

    def test_browser_close_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, browser, _cb, _cc), \
             patch('impl.youtube.platform.scrape_youtube_profile',
                   AsyncMock(return_value=('n', ''))):
            browser.close = AsyncMock(side_effect=RuntimeError('boom'))
            assert _run(p.sync_profile('ck.json')) == ('n', '')  # 不抛异常


class TestOpenCreatorCenter:
    def test_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_yt_occ.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.youtube.platform.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl.youtube.platform.create_context_sync', return_value=context) as ccs:
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            cbs.assert_called_once_with(headless=False)
            ccs.assert_called_once()
            page.goto.assert_called_once()
            page.wait_for_event.assert_called_once_with('close', timeout=0)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_wait_event_error_swallowed(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_yt_occ2.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.youtube.platform.create_browser_sync', return_value=browser), \
                 patch('impl.youtube.platform.create_context_sync', return_value=context):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_browser_close_error_swallowed(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_yt_occ3.json')
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('boom'))
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.youtube.platform.create_browser_sync', return_value=browser), \
                 patch('impl.youtube.platform.create_context_sync', return_value=context):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)


# ── 编排: _upload_one 全流程 ───────────────────────────────────────────────

class TestUploadOne:
    def _run(self, p, page, **kw):
        default = dict(
            title='标题', file_path='/m/v.mp4', tags=[],
            publish_date=0, account_file='/c/u1.json', desc='',
            thumbnail_path='', audience='not_kids', altered_content=False,
        )
        default.update(kw)
        return _run(p._upload_one(**default))

    def test_happy_full_flow(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.youtube.platform.logger'):
            ok = self._run(p, page, title='标题', desc='', tags=[])
        assert ok is None
        page.goto.assert_awaited_once_with(
            YOUTUBE_STUDIO_URL, wait_until='domcontentloaded', timeout=30000,
        )
        mocks['open_dialog'].assert_awaited_once_with(page)
        _loc(page, 'input[name="Filedata"]').first.set_input_files.assert_awaited_once_with('/m/v.mp4')
        _loc(page, '#title-textarea #textbox').first.wait_for.assert_awaited_once_with(
            state='visible', timeout=0,
        )
        mocks['clear_type'].assert_awaited_once_with(page, '#title-textarea #textbox', '标题')
        assert mocks['click_radio'].await_count == 2  # audience + altered content
        assert mocks['click_radio'].await_args.args == (
            page, 'VIDEO_HAS_ALTERED_CONTENT_NO', 'altered content',
        )
        next_btn = _loc(page, '#next-button').first
        assert next_btn.click.await_count == 3
        mocks['set_visibility'].assert_awaited_once_with(page, 0)
        _loc(page, '#done-button').first.click.assert_awaited_once()
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_desc_filled_when_provided(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.youtube.platform.logger'):
            self._run(p, page, title='T', desc='简介内容')
        assert mocks['clear_type'].await_count == 2
        assert mocks['clear_type'].await_args.args == (
            page, '#description-textarea #textbox', '简介内容',
        )

    def test_tags_string_parsed_and_entered(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as _mocks, \
             patch('impl.youtube.platform.logger'):
            self._run(p, page, title='T', tags='a,b，#c')
        tag_input = _loc(page, '#tags-container input#text-input').first
        tag_input.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        assert tag_input.press_sequentially.await_count == 3
        entered = [c.args[0] for c in tag_input.press_sequentially.await_args_list]
        assert entered == ['a', 'b', 'c']
        assert tag_input.press.await_count == 3  # 每标签 Enter

    def test_tags_list_passthrough_and_capped_15(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as _mocks, \
             patch('impl.youtube.platform.logger'):
            self._run(p, page, title='T', tags=[f'tag{i}' for i in range(20)])
        tag_input = _loc(page, '#tags-container input#text-input').first
        assert tag_input.press_sequentially.await_count == 15  # [:15] 截断

    def test_tags_non_list_non_str_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as _mocks, \
             patch('impl.youtube.platform.logger'):
            self._run(p, page, title='T', tags=123)
        _loc(page, '#tags-container input#text-input').first.wait_for.assert_not_awaited()

    def test_per_tag_failure_continues(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as _mocks, \
             patch('impl.youtube.platform.logger'):
            tag_input = _loc(page, '#tags-container input#text-input').first
            tag_input.press_sequentially = AsyncMock(
                side_effect=[None, RuntimeError('stale'), None]
            )
            self._run(p, page, title='T', tags=['a', 'b', 'c'])
        assert tag_input.press_sequentially.await_count == 3  # 中间失败不中断

    def test_tag_input_missing_continues(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.youtube.platform.logger'):
            _loc(page, '#tags-container input#text-input').first.wait_for = AsyncMock(
                side_effect=TimeoutError('no input')
            )
            self._run(p, page, title='T', tags=['a'])
        mocks['set_visibility'].assert_awaited_once()  # 标签失败不中断后续

    def test_thumbnail_set_when_exists(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as _mocks, \
             patch('impl.youtube.platform.os.path.exists', return_value=True), \
             patch('impl.youtube.platform.logger'):
            self._run(p, page, title='T', thumbnail_path='/thumb.png')
        thumb_in = _loc(page, 'ytcp-thumbnail-uploader input#file-loader').first
        thumb_in.set_input_files.assert_awaited_once_with('/thumb.png')

    def test_thumbnail_skipped_when_missing(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as _mocks, \
             patch('impl.youtube.platform.os.path.exists', return_value=False), \
             patch('impl.youtube.platform.logger'):
            self._run(p, page, title='T', thumbnail_path='/thumb.png')
        _loc(page, 'ytcp-thumbnail-uploader input#file-loader').first.set_input_files.assert_not_awaited()

    def test_thumbnail_component_missing_continues(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.youtube.platform.logger'):
            _loc(page, 'ytcp-thumbnail-uploader input#file-loader').first.wait_for = AsyncMock(
                side_effect=TimeoutError('no thumbnail component')
            )
            self._run(p, page, title='T')  # 未找到组件 → 继续
        mocks['clear_type'].assert_awaited_once()

    def test_upload_failed_text_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.youtube.platform.logger'):
            _loc(page, 'text=upload failed').count = AsyncMock(return_value=1)
            with pytest.raises(RuntimeError, match='video upload failed'):
                self._run(p, page, title='T')
        mocks['close_browser'].assert_awaited_once()

    def test_audience_kids_radio(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.youtube.platform.logger'):
            self._run(p, page, title='T', audience='kids', altered_content=True)
        first_call = mocks['click_radio'].await_args_list[0]
        assert first_call.args == (page, 'VIDEO_MADE_FOR_KIDS_MFK', 'audience')
        second_call = mocks['click_radio'].await_args_list[1]
        assert second_call.args == (page, 'VIDEO_HAS_ALTERED_CONTENT_YES', 'altered content')

    def test_toggle_already_collapsed_skips_click(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as _mocks, \
             patch('impl.youtube.platform.logger'):
            _loc(page, '#toggle-button').first.get_attribute = AsyncMock(
                return_value='隐藏高级设置'
            )
            self._run(p, page, title='T')
        _loc(page, '#toggle-button').first.click.assert_not_awaited()

    def test_toggle_expands_when_visible(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as _mocks, \
             patch('impl.youtube.platform.logger'):
            _loc(page, '#toggle-button').first.get_attribute = AsyncMock(
                return_value='展开'
            )
            self._run(p, page, title='T')
        _loc(page, '#toggle-button').first.click.assert_awaited_once_with(force=True)

    def test_cookie_save_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.youtube.platform.logger'):
            context.storage_state = AsyncMock(side_effect=RuntimeError('no fs'))
            self._run(p, page, title='T')  # 不抛异常
        mocks['close_browser'].assert_awaited_once()

    def test_upload_exception_re_raised(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.youtube.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            with pytest.raises(RuntimeError, match='net down'):
                self._run(p, page, title='T')
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_close_browser_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks:
            mocks['close_browser'].side_effect = RuntimeError('boom')
            with pytest.raises(RuntimeError, match='video upload failed'):
                # 先触发上传失败,再验证 finally 中 close 异常被吞 → 原始异常冒泡
                _loc(page, 'text=upload failed').count = AsyncMock(return_value=1)
                self._run(p, page, title='T')


# ── DOM 辅助 ───────────────────────────────────────────────────────────────

class TestClearAndType:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        el = _loc(page, '#title-textarea #textbox').first
        with patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._clear_and_type(page, '#title-textarea #textbox', '新标题'))
        el.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        el.click.assert_awaited_once()
        assert page.keyboard.press.await_args_list == [
            (( 'Control+a',), {}), (( 'Backspace',), {}),
        ]
        el.press_sequentially.assert_awaited_once_with('新标题', delay=30)


class TestClickRadio:
    def test_already_checked(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, 'tp-yt-paper-radio-button[name="X"]').first
        radio.get_attribute = AsyncMock(return_value='true')
        with patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._click_radio(page, 'X', 'label'))
        radio.click.assert_not_awaited()

    def test_set_on_first_click(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, 'tp-yt-paper-radio-button[name="X"]').first
        radio.get_attribute = AsyncMock(side_effect=[None, 'true'])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._click_radio(page, 'X', 'label'))
        radio.click.assert_awaited_once_with(force=True)

    def test_retry_when_not_checked(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, 'tp-yt-paper-radio-button[name="X"]').first
        radio.get_attribute = AsyncMock(side_effect=[None, None, 'true'])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._click_radio(page, 'X', 'label'))
        assert radio.click.await_count == 2  # 首点 + 重试

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, 'tp-yt-paper-radio-button[name="X"]').first.wait_for = AsyncMock(
            side_effect=TimeoutError('no radio')
        )
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.youtube.platform.logger', logger):
            _run(p._click_radio(page, 'X', 'label'))  # 不抛异常
        assert logger.info.called


class TestOpenUploadDialog:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        upload_btn = _loc(page, '#upload-icon, [aria-label="Upload videos"], ytcp-icon-button[aria-label="Upload videos"]').first
        file_picker = _loc(page, '#select-files-button, ytcp-uploads-file-picker').first
        with patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._open_upload_dialog(page))
        upload_btn.wait_for.assert_awaited_once_with(state='visible', timeout=20000)
        upload_btn.click.assert_awaited_once_with(force=True)
        file_picker.wait_for.assert_awaited_once_with(state='visible', timeout=15000)


class TestSetVisibility:
    def test_already_public_no_clicks(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '#privacy-radios').first.wait_for = AsyncMock()
        _loc(page, 'tp-yt-paper-radio-button[name="PUBLIC"]').first.get_attribute = AsyncMock(
            return_value='true'
        )
        with patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_visibility(page, 0))
        _loc(page, 'tp-yt-paper-radio-button[name="PUBLIC"]').first.evaluate.assert_not_awaited()
        _loc(page, 'tp-yt-paper-radio-button[name="PUBLIC"]').first.click.assert_not_awaited()

    def test_evaluate_strategy(self):
        p = _mk_platform()
        page = _mk_page()
        public = _loc(page, 'tp-yt-paper-radio-button[name="PUBLIC"]').first
        public.get_attribute = AsyncMock(side_effect=[None, 'true', 'true', 'true'])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_visibility(page, 0))
        public.evaluate.assert_awaited_once_with('el => el.click()')
        public.click.assert_not_awaited()

    def test_force_click_strategy(self):
        p = _mk_platform()
        page = _mk_page()
        public = _loc(page, 'tp-yt-paper-radio-button[name="PUBLIC"]').first
        public.get_attribute = AsyncMock(side_effect=[None, None, 'true', 'true'])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_visibility(page, 0))
        public.evaluate.assert_awaited_once_with('el => el.click()')
        public.click.assert_awaited_once_with(force=True)

    def test_off_radio_strategy(self):
        p = _mk_platform()
        page = _mk_page()
        public = _loc(page, 'tp-yt-paper-radio-button[name="PUBLIC"]').first
        public.get_attribute = AsyncMock(return_value=None)
        off_radio = public.locator('#offRadio').first
        off_radio.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_visibility(page, 0))
        assert public.evaluate.await_count == 1
        assert public.click.await_count == 1
        off_radio.click.assert_awaited_once_with(force=True)

    def test_off_radio_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        public = _loc(page, 'tp-yt-paper-radio-button[name="PUBLIC"]').first
        public.get_attribute = AsyncMock(return_value=None)
        public.locator('#offRadio').first.click = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_visibility(page, 0))  # 不抛异常

    def test_scheduled_publish_called(self):
        p = _mk_platform()
        page = _mk_page()
        pd = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        _loc(page, 'tp-yt-paper-radio-button[name="PUBLIC"]').first.get_attribute = AsyncMock(
            return_value='true'
        )
        with patch.object(p, '_set_scheduled_publish', AsyncMock()) as sched, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_visibility(page, pd))
        sched.assert_awaited_once_with(page, pd)

    def test_schedule_skipped_when_zero_or_none(self):
        p = _mk_platform()
        for pd in (0, None):
            page = _mk_page()
            _loc(page, 'tp-yt-paper-radio-button[name="PUBLIC"]').first.get_attribute = AsyncMock(
                return_value='true'
            )
            with patch.object(p, '_set_scheduled_publish', AsyncMock()) as sched, \
                 patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
                _run(p._set_visibility(page, pd))
            sched.assert_not_awaited()


class TestSetScheduledPublish:
    DATE_SEL = ('#datepicker-trigger tp-yt-iron-input input, '
                'tp-yt-paper-dialog.ytcp-datepicker tp-yt-iron-input input')
    TIME_SEL = '#time-of-day-container tp-yt-iron-input input, #time-of-day-container input'
    TZ_BTN = 'button[aria-label="时区"], #timezone-select-button'
    TZ_OPT = ('tp-yt-paper-item:has-text("（GMT+08:00）香港"), '
              'tp-yt-paper-item:has-text("(GMT+08:00) Hong Kong"), '
              'tp-yt-paper-item:has-text("GMT+08:00")')
    PD = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))

    def _mk_populated(self, page):
        _loc(page, '#second-container').first.count = AsyncMock(return_value=1)
        date_trigger = _loc(page, '#datepicker-trigger').first
        date_trigger.locator('.dropdown-trigger-text')  # 预注册兜底子选择器
        _loc(page, self.DATE_SEL).first.wait_for = AsyncMock()
        _loc(page, self.TIME_SEL).first.wait_for = AsyncMock()
        tz_btn = _loc(page, self.TZ_BTN).first
        tz_btn.locator  # noqa: B018 -- 仅确保可调用
        _loc(page, self.TZ_OPT).first.wait_for = AsyncMock()

    def test_happy_datetime(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_populated(page)
        with patch('impl.youtube.platform.clear_input', AsyncMock()) as ci, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_scheduled_publish(page, self.PD))
        date_input = _loc(page, self.DATE_SEL).first
        date_input.click.assert_awaited_once()
        ci.assert_any_await(page, date_input)
        date_input.press_sequentially.assert_awaited_once_with('2026年8月22日', delay=30)
        time_input = _loc(page, self.TIME_SEL).first
        time_input.click.assert_awaited_once()
        time_input.press_sequentially.assert_awaited_once_with('10:05', delay=30)
        page.keyboard.press.assert_awaited_with('Enter')
        tz_btn = _loc(page, self.TZ_BTN).first
        tz_btn.click.assert_awaited_once_with(force=True)
        _loc(page, self.TZ_OPT).first.click.assert_awaited_once()
        _loc(page, '#second-container').first.click.assert_awaited_once_with(force=True)

    def test_int_timestamp(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_populated(page)
        ts = int(datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai')).timestamp())
        with patch('impl.youtube.platform.clear_input', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_scheduled_publish(page, ts))
        date_input = _loc(page, self.DATE_SEL).first
        assert date_input.press_sequentially.await_args.args[0] == '2026年8月22日'

    def test_expand_button_clicked_when_visible(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_populated(page)
        expand_btn = _loc(page, '#second-container-expand-button').first
        expand_btn.is_visible = AsyncMock(return_value=True)
        with patch('impl.youtube.platform.clear_input', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_scheduled_publish(page, self.PD))
        expand_btn.click.assert_awaited_once_with(force=True)

    def test_expand_button_hidden_or_exception(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_populated(page)
        _loc(page, '#second-container-expand-button').first.is_visible = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        with patch('impl.youtube.platform.clear_input', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_scheduled_publish(page, self.PD))  # 异常吞掉,继续

    def test_date_input_fallback_dropdown(self):
        """日期输入框不可见 → Escape 兜底 dropdown 直接输入。"""
        p = _mk_platform()
        page = _mk_page()
        self._mk_populated(page)
        _loc(page, self.DATE_SEL).first.wait_for = AsyncMock(
            side_effect=TimeoutError('no date input')
        )
        with patch('impl.youtube.platform.clear_input', AsyncMock()) as ci, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_scheduled_publish(page, self.PD))
        dropdown = _loc(page, '#datepicker-trigger').first.subs['.dropdown-trigger-text'].first
        dropdown.click.assert_awaited_once_with(force=True)
        dropdown.press_sequentially.assert_awaited_once_with('2026年8月22日', delay=30)
        # 兜底路径:date_input 未走 clear_input,dropdown 走了(首次调用)
        assert ci.await_args_list[0].args[1] is dropdown

    def test_timezone_failure_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_populated(page)
        _loc(page, self.TZ_BTN).first.wait_for = AsyncMock(side_effect=TimeoutError('no tz'))
        with patch('impl.youtube.platform.clear_input', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_scheduled_publish(page, self.PD))  # 不抛异常

    def test_timezone_escape_error_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_populated(page)
        _loc(page, self.TZ_BTN).first.wait_for = AsyncMock(side_effect=TimeoutError('no tz'))

        def _press(arg):
            if arg == 'Escape':
                raise RuntimeError('kbd gone')

        page.keyboard.press = AsyncMock(side_effect=_press)
        with patch('impl.youtube.platform.clear_input', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), patch('impl.youtube.platform.logger'):
            _run(p._set_scheduled_publish(page, self.PD))  # 不抛异常

    def test_outer_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '#second-container').first.wait_for = AsyncMock(
            side_effect=TimeoutError('no container')
        )
        logger = MagicMock()
        with patch('impl.youtube.platform.clear_input', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.youtube.platform.logger', logger):
            _run(p._set_scheduled_publish(page, self.PD))  # 不抛异常
        assert any('定时发布失败' in str(c) for c in logger.info.call_args_list)
