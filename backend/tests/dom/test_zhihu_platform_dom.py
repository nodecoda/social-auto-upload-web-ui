"""知乎 platform.py DOM 交互层契约测试（T35 第十一期）。

覆盖 impl/zhihu/platform.py (813 stmts, 基线 15%):
- 纯函数: _parse_cookie_to_storage_state / _extract_year / _extract_month /
  _get_video_orientation(素材表 id 查询/stored_path 兜底/异常兜底)
- 登录/校验/同步: login(头像 wait_for/超时保留浏览器/close 异常吞掉/
  create_browser/context 异常传播) / check_cookie(有效/失效/load_state 异常兜底)
  / sync_profile(name/avatar+stats/抓取异常兜底/外层异常兜底) /
  _scrape_zhihu_stats(两阶段/累计按钮/未匹配 label/去重排序/_parse_int 分支) /
  _login_stats_fn / open_creator_center(真实线程+事件断言)
- 编排: publish_video(RAW 参数截断分支) / _upload_single_video 全流程
  (定向封面/类别/定时/发布成功失败/截图异常/cookie 回写/dry_run 保留浏览器/
  cookie 失效 raise/步骤异常不写 cookie/资源清理异常吞掉)
- DOM 辅助: _upload_video_file(iframe→video input→任意 input→上传按钮四策略/
  全失败 RuntimeError) / _wait_upload_complete(成功/上传失败 raise/轮询异常
  继续/进度日志) / _set_thumbnail(封面文件缺失早退/file_chooser/Modal input
  兜底/排除编辑区/预览轮询/确认按钮多策略/弹窗关闭/Escape 兜底/外层异常吞掉)
  / _fill_title(空标题早退/50 截断) / _fill_desc_and_tags(2000 截断/标签解析
  切分/剪贴板粘贴回退 type/非字符串标签跳过) / _set_video_mark(默认项跳过选项/
  非默认点选项/异常 Escape) / _ensure_original_checked(已勾选/未勾选点击开关/
  异常吞掉) / _set_category(force 重试/异常 Escape) / _set_schedule_time
  (int 0/非 0/空值早退/开关状态探测/日历年/月导航/日期匹配/时/分下拉兜底/
  异常吞掉) / _click_submit(成功 code=0/失败 raise/响应超时/解析失败/点击失败/
  dry-run) / _dump_form_state(表单状态日志/抓取失败)
"""
import asyncio
import sys
import time as _time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from impl.zhihu.platform import (
    ZHIHU_CREATOR_URL,
    ZHIHU_LOGIN_URL,
    ZHIHU_UPLOAD_URL,
    ZhihuPlatform,
    _extract_month,
    _extract_year,
    _get_video_orientation,
    scrape_zhihu_profile,
)


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return ZhihuPlatform()


def _mk_leaf():
    loc = MagicMock()
    loc.count = AsyncMock(return_value=0)
    loc.click = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.set_input_files = AsyncMock()
    loc.is_visible = AsyncMock(return_value=True)
    loc.is_checked = AsyncMock(return_value=False)
    loc.text_content = AsyncMock(return_value='')
    loc.inner_text = AsyncMock(return_value='')
    loc.fill = AsyncMock()
    loc.press = AsyncMock()
    loc.press_sequentially = AsyncMock()
    loc.evaluate = AsyncMock(return_value='')
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


def _mk_frame(hit=False):
    """iframe 上传区 fake: hit=True 时 first.wait_for 成功,否则抛异常。"""
    frame = MagicMock()
    inp = _mk_locator()
    if hit:
        inp.first.wait_for = AsyncMock()
    else:
        inp.first.wait_for = AsyncMock(side_effect=RuntimeError('no frame input'))
    frame.locator = MagicMock(return_value=inp)
    return frame


def _mk_page(url=ZHIHU_UPLOAD_URL):
    page = MagicMock()
    page.url = url
    page.main_frame = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_event = AsyncMock()
    page.evaluate = AsyncMock(return_value=[])
    page.screenshot = AsyncMock()
    page.close = AsyncMock()
    page.expect_file_chooser = MagicMock()
    page.expect_response = MagicMock()
    page.get_by_text = MagicMock(return_value=_mk_locator())
    page.frame_locator = MagicMock(return_value=_mk_frame())
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


@contextmanager
def _no_sleep():
    with patch('asyncio.sleep', AsyncMock()):
        yield


async def _immediate(value):
    return value


class _FakeCM:
    """async 上下文管理器:__aenter__ 返回自身,value 属性可 await。

    用于 page.expect_response / page.expect_file_chooser。
    """

    def __init__(self, value=None, enter_error=None):
        self._value = value
        self._enter_error = enter_error

    async def __aenter__(self):
        if self._enter_error is not None:
            raise self._enter_error
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def value(self):
        return _immediate(self._value)


def _mk_response(data):
    resp = MagicMock()
    resp.json = AsyncMock(return_value=data)
    return resp


# ── 纯函数: cookie 解析 / 日历解析 / 素材方向 ──────────────────────────────

class TestParseCookieToStorageState:
    def test_happy_parse(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('z_c0=abc; d_c0=123; x=1')
        assert len(cookies) == 3
        assert origins == []
        c0 = cookies[0]
        assert c0['name'] == 'z_c0'
        assert c0['value'] == 'abc'
        assert c0['domain'] == '.zhihu.com'
        assert c0['path'] == '/'
        assert c0['httpOnly'] is True
        assert c0['secure'] is False
        assert c0['sameSite'] == 'Lax'

    def test_skips_invalid_pairs(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('a=1; ; novalue; b=2')
        assert [c['name'] for c in cookies] == ['a', 'b']

    def test_empty_string(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('')
        assert cookies == []
        assert origins == []

    def test_expires_is_future(self):
        p = _mk_platform()
        import time as _t
        cookies, _ = p._parse_cookie_to_storage_state('k=v')
        assert cookies[0]['expires'] > _t.time()


class TestExtractYear:
    def test_with_year(self):
        assert _extract_year('2026年8月') == '2026'

    def test_no_match(self):
        assert _extract_year('八月') == '0'
        assert _extract_year('') == '0'


class TestExtractMonth:
    def test_with_month(self):
        assert _extract_month('2026年8月') == '8'
        assert _extract_month('2026年12月') == '12'

    def test_year_only_fallback(self):
        assert _extract_month('2026年8') == '8'

    def test_no_match(self):
        assert _extract_month('abc') == '0'


class TestGetVideoOrientation:
    def _mk_conn(self, rows):
        """rows: [fetchone 返回值序列];conn 支持 with 协议。"""
        conn = MagicMock()
        conn.row_factory = None
        results = [MagicMock() for _ in rows]
        for r, v in zip(results, rows, strict=False):
            r.fetchone.return_value = v
        conn.execute = MagicMock(side_effect=lambda sql, *a: results.pop(0))
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        return conn

    def test_by_material_id(self):
        with patch('sqlite3.connect') as connect:
            connect.return_value = self._mk_conn([{'orientation': 'vertical'}])
            assert _get_video_orientation('/m/550e8400-e29b-41d4-a716-446655440000.mp4') == 'vertical'

    def test_id_row_empty_returns_empty(self):
        """id 命中但 orientation 为空串 → 直接返回 ''（不进 stored_path 兜底）。"""
        with patch('sqlite3.connect') as connect:
            connect.return_value = self._mk_conn([{'orientation': ''}])
            path = '/m/550e8400-e29b-41d4-a716-446655440000.mp4'
            assert _get_video_orientation(path) == ''

    def test_id_miss_falls_back_to_stored_path(self):
        with patch('sqlite3.connect') as connect:
            connect.return_value = self._mk_conn([None, {'orientation': 'square'}])
            path = '/m/550e8400-e29b-41d4-a716-446655440000.mp4'
            assert _get_video_orientation(path) == 'square'

    def test_no_uuid_uses_stored_path(self):
        with patch('sqlite3.connect') as connect:
            connect.return_value = self._mk_conn([{'orientation': 'vertical'}])
            assert _get_video_orientation('/m/video.mp4') == 'vertical'

    def test_no_row_found_returns_empty(self):
        with patch('sqlite3.connect') as connect:
            connect.return_value = self._mk_conn([None, None])
            path = '/m/550e8400-e29b-41d4-a716-446655440000.mp4'
            assert _get_video_orientation(path) == ''

    def test_exception_returns_empty(self):
        logger = MagicMock()
        with patch('sqlite3.connect', side_effect=RuntimeError('db down')), \
             patch('impl.zhihu.platform.logger', logger):
            assert _get_video_orientation('/m/v.mp4') == ''
        assert any('查询视频方向失败' in str(c) for c in logger.info.call_args_list)


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLogin:
    def test_success(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch('impl.zhihu.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.zhihu.platform.logger'):
            _run(p.login('u1', MagicMock(), account_id='acc1'))
        page.goto.assert_awaited_once_with(ZHIHU_LOGIN_URL)
        _loc(page, '.AppHeader-profileEntry').first.wait_for.assert_awaited_once_with(
            timeout=999999999
        )
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 14
        assert kwargs['platform_name'] == '知乎'
        assert kwargs['account_id'] == 'acc1'
        assert kwargs['scrape_fn'] is scrape_zhihu_profile
        assert kwargs['stats_fn'].__func__ is ZhihuPlatform._login_stats_fn
        page.close.assert_awaited_once()
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()  # 成功才关

    def test_wait_timeout_keeps_browser(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch('impl.zhihu.platform.logger'):
            _loc(page, '.AppHeader-profileEntry').first.wait_for = AsyncMock(
                side_effect=TimeoutError('user aborted')
            )
            with pytest.raises(TimeoutError):
                _run(p.login('u1', MagicMock()))
        page.close.assert_awaited_once()
        context.close.assert_awaited_once()
        browser.close.assert_not_awaited()  # 失败保留浏览器看现场

    def test_page_close_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.zhihu.platform.save_login_result', AsyncMock()), \
             patch('impl.zhihu.platform.logger'):
            page.close = AsyncMock(side_effect=RuntimeError('boom'))
            _run(p.login('u1', MagicMock()))  # 不抛异常
            browser.close.assert_awaited_once()

    def test_context_close_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, context, browser, _cb, _cc), \
             patch('impl.zhihu.platform.save_login_result', AsyncMock()), \
             patch('impl.zhihu.platform.logger'):
            context.close = AsyncMock(side_effect=RuntimeError('boom'))
            _run(p.login('u1', MagicMock()))
            browser.close.assert_awaited_once()

    def test_create_context_failure_propagates(self):
        """create_browser 在 try 外;create_context 异常走外层 finally,不关浏览器。"""
        p = _mk_platform()
        browser = MagicMock()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context',
                          AsyncMock(side_effect=RuntimeError('ctx boom'))), \
             patch('impl.zhihu.platform.logger'), pytest.raises(RuntimeError, match='ctx boom'):
            _run(p.login('u1', MagicMock()))
        browser.close.assert_not_called()

    def test_create_browser_failure_propagates(self):
        p = _mk_platform()
        with patch.object(p, 'create_browser',
                          AsyncMock(side_effect=RuntimeError('browser boom'))), \
             pytest.raises(RuntimeError, match='browser boom'):
            _run(p.login('u1', MagicMock()))


class TestCheckCookie:
    def test_valid(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.zhihu.platform.logger'), _no_sleep():
            _loc(page, '.AppHeader-profileEntry').first.count = AsyncMock(return_value=1)
            assert _run(p.check_cookie('ck.json')) is True
        page.goto.assert_awaited_once_with(ZHIHU_LOGIN_URL)
        page.wait_for_load_state.assert_awaited_once_with('domcontentloaded', timeout=10000)
        browser.close.assert_awaited_once()

    def test_invalid(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, browser, _cb, _cc), \
             patch('impl.zhihu.platform.logger'), _no_sleep():
            assert _run(p.check_cookie('ck.json')) is False
        browser.close.assert_awaited_once()

    def test_load_state_error_falls_through(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.zhihu.platform.logger'), _no_sleep():
            page.wait_for_load_state = AsyncMock(side_effect=TimeoutError('slow'))
            _loc(page, '.AppHeader-profileEntry').first.count = AsyncMock(return_value=1)
            assert _run(p.check_cookie('ck.json')) is True
        browser.close.assert_awaited_once()


class TestSyncProfile:
    STATS: ClassVar[list[dict]] = [{'ICON': 'user', 'COUNT': 9, 'NAME': '关注者', 'SORT': 1}]

    def test_happy(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.zhihu.platform.scrape_zhihu_profile',
                   AsyncMock(return_value=('昵称', 'http://a.png'))) as sp, \
             patch.object(p, '_scrape_zhihu_stats', AsyncMock(return_value=self.STATS)) as sst, \
             patch('impl.zhihu.platform.logger'):
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '昵称', 'avatar': 'http://a.png', 'stats': self.STATS}
        page.goto.assert_awaited_once_with(
            ZHIHU_LOGIN_URL, wait_until='domcontentloaded', timeout=30000
        )
        sp.assert_awaited_once_with(page)
        sst.assert_awaited_once_with(page)
        browser.close.assert_awaited_once()

    def test_profile_scrape_error_falls_back(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             patch('impl.zhihu.platform.scrape_zhihu_profile',
                   AsyncMock(side_effect=RuntimeError('scrape boom'))) as sp, \
             patch.object(p, '_scrape_zhihu_stats', AsyncMock(return_value=self.STATS)) as sst, \
             patch('impl.zhihu.platform.logger'):
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': self.STATS}
        sp.assert_awaited_once()
        sst.assert_awaited_once()

    def test_stats_error_returns_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             patch('impl.zhihu.platform.scrape_zhihu_profile',
                   AsyncMock(return_value=('n', ''))), \
             patch.object(p, '_scrape_zhihu_stats',
                          AsyncMock(side_effect=RuntimeError('stats boom'))), \
             patch('impl.zhihu.platform.logger'):
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': 'n', 'avatar': '', 'stats': []}

    def test_goto_error_falls_back_empty_profile(self):
        """goto 与 scrape 在同一 try:goto 抛异常 → name/avatar 兜底为空。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.zhihu.platform.scrape_zhihu_profile',
                   AsyncMock(return_value=('n', ''))) as sp, \
             patch.object(p, '_scrape_zhihu_stats', AsyncMock(return_value=self.STATS)) as sst, \
             patch('impl.zhihu.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': self.STATS}
        sp.assert_not_awaited()
        sst.assert_awaited_once()

    def test_outer_exception_returns_empty(self):
        """内层 except 的 logger 抛异常 → 外层 except 兜底返回空 profile。"""
        p = _mk_platform()
        logger = MagicMock()

        def _boom(*args, **kwargs):
            if args and args[0].startswith('[zhihu] 抓 name/avatar 失败'):
                raise RuntimeError('logger boom')

        logger.info = MagicMock(side_effect=_boom)
        with _mk_browser_chain(p) as (_page, _context, browser, _cb, _cc), \
             patch('impl.zhihu.platform.scrape_zhihu_profile',
                   AsyncMock(side_effect=RuntimeError('scrape fail'))), \
             patch('impl.zhihu.platform.logger', logger):
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': []}
        browser.close.assert_awaited_once()


# ── stats 抓取 / 登录 stats 入口 / 创作中心 ────────────────────────────────

class TestScrapeZhihuStats:
    def test_happy_two_stages(self):
        p = _mk_platform()
        page = _mk_page()
        stage1 = [
            {'label': '关注者总数', 'value': '1,234'},
            {'label': '昨日关注者变化', 'value': '5'},
            {'label': '转发总数', 'value': None},
            {'label': '播放总量', 'value': '12.5'},
        ]
        stage2 = [
            {'label': '阅读总量', 'value': '100'},
            {'label': '赞同总量', 'value': '0.0%'},
            {'label': '喜欢总量', 'value': 'x'},
            {'label': '创作周报', 'value': '1'},
        ]
        page.evaluate = AsyncMock(side_effect=[stage1, stage2])
        _loc(page, 'button:has-text("累计")').first.count = AsyncMock(return_value=1)
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            stats = _run(p._scrape_zhihu_stats(page))
        assert stats == [
            {'ICON': 'user', 'COUNT': 1234, 'NAME': '关注者', 'SORT': 1},
            {'ICON': 'like', 'COUNT': 0, 'NAME': '赞同', 'SORT': 2},
            {'ICON': 'play', 'COUNT': 100, 'NAME': '阅读', 'SORT': 3},
            {'ICON': 'star', 'COUNT': 0, 'NAME': '喜欢', 'SORT': 4},
            {'ICON': 'share', 'COUNT': 0, 'NAME': '转发', 'SORT': 8},
            {'ICON': 'play', 'COUNT': 12, 'NAME': '播放', 'SORT': 9},
        ]
        page.goto.assert_awaited()
        _loc(page, 'button:has-text("累计")').first.click.assert_awaited_once_with(timeout=3000)

    def test_accumulate_btn_missing_skips_click(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[[], []])
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            assert _run(p._scrape_zhihu_stats(page)) == []
        _loc(page, 'button:has-text("累计")').click.assert_not_awaited()

    def test_accumulate_click_error_continues(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[[], []])
        _loc(page, 'button:has-text("累计")').first.count = AsyncMock(return_value=1)
        _loc(page, 'button:has-text("累计")').first.click = AsyncMock(
            side_effect=RuntimeError('click boom')
        )
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            assert _run(p._scrape_zhihu_stats(page)) == []
        assert any('累计按钮点击失败' in str(c) for c in logger.info.call_args_list)

    def test_stage1_wait_timeout_logged(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=[TimeoutError('slow'), None])
        page.evaluate = AsyncMock(side_effect=[[{'label': '关注者总数', 'value': '1'}], []])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            stats = _run(p._scrape_zhihu_stats(page))
        assert any('阶段1 等待数据超时' in str(c) for c in logger.info.call_args_list)
        assert stats[0]['COUNT'] == 1

    def test_stage1_evaluate_error_stage2_empty(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[RuntimeError('eval boom'), []])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            assert _run(p._scrape_zhihu_stats(page)) == []
        assert any('阶段1(数据总览)抓取失败' in str(c) for c in logger.info.call_args_list)
        assert any('阶段2 raw 数据为空' in str(c) for c in logger.info.call_args_list)

    def test_stage2_wait_timeout_logged(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=[None, TimeoutError('slow')])
        page.evaluate = AsyncMock(side_effect=[[], []])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            assert _run(p._scrape_zhihu_stats(page)) == []
        assert any('阶段2 等待 .StatisticCard 超时' in str(c) for c in logger.info.call_args_list)

    def test_stage2_evaluate_error(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[[{'label': '关注者总数', 'value': '1'}], RuntimeError('boom')])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            stats = _run(p._scrape_zhihu_stats(page))
        assert stats[0]['COUNT'] == 1
        assert any('阶段2(作品分析)抓取失败' in str(c) for c in logger.info.call_args_list)

    def test_stage1_goto_error_stage2_still_runs(self):
        p = _mk_platform()
        page = _mk_page()
        page.goto = AsyncMock(side_effect=[RuntimeError('nav boom'), None])
        # 阶段1 goto 抛异常,evaluate 不会执行;唯一 evaluate 调用在阶段2
        page.evaluate = AsyncMock(return_value=[{'label': '阅读总量', 'value': '7'}])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            stats = _run(p._scrape_zhihu_stats(page))
        assert any('阶段1(数据总览)抓取失败' in str(c) for c in logger.info.call_args_list)
        assert stats == [{'ICON': 'play', 'COUNT': 7, 'NAME': '阅读', 'SORT': 3}]

    def test_stage2_goto_error_returns_stage1(self):
        p = _mk_platform()
        page = _mk_page()
        page.goto = AsyncMock(side_effect=[None, RuntimeError('nav boom')])
        page.evaluate = AsyncMock(side_effect=[[{'label': '关注者总数', 'value': '3'}], []])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            stats = _run(p._scrape_zhihu_stats(page))
        assert any('阶段2(作品分析)抓取失败' in str(c) for c in logger.info.call_args_list)
        assert stats == [{'ICON': 'user', 'COUNT': 3, 'NAME': '关注者', 'SORT': 1}]

    def test_dedup_keeps_first(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[
            [{'label': '关注者总数', 'value': '1'}],
            [{'label': '关注者总数', 'value': '999'}],
        ])
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            stats = _run(p._scrape_zhihu_stats(page))
        assert stats == [{'ICON': 'user', 'COUNT': 1, 'NAME': '关注者', 'SORT': 1}]

    def test_unmatched_labels_logged_both_stages(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[
            [{'label': '昨日关注者变化', 'value': '5'}],
            [{'label': '创作周报', 'value': '1'}],
        ])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            assert _run(p._scrape_zhihu_stats(page)) == []
        infos = [str(c) for c in logger.info.call_args_list]
        assert any('阶段1 未匹配 label' in s for s in infos)
        assert any('阶段2 未匹配 label' in s for s in infos)


class TestLoginStatsFn:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_zhihu_stats',
                          AsyncMock(return_value=[{'ICON': 'user', 'COUNT': 1, 'NAME': '关注者', 'SORT': 1}])) as sst, \
             patch('impl.zhihu.platform.logger'):
            stats = _run(p._login_stats_fn(page, 'acc1'))
        assert stats[0]['COUNT'] == 1
        sst.assert_awaited_once_with(page)

    def test_error_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch.object(p, '_scrape_zhihu_stats',
                          AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('impl.zhihu.platform.logger', logger):
            assert _run(p._login_stats_fn(page, 'acc1')) == []
        assert any('_login_stats_fn 抓取失败' in str(c) for c in logger.info.call_args_list)


class TestOpenCreatorCenter:
    def test_starts_thread(self):
        p = _mk_platform()
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        with patch('impl.zhihu.platform.create_browser_sync', return_value=browser) as cbs, \
             patch('impl.zhihu.platform.create_context_sync', return_value=context) as ccs, \
             patch('impl.zhihu.platform.logger'):
            _run(p.open_creator_center('ck.json'))
            for _ in range(200):
                if browser.close.called:
                    break
                _time.sleep(0.02)
        cbs.assert_called_once_with(headless=False)
        ccs.assert_called_once()
        page.goto.assert_called_once_with(ZHIHU_CREATOR_URL)
        page.wait_for_event.assert_called_once_with('close', timeout=0)
        browser.close.assert_called_once()

    def test_wait_event_error_swallowed(self):
        p = _mk_platform()
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        with patch('impl.zhihu.platform.create_browser_sync', return_value=browser), \
             patch('impl.zhihu.platform.create_context_sync', return_value=context), \
             patch('impl.zhihu.platform.logger'):
            _run(p.open_creator_center('ck.json'))
            for _ in range(200):
                if browser.close.called:
                    break
                _time.sleep(0.02)
        browser.close.assert_called_once()

    def test_browser_close_error_swallowed(self):
        p = _mk_platform()
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('boom'))
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        with patch('impl.zhihu.platform.create_browser_sync', return_value=browser), \
             patch('impl.zhihu.platform.create_context_sync', return_value=context), \
             patch('impl.zhihu.platform.logger'):
            _run(p.open_creator_center('ck.json'))
            for _ in range(200):
                if browser.close.called:
                    break
                _time.sleep(0.02)
        browser.close.assert_called_once()


# ── publish_video 编排(RAW 参数截断分支) ──────────────────────────────────

class TestPublishVideoRawLog:
    def test_long_value_truncated(self):
        p = _mk_platform()
        upload = AsyncMock()
        logger = MagicMock()
        with patch.object(p, '_upload_single_video', upload), \
             patch('impl.zhihu.platform.parse_schedule_time', MagicMock(return_value=0)), \
             patch('impl.zhihu.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.zhihu.platform.bind_account_name', MagicMock()), \
             patch('impl.zhihu.platform._get_video_orientation', return_value='horizontal'), \
             patch('impl.zhihu.platform.logger', logger):
            assert asyncio.run(p.publish_video(
                title='T', files=['/v.mp4'], account_file=['a.json'], desc='x' * 200
            )) is True
        raw = [c for c in logger.info.call_args_list
               if c.args and c.args[0] == '[发布参数 RAW] %s = %s']
        assert len(raw) == 4
        long_desc = [c.args[2] for c in raw if c.args[2].startswith("'x")]
        assert long_desc and long_desc[0].endswith('...')


# ── _upload_single_video 全流程 ────────────────────────────────────────────

@contextmanager
def _mk_upload_steps(p, submit_result=(True, '发布成功')):
    """把 _upload_single_video 内部子步骤替换为 AsyncMock。"""
    mocks = dict(
        upload_video_file=AsyncMock(),
        wait_upload_complete=AsyncMock(),
        set_thumbnail=AsyncMock(),
        fill_title=AsyncMock(),
        fill_desc_tags=AsyncMock(),
        set_video_mark=AsyncMock(),
        ensure_original=AsyncMock(),
        set_category=AsyncMock(),
        set_schedule=AsyncMock(),
        click_submit=AsyncMock(return_value=submit_result),
        close_browser=AsyncMock(),
    )
    with patch.object(p, '_upload_video_file', mocks['upload_video_file']), \
         patch.object(p, '_wait_upload_complete', mocks['wait_upload_complete']), \
         patch.object(p, '_set_thumbnail', mocks['set_thumbnail']), \
         patch.object(p, '_fill_title', mocks['fill_title']), \
         patch.object(p, '_fill_desc_and_tags', mocks['fill_desc_tags']), \
         patch.object(p, '_set_video_mark', mocks['set_video_mark']), \
         patch.object(p, '_ensure_original_checked', mocks['ensure_original']), \
         patch.object(p, '_set_category', mocks['set_category']), \
         patch.object(p, '_set_schedule_time', mocks['set_schedule']), \
         patch.object(p, '_click_submit', mocks['click_submit']), \
         patch.object(p, 'close_browser', mocks['close_browser']):
        yield mocks


def _run_upload(p, page, **kw):
    default = dict(
        title='标题', file_path='/m/v.mp4', tags=['a'], publish_date=0,
        account_file='/c/u1.json', category='', creation_declaration='内容无需标注',
        desc='', thumbnail_path=None,
    )
    default.update(kw)
    return _run(p._upload_single_video(**default))


class TestUploadSingleVideo:
    def test_happy_not_scheduled(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, _no_sleep(), \
             patch('impl.zhihu.platform.logger'):
            res = _run_upload(p, page, title='标题', file_path='/m/v.mp4')
        assert res is None
        page.goto.assert_awaited_once_with(ZHIHU_UPLOAD_URL)
        mocks['upload_video_file'].assert_awaited_once_with(page, '/m/v.mp4')
        mocks['wait_upload_complete'].assert_awaited_once_with(page)
        mocks['fill_title'].assert_awaited_once_with(page, '标题')
        mocks['fill_desc_tags'].assert_awaited_once_with(page, '', ['a'])
        mocks['set_video_mark'].assert_awaited_once_with(page, '内容无需标注')
        mocks['ensure_original'].assert_awaited_once_with(page)
        mocks['click_submit'].assert_awaited_once_with(page, False)
        # 无封面/类别/定时 → 相关步骤跳过
        mocks['set_thumbnail'].assert_not_awaited()
        mocks['set_category'].assert_not_awaited()
        mocks['set_schedule'].assert_not_awaited()
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_scheduled_thumbnail_category_submit_failed(self):
        pd = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        p = _mk_platform()
        logger = MagicMock()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_steps(p, submit_result=(False, '接口限流')) as mocks, \
             _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run_upload(
                p, page, publish_date=pd, thumbnail_path='/x.png', category='科技',
                creation_declaration='内容由AI生成', desc='简介', tags=['旅行'],
            )
        mocks['set_thumbnail'].assert_awaited_once_with(page, '/x.png')
        mocks['set_category'].assert_awaited_once_with(page, '科技')
        mocks['set_schedule'].assert_awaited_once_with(page, pd)
        # is_scheduled 表达式返回 datetime 本身(真值),非 bool
        mocks['click_submit'].assert_awaited_once_with(page, pd)
        assert any('✗ 发布失败' in str(c) for c in logger.info.call_args_list)

    def test_cookie_invalid_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, _no_sleep(), \
             patch('impl.zhihu.platform.logger'):
            page.url = 'https://www.zhihu.com/signin?next=/upload-video'
            with pytest.raises(RuntimeError, match='cookie 失效'):
                _run_upload(p, page)
        mocks['upload_video_file'].assert_not_awaited()
        context.storage_state.assert_not_awaited()  # 流程未跑完不写 cookie
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_step_error_no_cookie_write(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, _no_sleep(), \
             patch('impl.zhihu.platform.logger'):
            mocks['fill_title'].side_effect = RuntimeError('boom')
            with pytest.raises(RuntimeError, match='boom'):
                _run_upload(p, page)
        context.storage_state.assert_not_awaited()
        context.close.assert_awaited_once()

    def test_wait_load_state_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_steps(p), _no_sleep(), patch('impl.zhihu.platform.logger'):
            page.wait_for_load_state = AsyncMock(side_effect=TimeoutError('slow'))
            assert _run_upload(p, page) is None

    def test_screenshot_errors_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_steps(p), _no_sleep(), patch('impl.zhihu.platform.logger'):
            page.screenshot = AsyncMock(side_effect=RuntimeError('shot boom'))
            assert _run_upload(p, page) is None

    def test_storage_state_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             _mk_upload_steps(p), _no_sleep(), patch('impl.zhihu.platform.logger'):
            context.storage_state = AsyncMock(side_effect=RuntimeError('boom'))
            assert _run_upload(p, page) is None

    def test_context_close_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             _mk_upload_steps(p), _no_sleep(), patch('impl.zhihu.platform.logger'):
            context.close = AsyncMock(side_effect=RuntimeError('boom'))
            assert _run_upload(p, page) is None

    def test_close_browser_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, _no_sleep(), \
             patch('impl.zhihu.platform.logger'):
            mocks['close_browser'].side_effect = RuntimeError('boom')
            assert _run_upload(p, page) is None

    def test_submit_failed_screenshot_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_steps(p, submit_result=(False, '接口限流')), _no_sleep(), \
             patch('impl.zhihu.platform.logger'):
            page.screenshot = AsyncMock(side_effect=RuntimeError('shot boom'))
            assert _run_upload(p, page) is None  # 提交前/失败后截图异常都吞掉

    def test_dry_run_keeps_browser(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, _no_sleep(), \
             patch('impl.zhihu.platform.DEBUG_DRY_RUN_SUBMIT', True), \
             patch('impl.zhihu.platform.logger'):
            assert _run_upload(p, page) is None
        context.storage_state.assert_awaited_once()  # 流程跑完仍回写 cookie
        context.close.assert_not_awaited()
        mocks['close_browser'].assert_not_awaited()


# ── DOM 辅助: 上传视频文件 ─────────────────────────────────────────────────

class TestUploadVideoFile:
    @staticmethod
    def _run(page, file_path='/m/v.mp4'):
        return _run(ZhihuPlatform._upload_video_file(page, file_path))

    def test_iframe_hit(self):
        page = _mk_page()
        frame = _mk_frame(hit=True)
        page.frame_locator = MagicMock(return_value=frame)
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            self._run(page)
        frame.locator('input[type="file"]').first.set_input_files.assert_awaited_once_with('/m/v.mp4')
        # 主页面 input 未被使用
        _loc(page, 'input[type="file"]').first.set_input_files.assert_not_awaited()

    def test_main_video_input_hit(self):
        page = _mk_page()  # iframe 默认 miss
        candidate = _loc(
            page, 'input[type="file"][accept*="video"], input[type="file"][accept*="mp4"]'
        ).first
        candidate.wait_for = AsyncMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            self._run(page)
        candidate.set_input_files.assert_awaited_once_with('/m/v.mp4')

    def test_fallback_any_input(self):
        page = _mk_page()
        _loc(page, 'input[type="file"][accept*="video"], '
                  'input[type="file"][accept*="mp4"]').first.wait_for = AsyncMock(
            side_effect=RuntimeError('no video input')
        )
        fallback = _loc(page, 'input[type="file"]').first
        fallback.wait_for = AsyncMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            self._run(page)
        fallback.set_input_files.assert_awaited_once_with('/m/v.mp4')

    def test_upload_button_then_input(self):
        page = _mk_page()
        _loc(page, 'input[type="file"][accept*="video"], '
                  'input[type="file"][accept*="mp4"]').first.wait_for = AsyncMock(
            side_effect=RuntimeError('no video input')
        )
        # 策略 3 的 wait_for 抛异常,策略 4 点击按钮后同一 selector 命中
        _loc(page, 'input[type="file"]').first.wait_for = AsyncMock(
            side_effect=[RuntimeError('not attached'), None]
        )
        upload_btn = _loc(
            page, 'button:has-text("上传视频"), '
                  'div[role="button"]:has-text("上传"), '
                  '[class*="UploadDropzone"], [class*="upload-dropzone"], '
                  'div:has-text("选择文件"):not(:has(*)), '
                  'div:has-text("拖拽"):not(:has(*))'
        ).first
        upload_btn.wait_for = AsyncMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            self._run(page)
        upload_btn.click.assert_awaited_once()
        _loc(page, 'input[type="file"]').first.set_input_files.assert_awaited_once_with('/m/v.mp4')

    def test_all_strategies_fail_raises(self):
        page = _mk_page()
        _loc(page, 'input[type="file"][accept*="video"], '
                  'input[type="file"][accept*="mp4"]').first.wait_for = AsyncMock(
            side_effect=RuntimeError('no video input')
        )
        _loc(page, 'input[type="file"]').first.wait_for = AsyncMock(
            side_effect=RuntimeError('no file input')
        )
        _loc(
            page, 'button:has-text("上传视频"), '
                  'div[role="button"]:has-text("上传"), '
                  '[class*="UploadDropzone"], [class*="upload-dropzone"], '
                  'div:has-text("选择文件"):not(:has(*)), '
                  'div:has-text("拖拽"):not(:has(*))'
        ).first.wait_for = AsyncMock(side_effect=RuntimeError('no button'))
        logger = MagicMock()
        page.screenshot = AsyncMock(side_effect=RuntimeError('shot boom'))
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger), \
             pytest.raises(RuntimeError, match='未找到视频上传 input'):
            self._run(page)
        page.screenshot.assert_awaited()
        _loc(page, 'input[type="file"]').first.set_input_files.assert_not_awaited()
        assert any('上传按钮兜底失败' in str(c) for c in logger.info.call_args_list)

    def test_screenshot_before_error_swallowed(self):
        page = _mk_page()
        page.screenshot = AsyncMock(side_effect=RuntimeError('shot boom'))
        frame = _mk_frame(hit=True)
        page.frame_locator = MagicMock(return_value=frame)
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            self._run(page)  # 不抛异常
        frame.locator('input[type="file"]').first.set_input_files.assert_awaited_once()

    def test_evaluate_probe_error_swallowed(self):
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('eval boom'))
        frame = _mk_frame(hit=True)
        page.frame_locator = MagicMock(return_value=frame)
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        assert any('file input 探测失败' in str(c) for c in logger.info.call_args_list)


# ── DOM 辅助: 等待上传完成 ─────────────────────────────────────────────────

class TestWaitUploadComplete:
    @staticmethod
    def _run(page):
        return _run(ZhihuPlatform._wait_upload_complete(page))

    def test_success_first_try(self):
        page = _mk_page()
        _loc(page, 'text=上传成功').count = AsyncMock(return_value=1)
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        assert any('检测到「上传成功」' in str(c) for c in logger.info.call_args_list)

    def test_success_after_retries_with_progress_log(self):
        page = _mk_page()
        done = _loc(page, 'text=上传成功')
        done.count = AsyncMock(side_effect=[0] * 11 + [1])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        assert done.count.await_count == 12
        assert sum('上传中...' in str(c) for c in logger.info.call_args_list) >= 2

    def test_fail_text_raises(self):
        page = _mk_page()
        _loc(page, 'text=上传失败').count = AsyncMock(return_value=1)
        with _no_sleep(), patch('impl.zhihu.platform.logger'), \
             pytest.raises(RuntimeError, match='视频上传失败'):
            self._run(page)

    def test_poll_exception_continues(self):
        page = _mk_page()
        done = _loc(page, 'text=上传成功')
        done.count = AsyncMock(side_effect=[TimeoutError('stale'), 1])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        assert done.count.await_count == 2
        assert any('状态检查异常' in str(c) for c in logger.info.call_args_list)

    def test_done_visible_false_then_true(self):
        page = _mk_page()
        done = _loc(page, 'text=上传成功')
        done.count = AsyncMock(return_value=1)
        done.first.is_visible = AsyncMock(side_effect=[False, True])
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            self._run(page)  # 第二轮命中
        assert done.first.is_visible.await_count == 2


# ── DOM 辅助: 设置封面 ─────────────────────────────────────────────────────

class TestSetThumbnail:
    EDIT_BTN = '.VideoUploadForm-imageEditButton, [class*="VideoUploadForm-imageEditButton"]'
    DROPZONE = ('.Modal-content [class*="Dropzone"], .Modal-content [class*="dropzone"], '
                '.Modal-content [class*="upload"], [role="dialog"] [class*="Dropzone"], '
                '[role="dialog"] [class*="upload"]')
    REPL = '.Modal-content button:has-text("重新上传"), [role="dialog"] button:has-text("重新上传")'
    CONFIRM = ('.Modal-content button:has-text("确认选择"), '
               '[role="dialog"] button:has-text("确认选择"), '
               '.Modal-content button.Button--primary:has-text("确认"), '
               '[role="dialog"] button.Button--primary:has-text("确认"), '
               'button.Button--primary:has-text("确认选择")')
    MODAL_VISIBLE = '.Modal-content:visible, [role="dialog"]:visible'

    @staticmethod
    def _run(page, thumb='/cover.png'):
        return _run(ZhihuPlatform._set_thumbnail(page, thumb))

    def test_file_missing_returns_early(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('os.path.exists', return_value=False), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        _loc(page, self.EDIT_BTN).first.click.assert_not_awaited()
        assert any('封面文件不存在' in str(c) for c in logger.info.call_args_list)

    def test_happy_file_chooser(self):
        page = _mk_page()
        fc = MagicMock()
        fc.set_files = AsyncMock()
        page.expect_file_chooser = MagicMock(return_value=_FakeCM(value=fc))
        _loc(page, self.REPL).count = AsyncMock(return_value=1)
        _loc(page, self.MODAL_VISIBLE).count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page, '/cover.png')
        _loc(page, self.EDIT_BTN).first.click.assert_awaited_once()
        page.get_by_text('本地上传').first.click.assert_awaited_once()
        fc.set_files.assert_awaited_once_with('/cover.png')
        _loc(page, self.CONFIRM).first.click.assert_awaited_once()
        assert any('file_chooser 方式上传成功' in str(c) for c in logger.info.call_args_list)
        assert any('弹窗已关闭' in str(c) for c in logger.info.call_args_list)
        page.keyboard.press.assert_not_awaited()

    def test_file_chooser_fail_modal_input_fallback(self):
        page = _mk_page()
        page.expect_file_chooser = MagicMock(
            return_value=_FakeCM(enter_error=RuntimeError('no chooser'))
        )
        modal_input = _loc(
            page, '.Modal-content input[type="file"], [role="dialog"] input[type="file"]'
        ).first
        modal_input.wait_for = AsyncMock()
        _loc(page, self.REPL).count = AsyncMock(return_value=1)
        _loc(page, self.MODAL_VISIBLE).count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        modal_input.set_input_files.assert_awaited_once_with('/cover.png')
        assert any('Modal 内 input 命中' in str(c) for c in logger.info.call_args_list)
        

    def test_modal_input_fail_exclusion_raises_outer(self):
        page = _mk_page()
        page.expect_file_chooser = MagicMock(
            return_value=_FakeCM(enter_error=RuntimeError('no chooser'))
        )
        _loc(
            page, '.Modal-content input[type="file"], [role="dialog"] input[type="file"]'
        ).first.wait_for = AsyncMock(side_effect=RuntimeError('no modal input'))
        page.evaluate = AsyncMock(return_value=2)  # 排除编辑区后仍有 input → raise
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)  # 外层 except 吞掉
        assert any('排除法失败' in str(c) for c in logger.info.call_args_list)
        assert any('封面文件未能上传到弹窗' in str(c) for c in logger.info.call_args_list)
        assert any('设置封面失败' in str(c) for c in logger.info.call_args_list)
        page.keyboard.press.assert_awaited()  # 外层 Escape

    def test_exclusion_zero_keeps_going(self):
        page = _mk_page()
        page.expect_file_chooser = MagicMock(
            return_value=_FakeCM(enter_error=RuntimeError('no chooser'))
        )
        _loc(
            page, '.Modal-content input[type="file"], [role="dialog"] input[type="file"]'
        ).first.wait_for = AsyncMock(side_effect=RuntimeError('no modal input'))
        page.evaluate = AsyncMock(return_value=0)  # 无可用 image input,不 raise
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        assert any('封面文件未能上传到弹窗' in str(c) for c in logger.info.call_args_list)

    def test_preview_timeout_warns(self):
        page = _mk_page()
        fc = MagicMock()
        fc.set_files = AsyncMock()
        page.expect_file_chooser = MagicMock(return_value=_FakeCM(value=fc))
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)  # repl.count 默认 0 → 30 轮循环
        assert any('未检测到封面上传成功标志' in str(c) for c in logger.info.call_args_list)
        _loc(page, self.CONFIRM).first.click.assert_awaited_once()

    def test_repl_probe_error_swallowed(self):
        page = _mk_page()
        fc = MagicMock()
        fc.set_files = AsyncMock()
        page.expect_file_chooser = MagicMock(return_value=_FakeCM(value=fc))
        _loc(page, self.REPL).count = AsyncMock(side_effect=RuntimeError('stale'))
        _loc(page, self.MODAL_VISIBLE).count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        assert any('未检测到封面上传成功标志' in str(c) for c in logger.info.call_args_list)

    def test_confirm_click_retry_force(self):
        page = _mk_page()
        fc = MagicMock()
        fc.set_files = AsyncMock()
        page.expect_file_chooser = MagicMock(return_value=_FakeCM(value=fc))
        _loc(page, self.REPL).count = AsyncMock(return_value=1)
        _loc(page, self.MODAL_VISIBLE).count = AsyncMock(return_value=0)
        confirm = _loc(page, self.CONFIRM).first
        confirm.click = AsyncMock(side_effect=[RuntimeError('overlap'), None])
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        assert confirm.click.await_count == 2
        assert confirm.click.await_args.kwargs == {'timeout': 5000, 'force': True}
        assert any('attempt=1 失败' in str(c) for c in logger.info.call_args_list)

    def test_confirm_click_fail_then_js_evaluate(self):
        page = _mk_page()
        fc = MagicMock()
        fc.set_files = AsyncMock()
        page.expect_file_chooser = MagicMock(return_value=_FakeCM(value=fc))
        _loc(page, self.REPL).count = AsyncMock(return_value=1)
        _loc(page, self.MODAL_VISIBLE).count = AsyncMock(return_value=0)
        confirm = _loc(page, self.CONFIRM).first
        confirm.click = AsyncMock(side_effect=[RuntimeError('a'), RuntimeError('b')])
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        confirm.evaluate.assert_awaited_once_with('el => el.click()')
        assert any('JS evaluate click 命中' in str(c) for c in logger.info.call_args_list)

    def test_js_click_fails_logged(self):
        page = _mk_page()
        fc = MagicMock()
        fc.set_files = AsyncMock()
        page.expect_file_chooser = MagicMock(return_value=_FakeCM(value=fc))
        _loc(page, self.REPL).count = AsyncMock(return_value=1)
        _loc(page, self.MODAL_VISIBLE).count = AsyncMock(return_value=0)
        confirm = _loc(page, self.CONFIRM).first
        confirm.click = AsyncMock(side_effect=[RuntimeError('a'), RuntimeError('b')])
        confirm.evaluate = AsyncMock(side_effect=RuntimeError('js boom'))
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)  # 不抛异常
        assert any('JS evaluate click 失败' in str(c) for c in logger.info.call_args_list)

    def test_modal_not_closed_escapes(self):
        page = _mk_page()
        fc = MagicMock()
        fc.set_files = AsyncMock()
        page.expect_file_chooser = MagicMock(return_value=_FakeCM(value=fc))
        _loc(page, self.REPL).count = AsyncMock(return_value=1)
        _loc(page, self.MODAL_VISIBLE).count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        assert any('弹窗 15s 未关，Escape 兜底' in str(c) for c in logger.info.call_args_list)
        page.keyboard.press.assert_awaited_once_with('Escape')

    def test_modal_probe_error_swallowed(self):
        page = _mk_page()
        fc = MagicMock()
        fc.set_files = AsyncMock()
        page.expect_file_chooser = MagicMock(return_value=_FakeCM(value=fc))
        _loc(page, self.REPL).count = AsyncMock(return_value=1)
        _loc(page, self.MODAL_VISIBLE).count = AsyncMock(side_effect=RuntimeError('stale'))
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)
        assert any('弹窗 15s 未关，Escape 兜底' in str(c) for c in logger.info.call_args_list)

    def test_modal_not_closed_escape_error_swallowed(self):
        page = _mk_page()
        fc = MagicMock()
        fc.set_files = AsyncMock()
        page.expect_file_chooser = MagicMock(return_value=_FakeCM(value=fc))
        _loc(page, self.REPL).count = AsyncMock(return_value=1)
        _loc(page, self.MODAL_VISIBLE).count = AsyncMock(return_value=1)
        page.keyboard.press = AsyncMock(side_effect=RuntimeError('kbd boom'))
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger'):
            self._run(page)  # Escape 异常吞掉

    def test_outer_exception_screenshot_escape(self):
        page = _mk_page()
        _loc(page, self.EDIT_BTN).first.wait_for = AsyncMock(
            side_effect=RuntimeError('no edit btn')
        )
        logger = MagicMock()
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger', logger):
            self._run(page)  # 不抛异常
        page.screenshot.assert_awaited()
        page.keyboard.press.assert_awaited_once_with('Escape')
        assert any('设置封面失败' in str(c) for c in logger.info.call_args_list)

    def test_outer_exception_escape_error_swallowed(self):
        page = _mk_page()
        _loc(page, self.EDIT_BTN).first.wait_for = AsyncMock(
            side_effect=RuntimeError('no edit btn')
        )
        page.keyboard.press = AsyncMock(side_effect=RuntimeError('kbd boom'))
        page.screenshot = AsyncMock(side_effect=RuntimeError('shot boom'))
        with patch('os.path.exists', return_value=True), _no_sleep(), \
             patch('impl.zhihu.platform.logger'):
            self._run(page)  # 截图与 Escape 异常都吞掉


# ── DOM 辅助: 标题 / 简介+标签 ─────────────────────────────────────────────

class TestFillTitle:
    def test_empty_title_returns(self):
        page = _mk_page()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._fill_title(page, ''))
        _loc(page, 'textarea[name="title"], textarea[placeholder*="标题"], '
                  '.TitleArea textarea').first.fill.assert_not_awaited()

    def test_fills_truncated_50(self):
        page = _mk_page()
        title_input = _loc(
            page, 'textarea[name="title"], textarea[placeholder*="标题"], '
                  '.TitleArea textarea'
        ).first
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._fill_title(page, 'x' * 80))
        title_input.click.assert_awaited_once()
        assert title_input.fill.await_args_list[0].args == ('',)
        assert title_input.fill.await_args_list[1].args == ('x' * 50,)


class TestFillDescAndTags:
    EDITOR = ('.EditorArea [contenteditable="true"], '
              '.Editable [contenteditable="true"], '
              '.WritePinV2-Form [contenteditable="true"]')

    def test_happy_with_tags(self):
        page = _mk_page()
        editor = _loc(page, self.EDITOR).first
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._fill_desc_and_tags(
                page, '简介内容', ['旅行', '#美食', 'a,b，#c'])
            )
        editor.click.assert_awaited_once()
        # 剪贴板粘贴简介
        page.evaluate.assert_awaited_once()
        assert page.evaluate.await_args.args[1] == '简介内容'
        page.keyboard.press.assert_awaited()  # Control+V + 每标签空格
        # 5 个解析后的标签逐个 press_sequentially
        texts = [c.args[0] for c in editor.press_sequentially.await_args_list]
        assert texts == [' #旅行', ' #美食', ' #a', ' #b', ' #c']
        assert editor.press_sequentially.await_args.kwargs == {'delay': 150}

    def test_desc_truncated_2000(self):
        page = _mk_page()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._fill_desc_and_tags(page, 'x' * 2500, []))
        assert page.evaluate.await_args.args[1] == 'x' * 2000

    def test_paste_fallback_to_type(self):
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('clipboard denied'))
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._fill_desc_and_tags(page, '简介', []))
        page.keyboard.type.assert_awaited_once_with('简介')
        assert any('粘贴失败，回退 type' in str(c) for c in logger.info.call_args_list)

    def test_non_string_tags_skipped(self):
        page = _mk_page()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._fill_desc_and_tags(page, '', ['a', 123, None, 'b']))
        editor = _loc(page, self.EDITOR).first
        texts = [c.args[0] for c in editor.press_sequentially.await_args_list]
        assert texts == [' #a', ' #b']

    def test_empty_desc_no_tags_skips_editor_input(self):
        page = _mk_page()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._fill_desc_and_tags(page, '', []))
        editor = _loc(page, self.EDITOR).first
        editor.click.assert_awaited_once()
        page.evaluate.assert_not_awaited()
        editor.press_sequentially.assert_not_awaited()


# ── DOM 辅助: 视频标记 / 原创开关 ──────────────────────────────────────────

class TestSetVideoMark:
    OVERLAY = '.VideoUploadForm-videoTypeSelectOverlay, button[aria-label="选择视频标记"]'
    MODAL = '.VideoUploadForm-videoTypeModalContent, .Modal-inner:has-text("添加视频标记")'
    CONFIRM = ('.VideoUploadForm-videoTypeModalActions button:has-text("确认"), '
               '.ModalButtonGroup button.Button--blue:has-text("确认")')

    def test_default_confirms_only(self):
        page = _mk_page()
        modal = _loc(page, self.MODAL).first
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_video_mark(page, ''))
        _loc(page, self.OVERLAY).first.click.assert_awaited_once()
        modal.locator(
            '.VideoUploadForm-videoTypeModalOption:has-text("内容无需标注")'
        ).first.click.assert_not_awaited()  # 默认项不点选项
        modal.locator(self.CONFIRM).first.click.assert_awaited_once()

    def test_non_default_selects_option(self):
        page = _mk_page()
        modal = _loc(page, self.MODAL).first
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_video_mark(page, '内容由AI生成'))
        option = modal.locator(
            '.VideoUploadForm-videoTypeModalOption:has-text("内容由AI生成")'
        ).first
        option.click.assert_awaited_once()
        modal.locator(self.CONFIRM).first.click.assert_awaited_once()

    def test_exception_escapes(self):
        page = _mk_page()
        _loc(page, self.OVERLAY).first.wait_for = AsyncMock(
            side_effect=RuntimeError('no overlay')
        )
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_video_mark(page, '内容无需标注'))  # 不抛异常
        page.keyboard.press.assert_awaited_once_with('Escape')
        assert any('设置失败' in str(c) for c in logger.info.call_args_list)

    def test_escape_error_swallowed(self):
        page = _mk_page()
        _loc(page, self.OVERLAY).first.wait_for = AsyncMock(
            side_effect=RuntimeError('no overlay')
        )
        page.keyboard.press = AsyncMock(side_effect=RuntimeError('kbd boom'))
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_video_mark(page, '内容无需标注'))  # 不抛异常


class TestEnsureOriginalChecked:
    CHECKBOX = '.VideoUploadForm-typeContainer input[type="checkbox"]'
    TOGGLE = '.VideoUploadForm-typeContainer button, .VideoUploadForm-typeContainer label'

    def test_checked_logs(self):
        page = _mk_page()
        _loc(page, self.CHECKBOX).first.is_checked = AsyncMock(return_value=True)
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._ensure_original_checked(page))
        _loc(page, self.TOGGLE).first.click.assert_not_awaited()
        assert any('原创开关已开启' in str(c) for c in logger.info.call_args_list)

    def test_unchecked_clicks_toggle(self):
        page = _mk_page()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._ensure_original_checked(page))
        _loc(page, self.TOGGLE).first.click.assert_awaited_once()

    def test_exception_swallowed(self):
        page = _mk_page()
        _loc(page, self.CHECKBOX).first.wait_for = AsyncMock(
            side_effect=RuntimeError('no checkbox')
        )
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._ensure_original_checked(page))  # 不抛异常
        assert any('检查失败' in str(c) for c in logger.info.call_args_list)


# ── DOM 辅助: 所属领域 ─────────────────────────────────────────────────────

class TestSetCategory:
    AREA = '.VideoUploadForm-item'
    LISTBOX = '.Popover-content [role="listbox"], div[role="listbox"]'

    def test_empty_returns(self):
        page = _mk_page()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_category(page, ''))
        _loc(page, self.AREA).first.click.assert_not_awaited()

    def test_happy(self):
        page = _mk_page()
        area = _loc(page, self.AREA).first
        trigger = area.locator('button[role="combobox"]').first
        listbox = _loc(page, self.LISTBOX).first
        option = listbox.locator('button[role="option"]:has-text("科技")').first
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_category(page, '科技'))
        trigger.click.assert_awaited_once_with(timeout=5000, force=False)
        option.click.assert_awaited_once_with(timeout=5000, force=False)

    def test_trigger_retry_force(self):
        page = _mk_page()
        trigger = _loc(page, self.AREA).first.locator('button[role="combobox"]').first
        trigger.click = AsyncMock(side_effect=[RuntimeError('hidden'), None])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_category(page, '科技'))
        assert trigger.click.await_count == 2
        assert trigger.click.await_args.kwargs == {'timeout': 5000, 'force': True}
        assert any('普通点击失败，尝试 force click' in str(c) for c in logger.info.call_args_list)

    def test_trigger_both_fail_outer_except(self):
        page = _mk_page()
        trigger = _loc(page, self.AREA).first.locator('button[role="combobox"]').first
        trigger.click = AsyncMock(side_effect=[RuntimeError('a'), RuntimeError('b')])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_category(page, '科技'))  # 不抛异常
        page.keyboard.press.assert_awaited_once_with('Escape')
        assert any('设置失败' in str(c) for c in logger.info.call_args_list)

    def test_option_retry_force(self):
        page = _mk_page()
        option = _loc(page, self.LISTBOX).first.locator(
            'button[role="option"]:has-text("科技")'
        ).first
        option.click = AsyncMock(side_effect=[RuntimeError('hidden'), None])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_category(page, '科技'))
        assert option.click.await_args.kwargs == {'timeout': 5000, 'force': True}
        assert any('option 普通点击失败，force 重试' in str(c) for c in logger.info.call_args_list)

    def test_option_both_fail_outer_except(self):
        page = _mk_page()
        option = _loc(page, self.LISTBOX).first.locator(
            'button[role="option"]:has-text("科技")'
        ).first
        option.click = AsyncMock(side_effect=[RuntimeError('a'), RuntimeError('b')])
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_category(page, '科技'))  # 不抛异常
        page.keyboard.press.assert_awaited_once_with('Escape')
        assert any('设置失败' in str(c) for c in logger.info.call_args_list)

    def test_area_missing_outer_except(self):
        page = _mk_page()
        _loc(page, self.AREA).first.wait_for = AsyncMock(
            side_effect=RuntimeError('no area')
        )
        page.keyboard.press = AsyncMock(side_effect=RuntimeError('kbd boom'))
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_category(page, '科技'))  # Escape 异常吞掉
        assert any('设置失败' in str(c) for c in logger.info.call_args_list)


# ── DOM 辅助: 定时发布 ─────────────────────────────────────────────────────

class TestSetScheduleTime:
    PD = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
    SWITCH = ('.VideoUploadForm-scheduledPublish--switch input[type="checkbox"], '
              '.VideoUploadForm-scheduledPublish label')
    CB = '.VideoUploadForm-scheduledPublish--switch input[type="checkbox"]'
    TOOL = '.Calendar-topToolDate'
    NEXT_MONTH = '.Calendar-topToolButton--nextMonth'
    PREV_MONTH = '.Calendar-topToolButton--prevMonth'
    DAY_CELLS = 'td.Calendar-day:not(.is-disabled):not(.is-not-this-month)'
    HOUR_TRIGGER = ('.DateTimePicker .Popover:has(.DatePicker) ~ .Popover '
                    '.Select-button, .DateTimePicker button[role="combobox"]')
    HOUR_OPT = '.DateTimePicker-selectList .Select-option:not([disabled]):has-text("10")'
    MINUTE_TRIGGER = '.DateTimePicker button[role="combobox"]'
    MINUTE_OPT = '.DateTimePicker-selectList .Select-option:not([disabled]):has-text("05")'

    def test_int_zero_returns(self):
        page = _mk_page()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            assert _run(ZhihuPlatform._set_schedule_time(page, 0)) is None
        assert page.locator.call_count == 0

    def test_int_nonzero_returns(self):
        page = _mk_page()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            assert _run(ZhihuPlatform._set_schedule_time(page, 5)) is None
        assert page.locator.call_count == 0

    def test_none_returns(self):
        page = _mk_page()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            assert _run(ZhihuPlatform._set_schedule_time(page, None)) is None
        assert page.locator.call_count == 0

    def _mk_happy_page(self, day='22'):
        page = _mk_page()
        cb = _loc(page, self.CB).first
        cb.count = AsyncMock(return_value=1)
        cb.is_checked = AsyncMock(return_value=True)  # 开关已开 → 不点 switch
        tool = _loc(page, self.TOOL).first
        tool.count = AsyncMock(return_value=1)
        tool.text_content = AsyncMock(return_value='2026年8月')  # 目标年月 → 首轮 break
        day_cells = _loc(page, self.DAY_CELLS)
        day_cells.count = AsyncMock(return_value=2)
        day_cells.nth(0).text_content = AsyncMock(return_value='21')
        day_cells.nth(1).text_content = AsyncMock(return_value=day)
        hour_opt = _loc(page, self.HOUR_OPT).first
        hour_opt.count = AsyncMock(return_value=1)
        minute_opt = _loc(page, self.MINUTE_OPT).first
        minute_opt.count = AsyncMock(return_value=1)
        return page

    def test_happy_scheduled(self):
        page = self._mk_happy_page()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        _loc(page, self.SWITCH).first.click.assert_not_awaited()  # 开关已开
        _loc(page, '.DatePicker-Button').first.click.assert_awaited_once()
        day_cells = _loc(page, self.DAY_CELLS)
        day_cells.nth(1).click.assert_awaited_once()
        _loc(page, self.HOUR_OPT).first.click.assert_awaited_once()
        _loc(page, self.MINUTE_OPT).first.click.assert_awaited_once()
        page.keyboard.press.assert_awaited_once_with('Escape')

    def test_switch_off_clicks(self):
        page = self._mk_happy_page()
        _loc(page, self.CB).first.is_checked = AsyncMock(return_value=False)
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        _loc(page, self.SWITCH).first.click.assert_awaited_once()
        assert any('已打开开关' in str(c) for c in logger.info.call_args_list)

    def test_cb_missing_turns_on(self):
        page = self._mk_happy_page()
        _loc(page, self.CB).first.count = AsyncMock(return_value=0)
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        _loc(page, self.SWITCH).first.click.assert_awaited_once()

    def test_cb_probe_error_turns_on(self):
        page = self._mk_happy_page()
        _loc(page, self.CB).first.count = AsyncMock(side_effect=RuntimeError('stale'))
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        _loc(page, self.SWITCH).first.click.assert_awaited_once()

    def test_calendar_next_month(self):
        page = self._mk_happy_page()
        tool = _loc(page, self.TOOL).first
        tool.text_content = AsyncMock(side_effect=['2026年1月', '2026年8月'])
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        _loc(page, self.NEXT_MONTH).first.click.assert_awaited_once()

    def test_calendar_prev_month(self):
        page = self._mk_happy_page()
        _loc(page, self.TOOL).first.text_content = AsyncMock(
            side_effect=['2026年12月', '2026年8月']
        )
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        _loc(page, self.PREV_MONTH).first.click.assert_awaited_once()

    def test_calendar_tool_missing_fallback(self):
        page = self._mk_happy_page()
        _loc(page, self.TOOL).first.count = AsyncMock(return_value=0)
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        _loc(page, self.NEXT_MONTH).first.click.assert_awaited()

    def test_calendar_tool_probe_error_fallback(self):
        page = self._mk_happy_page()
        _loc(page, self.TOOL).first.count = AsyncMock(side_effect=RuntimeError('stale'))
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        _loc(page, self.NEXT_MONTH).first.click.assert_awaited()

    def test_calendar_parse_error_fallback(self):
        page = self._mk_happy_page()
        _loc(page, self.TOOL).first.text_content = AsyncMock(return_value='2025年12月')
        with patch('impl.zhihu.platform._extract_year', return_value='abc'), \
             _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        _loc(page, self.NEXT_MONTH).first.click.assert_awaited()

    def test_day_not_found_logs(self):
        page = self._mk_happy_page(day='23')  # 无 22 号
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        day_cells = _loc(page, self.DAY_CELLS)
        day_cells.nth(1).click.assert_not_awaited()
        assert any('找不到可点击日期 22' in str(c) for c in logger.info.call_args_list)

    def test_hour_trigger_fallback(self):
        page = self._mk_happy_page()
        hour_trigger = _loc(page, self.HOUR_TRIGGER).nth(0)
        hour_trigger.click = AsyncMock(side_effect=RuntimeError('hidden'))
        fallback = _loc(page, self.MINUTE_TRIGGER).nth(0)
        fallback.click = AsyncMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        fallback.click.assert_awaited_once_with(timeout=5000)

    def test_hour_option_missing_logs(self):
        page = self._mk_happy_page()
        _loc(page, self.HOUR_OPT).first.count = AsyncMock(return_value=0)
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        assert any('找不到小时选项 10' in str(c) for c in logger.info.call_args_list)

    def test_minute_trigger_error_logs(self):
        page = self._mk_happy_page()
        _loc(page, self.MINUTE_TRIGGER).nth(1).click = AsyncMock(
            side_effect=RuntimeError('hidden')
        )
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        assert any('分钟下拉点击失败' in str(c) for c in logger.info.call_args_list)

    def test_minute_option_missing_logs(self):
        page = self._mk_happy_page()
        _loc(page, self.MINUTE_OPT).first.count = AsyncMock(return_value=0)
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))
        assert any('找不到分钟选项 05' in str(c) for c in logger.info.call_args_list)

    def test_outer_exception_logged(self):
        page = _mk_page()
        _loc(page, self.SWITCH).first.wait_for = AsyncMock(
            side_effect=RuntimeError('no switch')
        )
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))  # 不抛异常
        assert any('定时发布] 设置失败' in str(c) for c in logger.info.call_args_list)

    def test_escape_error_swallowed(self):
        page = self._mk_happy_page()
        page.keyboard.press = AsyncMock(side_effect=RuntimeError('kbd boom'))
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            _run(ZhihuPlatform._set_schedule_time(page, self.PD))  # 不抛异常


# ── DOM 辅助: 点击发布 / 表单 dump ─────────────────────────────────────────

class TestClickSubmit:
    SUBMIT = ('button.VideoUploadForm-submitButton:has-text("发布视频"), '
              'button:has-text("发布视频")')
    SUBMIT_SCHEDULED = ('button.VideoUploadForm-submitButton:has-text("定时发布"), '
                        'button:has-text("定时发布")')
    GENERIC = '.VideoUploadForm-submitButton'

    def test_success_not_scheduled(self):
        page = _mk_page()
        resp = _mk_response({'code': 0, 'message': 'ok'})
        page.expect_response = MagicMock(return_value=_FakeCM(value=resp))
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            ok, msg = _run(ZhihuPlatform._click_submit(page, False))
        assert (ok, msg) == (True, '发布成功')
        page.evaluate.assert_awaited_once_with('window.scrollTo(0, document.body.scrollHeight)')
        _loc(page, self.SUBMIT).first.click.assert_awaited_once()
        resp.json.assert_awaited_once()

    def test_success_scheduled_text(self):
        page = _mk_page()
        resp = _mk_response({'code': 0, 'toast_message': 'ok'})
        page.expect_response = MagicMock(return_value=_FakeCM(value=resp))
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            ok, msg = _run(ZhihuPlatform._click_submit(page, True))
        assert (ok, msg) == (True, '发布成功')
        _loc(page, self.SUBMIT_SCHEDULED).first.click.assert_awaited_once()

    def test_submit_wait_timeout_falls_back(self):
        page = _mk_page()
        resp = _mk_response({'code': 0, 'message': 'ok'})
        page.expect_response = MagicMock(return_value=_FakeCM(value=resp))
        _loc(page, self.SUBMIT).first.wait_for = AsyncMock(
            side_effect=TimeoutError('no button')
        )
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            ok, msg = _run(ZhihuPlatform._click_submit(page, False))
        assert (ok, msg) == (True, '发布成功')
        _loc(page, self.GENERIC).first.click.assert_awaited_once()
        assert any('尝试通用提交' in str(c) for c in logger.info.call_args_list)

    def test_click_error_returns_false(self):
        page = _mk_page()
        page.expect_response = MagicMock(return_value=_FakeCM(value=_mk_response({})))
        _loc(page, self.SUBMIT).first.click = AsyncMock(
            side_effect=RuntimeError('btn hidden')
        )
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            ok, msg = _run(ZhihuPlatform._click_submit(page, False))
        assert ok is False
        assert '点击发布按钮失败: btn hidden' in msg

    def test_response_timeout(self):
        page = _mk_page()
        page.expect_response = MagicMock(
            return_value=_FakeCM(enter_error=TimeoutError('resp timeout'))
        )
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            ok, msg = _run(ZhihuPlatform._click_submit(page, False))
        assert (ok, msg) == (False, '等待发布 API 响应超时')

    def test_json_error(self):
        page = _mk_page()
        resp = _mk_response({})
        resp.json = AsyncMock(side_effect=ValueError('bad json'))
        page.expect_response = MagicMock(return_value=_FakeCM(value=resp))
        with _no_sleep(), patch('impl.zhihu.platform.logger'):
            ok, msg = _run(ZhihuPlatform._click_submit(page, False))
        assert (ok, msg) == (False, '发布响应解析失败')

    def test_nonzero_code_raises(self):
        page = _mk_page()
        page.expect_response = MagicMock(
            return_value=_FakeCM(value=_mk_response({'code': 1001, 'message': 'bad'}))
        )
        with _no_sleep(), patch('impl.zhihu.platform.logger'), \
             pytest.raises(RuntimeError, match='code=1001'):
            _run(ZhihuPlatform._click_submit(page, False))

    def test_code_missing_default_msg_raises(self):
        page = _mk_page()
        page.expect_response = MagicMock(return_value=_FakeCM(value=_mk_response({})))
        with _no_sleep(), patch('impl.zhihu.platform.logger'), \
             pytest.raises(RuntimeError, match='发布失败'):
            _run(ZhihuPlatform._click_submit(page, False))

    def test_dry_run_dumps_form(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value={
            'title': 'T', 'desc_preview': '', 'desc_len': 0, 'videoMark': '',
            'original': True, 'category': '', 'scheduled': None,
            'scheduleTime': '', 'cover': '', 'url': 'http://x',
        })
        with patch('impl.zhihu.platform.DEBUG_DRY_RUN_SUBMIT', True), \
             _no_sleep(), patch('impl.zhihu.platform.logger'):
            ok, msg = _run(ZhihuPlatform._click_submit(page, False))
        assert (ok, msg) == (True, 'dry-run')
        page.evaluate.assert_awaited_once()  # _dump_form_state 已执行


class TestDumpFormState:
    def test_happy(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value={
            'title': '标题', 'desc_preview': '简介', 'desc_len': 2,
            'videoMark': '', 'original': True, 'category': '科技',
            'scheduled': False, 'scheduleTime': '', 'cover': 'http://c',
            'url': 'http://x',
        })
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._dump_form_state(page))
        infos = [str(c) for c in logger.info.call_args_list]
        assert any('title: 标题' in s for s in infos)
        assert any('category: 科技' in s for s in infos)

    def test_evaluate_error_logged(self):
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('js boom'))
        logger = MagicMock()
        with _no_sleep(), patch('impl.zhihu.platform.logger', logger):
            _run(ZhihuPlatform._dump_form_state(page))  # 不抛异常
        assert any('抓取失败' in str(c) for c in logger.info.call_args_list)
