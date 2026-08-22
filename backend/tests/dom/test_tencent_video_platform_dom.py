"""腾讯视频 platform.py DOM 交互层契约测试（T35 第五期）。

覆盖 impl/tencent_video/platform.py（533 stmts，基线 22%）:
- 模块级: _scrape_tencent_video_profile（昵称+头像抓取/超时/缺失/探测异常兜底）
- 纯函数: _parse_cookie_to_storage_state（.qq.com 域/expires/httpOnly/跳过无效对）
- 登录/校验/同步: login（framenavigated 事件驱动/主 frame 判定/非主 frame 忽略）
  / check_cookie（userInfo 判定/外层异常 False） / sync_profile（profile+stats/网络超时兜底）
  / _scrape_tencent_video_stats（data-name map/SORT 排序/千分位/非法数字/超时诊断）
  / _login_stats_fn（goto 异常吞掉仍抓取） / open_creator_center（线程启动/close 异常吞掉）
- 编排: _upload_one_video 全流程（request 监听 UploadNotify/上传入口超时 DEBUG dump/
  4h 超时继续/标题/封面/声明/定时/发布/回写/关闭）
- DOM 辅助: _fill_title（双选择器/80 截断） / _upload_cover（上传区/替换兜底/ReactModal/
  display:block+set_input_files/使用按钮双兜底/异常非阻断） / _upload_extra_landscape_cover
  （filter 选填/同 modal 流程） / _upload_extra_portrait_cover（对称流程）
  / _set_creation_declarations（白名单/已勾选跳过/未知/异常吞掉）
  / _set_schedule_time（switch 开关/dateTimeSelect/popupWrap/itemWrap 三列/确定/异常吞掉）
  / _click_publish（成功文本/URL 跳转/disabled 等待/5s 重试点击/60s 超时 raise）
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
from impl.tencent_video.platform import (
    _HOME_URL,
    _LOGIN_URL,
    _PUBLISH_URL,
    CREATION_DECLARATIONS,
    TencentVideoPlatform,
    _scrape_tencent_video_profile,
)


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return TencentVideoPlatform()


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
    loc.is_checked = AsyncMock(return_value=False)
    loc.is_enabled = AsyncMock(return_value=True)
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


def _mk_page(url='https://mp.v.qq.com/publishVideo/video'):
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


def _mk_cookie_file(name='t35_tencent_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


@contextmanager
def _mk_upload_one_steps(p):
    """把 _upload_one_video 的内部子步骤全部替换为可断言的 AsyncMock。"""
    mocks = dict(
        fill_title=AsyncMock(),
        cover=AsyncMock(),
        extra_landscape=AsyncMock(),
        extra_portrait=AsyncMock(),
        declarations=AsyncMock(),
        schedule=AsyncMock(),
        publish=AsyncMock(return_value=True),
        close_browser=AsyncMock(),
    )
    with patch.object(p, '_fill_title', mocks['fill_title']), \
         patch.object(p, '_upload_cover', mocks['cover']), \
         patch.object(p, '_upload_extra_landscape_cover', mocks['extra_landscape']), \
         patch.object(p, '_upload_extra_portrait_cover', mocks['extra_portrait']), \
         patch.object(p, '_set_creation_declarations', mocks['declarations']), \
         patch.object(p, '_set_schedule_time', mocks['schedule']), \
         patch.object(p, '_click_publish', mocks['publish']), \
         patch.object(p, 'close_browser', mocks['close_browser']), \
         patch('impl.tencent_video.platform.asyncio.wait_for', AsyncMock()), \
         patch('asyncio.sleep', AsyncMock()):
        yield mocks


def _mk_filtered(base, **kw):
    """把 base.filter(...) 固定返回一个可配置的 locator(filter 默认每次新建对象)。"""
    flt = _mk_locator()
    base.filter = MagicMock(side_effect=lambda **fkw: flt)
    return flt


async def _yield_once():
    await asyncio.sleep(0)


class _FakeEvent:
    """wait 立即返回(带一次 yield),set 记录调用;用于验证 handler 不置位时不挂起。"""

    def __init__(self):
        self.set = MagicMock()
        self.wait = AsyncMock(side_effect=_yield_once)


# ── 模块级: profile 抓取 ───────────────────────────────────────────────────

class TestScrapeTencentVideoProfile:
    def test_happy_path(self):
        page = _mk_page()
        name_el = _loc(page, 'a[href*="videoplus"][class*="name"]').first
        name_el.count = AsyncMock(return_value=1)
        name_el.text_content = AsyncMock(return_value='  鹅厂君  ')
        ava_el = _loc(page, 'div[class*="userAvatar"] img').first
        ava_el.count = AsyncMock(return_value=1)
        ava_el.get_attribute = AsyncMock(return_value='http://avatar.png')
        with patch('impl.tencent_video.platform.logger'):
            name, avatar = _run(_scrape_tencent_video_profile(page))
        assert name == '鹅厂君'
        assert avatar == 'http://avatar.png'
        page.wait_for_selector.assert_awaited_once_with('div[class*="userInfo"]', timeout=10000)

    def test_wait_selector_timeout_still_scrapes(self):
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        name_el = _loc(page, 'a[href*="videoplus"][class*="name"]').first
        name_el.count = AsyncMock(return_value=1)
        name_el.text_content = AsyncMock(return_value='n')
        with patch('impl.tencent_video.platform.logger'):
            name, avatar = _run(_scrape_tencent_video_profile(page))
        assert name == 'n'
        assert avatar == ''

    def test_name_missing(self):
        page = _mk_page()
        ava_el = _loc(page, 'div[class*="userAvatar"] img').first
        ava_el.count = AsyncMock(return_value=1)
        ava_el.get_attribute = AsyncMock(return_value='http://a.png')
        with patch('impl.tencent_video.platform.logger'):
            name, avatar = _run(_scrape_tencent_video_profile(page))
        assert name == ''
        assert avatar == 'http://a.png'

    def test_avatar_missing(self):
        page = _mk_page()
        name_el = _loc(page, 'a[href*="videoplus"][class*="name"]').first
        name_el.count = AsyncMock(return_value=1)
        name_el.text_content = AsyncMock(return_value='n')
        with patch('impl.tencent_video.platform.logger'):
            name, avatar = _run(_scrape_tencent_video_profile(page))
        assert name == 'n'
        assert avatar == ''

    def test_probe_exceptions_swallowed(self):
        page = _mk_page()
        _loc(page, 'a[href*="videoplus"][class*="name"]').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        _loc(page, 'div[class*="userAvatar"] img').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        with patch('impl.tencent_video.platform.logger'):
            assert _run(_scrape_tencent_video_profile(page)) == ('', '')


# ── 纯函数: cookie 解析 ────────────────────────────────────────────────────

class TestParseCookieToStorageState:
    def test_happy_parse(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('a=1; b=2')
        assert origins == []
        assert [c['name'] for c in cookies] == ['a', 'b']
        for c in cookies:
            assert c['domain'] == '.qq.com'
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
        page = _mk_page(url='https://mp.v.qq.com/homepage')
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('impl.tencent_video.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.tencent_video.platform.logger'):
            # framenavigated 注册时立即触发 handler(模拟登录后跳转到 homepage)
            page.on = MagicMock(side_effect=lambda event, fn: fn(page.main_frame))
            _run(p.login('u1', MagicMock(), account_id='acc1'))
        page.goto.assert_awaited_once_with(_LOGIN_URL)
        page.on.assert_called_once()
        assert page.on.call_args.args[0] == 'framenavigated'
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 9
        assert kwargs['platform_name'] == '腾讯视频'
        assert kwargs['account_id'] == 'acc1'
        assert kwargs['scrape_fn'] is _scrape_tencent_video_profile
        assert kwargs['stats_fn'].__func__ is TencentVideoPlatform._login_stats_fn
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    def test_non_main_frame_ignored(self):
        """非主 frame → lambda 返回 None,事件不置位(无超时,靠 fake wait 不挂起)。"""
        p = _mk_platform()
        page = _mk_page(url=_LOGIN_URL)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        fake_ev = _FakeEvent()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('impl.tencent_video.platform.asyncio.Event', return_value=fake_ev), \
             patch('impl.tencent_video.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.tencent_video.platform.logger'):
            page.on = MagicMock(side_effect=lambda event, fn: fn(MagicMock()))
            _run(p.login('u1', MagicMock()))
        fake_ev.set.assert_not_called()
        slr.assert_awaited_once()  # fake wait 立即返回 → 流程继续(真实场景会一直等待用户扫码)
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    def test_main_frame_without_homepage_does_not_set(self):
        """主 frame 但 URL 不含 homepage → handler 探测不置位。"""
        p = _mk_platform()
        page = _mk_page(url=_LOGIN_URL)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        fake_ev = _FakeEvent()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('impl.tencent_video.platform.asyncio.Event', return_value=fake_ev), \
             patch('impl.tencent_video.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.tencent_video.platform.logger'):
            page.on = MagicMock(side_effect=lambda event, fn: fn(page.main_frame))
            _run(p.login('u1', MagicMock()))
        fake_ev.set.assert_not_called()
        slr.assert_awaited_once()
        context.close.assert_awaited_once()


class TestCheckCookie:
    def test_valid(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.tencent_video.platform.logger'):
            assert _run(p.check_cookie('ck.json')) is True
        page.goto.assert_awaited_once_with(_HOME_URL, wait_until='domcontentloaded')
        page.wait_for_load_state.assert_awaited_once_with('networkidle')
        browser.close.assert_awaited_once()

    def test_expired(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.tencent_video.platform.logger'):
            page.wait_for_selector = AsyncMock(side_effect=TimeoutError('not logged in'))
            assert _run(p.check_cookie('ck.json')) is False

    def test_outer_exception_returns_false(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.tencent_video.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            assert _run(p.check_cookie('ck.json')) is False


class TestSyncProfile:
    def test_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             patch('impl.tencent_video.platform._scrape_tencent_video_profile',
                   AsyncMock(return_value=('昵称', 'http://a.png'))) as sp, \
             patch.object(p, '_scrape_tencent_video_stats',
                          AsyncMock(return_value=[{'ICON': 'user', 'COUNT': 1, 'NAME': '粉丝', 'SORT': 1}])) as ss:
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '昵称', 'avatar': 'http://a.png',
                       'stats': [{'ICON': 'user', 'COUNT': 1, 'NAME': '粉丝', 'SORT': 1}]}
        sp.assert_awaited_once()
        ss.assert_awaited_once()

    def test_networkidle_timeout_still_stats(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             patch('impl.tencent_video.platform._scrape_tencent_video_profile',
                   AsyncMock(return_value=('n', ''))), \
             patch.object(p, '_scrape_tencent_video_stats', AsyncMock(return_value=[])) as ss:
            _page.wait_for_load_state = AsyncMock(side_effect=[
                None,  # 第一次 networkidle(首页)
                TimeoutError('spa slow'),  # 第二次 networkidle(分析页) 超时 → 吞掉
            ])
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': 'n', 'avatar': '', 'stats': []}
        ss.assert_awaited_once()

    def test_stats_exception_keeps_profile(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             patch('impl.tencent_video.platform._scrape_tencent_video_profile',
                   AsyncMock(return_value=('昵称', 'http://a.png'))), \
             patch.object(p, '_scrape_tencent_video_stats',
                          AsyncMock(side_effect=RuntimeError('js fail'))) as ss, \
             patch('impl.tencent_video.platform.logger'):
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '昵称', 'avatar': 'http://a.png', 'stats': []}
        ss.assert_awaited_once()

    def test_outer_exception_returns_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.tencent_video.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            assert _run(p.sync_profile('ck.json')) == {'name': '', 'avatar': '', 'stats': []}


class TestScrapeTencentVideoStats:
    def test_happy_sorted_and_unknown_dropped(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'key': 'in_like_cnt', 'num': '2'},
            {'key': 'in_subscribe_cnt', 'num': '1'},
            {'key': 'in_comment_cnt', 'num': '3'},
            {'key': 'unknown_key', 'num': '9'},
        ])
        with patch('impl.tencent_video.platform.logger'):
            stats = _run(p._scrape_tencent_video_stats(page))
        assert [s['NAME'] for s in stats] == ['粉丝', '总点赞', '总评论']
        assert stats[0]['COUNT'] == 1
        assert stats[0]['ICON'] == 'user'
        assert stats[1]['SORT'] == 2

    def test_all_map_keys(self):
        p = _mk_platform()
        page = _mk_page()
        raw = [
            {'key': 'in_subscribe_cnt', 'num': '1'},
            {'key': 'in_like_cnt', 'num': '2'},
            {'key': 'in_comment_cnt', 'num': '3'},
            {'key': 'in_anti_vfinish_cnt', 'num': '4'},
            {'key': 'in_vfinish_valid_cnt', 'num': '5'},
            {'key': 'in_pdtm_ms', 'num': '6'},
            {'key': 'in_binge_uv', 'num': '7'},
            {'key': 'in_call_share_page_cnt', 'num': '8'},
        ]
        page.evaluate = AsyncMock(return_value=raw)
        with patch('impl.tencent_video.platform.logger'):
            stats = _run(p._scrape_tencent_video_stats(page))
        assert [s['SORT'] for s in stats] == [1, 2, 3, 4, 5, 6, 7, 8]
        assert stats[-1]['NAME'] == '总分享'

    def test_thousand_separators(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[{'key': 'in_subscribe_cnt', 'num': '1,234'}])
        with patch('impl.tencent_video.platform.logger'):
            stats = _run(p._scrape_tencent_video_stats(page))
        assert stats[0]['COUNT'] == 1234

    def test_invalid_number_zero(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[{'key': 'in_subscribe_cnt', 'num': 'abc'}])
        with patch('impl.tencent_video.platform.logger'):
            stats = _run(p._scrape_tencent_video_stats(page))
        assert stats[0]['COUNT'] == 0

    def test_wait_timeout_still_scrapes_with_diagnostics(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        page.title = AsyncMock(return_value='数据中心')
        page.evaluate = AsyncMock(return_value=[{'key': 'in_like_cnt', 'num': '3'}])
        with patch('impl.tencent_video.platform.logger'):
            stats = _run(p._scrape_tencent_video_stats(page))
        assert stats[0]['COUNT'] == 3
        page.title.assert_awaited_once()
        page.evaluate.assert_awaited()

    def test_diagnostic_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        page.title = AsyncMock(side_effect=RuntimeError('no title'))
        page.evaluate = AsyncMock(return_value=[{'key': 'in_like_cnt', 'num': '3'}])
        with patch('impl.tencent_video.platform.logger'):
            stats = _run(p._scrape_tencent_video_stats(page))
        assert stats[0]['COUNT'] == 3

    def test_empty_results_logs(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[{'key': 'unknown_key', 'num': '9'}])
        logger = MagicMock()
        with patch('impl.tencent_video.platform.logger', logger):
            assert _run(p._scrape_tencent_video_stats(page)) == []
        assert any('未抓到任何 stats' in str(c) for c in logger.info.call_args_list)

    def test_evaluate_exception_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('js fail'))
        with patch('impl.tencent_video.platform.logger'):
            assert _run(p._scrape_tencent_video_stats(page)) == []

    def test_empty_evaluate(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[])
        with patch('impl.tencent_video.platform.logger'):
            assert _run(p._scrape_tencent_video_stats(page)) == []


class TestLoginStatsFn:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_tencent_video_stats', AsyncMock(return_value=[1])) as ss:
            assert _run(p._login_stats_fn(page, 'acc1')) == [1]
        ss.assert_awaited_once_with(page)

    def test_networkidle_timeout_continues(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_load_state = AsyncMock(side_effect=TimeoutError('slow'))
        with patch.object(p, '_scrape_tencent_video_stats', AsyncMock(return_value=[1])) as ss:
            assert _run(p._login_stats_fn(page, 'acc1')) == [1]
        ss.assert_awaited_once_with(page)

    def test_goto_exception_still_scrapes(self):
        p = _mk_platform()
        page = _mk_page()
        page.goto = AsyncMock(side_effect=RuntimeError('net down'))
        with patch.object(p, '_scrape_tencent_video_stats', AsyncMock(return_value=[1])) as ss:
            assert _run(p._login_stats_fn(page, 'acc1')) == [1]
        ss.assert_awaited_once_with(page)

    def test_stats_exception_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_tencent_video_stats',
                          AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('impl.tencent_video.platform.logger'):
            assert _run(p._login_stats_fn(page, 'acc1')) == []


class TestOpenCreatorCenter:
    def test_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_tencent_occ.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.tencent_video.platform.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl.tencent_video.platform.create_context_sync', return_value=context) as ccs:
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
        cookie = _mk_cookie_file('t35_tencent_occ2.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.tencent_video.platform.create_browser_sync', return_value=browser), \
                 patch('impl.tencent_video.platform.create_context_sync', return_value=context):
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
        cookie = _mk_cookie_file('t35_tencent_occ3.json')
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('boom'))
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.tencent_video.platform.create_browser_sync', return_value=browser), \
                 patch('impl.tencent_video.platform.create_context_sync', return_value=context):
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
            primary_cover=None, primary_aspect='16:9',
            extra_landscape_cover=None, extra_portrait_cover=None,
            creation_declarations=None, desc='简介',
        )
        default.update(kw)
        return _run(p._upload_one_video(**default))

    def test_happy_full_flow(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.tencent_video.platform.logger'):
            ok = self._run(p, page, title='标题', desc='简介', tags=['a', 'b'])
        assert ok is None  # _upload_one_video 无返回值
        page.goto.assert_awaited_once_with(_PUBLISH_URL)
        page.wait_for_load_state.assert_awaited_once_with('networkidle')
        page.on.assert_called_once()
        assert page.on.call_args.args[0] == 'request'
        page.wait_for_selector.assert_awaited_once_with(
            'input[type="file"], [dt-mpid*="upload"]', state='attached', timeout=30000,
        )
        _loc(page, 'input[type="file"]').first.set_input_files.assert_awaited_once_with('/m/v.mp4')
        mocks['fill_title'].assert_awaited_once_with(page, '标题')
        mocks['publish'].assert_awaited_once_with(page)
        context.storage_state.assert_called_once_with(path='/c/u1.json')
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)
        # 未启用定时/无封面/无声明 → 相关步骤不调用
        mocks['cover'].assert_not_awaited()
        mocks['extra_landscape'].assert_not_awaited()
        mocks['extra_portrait'].assert_not_awaited()
        mocks['declarations'].assert_not_awaited()
        mocks['schedule'].assert_not_awaited()

    def test_desc_fallback_when_no_title(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.tencent_video.platform.logger'):
            self._run(p, page, title='', desc='简介文本')
        mocks['fill_title'].assert_awaited_once_with(page, '简介文本')

    def test_request_listener_sets_event(self):
        """注册的 request 监听:URL 命中 UploadNotify → 事件置位 → wait 立即返回。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks:
            def _on(event, fn):
                req = MagicMock()
                req.url = 'https://mp.v.qq.com/cgi/trpc.creator_center.backend.VideoFusion/UploadNotify?vid=1'
                fn(req)
            page.on = MagicMock(side_effect=_on)
            # wait_for 改为真实等待事件(默认被 steps 上下文替换为 AsyncMock)
            with patch('impl.tencent_video.platform.asyncio.wait_for',
                       side_effect=lambda coro, timeout: coro):
                self._run(p, page, title='T')
        page.on.assert_called_once()
        mocks['fill_title'].assert_awaited_once()  # 事件置位后流程继续

    def test_upload_entry_timeout_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.tencent_video.platform.logger'):
            page.wait_for_selector = AsyncMock(side_effect=TimeoutError('30s up'))
            with pytest.raises(Exception, match='未找到视频上传入口'):
                self._run(p, page, title='T')
        # DEBUG dump: body 文本探测被调用
        page.title.assert_awaited()
        mocks['fill_title'].assert_not_awaited()

    def test_upload_entry_timeout_dump_error_still_raises(self):
        """DEBUG dump 探测本身抛异常 → 内层 except 吞掉,仍 raise 未找到上传入口。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.tencent_video.platform.logger'):
            page.wait_for_selector = AsyncMock(side_effect=TimeoutError('30s up'))
            page.title = AsyncMock(side_effect=RuntimeError('tab closed'))
            with pytest.raises(Exception, match='未找到视频上传入口'):
                self._run(p, page, title='T')
        mocks['fill_title'].assert_not_awaited()

    def test_upload_notify_timeout_continues(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.tencent_video.platform.asyncio.wait_for',
                   AsyncMock(side_effect=TimeoutError('4h up'))), \
             patch('impl.tencent_video.platform.logger'):
            self._run(p, page, title='T')
        mocks['fill_title'].assert_awaited_once()  # 4h 超时仅告警,继续后续步骤

    def test_covers_and_declarations_passed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.tencent_video.platform.logger'):
            self._run(
                p, page, title='T',
                primary_cover='/main.png', primary_aspect='portrait',
                extra_landscape_cover='/l.png', extra_portrait_cover='/p.png',
                creation_declarations=['内容由AI生成'],
            )
        mocks['cover'].assert_awaited_once_with(page, '/main.png', aspect='portrait')
        mocks['extra_landscape'].assert_awaited_once_with(page, '/l.png')
        mocks['extra_portrait'].assert_awaited_once_with(page, '/p.png')
        mocks['declarations'].assert_awaited_once_with(page, ['内容由AI生成'])

    def test_schedule_enabled(self):
        p = _mk_platform()
        pd = datetime(2026, 8, 22, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.tencent_video.platform.logger'):
            self._run(p, page, enableTimer=True, publish_date=pd)
        mocks['schedule'].assert_awaited_once_with(page, pd)

    def test_schedule_disabled_when_publish_date_zero(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks, \
             patch('impl.tencent_video.platform.logger'):
            self._run(p, page, enableTimer=True, publish_date=0)
        mocks['schedule'].assert_not_awaited()

    def test_publish_failure_propagates(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p) as mocks:
            mocks['publish'].side_effect = RuntimeError('publish fail')
            with pytest.raises(RuntimeError, match='publish fail'):
                self._run(p, page, title='T')
        mocks['close_browser'].assert_awaited_once()  # finally 仍关闭浏览器


# ── DOM 辅助: 标题 / 封面 ─────────────────────────────────────────────────

class TestFillTitle:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        container = _loc(page, 'div[data-field-name="videos.0.title"]').first
        container.count = AsyncMock(return_value=1)
        title_div = container.locator('div.ProseMirror.ExEditor-cc-title-input').first
        title_div.count = AsyncMock(return_value=1)
        with patch('impl.tencent_video.platform.clear_and_type', AsyncMock()) as cat, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._fill_title(page, '我的标题'))
        title_div.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        title_div.click.assert_awaited_once()
        cat.assert_awaited_once_with(page, '我的标题')

    def test_empty_title_returns(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.tencent_video.platform.clear_and_type', AsyncMock()) as cat, \
             patch('impl.tencent_video.platform.logger'):
            _run(p._fill_title(page, ''))
        cat.assert_not_awaited()

    def test_container_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.tencent_video.platform.clear_and_type', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._fill_title(page, '标题'))
        assert any('Title field not found' in str(c) for c in logger.warning.call_args_list)

    def test_contenteditable_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, 'div[data-field-name="videos.0.title"]').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('impl.tencent_video.platform.clear_and_type', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._fill_title(page, '标题'))
        assert any('Title contenteditable div not found' in str(c) for c in logger.warning.call_args_list)

    def test_title_truncated_to_80(self):
        p = _mk_platform()
        page = _mk_page()
        container = _loc(page, 'div[data-field-name="videos.0.title"]').first
        container.count = AsyncMock(return_value=1)
        container.locator('div.ProseMirror.ExEditor-cc-title-input').first.count = AsyncMock(return_value=1)
        long_title = '字' * 100
        with patch('impl.tencent_video.platform.clear_and_type', AsyncMock()) as cat, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._fill_title(page, long_title))
        assert cat.await_args.args[1] == '字' * 80


class TestUploadCover:
    def test_happy_via_upload_area(self):
        p = _mk_platform()
        page = _mk_page()
        upload_area = _loc(page, '[role="button"]:has-text("上传横版封面")').first
        upload_area.count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.ReactModal__Content').first
        cover_input = modal.locator('input#uploadCoverBtn')
        use_btn = modal.locator('button[dt-mpid="上传封面确定"]').first
        use_btn.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._upload_cover(page, '/cover.png', aspect='16:9'))
        upload_area.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        upload_area.click.assert_awaited_once()
        modal.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        cover_input.wait_for.assert_awaited_once_with(state='attached', timeout=10000)
        cover_input.evaluate.assert_awaited_once_with("el => el.style.display = 'block'")
        cover_input.set_input_files.assert_awaited_once_with('/cover.png')
        use_btn.click.assert_awaited_once()

    def test_replace_button_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '[role="button"]:has-text("上传横版封面")').first.count = AsyncMock(return_value=0)
        replace_btn = _loc(page, '[role="button"]:has-text("替换")').first
        replace_btn.count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.ReactModal__Content').first
        modal.locator('input#uploadCoverBtn')
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._upload_cover(page, '/cover.png'))
        replace_btn.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        replace_btn.click.assert_awaited_once()
        modal.wait_for.assert_awaited_once()

    def test_no_upload_entry_warns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._upload_cover(page, '/cover.png'))
        assert any('not found' in str(c) for c in logger.warning.call_args_list)

    def test_use_button_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        upload_area = _loc(page, '[role="button"]:has-text("上传横版封面")').first
        upload_area.count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.ReactModal__Content').first
        modal.locator('input#uploadCoverBtn')
        modal.locator('button[dt-mpid="上传封面确定"]').first.count = AsyncMock(return_value=0)
        fallback = modal.locator('button:has-text("使用")').first
        fallback.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._upload_cover(page, '/cover.png'))
        fallback.click.assert_awaited_once()

    def test_no_use_button_warns(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '[role="button"]:has-text("上传横版封面")').first.count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.ReactModal__Content').first
        modal.locator('input#uploadCoverBtn')
        modal.locator('button[dt-mpid="上传封面确定"]').first.count = AsyncMock(return_value=0)
        modal.locator('button:has-text("使用")').first.count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._upload_cover(page, '/cover.png'))
        assert any("'使用' button not found" in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '[role="button"]:has-text("上传横版封面")').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._upload_cover(page, '/cover.png'))  # 不抛异常
        assert logger.warning.called


class TestUploadExtraLandscapeCover:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        base = _loc(page, '[role="button"]:has-text("上传横版封面")')
        extra_btn = _mk_filtered(base, has_text='选填').first
        extra_btn.count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.ReactModal__Content').first
        cover_input = modal.locator('input#uploadCoverBtn')
        use_btn = _loc(page, 'button[dt-mpid="上传封面确定"]').first
        use_btn.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._upload_extra_landscape_cover(page, '/l.png'))
        extra_btn.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        extra_btn.click.assert_awaited_once()
        cover_input.wait_for.assert_awaited_once_with(state='attached', timeout=10000)
        cover_input.set_input_files.assert_awaited_once_with('/l.png')
        use_btn.click.assert_awaited_once()

    def test_entry_missing_skips(self):
        p = _mk_platform()
        page = _mk_page()
        _mk_filtered(_loc(page, '[role="button"]:has-text("上传横版封面")'), has_text='选填')
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._upload_extra_landscape_cover(page, '/l.png'))
        assert any('未找到选填横版封面入口' in str(c) for c in logger.warning.call_args_list)

    def test_use_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        _mk_filtered(_loc(page, '[role="button"]:has-text("上传横版封面")'),
                     has_text='选填').first.count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.ReactModal__Content').first
        modal.locator('input#uploadCoverBtn')
        _loc(page, 'button[dt-mpid="上传封面确定"]').first.count = AsyncMock(return_value=0)
        fallback = _loc(page, 'button:has-text("使用")').first
        fallback.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._upload_extra_landscape_cover(page, '/l.png'))
        fallback.click.assert_awaited_once()

    def test_no_use_button_warns(self):
        p = _mk_platform()
        page = _mk_page()
        _mk_filtered(_loc(page, '[role="button"]:has-text("上传横版封面")'),
                     has_text='选填').first.count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.ReactModal__Content').first
        modal.locator('input#uploadCoverBtn')
        _loc(page, 'button[dt-mpid="上传封面确定"]').first.count = AsyncMock(return_value=0)
        _loc(page, 'button:has-text("使用")').first.count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._upload_extra_landscape_cover(page, '/l.png'))
        assert any('使用' in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _mk_filtered(_loc(page, '[role="button"]:has-text("上传横版封面")'),
                     has_text='选填').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._upload_extra_landscape_cover(page, '/l.png'))  # 不抛异常
        assert logger.warning.called


class TestUploadExtraPortraitCover:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        _mk_filtered(_loc(page, '[role="button"]:has-text("上传竖版封面")'),
                     has_text='选填').first.count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.ReactModal__Content').first
        cover_input = modal.locator('input#uploadCoverBtn')
        use_btn = _loc(page, 'button[dt-mpid="上传封面确定"]').first
        use_btn.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._upload_extra_portrait_cover(page, '/p.png'))
        cover_input.set_input_files.assert_awaited_once_with('/p.png')
        use_btn.click.assert_awaited_once()

    def test_entry_missing_skips(self):
        p = _mk_platform()
        page = _mk_page()
        _mk_filtered(_loc(page, '[role="button"]:has-text("上传竖版封面")'), has_text='选填')
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._upload_extra_portrait_cover(page, '/p.png'))
        assert any('未找到选填竖版封面入口' in str(c) for c in logger.warning.call_args_list)

    def test_use_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        _mk_filtered(_loc(page, '[role="button"]:has-text("上传竖版封面")'),
                     has_text='选填').first.count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.ReactModal__Content').first
        modal.locator('input#uploadCoverBtn')
        _loc(page, 'button[dt-mpid="上传封面确定"]').first.count = AsyncMock(return_value=0)
        fallback = _loc(page, 'button:has-text("使用")').first
        fallback.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._upload_extra_portrait_cover(page, '/p.png'))
        fallback.click.assert_awaited_once()

    def test_no_use_button_warns(self):
        p = _mk_platform()
        page = _mk_page()
        _mk_filtered(_loc(page, '[role="button"]:has-text("上传竖版封面")'),
                     has_text='选填').first.count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.ReactModal__Content').first
        modal.locator('input#uploadCoverBtn')
        _loc(page, 'button[dt-mpid="上传封面确定"]').first.count = AsyncMock(return_value=0)
        _loc(page, 'button:has-text("使用")').first.count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._upload_extra_portrait_cover(page, '/p.png'))
        assert any('使用' in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _mk_filtered(_loc(page, '[role="button"]:has-text("上传竖版封面")'),
                     has_text='选填').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._upload_extra_portrait_cover(page, '/p.png'))  # 不抛异常
        assert logger.warning.called


# ── DOM 辅助: 创作声明 / 定时发布 ─────────────────────────────────────────

class TestSetCreationDeclarations:
    def test_happy_checks_boxes(self):
        p = _mk_platform()
        page = _mk_page()
        decl = CREATION_DECLARATIONS[0]
        checkbox = _loc(page, f'label[class*="checkboxItem"]:has-text("{decl}")').first
        checkbox.count = AsyncMock(return_value=1)
        checkbox.locator('input[type="checkbox"]').is_checked = AsyncMock(return_value=False)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._set_creation_declarations(page, [decl]))
        checkbox.wait_for.assert_awaited_once_with(state='visible', timeout=5000)
        checkbox.click.assert_awaited_once()

    def test_already_checked_skips(self):
        p = _mk_platform()
        page = _mk_page()
        decl = CREATION_DECLARATIONS[0]
        checkbox = _loc(page, f'label[class*="checkboxItem"]:has-text("{decl}")').first
        checkbox.count = AsyncMock(return_value=1)
        checkbox.locator('input[type="checkbox"]').is_checked = AsyncMock(return_value=True)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._set_creation_declarations(page, [decl]))
        checkbox.click.assert_not_awaited()
        assert any('already checked' in str(c) for c in logger.info.call_args_list)

    def test_unknown_declaration_skips(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._set_creation_declarations(page, ['不存在的声明']))
        assert any('Unknown declaration' in str(c) for c in logger.warning.call_args_list)

    def test_checkbox_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._set_creation_declarations(page, [CREATION_DECLARATIONS[0]]))
        assert any('not found' in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        decl = CREATION_DECLARATIONS[0]
        _loc(page, f'label[class*="checkboxItem"]:has-text("{decl}")').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._set_creation_declarations(page, [decl]))  # 不抛异常
        assert logger.warning.called


class TestSetScheduleTime:
    PD = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))

    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        switch = _loc(page, 'button[role="switch"]').first
        switch.count = AsyncMock(return_value=1)
        switch.get_attribute = AsyncMock(return_value='false')
        trigger = _loc(page, 'div[class*="dateTimeSelect"]').first
        trigger.count = AsyncMock(return_value=1)
        popup = _loc(page, 'div[class*="popupWrap"]').first
        popup.count = AsyncMock(return_value=1)
        date_item = popup.locator('div[class*="itemWrap"]:has-text("2026-08-22")').first
        date_item.count = AsyncMock(return_value=1)
        hour_item = popup.locator('div[class*="itemWrap"]:has-text("10时")').first
        hour_item.count = AsyncMock(return_value=1)
        minute_item = popup.locator('div[class*="itemWrap"]:has-text("5分")').first
        minute_item.count = AsyncMock(return_value=1)
        confirm = popup.locator('button:has-text("确定")').first
        confirm.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._set_schedule_time(page, self.PD))
        switch.click.assert_awaited_once()
        trigger.click.assert_awaited_once()
        date_item.click.assert_awaited_once()
        hour_item.click.assert_awaited_once()
        minute_item.click.assert_awaited_once()
        confirm.click.assert_awaited_once()

    def test_switch_already_enabled(self):
        p = _mk_platform()
        page = _mk_page()
        switch = _loc(page, 'button[role="switch"]').first
        switch.count = AsyncMock(return_value=1)
        switch.get_attribute = AsyncMock(return_value='true')
        _loc(page, 'div[class*="dateTimeSelect"]').first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._set_schedule_time(page, self.PD))
        switch.click.assert_not_awaited()

    def test_switch_missing_still_opens_picker(self):
        p = _mk_platform()
        page = _mk_page()
        trigger = _loc(page, 'div[class*="dateTimeSelect"]').first
        trigger.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._set_schedule_time(page, self.PD))
        trigger.click.assert_awaited_once()

    def test_trigger_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._set_schedule_time(page, self.PD))
        assert any('Datetime trigger not found' in str(c) for c in logger.warning.call_args_list)

    def test_popup_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, 'div[class*="dateTimeSelect"]').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._set_schedule_time(page, self.PD))
        assert any('Datetime popup not found' in str(c) for c in logger.warning.call_args_list)

    def test_missing_items_skip_clicks(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, 'div[class*="dateTimeSelect"]').first.count = AsyncMock(return_value=1)
        popup = _loc(page, 'div[class*="popupWrap"]').first
        popup.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._set_schedule_time(page, self.PD))
        # 无任何 item 时:仅弹窗打开,不点击任何 item/确定
        popup.locator('div[class*="itemWrap"]:has-text("2026-08-22")')
        assert not popup.subs['div[class*="itemWrap"]:has-text("2026-08-22")'].first.click.called

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, 'button[role="switch"]').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._set_schedule_time(page, self.PD))  # 不抛异常
        assert logger.warning.called


# ── DOM 辅助: 发布按钮 ─────────────────────────────────────────────────────

class TestClickPublish:
    BTN = 'button[dt-mpid="video_submit_click"]'
    TXT = 'text=提交成功, text=发布成功, text=投稿成功'

    def test_success_text_detected(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, self.BTN).first.count = AsyncMock(return_value=1)
        success_text = _loc(page, self.TXT).first
        success_text.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._click_publish(page))
        btn = _loc(page, self.BTN).first
        btn.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        btn.click.assert_awaited_once()
        assert any('success text detected' in str(c) for c in logger.info.call_args_list)

    def test_url_redirect_success(self):
        p = _mk_platform()
        page = _mk_page(url='https://mp.v.qq.com/content/list')
        _loc(page, self.BTN).first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._click_publish(page))
        _loc(page, self.BTN).first.click.assert_awaited_once()
        assert 'publishVideo' not in page.url

    def test_disabled_button_waits_for_enable(self):
        p = _mk_platform()
        page = _mk_page(url='https://mp.v.qq.com/content')
        btn = _loc(page, self.BTN).first
        btn.count = AsyncMock(return_value=1)
        btn.get_attribute = AsyncMock(return_value='disabled')
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._click_publish(page))
        page.wait_for_function.assert_awaited_once()
        btn.click.assert_awaited_once()

    def test_retry_click_after_5s(self):
        """前 6 次文本探测异常 + URL 未跳转 → i==5 时按钮可用则重试点击 → 第 7 次成功。"""
        p = _mk_platform()
        page = _mk_page()
        btn = _loc(page, self.BTN).first
        btn.count = AsyncMock(return_value=1)
        btn.is_enabled = AsyncMock(return_value=True)
        success_text = _loc(page, self.TXT).first
        success_text.count = AsyncMock(side_effect=[RuntimeError('probe')] * 6 + [1])
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.tencent_video.platform.logger', logger):
            _run(p._click_publish(page))
        assert btn.click.await_count == 2  # 初次 + i==5 重试
        assert any('retrying click' in str(c) for c in logger.info.call_args_list)

    def test_retry_block_exception_ignored(self):
        p = _mk_platform()
        page = _mk_page()
        btn = _loc(page, self.BTN).first
        btn.count = AsyncMock(return_value=1)
        btn.is_enabled = AsyncMock(side_effect=RuntimeError('stale'))
        success_text = _loc(page, self.TXT).first
        success_text.count = AsyncMock(side_effect=[RuntimeError('probe')] * 7 + [1])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._click_publish(page))
        assert btn.click.await_count == 1  # 重试块异常被吞,不重复点击

    def test_url_probe_exception_continues(self):
        """URL 探测抛异常 → 走文本探测兜底 → 成功。"""
        p = _mk_platform()

        class _RaisingURL:
            def __contains__(self, item):
                raise RuntimeError('nav fail')

        page = _mk_page()
        page.url = _RaisingURL()
        _loc(page, self.BTN).first.count = AsyncMock(return_value=1)
        success_text = _loc(page, self.TXT).first
        success_text.count = AsyncMock(side_effect=[RuntimeError('probe'), 1])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._click_publish(page))  # 不抛异常

    def test_no_success_raises_after_60s(self):
        """60 次轮询无成功信号 → raise 发布失败。"""
        p = _mk_platform()
        page = _mk_page()
        _loc(page, self.BTN).first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'), \
             pytest.raises(Exception, match='发布失败'):
            _run(p._click_publish(page))

    def test_text_probe_exception_continues(self):
        """文本探测抛异常 → 走 URL 跳转判定(已跳转 → 成功)。"""
        p = _mk_platform()
        page = _mk_page(url='https://mp.v.qq.com/content')
        _loc(page, self.BTN).first.count = AsyncMock(return_value=1)
        _loc(page, self.TXT).first.count = AsyncMock(side_effect=RuntimeError('probe'))
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tencent_video.platform.logger'):
            _run(p._click_publish(page))  # 不抛异常
