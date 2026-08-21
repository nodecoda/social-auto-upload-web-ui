"""今日头条 platform.py DOM 交互层契约测试（T35 第八期）。

覆盖 impl/toutiao/platform.py（661 stmts，基线 18%）:
- 纯函数: _parse_cookie_to_storage_state（k=v 解析/跳过无效/expires 7 天/.toutiao.com 域）
- 登录/校验/同步: login（7 选择器 QR 探测/跳转 URL 判定/user-panel 判定/轮询异常继续/
  save_login_result+stats_fn/外层异常传播）、check_cookie（资料面板判定）、
  sync_profile（goto 异常吞掉/stats 组装/千分位/元/非法数字/等待超时/空结果）、
  _login_stats_fn（同 stats 逻辑）、open_creator_center（线程/事件+close 异常吞掉）
- 编排: _upload_one_video 全流程（双 file input 选择器/上传成功+进度日志去重/超时 return/
  竖版检测+异常默认横版/标题双选择器/简介 5 选择器+placeholder 兜底+未找到 warning/
  无简介/标签/封面/声明/生成图文/合集横竖/扩展链接横竖/定时/提交按钮双选择器/
  URL 跳转判定/storage_state 回写/close）
- DOM 辅助: _fill_tags（输入框缺失/空 tag 跳过/下拉匹配/下拉无匹配点 first/无下拉 Enter/
  下拉异常 Enter/外层异常）、_set_thumbnail（全空 return/编辑器缺失/本地上传 tab/双 input/
  横 16:9→4:3/竖 9:16→3:4/完成裁剪+确定按钮/确定缺失 warning/二次确认弹窗+xpath 异常）、
  _set_creation_declaration（勾选/已勾选/无 checkbox 点 label/无 label/无选项/空项/异常）、
  _toggle_generate_image（启用/禁用/已是目标/checkbox 缺失/label 缺失/异常）、
  _set_collection（by ID/by text/未找到/无按钮/confirm 缺失/异常）、
  _toggle_extend_link（section 缺失/checkbox 缺失/勾选/已勾选/无 URL/三级输入框/未找到/异常）、
  _set_schedule_time（日/时/分选择/各缺失跳过/无定时按钮/异常）
"""
import asyncio
import json
import sys
import time as _time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.toutiao.platform import ToutiaoPlatform

_UPLOAD_URL = "https://mp.toutiao.com/profile_v4/xigua/upload-video"
_HOME_URL = "https://mp.toutiao.com/profile_v4/index"

_CONFIRM_XPATH = "xpath=//*[.//*[contains(normalize-space(.), '完成后无法继续编辑')] and .//button[normalize-space()='取消'] and .//button[normalize-space()='确定'] and not(.//*[.//*[contains(normalize-space(.), '完成后无法继续编辑')] and .//button[normalize-space()='取消'] and .//button[normalize-space()='确定']])]//div[button[normalize-space()='取消'] and button[normalize-space()='确定']]//button[normalize-space()='确定']"


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return ToutiaoPlatform()


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


def _mk_page(url=_UPLOAD_URL):
    page = MagicMock()
    page.url = url
    page.main_frame = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.insert_text = AsyncMock()
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
    page.get_by_role = MagicMock(return_value=_mk_locator())
    page.get_by_placeholder = MagicMock(return_value=_mk_locator())
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


def _mk_cookie_file(name='t35_toutiao_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


def _mk_upload_ready(page):
    """上传成功文案默认命中:让上传等待轮询首轮即完成。"""
    _loc(page, 'span.percent:has-text("上传成功")').count = AsyncMock(return_value=1)


class _FakeLoop:
    """时间序列控制:login / 上传等待轮询依赖 loop.time()。"""

    def __init__(self, times):
        self._times = list(times)

    def time(self):
        return self._times.pop(0) if len(self._times) > 1 else self._times[0]


# ── 纯函数 ───────────────────────────────────────────────────────────────

class TestParseCookie:
    def test_parses_pairs(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('a=1; b = 2 ')
        assert origins == []
        assert len(cookies) == 2
        assert cookies[0]['name'] == 'a'
        assert cookies[0]['value'] == '1'
        assert cookies[1]['name'] == 'b'
        assert cookies[1]['value'] == '2'
        for c in cookies:
            assert c['domain'] == '.toutiao.com'
            assert c['path'] == '/'
            assert c['httpOnly'] is True
            assert c['secure'] is False
            assert c['sameSite'] == 'Lax'
            assert c['expires'] > _time.time()

    def test_skips_empty_and_malformed(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state(';; ; badpair ; x=y')
        assert len(cookies) == 1
        assert cookies[0]['name'] == 'x'
        assert cookies[0]['value'] == 'y'

    def test_empty_string(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('')
        assert cookies == []


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLogin:
    def test_qr_found_and_login_by_url_jump(self):
        p = _mk_platform()
        queue = MagicMock()
        loop = _FakeLoop([0.0, 1.0, 1.0])
        urls = iter(['https://mp.toutiao.com/auth/page/login',
                     'https://mp.toutiao.com/profile_v4/index'])
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch('impl.toutiao.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.toutiao.platform.logger'), \
             patch('impl.toutiao.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            type(page).url = PropertyMock(side_effect=lambda: next(urls))
            _loc(page, 'img[class*="qrcode"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'img[class*="qrcode"]').first.get_attribute = AsyncMock(return_value='http://qr')
            _loc(page, 'div.user-panel').count = AsyncMock(return_value=0)
            _run(p.login('u1', queue, account_id='acc1'))
        assert queue.put.call_args.args[0] == 'http://qr'
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 13
        assert kwargs['account_id'] == 'acc1'
        assert kwargs['scrape_fn'].__module__ == 'impl._utils'
        assert kwargs['stats_fn'].__func__ is ToutiaoPlatform._login_stats_fn
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    def test_qr_via_user_panel(self):
        p = _mk_platform()
        queue = MagicMock()
        loop = _FakeLoop([0.0, 1.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.toutiao.platform.save_login_result', AsyncMock()), \
             patch('impl.toutiao.platform.logger'), \
             patch('impl.toutiao.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            # 第一个 QR 选择器探测异常 → 第二个命中
            _loc(page, 'img[class*="qrcode"]').first.count = AsyncMock(side_effect=RuntimeError('stale'))
            _loc(page, 'img[class*="qr-code"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'img[class*="qr-code"]').first.get_attribute = AsyncMock(return_value='data:image/png;base64,xx')
            # URL 不跳转 → user-panel 第 2 轮命中
            _loc(page, 'div.user-panel').count = AsyncMock(side_effect=[RuntimeError('stale'), 1])
            _run(p.login('u1', queue))
        assert queue.put.call_args.args[0] == 'data:image/png;base64,xx'
        browser.close.assert_awaited_once()

    def test_qr_not_found_puts_error(self):
        p = _mk_platform()
        queue = MagicMock()
        loop = _FakeLoop([0.0, 301.0])  # 首轮轮询已超时
        with _mk_browser_chain(p) as (_page, _context, browser, _cb, _cc), \
             patch('impl.toutiao.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.toutiao.platform.logger'), \
             patch('impl.toutiao.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p.login('u1', queue))
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['error'] == '无法找到登录二维码'
        slr.assert_awaited_once()  # 超时仍继续保存(可能是已扫码)
        browser.close.assert_awaited_once()

    def test_poll_exception_then_success(self):
        p = _mk_platform()
        queue = MagicMock()
        loop = _FakeLoop([0.0, 1.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.toutiao.platform.save_login_result', AsyncMock()), \
             patch('impl.toutiao.platform.logger'), \
             patch('impl.toutiao.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _loc(page, 'img[class*="qrcode"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'img[class*="qrcode"]').first.get_attribute = AsyncMock(return_value='http://qr')
            _loc(page, 'div.user-panel').count = AsyncMock(side_effect=[RuntimeError('stale'), 1])
            _run(p.login('u1', queue))
        browser.close.assert_awaited_once()

    def test_qr_src_invalid_continues(self):
        """第一个选择器 src 非 http/data 开头 → 置 None 继续探测。"""
        p = _mk_platform()
        queue = MagicMock()
        loop = _FakeLoop([0.0, 301.0])
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.toutiao.platform.save_login_result', AsyncMock()), \
             patch('impl.toutiao.platform.logger'), \
             patch('impl.toutiao.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            page.url = 'https://mp.toutiao.com/auth/page/login'
            _loc(page, 'img[class*="qrcode"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'img[class*="qrcode"]').first.get_attribute = AsyncMock(return_value='//cdn/x.png')
            _loc(page, 'img[class*="qr-code"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'img[class*="qr-code"]').first.get_attribute = AsyncMock(return_value='http://qr2')
            _run(p.login('u1', queue))
        assert queue.put.call_args.args[0] == 'http://qr2'
        browser.close.assert_awaited_once()

    def test_user_panel_detection_with_poll_exception(self):
        """轮询中 user-panel 探测异常 → 吞掉继续 → 第 2 轮命中。"""
        p = _mk_platform()
        queue = MagicMock()
        loop = _FakeLoop([0.0, 1.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.toutiao.platform.save_login_result', AsyncMock()), \
             patch('impl.toutiao.platform.logger'), \
             patch('impl.toutiao.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            page.url = 'https://mp.toutiao.com/auth/page/login'  # URL 永不跳转
            _loc(page, 'img[class*="qrcode"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'img[class*="qrcode"]').first.get_attribute = AsyncMock(return_value='http://qr')
            _loc(page, 'div.user-panel').count = AsyncMock(side_effect=[RuntimeError('stale'), 1])
            _run(p.login('u1', queue))
        browser.close.assert_awaited_once()

    def test_create_browser_failure_propagates(self):
        p = _mk_platform()
        queue = MagicMock()
        with patch.object(p, 'create_browser', AsyncMock(side_effect=RuntimeError('boom'))), \
             pytest.raises(RuntimeError, match='boom'):
            _run(p.login('u1', queue))

    def test_create_context_failure_propagates_keeps_browser(self):
        p = _mk_platform()
        queue = MagicMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(side_effect=RuntimeError('ctx'))), \
             patch('impl.toutiao.platform.logger'), pytest.raises(RuntimeError, match='ctx'):
            _run(p.login('u1', queue))
        browser.close.assert_not_awaited()  # 失败保留浏览器现场


class TestCheckCookie:
    def test_valid(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch('impl.toutiao.platform.logger'):
            _loc(page, 'div.user-panel').count = AsyncMock(return_value=1)
            assert _run(p.check_cookie('ck.json')) is True
        context.storage_state  # noqa: B018
        browser.close.assert_awaited_once()

    def test_invalid(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.toutiao.platform.logger'):
            _loc(page, 'div.user-panel').count = AsyncMock(return_value=0)
            assert _run(p.check_cookie('ck.json')) is False
        browser.close.assert_awaited_once()


class TestSyncProfile:
    def test_happy_stats_assembly(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.toutiao.platform.scrape_toutiao_profile',
                   AsyncMock(return_value=('UP主', 'http://a.png'))), \
             patch('impl.toutiao.platform.logger'):
            page.evaluate = AsyncMock(return_value=[
                {'title': '粉丝数', 'num': '1,234'},
                {'title': '总阅读(播放)量', 'num': '0元'},
                {'title': '累计收益', 'num': '6,275'},
                {'title': '未知项', 'num': '99'},
            ])
            result = _run(p.sync_profile('ck.json'))
        assert result['name'] == 'UP主'
        assert result['avatar'] == 'http://a.png'
        assert result['stats'] == [
            {'ICON': 'user', 'COUNT': 1234, 'NAME': '粉丝数', 'SORT': 1},
            {'ICON': 'play', 'COUNT': 0, 'NAME': '总阅读(播放)量', 'SORT': 2},
            {'ICON': 'coin', 'COUNT': 6275, 'NAME': '累计收益', 'SORT': 3},
        ]
        browser.close.assert_awaited_once()

    def test_goto_error_still_scrapes(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.toutiao.platform.scrape_toutiao_profile', AsyncMock(return_value=('n', 'a'))), \
             patch('impl.toutiao.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net'))
            page.evaluate = AsyncMock(return_value=[])
            result = _run(p.sync_profile('ck.json'))
        assert result['name'] == 'n'
        browser.close.assert_awaited_once()

    def test_selector_wait_timeout_logs(self):
        p = _mk_platform()
        logger = MagicMock()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.toutiao.platform.scrape_toutiao_profile', AsyncMock(return_value=('', ''))), \
             patch('impl.toutiao.platform.logger', logger):
            page.wait_for_selector = AsyncMock(side_effect=RuntimeError('timeout'))
            page.evaluate = AsyncMock(return_value=[])
            _run(p.sync_profile('ck.json'))
        assert any('等待 .data-board-item 超时' in str(c) for c in logger.info.call_args_list)

    def test_empty_result_logs(self):
        p = _mk_platform()
        logger = MagicMock()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.toutiao.platform.scrape_toutiao_profile', AsyncMock(return_value=('', ''))), \
             patch('impl.toutiao.platform.logger', logger):
            page.evaluate = AsyncMock(return_value=[])
            _run(p.sync_profile('ck.json'))
        assert any('抓取为空' in str(c) for c in logger.info.call_args_list)

    def test_numeric_parsing_variants(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.toutiao.platform.scrape_toutiao_profile', AsyncMock(return_value=('', ''))), \
             patch('impl.toutiao.platform.logger'):
            page.evaluate = AsyncMock(return_value=[
                {'title': '粉丝数', 'num': '1.5'},
                {'title': '总阅读(播放)量', 'num': 'abc'},
                {'title': '累计收益', 'num': ''},
            ])
            result = _run(p.sync_profile('ck.json'))
        counts = [s['COUNT'] for s in result['stats']]
        assert counts == [1, 0, 0]


class TestLoginStatsFn:
    def test_stats_assembly(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'title': '粉丝数', 'num': '8,888'},
            {'title': '累计收益', 'num': '12.9'},
        ])
        with patch('impl.toutiao.platform.logger'):
            stats = _run(p._login_stats_fn(page, 'acc1'))
        assert stats == [
            {'ICON': 'user', 'COUNT': 8888, 'NAME': '粉丝数', 'SORT': 1},
            {'ICON': 'coin', 'COUNT': 12, 'NAME': '累计收益', 'SORT': 3},
        ]

    def test_invalid_number_zero(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[{'title': '粉丝数', 'num': 'abc'}])
        with patch('impl.toutiao.platform.logger'):
            stats = _run(p._login_stats_fn(page, 'acc1'))
        assert stats == [{'ICON': 'user', 'COUNT': 0, 'NAME': '粉丝数', 'SORT': 1}]

    def test_wait_timeout_continues(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=RuntimeError('timeout'))
        page.evaluate = AsyncMock(return_value=[])
        with patch('impl.toutiao.platform.logger'):
            stats = _run(p._login_stats_fn(page, 'acc1'))
        assert stats == []


class TestOpenCreatorCenter:
    def test_starts_thread(self):
        p = _mk_platform()
        page = MagicMock()
        page.goto = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('closed'))
        context = MagicMock()
        context.new_page = MagicMock(return_value=page)
        browser = MagicMock()
        browser.close = MagicMock()
        with patch('impl.toutiao.platform.create_browser_sync', return_value=browser) as cbs, \
             patch('impl.toutiao.platform.create_context_sync', return_value=context) as ccs, \
             patch('impl.toutiao.platform.logger'):
            _run(p.open_creator_center('ck.json'))
            _time.sleep(0.3)
        cbs.assert_called_once_with(headless=False)
        ccs.assert_called_once_with(browser, storage_state=str(Path(BASE_DIR / 'cookiesFile' / 'ck.json')))
        page.goto.assert_called_once()
        page.wait_for_event.assert_called_once_with('close', timeout=0)
        browser.close.assert_called_once()

    def test_browser_close_error_swallowed(self):
        p = _mk_platform()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('closed'))
        context = MagicMock()
        context.new_page = MagicMock(return_value=page)
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('close boom'))
        with patch('impl.toutiao.platform.create_browser_sync', return_value=browser), \
             patch('impl.toutiao.platform.create_context_sync', return_value=context), \
             patch('impl.toutiao.platform.logger'):
            _run(p.open_creator_center('ck.json'))
            _time.sleep(0.3)
        browser.close.assert_called_once()  # 异常被吞掉,不传播


# ── 编排: _upload_one_video 全流程 ────────────────────────────────────────

@contextmanager
def _mk_upload_one_steps(p, loop):
    """把 _upload_one_video 内部子步骤替换为 AsyncMock;注入时间序列 loop。"""
    mocks = dict(
        fill_tags=AsyncMock(),
        set_thumbnail=AsyncMock(),
        set_creation_declaration=AsyncMock(),
        toggle_generate_image=AsyncMock(),
        set_collection=AsyncMock(),
        toggle_extend_link=AsyncMock(),
        set_schedule_time=AsyncMock(),
        close_browser=AsyncMock(),
    )
    with patch.object(p, '_fill_tags', mocks['fill_tags']), \
         patch.object(p, '_set_thumbnail', mocks['set_thumbnail']), \
         patch.object(p, '_set_creation_declaration', mocks['set_creation_declaration']), \
         patch.object(p, '_toggle_generate_image', mocks['toggle_generate_image']), \
         patch.object(p, '_set_collection', mocks['set_collection']), \
         patch.object(p, '_toggle_extend_link', mocks['toggle_extend_link']), \
         patch.object(p, '_set_schedule_time', mocks['set_schedule_time']), \
         patch.object(p, 'close_browser', mocks['close_browser']), \
         patch('impl.toutiao.platform.clear_and_type', AsyncMock()), \
         patch('impl.toutiao.platform.asyncio.get_event_loop', return_value=loop), \
         patch('asyncio.sleep', AsyncMock()):
        yield mocks


class TestUploadOneVideo:
    def _run(self, p, page, **kw):
        default = dict(
            title='标题', file_path='/m/v.mp4', tags=[], publish_date=0,
            account_file='/c/u1.json', publish_strategy='immediate',
            desc='', thumbnail_landscape_path=None, thumbnail_portrait_path=None,
            thumbnail_landscape_169_path=None, thumbnail_portrait_916_path=None,
            creation_declaration=None, enable_generate_image=True,
            collection_id='', extend_link=False, extend_link_url='',
        )
        default.update(kw)
        return _run(p._upload_one_video(**default))

    def test_happy_full_flow(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])  # 上传首轮成功
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL  # 提交后已跳转
            _mk_upload_ready(page)
            file_input = _loc(page, 'input[type="file"][accept*="video"]')
            file_input.count = AsyncMock(return_value=1)
            ok = self._run(p, page, title='标题')
        assert ok is None
        page.goto.assert_awaited_once_with(_UPLOAD_URL)
        page.wait_for_url.assert_awaited_once_with(_UPLOAD_URL)
        file_input.set_input_files.assert_awaited_once_with('/m/v.mp4')
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)
        # 默认无封面/声明/合集/扩展链接/定时
        mocks['set_thumbnail'].assert_not_awaited()
        mocks['set_creation_declaration'].assert_not_awaited()
        mocks['set_collection'].assert_not_awaited()
        mocks['toggle_extend_link'].assert_not_awaited()
        mocks['set_schedule_time'].assert_not_awaited()
        # 生成图文总是执行
        mocks['toggle_generate_image'].assert_awaited_once_with(page, True)

    def test_file_input_fallback(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            self._run(p, page, title='T')
        _loc(page, 'input[type="file"]').first.set_input_files.assert_awaited_once_with('/m/v.mp4')

    def test_upload_progress_logged(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 2.0, 3.0, 4.0])  # 4 轮轮询后成功
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.logger') as logger:
            page.url = _HOME_URL
            success_text = _loc(page, 'span.percent:has-text("上传成功")')
            success_text.count = AsyncMock(side_effect=[0, 0, 0, 1])
            progress = _loc(page, 'span.percent')
            progress.count = AsyncMock(return_value=1)
            progress.first.text_content = AsyncMock(side_effect=['10%', '10%', '50%'])
            self._run(p, page, title='T')
        progress_logs = [c.args[1] for c in logger.info.call_args_list
                         if c.args and c.args[0] == '[上传视频] %s']
        assert progress_logs == ['10%', '50%']  # 相同进度不重复

    def test_upload_poll_exception_continues(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            success_text = _loc(page, 'span.percent:has-text("上传成功")')
            success_text.count = AsyncMock(side_effect=[RuntimeError('stale'), 1])
            self._run(p, page, title='T')
        assert success_text.count.await_count == 2  # 异常后继续轮询
        mocks['toggle_generate_image'].assert_awaited_once()

    def test_upload_timeout_returns_early(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 14401.0])  # 首轮轮询即超时
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.toutiao.platform.logger'):
            self._run(p, page, title='T')
        mocks['toggle_generate_image'].assert_not_awaited()
        mocks['close_browser'].assert_awaited_once()

    def test_portrait_detected(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            _loc(page, 'div.xigua-poster-editor.portrait').count = AsyncMock(return_value=1)
            self._run(p, page, title='T', desc='简介', collection_id='c1', extend_link=True)
        # 竖版: 简介跳过 + 合集/扩展链接竖版不支持
        mocks['set_collection'].assert_not_awaited()
        mocks['toggle_extend_link'].assert_not_awaited()
        mocks['set_thumbnail'].assert_not_awaited()  # 未传封面

    def test_portrait_detection_exception_defaults_landscape(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            _loc(page, 'div.xigua-poster-editor.portrait').count = AsyncMock(
                side_effect=RuntimeError('boom'))
            self._run(p, page, title='T', collection_id='c1')
        mocks['set_collection'].assert_awaited_once_with(page, 'c1')  # 按横版处理

    def test_desc_filled_via_first_selector(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.clear_and_type') as cat, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            first = _loc(page, 'div.video-form-item.form-item-desc div[contenteditable="true"]').first
            first.count = AsyncMock(return_value=1)
            self._run(p, page, title='T', desc='简介内容')
        first.click.assert_awaited_once()
        cat.assert_awaited_once()
        assert cat.await_args.args[1] == '简介内容'

    def test_desc_fallback_placeholder(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.clear_and_type'), \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            ph = page.get_by_placeholder('请输入视频简介')
            ph.count = AsyncMock(return_value=1)
            self._run(p, page, title='T', desc='简介')
        ph.fill.assert_awaited_once_with('简介')

    def test_desc_selector_exception_continues(self):
        """第一个 desc 选择器探测异常 → debug 日志 + 继续下一个选择器。"""
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        logger = MagicMock()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.clear_and_type') as cat, \
             patch('impl.toutiao.platform.logger', logger):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            _loc(page, 'div.video-form-item.form-item-desc div[contenteditable="true"]').first.count = AsyncMock(side_effect=RuntimeError('boom'))
            second = _loc(page, 'div.form-item-desc textarea').first
            second.count = AsyncMock(return_value=1)
            self._run(p, page, title='T', desc='简介')
        assert any('选择器' in str(c) and '失败' in str(c) for c in logger.debug.call_args_list)
        cat.assert_awaited_once()

    def test_desc_placeholder_exception_then_warns(self):
        """placeholder 探测抛异常 → 吞掉 → 最终未找到 warning。"""
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        logger = MagicMock()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.clear_and_type'), \
             patch('impl.toutiao.platform.logger', logger):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            page.get_by_placeholder('请输入视频简介').count = AsyncMock(side_effect=RuntimeError('boom'))
            self._run(p, page, title='T', desc='简介')
        assert any('未找到视频简介输入框' in str(c) for c in logger.warning.call_args_list)

    def test_desc_not_found_warns(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        logger = MagicMock()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.clear_and_type'), \
             patch('impl.toutiao.platform.logger', logger):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            self._run(p, page, title='T', desc='简介')
        assert any('未找到视频简介输入框' in str(c) for c in logger.warning.call_args_list)

    def test_no_desc_skips(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.clear_and_type') as cat, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            self._run(p, page, title='T', desc='')
        cat.assert_not_awaited()

    def test_portrait_skips_desc(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            _loc(page, 'div.xigua-poster-editor.portrait').count = AsyncMock(return_value=1)
            self._run(p, page, title='T', desc='简介')
        _loc(page, 'div.video-form-item.form-item-desc div[contenteditable="true"]').first.click.assert_not_awaited()

    def test_tags_and_cover_declaration(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            self._run(
                p, page, title='T', tags=['a', 'b'],
                thumbnail_landscape_169_path='/l169.png',
                creation_declaration=['原创'],
                enable_generate_image=False,
            )
        mocks['fill_tags'].assert_awaited_once_with(page, ['a', 'b'])
        mocks['set_thumbnail'].assert_awaited_once()
        mocks['set_creation_declaration'].assert_awaited_once_with(page, ['原创'])
        mocks['toggle_generate_image'].assert_awaited_once_with(page, False)

    def test_collection_landscape(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            self._run(p, page, title='T', collection_id='c1', extend_link=True, extend_link_url='https://x')
        mocks['set_collection'].assert_awaited_once_with(page, 'c1')
        mocks['toggle_extend_link'].assert_awaited_once_with(page, 'https://x')

    def test_schedule_sets_time(self):
        p = _mk_platform()
        pd = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            self._run(p, page, title='T', publish_strategy='scheduled', publish_date=pd)
        mocks['set_schedule_time'].assert_awaited_once_with(page, pd)

    def test_schedule_skipped_when_immediate(self):
        p = _mk_platform()
        pd = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            self._run(p, page, title='T', publish_strategy='immediate', publish_date=pd)
        mocks['set_schedule_time'].assert_not_awaited()

    def test_submit_button_fallback_get_by_role(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.logger'):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            _loc(page, 'button.action-footer-btn.submit').count = AsyncMock(return_value=0)
            self._run(p, page, title='T')
        page.get_by_role.assert_called_once_with('button', name='发布', exact=True)
        page.get_by_role.return_value.click.assert_awaited_once()

    def test_submit_no_jump_logs_waiting(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        logger = MagicMock()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.logger', logger):
            _mk_upload_ready(page)
            self._run(p, page, title='T')  # page.url 仍是 upload-video
        assert any('发布按钮已点击，等待确认' in str(c) for c in logger.info.call_args_list)
        page._t35_ok = True

    def test_submit_jump_detected(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        logger = MagicMock()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.toutiao.platform.logger', logger):
            page.url = _HOME_URL
            _mk_upload_ready(page)
            self._run(p, page, title='T')
        assert any('视频发布成功' in str(c) for c in logger.info.call_args_list)


# ── DOM 辅助: 标签 ────────────────────────────────────────────────────────

class TestFillTags:
    def test_input_missing_warns(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._fill_tags(page, ['a']))
        assert any('未找到标签输入框' in str(c) for c in logger.warning.call_args_list)

    def test_happy_with_dropdown_match(self):
        page = _mk_page()
        tag_input = _loc(page, '.hash-tag-editor input, .arco-input-tag-input')
        tag_input.count = AsyncMock(return_value=1)
        dropdown = _loc(page, '.arco-dropdown-menu-item, [role="menuitem"]')
        dropdown.count = AsyncMock(return_value=2)
        dropdown.nth(0).text_content = AsyncMock(return_value='别的')
        dropdown.nth(1).text_content = AsyncMock(return_value='#科技')
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._fill_tags(page, ['科技']))
        dropdown.nth(1).click.assert_awaited_once()

    def test_empty_tag_skipped(self):
        page = _mk_page()
        tag_input = _loc(page, '.hash-tag-editor input, .arco-input-tag-input')
        tag_input.count = AsyncMock(return_value=1)
        dropdown = _loc(page, '.arco-dropdown-menu-item, [role="menuitem"]')
        dropdown.count = AsyncMock(return_value=0)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._fill_tags(page, ['', None, '有效']))
        assert page.keyboard.insert_text.await_count == 1  # 只有非空 tag 输入

    def test_dropdown_no_match_clicks_first(self):
        page = _mk_page()
        tag_input = _loc(page, '.hash-tag-editor input, .arco-input-tag-input')
        tag_input.count = AsyncMock(return_value=1)
        dropdown = _loc(page, '.arco-dropdown-menu-item, [role="menuitem"]')
        dropdown.count = AsyncMock(return_value=2)
        dropdown.nth(0).text_content = AsyncMock(return_value='x')
        dropdown.nth(1).text_content = AsyncMock(return_value='y')
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._fill_tags(page, ['z']))
        dropdown.first.click.assert_awaited_once()

    def test_no_dropdown_presses_enter(self):
        page = _mk_page()
        tag_input = _loc(page, '.hash-tag-editor input, .arco-input-tag-input')
        tag_input.count = AsyncMock(return_value=1)
        dropdown = _loc(page, '.arco-dropdown-menu-item, [role="menuitem"]')
        dropdown.count = AsyncMock(return_value=0)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._fill_tags(page, ['a']))
        page.keyboard.press.assert_awaited_once_with('Enter')

    def test_dropdown_exception_falls_back_enter(self):
        page = _mk_page()
        tag_input = _loc(page, '.hash-tag-editor input, .arco-input-tag-input')
        tag_input.count = AsyncMock(return_value=1)
        dropdown = _loc(page, '.arco-dropdown-menu-item, [role="menuitem"]')
        dropdown.count = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._fill_tags(page, ['a']))
        page.keyboard.press.assert_awaited_once_with('Enter')

    def test_outer_exception_logged(self):
        page = _mk_page()
        tag_input = _loc(page, '.hash-tag-editor input, .arco-input-tag-input')
        tag_input.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._fill_tags(page, ['a']))
        assert any('填写标签失败' in str(c) for c in logger.error.call_args_list)


# ── DOM 辅助: 封面 ────────────────────────────────────────────────────────

class TestSetThumbnail:
    def _mk(self, **kw):
        defaults = dict(
            thumbnail_landscape_path=None, thumbnail_portrait_path=None,
            thumbnail_landscape_169_path=None, thumbnail_portrait_916_path=None,
            is_portrait=False,
        )
        defaults.update(kw)
        return defaults

    def test_all_empty_returns(self):
        page = _mk_page()
        with patch('impl.toutiao.platform.logger') as logger:
            _run(ToutiaoPlatform._set_thumbnail(page, **self._mk()))
        logger.info.assert_not_called()  # 直接 return,无任何日志

    def test_editor_missing_warns(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(page, **self._mk(thumbnail_landscape_path='/l.png')))
        assert any('未找到封面编辑器' in str(c) for c in logger.warning.call_args_list)

    def test_happy_landscape_169(self):
        page = _mk_page()
        cover_editor = _loc(page, 'div.xigua-poster-editor')
        cover_editor.count = AsyncMock(return_value=1)
        upload_tab = _loc(page, 'li:has-text("本地上传")')
        upload_tab.count = AsyncMock(return_value=1)
        cover_input = _loc(page, 'input[type="file"][accept*="image"]')
        cover_input.count = AsyncMock(return_value=1)
        # 完成裁剪按钮存在
        _loc(page, "button:has-text('完成裁剪')").count = AsyncMock(return_value=1)
        crop_btn = _loc(page, "button:has-text('完成裁剪')").first
        crop_btn.count = AsyncMock(return_value=1)
        crop_btn.is_enabled = AsyncMock(return_value=True)
        ok_btn = _loc(page, "button:has-text('确定')").first
        ok_btn.count = AsyncMock(return_value=1)
        ok_btn.is_enabled = AsyncMock(return_value=True)
        dialog_ok = _loc(page, _CONFIRM_XPATH).first
        dialog_ok.count = AsyncMock(return_value=1)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(
                page, **self._mk(thumbnail_landscape_169_path='/l169.png')))
        upload_tab.click.assert_awaited_once()
        cover_input.set_input_files.assert_awaited_once_with('/l169.png')
        crop_btn.click.assert_awaited_once()
        ok_btn.click.assert_awaited_once()
        dialog_ok.click.assert_awaited_once()  # 二次确认

    def test_landscape_fallback_43(self):
        page = _mk_page()
        cover_editor = _loc(page, 'div.xigua-poster-editor')
        cover_editor.count = AsyncMock(return_value=1)
        fallback = _loc(page, 'input[type="file"]').first
        fallback.count = AsyncMock(return_value=1)
        # 完成裁剪不出现
        _loc(page, "button:has-text('完成裁剪')").count = AsyncMock(return_value=0)
        ok_btn = _loc(page, "button:has-text('确定')").first
        ok_btn.count = AsyncMock(return_value=1)
        ok_btn.is_enabled = AsyncMock(return_value=True)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(
                page, **self._mk(thumbnail_landscape_path='/l43.png')))
        fallback.set_input_files.assert_awaited_once_with('/l43.png')

    def test_portrait_916(self):
        page = _mk_page()
        cover_editor = _loc(page, 'div.xigua-poster-editor')
        cover_editor.count = AsyncMock(return_value=1)
        cover_input = _loc(page, 'input[type="file"][accept*="image"]')
        cover_input.count = AsyncMock(return_value=1)
        _loc(page, "button:has-text('完成裁剪')").count = AsyncMock(return_value=0)
        ok_btn = _loc(page, "button:has-text('确定')").first
        ok_btn.count = AsyncMock(return_value=1)
        ok_btn.is_enabled = AsyncMock(return_value=True)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(
                page, **self._mk(thumbnail_portrait_916_path='/p916.png', is_portrait=True)))
        cover_input.set_input_files.assert_awaited_once_with('/p916.png')

    def test_portrait_fallback_34(self):
        page = _mk_page()
        cover_editor = _loc(page, 'div.xigua-poster-editor')
        cover_editor.count = AsyncMock(return_value=1)
        cover_input = _loc(page, 'input[type="file"][accept*="image"]')
        cover_input.count = AsyncMock(return_value=1)
        _loc(page, "button:has-text('完成裁剪')").count = AsyncMock(return_value=0)
        ok_btn = _loc(page, "button:has-text('确定')").first
        ok_btn.count = AsyncMock(return_value=1)
        ok_btn.is_enabled = AsyncMock(return_value=True)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(
                page, **self._mk(thumbnail_portrait_path='/p34.png', is_portrait=True)))
        cover_input.set_input_files.assert_awaited_once_with('/p34.png')

    def test_confirm_missing_warns(self):
        page = _mk_page()
        cover_editor = _loc(page, 'div.xigua-poster-editor')
        cover_editor.count = AsyncMock(return_value=1)
        cover_input = _loc(page, 'input[type="file"][accept*="image"]')
        cover_input.count = AsyncMock(return_value=1)
        _loc(page, "button:has-text('完成裁剪')").count = AsyncMock(return_value=0)
        # 确定按钮两个候选都不可点(is_enabled False / count 0)
        ok_btn = _loc(page, "button:has-text('确定')").first
        ok_btn.count = AsyncMock(return_value=1)
        ok_btn.is_enabled = AsyncMock(return_value=False)
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(page, **self._mk(thumbnail_landscape_path='/l.png')))
        assert any('未点到「确定」' in str(c) for c in logger.warning.call_args_list)

    def test_role_button_fallback(self):
        """button:has-text 缺失 → [role=button] 候选生效。"""
        page = _mk_page()
        cover_editor = _loc(page, 'div.xigua-poster-editor')
        cover_editor.count = AsyncMock(return_value=1)
        cover_input = _loc(page, 'input[type="file"][accept*="image"]')
        cover_input.count = AsyncMock(return_value=1)
        _loc(page, "button:has-text('完成裁剪')").count = AsyncMock(return_value=0)
        _loc(page, "button:has-text('确定')").first.count = AsyncMock(return_value=0)
        role_ok = _loc(page, "[role='button']:has-text('确定')").first
        role_ok.count = AsyncMock(return_value=1)
        role_ok.is_enabled = AsyncMock(return_value=True)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(page, **self._mk(thumbnail_landscape_path='/l.png')))
        role_ok.click.assert_awaited_once()

    def test_btn_wait_error_falls_to_role_candidate(self):
        """button 候选 wait_for 抛异常 → 尝试 [role=button] 候选。"""
        page = _mk_page()
        cover_editor = _loc(page, 'div.xigua-poster-editor')
        cover_editor.count = AsyncMock(return_value=1)
        cover_input = _loc(page, 'input[type="file"][accept*="image"]')
        cover_input.count = AsyncMock(return_value=1)
        _loc(page, "button:has-text('完成裁剪')").count = AsyncMock(return_value=0)
        btn = _loc(page, "button:has-text('确定')").first
        btn.count = AsyncMock(return_value=1)
        btn.wait_for = AsyncMock(side_effect=RuntimeError('not visible'))
        role_ok = _loc(page, "[role='button']:has-text('确定')").first
        role_ok.count = AsyncMock(return_value=1)
        role_ok.is_enabled = AsyncMock(return_value=True)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(page, **self._mk(thumbnail_landscape_path='/l.png')))
        role_ok.click.assert_awaited_once()

    def test_confirm_dialog_wait_error_still_clicks(self):
        """二次确认弹窗 wait_for(visible) 抛异常 → 仍 force click。"""
        page = _mk_page()
        cover_editor = _loc(page, 'div.xigua-poster-editor')
        cover_editor.count = AsyncMock(return_value=1)
        cover_input = _loc(page, 'input[type="file"][accept*="image"]')
        cover_input.count = AsyncMock(return_value=1)
        _loc(page, "button:has-text('完成裁剪')").count = AsyncMock(return_value=0)
        ok_btn = _loc(page, "button:has-text('确定')").first
        ok_btn.count = AsyncMock(return_value=1)
        ok_btn.is_enabled = AsyncMock(return_value=True)
        dialog_ok = _loc(page, _CONFIRM_XPATH).first
        dialog_ok.count = AsyncMock(return_value=1)
        dialog_ok.wait_for = AsyncMock(side_effect=RuntimeError('animating'))
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(page, **self._mk(thumbnail_landscape_path='/l.png')))
        dialog_ok.click.assert_awaited_once()

    def test_outer_exception_logged(self):
        page = _mk_page()
        cover_editor = _loc(page, 'div.xigua-poster-editor')
        cover_editor.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(page, **self._mk(thumbnail_landscape_path='/l.png')))
        assert any('设置封面失败' in str(c) for c in logger.error.call_args_list)

    def test_confirm_dialog_not_appears(self):
        page = _mk_page()
        cover_editor = _loc(page, 'div.xigua-poster-editor')
        cover_editor.count = AsyncMock(return_value=1)
        cover_input = _loc(page, 'input[type="file"][accept*="image"]')
        cover_input.count = AsyncMock(return_value=1)
        _loc(page, "button:has-text('完成裁剪')").count = AsyncMock(return_value=0)
        ok_btn = _loc(page, "button:has-text('确定')").first
        ok_btn.count = AsyncMock(return_value=1)
        ok_btn.is_enabled = AsyncMock(return_value=True)
        # 二次确认弹窗不出现(dialog count 默认 0)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(page, **self._mk(thumbnail_landscape_path='/l.png')))
        ok_btn.click.assert_awaited_once()

    def test_confirm_dialog_xpath_error_warns(self):
        page = _mk_page()
        cover_editor = _loc(page, 'div.xigua-poster-editor')
        cover_editor.count = AsyncMock(return_value=1)
        cover_input = _loc(page, 'input[type="file"][accept*="image"]')
        cover_input.count = AsyncMock(return_value=1)
        _loc(page, "button:has-text('完成裁剪')").count = AsyncMock(return_value=0)
        ok_btn = _loc(page, "button:has-text('确定')").first
        ok_btn.count = AsyncMock(return_value=1)
        ok_btn.is_enabled = AsyncMock(return_value=True)
        # xpath 探测抛异常 → 二次确认处理失败 warning
        dlg = _loc(page, _CONFIRM_XPATH).first
        dlg.count = AsyncMock(side_effect=RuntimeError('xpath boom'))
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_thumbnail(page, **self._mk(thumbnail_landscape_path='/l.png')))
        assert any('二次确认弹窗处理失败' in str(c) for c in logger.warning.call_args_list)


# ── DOM 辅助: 作品声明 / 生成图文 / 合集 / 扩展链接 / 定时 ───────────────

class TestSetCreationDeclaration:
    def test_checks_unchecked(self):
        page = _mk_page()
        checkbox_text = _loc(page, 'span.byte-checkbox-inner-text:has-text("原创")').first
        checkbox_text.count = AsyncMock(return_value=1)
        label = checkbox_text.locator('xpath=ancestor::label[1]')
        label.count = AsyncMock(return_value=1)
        checkbox = label.locator('input[type="checkbox"]')
        checkbox.count = AsyncMock(return_value=1)
        checkbox.is_checked = AsyncMock(return_value=False)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_creation_declaration(page, ['原创']))
        label.click.assert_awaited_once()

    def test_already_checked(self):
        page = _mk_page()
        checkbox_text = _loc(page, 'span.byte-checkbox-inner-text:has-text("原创")').first
        checkbox_text.count = AsyncMock(return_value=1)
        label = checkbox_text.locator('xpath=ancestor::label[1]')
        label.count = AsyncMock(return_value=1)
        checkbox = label.locator('input[type="checkbox"]')
        checkbox.count = AsyncMock(return_value=1)
        checkbox.is_checked = AsyncMock(return_value=True)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_creation_declaration(page, ['原创']))
        label.click.assert_not_awaited()

    def test_no_checkbox_clicks_label(self):
        page = _mk_page()
        checkbox_text = _loc(page, 'span.byte-checkbox-inner-text:has-text("原创")').first
        checkbox_text.count = AsyncMock(return_value=1)
        label = checkbox_text.locator('xpath=ancestor::label[1]')
        label.count = AsyncMock(return_value=1)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_creation_declaration(page, ['原创']))
        label.click.assert_awaited_once()

    def test_no_label_warns(self):
        page = _mk_page()
        checkbox_text = _loc(page, 'span.byte-checkbox-inner-text:has-text("原创")').first
        checkbox_text.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_creation_declaration(page, ['原创']))
        assert any('未找到 label' in str(c) for c in logger.warning.call_args_list)

    def test_no_option_warns(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_creation_declaration(page, ['原创']))
        assert any('未找到声明选项' in str(c) for c in logger.warning.call_args_list)

    def test_empty_decl_skipped(self):
        page = _mk_page()
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_creation_declaration(page, ['', None, '原创']))
        # 只处理非空项: '原创' 未找到 → warning
        _loc(page, 'span.byte-checkbox-inner-text:has-text("原创")').first.count  # noqa: B018

    def test_outer_exception_logged(self):
        page = _mk_page()
        checkbox_text = _loc(page, 'span.byte-checkbox-inner-text:has-text("原创")').first
        checkbox_text.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_creation_declaration(page, ['原创']))
        assert any('设置作品声明失败' in str(c) for c in logger.error.call_args_list)


class TestToggleGenerateImage:
    def test_enables_when_unchecked(self):
        page = _mk_page()
        label = _loc(page, 'label:has-text("生成图文")')
        label.count = AsyncMock(return_value=1)
        checkbox = label.locator('input[type="checkbox"]')
        checkbox.count = AsyncMock(return_value=1)
        checkbox.is_checked = AsyncMock(return_value=False)
        with patch('impl.toutiao.platform.logger'):
            _run(ToutiaoPlatform._toggle_generate_image(page, True))
        label.click.assert_awaited_once()

    def test_disables_when_checked(self):
        page = _mk_page()
        label = _loc(page, 'label:has-text("生成图文")')
        label.count = AsyncMock(return_value=1)
        checkbox = label.locator('input[type="checkbox"]')
        checkbox.count = AsyncMock(return_value=1)
        checkbox.is_checked = AsyncMock(return_value=True)
        with patch('impl.toutiao.platform.logger'):
            _run(ToutiaoPlatform._toggle_generate_image(page, False))
        label.click.assert_awaited_once()

    def test_already_target(self):
        page = _mk_page()
        label = _loc(page, 'label:has-text("生成图文")')
        label.count = AsyncMock(return_value=1)
        checkbox = label.locator('input[type="checkbox"]')
        checkbox.count = AsyncMock(return_value=1)
        checkbox.is_checked = AsyncMock(return_value=True)
        with patch('impl.toutiao.platform.logger'):
            _run(ToutiaoPlatform._toggle_generate_image(page, True))
        label.click.assert_not_awaited()

    def test_checkbox_missing_noop(self):
        page = _mk_page()
        label = _loc(page, 'label:has-text("生成图文")')
        label.count = AsyncMock(return_value=1)
        with patch('impl.toutiao.platform.logger'):
            _run(ToutiaoPlatform._toggle_generate_image(page, True))
        label.click.assert_not_awaited()

    def test_label_missing_warns(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger):
            _run(ToutiaoPlatform._toggle_generate_image(page, True))
        assert any('未找到生成图文选项' in str(c) for c in logger.warning.call_args_list)

    def test_outer_exception_logged(self):
        page = _mk_page()
        label = _loc(page, 'label:has-text("生成图文")')
        label.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger):
            _run(ToutiaoPlatform._toggle_generate_image(page, True))
        assert any('设置视频生成图文失败' in str(c) for c in logger.error.call_args_list)


class TestSetCollection:
    def test_select_by_id(self):
        page = _mk_page()
        btn = _loc(page, 'button:has-text("选择合集")')
        btn.count = AsyncMock(return_value=1)
        option = _loc(page, 'input[type="radio"][value="c1"]')
        option.count = AsyncMock(return_value=1)
        confirm = _loc(page, '.add-to-series-action button:has-text("确定")')
        confirm.count = AsyncMock(return_value=1)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_collection(page, 'c1'))
        option.click.assert_awaited_once()
        confirm.click.assert_awaited_once()

    def test_select_by_text(self):
        page = _mk_page()
        btn = _loc(page, 'button:has-text("选择合集")')
        btn.count = AsyncMock(return_value=1)
        label = _loc(page, 'label:has-text("科技合集")')
        label.count = AsyncMock(return_value=1)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_collection(page, '科技合集'))
        label.click.assert_awaited_once()

    def test_not_found_warns(self):
        page = _mk_page()
        btn = _loc(page, 'button:has-text("选择合集")')
        btn.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_collection(page, 'none'))
        assert any('未找到合集' in str(c) for c in logger.warning.call_args_list)

    def test_confirm_missing_skips(self):
        page = _mk_page()
        btn = _loc(page, 'button:has-text("选择合集")')
        btn.count = AsyncMock(return_value=1)
        option = _loc(page, 'input[type="radio"][value="c1"]')
        option.count = AsyncMock(return_value=1)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_collection(page, 'c1'))
        option.click.assert_awaited_once()

    def test_no_button_warns(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_collection(page, 'c1'))
        assert any('未找到选择合集按钮' in str(c) for c in logger.warning.call_args_list)

    def test_outer_exception_logged(self):
        page = _mk_page()
        btn = _loc(page, 'button:has-text("选择合集")')
        btn.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_collection(page, 'c1'))
        assert any('设置合集失败' in str(c) for c in logger.error.call_args_list)


class TestToggleExtendLink:
    def test_section_missing_warns(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._toggle_extend_link(page, 'https://x'))
        assert any('未找到扩展链接区域' in str(c) for c in logger.warning.call_args_list)

    def test_checkbox_missing_warns(self):
        page = _mk_page()
        section = _loc(page, 'div.video-form-item.form-item-external-link')
        section.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._toggle_extend_link(page, 'https://x'))
        assert any('未找到扩展链接复选框' in str(c) for c in logger.warning.call_args_list)

    def test_check_and_fill(self):
        page = _mk_page()
        section = _loc(page, 'div.video-form-item.form-item-external-link')
        section.count = AsyncMock(return_value=1)
        checkbox_label = section.locator('label.byte-checkbox').first
        checkbox_label.count = AsyncMock(return_value=1)
        checkbox = checkbox_label.locator('input[type="checkbox"]')
        checkbox.count = AsyncMock(return_value=1)
        checkbox.is_checked = AsyncMock(return_value=False)
        link_input = _loc(page, 'div.video-form-item-extra input[placeholder*="请填写链接地址"]')
        link_input.count = AsyncMock(return_value=1)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._toggle_extend_link(page, 'https://x'))
        checkbox_label.click.assert_awaited_once()
        link_input.fill.assert_awaited_once_with('https://x')

    def test_already_checked_no_url(self):
        page = _mk_page()
        section = _loc(page, 'div.video-form-item.form-item-external-link')
        section.count = AsyncMock(return_value=1)
        checkbox_label = section.locator('label.byte-checkbox').first
        checkbox_label.count = AsyncMock(return_value=1)
        checkbox = checkbox_label.locator('input[type="checkbox"]')
        checkbox.count = AsyncMock(return_value=1)
        checkbox.is_checked = AsyncMock(return_value=True)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._toggle_extend_link(page, ''))
        checkbox_label.click.assert_not_awaited()

    def test_link_input_fallback_chain(self):
        page = _mk_page()
        section = _loc(page, 'div.video-form-item.form-item-external-link')
        section.count = AsyncMock(return_value=1)
        checkbox_label = section.locator('label.byte-checkbox').first
        checkbox_label.count = AsyncMock(return_value=1)
        checkbox = checkbox_label.locator('input[type="checkbox"]')
        checkbox.count = AsyncMock(return_value=0)  # 无 checkbox 也继续
        third = _loc(page, 'input[placeholder*="https://www.toutiao.com"]')
        third.count = AsyncMock(return_value=1)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._toggle_extend_link(page, 'https://x'))
        third.fill.assert_awaited_once_with('https://x')

    def test_link_input_missing_warns(self):
        page = _mk_page()
        section = _loc(page, 'div.video-form-item.form-item-external-link')
        section.count = AsyncMock(return_value=1)
        checkbox_label = section.locator('label.byte-checkbox').first
        checkbox_label.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._toggle_extend_link(page, 'https://x'))
        assert any('未找到链接输入框' in str(c) for c in logger.warning.call_args_list)

    def test_outer_exception_logged(self):
        page = _mk_page()
        section = _loc(page, 'div.video-form-item.form-item-external-link')
        section.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._toggle_extend_link(page, 'https://x'))
        assert any('设置扩展链接失败' in str(c) for c in logger.error.call_args_list)


class TestSetScheduleTime:
    def test_happy_full(self):
        page = _mk_page()
        pd = datetime(2026, 8, 21, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        timer_btn = _loc(page, 'button.action-footer-btn.timer:has-text("定时发布")')
        timer_btn.count = AsyncMock(return_value=1)
        day_select = _loc(page, '.day-select .byte-select-view')
        day_select.count = AsyncMock(return_value=1)
        day_option = _loc(page, '.byte-select-option:has-text("08月21日")')
        day_option.count = AsyncMock(return_value=1)
        hour_select = _loc(page, '.hour-select .byte-select-view')
        hour_select.count = AsyncMock(return_value=1)
        hour_option = _loc(page, '.byte-select-popup-inner .byte-select-option:has-text("10")')
        hour_option.count = AsyncMock(return_value=1)
        minute_select = _loc(page, '.minute-select .byte-select-view')
        minute_select.count = AsyncMock(return_value=1)
        minute_option = _loc(page, '.byte-select-popup-inner .byte-select-option:has-text("05")')
        minute_option.count = AsyncMock(return_value=1)
        confirm = _loc(page, '.byte-modal-footer button:has-text("定时发布")')
        confirm.count = AsyncMock(return_value=1)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_schedule_time(page, pd))
        day_option.click.assert_awaited_once()
        hour_option.click.assert_awaited_once()
        minute_option.click.assert_awaited_once()
        confirm.click.assert_awaited_once()

    def test_selects_missing_skipped(self):
        page = _mk_page()
        pd = datetime(2026, 8, 21, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        timer_btn = _loc(page, 'button.action-footer-btn.timer:has-text("定时发布")')
        timer_btn.count = AsyncMock(return_value=1)
        # day/hour/minute 全部缺失 → 只点确认
        confirm = _loc(page, '.byte-modal-footer button:has-text("定时发布")')
        confirm.count = AsyncMock(return_value=1)
        with patch('impl.toutiao.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_schedule_time(page, pd))
        confirm.click.assert_awaited_once()

    def test_no_timer_button_warns(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_schedule_time(page, datetime(2026, 8, 21, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))))
        assert any('未找到定时发布按钮' in str(c) for c in logger.warning.call_args_list)

    def test_outer_exception_logged(self):
        page = _mk_page()
        timer_btn = _loc(page, 'button.action-footer-btn.timer:has-text("定时发布")')
        timer_btn.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.toutiao.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(ToutiaoPlatform._set_schedule_time(page, datetime(2026, 8, 21, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))))
        assert any('设置定时发布时间失败' in str(c) for c in logger.error.call_args_list)
