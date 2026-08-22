"""微信公众号 platform.py DOM 交互层契约测试（T35 批次第 13 期）。

覆盖 impl/weixin_gzh/platform.py（1014 stmts，基线 23%）—— 与
test_weixin_gzh_publish.py 已覆盖的纯函数/编排基线互补，目标合并 100%：

- 登录/校验/同步: login（QR 轮询成功/未找到 error JSON/探测异常继续/登录超时保留浏览器/
  URL 读取异常继续/save_login_result+stats_fn/goto 首页异常吞掉）
  / check_cookie（两个失效 marker/有效/其他 URL 失效）
  / sync_profile（抓昵称头像+stats/goto 异常吞掉/全空日志）
  / _scrape_stats（span 解析/float/int/空串/非法数字/未知标题跳过/result None/
  wait_for_selector 超时/url 读取异常/evaluate 异常空）
  / _login_stats_fn（正常/异常空） / open_creator_center（线程/wait_for_event 异常吞掉/
  browser.close 异常吞掉）
- 编排: _upload_one_video 全流程（token 失败 raise/带封面+原创+合集+来源+定时 valid/
  定时解析 0 改立即/truthy int 定时/最小流立即发表/storage_state 回写/close_browser）
  / _upload_one_image（token 失败/全流程定时/最小流立即发表）
  / _upload_all_images（单账号全图/多账号/无账号/desc 分支）
  / publish_image（dry_run 早返回/正常）
- DOM 辅助(阶段①): _upload_video_file / _wait_for_video_uploaded 补丁分支（success 探测
  异常/失败探测异常/进度日志去重）/ _set_cover / _fill_material_title（截断/None）
  / _set_original（弹窗确定/未找到 warning）/ _check_service_rule（未勾选/已勾选/超时跳过/
  is_checked 异常兜底）
  / _click_save_and_send（handler 捕获候选 tab/handler url 读取异常/pages 扫描+继续提交弹窗/
  弹窗处理导航异常→兜底扫描→raise/wait_for_url 超时非致命/disabled→force click）
- DOM 辅助(阶段②): _fill_publish_title（textarea/选择器回退/ProseMirror/click 异常/
  is_visible 异常）/ _fill_description（desc+tags/回落 title/空白 tag 过滤/截断/空跳过）
  / _set_collection（正常/下拉缺失早返回/未匹配 warning）/ _set_claim_source（直接命中/
  模糊匹配/未知跳过/入口回退/radio 未找到）
  / _click_dialog_primary（命中/超时 warning）/ _publish_immediate / _publish_scheduled
  （开关校验通过/失败仍继续）/ _select_schedule_date（正常/下拉缺失/未匹配）
  / _select_schedule_time（首轮已展开/展开失败放弃/鼠标点击异常补 Escape/Escape 异常吞掉）
  / _click_time_wheel_item（JS 选中/未找到/mouse 兜底/无中心坐标/mouse 异常）
  / _is_wheel_item_selected / _wait_for_home（成功/超时/url 异常后成功）
- 图集: _click_image_menu（handler 捕获/url 异常/pages 扫描/wait_for_url 超时/未捕获 raise）
  / _upload_images（空列表/首选择器/选择器回退/全失败 raise/上传中→已结束/超时 warning）
- 纯函数补测: _find_visible_picker_dl_js / _wheel_items_js_body / _parse_cookie_to_storage_state
  用模块级 time stub（禁止 patch 全局 time.time，见 _StubTime/_mk_stub_time 已修复版）

轮询类函数一律注入 fake 时间（_FakeLoop/_mk_time，patch 模块级 asyncio.get_event_loop）
并 patch asyncio.sleep，避免真等待/挂死。
"""
import asyncio
import json
import os
import sys
import tempfile
import time as _time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from conf import BASE_DIR
from impl.weixin_gzh.platform import _LOGIN_URL, _MATERIAL_UPLOAD_PATH, WeixinGzhPlatform

_HOME_URL = (
    "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=123456"
)
_EDIT_URL = (
    "https://mp.weixin.qq.com/cgi-bin/appmsg_edit_v2?action=edit&type=77&token=123456"
)


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return WeixinGzhPlatform()


def _mk_leaf():
    """叶子 locator：所有异步方法默认成功；locator(sel) 返回稳定可预配置对象。"""
    loc = MagicMock()
    loc.count = AsyncMock(return_value=0)
    loc.click = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.set_input_files = AsyncMock()
    loc.get_attribute = AsyncMock(return_value=None)
    loc.inner_text = AsyncMock(return_value='')
    loc.is_visible = AsyncMock(return_value=True)
    loc.is_checked = AsyncMock(return_value=False)
    loc.fill = AsyncMock()
    loc.press = AsyncMock()
    loc.press_sequentially = AsyncMock()
    loc.evaluate = AsyncMock(return_value='')
    loc.all_inner_texts = AsyncMock(return_value=[])
    subs = {}
    loc.locator = MagicMock(side_effect=lambda sel, **kw: subs.setdefault(sel, _mk_locator()))
    loc.subs = subs
    loc.nth = MagicMock(side_effect=lambda i: _mk_leaf())
    loc.filter = MagicMock(side_effect=lambda **kw: _mk_leaf())
    return loc


def _mk_locator():
    loc = _mk_leaf()
    loc.first = _mk_leaf()
    loc.last = _mk_leaf()
    return loc


class _RaiseUrl:
    """_SeqUrlPage 哨兵:读取 url 时抛异常。"""


class _SeqUrlPage(MagicMock):
    """按顺序返回 url 的 page;序列耗尽重复末值;哨兵值抛异常。"""

    def __init__(self, urls):
        super().__init__()
        self._url_seq = list(urls)

    @property
    def url(self):
        val = self._url_seq.pop(0) if len(self._url_seq) > 1 else self._url_seq[0]
        if val is _RaiseUrl:
            raise RuntimeError('url read boom')
        return val

    @url.setter
    def url(self, value):
        pass


def _mk_page(url=_LOGIN_URL, urls=None):
    """通用 fake page:locator 按 selector 分派,带默认 async 方法。"""
    if urls is not None:
        page = _SeqUrlPage(urls)
    else:
        page = MagicMock()
        page.url = url
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.mouse = MagicMock()
    page.mouse.click = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_event = AsyncMock()
    page.evaluate = AsyncMock(return_value=False)
    page.on = MagicMock()
    page.bring_to_front = AsyncMock()
    locators = {}
    page.locator = MagicMock(
        side_effect=lambda sel, **kw: locators.setdefault(sel, _mk_locator())
    )
    page.locators = locators
    return page


def _loc(page, sel):
    page.locator(sel)
    return page.locators[sel]


@contextmanager
def _mk_browser_chain(platform, urls=None):
    """create_browser/create_context 链 mocks（with 内生效）。"""
    page = _mk_page(urls=urls)
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.storage_state = AsyncMock()
    context.on = MagicMock()
    context.remove_listener = MagicMock()
    context.pages = []
    browser = MagicMock()
    browser.close = AsyncMock()
    with patch.object(platform, 'create_browser', AsyncMock(return_value=browser)) as cb, \
         patch.object(platform, 'create_context', AsyncMock(return_value=context)) as cc:
        yield page, context, browser, cb, cc


def _mk_cookie_file(name='t35_wxgzh_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


def _mk_edit_page(url=_EDIT_URL):
    """阶段②发布编辑页 page mock。"""
    page2 = MagicMock()
    page2.url = url
    page2.wait_for_url = AsyncMock()
    page2.wait_for_load_state = AsyncMock()
    page2.bring_to_front = AsyncMock()
    page2.keyboard = MagicMock()
    page2.mouse = MagicMock()
    return page2


class _FakeLoop:
    """时间序列控制:所有轮询都依赖 loop.time()。"""

    def __init__(self, times):
        self._times = list(times)

    def time(self):
        return self._times.pop(0) if len(self._times) > 1 else self._times[0]


@contextmanager
def _mk_time(*times):
    """注入 fake loop.time() 序列 + patch asyncio.sleep。"""
    loop = _FakeLoop(list(times))
    with patch('impl.weixin_gzh.platform.asyncio.get_event_loop', return_value=loop), \
         patch('asyncio.sleep', AsyncMock()):
        yield loop


class _StubTime:
    """模块级 time 替身:只影响 platform 模块内部 time.time(),序列耗尽重复末值。"""

    def __init__(self, values):
        self._values = list(values)
        self._last = values[-1]

    def time(self):
        if self._values:
            return self._values.pop(0)
        return self._last


def _mk_stub_time(*values):
    return _StubTime(list(values))


@contextmanager
def _mk_upload_one_video_steps(p):
    """把 _upload_one_video 内部子步骤替换为 AsyncMock。"""
    mocks = dict(
        resolve_token=AsyncMock(return_value='123'),
        upload_video_file=AsyncMock(),
        wait_uploaded=AsyncMock(),
        dismiss_notice=AsyncMock(),
        set_cover=AsyncMock(),
        fill_material_title=AsyncMock(),
        set_original=AsyncMock(),
        check_service_rule=AsyncMock(),
        click_save_send=AsyncMock(),
        fill_publish_title=AsyncMock(),
        fill_description=AsyncMock(),
        set_collection=AsyncMock(),
        set_claim_source=AsyncMock(),
        publish_immediate=AsyncMock(),
        publish_scheduled=AsyncMock(),
        build_publish_datetime=MagicMock(),
        close_browser=AsyncMock(),
    )
    with patch.object(p, '_resolve_token', mocks['resolve_token']), \
         patch.object(p, '_upload_video_file', mocks['upload_video_file']), \
         patch.object(p, '_wait_for_video_uploaded', mocks['wait_uploaded']), \
         patch.object(p, '_dismiss_upload_notice', mocks['dismiss_notice']), \
         patch.object(p, '_set_cover', mocks['set_cover']), \
         patch.object(p, '_fill_material_title', mocks['fill_material_title']), \
         patch.object(p, '_set_original', mocks['set_original']), \
         patch.object(p, '_check_service_rule', mocks['check_service_rule']), \
         patch.object(p, '_click_save_and_send', mocks['click_save_send']), \
         patch.object(p, '_fill_publish_title', mocks['fill_publish_title']), \
         patch.object(p, '_fill_description', mocks['fill_description']), \
         patch.object(p, '_set_collection', mocks['set_collection']), \
         patch.object(p, '_set_claim_source', mocks['set_claim_source']), \
         patch.object(p, '_publish_immediate', mocks['publish_immediate']), \
         patch.object(p, '_publish_scheduled', mocks['publish_scheduled']), \
         patch.object(p, '_build_publish_datetime', mocks['build_publish_datetime']), \
         patch.object(p, 'close_browser', mocks['close_browser']), \
         patch('asyncio.sleep', AsyncMock()):
        yield mocks


@contextmanager
def _mk_upload_one_image_steps(p):
    """把 _upload_one_image 内部子步骤替换为 AsyncMock。"""
    mocks = dict(
        resolve_token=AsyncMock(return_value='123'),
        click_image_menu=AsyncMock(),
        upload_images=AsyncMock(),
        fill_publish_title=AsyncMock(),
        fill_description=AsyncMock(),
        set_collection=AsyncMock(),
        set_claim_source=AsyncMock(),
        publish_immediate=AsyncMock(),
        publish_scheduled=AsyncMock(),
        build_publish_datetime=MagicMock(),
        close_browser=AsyncMock(),
    )
    with patch.object(p, '_resolve_token', mocks['resolve_token']), \
         patch.object(p, '_click_image_menu', mocks['click_image_menu']), \
         patch.object(p, '_upload_images', mocks['upload_images']), \
         patch.object(p, '_fill_publish_title', mocks['fill_publish_title']), \
         patch.object(p, '_fill_description', mocks['fill_description']), \
         patch.object(p, '_set_collection', mocks['set_collection']), \
         patch.object(p, '_set_claim_source', mocks['set_claim_source']), \
         patch.object(p, '_publish_immediate', mocks['publish_immediate']), \
         patch.object(p, '_publish_scheduled', mocks['publish_scheduled']), \
         patch.object(p, '_build_publish_datetime', mocks['build_publish_datetime']), \
         patch.object(p, 'close_browser', mocks['close_browser']), \
         patch('asyncio.sleep', AsyncMock()):
        yield mocks


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLogin:
    def test_success_with_qr_found(self):
        p = _mk_platform()
        queue = MagicMock()
        with _mk_browser_chain(p, urls=[_HOME_URL, _HOME_URL]) as (page, context, browser, _cb, _cc), \
             _mk_time(0.0, 1.0), \
             patch('impl.weixin_gzh.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.weixin_gzh.platform.logger'):
            # 第二个选择器命中但 src 为空 → src 重置继续;第三个命中 data: → break
            _loc(page, 'img[class*="qr_code"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'img[class*="QRCode"]').first.count = AsyncMock(return_value=1)
            _loc(page, 'img[class*="QRCode"]').first.get_attribute = AsyncMock(
                return_value='data:image/png;base64,xxx'
            )
            _run(p.login('u1', queue, account_id='acc1'))
        assert queue.put.call_args.args[0] == 'data:image/png;base64,xxx'
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 17
        assert kwargs['account_id'] == 'acc1'
        assert kwargs['stats_fn'].__func__ is WeixinGzhPlatform._login_stats_fn
        page.goto.assert_any_await(_LOGIN_URL, wait_until='domcontentloaded')
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()  # 成功才关浏览器

    def test_qr_not_found_puts_error_json(self):
        p = _mk_platform()
        queue = MagicMock()
        with _mk_browser_chain(p, urls=[_HOME_URL, _HOME_URL]) as (_page, _context, browser, _cb, _cc), \
             _mk_time(0.0, 1.0), \
             patch('impl.weixin_gzh.platform.save_login_result', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(p.login('u1', queue))
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['error']
        browser.close.assert_awaited_once()

    def test_qr_probe_exception_continues(self):
        p = _mk_platform()
        queue = MagicMock()
        with _mk_browser_chain(p, urls=[_HOME_URL, _HOME_URL]) as (page, _context, browser, _cb, _cc), \
             _mk_time(0.0, 1.0), \
             patch('impl.weixin_gzh.platform.save_login_result', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _loc(page, 'img[class*="qrcode"]').first.count = AsyncMock(
                side_effect=RuntimeError('stale dom')
            )
            _run(p.login('u1', queue))
        payload = json.loads(queue.put.call_args.args[0])
        assert payload['error']
        browser.close.assert_awaited_once()

    def test_login_timeout_returns(self):
        p = _mk_platform()
        queue = MagicMock()
        with _mk_browser_chain(p) as (_page, context, browser, _cb, _cc), \
             _mk_time(0.0, 300.0), \
             patch('impl.weixin_gzh.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.weixin_gzh.platform.logger'):
            _run(p.login('u1', queue))
        slr.assert_not_awaited()
        browser.close.assert_not_awaited()  # 失败保留浏览器看现场
        context.close.assert_awaited_once()

    def test_url_read_exception_then_success(self):
        p = _mk_platform()
        queue = MagicMock()
        with _mk_browser_chain(p, urls=[_RaiseUrl, _HOME_URL, _HOME_URL]) as (_page, _context, browser, _cb, _cc), \
             _mk_time(0.0, 1.0, 2.0), \
             patch('impl.weixin_gzh.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.weixin_gzh.platform.logger'):
            _run(p.login('u1', queue))
        slr.assert_awaited_once()
        browser.close.assert_awaited_once()

    def test_goto_home_error_swallowed(self):
        p = _mk_platform()
        queue = MagicMock()
        with _mk_browser_chain(p, urls=[_HOME_URL, _HOME_URL]) as (page, _context, browser, _cb, _cc), \
             _mk_time(0.0, 1.0), \
             patch('impl.weixin_gzh.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.weixin_gzh.platform.logger'):
            page.goto = AsyncMock(side_effect=[None, RuntimeError('nav timeout')])
            _run(p.login('u1', queue))
        slr.assert_awaited_once()  # 跳转首页异常吞掉,继续抓资料
        browser.close.assert_awaited_once()


class TestCheckCookie:
    def _run_check(self, url, cookie):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            page.url = url
            return _run(p.check_cookie(cookie.name))

    def test_invalid_marker_bizlogin(self):
        cookie = _mk_cookie_file('t35_wxgzh_bizlogin.json')
        try:
            assert self._run_check('https://mp.weixin.qq.com/cgi-bin/bizlogin?redirect=1', cookie) is False
        finally:
            cookie.unlink(missing_ok=True)

    def test_invalid_marker_loginpage(self):
        cookie = _mk_cookie_file('t35_wxgzh_loginpage.json')
        try:
            assert self._run_check('https://mp.weixin.qq.com/cgi-bin/loginpage', cookie) is False
        finally:
            cookie.unlink(missing_ok=True)

    def test_valid(self):
        cookie = _mk_cookie_file('t35_wxgzh_valid.json')
        try:
            assert self._run_check(_HOME_URL, cookie) is True
        finally:
            cookie.unlink(missing_ok=True)

    def test_other_url_invalid(self):
        cookie = _mk_cookie_file('t35_wxgzh_other.json')
        try:
            assert self._run_check('https://mp.weixin.qq.com/cgi-bin/other', cookie) is False
        finally:
            cookie.unlink(missing_ok=True)


class TestSyncProfile:
    def test_happy(self):
        cookie = _mk_cookie_file('t35_wxgzh_sync.json')
        try:
            p = _mk_platform()
            with _mk_browser_chain(p, urls=[_HOME_URL, _HOME_URL]) as (page, context, browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.weixin_gzh.platform.scrape_weixin_gzh_profile',
                       AsyncMock(return_value=('昵称', 'https://avatar/1.png'))) as scrape, \
                 patch.object(p, '_scrape_stats', AsyncMock(return_value=[1, 2])) as stats, \
                 patch('impl.weixin_gzh.platform.logger'):
                result = _run(p.sync_profile(cookie.name))
            assert result == {'name': '昵称', 'avatar': 'https://avatar/1.png', 'stats': [1, 2]}
            scrape.assert_awaited_once()
            stats.assert_awaited_once()
            page.goto.assert_any_await(_HOME_URL, wait_until='domcontentloaded', timeout=30000)
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_goto_home_error_swallowed(self):
        cookie = _mk_cookie_file('t35_wxgzh_sync2.json')
        try:
            p = _mk_platform()
            with _mk_browser_chain(p, urls=[_HOME_URL, _HOME_URL]) as (page, _context, browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.weixin_gzh.platform.scrape_weixin_gzh_profile',
                       AsyncMock(return_value=('昵称', None))), \
                 patch.object(p, '_scrape_stats', AsyncMock(return_value=[])), \
                 patch('impl.weixin_gzh.platform.logger'):
                    page.goto = AsyncMock(side_effect=[None, RuntimeError('boom')])
                    result = _run(p.sync_profile(cookie.name))
            assert result['avatar'] is None  # avatar 空 → 「无」分支
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_empty_result_logged(self):
        cookie = _mk_cookie_file('t35_wxgzh_sync3.json')
        try:
            p = _mk_platform()
            with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.weixin_gzh.platform.scrape_weixin_gzh_profile',
                       AsyncMock(return_value=(None, None))), \
                 patch.object(p, '_scrape_stats', AsyncMock(return_value=[])), \
                 patch('impl.weixin_gzh.platform.logger') as logger:
                result = _run(p.sync_profile(cookie.name))
            assert result == {'name': None, 'avatar': None, 'stats': []}
            assert any('sync_profile 抓取为空' in c.args[0] for c in logger.info.call_args_list)
        finally:
            cookie.unlink(missing_ok=True)


class TestScrapeStats:
    def _mk(self, evaluate, urls=None):
        page = _mk_page(urls=urls)
        if evaluate is not None:
            page.evaluate = AsyncMock(return_value=evaluate)
        return page

    def test_happy_parse(self):
        page = self._mk([
            {'title': '原创内容', 'num': '2'},
            {'title': '总用户数', 'num': '1,234.5'},
            {'title': '未知指标', 'num': '9'},
        ])
        with patch('impl.weixin_gzh.platform.logger'):
            stats = _run(_mk_platform()._scrape_stats(page))
        assert stats == [
            {'ICON': 'edit', 'COUNT': 2, 'NAME': '原创内容', 'SORT': 1},
            {'ICON': 'user', 'COUNT': 1234, 'NAME': '总用户数', 'SORT': 2},
        ]

    def test_num_variants(self):
        page = self._mk([
            {'title': '原创内容', 'num': ''},      # 空 → 0
            {'title': '总用户数', 'num': 'abc'},   # 非法 → 0
            {'title': '原创内容', 'num': '007'},   # int → 7
        ])
        with patch('impl.weixin_gzh.platform.logger'):
            stats = _run(_mk_platform()._scrape_stats(page))
        assert [s['COUNT'] for s in stats] == [0, 0, 7]

    def test_result_none(self):
        page = self._mk(None)
        with patch('impl.weixin_gzh.platform.logger'):
            assert _run(_mk_platform()._scrape_stats(page)) == []

    def test_wait_selector_timeout_warns(self):
        page = self._mk([{'title': '原创内容', 'num': '2'}])
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('t'))
        with patch('impl.weixin_gzh.platform.logger') as logger:
            stats = _run(_mk_platform()._scrape_stats(page))
        assert stats[0]['COUNT'] == 2
        assert any('超时' in c.args[0] for c in logger.warning.call_args_list)

    def test_url_read_exception_falls_back(self):
        page = self._mk([{'title': '原创内容', 'num': '2'}], urls=[_RaiseUrl])
        with patch('impl.weixin_gzh.platform.logger'):
            stats = _run(_mk_platform()._scrape_stats(page))
        assert stats[0]['COUNT'] == 2

    def test_evaluate_exception_returns_empty(self):
        page = self._mk(None)
        page.evaluate = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('impl.weixin_gzh.platform.logger'):
            assert _run(_mk_platform()._scrape_stats(page)) == []


class TestLoginStatsFn:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_stats', AsyncMock(return_value=[1, 2])) as ss, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            assert _run(p._login_stats_fn(page, 'acc1')) == [1, 2]
        ss.assert_awaited_once_with(page)

    def test_exception_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_stats', AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            assert _run(p._login_stats_fn(page, 'acc1')) == []


class TestOpenCreatorCenter:
    def _run_thread(self, p, cookie, wait_for_event=None, browser_close=None):
        browser = MagicMock()
        if browser_close is not None:
            browser.close = browser_close
        page = MagicMock()
        page.wait_for_event = wait_for_event or MagicMock()
        context = MagicMock()
        context.new_page = MagicMock(return_value=page)
        with patch('impl.weixin_gzh.platform.create_browser_sync', return_value=browser), \
             patch('impl.weixin_gzh.platform.create_context_sync', return_value=context), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(p.open_creator_center(cookie.name))
            for _ in range(200):
                if browser.close.called:
                    break
                _time.sleep(0.02)
        return browser, page

    def test_launch_and_close(self):
        cookie = _mk_cookie_file('t35_wxgzh_occ.json')
        try:
            p = _mk_platform()
            browser, page = self._run_thread(p, cookie)
            browser.close.assert_called_once()
            page.goto.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_wait_event_and_close_errors_swallowed(self):
        cookie = _mk_cookie_file('t35_wxgzh_occ2.json')
        try:
            p = _mk_platform()
            browser, _page = self._run_thread(
                p, cookie,
                wait_for_event=MagicMock(side_effect=RuntimeError('boom')),
                browser_close=MagicMock(side_effect=RuntimeError('boom')),
            )
            browser.close.assert_called_once()  # close 异常吞掉
        finally:
            cookie.unlink(missing_ok=True)


# ── 编排: _upload_one_video / _upload_one_image ───────────────────────────

class TestUploadOneVideo:
    def _run(self, p, page, context, browser, **kw):
        default = dict(
            title='标题', file_path='/m/v.mp4', tags=[], account_file='/c/c.json',
            cover_path=None, desc='', is_original=False, gzh_collection_name='',
            gzh_claim_source='', enable_timer=False, schedule_time_str='', files_count=1,
        )
        default.update(kw)
        return _run(p._upload_one_video(**default))

    def test_happy_full_flow(self):
        p = _mk_platform()
        page2 = _mk_edit_page()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_video_steps(p) as mocks, \
             patch('impl.weixin_gzh.platform.logger'):
            mocks['click_save_send'].return_value = page2
            mocks['build_publish_datetime'].return_value = datetime(
                2026, 8, 30, 10, 30, tzinfo=ZoneInfo('Asia/Shanghai'))
            self._run(p, page, context, browser, title='标题', cover_path='/cov/169.jpg',
                      desc='简介', is_original=True, gzh_collection_name='合集',
                      gzh_claim_source='内容由AI生成', enable_timer=True,
                      schedule_time_str='2026-08-30 10:30')
        mocks['resolve_token'].assert_awaited_once_with(page)
        page.goto.assert_any_await(
            _MATERIAL_UPLOAD_PATH.format(token='123'),
            wait_until='domcontentloaded', timeout=30000,
        )
        mocks['upload_video_file'].assert_awaited_once_with(page, '/m/v.mp4')
        mocks['wait_uploaded'].assert_awaited_once_with(page)
        mocks['dismiss_notice'].assert_awaited_once_with(page)
        mocks['set_cover'].assert_awaited_once_with(page, '/cov/169.jpg')
        mocks['fill_material_title'].assert_awaited_once_with(page, '标题')
        mocks['set_original'].assert_awaited_once_with(page)
        mocks['check_service_rule'].assert_awaited_once_with(page)
        mocks['click_save_send'].assert_awaited_once_with(page, context)
        mocks['fill_publish_title'].assert_awaited_once_with(page2, '标题')
        mocks['fill_description'].assert_awaited_once_with(page2, '简介', '标题', [])
        mocks['set_collection'].assert_awaited_once_with(page2, '合集')
        mocks['set_claim_source'].assert_awaited_once_with(page2, '内容由AI生成')
        mocks['publish_scheduled'].assert_awaited_once()
        mocks['publish_immediate'].assert_not_awaited()
        context.storage_state.assert_awaited_once_with(path='/c/c.json')
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_token_failure_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             _mk_upload_one_video_steps(p) as mocks, \
             patch('impl.weixin_gzh.platform.logger'), \
             pytest.raises(RuntimeError, match='token'):
            mocks['resolve_token'].return_value = ''
            self._run(p, _page, _context, _browser)

    def test_timer_invalid_falls_back_immediate(self):
        p = _mk_platform()
        page2 = _mk_edit_page()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_video_steps(p) as mocks, \
             patch('impl.weixin_gzh.platform.logger'):
            mocks['click_save_send'].return_value = page2
            mocks['build_publish_datetime'].return_value = 0
            self._run(p, page, context, browser, enable_timer=True, schedule_time_str='bad')
        mocks['publish_immediate'].assert_awaited_once_with(page2)
        mocks['publish_scheduled'].assert_not_awaited()

    def test_timer_truthy_int_schedules(self):
        """publish_dt 为 truthy int 时 `publish_dt == 0` 内层条件也要执行。"""
        p = _mk_platform()
        page2 = _mk_edit_page()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_video_steps(p) as mocks, \
             patch('impl.weixin_gzh.platform.logger'):
            mocks['click_save_send'].return_value = page2
            mocks['build_publish_datetime'].return_value = 5
            self._run(p, page, context, browser, enable_timer=True, schedule_time_str='x')
        mocks['publish_scheduled'].assert_awaited_once_with(page2, 5)

    def test_minimal_immediate(self):
        p = _mk_platform()
        page2 = _mk_edit_page()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_video_steps(p) as mocks, \
             patch('impl.weixin_gzh.platform.logger'):
            mocks['click_save_send'].return_value = page2
            self._run(p, page, context, browser)
        mocks['set_cover'].assert_not_awaited()
        mocks['set_original'].assert_not_awaited()
        mocks['set_collection'].assert_not_awaited()
        mocks['set_claim_source'].assert_not_awaited()
        mocks['publish_immediate'].assert_awaited_once_with(page2)
        mocks['publish_scheduled'].assert_not_awaited()


class TestUploadOneImage:
    def _run(self, p, page, context, browser, **kw):
        default = dict(
            title='标题', file_path_list=['/a.png', '/b.png'], tags=[], account_file='/c/c.json',
            desc='', is_original=False, gzh_collection_name='', gzh_claim_source='',
            enable_timer=False, schedule_time_str='',
        )
        default.update(kw)
        return _run(p._upload_one_image(**default))

    def test_happy_full_flow(self):
        p = _mk_platform()
        page2 = _mk_edit_page()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_image_steps(p) as mocks, \
             patch('impl.weixin_gzh.platform.logger'):
            mocks['click_image_menu'].return_value = page2
            mocks['build_publish_datetime'].return_value = datetime(
                2026, 8, 30, 10, 30, tzinfo=ZoneInfo('Asia/Shanghai'))
            self._run(p, page, context, browser, desc='简介', gzh_collection_name='合集',
                      gzh_claim_source='内容由AI生成', enable_timer=True,
                      schedule_time_str='2026-08-30 10:30')
        mocks['resolve_token'].assert_awaited_once_with(page)
        page.goto.assert_any_await(
            WeixinGzhPlatform._build_home_url('123'), wait_until='domcontentloaded', timeout=30000)
        mocks['click_image_menu'].assert_awaited_once_with(page, context)
        mocks['upload_images'].assert_awaited_once_with(page2, ['/a.png', '/b.png'])
        mocks['fill_publish_title'].assert_awaited_once_with(
            page2, '标题', max_len=WeixinGzhPlatform._IMAGE_TITLE_MAX)
        mocks['fill_description'].assert_awaited_once_with(
            page2, '简介', '标题', [], max_len=WeixinGzhPlatform._IMAGE_DESC_MAX)
        mocks['set_collection'].assert_awaited_once_with(page2, '合集')
        mocks['set_claim_source'].assert_awaited_once_with(page2, '内容由AI生成')
        mocks['publish_scheduled'].assert_awaited_once()
        mocks['publish_immediate'].assert_not_awaited()
        context.storage_state.assert_awaited_once_with(path='/c/c.json')
        context.close.assert_awaited_once()
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_token_failure_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             _mk_upload_one_image_steps(p) as mocks, \
             patch('impl.weixin_gzh.platform.logger'), \
             pytest.raises(RuntimeError, match='token'):
            mocks['resolve_token'].return_value = ''
            self._run(p, _page, _context, _browser)

    def test_minimal_immediate(self):
        p = _mk_platform()
        page2 = _mk_edit_page()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_image_steps(p) as mocks, \
             patch('impl.weixin_gzh.platform.logger'):
            mocks['click_image_menu'].return_value = page2
            self._run(p, page, context, browser)
        mocks['set_collection'].assert_not_awaited()
        mocks['set_claim_source'].assert_not_awaited()
        mocks['publish_immediate'].assert_awaited_once()
        mocks['publish_scheduled'].assert_not_awaited()

    def test_timer_invalid_falls_back_immediate(self):
        p = _mk_platform()
        page2 = _mk_edit_page()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_one_image_steps(p) as mocks, \
             patch('impl.weixin_gzh.platform.logger'):
            mocks['click_image_menu'].return_value = page2
            mocks['build_publish_datetime'].return_value = 0
            self._run(p, page, context, browser, enable_timer=True, schedule_time_str='bad')
        mocks['publish_immediate'].assert_awaited_once_with(page2)
        mocks['publish_scheduled'].assert_not_awaited()


class TestPublishImage:
    def test_dry_run(self):
        p = _mk_platform()
        with patch.object(p, '_upload_all_images', AsyncMock()) as uai, \
             patch('impl.weixin_gzh.platform.logger'):
            assert p.publish_image(dry_run=True, files=['/a.png']) is True
        uai.assert_not_awaited()

    def test_normal(self):
        p = _mk_platform()
        with patch.object(p, '_upload_all_images', AsyncMock()) as uai, \
             patch('impl.weixin_gzh.platform.logger'):
            assert p.publish_image(files=['/a.png'], account_file=['c.json']) is True
        uai.assert_awaited_once()
        assert uai.await_args.kwargs['files'] == ['/a.png']


class TestUploadAllImages:
    def _run(self, p, **kwargs):
        upload = AsyncMock()
        with patch.object(p, '_upload_one_image', upload), \
             patch('impl.weixin_gzh.platform.get_account_name_by_cookie_file', return_value='号'), \
             patch('impl.weixin_gzh.platform.bind_account_name', MagicMock()):
            _run(p._upload_all_images(**kwargs))
        return upload

    def test_single_account_all_files_with_desc(self):
        p = _mk_platform()
        upload = self._run(p, title='T', files=['/a.png', '/b.png'],
                           account_file=['c.json'], desc='简介')
        assert upload.call_count == 1
        assert upload.await_args.kwargs['file_path_list'] == ['/a.png', '/b.png']

    def test_multi_account(self):
        p = _mk_platform()
        upload = self._run(p, title='T', files=['/a.png'], account_file=['c1.json', 'c2.json'])
        assert upload.call_count == 2

    def test_no_accounts_no_calls(self):
        p = _mk_platform()
        upload = self._run(p, title='T', files=['/a.png'], account_file=[])
        upload.assert_not_called()


# ── 阶段① DOM 辅助 ────────────────────────────────────────────────────────

class TestUploadVideoFile:
    def test_upload(self):
        fd, path = tempfile.mkstemp(prefix='t35_wxgzh_video_', suffix='.mp4')
        os.write(fd, b'x' * 2048)
        os.close(fd)
        try:
            page = _mk_page()
            with patch('impl.weixin_gzh.platform.logger'):
                _run(WeixinGzhPlatform._upload_video_file(page, path))
            inp = _loc(page, "input[type='file'][name='vid']").first
            inp.wait_for.assert_awaited_once_with(state='attached', timeout=15000)
            inp.set_input_files.assert_awaited_once_with(path)
        finally:
            os.unlink(path)


class TestWaitForVideoUploadedExtra:
    def test_success_eval_exception_continues(self):
        """成功信号 evaluate 抛异常 → except 吞掉继续 → 下一轮成功。"""
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[RuntimeError('boom'), False, False, False, True])
        with _mk_time(0.0, 1.0, 2.0, 3.0), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._wait_for_video_uploaded(page, timeout_s=30))

    def test_fail_eval_exception_continues(self):
        """失败信号 evaluate 抛非 RuntimeError → except 吞掉继续。"""
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[False, ValueError('boom'), False, False, True])
        with _mk_time(0.0, 1.0, 2.0, 3.0), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._wait_for_video_uploaded(page, timeout_s=30))

    def test_progress_logged_and_deduped(self):
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[
            False, False,  # iter1
            False, False,  # iter2
            False, False,  # iter3
            True,          # iter4 成功
        ])
        _loc(page, '.weui-desktop-upload__file__extra-info__item').all_inner_texts = AsyncMock(
            side_effect=[['10%', '', '50%'], ['10%', '', '50%'], ['100%']]
        )
        with _mk_time(0.0, 1.0, 2.0, 3.0, 4.0), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._wait_for_video_uploaded(page, timeout_s=30))
        progress_logs = [c.args for c in logger.info.call_args_list
                         if c.args and c.args[0] == '[阶段①] 上传进度: %s']
        assert progress_logs == [
            ('[阶段①] 上传进度: %s', '10% | 50%'),
            ('[阶段①] 上传进度: %s', '100%'),
        ]


class TestSetCover:
    def test_happy(self):
        page = _mk_page()
        with patch.object(WeixinGzhPlatform, '_click_primary_when_enabled', AsyncMock()) as cpe, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._set_cover(page, '/cov/169.jpg'))
        empty = _loc(page, '.cover__options__item_empty').first
        empty.wait_for.assert_awaited_once_with(state='visible', timeout=15000)
        empty.click.assert_awaited_once()
        cover_input = _loc(page, "input[type='file'][accept*='image']").first
        cover_input.wait_for.assert_awaited_once_with(state='attached', timeout=15000)
        cover_input.set_input_files.assert_awaited_once_with('/cov/169.jpg')
        assert cpe.await_count == 2
        assert cpe.await_args_list[0].args[:2] == (page, '下一步')
        assert cpe.await_args_list[1].args[:2] == (page, '完成')


class TestFillMaterialTitle:
    def test_truncated_to_64(self):
        page = _mk_page()
        with patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._fill_material_title(page, '标' * 70))
        inp = _loc(page, "input[name='title']").first
        inp.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        inp.fill.assert_awaited_once_with('标' * 64)

    def test_none_title(self):
        page = _mk_page()
        with patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._fill_material_title(page, None))
        _loc(page, "input[name='title']").first.fill.assert_awaited_once_with('')


class TestSetOriginal:
    def _run_orig(self, evaluate):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=evaluate)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._set_original(page))
        return page

    def test_dialog_found(self):
        page = self._run_orig(True)
        switch = _loc(page, '.ori-reward-info_wrp .weui-desktop-switch').first
        switch.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        switch.click.assert_awaited_once()

    def test_dialog_missing_warns(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=False)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._set_original(page))
        assert any('未找到原创须知弹窗' in c.args[0] for c in logger.warning.call_args_list)


class TestCheckServiceRule:
    def test_unchecked_checks(self):
        page = _mk_page()
        cb = _loc(page, '.video-setting__footer-link input.weui-desktop-form__checkbox').first
        cb.is_checked = AsyncMock(return_value=False)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._check_service_rule(page))
        cb.evaluate.assert_awaited_once_with('el => { if (!el.checked) el.click(); }')

    def test_already_checked(self):
        page = _mk_page()
        cb = _loc(page, '.video-setting__footer-link input.weui-desktop-form__checkbox').first
        cb.is_checked = AsyncMock(return_value=True)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._check_service_rule(page))
        cb.evaluate.assert_not_awaited()

    def test_wait_timeout_skips(self):
        page = _mk_page()
        _loc(page, '.video-setting__footer-link input.weui-desktop-form__checkbox').first.wait_for = (
            AsyncMock(side_effect=TimeoutError('t'))
        )
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._check_service_rule(page))
        assert any('未找到服务规则 checkbox' in c.args[0] for c in logger.warning.call_args_list)

    def test_is_checked_raises_falls_back_check(self):
        page = _mk_page()
        cb = _loc(page, '.video-setting__footer-link input.weui-desktop-form__checkbox').first
        cb.is_checked = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._check_service_rule(page))
        cb.evaluate.assert_awaited_once()


class TestClickSaveAndSend:
    def _mk_page2(self):
        return _mk_edit_page()

    def test_new_page_handler_captures_target(self):
        page = _mk_page()
        page2 = self._mk_page2()
        context = MagicMock()
        context.on = MagicMock(side_effect=lambda event, fn: fn(page2))
        context.remove_listener = MagicMock()
        context.pages = [page]
        with _mk_time(0.0, 1.0), patch('impl.weixin_gzh.platform.logger'):
            result = _run(WeixinGzhPlatform._click_save_and_send(page, context))
        assert result is page2
        _loc(page, '.video-save-send-btn button').first.click.assert_awaited_once()
        page2.bring_to_front.assert_awaited_once()
        context.remove_listener.assert_called_once()

    def test_new_page_handler_url_error_swallowed(self):
        page = _mk_page()
        page2 = self._mk_page2()

        class _BadUrl:
            @property
            def url(self):
                raise RuntimeError('boom')

        context = MagicMock()
        context.on = MagicMock(side_effect=lambda event, fn: fn(_BadUrl()) or fn(page2))
        context.remove_listener = MagicMock()
        context.pages = [page]
        with _mk_time(0.0, 1.0), patch('impl.weixin_gzh.platform.logger'):
            result = _run(WeixinGzhPlatform._click_save_and_send(page, context))
        assert result is page2

    def test_pages_scan_and_continue_submit_dialog(self):
        page = _mk_page()
        page2 = self._mk_page2()
        pages = [page]
        context = MagicMock()
        context.pages = pages
        context.on = MagicMock()
        context.remove_listener = MagicMock()

        def _ev(js, *args):
            if args and args[0] == '继续提交':
                pages.append(page2)  # 模拟弹窗点击后新 tab 导航完成
                return True
            return False

        page.evaluate = AsyncMock(side_effect=_ev)
        with _mk_time(0.0, 1.0), patch('impl.weixin_gzh.platform.logger'):
            result = _run(WeixinGzhPlatform._click_save_and_send(page, context))
        assert result is page2

    def test_dialog_navigation_error_then_raise(self):
        page = _mk_page()
        context = MagicMock()
        context.pages = [page]
        context.on = MagicMock()
        context.remove_listener = MagicMock()

        def _ev(js, *args):
            if args and args[0] == '继续提交':
                raise RuntimeError('Execution context was destroyed')
            return False

        page.evaluate = AsyncMock(side_effect=_ev)
        with _mk_time(0.0, 1.0), \
             patch('impl.weixin_gzh.platform.logger') as logger, \
             pytest.raises(RuntimeError, match='未捕获到发布编辑页'):
            _run(WeixinGzhPlatform._click_save_and_send(page, context))
        assert any('预期行为' in c.args[0] for c in logger.info.call_args_list)

    def test_dialog_handled_then_exhausts_and_raises(self):
        """继续提交弹窗点过一次 → 后续轮询跳过已处理按钮(for-else sleep) →
        时间耗尽走 30 次兜底扫描(含 url 读取异常页) → raise。"""
        page = _mk_page()
        plain = _mk_edit_page(url='https://mp.weixin.qq.com/cgi-bin/home?t=home/index&token=1')

        class _BadUrl:
            @property
            def url(self):
                raise RuntimeError('boom')

        context = MagicMock()
        context.pages = [page, plain, _BadUrl()]
        context.on = MagicMock()
        context.remove_listener = MagicMock()

        def _ev(js, *args):
            return bool(args and args[0] == '继续提交')

        page.evaluate = AsyncMock(side_effect=_ev)
        with _mk_time(0.0, 1.0, 1.0, 1.0, 1.0, 121.0), \
             patch('impl.weixin_gzh.platform.logger') as logger, \
             pytest.raises(RuntimeError, match='未捕获到发布编辑页'):
            _run(WeixinGzhPlatform._click_save_and_send(page, context))
        assert any('已点击中间确认弹窗' in c.args[0] for c in logger.info.call_args_list)

    def test_fallback_scan_finds_target(self):
        """wait 循环因 deadline 退出 → 兜底扫描从 context.pages 捕获目标 tab。"""
        page = _mk_page()
        page2 = self._mk_page2()
        pages = [page]
        context = MagicMock()
        context.pages = pages
        context.on = MagicMock()
        context.remove_listener = MagicMock()

        def _ev(js, *args):
            hit = bool(args and args[0] == '继续提交')
            if hit:
                pages.append(page2)  # 弹窗点击后才出现目标 tab
            return hit

        page.evaluate = AsyncMock(side_effect=_ev)
        with _mk_time(0.0, 1.0, 1.0, 1.0, 121.0), \
             patch('impl.weixin_gzh.platform.logger'):
            result = _run(WeixinGzhPlatform._click_save_and_send(page, context))
        assert result is page2

    def test_wait_for_url_timeout_logged(self):
        page = _mk_page()
        page2 = self._mk_page2()
        page2.wait_for_url = AsyncMock(side_effect=TimeoutError('nav'))
        context = MagicMock()
        context.on = MagicMock(side_effect=lambda event, fn: fn(page2))
        context.remove_listener = MagicMock()
        context.pages = [page]
        with _mk_time(0.0, 1.0), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            result = _run(WeixinGzhPlatform._click_save_and_send(page, context))
        assert result is page2
        assert any('新 tab URL 等待' in c.args[0] for c in logger.info.call_args_list)

    def test_force_click_when_disabled(self):
        page = _mk_page()
        page2 = self._mk_page2()
        _loc(page, '.video-save-send-btn button').first.evaluate = AsyncMock(return_value=True)
        context = MagicMock()
        context.on = MagicMock(side_effect=lambda event, fn: fn(page2))
        context.remove_listener = MagicMock()
        context.pages = [page]
        with _mk_time(0.0, 0.0, 60.0), patch('impl.weixin_gzh.platform.logger'):
            result = _run(WeixinGzhPlatform._click_save_and_send(page, context))
        assert result is page2
        _loc(page, '.video-save-send-btn button').first.click.assert_awaited_once_with(force=True)


# ── 阶段② DOM 辅助 ────────────────────────────────────────────────────────

class TestFillPublishTitle:
    def test_textarea_fill(self):
        page = _mk_page()
        _loc(page, '#title.js_title').first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._fill_publish_title(page, '标题'))
        _loc(page, '#title.js_title').first.fill.assert_awaited_once_with('标题')

    def test_fallback_selector(self):
        page = _mk_page()
        with patch('asyncio.sleep', AsyncMock()), patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._fill_publish_title(page, 'T'))
        _loc(page, 'textarea.js_title').first.fill.assert_awaited_once_with('T')

    def test_prosemirror_when_hidden(self):
        page = _mk_page()
        _loc(page, '#title.js_title').first.count = AsyncMock(return_value=1)
        _loc(page, '#title.js_title').first.is_visible = AsyncMock(return_value=False)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._fill_publish_title(page, '标题'))
        pm = _loc(page, '.title-editor-overlay .ProseMirror').first
        pm.wait_for.assert_awaited_once_with(state='visible', timeout=10000)
        pm.press_sequentially.assert_awaited_once_with('标题', delay=30)

    def test_prosemirror_click_error_swallowed(self):
        page = _mk_page()
        _loc(page, '#title.js_title').first.count = AsyncMock(return_value=1)
        _loc(page, '#title.js_title').first.is_visible = AsyncMock(return_value=False)
        _loc(page, '.title-editor-overlay .ProseMirror').first.click = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        with patch('asyncio.sleep', AsyncMock()), patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._fill_publish_title(page, '标题'))
        _loc(page, '.title-editor-overlay .ProseMirror').first.press_sequentially.assert_awaited_once()

    def test_is_visible_raises_uses_prosemirror(self):
        page = _mk_page()
        _loc(page, '#title.js_title').first.count = AsyncMock(return_value=1)
        _loc(page, '#title.js_title').first.is_visible = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._fill_publish_title(page, 'T'))
        _loc(page, '.title-editor-overlay .ProseMirror').first.press_sequentially.assert_awaited_once_with('T', delay=30)


class TestFillDescription:
    def _run_fd(self, page, desc='', title='', tags=None, max_len=300):
        with patch('impl.weixin_gzh.platform.clear_input', AsyncMock()) as ci, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._fill_description(page, desc, title, tags or [], max_len))
        return ci

    def test_desc_and_tags(self):
        page = _mk_page()
        ci = self._run_fd(page, desc='简介', title='标题', tags=['a', ' b '])
        editor = _loc(page, '#guide_words_main .ProseMirror').first
        editor.wait_for.assert_awaited_once_with(state='visible', timeout=15000)
        editor.press_sequentially.assert_awaited_once_with('简介 #a #b', delay=30)
        ci.assert_awaited_once()

    def test_desc_empty_falls_back_title(self):
        page = _mk_page()
        ci = self._run_fd(page, desc='', title='标题', tags=[])
        _loc(page, '#guide_words_main .ProseMirror').first.press_sequentially.assert_awaited_once_with(
            '标题', delay=30)
        ci.assert_awaited_once()

    def test_tags_whitespace_filtered(self):
        page = _mk_page()
        self._run_fd(page, desc='d', title='t', tags=['', ' ', 'x'])
        _loc(page, '#guide_words_main .ProseMirror').first.press_sequentially.assert_awaited_once_with(
            'd #x', delay=30)

    def test_truncation(self):
        page = _mk_page()
        self._run_fd(page, desc='一二三四五', title='t', tags=[], max_len=3)
        _loc(page, '#guide_words_main .ProseMirror').first.press_sequentially.assert_awaited_once_with(
            '一二三', delay=30)

    def test_empty_skips(self):
        page = _mk_page()
        ci = self._run_fd(page, desc='  ', title='')
        editor = _loc(page, '#guide_words_main .ProseMirror').first
        editor.press_sequentially.assert_not_awaited()
        ci.assert_not_awaited()


class TestSetCollection:
    def test_happy(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        with patch.object(WeixinGzhPlatform, '_click_dialog_primary', AsyncMock()) as cdp, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._set_collection(page, 'AI 合集'))
        _loc(page, '#js_article_tags_area .js_article_tags_label').first.click.assert_awaited_once()
        _loc(page, "input[placeholder='请选择合集']").first.click.assert_awaited_once()
        cdp.assert_awaited_once_with(page, '确认')

    def test_select_input_missing_returns(self):
        page = _mk_page()
        _loc(page, "input[placeholder='请选择合集']").first.wait_for = AsyncMock(
            side_effect=TimeoutError('t'))
        with patch.object(WeixinGzhPlatform, '_click_dialog_primary', AsyncMock()) as cdp, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._set_collection(page, '合集'))
        cdp.assert_not_awaited()

    def test_no_match_warns(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=False)
        with patch.object(WeixinGzhPlatform, '_click_dialog_primary', AsyncMock()) as cdp, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._set_collection(page, '不存在'))
        assert any('未找到合集' in c.args[0] for c in logger.warning.call_args_list)
        cdp.assert_awaited_once_with(page, '确认')


class TestSetClaimSource:
    def test_direct_map(self):
        page = _mk_page()
        _loc(page, '#js_claim_source_area .js_claim_source_desc').first.count = AsyncMock(return_value=1)
        page.evaluate = AsyncMock(return_value=True)
        with patch.object(WeixinGzhPlatform, '_click_dialog_primary', AsyncMock()) as cdp, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._set_claim_source(page, '内容由AI生成'))
        _loc(page, '#js_claim_source_area .js_claim_source_desc').first.click.assert_awaited_once()
        cdp.assert_awaited_once_with(page, '确认', timeout_s=15)

    def test_fuzzy_match(self):
        page = _mk_page()
        _loc(page, '#js_claim_source_area .js_claim_source_desc').first.count = AsyncMock(return_value=1)
        page.evaluate = AsyncMock(return_value=True)
        with patch.object(WeixinGzhPlatform, '_click_dialog_primary', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._set_claim_source(page, '仅供参考'))
        page.evaluate.assert_awaited_once()  # 模糊匹配命中 value=4,继续弹窗流程

    def test_unknown_skips(self):
        page = _mk_page()
        with patch.object(WeixinGzhPlatform, '_click_dialog_primary', AsyncMock()) as cdp, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._set_claim_source(page, '不存在的声明'))
        cdp.assert_not_awaited()
        assert any('未知创作来源' in c.args[0] for c in logger.warning.call_args_list)

    def test_entry_fallback(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        with patch.object(WeixinGzhPlatform, '_click_dialog_primary', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._set_claim_source(page, '无需声明'))
        _loc(page, '#js_claim_source_area').first.click.assert_awaited_once()

    def test_radio_not_found(self):
        page = _mk_page()
        _loc(page, '#js_claim_source_area .js_claim_source_desc').first.count = AsyncMock(return_value=1)
        page.evaluate = AsyncMock(return_value=False)
        with patch.object(WeixinGzhPlatform, '_click_dialog_primary', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._set_claim_source(page, '内容由AI生成'))
        assert any('未找到创作来源' in c.args[0] for c in logger.warning.call_args_list)


class TestClickDialogPrimary:
    def test_clicked(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._click_dialog_primary(page, '确认'))

    def test_timeout_warns(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=False)
        with _mk_time(0.0, 0.0, 30.1), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._click_dialog_primary(page, '确认', timeout_s=30))
        assert any('未可点' in c.args[0] for c in logger.warning.call_args_list)


class TestPublishImmediate:
    def test_flow(self):
        page = _mk_page()
        with patch.object(WeixinGzhPlatform, '_click_dialog_primary', AsyncMock()) as cdp, \
             patch.object(WeixinGzhPlatform, '_wait_for_home', AsyncMock()) as wfh, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._publish_immediate(page))
        _loc(page, '#js_send .mass_send').first.click.assert_awaited_once()
        assert cdp.await_count == 2
        assert cdp.await_args_list[0].args[:2] == (page, '发表')
        assert cdp.await_args_list[1].args[:2] == (page, '继续发表')
        wfh.assert_awaited_once_with(page, timeout_s=600)


class TestPublishScheduled:
    DT = datetime(2026, 8, 30, 10, 30, tzinfo=ZoneInfo('Asia/Shanghai'))

    def _ev(self, switch_ok):
        def _h(js, *args):
            if 'clicked: false' in js:
                return {'clicked': True, 'checked': False, 'reason': 'clicked', 'count': 1}
            if 'dlExists' in js:
                return {'on': switch_ok, 'dlExists': True, 'dlVisible': switch_ok}
            return False

        return _h

    def _run_sched(self, page, switch_ok, times):
        with patch.object(WeixinGzhPlatform, '_resolve_date_label', MagicMock(return_value='今天')) as rdl, \
             patch.object(WeixinGzhPlatform, '_select_schedule_date', AsyncMock()) as ssd, \
             patch.object(WeixinGzhPlatform, '_select_schedule_time', AsyncMock()) as sst, \
             patch.object(WeixinGzhPlatform, '_click_dialog_primary', AsyncMock()) as cdp, \
             patch.object(WeixinGzhPlatform, '_wait_for_home', AsyncMock()) as wfh, \
             _mk_time(*times), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._publish_scheduled(page, self.DT))
        return rdl, ssd, sst, cdp, wfh

    def test_switch_success(self):
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=self._ev(True))
        rdl, ssd, sst, cdp, wfh = self._run_sched(page, True, (0.0, 1.0))
        _loc(page, '#js_send .mass_send').first.click.assert_awaited_once()
        rdl.assert_called_once_with(self.DT)
        ssd.assert_awaited_once_with(page, '今天')
        sst.assert_awaited_once_with(page, '10', '30')
        assert cdp.await_count == 2
        wfh.assert_awaited_once_with(page, timeout_s=600)

    def test_switch_fail_still_continues(self):
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=self._ev(False))
        with patch.object(WeixinGzhPlatform, '_resolve_date_label', MagicMock(return_value='今天')) as rdl, \
             patch.object(WeixinGzhPlatform, '_select_schedule_date', AsyncMock()) as ssd, \
             patch.object(WeixinGzhPlatform, '_select_schedule_time', AsyncMock()) as sst, \
             patch.object(WeixinGzhPlatform, '_click_dialog_primary', AsyncMock()), \
             patch.object(WeixinGzhPlatform, '_wait_for_home', AsyncMock()), \
             _mk_time(0.0, 1.0, 21.0), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._publish_scheduled(page, self.DT))
        assert any('定时开关校验失败' in c.args[0] for c in logger.error.call_args_list)
        rdl.assert_called_once_with(self.DT)
        ssd.assert_awaited_once_with(page, '今天')
        sst.assert_awaited_once_with(page, '10', '30')


class TestSelectScheduleDate:
    def test_happy(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._select_schedule_date(page, '今天'))
        _loc(page, '.mass-send__timer .weui-desktop-form__dropdown').first.click.assert_awaited_once()

    def test_dropdown_missing_returns(self):
        page = _mk_page()
        _loc(page, '.mass-send__timer .weui-desktop-form__dropdown').first.wait_for = AsyncMock(
            side_effect=TimeoutError('t'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._select_schedule_date(page, '今天'))
        assert any('未找到日期下拉' in c.args[0] for c in logger.warning.call_args_list)

    def test_no_match_warns(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=False)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._select_schedule_date(page, 'x'))
        assert any('未找到定时日期选项' in c.args[0] for c in logger.warning.call_args_list)


class TestFindVisiblePickerDlJs:
    def test_returns_js(self):
        js = WeixinGzhPlatform._find_visible_picker_dl_js()
        assert 'weui-desktop-picker__time' in js
        assert 'getComputedStyle' in js


class TestWheelItemsJsBody:
    def test_hour(self):
        body = WeixinGzhPlatform._wheel_items_js_body('hour')
        assert 'weui-desktop-picker__time__hour li' in body

    def test_minute(self):
        body = WeixinGzhPlatform._wheel_items_js_body('minute')
        assert 'weui-desktop-picker__time__minute li' in body


class TestSelectScheduleTime:
    def _mk_time_page(self, *, focus=True, click_ok=True, final_value=None):
        page = _mk_page()

        def _ev(js, *args):
            if 'dl_visible_count' in js:
                return {'dl_total': 2, 'dl_visible_count': 1, 'dls': [], 'input_total': 2,
                        'input_visible_count': 1, 'inputs': []}
            if 'classList.contains' in js and 'picker__focus' in js:
                return focus
            if 'innerSel' in js:
                return {'ok': click_ok, 'reason': 'none', 'box': {'x': 1, 'y': 2, 'w': 3, 'h': 4}}
            if 'outerHTML' in js:
                return [{'i': 0, 'focus': False, 'display': 'none', 'style': '', 'head': '<dl/>'}]
            if 'inp.value' in js:
                return final_value if final_value is not None else {'value': '10:30', 'reason': None}
            return False

        page.evaluate = AsyncMock(side_effect=_ev)
        return page

    def _run_time(self, page, times):
        with patch.object(WeixinGzhPlatform, '_click_time_wheel_item',
                          AsyncMock(return_value=True)) as ctw, \
             _mk_time(*times), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._select_schedule_time(page, '9', '5'))
        return ctw

    def test_opened_first_then_close(self):
        page = self._mk_time_page(focus=True)
        ctw = self._run_time(page, (0.0, 1.0))
        assert ctw.await_count == 2
        assert ctw.await_args_list[0].args == (page, 'hour', '09')
        assert ctw.await_args_list[1].args == (page, 'minute', '05')
        page.mouse.click.assert_awaited_once_with(10, 10)
        page.keyboard.press.assert_awaited_once_with('Escape')  # 点外部未关闭 → Escape

    def test_open_exhausted_aborts(self):
        page = self._mk_time_page(focus=False, click_ok=False)
        with patch.object(WeixinGzhPlatform, '_click_time_wheel_item', AsyncMock()) as ctw, \
             _mk_time(0.0, 0.0, 10.1), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._select_schedule_time(page, '9', '5'))
        ctw.assert_not_awaited()
        assert any('时分选择面板未展开' in c.args[0] for c in logger.warning.call_args_list)

    def test_mouse_click_error_escape(self):
        page = self._mk_time_page(focus=True)
        page.mouse.click = AsyncMock(side_effect=RuntimeError('boom'))
        with patch.object(WeixinGzhPlatform, '_click_time_wheel_item',
                          AsyncMock(return_value=True)), \
             _mk_time(0.0, 1.0), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._select_schedule_time(page, '9', '5'))
        page.keyboard.press.assert_awaited_once_with('Escape')

    def test_opened_after_click_attempt(self):
        page = _mk_page()
        state = {'focus_calls': 0}

        def _ev(js, *args):
            if 'dl_visible_count' in js:
                return {'dl_total': 2, 'dl_visible_count': 1, 'dls': [], 'input_total': 2,
                        'input_visible_count': 1, 'inputs': []}
            if 'classList.contains' in js and 'picker__focus' in js:
                state['focus_calls'] += 1
                return state['focus_calls'] >= 2  # before=False → after=True
            if 'innerSel' in js:
                return {'ok': True, 'reason': 'none', 'box': {'x': 1, 'y': 2, 'w': 3, 'h': 4}}
            if 'outerHTML' in js:
                return [{'i': 0, 'focus': False, 'display': 'none', 'style': '', 'head': '<dl/>'}]
            if 'inp.value' in js:
                return {'value': '10:30', 'reason': None}
            return False

        page.evaluate = AsyncMock(side_effect=_ev)
        with patch.object(WeixinGzhPlatform, '_click_time_wheel_item',
                          AsyncMock(return_value=True)) as ctw, \
             _mk_time(0.0, 1.0), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._select_schedule_time(page, '9', '5'))
        assert ctw.await_count == 2  # 点击候选后面板展开,继续选时分

    def test_escape_error_swallowed(self):
        page = self._mk_time_page(focus=True)
        page.mouse.click = AsyncMock(side_effect=RuntimeError('boom'))
        page.keyboard.press = AsyncMock(side_effect=RuntimeError('boom2'))
        with patch.object(WeixinGzhPlatform, '_click_time_wheel_item',
                          AsyncMock(return_value=True)), \
             _mk_time(0.0, 1.0), \
             patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._select_schedule_time(page, '9', '5'))  # 不抛异常


class TestClickTimeWheelItem:
    def _mk_info_page(self, found=True, center=None):
        page = _mk_page()

        def _ev(js, *args):
            if 'found_disabled' in js:
                return {'total': 24, 'disabled': 1, 'found': found, 'found_disabled': False}
            if 'li.click()' in js:
                return None
            if 'getBoundingClientRect' in js:
                return center
            return False

        page.evaluate = AsyncMock(side_effect=_ev)
        return page

    def test_found_and_js_selected(self):
        page = self._mk_info_page(center={'x': 100.0, 'y': 200.0})
        with patch.object(WeixinGzhPlatform, '_is_wheel_item_selected',
                          AsyncMock(return_value=True)) as iws, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            assert _run(WeixinGzhPlatform._click_time_wheel_item(page, 'hour', '10')) is True
        iws.assert_awaited_once()
        page.mouse.click.assert_not_awaited()

    def test_not_found_returns_false(self):
        page = self._mk_info_page(found=False)
        with patch.object(WeixinGzhPlatform, '_is_wheel_item_selected', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            assert _run(WeixinGzhPlatform._click_time_wheel_item(page, 'hour', '10')) is False

    def test_mouse_fallback(self):
        page = self._mk_info_page(center={'x': 100.0, 'y': 200.0})
        with patch.object(WeixinGzhPlatform, '_is_wheel_item_selected',
                          AsyncMock(side_effect=[False, True])), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger'):
            assert _run(WeixinGzhPlatform._click_time_wheel_item(page, 'hour', '10')) is True
        page.mouse.click.assert_awaited_once_with(100.0, 200.0)

    def test_center_none_warns(self):
        page = self._mk_info_page(center=None)
        with patch.object(WeixinGzhPlatform, '_is_wheel_item_selected',
                          AsyncMock(side_effect=[False, False])), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            assert _run(WeixinGzhPlatform._click_time_wheel_item(page, 'hour', '10')) is False
        assert any('无法取到 li 中心坐标' in c.args[0] for c in logger.warning.call_args_list)

    def test_mouse_click_error_warns(self):
        page = self._mk_info_page(center={'x': 100.0, 'y': 200.0})
        page.mouse.click = AsyncMock(side_effect=RuntimeError('boom'))
        with patch.object(WeixinGzhPlatform, '_is_wheel_item_selected',
                          AsyncMock(side_effect=[False, False])), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            assert _run(WeixinGzhPlatform._click_time_wheel_item(page, 'hour', '10')) is False
        assert any('鼠标点击异常' in c.args[0] for c in logger.warning.call_args_list)


class TestIsWheelItemSelected:
    def test_true(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        with patch('impl.weixin_gzh.platform.logger'):
            assert _run(WeixinGzhPlatform._is_wheel_item_selected(page, 'hour', '10')) is True

    def test_false(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=False)
        with patch('impl.weixin_gzh.platform.logger'):
            assert _run(WeixinGzhPlatform._is_wheel_item_selected(page, 'minute', '05')) is False


class TestWaitForHome:
    def test_success(self):
        page = _mk_page(url=_HOME_URL)
        with _mk_time(0.0, 1.0), patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._wait_for_home(page, timeout_s=30))

    def test_timeout_warns(self):
        page = _mk_page(url=_LOGIN_URL)
        with _mk_time(0.0, 30.1), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._wait_for_home(page, timeout_s=30))
        assert any('未跳转首页' in c.args[0] for c in logger.warning.call_args_list)

    def test_url_read_exception_then_success(self):
        page = _mk_page(urls=[_RaiseUrl, _HOME_URL])
        with _mk_time(0.0, 1.0, 2.0), patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._wait_for_home(page, timeout_s=30))


# ── 图集: 菜单 / 上传 ─────────────────────────────────────────────────────

class TestClickImageMenu:
    def _mk_page2(self):
        return _mk_edit_page()

    def test_handler_captures_target(self):
        page = _mk_page()
        page2 = self._mk_page2()
        context = MagicMock()
        context.on = MagicMock(side_effect=lambda event, fn: fn(page2))
        context.remove_listener = MagicMock()
        context.pages = [page]
        with _mk_time(0.0, 1.0), patch('impl.weixin_gzh.platform.logger'):
            result = _run(_mk_platform()._click_image_menu(page, context))
        assert result is page2
        menu_title = _loc(page, '.new-creation__menu-title')
        menu_title.first.wait_for.assert_awaited_once_with(state='visible', timeout=15000)
        menu = menu_title.first.locator(
            "xpath=ancestor::div[contains(@class,'new-creation__menu-item')][1]")
        menu.wait_for.assert_awaited_once_with(state='visible', timeout=15000)
        menu.click.assert_awaited_once()
        page2.bring_to_front.assert_awaited_once()
        context.remove_listener.assert_called_once()

    def test_handler_url_error_swallowed(self):
        page = _mk_page()
        page2 = self._mk_page2()

        class _BadUrl:
            @property
            def url(self):
                raise RuntimeError('boom')

        context = MagicMock()
        context.on = MagicMock(side_effect=lambda event, fn: fn(_BadUrl()) or fn(page2))
        context.remove_listener = MagicMock()
        context.pages = [page]
        with _mk_time(0.0, 1.0), patch('impl.weixin_gzh.platform.logger'):
            result = _run(_mk_platform()._click_image_menu(page, context))
        assert result is page2

    def test_pages_scan_and_wait_for_url_timeout(self):
        page = _mk_page()
        page2 = self._mk_page2()
        page2.wait_for_url = AsyncMock(side_effect=TimeoutError('nav'))
        class _BadUrl:
            @property
            def url(self):
                raise RuntimeError('boom')

        context = MagicMock()
        context.pages = [page, _BadUrl(), page2]
        context.on = MagicMock()
        context.remove_listener = MagicMock()
        with _mk_time(0.0, 1.0), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            result = _run(_mk_platform()._click_image_menu(page, context))
        assert result is page2
        assert any('新 tab URL 等待' in c.args[0] for c in logger.info.call_args_list)

    def test_raise_when_no_target(self):
        page = _mk_page()
        context = MagicMock()
        context.pages = [page]
        context.on = MagicMock()
        context.remove_listener = MagicMock()
        with _mk_time(0.0, 0.0, 30.1), \
             patch('impl.weixin_gzh.platform.logger'), \
             pytest.raises(RuntimeError, match='未捕获到编辑页'):
            _run(_mk_platform()._click_image_menu(page, context))


class TestUploadImages:
    def test_empty_list_warns(self):
        page = _mk_page()
        with patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._upload_images(page, []))
        assert any('无图片可上传' in c.args[0] for c in logger.warning.call_args_list)

    def test_first_selector_and_complete(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value={'best': 2, 'uploading': 0, 'target': 2})
        with _mk_time(0.0, 1.0), patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._upload_images(page, ['/a.png', '/b.png']))
        img = _loc(page, ".js_upload_btn_container input[type='file']").first
        img.wait_for.assert_awaited_once_with(state='attached', timeout=8000)
        img.set_input_files.assert_awaited_once_with(['/a.png', '/b.png'])

    def test_selector_fallback(self):
        page = _mk_page()
        _loc(page, ".js_upload_btn_container input[type='file']").first.wait_for = AsyncMock(
            side_effect=TimeoutError('t'))
        page.evaluate = AsyncMock(return_value={'best': 1, 'uploading': 0, 'target': 1})
        with _mk_time(0.0, 1.0), patch('impl.weixin_gzh.platform.logger'):
            _run(WeixinGzhPlatform._upload_images(page, ['/a.png']))
        _loc(page, "input[type='file'][accept*='image']").first.set_input_files.assert_awaited_once_with(
            ['/a.png'])

    def test_all_selectors_fail_raises(self):
        page = _mk_page()
        for sel in (".js_upload_btn_container input[type='file']",
                    "input[type='file'][accept*='image']",
                    "input[type='file'][multiple]"):
            _loc(page, sel).first.wait_for = AsyncMock(side_effect=TimeoutError('t'))
        with patch('impl.weixin_gzh.platform.logger'), \
             pytest.raises(RuntimeError, match='未找到图片上传 input'):
            _run(WeixinGzhPlatform._upload_images(page, ['/a.png']))

    def test_uploading_then_ended(self):
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[
            {'best': 0, 'uploading': 1, 'target': 2},
            {'best': 1, 'uploading': 0, 'target': 2},
        ])
        with _mk_time(0.0, 1.0, 2.0), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._upload_images(page, ['/a.png', '/b.png']))
        progress_logs = [c.args for c in logger.info.call_args_list
                         if c.args and c.args[0] == '[发布图集] 上传进度: %s']
        assert progress_logs == [
            ('[发布图集] 上传进度: %s', '已上传预览=0/目标=2 上传中=1'),
            ('[发布图集] 上传进度: %s', '已上传预览=1/目标=2 上传中=0'),
        ]

    def test_timeout_warns(self):
        page = _mk_page()
        page.evaluate = AsyncMock(return_value={'best': 0, 'uploading': 0, 'target': 2})
        with _mk_time(0.0, 0.0, 301.0), \
             patch('impl.weixin_gzh.platform.logger') as logger:
            _run(WeixinGzhPlatform._upload_images(page, ['/a.png', '/b.png']))
        assert any('图片上传等待超时' in c.args[0] for c in logger.warning.call_args_list)


# ── 纯函数补测（模块级 time stub 模式）───────────────────────────────────

class TestParseCookieStubTime:
    def test_expires_uses_module_time_stub(self):
        p = _mk_platform()
        with patch('impl.weixin_gzh.platform.time', _mk_stub_time(1000.0)):
            cookies, origins = p._parse_cookie_to_storage_state('a=1; bad; b=2')
        assert origins == []
        assert [c['name'] for c in cookies] == ['a', 'b']
        assert cookies[0]['expires'] == 1000.0 + WeixinGzhPlatform._IMPORT_COOKIE_EXPIRES_SECONDS
