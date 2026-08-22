"""小红书 platform.py DOM 交互层契约测试（T35 第 10 期）。

覆盖 impl/xiaohongshu/platform.py（855 stmts，基线 15%）:
- 纯函数: _count_hashtags（空/基本/假阳性/多行）/ _normalize_desc_hashtags（行首空白不动/
  其他位置补空格/双#/tab换行）
- cookie: _parse_cookie_to_storage_state（.xiaohongshu.com 域/expires 未来/httpOnly/
  跳过无效对/去空白）
- 登录/校验/同步: login（QR 码取 3rd img/URL 变化事件/主 frame 才建监听 task/
  save_login_result+stats_fn/context close 异常冒泡但浏览器仍关/create_context 失败保留浏览器/
  create_browser 失败传播） / check_cookie（有效/登录页跳转过期/文件缺失/异常兜底）
  / sync_profile（组装 name+avatar+stats/外层异常空 dict） / _login_stats_fn（goto 超时吞掉/
  抓取异常空） / open_creator_center（真实线程/close 事件异常吞掉/browser close 异常吞掉）
- 编排: publish_video（话题≤10 校验/方向感知封面/排期 compat/多文件×多账号循环/
  scheduled 策略 pub_date 索引） / publish_image（无文件/无账号/截断/dry_run/真实发布/
  部分失败计数/异常日志） / _publish_single_video（全流程/dry_run 等待用户关浏览器/
  is_connected 异常吞掉/context 异常仍关浏览器/上传异常传播） /
  _publish_single_image（dry_run/上传失败 False/真实发布成功与未跳转/scheduled 按钮文案/
  双层异常兜底）
- 上传轮询: _upload_video_content（CDP 扁平化 DOM 探测发布按钮/disabled→enabled/
  轮询异常继续/奇数 attrs IndexError/合集/定时/内容来源声明二级/dry_run 提前 return/
  URL 跳转成功与失败） / _upload_images（四级 input 选择器回退/文件选择器模式/
  按钮回退链/query_selector_all 兜底/上传进度日志/超时 warning/异常兜底）
- 页面就绪: _wait_for_page_ready（submit-disabled=false 首轮命中/等待日志节流/超时截图成功与异常）
- DOM 辅助: _click_publish_button（CDP 定位/class 错位匹配/无按钮/无盒子模型/点击坐标）
  / _fill_title（20 字截断） / _fill_desc（空返回/话题规范化日志/clear_and_type+空格）
  / _fill_tags（desc 聚焦/下拉等待超时/键盘输入） / _set_thumbnail（无路径/文件缺失/
  悬停失败/弹窗重试/确认按钮双选择器/弹窗未隐藏/异常兜底） / _set_collection（名称优先/
  入口回退/浮层选项回退/Escape/异常兜底） / _set_schedule_time（开关+时间输入）
  / _set_content_declaration（一级选项缺失/二级 self/repost/无 source_type 跳过/异常兜底）
  / _fill_self_shooting_dialog（地点下拉 20 轮询/匹配/不匹配/日期单元格/确认按钮回退/异常兜底）
  / _fill_repost_dialog（来源输入/确认按钮回退/异常兜底） / _set_original_declaration（开关缺失/
  已开启/同意弹窗/声明原创按钮） / _scrape_xhs_stats（三指标排序/未知标签/超时/抓取异常/
  数字解析兜底）
"""
import asyncio
import os
import sys
import tempfile
import time as _time
from collections import defaultdict
from contextlib import ExitStack, contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from conf import BASE_DIR
from impl.xiaohongshu.platform import (
    _PUBLISH_STRATEGY_IMMEDIATE,
    _PUBLISH_STRATEGY_SCHEDULED,
    _XHS_CREATOR_URL,
    _XHS_LOGIN_SWITCH_SELECTOR,
    _XHS_LOGIN_URL,
    _XHS_PUBLISH_IMAGE_URL,
    _XHS_PUBLISH_VIDEO_URL,
    XiaohongshuPlatform,
    _click_publish_button,
    _count_hashtags,
    _fill_desc,
    _fill_repost_dialog,
    _fill_self_shooting_dialog,
    _fill_tags,
    _fill_title,
    _normalize_desc_hashtags,
    _publish_single_image,
    _publish_single_video,
    _scrape_xhs_stats,
    _set_collection,
    _set_content_declaration,
    _set_original_declaration,
    _set_schedule_time,
    _set_thumbnail,
    _upload_images,
    _upload_video_content,
    _wait_for_page_ready,
)


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return XiaohongshuPlatform()


def _mk_leaf():
    """叶子 locator：所有异步方法默认成功；locator(sel)/nth(i)/filter(**kw) 返回稳定可预配置对象。"""
    loc = MagicMock()
    loc.count = AsyncMock(return_value=0)
    loc.click = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.set_input_files = AsyncMock()
    loc.get_attribute = AsyncMock(return_value=None)
    loc.inner_text = AsyncMock(return_value='')
    loc.is_visible = AsyncMock(return_value=True)
    loc.fill = AsyncMock()
    loc.type = AsyncMock()
    loc.press = AsyncMock()
    loc.hover = AsyncMock()
    loc.evaluate = AsyncMock(return_value='')
    subs = defaultdict(_mk_locator)
    nth_subs = defaultdict(_mk_leaf)
    filter_subs = defaultdict(_mk_locator)
    loc.locator = MagicMock(side_effect=lambda sel, **kw: subs[sel])
    loc.subs = subs
    loc.nth = MagicMock(side_effect=lambda i: nth_subs[i])
    loc.nth_subs = nth_subs
    loc.filter = MagicMock(side_effect=lambda **kw: filter_subs[tuple(sorted(kw.items()))])
    loc.filter_subs = filter_subs
    return loc


def _mk_locator():
    loc = _mk_leaf()
    loc.first = _mk_leaf()
    loc.last = _mk_leaf()
    return loc


def _mk_page(urls=None):
    if urls is not None:

        class _SeqUrlPage(MagicMock):
            def __init__(self):
                super().__init__()
                self._url_seq = list(urls)

            @property
            def url(self):
                if len(self._url_seq) > 1:
                    return self._url_seq.pop(0)
                return self._url_seq[0]

            @url.setter
            def url(self, v):
                pass

        page = _SeqUrlPage()
    else:
        page = MagicMock()
        page.url = _XHS_CREATOR_URL
    page.main_frame = MagicMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_event = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=[])
    page.evaluate = AsyncMock(return_value=[])
    page.screenshot = AsyncMock()
    page.on = MagicMock()
    page.expect_file_chooser = MagicMock()
    page.mouse = MagicMock()
    page.mouse.click = AsyncMock()
    cdp = MagicMock()
    cdp.send = AsyncMock()
    cdp.detach = AsyncMock()
    page.context = MagicMock()
    page.context.new_cdp_session = AsyncMock(return_value=cdp)
    page.cdp = cdp
    locators = {}
    page.locator = MagicMock(
        side_effect=lambda sel, **kw: locators.setdefault(sel, _mk_locator())
    )
    page.get_by_text = MagicMock(
        side_effect=lambda text, exact=False: locators.setdefault(
            f'text:{text}:{exact}', _mk_locator()
        )
    )
    page.get_by_role = MagicMock(
        side_effect=lambda role, name=None, exact=False: locators.setdefault(
            f'role:{role}:{name}', _mk_locator()
        )
    )
    page.get_by_placeholder = MagicMock(
        side_effect=lambda text, exact=False: locators.setdefault(
            f'ph:{text}:{exact}', _mk_locator()
        )
    )
    page.locators = locators
    return page


def _loc(page, sel):
    """预注册 selector 并返回稳定 locator(page.locators[sel])。"""
    page.locator(sel)
    return page.locators[sel]


@contextmanager
def _mk_browser_chain(platform, urls=None):
    """create_browser/create_context 链的 mocks（with 内生效）。"""
    page = _mk_page(urls=urls)
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.storage_state = AsyncMock()
    context.grant_permissions = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    browser.is_connected = MagicMock(return_value=False)
    with patch.object(platform, 'create_browser', AsyncMock(return_value=browser)) as cb, \
         patch.object(platform, 'create_context', AsyncMock(return_value=context)) as cc:
        yield page, context, browser, cb, cc


def _mk_cookie_file(name='t35_xhs_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


def _mk_img_file(name='t35_xhs_img.png', size=512):
    fd, path = tempfile.mkstemp(prefix=name, suffix='.png')
    with os.fdopen(fd, 'wb') as f:
        f.write(b'x' * size)
    return path


class _AwaitableValue:
    """可 await 的值包装:AsyncMock 实例不可 await,须用真实 __await__。"""

    def __init__(self, value):
        self._value = value

    def __await__(self):
        yield
        return self._value


class _FakeFileChooserCtx:
    """async with 协议走 type 的 __aenter__:MagicMock 实例属性会被忽略,须用真实类。"""

    def __init__(self, fc_info):
        self._fc_info = fc_info

    async def __aenter__(self):
        return self._fc_info

    async def __aexit__(self, *_exc):
        return False


def _mk_expect_file_chooser(page, file_chooser):
    """async with page.expect_file_chooser() 的 __aenter__ 返回 fc_info(value 可 await)。"""
    fc_info = MagicMock()
    fc_info.value = _AwaitableValue(file_chooser)
    page.expect_file_chooser = MagicMock(return_value=_FakeFileChooserCtx(fc_info))
    return fc_info


def _publish_btn_flat(attrs=None):
    """CDP getFlattenedDocument 响应:单个 ce-btn bg-red 发布按钮。"""
    attr_list = []
    for k, v in (attrs or {}).items():
        attr_list.extend([k, v])
    return {'nodes': [{'localName': 'button', 'nodeId': 1, 'attributes': attr_list}]}


@contextmanager
def _mk_upload_video_steps():
    """把 _upload_video_content 内部子步骤替换为可断言的 AsyncMock。"""
    mocks = dict(
        fill_title=AsyncMock(),
        fill_desc=AsyncMock(),
        fill_tags=AsyncMock(),
        set_thumbnail=AsyncMock(),
        set_collection=AsyncMock(),
        set_schedule=AsyncMock(),
        set_content_decl=AsyncMock(),
        set_original=AsyncMock(),
        wait_ready=AsyncMock(),
        click_publish=AsyncMock(),
    )
    with patch('impl.xiaohongshu.platform._fill_title', mocks['fill_title']), \
         patch('impl.xiaohongshu.platform._fill_desc', mocks['fill_desc']), \
         patch('impl.xiaohongshu.platform._fill_tags', mocks['fill_tags']), \
         patch('impl.xiaohongshu.platform._set_thumbnail', mocks['set_thumbnail']), \
         patch('impl.xiaohongshu.platform._set_collection', mocks['set_collection']), \
         patch('impl.xiaohongshu.platform._set_schedule_time', mocks['set_schedule']), \
         patch('impl.xiaohongshu.platform._set_content_declaration', mocks['set_content_decl']), \
         patch('impl.xiaohongshu.platform._set_original_declaration', mocks['set_original']), \
         patch('impl.xiaohongshu.platform._wait_for_page_ready', mocks['wait_ready']), \
         patch('impl.xiaohongshu.platform._click_publish_button', mocks['click_publish']), \
         patch('asyncio.sleep', AsyncMock()):
        yield mocks


def _run_single_video(page, context, browser, **kwargs):
    args = dict(
        title='T', file_path='/v.mp4', tags=[], publish_date=0, account_file='/tmp/a.json',
        create_browser_fn=AsyncMock(return_value=browser),
        create_context_fn=AsyncMock(return_value=context),
    )
    args.update(kwargs)
    return _publish_single_video(**args)


def _run_single_image(page, context, browser, **kwargs):
    args = dict(
        title='T', files=['/i1.png'], tags=[], account_file='/tmp/a.json',
        create_browser_fn=AsyncMock(return_value=browser),
        create_context_fn=AsyncMock(return_value=context),
    )
    args.update(kwargs)
    return _publish_single_image(**args)


# ── 纯函数: 话题计数 / 描述规范化 ──────────────────────────────────────────

class _StubTime:
    """模块级 time 替身:只影响 platform 模块内部 time.time(),序列耗尽后重复末值。"""

    def __init__(self, values):
        self._values = list(values)
        self._last = values[-1]

    def time(self):
        if self._values:
            return self._values.pop(0)
        return self._last


def _mk_stub_time(*values):
    return _StubTime(list(values))


class TestCountHashtags:
    def test_empty_or_none(self):
        assert _count_hashtags('') == 0
        assert _count_hashtags(None) == 0

    def test_basic(self):
        assert _count_hashtags('#a #b #c') == 3
        assert _count_hashtags('前缀 #话题1 后缀 #话题2') == 2

    def test_ignores_false_positives(self):
        assert _count_hashtags('a#b http://x#anchor ## 孤立#') == 0

    def test_multiline(self):
        assert _count_hashtags('第一行 #a\n第二行 #b') == 2


class TestNormalizeDescHashtags:
    def test_empty(self):
        assert _normalize_desc_hashtags('') == ''

    def test_leading_and_after_space_unchanged(self):
        assert _normalize_desc_hashtags('#话题 描述 #话题2') == '#话题 描述 #话题2'

    def test_adds_space_before_embedded_hash(self):
        assert _normalize_desc_hashtags('文案#话题1#话题2 看这个#话题3') == \
            '文案 #话题1 #话题2 看这个 #话题3'

    def test_double_hash(self):
        assert _normalize_desc_hashtags('##') == '# #'

    def test_tab_and_newline_unchanged(self):
        assert _normalize_desc_hashtags('\t#a\n#b') == '\t#a\n#b'


# ── 纯函数: cookie 解析 ────────────────────────────────────────────────────

class TestParseCookieToStorageState:
    def test_happy_parse(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('a=1; b=2')
        assert origins == []
        assert [c['name'] for c in cookies] == ['a', 'b']
        for c in cookies:
            assert c['domain'] == '.xiaohongshu.com'
            assert c['path'] == '/'
            assert c['httpOnly'] is True
            assert c['secure'] is False
            assert c['sameSite'] == 'Lax'
            assert c['expires'] > _time.time()

    def test_expires_in_future_window(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('a=1')
        delta = cookies[0]['expires'] - _time.time()
        assert 6 * 24 * 3600 < delta < 8 * 24 * 3600  # _IMPORT_COOKIE_EXPIRES_SECONDS = 7d

    def test_skips_invalid_pairs(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('a=1; ; novalue')
        assert [c['name'] for c in cookies] == ['a']

    def test_empty(self):
        p = _mk_platform()
        assert p._parse_cookie_to_storage_state('') == ([], [])

    def test_strips_whitespace(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('  a = 1 ; b=2  ')
        by = {c['name']: c for c in cookies}
        assert by['a']['value'] == '1'
        assert by['b']['value'] == '2'


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLogin:
    def test_happy_path(self):
        p = _mk_platform()
        qr = 'data:image/png;base64,xxx'
        with _mk_browser_chain(p, urls=[
            _XHS_CREATOR_URL, _XHS_PUBLISH_VIDEO_URL,
        ]) as (page, context, browser, cb, cc), \
             patch('impl.xiaohongshu.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.xiaohongshu.platform.logger'):
            page.on = MagicMock(side_effect=lambda ev, h: h(page.main_frame))
            img_loc = page.get_by_role('img')
            img_loc.nth(2).get_attribute = AsyncMock(return_value=qr)
            queue = MagicMock()
            _run(p.login('u1', queue, account_id='acc1'))
        cb.assert_awaited_once_with(login_mode=True)
        cc.assert_awaited_once_with(browser)
        page.goto.assert_awaited_once_with(_XHS_CREATOR_URL)
        page.locator(_XHS_LOGIN_SWITCH_SELECTOR).click.assert_awaited_once()
        page.get_by_role.assert_called_with('img')
        assert img_loc.nth(2).get_attribute.await_args.args[0] == 'src'
        assert queue.put.call_args.args[0] == qr
        page.on.assert_called_once_with('framenavigated', page.on.call_args.args[1])
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 1
        assert kwargs['platform_name'] == '小红书'
        assert kwargs['account_id'] == 'acc1'
        assert kwargs['status_queue'] is queue
        assert kwargs['stats_fn'].__func__ is XiaohongshuPlatform._login_stats_fn
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()  # 成功才关浏览器

    def test_subframe_event_ignored_and_no_url_change_blocks(self):
        """非主 frame 不建监听 task；主 frame 但 URL 未变 → 事件不 set → login 挂起。"""
        real_sleep = asyncio.sleep  # patch 前捕获真实 sleep
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.xiaohongshu.platform.save_login_result', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger'):
            page.on = MagicMock(side_effect=lambda ev, h: None)

            async def _probe():
                task = asyncio.create_task(p.login('u1', MagicMock()))
                await real_sleep(0.02)  # 让 login 跑到 page.on 注册
                assert page.on.call_args.args[0] == 'framenavigated'
                handler = page.on.call_args.args[1]
                other = MagicMock()
                assert handler(other) is None  # 非主 frame → None
                t = handler(page.main_frame)  # 主 frame → 建监听 task；URL 未变 → 不 set
                assert t is not None
                await real_sleep(0.02)
                assert not task.done()  # 事件未 set → login 仍挂起
                task.cancel()

            _run(_probe())

    def test_create_context_error_keeps_browser(self):
        p = _mk_platform()
        browser = MagicMock()
        queue = MagicMock()
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(side_effect=RuntimeError('ctx boom'))), \
             patch('impl.xiaohongshu.platform.logger'), pytest.raises(RuntimeError, match='ctx boom'):
            _run(p.login('u1', queue))
        browser.close.assert_not_called()  # 失败保留浏览器看现场
        queue.put.assert_not_called()

    def test_create_browser_error_propagates(self):
        p = _mk_platform()
        queue = MagicMock()
        with patch.object(p, 'create_browser', AsyncMock(side_effect=RuntimeError('browser boom'))), \
             patch('impl.xiaohongshu.platform.logger'), pytest.raises(RuntimeError, match='browser boom'):
            _run(p.login('u1', queue))
        queue.put.assert_not_called()

    def test_context_close_error_still_closes_browser(self):
        p = _mk_platform()
        with _mk_browser_chain(p, urls=[
            _XHS_CREATOR_URL, _XHS_PUBLISH_VIDEO_URL,
        ]) as (page, context, browser, _cb, _cc), \
             patch('impl.xiaohongshu.platform.save_login_result', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger'):
            page.on = MagicMock(side_effect=lambda ev, h: h(page.main_frame))
            context.close = AsyncMock(side_effect=RuntimeError('close boom'))
            with pytest.raises(RuntimeError, match='close boom'):
                _run(p.login('u1', MagicMock()))
            browser.close.assert_awaited_once()  # success=True 仍关浏览器


class TestCheckCookie:
    def test_valid(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_xhs_cc_v.json')
        try:
            with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.xiaohongshu.platform.logger'):
                page.url = _XHS_CREATOR_URL
                assert _run(p.check_cookie(cookie.name)) is True
            page.goto.assert_awaited_once_with(_XHS_CREATOR_URL, timeout=30000)
            page.wait_for_load_state.assert_awaited_once_with('domcontentloaded', timeout=10000)
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_expired_redirect(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_xhs_cc_r.json')
        try:
            with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.xiaohongshu.platform.logger'):
                page.url = _XHS_LOGIN_URL + '?redirect=1'
                assert _run(p.check_cookie(cookie.name)) is False
        finally:
            cookie.unlink(missing_ok=True)

    def test_missing_cookie_file(self):
        p = _mk_platform()
        with patch.object(p, 'create_browser', AsyncMock()) as cb, \
             patch('impl.xiaohongshu.platform.logger'):
            assert _run(p.check_cookie('t35_no_such_cookie.json')) is False
        cb.assert_not_awaited()

    def test_exception_returns_false(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_xhs_cc_e.json')
        try:
            with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.xiaohongshu.platform.logger'):
                page.goto = AsyncMock(side_effect=RuntimeError('net down'))
                assert _run(p.check_cookie(cookie.name)) is False
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)


class TestSyncProfile:
    def test_happy(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_xhs_sp.json')
        stats = [{'ICON': 'follow', 'COUNT': 1, 'NAME': '关注数', 'SORT': 1}]
        try:
            with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
                 patch('impl.xiaohongshu.platform.scrape_user_profile',
                       AsyncMock(return_value=('昵称', 'http://avatar.png'))), \
                 patch('impl.xiaohongshu.platform._scrape_xhs_stats', AsyncMock(return_value=stats)):
                res = _run(p.sync_profile(cookie.name))
            assert res == {'name': '昵称', 'avatar': 'http://avatar.png', 'stats': stats}
            page.goto.assert_awaited_once_with(
                _XHS_CREATOR_URL, wait_until='networkidle', timeout=30000
            )
        finally:
            cookie.unlink(missing_ok=True)

    def test_outer_exception_returns_empty(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_xhs_sp_e.json')
        try:
            with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
                 patch('impl.xiaohongshu.platform.logger'):
                page.goto = AsyncMock(side_effect=RuntimeError('net down'))
                assert _run(p.sync_profile(cookie.name)) == \
                    {'name': '', 'avatar': '', 'stats': []}
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)


class TestLoginStatsFn:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        stats = [{'ICON': 'like', 'COUNT': 7, 'NAME': '获赞与收藏', 'SORT': 3}]
        with patch('impl.xiaohongshu.platform._scrape_xhs_stats', AsyncMock(return_value=stats)):
            assert _run(p._login_stats_fn(page, 'acc1')) == stats
        page.goto.assert_awaited_once_with(
            _XHS_CREATOR_URL, wait_until='networkidle', timeout=30000
        )

    def test_goto_timeout_continues(self):
        p = _mk_platform()
        page = _mk_page()
        page.goto = AsyncMock(side_effect=TimeoutError('slow'))
        with patch('impl.xiaohongshu.platform._scrape_xhs_stats', AsyncMock(return_value=[])):
            assert _run(p._login_stats_fn(page, 'acc1')) == []

    def test_stats_exception_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.xiaohongshu.platform._scrape_xhs_stats',
                   AsyncMock(side_effect=RuntimeError('js boom'))), \
             patch('impl.xiaohongshu.platform.logger') as lg:
            assert _run(p._login_stats_fn(page, 'acc1')) == []
        assert any('抓取失败' in str(c) for c in lg.info.call_args_list)


class TestOpenCreatorCenter:
    def _run_occ(self, page, context, browser):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_xhs_occ.json')
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.xiaohongshu.platform.create_browser_sync',
                       return_value=browser) as cbs, \
                 patch('impl.xiaohongshu.platform.create_context_sync',
                       return_value=context) as ccs:
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            return cbs, ccs
        finally:
            cookie.unlink(missing_ok=True)

    def test_starts_thread(self):
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        cbs, ccs = self._run_occ(page, context, browser)
        cbs.assert_called_once_with(headless=False)
        ccs.assert_called_once()
        page.goto.assert_called_once()
        page.wait_for_event.assert_called_once_with('close', timeout=0)
        browser.close.assert_called_once()

    def test_wait_event_error_swallowed(self):
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        self._run_occ(page, context, browser)
        browser.close.assert_called_once()

    def test_browser_close_error_swallowed(self):
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('boom'))
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        self._run_occ(page, context, browser)
        browser.close.assert_called_once()


# ── 编排层: publish_video / publish_image ─────────────────────────────────

class TestPublishVideo:
    @staticmethod
    def _run_publish(platform, **kwargs):
        single = AsyncMock()
        n_files = len(kwargs.get('files') or [])
        pst = MagicMock(return_value=[
            datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        ] * max(n_files, 1))
        with patch('impl.xiaohongshu.platform._publish_single_video', single), \
             patch('impl.xiaohongshu.platform.parse_schedule_time', pst), \
             patch('impl.xiaohongshu.platform.get_account_name_by_cookie_file',
                   return_value='昵称'), \
             patch('impl.xiaohongshu.platform.bind_account_name', MagicMock()):
            result = asyncio.run(platform.publish_video(**kwargs))
        return result, single

    def test_preflight_over_10_raises(self):
        inst = _mk_platform()
        desc = ' '.join(f'#话题{i}' for i in range(6))
        tags = [f't{i}' for i in range(5)]
        with pytest.raises(ValueError, match='话题总数 11 超过 10'):
            self._run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'],
                              desc=desc, tags=tags)

    def test_exactly_10_topics_ok(self):
        inst = _mk_platform()
        desc = ' '.join(f'#话题{i}' for i in range(5))
        result, single = self._run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            desc=desc, tags=[f't{i}' for i in range(5)],
        )
        assert result is True
        assert single.await_count == 1

    def test_multi_file_multi_account_scheduled_indexing(self):
        inst = _mk_platform()
        dts = [
            datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai')),
            datetime(2026, 8, 22, 11, 30, tzinfo=ZoneInfo('Asia/Shanghai')),
        ]
        single = AsyncMock()
        with patch('impl.xiaohongshu.platform._publish_single_video', single), \
             patch('impl.xiaohongshu.platform.parse_schedule_time', return_value=dts), \
             patch('impl.xiaohongshu.platform.get_account_name_by_cookie_file',
                   return_value='昵称'), \
             patch('impl.xiaohongshu.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'],
                account_file=['a.json', 'b.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
                xhs_collection_id='c1', xhs_collection_name='合集A',
                xhs_source_type='self', xhs_shoot_location='北京',
                xhs_shoot_date='2026-08-01', xhs_repost_source='',
            ))
        assert single.await_count == 4  # 2 文件 × 2 账号
        calls = single.await_args_list
        assert calls[0].kwargs['publish_strategy'] == _PUBLISH_STRATEGY_SCHEDULED
        assert calls[0].kwargs['publish_date'] == dts[0]
        assert calls[2].kwargs['publish_date'] == dts[1]
        assert calls[0].kwargs['account_file'].endswith('a.json')
        assert calls[1].kwargs['account_file'].endswith('b.json')
        assert calls[0].kwargs['collection_id'] == 'c1'
        assert calls[0].kwargs['xhs_source_type'] == 'self'

    def test_immediate_no_timer_compat_zero(self):
        inst = _mk_platform()
        result, single = self._run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
        )
        assert result is True
        call = single.await_args
        assert call.kwargs['publish_strategy'] == _PUBLISH_STRATEGY_IMMEDIATE
        assert call.kwargs['publish_date'] == 0
        assert call.kwargs['create_browser_fn'] == inst.create_browser
        assert call.kwargs['create_context_fn'] == inst.create_context

    def test_horizontal_cover_preference(self):
        inst = _mk_platform()
        _, single = self._run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            video_orientation='horizontal',
            thumbnail_landscape_path='/l.png', thumbnail_portrait_path='/p.png',
            thumbnail_path='/legacy.png',
        )
        assert single.await_args.kwargs['thumbnail_path'] == '/l.png'

    def test_no_files_no_accounts(self):
        inst = _mk_platform()
        result, single = self._run_publish(inst, title='T')
        assert result is True
        assert single.await_count == 0


class TestPublishImage:
    def test_no_files_returns_false(self):
        inst = _mk_platform()
        with patch('impl.xiaohongshu.platform.logger'):
            assert _run(inst.publish_image(title='T', account_file=['a.json'])) is False

    def test_no_accounts_returns_false(self):
        inst = _mk_platform()
        with patch('impl.xiaohongshu.platform.logger'):
            assert _run(inst.publish_image(title='T', files=['/i1.png'])) is False

    def test_happy_dry_run_default(self):
        inst = _mk_platform()
        single = AsyncMock(return_value=True)
        with patch('impl.xiaohongshu.platform._publish_single_image', single), \
             patch('impl.xiaohongshu.platform.parse_schedule_time', return_value=[0]), \
             patch('impl.xiaohongshu.platform.get_account_name_by_cookie_file',
                   return_value='昵称'), \
             patch('impl.xiaohongshu.platform.bind_account_name', MagicMock()):
            assert _run(inst.publish_image(
                title='T', files=['/i1.png'], account_file=['a.json'],
            )) is True
        call = single.await_args
        assert call.kwargs['dry_run'] is True
        assert call.kwargs['publish_date'] == 0

    def test_truncations_and_real_publish(self):
        inst = _mk_platform()
        single = AsyncMock(return_value=True)
        pd = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        with patch('impl.xiaohongshu.platform._publish_single_image', single), \
             patch('impl.xiaohongshu.platform.parse_schedule_time', return_value=[pd]), \
             patch('impl.xiaohongshu.platform.get_account_name_by_cookie_file',
                   return_value='昵称'), \
             patch('impl.xiaohongshu.platform.bind_account_name', MagicMock()):
            result = _run(inst.publish_image(
                title='很长的标题' * 5, files=['/i1.png'],
                tags=[f't{i}' for i in range(12)], account_file=['a.json'],
                desc='很长的描述' * 200, enableTimer=True,
                schedule_time_str='2026-08-22 10:05', ai_content='原创',
                is_original=True, dry_run=False,
            ))
        assert result is True
        call = single.await_args
        assert len(call.kwargs['title']) == 20
        assert len(call.kwargs['tags']) == 10
        assert len(call.kwargs['desc']) == 1000
        assert call.kwargs['publish_date'] == pd
        assert call.kwargs['dry_run'] is False
        assert call.kwargs['is_original'] is True

    def test_partial_failure_counts(self):
        inst = _mk_platform()
        single = AsyncMock(side_effect=[True, False])
        with patch('impl.xiaohongshu.platform._publish_single_image', single), \
             patch('impl.xiaohongshu.platform.parse_schedule_time', return_value=[0, 0]), \
             patch('impl.xiaohongshu.platform.get_account_name_by_cookie_file',
                   return_value='昵称'), \
             patch('impl.xiaohongshu.platform.bind_account_name', MagicMock()):
            assert _run(inst.publish_image(
                title='T', files=['/i1.png'], account_file=['a.json', 'b.json'],
            )) is True  # 1/2 成功 → success_count > 0

    def test_all_fail_returns_false(self):
        inst = _mk_platform()
        single = AsyncMock(return_value=False)
        with patch('impl.xiaohongshu.platform._publish_single_image', single), \
             patch('impl.xiaohongshu.platform.parse_schedule_time', return_value=[0]), \
             patch('impl.xiaohongshu.platform.get_account_name_by_cookie_file',
                   return_value='昵称'), \
             patch('impl.xiaohongshu.platform.bind_account_name', MagicMock()):
            assert _run(inst.publish_image(
                title='T', files=['/i1.png'], account_file=['a.json'],
            )) is False

    def test_account_exception_logged_and_continues(self):
        inst = _mk_platform()
        single = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.xiaohongshu.platform._publish_single_image', single), \
             patch('impl.xiaohongshu.platform.parse_schedule_time', return_value=[0]), \
             patch('impl.xiaohongshu.platform.get_account_name_by_cookie_file',
                   return_value='昵称'), \
             patch('impl.xiaohongshu.platform.bind_account_name', MagicMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(inst.publish_image(
                title='T', files=['/i1.png'], account_file=['a.json'],
            )) is False
        assert any('发布失败' in str(c) for c in logger.error.call_args_list)


# ── 模块级: 单条视频/图集发布 ─────────────────────────────────────────────

class TestPublishSingleVideo:
    def _mk_chain(self):
        page = _mk_page()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        context.storage_state = AsyncMock()
        context.grant_permissions = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        browser.is_connected = MagicMock(return_value=False)
        return page, context, browser

    def test_happy_path(self):
        page, context, browser = self._mk_chain()
        with patch('impl.xiaohongshu.platform._upload_video_content', AsyncMock()) as uv, \
             patch('impl.xiaohongshu.platform.close_browser', AsyncMock()) as cb, \
             patch('asyncio.sleep', AsyncMock()):
            _run(_run_single_video(page, context, browser, tags=['a'], desc='d'))
        uv.assert_awaited_once()
        kwargs = uv.await_args.kwargs
        assert kwargs['title'] == 'T'
        assert kwargs['file_path'] == '/v.mp4'
        assert kwargs['tags'] == ['a']
        context.grant_permissions.assert_awaited_once_with(['geolocation'])
        context.storage_state.assert_awaited_once_with(path='/tmp/a.json')
        context.close.assert_awaited_once()
        cb.assert_awaited_once_with(browser, is_close_by_code=True)

    def test_dry_run_waits_for_user_close(self):
        _page, context, browser = self._mk_chain()
        browser.is_connected = MagicMock(side_effect=[True, False])
        with patch('impl.xiaohongshu.platform._upload_video_content', AsyncMock()), \
             patch('impl.xiaohongshu.platform.close_browser', AsyncMock()), \
             patch('impl.xiaohongshu.platform._PUBLISH_DRY_RUN', True), \
             patch('asyncio.sleep', AsyncMock()):
            _run(_run_single_video(_page, context, browser))
        assert browser.is_connected.call_count == 2  # 轮询循环执行了一次
        context.close.assert_awaited_once()

    def test_dry_run_is_connected_error_swallowed(self):
        _page, context, browser = self._mk_chain()
        browser.is_connected = MagicMock(side_effect=RuntimeError('boom'))
        with patch('impl.xiaohongshu.platform._upload_video_content', AsyncMock()), \
             patch('impl.xiaohongshu.platform.close_browser', AsyncMock()), \
             patch('impl.xiaohongshu.platform._PUBLISH_DRY_RUN', True), \
             patch('asyncio.sleep', AsyncMock()):
            _run(_run_single_video(_page, context, browser))  # 不抛异常
        context.close.assert_awaited_once()

    def test_context_error_still_closes_browser(self):
        _page, _context, browser = self._mk_chain()
        with patch('impl.xiaohongshu.platform.close_browser', AsyncMock()) as cb, \
             patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='ctx boom'):
            _run(_publish_single_video(
                title='T', file_path='/v.mp4', tags=[], publish_date=0,
                account_file='/tmp/a.json',
                create_browser_fn=AsyncMock(return_value=browser),
                create_context_fn=AsyncMock(side_effect=RuntimeError('ctx boom')),
            ))
        cb.assert_awaited_once_with(browser, is_close_by_code=True)

    def test_upload_error_propagates_after_cleanup(self):
        _page, context, browser = self._mk_chain()
        with patch('impl.xiaohongshu.platform._upload_video_content',
                   AsyncMock(side_effect=RuntimeError('up boom'))), \
             patch('impl.xiaohongshu.platform.close_browser', AsyncMock()) as cb, \
             patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='up boom'):
            _run(_run_single_video(_page, context, browser))
        context.close.assert_awaited_once()
        cb.assert_awaited_once_with(browser, is_close_by_code=True)


class TestPublishSingleImage:
    def _mk_chain(self):
        page = _mk_page()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        context.storage_state = AsyncMock()
        context.grant_permissions = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        return page, context, browser

    def _patch_helpers(self):
        return dict(
            upload_images=AsyncMock(return_value=True),
            fill_title=AsyncMock(),
            fill_desc=AsyncMock(),
            fill_tags=AsyncMock(),
            set_original=AsyncMock(),
            set_content_decl=AsyncMock(),
            set_schedule=AsyncMock(),
            wait_ready=AsyncMock(),
            click_publish=AsyncMock(),
            close_browser=AsyncMock(),
        )

    @contextmanager
    def _patch_all(self, mocks):
        patches = [
            patch('impl.xiaohongshu.platform._upload_images', mocks['upload_images']),
            patch('impl.xiaohongshu.platform._fill_title', mocks['fill_title']),
            patch('impl.xiaohongshu.platform._fill_desc', mocks['fill_desc']),
            patch('impl.xiaohongshu.platform._fill_tags', mocks['fill_tags']),
            patch('impl.xiaohongshu.platform._set_original_declaration',
                  mocks['set_original']),
            patch('impl.xiaohongshu.platform._set_content_declaration',
                  mocks['set_content_decl']),
            patch('impl.xiaohongshu.platform._set_schedule_time', mocks['set_schedule']),
            patch('impl.xiaohongshu.platform._wait_for_page_ready', mocks['wait_ready']),
            patch('impl.xiaohongshu.platform._click_publish_button',
                  mocks['click_publish']),
            patch('impl.xiaohongshu.platform.close_browser', mocks['close_browser']),
        ]
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            yield mocks

    def test_happy_dry_run(self):
        page, context, browser = self._mk_chain()
        mocks = self._patch_helpers()
        with self._patch_all(mocks), patch('asyncio.sleep', AsyncMock()):
            assert _run(_run_single_image(page, context, browser)) is True
        page.goto.assert_awaited_once_with(_XHS_PUBLISH_IMAGE_URL)
        page.wait_for_url.assert_awaited_once_with(_XHS_PUBLISH_IMAGE_URL)
        mocks['upload_images'].assert_awaited_once_with(page, ['/i1.png'])
        mocks['fill_title'].assert_awaited_once()
        page.keyboard.press.assert_awaited_once_with('Space')
        mocks['click_publish'].assert_not_awaited()  # dry_run 不点击
        context.storage_state.assert_awaited_once_with(path='/tmp/a.json')
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_upload_failure_returns_false(self):
        page, context, browser = self._mk_chain()
        mocks = self._patch_helpers()
        mocks['upload_images'] = AsyncMock(return_value=False)
        with self._patch_all(mocks), patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger'):
            assert _run(_run_single_image(page, context, browser)) is False
        mocks['fill_title'].assert_not_awaited()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_real_publish_success_and_scheduled(self):
        page, context, browser = self._mk_chain()

        class _UrlPage(MagicMock):
            @property
            def url(self):
                return _XHS_PUBLISH_IMAGE_URL + '?status=success'

        page.url = _UrlPage()
        pd = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        mocks = self._patch_helpers()
        with self._patch_all(mocks), patch('asyncio.sleep', AsyncMock()):
            assert _run(_run_single_image(
                page, context, browser,
                dry_run=False, enableTimer=True, schedule_time_str='2026-08-22 10:05',
                publish_date=pd, ai_content='原创', is_original=True,
            )) is True
        mocks['set_original'].assert_awaited_once_with(page)
        mocks['set_content_decl'].assert_awaited_once_with(page, '原创')
        mocks['set_schedule'].assert_awaited_once_with(page, pd)
        mocks['click_publish'].assert_awaited_once_with(page, '定时发布')
        context.storage_state.assert_awaited_once_with(path='/tmp/a.json')

    def test_real_publish_no_jump_returns_false(self):
        page, context, browser = self._mk_chain()
        page.url = _XHS_PUBLISH_IMAGE_URL  # 停留在发布页 → 未跳转
        mocks = self._patch_helpers()
        with self._patch_all(mocks), patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger'):
            # page.url 始终停留在发布页 → 未跳转
            assert _run(_run_single_image(page, context, browser, dry_run=False)) is False
        mocks['click_publish'].assert_awaited_once_with(page, '发布')
        context.storage_state.assert_not_awaited()

    def test_inner_exception_returns_false(self):
        page, context, browser = self._mk_chain()
        mocks = self._patch_helpers()
        mocks['upload_images'] = AsyncMock(side_effect=RuntimeError('up boom'))
        with self._patch_all(mocks), patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger'):
            assert _run(_run_single_image(page, context, browser)) is False
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_outer_exception_returns_false(self):
        _page, _context, browser = self._mk_chain()
        with patch('impl.xiaohongshu.platform.close_browser', AsyncMock()) as cb, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger'):
            assert _run(_publish_single_image(
                title='T', files=['/i1.png'], tags=[], account_file='/tmp/a.json',
                create_browser_fn=AsyncMock(return_value=browser),
                create_context_fn=AsyncMock(side_effect=RuntimeError('ctx boom')),
            )) is False
        cb.assert_awaited_once_with(browser, is_close_by_code=True)

    def test_upload_zone_timeout_warns_and_continues(self):
        page, context, browser = self._mk_chain()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        mocks = self._patch_helpers()
        logger = MagicMock()
        with self._patch_all(mocks), patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(_run_single_image(page, context, browser)) is True
        page.wait_for_selector.assert_awaited_once_with(
            '.upload-wrapper, .upload-input, input[type="file"]', timeout=15000)
        assert any('未找到上传区域' in str(c) for c in logger.warning.call_args_list)
        mocks['upload_images'].assert_awaited_once_with(page, ['/i1.png'])


# ── 页面就绪轮询 ──────────────────────────────────────────────────────────

class TestWaitForPageReady:
    def test_ready_on_first_poll(self):
        page = _mk_page()
        _loc(page, 'xhs-publish-btn').count = AsyncMock(return_value=1)
        _loc(page, 'xhs-publish-btn').first.get_attribute = AsyncMock(return_value='false')
        with patch('impl.xiaohongshu.platform.time', _mk_stub_time(0.0, 1.0, 1.0)), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger'):
            assert _run(_wait_for_page_ready(page)) is True

    def test_disabled_then_ready(self):
        page = _mk_page()
        _loc(page, 'xhs-publish-btn').count = AsyncMock(return_value=1)
        _loc(page, 'xhs-publish-btn').first.get_attribute = AsyncMock(
            side_effect=['true', 'false']
        )
        with patch('impl.xiaohongshu.platform.time',
                   _mk_stub_time(0.0, 2.0, 3.0, 3.0, 4.0)), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger'):
            assert _run(_wait_for_page_ready(page)) is True

    def test_progress_log_throttle_then_timeout(self):
        page = _mk_page()
        logger = MagicMock()
        # iter1: elapsed 16 → 记录进度日志(last_log=16); iter2: elapsed 20 → 跳过; iter3: 300 超时
        with patch('impl.xiaohongshu.platform.time',
                   _mk_stub_time(0.0, 16.0, 16.0, 20.0, 20.0, 300.0)), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(_wait_for_page_ready(page)) is False
        assert any('仍在等待页面就绪' in str(c) for c in logger.info.call_args_list)
        assert any('页面在' in str(c) and '未就绪' in str(c)
                   for c in logger.error.call_args_list)
        page.screenshot.assert_awaited_once_with(path='debug_page_not_ready.png')

    def test_timeout_screenshot_error_swallowed(self):
        page = _mk_page()
        page.screenshot = AsyncMock(side_effect=RuntimeError('no shot'))
        with patch('impl.xiaohongshu.platform.time', _mk_stub_time(0.0, 300.0)), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger'):
            assert _run(_wait_for_page_ready(page)) is False  # 不抛异常


# ── 上传轮询 / 视频内容填写 ───────────────────────────────────────────────

class TestUploadVideoContent:
    def test_happy_full_flow(self):
        page = _mk_page(urls=[
            _XHS_PUBLISH_VIDEO_URL, _XHS_PUBLISH_VIDEO_URL + '&state=success',
        ])
        page.cdp.send = AsyncMock(side_effect=[
            None, _publish_btn_flat({'class': 'ce-btn bg-red'}),
        ])
        pd = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        with _mk_upload_video_steps() as mocks, \
             patch('impl.xiaohongshu.platform.logger'):
            _run(_upload_video_content(
                page=page, title='T', file_path='/v.mp4', tags=['a'], desc='描述',
                thumbnail_path='/t.png', ai_content='内容来源声明', publish_date=pd,
                publish_strategy=_PUBLISH_STRATEGY_SCHEDULED,
                collection_id='c1', collection_name='合集A',
                xhs_source_type='self', xhs_shoot_location='北京',
                xhs_shoot_date='2026-08-01', xhs_repost_source='',
            ))
        page.goto.assert_awaited_once_with(_XHS_PUBLISH_VIDEO_URL)
        page.wait_for_url.assert_awaited_once_with(_XHS_PUBLISH_VIDEO_URL)
        page.locator("div[class^='upload-content'] input[class='upload-input']") \
            .set_input_files.assert_awaited_once_with('/v.mp4')
        page.cdp.send.assert_any_await('DOM.enable')
        page.cdp.detach.assert_awaited_once()
        mocks['fill_title'].assert_awaited_once_with(page, 'T')
        mocks['fill_desc'].assert_awaited_once_with(page, '描述')
        mocks['fill_tags'].assert_awaited_once_with(page, ['a'])
        mocks['set_thumbnail'].assert_awaited_once_with(page, '/t.png')
        mocks['set_collection'].assert_awaited_once_with(page, 'c1', '合集A')
        mocks['set_schedule'].assert_awaited_once_with(page, pd)
        mocks['set_content_decl'].assert_awaited_once_with(
            page, '内容来源声明', source_type='self', shoot_location='北京',
            shoot_date='2026-08-01', repost_source='',
        )
        mocks['set_original'].assert_awaited_once_with(page)
        mocks['wait_ready'].assert_awaited_once_with(page)
        mocks['click_publish'].assert_awaited_once_with(page, '定时发布')

    def test_upload_poll_disabled_then_enabled(self):
        page = _mk_page(urls=[_XHS_PUBLISH_VIDEO_URL, _XHS_PUBLISH_VIDEO_URL])
        page.cdp.send = AsyncMock(side_effect=[
            None,
            _publish_btn_flat({'class': 'ce-btn bg-red', 'disabled': ''}),
            _publish_btn_flat({'class': 'ce-btn bg-red'}),
        ])
        with _mk_upload_video_steps() as mocks, \
             patch('impl.xiaohongshu.platform.logger'):
            _run(_upload_video_content(
                page=page, title='T', file_path='/v.mp4', tags=[], desc='',
                thumbnail_path='', ai_content='', publish_date=0,
                publish_strategy=_PUBLISH_STRATEGY_IMMEDIATE,
            ))
        assert page.cdp.send.await_count == 3  # enable + 2 次扁平化探测
        mocks['click_publish'].assert_awaited_once_with(page, '发布')

    def test_upload_poll_exception_continues(self):
        page = _mk_page(urls=[_XHS_PUBLISH_VIDEO_URL, _XHS_PUBLISH_VIDEO_URL])
        page.cdp.send = AsyncMock(side_effect=[
            None, RuntimeError('cdp boom'), _publish_btn_flat({'class': 'ce-btn bg-red'}),
        ])
        with _mk_upload_video_steps() as mocks, \
             patch('impl.xiaohongshu.platform.logger') as lg:
            _run(_upload_video_content(
                page=page, title='T', file_path='/v.mp4', tags=[], desc='',
                thumbnail_path='', ai_content='', publish_date=0,
                publish_strategy=_PUBLISH_STRATEGY_IMMEDIATE,
            ))
        assert any('上传状态检查' in str(c) for c in lg.info.call_args_list)
        mocks['click_publish'].assert_awaited_once_with(page, '发布')

    def test_upload_poll_odd_attrs_index_error(self):
        """奇数长度 attrs 触发 IndexError → 轮询 except 吞掉继续。"""
        page = _mk_page(urls=[_XHS_PUBLISH_VIDEO_URL, _XHS_PUBLISH_VIDEO_URL])
        odd = {'nodes': [{'localName': 'button', 'nodeId': 1, 'attributes': ['class']}]}
        page.cdp.send = AsyncMock(side_effect=[
            None, odd, _publish_btn_flat({'class': 'ce-btn bg-red'}),
        ])
        with _mk_upload_video_steps() as mocks, \
             patch('impl.xiaohongshu.platform.logger'):
            _run(_upload_video_content(
                page=page, title='T', file_path='/v.mp4', tags=[], desc='',
                thumbnail_path='', ai_content='', publish_date=0,
                publish_strategy=_PUBLISH_STRATEGY_IMMEDIATE,
            ))
        mocks['click_publish'].assert_awaited_once_with(page, '发布')

    def test_optional_steps_skipped(self):
        page = _mk_page(urls=[_XHS_PUBLISH_VIDEO_URL, _XHS_PUBLISH_VIDEO_URL])
        page.cdp.send = AsyncMock(side_effect=[
            None, _publish_btn_flat({'class': 'ce-btn bg-red'}),
        ])
        with _mk_upload_video_steps() as mocks, \
             patch('impl.xiaohongshu.platform.logger'):
            _run(_upload_video_content(
                page=page, title='T', file_path='/v.mp4', tags=[], desc='',
                thumbnail_path='', ai_content='', publish_date=0,
                publish_strategy=_PUBLISH_STRATEGY_IMMEDIATE,
            ))
        mocks['set_collection'].assert_not_awaited()   # 无合集
        mocks['set_schedule'].assert_not_awaited()     # immediate 策略
        mocks['set_content_decl'].assert_awaited_once_with(
            page, '', source_type='', shoot_location='', shoot_date='', repost_source='',
        )

    def test_no_jump_logs_error(self):
        page = _mk_page(urls=[_XHS_PUBLISH_VIDEO_URL, _XHS_PUBLISH_VIDEO_URL])
        page.cdp.send = AsyncMock(side_effect=[
            None, _publish_btn_flat({'class': 'ce-btn bg-red'}),
        ])
        logger = MagicMock()
        with _mk_upload_video_steps() as mocks, \
             patch('impl.xiaohongshu.platform.logger', logger):
            _run(_upload_video_content(
                page=page, title='T', file_path='/v.mp4', tags=[], desc='',
                thumbnail_path='', ai_content='', publish_date=0,
                publish_strategy=_PUBLISH_STRATEGY_IMMEDIATE,
            ))
        mocks['click_publish'].assert_awaited_once_with(page, '发布')
        assert any('页面未跳转到成功页' in str(c) for c in logger.error.call_args_list)

    def test_dry_run_returns_before_click(self):
        page = _mk_page()
        page.cdp.send = AsyncMock(side_effect=[
            None, _publish_btn_flat({'class': 'ce-btn bg-red'}),
        ])
        with _mk_upload_video_steps() as mocks, \
             patch('impl.xiaohongshu.platform._PUBLISH_DRY_RUN', True), \
             patch('impl.xiaohongshu.platform.logger'):
            _run(_upload_video_content(
                page=page, title='T', file_path='/v.mp4', tags=[], desc='',
                thumbnail_path='', ai_content='', publish_date=0,
                publish_strategy=_PUBLISH_STRATEGY_IMMEDIATE,
            ))
        mocks['click_publish'].assert_not_awaited()  # dry_run 提前 return

    def test_upload_poll_skips_non_button_nodes(self):
        """扁平化文档含非 button 节点时 continue 跳过, 仍能识别发布按钮。"""
        page = _mk_page(urls=[_XHS_PUBLISH_VIDEO_URL, _XHS_PUBLISH_VIDEO_URL])
        flat = {'nodes': [
            {'localName': 'div', 'nodeId': 2, 'attributes': ['class', 'upload-content']},
            {'localName': 'button', 'nodeId': 1,
             'attributes': ['class', 'ce-btn bg-red']},
        ]}
        page.cdp.send = AsyncMock(side_effect=[None, flat])
        with _mk_upload_video_steps() as mocks, \
             patch('impl.xiaohongshu.platform.logger'):
            _run(_upload_video_content(
                page=page, title='T', file_path='/v.mp4', tags=[], desc='',
                thumbnail_path='', ai_content='', publish_date=0,
                publish_strategy=_PUBLISH_STRATEGY_IMMEDIATE,
            ))
        mocks['click_publish'].assert_awaited_once_with(page, '发布')


class TestClickPublishButton:
    def test_happy_click(self):
        page = _mk_page()
        page.cdp.send = AsyncMock(side_effect=[
            None,  # DOM.enable
            {'nodes': [
                {'localName': 'div', 'nodeId': 9},
                {'localName': 'button', 'nodeId': 2,
                 'attributes': ['x', 'y', 'class', 'bg-red']},
            ]},
            None,  # scrollIntoViewIfNeeded
            {'model': {'content': [0, 1, 2, 3, 4, 5, 6, 7]}},
        ])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_click_publish_button(page, '发布'))
        page.evaluate.assert_awaited_once_with(
            'window.scrollTo(0, document.body.scrollHeight)'
        )
        page.cdp.send.assert_any_await('DOM.scrollIntoViewIfNeeded', {'nodeId': 2})
        page.mouse.click.assert_awaited_once_with(2.0, 3.0)
        page.cdp.detach.assert_awaited_once()

    def test_no_button_returns(self):
        page = _mk_page()
        page.cdp.send = AsyncMock(side_effect=[
            None,
            {'nodes': [
                {'localName': 'button', 'nodeId': 1, 'attributes': ['class', None]},
            ]},
        ])
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            _run(_click_publish_button(page, '发布'))
        assert any('未找到发布按钮' in str(c) for c in logger.error.call_args_list)
        page.mouse.click.assert_not_awaited()
        page.cdp.detach.assert_awaited_once()

    def test_box_model_missing_returns(self):
        page = _mk_page()
        page.cdp.send = AsyncMock(side_effect=[
            None,
            _publish_btn_flat({'class': 'bg-red'}),
            None,
            None,  # getBoxModel → None
        ])
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            _run(_click_publish_button(page, '发布'))
        assert any('无法获取发布按钮的盒子模型' in str(c) for c in logger.error.call_args_list)
        page.mouse.click.assert_not_awaited()

    def test_box_model_without_model_key_returns(self):
        page = _mk_page()
        page.cdp.send = AsyncMock(side_effect=[
            None,
            _publish_btn_flat({'class': 'bg-red'}),
            None,
            {'foo': 'bar'},  # 无 'model' 键
        ])
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            _run(_click_publish_button(page, '发布'))
        assert any('无法获取发布按钮的盒子模型' in str(c) for c in logger.error.call_args_list)


# ── DOM 辅助: 标题 / 描述 / 标签 ──────────────────────────────────────────

class TestFillTitle:
    def test_truncates_to_20(self):
        page = _mk_page()
        with patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_title(page, '很长的标题' * 10))
        _loc(page, 'input[placeholder*="填写标题"]').fill.assert_awaited_once_with(
            '很长的标题' * 4
        )


class TestFillDesc:
    def test_empty_returns(self):
        page = _mk_page()
        with patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_desc(page, ''))
        _loc(page, 'p[data-placeholder*="输入正文描述"]').click.assert_not_awaited()

    def test_desc_with_embedded_hashtag_normalizes(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.xiaohongshu.platform.clear_and_type', AsyncMock()) as cat, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            _run(_fill_desc(page, '文案#话题'))
        assert any('已规范化补空格' in str(c) for c in logger.info.call_args_list)
        cat.assert_awaited_once_with(page, '文案 #话题', delay=30)
        page.keyboard.press.assert_awaited_once_with('Space')

    def test_desc_without_hashtag(self):
        page = _mk_page()
        with patch('impl.xiaohongshu.platform.clear_and_type', AsyncMock()) as cat, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_desc(page, '普通描述'))
        cat.assert_awaited_once_with(page, '普通描述', delay=30)


class TestFillTags:
    def test_empty_returns(self):
        page = _mk_page()
        with patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_tags(page, []))
        page.keyboard.type.assert_not_awaited()

    def test_desc_focused_then_type(self):
        page = _mk_page()
        desc = _loc(page, 'p[data-placeholder*="输入正文描述"]')
        desc.count = AsyncMock(return_value=1)
        desc.is_visible = AsyncMock(return_value=True)
        dd = _loc(page, 'div#creator-editor-topic-container div.item').first
        dd.wait_for = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_tags(page, ['三亚']))
        desc.click.assert_awaited_once()
        page.keyboard.type.assert_awaited_once_with('#三亚', delay=30)
        page.keyboard.press.assert_awaited_once_with('Space')
        dd.wait_for.assert_awaited_once_with(state='visible', timeout=8000)

    def test_desc_missing_skips_focus(self):
        page = _mk_page()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_tags(page, ['三亚']))
        _loc(page, 'p[data-placeholder*="输入正文描述"]').click.assert_not_awaited()

    def test_dropdown_timeout_logs_and_continues(self):
        page = _mk_page()
        logger = MagicMock()
        dd = _loc(page, 'div#creator-editor-topic-container div.item').first
        dd.wait_for = AsyncMock(side_effect=TimeoutError('no dropdown'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            _run(_fill_tags(page, ['三亚']))
        assert any('话题下拉未出现' in str(c) for c in logger.info.call_args_list)
        page.keyboard.press.assert_awaited_once_with('Space')


# ── DOM 辅助: 封面 ────────────────────────────────────────────────────────

class TestSetThumbnail:
    def test_no_path_returns(self):
        page = _mk_page()
        with patch('impl.xiaohongshu.platform.logger'):
            _run(_set_thumbnail(page, ''))
        page.locator('div[style*="background-image"]').first.wait_for.assert_not_awaited()

    def test_file_missing_skips(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.xiaohongshu.platform.logger', logger):
            _run(_set_thumbnail(page, '/no/such/cover.png'))
        assert any('封面不存在' in str(c) for c in logger.info.call_args_list)

    def test_happy_path(self):
        page = _mk_page()
        img = _mk_img_file()
        cover = _loc(page, 'div[style*="background-image"]').first
        cover.wait_for = AsyncMock()
        cover.hover = AsyncMock()
        op = _loc(page, 'div.operator.pointer').first
        op.click = AsyncMock()
        _loc(page, 'div.d-modal.cover-modal').count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.d-modal.cover-modal').first
        file_input = modal.subs['input[type="file"][accept*="image"]'].first
        file_input.wait_for = AsyncMock()
        file_input.set_input_files = AsyncMock()
        confirm = modal.subs["button.mojito-button:has-text('确定')"]
        confirm.count = AsyncMock(return_value=1)
        modal.wait_for = AsyncMock()
        try:
            with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
                _run(_set_thumbnail(page, img))
        finally:
            os.unlink(img)
        cover.wait_for.assert_awaited_once_with(state='attached', timeout=10000)
        cover.hover.assert_awaited_once()
        op.click.assert_awaited_once_with(force=True, timeout=5000)
        file_input.set_input_files.assert_awaited_once_with(img)
        confirm.first.click.assert_awaited_once()
        modal.wait_for.assert_awaited_once_with(state='hidden', timeout=15000)

    def test_cover_hover_failure_skips(self):
        page = _mk_page()
        img = _mk_img_file()
        cover = _loc(page, 'div[style*="background-image"]').first
        cover.wait_for = AsyncMock(side_effect=TimeoutError('no cover'))
        logger = MagicMock()
        try:
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.xiaohongshu.platform.logger', logger):
                _run(_set_thumbnail(page, img))
        finally:
            os.unlink(img)
        assert any('封面悬停/点击失败' in str(c) for c in logger.info.call_args_list)

    def test_operator_click_failure_skips(self):
        page = _mk_page()
        img = _mk_img_file()
        cover = _loc(page, 'div[style*="background-image"]').first
        cover.wait_for = AsyncMock()
        op = _loc(page, 'div.operator.pointer').first
        op.click = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        try:
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.xiaohongshu.platform.logger', logger):
                _run(_set_thumbnail(page, img))
        finally:
            os.unlink(img)
        assert any('封面悬停/点击失败' in str(c) for c in logger.info.call_args_list)

    def test_modal_retry_then_found_on_second_selector(self):
        page = _mk_page()
        img = _mk_img_file()
        cover = _loc(page, 'div[style*="background-image"]').first
        cover.wait_for = AsyncMock()
        cover.hover = AsyncMock()
        op = _loc(page, 'div.operator.pointer').first
        op.click = AsyncMock(side_effect=[None, RuntimeError('retry fail')])
        _loc(page, 'div.d-modal.cover-modal').count = AsyncMock(side_effect=[0, 0])
        _loc(page, 'div.cover-modal').count = AsyncMock(side_effect=[0, 1])  # 第 2 次尝试才出现
        modal = _loc(page, 'div.cover-modal').first
        file_input = modal.subs['input[type="file"][accept*="image"]'].first
        file_input.wait_for = AsyncMock()
        file_input.set_input_files = AsyncMock()
        confirm = modal.subs["button.mojito-button:has-text('确定')"]
        confirm.count = AsyncMock(return_value=1)
        modal.wait_for = AsyncMock()
        try:
            with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
                _run(_set_thumbnail(page, img))
        finally:
            os.unlink(img)
        assert op.click.await_count == 2  # 首次 + 重试
        file_input.set_input_files.assert_awaited_once_with(img)

    def test_modal_missing_screenshot_saved(self):
        page = _mk_page()
        img = _mk_img_file()
        cover = _loc(page, 'div[style*="background-image"]').first
        cover.wait_for = AsyncMock()
        op = _loc(page, 'div.operator.pointer').first
        op.click = AsyncMock()
        try:
            with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
                _run(_set_thumbnail(page, img))
        finally:
            os.unlink(img)
        page.screenshot.assert_awaited_once_with(path='debug_cover_modal_missing.png')

    def test_modal_missing_screenshot_error_swallowed(self):
        page = _mk_page()
        img = _mk_img_file()
        cover = _loc(page, 'div[style*="background-image"]').first
        cover.wait_for = AsyncMock()
        op = _loc(page, 'div.operator.pointer').first
        op.click = AsyncMock()
        page.screenshot = AsyncMock(side_effect=RuntimeError('no shot'))
        try:
            with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
                _run(_set_thumbnail(page, img))  # 不抛异常
        finally:
            os.unlink(img)

    def test_file_input_wait_error_swallowed(self):
        page = _mk_page()
        img = _mk_img_file()
        cover = _loc(page, 'div[style*="background-image"]').first
        cover.wait_for = AsyncMock()
        op = _loc(page, 'div.operator.pointer').first
        op.click = AsyncMock()
        _loc(page, 'div.d-modal.cover-modal').count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.d-modal.cover-modal').first
        file_input = modal.subs['input[type="file"][accept*="image"]'].first
        file_input.wait_for = AsyncMock(side_effect=TimeoutError('no input'))
        logger = MagicMock()
        try:
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.xiaohongshu.platform.logger', logger):
                _run(_set_thumbnail(page, img))
        finally:
            os.unlink(img)
        assert any('封面上传失败' in str(c) for c in logger.info.call_args_list)

    def test_confirm_fallback_selector(self):
        page = _mk_page()
        img = _mk_img_file()
        cover = _loc(page, 'div[style*="background-image"]').first
        cover.wait_for = AsyncMock()
        op = _loc(page, 'div.operator.pointer').first
        op.click = AsyncMock()
        _loc(page, 'div.d-modal.cover-modal').count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.d-modal.cover-modal').first
        file_input = modal.subs['input[type="file"][accept*="image"]'].first
        file_input.wait_for = AsyncMock()
        file_input.set_input_files = AsyncMock()
        first_confirm = modal.subs["button.mojito-button:has-text('确定')"]
        first_confirm.count = AsyncMock(return_value=0)
        second_confirm = modal.subs["button:has-text('确定')"]
        second_confirm.count = AsyncMock(return_value=1)
        modal.wait_for = AsyncMock()
        try:
            with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
                _run(_set_thumbnail(page, img))
        finally:
            os.unlink(img)
        second_confirm.first.click.assert_awaited_once()

    def test_confirm_missing_logs(self):
        page = _mk_page()
        img = _mk_img_file()
        cover = _loc(page, 'div[style*="background-image"]').first
        cover.wait_for = AsyncMock()
        op = _loc(page, 'div.operator.pointer').first
        op.click = AsyncMock()
        _loc(page, 'div.d-modal.cover-modal').count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.d-modal.cover-modal').first
        file_input = modal.subs['input[type="file"][accept*="image"]'].first
        file_input.wait_for = AsyncMock()
        file_input.set_input_files = AsyncMock()
        logger = MagicMock()
        try:
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.xiaohongshu.platform.logger', logger):
                _run(_set_thumbnail(page, img))
        finally:
            os.unlink(img)
        assert any('未找到确定按钮' in str(c) for c in logger.info.call_args_list)

    def test_modal_not_hidden_continues(self):
        page = _mk_page()
        img = _mk_img_file()
        cover = _loc(page, 'div[style*="background-image"]').first
        cover.wait_for = AsyncMock()
        op = _loc(page, 'div.operator.pointer').first
        op.click = AsyncMock()
        _loc(page, 'div.d-modal.cover-modal').count = AsyncMock(return_value=1)
        modal = _loc(page, 'div.d-modal.cover-modal').first
        file_input = modal.subs['input[type="file"][accept*="image"]'].first
        file_input.wait_for = AsyncMock()
        file_input.set_input_files = AsyncMock()
        confirm = modal.subs["button.mojito-button:has-text('确定')"]
        confirm.count = AsyncMock(return_value=1)
        modal.wait_for = AsyncMock(side_effect=TimeoutError('still open'))
        logger = MagicMock()
        try:
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.xiaohongshu.platform.logger', logger):
                _run(_set_thumbnail(page, img))
        finally:
            os.unlink(img)
        assert any('封面弹窗未关闭' in str(c) for c in logger.info.call_args_list)


# ── DOM 辅助: 图集上传 ────────────────────────────────────────────────────

class TestUploadImages:
    def test_no_files_warns(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(_upload_images(page, [])) is False
        assert any('没有图片可上传' in str(c) for c in logger.warning.call_args_list)

    def test_happy_file_input(self):
        page = _mk_page()
        file_input = _loc(page, 'input.upload-input[type="file"]')
        file_input.wait_for = AsyncMock()
        file_input.count = AsyncMock(return_value=1)
        file_input.first.set_input_files = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[MagicMock()])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            assert _run(_upload_images(page, ['/i1.png'])) is True
        file_input.first.set_input_files.assert_awaited_once_with(['/i1.png'])

    def test_primary_missing_falls_back_to_jpg_input(self):
        page = _mk_page()
        primary = _loc(page, 'input.upload-input[type="file"]')
        primary.wait_for = AsyncMock(side_effect=TimeoutError('slow'))
        primary.count = AsyncMock(return_value=0)
        jpg = _loc(page, 'input[type="file"][accept*=".jpg"]')
        jpg.count = AsyncMock(return_value=1)
        jpg.first.set_input_files = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[MagicMock()])
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(_upload_images(page, ['/i1.png'])) is True
        assert any('未找到上传input' in str(c) for c in logger.info.call_args_list)
        jpg.first.set_input_files.assert_awaited_once_with(['/i1.png'])

    def test_cascade_to_multiple_input(self):
        page = _mk_page()
        _loc(page, 'input.upload-input[type="file"]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"][accept*=".jpg"]').count = AsyncMock(return_value=0)
        multiple = _loc(page, 'input[type="file"][multiple]')
        multiple.count = AsyncMock(return_value=1)
        multiple.first.set_input_files = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[MagicMock()])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            assert _run(_upload_images(page, ['/i1.png'])) is True
        multiple.first.set_input_files.assert_awaited_once_with(['/i1.png'])

    def test_file_chooser_mode(self):
        page = _mk_page()
        _loc(page, 'input.upload-input[type="file"]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"][accept*=".jpg"]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"][multiple]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"]').count = AsyncMock(return_value=0)
        btn = _loc(page, 'button:has-text("上传图片")')
        btn.count = AsyncMock(return_value=1)
        file_chooser = MagicMock()
        file_chooser.set_files = AsyncMock()
        _mk_expect_file_chooser(page, file_chooser)
        page.query_selector_all = AsyncMock(return_value=[MagicMock()])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            assert _run(_upload_images(page, ['/i1.png'])) is True
        btn.click.assert_awaited_once()
        file_chooser.set_files.assert_awaited_once_with(['/i1.png'])

    def test_upload_button_fallback_to_upload_button_class(self):
        page = _mk_page()
        _loc(page, 'input.upload-input[type="file"]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"][accept*=".jpg"]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"][multiple]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"]').count = AsyncMock(return_value=0)
        _loc(page, 'button:has-text("上传图片")').count = AsyncMock(return_value=0)
        ub = _loc(page, '.upload-button').first
        ub.count = AsyncMock(return_value=1)
        file_chooser = MagicMock()
        file_chooser.set_files = AsyncMock()
        _mk_expect_file_chooser(page, file_chooser)
        page.query_selector_all = AsyncMock(return_value=[MagicMock()])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            assert _run(_upload_images(page, ['/i1.png'])) is True
        ub.click.assert_awaited_once()

    def test_upload_button_fallback_to_bg_red(self):
        page = _mk_page()
        _loc(page, 'input.upload-input[type="file"]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"][accept*=".jpg"]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"][multiple]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"]').count = AsyncMock(return_value=0)
        _loc(page, 'button:has-text("上传图片")').count = AsyncMock(return_value=0)
        _loc(page, '.upload-button').first.count = AsyncMock(return_value=0)
        red = _loc(page, 'button.bg-red').first
        red.count = AsyncMock(return_value=1)
        file_chooser = MagicMock()
        file_chooser.set_files = AsyncMock()
        _mk_expect_file_chooser(page, file_chooser)
        page.query_selector_all = AsyncMock(return_value=[MagicMock()])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            assert _run(_upload_images(page, ['/i1.png'])) is True
        red.click.assert_awaited_once()

    def test_query_selector_all_fallback(self):
        page = _mk_page()
        _loc(page, 'input.upload-input[type="file"]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"][accept*=".jpg"]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"][multiple]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"]').count = AsyncMock(return_value=0)
        _loc(page, 'button:has-text("上传图片")').count = AsyncMock(return_value=0)
        _loc(page, '.upload-button').first.count = AsyncMock(return_value=0)
        _loc(page, 'button.bg-red').first.count = AsyncMock(return_value=0)
        el = MagicMock()
        el.set_input_files = AsyncMock()
        page.query_selector_all = AsyncMock(side_effect=[[el], [MagicMock()]])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            assert _run(_upload_images(page, ['/i1.png'])) is True
        el.set_input_files.assert_awaited_once_with(['/i1.png'])

    def test_no_upload_mechanism_returns_false(self):
        page = _mk_page()
        _loc(page, 'input.upload-input[type="file"]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"][accept*=".jpg"]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"][multiple]').count = AsyncMock(return_value=0)
        _loc(page, 'input[type="file"]').count = AsyncMock(return_value=0)
        _loc(page, 'button:has-text("上传图片")').count = AsyncMock(return_value=0)
        _loc(page, '.upload-button').first.count = AsyncMock(return_value=0)
        _loc(page, 'button.bg-red').first.count = AsyncMock(return_value=0)
        page.query_selector_all = AsyncMock(return_value=[])
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(_upload_images(page, ['/i1.png'])) is False
        assert any('未找到任何上传机制' in str(c) for c in logger.error.call_args_list)

    def test_progress_logging(self):
        page = _mk_page()
        file_input = _loc(page, 'input.upload-input[type="file"]')
        file_input.wait_for = AsyncMock()
        file_input.count = AsyncMock(return_value=1)
        file_input.first.set_input_files = AsyncMock()
        img = MagicMock()
        page.query_selector_all = AsyncMock(side_effect=[[img]] * 10 + [[img, img]])
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(_upload_images(page, ['/i1.png', '/i2.png'])) is True
        assert any('正在上传图片' in str(c) for c in logger.info.call_args_list)
        assert any('全部 %d 张图片上传完成' in str(c) for c in logger.info.call_args_list)

    def test_timeout_warns_returns_partial(self):
        page = _mk_page()
        file_input = _loc(page, 'input.upload-input[type="file"]')
        file_input.wait_for = AsyncMock()
        file_input.count = AsyncMock(return_value=1)
        file_input.first.set_input_files = AsyncMock()
        img = MagicMock()
        page.query_selector_all = AsyncMock(return_value=[img])  # 始终只有 1 张(期望 2 张)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(_upload_images(page, ['/i1.png', '/i2.png'])) is True  # len>0
        assert any('图片上传超时' in str(c) for c in logger.warning.call_args_list)

    def test_timeout_zero_returns_false(self):
        page = _mk_page()
        file_input = _loc(page, 'input.upload-input[type="file"]')
        file_input.wait_for = AsyncMock()
        file_input.count = AsyncMock(return_value=1)
        file_input.first.set_input_files = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(_upload_images(page, ['/i1.png', '/i2.png'])) is False
        assert any('图片上传超时' in str(c) for c in logger.warning.call_args_list)

    def test_outer_exception_returns_false(self):
        page = _mk_page()
        file_input = _loc(page, 'input.upload-input[type="file"]')
        file_input.wait_for = AsyncMock()
        file_input.count = AsyncMock(return_value=1)
        file_input.first.set_input_files = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(_upload_images(page, ['/i1.png'])) is False
        assert any('图片上传失败' in str(c) for c in logger.error.call_args_list)


# ── DOM 辅助: 合集 / 定时 / 声明 ──────────────────────────────────────────

class TestSetCollection:
    def test_no_label_returns(self):
        page = _mk_page()
        with patch('impl.xiaohongshu.platform.logger'):
            _run(_set_collection(page, '', ''))
        page.get_by_text.assert_not_called()

    def test_happy_path(self):
        page = _mk_page()
        entry = page.get_by_text('加入合集', exact=True)
        entry.count = AsyncMock(return_value=1)
        entry_card = entry.subs['xpath=ancestor::*[contains(.,\'选择合集\')][1]'].first
        entry_card.click = AsyncMock()
        option = page.get_by_text('合集A', exact=True)
        option.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_set_collection(page, 'c1', '合集A'))
        entry_card.click.assert_awaited_once_with(timeout=5000)
        option.first.click.assert_awaited_once()

    def test_entry_fallback_text(self):
        page = _mk_page()
        page.get_by_text('加入合集', exact=True).count = AsyncMock(return_value=0)
        entry = page.get_by_text('选择合集', exact=False).first  # 平台代码退回 .first
        entry.count = AsyncMock(return_value=1)
        entry_card = entry.subs['xpath=ancestor::*[contains(.,\'选择合集\')][1]'].first
        entry_card.click = AsyncMock()
        option = page.get_by_text('c1', exact=True)
        option.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_set_collection(page, 'c1', ''))  # 名称缺失 → 退回 id
        entry_card.click.assert_awaited_once_with(timeout=5000)

    def test_entry_missing_warns(self):
        page = _mk_page()
        page.get_by_text('加入合集', exact=True).count = AsyncMock(return_value=0)
        page.get_by_text('选择合集', exact=False).count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('impl.xiaohongshu.platform.logger', logger):
            _run(_set_collection(page, 'c1', '合集A'))
        assert any('未找到「加入合集」入口' in str(c) for c in logger.warning.call_args_list)

    def test_entry_card_click_falls_back_to_entry(self):
        page = _mk_page()
        entry = page.get_by_text('加入合集', exact=True)
        entry.count = AsyncMock(return_value=1)
        entry_card = entry.subs['xpath=ancestor::*[contains(.,\'选择合集\')][1]'].first
        entry_card.click = AsyncMock(side_effect=TimeoutError('no card'))
        entry.first.click = AsyncMock()
        option = page.get_by_text('合集A', exact=True)
        option.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_set_collection(page, 'c1', '合集A'))
        entry.first.click.assert_awaited_once_with(timeout=5000)

    def test_option_partial_match(self):
        page = _mk_page()
        entry = page.get_by_text('加入合集', exact=True)
        entry.count = AsyncMock(return_value=1)
        entry_card = entry.subs['xpath=ancestor::*[contains(.,\'选择合集\')][1]'].first
        entry_card.click = AsyncMock()
        page.get_by_text('合集A', exact=True).count = AsyncMock(return_value=0)
        option = page.get_by_text('合集A', exact=False)
        option.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_set_collection(page, 'c1', '合集A'))
        option.first.click.assert_awaited_once()

    def test_option_missing_escape(self):
        page = _mk_page()
        entry = page.get_by_text('加入合集', exact=True)
        entry.count = AsyncMock(return_value=1)
        entry_card = entry.subs['xpath=ancestor::*[contains(.,\'选择合集\')][1]'].first
        entry_card.click = AsyncMock()
        page.get_by_text('合集A', exact=True).count = AsyncMock(return_value=0)
        page.get_by_text('合集A', exact=False).count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_set_collection(page, 'c1', '合集A'))
        page.keyboard.press.assert_awaited_once_with('Escape')
        assert any('浮层内未找到合集' in str(c) for c in logger.warning.call_args_list)

    def test_outer_exception_warns(self):
        page = _mk_page()
        entry = page.get_by_text('加入合集', exact=True)
        entry.count = AsyncMock(return_value=1)
        entry_card = entry.subs['xpath=ancestor::*[contains(.,\'选择合集\')][1]'].first
        entry_card.click = AsyncMock(side_effect=TimeoutError('no card'))
        entry.first.click = AsyncMock(side_effect=TimeoutError('no entry'))
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_set_collection(page, 'c1', '合集A'))  # 不抛异常
        assert any('合集设置失败' in str(c) for c in logger.warning.call_args_list)


class TestSetScheduleTime:
    def test_happy_path(self):
        page = _mk_page()
        pd = datetime(2026, 8, 22, 10, 5, tzinfo=ZoneInfo('Asia/Shanghai'))
        card = _loc(page, '.custom-switch-card')
        switch = card.filter_subs[(('has_text', '定时发布'),)].subs['.d-switch']
        switch.click = AsyncMock()
        time_input = _loc(page, '.d-datepicker-input-filter input.d-text')
        time_input.fill = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_set_schedule_time(page, pd))
        switch.click.assert_awaited_once()
        time_input.fill.assert_awaited_once_with('2026-08-22 10:05')


class TestSetContentDeclaration:
    def test_no_ai_content_returns(self):
        page = _mk_page()
        with patch('impl.xiaohongshu.platform.logger'):
            _run(_set_content_declaration(page, ''))
        page.get_by_text.assert_not_called()

    def test_simple_declaration(self):
        page = _mk_page()
        trigger = page.get_by_text('添加内容类型声明', exact=True)
        trigger.subs['xpath=ancestor::div[contains(@class,\'d-select\')][1]'] \
            .first.click = AsyncMock()
        option = page.get_by_text('原创', exact=True)
        option.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_set_content_declaration(page, '原创'))
        option.first.click.assert_awaited_once()

    def test_source_self_flow(self):
        page = _mk_page()
        trigger = page.get_by_text('添加内容类型声明', exact=True)
        trigger.subs['xpath=ancestor::div[contains(@class,\'d-select\')][1]'] \
            .first.click = AsyncMock()
        option = page.get_by_text('内容来源声明', exact=True)
        option.count = AsyncMock(return_value=1)
        second = page.get_by_text('自主拍摄', exact=True)
        second.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform._fill_self_shooting_dialog',
                   AsyncMock()) as self_dlg, \
             patch('impl.xiaohongshu.platform.logger'):
            _run(_set_content_declaration(
                page, '内容来源声明', source_type='self',
                shoot_location='北京', shoot_date='2026-08-01', repost_source='',
            ))
        second.first.click.assert_awaited_once()
        self_dlg.assert_awaited_once_with(page, '北京', '2026-08-01')

    def test_source_repost_flow(self):
        page = _mk_page()
        trigger = page.get_by_text('添加内容类型声明', exact=True)
        trigger.subs['xpath=ancestor::div[contains(@class,\'d-select\')][1]'] \
            .first.click = AsyncMock()
        option = page.get_by_text('内容来源声明', exact=True)
        option.count = AsyncMock(return_value=1)
        second = page.get_by_text('来源转载', exact=True)
        second.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.xiaohongshu.platform._fill_repost_dialog', AsyncMock()) as repost_dlg, \
             patch('impl.xiaohongshu.platform.logger'):
            _run(_set_content_declaration(
                page, '内容来源声明', source_type='repost', repost_source='https://x.com',
            ))
        second.first.click.assert_awaited_once()
        repost_dlg.assert_awaited_once_with(page, 'https://x.com')

    def test_source_type_missing_skips_secondary(self):
        page = _mk_page()
        trigger = page.get_by_text('添加内容类型声明', exact=True)
        trigger.subs['xpath=ancestor::div[contains(@class,\'d-select\')][1]'] \
            .first.click = AsyncMock()
        option = page.get_by_text('内容来源声明', exact=True)
        option.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_set_content_declaration(page, '内容来源声明', source_type=''))
        option.first.click.assert_awaited_once()

    def test_option_missing_returns(self):
        page = _mk_page()
        trigger = page.get_by_text('添加内容类型声明', exact=True)
        trigger.subs['xpath=ancestor::div[contains(@class,\'d-select\')][1]'] \
            .first.click = AsyncMock()
        page.get_by_text('原创', exact=True).count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_set_content_declaration(page, '原创'))
        assert page.get_by_text('原创', exact=True).first.click.await_count == 0

    def test_second_option_missing_warns(self):
        page = _mk_page()
        trigger = page.get_by_text('添加内容类型声明', exact=True)
        trigger.subs['xpath=ancestor::div[contains(@class,\'d-select\')][1]'] \
            .first.click = AsyncMock()
        option = page.get_by_text('内容来源声明', exact=True)
        option.count = AsyncMock(return_value=1)
        page.get_by_text('自主拍摄', exact=True).count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_set_content_declaration(page, '内容来源声明', source_type='self'))
        assert any('未找到二级选项' in str(c) for c in logger.warning.call_args_list)

    def test_trigger_click_error_swallowed(self):
        page = _mk_page()
        trigger = page.get_by_text('添加内容类型声明', exact=True)
        trigger.subs['xpath=ancestor::div[contains(@class,\'d-select\')][1]'] \
            .first.click = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_set_content_declaration(page, '原创'))
        assert any('内容声明设置失败' in str(c) for c in logger.info.call_args_list)


# ── DOM 辅助: 自主拍摄 / 来源转载弹窗 ─────────────────────────────────────

class TestFillSelfShootingDialog:
    def test_happy_path(self):
        page = _mk_page()
        loc_input = page.get_by_placeholder('下拉选择地点', exact=False)
        loc_input.count = AsyncMock(return_value=1)
        loc_input.first.type = AsyncMock()
        option_items = _loc(page, 'li[role="option"]')
        option_items.count = AsyncMock(return_value=1)
        li = option_items.nth(0)
        name_el = li.subs['div.name'].first
        name_el.count = AsyncMock(return_value=1)
        name_el.inner_text = AsyncMock(return_value='北京')
        li.click = AsyncMock()
        date_trigger = page.get_by_text('拍摄日期', exact=True).subs['xpath=following::input[1]']
        date_trigger.count = AsyncMock(return_value=1)
        day_cell = page.get_by_text('1', exact=True).first
        day_cell.click = AsyncMock()
        confirm = page.get_by_role('button', name='确认', exact=False)
        confirm.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_self_shooting_dialog(page, '北京', '2026-08-01'))
        loc_input.first.click.assert_awaited_once()
        loc_input.first.type.assert_awaited_once_with('北京', delay=80)
        li.click.assert_awaited_once()
        date_trigger.first.click.assert_awaited_once()
        day_cell.click.assert_awaited_once_with(timeout=3000)
        confirm.first.click.assert_awaited_once()

    def test_no_location_no_date(self):
        page = _mk_page()
        confirm = page.get_by_role('button', name='确认', exact=False)
        confirm.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_self_shooting_dialog(page, '', ''))
        page.get_by_placeholder('下拉选择地点', exact=False).first.click.assert_not_awaited()
        page.get_by_text('拍摄日期', exact=True).first.click.assert_not_awaited()
        confirm.first.click.assert_awaited_once()

    def test_dropdown_never_appears(self):
        page = _mk_page()
        loc_input = page.get_by_placeholder('下拉选择地点', exact=False)
        loc_input.count = AsyncMock(return_value=1)
        loc_input.first.type = AsyncMock()
        option_items = _loc(page, 'li[role="option"]')
        option_items.count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_fill_self_shooting_dialog(page, '北京', ''))
        assert any('地点下拉出现 %d 个选项' in str(c) for c in logger.info.call_args_list)
        assert any('未找到匹配地点选项' in str(c) for c in logger.info.call_args_list)

    def test_name_mismatch_not_selected(self):
        page = _mk_page()
        loc_input = page.get_by_placeholder('下拉选择地点', exact=False)
        loc_input.count = AsyncMock(return_value=1)
        loc_input.first.type = AsyncMock()
        option_items = _loc(page, 'li[role="option"]')
        option_items.count = AsyncMock(return_value=1)
        li = option_items.nth(0)
        name_el = li.subs['div.name'].first
        name_el.count = AsyncMock(return_value=1)
        name_el.inner_text = AsyncMock(return_value='上海')
        li.click = AsyncMock()
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_fill_self_shooting_dialog(page, '北京', ''))
        li.click.assert_not_awaited()
        assert any('未找到匹配地点选项' in str(c) for c in logger.info.call_args_list)

    def test_name_el_missing_continues(self):
        page = _mk_page()
        loc_input = page.get_by_placeholder('下拉选择地点', exact=False)
        loc_input.count = AsyncMock(return_value=1)
        loc_input.first.type = AsyncMock()
        option_items = _loc(page, 'li[role="option"]')
        option_items.count = AsyncMock(return_value=2)
        li0 = option_items.nth(0)
        li0.subs['div.name'].first.count = AsyncMock(return_value=0)
        li1 = option_items.nth(1)
        name_el1 = li1.subs['div.name'].first
        name_el1.count = AsyncMock(return_value=1)
        name_el1.inner_text = AsyncMock(return_value='北京')
        li1.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_self_shooting_dialog(page, '北京', ''))
        li1.click.assert_awaited_once()

    def test_day_cell_click_error_swallowed(self):
        page = _mk_page()
        date_trigger = page.get_by_text('拍摄日期', exact=True).subs['xpath=following::input[1]']
        date_trigger.count = AsyncMock(return_value=1)
        day_cell = page.get_by_text('1', exact=True).first
        day_cell.click = AsyncMock(side_effect=TimeoutError('no cell'))
        confirm = page.get_by_role('button', name='确认', exact=False)
        confirm.count = AsyncMock(return_value=1)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_fill_self_shooting_dialog(page, '', '2026-08-00'))  # day '' → '1' 兜底
        assert any('日期单元格点击失败' in str(c) for c in logger.info.call_args_list)
        confirm.first.click.assert_awaited_once()

    def test_date_trigger_missing_skips(self):
        page = _mk_page()
        page.get_by_text('拍摄日期', exact=True).subs['xpath=following::input[1]'] \
            .count = AsyncMock(return_value=0)
        confirm = page.get_by_role('button', name='确认', exact=False)
        confirm.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_self_shooting_dialog(page, '', '2026-08-15'))
        confirm.first.click.assert_awaited_once()

    def test_confirm_text_fallback(self):
        page = _mk_page()
        page.get_by_role('button', name='确认', exact=False).count = AsyncMock(return_value=0)
        text_confirm = page.get_by_text('确认', exact=True)
        text_confirm.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_self_shooting_dialog(page, '', ''))
        text_confirm.first.click.assert_awaited_once()

    def test_outer_exception_warns(self):
        page = _mk_page()
        loc_input = page.get_by_placeholder('下拉选择地点', exact=False)
        loc_input.count = AsyncMock(return_value=1)
        loc_input.first.type = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_fill_self_shooting_dialog(page, '北京', ''))  # 不抛异常
        assert any('填写失败' in str(c) for c in logger.warning.call_args_list)


class TestFillRepostDialog:
    def test_happy_path(self):
        page = _mk_page()
        src_input = page.get_by_placeholder('请输入媒体名称', exact=False)
        src_input.count = AsyncMock(return_value=1)
        src_input.first.fill = AsyncMock()
        confirm = page.get_by_role('button', name='确认', exact=False)
        confirm.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_repost_dialog(page, '某媒体'))
        src_input.first.click.assert_awaited_once()
        src_input.first.fill.assert_awaited_once_with('某媒体')
        confirm.first.click.assert_awaited_once()

    def test_no_repost_source(self):
        page = _mk_page()
        confirm = page.get_by_role('button', name='确认', exact=False)
        confirm.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_repost_dialog(page, ''))
        page.get_by_placeholder('请输入媒体名称', exact=False).first.click.assert_not_awaited()
        confirm.first.click.assert_awaited_once()

    def test_input_missing_logs(self):
        page = _mk_page()
        page.get_by_placeholder('请输入媒体名称', exact=False).count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_fill_repost_dialog(page, '某媒体'))
        assert any('未找到转载来源输入框' in str(c) for c in logger.info.call_args_list)

    def test_confirm_text_fallback(self):
        page = _mk_page()
        page.get_by_role('button', name='确认', exact=False).count = AsyncMock(return_value=0)
        text_confirm = page.get_by_text('确认', exact=True)
        text_confirm.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_fill_repost_dialog(page, ''))
        text_confirm.first.click.assert_awaited_once()

    def test_outer_exception_warns(self):
        page = _mk_page()
        src_input = page.get_by_placeholder('请输入媒体名称', exact=False)
        src_input.count = AsyncMock(return_value=1)
        src_input.first.fill = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_fill_repost_dialog(page, '某媒体'))  # 不抛异常
        assert any('填写失败' in str(c) for c in logger.warning.call_args_list)


# ── DOM 辅助: 原创声明 ────────────────────────────────────────────────────

class TestSetOriginalDeclaration:
    @staticmethod
    def _switch(page):
        return _loc(page, '.custom-switch-card').filter_subs[(('has_text', '原创声明'),)] \
            .subs['.d-switch']

    def test_switch_missing_skips(self):
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.xiaohongshu.platform.logger', logger):
            _run(_set_original_declaration(page))
        assert any('未找到原创声明开关' in str(c) for c in logger.info.call_args_list)

    def test_already_checked_returns(self):
        page = _mk_page()
        switch = self._switch(page)
        switch.count = AsyncMock(return_value=1)
        switch.first.get_attribute = AsyncMock(return_value='d-switch-checked')
        logger = MagicMock()
        with patch('impl.xiaohongshu.platform.logger', logger):
            _run(_set_original_declaration(page))
        assert any('原创声明已开启' in str(c) for c in logger.info.call_args_list)
        switch.first.click.assert_not_awaited()

    def test_happy_path(self):
        page = _mk_page()
        switch = self._switch(page)
        switch.count = AsyncMock(return_value=1)
        switch.first.get_attribute = AsyncMock(return_value=None)
        modal = _loc(page, 'div.d-modal.d-modal-centered')
        modal.count = AsyncMock(return_value=1)
        checkbox = modal.first.subs['.d-checkbox-simulator']
        checkbox.count = AsyncMock(return_value=1)
        confirm = modal.first.subs['button:has-text("声明原创")']
        confirm.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_set_original_declaration(page))
        switch.first.click.assert_awaited_once()
        checkbox.first.click.assert_awaited_once()
        confirm.first.click.assert_awaited_once()
        page.wait_for_timeout.assert_any_await(1500)

    def test_checkbox_missing(self):
        page = _mk_page()
        switch = self._switch(page)
        switch.count = AsyncMock(return_value=1)
        switch.first.get_attribute = AsyncMock(return_value=None)
        modal = _loc(page, 'div.d-modal.d-modal-centered')
        modal.count = AsyncMock(return_value=1)
        modal.first.subs['.d-checkbox-simulator'].count = AsyncMock(return_value=0)
        confirm = modal.first.subs['button:has-text("声明原创")']
        confirm.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger'):
            _run(_set_original_declaration(page))
        modal.first.subs['.d-checkbox-simulator'].first.click.assert_not_awaited()
        confirm.first.click.assert_awaited_once()

    def test_confirm_missing_logs(self):
        page = _mk_page()
        switch = self._switch(page)
        switch.count = AsyncMock(return_value=1)
        switch.first.get_attribute = AsyncMock(return_value=None)
        modal = _loc(page, 'div.d-modal.d-modal-centered')
        modal.count = AsyncMock(return_value=1)
        modal.first.subs['button:has-text("声明原创")'].count = AsyncMock(return_value=0)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_set_original_declaration(page))
        assert any('未找到声明原创按钮' in str(c) for c in logger.info.call_args_list)

    def test_modal_missing_skips(self):
        page = _mk_page()
        switch = self._switch(page)
        switch.count = AsyncMock(return_value=1)
        switch.first.get_attribute = AsyncMock(return_value=None)
        logger = MagicMock()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.xiaohongshu.platform.logger', logger):
            _run(_set_original_declaration(page))
        assert any('未找到原创声明弹窗' in str(c) for c in logger.info.call_args_list)

    def test_outer_exception_swallowed(self):
        page = _mk_page()
        switch = self._switch(page)
        switch.count = AsyncMock(side_effect=RuntimeError('boom'))
        logger = MagicMock()
        with patch('impl.xiaohongshu.platform.logger', logger):
            _run(_set_original_declaration(page))  # 不抛异常
        assert any('原创声明设置失败' in str(c) for c in logger.info.call_args_list)


# ── 运营数据抓取 ──────────────────────────────────────────────────────────

class TestScrapeXhsStats:
    def test_happy_sorted(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'label': '获赞与收藏', 'num': '7'},
            {'label': '未知指标', 'num': '9'},
            {'label': '粉丝数', 'num': '1,234'},
            {'label': '关注数', 'num': '12'},
        ])
        stats = _run(_scrape_xhs_stats(page))
        assert [s['NAME'] for s in stats] == ['关注数', '粉丝数', '获赞与收藏']
        assert stats[1]['COUNT'] == 1234  # 逗号被去除
        assert stats[0]['ICON'] == 'follow'

    def test_wait_timeout_continues(self):
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        page.evaluate = AsyncMock(return_value=[])
        logger = MagicMock()
        with patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(_scrape_xhs_stats(page)) == []
        assert any('等待 .numerical 超时' in str(c) for c in logger.info.call_args_list)

    def test_evaluate_exception_returns_empty(self):
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('js boom'))
        logger = MagicMock()
        with patch('impl.xiaohongshu.platform.logger', logger):
            assert _run(_scrape_xhs_stats(page)) == []
        assert any('抓取失败' in str(c) for c in logger.info.call_args_list)

    def test_bad_count_falls_back_zero(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'label': '粉丝数', 'num': 'abc'},
            {'label': '关注数', 'num': ''},
        ])
        stats = _run(_scrape_xhs_stats(page))
        assert [s['COUNT'] for s in stats] == [0, 0]
