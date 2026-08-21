"""TikTok platform.py DOM 交互层契约测试（T35 第三期）。

覆盖 impl/tiktok/platform.py（467 stmts，基线 20%）:
- 纯函数: _parse_cookie_to_storage_state（.tiktok.com 域/expires 未来/httpOnly/跳过无效对/去空白）
- 登录/校验/同步: login（URL 正则 wait_for_url=0/失败留浏览器现场） / check_cookie（select class 判定/异常兜底）
  / sync_profile（昵称+头像抓取/超时/缺失字段/异常兜底） / open_creator_center（线程启动/close 异常吞掉）
- 编排: _upload_single 全流程（iframe/main 文件输入/上传失败 raise/caption 等待/封面/AI 声明/
  定时/发布/视频 id/cookie 回写/浏览器关闭）
- DOM 辅助: _dismiss_tutorial_tooltip / _dismiss_content_check_modal / _dismiss_ai_label_modal /
  _dismiss_publish_confirm_modal（page+多 frame 遍历/force click） / _add_title_tags（DraftEditor 键盘输入） /
  _set_cover（弹窗上传+保存） / _set_ai_declaration（显示更多展开/Switch__root 点击/确认弹窗） /
  _set_schedule_time（预约发布/日历月导航 CN+EN+未知/日期/时分选择/Escape） /
  _click_publish（disabled/页面关闭/轮询耗尽/成功） / _get_last_video_id（href 解析/兜底）
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

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl._utils import scrape_user_profile
from impl.tiktok.platform import TiktokPlatform


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return TiktokPlatform()


def _mk_leaf():
    """叶子 locator：所有异步方法默认成功；locator(sel)/nth(i) 返回稳定可预配置对象。"""
    loc = MagicMock()
    loc.count = AsyncMock(return_value=0)
    loc.click = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.set_input_files = AsyncMock()
    loc.get_attribute = AsyncMock(return_value=None)
    loc.inner_text = AsyncMock(return_value='')
    loc.is_visible = AsyncMock(return_value=True)
    loc.fill = AsyncMock()
    loc.press = AsyncMock()
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


def _mk_page():
    page = MagicMock()
    page.url = 'https://www.tiktok.com/tiktokstudio/upload?lang=en'
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_event = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=[])
    page.frame_locator = MagicMock()
    page.is_closed = MagicMock(return_value=False)
    page.frames = []
    page.evaluate = AsyncMock(return_value=[])
    page.close = AsyncMock()
    locators = {}
    page.locator = MagicMock(side_effect=lambda sel, **kw: locators.setdefault(sel, _mk_locator()))
    page.locators = locators
    return page


def _loc(page, sel):
    """预注册 selector 并返回稳定 locator(page.locators[sel])。"""
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


def _mk_cookie_file(name='t35_tiktok_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


@contextmanager
def _mk_upload_single_steps(p):
    """把 _upload_single 的内部子步骤全部替换为可断言的 AsyncMock。"""
    mocks = dict(
        dismiss_tooltip=AsyncMock(),
        dismiss_content=AsyncMock(),
        add_title_tags=AsyncMock(),
        set_cover=AsyncMock(),
        set_ai=AsyncMock(),
        set_schedule=AsyncMock(),
        click_publish=AsyncMock(),
        get_video_id=AsyncMock(return_value='7391234567890123456'),
        close_browser=AsyncMock(),
    )
    with patch.object(p, '_dismiss_tutorial_tooltip', mocks['dismiss_tooltip']), \
         patch.object(p, '_dismiss_content_check_modal', mocks['dismiss_content']), \
         patch.object(p, '_add_title_tags', mocks['add_title_tags']), \
         patch.object(p, '_set_cover', mocks['set_cover']), \
         patch.object(p, '_set_ai_declaration', mocks['set_ai']), \
         patch.object(p, '_set_schedule_time', mocks['set_schedule']), \
         patch.object(p, '_click_publish', mocks['click_publish']), \
         patch.object(p, '_get_last_video_id', mocks['get_video_id']), \
         patch.object(p, 'close_browser', mocks['close_browser']), \
         patch('asyncio.sleep', AsyncMock()):
        yield mocks


# ── 纯函数: cookie 解析 ────────────────────────────────────────────────────

class TestParseCookieToStorageState:
    def test_happy_parse(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('a=1; b=2')
        assert origins == []
        assert [c['name'] for c in cookies] == ['a', 'b']
        for c in cookies:
            assert c['domain'] == '.tiktok.com'
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
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             patch('impl.tiktok.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.tiktok.platform.logger'):
            _run(p.login('u1', MagicMock(), account_id='acc1'))
        page.goto.assert_awaited_once_with('https://www.tiktok.com/login?lang=en')
        page.wait_for_url.assert_awaited_once()
        url_args = page.wait_for_url.await_args
        assert url_args.kwargs['timeout'] == 0
        assert url_args.args[0].pattern == r'/(foryou|following|upload|@)'
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 7
        assert kwargs['account_id'] == 'acc1'
        assert kwargs['scrape_fn'] is scrape_user_profile
        context.close.assert_awaited_once()
        _browser.close.assert_awaited_once()

    def test_wait_url_timeout_keeps_browser(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             patch('impl.tiktok.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.tiktok.platform.logger'):
            page.wait_for_url = AsyncMock(side_effect=TimeoutError('user closed'))
            with pytest.raises(TimeoutError):
                _run(p.login('u1', MagicMock()))
        slr.assert_not_awaited()
        context.close.assert_awaited_once()
        _browser.close.assert_not_awaited()  # 失败留浏览器给用户看现场

    def test_goto_error_keeps_browser(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             patch('impl.tiktok.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.tiktok.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            with pytest.raises(RuntimeError):
                _run(p.login('u1', MagicMock()))
        slr.assert_not_awaited()
        context.close.assert_awaited_once()
        _browser.close.assert_not_awaited()


class TestCheckCookie:
    @staticmethod
    def _el(cls_name):
        el = MagicMock()
        el.get_attribute = AsyncMock(return_value=cls_name)
        return el

    def test_valid_no_matching_select(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.tiktok.platform.logger'):
            page.query_selector_all = AsyncMock(return_value=[
                self._el('tiktok-SelectForm'),
                self._el('other-class'),
            ])
            assert _run(p.check_cookie('ck.json')) is True
        page.goto.assert_awaited_once_with('https://www.tiktok.com/tiktokstudio/upload?lang=en')
        page.wait_for_load_state.assert_awaited_once_with('networkidle')

    def test_expired_matching_select(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.tiktok.platform.logger'):
            page.query_selector_all = AsyncMock(return_value=[
                self._el('tiktok-upload-SelectFormContainer-custom'),
            ])
            assert _run(p.check_cookie('ck.json')) is False

    def test_exception_returns_true(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.tiktok.platform.logger'):
            page.query_selector_all = AsyncMock(side_effect=RuntimeError('boom'))
            assert _run(p.check_cookie('ck.json')) is True
        browser.close.assert_awaited_once()


class TestSyncProfile:
    def test_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.tiktok.platform.logger'):
            nick = _loc(page, 'div[data-tt="NewHome_UserInfo_Hover"]').first
            nick.count = AsyncMock(return_value=1)
            nick.inner_text = AsyncMock(return_value='  我的昵称  ')
            ava = _loc(page, 'img[data-tt="components_Avatar_AvatarImg"]').first
            ava.count = AsyncMock(return_value=1)
            ava.get_attribute = AsyncMock(return_value='http://a.png')
            name, avatar = _run(p.sync_profile('ck.json'))
        assert name == '我的昵称'
        assert avatar == 'http://a.png'
        page.wait_for_selector.assert_awaited_once_with(
            'div[data-tt="NewHome_UserInfo_FlexRow"]', timeout=15_000
        )
        page.goto.assert_awaited_once_with(
            'https://www.tiktok.com/tiktokstudio', wait_until='domcontentloaded'
        )
        browser.close.assert_awaited_once()

    def test_user_info_block_timeout_returns_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.tiktok.platform.logger'):
            page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
            assert _run(p.sync_profile('ck.json')) == ('', '')

    def test_nickname_missing(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.tiktok.platform.logger'):
            ava = _loc(page, 'img[data-tt="components_Avatar_AvatarImg"]').first
            ava.count = AsyncMock(return_value=1)
            ava.get_attribute = AsyncMock(return_value='http://a.png')
            name, avatar = _run(p.sync_profile('ck.json'))
        assert name == ''
        assert avatar == 'http://a.png'

    def test_avatar_missing(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.tiktok.platform.logger'):
            nick = _loc(page, 'div[data-tt="NewHome_UserInfo_Hover"]').first
            nick.count = AsyncMock(return_value=1)
            nick.inner_text = AsyncMock(return_value='昵称')
            name, avatar = _run(p.sync_profile('ck.json'))
        assert name == '昵称'
        assert avatar == ''

    def test_nickname_probe_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.tiktok.platform.logger'):
            _loc(page, 'div[data-tt="NewHome_UserInfo_Hover"]').first.count = AsyncMock(
                side_effect=RuntimeError('probe fail')
            )
            ava = _loc(page, 'img[data-tt="components_Avatar_AvatarImg"]').first
            ava.count = AsyncMock(return_value=1)
            ava.get_attribute = AsyncMock(return_value='http://a.png')
            name, avatar = _run(p.sync_profile('ck.json'))
        assert name == ''          # 昵称探测失败兜底为空
        assert avatar == 'http://a.png'

    def test_avatar_probe_error_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.tiktok.platform.logger'):
            nick = _loc(page, 'div[data-tt="NewHome_UserInfo_Hover"]').first
            nick.count = AsyncMock(return_value=1)
            nick.inner_text = AsyncMock(return_value='昵称')
            _loc(page, 'img[data-tt="components_Avatar_AvatarImg"]').first.count = AsyncMock(
                side_effect=RuntimeError('probe fail')
            )
            name, avatar = _run(p.sync_profile('ck.json'))
        assert name == '昵称'
        assert avatar == ''        # 头像探测失败兜底为空

    def test_outer_exception_returns_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.tiktok.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            assert _run(p.sync_profile('ck.json')) == ('', '')

    def test_browser_closed_on_outer_error(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.tiktok.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net down'))
            _run(p.sync_profile('ck.json'))
        browser.close.assert_awaited_once()


class TestOpenCreatorCenter:
    def test_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_tiktok_occ.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.tiktok.platform.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl.tiktok.platform.create_context_sync', return_value=context) as ccs:
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
        cookie = _mk_cookie_file('t35_tiktok_occ2.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.tiktok.platform.create_browser_sync', return_value=browser), \
                 patch('impl.tiktok.platform.create_context_sync', return_value=context):
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
        cookie = _mk_cookie_file('t35_tiktok_occ3.json')
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('boom'))
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.tiktok.platform.create_browser_sync', return_value=browser), \
                 patch('impl.tiktok.platform.create_context_sync', return_value=context):
                _run(p.open_creator_center(cookie.name))  # 不抛异常
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)


# ── 编排: _upload_single 全流程 ──────────────────────────────────────────

class TestUploadSingle:
    def _run(self, p, page, **kw):
        default = dict(
            title='标题', file_path='/m/v.mp4', tags=['a'],
            publish_date=0, account_file='/c/u1.json',
            thumbnail_path=None, ai_content=None,
        )
        default.update(kw)
        return _run(p._upload_single(**default))

    def test_happy_iframe_flow(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_single_steps(p) as mocks, \
             patch('impl.tiktok.platform.logger'):
            _loc(page, 'iframe[data-tt="Upload_index_iframe"]').count = AsyncMock(return_value=1)
            frame = MagicMock()
            finput = _mk_locator()
            finput.first.set_input_files = AsyncMock()
            frame.locator = MagicMock(return_value=finput)
            page.frame_locator = MagicMock(return_value=frame)
            self._run(p, page, publish_date=0, thumbnail_path=None, ai_content=None)
        finput.first.set_input_files.assert_awaited_once_with('/m/v.mp4', timeout=60_000)
        mocks['dismiss_tooltip'].assert_awaited_once_with(page)
        mocks['dismiss_content'].assert_awaited_once_with(page)
        mocks['add_title_tags'].assert_awaited_once_with(page, '标题', ['a'])
        mocks['set_cover'].assert_not_awaited()
        mocks['set_ai'].assert_not_awaited()
        mocks['set_schedule'].assert_not_awaited()
        mocks['click_publish'].assert_awaited_once_with(page)
        mocks['get_video_id'].assert_awaited_once_with(page)
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)

    def test_main_page_input(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), \
             _mk_upload_single_steps(p) as mocks, \
             patch('impl.tiktok.platform.logger'):
            _loc(page, 'input[type="file"]').first.set_input_files = AsyncMock()
            self._run(p, page)
        _loc(page, 'iframe[data-tt="Upload_index_iframe"]').count.assert_awaited_once()
        _loc(page, 'input[type="file"]').first.set_input_files.assert_awaited_once_with(
            '/m/v.mp4', timeout=60_000
        )
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)
        context.storage_state.assert_awaited_once()

    def test_file_input_wait_timeout_continues(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_single_steps(p) as mocks, \
             patch('impl.tiktok.platform.logger'):
            page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
            self._run(p, page)  # 不抛异常,走 set_input_files auto-wait
        mocks['add_title_tags'].assert_awaited_once()

    def test_set_input_files_failure_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             _mk_upload_single_steps(p) as mocks, \
             patch('impl.tiktok.platform.logger'):
            _loc(page, 'input[type="file"]').first.set_input_files = AsyncMock(
                side_effect=RuntimeError('boom')
            )
            with pytest.raises(RuntimeError):
                self._run(p, page)
        mocks['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)  # finally 仍关浏览器

    def test_thumbnail_provided_calls_cover(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_single_steps(p) as mocks, \
             patch('impl.tiktok.platform.logger'):
            self._run(p, page, thumbnail_path='/t.png')
        mocks['set_cover'].assert_awaited_once_with(page, '/t.png')

    @pytest.mark.parametrize('ai', [None, False, 0, '', 'false', '0', 'FALSE'])
    def test_ai_content_falsy_skips(self, ai):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_single_steps(p) as mocks, \
             patch('impl.tiktok.platform.logger'):
            self._run(p, page, ai_content=ai)
        mocks['set_ai'].assert_not_awaited()

    def test_ai_content_truthy_enables(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_single_steps(p) as mocks, \
             patch('impl.tiktok.platform.logger'):
            self._run(p, page, ai_content=True)
        mocks['set_ai'].assert_awaited_once_with(page, enable=True)

    def test_publish_date_zero_skips_schedule(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_single_steps(p) as mocks, \
             patch('impl.tiktok.platform.logger'):
            self._run(p, page, publish_date=0)
        mocks['set_schedule'].assert_not_awaited()

    def test_publish_date_scheduled(self):
        p = _mk_platform()
        pd = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_single_steps(p) as mocks, \
             patch('impl.tiktok.platform.logger'):
            self._run(p, page, publish_date=pd)
        mocks['set_schedule'].assert_awaited_once_with(page, pd)

    def test_parent_dir_listing_logged(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix='sau_t35_tiktok_parent_')
        file_path = str(Path(tmp) / 'v.mp4')  # 文件不存在但父目录存在
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_single_steps(p) as mocks, \
             patch('impl.tiktok.platform.logger') as logger:
            self._run(p, page, file_path=file_path)
        assert any(
            '父目录' in str(c) and '样本' in str(c) for c in logger.info.call_args_list
        )
        mocks['add_title_tags'].assert_awaited_once()

    def test_video_id_logged_and_sleep(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             _mk_upload_single_steps(p) as mocks, \
             patch('impl.tiktok.platform.logger') as logger, \
             patch('asyncio.sleep', AsyncMock()) as sleep_mock:
            self._run(p, page)
            mocks['get_video_id'].assert_awaited_once_with(page)
            assert any('video_id' in str(c) for c in logger.info.call_args_list)
            sleep_mock.assert_awaited_with(2)


# ── DOM 辅助: 弹窗关闭 ────────────────────────────────────────────────────

class TestDismissTutorialTooltip:
    def test_visible_clicks_got_it(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_tutorial_tooltip(page))
        tooltip = _loc(page, 'div.tutorial-tooltip').first
        tooltip.is_visible.assert_awaited_once_with(timeout=2_000)
        got = tooltip.subs['button.Button__root--type-primary:has-text("知道了")'].first
        got.wait_for.assert_awaited_once_with(state='visible', timeout=3_000)
        got.click.assert_awaited_once()

    def test_not_visible_noop(self):
        p = _mk_platform()
        page = _mk_page()
        tooltip = _loc(page, 'div.tutorial-tooltip').first
        tooltip.is_visible = AsyncMock(return_value=False)
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_tutorial_tooltip(page))
        assert tooltip.subs == {}  # 未探测子按钮
        tooltip.click.assert_not_awaited()

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, 'div.tutorial-tooltip').first.is_visible = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_tutorial_tooltip(page))  # 不抛异常


class TestDismissContentCheckModal:
    def test_visible_clicks_enable(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_content_check_modal(page))
        modal = _loc(page, 'div.TUXModal.common-modal').first
        modal.is_visible.assert_awaited_once_with(timeout=2_000)
        btn = page.locators[
            'div.TUXModal.common-modal div.common-modal-footer '
            'button.Button__root--type-primary'
        ].first
        btn.wait_for.assert_awaited_once_with(state='visible', timeout=3_000)
        btn.click.assert_awaited_once()

    def test_not_visible_noop(self):
        p = _mk_platform()
        page = _mk_page()
        modal = _loc(page, 'div.TUXModal.common-modal').first
        modal.is_visible = AsyncMock(return_value=False)
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_content_check_modal(page))
        assert modal.subs == {}
        modal.click.assert_not_awaited()

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, 'div.TUXModal.common-modal').first.is_visible = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_content_check_modal(page))


class TestDismissAiLabelModal:
    def test_visible_clicks_enable(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_ai_label_modal(page))
        modal = page.locators[
            'div.TUXModal.common-modal:has(h2:has-text("标记 AI 生成的内容"))'
        ].first
        modal.is_visible.assert_awaited_once_with(timeout=2_000)
        btn = modal.subs[
            'div.common-modal-footer button.Button__root--type-primary:has-text("开启")'
        ].first
        btn.wait_for.assert_awaited_once_with(state='visible', timeout=3_000)
        btn.click.assert_awaited_once()

    def test_not_visible_noop(self):
        p = _mk_platform()
        page = _mk_page()
        modal = _loc(
            page, 'div.TUXModal.common-modal:has(h2:has-text("标记 AI 生成的内容"))'
        ).first
        modal.is_visible = AsyncMock(return_value=False)
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_ai_label_modal(page))
        assert modal.subs == {}
        modal.click.assert_not_awaited()

    def test_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(
            page, 'div.TUXModal.common-modal:has(h2:has-text("标记 AI 生成的内容"))'
        ).first.is_visible = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_ai_label_modal(page))


class TestDismissPublishConfirmModal:
    MODAL_SEL = (
        'div.TUXModal.common-modal-confirm-modal '
        'div.common-modal-footer button:has-text("立即发布")'
    )

    def test_found_in_page_force_click(self):
        p = _mk_platform()
        page = _mk_page()
        logger = MagicMock()
        with patch('impl.tiktok.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_publish_confirm_modal(page))
        btn = page.locators[self.MODAL_SEL].first
        btn.wait_for.assert_awaited_once_with(state='attached', timeout=10_000)
        btn.click.assert_awaited_once_with(force=True, timeout=2_000)

    def test_found_in_frame(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, self.MODAL_SEL).first.wait_for = AsyncMock(side_effect=TimeoutError('no'))
        frame = MagicMock()
        fsubs = {}
        frame.locator = MagicMock(side_effect=lambda sel, **kw: fsubs.setdefault(sel, _mk_locator()))
        frame.url = 'https://iframe'
        page.frames = [frame]
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_publish_confirm_modal(page))
        fbtn = fsubs[self.MODAL_SEL].first
        fbtn.wait_for.assert_awaited_once_with(state='attached', timeout=10_000)
        fbtn.click.assert_awaited_once_with(force=True, timeout=2_000)

    def test_not_found_any_frame_logs(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, self.MODAL_SEL).first.wait_for = AsyncMock(side_effect=TimeoutError('no'))
        logger = MagicMock()
        with patch('impl.tiktok.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_publish_confirm_modal(page))  # 不抛异常
        assert any(
            'button not found in any frame within 10s' in str(c)
            for c in logger.info.call_args_list
        )

    def test_outer_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        page.frames = None  # list(None) 抛 TypeError,走外层兜底
        logger = MagicMock()
        with patch('impl.tiktok.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(p._dismiss_publish_confirm_modal(page))  # 不抛异常
        assert any('_dismiss_publish_confirm_modal' in str(c) for c in logger.info.call_args_list)


# ── DOM 辅助: 标题/标签/封面 ─────────────────────────────────────────────

class TestAddTitleTags:
    def test_happy_title_and_tags(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.tiktok.platform.clear_and_type', AsyncMock()) as cat, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.tiktok.platform.logger'):
            _run(p._add_title_tags(page, ' 标题  ', ['a', '', 'b']))
        editor = _loc(page, 'div.public-DraftEditor-content').first
        editor.wait_for.assert_awaited_once_with(state='visible', timeout=5_000)
        editor.click.assert_awaited_once()
        cat.assert_awaited_once_with(page, '')
        types = [c.args for c in page.keyboard.type.await_args_list]
        assert (' 标题',) in types  # 只 rstrip 尾部空白,保留前导
        assert (' #a',) in types and (' #b',) in types
        assert (' #',) not in types  # 空 tag 跳过
        presses = [c.args[0] for c in page.keyboard.press.await_args_list]
        assert presses == ['Space', 'Space', 'Space', 'Escape']

    def test_empty_title_skips_typing(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.tiktok.platform.clear_and_type', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), patch('impl.tiktok.platform.logger'):
            _run(p._add_title_tags(page, '   ', []))
        page.keyboard.type.assert_not_awaited()
        presses = [c.args[0] for c in page.keyboard.press.await_args_list]
        assert presses == ['Space', 'Escape']

    def test_no_tags_only_escape(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.tiktok.platform.clear_and_type', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), patch('impl.tiktok.platform.logger'):
            _run(p._add_title_tags(page, 'T', None))
        presses = [c.args[0] for c in page.keyboard.press.await_args_list]
        assert presses == ['Space', 'Escape']


class TestSetCover:
    def test_happy_upload_save(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._set_cover(page, '/img.png'))
        cov = _loc(page, '[data-e2e="cover_container"]').first
        cov.wait_for.assert_awaited_once_with(state='visible', timeout=5_000)
        cov.subs['.edit-container:has-text("编辑封面")'].click.assert_awaited_once()
        dialog = _loc(page, 'div.Dialog__content[data-open="true"]').first
        assert dialog.wait_for.await_args_list[0].kwargs == dict(state='visible', timeout=5_000)
        dialog.subs['input[type="file"]'].first.set_input_files.assert_awaited_once_with('/img.png')
        save = dialog.subs['button.header-button:has-text("保存")'].first
        save.wait_for.assert_awaited_once_with(state='visible', timeout=5_000)
        save.click.assert_awaited_once()
        assert dialog.wait_for.await_args_list[-1].kwargs == dict(state='hidden', timeout=5_000)

    def test_cover_container_wait_raises(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '[data-e2e="cover_container"]').first.wait_for = AsyncMock(
            side_effect=TimeoutError('no')
        )
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()), \
             pytest.raises(TimeoutError):
            _run(p._set_cover(page, '/img.png'))


# ── DOM 辅助: AI 声明 ─────────────────────────────────────────────────────

class TestSetAiDeclaration:
    @staticmethod
    def _mk_container(page, checked='false'):
        container = _loc(page, '[data-e2e="aigc_container"]').first
        container.locator('div.Switch__content')  # 预注册子选择器
        container.locator('div.Switch__root')
        container.subs['div.Switch__content'].first.get_attribute = AsyncMock(return_value=checked)
        return container

    def test_enable_when_off_clicks_switch_and_confirms(self):
        p = _mk_platform()
        page = _mk_page()
        container = self._mk_container(page, checked='false')
        with patch.object(TiktokPlatform, '_dismiss_ai_label_modal', AsyncMock()) as dml, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.tiktok.platform.logger'):
            _run(p._set_ai_declaration(page, enable=True))
        more = _loc(page, 'div.more-btn:has-text("显示更多")').first
        more.click.assert_awaited_once_with(force=True)  # 展开折叠区
        container.subs['div.Switch__root'].click.assert_awaited_once_with(force=True)
        dml.assert_awaited_once_with(page)

    def test_disable_when_on_clicks_switch(self):
        p = _mk_platform()
        page = _mk_page()
        container = self._mk_container(page, checked='true')
        with patch.object(TiktokPlatform, '_dismiss_ai_label_modal', AsyncMock()) as dml, \
             patch('asyncio.sleep', AsyncMock()), patch('impl.tiktok.platform.logger'):
            _run(p._set_ai_declaration(page, enable=False))
        container.subs['div.Switch__root'].click.assert_awaited_once_with(force=True)
        dml.assert_not_awaited()

    def test_already_in_target_state_no_click(self):
        p = _mk_platform()
        page = _mk_page()
        container = self._mk_container(page, checked='true')
        with patch.object(TiktokPlatform, '_dismiss_ai_label_modal', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), patch('impl.tiktok.platform.logger'):
            _run(p._set_ai_declaration(page, enable=True))
        container.subs['div.Switch__root'].click.assert_not_awaited()

    def test_more_btn_not_visible_skips_expand(self):
        p = _mk_platform()
        page = _mk_page()
        more = _loc(page, 'div.more-btn:has-text("显示更多")').first
        more.is_visible = AsyncMock(return_value=False)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tiktok.platform.logger'):
            _run(p._set_ai_declaration(page, enable=False))
        more.click.assert_not_awaited()

    def test_more_btn_expand_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, 'div.more-btn:has-text("显示更多")').first.is_visible = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tiktok.platform.logger'):
            _run(p._set_ai_declaration(page, enable=False))  # 不抛异常,继续诊断

    def test_diagnosis_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        container = _loc(page, '[data-e2e="aigc_container"]').first
        container.locator('div.Switch__content')
        container.locator('div.Switch__root')
        _loc(page, 'div.options-form').first.get_attribute = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tiktok.platform.logger'):
            _run(p._set_ai_declaration(page, enable=False))  # 诊断失败不阻断,继续等容器

    def test_container_not_visible_raises(self):
        p = _mk_platform()
        page = _mk_page()
        container = _loc(page, '[data-e2e="aigc_container"]').first
        container.wait_for = AsyncMock(side_effect=TimeoutError('not visible'))
        with patch('asyncio.sleep', AsyncMock()), patch('impl.tiktok.platform.logger'), \
             pytest.raises(TimeoutError):
            _run(p._set_ai_declaration(page, enable=True))


# ── DOM 辅助: 定时发布 ────────────────────────────────────────────────────

class TestSetScheduleTime:
    PD = datetime(2026, 8, 21, 10, 7, tzinfo=ZoneInfo('Asia/Shanghai'))

    def _mk_page_with_calendar(self, month_text='八月', day_count=3, days=('20', '21', '22')):
        page = _mk_page()
        calendar = _loc(page, 'div.calendar-wrapper').first
        # 预注册日历子选择器(代码路径会在运行时调用 calendar.locator(...))
        calendar.locator('span.month-title')
        calendar.locator('span.arrow')
        calendar.locator('span.day.valid')
        calendar.subs['span.month-title'].first.inner_text = AsyncMock(return_value=month_text)
        days_loc = calendar.subs['span.day.valid']
        days_loc.count = AsyncMock(return_value=day_count)
        for i, text in enumerate(days):
            days_loc.nth(i)  # 预注册 nth_subs[i]
            days_loc.nth_subs[i].inner_text = AsyncMock(return_value=text)
        return page, calendar, days_loc

    def _run_schedule(self, p, page):
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._set_schedule_time(page, self.PD))

    def test_happy_cn_month(self):
        p = _mk_platform()
        page, calendar, days = self._mk_page_with_calendar()
        self._run_schedule(p, page)
        label = _loc(page, 'label.Radio__root:has-text("预约发布")').first
        label.wait_for.assert_awaited_once_with(state='visible', timeout=5_000)
        label.click.assert_awaited_once()
        calendar.subs['span.arrow'].nth_subs[1].click.assert_not_awaited()  # 同月不翻页
        days.nth_subs[1].click.assert_awaited_once()  # 命中 21 号
        calendar.wait_for.assert_awaited_with(state='hidden', timeout=5_000)
        tp = _loc(page, 'div.tiktok-timepicker-time-picker-container').first
        tp.subs['span.tiktok-timepicker-left:has-text("10")'].first.click.assert_awaited_once()
        tp.subs['span.tiktok-timepicker-right:has-text("01")'].first.click.assert_awaited_once()
        page.keyboard.press.assert_awaited_with('Escape')

    def test_month_mismatch_clicks_right_arrow(self):
        p = _mk_platform()
        page, calendar, _days = self._mk_page_with_calendar(month_text='一月')
        self._run_schedule(p, page)
        calendar.subs['span.arrow'].nth_subs[1].click.assert_awaited_once_with(timeout=2_000)

    def test_english_month_parse(self):
        p = _mk_platform()
        page, calendar, _days = self._mk_page_with_calendar(month_text='August')
        self._run_schedule(p, page)
        calendar.subs['span.arrow'].nth_subs[1].click.assert_not_awaited()  # 8 月与目标一致

    def test_unknown_month_defaults_to_target(self):
        p = _mk_platform()
        page, calendar, _days = self._mk_page_with_calendar(month_text='Frimaire')
        self._run_schedule(p, page)
        calendar.subs['span.arrow'].nth_subs[1].click.assert_not_awaited()

    def test_day_not_found_no_click(self):
        p = _mk_platform()
        page, _calendar, days = self._mk_page_with_calendar(days=('30', '31', '32'))
        self._run_schedule(p, page)
        assert all(not d.click.await_args_list for d in days.nth_subs.values())

    def test_minute_rounding_down(self):
        p = _mk_platform()
        pd = datetime(2026, 8, 21, 10, 4, tzinfo=ZoneInfo('Asia/Shanghai'))
        page = _mk_page()
        calendar = _loc(page, 'div.calendar-wrapper').first
        calendar.locator('span.month-title')
        calendar.locator('span.arrow')
        calendar.locator('span.day.valid')
        calendar.subs['span.month-title'].first.inner_text = AsyncMock(return_value='八月')
        days = calendar.subs['span.day.valid']
        days.count = AsyncMock(return_value=1)
        days.nth(0)  # 预注册 nth_subs[0]
        days.nth_subs[0].inner_text = AsyncMock(return_value='21')
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._set_schedule_time(page, pd))
        tp = _loc(page, 'div.tiktok-timepicker-time-picker-container').first
        tp.subs['span.tiktok-timepicker-right:has-text("00")'].first.click.assert_awaited_once()

    def test_right_arrow_click_error_swallowed(self):
        p = _mk_platform()
        page, calendar, days = self._mk_page_with_calendar(month_text='一月')
        calendar.subs['span.arrow'].nth(1)  # 预注册 nth_subs[1]
        calendar.subs['span.arrow'].nth_subs[1].click = AsyncMock(side_effect=TimeoutError('boom'))
        self._run_schedule(p, page)  # 不抛异常,继续选日
        days.nth_subs[1].click.assert_awaited_once()


# ── DOM 辅助: 发布按钮 / 视频 ID ──────────────────────────────────────────

class TestClickPublish:
    def test_success_clicks_and_waits_url(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(TiktokPlatform, '_dismiss_publish_confirm_modal', AsyncMock()) as dpm, \
             patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._click_publish(page))
        btn = _loc(page, 'button[data-e2e="post_video_button"]').first
        btn.wait_for.assert_awaited_once_with(state='visible', timeout=5_000)
        btn.click.assert_awaited_once()
        dpm.assert_awaited_once_with(page)
        page.wait_for_url.assert_awaited_once()
        pattern = page.wait_for_url.await_args.args[0]
        assert pattern.pattern == r'/tiktokstudio/content'
        assert page.wait_for_url.await_args.kwargs['timeout'] == 10_000

    def test_disabled_button_waits(self):
        p = _mk_platform()
        page = _mk_page()
        btn = _loc(page, 'button[data-e2e="post_video_button"]').first
        btn.get_attribute = AsyncMock(side_effect=['disabled', None])
        with patch.object(TiktokPlatform, '_dismiss_publish_confirm_modal', AsyncMock()), \
             patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._click_publish(page))
        assert btn.get_attribute.await_count == 2
        btn.click.assert_awaited_once()

    def test_page_closed_returns(self):
        p = _mk_platform()
        page = _mk_page()
        page.is_closed = MagicMock(return_value=True)
        with patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._click_publish(page))
        _loc(page, 'button[data-e2e="post_video_button"]').first.wait_for.assert_not_awaited()

    def test_loop_exhausted_after_60_attempts(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_url = AsyncMock(side_effect=TimeoutError('never redirects'))
        logger = MagicMock()
        with patch.object(TiktokPlatform, '_dismiss_publish_confirm_modal', AsyncMock()), \
             patch('impl.tiktok.platform.logger', logger), patch('asyncio.sleep', AsyncMock()):
            _run(p._click_publish(page))
        btn = _loc(page, 'button[data-e2e="post_video_button"]').first
        assert btn.click.call_count == 60
        assert any('loop exhausted 60 attempts' in str(c) for c in logger.info.call_args_list)

    def test_click_exception_retries(self):
        p = _mk_platform()
        page = _mk_page()
        btn = _loc(page, 'button[data-e2e="post_video_button"]').first
        btn.click = AsyncMock(side_effect=[RuntimeError('stale'), None])
        with patch.object(TiktokPlatform, '_dismiss_publish_confirm_modal', AsyncMock()), \
             patch('impl.tiktok.platform.logger'), patch('asyncio.sleep', AsyncMock()):
            _run(p._click_publish(page))
        assert btn.click.await_count == 2


class TestGetLastVideoId:
    def test_happy_href_match(self):
        p = _mk_platform()
        page = _mk_page()
        vl = _loc(
            page,
            'div[data-tt="components_PostTable_Container"] '
            'div[data-tt="components_PostInfoCell_Container"] a',
        )
        vl.count = AsyncMock(return_value=1)
        vl.nth(0)  # 预注册 nth_subs[0]
        vl.nth_subs[0].get_attribute = AsyncMock(
            return_value='https://www.tiktok.com/@user/video/7391234567890123456'
        )
        with patch('impl.tiktok.platform.logger'):
            vid = _run(p._get_last_video_id(page))
        assert vid == '7391234567890123456'
        page.wait_for_selector.assert_awaited_once_with(
            'div[data-tt="components_PostTable_Container"]', timeout=10_000
        )

    def test_href_no_match_returns_none(self):
        p = _mk_platform()
        page = _mk_page()
        vl = _loc(
            page,
            'div[data-tt="components_PostTable_Container"] '
            'div[data-tt="components_PostInfoCell_Container"] a',
        )
        vl.count = AsyncMock(return_value=1)
        vl.nth(0)  # 预注册 nth_subs[0]
        vl.nth_subs[0].get_attribute = AsyncMock(return_value='https://www.tiktok.com/@user/photo/1')
        with patch('impl.tiktok.platform.logger'):
            assert _run(p._get_last_video_id(page)) is None

    def test_no_video_list_returns_none(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.tiktok.platform.logger'):
            assert _run(p._get_last_video_id(page)) is None

    def test_exception_returns_none(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('impl.tiktok.platform.logger'):
            assert _run(p._get_last_video_id(page)) is None
