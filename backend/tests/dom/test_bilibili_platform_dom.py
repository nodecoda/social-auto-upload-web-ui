"""Bilibili platform.py DOM 交互层契约测试（T35 第十二期）。

覆盖 impl/bilibili/platform.py（792 stmts，基线 14%）:
- 纯函数: _sanitize_title（emoji/HTML 危险字符过滤） / _truncate_desc_by_length（emoji=3 截断）
  / _parse_cookie_to_storage_state（.bilibili.com 域/expires 7d/跳过无效对）
- 登录/校验/同步: login（QR 多选择器/缺失回退 get_by_role→500/定位异常兜底/framenavigated
  事件驱动/save_login_result+stats_fn/成功才关浏览器） / check_cookie（passport 判定/超时 False）
  / sync_profile（两步抓取/各步异常兜底/外层异常空结果/close 异常吞掉） / _login_stats_fn
  / _scrape_bilibili_stats（8 项 label_map/未知项丢弃/千分位/非法数字/超时仍抓取/evaluate 异常）
  / open_creator_center（线程启动/事件+close 异常吞掉）
- 编排: _upload_single_video 全流程（passport 过期 raise/表单轮询 4h 超时/提交按钮 10 次重试/
  按钮消失判定/URL 跳转判定/提交异常重试/dry_run 提前 return/cookie 回写/回写异常吞掉/
  定时/合集/close_browser）
- DOM 辅助: _upload_video_file（iframe 探测/主页面回退） / _wait_upload_complete（上传完成/
  上传失败 raise/进度日志/探测异常继续/超时 raise） / _fill_title（过滤+80 截断）
  / _set_category（int/str 中文/str 数字/未知 tid/分区缺失/容器兜底/下拉再点/选项缺失/异常非致命）
  / _fill_tags（解析/选择器回退/可见性/探测异常/输入框丢失/editable 异常/添加失败/10 个截断）
  / _fill_desc（emoji 截断/编辑器缺失） / _set_thumbnail（三档点击策略/弹窗容器回退/page 兜底/
  4:3/同步勾选/双 file input/提交确认/Escape/异常 raise）
  / _set_creation_declaration（直选/scoped 回退/下拉超时 fallback/选项匹配/转载来源填入/异常非致命）
  / _set_collection（入口/选项匹配/父级点击回退/未找到/下拉未出现/异常非致命）
  / _set_schedule_time（日期选择/禁用项跳过/小时分钟/异常非致命）
"""
import asyncio
import os
import sys
import tempfile
import time as _time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from conf import BASE_DIR
from impl.bilibili.platform import (
    BILIBILI_MANAGE_URL,
    BILIBILI_UPLOAD_URL,
    BilibiliPlatform,
    _sanitize_title,
    _truncate_desc_by_length,
    scrape_bilibili_profile,
)

_XPATH_CONTAINER = ("xpath=ancestor::div[contains(@class,'section-title-container')][1]"
                    "/following-sibling::div[contains(@class,'selector-container')][1]")
_XPATH_CONTAINER_FALLBACK = "xpath=ancestor::div[2]"
_XPATH_SEASON_PARENT = "xpath=ancestor::div[contains(@class,'season-item')][1]"
_TITLE_INPUT = ('input[placeholder*="标题"], input[placeholder*="Title"], '
                '.video-title input, [class*="title"] input[type="text"]')
_DESC_EDITOR = ('[contenteditable="true"][class*="editor"], .ql-editor, '
                '[class*="desc"] textarea, [class*="desc"] [contenteditable="true"]')
_TAG_SELECTORS = [
    'input[placeholder*="回车键Enter创建标签"]',
    'input[placeholder*="Enter创建标签"]',
    'input[placeholder*="按回车"]',
    'input[placeholder*="标签"]',
    '.tag-input input',
    '[class*="tag"] input[type="text"]',
]
_TRIGGER1 = '[data-reporter-id="80"] .cover-empty-pill .add-text'
_TRIGGER2 = '[data-reporter-id="80"] .cover-empty-pill .add-icon'
_DIALOG1 = 'div.bcc-dialog:has-text("封面制作")'
_DIALOG2 = 'div.bcc-dialog:has-text("封面设置")'
_DIALOG_SELECTORS = [
    _DIALOG1,
    _DIALOG2,
    'div.bcc-dialog',
    'div[class*="cover-editor"]:visible',
    'div[class*="cover-dialog"]:visible',
    'div[class*="upload-cover"]:visible',
]
_STATEMENT_SCOPE = 'div.statement-content, div[class*="statement-content"]'


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return BilibiliPlatform()


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
    loc.fill = AsyncMock()
    loc.press = AsyncMock()
    loc.press_sequentially = AsyncMock()
    loc.evaluate = AsyncMock(return_value='')
    loc.scroll_into_view_if_needed = AsyncMock()
    loc.dispatch_event = AsyncMock()
    subs = defaultdict(_mk_locator)
    nth_subs = defaultdict(_mk_leaf)
    loc.locator = MagicMock(side_effect=lambda sel, **kw: subs.setdefault(sel, _mk_locator()))
    loc.subs = subs
    loc.nth = MagicMock(side_effect=lambda i: nth_subs.setdefault(i, _mk_leaf()))
    loc.nth_subs = nth_subs
    filters = defaultdict(_mk_locator)
    loc.filter = MagicMock(
        side_effect=lambda **kw: filters.setdefault(repr(sorted(kw.items())), _mk_locator())
    )
    loc.filters = filters
    return loc


def _mk_locator():
    loc = _mk_leaf()
    loc.first = _mk_leaf()
    loc.last = _mk_leaf()
    return loc


def _mk_page(url=BILIBILI_UPLOAD_URL):
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
    page.screenshot = AsyncMock()
    page.on = MagicMock()
    page.expect_file_chooser = MagicMock()
    by_text = {}
    page.get_by_text = MagicMock(
        side_effect=lambda text, exact=False: by_text.setdefault(text, _mk_locator())
    )
    page.by_text = by_text
    page.get_by_role = MagicMock(return_value=_mk_locator())
    locators = {}
    page.locator = MagicMock(
        side_effect=lambda sel, **kw: locators.setdefault(sel, _mk_locator())
    )
    page.locators = locators
    return page


def _loc(page, sel):
    page.locator(sel)
    return page.locators[sel]


def _txt(page, text):
    page.get_by_text(text, exact=True)
    return page.by_text[text]


@contextmanager
def _mk_browser_chain(platform, url=BILIBILI_UPLOAD_URL):
    page = _mk_page(url=url)
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.storage_state = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    browser.is_connected = MagicMock(return_value=False)
    with patch.object(platform, 'create_browser', AsyncMock(return_value=browser)) as cb, \
         patch.object(platform, 'create_context', AsyncMock(return_value=context)) as cc:
        yield page, context, browser, cb, cc


def _mk_cookie_file(name='t35_bili_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


def _mk_cover_file():
    fd, path = tempfile.mkstemp(prefix='sau_bili_cover_', suffix='.png')
    os.close(fd)
    return path


class _ChangedUrl:
    """page.url 替身:与原地址比较恒不相等(驱动 framenavigated 事件置位)。"""

    def __ne__(self, other):
        return True


class _FakeEvent:
    """asyncio.Event 替身:wait 立即返回,set 只记录调用(不依赖真实事件循环置位)。"""

    def __init__(self):
        self.wait = AsyncMock()
        self.set = MagicMock()


@contextmanager
def _mk_upload_steps(p, **mocks):
    """把 _upload_single_video 内部子步骤替换为 AsyncMock;asyncio.sleep 一并打桩。"""
    defaults = dict(
        upload_video_file=AsyncMock(),
        wait_upload_complete=AsyncMock(),
        fill_title=AsyncMock(),
        set_category=AsyncMock(),
        fill_tags=AsyncMock(),
        fill_desc=AsyncMock(),
        set_thumbnail=AsyncMock(),
        set_creation_declaration=AsyncMock(),
        set_schedule_time=AsyncMock(),
        set_collection=AsyncMock(),
        close_browser=AsyncMock(),
    )
    defaults.update(mocks)
    with patch.object(p, '_upload_video_file', defaults['upload_video_file']), \
         patch.object(p, '_wait_upload_complete', defaults['wait_upload_complete']), \
         patch.object(p, '_fill_title', defaults['fill_title']), \
         patch.object(p, '_set_category', defaults['set_category']), \
         patch.object(p, '_fill_tags', defaults['fill_tags']), \
         patch.object(p, '_fill_desc', defaults['fill_desc']), \
         patch.object(p, '_set_thumbnail', defaults['set_thumbnail']), \
         patch.object(p, '_set_creation_declaration', defaults['set_creation_declaration']), \
         patch.object(p, '_set_schedule_time', defaults['set_schedule_time']), \
         patch.object(p, '_set_collection', defaults['set_collection']), \
         patch.object(p, 'close_browser', defaults['close_browser']), \
         patch('asyncio.sleep', AsyncMock()):
        yield defaults


# ── 纯函数 ────────────────────────────────────────────────────────────────

class TestSanitizeTitle:
    def test_empty_and_none(self):
        assert _sanitize_title('') == ''
        assert _sanitize_title(None) is None

    def test_removes_emoji_and_html_chars(self):
        assert _sanitize_title('视频😀标题<b>"q"\'&') == '视频标题bq'

    def test_keeps_normal_text(self):
        assert _sanitize_title('中文 English 123 标点,。!?') == '中文 English 123 标点,。!?'


class TestTruncateDescByLength:
    def test_empty_and_none(self):
        assert _truncate_desc_by_length('') == ''
        assert _truncate_desc_by_length(None) is None

    def test_short_unchanged(self):
        assert _truncate_desc_by_length('short 文本') == 'short 文本'

    def test_truncates_at_limit(self):
        assert len(_truncate_desc_by_length('a' * 2001)) == 2000

    def test_emoji_costs_three(self):
        out = _truncate_desc_by_length('😀' * 1000)
        assert len(out) == 666  # 666*3=1998 ≤ 2000;667*3=2001 > 2000

    def test_boundary_emoji_breaks(self):
        assert _truncate_desc_by_length('a' * 1999 + '😀') == 'a' * 1999


class TestParseCookieToStorageState:
    def test_happy_parse(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('a=1; b = 2')
        assert origins == []
        assert [c['name'] for c in cookies] == ['a', 'b']
        for c in cookies:
            assert c['domain'] == '.bilibili.com'
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
        cookies, origins = p._parse_cookie_to_storage_state('')
        assert cookies == []
        assert origins == []

    def test_expires_seven_day_window(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('a=1')
        delta = cookies[0]['expires'] - _time.time()
        assert 6 * 24 * 3600 < delta < 8 * 24 * 3600

# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLogin:
    def test_success_qr_found(self):
        p = _mk_platform()
        page = _mk_page(url='https://passport.bilibili.com/login')
        page.url = _ChangedUrl()  # framenavigated 后与原地址不相等 → 事件置位
        queue = MagicMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()

        def _register(event, fn):
            fn(page.main_frame)  # create_task 分支
            fn(MagicMock())      # 非主 frame → lambda 返回 None

        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('asyncio.Event', _FakeEvent), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.bilibili.platform.logger'):
            page.on = MagicMock(side_effect=_register)
            _loc(page, '.qrcode-img img, img[src*="qrcode"], .login-scan img').first \
                .get_attribute = AsyncMock(return_value='http://qr.example/scan')
            _run(p.login('u1', queue, account_id='acc1'))
        queue.put.assert_called_once_with('http://qr.example/scan')
        assert page.goto.await_count == 2  # passport 登录页 + account home
        assert page.goto.await_args_list[0].args == ('https://passport.bilibili.com/login',)
        assert page.goto.await_args_list[1].args == ('https://account.bilibili.com/account/home',)
        assert page.on.call_args.args[0] == 'framenavigated'
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 5
        assert kwargs['account_id'] == 'acc1'
        assert kwargs['scrape_fn'] is scrape_bilibili_profile
        assert kwargs['stats_fn'].__func__ is BilibiliPlatform._login_stats_fn
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()  # 成功才关浏览器

    def test_qr_missing_500(self):
        """主选择器与 get_by_role 回退都拿不到 src → put 500,保留浏览器。"""
        p = _mk_platform()
        page = _mk_page(url='https://passport.bilibili.com/login')
        queue = MagicMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('impl.bilibili.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.bilibili.platform.logger'):
            _run(p.login('u1', queue))
        queue.put.assert_called_once_with('500')
        slr.assert_not_awaited()
        page.close.assert_awaited()
        context.close.assert_awaited()
        browser.close.assert_not_awaited()  # 失败保留浏览器看现场

    def test_qr_locate_exception_puts_500(self):
        p = _mk_platform()
        page = _mk_page(url='https://passport.bilibili.com/login')
        queue = MagicMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('impl.bilibili.platform.logger') as logger:
            _loc(page, '.qrcode-img img, img[src*="qrcode"], .login-scan img').first \
                .get_attribute = AsyncMock(side_effect=RuntimeError('boom'))
            _run(p.login('u1', queue))
        queue.put.assert_called_once_with('500')
        assert any('failed to locate QR code' in str(c) for c in logger.info.call_args_list)


class TestCheckCookie:
    def test_valid(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_bili_cc1.json')
        try:
            with _mk_browser_chain(p, url='https://member.bilibili.com/platform/home') \
                    as (page, _context, browser, cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger'):
                assert _run(p.check_cookie(cookie.name)) is True
            cb.assert_awaited_once_with(headless=True)
            page.goto.assert_awaited_once_with('https://member.bilibili.com/platform/home')
            page.wait_for_load_state.assert_awaited_once_with('domcontentloaded', timeout=10000)
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_expired(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_bili_cc2.json')
        try:
            with _mk_browser_chain(p, url='https://passport.bilibili.com/login') \
                    as (_page, _context, browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger'):
                assert _run(p.check_cookie(cookie.name)) is False
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_load_state_timeout_returns_false(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_bili_cc3.json')
        try:
            with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger') as logger:
                page.wait_for_load_state = AsyncMock(side_effect=TimeoutError('slow'))
                assert _run(p.check_cookie(cookie.name)) is False
            assert any('cookie check timed out' in str(c) for c in logger.info.call_args_list)
        finally:
            cookie.unlink(missing_ok=True)


class TestSyncProfile:
    STATS: ClassVar = [{'ICON': 'user', 'COUNT': 1, 'NAME': '粉丝', 'SORT': 1}]

    def test_happy(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.bilibili.platform.scrape_bilibili_profile',
                   AsyncMock(return_value=('昵称', 'http://a.png'))) as sp, \
             patch.object(p, '_scrape_bilibili_stats', AsyncMock(return_value=self.STATS)), \
             patch('impl.bilibili.platform.logger'):
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '昵称', 'avatar': 'http://a.png', 'stats': self.STATS}
        assert page.goto.await_count == 2
        sp.assert_awaited_once()
        browser.close.assert_awaited_once()

    def test_step1_error_empty_name(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.bilibili.platform.scrape_bilibili_profile',
                   AsyncMock(return_value=('n', ''))) as sp, \
             patch.object(p, '_scrape_bilibili_stats', AsyncMock(return_value=self.STATS)), \
             patch('impl.bilibili.platform.logger'):
            page.goto = AsyncMock(side_effect=[RuntimeError('net'), None])
            res = _run(p.sync_profile('ck.json'))
        assert res['name'] == ''
        assert res['avatar'] == ''
        assert res['stats'] == self.STATS
        sp.assert_not_awaited()

    def test_step2_error_empty_stats(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.bilibili.platform.scrape_bilibili_profile',
                   AsyncMock(return_value=('昵称', 'http://a.png'))), \
             patch.object(p, '_scrape_bilibili_stats',
                          AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('impl.bilibili.platform.logger'):
            page.goto = AsyncMock(side_effect=[None, RuntimeError('net2')])
            res = _run(p.sync_profile('ck.json'))
        assert res['name'] == '昵称'
        assert res['stats'] == []

    def test_outer_exception_returns_empty(self):
        """Step1 兜底 handler 内 logger 抛异常 → 冒泡到外层 except → 空结果。"""
        p = _mk_platform()
        logger = MagicMock()

        def _info(*args, **_kwargs):
            if args and '抓 name/avatar 失败' in str(args[0]):
                raise RuntimeError('boom')

        logger.info = MagicMock(side_effect=_info)
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.bilibili.platform.logger', logger):
            page.goto = AsyncMock(side_effect=RuntimeError('net'))
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': []}

    def test_close_errors_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch('impl.bilibili.platform.scrape_bilibili_profile',
                   AsyncMock(return_value=('n', ''))), \
             patch.object(p, '_scrape_bilibili_stats', AsyncMock(return_value=[])), \
             patch('impl.bilibili.platform.logger'):
            page.close = AsyncMock(side_effect=RuntimeError('boom'))
            context.close = AsyncMock(side_effect=RuntimeError('boom'))
            browser.close = AsyncMock(side_effect=RuntimeError('boom'))
            res = _run(p.sync_profile('ck.json'))  # 不抛异常
        assert res['name'] == 'n'


class TestLoginStatsFn:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_bilibili_stats',
                          AsyncMock(return_value=[{'ICON': 'user', 'COUNT': 9,
                                                   'NAME': '粉丝', 'SORT': 1}])), \
             patch('impl.bilibili.platform.logger'):
            stats = _run(p._login_stats_fn(page, 'acc1'))
        assert stats[0]['COUNT'] == 9
        page.goto.assert_awaited_once_with(
            'https://member.bilibili.com/platform/home',
            wait_until='networkidle', timeout=30000,
        )

    def test_goto_error_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        page.goto = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('impl.bilibili.platform.logger'):
            assert _run(p._login_stats_fn(page, 'acc1')) == []

    def test_scrape_error_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_bilibili_stats',
                          AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('impl.bilibili.platform.logger'):
            assert _run(p._login_stats_fn(page, 'acc1')) == []


class TestScrapeStats:
    RAW: ClassVar = [
        {'label': '播放量', 'num': '1,114'},
        {'label': '评论', 'num': '15'},
        {'label': '弹幕', 'num': '2'},
        {'label': '点赞', 'num': '83'},
        {'label': '分享', 'num': '2'},
        {'label': '收藏', 'num': '21'},
        {'label': '投币', 'num': '24'},
        {'label': '粉丝总数', 'num': '1'},
    ]

    def test_happy_sorted(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=list(reversed(self.RAW)))
        with patch('impl.bilibili.platform.logger'):
            stats = _run(p._scrape_bilibili_stats(page))
        assert [s['NAME'] for s in stats] == \
            ['粉丝', '点赞', '收藏', '投币', '播放量', '评论', '弹幕', '分享']
        assert stats[0]['COUNT'] == 1
        assert stats[4]['COUNT'] == 1114  # 千分位

    def test_unknown_and_missing_dropped(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'label': '点赞', 'num': '83'},
            {'label': '未知项', 'num': '9'},
            {'num': '5'},      # label 缺失 → ''
            {'label': '收藏'},  # num 缺失 → '0'
        ])
        with patch('impl.bilibili.platform.logger'):
            stats = _run(p._scrape_bilibili_stats(page))
        assert [s['NAME'] for s in stats] == ['点赞', '收藏']
        assert stats[1]['COUNT'] == 0

    def test_invalid_number_zero(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'label': '点赞', 'num': 'abc'},
            {'label': '评论', 'num': '  12 3 '},
        ])
        with patch('impl.bilibili.platform.logger'):
            stats = _run(p._scrape_bilibili_stats(page))
        by_name = {s['NAME']: s['COUNT'] for s in stats}
        assert by_name['点赞'] == 0
        assert by_name['评论'] == 123

    def test_wait_timeout_still_scrapes(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        page.evaluate = AsyncMock(return_value=[{'label': '点赞', 'num': '1'}])
        with patch('impl.bilibili.platform.logger') as logger:
            stats = _run(p._scrape_bilibili_stats(page))
        assert [s['NAME'] for s in stats] == ['点赞']
        assert any('等待 .data-card/.fan-num 超时' in str(c) for c in logger.info.call_args_list)

    def test_evaluate_exception_empty(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('impl.bilibili.platform.logger') as logger:
            stats = _run(p._scrape_bilibili_stats(page))
        assert stats == []
        assert any('抓取失败' in str(c) for c in logger.info.call_args_list)

    def test_empty_evaluate(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.bilibili.platform.logger'):
            assert _run(p._scrape_bilibili_stats(page)) == []


class TestOpenCreatorCenter:
    def test_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_bili_occ.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.bilibili.platform.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl.bilibili.platform.create_context_sync', return_value=context) as ccs, \
                 patch('impl.bilibili.platform.logger'):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            cbs.assert_called_once_with(headless=False)
            ccs.assert_called_once()
            page.goto.assert_called_once_with(BILIBILI_MANAGE_URL)
            page.wait_for_event.assert_called_once_with('close', timeout=0)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_wait_event_error_swallowed(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_bili_occ2.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.bilibili.platform.create_browser_sync', return_value=browser), \
                 patch('impl.bilibili.platform.create_context_sync', return_value=context), \
                 patch('impl.bilibili.platform.logger'):
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
        cookie = _mk_cookie_file('t35_bili_occ3.json')
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('boom'))
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.bilibili.platform.create_browser_sync', return_value=browser), \
                 patch('impl.bilibili.platform.create_context_sync', return_value=context), \
                 patch('impl.bilibili.platform.logger'):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)


# ── 编排: _upload_single_video 全流程 ─────────────────────────────────────

class TestUploadSingleVideo:
    def _run(self, p, page, **kw):
        defaults = dict(
            title='标题', file_path='/m/v.mp4', tags=['t1'], publish_date=0,
            account_file='/c/u1.json', category=3, desc='描述',
            thumbnail_path=None, creation_declaration='', bili_collection_name='',
            bili_repost_source='',
        )
        defaults.update(kw)
        return _run(p._upload_single_video(**defaults))

    def test_happy_full_flow(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, cb, cc), \
             _mk_upload_steps(p) as mocks, \
             patch('impl.bilibili.platform.logger'):
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'span.submit-add').count = AsyncMock(side_effect=[1, 1, 0])
            self._run(p, page)
        cb.assert_awaited_once_with(headless=False)
        cc.assert_awaited_once_with(browser, storage_state='/c/u1.json')
        page.goto.assert_awaited_once_with(BILIBILI_UPLOAD_URL)
        page.wait_for_url.assert_awaited_once_with('**/platform/upload/**', timeout=30000)
        mocks['upload_video_file'].assert_awaited_once_with(page, '/m/v.mp4')
        mocks['wait_upload_complete'].assert_awaited_once_with(page)
        mocks['fill_title'].assert_awaited_once_with(page, '标题')
        mocks['set_category'].assert_awaited_once_with(page, 3)
        mocks['fill_tags'].assert_awaited_once_with(page, ['t1'])
        mocks['fill_desc'].assert_awaited_once_with(page, '描述')
        mocks['set_thumbnail'].assert_awaited_once_with(page, None)
        mocks['set_creation_declaration'].assert_awaited_once_with(page, '', '')
        mocks['set_schedule_time'].assert_not_awaited()   # publish_date=0 → immediate
        mocks['set_collection'].assert_not_awaited()
        assert page.screenshot.await_count == 3  # before_form / before_submit / after_submit
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_scheduled_publish_date(self):
        p = _mk_platform()
        dt = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, \
             patch('impl.bilibili.platform.logger'):
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'span.submit-add').count = AsyncMock(side_effect=[1, 1, 0])
            self._run(p, page, publish_date=dt)
        mocks['set_schedule_time'].assert_awaited_once_with(page, dt)

    def test_publish_date_none_schedules_with_none(self):
        """None 的 publish_date 在 elif publish_date != 0 下走 scheduled(如实契约)。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, \
             patch('impl.bilibili.platform.logger'):
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'span.submit-add').count = AsyncMock(side_effect=[1, 1, 0])
            self._run(p, page, publish_date=None)
        mocks['set_schedule_time'].assert_awaited_once_with(page, None)

    def test_immediate_float_zero(self):
        """0.0 命中 else 分支 → immediate,不设定时。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, \
             patch('impl.bilibili.platform.logger'):
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'span.submit-add').count = AsyncMock(side_effect=[1, 1, 0])
            self._run(p, page, publish_date=0.0)
        mocks['set_schedule_time'].assert_not_awaited()

    def test_collection_set_called(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, \
             patch('impl.bilibili.platform.logger'):
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'span.submit-add').count = AsyncMock(side_effect=[1, 1, 0])
            self._run(p, page, bili_collection_name='合集A')
        mocks['set_collection'].assert_awaited_once_with(page, '合集A')

    def test_storage_state_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, \
             patch('impl.bilibili.platform.logger'):
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'span.submit-add').count = AsyncMock(side_effect=[1, 1, 0])
            context.storage_state = AsyncMock(side_effect=RuntimeError('boom'))
            self._run(p, page)  # 回写异常吞掉,不影响关闭
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_passport_redirect_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p, url='https://passport.bilibili.com/login') \
                as (_page, _context, browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, \
             patch('impl.bilibili.platform.logger'), \
             pytest.raises(RuntimeError, match='cookie expired'):
            self._run(p, _page)
        mocks['upload_video_file'].assert_not_awaited()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_form_not_ready_timeout(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, \
             patch('impl.bilibili.platform.logger'), \
             patch('impl.bilibili.platform._UPLOAD_WAIT_POLLS', 60), \
             pytest.raises(TimeoutError, match='发布表单未渲染'):
            self._run(p, page)  # 标题输入框 count 恒 0 → 轮询耗尽后超时
        mocks['fill_title'].assert_not_awaited()

    def test_submit_not_found_retries(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as _mocks, \
             patch('impl.bilibili.platform.logger') as logger:
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            self._run(p, page)  # submit 按钮恒缺失 → 10 次重试后放弃
        assert any('could not confirm submission' in str(c) for c in logger.info.call_args_list)
        context.storage_state.assert_awaited_once()  # 仍回写 cookie

    def test_page_unchanged_logs_and_retries(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as _mocks, \
             patch('impl.bilibili.platform.logger') as logger:
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'span.submit-add').count = AsyncMock(return_value=1)  # 按钮一直在
            self._run(p, page)  # URL 不变 → 15 轮内检 × 10 次尝试 → 未确认
        assert any('page unchanged after click' in str(c[0]) for c in logger.info.call_args_list)
        assert any('could not confirm submission' in str(c[0]) for c in logger.info.call_args_list)
        context.storage_state.assert_awaited_once()  # 仍回写 cookie

    def test_submit_redirect_success(self):
        p = _mk_platform()
        with _mk_browser_chain(p, url='https://member.bilibili.com/platform/upload-manager/article') \
                as (page, context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as _mocks, \
             patch('impl.bilibili.platform.logger') as logger:
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'span.submit-add').count = AsyncMock(side_effect=[1, 1])
            page.screenshot = AsyncMock(side_effect=[None, None, RuntimeError('shot fail')])
            self._run(p, page)  # after_submit 截图失败 → except pass 吞掉
        assert any('redirected to' in str(c) for c in logger.info.call_args_list)
        context.storage_state.assert_awaited_once()

    def test_submit_exception_then_retry_success(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             _mk_upload_steps(p) as _mocks, \
             patch('impl.bilibili.platform.logger'):
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'span.submit-add').count = \
                AsyncMock(side_effect=[RuntimeError('boom'), 1, 1, 0])
            self._run(p, page)
        context.storage_state.assert_awaited_once()

    def test_dry_run_returns_before_submit(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_steps(p) as mocks, \
             patch('impl.bilibili.platform.logger') as logger, \
             patch('impl.bilibili.platform._PUBLISH_DRY_RUN', True):
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            browser.is_connected = MagicMock(side_effect=[True, False])  # 循环体跑一轮
            self._run(p, page)
        assert any('DRY_RUN' in str(c) for c in logger.warning.call_args_list)
        _loc(page, 'span.submit-add').first.click.assert_not_awaited()
        context.storage_state.assert_not_awaited()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_dry_run_is_connected_exception(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             _mk_upload_steps(p) as _mocks, \
             patch('impl.bilibili.platform.logger'), \
             patch('impl.bilibili.platform._PUBLISH_DRY_RUN', True):
            _loc(page, 'input[placeholder*="标题"]').first.count = AsyncMock(return_value=1)
            browser.is_connected = MagicMock(side_effect=RuntimeError('gone'))
            self._run(p, page)  # while 探测异常 → except pass → return

# ── DOM 辅助: 上传文件 / 等待上传完成 ─────────────────────────────────────

class TestUploadVideoFile:
    def test_iframe_found(self):
        page = _mk_page()
        frame = MagicMock()
        frame.locator = MagicMock(return_value=_mk_leaf())
        page.frame_locator = MagicMock(return_value=frame)
        with patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._upload_video_file(page, '/m/v.mp4'))
        page.frame_locator.assert_called_once_with('iframe[name="videoUpload"]')
        frame.locator.assert_called_once_with('input[type="file"]')
        frame.locator.return_value.wait_for.assert_awaited_once_with(
            state='attached', timeout=5000,
        )
        frame.locator.return_value.set_input_files.assert_awaited_once_with('/m/v.mp4')

    def test_iframe_missing_fallback_main_page(self):
        page = _mk_page()
        page.frame_locator.return_value.locator.return_value.wait_for = \
            AsyncMock(side_effect=TimeoutError('no frame'))
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._upload_video_file(page, '/m/v.mp4'))
        fallback = _loc(page, 'input[type="file"][accept*="video"], input[type="file"]').first
        fallback.wait_for.assert_awaited_once_with(state='attached', timeout=10000)
        fallback.set_input_files.assert_awaited_once_with('/m/v.mp4')
        assert any('upload iframe not found' in str(c) for c in logger.info.call_args_list)


class TestWaitUploadComplete:
    def test_success_first_poll(self):
        page = _mk_page()
        _txt(page, '上传完成').count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._wait_upload_complete(page))
        assert any('检测到「上传完成」' in str(c) for c in logger.info.call_args_list)

    def test_fail_text_raises(self):
        page = _mk_page()
        _txt(page, '上传失败').count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'), \
             pytest.raises(RuntimeError, match='上传失败'):
            _run(BilibiliPlatform._wait_upload_complete(page))

    def test_progress_log_then_success(self):
        page = _mk_page()
        _txt(page, '上传完成').count = AsyncMock(side_effect=[0] * 61 + [1])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._wait_upload_complete(page))
        assert any('仍在上传中' in str(c) for c in logger.info.call_args_list)
        assert any('检测到「上传完成」' in str(c) for c in logger.info.call_args_list)

    def test_probe_exception_logs_at_interval(self):
        page = _mk_page()
        _txt(page, '上传完成').count = AsyncMock(side_effect=[0] * 60 + [ValueError('boom'), 1])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._wait_upload_complete(page))
        assert any('上传状态检查' in str(c) for c in logger.info.call_args_list)

    def test_probe_exception_early_no_log(self):
        page = _mk_page()
        _txt(page, '上传完成').count = AsyncMock(side_effect=[0, ValueError('boom'), 1])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._wait_upload_complete(page))
        assert not any('上传状态检查' in str(c) for c in logger.info.call_args_list)

    def test_timeout_raises(self):
        page = _mk_page()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'), \
             patch('impl.bilibili.platform._UPLOAD_WAIT_POLLS', 60), \
             pytest.raises(TimeoutError, match='上传超时'):
            _run(BilibiliPlatform._wait_upload_complete(page))


# ── DOM 辅助: 标题 / 分区 / 标签 / 简介 ───────────────────────────────────

class TestFillTitle:
    def test_sanitizes_emoji_and_special(self):
        page = _mk_page()
        title_input = _loc(page, _TITLE_INPUT).first
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._fill_title(page, '标题😀<b>&"\'片段'))
        title_input.wait_for.assert_awaited_once_with(state='visible', timeout=15000)
        title_input.click.assert_awaited_once()
        assert title_input.fill.await_args_list[0].args == ('',)
        assert title_input.fill.await_args_list[1].args == ('标题b片段',)
        assert any('标题已过滤特殊字符' in str(c) for c in logger.info.call_args_list)

    def test_plain_title_no_filter_log(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._fill_title(page, '普通标题'))
        assert not any('标题已过滤特殊字符' in str(c) for c in logger.info.call_args_list)


class TestSetCategory:
    def _mk_happy_dom(self, page, cn_name, *, title_hits=1, container_hits=1,
                      drop_ok=True, target_hits=1):
        title = _loc(page, '.section-title-content-main').first
        title.count = AsyncMock(return_value=title_hits)
        title.subs[_XPATH_CONTAINER].count = AsyncMock(return_value=container_hits)
        if not drop_ok:
            _loc(page, '.drop-list-v2-container').first.wait_for = \
                AsyncMock(side_effect=TimeoutError('no drop'))
        _loc(page, f'.drop-list-v2-item[title="{cn_name}"]').count = \
            AsyncMock(return_value=target_hits)
        return title

    def test_none_returns(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_category(page, None))
        assert not logger.info.called

    def test_empty_string_returns(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_category(page, ''))
        assert not logger.info.called

    def test_int_known_happy(self):
        page = _mk_page()
        self._mk_happy_dom(page, '音乐')
        with patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._set_category(page, 3))
        _loc(page, '.drop-list-v2-item[title="音乐"]').first \
            .click.assert_awaited_once_with(force=True)

    def test_int_unknown_skips(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_category(page, 999))
        assert any('unknown category' in str(c) for c in logger.info.call_args_list)

    def test_str_chinese_name(self):
        page = _mk_page()
        self._mk_happy_dom(page, '音乐')
        with patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._set_category(page, '音乐'))
        _loc(page, '.drop-list-v2-item[title="音乐"]').first.click.assert_awaited_once()

    def test_str_digit_tid(self):
        page = _mk_page()
        self._mk_happy_dom(page, '音乐')
        with patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._set_category(page, '3'))
        _loc(page, '.drop-list-v2-item[title="音乐"]').first.click.assert_awaited_once()

    def test_str_digit_unknown_uses_raw(self):
        page = _mk_page()
        self._mk_happy_dom(page, '99999', target_hits=0)
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_category(page, '99999'))
        assert any('partition not found' in str(c) for c in logger.error.call_args_list)

    def test_str_unknown_name_uses_raw(self):
        page = _mk_page()
        self._mk_happy_dom(page, '随便', target_hits=0)
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_category(page, '随便'))
        assert any('partition not found' in str(c) for c in logger.error.call_args_list)
        page.screenshot.assert_awaited_once()

    def test_other_type_skips(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_category(page, 1.5))
        assert any('unknown category' in str(c) for c in logger.info.call_args_list)

    def test_title_missing(self):
        page = _mk_page()
        self._mk_happy_dom(page, '音乐', title_hits=0)
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_category(page, 3))
        assert any("找不到 '分区' section 标题" in str(c) for c in logger.error.call_args_list)
        page.screenshot.assert_awaited_once()

    def test_container_fallback(self):
        page = _mk_page()
        self._mk_happy_dom(page, '音乐', container_hits=0)
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_category(page, 3))
        assert any('ancestor::div[2] 兜底' in str(c) for c in logger.warning.call_args_list)
        fallback = _loc(page, '.section-title-content-main').first.subs[_XPATH_CONTAINER_FALLBACK]
        fallback.subs['.select-controller'].first.click.assert_awaited_once_with(force=True)

    def test_dropdown_timeout_reclick(self):
        page = _mk_page()
        self._mk_happy_dom(page, '音乐', drop_ok=False)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_category(page, 3))
        assert any('下拉未出现' in str(c) for c in logger.warning.call_args_list)
        controller = _loc(page, '.section-title-content-main').first \
            .subs[_XPATH_CONTAINER].subs['.select-controller'].first
        assert controller.click.await_count == 2  # 初始 + 再点一次

    def test_outer_exception_nonfatal(self):
        page = _mk_page()
        title = _loc(page, '.section-title-content-main').first
        title.count = AsyncMock(return_value=1)
        title.subs[_XPATH_CONTAINER].count = AsyncMock(return_value=1)
        title.subs[_XPATH_CONTAINER].subs['.select-controller'].first.wait_for = \
            AsyncMock(side_effect=RuntimeError('boom'))
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_category(page, 3))
        assert any('category setting failed' in str(c) for c in logger.info.call_args_list)


class TestFillTags:
    def test_empty_returns(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._fill_tags(page, []))
        assert not logger.info.called

    def test_parsing(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._fill_tags(page, ['#a #b', 'c,d', 'e', '  ']))
        # '#a #b'→['a','b']; 'c,d'→['c','d']; 'e'; 全空格 str → elif 原样追加 → 共 6 个
        assert any('adding 6 tags' in str(c[0]) for c in logger.info.call_args_list)

    def test_found_first_selector(self):
        page = _mk_page()
        loc = _loc(page, _TAG_SELECTORS[0]).first
        loc.count = AsyncMock(side_effect=[1, 1])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._fill_tags(page, ['标签1']))
        loc.click.assert_awaited_once()
        loc.press_sequentially.assert_awaited_once_with('标签1', delay=100)
        loc.press.assert_awaited_once_with('Enter')
        assert any('found tag input' in str(c[0]) for c in logger.info.call_args_list)

    def test_selector_fallback(self):
        page = _mk_page()
        _loc(page, _TAG_SELECTORS[0]).first.count = AsyncMock(side_effect=[0, 0])
        second = _loc(page, _TAG_SELECTORS[1]).first
        second.count = AsyncMock(side_effect=[1, 1])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._fill_tags(page, ['标签1']))
        assert any(_TAG_SELECTORS[1] in str(c[0]) for c in logger.info.call_args_list)
        second.press_sequentially.assert_awaited_once_with('标签1', delay=100)

    def test_visibility_false_skips_selector(self):
        page = _mk_page()
        first = _loc(page, _TAG_SELECTORS[0]).first
        first.count = AsyncMock(side_effect=[1, 1])
        first.is_visible = AsyncMock(side_effect=[False, False])
        second = _loc(page, _TAG_SELECTORS[1]).first
        second.count = AsyncMock(side_effect=[1, 1])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._fill_tags(page, ['标签1']))
        second.press_sequentially.assert_awaited_once()

    def test_probe_exception_skips_selector(self):
        page = _mk_page()
        _loc(page, _TAG_SELECTORS[0]).first.count = \
            AsyncMock(side_effect=[RuntimeError('boom'), RuntimeError('boom')])
        second = _loc(page, _TAG_SELECTORS[1]).first
        second.count = AsyncMock(side_effect=[1, 1])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._fill_tags(page, ['标签1']))
        second.press_sequentially.assert_awaited_once()

    def test_not_found_screenshot(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._fill_tags(page, ['标签1']))
        assert any('tag input not found' in str(c[0]) for c in logger.info.call_args_list)
        page.screenshot.assert_awaited_once()

    def test_tag_lost_stops(self):
        page = _mk_page()
        loc = _loc(page, _TAG_SELECTORS[0]).first
        loc.count = AsyncMock(side_effect=[1, 1, 0])  # probe / re-locate i0 / re-locate i1
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._fill_tags(page, ['标签1', '标签2']))
        assert any('tag input lost' in str(c[0]) for c in logger.info.call_args_list)
        loc.press_sequentially.assert_awaited_once()  # 只加了第一个

    def test_editable_wait_exception_passed(self):
        page = _mk_page()
        loc = _loc(page, _TAG_SELECTORS[0]).first
        loc.count = AsyncMock(side_effect=[1, 1])
        loc.wait_for = AsyncMock(side_effect=TimeoutError('not editable'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._fill_tags(page, ['标签1']))
        loc.press_sequentially.assert_awaited_once()  # 异常被吞,继续输入

    def test_add_exception_nonfatal(self):
        page = _mk_page()
        loc = _loc(page, _TAG_SELECTORS[0]).first
        loc.count = AsyncMock(side_effect=[1, 1, 1, 1])
        loc.press_sequentially = AsyncMock(side_effect=RuntimeError('type boom'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._fill_tags(page, ['标签1', '标签2']))
        assert any('failed to add tag' in str(c[0]) for c in logger.info.call_args_list)

    def test_truncated_to_10(self):
        page = _mk_page()
        loc = _loc(page, _TAG_SELECTORS[0]).first
        loc.count = AsyncMock(side_effect=[1] * 11)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._fill_tags(page, [f't{i}' for i in range(12)]))
        assert loc.press_sequentially.await_count == 10


class TestFillDesc:
    def test_empty_returns(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._fill_desc(page, ''))
        assert not logger.info.called

    def test_happy(self):
        page = _mk_page()
        editor = _loc(page, _DESC_EDITOR).first
        editor.count = AsyncMock(return_value=1)
        with patch('impl.bilibili.platform.logger'), \
             patch('impl.bilibili.platform.clear_and_type', AsyncMock()) as cat:
            _run(BilibiliPlatform._fill_desc(page, '描述文本'))
        editor.click.assert_awaited_once()
        cat.assert_awaited_once_with(page, '描述文本', delay=10)

    def test_truncated_logs(self):
        page = _mk_page()
        editor = _loc(page, _DESC_EDITOR).first
        editor.count = AsyncMock(return_value=1)
        with patch('impl.bilibili.platform.logger') as logger, \
             patch('impl.bilibili.platform.clear_and_type', AsyncMock()):
            _run(BilibiliPlatform._fill_desc(page, 'a' * 2001))
        assert any('简介已截断' in str(c[0]) for c in logger.info.call_args_list)

    def test_editor_not_found(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._fill_desc(page, '描述'))
        assert any('description editor not found' in str(c[0]) for c in logger.info.call_args_list)

# ── DOM 辅助: 封面 ────────────────────────────────────────────────────────

class TestSetThumbnail:
    def _mk_happy_dom(self, page, *, strategy='normal', dialog_sel=_DIALOG1,
                      sync_checked=False, sync_hits=1, input_hits=1,
                      submit_hits=1, confirm_hits=1, trigger_sel=_TRIGGER1,
                      trigger_hits=1, four_three_hits=1):
        trigger = _loc(page, trigger_sel).first
        trigger.count = AsyncMock(return_value=trigger_hits)
        if strategy == 'normal':
            pass
        elif strategy == 'force':
            trigger.click = AsyncMock(side_effect=[RuntimeError('hit-test'), None])
        elif strategy == 'dispatch':
            trigger.click = AsyncMock(side_effect=[RuntimeError('h1'), RuntimeError('h2'), None])
        dialog = _loc(page, dialog_sel).first
        dialog.wait_for = AsyncMock()  # 弹窗命中
        _loc(page, 'div.cover-editor-panel-canvas-image.editor_4_3').first.count = \
            AsyncMock(return_value=four_three_hits)
        sync = _loc(page, '.sync-checkbox input[type="checkbox"]').first
        sync.count = AsyncMock(return_value=sync_hits)
        sync.is_checked = AsyncMock(return_value=sync_checked)
        _loc(page, '.cover-upload input[type="file"]').first.count = \
            AsyncMock(return_value=input_hits)
        _loc(page, 'div.button.submit').first.count = AsyncMock(return_value=submit_hits)
        dialog.subs['button.bcc-button--primary'].first.count = \
            AsyncMock(return_value=confirm_hits)
        return trigger, dialog

    def test_none_returns(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_thumbnail(page, None))
        assert not logger.info.called

    def test_file_missing_returns(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_thumbnail(page, '/definitely/missing/cover.png'))
        assert any('cover file not found' in str(c[0]) for c in logger.info.call_args_list)

    def test_happy(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            trigger, dialog = self._mk_happy_dom(page)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger') as logger:
                _run(BilibiliPlatform._set_thumbnail(page, path))
            trigger.click.assert_awaited_once_with(timeout=3000)
            dialog.subs['button.bcc-button--primary'].first.click.assert_awaited_once()
            _loc(page, '.cover-upload input[type="file"]').first \
                .set_input_files.assert_awaited_once_with(path)
            page.keyboard.press.assert_awaited_once_with('Escape')
            assert any('cover set successfully' in str(c[0]) for c in logger.info.call_args_list)
        finally:
            os.unlink(path)

    def test_force_strategy(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            trigger, _dialog = self._mk_happy_dom(page, strategy='force')
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger') as logger:
                _run(BilibiliPlatform._set_thumbnail(page, path))
            assert trigger.click.await_count == 2  # normal 失败 → force 成功
            assert any(len(c.args) > 1 and c.args[1] == 'force' for c in logger.info.call_args_list)
        finally:
            os.unlink(path)

    def test_dispatch_strategy(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            trigger, _dialog = self._mk_happy_dom(page, strategy='dispatch')
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger') as logger:
                _run(BilibiliPlatform._set_thumbnail(page, path))
            trigger.dispatch_event.assert_awaited_once_with('click')
            assert any(len(c.args) > 1 and c.args[1] == 'dispatch' for c in logger.info.call_args_list)
        finally:
            os.unlink(path)

    def test_trigger_selector_skip(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            self._mk_happy_dom(page, trigger_sel=_TRIGGER2)  # 第一个触发器缺失
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger'):
                _run(BilibiliPlatform._set_thumbnail(page, path))
            _loc(page, _TRIGGER2).first.click.assert_awaited_once_with(timeout=3000)
        finally:
            os.unlink(path)

    def test_no_trigger_skips(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger') as logger:
                _run(BilibiliPlatform._set_thumbnail(page, path))
            assert any('all cover triggers failed' in str(c[0]) for c in logger.info.call_args_list)
        finally:
            os.unlink(path)

    def test_dialog_fallback_selector(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            self._mk_happy_dom(page)
            _loc(page, _DIALOG1).first.wait_for = \
                AsyncMock(side_effect=TimeoutError('no'))
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger'):
                _run(BilibiliPlatform._set_thumbnail(page, path))
            _loc(page, _DIALOG2).first.wait_for.assert_awaited()  # 弹窗走第二个容器
        finally:
            os.unlink(path)

    def test_dialog_page_fallback(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            self._mk_happy_dom(page)
            for sel in _DIALOG_SELECTORS:
                _loc(page, sel).first.wait_for = AsyncMock(side_effect=TimeoutError('no'))
            _loc(page, 'input[type="file"][accept*="image"]').count = AsyncMock(return_value=1)
            _loc(page, 'button.bcc-button--primary').first.count = AsyncMock(return_value=1)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger'):
                _run(BilibiliPlatform._set_thumbnail(page, path))
            _loc(page, 'button.bcc-button--primary').first.click.assert_awaited_once()
        finally:
            os.unlink(path)

    def test_dialog_missing_raises(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            self._mk_happy_dom(page)
            for sel in _DIALOG_SELECTORS:
                _loc(page, sel).first.wait_for = AsyncMock(side_effect=TimeoutError('no'))
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger'), \
                 pytest.raises(RuntimeError, match='cover setting failed'):
                _run(BilibiliPlatform._set_thumbnail(page, path))
        finally:
            os.unlink(path)

    def test_sync_already_checked_no_label_click(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            self._mk_happy_dom(page, sync_checked=True)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger'):
                _run(BilibiliPlatform._set_thumbnail(page, path))
            _loc(page, '.sync-checkbox').first.click.assert_not_awaited()
        finally:
            os.unlink(path)

    def test_sync_checkbox_missing(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            self._mk_happy_dom(page, sync_hits=0)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger'):
                _run(BilibiliPlatform._set_thumbnail(page, path))
            _loc(page, '.sync-checkbox').first.click.assert_not_awaited()
        finally:
            os.unlink(path)

    def test_four_three_missing(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            self._mk_happy_dom(page, four_three_hits=0)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger'):
                _run(BilibiliPlatform._set_thumbnail(page, path))
            _loc(page, 'div.cover-editor-panel-canvas-image.editor_4_3').first \
                .click.assert_not_awaited()
        finally:
            os.unlink(path)

    def test_fallback_file_input(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            self._mk_happy_dom(page, input_hits=0)
            fallback = _loc(page, 'input[accept*="image"]').first
            fallback.count = AsyncMock(return_value=1)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger'):
                _run(BilibiliPlatform._set_thumbnail(page, path))
            fallback.set_input_files.assert_awaited_once_with(path)
        finally:
            os.unlink(path)

    def test_no_file_input_returns(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            self._mk_happy_dom(page, input_hits=0)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger') as logger:
                _run(BilibiliPlatform._set_thumbnail(page, path))
            assert any('cover file input not found' in str(c[0]) for c in logger.info.call_args_list)
        finally:
            os.unlink(path)

    def test_submit_confirm_missing(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            self._mk_happy_dom(page, submit_hits=0, confirm_hits=0)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger') as logger:
                _run(BilibiliPlatform._set_thumbnail(page, path))
            _loc(page, 'div.button.submit').first.click.assert_not_awaited()
            assert any('cover set successfully' in str(c[0]) for c in logger.info.call_args_list)
        finally:
            os.unlink(path)

    def test_outer_exception_raises(self):
        path = _mk_cover_file()
        try:
            page = _mk_page()
            page.screenshot = AsyncMock(side_effect=RuntimeError('shot fail'))
            self._mk_happy_dom(page)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.bilibili.platform.logger'), \
                 pytest.raises(RuntimeError, match='cover setting failed'):
                _run(BilibiliPlatform._set_thumbnail(page, path))
        finally:
            os.unlink(path)


# ── DOM 辅助: 创作声明 / 合集 / 定时发布 ──────────────────────────────────

class TestSetCreationDeclaration:
    def _mk_options(self, page, text, *, count=1, options_wait_ok=True):
        scoped = _loc(page, _STATEMENT_SCOPE).first
        opts = scoped.subs['li.bcc-option']
        opts.count = AsyncMock(return_value=count)
        opts.nth_subs[0].subs['span'].first.text_content = AsyncMock(return_value=text)
        if not options_wait_ok:
            opts.first.wait_for = AsyncMock(side_effect=TimeoutError('slow'))
        return opts

    def test_empty_returns(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_creation_declaration(page, ''))
        assert not logger.info.called

    def test_happy_direct(self):
        page = _mk_page()
        select = _loc(page, 'input.bcc-select-input-inner[placeholder*="创作声明"]')
        select.count = AsyncMock(return_value=1)
        self._mk_options(page, '原创')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_creation_declaration(page, '原创'))
        select.first.scroll_into_view_if_needed.assert_awaited_once()
        select.first.click.assert_awaited_once_with(force=True)
        opts = _loc(page, _STATEMENT_SCOPE).first.subs['li.bcc-option']
        opts.nth_subs[0].click.assert_awaited_once()
        assert any('selected creation declaration' in str(c[0]) for c in logger.info.call_args_list)

    def test_scoped_fallback(self):
        page = _mk_page()
        select = _loc(page, 'input.bcc-select-input-inner[placeholder*="创作声明"]')
        select.count = AsyncMock(return_value=0)
        scoped_input = _loc(page, _STATEMENT_SCOPE).first \
            .subs['input.bcc-select-input-inner'].first
        scoped_input.count = AsyncMock(return_value=1)
        scoped_input.first = _mk_leaf()  # 代码访问 select_input.first.* → 叶子替身
        self._mk_options(page, '原创')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._set_creation_declaration(page, '原创'))
        scoped_input.first.scroll_into_view_if_needed.assert_awaited_once()
        scoped_input.first.click.assert_awaited_once_with(force=True)

    def test_scoped_missing_skips(self):
        page = _mk_page()
        _loc(page, 'input.bcc-select-input-inner[placeholder*="创作声明"]') \
            .count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_creation_declaration(page, '原创'))
        assert any('not present, skipping' in str(c[0]) for c in logger.info.call_args_list)

    def test_list_wrap_timeout_fallback(self):
        page = _mk_page()
        _loc(page, 'input.bcc-select-input-inner[placeholder*="创作声明"]') \
            .count = AsyncMock(return_value=1)
        self._mk_options(page, '原创')
        _loc(page, '.bcc-select-list-wrap:not([style*="display: none"])').first.wait_for = \
            AsyncMock(side_effect=TimeoutError('no wrap'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._set_creation_declaration(page, '原创'))
        _loc(page, '.bcc-select.is-open, .bcc-select.is-focus, '
                   '.bcc-select[class*="open"], .bcc-select[class*="focus"]') \
            .first.wait_for.assert_awaited_once_with(state='attached', timeout=3000)

    def test_options_wait_exception_passed(self):
        page = _mk_page()
        _loc(page, 'input.bcc-select-input-inner[placeholder*="创作声明"]') \
            .count = AsyncMock(return_value=1)
        opts = self._mk_options(page, '原创', options_wait_ok=False)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._set_creation_declaration(page, '原创'))
        opts.nth_subs[0].click.assert_awaited_once()  # 超时被吞,继续按 count 匹配

    def test_option_not_found(self):
        page = _mk_page()
        _loc(page, 'input.bcc-select-input-inner[placeholder*="创作声明"]') \
            .count = AsyncMock(return_value=1)
        self._mk_options(page, '其它选项')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_creation_declaration(page, '原创'))
        assert any('option not found' in str(c[0]) for c in logger.info.call_args_list)

    def test_repost_source_filled(self):
        page = _mk_page()
        _loc(page, 'input.bcc-select-input-inner[placeholder*="创作声明"]') \
            .count = AsyncMock(return_value=1)
        self._mk_options(page, '内容为转载')
        repost = _loc(page, 'div.statement-source input.input-val').first
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._set_creation_declaration(
                page, '内容为转载', repost_source='https://example.com/src',
            ))
        repost.wait_for.assert_awaited_once_with(state='visible', timeout=3000)
        repost.click.assert_awaited_once()
        repost.fill.assert_awaited_once_with('')
        repost.press_sequentially.assert_awaited_once_with(
            'https://example.com/src', delay=30,
        )

    def test_repost_fill_error_nonfatal(self):
        page = _mk_page()
        _loc(page, 'input.bcc-select-input-inner[placeholder*="创作声明"]') \
            .count = AsyncMock(return_value=1)
        self._mk_options(page, '内容为转载')
        _loc(page, 'div.statement-source input.input-val').first.wait_for = \
            AsyncMock(side_effect=TimeoutError('no repost input'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_creation_declaration(
                page, '内容为转载', repost_source='https://example.com/src',
            ))
        assert any('repost source fill failed' in str(c[0]) for c in logger.info.call_args_list)

    def test_outer_exception_nonfatal(self):
        page = _mk_page()
        page.keyboard.press = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_creation_declaration(page, '原创'))
        assert any('creation declaration failed' in str(c[0]) for c in logger.info.call_args_list)


class TestSetCollection:
    def test_empty_returns(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_collection(page, ''))
        assert not logger.info.called

    def test_entry_missing_skips(self):
        page = _mk_page()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_collection(page, '合集A'))
        assert any('未找到「请选择合集」入口' in str(c[0]) for c in logger.warning.call_args_list)

    def test_happy(self):
        page = _mk_page()
        entry = _txt(page, '请选择合集')
        entry.count = AsyncMock(return_value=1)
        items = _loc(page, '.season-item-title')
        items.count = AsyncMock(return_value=1)
        items.nth_subs[0].inner_text = AsyncMock(return_value='合集A')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_collection(page, '合集A'))
        entry.first.click.assert_awaited_once()
        parent = items.nth_subs[0].subs[_XPATH_SEASON_PARENT]
        parent.first.click.assert_awaited_once_with(timeout=3000)
        assert any('已选择合集' in str(c[0]) for c in logger.info.call_args_list)

    def test_parent_click_fallback(self):
        page = _mk_page()
        entry = _txt(page, '请选择合集')
        entry.count = AsyncMock(return_value=1)
        items = _loc(page, '.season-item-title')
        items.count = AsyncMock(return_value=1)
        items.nth_subs[0].inner_text = AsyncMock(return_value='合集A')
        items.nth_subs[0].subs[_XPATH_SEASON_PARENT].first.click = \
            AsyncMock(side_effect=RuntimeError('stale'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._set_collection(page, '合集A'))
        items.nth_subs[0].click.assert_awaited_once()  # 父级失败 → 直接点选项

    def test_option_not_found(self):
        page = _mk_page()
        entry = _txt(page, '请选择合集')
        entry.count = AsyncMock(return_value=1)
        items = _loc(page, '.season-item-title')
        items.count = AsyncMock(return_value=1)
        items.nth_subs[0].inner_text = AsyncMock(return_value='其他合集')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_collection(page, '合集A'))
        assert any('未找到合集' in str(c[0]) for c in logger.warning.call_args_list)
        page.keyboard.press.assert_awaited_once_with('Escape')

    def test_dropdown_not_ready(self):
        page = _mk_page()
        entry = _txt(page, '请选择合集')
        entry.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_collection(page, '合集A'))
        assert any('下拉浮层未出现' in str(c[0]) for c in logger.warning.call_args_list)

    def test_outer_exception_nonfatal(self):
        page = _mk_page()
        entry = _txt(page, '请选择合集')
        entry.count = AsyncMock(return_value=1)
        entry.first.click = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_collection(page, '合集A'))
        assert any('合集设置失败' in str(c[0]) for c in logger.warning.call_args_list)


class TestSetScheduleTime:
    DT = datetime(2026, 8, 21, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))

    def _mk_happy_dom(self, page, *, date_hits=1, date_classes=('',),
                      date_texts=('21',), hour_hits=1, minute_hits=1):
        date_els = _loc(page, 'div.date-picker-body-item.date-item').filter(has_text='21')
        date_els.count = AsyncMock(return_value=date_hits)
        for i, cls in enumerate(date_classes):
            date_els.nth_subs[i].get_attribute = AsyncMock(return_value=cls)
        for i, text in enumerate(date_texts):
            date_els.nth_subs[i].text_content = AsyncMock(return_value=text)
        panels = _loc(page, '.time-picker-panel-select-wrp')
        hour_item = panels.nth_subs[0].subs['span.time-picker-panel-select-item'] \
            .filter(has_text='10')
        hour_item.count = AsyncMock(return_value=hour_hits)
        minute_item = panels.nth_subs[1].subs['span.time-picker-panel-select-item'] \
            .filter(has_text='05')
        minute_item.count = AsyncMock(return_value=minute_hits)
        return date_els, panels

    def test_zero_returns(self):
        page = _mk_page()
        with patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_schedule_time(page, 0))
        assert not logger.info.called

    def test_happy(self):
        page = _mk_page()
        date_els, panels = self._mk_happy_dom(page)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_schedule_time(page, self.DT))
        date_els.nth_subs[0].click.assert_awaited_once()
        hour_item = panels.nth_subs[0].subs['span.time-picker-panel-select-item'] \
            .filter(has_text='10')
        minute_item = panels.nth_subs[1].subs['span.time-picker-panel-select-item'] \
            .filter(has_text='05')
        hour_item.first.click.assert_awaited_once()
        minute_item.first.click.assert_awaited_once()
        page.keyboard.press.assert_awaited_once_with('Escape')
        assert any('schedule time set' in str(c[0]) for c in logger.info.call_args_list)

    def test_disabled_date_skipped(self):
        page = _mk_page()
        date_els, _panels = self._mk_happy_dom(
            page, date_hits=2, date_classes=('date-item-disabled', ''),
            date_texts=('21', '21'),
        )
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger'):
            _run(BilibiliPlatform._set_schedule_time(page, self.DT))
        date_els.nth_subs[0].click.assert_not_awaited()  # 禁用项跳过
        date_els.nth_subs[1].click.assert_awaited_once()

    def test_date_not_found(self):
        page = _mk_page()
        date_els, _panels = self._mk_happy_dom(page, date_texts=('30',))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_schedule_time(page, self.DT))
        assert any('could not find clickable date' in str(c[0]) for c in logger.info.call_args_list)
        date_els.nth_subs[0].click.assert_not_awaited()

    def test_hour_minute_missing(self):
        page = _mk_page()
        self._mk_happy_dom(page, hour_hits=0, minute_hits=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_schedule_time(page, self.DT))
        # 无小时/分钟项 → 跳过点击,仍完成
        assert any('schedule time set' in str(c[0]) for c in logger.info.call_args_list)

    def test_outer_exception_nonfatal(self):
        page = _mk_page()
        _loc(page, '.switch-container').first.wait_for = \
            AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.bilibili.platform.logger') as logger:
            _run(BilibiliPlatform._set_schedule_time(page, self.DT))
        assert any('schedule time setting failed' in str(c[0]) for c in logger.info.call_args_list)
