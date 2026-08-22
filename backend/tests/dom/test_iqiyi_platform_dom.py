"""爱奇艺 platform.py DOM 交互层契约测试（T35 第四期）。

覆盖 impl/iqiyi/platform.py（524 stmts，基线 21%）:
- 模块级: _scrape_iqiyi_profile（昵称+头像抓取/超时/缺失/探测异常兜底）
- 纯函数: _parse_cookie_to_storage_state（.iqiyi.com 域/expires/httpOnly/跳过无效对）
- 登录/校验/同步: login（framenavigated 事件驱动/300s 超时 put 500/非主 frame 忽略）
  / check_cookie（user-info 判定/外层异常 False） / sync_profile（evaluate 抓取+stats/异常兜底）
  / _scrape_iqiyi_stats（label_map 排序/千分位/非法数字/超时仍抓取） / _login_stats_fn
  / open_creator_center（线程启动/事件+close 异常吞掉）
- 编排: _upload_one_video 全流程（request 监听 upload/record/表单等待/标题/简介/现金活动/
  声明/风险/封面/定时/发布成功失败/回写/关闭）
- DOM 辅助: _wait_video_upload_complete（事件/4h 超时继续） / _fill_title（双选择器/30 截断）
  / _fill_description（450 截断） / _set_creation_declaration（map+文本兜底/未知/异常吞掉）
  / _set_risk_warning（白名单校验/下拉） / _click_cash_activity
  / _upload_cover（竖/4:3/16:9 三 tab+file_chooser+完成） / _set_schedule_time（fill 日期/Enter）
  / _click_publish（上传卡轮询/URL 成功路径/文本关键词/超时/异常 raise）
"""
import asyncio
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
from impl.iqiyi.platform import (
    _LOGIN_URL,
    CREATION_DECLARATION_MAP,
    IqiyiPlatform,
    _scrape_iqiyi_profile,
)


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return IqiyiPlatform()


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
    loc.fill = AsyncMock()
    loc.press = AsyncMock()
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


def _mk_page(url='https://creator.iqiyi.com/publish/video/wemedia'):
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


def _mk_cookie_file(name='t35_iqiyi_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


@contextmanager
def _mk_upload_one_steps(p):
    """把 _upload_one_video 的内部子步骤全部替换为可断言的 AsyncMock。"""
    mocks = dict(
        wait_upload=AsyncMock(),
        fill_title=AsyncMock(),
        fill_desc=AsyncMock(),
        cash=AsyncMock(),
        declaration=AsyncMock(),
        risk=AsyncMock(),
        cover=AsyncMock(),
        schedule=AsyncMock(),
        publish=AsyncMock(return_value=True),
        close_browser=AsyncMock(),
    )
    with patch.object(p, '_wait_video_upload_complete', mocks['wait_upload']), \
         patch.object(p, '_fill_title', mocks['fill_title']), \
         patch.object(p, '_fill_description', mocks['fill_desc']), \
         patch.object(p, '_click_cash_activity', mocks['cash']), \
         patch.object(p, '_set_creation_declaration', mocks['declaration']), \
         patch.object(p, '_set_risk_warning', mocks['risk']), \
         patch.object(p, '_upload_cover', mocks['cover']), \
         patch.object(p, '_set_schedule_time', mocks['schedule']), \
         patch.object(p, '_click_publish', mocks['publish']), \
         patch.object(p, 'close_browser', mocks['close_browser']), \
         patch('asyncio.sleep', AsyncMock()):
        yield mocks


# ── 模块级: profile 抓取 ───────────────────────────────────────────────────

class TestScrapeIqiyiProfile:
    def test_happy_path(self):
        page = _mk_page()
        name_el = _loc(page, 'span[class*="emoji-wrap"]').first
        name_el.count = AsyncMock(return_value=1)
        name_el.text_content = AsyncMock(return_value='  恶v魔  ')
        ava_el = _loc(page, '[class*="user-info"] img').first
        ava_el.count = AsyncMock(return_value=1)
        ava_el.get_attribute = AsyncMock(return_value='http://avatar.png')
        with patch('impl.iqiyi.platform.logger'):
            name, avatar = _run(_scrape_iqiyi_profile(page))
        assert name == '恶v魔'
        assert avatar == 'http://avatar.png'
        page.wait_for_selector.assert_awaited_once_with('[class*="user-info"]', timeout=10000)

    def test_wait_selector_timeout_still_scrapes(self):
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        name_el = _loc(page, 'span[class*="emoji-wrap"]').first
        name_el.count = AsyncMock(return_value=1)
        name_el.text_content = AsyncMock(return_value='n')
        with patch('impl.iqiyi.platform.logger'):
            name, avatar = _run(_scrape_iqiyi_profile(page))
        assert name == 'n'
        assert avatar == ''

    def test_name_missing(self):
        page = _mk_page()
        ava_el = _loc(page, '[class*="user-info"] img').first
        ava_el.count = AsyncMock(return_value=1)
        ava_el.get_attribute = AsyncMock(return_value='http://a.png')
        with patch('impl.iqiyi.platform.logger'):
            name, avatar = _run(_scrape_iqiyi_profile(page))
        assert name == ''
        assert avatar == 'http://a.png'

    def test_avatar_missing(self):
        page = _mk_page()
        name_el = _loc(page, 'span[class*="emoji-wrap"]').first
        name_el.count = AsyncMock(return_value=1)
        name_el.text_content = AsyncMock(return_value='n')
        with patch('impl.iqiyi.platform.logger'):
            name, avatar = _run(_scrape_iqiyi_profile(page))
        assert name == 'n'
        assert avatar == ''

    def test_probe_exceptions_swallowed(self):
        page = _mk_page()
        _loc(page, 'span[class*="emoji-wrap"]').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        _loc(page, '[class*="user-info"] img').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        with patch('impl.iqiyi.platform.logger'):
            assert _run(_scrape_iqiyi_profile(page)) == ('', '')


# ── 纯函数: cookie 解析 ────────────────────────────────────────────────────

class TestParseCookieToStorageState:
    def test_happy_parse(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('a=1; b=2')
        assert origins == []
        assert [c['name'] for c in cookies] == ['a', 'b']
        for c in cookies:
            assert c['domain'] == '.iqiyi.com'
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

class TestLogin:
    def test_happy_path(self):
        p = _mk_platform()
        page = _mk_page(url=_LOGIN_URL)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('impl.iqiyi.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.iqiyi.platform.logger'):
            # framenavigated 注册时立即触发 handler(模拟登录后页面跳转)
            page.on = MagicMock(
                side_effect=lambda event, fn: fn(page.main_frame)
            )
            _run(p.login('u1', MagicMock(), account_id='acc1'))
        page.goto.assert_awaited_once_with(_LOGIN_URL)
        page.on.assert_called_once()
        assert page.on.call_args.args[0] == 'framenavigated'
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 10
        assert kwargs['account_id'] == 'acc1'
        assert kwargs['scrape_fn'] is _scrape_iqiyi_profile
        assert kwargs['stats_fn'].__func__ is IqiyiPlatform._login_stats_fn
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    def test_login_timeout_puts_500(self):
        p = _mk_platform()
        page = _mk_page(url=_LOGIN_URL)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('impl.iqiyi.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.iqiyi.platform.asyncio.wait_for',
                   AsyncMock(side_effect=TimeoutError('300s up'))), \
             patch('impl.iqiyi.platform.logger'):
            queue = MagicMock()
            _run(p.login('u1', queue))
        queue.put.assert_called_once_with('500')
        slr.assert_not_awaited()
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    def test_handler_probe_error_does_not_set_event(self):
        """_on_url_change 内 wait_for_selector 失败 → except pass,事件不置位 → 走 500。"""
        p = _mk_platform()
        page = _mk_page(url=_LOGIN_URL)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('impl.iqiyi.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.iqiyi.platform.asyncio.wait_for',
                   AsyncMock(side_effect=TimeoutError('300s up'))), \
             patch('impl.iqiyi.platform.logger'):
            page.on = MagicMock(
                side_effect=lambda event, fn: fn(page.main_frame)
            )
            page.wait_for_selector = AsyncMock(side_effect=TimeoutError('no user-info'))
            queue = MagicMock()
            _run(p.login('u1', queue))
        queue.put.assert_called_once_with('500')
        slr.assert_not_awaited()

    def test_non_main_frame_ignored(self):
        p = _mk_platform()
        page = _mk_page(url=_LOGIN_URL)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('impl.iqiyi.platform.save_login_result', AsyncMock()), \
             patch('impl.iqiyi.platform.asyncio.wait_for',
                   AsyncMock(side_effect=TimeoutError('300s up'))), \
             patch('impl.iqiyi.platform.logger'):
            page.on = MagicMock(
                side_effect=lambda event, fn: fn(MagicMock())  # 非主 frame → lambda 返回 None
            )
            queue = MagicMock()
            _run(p.login('u1', queue))
        queue.put.assert_called_once_with('500')
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()


class TestCheckCookie:
    def test_valid(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.iqiyi.platform.logger'):
            assert _run(p.check_cookie('ck.json')) is True
        page.goto.assert_awaited_once_with(_LOGIN_URL, wait_until='domcontentloaded')
        page.wait_for_load_state.assert_awaited_once_with('networkidle')
        browser.close.assert_awaited_once()

    def test_expired(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.iqiyi.platform.logger'):
            page.wait_for_selector = AsyncMock(side_effect=TimeoutError('not logged in'))
            assert _run(p.check_cookie('ck.json')) is False

    def test_outer_exception_returns_false(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.iqiyi.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            assert _run(p.check_cookie('ck.json')) is False


class TestSyncProfile:
    def test_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             patch('impl.iqiyi.platform._scrape_iqiyi_profile',
                   AsyncMock(return_value=('昵称', 'http://a.png'))) as sp, \
             patch.object(p, '_scrape_iqiyi_stats',
                          AsyncMock(return_value=[{'ICON': 'user', 'COUNT': 1, 'NAME': '粉丝', 'SORT': 1}])) as ss:
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '昵称', 'avatar': 'http://a.png',
                       'stats': [{'ICON': 'user', 'COUNT': 1, 'NAME': '粉丝', 'SORT': 1}]}
        sp.assert_awaited_once()
        ss.assert_awaited_once()

    def test_outer_exception_returns_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.iqiyi.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            assert _run(p.sync_profile('ck.json')) == {'name': '', 'avatar': '', 'stats': []}


class TestScrapeIqiyiStats:
    def test_happy_sorted_and_unknown_dropped(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'label': '获赞', 'num': '2'},
            {'label': '粉丝', 'num': '1'},
            {'label': '关注', 'num': '0'},
            {'label': '未知', 'num': '9'},
        ])
        with patch('impl.iqiyi.platform.logger'):
            stats = _run(p._scrape_iqiyi_stats(page))
        assert [s['NAME'] for s in stats] == ['粉丝', '获赞', '关注']
        assert stats[0]['COUNT'] == 1
        assert stats[0]['ICON'] == 'user'

    def test_thousand_separators(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[{'label': '粉丝', 'num': '1,234'}])
        with patch('impl.iqiyi.platform.logger'):
            stats = _run(p._scrape_iqiyi_stats(page))
        assert stats[0]['COUNT'] == 1234

    def test_invalid_number_zero(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[{'label': '粉丝', 'num': 'abc'}])
        with patch('impl.iqiyi.platform.logger'):
            stats = _run(p._scrape_iqiyi_stats(page))
        assert stats[0]['COUNT'] == 0

    def test_wait_timeout_still_scrapes(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        page.evaluate = AsyncMock(return_value=[{'label': '粉丝', 'num': '3'}])
        with patch('impl.iqiyi.platform.logger'):
            stats = _run(p._scrape_iqiyi_stats(page))
        assert stats[0]['COUNT'] == 3

    def test_evaluate_exception_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('js fail'))
        with patch('impl.iqiyi.platform.logger'):
            assert _run(p._scrape_iqiyi_stats(page)) == []

    def test_empty_evaluate(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[])
        with patch('impl.iqiyi.platform.logger'):
            assert _run(p._scrape_iqiyi_stats(page)) == []


class TestLoginStatsFn:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_iqiyi_stats', AsyncMock(return_value=[1])) as ss:
            assert _run(p._login_stats_fn(page, 'acc1')) == [1]
        ss.assert_awaited_once_with(page)

    def test_exception_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_iqiyi_stats',
                          AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('impl.iqiyi.platform.logger'):
            assert _run(p._login_stats_fn(page, 'acc1')) == []


class TestOpenCreatorCenter:
    def test_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_iqiyi_occ.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.iqiyi.platform.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl.iqiyi.platform.create_context_sync', return_value=context) as ccs:
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
        cookie = _mk_cookie_file('t35_iqiyi_occ2.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.iqiyi.platform.create_browser_sync', return_value=browser), \
                 patch('impl.iqiyi.platform.create_context_sync', return_value=context):
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
        cookie = _mk_cookie_file('t35_iqiyi_occ3.json')
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('boom'))
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.iqiyi.platform.create_browser_sync', return_value=browser), \
                 patch('impl.iqiyi.platform.create_context_sync', return_value=context):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)


# ── 编排: _upload_one_video 全流程 ─────────────────────────────────────────

class TestUploadOneVideo:
    def _run(self, p, page, **kw):
        default = dict(
            title='标题', file_path='/m/v.mp4', tags=['a'],
            publish_date=0, account_file='/c/u1.json', enableTimer=False,
            cover_path=None, landscape_cover=None, landscape_cover_169=None,
            creation_declaration='', risk_warning='', enable_cash_activity=False,
            desc='简介',
        )
        default.update(kw)
        return _run(p._upload_one_video(**default))

    def test_happy_full_flow(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.iqiyi.platform.logger'):
            ok = self._run(p, page, title='标题', desc='简介', tags=['a', 'b'])
        assert ok is True
        page.goto.assert_awaited_once_with('https://creator.iqiyi.com/publish/video/wemedia')
        page.wait_for_load_state.assert_awaited_once_with('networkidle')
        page.on.assert_called_once()
        assert page.on.call_args.args[0] == 'request'
        page.locators['input[type="file"]'].first.set_input_files.assert_awaited_once_with('/m/v.mp4')
        mocks['wait_upload'].assert_awaited_once()
        page.wait_for_selector.assert_awaited()
        mocks['fill_title'].assert_awaited_once_with(page, '标题')
        mocks['fill_desc'].assert_awaited_once_with(page, '简介 #a #b')
        mocks['cash'].assert_not_awaited()
        mocks['declaration'].assert_not_awaited()
        mocks['risk'].assert_not_awaited()
        mocks['cover'].assert_not_awaited()
        mocks['schedule'].assert_not_awaited()
        mocks['publish'].assert_awaited_once_with(page)
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)
        context.close.assert_awaited_once()

    def test_publish_failure_returns_false(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.iqiyi.platform.logger'):
            mocks['publish'].return_value = False
            assert self._run(p, page) is False

    def test_request_listener_registered(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p), patch('impl.iqiyi.platform.logger'):
            _run(p._upload_one_video(
                title='T', file_path='/v.mp4', tags=[], publish_date=0,
                account_file='/c.json', desc='',
            ))
        # 上传完成监听器在 set_input_files 之前注册(request 事件)
        assert page.on.call_args.args[0] == 'request'
        handler = page.on.call_args.args[1]
        assert callable(handler)
        # 匹配 upload/record URL 的请求触发 upload_done(通过 _wait 不卡死佐证)
        req = MagicMock()
        req.url = 'https://mp-api.iqiyi.com/v-tool/api/1.0/upload/record?x=1'
        handler(req)
        req2 = MagicMock()
        req2.url = 'https://other.iqiyi.com/foo'
        handler(req2)

    def test_tags_appended_to_desc(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.iqiyi.platform.logger'):
            self._run(p, page, desc='我的简介', tags=['x', 'y'])
        mocks['fill_desc'].assert_awaited_once_with(page, '我的简介 #x #y')

    def test_no_desc_no_tags(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.iqiyi.platform.logger'):
            self._run(p, page, desc='', tags=[])
        mocks['fill_desc'].assert_awaited_once_with(page, '')

    def test_cash_activity_enabled(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.iqiyi.platform.logger'):
            self._run(p, page, enable_cash_activity=True)
        mocks['cash'].assert_awaited_once_with(page)

    def test_creation_declaration_and_risk(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.iqiyi.platform.logger'):
            self._run(p, page, creation_declaration='含AI生成内容', risk_warning='内容可能引人不适，请谨慎观看')
        mocks['declaration'].assert_awaited_once_with(page, '含AI生成内容')
        mocks['risk'].assert_awaited_once_with(page, '内容可能引人不适，请谨慎观看')

    def test_cover_paths_passed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.iqiyi.platform.logger'):
            self._run(p, page, cover_path='/p.png', landscape_cover='/l.png',
                      landscape_cover_169='/l169.png')
        mocks['cover'].assert_awaited_once_with(
            page, portrait_path='/p.png', landscape_path='/l.png',
            landscape_169_path='/l169.png',
        )

    def test_schedule_enabled(self):
        p = _mk_platform()
        pd = datetime(2026, 8, 22, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.iqiyi.platform.logger'):
            self._run(p, page, enableTimer=True, publish_date=pd)
        mocks['schedule'].assert_awaited_once_with(page, pd)

    def test_schedule_disabled_when_timer_off(self):
        p = _mk_platform()
        pd = datetime(2026, 8, 22, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.iqiyi.platform.logger'):
            self._run(p, page, enableTimer=False, publish_date=pd)
        mocks['schedule'].assert_not_awaited()


# ── DOM 辅助: 上传等待 / 标题 / 简介 ──────────────────────────────────────

class TestWaitVideoUploadComplete:
    def test_event_set_returns(self):
        p = _mk_platform()
        page = _mk_page()
        ev = asyncio.Event()
        ev.set()
        with patch('impl.iqiyi.platform.logger'):
            _run(p._wait_video_upload_complete(page, ev))  # 不抛异常,立即返回

    def test_timeout_continues(self):
        p = _mk_platform()
        page = _mk_page()
        ev = asyncio.Event()
        with patch('impl.iqiyi.platform.asyncio.wait_for',
                   AsyncMock(side_effect=TimeoutError('4h up'))), \
             patch('impl.iqiyi.platform.logger'):
            _run(p._wait_video_upload_complete(page, ev))  # 超时仅告警,继续后续步骤


class TestFillTitle:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        inp = _loc(page, 'input[placeholder*="标题字数"]').first
        inp.count = AsyncMock(return_value=1)
        with patch('impl.iqiyi.platform.clear_and_type', AsyncMock()) as cat, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._fill_title(page, '我的标题'))
        inp.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        inp.click.assert_awaited_once()
        cat.assert_awaited_once_with(page, '我的标题'[:30], element=inp)

    def test_empty_title_returns(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.iqiyi.platform.clear_and_type', AsyncMock()) as cat, \
             patch('impl.iqiyi.platform.logger'):
            _run(p._fill_title(page, ''))
        cat.assert_not_awaited()

    def test_fallback_selector(self):
        p = _mk_platform()
        page = _mk_page()
        fallback = _loc(page, '.catalog-desc-title-input input[type="text"]').first
        fallback.count = AsyncMock(return_value=1)
        with patch('impl.iqiyi.platform.clear_and_type', AsyncMock()) as cat, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._fill_title(page, 'T'))
        cat.assert_awaited_once()
        fallback.wait_for.assert_awaited_once_with(state='visible', timeout=10000)

    def test_no_title_input_warns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.iqiyi.platform.clear_and_type', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            _run(p._fill_title(page, '标题'))
        assert any('未找到标题输入框' in str(c) for c in logger.warning.call_args_list)

    def test_title_truncated_to_30(self):
        p = _mk_platform()
        page = _mk_page()
        inp = _loc(page, 'input[placeholder*="标题字数"]').first
        inp.count = AsyncMock(return_value=1)
        long_title = '字' * 40
        with patch('impl.iqiyi.platform.clear_and_type', AsyncMock()) as cat, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._fill_title(page, long_title))
        assert cat.await_args.args[1] == '字' * 30


class TestFillDescription:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        ta = _loc(page, 'textarea[placeholder*="作品简介"]').first
        ta.count = AsyncMock(return_value=1)
        with patch('impl.iqiyi.platform.clear_and_type', AsyncMock()) as cat, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._fill_description(page, '简介' * 200))
        ta.wait_for.assert_awaited_once_with(state='visible', timeout=5000)
        expected = ('简介' * 200)[:450]
        cat.assert_awaited_once_with(page, expected, element=ta)

    def test_empty_returns(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.iqiyi.platform.clear_and_type', AsyncMock()) as cat, \
             patch('impl.iqiyi.platform.logger'):
            _run(p._fill_description(page, ''))
        cat.assert_not_awaited()

    def test_not_found_warns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.iqiyi.platform.clear_and_type', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            _run(p._fill_description(page, 'd'))
        assert any('not found' in str(c) for c in logger.warning.call_args_list)


# ── DOM 辅助: 声明 / 风险 / 现金活动 ──────────────────────────────────────

class TestSetCreationDeclaration:
    def test_map_value_match(self):
        p = _mk_platform()
        page = _mk_page()
        value = CREATION_DECLARATION_MAP['含AI生成内容']
        label = _loc(
            page,
            f'.form-declare-group label.el-radio '
            f'input[type="radio"][value="{value}"] '
            f'>> xpath=ancestor::label',
        ).first
        label.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._set_creation_declaration(page, '含AI生成内容'))
        label.wait_for.assert_awaited_once_with(state='visible', timeout=5000)
        label.click.assert_awaited_once()

    def test_text_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        value = CREATION_DECLARATION_MAP['含AI生成内容']
        # 反查 label:value '1' → '含AI生成内容'
        from impl.iqiyi.platform import CREATION_DECLARATION_REVERSE
        decl_label = CREATION_DECLARATION_REVERSE[value]
        text_label = _loc(
            page,
            f'.form-declare-group label.el-radio:has-text("{decl_label}")',
        ).first
        # 第一个选择器 count=0 → 文本兜底
        _loc(
            page,
            f'.form-declare-group label.el-radio '
            f'input[type="radio"][value="{value}"] '
            f'>> xpath=ancestor::label',
        ).first.count = AsyncMock(return_value=0)
        text_label.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._set_creation_declaration(page, '含AI生成内容'))
        text_label.wait_for.assert_awaited_once_with(state='visible', timeout=5000)
        text_label.click.assert_awaited_once()

    def test_unknown_declaration(self):
        p = _mk_platform()
        page = _mk_page()
        # 未知声明 → value 原样 + 文本兜底(反查不到就原样)
        sel = _loc(
            page,
            '.form-declare-group label.el-radio '
            'input[type="radio"][value="自创"] '
            '>> xpath=ancestor::label',
        ).first
        sel.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._set_creation_declaration(page, '自创'))
        sel.click.assert_awaited_once()

    def test_not_found_warns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            _run(p._set_creation_declaration(page, '含AI生成内容'))
        assert any('not found' in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        page.locator = MagicMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            _run(p._set_creation_declaration(page, '含AI生成内容'))  # 不抛异常
        assert logger.warning.called


class TestSetRiskWarning:
    def test_unknown_option_returns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.iqiyi.platform.logger', logger):
            _run(p._set_risk_warning(page, '不存在的提示'))
        assert any('Unknown risk warning' in str(c) for c in logger.warning.call_args_list)

    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        trigger = _loc(page, '.form-select-full .el-input__inner').first
        trigger.count = AsyncMock(return_value=1)
        option = _loc(page, '.el-select-dropdown__item:has-text("内容含有高危险行为，请勿模仿")').first
        option.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._set_risk_warning(page, '内容含有高危险行为，请勿模仿'))
        trigger.click.assert_awaited_once()
        option.wait_for.assert_awaited_once_with(state='visible', timeout=5000)
        option.click.assert_awaited_once()

    def test_select_not_found(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.iqiyi.platform.logger', logger):
            _run(p._set_risk_warning(page, '内容含有高危险行为，请勿模仿'))
        assert any('not found' in str(c) for c in logger.warning.call_args_list)

    def test_option_not_found_warns(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.form-select-full .el-input__inner').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            _run(p._set_risk_warning(page, '内容含有高危险行为，请勿模仿'))
        assert any('option not found' in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.form-select-full .el-input__inner').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        logger = MagicMock()
        with patch('impl.iqiyi.platform.logger', logger):
            _run(p._set_risk_warning(page, '内容含有高危险行为，请勿模仿'))  # 不抛异常
        assert logger.warning.called


class TestClickCashActivity:
    def test_clicks_activity(self):
        p = _mk_platform()
        page = _mk_page()
        act = _loc(page, '.activity-radio-option:not(.is-checked)').first
        act.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._click_cash_activity(page))
        act.click.assert_awaited_once()

    def test_already_checked_noop(self):
        p = _mk_platform()
        page = _mk_page()
        act = _loc(page, '.activity-radio-option:not(.is-checked)').first
        act.count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('impl.iqiyi.platform.logger', logger):
            _run(p._click_cash_activity(page))
        assert any('already checked' in str(c) for c in logger.info.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.activity-radio-option:not(.is-checked)').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        logger = MagicMock()
        with patch('impl.iqiyi.platform.logger', logger):
            _run(p._click_cash_activity(page))  # 不抛异常
        assert logger.warning.called


# ── DOM 辅助: 封面 ─────────────────────────────────────────────────────────

class _ReusableAwaitable:
    """每次 __await__ 生成全新协程,支持多次 await(AsyncMock 实例本身不可 await)。"""

    def __init__(self, value):
        self._value = value

    def __await__(self):
        async def _gen():
            return self._value
        return _gen().__await__()


def _mk_file_chooser_cm(file_chooser):
    fc_info = MagicMock()
    fc_info.value = _ReusableAwaitable(file_chooser)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fc_info)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestUploadCover:
    def _mk_chooser_page(self):
        page = _mk_page()
        file_chooser = MagicMock()
        file_chooser.set_files = AsyncMock()
        page.expect_file_chooser = MagicMock(return_value=_mk_file_chooser_cm(file_chooser))
        page._file_chooser = file_chooser
        return page

    def test_happy_three_tabs(self):
        p = _mk_platform()
        page = self._mk_chooser_page()
        trigger = _loc(page, 'div.main-edit-bar').first
        trigger.count = AsyncMock(return_value=1)
        tab43 = _loc(page, '.tab-item:has-text("4:3")').first
        tab43.count = AsyncMock(return_value=1)
        tab169 = _loc(page, '.tab-item:has-text("16:9")').first
        tab169.count = AsyncMock(return_value=1)
        panel = _loc(page, '.crop-content:not([style*="display: none"])').first
        panel.count = AsyncMock(return_value=1)
        panel.locator('.upload-btn-wrap')  # 预注册子选择器
        panel.subs['.upload-btn-wrap'].first.click = AsyncMock()
        done = _loc(page, 'button:has-text("完成")').first
        done.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._upload_cover(
                page, portrait_path='/p.png', landscape_path='/l.png',
                landscape_169_path='/l169.png',
            ))
        trigger.evaluate.assert_awaited_once_with('el => el.click()')
        page.expect_file_chooser.assert_called()
        assert page._file_chooser.set_files.await_count == 3
        paths = [c.args[0] for c in page._file_chooser.set_files.await_args_list]
        assert paths == ['/p.png', '/l.png', '/l169.png']
        tab43.click.assert_awaited_once()
        tab169.click.assert_awaited_once()
        done.click.assert_awaited_once()

    def test_trigger_not_found_aborts(self):
        p = _mk_platform()
        page = self._mk_chooser_page()
        logger = MagicMock()
        with patch('impl.iqiyi.platform.logger', logger):
            _run(p._upload_cover(page, portrait_path='/p.png'))
        assert any('trigger not found' in str(c) for c in logger.warning.call_args_list)
        page.expect_file_chooser.assert_not_called()

    def test_no_portrait_skips(self):
        p = _mk_platform()
        page = self._mk_chooser_page()
        _loc(page, 'div.main-edit-bar').first.count = AsyncMock(return_value=1)
        _loc(page, '.tab-item:has-text("4:3")').first.count = AsyncMock(return_value=1)
        done = _loc(page, 'button:has-text("完成")').first
        done.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._upload_cover(page, landscape_path='/l.png'))
        assert page._file_chooser.set_files.await_count == 1
        assert page._file_chooser.set_files.await_args.args[0] == '/l.png'

    def test_landscape_tab_missing(self):
        p = _mk_platform()
        page = self._mk_chooser_page()
        _loc(page, 'div.main-edit-bar').first.count = AsyncMock(return_value=1)
        tab43 = _loc(page, '.tab-item:has-text("4:3")').first
        tab43.count = AsyncMock(return_value=0)
        _loc(page, '.tab-item:has-text("16:9")').first.count = AsyncMock(return_value=1)
        done = _loc(page, 'button:has-text("完成")').first
        done.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            _run(p._upload_cover(
                page, portrait_path='/p.png', landscape_path='/l.png',
                landscape_169_path='/l169.png',
            ))
        assert page._file_chooser.set_files.await_count == 2  # 竖 + 16:9
        assert any('tab not found' in str(c) for c in logger.warning.call_args_list)

    def test_169_tab_missing(self):
        p = _mk_platform()
        page = self._mk_chooser_page()
        _loc(page, 'div.main-edit-bar').first.count = AsyncMock(return_value=1)
        _loc(page, '.tab-item:has-text("4:3")').first.count = AsyncMock(return_value=1)
        _loc(page, '.tab-item:has-text("16:9")').first.count = AsyncMock(return_value=0)
        done = _loc(page, 'button:has-text("完成")').first
        done.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            _run(p._upload_cover(
                page, portrait_path='/p.png', landscape_path='/l.png',
                landscape_169_path='/l169.png',
            ))
        assert page._file_chooser.set_files.await_count == 2  # 竖 + 4:3
        assert any('16:9 landscape tab not found' in str(c) for c in logger.warning.call_args_list)

    def test_done_missing(self):
        p = _mk_platform()
        page = self._mk_chooser_page()
        _loc(page, 'div.main-edit-bar').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            _run(p._upload_cover(page, portrait_path='/p.png'))
        assert any("'完成' button not found" in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = self._mk_chooser_page()
        page.locator = MagicMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.iqiyi.platform.logger', logger):
            _run(p._upload_cover(page, portrait_path='/p.png'))  # 不抛异常
        assert logger.exception.called

    def test_legacy_kwargs_fallback(self):
        p = _mk_platform()
        page = self._mk_chooser_page()
        _loc(page, 'div.main-edit-bar').first.count = AsyncMock(return_value=1)
        done = _loc(page, 'button:has-text("完成")').first
        done.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._upload_cover(page, cover_path='/legacy.png'))
        assert page._file_chooser.set_files.await_args.args[0] == '/legacy.png'


# ── DOM 辅助: 定时发布 ─────────────────────────────────────────────────────

class TestSetScheduleTime:
    PD = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))

    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, '.form-publish-block .el-radio-group label:has-text("定时发布")').first
        radio.count = AsyncMock(return_value=1)
        date_sel = ('.form-publish-block input[placeholder*="选择日期"], '
                    '.form-publish-block input[placeholder*="时间"]')
        date_input = _loc(page, date_sel).first
        date_input.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._set_schedule_time(page, self.PD))
        radio.click.assert_awaited_once()
        date_input.click.assert_awaited_once()
        date_input.fill.assert_awaited_once_with('2026-08-22 10:05')
        page.keyboard.press.assert_awaited_once_with('Enter')

    def test_radio_missing_still_fills_date(self):
        p = _mk_platform()
        page = _mk_page()
        date_sel = ('.form-publish-block input[placeholder*="选择日期"], '
                    '.form-publish-block input[placeholder*="时间"]')
        date_input = _loc(page, date_sel).first
        date_input.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            _run(p._set_schedule_time(page, self.PD))
        date_input.fill.assert_awaited_once()

    def test_date_input_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            _run(p._set_schedule_time(page, self.PD))
        assert any('not found' in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, '.form-publish-block .el-radio-group label:has-text("定时发布")').first
        radio.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.iqiyi.platform.logger', logger):
            _run(p._set_schedule_time(page, self.PD))  # 不抛异常
        assert logger.warning.called


# ── DOM 辅助: 发布按钮 ─────────────────────────────────────────────────────

class TestClickPublish:
    def test_no_upload_card_url_success(self):
        p = _mk_platform()
        page = _mk_page(url='https://creator.iqiyi.com/publish/success')
        publish_btn = _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first
        publish_btn.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            assert _run(p._click_publish(page)) is True
        publish_btn.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        publish_btn.click.assert_awaited_once()
        page.wait_for_function.assert_awaited_once()

    def test_success_text_keyword(self):
        p = _mk_platform()
        page = _mk_page(url='https://creator.iqiyi.com/content')
        _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first.count = AsyncMock(return_value=1)
        # 页面文本命中「已发布」
        def _by_text(kw, exact=False):
            loc = _mk_locator()
            loc.count = AsyncMock(return_value=1 if kw == '已发布' else 0)
            return loc
        page.get_by_text = MagicMock(side_effect=_by_text)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            assert _run(p._click_publish(page)) is True

    def test_no_success_flag_returns_false(self):
        p = _mk_platform()
        page = _mk_page(url='https://creator.iqiyi.com/content')
        _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            assert _run(p._click_publish(page)) is False
        assert any('未检测到成功标志' in str(c) for c in logger.warning.call_args_list)

    def test_url_timeout_returns_false(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first.count = AsyncMock(return_value=1)
        page.wait_for_function = AsyncMock(side_effect=TimeoutError('still on page'))
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            assert _run(p._click_publish(page)) is False

    def test_upload_card_present_waits_then_publish(self):
        p = _mk_platform()
        page = _mk_page(url='https://creator.iqiyi.com/publish/success')
        card = _loc(page, '.up-phone-card').first
        card.count = AsyncMock(side_effect=[1, 0])  # 出现 → 消失
        _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            assert _run(p._click_publish(page)) is True
        assert card.count.await_count >= 2

    def test_percent_probe_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page(url='https://creator.iqiyi.com/publish/success')
        card = _loc(page, '.up-phone-card').first
        card.count = AsyncMock(side_effect=[1, 1, 0])  # 初始可见 → 循环内仍可见(触发探测) → 消失
        card.locator('.up-progress-percent')  # 预注册
        card.subs['.up-progress-percent'].first.count = AsyncMock(
            side_effect=RuntimeError('probe fail')
        )
        _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            assert _run(p._click_publish(page)) is True  # 探测异常 pass,继续轮询

    def test_upload_card_30min_timeout_warns(self):
        p = _mk_platform()
        page = _mk_page(url='https://creator.iqiyi.com/publish/success')
        _loc(page, '.up-phone-card').first.count = AsyncMock(return_value=1)  # 卡片一直存在

        class _FakeLoop:
            def __init__(self):
                self._times = [0.0, 10 ** 9]

            def time(self):
                return self._times.pop(0) if len(self._times) > 1 else self._times[0]

        fake_loop = _FakeLoop()
        _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.iqiyi.platform.asyncio.get_event_loop', return_value=fake_loop), \
             patch('impl.iqiyi.platform.logger', logger):
            assert _run(p._click_publish(page)) is True
        assert any('等待上传区域消失超时(30min)' in str(c) for c in logger.warning.call_args_list)

    def test_upload_card_count_exception_breaks(self):
        p = _mk_platform()
        page = _mk_page(url='https://creator.iqiyi.com/publish/success')
        card = _loc(page, '.up-phone-card').first
        card.count = AsyncMock(side_effect=[1, RuntimeError('boom')])  # 初始可见 → 循环内探测异常 → break
        _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            assert _run(p._click_publish(page)) is True  # 异常 break 后继续发布

    def test_upload_card_initial_probe_error_ignored(self):
        """初始 count 探测抛异常 → 外层 except,忽略后直接点发布。"""
        p = _mk_platform()
        page = _mk_page(url='https://creator.iqiyi.com/publish/success')
        _loc(page, '.up-phone-card').first.count = AsyncMock(side_effect=RuntimeError('boom'))
        _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            assert _run(p._click_publish(page)) is True
        assert any('等待上传区域异常' in str(c) for c in logger.info.call_args_list)

    def test_upload_card_percent_logged(self):
        p = _mk_platform()
        page = _mk_page(url='https://creator.iqiyi.com/publish/success')
        card = _loc(page, '.up-phone-card').first
        card.count = AsyncMock(side_effect=[1, 1, 0])
        card.locator('.up-progress-percent')  # 预注册子选择器
        percent = card.subs['.up-progress-percent'].first
        percent.count = AsyncMock(return_value=1)
        percent.text_content = AsyncMock(side_effect=['42%', '42%', '77%'])
        _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.iqiyi.platform.logger', logger):
            assert _run(p._click_publish(page)) is True
        assert any(
            c.args[0] == '[iqiyi] 视频上传中 %s,等待完成...' and c.args[1] == '42%'
            for c in logger.info.call_args_list
        )

    def test_text_probe_exception_continues(self):
        p = _mk_platform()
        page = _mk_page(url='https://creator.iqiyi.com/content')
        _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first.count = AsyncMock(return_value=1)
        attempts = {'n': 0}

        def _by_text(kw, exact=False):
            attempts['n'] += 1
            if attempts['n'] == 1:
                raise RuntimeError('probe fail')  # 第一个关键词探测失败 → continue
            loc = _mk_locator()
            loc.count = AsyncMock(return_value=1 if kw == '已发布' else 0)
            return loc

        page.get_by_text = MagicMock(side_effect=_by_text)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'):
            assert _run(p._click_publish(page)) is True

    def test_publish_click_exception_raises(self):
        p = _mk_platform()
        page = _mk_page()
        btn = _loc(page, 'button:has-text("发布"), button:has-text("提交"), button[type="submit"]').first
        btn.count = AsyncMock(return_value=1)
        btn.click = AsyncMock(side_effect=RuntimeError('stale'))
        with patch('asyncio.sleep', AsyncMock()), patch('impl.iqiyi.platform.logger'), \
             pytest.raises(RuntimeError):
            _run(p._click_publish(page))
