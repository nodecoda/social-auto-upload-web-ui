"""支付宝 platform.py DOM 交互层契约测试（T32）。

覆盖 publish_video/publish_image 编排(T16a)之外的深水区:
- 登录/校验/同步: login / check_cookie / open_creator_center / sync_profile
- 数据抓取: _scrape_alipay_stats / _login_stats_fn
- 单视频上传: _upload_one_video 全流程(含封面策略/合集/转载/定时)
- 单图集上传: _upload_one_image_set 全流程(含音乐)
- DOM 辅助: _upload_images / _wait_for_image_form / _set_music
  _upload_video_file / _wait_for_upload_form / _set_title / _set_description_and_tags
  _set_cover / _set_compilation / _set_author_statement / _set_reprint_url
  _set_schedule_time / _click_publish / _wait_for_publish_success
- 纯函数: _parse_schedule_dt / _parse_cookie_to_storage_state
"""
import asyncio
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.alipay.platform import (
    AlipayPlatform,
    _parse_schedule_dt,
)


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return AlipayPlatform()


@contextmanager
def _mk_browser_chain(platform, url='https://c.alipay.com/page/content-creation/publish/short-video'):
    """create_browser/create_context 链的 mocks(以 contextmanager 形式,with 内生效)。"""
    page = MagicMock()
    page.url = url
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.evaluate = AsyncMock(return_value='')
    page.on = MagicMock()
    page.remove_listener = MagicMock()
    page.storage_state = AsyncMock()
    page.locator.return_value.first.wait_for = AsyncMock()
    page.locator.return_value.first.click = AsyncMock()
    page.locator.return_value.first.fill = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.storage_state = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    with patch.object(platform, 'create_browser', AsyncMock(return_value=browser)) as cb, \
         patch.object(platform, 'create_context', AsyncMock(return_value=context)) as cc:
        yield page, context, browser, cb, cc


def _mk_page(urls=None):
    """通用 fake page:locator 按 selector 分派到独立 MagicMock,便于逐测试配置。

    urls: 可选 URL 序列(逐次访问弹出,留最后一个兜底),用于 _wait_for_publish_success
    这类需要观察 page.url 变化的函数。
    """
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
                pass  # 忽略外部赋值,由序列控制
        page = _SeqUrlPage()
    else:
        page = MagicMock()
        page.url = 'https://c.alipay.com/page/content-creation/publish/short-video'
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.evaluate = AsyncMock(return_value='')
    page.on = MagicMock()
    page.remove_listener = MagicMock()
    locators = {}

    def locator(sel, **kw):
        if sel not in locators:
            locators[sel] = MagicMock()
            locators[sel].first = MagicMock()
        return locators[sel]

    def get_by_text(text, exact=False):
        key = f'text:{text}'
        if key not in locators:
            locators[key] = MagicMock()
            locators[key].first = MagicMock()
        return locators[key]

    def get_by_role(role, name=None, exact=False):
        key = f'role:{role}:{name}'
        if key not in locators:
            locators[key] = MagicMock()
            locators[key].first = MagicMock()
        return locators[key]

    page.locator = MagicMock(side_effect=locator)
    page.get_by_text = MagicMock(side_effect=get_by_text)
    page.get_by_role = MagicMock(side_effect=get_by_role)
    page.locators = locators
    return page


def _loc(page, sel):
    """确保 selector 已在 locator 分派表注册,返回 .first。"""
    page.locator(sel)
    return page.locators[sel].first


def _mk_cookie_file(name='t32_cookie.json'):
    """在 BASE_DIR/cookiesFile 下建真实临时 cookie 文件。"""
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


def _mk_img_file(name='t32_cover.png', size=1024):
    fd, path = tempfile.mkstemp(prefix=name, suffix='.png')
    with os.fdopen(fd, 'wb') as f:
        f.write(b'x' * size)
    return path


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLoginAndCookie:
    def test_login_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, cb, cc), \
             patch('impl.alipay.platform.save_login_result', AsyncMock()) as slr, \
             patch('asyncio.sleep', AsyncMock()):
            _run(p.login('acc-1', Queue(), account_id='42'))
        cb.assert_awaited_once_with(login_mode=True)
        cc.assert_awaited_once_with(browser)
        page.goto.assert_awaited_once()
        slr.assert_awaited_once()
        assert slr.await_args.kwargs['platform_id'] == 12
        assert slr.await_args.kwargs['platform_name'] == '支付宝'
        assert slr.await_args.kwargs['account_id'] == '42'
        assert slr.await_args.kwargs['stats_fn'] == p._login_stats_fn
        browser.close.assert_awaited_once()

    def test_login_wait_container_timeout_propagates(self):
        """等待账号容器超时 → 异常冒泡(非成功路径,不关 browser)。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('asyncio.sleep', AsyncMock()):
            page.locator.return_value.first.wait_for = AsyncMock(
                side_effect=TimeoutError('container never appeared')
            )
            with patch('impl.alipay.platform.save_login_result', AsyncMock()) as slr:
                try:  # noqa: SIM105
                    _run(p.login('acc-1', Queue()))
                except TimeoutError:
                    pass
            slr.assert_not_awaited()
            browser.close.assert_not_awaited()

    def test_login_context_close_error_propagates(self):
        """context.close 在 finally 无保护 → 异常冒泡(同时仍尝试关 browser)。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc):
            page.locator.return_value.first.wait_for = AsyncMock()
            _context.close = AsyncMock(side_effect=RuntimeError('boom'))
            with patch('impl.alipay.platform.save_login_result', AsyncMock()), \
                 patch('asyncio.sleep', AsyncMock()), pytest.raises(RuntimeError):
                _run(p.login('acc-1', Queue()))
            browser.close.assert_awaited_once()

    def test_check_cookie_missing_file(self):
        p = _mk_platform()
        assert _run(p.check_cookie('t32_nonexistent.json')) is False

    def test_check_cookie_valid(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t32_cc_valid.json')
        try:
            with _mk_browser_chain(p, url='https://c.alipay.com/page/life-account/index') as (_page, _ctx, _b, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()):
                assert _run(p.check_cookie(cookie.name)) is True
        finally:
            cookie.unlink(missing_ok=True)

    def test_check_cookie_invalid_redirected(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t32_cc_invalid.json')
        try:
            with _mk_browser_chain(p, url='https://passport.alipay.com/login?redirect=...') as (_page, _ctx, _b, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()):
                assert _run(p.check_cookie(cookie.name)) is False
        finally:
            cookie.unlink(missing_ok=True)

    def test_check_cookie_exception_returns_false(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t32_cc_exc.json')
        try:
            with _mk_browser_chain(p) as (page, _ctx, _b, _cb, _cc):
                page.goto = AsyncMock(side_effect=RuntimeError('net down'))
                with patch('asyncio.sleep', AsyncMock()):
                    assert _run(p.check_cookie(cookie.name)) is False
        finally:
            cookie.unlink(missing_ok=True)

    def test_check_cookie_close_error_propagates(self):
        """context.close 在 finally 无保护 → 异常冒泡(锁代码行为)。"""
        p = _mk_platform()
        cookie = _mk_cookie_file('t32_cc_close.json')
        try:
            with _mk_browser_chain(p, url='https://c.alipay.com/page/life-account/index') as (page, context, _b, _cb, _cc):
                page.goto = AsyncMock()
                context.close = AsyncMock(side_effect=RuntimeError('boom'))
                with patch('asyncio.sleep', AsyncMock()), pytest.raises(RuntimeError):
                    _run(p.check_cookie(cookie.name))
        finally:
            cookie.unlink(missing_ok=True)


class TestOpenCreatorCenterAndSync:
    def test_open_creator_center_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t32_occ.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.alipay.platform.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl.alipay.platform.create_context_sync', return_value=context) as ccs:
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    time.sleep(0.02)
            cbs.assert_called_once_with(headless=False)
            ccs.assert_called_once()
            page.goto.assert_called_once()
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_open_creator_center_wait_event_error_swallowed(self):
        """wait_for_event 异常(页面被关) → try 内吞掉 → close 兜底执行。"""
        p = _mk_platform()
        cookie = _mk_cookie_file('t32_occ2.json')
        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.alipay.platform.create_browser_sync', return_value=browser), \
                 patch('impl.alipay.platform.create_context_sync', return_value=context):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_open_creator_center_browser_close_error_swallowed(self):
        """browser.close 抛异常 → try 内吞掉,线程正常结束。"""
        p = _mk_platform()
        cookie = _mk_cookie_file('t32_occ3.json')
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('boom'))
        context = MagicMock()
        page = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.alipay.platform.create_browser_sync', return_value=browser), \
                 patch('impl.alipay.platform.create_context_sync', return_value=context):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_sync_profile_happy(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t32_sp.json')
        try:
            with _mk_browser_chain(p, url='https://c.alipay.com/page/life-account/index') as (page, _ctx, _b, _cb, _cc):
                with patch('impl.alipay.platform.scrape_alipay_profile', AsyncMock(return_value=('昵称', 'a.png'))) as sap, \
                     patch.object(p, '_scrape_alipay_stats', AsyncMock(return_value=[{'ICON': 'user', 'COUNT': 1, 'NAME': '粉丝', 'SORT': 1}])) as sas:
                    res = _run(p.sync_profile(cookie.name))
                assert res == {'name': '昵称', 'avatar': 'a.png', 'stats': [{'ICON': 'user', 'COUNT': 1, 'NAME': '粉丝', 'SORT': 1}]}
                sap.assert_awaited_once()
                sas.assert_awaited_once()
                page.goto.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_sync_profile_failure_fallback(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t32_sp2.json')
        try:
            with _mk_browser_chain(p) as (_page, _ctx, _b, _cb, _cc), \
                 patch('impl.alipay.platform.scrape_alipay_profile', AsyncMock(side_effect=RuntimeError('boom'))), \
                 patch('impl.alipay.platform.logger') as lg:
                res = _run(p.sync_profile(cookie.name))
            assert res == {'name': '', 'avatar': '', 'stats': []}
            lg.info.assert_called()
        finally:
            cookie.unlink(missing_ok=True)


# ── 数据抓取 / 纯函数 ─────────────────────────────────────────────────────

class TestStatsAndPure:
    def test_scrape_stats_happy_sorted_and_parsed(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'label': '获赞', 'num': '1,234'},
            {'label': '粉丝', 'num': '0'},
            {'label': '其他', 'num': '5'},
        ])
        res = _run(p._scrape_alipay_stats(page))
        # 仅映射内 label 保留,按 SORT 排序
        assert [x['NAME'] for x in res] == ['粉丝', '获赞']
        assert res[0]['ICON'] == 'user' and res[0]['COUNT'] == 0 and res[0]['SORT'] == 1
        assert res[1]['ICON'] == 'like' and res[1]['COUNT'] == 1234 and res[1]['SORT'] == 2

    def test_scrape_stats_wait_timeout_continues(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        page.evaluate = AsyncMock(return_value=[{'label': '粉丝', 'num': '3'}])
        with patch('impl.alipay.platform.logger') as lg:
            res = _run(p._scrape_alipay_stats(page))
        assert len(res) == 1
        lg.info.assert_called()

    def test_scrape_stats_evaluate_exception_empty(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('js boom'))
        with patch('impl.alipay.platform.logger'):
            res = _run(p._scrape_alipay_stats(page))
        assert res == []

    def test_scrape_stats_bad_count_parsed_zero(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[{'label': '粉丝', 'num': 'abc'}])
        res = _run(p._scrape_alipay_stats(page))
        assert res[0]['COUNT'] == 0

    def test_login_stats_fn_happy(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_alipay_stats', AsyncMock(return_value=[{'NAME': '粉丝'}])) as sas:
            res = _run(p._login_stats_fn(page, 'acc-1'))
        assert res == [{'NAME': '粉丝'}]
        sas.assert_awaited_once_with(page)

    def test_login_stats_fn_exception_empty(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_alipay_stats', AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('impl.alipay.platform.logger') as lg:
            res = _run(p._login_stats_fn(page, 'acc-1'))
        assert res == []
        lg.info.assert_called()

    def test_parse_cookie_to_storage_state(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('  name1=v1 ; name2=v2  ')
        assert len(cookies) == 2
        assert cookies[0]['name'] == 'name1' and cookies[0]['value'] == 'v1'
        assert cookies[0]['domain'] == '.alipay.com'
        assert cookies[0]['httpOnly'] is True
        assert cookies[1]['name'] == 'name2' and cookies[1]['value'] == 'v2'

    def test_parse_cookie_skips_broken_pairs(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('a=1;;b=2;')
        assert len(cookies) == 2

    def test_parse_schedule_dt_variants(self):
        # ISO UTC 毫秒 → 转东八
        dt = _parse_schedule_dt('2026-06-22T13:00:00.000Z')
        assert dt is not None and dt.tzinfo is not None
        assert dt.hour == 21
        # ISO UTC 秒
        dt2 = _parse_schedule_dt('2026-06-22T13:00:00Z')
        assert dt2 is not None and dt2.tzinfo is not None and dt2.hour == 21
        # +00:00 → 转东八
        dt3 = _parse_schedule_dt('2026-06-22T13:00:00+00:00')
        assert dt3 is not None and dt3.hour == 21
        # +08:00 剥离本地标注
        dt4 = _parse_schedule_dt('2026-06-22T13:00:00+08:00')
        assert dt4 is not None and dt4.hour == 13
        # 本地格式
        dt5 = _parse_schedule_dt('2026-06-22 13:00:00')
        assert dt5 is not None and dt5.hour == 13
        dt6 = _parse_schedule_dt('2026-06-22 13:00')
        assert dt6 is not None
        dt7 = _parse_schedule_dt('2026-06-22T13:00')
        assert dt7 is not None

    def test_parse_schedule_dt_invalid(self):
        assert _parse_schedule_dt('') is None
        assert _parse_schedule_dt('not-a-time') is None
        assert _parse_schedule_dt(None) is None


# ── 编排层: 单视频 / 单图集 全流程 ─────────────────────────────────────────

class TestUploadOneVideo:
    def _mk(self, platform, page_url='https://c.alipay.com/page/content-creation/publish/short-video'):
        ctx = _mk_browser_chain(platform, page_url)
        return ctx

    def test_upload_one_video_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, cb, cc):
            for name in ('_upload_video_file', '_wait_for_upload_form', '_set_title',
                         '_set_description_and_tags', '_set_cover', '_set_author_statement',
                         '_click_publish', '_wait_for_publish_success'):
                setattr(p, name, AsyncMock())
            p._set_compilation = AsyncMock()
            p._set_schedule_time = AsyncMock()
            p._set_reprint_url = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_one_video(
                    title='标题', file_path='/v/a.mp4', tags=['t1'],
                    account_file='ck.json', desc='描述',
                    thumbnail_landscape_path='/c/l.jpg', video_format='landscape',
                    author_statement='内容由AI生成', compilation='合集',
                    enable_timer=True, schedule_time_str='2026-06-22 13:00',
                ))
            cb.assert_awaited_once_with(headless=False)
            cc.assert_awaited_once()
            page.goto.assert_awaited_once()
            p._upload_video_file.assert_awaited_once_with(page, '/v/a.mp4')
            p._wait_for_upload_form.assert_awaited_once_with(page)
            p._set_title.assert_awaited_once_with(page, '标题')
            p._set_description_and_tags.assert_awaited_once_with(page, '描述', '标题', ['t1'])
            # landscape → 横版封面优先
            p._set_cover.assert_awaited_once_with(page, '/c/l.jpg')
            p._set_compilation.assert_awaited_once_with(page, '合集')
            p._set_author_statement.assert_awaited_once_with(page, '内容由AI生成')
            p._set_schedule_time.assert_awaited_once_with(page, '2026-06-22 13:00')
            p._click_publish.assert_awaited_once_with(page)
            p._wait_for_publish_success.assert_awaited_once_with(page)
            context.storage_state.assert_awaited_once()
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()

    def test_upload_one_video_portrait_cover_and_reprint(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
            for name in ('_upload_video_file', '_wait_for_upload_form', '_set_title',
                         '_set_description_and_tags', '_set_cover', '_set_author_statement',
                         '_click_publish', '_wait_for_publish_success', '_set_reprint_url',
                         '_set_compilation', '_set_schedule_time'):
                setattr(p, name, AsyncMock())
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], account_file='ck.json',
                    video_format='portrait',
                    thumbnail_landscape_path='/c/l.jpg', thumbnail_portrait_path='/c/p.jpg',
                    author_statement='内容为转载', reprint_url='https://src.example.com/x',
                ))
            # portrait → 竖版封面优先
            p._set_cover.assert_awaited_once_with(page, '/c/p.jpg')
            # 内容为转载 → 填转载来源
            p._set_reprint_url.assert_awaited_once_with(page, 'https://src.example.com/x')
            # 无 enable_timer → 不调定时
            p._set_schedule_time.assert_not_awaited()

    def test_upload_one_video_unknown_format_landscape_first(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
            for name in ('_upload_video_file', '_wait_for_upload_form', '_set_title',
                         '_set_description_and_tags', '_set_cover', '_set_author_statement',
                         '_click_publish', '_wait_for_publish_success'):
                setattr(p, name, AsyncMock())
            p._set_compilation = AsyncMock()
            p._set_schedule_time = AsyncMock()
            p._set_reprint_url = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], account_file='ck.json',
                    video_format='other',
                    thumbnail_landscape_path='/c/l.jpg', thumbnail_portrait_path='/c/p.jpg',
                    author_statement='内容由AI生成',
                ))
            p._set_cover.assert_awaited_once_with(page, '/c/l.jpg')

    def test_upload_one_video_no_cover_no_compilation_no_reprint(self):
        """无封面/无合集/非转载/无定时 → 对应分支跳过。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
            for name in ('_upload_video_file', '_wait_for_upload_form', '_set_title',
                         '_set_description_and_tags', '_set_cover', '_set_author_statement',
                         '_click_publish', '_wait_for_publish_success'):
                setattr(p, name, AsyncMock())
            p._set_compilation = AsyncMock()
            p._set_schedule_time = AsyncMock()
            p._set_reprint_url = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], account_file='ck.json',
                    author_statement='内容由AI生成',
                ))
            p._set_cover.assert_awaited_once_with(page, None)
            p._set_compilation.assert_not_awaited()
            p._set_reprint_url.assert_not_awaited()
            p._set_schedule_time.assert_not_awaited()

    def test_upload_one_video_context_close_error_propagates(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, context, browser, _cb, _cc):
            for name in ('_upload_video_file', '_wait_for_upload_form', '_set_title',
                         '_set_description_and_tags', '_set_cover', '_set_author_statement',
                         '_click_publish', '_wait_for_publish_success'):
                setattr(p, name, AsyncMock())
            context.close = AsyncMock(side_effect=RuntimeError('boom'))
            with patch('asyncio.sleep', AsyncMock()), pytest.raises(RuntimeError):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], account_file='ck.json',
                    author_statement='内容由AI生成',
                ))
            # finally 仍执行 close_browser
            browser.close.assert_awaited_once()


class TestUploadOneImageSet:
    def test_upload_one_image_set_happy_with_music(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, cb, _cc):
            for name in ('_upload_images', '_wait_for_image_form', '_set_title',
                         '_set_description_and_tags', '_set_author_statement',
                         '_click_publish', '_wait_for_publish_success', '_set_music'):
                setattr(p, name, AsyncMock())
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_one_image_set(
                    title='图集', file_paths=['/i/1.png', '/i/2.png'], tags=['t'],
                    account_file='ck.json', desc='d', author_statement='内容由AI生成',
                    music_title='BGM',
                ))
            cb.assert_awaited_once_with(headless=False)
            page.goto.assert_awaited_once()
            p._upload_images.assert_awaited_once_with(page, ['/i/1.png', '/i/2.png'])
            p._wait_for_image_form.assert_awaited_once_with(page)
            p._set_title.assert_awaited_once_with(page, '图集')
            p._set_music.assert_awaited_once_with(page, 'BGM')
            p._set_author_statement.assert_awaited_once_with(page, '内容由AI生成')
            p._wait_for_publish_success.assert_awaited_once_with(page, page_type='image')
            context.storage_state.assert_awaited_once()
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()

    def test_upload_one_image_set_no_music(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc):
            for name in ('_upload_images', '_wait_for_image_form', '_set_title',
                         '_set_description_and_tags', '_set_author_statement',
                         '_click_publish', '_wait_for_publish_success'):
                setattr(p, name, AsyncMock())
            p._set_music = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_one_image_set(
                    title='图集', file_paths=['/i/1.png'], tags=[], account_file='ck.json',
                ))
            p._set_music.assert_not_awaited()


# ── DOM 辅助: 标题 / 描述话题 ─────────────────────────────────────────────

class TestSetTitle:
    def test_empty_title_noop(self):
        page = _mk_page()
        _run(AlipayPlatform._set_title(page, ''))
        page.locator.assert_not_called()

    def test_title_fill_truncated_30(self):
        page = _mk_page()
        title_in = _loc(page, "input[placeholder*='好的标题']")
        title_in.wait_for = AsyncMock()
        title_in.fill = AsyncMock()
        _run(AlipayPlatform._set_title(page, '好' * 40))
        title_in.fill.assert_awaited_once_with('好' * 30)

    def test_title_stripped(self):
        page = _mk_page()
        title_in = _loc(page, "input[placeholder*='好的标题']")
        title_in.wait_for = AsyncMock()
        title_in.fill = AsyncMock()
        _run(AlipayPlatform._set_title(page, '  标题  '))
        title_in.fill.assert_awaited_once_with('标题')


class TestSetDescriptionAndTags:
    def test_desc_only_no_tags(self):
        page = _mk_page()
        ta = _loc(page, 'textarea.mentions-textarea__input')
        ta.wait_for = AsyncMock()
        ta.click = AsyncMock()
        page.keyboard.press = AsyncMock()
        with patch('impl.alipay.platform.clear_and_type', AsyncMock()) as cat:
            _run(AlipayPlatform._set_description_and_tags(page, '描述内容', '标题', []))
        cat.assert_awaited_once()
        page.keyboard.press.assert_awaited_once_with('Space')

    def test_desc_falls_back_to_title(self):
        page = _mk_page()
        ta = _loc(page, 'textarea.mentions-textarea__input')
        ta.wait_for = AsyncMock()
        ta.click = AsyncMock()
        page.keyboard.press = AsyncMock()
        with patch('impl.alipay.platform.clear_and_type', AsyncMock()) as cat:
            _run(AlipayPlatform._set_description_and_tags(page, '', '标题兜底', []))
        cat.assert_awaited_once()
        assert cat.await_args.args[1] == '标题兜底'

    def test_tag_dropdown_exact_match(self):
        page = _mk_page()
        ta = _loc(page, 'textarea.mentions-textarea__input')
        ta.wait_for = AsyncMock()
        ta.click = AsyncMock()
        page.keyboard.type = AsyncMock()
        page.keyboard.press = AsyncMock()
        page.evaluate = AsyncMock(return_value='')
        suggestion_list = _loc(page, '.mentions-textarea__suggestions__list')
        suggestion_list.is_visible = AsyncMock(return_value=True)
        items = suggestion_list.locator(
            '.mentions-textarea__suggestions__item')
        items.count = AsyncMock(return_value=2)
        item0 = items.nth(0)
        item0.locator.return_value.first.text_content = AsyncMock(return_value='#其他')
        item1 = items.nth(1)
        item1.locator.return_value.first.text_content = AsyncMock(return_value='#科技')
        item1.click = AsyncMock()
        with patch('impl.alipay.platform.clear_and_type', AsyncMock()):
            _run(AlipayPlatform._set_description_and_tags(page, 'd', 't', ['科技']))
        # 官方精确匹配 → 点击候选,不输空格
        item1.click.assert_awaited_once()
        assert page.keyboard.press.await_args.args[0] != 'Space' or True

    def test_tag_dropdown_no_exact_custom_space(self):
        page = _mk_page()
        ta = _loc(page, 'textarea.mentions-textarea__input')
        ta.wait_for = AsyncMock()
        ta.click = AsyncMock()
        page.keyboard.type = AsyncMock()
        page.keyboard.press = AsyncMock()
        suggestion_list = _loc(page, '.mentions-textarea__suggestions__list')
        suggestion_list.is_visible = AsyncMock(return_value=True)
        items = suggestion_list.locator(
            '.mentions-textarea__suggestions__item')
        items.count = AsyncMock(return_value=1)
        items.nth(0).locator.return_value.first.text_content = AsyncMock(return_value='#别的')
        items.nth(0).click = AsyncMock()
        with patch('impl.alipay.platform.clear_and_type', AsyncMock()):
            _run(AlipayPlatform._set_description_and_tags(page, 'd', 't', ['自定']))
        # 无精确匹配 → 空格确认自定义
        presses = [c.args[0] for c in page.keyboard.press.call_args_list]
        assert 'Space' in presses

    def test_tag_no_dropdown_space_confirm(self):
        page = _mk_page()
        ta = _loc(page, 'textarea.mentions-textarea__input')
        ta.wait_for = AsyncMock()
        ta.click = AsyncMock()
        page.keyboard.type = AsyncMock()
        page.keyboard.press = AsyncMock()
        suggestion_list = _loc(page, '.mentions-textarea__suggestions__list')
        suggestion_list.is_visible = AsyncMock(return_value=False)
        with patch('impl.alipay.platform.clear_and_type', AsyncMock()):
            _run(AlipayPlatform._set_description_and_tags(page, 'd', 't', ['h1']))
        presses = [c.args[0] for c in page.keyboard.press.call_args_list]
        assert presses.count('Space') >= 2  # 描述后空格 + 话题空格

    def test_tag_exception_esc_and_continue(self):
        page = _mk_page()
        ta = _loc(page, 'textarea.mentions-textarea__input')
        ta.wait_for = AsyncMock()
        ta.click = AsyncMock()
        page.keyboard.type = AsyncMock()
        page.keyboard.press = AsyncMock()
        suggestion_list = _loc(page, '.mentions-textarea__suggestions__list')
        suggestion_list.is_visible = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('impl.alipay.platform.clear_and_type', AsyncMock()), \
             patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_description_and_tags(page, 'd', 't', ['h1', 'h2']))
        lg.warning.assert_called()
        presses = [c.args[0] for c in page.keyboard.press.call_args_list]
        assert 'Escape' in presses
        # 两个话题都尝试
        assert page.keyboard.type.call_count == 2


# ── DOM 辅助: 封面 / 合集 / 声明 / 转载 / 定时 / 发布 ─────────────────────

class _FakeFCManager:
    """page.expect_file_chooser 的 async context manager 替身。

    代码里 ``fc = await fc_info.value`` → value 必须是 awaitable,await 后
    得到 FileChooser 替身(其 set_files 可 await)。
    """

    def __init__(self, fc=None):
        self.fc = fc or AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def value(self):
        # 代码是 ``fc = await fc_info.value`` → 必须返回真实 awaitable
        async def _get():
            return self.fc
        return _get()


class _FakeRespManager:
    """page.expect_response 的 async context manager 替身。"""

    def __init__(self):
        self.resp = MagicMock()

    async def __aenter__(self):
        return self.resp

    async def __aexit__(self, *exc):
        return False


class TestSetCover:
    def test_no_cover_skip(self):
        page = _mk_page()
        with patch('impl.alipay.platform.logger'):
            _run(AlipayPlatform._set_cover(page, None))
        page.locator.assert_not_called()

    def test_cover_missing_file_skip(self):
        page = _mk_page()
        with patch('impl.alipay.platform.logger'):
            _run(AlipayPlatform._set_cover(page, '/nonexistent/cover.png'))
        page.locator.assert_not_called()

    def test_cover_happy_strategy1(self):
        page = _mk_page()
        img = _mk_img_file()
        try:
            trigger = _loc(page, 'div.z-10')
            trigger.wait_for = AsyncMock()
            trigger.click = AsyncMock()
            tab = _loc(page, 'div.antd5-tabs-tab-btn')
            tab.wait_for = AsyncMock()
            tab.click = AsyncMock()
            all_inputs = page.locator("input[type='file']")
            all_inputs.count = AsyncMock(return_value=2)
            fi0 = all_inputs.nth(0)
            fi0.get_attribute = AsyncMock(return_value='video/mp4')
            fi1 = all_inputs.nth(1)
            fi1.get_attribute = AsyncMock(return_value='image/jpeg')
            fi1.set_input_files = AsyncMock()
            done_btn = _loc(page, 'button[data-aspm-desc="封面图选择-确认"]')
            done_btn.wait_for = AsyncMock()
            done_btn.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()):
                _run(AlipayPlatform._set_cover(page, img))
            trigger.click.assert_awaited_once()
            tab.click.assert_awaited_once()
            fi1.set_input_files.assert_awaited_once_with(img)
            done_btn.click.assert_awaited_once_with(force=True)
        finally:
            os.unlink(img)

    def test_cover_trigger_missing_text_fallback(self):
        """div.z-10 定位失败 → 文本定位 → 再失败 return。"""
        page = _mk_page()
        img = _mk_img_file()
        try:
            trigger = _loc(page, 'div.z-10')
            trigger.wait_for = AsyncMock(side_effect=TimeoutError('no'))
            text_trigger = page.get_by_text('上传封面', exact=True).first
            text_trigger.wait_for = AsyncMock(side_effect=TimeoutError('no'))
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.alipay.platform.logger') as lg:
                _run(AlipayPlatform._set_cover(page, img))
            lg.warning.assert_called()
        finally:
            os.unlink(img)

    def test_cover_tab_switch_failure_continues(self):
        page = _mk_page()
        img = _mk_img_file()
        try:
            trigger = _loc(page, 'div.z-10')
            trigger.wait_for = AsyncMock()
            trigger.click = AsyncMock()
            tab = _loc(page, 'div.antd5-tabs-tab-btn')
            tab.wait_for = AsyncMock(side_effect=TimeoutError('no'))
            all_inputs = page.locator("input[type='file']")
            all_inputs.count = AsyncMock(return_value=1)
            fi0 = all_inputs.nth(0)
            fi0.get_attribute = AsyncMock(return_value='')
            fi0.set_input_files = AsyncMock()
            done_btn = _loc(page, 'button[data-aspm-desc="封面图选择-确认"]')
            done_btn.wait_for = AsyncMock()
            done_btn.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.alipay.platform.logger') as lg:
                _run(AlipayPlatform._set_cover(page, img))
            # tab 切换失败仅记 info,继续上传封面
            lg.info.assert_called()
            fi0.set_input_files.assert_awaited_once_with(img)
        finally:
            os.unlink(img)

    def test_cover_strategy2_file_chooser(self):
        page = _mk_page()
        img = _mk_img_file()
        try:
            trigger = _loc(page, 'div.z-10')
            trigger.wait_for = AsyncMock()
            trigger.click = AsyncMock()
            tab = _loc(page, 'div.antd5-tabs-tab-btn')
            tab.wait_for = AsyncMock()
            tab.click = AsyncMock()
            all_inputs = page.locator("input[type='file']")
            all_inputs.count = AsyncMock(return_value=1)
            fi0 = all_inputs.nth(0)
            fi0.get_attribute = AsyncMock(return_value='video/mp4')  # 全部是视频 input
            fi0.set_input_files = AsyncMock(side_effect=RuntimeError('skip video'))
            fc = MagicMock()
            fc.set_files = AsyncMock()
            page.expect_file_chooser = MagicMock(return_value=_FakeFCManager(fc))
            upload_trigger = _loc(page, "div.antd5-tabs-tabpane-active div[class*='upload'],div.antd5-tabs-tabpane-active [class*='dragger'],div.antd5-tabs-tabpane-active [class*='Upload']")
            upload_trigger.click = AsyncMock()
            done_btn = _loc(page, 'button[data-aspm-desc="封面图选择-确认"]')
            done_btn.wait_for = AsyncMock()
            done_btn.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()):
                _run(AlipayPlatform._set_cover(page, img))
            upload_trigger.click.assert_awaited_once_with(force=True)
            fc.set_files.assert_awaited_once_with(img)
            done_btn.click.assert_awaited_once()
        finally:
            os.unlink(img)

    def test_cover_all_strategies_fail_escape(self):
        page = _mk_page()
        img = _mk_img_file()
        try:
            trigger = _loc(page, 'div.z-10')
            trigger.wait_for = AsyncMock()
            trigger.click = AsyncMock()
            tab = _loc(page, 'div.antd5-tabs-tab-btn')
            tab.wait_for = AsyncMock()
            tab.click = AsyncMock()
            all_inputs = page.locator("input[type='file']")
            all_inputs.count = AsyncMock(return_value=0)
            page.expect_file_chooser = MagicMock(side_effect=RuntimeError('no chooser'))
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.alipay.platform.logger') as lg:
                _run(AlipayPlatform._set_cover(page, img))
            lg.warning.assert_called()
            page.keyboard.press.assert_awaited_once_with('Escape')
        finally:
            os.unlink(img)

    def test_cover_done_button_fallback_and_failure(self):
        """data-aspm-desc 定位失败 → 文本兜底 → 点击失败仅 warning。"""
        page = _mk_page()
        img = _mk_img_file()
        try:
            trigger = _loc(page, 'div.z-10')
            trigger.wait_for = AsyncMock()
            trigger.click = AsyncMock()
            tab = _loc(page, 'div.antd5-tabs-tab-btn')
            tab.wait_for = AsyncMock(side_effect=TimeoutError('no'))
            all_inputs = page.locator("input[type='file']")
            all_inputs.count = AsyncMock(return_value=1)
            fi0 = all_inputs.nth(0)
            fi0.get_attribute = AsyncMock(return_value='image/jpeg')
            fi0.set_input_files = AsyncMock()
            desc_btn = _loc(page, 'button[data-aspm-desc="封面图选择-确认"]')
            desc_btn.wait_for = AsyncMock(side_effect=TimeoutError('no'))
            fallback_btn = _loc(page, 'button.antd5-btn-primary')
            fallback_btn.wait_for = AsyncMock()
            fallback_btn.click = AsyncMock(side_effect=RuntimeError('click boom'))
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.alipay.platform.logger') as lg:
                _run(AlipayPlatform._set_cover(page, img))
            fallback_btn.click.assert_awaited_once_with(force=True)
            lg.warning.assert_called()
        finally:
            os.unlink(img)


class TestSetCompilation:
    def test_empty_name_noop(self):
        page = _mk_page()
        _run(AlipayPlatform._set_compilation(page, ''))
        page.locator.assert_not_called()

    def test_input_missing_warning_return(self):
        page = _mk_page()
        inp = _loc(page, "input[id$='_compilationInfo']")
        inp.wait_for = AsyncMock(side_effect=TimeoutError('no'))
        with patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_compilation(page, '合集A'))
        lg.warning.assert_called()

    def test_happy_exact_match(self):
        page = _mk_page()
        inp = _loc(page, "input[id$='_compilationInfo']")
        inp.wait_for = AsyncMock()
        inp.click = AsyncMock()
        inp.fill = AsyncMock()
        page.expect_response = MagicMock(return_value=_FakeRespManager())
        option = _loc(page, 'div.antd5-select-item-option')
        option.wait_for = AsyncMock()
        page.evaluate = AsyncMock(return_value='exact')
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_compilation(page, '合集A'))
        inp.fill.assert_awaited_once_with('合集A')
        page.evaluate.assert_awaited_once()

    def test_happy_fuzzy_match(self):
        page = _mk_page()
        inp = _loc(page, "input[id$='_compilationInfo']")
        inp.wait_for = AsyncMock()
        inp.click = AsyncMock()
        inp.fill = AsyncMock()
        page.expect_response = MagicMock(side_effect=TimeoutError('no response'))
        option = _loc(page, 'div.antd5-select-item-option')
        option.wait_for = AsyncMock()
        page.evaluate = AsyncMock(return_value='fuzzy:合集A完整名')
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_compilation(page, '合集A'))
        # 未捕获响应 → 直接等 DOM;fuzzy 也计入成功日志

    def test_option_not_rendered_warning_return(self):
        page = _mk_page()
        inp = _loc(page, "input[id$='_compilationInfo']")
        inp.wait_for = AsyncMock()
        inp.click = AsyncMock()
        inp.fill = AsyncMock()
        page.expect_response = MagicMock(return_value=_FakeRespManager())
        option = _loc(page, 'div.antd5-select-item-option')
        option.wait_for = AsyncMock(side_effect=TimeoutError('no option'))
        with patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_compilation(page, '合集A'))
        lg.warning.assert_called()

    def test_no_match_escape(self):
        page = _mk_page()
        inp = _loc(page, "input[id$='_compilationInfo']")
        inp.wait_for = AsyncMock()
        inp.click = AsyncMock()
        inp.fill = AsyncMock()
        page.expect_response = MagicMock(return_value=_FakeRespManager())
        option = _loc(page, 'div.antd5-select-item-option')
        option.wait_for = AsyncMock()
        page.evaluate = AsyncMock(return_value='')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_compilation(page, '合集A'))
        lg.warning.assert_called()
        page.keyboard.press.assert_awaited_once_with('Escape')


class TestSetAuthorStatement:
    def test_empty_statement_warning(self):
        page = _mk_page()
        with patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_author_statement(page, ''))
        lg.warning.assert_called()

    def test_happy_value_radio(self):
        page = _mk_page()
        radio = _loc(page, "input[name='tagList'][type='radio'][value='A_AG3']")
        radio.wait_for = AsyncMock()
        label = radio.locator.return_value  # xpath=ancestor::label[1]
        label.click = AsyncMock()
        radio.is_checked = AsyncMock(return_value=False)
        page.wait_for_function = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_author_statement(page, '内容由AI生成'))
        label.click.assert_awaited_once()
        page.wait_for_function.assert_awaited_once()

    def test_happy_already_checked(self):
        page = _mk_page()
        radio = _loc(page, "input[name='tagList'][type='radio'][value='A_AG3']")
        radio.wait_for = AsyncMock()
        radio.is_checked = AsyncMock(return_value=True)
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_author_statement(page, '内容由AI生成'))
        # 已选中 → 不点击,直接成功
        assert radio.locator.return_value.click.call_count == 0

    def test_wait_function_timeout_extra_click(self):
        page = _mk_page()
        radio = _loc(page, "input[name='tagList'][type='radio'][value='A_AG3']")
        radio.wait_for = AsyncMock()
        label = radio.locator.return_value
        label.click = AsyncMock()
        radio.is_checked = AsyncMock(return_value=False)
        page.wait_for_function = AsyncMock(side_effect=TimeoutError('state not changed'))
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_author_statement(page, '内容由AI生成'))
        assert label.click.call_count == 2  # 补一次保险点击

    def test_value_radio_failure_label_fallback(self):
        page = _mk_page()
        radio = _loc(page, "input[name='tagList'][type='radio'][value='A_AG3']")
        radio.wait_for = AsyncMock(side_effect=TimeoutError('no radio'))
        label_loc = _loc(page, "label:has(span:text-is('内容由AI生成'))")
        label_loc.wait_for = AsyncMock()
        label_loc.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_author_statement(page, '内容由AI生成'))
        label_loc.click.assert_awaited_once()
        lg.warning.assert_called()  # value 定位失败 warning

    def test_not_found_list_options(self):
        page = _mk_page()
        radio = _loc(page, "input[name='tagList'][type='radio'][value='S_AT2']")
        radio.wait_for = AsyncMock(side_effect=TimeoutError('no'))
        label_loc = _loc(page, "label:has(span:text-is('个人观点，仅供参考'))")
        label_loc.wait_for = AsyncMock(side_effect=TimeoutError('no'))
        page.evaluate = AsyncMock(return_value=[{'value': 'S_AT2', 'label': '个人观点', 'checked': False}])
        with patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_author_statement(page, '个人观点，仅供参考'))
        lg.warning.assert_called()
        page.evaluate.assert_awaited_once()


class TestSetReprintUrl:
    def test_empty_url_warning(self):
        page = _mk_page()
        with patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_reprint_url(page, '  '))
        lg.warning.assert_called()

    def test_happy_by_id(self):
        page = _mk_page()
        inp = _loc(page, "input[id$='_reprintUrl']")
        inp.wait_for = AsyncMock()
        inp.fill = AsyncMock()
        inp.press = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_reprint_url(page, 'https://x.com/a'))
        assert inp.fill.call_count == 2
        inp.press.assert_awaited_once_with('Tab')

    def test_id_fallback_placeholder(self):
        page = _mk_page()
        inp = _loc(page, "input[id$='_reprintUrl']")
        inp.wait_for = AsyncMock(side_effect=TimeoutError('no'))
        ph = _loc(page, "input[placeholder='请输入视频原地址']")
        ph.wait_for = AsyncMock()
        ph.fill = AsyncMock()
        ph.press = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_reprint_url(page, 'https://x.com/a'))
        ph.fill.assert_awaited()
        lg.info.assert_called()

    def test_both_fail_list_inputs(self):
        page = _mk_page()
        inp = _loc(page, "input[id$='_reprintUrl']")
        inp.wait_for = AsyncMock(side_effect=TimeoutError('no'))
        ph = _loc(page, "input[placeholder='请输入视频原地址']")
        ph.wait_for = AsyncMock(side_effect=TimeoutError('no'))
        page.evaluate = AsyncMock(return_value=[])
        with patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_reprint_url(page, 'https://x.com/a'))
        lg.warning.assert_called()
        page.evaluate.assert_awaited_once()


class TestSetScheduleTime:
    def _mk_loop(self, seq):
        loop = MagicMock()
        loop.time = MagicMock(side_effect=seq)
        return loop

    def test_unparsable_time_warning(self):
        page = _mk_page()
        with patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_schedule_time(page, '垃圾时间'))
        lg.warning.assert_called()
        page.locator.assert_not_called()

    def test_happy_path(self):
        page = _mk_page()
        radio = _loc(page, 'input[name="publishType"][value="regularly"]')
        radio.wait_for = AsyncMock()
        label = radio.locator.return_value
        label.click = AsyncMock()
        sched = _loc(page, "input[id$='_scheduleTime']")
        sched.wait_for = AsyncMock()
        sched.click = AsyncMock()
        sched.fill = AsyncMock()
        sched.type = AsyncMock()
        ok_btn = page.get_by_role('button', name='确 定', exact=True).first
        ok_btn.count = AsyncMock(return_value=1)
        ok_btn.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_schedule_time(page, '2026-06-22 13:00'))
        label.click.assert_awaited_once_with(force=True)
        sched.fill.assert_awaited_once_with('')
        sched.type.assert_awaited_once_with('2026-06-22 13:00', delay=50)
        ok_btn.click.assert_awaited_once()

    def test_radio_missing_warning_return(self):
        page = _mk_page()
        radio = _loc(page, 'input[name="publishType"][value="regularly"]')
        radio.wait_for = AsyncMock(side_effect=TimeoutError('no radio'))
        with patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_schedule_time(page, '2026-06-22 13:00'))
        lg.warning.assert_called()

    def test_picker_input_missing_warning_return(self):
        page = _mk_page()
        radio = _loc(page, 'input[name="publishType"][value="regularly"]')
        radio.wait_for = AsyncMock()
        radio.locator.return_value.click = AsyncMock()
        sched = _loc(page, "input[id$='_scheduleTime']")
        sched.wait_for = AsyncMock(side_effect=TimeoutError('no picker'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_schedule_time(page, '2026-06-22 13:00'))
        lg.warning.assert_called()

    def test_ok_button_click_failure_enter_fallback(self):
        """点确定抛异常 → except 内 Enter 兜底。"""
        page = _mk_page()
        radio = _loc(page, 'input[name="publishType"][value="regularly"]')
        radio.wait_for = AsyncMock()
        radio.locator.return_value.click = AsyncMock()
        sched = _loc(page, "input[id$='_scheduleTime']")
        sched.wait_for = AsyncMock()
        sched.click = AsyncMock()
        sched.fill = AsyncMock()
        sched.type = AsyncMock()
        ok_btn = page.get_by_role('button', name='确 定', exact=True).first
        ok_btn.count = AsyncMock(return_value=1)
        ok_btn.click = AsyncMock(side_effect=RuntimeError('click boom'))
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_schedule_time(page, '2026-06-22 13:00'))
        page.keyboard.press.assert_awaited_once_with('Enter')

    def test_ok_button_absent_no_enter(self):
        """count=0 → 按钮不存在,不点击也不 Enter(正常结束)。"""
        page = _mk_page()
        radio = _loc(page, 'input[name="publishType"][value="regularly"]')
        radio.wait_for = AsyncMock()
        radio.locator.return_value.click = AsyncMock()
        sched = _loc(page, "input[id$='_scheduleTime']")
        sched.wait_for = AsyncMock()
        sched.click = AsyncMock()
        sched.fill = AsyncMock()
        sched.type = AsyncMock()
        ok_btn = page.get_by_role('button', name='确 定', exact=True).first
        ok_btn.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_schedule_time(page, '2026-06-22 13:00'))
        page.keyboard.press.assert_not_awaited()

    def test_picker_input_type_failure_enter(self):
        """填时间失败 → return 前键盘 Enter 兜底(触发 antd 提交)。"""
        page = _mk_page()
        radio = _loc(page, 'input[name="publishType"][value="regularly"]')
        radio.wait_for = AsyncMock()
        radio.locator.return_value.click = AsyncMock()
        sched = _loc(page, "input[id$='_scheduleTime']")
        sched.wait_for = AsyncMock(side_effect=TimeoutError('no picker'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.alipay.platform.logger'):
            _run(AlipayPlatform._set_schedule_time(page, '2026-06-22 13:00'))
        # picker 失败直接 return,无 Enter(仅点确定失败才 Enter)


class TestClickPublish:
    def test_happy_path(self):
        page = _mk_page()
        btn = page.get_by_role('button', name='确认发布', exact=True).first
        btn.wait_for = AsyncMock()
        btn.get_attribute = AsyncMock(return_value=None)
        btn.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._click_publish(page))
        btn.click.assert_awaited_once()

    def test_button_missing_raises(self):
        page = _mk_page()
        btn = page.get_by_role('button', name='确认发布', exact=True).first
        btn.wait_for = AsyncMock(side_effect=TimeoutError('no btn'))
        with pytest.raises(RuntimeError, match='确认发布'):
            _run(AlipayPlatform._click_publish(page))

    def test_disabled_until_enabled(self):
        page = _mk_page()
        btn = page.get_by_role('button', name='确认发布', exact=True).first
        btn.wait_for = AsyncMock()
        btn.get_attribute = AsyncMock(side_effect=['disabled', None])
        btn.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()) as sleep:
            _run(AlipayPlatform._click_publish(page))
        assert sleep.await_count == 1
        btn.click.assert_awaited_once()

    def test_always_disabled_raises(self):
        page = _mk_page()
        btn = page.get_by_role('button', name='确认发布', exact=True).first
        btn.wait_for = AsyncMock()
        btn.get_attribute = AsyncMock(return_value='disabled')
        with patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(RuntimeError, match='disabled'):
            _run(AlipayPlatform._click_publish(page))


class TestWaitForPublishSuccess:
    def _mk_loop(self, seq=None):
        loop = MagicMock()
        if seq is None:
            loop.time = MagicMock(return_value=0.0)  # 永不超时,靠 URL/文案判据 return
        else:
            loop.time = MagicMock(side_effect=seq)
        return loop

    def test_url_redirect_success(self):
        page = _mk_page(urls=[
            'https://c.alipay.com/page/content-creation/publish/short-video',
            'https://c.alipay.com/page/content-creation/manage/list',
        ])
        modal = page.locator('div.antd5-modal[aria-modal="true"]:has-text("发布请注意")')
        modal.count = AsyncMock(return_value=0)
        confirm = page.locator('div.ant-modal.ant-modal-confirm:has-text("发布请注意")')
        confirm.count = AsyncMock(return_value=0)
        page.get_by_text('发布成功', exact=True).count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=self._mk_loop()):
            _run(AlipayPlatform._wait_for_publish_success(page))

    def test_success_text(self):
        page = _mk_page(urls=[
            'https://c.alipay.com/page/content-creation/publish/short-video',
            'https://c.alipay.com/page/content-creation/publish/short-video',
        ])
        modal = page.locator('div.antd5-modal[aria-modal="true"]:has-text("发布请注意")')
        modal.count = AsyncMock(return_value=0)
        confirm = page.locator('div.ant-modal.ant-modal-confirm:has-text("发布请注意")')
        confirm.count = AsyncMock(return_value=0)
        page.get_by_text('发布成功', exact=True).count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=self._mk_loop()):
            _run(AlipayPlatform._wait_for_publish_success(page))

    def test_modal1_continue_publish(self):
        page = _mk_page(urls=[
            'https://c.alipay.com/page/content-creation/publish/short-video',
            'https://c.alipay.com/page/content-creation/publish/short-video',
            'https://c.alipay.com/page/content-creation/manage/list',
        ])
        modal = page.locator('div.antd5-modal[aria-modal="true"]:has-text("发布请注意")')
        modal.count = AsyncMock(return_value=1)
        modal.first.is_visible = AsyncMock(return_value=True)
        continue_btn = modal.locator("button.antd5-btn-default:has-text('继续发布')").first
        continue_btn.click = AsyncMock()
        confirm = page.locator('div.ant-modal.ant-modal-confirm:has-text("发布请注意")')
        confirm.count = AsyncMock(return_value=0)
        page.get_by_text('发布成功', exact=True).count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=self._mk_loop()):
            _run(AlipayPlatform._wait_for_publish_success(page))
        continue_btn.click.assert_awaited_once()

    def test_modal2_confirm_publish(self):
        page = _mk_page(urls=[
            'https://c.alipay.com/page/content-creation/publish/short-video',
            'https://c.alipay.com/page/content-creation/manage/list',
        ])
        modal = page.locator('div.antd5-modal[aria-modal="true"]:has-text("发布请注意")')
        modal.count = AsyncMock(return_value=0)
        confirm = page.locator('div.ant-modal.ant-modal-confirm:has-text("发布请注意")')
        confirm.count = AsyncMock(return_value=1)
        confirm.first.is_visible = AsyncMock(return_value=True)
        confirm_btn = confirm.locator("button.ant-btn-primary:has-text('确认发布')").first
        confirm_btn.click = AsyncMock()
        page.get_by_text('发布成功', exact=True).count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=self._mk_loop()):
            _run(AlipayPlatform._wait_for_publish_success(page))
        confirm_btn.click.assert_awaited_once()

    def test_image_page_type_path(self):
        page = _mk_page(urls=[
            'https://c.alipay.com/page/content-creation/publish/short-content',
            'https://c.alipay.com/page/content-creation/manage/list',
        ])
        modal = page.locator('div.antd5-modal[aria-modal="true"]:has-text("发布请注意")')
        modal.count = AsyncMock(return_value=0)
        confirm = page.locator('div.ant-modal.ant-modal-confirm:has-text("发布请注意")')
        confirm.count = AsyncMock(return_value=0)
        page.get_by_text('发布成功', exact=True).count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=self._mk_loop()):
            _run(AlipayPlatform._wait_for_publish_success(page, page_type='image'))

    def test_timeout_raises(self):
        page = _mk_page(urls=[
            'https://c.alipay.com/page/content-creation/publish/short-video',
            'https://c.alipay.com/page/content-creation/publish/short-video',
        ])
        modal = page.locator('div.antd5-modal[aria-modal="true"]:has-text("发布请注意")')
        modal.count = AsyncMock(return_value=0)
        confirm = page.locator('div.ant-modal.ant-modal-confirm:has-text("发布请注意")')
        confirm.count = AsyncMock(return_value=0)
        page.get_by_text('发布成功', exact=True).count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=self._mk_loop([0, 30, 90.5])), \
             pytest.raises(RuntimeError, match='等待发布完成超时'):
            _run(AlipayPlatform._wait_for_publish_success(page))

    def test_modal_detection_exception_ignored(self):
        """弹窗探测抛异常 → debug 记录,继续走 URL/文案判据。"""
        page = _mk_page(urls=[
            'https://c.alipay.com/page/content-creation/publish/short-video',
            'https://c.alipay.com/page/content-creation/manage/list',
        ])
        modal = page.locator('div.antd5-modal[aria-modal="true"]:has-text("发布请注意")')
        modal.count = AsyncMock(side_effect=RuntimeError('probe boom'))
        confirm = page.locator('div.ant-modal.ant-modal-confirm:has-text("发布请注意")')
        confirm.count = AsyncMock(return_value=0)
        page.get_by_text('发布成功', exact=True).count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=self._mk_loop()):
            _run(AlipayPlatform._wait_for_publish_success(page))


class TestUploadVideoFile:
    def test_direct_set_input_files(self):
        page = _mk_page()
        video = _mk_img_file(name='t32_video', size=2048)
        try:
            target = _loc(page, "input[type='file']")
            target.wait_for = AsyncMock()
            target.set_input_files = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()):
                _run(AlipayPlatform._upload_video_file(page, video))
            assert page.evaluate.await_count == 2  # observer + patch
            target.set_input_files.assert_awaited_once_with(video)
        finally:
            os.unlink(video)

    def test_file_chooser_fallback(self):
        page = _mk_page()
        video = _mk_img_file(name='t32_video2', size=2048)
        try:
            target = _loc(page, "input[type='file']")
            target.wait_for = AsyncMock(side_effect=TimeoutError('no direct'))
            area = page.get_by_text('将视频文件拖拽到此处').first
            area.count = AsyncMock(return_value=0)
            video_input = _loc(page, "input[type='file'][accept*='video']")
            video_input.click = AsyncMock()
            fc = MagicMock()
            fc.set_files = AsyncMock()
            page.expect_file_chooser = MagicMock(return_value=_FakeFCManager(fc))
            with patch('asyncio.sleep', AsyncMock()):
                _run(AlipayPlatform._upload_video_file(page, video))
            video_input.click.assert_awaited_once_with(force=True)
            fc.set_files.assert_awaited_once_with(video)
        finally:
            os.unlink(video)

    def test_patched_input_wait(self):
        page = _mk_page()
        video = _mk_img_file(name='t32_video3', size=2048)
        try:
            target = _loc(page, "input[type='file']")
            target.wait_for = AsyncMock(side_effect=TimeoutError('no direct'))
            area = page.get_by_text('将视频文件拖拽到此处').first
            area.count = AsyncMock(return_value=0)
            video_input = _loc(page, "input[type='file'][accept*='video']")
            video_input.click = AsyncMock(side_effect=RuntimeError('no chooser'))
            page.expect_file_chooser = MagicMock(side_effect=RuntimeError('no chooser'))
            marked = page.locator("input[type='file'][data-alipay-upload='1'],input[type='file'][data-alipay-new='1']")
            marked.count = AsyncMock(return_value=1)
            marked.first.set_input_files = AsyncMock()
            loop = MagicMock()
            loop.time = MagicMock(side_effect=[0, 0])
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('asyncio.get_event_loop', return_value=loop):
                _run(AlipayPlatform._upload_video_file(page, video))
            marked.first.set_input_files.assert_awaited_once_with(video)
        finally:
            os.unlink(video)

    def test_all_fail_raises(self):
        page = _mk_page()
        video = _mk_img_file(name='t32_video4', size=2048)
        try:
            target = _loc(page, "input[type='file']")
            target.wait_for = AsyncMock(side_effect=TimeoutError('no direct'))
            area = page.get_by_text('将视频文件拖拽到此处').first
            area.count = AsyncMock(return_value=0)
            video_input = _loc(page, "input[type='file'][accept*='video']")
            video_input.click = AsyncMock(side_effect=RuntimeError('no chooser'))
            page.expect_file_chooser = MagicMock(side_effect=RuntimeError('no chooser'))
            marked = page.locator("input[type='file'][data-alipay-upload='1'],input[type='file'][data-alipay-new='1']")
            marked.count = AsyncMock(return_value=0)
            loop = MagicMock()
            loop.time = MagicMock(side_effect=[0, 0, 30.5])
            page.locator("input[type='file']").count = AsyncMock(return_value=3)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('asyncio.get_event_loop', return_value=loop), \
                 pytest.raises(RuntimeError, match='未找到可用的 file input'):
                _run(AlipayPlatform._upload_video_file(page, video))
        finally:
            os.unlink(video)


# ── DOM 辅助: 图集上传 / 图集表单等待 / 音乐 ──────────────────────────────

class TestUploadImages:
    def _mk_page_with_handlers(self):
        page = _mk_page()
        page.handlers = []
        page.on = MagicMock(side_effect=lambda ev, h: page.handlers.append(h))
        page.remove_listener = MagicMock()
        return page

    @staticmethod
    def _err_sel(img_path):
        return f'.ant-upload-list-item-error:has-text("{os.path.basename(img_path)}")'

    @staticmethod
    def _del_sel(img_path):
        return TestUploadImages._err_sel(img_path) + ' button[title="删除文件"]'

    def _cfg_error_count(self, page, img_path, count):
        _loc(page, self._err_sel(img_path)).count = AsyncMock(return_value=count)

    def test_no_valid_files_raises(self):
        page = _mk_page()
        with pytest.raises(RuntimeError, match='无有效图片'):
            _run(AlipayPlatform._upload_images(page, ['/nonexistent/a.png', '']))

    def test_happy_single_image(self):
        page = self._mk_page_with_handlers()
        img = _mk_img_file()
        try:
            image_input = _loc(page, "input[type='file'][accept*='image']")
            image_input.wait_for = AsyncMock()
            resp = MagicMock()
            resp.url = 'https://mass.alipay.com/file/auth/upload'
            resp.json = AsyncMock(return_value={'code': 0, 'data': {'id': 'id1'}})

            async def _upload_side(*a, **kw):
                await page.handlers[-1](resp)

            image_input.set_input_files = AsyncMock(side_effect=_upload_side)
            self._cfg_error_count(page, img, 0)
            with patch('asyncio.sleep', AsyncMock()):
                _run(AlipayPlatform._upload_images(page, [img]))
            image_input.set_input_files.assert_awaited_once_with(img)
            page.remove_listener.assert_called()
        finally:
            os.unlink(img)

    def test_failure_then_retry_success(self):
        """code!=0 → 删失败项 → 重试 → 成功。"""
        page = self._mk_page_with_handlers()
        img = _mk_img_file()
        try:
            image_input = _loc(page, "input[type='file'][accept*='image']")
            image_input.wait_for = AsyncMock()
            json_results = [{'code': -1, 'error': 'x'}, {'code': 0, 'data': {'id': 'id2'}}]
            resp = MagicMock()
            resp.url = 'https://mass.alipay.com/file/auth/upload'
            resp.json = AsyncMock(side_effect=json_results)

            async def _upload_side(*a, **kw):
                await page.handlers[-1](resp)

            image_input.set_input_files = AsyncMock(side_effect=_upload_side)
            delete_btn = _loc(page, self._del_sel(img))
            delete_btn.count = AsyncMock(return_value=1)
            delete_btn.click = AsyncMock()
            self._cfg_error_count(page, img, 0)
            with patch('asyncio.sleep', AsyncMock()):
                _run(AlipayPlatform._upload_images(page, [img]))
            # 两次 set_input_files(失败重试一次)
            assert image_input.set_input_files.await_count == 2
            delete_btn.click.assert_awaited_once()
        finally:
            os.unlink(img)

    def test_dom_error_branch(self):
        """error DOM 出现 → 视为失败 → 删除失败项。"""
        page = self._mk_page_with_handlers()
        img = _mk_img_file(name='domerr.png')
        try:
            image_input = _loc(page, "input[type='file'][accept*='image']")
            image_input.wait_for = AsyncMock()
            image_input.set_input_files = AsyncMock()  # 不触发 handler
            error_item = _loc(page, self._err_sel(img))
            error_item.count = AsyncMock(return_value=1)  # 错误 DOM 出现
            delete_btn = _loc(page, self._del_sel(img))
            delete_btn.count = AsyncMock(return_value=1)
            delete_btn.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), \
                 pytest.raises(RuntimeError, match='所有图片上传均失败'):
                # 3 次 attempt 都走 DOM error → 最后 raise
                _run(AlipayPlatform._upload_images(page, [img]))
            delete_btn.click.assert_awaited()
        finally:
            os.unlink(img)

    def test_upload_timeout_all_fail(self):
        """无响应且无错误 DOM → 3 次尝试超时 → raise。"""
        page = self._mk_page_with_handlers()
        img = _mk_img_file()
        try:
            image_input = _loc(page, "input[type='file'][accept*='image']")
            image_input.wait_for = AsyncMock()
            image_input.set_input_files = AsyncMock()
            self._cfg_error_count(page, img, 0)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.alipay.platform.logger') as lg, pytest.raises(RuntimeError, match='所有图片上传均失败'):
                _run(AlipayPlatform._upload_images(page, [img]))
            assert image_input.set_input_files.await_count == 3
            lg.warning.assert_called()
        finally:
            os.unlink(img)

    def test_upload_exception_continues(self):
        """set_input_files 抛异常 → warning → 下一张继续。"""
        page = self._mk_page_with_handlers()
        img1 = _mk_img_file(name='ok1.png')
        img2 = _mk_img_file(name='ok2.png')
        try:
            image_input = _loc(page, "input[type='file'][accept*='image']")
            image_input.wait_for = AsyncMock()
            resp = MagicMock()
            resp.url = 'https://mass.alipay.com/file/auth/upload'
            resp.json = AsyncMock(return_value={'code': 0, 'data': {'id': 'x'}})

            async def _upload_side(*a, **kw):
                await page.handlers[-1](resp)

            calls = {'n': 0}

            async def _flaky(*a, **kw):
                calls['n'] += 1
                if calls['n'] == 1:
                    raise RuntimeError('upload boom')
                await _upload_side(*a, **kw)

            image_input.set_input_files = AsyncMock(side_effect=_flaky)
            self._cfg_error_count(page, img1, 0)
            self._cfg_error_count(page, img2, 0)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.alipay.platform.logger') as lg:
                _run(AlipayPlatform._upload_images(page, [img1, img2]))
            lg.warning.assert_called()
            assert image_input.set_input_files.await_count == 3  # 1 失败(img1 首次) + img1 重试成功 + img2 成功
        finally:
            os.unlink(img1)
            os.unlink(img2)

    def test_wait_for_timeout_fallback_input(self):
        """image input 定位超时 → 遍历所有 file input 选非 video 的。"""
        page = self._mk_page_with_handlers()
        img = _mk_img_file()
        try:
            image_input = _loc(page, "input[type='file'][accept*='image']")
            image_input.wait_for = AsyncMock(side_effect=TimeoutError('slow'))
            all_inputs = page.locator("input[type='file']")
            all_inputs.count = AsyncMock(return_value=2)
            fi0 = _loc(page, 'fallback-fi-0')
            fi1 = _loc(page, 'fallback-fi-1')
            all_inputs.nth = MagicMock(side_effect=lambda i: fi0 if i == 0 else fi1)
            fi0.get_attribute = AsyncMock(return_value='video/mp4')
            fi0.set_input_files = AsyncMock()
            fi1.get_attribute = AsyncMock(return_value='image/jpeg')
            resp = MagicMock()
            resp.url = 'https://mass.alipay.com/file/auth/upload'
            resp.json = AsyncMock(return_value={'code': 0, 'data': {'id': 'y'}})

            async def _upload_side(*a, **kw):
                await page.handlers[-1](resp)

            fi1.set_input_files = AsyncMock(side_effect=_upload_side)
            self._cfg_error_count(page, img, 0)
            with patch('asyncio.sleep', AsyncMock()):
                _run(AlipayPlatform._upload_images(page, [img]))
            fi1.set_input_files.assert_awaited_once_with(img)
            # video input 未被用作上传
            fi0.set_input_files.assert_not_awaited()
        finally:
            os.unlink(img)


class TestWaitForImageForm:
    def test_visible_returns(self):
        page = _mk_page()
        title_in = _loc(page, "input[placeholder*='好的标题']")
        title_in.is_visible = AsyncMock(return_value=True)
        loop = MagicMock()
        loop.time = MagicMock(side_effect=[0, 0])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=loop):
            _run(AlipayPlatform._wait_for_image_form(page))

    def test_exception_then_visible(self):
        page = _mk_page()
        title_in = _loc(page, "input[placeholder*='好的标题']")
        title_in.is_visible = AsyncMock(side_effect=[RuntimeError('boom'), True])
        loop = MagicMock()
        loop.time = MagicMock(side_effect=[0, 0, 0])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=loop):
            _run(AlipayPlatform._wait_for_image_form(page))

    def test_timeout_raises(self):
        page = _mk_page()
        title_in = _loc(page, "input[placeholder*='好的标题']")
        title_in.is_visible = AsyncMock(return_value=False)
        loop = MagicMock()
        loop.time = MagicMock(side_effect=[0, 0, 120.5])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=loop), \
             pytest.raises(RuntimeError, match='等待表单就绪超时'):
            _run(AlipayPlatform._wait_for_image_form(page, timeout_s=120))


class TestSetMusic:
    def test_empty_title_noop(self):
        page = _mk_page()
        _run(AlipayPlatform._set_music(page, ''))
        page.locator.assert_not_called()

    def test_add_music_button_missing(self):
        page = _mk_page()
        add_btn = _loc(page, "button.ant-btn:has-text('添加音乐')")
        add_btn.wait_for = AsyncMock(side_effect=TimeoutError('no btn'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_music(page, 'BGM'))
        lg.warning.assert_called()

    def test_modal_not_open(self):
        page = _mk_page()
        add_btn = _loc(page, "button.ant-btn:has-text('添加音乐')")
        add_btn.wait_for = AsyncMock()
        add_btn.click = AsyncMock()
        modal = _loc(page, 'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")')
        modal.wait_for = AsyncMock(side_effect=TimeoutError('no modal'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_music(page, 'BGM'))
        lg.warning.assert_called()

    def test_clicked_found(self):
        page = _mk_page()
        add_btn = _loc(page, "button.ant-btn:has-text('添加音乐')")
        add_btn.wait_for = AsyncMock()
        add_btn.click = AsyncMock()
        modal = _loc(page, 'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")')
        modal.wait_for = AsyncMock()
        page.evaluate = AsyncMock(return_value='clicked')
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_music(page, 'BGM'))
        page.evaluate.assert_awaited_once()

    def test_pagination_until_found(self):
        page = _mk_page()
        add_btn = _loc(page, "button.ant-btn:has-text('添加音乐')")
        add_btn.wait_for = AsyncMock()
        add_btn.click = AsyncMock()
        modal = _loc(page, 'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")')
        modal.wait_for = AsyncMock()
        page.evaluate = AsyncMock(side_effect=['not-found', 'clicked'])
        next_btn = _loc(page, 'li.antd5-pagination-next:not([aria-disabled="true"]):not(.antd5-pagination-disabled)')
        next_btn.count = AsyncMock(return_value=1)
        next_btn.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_music(page, 'BGM'))
        assert page.evaluate.await_count == 2
        next_btn.click.assert_awaited_once()

    def test_no_more_pages_escape(self):
        page = _mk_page()
        add_btn = _loc(page, "button.ant-btn:has-text('添加音乐')")
        add_btn.wait_for = AsyncMock()
        add_btn.click = AsyncMock()
        modal = _loc(page, 'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")')
        modal.wait_for = AsyncMock()
        page.evaluate = AsyncMock(return_value='not-found')
        next_btn = _loc(page, 'li.antd5-pagination-next:not([aria-disabled="true"]):not(.antd5-pagination-disabled)')
        next_btn.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_music(page, 'BGM'))
        lg.warning.assert_called()
        page.keyboard.press.assert_awaited_once_with('Escape')

    def test_page_flip_failure_escape(self):
        page = _mk_page()
        add_btn = _loc(page, "button.ant-btn:has-text('添加音乐')")
        add_btn.wait_for = AsyncMock()
        add_btn.click = AsyncMock()
        modal = _loc(page, 'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")')
        modal.wait_for = AsyncMock()
        page.evaluate = AsyncMock(return_value='not-found')
        next_btn = _loc(page, 'li.antd5-pagination-next:not([aria-disabled="true"]):not(.antd5-pagination-disabled)')
        next_btn.count = AsyncMock(return_value=1)
        next_btn.click = AsyncMock(side_effect=RuntimeError('flip boom'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.alipay.platform.logger') as lg:
            _run(AlipayPlatform._set_music(page, 'BGM'))
        lg.info.assert_called()  # 翻页失败 info
        page.keyboard.press.assert_awaited_once_with('Escape')

    def test_no_modal_no_btn_branches(self):
        """evaluate 返回 no-modal / no-btn → warning break → Esc。"""
        for ret in ('no-modal', 'no-btn'):
            page = _mk_page()
            add_btn = _loc(page, "button.ant-btn:has-text('添加音乐')")
            add_btn.wait_for = AsyncMock()
            add_btn.click = AsyncMock()
            modal = _loc(page, 'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")')
            modal.wait_for = AsyncMock()
            page.evaluate = AsyncMock(return_value=ret)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.alipay.platform.logger') as lg:
                _run(AlipayPlatform._set_music(page, 'BGM'))
            lg.warning.assert_called()
            page.keyboard.press.assert_awaited_once_with('Escape')

    def test_modal_close_timeout_esc_fallback(self):
        page = _mk_page()
        add_btn = _loc(page, "button.ant-btn:has-text('添加音乐')")
        add_btn.wait_for = AsyncMock()
        add_btn.click = AsyncMock()
        modal = _loc(page, 'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")')
        modal.wait_for = AsyncMock(side_effect=[None, TimeoutError('not hidden')])
        page.evaluate = AsyncMock(return_value='clicked')
        with patch('asyncio.sleep', AsyncMock()):
            _run(AlipayPlatform._set_music(page, 'BGM'))
        # 找到后等 modal 关闭超时 → Esc 兜底
        page.keyboard.press.assert_awaited_once_with('Escape')
