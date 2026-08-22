"""百家号 platform.py DOM 交互层契约测试（T35 第一期）。

覆盖 baijiahao/platform.py 深水区(518 stmts, 基线 26%):
- 纯函数: _parse_cookie_to_storage_state / _count_chars / _validate_publish_params
- 登录/校验/同步: login(QR 流程+success 才关浏览器) / check_cookie(失效 marker/业务域)
  / sync_profile(profile+stats+storage_state 回写) / _scrape_baijiahao_stats(label_map)
  / _login_stats_fn / open_creator_center(线程)
- 编排: publish_video(前置校验) / _upload_all(文件×账号矩阵)
- 单视频: _upload_one_video 全流程(请求监听/上传轮询/封面就绪/人机校验/成功跳转)
- DOM 辅助: _wait_for_upload / _add_title_tags(Lexical/placeholder 兜底) / _publish_video
  (定时/直接) / _direct_publish / _set_schedule_publish(1h-7d 校验) / _pick_schedule_option
  (aria-activedescendant 键盘导航) / _set_cover(双 cover-container) / _set_creation_declaration
"""
import asyncio
import sys
import time as _time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from conf import BASE_DIR
from impl.baijiahao.platform import BaijiahaoPlatform


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return BaijiahaoPlatform()


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
    loc.focus = AsyncMock()
    loc.is_visible = AsyncMock(return_value=True)
    loc.inner_text = AsyncMock(return_value='')
    loc.text_content = AsyncMock(return_value='')
    loc.get_attribute = AsyncMock(return_value='')
    loc.nth = MagicMock(side_effect=lambda i: _mk_leaf())
    loc.filter = MagicMock(side_effect=lambda **kw: _mk_leaf())
    loc.locator = MagicMock(side_effect=lambda sel, **kw: _mk_leaf())
    loc.get_by_role = MagicMock(side_effect=lambda role, name=None, exact=False: _mk_leaf())
    loc.get_by_text = MagicMock(side_effect=lambda text, exact=False: _mk_leaf())
    loc.get_by_placeholder = MagicMock(side_effect=lambda text: _mk_leaf())
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


@contextmanager
def _mk_browser_chain(platform, urls=None):
    """create_browser/create_context 链 mocks(page 走 _mk_page 分派)。"""
    page = _mk_page(urls=urls)
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.storage_state = AsyncMock()
    context.grant_permissions = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    with patch.object(platform, 'create_browser', AsyncMock(return_value=browser)) as cb, \
         patch.object(platform, 'create_context', AsyncMock(return_value=context)) as cc:
        yield page, context, browser, cb, cc


def _mk_page(urls=None):
    """通用 fake page:locator/get_by_* 按 key 分派,带默认 async 方法。"""
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
        page.url = 'https://baijiahao.baidu.com/builder/rc/home'
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_event = AsyncMock()
    page.evaluate = AsyncMock(return_value=[])
    page.on = MagicMock()
    page.input_value = AsyncMock()
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


def _mk_cookie_file(name='t35_bjh_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


def _mk_img_file(name='t35_bjh_img.png', size=1024):
    import os as _os
    import tempfile as _tf
    fd, path = _tf.mkstemp(prefix=name, suffix='.png')
    with _os.fdopen(fd, 'wb') as f:
        f.write(b'x' * size)
    return path


# ── 纯函数: cookie 解析 / 字符计数 / 前置校验 ───────────────────────────

class TestParseCookieToStorageState:
    def test_happy_parse(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('BAIDUID=abc; PSTM=123; x=1')
        assert len(cookies) == 3
        assert origins == []
        c0 = cookies[0]
        assert c0['name'] == 'BAIDUID'
        assert c0['value'] == 'abc'
        assert c0['domain'] == '.baidu.com'
        assert c0['path'] == '/'
        assert c0['httpOnly'] is True
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


class TestCountChars:
    def test_ascii_and_cjk(self):
        assert BaijiahaoPlatform._count_chars('abc百家号') == 6

    def test_emoji_counts_3(self):
        s = 'a' + '\U0001F600'  # a + emoji(surrogate pair, codepoint > 0xFFFF)
        assert BaijiahaoPlatform._count_chars(s) == 4

    def test_empty(self):
        assert BaijiahaoPlatform._count_chars('') == 0


class TestValidatePublishParams:
    def test_ok_empty(self):
        ok, err = BaijiahaoPlatform._validate_publish_params('', [])
        assert ok and err == ''

    def test_ok_short(self):
        ok, _err = BaijiahaoPlatform._validate_publish_params('你好', ['旅行'])
        assert ok

    def test_tags_over_10(self):
        ok, err = BaijiahaoPlatform._validate_publish_params('', [f't{i}' for i in range(11)])
        assert not ok and '最多 10 个标签' in err

    def test_over_50_chars(self):
        ok, err = BaijiahaoPlatform._validate_publish_params('x' * 40, ['y' * 20])
        assert not ok and '总字符数' in err and '50' in err


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLogin:
    def test_login_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.baijiahao.platform.save_login_result', AsyncMock()) as slr, \
             patch('asyncio.sleep', AsyncMock()):
            _run(p.login('u1', MagicMock(), account_id='acc1'))
        page.goto.assert_awaited_once()
        page.wait_for_url.assert_awaited_once_with('**/builder/rc/home**', timeout=0)
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 6
        assert kwargs['account_id'] == 'acc1'
        browser.close.assert_awaited_once()

    def test_login_timeout_keeps_browser_open(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, browser, _cb, _cc), \
             patch('impl.baijiahao.platform.save_login_result', AsyncMock()) as slr, \
             patch('asyncio.sleep', AsyncMock()):
            p.create_context = AsyncMock(side_effect=TimeoutError('qr timeout'))
            with pytest.raises(TimeoutError):
                _run(p.login('u1', MagicMock()))
        slr.assert_not_awaited()
        browser.close.assert_not_awaited()  # 失败留浏览器看现场


class TestCheckCookie:
    def test_missing_file(self):
        p = _mk_platform()
        with patch.object(p, 'create_browser', AsyncMock()) as cb:
            assert _run(p.check_cookie('no_such_t35.json')) is False
        cb.assert_not_awaited()

    def test_valid(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_ck_valid.json')
        try:
            with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()):
                page.url = 'https://baijiahao.baidu.com/builder/rc/home'
                assert _run(p.check_cookie(cookie.name)) is True
        finally:
            cookie.unlink(missing_ok=True)

    def test_expired_marker(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_ck_exp.json')
        try:
            with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()):
                page.url = 'https://passport.baidu.com/v3/login?tp=baijiahao'
                assert _run(p.check_cookie(cookie.name)) is False
        finally:
            cookie.unlink(missing_ok=True)

    def test_off_domain(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_ck_off.json')
        try:
            with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()):
                page.url = 'https://www.baidu.com/'
                assert _run(p.check_cookie(cookie.name)) is False
        finally:
            cookie.unlink(missing_ok=True)

    def test_page_error_returns_false(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_ck_err.json')
        try:
            with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()):
                page.goto = AsyncMock(side_effect=TimeoutError('nav fail'))
                assert _run(p.check_cookie(cookie.name)) is False
                browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)


class TestSyncProfile:
    def test_happy_path(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_sp.json')
        try:
            with _mk_browser_chain(p) as (_page, context, _browser, _cb, _cc), \
                 patch('impl.baijiahao.platform.scrape_baijiahao_profile',
                       AsyncMock(return_value=('昵称', 'http://a.png'))), \
                 patch.object(p, '_scrape_baijiahao_stats',
                              AsyncMock(return_value=[{'SORT': 1}])) as sbs, \
                 patch('impl.baijiahao.platform.logger'):
                res = _run(p.sync_profile(cookie.name))
            assert res == {'name': '昵称', 'avatar': 'http://a.png', 'stats': [{'SORT': 1}]}
            sbs.assert_awaited_once()
            context.storage_state.assert_awaited_once_with(path=str(cookie))
        finally:
            cookie.unlink(missing_ok=True)

    def test_stats_failure_falls_back_empty(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_sp2.json')
        try:
            with _mk_browser_chain(p) as (_page, context, _browser, _cb, _cc), \
                 patch('impl.baijiahao.platform.scrape_baijiahao_profile',
                       AsyncMock(return_value=('n', 'a'))), \
                 patch.object(p, '_scrape_baijiahao_stats',
                              AsyncMock(side_effect=RuntimeError('boom'))), \
                 patch('impl.baijiahao.platform.logger'):
                res = _run(p.sync_profile(cookie.name))
            assert res == {'name': 'n', 'avatar': 'a', 'stats': []}
            context.storage_state.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_writeback_failure_swallowed(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_sp3.json')
        try:
            with _mk_browser_chain(p) as (_page, context, _browser, _cb, _cc), \
                 patch('impl.baijiahao.platform.scrape_baijiahao_profile',
                       AsyncMock(return_value=('n', 'a'))), \
                 patch.object(p, '_scrape_baijiahao_stats', AsyncMock(return_value=[])), \
                 patch('impl.baijiahao.platform.logger'):
                context.storage_state = AsyncMock(side_effect=OSError('disk full'))
                res = _run(p.sync_profile(cookie.name))
            assert res['name'] == 'n'  # 写回失败不影响返回
        finally:
            cookie.unlink(missing_ok=True)


class TestScrapeStats:
    def test_empty_raw(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.baijiahao.platform.logger'):
            assert _run(p._scrape_baijiahao_stats(page)) == []

    def test_mapped_sorted_and_normalized(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'label': '累计总收益', 'num': '1,234'},
            {'label': '未知指标', 'num': '5'},
            {'label': '总粉丝量', 'num': '8,888'},
            {'label': '累计阅读(播放)量', 'num': '9+'},
            {'label': '近30天分润收益', 'num': 'abc'},
        ])
        with patch('impl.baijiahao.platform.logger'):
            stats = _run(p._scrape_baijiahao_stats(page))
        # 未知 label 丢弃;按 SORT 排序
        assert [s['NAME'] for s in stats] == ['粉丝', '播放量', '累计收益', '近30天分润']
        assert stats[0]['COUNT'] == 8888
        assert stats[1]['COUNT'] == 9   # '9+' → 9
        assert stats[2]['COUNT'] == 1234  # 千分位
        assert stats[3]['COUNT'] == 0   # 非法数字 → 0

    def test_wait_timeout_still_scrapes(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        page.evaluate = AsyncMock(return_value=[{'label': '总粉丝量', 'num': '3'}])
        with patch('impl.baijiahao.platform.logger'):
            stats = _run(p._scrape_baijiahao_stats(page))
        assert len(stats) == 1 and stats[0]['NAME'] == '粉丝'

    def test_evaluate_error_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('js fail'))
        with patch('impl.baijiahao.platform.logger'):
            assert _run(p._scrape_baijiahao_stats(page)) == []


class TestLoginStatsFn:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_baijiahao_stats',
                          AsyncMock(return_value=[{'SORT': 1}])) as sbs, \
             patch('impl.baijiahao.platform.logger'):
            res = _run(p._login_stats_fn(page, 'acc1'))
        assert res == [{'SORT': 1}]
        sbs.assert_awaited_once()
        page.goto.assert_awaited_once()

    def test_goto_timeout_continues(self):
        p = _mk_platform()
        page = _mk_page()
        page.goto = AsyncMock(side_effect=TimeoutError('slow'))
        with patch.object(p, '_scrape_baijiahao_stats', AsyncMock(return_value=[])), \
             patch('impl.baijiahao.platform.logger'):
            assert _run(p._login_stats_fn(page, 'acc1')) == []

    def test_scrape_error_returns_empty(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_baijiahao_stats',
                          AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('impl.baijiahao.platform.logger'):
            assert _run(p._login_stats_fn(page, 'acc1')) == []


class TestOpenCreatorCenter:
    def test_starts_thread_and_opens(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_occ.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.baijiahao.platform.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl.baijiahao.platform.create_context_sync', return_value=context) as ccs:
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

    def test_wait_event_error_swallowed(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_occ2.json')
        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.baijiahao.platform.create_browser_sync', return_value=browser), \
                 patch('impl.baijiahao.platform.create_context_sync', return_value=context):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            page.wait_for_event.assert_called_once()
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)


# ── 编排: publish_video 前置校验 / _upload_all 矩阵 ─────────────────────

class TestPublishVideoWrapper:
    def test_tags_over_10_raises(self):
        p = _mk_platform()
        with patch('impl.baijiahao.platform.logger'), pytest.raises(ValueError, match='最多 10 个标签'):
            asyncio.run(p.publish_video(title='T', files=['/v/a.mp4'], tags=[f't{i}' for i in range(11)]))

    def test_over_50_chars_raises(self):
        p = _mk_platform()
        with patch('impl.baijiahao.platform.logger'), pytest.raises(ValueError, match='总字符数'):
            asyncio.run(p.publish_video(title='T', files=['/v/a.mp4'], desc='x' * 60))

    def test_valid_delegates_to_upload_all(self):
        p = _mk_platform()
        with patch.object(p, '_upload_all', AsyncMock()) as ua, \
             patch('impl.baijiahao.platform.logger'):
            res = asyncio.run(p.publish_video(title='T', files=['/v/a.mp4'], tags=['x'], desc='简介'))
        assert res is True
        ua.assert_awaited_once()


class TestUploadAll:
    def test_multi_file_multi_account(self):
        p = _mk_platform()
        dates = [datetime(2026, 8, 25, 10, 0, tzinfo=datetime.now().astimezone().tzinfo),
                 datetime(2026, 8, 26, 10, 0, tzinfo=datetime.now().astimezone().tzinfo)]
        with patch.object(p, '_upload_one_video', AsyncMock()) as uov, \
             patch('impl.baijiahao.platform.parse_schedule_time', return_value=dates), \
             patch('impl.baijiahao.platform.get_account_name_by_cookie_file', return_value='号'), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._upload_all(
                title='T', files=['/v/a.mp4', '/v/b.mp4'],
                account_file=['a.json', 'b.json'], tags=['x'],
            ))
        assert uov.await_count == 4
        calls = uov.await_args_list
        assert [c.kwargs['file_path'] for c in calls] == ['/v/a.mp4', '/v/a.mp4', '/v/b.mp4', '/v/b.mp4']
        assert calls[0].kwargs['publish_date'] == dates[0]
        assert calls[2].kwargs['publish_date'] == dates[1]
        assert calls[0].kwargs['account_file'].endswith('a.json')
        assert calls[3].kwargs['account_file'].endswith('b.json')

    def test_cover_and_declaration_passthrough(self):
        p = _mk_platform()
        with patch.object(p, '_upload_one_video', AsyncMock()) as uov, \
             patch('impl.baijiahao.platform.parse_schedule_time', return_value=[0]), \
             patch('impl.baijiahao.platform.get_account_name_by_cookie_file', return_value=''), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._upload_all(
                title='T', files=['/v/a.mp4'], account_file=['ck.json'], tags=[],
                thumbnail_landscape_path='/l.png', thumbnail_portrait_path='/p.png',
                thumbnail_landscape_169_path='/l169.png',
                creation_declaration='原创', supplementary_declaration='AI生成',
                ai_content=True,
            ))
        kw = uov.await_args.kwargs
        assert kw['thumbnail_landscape_path'] == '/l.png'
        assert kw['thumbnail_landscape_169_path'] == '/l169.png'
        assert kw['creation_declaration'] == '原创'
        assert kw['supplementary_declaration'] == 'AI生成'
        assert kw['ai_content'] is True


# ── 单视频上传: _upload_one_video 全流程 ────────────────────────────────

class TestUploadOneVideo:
    def _mk(self, p, page, **kw):
        """配置基础链路,返回常用对象。"""
        # 上传完成请求监听: page.on 注册即触发 handler(事件先置位)
        req = MagicMock()
        req.url = 'https://baijiahao.baidu.com/api/materialui/video/compuploadvideo?x=1'
        page.on = MagicMock(side_effect=lambda event, handler: handler(req))
        video_input = page.locator("input[type='file'][accept*='.mp4']")
        video_input.count = AsyncMock(return_value=1)
        video_input.set_input_files = AsyncMock()
        containers = page.locator("div[class*='coverWrap'] > div[class*='cover-container']")
        containers.count = AsyncMock(return_value=2)
        return video_input, containers

    def test_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, cc), \
             patch.object(p, '_add_title_tags', AsyncMock()) as att, \
             patch.object(p, '_wait_for_upload', AsyncMock(return_value=True)) as wfu, \
             patch.object(p, '_set_cover', AsyncMock()) as sc, \
             patch.object(p, '_set_creation_declaration', AsyncMock()) as scd, \
             patch.object(p, '_publish_video', AsyncMock()) as pv, \
             patch.object(p, 'close_browser', AsyncMock()) as cb2, \
             patch('asyncio.sleep', AsyncMock()):
            video_input, _containers = self._mk(p, page)
            _run(p._upload_one_video(
                title='T', file_path='/v/a.mp4', tags=['x'], publish_date=0,
                account_file='/tmp/t35_ck.json', desc='简介',
            ))
        cc.assert_awaited_once()
        assert cc.await_args.kwargs['storage_state'] == '/tmp/t35_ck.json'
        video_input.set_input_files.assert_awaited_once_with('/v/a.mp4')
        att.assert_awaited_once()
        wfu.assert_awaited_once()
        sc.assert_awaited_once()
        scd.assert_awaited_once()
        pv.assert_awaited_once()
        context.storage_state.assert_awaited_once_with(path='/tmp/t35_ck.json')
        cb2.assert_awaited_once_with(browser, is_close_by_code=True)

    def test_video_input_fallback(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch.object(p, '_add_title_tags', AsyncMock()), \
             patch.object(p, '_wait_for_upload', AsyncMock(return_value=True)), \
             patch.object(p, '_set_cover', AsyncMock()), \
             patch.object(p, '_set_creation_declaration', AsyncMock()), \
             patch.object(p, '_publish_video', AsyncMock()), \
             patch.object(p, 'close_browser', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()):
            video_input, _containers = self._mk(p, page)
            video_input.count = AsyncMock(return_value=0)  # mp4 专属 input 缺失
            fallback = page.locator("input[type='file']").first
            fallback.set_input_files = AsyncMock()
            _run(p._upload_one_video(
                title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                account_file='/tmp/t35_ck.json',
            ))
        fallback.set_input_files.assert_awaited_once_with('/v/a.mp4')
        video_input.set_input_files.assert_not_awaited()

    def test_upload_fail_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch.object(p, '_add_title_tags', AsyncMock()), \
             patch.object(p, '_wait_for_upload', AsyncMock(return_value=False)), \
             patch.object(p, '_set_cover', AsyncMock()), \
             patch.object(p, '_set_creation_declaration', AsyncMock()), \
             patch.object(p, '_publish_video', AsyncMock()), \
             patch.object(p, 'close_browser', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            self._mk(p, page)
            with pytest.raises(Exception, match='Video upload failed'):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                    account_file='/tmp/t35_ck.json',
                ))

    def test_captcha_wait_hidden(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             patch.object(p, '_add_title_tags', AsyncMock()), \
             patch.object(p, '_wait_for_upload', AsyncMock(return_value=True)), \
             patch.object(p, '_set_cover', AsyncMock()), \
             patch.object(p, '_set_creation_declaration', AsyncMock()), \
             patch.object(p, '_publish_video', AsyncMock()), \
             patch.object(p, 'close_browser', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            self._mk(p, page)
            captcha = page.locator('div.passMod_dialog-container:visible')
            captcha.count = AsyncMock(return_value=1)
            captcha.wait_for = AsyncMock()  # hidden → 通过
            _run(p._upload_one_video(
                title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                account_file='/tmp/t35_ck.json',
            ))
        captcha.wait_for.assert_awaited_once_with(state='hidden', timeout=120000)
        context.storage_state.assert_awaited_once()

    def test_captcha_timeout_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch.object(p, '_add_title_tags', AsyncMock()), \
             patch.object(p, '_wait_for_upload', AsyncMock(return_value=True)), \
             patch.object(p, '_set_cover', AsyncMock()), \
             patch.object(p, '_set_creation_declaration', AsyncMock()), \
             patch.object(p, '_publish_video', AsyncMock()), \
             patch.object(p, 'close_browser', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            self._mk(p, page)
            captcha = page.locator('div.passMod_dialog-container:visible')
            captcha.count = AsyncMock(return_value=1)
            captcha.wait_for = AsyncMock(side_effect=TimeoutError('human check timeout'))
            with pytest.raises(Exception, match='人机校验等待超时'):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                    account_file='/tmp/t35_ck.json',
                ))

    def test_redirect_fail_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch.object(p, '_add_title_tags', AsyncMock()), \
             patch.object(p, '_wait_for_upload', AsyncMock(return_value=True)), \
             patch.object(p, '_set_cover', AsyncMock()), \
             patch.object(p, '_set_creation_declaration', AsyncMock()), \
             patch.object(p, '_publish_video', AsyncMock()), \
             patch.object(p, 'close_browser', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            self._mk(p, page)
            # 第 1 次 wait_for_url(发布页) 成功;第 2 次(成功跳转) 失败
            page.wait_for_url = AsyncMock(side_effect=[None, TimeoutError('no redirect')])
            with pytest.raises(Exception, match='未成功跳转'):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                    account_file='/tmp/t35_ck.json',
                ))


# ── 上传完成等待: _wait_for_upload ──────────────────────────────────────

class TestWaitForUpload:
    def test_event_set_returns_true(self):
        p = _mk_platform()
        page = _mk_page()
        ev = asyncio.Event()
        ev.set()
        with patch('impl.baijiahao.platform.logger'):
            assert _run(p._wait_for_upload(page, ev)) is True


# ── 标题/话题: _add_title_tags(Lexical / placeholder 兜底) ──────────────

class TestAddTitleTags:
    def test_lexical_editor_happy(self):
        p = _mk_platform()
        page = _mk_page()
        lexical = page.locator('[data-lexical-editor="true"]')
        lexical.count = AsyncMock(return_value=1)
        lexical.first.click = AsyncMock()
        topic_list = page.locator("div[class*='topicListInner']")
        subs = _sub_locators(topic_list)
        topic_list.locator("div[class*='topicItem']")
        topic_item = subs["div[class*='topicItem']"].first
        topic_item.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.clear_and_type', AsyncMock()) as cat, \
             patch('impl.baijiahao.platform.logger'):
            _run(p._add_title_tags(page, '标题', '简介', ['旅行', '美食']))
        lexical.first.click.assert_awaited_once()
        cat.assert_awaited_once_with(page, '简介', delay=50)
        assert page.keyboard.type.await_count == 2
        topic_item.click.assert_awaited()

    def test_placeholder_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        lexical = page.locator('[data-lexical-editor="true"]')
        lexical.count = AsyncMock(return_value=0)
        ph = page.get_by_placeholder('添加标题获得更多推荐')
        ph.count = AsyncMock(return_value=1)
        ph.fill = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._add_title_tags(page, '标题', '简介', ['旅行']))
        ph.fill.assert_awaited_once_with('简介 #旅行')
        page.keyboard.type.assert_not_awaited()

    def test_neither_found_warns(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._add_title_tags(page, '标题', '简介', ['旅行']))
        page.keyboard.type.assert_not_awaited()

    def test_tag_dropdown_timeout_skips(self):
        p = _mk_platform()
        page = _mk_page()
        lexical = page.locator('[data-lexical-editor="true"]')
        lexical.count = AsyncMock(return_value=1)
        topic_list = page.locator("div[class*='topicListInner']")
        topic_list.wait_for = AsyncMock(side_effect=TimeoutError('no dropdown'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.clear_and_type', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._add_title_tags(page, '标题', '', ['旅行', '美食']))
        assert page.keyboard.type.await_count == 2  # 两个 tag 都输入了
        topic_list.locator.assert_not_called()


# ── 发布分派/直接发布 ───────────────────────────────────────────────────

class TestPublishDispatch:
    def test_schedule_branch(self):
        p = _mk_platform()
        page = _mk_page()
        dt = datetime.now(ZoneInfo('Asia/Shanghai')) + timedelta(days=2)
        with patch.object(p, '_set_schedule_publish', AsyncMock()) as ssp, \
             patch.object(p, '_direct_publish', AsyncMock()) as dp, \
             patch('impl.baijiahao.platform.logger'):
            _run(p._publish_video(page, dt))
        ssp.assert_awaited_once_with(page, dt)
        dp.assert_not_awaited()

    def test_direct_branch(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_set_schedule_publish', AsyncMock()) as ssp, \
             patch.object(p, '_direct_publish', AsyncMock()) as dp, \
             patch('impl.baijiahao.platform.logger'):
            _run(p._publish_video(page, 0))
        dp.assert_awaited_once()
        ssp.assert_not_awaited()


class TestDirectPublish:
    def test_data_testid_button(self):
        p = _mk_platform()
        page = _mk_page()
        btn = page.locator("button[data-testid='publish-btn']")
        btn.count = AsyncMock(return_value=1)
        btn.click = AsyncMock()
        with patch('impl.baijiahao.platform.logger'):
            _run(p._direct_publish(page))
        btn.click.assert_awaited_once()

    def test_fallback_cheetah_button(self):
        p = _mk_platform()
        page = _mk_page()
        btn = page.locator("button[data-testid='publish-btn']")
        btn.count = AsyncMock(return_value=0)
        fb = page.locator("button.cheetah-btn-primary:has-text('发布')")
        fb.count = AsyncMock(return_value=1)
        fb.first.click = AsyncMock()
        with patch('impl.baijiahao.platform.logger'):
            _run(p._direct_publish(page))
        fb.first.click.assert_awaited_once()

    def test_exception_raises(self):
        p = _mk_platform()
        page = _mk_page()
        btn = page.locator("button[data-testid='publish-btn']")
        btn.count = AsyncMock(side_effect=RuntimeError('dom broken'))
        with patch('impl.baijiahao.platform.logger'), pytest.raises(RuntimeError, match='dom broken'):
            _run(p._direct_publish(page))


# ── 定时发布: _set_schedule_publish(1h-7d 校验) + _pick_schedule_option ──

class TestSetSchedulePublish:
    def test_past_date_raises(self):
        p = _mk_platform()
        page = _mk_page()
        dt = datetime.now(ZoneInfo('Asia/Shanghai')) - timedelta(days=1)
        with patch('impl.baijiahao.platform.logger'), pytest.raises(ValueError, match='早于当前时间'):
            _run(p._set_schedule_publish(page, dt))

    def test_beyond_7_days_raises(self):
        p = _mk_platform()
        page = _mk_page()
        dt = datetime.now(ZoneInfo('Asia/Shanghai')) + timedelta(days=8)
        with patch('impl.baijiahao.platform.logger'), pytest.raises(ValueError, match='7 天限制'):
            _run(p._set_schedule_publish(page, dt))

    def test_today_hour_not_greater_raises(self):
        p = _mk_platform()
        page = _mk_page()
        now = datetime.now(ZoneInfo('Asia/Shanghai'))
        dt = now.replace(hour=now.hour, minute=0, second=0, microsecond=0)
        with patch('impl.baijiahao.platform.logger'), pytest.raises(ValueError, match='必须大于当前小时'):
            _run(p._set_schedule_publish(page, dt))

    def test_happy_path(self):
        p = _mk_platform()
        page = _mk_page()
        dt = datetime.now(ZoneInfo('Asia/Shanghai')) + timedelta(days=2)
        dt = dt.replace(hour=10, minute=30, second=0, microsecond=0)
        schedule_btn = page.get_by_role('button', name='定时发布', exact=True)
        schedule_btn.click = AsyncMock()
        dialog = page.locator("div[role='dialog']")
        confirm_btn = MagicMock()
        confirm_btn.click = AsyncMock()
        dialog.get_by_role = MagicMock(return_value=confirm_btn)
        with patch.object(p, '_pick_schedule_option', AsyncMock()) as pso, \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._set_schedule_publish(page, dt))
        schedule_btn.click.assert_awaited_once()
        page.wait_for_selector.assert_any_await('#select-date', timeout=5000)
        assert pso.await_count == 3
        labels = [c.args[2] for c in pso.await_args_list]
        assert labels == [f'{dt.month}月{dt.day}日', f'{dt.hour}点', f'{dt.minute}分']
        confirm_btn.click.assert_awaited_once()


class TestPickScheduleOption:
    def test_minute_arrowdown(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value='select-minute_list_0')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._pick_schedule_option(page, '#select-minute', '25分'))
        downs = [c for c in page.keyboard.press.call_args_list if c.args[0] == 'ArrowDown']
        assert len(downs) == 25
        page.keyboard.press.assert_any_await('Enter')

    def test_hour_arrowup(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value='select-hour_list_10')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._pick_schedule_option(page, '#select-hour', '5点'))
        ups = [c for c in page.keyboard.press.call_args_list if c.args[0] == 'ArrowUp']
        assert len(ups) == 5
        page.keyboard.press.assert_any_await('Enter')

    def test_expanded_wait_timeout_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=None)
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('expanded wait slow'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._pick_schedule_option(page, '#select-hour', '5点'))
        page.wait_for_timeout.assert_any_await(500)
        page.keyboard.press.assert_any_await('Enter')

    def test_no_active_id_uses_zero(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=None)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._pick_schedule_option(page, '#select-minute', '30分'))
        downs = [c for c in page.keyboard.press.call_args_list if c.args[0] == 'ArrowDown']
        assert len(downs) == 30

    def test_day_label_clamped(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value='select-date_list_0')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._pick_schedule_option(page, '#select-date', '8月25日'))  # 无异常即通过
        page.keyboard.press.assert_any_await('Enter')


# ── 封面: _set_cover(双 cover-container) ────────────────────────────────

class TestSetCover:
    def _mk_containers(self, page, n=2):
        containers = page.locator("div[class*='coverWrap'] > div[class*='cover-container']")
        containers.count = AsyncMock(return_value=n)
        leaves = [_mk_leaf() for _ in range(n)]
        containers.nth = MagicMock(side_effect=lambda i: leaves[i])
        for lf in leaves:
            lf.click = AsyncMock()
        return containers, leaves

    def _mk_modal(self, page):
        page.wait_for_selector = AsyncMock()
        file_in = page.locator("div.cheetah-modal:visible input[type='file']")
        file_in.count = AsyncMock(return_value=1)
        file_in.first.set_input_files = AsyncMock()
        confirm = page.locator(
            "div.cheetah-modal:visible button.cheetah-btn-primary:has-text('确定')"
        )
        confirm.count = AsyncMock(return_value=1)
        confirm.first.click = AsyncMock()
        return file_in.first, confirm.first

    def test_both_covers_set(self):
        p = _mk_platform()
        page = _mk_page()
        _containers, leaves = self._mk_containers(page)
        file_in, confirm = self._mk_modal(page)
        l1 = _mk_img_file('t35_bjh_l.png')
        p1 = _mk_img_file('t35_bjh_p.png')
        try:
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.baijiahao.platform.logger'):
                _run(p._set_cover(page, l1, p1))
            leaves[0].click.assert_awaited_once()
            leaves[1].click.assert_awaited_once()
            assert file_in.set_input_files.await_count == 2
            assert confirm.click.await_count == 2
        finally:
            for f in (l1, p1):
                import os as _os
                _os.remove(f)

    def test_missing_landscape_skips(self):
        p = _mk_platform()
        page = _mk_page()
        _containers, leaves = self._mk_containers(page)
        _file_in, _confirm = self._mk_modal(page)
        p1 = _mk_img_file('t35_bjh_p.png')
        try:
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.baijiahao.platform.logger'):
                _run(p._set_cover(page, None, p1))
            leaves[0].click.assert_not_awaited()
            leaves[1].click.assert_awaited_once()
        finally:
            import os as _os
            _os.remove(p1)

    def test_not_exists_file_skips(self):
        p = _mk_platform()
        page = _mk_page()
        _containers, leaves = self._mk_containers(page)
        _file_in, _confirm = self._mk_modal(page)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._set_cover(page, '/no/such/l.png', '/no/such/p.png'))
        leaves[0].click.assert_not_awaited()
        leaves[1].click.assert_not_awaited()

    def test_container_shortage_warns(self):
        p = _mk_platform()
        page = _mk_page()
        _containers, leaves = self._mk_containers(page, n=1)
        file_in, _confirm = self._mk_modal(page)
        l1 = _mk_img_file('t35_bjh_l.png')
        p1 = _mk_img_file('t35_bjh_p.png')
        try:
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.baijiahao.platform.logger'):
                _run(p._set_cover(page, l1, p1))
            leaves[0].click.assert_awaited_once()   # 第 1 个正常
            assert file_in.set_input_files.await_count == 1  # 第 2 个 idx>=total 跳过
        finally:
            import os as _os
            for f in (l1, p1):
                _os.remove(f)

    def test_no_confirm_button_warns(self):
        p = _mk_platform()
        page = _mk_page()
        _containers, leaves = self._mk_containers(page)
        page.wait_for_selector = AsyncMock()
        file_in = page.locator("div.cheetah-modal:visible input[type='file']")
        file_in.count = AsyncMock(return_value=1)
        file_in.first.set_input_files = AsyncMock()
        confirm = page.locator(
            "div.cheetah-modal:visible button.cheetah-btn-primary:has-text('确定')"
        )
        confirm.count = AsyncMock(return_value=0)
        l1 = _mk_img_file('t35_bjh_l.png')
        p1 = _mk_img_file('t35_bjh_p.png')
        try:
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.baijiahao.platform.logger'):
                _run(p._set_cover(page, l1, p1))
            leaves[0].click.assert_awaited_once()
            leaves[1].click.assert_awaited_once()
            confirm.first.click.assert_not_awaited()
        finally:
            import os as _os
            for f in (l1, p1):
                _os.remove(f)

    def test_click_exception_non_fatal(self):
        p = _mk_platform()
        page = _mk_page()
        _containers, leaves = self._mk_containers(page)
        leaves[0].click = AsyncMock(side_effect=TimeoutError('modal not open'))
        file_in, confirm = self._mk_modal(page)
        l1 = _mk_img_file('t35_bjh_l.png')
        p1 = _mk_img_file('t35_bjh_p.png')
        try:
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.baijiahao.platform.logger'):
                _run(p._set_cover(page, l1, p1))
            leaves[1].click.assert_awaited_once()  # 第 1 个失败不阻塞第 2 个
            assert file_in.set_input_files.await_count == 1
            confirm.click.assert_awaited_once()
        finally:
            import os as _os
            for f in (l1, p1):
                _os.remove(f)


# ── 创作声明: _set_creation_declaration(必选+补充) ─────────────────────

class TestSetCreationDeclaration:
    def test_both_empty_returns(self):
        p = _mk_platform()
        page = _mk_page()
        _run(p._set_creation_declaration(page))
        page.locator.assert_not_called()

    def test_no_input_returns(self):
        p = _mk_platform()
        page = _mk_page()
        decl_input = page.locator("input[placeholder='请选择创作声明']")
        decl_input.count = AsyncMock(return_value=0)
        with patch('impl.baijiahao.platform.logger'):
            _run(p._set_creation_declaration(page, '原创', 'AI生成'))
        decl_input.click.assert_not_awaited()

    def test_happy_both_selected(self):
        p = _mk_platform()
        page = _mk_page()
        decl_input = page.locator("input[placeholder='请选择创作声明']")
        decl_input.count = AsyncMock(return_value=1)
        decl_input.click = AsyncMock()
        modal = page.get_by_role('dialog', name='创作声明')
        modal.wait_for = AsyncMock()
        subs = _sub_locators(modal)
        modal.locator("div.flex.items-center.cursor-pointer")
        rows_sel = "div.flex.items-center.cursor-pointer"
        row0 = _mk_leaf()
        row0.inner_text = AsyncMock(return_value='原创')
        row1 = _mk_leaf()
        row1.inner_text = AsyncMock(return_value='AI生成')
        subs[rows_sel].count = AsyncMock(return_value=2)
        subs[rows_sel].nth = MagicMock(side_effect=lambda i: [row0, row1][i])
        radio0 = MagicMock()
        radio0.click = AsyncMock()
        radio1 = MagicMock()
        radio1.click = AsyncMock()
        row0.locator = MagicMock(return_value=radio0)
        row1.locator = MagicMock(return_value=radio1)
        confirm_sel = "button.cheetah-btn-primary:has-text('确定')"
        modal.locator(confirm_sel)
        confirm = subs[confirm_sel]
        confirm.count = AsyncMock(return_value=1)
        confirm.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._set_creation_declaration(page, '原创', 'AI生成'))
        decl_input.click.assert_awaited_once()
        modal.wait_for.assert_awaited_once_with(state='visible', timeout=5000)
        radio0.click.assert_awaited_once_with(force=True)
        radio1.click.assert_awaited_once_with(force=True)
        confirm.click.assert_awaited_once()

    def test_not_found_still_confirms(self):
        p = _mk_platform()
        page = _mk_page()
        decl_input = page.locator("input[placeholder='请选择创作声明']")
        decl_input.count = AsyncMock(return_value=1)
        modal = page.get_by_role('dialog', name='创作声明')
        modal.wait_for = AsyncMock()
        subs = _sub_locators(modal)
        rows_sel = "div.flex.items-center.cursor-pointer"
        modal.locator(rows_sel)
        row0 = _mk_leaf()
        row0.inner_text = AsyncMock(return_value='不匹配的声明')
        subs[rows_sel].count = AsyncMock(return_value=1)
        subs[rows_sel].nth = MagicMock(side_effect=lambda i: row0)
        confirm_sel = "button.cheetah-btn-primary:has-text('确定')"
        modal.locator(confirm_sel)
        confirm = subs[confirm_sel]
        confirm.count = AsyncMock(return_value=1)
        confirm.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._set_creation_declaration(page, '原创', 'AI生成'))
        row0.locator.assert_not_called()
        confirm.click.assert_awaited_once()

    def test_exception_non_fatal(self):
        p = _mk_platform()
        page = _mk_page()
        decl_input = page.locator("input[placeholder='请选择创作声明']")
        decl_input.count = AsyncMock(return_value=1)
        decl_input.click = AsyncMock(side_effect=TimeoutError('dialog failed'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.baijiahao.platform.logger'):
            _run(p._set_creation_declaration(page, '原创', ''))  # 无异常即通过
