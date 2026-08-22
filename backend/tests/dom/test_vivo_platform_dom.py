"""VIVO platform.py DOM 交互层契约测试（T35 第七期）。

覆盖 impl/vivo/platform.py（523 stmts，基线 19%）:
- 登录/校验/同步: login（QR 轮询 .user-info-area/超时 failed+保留浏览器/轮询异常继续/
  save_login_result+stats_fn/外层异常 traceback+failed/context close 异常吞掉）
  / check_cookie（资料卡判定/无效 False） / sync_profile（goto 异常吞掉/3 项 stats 组装）
  / _login_stats_fn（goto 异常吞掉/抓取异常空） / open_creator_center（线程/事件+close 异常吞掉）
- 编排: _upload_one_video 全流程（双 file input 选择器/上传成功+进度日志/上传超时 return/
  desc+tags 拼接 500 截断/双 contenteditable 选择器/无描述/封面/位置/作品同步/声明/双 radio/
  定时/提交按钮双选择器/URL 跳转判定/提交超时 warning/回写/dry_run 提前 return/close）
- DOM 辅助: _set_cover（封面图入口/弹窗容器/上传封面 tab 激活判断/input 双选择器/裁剪区轮询/
  确定 div/异常吞掉） / _set_location（入口/键盘输入/下拉轮询/精确匹配/第一项兜底/异常吞掉）
  / _toggle_distribution（勾选/取消/已是目标/checkbox 缺失/异常吞掉） / _set_declaration（触发器双选择器/
  选项匹配/Escape 关闭/异常吞掉） / _set_radio_by_label（字段区块/选项/aria-checked+is-checked/异常吞掉）
  / _set_schedule_time（定时 radio/日期编辑器/双 input fill/确定按钮双选择器/异常吞掉）
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
from impl.vivo.platform import (
    _UPLOAD_MAX_WAIT,
    _VIVO_HOME_URL,
    _VIVO_UPLOAD_URL,
    VivoPlatform,
)


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return VivoPlatform()


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


def _mk_page(url=_VIVO_UPLOAD_URL):
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
    page.get_by_role = MagicMock(return_value=_mk_locator())
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


def _mk_cookie_file(name='t35_vivo_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


def _mk_upload_ready(page):
    """上传成功文案默认命中:让上传等待轮询首轮即完成。"""
    _loc(page, '.success-text:has-text("上传成功")').count = AsyncMock(return_value=1)


class _FakeLoop:
    """时间序列控制:login / 上传等待 / 提交跳转轮询都依赖 loop.time()。"""

    def __init__(self, times):
        self._times = list(times)

    def time(self):
        return self._times.pop(0) if len(self._times) > 1 else self._times[0]


@contextmanager
def _mk_upload_one_steps(p, loop):
    """把 _upload_one_video 内部子步骤替换为 AsyncMock;注入时间序列 loop。"""
    mocks = dict(
        set_cover=AsyncMock(),
        set_location=AsyncMock(),
        toggle_distribution=AsyncMock(),
        set_declaration=AsyncMock(),
        set_radio=AsyncMock(),
        set_schedule=AsyncMock(),
        close_browser=AsyncMock(),
    )
    with patch.object(p, '_set_cover', mocks['set_cover']), \
         patch.object(p, '_set_location', mocks['set_location']), \
         patch.object(p, '_toggle_distribution', mocks['toggle_distribution']), \
         patch.object(p, '_set_declaration', mocks['set_declaration']), \
         patch.object(p, '_set_radio_by_label', mocks['set_radio']), \
         patch.object(p, '_set_schedule_time', mocks['set_schedule']), \
         patch.object(p, 'close_browser', mocks['close_browser']), \
         patch('impl.vivo.platform.asyncio.get_event_loop', return_value=loop), \
         patch('asyncio.sleep', AsyncMock()):
        yield mocks


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLogin:
    def test_success_via_profile_card(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch('impl.vivo.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.vivo.platform.logger'):
            _loc(page, '.user-info-area').count = AsyncMock(return_value=1)
            loop = _FakeLoop([0.0, 1.0])
            with patch('impl.vivo.platform.asyncio.get_event_loop', return_value=loop), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(p.login('u1', MagicMock(), account_id='acc1'))
        page.goto.assert_awaited_once_with(
            _VIVO_HOME_URL, wait_until='domcontentloaded', timeout=30000,
        )
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 16
        assert kwargs['account_id'] == 'acc1'
        assert kwargs['stats_fn'].__func__ is VivoPlatform._login_stats_fn
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()  # 成功才关

    def test_timeout_keeps_browser(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, context, browser, _cb, _cc), \
             patch('impl.vivo.platform.logger'):
            queue = MagicMock()
            loop = _FakeLoop([0.0, 1.0, 300.0])  # 第二次轮询已超时
            with patch('impl.vivo.platform.asyncio.get_event_loop', return_value=loop), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(p.login('u1', queue))
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['status'] == 'failed'
        assert '登录超时' in payload['message']
        context.close.assert_awaited_once()
        browser.close.assert_not_awaited()  # 失败保留浏览器看现场

    def test_poll_exception_then_success(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.vivo.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.vivo.platform.logger'):
            _loc(page, '.user-info-area').count = AsyncMock(
                side_effect=[RuntimeError('stale'), 1]
            )
            loop = _FakeLoop([0.0, 1.0, 2.0])
            with patch('impl.vivo.platform.asyncio.get_event_loop', return_value=loop), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(p.login('u1', MagicMock()))
        slr.assert_awaited_once()
        browser.close.assert_awaited_once()

    def test_goto_error_still_waits(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.vivo.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.vivo.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            _loc(page, '.user-info-area').count = AsyncMock(return_value=1)
            loop = _FakeLoop([0.0, 1.0])
            with patch('impl.vivo.platform.asyncio.get_event_loop', return_value=loop), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(p.login('u1', MagicMock()))
        slr.assert_awaited_once()  # goto 异常吞掉,仍等资料卡

    def test_create_context_exception_puts_failed(self):
        """create_browser 在 try 块外(异常直接传播);create_context 异常走外层兜底。"""
        p = _mk_platform()
        queue = MagicMock()
        browser = MagicMock()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context',
                          AsyncMock(side_effect=RuntimeError('ctx boom'))), \
             patch('impl.vivo.platform.logger'):
            _run(p.login('u1', queue))
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['status'] == 'failed'
        assert 'ctx boom' in payload['message']

    def test_create_browser_failure_propagates(self):
        """create_browser 在 try 块外:异常直接冒泡,不入 status_queue。"""
        p = _mk_platform()
        queue = MagicMock()
        with patch.object(p, 'create_browser',
                          AsyncMock(side_effect=RuntimeError('browser boom'))), \
             patch('impl.vivo.platform.logger'), pytest.raises(RuntimeError, match='browser boom'):
            _run(p.login('u1', queue))
        queue.put.assert_not_called()

    def test_context_close_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch('impl.vivo.platform.save_login_result', AsyncMock()), \
             patch('impl.vivo.platform.logger'):
            context.close = AsyncMock(side_effect=RuntimeError('boom'))
            _loc(page, '.user-info-area').count = AsyncMock(return_value=1)
            loop = _FakeLoop([0.0, 1.0])
            with patch('impl.vivo.platform.asyncio.get_event_loop', return_value=loop), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(p.login('u1', MagicMock()))  # 不抛异常
            browser.close.assert_awaited_once()

    def test_browser_close_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.vivo.platform.save_login_result', AsyncMock()), \
             patch('impl.vivo.platform.logger'):
            browser.close = AsyncMock(side_effect=RuntimeError('boom'))
            _loc(page, '.user-info-area').count = AsyncMock(return_value=1)
            loop = _FakeLoop([0.0, 1.0])
            with patch('impl.vivo.platform.asyncio.get_event_loop', return_value=loop), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(p.login('u1', MagicMock()))  # 不抛异常


class TestCheckCookie:
    def test_valid(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.vivo.platform.logger'):
            _loc(page, '.user-info-area').count = AsyncMock(return_value=1)
            assert _run(p.check_cookie('ck.json')) is True
        page.goto.assert_awaited_once_with(
            _VIVO_HOME_URL, wait_until='domcontentloaded', timeout=15000,
        )
        browser.close.assert_awaited_once()

    def test_invalid(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             patch('impl.vivo.platform.logger'):
            assert _run(p.check_cookie('ck.json')) is False


class TestSyncProfile:
    def test_happy(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, browser, _cb, _cc), \
             patch('impl.vivo.platform.scrape_vivo_profile',
                   AsyncMock(return_value=('UP主', 'http://a.png', 100, 200, 300))), \
             patch('impl.vivo.platform.logger'):
            res = _run(p.sync_profile('ck.json'))
        assert res == {
            'name': 'UP主', 'avatar': 'http://a.png',
            'stats': [
                {'ICON': 'user', 'COUNT': 100, 'NAME': '粉丝', 'SORT': 1},
                {'ICON': 'like', 'COUNT': 200, 'NAME': '获赞', 'SORT': 2},
                {'ICON': 'follow', 'COUNT': 300, 'NAME': '关注', 'SORT': 3},
            ],
        }
        browser.close.assert_awaited_once()

    def test_goto_error_still_scrapes(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.vivo.platform.scrape_vivo_profile',
                   AsyncMock(return_value=('n', '', 0, 0, 0))) as sp, \
             patch('impl.vivo.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            res = _run(p.sync_profile('ck.json'))
        assert res['name'] == 'n'
        sp.assert_awaited_once()


class TestLoginStatsFn:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.vivo.platform.scrape_vivo_profile',
                   AsyncMock(return_value=('n', '', 1, 2, 3))), \
             patch('impl.vivo.platform.logger'):
            stats = _run(p._login_stats_fn(page, 'acc1'))
        assert [s['SORT'] for s in stats] == [1, 2, 3]
        assert stats[0]['COUNT'] == 1

    def test_goto_error_still_scrapes(self):
        p = _mk_platform()
        page = _mk_page()
        page.goto = AsyncMock(side_effect=RuntimeError('net down'))
        with patch('impl.vivo.platform.scrape_vivo_profile',
                   AsyncMock(return_value=('n', '', 0, 0, 0))) as sp, \
             patch('impl.vivo.platform.logger'):
            assert _run(p._login_stats_fn(page, 'acc1')) != []
        sp.assert_awaited_once()

    def test_scrape_exception_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.vivo.platform.scrape_vivo_profile',
                   AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('impl.vivo.platform.logger'):
            assert _run(p._login_stats_fn(page, 'acc1')) == []


class TestOpenCreatorCenter:
    def test_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_vivo_occ.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.vivo.platform.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl.vivo.platform.create_context_sync', return_value=context) as ccs, \
                 patch('impl.vivo.platform.logger'):
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
        cookie = _mk_cookie_file('t35_vivo_occ2.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.vivo.platform.create_browser_sync', return_value=browser), \
                 patch('impl.vivo.platform.create_context_sync', return_value=context), \
                 patch('impl.vivo.platform.logger'):
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
        cookie = _mk_cookie_file('t35_vivo_occ3.json')
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('boom'))
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.vivo.platform.create_browser_sync', return_value=browser), \
                 patch('impl.vivo.platform.create_context_sync', return_value=context), \
                 patch('impl.vivo.platform.logger'):
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
            title='标题', file_path='/m/v.mp4', tags=[], desc='',
            publish_date=0, publish_strategy='immediate',
            account_file='/c/u1.json',
            thumbnail_portrait_path=None, thumbnail_landscape_path=None,
            vivo_location_name='', vivo_distribution=False,
            vivo_declaration='', vivo_privacy='公开', vivo_download_permission='允许',
            dry_run=False,
        )
        default.update(kw)
        return _run(p._upload_one_video(**default))

    def test_happy_full_flow(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 0.0, 1.0])  # 上传首轮成功 + 提交首轮跳转
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.vivo.platform.logger'):
            page.url = _VIVO_HOME_URL  # 提交后已跳转
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            file_input = _loc(page, 'input[type="file"][accept*="video"]')
            file_input.count = AsyncMock(return_value=1)  # 主选择器存在
            ok = self._run(p, page, title='标题')
        assert ok is None
        page.goto.assert_awaited_once_with(_VIVO_UPLOAD_URL)
        file_input.set_input_files.assert_awaited_once_with('/m/v.mp4')
        success_text = _loc(page, '.success-text:has-text("上传成功")')
        assert success_text.count.await_count >= 1
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)
        # 无封面/位置/声明/非定时 → 相关步骤跳过
        mocks['set_cover'].assert_not_awaited()
        mocks['set_location'].assert_not_awaited()
        mocks['set_declaration'].assert_not_awaited()
        mocks['set_schedule'].assert_not_awaited()
        # 作品同步 + 双 radio 总是执行
        mocks['toggle_distribution'].assert_awaited_once_with(page, False)
        assert mocks['set_radio'].await_count == 2

    def test_file_input_fallback(self):
        """accept*="video" 不存在 → 回退 input[type="file"]。"""
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.vivo.platform.logger'):
            page.url = _VIVO_HOME_URL
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            self._run(p, page, title='T')
        _loc(page, 'input[type="file"]').first.set_input_files.assert_awaited_once_with('/m/v.mp4')

    def test_upload_progress_logged(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 2.0, 3.0, 4.0])  # 4 轮轮询后成功
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.vivo.platform.logger') as logger:
            page.url = _VIVO_HOME_URL
            success_text = _loc(page, '.success-text:has-text("上传成功")')
            success_text.count = AsyncMock(side_effect=[0, 0, 0, 1])
            progress = _loc(page, '.upload-progress').first
            progress.count = AsyncMock(return_value=1)
            progress.text_content = AsyncMock(side_effect=['10%', '10%', '50%'])
            self._run(p, page, title='T')
        progress_logs = [c.args for c in logger.info.call_args_list
                        if c.args and c.args[0] == '[上传视频] 进度: %s']
        # 10% 出现一次,50% 出现一次;相同进度不重复记录
        assert progress_logs == [
            ('[上传视频] 进度: %s', '10%'),
            ('[上传视频] 进度: %s', '50%'),
        ]

    def test_upload_poll_exception_continues(self):
        """轮询中 success-text 探测抛异常 → except 吞掉继续 → 下一轮成功。"""
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 1.0])  # start 0, 两轮轮询(首轮异常,次轮成功)
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.vivo.platform.logger'):
            page.url = _VIVO_HOME_URL
            success_text = _loc(page, '.success-text:has-text("上传成功")')
            success_text.count = AsyncMock(side_effect=[RuntimeError('stale'), 1])
            self._run(p, page, title='T')
        assert success_text.count.await_count == 2  # 异常后继续轮询
        mocks['toggle_distribution'].assert_awaited_once()  # 上传成功继续后续步骤

    def test_upload_timeout_returns_early(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, float(_UPLOAD_MAX_WAIT) + 1])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.vivo.platform.logger'):
            self._run(p, page, title='T')
        # 超时直接 return:后续步骤全部跳过
        mocks['toggle_distribution'].assert_not_awaited()
        mocks['close_browser'].assert_awaited_once()

    def test_desc_with_tags_and_space(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.vivo.platform.logger'):
            page.url = _VIVO_HOME_URL
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            desc_editor = _loc(page, '.rich-text [contenteditable="true"].add-text').first
            desc_editor.count = AsyncMock(return_value=1)
            self._run(p, page, title='T', desc='简介', tags=['a', 'b'])
        desc_editor.click.assert_awaited_once()
        assert desc_editor.press_sequentially.await_args.args[0] == '简介 #a #b'
        page.keyboard.press.assert_awaited_once_with(' ')

    def test_desc_fallback_editor(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.vivo.platform.logger'):
            page.url = _VIVO_HOME_URL
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            _loc(page, '.rich-text [contenteditable="true"].add-text').first.count = AsyncMock(return_value=0)
            fallback = _loc(page, '.rich-text [contenteditable="true"]').first
            fallback.count = AsyncMock(return_value=1)
            self._run(p, page, title='T', desc='简介')
        fallback.click.assert_awaited_once()

    def test_desc_editor_missing_warns(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 0.0, 1.0])
        logger = MagicMock()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.vivo.platform.logger', logger):
            page.url = _VIVO_HOME_URL
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            self._run(p, page, title='T', desc='简介')
        assert any('未找到描述输入框' in str(c) for c in logger.warning.call_args_list)

    def test_no_desc_skips_editor(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.vivo.platform.logger'):
            page.url = _VIVO_HOME_URL
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            self._run(p, page, title='T', desc='', tags=[])
        _loc(page, '.rich-text [contenteditable="true"].add-text').first.click.assert_not_awaited()

    def test_covers_location_declaration_schedule(self):
        p = _mk_platform()
        pd = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        loop = _FakeLoop([0.0, 1.0, 0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.vivo.platform.logger'):
            page.url = _VIVO_HOME_URL
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            self._run(
                p, page, title='T',
                thumbnail_portrait_path='/p.png', thumbnail_landscape_path='/l.png',
                vivo_location_name='上海', vivo_declaration='原创',
                publish_strategy='scheduled', publish_date=pd,
            )
        mocks['set_cover'].assert_awaited_once_with(page, '/p.png')
        mocks['set_location'].assert_awaited_once_with(page, '上海')
        mocks['set_declaration'].assert_awaited_once_with(page, '原创')
        mocks['set_schedule'].assert_awaited_once_with(page, pd)

    def test_cover_landscape_fallback(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.vivo.platform.logger'):
            page.url = _VIVO_HOME_URL
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            self._run(p, page, title='T', thumbnail_landscape_path='/l.png')
        mocks['set_cover'].assert_awaited_once_with(page, '/l.png')

    def test_schedule_skipped_when_immediate(self):
        p = _mk_platform()
        pd = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        loop = _FakeLoop([0.0, 1.0, 0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.vivo.platform.logger'):
            page.url = _VIVO_HOME_URL
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            self._run(p, page, title='T', publish_strategy='immediate', publish_date=pd)
        mocks['set_schedule'].assert_not_awaited()

    def test_submit_button_fallback_get_by_role(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 0.0, 1.0])
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.vivo.platform.logger'):
            page.url = _VIVO_HOME_URL
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            _loc(page, '.btns button.el-button--primary:has-text("提交")').count = AsyncMock(return_value=0)
            self._run(p, page, title='T')
        page.get_by_role.assert_called_once_with('button', name='提交', exact=True)
        page.get_by_role.return_value.click.assert_awaited_once()

    def test_submit_no_jump_warns(self):
        """提交后 URL 未跳转 → 60s 超时 → warning,仍回写 cookie。"""
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0, 0.0, 1.0, 60.0])
        logger = MagicMock()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as _mocks, \
             patch('impl.vivo.platform.logger', logger):
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            self._run(p, page, title='T')  # page.url 仍是 uploads
        assert any('未检测到页面跳转' in str(c) for c in logger.warning.call_args_list)
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')

    def test_dry_run_returns_before_submit(self):
        p = _mk_platform()
        loop = _FakeLoop([0.0, 1.0])
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             _mk_upload_one_steps(p, loop) as mocks, \
             patch('impl.vivo.platform.logger'):
            _mk_upload_ready(page)  # 上传成功文案默认命中,首轮轮询即完成
            self._run(p, page, title='T', dry_run=True)
        _loc(page, '.btns button.el-button--primary:has-text("提交")').click.assert_not_awaited()
        context.storage_state.assert_not_awaited()
        mocks['close_browser'].assert_awaited_once()


# ── DOM 辅助: 封面 ─────────────────────────────────────────────────────────

class TestSetCover:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        cover_img = _loc(page, '.cover-photo-img').first
        cover_img.count = AsyncMock(return_value=1)
        dialog = _loc(page, "div.el-dialog[role='dialog']").last
        dialog.count = AsyncMock(return_value=1)
        upload_tab = dialog.locator('.el-tabs__item:has-text("上传封面")').first
        upload_tab.count = AsyncMock(return_value=1)
        upload_tab.get_attribute = AsyncMock(return_value='el-tabs__item')
        cover_input = dialog.locator('input[type="file"][accept=".png,.jpg,.jpeg"]').first
        cover_input.count = AsyncMock(return_value=1)
        croppert = dialog.locator('.vue-croppert').first
        croppert.count = AsyncMock(return_value=1)
        croppert.get_attribute = AsyncMock(return_value='width: 100px')
        confirm_btn = dialog.locator('.dialog-footer-right:has-text("确定")').first
        confirm_btn.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_cover(page, '/cover.png'))
        cover_img.click.assert_awaited_once_with(force=True)
        upload_tab.click.assert_awaited_once()
        cover_input.set_input_files.assert_awaited_once_with('/cover.png')
        confirm_btn.click.assert_awaited_once()

    def test_cover_img_missing_skips(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_cover(page, '/cover.png'))
        assert any('未找到封面图' in str(c) for c in logger.warning.call_args_list)

    def test_dialog_missing_skips(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.cover-photo-img').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_cover(page, '/cover.png'))
        assert any('未找到弹窗容器' in str(c) for c in logger.warning.call_args_list)

    def test_tab_already_active(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.cover-photo-img').first.count = AsyncMock(return_value=1)
        dialog = _loc(page, "div.el-dialog[role='dialog']").last
        dialog.count = AsyncMock(return_value=1)
        upload_tab = dialog.locator('.el-tabs__item:has-text("上传封面")').first
        upload_tab.count = AsyncMock(return_value=1)
        upload_tab.get_attribute = AsyncMock(return_value='el-tabs__item is-active')
        dialog.locator('input[type="file"][accept=".png,.jpg,.jpeg"]').first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_cover(page, '/cover.png'))
        upload_tab.click.assert_not_awaited()

    def test_tab_fallback_tab2(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.cover-photo-img').first.count = AsyncMock(return_value=1)
        dialog = _loc(page, "div.el-dialog[role='dialog']").last
        dialog.count = AsyncMock(return_value=1)
        dialog.locator('.el-tabs__item:has-text("上传封面")').first.count = AsyncMock(return_value=0)
        tab2 = dialog.locator('#tab-2').first
        tab2.count = AsyncMock(return_value=1)
        tab2.get_attribute = AsyncMock(return_value='')
        dialog.locator('input[type="file"][accept=".png,.jpg,.jpeg"]').first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_cover(page, '/cover.png'))
        tab2.click.assert_awaited_once()

    def test_input_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.cover-photo-img').first.count = AsyncMock(return_value=1)
        dialog = _loc(page, "div.el-dialog[role='dialog']").last
        dialog.count = AsyncMock(return_value=1)
        dialog.locator('.el-tabs__item:has-text("上传封面")').first.count = AsyncMock(return_value=0)
        dialog.locator('#tab-2').first.count = AsyncMock(return_value=0)
        dialog.locator('input[type="file"][accept=".png,.jpg,.jpeg"]').first.count = AsyncMock(return_value=0)
        fallback = dialog.locator('input[type="file"]').first
        fallback.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_cover(page, '/cover.png'))
        fallback.set_input_files.assert_awaited_once_with('/cover.png')

    def test_input_missing_in_dialog_warns(self):
        """主选择器与兜底 input 都缺失 → warning 并跳过(不调用 set_input_files)。"""
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.cover-photo-img').first.count = AsyncMock(return_value=1)
        dialog = _loc(page, "div.el-dialog[role='dialog']").last
        dialog.count = AsyncMock(return_value=1)
        dialog.locator('.el-tabs__item:has-text("上传封面")').first.count = AsyncMock(return_value=0)
        dialog.locator('#tab-2').first.count = AsyncMock(return_value=0)
        # 主 input 与兜底 input 都默认 count=0
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger', logger):
            _run(p._set_cover(page, '/cover.png'))
        assert any('弹窗内未找到上传 input' in str(c) for c in logger.warning.call_args_list)
        dialog.locator('input[type="file"]').first.set_input_files.assert_not_awaited()

    def test_croppert_hidden_confirm(self):
        """裁剪区 display:none → 循环 20 次后按无裁剪直接确定。"""
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.cover-photo-img').first.count = AsyncMock(return_value=1)
        dialog = _loc(page, "div.el-dialog[role='dialog']").last
        dialog.count = AsyncMock(return_value=1)
        dialog.locator('.el-tabs__item:has-text("上传封面")').first.count = AsyncMock(return_value=0)
        dialog.locator('#tab-2').first.count = AsyncMock(return_value=0)
        dialog.locator('input[type="file"][accept=".png,.jpg,.jpeg"]').first.count = AsyncMock(return_value=1)
        croppert = dialog.locator('.vue-croppert').first
        croppert.count = AsyncMock(return_value=1)
        croppert.get_attribute = AsyncMock(return_value='display: none')
        confirm_btn = dialog.locator('.dialog-footer-right:has-text("确定")').first
        confirm_btn.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_cover(page, '/cover.png'))
        confirm_btn.click.assert_awaited_once()
        assert any('直接确定' in str(c) for c in logger.info.call_args_list)

    def test_confirm_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.cover-photo-img').first.count = AsyncMock(return_value=1)
        dialog = _loc(page, "div.el-dialog[role='dialog']").last
        dialog.count = AsyncMock(return_value=1)
        dialog.locator('.el-tabs__item:has-text("上传封面")').first.count = AsyncMock(return_value=0)
        dialog.locator('#tab-2').first.count = AsyncMock(return_value=0)
        dialog.locator('input[type="file"][accept=".png,.jpg,.jpeg"]').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_cover(page, '/cover.png'))
        assert any('未找到「确定」按钮' in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.cover-photo-img').first.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_cover(page, '/cover.png'))  # 不抛异常
        assert logger.error.called


# ── DOM 辅助: 位置 ─────────────────────────────────────────────────────────

class TestSetLocation:
    def test_exact_match(self):
        p = _mk_platform()
        page = _mk_page()
        pos_module = _loc(page, '.sel-position-module').first
        pos_module.count = AsyncMock(return_value=1)
        items = _loc(page, '.position-list li')
        items.count = AsyncMock(return_value=3)
        items.nth(1)  # 预注册
        name_el = items.nth_subs[1].locator('.position-name').first
        name_el.count = AsyncMock(return_value=1)
        name_el.inner_text = AsyncMock(return_value='  上海市  ')
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_location(page, '上海市'))
        page.keyboard.type.assert_awaited_once_with('上海市', delay=80)
        items.nth_subs[1].click.assert_awaited_once()

    def test_entry_missing_skips(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_location(page, '上海'))
        assert any('未找到位置入口' in str(c) for c in logger.warning.call_args_list)

    def test_no_dropdown_fallback_first_item(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.sel-position-module').first.count = AsyncMock(return_value=1)
        items = _loc(page, '.position-list li')
        items.count = AsyncMock(side_effect=[0, 0, 0, 2, 2])  # 3 次轮询后出现(第4次命中),再读一次数量
        items.first.count = AsyncMock(return_value=1)
        items.first.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_location(page, '不存在的城市'))
        items.first.click.assert_awaited_once()

    def test_no_match_falls_back_first(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.sel-position-module').first.count = AsyncMock(return_value=1)
        items = _loc(page, '.position-list li')
        items.count = AsyncMock(return_value=2)
        items.nth(0)  # 预注册
        name0 = items.nth_subs[0].locator('.position-name').first
        name0.count = AsyncMock(return_value=1)
        name0.inner_text = AsyncMock(return_value='北京市')
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_location(page, '上海市'))
        # 无精确匹配 → 点第一项
        _loc(page, '.position-list li').first.click.assert_awaited_once()

    def test_li_without_name_skipped(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.sel-position-module').first.count = AsyncMock(return_value=1)
        items = _loc(page, '.position-list li')
        items.count = AsyncMock(return_value=1)
        items.nth(0)  # 预注册
        items.nth_subs[0].locator('.position-name').first.count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_location(page, '上海市'))
        # 第一项无 name → continue → 无匹配 → 兜底点第一项
        _loc(page, '.position-list li').first.click.assert_awaited_once()

    def test_dropdown_never_appears_warns(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.sel-position-module').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_location(page, '上海市'))
        assert any('未出现下拉选项' in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.sel-position-module').first.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_location(page, '上海市'))  # 不抛异常
        assert logger.error.called


# ── DOM 辅助: 作品同步 / 声明 / radio / 定时 ───────────────────────────────

class TestToggleDistribution:
    LABEL = 'label.el-checkbox:has-text("同时分发到vivo浏览器")'

    def test_check_when_unchecked(self):
        p = _mk_platform()
        page = _mk_page()
        label = _loc(page, self.LABEL).first
        label.count = AsyncMock(return_value=1)
        checkbox = label.locator('input[type="checkbox"]').first
        checkbox.count = AsyncMock(return_value=1)
        checkbox.is_checked = AsyncMock(return_value=False)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._toggle_distribution(page, True))
        label.click.assert_awaited_once()

    def test_uncheck_when_checked(self):
        p = _mk_platform()
        page = _mk_page()
        label = _loc(page, self.LABEL).first
        label.count = AsyncMock(return_value=1)
        checkbox = label.locator('input[type="checkbox"]').first
        checkbox.count = AsyncMock(return_value=1)
        checkbox.is_checked = AsyncMock(return_value=True)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._toggle_distribution(page, False))
        label.click.assert_awaited_once()

    def test_already_target_state(self):
        p = _mk_platform()
        page = _mk_page()
        label = _loc(page, self.LABEL).first
        label.count = AsyncMock(return_value=1)
        checkbox = label.locator('input[type="checkbox"]').first
        checkbox.count = AsyncMock(return_value=1)
        checkbox.is_checked = AsyncMock(return_value=True)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._toggle_distribution(page, True))
        label.click.assert_not_awaited()
        assert any('已是目标状态' in str(c) for c in logger.info.call_args_list)

    def test_checkbox_missing_skips(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, self.LABEL).first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._toggle_distribution(page, True))
        assert logger.info.called

    def test_label_missing_skips(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._toggle_distribution(page, True))
        assert any('未找到作品同步复选框' in str(c) for c in logger.info.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, self.LABEL).first.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._toggle_distribution(page, True))  # 不抛异常
        assert logger.error.called


class TestSetDeclaration:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        trigger = _loc(page, '.short-play-select .el-input__inner').first
        trigger.count = AsyncMock(return_value=1)
        option = _loc(page, '.el-select-dropdown__item:has-text("原创")').first
        option.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_declaration(page, '原创'))
        trigger.click.assert_awaited_once()
        option.click.assert_awaited_once()

    def test_trigger_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.short-play-select .el-input__inner').first.count = AsyncMock(return_value=0)
        fallback = _loc(page, '.short-play-select').first
        fallback.count = AsyncMock(return_value=1)
        _loc(page, '.el-select-dropdown__item:has-text("原创")').first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_declaration(page, '原创'))
        fallback.click.assert_awaited_once()

    def test_option_missing_escapes(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.short-play-select .el-input__inner').first.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_declaration(page, '不存在'))
        page.keyboard.press.assert_awaited_once_with('Escape')
        assert any('未找到选项' in str(c) for c in logger.warning.call_args_list)

    def test_trigger_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_declaration(page, '原创'))
        assert any('未找到下拉触发器' in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.short-play-select .el-input__inner').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_declaration(page, '原创'))  # 不抛异常
        assert logger.error.called


class TestSetRadioByLabel:
    def test_selects_when_unchecked(self):
        p = _mk_platform()
        page = _mk_page()
        field_block = _loc(page, '.video-form-item:has(.video-form-label .name:has-text("谁可以看"))').first
        field_block.count = AsyncMock(return_value=1)
        target = field_block.locator('label[role="radio"]:has(.el-radio__label:has-text("仅自己"))').first
        target.count = AsyncMock(return_value=1)
        target.get_attribute = AsyncMock(return_value=None)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_radio_by_label(page, '谁可以看', '仅自己'))
        target.click.assert_awaited_once()

    def test_checked_by_class(self):
        p = _mk_platform()
        page = _mk_page()
        field_block = _loc(page, '.video-form-item:has(.video-form-label .name:has-text("谁可以看"))').first
        field_block.count = AsyncMock(return_value=1)
        target = field_block.locator('label[role="radio"]:has(.el-radio__label:has-text("公开"))').first
        target.count = AsyncMock(return_value=1)
        target.get_attribute = AsyncMock(side_effect=[None, 'el-radio is-checked'])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_radio_by_label(page, '谁可以看', '公开'))
        target.click.assert_not_awaited()

    def test_field_block_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_radio_by_label(page, '谁可以看', '公开'))
        assert any('未找到字段区块' in str(c) for c in logger.warning.call_args_list)

    def test_option_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        field_block = _loc(page, '.video-form-item:has(.video-form-label .name:has-text("谁可以看"))').first
        field_block.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_radio_by_label(page, '谁可以看', '不存在'))
        assert any('未找到选项' in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.video-form-item:has(.video-form-label .name:has-text("谁可以看"))').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_radio_by_label(page, '谁可以看', '公开'))  # 不抛异常
        assert logger.error.called


class TestSetScheduleTime:
    PD = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
    RADIO = 'label[role="radio"]:has(span.el-radio__label:has-text("定时发布"))'
    DATE_EDITOR = '.el-date-editor.el-input, .el-date-editor--datetime'

    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, self.RADIO).first
        radio.count = AsyncMock(return_value=1)
        radio.get_attribute = AsyncMock(return_value=None)
        editor = _loc(page, self.DATE_EDITOR).first
        editor.count = AsyncMock(return_value=1)
        date_input = _loc(page, '.el-date-picker__editor-wrap input[placeholder="选择日期"]').first
        date_input.count = AsyncMock(return_value=1)
        time_input = _loc(page, '.el-date-picker__editor-wrap input[placeholder="选择时间"]').first
        time_input.count = AsyncMock(return_value=1)
        confirm = _loc(page, '.el-picker-panel__footer button.is-plain').first
        confirm.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_schedule_time(page, self.PD))
        radio.click.assert_awaited_once()
        editor.click.assert_awaited_once()
        date_input.fill.assert_awaited_once_with('2026-08-22')
        time_input.fill.assert_awaited_once_with('10:05')
        confirm.click.assert_awaited_once()

    def test_radio_already_checked_by_class(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, self.RADIO).first
        radio.count = AsyncMock(return_value=1)
        radio.get_attribute = AsyncMock(side_effect=[None, 'el-radio is-checked'])
        editor = _loc(page, self.DATE_EDITOR).first
        editor.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.vivo.platform.logger'):
            _run(p._set_schedule_time(page, self.PD))
        radio.click.assert_not_awaited()

    def test_radio_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_schedule_time(page, self.PD))
        assert any('未找到「定时发布」radio' in str(c) for c in logger.warning.call_args_list)

    def test_date_editor_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, self.RADIO).first
        radio.count = AsyncMock(return_value=1)
        radio.get_attribute = AsyncMock(return_value='true')
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_schedule_time(page, self.PD))
        assert any('未找到日期编辑器' in str(c) for c in logger.warning.call_args_list)

    def test_inputs_missing_warns_but_confirms(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, self.RADIO).first
        radio.count = AsyncMock(return_value=1)
        radio.get_attribute = AsyncMock(return_value='true')
        editor = _loc(page, self.DATE_EDITOR).first
        editor.count = AsyncMock(return_value=1)
        confirm = _loc(page, '.el-picker-panel__footer button.is-plain').first
        confirm.count = AsyncMock(return_value=0)
        confirm_fallback = _loc(page, '.el-picker-panel__footer button:has-text("确定")').first
        confirm_fallback.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_schedule_time(page, self.PD))
        assert any('未找到「选择日期」文本框' in str(c) for c in logger.warning.call_args_list)
        assert any('未找到「选择时间」文本框' in str(c) for c in logger.warning.call_args_list)
        confirm_fallback.click.assert_awaited_once()

    def test_confirm_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, self.RADIO).first
        radio.count = AsyncMock(return_value=1)
        radio.get_attribute = AsyncMock(return_value='true')
        editor = _loc(page, self.DATE_EDITOR).first
        editor.count = AsyncMock(return_value=1)
        date_input = _loc(page, '.el-date-picker__editor-wrap input[placeholder="选择日期"]').first
        date_input.count = AsyncMock(return_value=1)
        time_input = _loc(page, '.el-date-picker__editor-wrap input[placeholder="选择时间"]').first
        time_input.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_schedule_time(page, self.PD))
        assert any('未找到确定按钮' in str(c) for c in logger.warning.call_args_list)

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, self.RADIO).first
        radio.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.vivo.platform.logger', logger):
            _run(p._set_schedule_time(page, self.PD))  # 不抛异常
        assert logger.error.called