"""Weibo platform.py DOM 交互层契约测试（T35 批次第 9 期）。

覆盖 impl/weibo/platform.py（865 stmts，基线 19%）:
- 纯函数: _parse_cookie_to_storage_state（.weibo.com 域/expires 窗口/httpOnly/跳过无效对/空白清理）
- 登录/校验/同步: login（完整流程/save_login_result+stats_fn/context close 异常吞掉/成功才关浏览器）
  / check_cookie（文件缺失 False/资料卡判定 valid+expired/异常兜底） / open_creator_center（线程启动/
  wait_for_event 异常吞掉/browser.close 异常吞掉） / sync_profile（stats 组装含逗号/int 解析异常→0/
  未知 label 跳过/空抓取告警/异常兜底空结果） / _login_stats_fn（stats 组装/异常空列表）
- 编排: _upload_one_image 全流程（创作卡片未渲染 RuntimeError/保存 cookie/close_browser）
  / _upload_images（无文件早退/直接 set_input_files/expect_file_chooser 兜底/patched input 兜底/
  30s 超时 raise/trigger 缺失 raise/发送按钮 5 分钟超时） / _click_send（正常/未找到/一直 disabled）
  / _wait_for_image_publish_success（textarea 空/按钮 disabled/探测异常继续/超时）
  / _upload_one_video 全流程（合集选择/跳过合集/上传请求响应监听/保存 cookie/close_browser）
  / _upload_video_file（主选择器/role 回退/expect_file_chooser 提交/click 失败 JS 兜底/
  patched input 超时/全部失败） / _wait_for_upload_form（spinner 消失/发布按钮可见/双命中/
  探测异常继续/上传失败 RuntimeError/进度日志/超时含 URL）
- DOM 辅助: _set_video_type（空/精确/部分匹配/未知/失败） / _set_title（空/截断 30 字）
  / _pick_cover_by_aspect（横版/竖版/无 aspect 默认横版/调试信息/evaluate 异常/等待告警）
  / _set_cover（完整流程/无封面跳过/文件不存在跳过/入口缺失/弹层超时/input 缺失/完成失败/弹层关闭超时 ESC）
  / _set_category（list/字符串/格式错误/无法识别/None/表未命中告警/trigger 缺失/级联失败 ESC）
  / _set_collection（开关命中/开关缺失/探测异常/列表未展开/value 空跳过/未匹配告警/勾选失败继续）
  / _set_description（desc+tags/title 回落/tags 仅有/空跳过） / _set_content_statement（v2 探测/探测异常兜底/
  v2 异常兜底/v1 路径） / _set_content_statement_v1（空/无/正常/入口缺失/选项失败 ESC）
  / _set_content_statement_v2（必选默认「内容无需标注」/btn 缺失直点 label/必选失败 ESC/可选跳过/可选失败继续/
  确定按钮/确定失败 ESC/trigger 缺失/面板缺失） / _click_publish（正常/未找到/一直 disabled）
  / _wait_for_publish_success（toast/URL 跳转/未检测到抛错）
"""
import asyncio
import sys
import time as _time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.weibo.platform import (
    _WEIBO_CREATOR_URL,
    _WEIBO_UPLOAD_URL,
    WeiboPlatform,
)

SWITCH = "label.woo-switch-main"
ALBUM_INPUT = 'input[type="text"][value*="集"]'


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return WeiboPlatform()


def _mk_leaf():
    loc = MagicMock()
    loc.count = AsyncMock(return_value=0)
    loc.click = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.set_input_files = AsyncMock()
    loc.get_attribute = AsyncMock(return_value=None)
    loc.input_value = AsyncMock(return_value='')
    loc.is_visible = AsyncMock(return_value=True)
    loc.fill = AsyncMock()
    loc.evaluate = AsyncMock(return_value='')
    loc.locator = MagicMock(side_effect=lambda sel, **kw: loc.subs.setdefault(sel, _mk_locator()))
    loc.subs = {}
    loc.nth = MagicMock(side_effect=lambda i: loc.nth_subs.setdefault(i, _mk_leaf()))
    loc.nth_subs = {}
    return loc


def _mk_locator():
    loc = _mk_leaf()
    loc.first = _mk_leaf()
    loc.last = _mk_leaf()
    return loc


def _mk_page(url=_WEIBO_UPLOAD_URL):
    page = MagicMock()
    page.url = url
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_event = AsyncMock()
    page.evaluate = AsyncMock(return_value=[])
    page.on = MagicMock()
    page.expect_file_chooser = MagicMock()
    page.get_by_text = MagicMock(
        side_effect=lambda text, **kw: page.text_locators.setdefault(
            (text, kw.get('exact')), _mk_locator(),
        ),
    )
    page.get_by_role = MagicMock(
        side_effect=lambda role, **kw: page.role_locators.setdefault(
            (role, kw.get('name'), kw.get('exact')), _mk_locator(),
        ),
    )
    page.locator = MagicMock(
        side_effect=lambda sel, **kw: page.locators.setdefault(sel, _mk_locator()),
    )
    page.text_locators = {}
    page.role_locators = {}
    page.locators = {}
    return page


def _loc(page, sel):
    page.locator(sel)
    return page.locators[sel]


def _text(page, text, exact=None):
    page.get_by_text(text, exact=exact)
    return page.text_locators[(text, exact)]


def _role(page, role, name=None, exact=None):
    page.get_by_role(role, name=name, exact=exact)
    return page.role_locators[(role, name, exact)]


def _sub(leaf, sel):
    leaf.locator(sel)
    return leaf.subs[sel]


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


def _mk_cookie_file(name='t35_weibo_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


def _mk_media_file(name='t35_weibo_media_tmp.mp4'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(b'0')
    return p


class _FakeFileChooserCM:
    """async with 走 type 级 __aenter__/__aexit__,实例属性不生效,必须用真类。

    注意:平台代码是 ``fc = await fc_info.value``(await 属性本身),所以
    ``value`` 必须是一个可 await 的协程对象,不能是 AsyncMock(实例不可 await)。
    """

    def __init__(self, fc):
        self.fc = fc
        self.info = MagicMock()
        self.info.value = self._resolve_value()

    async def _resolve_value(self):
        return self.fc

    async def __aenter__(self):
        return self.info

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _mk_fc_ctx():
    """成功路径的 expect_file_chooser 上下文:async with → fc_info.value → fc.set_files。"""
    fc = MagicMock()
    fc.set_files = AsyncMock()
    return _FakeFileChooserCM(fc), fc


class _FakeLoop:
    """时间序列控制:上传等待 / 轮询都依赖 loop.time()。"""

    def __init__(self, times):
        self._times = list(times)

    def time(self):
        return self._times.pop(0) if len(self._times) > 1 else self._times[0]


def _collect_handlers(page):
    handlers = {}
    for call in page.on.call_args_list:
        event, fn = call.args
        handlers[event] = fn
    return handlers


# ── 纯函数 ─────────────────────────────────────────────────────────────────

class TestParseCookieToStorageState:
    def test_happy_parse(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('SUB=abc; SCF=d')
        assert origins == []
        assert [c['name'] for c in cookies] == ['SUB', 'SCF']
        for c in cookies:
            assert c['domain'] == '.weibo.com'
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
    def test_success_full_flow(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch('impl.weibo.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p.login('u1', MagicMock(), account_id='acc1'))
        page.goto.assert_awaited_once_with(_WEIBO_CREATOR_URL)
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 11
        assert kwargs['platform_name'] == '微博'
        assert kwargs['account_id'] == 'acc1'
        assert kwargs['stats_fn'].__func__ is WeiboPlatform._login_stats_fn
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()  # 成功才关浏览器

    def test_save_login_result_exception_keeps_browser(self):
        """save_login_result 抛异常 → 传播;success=False → 不关浏览器。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, context, browser, _cb, _cc), \
             patch('impl.weibo.platform.save_login_result',
                   AsyncMock(side_effect=RuntimeError('save boom'))), \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='save boom'):
            _run(p.login('u1', MagicMock()))
        context.close.assert_awaited_once()
        browser.close.assert_not_awaited()

    def test_context_close_error_swallowed(self):
        """context.close 在 finally 抛异常 → 不遮盖上一步的 success 流程。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, context, browser, _cb, _cc), \
             patch('impl.weibo.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            context.close = AsyncMock()
            _run(p.login('u1', MagicMock()))
        slr.assert_awaited_once()
        browser.close.assert_awaited_once()


class TestCheckCookie:
    def test_missing_file_returns_false(self):
        p = _mk_platform()
        with patch.object(p, 'create_browser', AsyncMock()) as cb, \
             patch('impl.weibo.platform.logger'):
            assert _run(p.check_cookie('t35_weibo_nope.json')) is False
        cb.assert_not_awaited()  # 文件不存在直接 False,不开浏览器

    def test_valid(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_weibo_ck_valid.json')
        try:
            with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
                 patch('impl.weibo.platform.logger'):
                _loc(page, '.woo-tab-nav a[href^="/u/"] img[src*="sinaimg.cn"]') \
                    .first.count = AsyncMock(return_value=1)
                assert _run(p.check_cookie(cookie.name)) is True
            page.goto.assert_awaited_once_with(_WEIBO_CREATOR_URL, timeout=30000)
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_expired(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_weibo_ck_expired.json')
        try:
            with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
                 patch('impl.weibo.platform.logger') as logger:
                _loc(page, '.woo-tab-nav a[href^="/u/"] img[src*="sinaimg.cn"]') \
                    .first.count = AsyncMock(return_value=0)
                assert _run(p.check_cookie(cookie.name)) is False
            assert any('expired' in str(c) for c in logger.info.call_args_list)
        finally:
            cookie.unlink(missing_ok=True)

    def test_goto_error_returns_false(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_weibo_ck_err.json')
        try:
            with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
                 patch('impl.weibo.platform.logger'):
                page.goto = AsyncMock(side_effect=RuntimeError('net down'))
                assert _run(p.check_cookie(cookie.name)) is False
        finally:
            cookie.unlink(missing_ok=True)


class TestOpenCreatorCenter:
    def test_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_weibo_occ.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl._browser.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl._browser.create_context_sync', return_value=context) as ccs, \
                 patch('impl.weibo.platform.logger'):
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
        cookie = _mk_cookie_file('t35_weibo_occ2.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl._browser.create_browser_sync', return_value=browser), \
                 patch('impl._browser.create_context_sync', return_value=context), \
                 patch('impl.weibo.platform.logger'):
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
        cookie = _mk_cookie_file('t35_weibo_occ3.json')
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('boom'))
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl._browser.create_browser_sync', return_value=browser), \
                 patch('impl._browser.create_context_sync', return_value=context), \
                 patch('impl.weibo.platform.logger'):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)


class TestSyncProfile:
    def _stats_result(self):
        return {
            'name': '微博昵称',
            'avatar': 'http://a/sinaimg.cn/1.png',
            'stats': [
                {'name': '粉丝', 'num': '1,234'},
                {'name': '关注', 'num': '56'},
                {'name': '转评赞', 'num': '7,890'},
                {'name': '未知label', 'num': '99'},
            ],
        }

    def test_happy(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            page.evaluate = AsyncMock(return_value=self._stats_result())
            res = _run(p.sync_profile('ck.json'))
        assert res == {
            'name': '微博昵称', 'avatar': 'http://a/sinaimg.cn/1.png',
            'stats': [
                {'ICON': 'user', 'COUNT': 1234, 'NAME': '粉丝', 'SORT': 1},
                {'ICON': 'follow', 'COUNT': 56, 'NAME': '关注', 'SORT': 2},
                {'ICON': 'like', 'COUNT': 7890, 'NAME': '转评赞', 'SORT': 3},
            ],
        }
        browser.close.assert_awaited_once()

    def test_int_parse_error_counts_zero(self):
        p = _mk_platform()
        result = self._stats_result()
        result['stats'] = [{'name': '粉丝', 'num': 'abc'}]
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            page.evaluate = AsyncMock(return_value=result)
            res = _run(p.sync_profile('ck.json'))
        assert res['stats'] == [{'ICON': 'user', 'COUNT': 0, 'NAME': '粉丝', 'SORT': 1}]

    def test_empty_result_logs(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.weibo.platform.logger') as logger, patch('asyncio.sleep', AsyncMock()):
            page.evaluate = AsyncMock(return_value={})
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': []}
        assert any('抓取为空' in str(c) for c in logger.info.call_args_list)

    def test_result_none(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            page.evaluate = AsyncMock(return_value=None)
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': []}

    def test_avatar_click_error_still_scrapes(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _loc(page, '.woo-badge-box img').first.wait_for = AsyncMock(
                side_effect=RuntimeError('stale'),
            )
            page.evaluate = AsyncMock(return_value=self._stats_result())
            res = _run(p.sync_profile('ck.json'))
        assert res['name'] == '微博昵称'

    def test_networkidle_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            page.wait_for_load_state = AsyncMock(side_effect=RuntimeError('net'))
            page.evaluate = AsyncMock(return_value=self._stats_result())
            res = _run(p.sync_profile('ck.json'))
        assert res['name'] == '微博昵称'

    def test_evaluate_error_returns_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            page.evaluate = AsyncMock(side_effect=RuntimeError('js boom'))
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': []}


class TestLoginStatsFn:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'name': '粉丝', 'num': '1,234'},
            {'name': '关注', 'num': '5'},
            {'name': '转评赞', 'num': ''},
            {'name': '其它', 'num': '9'},
        ])
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            stats = _run(p._login_stats_fn(page, 'acc1'))
        assert [s['SORT'] for s in stats] == [1, 2, 3]
        assert stats[0]['COUNT'] == 1234
        assert stats[2]['COUNT'] == 0  # 空字符串 → 0

    def test_result_none(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=None)
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            assert _run(p._login_stats_fn(page, 'acc1')) == []

    def test_int_parse_error_counts_zero(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[{'name': '粉丝', 'num': 'x'}])
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            stats = _run(p._login_stats_fn(page, 'acc1'))
        assert stats == [{'ICON': 'user', 'COUNT': 0, 'NAME': '粉丝', 'SORT': 1}]

    def test_exception_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            assert _run(p._login_stats_fn(page, 'acc1')) == []


# ── 编排: _upload_one_image 图集全流程 ────────────────────────────────────

class TestUploadOneImage:
    @contextmanager
    def _mk_steps(self, p):
        mocks = dict(
            upload_images=AsyncMock(),
            set_description=AsyncMock(),
            set_content_statement=AsyncMock(),
            click_send=AsyncMock(),
            wait_image_success=AsyncMock(),
            close_browser=AsyncMock(),
        )
        with patch.object(p, '_upload_images', mocks['upload_images']), \
             patch.object(p, '_set_description', mocks['set_description']), \
             patch.object(p, '_set_content_statement', mocks['set_content_statement']), \
             patch.object(p, '_click_send', mocks['click_send']), \
             patch.object(p, '_wait_for_image_publish_success', mocks['wait_image_success']), \
             patch.object(p, 'close_browser', mocks['close_browser']), \
             patch('asyncio.sleep', AsyncMock()):
            yield mocks

    def test_happy_full_flow(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             self._mk_steps(p) as mocks, patch('impl.weibo.platform.logger'):
            _run(p._upload_one_image(
                title='图集', file_path_list=['/a.png', '/b.png'], tags=['t'],
                account_file='/c/u1.json', desc='d', ai_content='原创',
                content_statement='声明', content_statement2='必选',
                content_statement2_optional='可选',
            ))
        page.goto.assert_awaited_once_with('https://weibo.com', timeout=60000)
        mocks['upload_images'].assert_awaited_once_with(page, ['/a.png', '/b.png'])
        mocks['set_description'].assert_awaited_once()
        mocks['set_content_statement'].assert_awaited_once_with(
            page, '声明', '必选', '可选',
        )
        mocks['click_send'].assert_awaited_once_with(page)
        mocks['wait_image_success'].assert_awaited_once_with(page)
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_ai_content_fallback_for_v1(self):
        """content_statement 为空 → v1 用 ai_content 兜底。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             self._mk_steps(p) as mocks, patch('impl.weibo.platform.logger'):
            _run(p._upload_one_image(
                title='t', file_path_list=['/a.png'], tags=[], account_file='/c/u1.json',
                ai_content='原创',
            ))
        args = mocks['set_content_statement'].await_args.args
        assert args[1] == '原创'  # v1 = content_statement or ai_content

    def test_send_button_missing_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             self._mk_steps(p) as mocks, patch('impl.weibo.platform.logger'):
            _role(page, 'button', name='发送', exact=True).first.wait_for = AsyncMock(
                side_effect=RuntimeError('not attached'),
            )
            with pytest.raises(RuntimeError, match='创作卡片未渲染'):
                _run(p._upload_one_image(
                    title='t', file_path_list=['/a.png'], tags=[], account_file='/c/u1.json',
                ))
        mocks['upload_images'].assert_not_awaited()
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)


# ── 编排: _upload_images 多图上传 ──────────────────────────────────────────

class TestUploadImages:
    def test_no_files_returns_early(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger):
            _run(WeiboPlatform._upload_images(page, []))
        assert any('无图片可上传' in str(c) for c in logger.warning.call_args_list)

    def test_happy_direct_set_input_files(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0])  # 发送按钮轮询首轮命中
        _text(page, '图片', exact=True).first.count = AsyncMock(return_value=1)
        target = _loc(page, "input[type='file'][accept^='image/'][multiple]").first
        target.count = AsyncMock(return_value=1)
        with patch('impl.weibo.platform.logger') as logger, \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._upload_images(page, ['/a.png']))
        target.set_input_files.assert_awaited_once_with(['/a.png'])
        assert any('set_input_files 提交' in str(c) for c in logger.info.call_args_list)

    def test_fallback_file_chooser(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0])
        _text(page, '图片', exact=True).first.count = AsyncMock(return_value=1)
        target = _loc(page, "input[type='file'][accept^='image/'][multiple]").first
        target.wait_for = AsyncMock(side_effect=RuntimeError('hidden'))
        cm, fc = _mk_fc_ctx()
        page.expect_file_chooser = MagicMock(return_value=cm)
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._upload_images(page, ['/a.png']))
        fc.set_files.assert_awaited_once_with(['/a.png'])

    def test_fallback_patched_input(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0, 2.0, 3.0])  # marked 首轮命中 + 发送按钮首轮
        _text(page, '图片', exact=True).first.count = AsyncMock(return_value=1)
        target = _loc(page, "input[type='file'][accept^='image/'][multiple]").first
        target.wait_for = AsyncMock(side_effect=RuntimeError('hidden'))
        page.expect_file_chooser = MagicMock(side_effect=RuntimeError('no fc'))
        marked = _loc(page, "input[type='file'][data-weibo-img-upload='1'],"
                            "input[type='file'][data-weibo-img-new='1']")
        marked.count = AsyncMock(return_value=1)
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._upload_images(page, ['/a.png']))
        marked.first.set_input_files.assert_awaited_once_with(['/a.png'])

    def test_fallback_patched_input_timeout(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 2.0, 30.0])  # deadline=30,第二/三次 time() 越过
        _text(page, '图片', exact=True).first.count = AsyncMock(return_value=1)
        target = _loc(page, "input[type='file'][accept^='image/'][multiple]").first
        target.wait_for = AsyncMock(side_effect=RuntimeError('hidden'))
        page.expect_file_chooser = MagicMock(side_effect=RuntimeError('no fc'))
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='30s 内未找到可用的 file input'):
            _run(WeiboPlatform._upload_images(page, ['/a.png']))

    def test_trigger_missing_raises(self):
        page = _mk_page()
        with patch('impl.weibo.platform.logger'), \
             pytest.raises(RuntimeError, match='未找到「图片」工具图标'):
            _run(WeiboPlatform._upload_images(page, ['/a.png']))

    def test_send_poll_exception_then_success(self):
        """发送按钮探测抛异常 → except 吞掉 → 下一轮 enabled 即返回。"""
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0, 2.0])  # 首轮探测异常,次轮 enabled
        _text(page, '图片', exact=True).first.count = AsyncMock(return_value=1)
        target = _loc(page, "input[type='file'][accept^='image/'][multiple]").first
        target.count = AsyncMock(return_value=1)
        send_btn = _role(page, 'button', name='发送', exact=True).first
        send_btn.get_attribute = AsyncMock(side_effect=[RuntimeError('stale'), None])
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._upload_images(page, ['/a.png']))
        assert send_btn.get_attribute.await_count == 2

    def test_send_button_stays_disabled_timeout(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0, 300.1])  # deadline=300,第三/四次 time() 越过
        _text(page, '图片', exact=True).first.count = AsyncMock(return_value=1)
        target = _loc(page, "input[type='file'][accept^='image/'][multiple]").first
        target.count = AsyncMock(return_value=1)
        send_btn = _role(page, 'button', name='发送', exact=True).first
        send_btn.get_attribute = AsyncMock(return_value='disabled')
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='5 分钟内图片未上传完成'):
            _run(WeiboPlatform._upload_images(page, ['/a.png']))


# ── DOM 辅助: _click_send / _wait_for_image_publish_success ────────────────

class TestClickSend:
    def test_happy(self):
        page = _mk_page()
        send_btn = _role(page, 'button', name='发送', exact=True).first
        send_btn.get_attribute = AsyncMock(return_value=None)
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._click_send(page))
        send_btn.click.assert_awaited_once()

    def test_not_found_raises(self):
        page = _mk_page()
        _role(page, 'button', name='发送', exact=True).first.wait_for = AsyncMock(
            side_effect=RuntimeError('gone'),
        )
        with patch('impl.weibo.platform.logger'), \
             pytest.raises(RuntimeError, match='未找到「发送」按钮'):
            _run(WeiboPlatform._click_send(page))

    def test_always_disabled_raises(self):
        page = _mk_page()
        send_btn = _role(page, 'button', name='发送', exact=True).first
        send_btn.get_attribute = AsyncMock(return_value='disabled')
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='「发送」按钮一直 disabled'):
            _run(WeiboPlatform._click_send(page))


class TestWaitForImagePublishSuccess:
    def test_textarea_empty(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0])
        textarea = _loc(page, "textarea[placeholder*='有什么新鲜事']").first
        textarea.input_value = AsyncMock(return_value='')
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._wait_for_image_publish_success(page))
        textarea.input_value.assert_awaited_once()

    def test_send_disabled(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0])
        textarea = _loc(page, "textarea[placeholder*='有什么新鲜事']").first
        textarea.input_value = AsyncMock(return_value='还有内容')
        send_btn = _role(page, 'button', name='发送', exact=True).first
        send_btn.get_attribute = AsyncMock(return_value='disabled')
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._wait_for_image_publish_success(page))
        assert send_btn.get_attribute.await_count == 1

    def test_probe_exception_then_success(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0, 2.0, 3.0])  # 首轮异常,次轮成功
        textarea = _loc(page, "textarea[placeholder*='有什么新鲜事']").first
        textarea.input_value = AsyncMock(side_effect=[RuntimeError('stale'), ''])
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._wait_for_image_publish_success(page))
        assert textarea.input_value.await_count == 2

    def test_timeout_raises(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0, 61.0])  # deadline=60,第三次 time() 越过
        textarea = _loc(page, "textarea[placeholder*='有什么新鲜事']").first
        textarea.input_value = AsyncMock(return_value='还有内容')
        send_btn = _role(page, 'button', name='发送', exact=True).first
        send_btn.get_attribute = AsyncMock(return_value=None)
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='等待图集发布完成超时'):
            _run(WeiboPlatform._wait_for_image_publish_success(page))


# ── 编排: _upload_one_video 视频全流程 ─────────────────────────────────────

class TestUploadOneVideo:
    @contextmanager
    def _mk_steps(self, p):
        mocks = dict(
            upload_video_file=AsyncMock(),
            wait_upload_form=AsyncMock(),
            set_video_type=AsyncMock(),
            set_title=AsyncMock(),
            set_cover=AsyncMock(),
            set_category=AsyncMock(),
            set_collection=AsyncMock(),
            set_description=AsyncMock(),
            set_content_statement=AsyncMock(),
            click_publish=AsyncMock(),
            wait_publish_success=AsyncMock(),
            close_browser=AsyncMock(),
        )
        with patch.object(p, '_upload_video_file', mocks['upload_video_file']), \
             patch.object(p, '_wait_for_upload_form', mocks['wait_upload_form']), \
             patch.object(p, '_set_video_type', mocks['set_video_type']), \
             patch.object(p, '_set_title', mocks['set_title']), \
             patch.object(p, '_set_cover', mocks['set_cover']), \
             patch.object(p, '_set_category', mocks['set_category']), \
             patch.object(p, '_set_collection', mocks['set_collection']), \
             patch.object(p, '_set_description', mocks['set_description']), \
             patch.object(p, '_set_content_statement', mocks['set_content_statement']), \
             patch.object(p, '_click_publish', mocks['click_publish']), \
             patch.object(p, '_wait_for_publish_success', mocks['wait_publish_success']), \
             patch.object(p, 'close_browser', mocks['close_browser']), \
             patch('asyncio.sleep', AsyncMock()):
            yield mocks

    def _run_flow(self, p, page, **kw):
        default = dict(
            title='标题', file_path='/m/v.mp4', tags=['t1'],
            account_file='/c/u1.json', thumbnail_landscape_path='/l.png',
            thumbnail_portrait_path='/p.png', desc='描述', category=['VLOG', '旅行'],
            ai_content='原创', content_statement='声明',
            content_statement2='必选', content_statement2_optional='可选',
            weibo_collection='',
        )
        default.update(kw)
        return _run(p._upload_one_video(**default))

    def test_happy_full_flow_with_collection(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             self._mk_steps(p) as mocks, patch('impl.weibo.platform.logger'):
            self._run_flow(p, page, weibo_collection='合集A')
        page.goto.assert_awaited_once_with(_WEIBO_UPLOAD_URL, timeout=60000)
        mocks['upload_video_file'].assert_awaited_once_with(page, '/m/v.mp4')
        mocks['set_video_type'].assert_awaited_once_with(page, '原创')
        mocks['set_title'].assert_awaited_once_with(page, '标题')
        mocks['set_cover'].assert_awaited_once_with(
            page, '/l.png', '/p.png', None, None,
        )
        mocks['set_category'].assert_awaited_once_with(page, ['VLOG', '旅行'])
        mocks['set_collection'].assert_awaited_once_with(page, '合集A')
        mocks['set_description'].assert_awaited_once_with(page, '描述', '标题', ['t1'])
        mocks['set_content_statement'].assert_awaited_once_with(
            page, '声明', '必选', '可选',
        )
        mocks['click_publish'].assert_awaited_once_with(page)
        mocks['wait_publish_success'].assert_awaited_once_with(page)
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_no_collection_skips(self):
        p = _mk_platform()
        logger = MagicMock()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             self._mk_steps(p) as mocks, patch('impl.weibo.platform.logger', logger):
            self._run_flow(p, _mk_page())
        mocks['set_collection'].assert_not_awaited()
        assert any('未选择合集,跳过' in str(c) for c in logger.info.call_args_list)

    def test_request_response_handlers(self):
        """_on_upload_request/_on_upload_response:匹配 fileplatform/weibocdn 才计数+日志。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             self._mk_steps(p) as _mocks, patch('impl.weibo.platform.logger') as logger:
            self._run_flow(p, page)
            handlers = _collect_handlers(page)
            assert 'request' in handlers and 'response' in handlers
            # 匹配请求
            req = MagicMock()
            req.url = 'https://fileplatform.weibocdn.com/upload.json'
            req.method = 'POST'
            handlers['request'](req)
            # 不匹配请求(不计数)
            req2 = MagicMock()
            req2.url = 'https://weibo.com/some/api'
            req2.method = 'GET'
            handlers['request'](req2)
            # 匹配响应 + body 读取
            resp = MagicMock()
            resp.url = 'https://weibocdn.com/upload/chunk'
            resp.status = 200
            resp.text = AsyncMock(return_value='ok\nbody')
            _run(handlers['response'](resp))
            # 匹配响应但 body 读取失败
            resp2 = MagicMock()
            resp2.url = 'https://fileplatform.weibocdn.com/x'
            resp2.status = 500
            resp2.text = AsyncMock(side_effect=RuntimeError('no body'))
            _run(handlers['response'](resp2))
            # 不匹配响应(不计数)
            resp3 = MagicMock()
            resp3.url = 'https://weibo.com/upload/api?x=1'
            resp3.status = 200
            resp3.text = AsyncMock(return_value='x')
            _run(handlers['response'](resp3))
            req_logs = [c for c in logger.info.call_args_list
                        if c.args and c.args[0] == '[上传视频] ▲ 请求 #%d %s %s']
            assert len(req_logs) == 1
            resp_logs = [c for c in logger.info.call_args_list
                         if c.args and c.args[0] == '[上传视频] ▼ 响应 #%d status=%d body=%s']
            assert len(resp_logs) == 2  # ok body + body 读取失败
            assert 'ok body' in resp_logs[0].args[3]  # args=(fmt, n, status, body)
            assert 'body 读取失败' in resp_logs[1].args[3]


# ── 编排: _upload_video_file 主文件上传 ────────────────────────────────────

class TestUploadVideoFile:
    MARKED = ("input[type='file'][data-weibo-upload='1'],"
              "input[type='file'][data-weibo-new='1']")

    def test_happy_expect_file_chooser(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0])  # marked input 轮询首轮命中
        media = _mk_media_file()
        try:
            _loc(page, "button[id^='video_button_upload']").first.count = \
                AsyncMock(return_value=1)
            cm, fc = _mk_fc_ctx()
            page.expect_file_chooser = MagicMock(return_value=cm)
            marked = _loc(page, self.MARKED)
            marked.count = AsyncMock(return_value=1)
            with patch('impl.weibo.platform.logger'), \
                 patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(WeiboPlatform._upload_video_file(page, str(media)))
            fc.set_files.assert_awaited_once_with(str(media))
            marked.first.set_input_files.assert_awaited_once_with(str(media))
        finally:
            media.unlink(missing_ok=True)

    def test_role_fallback_button_and_js_click(self):
        """主选择器缺失 → role 回退;fc 失败 → force click;click 也失败 → JS click。"""
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0])
        media = _mk_media_file()
        try:
            # 主选择器 count=0(默认),role 按钮存在
            upload_btn = _role(page, 'button', name='上传视频', exact=True).first
            upload_btn.count = AsyncMock(return_value=1)
            upload_btn.click = AsyncMock(side_effect=RuntimeError('intercepted'))
            upload_btn.evaluate = AsyncMock(return_value='el')
            page.expect_file_chooser = MagicMock(side_effect=RuntimeError('no fc'))
            marked = _loc(page, self.MARKED)
            marked.count = AsyncMock(return_value=1)
            with patch('impl.weibo.platform.logger'), \
                 patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(WeiboPlatform._upload_video_file(page, str(media)))
            upload_btn.evaluate.assert_awaited_once_with('el => el.click()')
            marked.first.set_input_files.assert_awaited_once_with(str(media))
        finally:
            media.unlink(missing_ok=True)

    def test_force_click_success_path(self):
        """fc 失败 → force click 成功(不进 JS click)。"""
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0])
        media = _mk_media_file()
        try:
            upload_btn = _role(page, 'button', name='上传视频', exact=True).first
            upload_btn.count = AsyncMock(return_value=1)
            upload_btn.click = AsyncMock()  # 默认成功
            page.expect_file_chooser = MagicMock(side_effect=RuntimeError('no fc'))
            marked = _loc(page, self.MARKED)
            marked.count = AsyncMock(return_value=1)
            with patch('impl.weibo.platform.logger'), \
                 patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(WeiboPlatform._upload_video_file(page, str(media)))
            upload_btn.click.assert_awaited_once_with(force=True)
            upload_btn.evaluate.assert_not_awaited()
            marked.first.set_input_files.assert_awaited_once_with(str(media))
        finally:
            media.unlink(missing_ok=True)

    def test_marked_input_timeout_raises(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 2.0, 30.0])  # deadline=30,第三次 time() 越过
        media = _mk_media_file()
        try:
            _loc(page, "button[id^='video_button_upload']").first.count = \
                AsyncMock(return_value=1)
            page.expect_file_chooser = MagicMock(side_effect=RuntimeError('no fc'))
            with patch('impl.weibo.platform.logger'), \
                 patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
                 patch('asyncio.sleep', AsyncMock()), \
                 pytest.raises(RuntimeError, match='30s 内未检测到带标记的 file input'):
                _run(WeiboPlatform._upload_video_file(page, str(media)))
        finally:
            media.unlink(missing_ok=True)

    def test_locator_count_exception_continues(self):
        """轮询中 count 抛异常 → warning 吞掉 → 下一轮命中。"""
        page = _mk_page()
        loop = _FakeLoop([0.0, 2.0, 3.0])  # 首轮异常,次轮命中
        media = _mk_media_file()
        try:
            _loc(page, "button[id^='video_button_upload']").first.count = \
                AsyncMock(return_value=1)
            page.expect_file_chooser = MagicMock(side_effect=RuntimeError('no fc'))
            marked = _loc(page, self.MARKED)
            marked.count = AsyncMock(side_effect=[RuntimeError('stale'), 1])
            with patch('impl.weibo.platform.logger') as logger, \
                 patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(WeiboPlatform._upload_video_file(page, str(media)))
            marked.first.set_input_files.assert_awaited_once_with(str(media))
            assert any('locator count 异常' in str(c) for c in logger.warning.call_args_list)
        finally:
            media.unlink(missing_ok=True)

    def test_no_button_found_raises(self):
        page = _mk_page()
        media = _mk_media_file()
        try:
            with patch('impl.weibo.platform.logger'), \
                 pytest.raises(RuntimeError, match='未找到「上传视频」按钮'):
                _run(WeiboPlatform._upload_video_file(page, str(media)))
        finally:
            media.unlink(missing_ok=True)


# ── 编排: _wait_for_upload_form ────────────────────────────────────────────

class TestWaitForUploadForm:
    def test_spinner_gone_only(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0])
        _text(page, '上传中', exact=True).count = AsyncMock(return_value=0)
        _role(page, 'button', name='发布', exact=True).first.is_visible = \
            AsyncMock(return_value=False)
        with patch('impl.weibo.platform.logger') as logger, \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._wait_for_upload_form(page, timeout_s=60))
        assert any('「上传中」DOM 已消失,上传完成' in str(c)
                   for c in logger.info.call_args_list)

    def test_both_signals(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0])
        _text(page, '上传中', exact=True).count = AsyncMock(return_value=0)
        publish_btn = _role(page, 'button', name='发布', exact=True).first
        publish_btn.is_visible = AsyncMock(return_value=True)
        with patch('impl.weibo.platform.logger') as logger, \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._wait_for_upload_form(page, timeout_s=60))
        assert any('「上传中」DOM 已消失且「发布」按钮可见' in str(c)
                   for c in logger.info.call_args_list)

    def test_publish_visible_only(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0])
        _text(page, '上传中', exact=True).count = AsyncMock(return_value=1)
        publish_btn = _role(page, 'button', name='发布', exact=True).first
        publish_btn.is_visible = AsyncMock(return_value=True)
        with patch('impl.weibo.platform.logger') as logger, \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._wait_for_upload_form(page, timeout_s=60))
        assert any('「上传中」DOM 仍存在,但「发布」按钮已可见' in str(c)
                   for c in logger.info.call_args_list)

    def test_probe_exception_then_success(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0, 2.0, 3.0])  # 首轮探测异常,次轮成功
        _text(page, '上传中', exact=True).count = AsyncMock(
            side_effect=[RuntimeError('stale'), 0, 0],
        )
        _role(page, 'button', name='发布', exact=True).first.is_visible = \
            AsyncMock(return_value=False)
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._wait_for_upload_form(page, timeout_s=60))

    def test_upload_failed_probe_exception_swallowed(self):
        """「上传失败」探测抛非 RuntimeError → 吞掉继续 → 次轮 spinner 消失成功。"""
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0, 2.0, 3.0])  # 首轮探测异常,次轮 spinner 消失
        _text(page, '上传中', exact=True).count = AsyncMock(side_effect=[1, 1, 0, 0])
        _role(page, 'button', name='发布', exact=True).first.is_visible = \
            AsyncMock(return_value=False)
        _text(page, '上传失败', exact=True).count = AsyncMock(
            side_effect=[TimeoutError('stale'), 0],
        )
        with patch('impl.weibo.platform.logger') as logger, \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._wait_for_upload_form(page, timeout_s=60))
        assert any('「上传中」DOM 已消失,上传完成' in str(c)
                   for c in logger.info.call_args_list)

    def test_upload_failed_raises(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0])
        _text(page, '上传中', exact=True).count = AsyncMock(return_value=1)
        _role(page, 'button', name='发布', exact=True).first.is_visible = \
            AsyncMock(return_value=False)
        _text(page, '上传失败', exact=True).count = AsyncMock(return_value=1)
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='视频上传失败'):
            _run(WeiboPlatform._wait_for_upload_form(page, timeout_s=60))

    def test_progress_probe_exception_swallowed(self):
        """进度旁证探测抛异常 → except 吞掉 → 次轮 spinner 消失成功。"""
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0, 2.0, 3.0])
        _text(page, '上传中', exact=True).count = AsyncMock(
            side_effect=[1, RuntimeError('stale'), 0],
        )
        _role(page, 'button', name='发布', exact=True).first.is_visible = \
            AsyncMock(return_value=False)
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._wait_for_upload_form(page, timeout_s=60))

    def test_progress_logging(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0, 2.0, 3.0])  # remaining=58 < 60 → 进度日志
        _text(page, '上传中', exact=True).count = AsyncMock(
            side_effect=[1, 0, 0],
        )
        _role(page, 'button', name='发布', exact=True).first.is_visible = \
            AsyncMock(return_value=False)
        with patch('impl.weibo.platform.logger') as logger, \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._wait_for_upload_form(page, timeout_s=60))
        assert any('等待「上传中」消失或「发布」按钮可见' in str(c)
                   for c in logger.info.call_args_list)

    def test_timeout_raises_with_url(self):
        page = _mk_page()
        loop = _FakeLoop([0.0, 1.0, 2.0, 61.0])  # 第四次 time() 越过 deadline
        _text(page, '上传中', exact=True).count = AsyncMock(return_value=1)
        _role(page, 'button', name='发布', exact=True).first.is_visible = \
            AsyncMock(return_value=False)
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='等待视频上传完成超时'):
            _run(WeiboPlatform._wait_for_upload_form(page, timeout_s=60))

    def test_timeout_url_read_fails(self):
        """page.url 读取失败 → url='(unknown)' 进错误信息。"""
        page = _mk_page()
        del page.url
        type(page).url = PropertyMock(side_effect=RuntimeError('gone'))
        loop = _FakeLoop([0.0, 1.0, 2.0, 61.0])
        _text(page, '上传中', exact=True).count = AsyncMock(return_value=1)
        _role(page, 'button', name='发布', exact=True).first.is_visible = \
            AsyncMock(return_value=False)
        with patch('impl.weibo.platform.logger'), \
             patch('impl.weibo.platform.asyncio.get_event_loop', return_value=loop), \
             patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match=r'当前 URL: \(unknown\)'):
            _run(WeiboPlatform._wait_for_upload_form(page, timeout_s=60))


# ── DOM 辅助: 类型 / 标题 / 封面 ──────────────────────────────────────────

class TestSetVideoType:
    def test_empty_skips(self):
        page = _mk_page()
        with patch('impl.weibo.platform.logger'):
            _run(WeiboPlatform._set_video_type(page, ''))
        page.get_by_role.assert_not_called()

    def test_exact_match(self):
        page = _mk_page()
        radio = _role(page, 'radio', name='原创', exact=True).first
        radio.count = AsyncMock(return_value=1)
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_video_type(page, '原创'))
        radio.click.assert_awaited_once_with(force=True)

    def test_partial_match(self):
        page = _mk_page()
        radio = _role(page, 'radio', name='二创', exact=True).first
        radio.count = AsyncMock(return_value=1)
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_video_type(page, '我的二创视频'))
        radio.click.assert_awaited_once_with(force=True)

    def test_unknown_value_warns(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger):
            _run(WeiboPlatform._set_video_type(page, '随便写'))
        assert any('未知类型声明值' in str(c) for c in logger.warning.call_args_list)

    def test_click_failure_warns(self):
        page = _mk_page()
        radio = _role(page, 'radio', name='转载', exact=True).first
        radio.count = AsyncMock(return_value=1)
        radio.click = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_video_type(page, '转载'))
        assert any('选择类型失败' in str(c) for c in logger.warning.call_args_list)


class TestSetTitle:
    def test_empty_skips(self):
        page = _mk_page()
        with patch('impl.weibo.platform.logger'):
            _run(WeiboPlatform._set_title(page, ''))
        page.locator.assert_not_called()

    def test_truncates_to_30_chars(self):
        page = _mk_page()
        title_input = _loc(page, "input[placeholder*='填写标题']").first
        title_input.count = AsyncMock(return_value=1)
        with patch('impl.weibo.platform.logger'):
            _run(WeiboPlatform._set_title(page, '字' * 40))
        title_input.fill.assert_awaited_once_with('字' * 30)

    def test_strips_whitespace(self):
        page = _mk_page()
        title_input = _loc(page, "input[placeholder*='填写标题']").first
        title_input.count = AsyncMock(return_value=1)
        with patch('impl.weibo.platform.logger'):
            _run(WeiboPlatform._set_title(page, '  标题  '))
        title_input.fill.assert_awaited_once_with('标题')


class TestPickCoverByAspect:
    def test_landscape(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=(56.25, None))
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            got = _run(WeiboPlatform._pick_cover_by_aspect(
                page, landscape_path='/l.png', portrait_path='/p.png',
            ))
        assert got == '/l.png'

    def test_portrait(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=(177.78, None))
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            got = _run(WeiboPlatform._pick_cover_by_aspect(
                page, landscape_path='/l.png', portrait_path='/p.png',
            ))
        assert got == '/p.png'

    def test_portrait_fallback_to_landscape(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=(177.78, None))
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            got = _run(WeiboPlatform._pick_cover_by_aspect(
                page, landscape_path='/l.png', portrait_path=None,
            ))
        assert got == '/l.png'

    def test_no_aspect_default_landscape(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=(None, {'reason': 'no cover link found'}))
        with patch('impl.weibo.platform.logger') as logger, \
             patch('asyncio.sleep', AsyncMock()):
            got = _run(WeiboPlatform._pick_cover_by_aspect(
                page, landscape_path='/l.png', portrait_path='/p.png',
            ))
        assert got == '/l.png'
        assert any('封面宽高比调试' in str(c) for c in logger.info.call_args_list)

    def test_square_goes_landscape(self):
        """aspect == 100 → 走横版分支(else 之外还是 <100 为 False → 竖版)。
        实际代码 aspect<100 → 横版;100 属于 else → 竖版。"""
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=(100.0, None))
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            got = _run(WeiboPlatform._pick_cover_by_aspect(
                page, landscape_path='/l.png', portrait_path='/p.png',
            ))
        assert got == '/p.png'

    def test_evaluate_error_default_landscape(self):
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('js boom'))
        with patch('impl.weibo.platform.logger') as logger, \
             patch('asyncio.sleep', AsyncMock()):
            got = _run(WeiboPlatform._pick_cover_by_aspect(
                page, landscape_path='/l.png', portrait_path=None,
            ))
        assert got == '/l.png'
        assert any('读取封面区域宽高比失败' in str(c) for c in logger.warning.call_args_list)

    def test_upload_cover_link_timeout_warns(self):
        page = _mk_page()
        _text(page, '上传封面').first.wait_for = AsyncMock(
            side_effect=RuntimeError('slow'),
        )
        page.evaluate = AsyncMock(return_value=(56.25, None))
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._pick_cover_by_aspect(page, landscape_path='/l.png'))
        assert any('等「上传封面」链接超时' in str(c) for c in logger.warning.call_args_list)

    def test_picture_img_timeout_warns(self):
        page = _mk_page()
        inner = _text(page, '上传封面', exact=True).first.locator('xpath=../..')
        inner.locator('img').first.wait_for = AsyncMock(side_effect=RuntimeError('slow'))
        page.evaluate = AsyncMock(return_value=(56.25, None))
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._pick_cover_by_aspect(page, landscape_path='/l.png'))
        assert any('等封面 picture(img) 超时' in str(c) for c in logger.warning.call_args_list)


class TestSetCover:
    def test_happy_full_flow(self):
        page = _mk_page()
        cover = _mk_media_file('t35_weibo_cover_tmp.png')
        try:
            file_inputs = _loc(page, "input[type='file'][accept^='.jpg']")
            file_inputs.count = AsyncMock(return_value=1)
            with patch.object(WeiboPlatform, '_pick_cover_by_aspect',
                              AsyncMock(return_value=str(cover))), \
                 patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
                _run(WeiboPlatform._set_cover(page, thumbnail_landscape_path='/l.png'))
            link = _text(page, '上传封面').first
            link.click.assert_awaited_once()
            page.keyboard.press.assert_awaited_once_with('Escape')
            file_inputs.first.set_input_files.assert_awaited_once_with(str(cover))
            done = _role(page, 'button', name='完成', exact=True).first
            done.click.assert_awaited_once_with(force=True)
            _text(page, '编辑封面', exact=True).first.wait_for.assert_awaited_once_with(
                state='hidden', timeout=15000,
            )
        finally:
            cover.unlink(missing_ok=True)

    def test_no_cover_path_skips(self):
        page = _mk_page()
        logger = MagicMock()
        with patch.object(WeiboPlatform, '_pick_cover_by_aspect',
                          AsyncMock(return_value=None)), \
             patch('impl.weibo.platform.logger', logger):
            _run(WeiboPlatform._set_cover(page, thumbnail_landscape_path='/l.png'))
        assert any('无封面文件,跳过封面上传' in str(c) for c in logger.info.call_args_list)

    def test_cover_file_missing_on_disk_skips(self):
        page = _mk_page()
        logger = MagicMock()
        with patch.object(WeiboPlatform, '_pick_cover_by_aspect',
                          AsyncMock(return_value='/no/such/cover.png')), \
             patch('impl.weibo.platform.logger', logger):
            _run(WeiboPlatform._set_cover(page, thumbnail_landscape_path='/l.png'))
        assert any('无封面文件,跳过封面上传' in str(c) for c in logger.info.call_args_list)

    def test_upload_cover_entry_missing_skips(self):
        page = _mk_page()
        cover = _mk_media_file('t35_weibo_cover_tmp2.png')
        try:
            _text(page, '上传封面').first.wait_for = AsyncMock(
                side_effect=RuntimeError('gone'),
            )
            logger = MagicMock()
            with patch.object(WeiboPlatform, '_pick_cover_by_aspect',
                              AsyncMock(return_value=str(cover))), \
                 patch('impl.weibo.platform.logger', logger), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(WeiboPlatform._set_cover(page, thumbnail_landscape_path='/l.png'))
            assert any('未找到「上传封面」入口' in str(c) for c in logger.warning.call_args_list)
        finally:
            cover.unlink(missing_ok=True)

    def test_edit_modal_timeout_returns(self):
        page = _mk_page()
        cover = _mk_media_file('t35_weibo_cover_tmp3.png')
        try:
            _text(page, '编辑封面').first.wait_for = AsyncMock(
                side_effect=RuntimeError('slow'),
            )
            logger = MagicMock()
            with patch.object(WeiboPlatform, '_pick_cover_by_aspect',
                              AsyncMock(return_value=str(cover))), \
                 patch('impl.weibo.platform.logger', logger), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(WeiboPlatform._set_cover(page, thumbnail_landscape_path='/l.png'))
            assert any('等待封面弹层超时' in str(c) for c in logger.warning.call_args_list)
            _loc(page, "input[type='file'][accept^='.jpg']").first.set_input_files \
                .assert_not_awaited()
        finally:
            cover.unlink(missing_ok=True)

    def test_file_input_missing_warns(self):
        page = _mk_page()
        cover = _mk_media_file('t35_weibo_cover_tmp4.png')
        try:
            logger = MagicMock()
            with patch.object(WeiboPlatform, '_pick_cover_by_aspect',
                              AsyncMock(return_value=str(cover))), \
                 patch('impl.weibo.platform.logger', logger), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(WeiboPlatform._set_cover(page, thumbnail_landscape_path='/l.png'))
            assert any('封面弹层未找到 input' in str(c) for c in logger.warning.call_args_list)
        finally:
            cover.unlink(missing_ok=True)

    def test_done_button_failure_warns(self):
        page = _mk_page()
        cover = _mk_media_file('t35_weibo_cover_tmp5.png')
        try:
            _loc(page, "input[type='file'][accept^='.jpg']").count = AsyncMock(return_value=1)
            done = _role(page, 'button', name='完成', exact=True).first
            done.click = AsyncMock(side_effect=RuntimeError('boom'))
            logger = MagicMock()
            with patch.object(WeiboPlatform, '_pick_cover_by_aspect',
                              AsyncMock(return_value=str(cover))), \
                 patch('impl.weibo.platform.logger', logger), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(WeiboPlatform._set_cover(page, thumbnail_landscape_path='/l.png'))
            assert any('点击封面完成按钮失败' in str(c) for c in logger.warning.call_args_list)
        finally:
            cover.unlink(missing_ok=True)

    def test_modal_close_timeout_escapes(self):
        page = _mk_page()
        cover = _mk_media_file('t35_weibo_cover_tmp6.png')
        try:
            _loc(page, "input[type='file'][accept^='.jpg']").count = AsyncMock(return_value=1)
            _text(page, '编辑封面', exact=True).first.wait_for = AsyncMock(
                side_effect=RuntimeError('still open'),
            )
            logger = MagicMock()
            with patch.object(WeiboPlatform, '_pick_cover_by_aspect',
                              AsyncMock(return_value=str(cover))), \
                 patch('impl.weibo.platform.logger', logger), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(WeiboPlatform._set_cover(page, thumbnail_landscape_path='/l.png'))
            assert any('等待封面弹层关闭超时' in str(c) for c in logger.warning.call_args_list)
            assert page.keyboard.press.await_count == 3  # 前 1 次 + 关闭兜底 2 次
        finally:
            cover.unlink(missing_ok=True)


# ── DOM 辅助: 分类 ────────────────────────────────────────────────────────

class TestSetCategory:
    def _mk_page_ready(self):
        page = _mk_page()
        _text(page, '请选择合适的频道', exact=True).first.count = AsyncMock(return_value=1)
        return page

    def test_list_category_happy(self):
        p = _mk_platform()
        page = self._mk_page_ready()
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._set_category(page, ['VLOG', '旅行']))
        _text(page, 'VLOG', exact=True).first.click.assert_awaited_once()
        _text(page, '旅行', exact=True).last.click.assert_awaited_once()

    def test_string_category(self):
        p = _mk_platform()
        page = self._mk_page_ready()
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._set_category(page, 'VLOG|旅行'))
        _text(page, 'VLOG', exact=True).first.click.assert_awaited_once()
        _text(page, '旅行', exact=True).last.click.assert_awaited_once()

    def test_string_bad_format_warns(self):
        p = _mk_platform()
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger):
            _run(p._set_category(_mk_page(), '只有一个'))
        assert any('分类字符串格式错误' in str(c) for c in logger.warning.call_args_list)

    def test_unrecognizable_type_warns(self):
        p = _mk_platform()
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger):
            _run(p._set_category(_mk_page(), 12345))
        assert any('分类参数无法识别' in str(c) for c in logger.warning.call_args_list)

    def test_none_skips(self):
        p = _mk_platform()
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger):
            _run(p._set_category(_mk_page(), None))
        assert any('未传分类,使用默认' in str(c) for c in logger.info.call_args_list)

    def test_unknown_pair_warns_but_clicks(self):
        """分类未命中静态表 → warning,但仍尝试在页面上点。"""
        p = _mk_platform()
        page = self._mk_page_ready()
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._set_category(page, ['不存在频道', '不存在子类']))
        assert any('分类未在静态表里命中' in str(c) for c in logger.warning.call_args_list)
        _text(page, '不存在频道', exact=True).first.click.assert_awaited_once()

    def test_trigger_missing_warns(self):
        p = _mk_platform()
        page = _mk_page()
        _text(page, '请选择合适的频道', exact=True).first.wait_for = AsyncMock(
            side_effect=RuntimeError('gone'),
        )
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger):
            _run(p._set_category(page, ['VLOG', '旅行']))
        assert any('未找到分类下拉触发器' in str(c) for c in logger.warning.call_args_list)

    def test_cascade_failure_escapes(self):
        p = _mk_platform()
        page = self._mk_page_ready()
        _text(page, 'VLOG', exact=True).first.wait_for = AsyncMock(
            side_effect=RuntimeError('dropdown not open'),
        )
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._set_category(page, ['VLOG', '旅行']))
        assert any('级联选择失败' in str(c) for c in logger.warning.call_args_list)
        page.keyboard.press.assert_awaited_once_with('Escape')


# ── DOM 辅助: 合集 ────────────────────────────────────────────────────────

class TestSetCollection:
    def _mk_switches(self, page, n, matched_index=None):
        """配置 N 个 woo-switch-main 开关;matched_index 那个 evaluate 返回 True。"""
        sw = _loc(page, SWITCH)
        sw.count = AsyncMock(return_value=n)
        leaves = [_mk_leaf() for _ in range(n)]
        for i, leaf in enumerate(leaves):
            leaf.evaluate = AsyncMock(return_value=(i == matched_index))
        sw.nth = MagicMock(side_effect=lambda i: leaves[i])
        return leaves

    def test_happy(self):
        page = _mk_page()
        self._mk_switches(page, 2, matched_index=1)
        album = _loc(page, ALBUM_INPUT)
        album.count = AsyncMock(return_value=2)
        album_rows = {0: _leaf_with_value('美食(共2集)'), 1: _leaf_with_value('AI(共0集)')}
        album.nth = MagicMock(side_effect=lambda i: album_rows[i])
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_collection(page, 'AI'))
        checkbox = _sub(album_rows[1], (
            "xpath=ancestor::div[contains(@class,'_top2_')]"
            "//label[contains(@class,'woo-checkbox-main')]"
        )).first
        checkbox.click.assert_awaited_once()

    def test_switch_missing_skips(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_collection(page, 'AI'))
        assert any('未找到合集开关' in str(c) for c in logger.warning.call_args_list)

    def test_switch_probe_exception_warns(self):
        page = _mk_page()
        sw = _loc(page, SWITCH)
        sw.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_collection(page, 'AI'))
        assert any('点击合集开关失败' in str(c) for c in logger.warning.call_args_list)

    def test_album_list_not_expanded(self):
        page = _mk_page()
        self._mk_switches(page, 1, matched_index=0)
        album = _loc(page, ALBUM_INPUT)
        album.first.wait_for = AsyncMock(side_effect=RuntimeError('gone'))
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_collection(page, 'AI'))
        assert any('合集列表未展开' in str(c) for c in logger.warning.call_args_list)

    def test_empty_value_skipped(self):
        """value 为空 → continue 跳过该项。"""
        page = _mk_page()
        self._mk_switches(page, 1, matched_index=0)
        album = _loc(page, ALBUM_INPUT)
        album.count = AsyncMock(return_value=2)
        album_rows = {0: _leaf_with_value(''), 1: _leaf_with_value('AI(共0集)')}
        album.nth = MagicMock(side_effect=lambda i: album_rows[i])
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_collection(page, 'AI'))
        _sub(album_rows[1], (
            "xpath=ancestor::div[contains(@class,'_top2_')]"
            "//label[contains(@class,'woo-checkbox-main')]"
        )).first.click.assert_awaited_once()

    def test_no_matching_album_warns(self):
        page = _mk_page()
        self._mk_switches(page, 1, matched_index=0)
        album = _loc(page, ALBUM_INPUT)
        album.count = AsyncMock(return_value=1)
        album.nth = MagicMock(side_effect=lambda i: _leaf_with_value('别的(共1集)'))
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_collection(page, 'AI'))
        assert any('未找到匹配的合集' in str(c) for c in logger.warning.call_args_list)

    def test_checkbox_click_failure_continues(self):
        page = _mk_page()
        self._mk_switches(page, 1, matched_index=0)
        album = _loc(page, ALBUM_INPUT)
        album.count = AsyncMock(return_value=2)
        album_rows = {0: _leaf_with_value('B(共0集)'), 1: _leaf_with_value('B(共1集)')}
        _sub(album_rows[0], (
            "xpath=ancestor::div[contains(@class,'_top2_')]"
            "//label[contains(@class,'woo-checkbox-main')]"
        )).first.click = AsyncMock(side_effect=RuntimeError('boom'))
        album.nth = MagicMock(side_effect=lambda i: album_rows[i])
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_collection(page, 'B'))
        assert any(c.args and '勾选第' in c.args[0]
                   for c in logger.warning.call_args_list)
        # 第 0 项勾选失败 → continue 到第 1 项(同名)并勾选成功
        _sub(album_rows[1], (
            "xpath=ancestor::div[contains(@class,'_top2_')]"
            "//label[contains(@class,'woo-checkbox-main')]"
        )).first.click.assert_awaited_once()


def _leaf_with_value(value):
    leaf = _mk_leaf()
    leaf.get_attribute = AsyncMock(return_value=value)
    return leaf


# ── DOM 辅助: 正文 ────────────────────────────────────────────────────────

class TestSetDescription:
    def test_desc_with_tags(self):
        page = _mk_page()
        with patch('impl.weibo.platform.clear_and_type', AsyncMock()) as cat, \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_description(page, '简介', '标题', ['a', 'b']))
        cat.assert_awaited_once()
        assert cat.await_args.args[1] == '简介 #a #b'
        assert cat.await_args.kwargs['delay'] == 30
        page.keyboard.press.assert_awaited_once_with('Space')

    def test_title_fallback(self):
        page = _mk_page()
        with patch('impl.weibo.platform.clear_and_type', AsyncMock()) as cat, \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_description(page, '', '标题', []))
        assert cat.await_args.args[1] == '标题'

    def test_tags_only(self):
        page = _mk_page()
        with patch('impl.weibo.platform.clear_and_type', AsyncMock()) as cat, \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_description(page, '', '', ['x', 'y']))
        assert cat.await_args.args[1] == '#x #y'

    def test_empty_text_skips(self):
        page = _mk_page()
        textarea = _loc(page, "textarea[placeholder*='有什么新鲜事']").first
        with patch('impl.weibo.platform.clear_and_type', AsyncMock()) as cat, \
             patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_description(page, '   ', '', []))
        cat.assert_not_awaited()
        textarea.click.assert_not_awaited()


# ── DOM 辅助: 内容声明 ────────────────────────────────────────────────────

class TestSetContentStatement:
    def test_v2_detected(self):
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.count = AsyncMock(return_value=1)
        with patch.object(WeiboPlatform, '_set_content_statement_v2', AsyncMock()) as v2, \
             patch.object(WeiboPlatform, '_set_content_statement_v1', AsyncMock()) as v1, \
             patch('impl.weibo.platform.logger'):
            _run(WeiboPlatform._set_content_statement(page, 'v1', 'req', 'opt'))
        v2.assert_awaited_once_with(page, 'req', 'opt')
        v1.assert_not_awaited()

    def test_v2_detection_exception_falls_to_v1(self):
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.count = AsyncMock(
            side_effect=RuntimeError('boom'),
        )
        with patch.object(WeiboPlatform, '_set_content_statement_v2', AsyncMock()) as v2, \
             patch.object(WeiboPlatform, '_set_content_statement_v1', AsyncMock()) as v1, \
             patch('impl.weibo.platform.logger'):
            _run(WeiboPlatform._set_content_statement(page, 'v1', 'req', 'opt'))
        v2.assert_not_awaited()
        v1.assert_awaited_once_with(page, 'v1')

    def test_v2_handler_exception_logged(self):
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.count = AsyncMock(return_value=1)
        with patch.object(WeiboPlatform, '_set_content_statement_v2',
                          AsyncMock(side_effect=RuntimeError('v2 boom'))) as v2, \
             patch.object(WeiboPlatform, '_set_content_statement_v1', AsyncMock()) as v1, \
             patch('impl.weibo.platform.logger') as logger:
            _run(WeiboPlatform._set_content_statement(page, 'v1', 'req', 'opt'))
        v2.assert_awaited_once()
        v1.assert_not_awaited()  # v2 异常不落 v1
        assert any('版本2 处理异常' in str(c) for c in logger.exception.call_args_list)

    def test_v1_path(self):
        page = _mk_page()
        with patch.object(WeiboPlatform, '_set_content_statement_v2', AsyncMock()) as v2, \
             patch.object(WeiboPlatform, '_set_content_statement_v1', AsyncMock()) as v1, \
             patch('impl.weibo.platform.logger'):
            _run(WeiboPlatform._set_content_statement(page, 'v1'))
        v2.assert_not_awaited()
        v1.assert_awaited_once_with(page, 'v1')

    def test_v1_handler_exception_logged(self):
        page = _mk_page()
        with patch.object(WeiboPlatform, '_set_content_statement_v2', AsyncMock()), \
             patch.object(WeiboPlatform, '_set_content_statement_v1',
                          AsyncMock(side_effect=RuntimeError('v1 boom'))), \
             patch('impl.weibo.platform.logger') as logger:
            _run(WeiboPlatform._set_content_statement(page, 'v1'))
        assert any('版本1 处理异常' in str(c) for c in logger.exception.call_args_list)


class TestSetContentStatementV1:
    def test_empty_skips(self):
        page = _mk_page()
        with patch('impl.weibo.platform.logger'):
            _run(WeiboPlatform._set_content_statement_v1(page, ''))
        page.get_by_text.assert_not_called()

    def test_wu_skips(self):
        page = _mk_page()
        with patch('impl.weibo.platform.logger'):
            _run(WeiboPlatform._set_content_statement_v1(page, '无'))
        page.get_by_text.assert_not_called()

    def test_happy(self):
        page = _mk_page()
        trigger = _text(page, '内容声明', exact=True).first
        trigger.count = AsyncMock(return_value=1)
        option = _role(page, 'button', name='内容为自主创作', exact=True).first
        option.count = AsyncMock(return_value=1)
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_content_statement_v1(page, ' 内容为自主创作 '))
        trigger.click.assert_awaited_once_with(force=True)
        option.click.assert_awaited_once()

    def test_trigger_missing_warns(self):
        page = _mk_page()
        _text(page, '内容声明', exact=True).first.wait_for = AsyncMock(
            side_effect=RuntimeError('gone'),
        )
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger):
            _run(WeiboPlatform._set_content_statement_v1(page, '内容为转载'))
        assert any('未找到内容声明入口' in str(c) for c in logger.warning.call_args_list)

    def test_option_failure_escapes(self):
        page = _mk_page()
        option = _role(page, 'button', name='内容为转载', exact=True).first
        option.count = AsyncMock(return_value=1)
        option.click = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_content_statement_v1(page, '内容为转载'))
        assert any('选择内容声明失败' in str(c) for c in logger.warning.call_args_list)
        page.keyboard.press.assert_awaited_once_with('Escape')


class TestSetContentStatementV2:
    def _mk_option(self, page, text, with_btn=True):
        label = _loc(page, f"[class*='_optionLabel']:has-text('{text}')").first
        label.count = AsyncMock(return_value=1)
        btn = _sub(label, 'xpath=ancestor::button[1]')
        btn.count = AsyncMock(return_value=1 if with_btn else 0)
        return label, btn

    def test_happy_with_optional_and_confirm(self):
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.count = AsyncMock(return_value=1)
        panel = _loc(page, "._panel_nsgmr_114, [class*='_panel_']").first
        panel.count = AsyncMock(return_value=1)
        _req_label, req_btn = self._mk_option(page, '含AI生成内容')
        _opt_label, opt_btn = self._mk_option(page, '内容可能引人不适')
        confirm = _loc(page, ".woo-button-content:has-text('确定')").first
        confirm.count = AsyncMock(return_value=1)
        confirm_btn = _sub(confirm, 'xpath=ancestor::button[1]')
        confirm_btn.count = AsyncMock(return_value=1)
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_content_statement_v2(
                page, '含AI生成内容', '内容可能引人不适',
            ))
        req_btn.first.click.assert_awaited_once_with(force=True)
        opt_btn.first.click.assert_awaited_once_with(force=True)
        confirm_btn.first.click.assert_awaited_once_with(force=True)

    def test_required_default_woo(self):
        """必选为空/'无' → 默认点「内容无需标注」。"""
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.count = AsyncMock(return_value=1)
        panel = _loc(page, "._panel_nsgmr_114, [class*='_panel_']").first
        panel.count = AsyncMock(return_value=1)
        _req_label, req_btn = self._mk_option(page, '内容无需标注')
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_content_statement_v2(page, '无'))
        req_btn.first.click.assert_awaited_once_with(force=True)

    def test_btn_missing_clicks_label(self):
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.count = AsyncMock(return_value=1)
        panel = _loc(page, "._panel_nsgmr_114, [class*='_panel_']").first
        panel.count = AsyncMock(return_value=1)
        req_label, _ = self._mk_option(page, '内容无需标注', with_btn=False)
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_content_statement_v2(page, ''))
        req_label.click.assert_awaited_once_with(force=True)

    def test_required_failed_escapes(self):
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.count = AsyncMock(return_value=1)
        panel = _loc(page, "._panel_nsgmr_114, [class*='_panel_']").first
        panel.count = AsyncMock(return_value=1)
        req_label, _ = self._mk_option(page, '内容无需标注')
        req_label.wait_for = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_content_statement_v2(page, ''))
        assert any(c.args and '必选项' in c.args[0]
                   for c in logger.warning.call_args_list)
        page.keyboard.press.assert_awaited_once_with('Escape')

    def test_optional_skipped_when_empty(self):
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.count = AsyncMock(return_value=1)
        panel = _loc(page, "._panel_nsgmr_114, [class*='_panel_']").first
        panel.count = AsyncMock(return_value=1)
        _req_label, req_btn = self._mk_option(page, '内容无需标注')
        confirm = _loc(page, ".woo-button-content:has-text('确定')").first
        confirm.count = AsyncMock(return_value=1)
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_content_statement_v2(page, ''))
        req_btn.first.click.assert_awaited_once()
        # 可选为空 → 不查 _optionLabel;确定按钮 else 分支(btn count=0 → 直点 confirm)
        confirm.click.assert_awaited_once_with(force=True)

    def test_optional_failure_continues_to_confirm(self):
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.count = AsyncMock(return_value=1)
        panel = _loc(page, "._panel_nsgmr_114, [class*='_panel_']").first
        panel.count = AsyncMock(return_value=1)
        _req_label, _ = self._mk_option(page, '内容无需标注')
        opt_label, _ = self._mk_option(page, '内容可能引人不适')
        opt_label.wait_for = AsyncMock(side_effect=RuntimeError('boom'))
        confirm = _loc(page, ".woo-button-content:has-text('确定')").first
        confirm.count = AsyncMock(return_value=1)
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_content_statement_v2(
                page, '', '内容可能引人不适',
            ))
        confirm.click.assert_awaited_once_with(force=True)

    def test_trigger_missing_warns(self):
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.wait_for = AsyncMock(
            side_effect=RuntimeError('gone'),
        )
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger):
            _run(WeiboPlatform._set_content_statement_v2(page, 'x'))
        assert any('未找到 trigger 入口' in str(c) for c in logger.warning.call_args_list)

    def test_panel_missing_warns(self):
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.count = AsyncMock(return_value=1)
        _loc(page, "._panel_nsgmr_114, [class*='_panel_']").first.wait_for = AsyncMock(
            side_effect=RuntimeError('no panel'),
        )
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_content_statement_v2(page, 'x'))
        assert any('面板未展开' in str(c) for c in logger.warning.call_args_list)

    def test_confirm_failure_escapes(self):
        page = _mk_page()
        _text(page, '请进行内容声明', exact=False).first.count = AsyncMock(return_value=1)
        panel = _loc(page, "._panel_nsgmr_114, [class*='_panel_']").first
        panel.count = AsyncMock(return_value=1)
        _req_label, _ = self._mk_option(page, '内容无需标注')
        confirm = _loc(page, ".woo-button-content:has-text('确定')").first
        confirm.count = AsyncMock(return_value=1)
        confirm.wait_for = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.weibo.platform.logger', logger), \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._set_content_statement_v2(page, ''))
        assert any('点内容声明(版本2)确定按钮失败' in str(c)
                   for c in logger.warning.call_args_list)
        page.keyboard.press.assert_awaited_once_with('Escape')


# ── DOM 辅助: 发布按钮 / 发布成功信号 ─────────────────────────────────────

class TestClickPublish:
    def test_happy(self):
        page = _mk_page()
        publish_btn = _role(page, 'button', name='发布', exact=True).first
        publish_btn.count = AsyncMock(return_value=1)
        publish_btn.get_attribute = AsyncMock(return_value=None)
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._click_publish(page))
        publish_btn.click.assert_awaited_once()

    def test_not_found_raises(self):
        page = _mk_page()
        _role(page, 'button', name='发布', exact=True).first.wait_for = AsyncMock(
            side_effect=RuntimeError('gone'),
        )
        with patch('impl.weibo.platform.logger'), \
             pytest.raises(RuntimeError, match='未找到发布按钮'):
            _run(WeiboPlatform._click_publish(page))

    def test_always_disabled_raises(self):
        page = _mk_page()
        publish_btn = _role(page, 'button', name='发布', exact=True).first
        publish_btn.count = AsyncMock(return_value=1)
        publish_btn.get_attribute = AsyncMock(return_value='disabled')
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='发布按钮一直 disabled'):
            _run(WeiboPlatform._click_publish(page))


class TestWaitForPublishSuccess:
    def test_toast_found(self):
        page = _mk_page()
        with patch('impl.weibo.platform.logger') as logger:
            _run(WeiboPlatform._wait_for_publish_success(page))
        toast = _loc(page, 'text=视频已上传成功').first
        toast.wait_for.assert_awaited_once_with(state='visible', timeout=60000)
        assert any('视频已上传成功' in str(c) for c in logger.info.call_args_list)

    def test_url_jumped(self):
        page = _mk_page()
        _loc(page, 'text=视频已上传成功').first.wait_for = AsyncMock(
            side_effect=RuntimeError('no toast'),
        )
        page.url = 'https://weibo.com/video/manage'
        with patch('impl.weibo.platform.logger') as logger, \
             patch('asyncio.sleep', AsyncMock()):
            _run(WeiboPlatform._wait_for_publish_success(page))
        assert any('URL 已跳转' in str(c) for c in logger.info.call_args_list)

    def test_still_on_upload_channel_raises(self):
        page = _mk_page()
        _loc(page, 'text=视频已上传成功').first.wait_for = AsyncMock(
            side_effect=RuntimeError('no toast'),
        )
        page.url = 'https://weibo.com/upload/channel'
        with patch('impl.weibo.platform.logger'), patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='发布后未检测到成功信号'):
            _run(WeiboPlatform._wait_for_publish_success(page))
