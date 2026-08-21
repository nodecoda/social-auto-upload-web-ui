"""快手 platform.py DOM 交互层契约测试（T34）。

覆盖 publish_video/publish_image 编排层(T22)之外的深水区:
- 登录/校验/同步: login(QR 流程+URL 轮询) / check_cookie / sync_profile / open_creator_center
- 数据抓取: _scrape_kuaishou_stats / _login_stats_fn / _parse_cookie_to_storage_state
- 图集编排: publish_image / _upload_image_note 全流程(文件选择器/dry_run/正式发布)
- 单视频上传: _upload_single 全流程(文件选择器/上传轮询/发布循环)
- DOM 辅助: _close_guide_overlay / _input_tags(CDP 打字机) / _set_thumbnail(横竖比例)
  _set_image_cover / _set_image_music / _set_author_declaration(三策略) / _set_schedule_time
"""
import asyncio
import sys
import time as _time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from queue import Queue
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.kuaishou.platform import _DECLARATION_NONE, KuaishouPlatform


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return KuaishouPlatform()


def _mk_leaf():
    loc = MagicMock()
    loc.count = AsyncMock(return_value=0)
    loc.click = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.fill = AsyncMock()
    loc.set_input_files = AsyncMock()
    loc.evaluate = AsyncMock(return_value='')
    loc.hover = AsyncMock()
    loc.press = AsyncMock()
    loc.press_sequentially = AsyncMock()
    loc.is_visible = AsyncMock(return_value=True)
    loc.is_checked = AsyncMock(return_value=True)
    loc.inner_text = AsyncMock(return_value='')
    loc.text_content = AsyncMock(return_value='')
    loc.input_value = AsyncMock(return_value='')
    loc.get_attribute = AsyncMock(return_value='')
    loc.screenshot = AsyncMock(return_value=b'')
    loc.nth = MagicMock(side_effect=lambda i: _mk_leaf())
    loc.filter = MagicMock(side_effect=lambda **kw: _mk_leaf())
    loc.locator = MagicMock(side_effect=lambda sel, **kw: _mk_leaf())
    return loc


def _mk_locator():
    loc = _mk_leaf()
    loc.first = _mk_leaf()
    loc.last = _mk_leaf()
    return loc


def _sub_locators(owner):
    """给 owner.locator 挂 selector 分派, 返回 {selector: locator} 供断言。"""
    subs = {}

    def _reg(sel, **kw):
        if sel not in subs:
            subs[sel] = _mk_locator()
        return subs[sel]

    owner.locator = MagicMock(side_effect=_reg)
    return subs


class _FileChooserContext:
    """fake page.expect_file_chooser() 异步上下文,value 为 awaitable。"""

    def __init__(self, file_chooser):
        self._fc = file_chooser

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def value(self):
        async def _v():
            return self._fc
        return _v()


@contextmanager
def _mk_browser_chain(platform, urls=None):
    """create_browser/create_context 链 mocks(page 走 _mk_page 分派)。"""
    page = _mk_page(urls=urls)
    page.wait_for_url = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.eval_on_selector = AsyncMock(return_value='')
    page.input_value = AsyncMock()
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


def _mk_page(urls=None):
    """通用 fake page:locator 按 selector 分派,带默认 async 方法。"""
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
        page.url = 'https://cp.kuaishou.com/article/publish/video'
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.insert_text = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.evaluate = AsyncMock(return_value=[])
    page.on = MagicMock()
    page.main_frame = MagicMock()
    page.input_value = AsyncMock()
    page.click = AsyncMock()
    page.mouse = MagicMock()
    page.mouse.click = AsyncMock()
    page.context = MagicMock()
    locators = {}

    def locator(sel, **kw):
        if sel not in locators:
            locators[sel] = _mk_locator()
        return locators[sel]

    def get_by_text(text, exact=False):
        key = f'text:{text}'
        if key not in locators:
            locators[key] = _mk_locator()
        return locators[key]

    def get_by_role(role, name=None, exact=False):
        key = f'role:{role}:{name}'
        if key not in locators:
            locators[key] = _mk_locator()
        return locators[key]

    def get_by_placeholder(text):
        key = f'ph:{text}'
        if key not in locators:
            locators[key] = _mk_locator()
        return locators[key]

    page.locator = MagicMock(side_effect=locator)
    page.get_by_text = MagicMock(side_effect=get_by_text)
    page.get_by_role = MagicMock(side_effect=get_by_role)
    page.get_by_placeholder = MagicMock(side_effect=get_by_placeholder)
    page.locators = locators
    return page


def _loc(page, sel):
    """确保 selector 已注册,返回 .first。"""
    page.locator(sel)
    return page.locators[sel].first


def _mk_fc(page, files):
    """注册 file chooser:返回 (file_chooser, page.expect_file_chooser 已配置)。"""
    fc = MagicMock()
    fc.set_files = AsyncMock()
    page.expect_file_chooser = MagicMock(return_value=_FileChooserContext(fc))
    return fc


def _mk_cookie_file(name='t34_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


def _mk_img_file(name='t34_img.png', size=1024):
    import os as _os
    import tempfile as _tf
    fd, path = _tf.mkstemp(prefix=name, suffix='.png')
    with _os.fdopen(fd, 'wb') as f:
        f.write(b'x' * size)
    return path


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLoginAndCookie:
    def test_login_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, cb, cc), \
             patch('impl.kuaishou.platform.save_login_result', AsyncMock()) as slr, \
             patch('asyncio.sleep', AsyncMock()):
            login_btn = page.locator('button:has-text("立即登录"), a:has-text("立即登录")')
            login_btn.first.wait_for = AsyncMock()
            login_btn.first.click = AsyncMock()
            qrcode = page.locator('img[name="qrcode"], div.qr-login img[alt="qrcode"]')
            qrcode.first.wait_for = AsyncMock()
            _run(p.login('acc-1', Queue(), account_id='42'))
        cb.assert_awaited_once_with(login_mode=True)
        cc.assert_awaited_once_with(browser)
        page.goto.assert_awaited_once_with('https://cp.kuaishou.com')
        login_btn.first.click.assert_awaited_once()
        slr.assert_awaited_once()
        assert slr.await_args.kwargs['platform_id'] == 4
        assert slr.await_args.kwargs['account_id'] == '42'
        assert slr.await_args.kwargs['stats_fn'] == p._login_stats_fn
        browser.close.assert_awaited_once()

    def test_login_clicks_qr_tab(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.kuaishou.platform.save_login_result', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()):
            qr_tab = page.locator('text="扫码登录"')
            qr_tab.first.count = AsyncMock(return_value=1)
            qr_tab.first.is_visible = AsyncMock(return_value=True)
            qr_tab.first.click = AsyncMock()
            qrcode = page.locator('img[name="qrcode"], div.qr-login img[alt="qrcode"]')
            qrcode.first.wait_for = AsyncMock()
            _run(p.login('acc-1', Queue()))
        qr_tab.first.click.assert_awaited_once()

    def test_login_qr_expired_refresh(self):
        """URL 未变化 → 检测二维码过期 → 点刷新 → 直到 URL 匹配。"""
        p = _mk_platform()
        with _mk_browser_chain(p, urls=[
            'https://cp.kuaishou.com/',
            'https://cp.kuaishou.com/article/publish/video',
            'https://cp.kuaishou.com/article/publish/video',
        ]) as (page, _context, _browser, _cb, _cc), \
             patch('impl.kuaishou.platform.save_login_result', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()):
            expired = page.locator('div.qrcode-status.qrcode-status-timeout:visible')
            expired.first.count = AsyncMock(return_value=1)
            refresh_btn = page.locator('p.qrcode-refresh')
            refresh_btn.first.count = AsyncMock(return_value=1)
            refresh_btn.first.click = AsyncMock()
            qrcode = page.locator('img[name="qrcode"], div.qr-login img[alt="qrcode"]')
            qrcode.first.wait_for = AsyncMock()
            _run(p.login('acc-1', Queue()))
        refresh_btn.first.click.assert_awaited_once()

    def test_login_navigates_to_upload_if_needed(self):
        """登录成功 URL 是 profile 而非上传页 → goto 上传页再保存。"""
        p = _mk_platform()
        with _mk_browser_chain(p, urls=[
            'https://cp.kuaishou.com/profile',
            'https://cp.kuaishou.com/profile',
        ]) as (page, _context, _browser, _cb, _cc), \
             patch('impl.kuaishou.platform.save_login_result', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()):
            qrcode = page.locator('img[name="qrcode"], div.qr-login img[alt="qrcode"]')
            qrcode.first.wait_for = AsyncMock()
            _run(p.login('acc-1', Queue()))
        # 第一次 goto 是打开登录页,第二次是跳上传页
        assert page.goto.await_count == 2
        assert page.goto.await_args_list[1].args[0] == 'https://cp.kuaishou.com/article/publish/video'

    def test_login_error_puts_status(self):
        p = _mk_platform()
        q = Queue()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('asyncio.sleep', AsyncMock()):
            page.goto = AsyncMock(side_effect=RuntimeError('boom'))
            _run(p.login('acc-1', q))
        assert not q.empty()
        msg = q.get_nowait()
        assert '"status": "0"' in msg
        assert 'boom' in msg

    def test_check_cookie_invalid(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t34_cc_i.json')
        try:
            with _mk_browser_chain(p) as (page, context, browser, _cb, _cc):
                page.wait_for_selector = AsyncMock(return_value='found')
                result = _run(p.check_cookie(cookie.name))
            assert result is False
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_check_cookie_valid(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t34_cc_v.json')
        try:
            with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
                page.wait_for_selector = AsyncMock(side_effect=TimeoutError('none'))
                result = _run(p.check_cookie(cookie.name))
            assert result is True
        finally:
            cookie.unlink(missing_ok=True)

    def test_check_cookie_error_returns_false(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t34_cc_e.json')
        try:
            with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
                page.goto = AsyncMock(side_effect=RuntimeError('boom'))
                result = _run(p.check_cookie(cookie.name))
            assert result is False
        finally:
            cookie.unlink(missing_ok=True)


class TestSyncProfileAndStats:
    def test_sync_profile_happy(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t34_sp.json')
        try:
            with _mk_browser_chain(p) as (_page, context, browser, _cb, _cc), \
                 patch('impl.kuaishou.platform.scrape_user_profile',
                       AsyncMock(return_value=('昵称', 'http://a.png'))), \
                 patch.object(p, '_scrape_kuaishou_stats',
                              AsyncMock(return_value=[{'ICON': 'user', 'COUNT': 1}])):
                res = _run(p.sync_profile(cookie.name))
            assert res == {'name': '昵称', 'avatar': 'http://a.png',
                           'stats': [{'ICON': 'user', 'COUNT': 1}]}
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_sync_profile_error_fallback(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t34_sp2.json')
        try:
            with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
                page.goto = AsyncMock(side_effect=RuntimeError('boom'))
                res = _run(p.sync_profile(cookie.name))
            assert res == {'name': '', 'avatar': '', 'stats': []}
        finally:
            cookie.unlink(missing_ok=True)

    def test_scrape_stats_happy_sorted(self):
        p = _mk_platform()
        page = _mk_page()
        trigger = page.locator('.user-info-dpd')
        trigger.first.count = AsyncMock(return_value=1)
        trigger.first.click = AsyncMock()
        page.evaluate = AsyncMock(return_value=[
            {'label': '获赞', 'num': '125'},
            {'label': '粉丝', 'num': '25'},
            {'label': '关注', 'num': '7'},
        ])
        stats = _run(p._scrape_kuaishou_stats(page))
        assert [s['NAME'] for s in stats] == ['粉丝', '关注', '获赞']
        assert [s['SORT'] for s in stats] == [1, 2, 3]
        assert stats[0]['ICON'] == 'user' and stats[0]['COUNT'] == 25
        page.mouse.click.assert_awaited_once_with(10, 10)

    def test_scrape_stats_thousands_and_bad_num(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'label': '粉丝', 'num': '1,234'},
            {'label': '获赞', 'num': 'abc'},
            {'label': '未知', 'num': '99'},
        ])
        stats = _run(p._scrape_kuaishou_stats(page))
        # 未知 label 忽略;'abc' 解析失败 → count 0 仍追加;千分位归一
        assert stats == [
            {'ICON': 'user', 'COUNT': 1234, 'NAME': '粉丝', 'SORT': 1},
            {'ICON': 'like', 'COUNT': 0, 'NAME': '获赞', 'SORT': 3},
        ]

    def test_scrape_stats_trigger_missing_and_timeout(self):
        p = _mk_platform()
        page = _mk_page()
        page.locator('.user-info-dpd').first.count = AsyncMock(return_value=0)
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('none'))
        page.evaluate = AsyncMock(return_value=[{'label': '粉丝', 'num': '25'}])
        stats = _run(p._scrape_kuaishou_stats(page))
        assert len(stats) == 1
        page.mouse.click.assert_awaited_once()

    def test_scrape_stats_evaluate_error(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('js'))
        with patch('impl.kuaishou.platform.logger'):
            stats = _run(p._scrape_kuaishou_stats(page))
        assert stats == []

    def test_login_stats_fn_no_redirect(self):
        p = _mk_platform()
        page = _mk_page()
        page.url = 'https://cp.kuaishou.com/article/publish/video'
        with patch.object(p, '_scrape_kuaishou_stats', AsyncMock(return_value=[1])) as sc:
            res = _run(p._login_stats_fn(page, 'acc-1'))
        assert res == [1]
        page.goto.assert_not_awaited()
        sc.assert_awaited_once_with(page)

    def test_login_stats_fn_redirects(self):
        p = _mk_platform()
        page = _mk_page()
        page.url = 'https://cp.kuaishou.com/profile'
        with patch.object(p, '_scrape_kuaishou_stats', AsyncMock(return_value=[])):
            _run(p._login_stats_fn(page, 'acc-1'))
        assert page.goto.await_count == 1

    def test_login_stats_fn_error_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        page.url = 'https://cp.kuaishou.com/article/publish/video'
        with patch.object(p, '_scrape_kuaishou_stats',
                          AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('impl.kuaishou.platform.logger'):
            res = _run(p._login_stats_fn(page, 'acc-1'))
        assert res == []

    def test_parse_cookie_to_storage_state(self):
        p = _mk_platform()
        cookies, rest = p._parse_cookie_to_storage_state(
            'name1=value1; name2 =value2 ;; noequalsign'
        )
        assert len(cookies) == 2
        assert cookies[0]['name'] == 'name1' and cookies[0]['value'] == 'value1'
        assert cookies[0]['domain'] == '.kuaishou.com'
        assert cookies[1]['name'] == 'name2'
        assert rest == []

    def test_open_creator_center_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t34_occ.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.kuaishou.platform.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl.kuaishou.platform.create_context_sync', return_value=context) as ccs:
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            cbs.assert_called_once_with(headless=False)
            ccs.assert_called_once()
            page.goto.assert_called_once()
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_open_creator_center_wait_error_swallowed(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t34_occ2.json')
        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.kuaishou.platform.create_browser_sync', return_value=browser), \
                 patch('impl.kuaishou.platform.create_context_sync', return_value=context):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)


# ── 图集编排: publish_image / _upload_image_note ────────────────────────

class TestPublishImage:
    def test_tags_over_4_raises(self):
        p = _mk_platform()
        with pytest.raises(ValueError, match='标签最多 4 个'):
            _run(p.publish_image(
                title='T', files=['/i.png'], account_file=['a.json'],
                tags=['1', '2', '3', '4', '5'],
            ))

    def test_single_account_activities_appended(self):
        p = _mk_platform()
        with patch.object(p, '_upload_image_note', AsyncMock()) as uin, \
             patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value='号'):
            res = _run(p.publish_image(
                title='T', files=['/i.png'], tags=['x'], account_file=['ck.json'],
                desc='描述', activities=['A1', 'A2'], dry_run=False,
            ))
        assert res is True
        uin.assert_awaited_once()
        kw = uin.await_args.kwargs
        assert kw['desc'] == '描述 #A1 #A2'
        assert kw['account_file'].endswith('ck.json')
        assert kw['dry_run'] is False

    def test_multi_account_calls_each(self):
        p = _mk_platform()
        with patch.object(p, '_upload_image_note', AsyncMock()) as uin, \
             patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value=''):
            _run(p.publish_image(title='T', files=['/i.png'], tags=[], account_file=['a.json', 'b.json']))
        assert uin.await_count == 2

    def test_missing_cover_reset(self):
        p = _mk_platform()
        with patch.object(p, '_upload_image_note', AsyncMock()) as uin, \
             patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value=''):
            _run(p.publish_image(title='T', files=['/i.png'], tags=[], account_file=['ck.json'], cover_path='/no/such.png'))
        assert uin.await_args.kwargs['cover_path'] == ''

    def test_ai_content_alias(self):
        """ai_content 或 author_declaration 均可透传。"""
        p = _mk_platform()
        with patch.object(p, '_upload_image_note', AsyncMock()) as uin, \
             patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value=''):
            _run(p.publish_image(title='T', files=['/i.png'], tags=[], account_file=['ck.json'], ai_content='AI生成'))
        assert uin.await_args.kwargs['author_declaration'] == 'AI生成'


class TestUploadImageNote:
    def test_dry_run_happy(self):
        p = _mk_platform()
        imgs = [_mk_img_file('t34_n1.png'), _mk_img_file('t34_n2.png')]
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch.object(p, '_input_tags', AsyncMock()) as it:
            fc = _mk_fc(page, imgs)
            desc_editor = page.locator('#work-description-edit')
            desc_editor.first.wait_for = AsyncMock()
            desc_editor.first.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_image_note(
                    title='标题', file_paths=imgs, tags=['旅行'],
                    account_file='ck.json', desc='简介', dry_run=True,
                ))
            fc.set_files.assert_awaited_once_with(imgs)
            page.keyboard.type.assert_awaited()
            it.assert_awaited_once()
            assert it.await_args.kwargs['max_n'] == 4
            assert it.await_args.kwargs['element'] is not None
            # dry_run:不发布、不关 context/browser
            page.get_by_text('发布', exact=True).first.click.assert_not_awaited()
            context.close.assert_not_awaited()
            browser.close.assert_not_awaited()

    def test_publish_real_flow(self):
        p = _mk_platform()
        imgs = [_mk_img_file('t34_n3.png')]
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch.object(p, '_input_tags', AsyncMock()):
            _mk_fc(page, imgs)
            desc_editor = page.locator('#work-description-edit')
            desc_editor.first.wait_for = AsyncMock()
            desc_editor.first.click = AsyncMock()
            publish_btn = page.get_by_text('发布', exact=True)
            publish_btn.first.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_image_note(
                    title='T', file_paths=imgs, tags=[], account_file='ck.json',
                    dry_run=False,
                ))
            publish_btn.first.click.assert_awaited_once()
            page.wait_for_url.assert_awaited()
            context.storage_state.assert_awaited_once_with(path='ck.json')
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()

    def test_all_optional_helpers(self):
        p = _mk_platform()
        imgs = [_mk_img_file('t34_n4.png')]
        for name in ('_set_image_cover', '_set_image_music', '_set_author_declaration',
                     '_set_schedule_time'):
            setattr(p, name, AsyncMock())
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch.object(p, '_input_tags', AsyncMock()):
            _mk_fc(page, imgs)
            desc_editor = page.locator('#work-description-edit')
            desc_editor.first.wait_for = AsyncMock()
            desc_editor.first.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_image_note(
                    title='T', file_paths=imgs, tags=[], account_file='ck.json',
                    cover_path='/v/cover.png', music_id='m1', music_title='歌',
                    author_declaration='AI生成', enable_timer=True,
                    schedule_time_str='2026-08-25 14:30', dry_run=True,
                ))
            p._set_image_cover.assert_awaited_once()
            p._set_image_music.assert_awaited_once()
            p._set_author_declaration.assert_awaited_once()
            p._set_schedule_time.assert_awaited_once()

    def test_declaration_none_skips(self):
        p = _mk_platform()
        imgs = [_mk_img_file('t34_n5.png')]
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch.object(p, '_input_tags', AsyncMock()), \
             patch.object(p, '_set_author_declaration', AsyncMock()) as sad:
            _mk_fc(page, imgs)
            desc_editor = page.locator('#work-description-edit')
            desc_editor.first.wait_for = AsyncMock()
            desc_editor.first.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_image_note(
                    title='T', file_paths=imgs, tags=[], account_file='ck.json',
                    author_declaration=_DECLARATION_NONE, dry_run=True,
                ))
            sad.assert_not_awaited()

    def test_expect_file_chooser_closes_context_on_error(self):
        """file_chooser 设置失败 → 非 dry_run 下 context/browser 仍关闭。"""
        p = _mk_platform()
        imgs = [_mk_img_file('t34_n6.png')]
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch.object(p, '_input_tags', AsyncMock()):
            fc = _mk_fc(page, imgs)
            fc.set_files = AsyncMock(side_effect=RuntimeError('no chooser'))
            desc_editor = page.locator('#work-description-edit')
            desc_editor.first.wait_for = AsyncMock()
            desc_editor.first.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), pytest.raises(RuntimeError, match='no chooser'):
                _run(p._upload_image_note(
                    title='T', file_paths=imgs, tags=[], account_file='ck.json',
                    dry_run=False,
                ))
            # 异常冒泡但资源清理仍执行
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()


# ── 单视频上传: _upload_single ──────────────────────────────────────────

class TestUploadSingle:
    def _mk(self, p, page, video_path='/v/a.mp4', thumbnail='/v/cover.png'):
        fc = _mk_fc(page, [video_path])
        know_btn = page.locator('button[type="button"] span:text("我知道了")')
        know_btn.first.count = AsyncMock(return_value=0)
        desc_label = page.get_by_text('描述')
        desc_label.locator = MagicMock(side_effect=lambda sel, **kw: (
            MagicMock(click=AsyncMock()) if sel == 'xpath=following-sibling::div' else MagicMock()))
        uploading = page.locator('text=上传中')
        upload_fail = page.locator('text=上传失败')
        return fc, uploading, upload_fail

    def test_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             patch.object(p, '_close_guide_overlay', AsyncMock()) as cgo, \
             patch.object(p, '_input_tags', AsyncMock()) as it, \
             patch.object(p, '_set_thumbnail', AsyncMock()) as st, \
             patch.object(p, '_set_author_declaration', AsyncMock()) as sad, \
             patch('impl.kuaishou.platform.clear_and_type', AsyncMock()) as cat:
            fc, uploading, _fail = self._mk(p, page)
            uploading.count = AsyncMock(return_value=0)  # 无「上传中」→ 立即成功
            publish_btn = page.get_by_text('发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            confirm_btn = page.get_by_text('确认发布')
            confirm_btn.count = AsyncMock(return_value=0)
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_single(
                    video_path='/v/a.mp4', cookie_path='ck.json', title='T',
                    desc='简介', tags=['a'], thumbnail_path='/v/cover.png',
                    author_declaration='AI生成', publish_date=0, enable_timer=False,
                ))
            fc.set_files.assert_awaited_once_with('/v/a.mp4')
            cat.assert_awaited_once()
            page.keyboard.press.assert_any_await('Enter')
            it.assert_awaited_once()
            cgo.assert_awaited_once()
            st.assert_awaited_once()
            sad.assert_awaited_once()
            publish_btn.click.assert_awaited()
            page.wait_for_url.assert_awaited()
            context.storage_state.assert_awaited_once_with(path='ck.json')
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()

    def test_upload_retry_on_failure(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch.object(p, '_close_guide_overlay', AsyncMock()), \
             patch.object(p, '_input_tags', AsyncMock()), \
             patch.object(p, '_set_thumbnail', AsyncMock()), \
             patch('impl.kuaishou.platform.clear_and_type', AsyncMock()), \
             patch('impl.kuaishou.platform.logger') as lg:
            _fc, uploading, fail = self._mk(p, page)
            uploading.count = AsyncMock(side_effect=[1, 0])  # 第一轮上传中
            fail.count = AsyncMock(return_value=1)
            retry_input = page.locator('div.progress-div [class^="upload-btn-input"]')
            retry_input.set_input_files = AsyncMock()
            publish_btn = page.get_by_text('发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            confirm_btn = page.get_by_text('确认发布')
            confirm_btn.count = AsyncMock(return_value=0)
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_single(
                    video_path='/v/a.mp4', cookie_path='ck.json', title='T',
                    desc='', tags=[], thumbnail_path=None,
                    author_declaration='', publish_date=0, enable_timer=False,
                ))
            retry_input.set_input_files.assert_awaited_once_with('/v/a.mp4')
            assert any('上传失败' in str(c) for c in lg.info.call_args_list)

    def test_publish_retry_loop(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             patch.object(p, '_close_guide_overlay', AsyncMock()), \
             patch.object(p, '_input_tags', AsyncMock()), \
             patch.object(p, '_set_thumbnail', AsyncMock()), \
             patch('impl.kuaishou.platform.clear_and_type', AsyncMock()):
            _fc, uploading, _fail = self._mk(p, page)
            uploading.count = AsyncMock(return_value=0)
            publish_btn = page.get_by_text('发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            confirm_btn = page.get_by_text('确认发布')
            confirm_btn.count = AsyncMock(return_value=0)
            # 第 1 次 wait_for_url 是 goto 后的 _KS_UPLOAD_URL_PATTERN(消耗 1 次);
            # 之后发布循环 5 次失败 → 重试,最后 1 次成功
            page.wait_for_url = AsyncMock(side_effect=[None] + [TimeoutError('slow')] * 5 + [None])
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.kuaishou.platform.logger'):
                _run(p._upload_single(
                    video_path='/v/a.mp4', cookie_path='ck.json', title='T',
                    desc='', tags=[], thumbnail_path=None,
                    author_declaration='', publish_date=0, enable_timer=False,
                ))
            assert publish_btn.click.await_count >= 5
            context.storage_state.assert_awaited_once()

    def test_confirm_publish_clicked(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch.object(p, '_close_guide_overlay', AsyncMock()), \
             patch.object(p, '_input_tags', AsyncMock()), \
             patch.object(p, '_set_thumbnail', AsyncMock()), \
             patch('impl.kuaishou.platform.clear_and_type', AsyncMock()):
            _fc, uploading, _fail = self._mk(p, page)
            uploading.count = AsyncMock(return_value=0)
            publish_btn = page.get_by_text('发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            confirm_btn = page.get_by_text('确认发布')
            confirm_btn.count = AsyncMock(return_value=1)
            confirm_btn.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.kuaishou.platform.logger'):
                _run(p._upload_single(
                    video_path='/v/a.mp4', cookie_path='ck.json', title='T',
                    desc='', tags=[], thumbnail_path=None,
                    author_declaration='', publish_date=0, enable_timer=False,
                ))
            confirm_btn.click.assert_awaited()

    def test_know_btn_dismissed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch.object(p, '_close_guide_overlay', AsyncMock()), \
             patch.object(p, '_input_tags', AsyncMock()), \
             patch.object(p, '_set_thumbnail', AsyncMock()), \
             patch('impl.kuaishou.platform.clear_and_type', AsyncMock()):
            _fc, uploading, _fail = self._mk(p, page)
            uploading.count = AsyncMock(return_value=0)
            know_btn = page.locator('button[type="button"] span:text("我知道了")')
            know_btn.first.count = AsyncMock(return_value=1)
            know_btn.first.is_visible = AsyncMock(return_value=True)
            know_btn.first.click = AsyncMock()
            publish_btn = page.get_by_text('发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            confirm_btn = page.get_by_text('确认发布')
            confirm_btn.count = AsyncMock(return_value=0)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.kuaishou.platform.logger'):
                _run(p._upload_single(
                    video_path='/v/a.mp4', cookie_path='ck.json', title='T',
                    desc='', tags=[], thumbnail_path=None,
                    author_declaration='', publish_date=0, enable_timer=False,
                ))
            know_btn.first.click.assert_awaited_once()

    def test_schedule_and_declaration_none(self):
        """定时 + 声明 NONE:schedule 被调用,declaration 跳过。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch.object(p, '_close_guide_overlay', AsyncMock()), \
             patch.object(p, '_input_tags', AsyncMock()), \
             patch.object(p, '_set_thumbnail', AsyncMock()), \
             patch.object(p, '_set_author_declaration', AsyncMock()) as sad, \
             patch.object(p, '_set_schedule_time', AsyncMock()) as sst, \
             patch('impl.kuaishou.platform.clear_and_type', AsyncMock()):
            _fc, uploading, _fail = self._mk(p, page)
            uploading.count = AsyncMock(return_value=0)
            publish_btn = page.get_by_text('发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            confirm_btn = page.get_by_text('确认发布')
            confirm_btn.count = AsyncMock(return_value=0)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.kuaishou.platform.logger'):
                _run(p._upload_single(
                    video_path='/v/a.mp4', cookie_path='ck.json', title='T',
                    desc='', tags=[], thumbnail_path=None,
                    author_declaration=_DECLARATION_NONE,
                    publish_date=1730000000, enable_timer=True,
                ))
            sad.assert_not_awaited()
            sst.assert_awaited_once()


# ── 引导弹层: _close_guide_overlay ──────────────────────────────────────

class TestCloseGuideOverlay:
    def test_new_dom_skip(self):
        p = _mk_platform()
        page = _mk_page()
        tooltip = page.locator('div[role="alertdialog"]:visible')
        tooltip.count = AsyncMock(return_value=1)
        # 代码取 tooltip.locator(...).first;leaf.locator() 默认返回 fresh leaf,
        # 必须让 tooltip.locator 返回固定对象,并在该对象上配 .first
        close_btn = MagicMock()
        close_btn.first.count = AsyncMock(return_value=1)
        close_btn.first.click = AsyncMock()
        tooltip.locator = MagicMock(return_value=close_btn)
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._close_guide_overlay(page))
        close_btn.first.click.assert_awaited_once_with(force=True)

    def test_old_joyride_dom(self):
        p = _mk_platform()
        page = _mk_page()
        page.locator('div[role="alertdialog"]:visible').count = AsyncMock(return_value=0)
        joyride = page.locator('div[id^="react-joyride-step"] div[role="alertdialog"]')
        joyride.count = AsyncMock(return_value=1)
        joyride.first.is_visible = AsyncMock(return_value=True)
        alertdialog = page.locator('div[role="alertdialog"]')
        # leaf.locator() 返回 fresh leaf,用固定对象承接 close_btn
        close_btn = MagicMock()
        close_btn.click = AsyncMock()
        alertdialog.locator = MagicMock(return_value=close_btn)
        joyride.wait_for = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._close_guide_overlay(page))
        close_btn.click.assert_awaited_once_with(force=True)
        joyride.wait_for.assert_awaited_once_with(state='hidden', timeout=5000)

    def test_no_overlay(self):
        p = _mk_platform()
        page = _mk_page()
        page.locator('div[role="alertdialog"]:visible').count = AsyncMock(return_value=0)
        page.locator('div[id^="react-joyride-step"] div[role="alertdialog"]').count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._close_guide_overlay(page))
        # 无异常即通过


# ── 标签输入: _input_tags(CDP 打字机) ───────────────────────────────────

class TestInputTags:
    def test_empty_tags_returns(self):
        p = _mk_platform()
        page = _mk_page()
        _run(p._input_tags(page, [], max_n=4))
        page.context.new_cdp_session.assert_not_called()

    def test_happy_path_with_element(self):
        p = _mk_platform()
        page = _mk_page()
        cdp = MagicMock()
        cdp.send = AsyncMock()
        page.context.new_cdp_session = AsyncMock(return_value=cdp)
        element = MagicMock()
        element.press_sequentially = AsyncMock()
        dropdown = page.locator('div[class*="_dropdown-container_"]')
        dropdown.first.wait_for = AsyncMock()
        active = page.locator('div[class*="_topic-item_"][class*="_active_"]')
        active.first.count = AsyncMock(return_value=1)
        active.first.is_visible = AsyncMock(return_value=True)
        tag_name_el = active.first.locator('span[class*="_at-tag-name_"]')
        tag_name_el.first.text_content = AsyncMock(return_value='旅行')
        active.first.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._input_tags(page, ['旅行', '美食'], max_n=4, element=element))
        # 每个 tag: keyDown + keyUp
        assert cdp.send.await_count == 4
        element.press_sequentially.assert_awaited()
        assert element.press_sequentially.await_count == 2
        active.first.click.assert_awaited()
        page.keyboard.press.assert_not_awaited()  # 全部命中下拉,无空格兜底

    def test_space_fallback_no_dropdown(self):
        p = _mk_platform()
        page = _mk_page()
        cdp = MagicMock()
        cdp.send = AsyncMock()
        page.context.new_cdp_session = AsyncMock(return_value=cdp)
        dropdown = page.locator('div[class*="_dropdown-container_"]')
        dropdown.first.wait_for = AsyncMock(side_effect=TimeoutError('none'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._input_tags(page, ['旅行'], max_n=4))
        page.keyboard.press.assert_awaited_once_with('Space')

    def test_keyboard_type_without_element(self):
        p = _mk_platform()
        page = _mk_page()
        cdp = MagicMock()
        cdp.send = AsyncMock()
        page.context.new_cdp_session = AsyncMock(return_value=cdp)
        page.keyboard.type = AsyncMock()
        dropdown = page.locator('div[class*="_dropdown-container_"]')
        dropdown.first.wait_for = AsyncMock(side_effect=TimeoutError('none'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._input_tags(page, ['旅行'], max_n=4))
        page.keyboard.type.assert_awaited_once_with('旅行', delay=150)

    def test_active_not_visible_falls_back(self):
        p = _mk_platform()
        page = _mk_page()
        cdp = MagicMock()
        cdp.send = AsyncMock()
        page.context.new_cdp_session = AsyncMock(return_value=cdp)
        dropdown = page.locator('div[class*="_dropdown-container_"]')
        dropdown.first.wait_for = AsyncMock()
        active = page.locator('div[class*="_topic-item_"][class*="_active_"]')
        active.first.count = AsyncMock(return_value=1)
        active.first.is_visible = AsyncMock(return_value=False)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._input_tags(page, ['旅行'], max_n=4))
        page.keyboard.press.assert_awaited_once_with('Space')


# ── 封面设置: _set_thumbnail(悬停→弹窗→上传封面 tab→裁剪比例→上传→确认) ─

class TestSetThumbnail:
    def _mk_modal(self, page, ratio='4:3'):
        """构造封面弹窗子分派, 返回 (modal, subs, ratio_item, file_input, confirm_btn)。"""
        modal = page.locator('div[role="document"].ant-modal:visible')
        modal.wait_for = AsyncMock()
        subs = _sub_locators(modal)
        # 预注册: 先调用 owner.locator(sel) 触发登记, 再读取 subs
        upload_sel = "div[class*='header-title-item']"
        modal.locator(upload_sel)
        upload_tab = _mk_leaf()
        upload_tab.wait_for = AsyncMock()
        upload_tab.click = AsyncMock()
        subs[upload_sel].nth = MagicMock(return_value=upload_tab)  # .nth 每次 fresh, 覆盖为固定对象
        ratio_sel = f"div[class*='_ratio-item']:has(span:text-is('{ratio}'))"
        modal.locator(ratio_sel)
        ratio_item = subs[ratio_sel].first
        ratio_item.wait_for = AsyncMock()
        ratio_item.get_attribute = AsyncMock(return_value='_ratio-item')
        ratio_item.click = AsyncMock()
        modal.locator("input[type='file']")
        file_input = subs["input[type='file']"]
        file_input.wait_for = AsyncMock()
        file_input.set_input_files = AsyncMock()
        confirm_sel = "button:has-text('确认'), button:has-text('完成')"
        modal.locator(confirm_sel)
        confirm_btn = subs[confirm_sel].first
        confirm_btn.wait_for = AsyncMock()
        confirm_btn.click = AsyncMock()
        return modal, subs, ratio_item, file_input, confirm_btn

    def _mk_page_ctx(self, page):
        cover_area = page.locator("div[class*='default-cover']").first
        cover_area.hover = AsyncMock()
        cover_editor = page.locator("div[class*='cover-full-editor']").first
        cover_editor.wait_for = AsyncMock()
        cover_editor.click = AsyncMock()
        return cover_area, cover_editor

    def test_landscape_ratio_4_3(self):
        p = _mk_platform()
        page = _mk_page()
        cover_area, cover_editor = self._mk_page_ctx(page)
        modal, _subs, ratio_item, file_input, confirm_btn = self._mk_modal(page, '4:3')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_thumbnail(page, '/i/cover.png', 'landscape'))
        cover_area.hover.assert_awaited_once()
        cover_editor.click.assert_awaited_once()
        ratio_item.click.assert_awaited_once()
        file_input.set_input_files.assert_awaited_once_with('/i/cover.png')
        confirm_btn.click.assert_awaited_once()
        modal.wait_for.assert_awaited_with(state='hidden', timeout=30000)

    def test_portrait_ratio_3_4(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_page_ctx(page)
        _modal, _subs, ratio_item, file_input, _confirm = self._mk_modal(page, '3:4')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_thumbnail(page, '/i/cover.png', 'portrait'))
        ratio_item.click.assert_awaited_once()
        file_input.set_input_files.assert_awaited_once()

    def test_ratio_active_skips_click(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_page_ctx(page)
        _modal, _subs, ratio_item, file_input, _confirm = self._mk_modal(page, '4:3')
        ratio_item.get_attribute = AsyncMock(return_value='_ratio-item _active')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_thumbnail(page, '/i/cover.png', 'landscape'))
        ratio_item.click.assert_not_awaited()
        file_input.set_input_files.assert_awaited_once()

    def test_ratio_failure_non_blocking(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_page_ctx(page)
        _modal, _subs, ratio_item, file_input, confirm_btn = self._mk_modal(page, '4:3')
        ratio_item.wait_for = AsyncMock(side_effect=TimeoutError('no ratio option'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_thumbnail(page, '/i/cover.png', 'landscape'))
        ratio_item.click.assert_not_awaited()
        file_input.set_input_files.assert_awaited_once()
        confirm_btn.click.assert_awaited_once()

    def test_hover_failure_is_non_fatal(self):
        p = _mk_platform()
        page = _mk_page()
        cover_area, _cover_editor = self._mk_page_ctx(page)
        cover_area.hover = AsyncMock(side_effect=TimeoutError('hover failed'))
        modal = page.locator('div[role="document"].ant-modal:visible')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_thumbnail(page, '/i/cover.png', 'landscape'))
        modal.wait_for.assert_not_awaited()


# ── 图集封面: _set_image_cover ─────────────────────────────────────────

class TestSetImageCover:
    def test_happy_path(self):
        p = _mk_platform()
        page = _mk_page()
        edit_btn = page.get_by_text('编辑封面', exact=True)
        edit_btn.wait_for = AsyncMock()
        edit_btn.click = AsyncMock()
        modal = page.locator('div[role="document"].ant-modal:visible')
        modal.wait_for = AsyncMock()
        subs = _sub_locators(modal)
        upload_sel = "div[class*='header-title-item']"
        modal.locator(upload_sel)
        upload_tab = _mk_leaf()
        upload_tab.wait_for = AsyncMock()
        upload_tab.click = AsyncMock()
        subs[upload_sel].nth = MagicMock(return_value=upload_tab)
        modal.locator("input[type='file']")
        file_input = subs["input[type='file']"]
        file_input.wait_for = AsyncMock()
        file_input.set_input_files = AsyncMock()
        confirm_sel = "button:has-text('确认'), button:has-text('完成')"
        modal.locator(confirm_sel)
        confirm_btn = subs[confirm_sel].first
        confirm_btn.wait_for = AsyncMock()
        confirm_btn.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_image_cover(page, '/i/note.png'))
        edit_btn.click.assert_awaited_once()
        upload_tab.click.assert_awaited_once()
        file_input.set_input_files.assert_awaited_once_with('/i/note.png')
        confirm_btn.click.assert_awaited_once()
        modal.wait_for.assert_awaited_with(state='hidden', timeout=30000)

    def test_edit_btn_failure_non_fatal(self):
        p = _mk_platform()
        page = _mk_page()
        edit_btn = page.get_by_text('编辑封面', exact=True)
        edit_btn.wait_for = AsyncMock(side_effect=TimeoutError('no edit btn'))
        modal = page.locator('div[role="document"].ant-modal:visible')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_image_cover(page, '/i/note.png'))
        modal.wait_for.assert_not_awaited()


# ── 图集音乐: _set_image_music(抽屉搜索→精确/兜底→添加) ────────────────

class TestSetImageMusic:
    def _mk_drawer(self, page):
        text_div = page.locator("div:text-is('添加音乐')").first
        text_div.wait_for = AsyncMock()
        drawer = page.locator('div.ant-drawer-content-wrapper:visible').first
        drawer.wait_for = AsyncMock()
        subs = _sub_locators(drawer)
        search_sel = "input[placeholder='搜索音乐']"
        drawer.locator(search_sel)
        search_input = subs[search_sel].first
        search_input.click = AsyncMock()
        return drawer, subs

    def test_exact_title_match(self):
        p = _mk_platform()
        page = _mk_page()
        _drawer, subs = self._mk_drawer(page)
        title_sel = "div:text-is('我的歌')"
        _drawer.locator(title_sel)
        title_div = subs[title_sel].first
        title_div.count = AsyncMock(return_value=1)
        ancestor = MagicMock()
        ancestor.count = AsyncMock(return_value=1)
        inner = MagicMock()
        inner.last.click = AsyncMock()
        ancestor.locator = MagicMock(return_value=inner)
        title_div.locator = MagicMock(return_value=ancestor)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_image_music(page, 'm1', music_title='我的歌'))
        page.keyboard.type.assert_awaited_once_with('我的歌')
        inner.last.click.assert_awaited_once_with(force=True)

    def test_fallback_first_card(self):
        p = _mk_platform()
        page = _mk_page()
        _drawer, subs = self._mk_drawer(page)
        all_sel = "div[class*='item'], div[class*='card']"
        _drawer.locator(all_sel)
        all_cards = subs[all_sel]
        all_cards.count = AsyncMock(return_value=1)
        # target_card = all_cards.first 后代码还会 await target_card.count()
        all_cards.first.count = AsyncMock(return_value=1)
        inner = MagicMock()
        inner.last.click = AsyncMock()
        all_cards.first.locator = MagicMock(return_value=inner)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_image_music(page, 'm1', music_title=''))
        page.keyboard.type.assert_awaited_once_with('m1')
        inner.last.click.assert_awaited_once_with(force=True)

    def test_no_card_closes_drawer(self):
        p = _mk_platform()
        page = _mk_page()
        _drawer, subs = self._mk_drawer(page)
        all_sel = "div[class*='item'], div[class*='card']"
        _drawer.locator(all_sel)
        all_cards = subs[all_sel]
        all_cards.count = AsyncMock(return_value=0)
        close_btn = page.locator('div.ant-drawer-close').first
        close_btn.count = AsyncMock(return_value=1)
        close_btn.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_image_music(page, 'm1', music_title=''))
        close_btn.click.assert_awaited_once_with(force=True)


# ── 作者声明: _set_author_declaration(三策略 + 无匹配收起) ───────────────

class TestSetAuthorDeclaration:
    def test_none_skips(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.kuaishou.platform.logger'):
            _run(p._set_author_declaration(page, _DECLARATION_NONE))
        page.locator.assert_not_called()

    def test_empty_skips(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.kuaishou.platform.logger'):
            _run(p._set_author_declaration(page, ''))
        page.locator.assert_not_called()

    def test_strategy1_label_sibling(self):
        p = _mk_platform()
        page = _mk_page()
        label = page.locator("label:has-text('作者声明')")
        label.count = AsyncMock(return_value=1)
        wrapper = MagicMock()
        wrapper.first.count = AsyncMock(return_value=1)
        wrapper.first.click = AsyncMock()
        label.locator = MagicMock(return_value=wrapper)
        option = page.locator("div.ant-select-item-option:has-text('AI生成')").first
        option.count = AsyncMock(return_value=1)
        option.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_author_declaration(page, 'AI生成'))
        wrapper.first.click.assert_awaited_once()
        option.click.assert_awaited_once()
        page.keyboard.press.assert_not_awaited()

    def test_strategy2_placeholder_span(self):
        p = _mk_platform()
        page = _mk_page()
        ph_span = page.locator("span.ant-select-selection-placeholder:has-text('为作品添加补充说明')")
        ph_span.count = AsyncMock(return_value=1)
        wrapper = MagicMock()
        wrapper.first.count = AsyncMock(return_value=1)
        wrapper.first.click = AsyncMock()
        ph_span.locator = MagicMock(return_value=wrapper)
        option = page.locator("div.ant-select-item-option:has-text('AI生成')").first
        option.count = AsyncMock(return_value=1)
        option.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_author_declaration(page, 'AI生成'))
        wrapper.first.click.assert_awaited_once()
        option.click.assert_awaited_once()

    def test_strategy3_input_placeholder(self):
        p = _mk_platform()
        page = _mk_page()
        decl_input = page.locator("input[placeholder*='为作品添加补充说明']")
        decl_input.count = AsyncMock(return_value=1)
        wrapper = MagicMock()
        wrapper.first.count = AsyncMock(return_value=1)
        wrapper.first.click = AsyncMock()
        decl_input.locator = MagicMock(return_value=wrapper)
        option = page.locator("div.ant-select-item-option:has-text('AI生成')").first
        option.count = AsyncMock(return_value=1)
        option.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_author_declaration(page, 'AI生成'))
        wrapper.first.click.assert_awaited_once()
        option.click.assert_awaited_once()

    def test_no_match_option_escapes_and_skips(self):
        p = _mk_platform()
        page = _mk_page()
        label = page.locator("label:has-text('作者声明')")
        label.count = AsyncMock(return_value=1)
        wrapper = MagicMock()
        wrapper.first.count = AsyncMock(return_value=1)
        wrapper.first.click = AsyncMock()
        label.locator = MagicMock(return_value=wrapper)
        option = page.locator("div.ant-select-item-option:has-text('AI生成')").first
        option.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_author_declaration(page, 'AI生成'))
        wrapper.first.click.assert_awaited_once()
        page.keyboard.press.assert_awaited_once_with('Escape')
        option.click.assert_not_awaited()

    def test_no_select_found_skips(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_author_declaration(page, 'AI生成'))
        page.keyboard.press.assert_not_awaited()


# ── 定时发布: _set_schedule_time(radio + ant-picker) ───────────────────

class TestSetScheduleTime:
    def test_happy_path(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.kuaishou.platform.clear_and_type', AsyncMock()) as cat, \
             patch('impl.kuaishou.platform.logger'):
            _run(p._set_schedule_time(page, datetime(2026, 8, 25, 12, 30, 0, tzinfo=UTC)))
        # 链路: label:text('发布时间') → 兄弟 div → .ant-radio-input.nth(1).click()
        page.locator.assert_any_call("label:text('发布时间')")
        page.locator.assert_any_call('div.ant-picker-input input[placeholder="选择日期时间"]')
        page.keyboard.press.assert_awaited_once_with('Enter')
        cat.assert_awaited_once_with(page, '2026-08-25 12:30:00')


# ── 视频编排边界: _publish_video_async(封面优先级/标签上限/多文件多账号) ──

class TestPublishVideoAsync:
    def _base_patches(self, p, dates):
        return [
            patch.object(p, '_upload_single', AsyncMock()),
            patch('impl.kuaishou.platform.parse_schedule_time', return_value=dates),
            patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value='号'),
            patch('impl.kuaishou.platform.logger'),
        ]

    def test_cover_priority_and_ai_content(self):
        """封面优先级: 竖版 > 横版 > 通用;ai_content 透传为 author_declaration。"""
        p = _mk_platform()
        with patch.object(p, '_upload_single', AsyncMock()) as us, \
             patch('impl.kuaishou.platform.parse_schedule_time', return_value=[]), \
             patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value='号'), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._publish_video_async(
                title='T', files=['/v/a.mp4'], account_file=['ck.json'], tags=['x'],
                thumbnail_portrait_path='/p.png', thumbnail_landscape_path='/l.png',
                thumbnail_path='/g.png', video_format='portrait', ai_content='AI生成',
            ))
        us.assert_awaited_once()
        kw = us.await_args.kwargs
        assert kw['thumbnail_path'] == '/p.png'      # 竖版优先
        assert kw['video_format'] == 'portrait'
        assert kw['author_declaration'] == 'AI生成'

    def test_landscape_fallback_when_no_portrait(self):
        p = _mk_platform()
        with patch.object(p, '_upload_single', AsyncMock()) as us, \
             patch('impl.kuaishou.platform.parse_schedule_time', return_value=[]), \
             patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value='号'), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._publish_video_async(
                title='T', files=['/v/a.mp4'], account_file=['ck.json'], tags=[],
                thumbnail_landscape_path='/l.png', thumbnail_path='/g.png',
            ))
        assert us.await_args.kwargs['thumbnail_path'] == '/l.png'

    def test_tags_over_4_raises(self):
        p = _mk_platform()
        with pytest.raises(ValueError, match='标签最多 4 个'):
            _run(p._publish_video_async(
                title='T', files=['/v/a.mp4'], account_file=['ck.json'],
                tags=['1', '2', '3', '4', '5'],
            ))

    def test_multi_file_multi_account_dates(self):
        """2 文件 × 2 账号 → 4 次 _upload_single;每个文件用对应 publish_date。"""
        p = _mk_platform()
        dates = [datetime(2026, 8, 25, 10, 0, tzinfo=UTC), datetime(2026, 8, 26, 10, 0, tzinfo=UTC)]
        with patch.object(p, '_upload_single', AsyncMock()) as us, \
             patch('impl.kuaishou.platform.parse_schedule_time', return_value=dates), \
             patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value='号'), \
             patch('impl.kuaishou.platform.logger'):
            _run(p._publish_video_async(
                title='T', files=['/v/a.mp4', '/v/b.mp4'],
                account_file=['a.json', 'b.json'], tags=[],
                enableTimer=True, schedule_time_str='2026-08-25 10:00',
            ))
        assert us.await_count == 4
        calls = us.await_args_list
        assert [c.kwargs['video_path'] for c in calls] == [
            '/v/a.mp4', '/v/a.mp4', '/v/b.mp4', '/v/b.mp4',
        ]
        assert calls[0].kwargs['publish_date'] == dates[0]
        assert calls[2].kwargs['publish_date'] == dates[1]
        assert calls[2].kwargs['cookie_path'].endswith('a.json')
        assert calls[3].kwargs['cookie_path'].endswith('b.json')

    def test_publish_video_sync_wrapper(self):
        p = _mk_platform()
        with patch.object(p, '_publish_video_async', AsyncMock()) as pv:
            res = asyncio.run(p.publish_video(title='T', files=['/v/a.mp4']))
        assert res is True
        pv.assert_awaited_once()
