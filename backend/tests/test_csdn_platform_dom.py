"""CSDN platform.py DOM 交互层契约测试（T35 第二期）。

覆盖 csdn/platform.py 深水区(491 stmts, 基线 22%):
- 纯函数: _parse_cookie_to_storage_state(多子域映射/secure/httpOnly/SESSION 复制)
- 登录/校验/同步: login(用户信息卡检测/失败留浏览器) / check_cookie(卡片 count)
  / sync_profile(evaluate 抓取+label_map 组装) / _login_stats_fn / open_creator_center
- 编排: publish_video(文件×账号矩阵/横版封面优先) / _upload_single_video 全流程
  (cookie 失效检测/截图/提交成功与否/storage_state 回写)
- DOM 辅助: _upload_video_file(双策略) / _wait_upload_complete(成功/失败/轮询)
  / _set_thumbnail(封面 input 双策略/裁剪确认多策略/JS evaluate 兜底/异常 Escape)
  / _fill_title(30 截断) / _fill_desc(150 截断) / _fill_tags(解析/上限/回车激活)
  / _set_recommend / _click_submit(URL 跳转判定/JS 兜底/超时按成功)
"""
import asyncio
import sys
import time as _time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.csdn.platform import CSDN_MAX_DESC_LEN, CSDN_MAX_TITLE_LEN, CsdnPlatform


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return CsdnPlatform()


def _mk_leaf():
    loc = MagicMock()
    loc.count = AsyncMock(return_value=0)
    loc.click = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.fill = AsyncMock()
    loc.set_input_files = AsyncMock()
    loc.evaluate = AsyncMock(return_value='')
    loc.press = AsyncMock()
    loc.press_sequentially = AsyncMock()
    loc.is_visible = AsyncMock(return_value=True)
    loc.inner_text = AsyncMock(return_value='')
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
    subs = {}

    def _reg(sel, **kw):
        if sel not in subs:
            subs[sel] = _mk_locator()
        return subs[sel]

    owner.locator = MagicMock(side_effect=_reg)
    return subs


@contextmanager
def _mk_browser_chain(platform, urls=None):
    page = _mk_page(urls=urls)
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
        page.url = 'https://mp.csdn.net/mp_others/creation/videoUpload'
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
    page.screenshot = AsyncMock()
    page.close = AsyncMock()
    page.on = MagicMock()
    page.input_value = AsyncMock()
    page.context = MagicMock()
    locators = {}

    def locator(sel, **kw):
        if sel not in locators:
            locators[sel] = _mk_locator()
        return locators[sel]

    page.locator = MagicMock(side_effect=locator)
    page.locators = locators
    return page


def _loc(page, sel):
    """预注册 selector 并返回稳定 locator(page.locators[sel])。"""
    page.locator(sel)
    return page.locators[sel]


def _mk_cookie_file(name='t35_csdn_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


def _mk_img_file(name='t35_csdn_img.png', size=1024):
    import os as _os
    import tempfile as _tf
    fd, path = _tf.mkstemp(prefix=name, suffix='.png')
    with _os.fdopen(fd, 'wb') as f:
        f.write(b'x' * size)
    return path


# ── 纯函数: cookie 解析(多子域映射) ─────────────────────────────────────

class TestParseCookieToStorageState:
    def test_happy_parse(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state(
            'SESSION=s1; https_waf_cookie=w1; BAIDU_ID=x'
        )
        assert origins == []
        sessions = [c for c in cookies if c['name'] == 'SESSION']
        assert sorted(c['domain'] for c in sessions) == ['.csdn.net', 'msg.csdn.net']
        assert all(c['httpOnly'] is True for c in sessions)
        by_name = {c['name']: c for c in cookies}
        assert by_name['https_waf_cookie']['domain'] == 'passport.csdn.net'
        assert by_name['https_waf_cookie']['secure'] is True
        assert by_name['https_waf_cookie']['httpOnly'] is True
        assert by_name['BAIDU_ID']['secure'] is False
        assert by_name['BAIDU_ID']['httpOnly'] is False

    def test_session_duplicated_to_msg_domain(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('SESSION=s1')
        domains = sorted({c['domain'] for c in cookies})
        assert domains == ['.csdn.net', 'msg.csdn.net']
        assert len(cookies) == 2

    def test_domain_map_special(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('bc_bot_session=b; _bl_uid=u')
        by_name = {c['name']: c for c in cookies}
        assert by_name['bc_bot_session']['domain'] == '.blog.csdn.net'
        assert by_name['_bl_uid']['domain'] == 'i.csdn.net'

    def test_skips_invalid_pairs(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state('a=1; ; novalue')
        assert [c['name'] for c in cookies] == ['a']

    def test_empty(self):
        p = _mk_platform()
        assert p._parse_cookie_to_storage_state('') == ([], [])


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLogin:
    def test_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.csdn.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.csdn.platform.logger'):
            _run(p.login('u1', MagicMock(), account_id='acc1'))
        info_card = _loc(page, 'div.user-info-box').first
        info_card.wait_for.assert_awaited_once_with(timeout=999999999)
        slr.assert_awaited_once()
        kwargs = slr.await_args.kwargs
        assert kwargs['platform_id'] == 15
        assert kwargs['account_id'] == 'acc1'
        page.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    def test_wait_timeout_keeps_browser(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
             patch('impl.csdn.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.csdn.platform.logger'):
            page.locator('div.user-info-box')  # 预注册
            info_card = _loc(page, 'div.user-info-box').first
            info_card.wait_for = AsyncMock(side_effect=TimeoutError('user closed'))
            with pytest.raises(TimeoutError):
                _run(p.login('u1', MagicMock()))
        slr.assert_not_awaited()
        page.close.assert_awaited_once()
        context_side = browser  # 留浏览器给用户看现场
        assert context_side.close.call_count == 0  # browser 不关
        browser.close.assert_not_awaited()


class TestCheckCookie:
    def test_valid(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            page.locator('div.user-info-box')  # 预注册
            profile = _loc(page, 'div.user-info-box').first
            profile.count = AsyncMock(return_value=1)
            assert _run(p.check_cookie('ck.json')) is True
        page.close.assert_awaited_once()

    def test_expired(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            page.locator('div.user-info-box')  # 预注册
            profile = _loc(page, 'div.user-info-box').first
            profile.count = AsyncMock(return_value=0)
            assert _run(p.check_cookie('ck.json')) is False

    def test_load_state_timeout_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            page.wait_for_load_state = AsyncMock(side_effect=TimeoutError('slow'))
            page.locator('div.user-info-box')  # 预注册
            profile = _loc(page, 'div.user-info-box').first
            profile.count = AsyncMock(return_value=1)
            assert _run(p.check_cookie('ck.json')) is True


class TestSyncProfile:
    def test_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.csdn.platform.logger'):
            page.evaluate = AsyncMock(return_value={
                'name': '博主', 'avatar': 'http://a.png',
                'stats': [
                    {'name': '原创', 'num': '12'},
                    {'name': '粉丝数', 'num': '1,234'},
                    {'name': '博客积分', 'num': '50'},
                    {'name': '累计收益', 'num': '¥ 66'},
                    {'name': '总阅读量', 'num': '9.5'},
                ],
            })
            res = _run(p.sync_profile('ck.json'))
        assert res['name'] == '博主'
        assert res['avatar'] == 'http://a.png'
        by_name = {s['NAME']: s for s in res['stats']}
        assert by_name['原创']['COUNT'] == 12
        assert by_name['粉丝数']['COUNT'] == 1234      # 千分位
        assert by_name['累计收益']['COUNT'] == 66       # ¥ 剥离
        assert by_name['总阅读量']['COUNT'] == 9        # '9.5' → int(float) 9
        assert len(res['stats']) == 5
        page.close.assert_awaited_once()

    def test_unknown_labels_dropped_and_sorted(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.csdn.platform.logger'):
            page.evaluate = AsyncMock(return_value={
                'name': '', 'avatar': '',
                'stats': [
                    {'name': '未知项', 'num': '9'},
                    {'name': '累计收益', 'num': 'abc'},
                    {'name': '原创', 'num': '3'},
                ],
            })
            res = _run(p.sync_profile('ck.json'))
        # sync_profile 保持 evaluate 原始顺序(不排序),过滤未知项
        assert [s['NAME'] for s in res['stats']] == ['累计收益', '原创']
        assert res['stats'][0]['COUNT'] == 0  # 非法数字 → 0

    def test_wait_selector_timeout_still_scrapes(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.csdn.platform.logger'):
            page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
            page.evaluate = AsyncMock(return_value={
                'name': 'n', 'avatar': 'a', 'stats': [{'name': '原创', 'num': '1'}],
            })
            res = _run(p.sync_profile('ck.json'))
        assert res['name'] == 'n'

    def test_evaluate_error_returns_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.csdn.platform.logger'):
            page.evaluate = AsyncMock(side_effect=RuntimeError('js fail'))
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': []}


class TestLoginStatsFn:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {'name': '原创', 'num': '3'},
            {'name': '粉丝数', 'num': '4,000'},
        ])
        with patch('impl.csdn.platform.logger'):
            stats = _run(p._login_stats_fn(page, 'acc1'))
        assert [s['NAME'] for s in stats] == ['原创', '粉丝数']
        assert stats[1]['COUNT'] == 4000

    def test_wait_timeout_continues(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        page.evaluate = AsyncMock(return_value=[])
        with patch('impl.csdn.platform.logger'):
            assert _run(p._login_stats_fn(page, 'acc1')) == []


class TestOpenCreatorCenter:
    def test_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_csdn_occ.json')
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.csdn.platform.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl.csdn.platform.create_context_sync', return_value=context) as ccs:
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
        cookie = _mk_cookie_file('t35_csdn_occ2.json')
        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.csdn.platform.create_browser_sync', return_value=browser), \
                 patch('impl.csdn.platform.create_context_sync', return_value=context):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)


# ── 编排: publish_video / _upload_single_video ──────────────────────────

class TestPublishVideo:
    def test_multi_file_multi_account(self):
        p = _mk_platform()
        dates = [1, 2]
        with patch.object(p, '_upload_single_video', AsyncMock()) as usv, \
             patch('impl.csdn.platform.parse_schedule_time', return_value=dates), \
             patch('impl.csdn.platform.get_account_name_by_cookie_file', return_value='号'), \
             patch('impl.csdn.platform.logger'):
            res = p.publish_video(
                title='T', files=['/v/a.mp4', '/v/b.mp4'],
                account_file=['a.json', 'b.json'], tags=['x'], desc='简介',
                thumbnail_landscape_path='/l.png', thumbnail_portrait_path='/p.png',
            )
        assert res is True
        assert usv.await_count == 4
        calls = usv.await_args_list
        assert [c.kwargs['file_path'] for c in calls] == ['/v/a.mp4', '/v/a.mp4', '/v/b.mp4', '/v/b.mp4']
        assert calls[0].kwargs['publish_date'] == 1
        assert calls[2].kwargs['publish_date'] == 2
        assert calls[0].kwargs['thumbnail_path'] == '/l.png'   # 横版优先
        assert calls[0].kwargs['account_file'].endswith('a.json')
        assert calls[0].kwargs['desc'] == '简介'

    def test_portrait_fallback_thumbnail(self):
        p = _mk_platform()
        with patch.object(p, '_upload_single_video', AsyncMock()) as usv, \
             patch('impl.csdn.platform.parse_schedule_time', return_value=[0]), \
             patch('impl.csdn.platform.get_account_name_by_cookie_file', return_value=''), \
             patch('impl.csdn.platform.logger'):
            p.publish_video(
                title='T', files=['/v/a.mp4'], account_file=['ck.json'],
                tags=[], thumbnail_landscape_path='', thumbnail_portrait_path='/p.png',
            )
        assert usv.await_args.kwargs['thumbnail_path'] == '/p.png'

    def test_non_list_schedule(self):
        p = _mk_platform()
        with patch.object(p, '_upload_single_video', AsyncMock()) as usv, \
             patch('impl.csdn.platform.parse_schedule_time', return_value=42), \
             patch('impl.csdn.platform.get_account_name_by_cookie_file', return_value=''), \
             patch('impl.csdn.platform.logger'):
            p.publish_video(title='T', files=['/v/a.mp4'], account_file=['ck.json'], tags=[])
        assert usv.await_args.kwargs['publish_date'] == 42


class TestUploadSingleVideo:
    @contextmanager
    def _mk_steps(self, p, page, submit=True):
        with patch.object(p, '_upload_video_file', AsyncMock()) as uvf, \
             patch.object(p, '_wait_upload_complete', AsyncMock()) as wuc, \
             patch.object(p, '_set_thumbnail', AsyncMock()) as st, \
             patch.object(p, '_fill_title', AsyncMock()) as ft, \
             patch.object(p, '_fill_desc', AsyncMock()) as fd, \
             patch.object(p, '_fill_tags', AsyncMock()) as ftg, \
             patch.object(p, '_set_recommend', AsyncMock()) as sr, \
             patch.object(p, '_click_submit', AsyncMock(return_value=submit)) as cs, \
             patch.object(p, 'close_browser', AsyncMock()) as cb, \
             patch('asyncio.sleep', AsyncMock()):
            yield uvf, wuc, st, ft, fd, ftg, sr, cs, cb

    def test_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             self._mk_steps(p, page) as (uvf, wuc, st, ft, fd, ftg, sr, cs, cb):
            _run(p._upload_single_video(
                title='标题', file_path='/v/a.mp4', tags=['x'], publish_date=0,
                account_file='/tmp/t35_ck.json', desc='简介', recommend=True,
                thumbnail_path='/v/cover.png',
            ))
        page.goto.assert_awaited_once()
        uvf.assert_awaited_once_with(page, '/v/a.mp4')
        wuc.assert_awaited_once()
        st.assert_awaited_once_with(page, '/v/cover.png')
        ft.assert_awaited_once_with(page, '标题')
        fd.assert_awaited_once_with(page, '简介')
        ftg.assert_awaited_once_with(page, ['x'])
        sr.assert_awaited_once_with(page)
        cs.assert_awaited_once()
        context.storage_state.assert_awaited_once_with(path='/tmp/t35_ck.json')
        cb.assert_awaited_once()

    def test_cookie_invalid_raises(self):
        p = _mk_platform()
        with _mk_browser_chain(p, urls=['https://mp.csdn.net/login?redirect=1']) as (_page, _ctx, _browser, _cb, _cc), \
             patch('impl.csdn.platform.logger'), \
             pytest.raises(RuntimeError, match='cookie 失效'):
            _run(p._upload_single_video(
                title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                account_file='/tmp/t35_ck.json',
            ))

    def test_submit_fail_still_updates_cookie(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc), \
             patch('impl.csdn.platform.logger'), \
             self._mk_steps(p, page, submit=False) as (_uvf, _wuc, _st, _ft, _fd, _ftg, _sr, cs, cb):
            _run(p._upload_single_video(
                title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                account_file='/tmp/t35_ck.json',
            ))
        cs.assert_awaited_once()
        context.storage_state.assert_awaited_once()
        cb.assert_awaited_once()

    def test_no_thumbnail_skips(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             self._mk_steps(p, page) as (_uvf, _wuc, st, _ft, _fd, _ftg, _sr, _cs, _cb):
            _run(p._upload_single_video(
                title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                account_file='/tmp/t35_ck.json', thumbnail_path=None,
            ))
        st.assert_not_awaited()


# ── 上传视频文件: _upload_video_file(双策略) ─────────────────────────────

class TestUploadVideoFile:
    def test_strategy1_video_input(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.csdn.platform.logger'):
            _run(p._upload_video_file(page, '/v/a.mp4'))
        video_sel = ('input[type="file"][accept*="mp4"], '
                     'input[type="file"][accept*="video"], '
                     'input[type="file"][accept*="mov"]')
        candidate = _loc(page, video_sel).first
        candidate.wait_for.assert_awaited_once_with(state='attached', timeout=10000)
        candidate.set_input_files.assert_awaited_once_with('/v/a.mp4')

    def test_strategy2_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        video_sel = ('input[type="file"][accept*="mp4"], '
                     'input[type="file"][accept*="video"], '
                     'input[type="file"][accept*="mov"]')
        candidate = _loc(page, video_sel).first
        candidate.wait_for = AsyncMock(side_effect=TimeoutError('no video input'))
        with patch('impl.csdn.platform.logger'):
            _run(p._upload_video_file(page, '/v/a.mp4'))
        fb = _loc(page, 'input[type="file"]').first
        fb.wait_for.assert_awaited_once_with(state='attached', timeout=5000)
        fb.set_input_files.assert_awaited_once_with('/v/a.mp4')

    def test_no_input_raises(self):
        p = _mk_platform()
        page = _mk_page()
        video_sel = ('input[type="file"][accept*="mp4"], '
                     'input[type="file"][accept*="video"], '
                     'input[type="file"][accept*="mov"]')
        _loc(page, video_sel).first.wait_for = AsyncMock(side_effect=TimeoutError('a'))
        _loc(page, 'input[type="file"]').first.wait_for = AsyncMock(side_effect=TimeoutError('b'))
        with patch('impl.csdn.platform.logger'), pytest.raises(RuntimeError, match='未找到视频上传 input'):
            _run(p._upload_video_file(page, '/v/a.mp4'))
        page.screenshot.assert_awaited()


# ── 上传完成等待: _wait_upload_complete ─────────────────────────────────

class TestWaitUploadComplete:
    def test_done_immediately(self):
        p = _mk_platform()
        page = _mk_page()
        done = _loc(page, '.gement li.text:has-text("上传成功")')
        done.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            _run(p._wait_upload_complete(page))  # 无异常即返回

    def test_fail_raises(self):
        p = _mk_platform()
        page = _mk_page()
        done = _loc(page, '.gement li.text:has-text("上传成功")')
        done.count = AsyncMock(return_value=0)
        fail_sel = '.gement li:has-text("上传失败"), text=上传失败'
        fail = _loc(page, fail_sel)
        fail.count = AsyncMock(return_value=1)
        fail.first.is_visible = AsyncMock(return_value=True)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'), pytest.raises(RuntimeError, match='视频上传失败'):
            _run(p._wait_upload_complete(page))

    def test_polls_until_done(self):
        p = _mk_platform()
        page = _mk_page()
        done = _loc(page, '.gement li.text:has-text("上传成功")')
        done.count = AsyncMock(side_effect=[0, 0, 1])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            _run(p._wait_upload_complete(page))
        assert done.count.await_count == 3

    def test_check_exception_continues(self):
        p = _mk_platform()
        page = _mk_page()
        done = _loc(page, '.gement li.text:has-text("上传成功")')
        done.count = AsyncMock(side_effect=[TimeoutError('dom shake'), 1])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            _run(p._wait_upload_complete(page))
        assert done.count.await_count == 2


# ── 封面: _set_thumbnail(双策略/确认多策略/异常 Escape) ──────────────────

class TestSetThumbnail:
    def test_missing_file_returns(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.csdn.platform.logger'):
            _run(p._set_thumbnail(page, '/no/such.png'))
        page.locator.assert_not_called()

    def test_happy_path(self):
        p = _mk_platform()
        page = _mk_page()
        img = _mk_img_file('t35_csdn_cover.png')
        try:
            cover_sel = ('.essential-uploader input[type="file"][accept*="png"], '
                         '.essential-uploader input[type="file"][accept*="image"], '
                         '.essential-uploader input[type="file"]')
            candidate = _loc(page, cover_sel).first
            candidate.wait_for = AsyncMock()
            candidate.set_input_files = AsyncMock()
            confirm_sel = ('.dialog-footer .el-button--primary:has-text("确认"), '
                           '.el-dialog__footer .el-button--primary:has-text("确认")')
            confirm = _loc(page, confirm_sel).first
            confirm.wait_for = AsyncMock()
            confirm.click = AsyncMock()
            still_open = _loc(page, '.el-dialog__wrapper:not([style*="display: none"])')
            still_open.count = AsyncMock(return_value=0)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.csdn.platform.logger'):
                _run(p._set_thumbnail(page, img))
            candidate.set_input_files.assert_awaited_once_with(img)
            confirm.click.assert_awaited_once_with(timeout=5000)
        finally:
            import os as _os
            _os.remove(img)

    def test_click_fails_then_js_evaluate(self):
        p = _mk_platform()
        page = _mk_page()
        img = _mk_img_file('t35_csdn_cover.png')
        try:
            cover_sel = ('.essential-uploader input[type="file"][accept*="png"], '
                         '.essential-uploader input[type="file"][accept*="image"], '
                         '.essential-uploader input[type="file"]')
            candidate = _loc(page, cover_sel).first
            candidate.wait_for = AsyncMock()
            candidate.set_input_files = AsyncMock()
            confirm_sel = ('.dialog-footer .el-button--primary:has-text("确认"), '
                           '.el-dialog__footer .el-button--primary:has-text("确认")')
            confirm = _loc(page, confirm_sel).first
            confirm.wait_for = AsyncMock()
            confirm.click = AsyncMock(side_effect=[TimeoutError('a'), TimeoutError('b')])
            confirm.evaluate = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.csdn.platform.logger'):
                _run(p._set_thumbnail(page, img))
            assert confirm.click.await_count == 2
            confirm.evaluate.assert_awaited_once_with('el => el.click()')
        finally:
            import os as _os
            _os.remove(img)

    def test_no_crop_dialog(self):
        p = _mk_platform()
        page = _mk_page()
        img = _mk_img_file('t35_csdn_cover.png')
        try:
            cover_sel = ('.essential-uploader input[type="file"][accept*="png"], '
                         '.essential-uploader input[type="file"][accept*="image"], '
                         '.essential-uploader input[type="file"]')
            candidate = _loc(page, cover_sel).first
            candidate.wait_for = AsyncMock()
            candidate.set_input_files = AsyncMock()
            confirm_sel = ('.dialog-footer .el-button--primary:has-text("确认"), '
                           '.el-dialog__footer .el-button--primary:has-text("确认")')
            confirm = _loc(page, confirm_sel).first
            confirm.wait_for = AsyncMock(side_effect=TimeoutError('no dialog'))
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.csdn.platform.logger'):
                _run(p._set_thumbnail(page, img))
            candidate.set_input_files.assert_awaited_once()
        finally:
            import os as _os
            _os.remove(img)

    def test_cover_input_not_found_falls_back(self):
        p = _mk_platform()
        page = _mk_page()
        img = _mk_img_file('t35_csdn_cover.png')
        try:
            cover_sel = ('.essential-uploader input[type="file"][accept*="png"], '
                         '.essential-uploader input[type="file"][accept*="image"], '
                         '.essential-uploader input[type="file"]')
            _loc(page, cover_sel).first.wait_for = AsyncMock(side_effect=TimeoutError('none'))
            fb_sel = ('input[type="file"][accept*="png"], '
                      'input[type="file"][accept*="jpg"], '
                      'input[type="file"][accept*="image"]')
            fb = _loc(page, fb_sel).first
            fb.wait_for = AsyncMock()
            fb.set_input_files = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.csdn.platform.logger'):
                _run(p._set_thumbnail(page, img))
            fb.set_input_files.assert_awaited_once_with(img)
        finally:
            import os as _os
            _os.remove(img)


# ── 标题/简介/标签/推荐 ─────────────────────────────────────────────────

class TestFillTitle:
    def test_empty_returns(self):
        p = _mk_platform()
        page = _mk_page()
        _run(p._fill_title(page, ''))
        page.locator.assert_not_called()

    def test_truncates_to_30(self):
        p = _mk_platform()
        page = _mk_page()
        title_input = _loc(page, '#title.el-input__inner, input#title, .Management-content input.el-input__inner').first
        title_input.wait_for = AsyncMock()
        title_input.click = AsyncMock()
        title_input.fill = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            _run(p._fill_title(page, '长' * 50))
        expected = '长' * CSDN_MAX_TITLE_LEN
        assert title_input.fill.await_count == 2  # 先清空再填入
        title_input.fill.assert_awaited_with(expected)


class TestFillDesc:
    def test_empty_returns(self):
        p = _mk_platform()
        page = _mk_page()
        _run(p._fill_desc(page, ''))
        page.locator.assert_not_called()

    def test_truncates_to_150(self):
        p = _mk_platform()
        page = _mk_page()
        desc_input = _loc(page, '#description.el-textarea__inner, textarea#description, .VideoManagement_description textarea.el-textarea__inner').first
        desc_input.wait_for = AsyncMock()
        desc_input.click = AsyncMock()
        desc_input.fill = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            _run(p._fill_desc(page, 'x' * 200))
        expected = 'x' * CSDN_MAX_DESC_LEN
        desc_input.fill.assert_awaited_with(expected)


class TestFillTags:
    def test_parse_and_limits(self):
        p = _mk_platform()
        page = _mk_page()
        tag_input = _loc(page, '.video_mark_selection_box_header input.el-input__inner').first
        tag_input.wait_for = AsyncMock()
        tag_input.click = AsyncMock()
        tag_input.fill = AsyncMock()
        tag_input.press_sequentially = AsyncMock()
        tag_input.press = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            _run(p._fill_tags(page, ['#旅行, 美食', '科技，#AI', '超级超级长的标签', '第四个']))
        # 解析: [旅行, 美食, 科技, AI, 超级超级长的标签, 第四个] → 前 3 个,每个 ≤10 字
        assert tag_input.press_sequentially.await_count == 3
        tags_typed = [c.args[0] for c in tag_input.press_sequentially.await_args_list]
        assert tags_typed == ['旅行', '美食', '科技']
        assert tag_input.press.await_count == 3  # 每个 Enter 激活
        tag_input.press.assert_any_await('Enter')

    def test_empty_returns(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.csdn.platform.logger'):
            _run(p._fill_tags(page, []))
        page.locator.assert_not_called()

    def test_no_input_returns(self):
        p = _mk_platform()
        page = _mk_page()
        tag_input = _loc(page, '.video_mark_selection_box_header input.el-input__inner').first
        tag_input.wait_for = AsyncMock(side_effect=TimeoutError('no tag input'))
        with patch('impl.csdn.platform.logger'):
            _run(p._fill_tags(page, ['旅行']))
        tag_input.click.assert_not_awaited()

    def test_per_tag_exception_continues(self):
        p = _mk_platform()
        page = _mk_page()
        tag_input = _loc(page, '.video_mark_selection_box_header input.el-input__inner').first
        tag_input.wait_for = AsyncMock()
        tag_input.click = AsyncMock(side_effect=[None, TimeoutError('typing fail')])
        tag_input.fill = AsyncMock()
        tag_input.press_sequentially = AsyncMock()
        tag_input.press = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            _run(p._fill_tags(page, ['旅行', '美食']))
        assert tag_input.press_sequentially.await_count == 1  # 第 2 个失败跳过


class TestSetRecommend:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, '.el-radio:has-text("是否被推荐")').first
        radio.wait_for = AsyncMock()
        radio.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            _run(p._set_recommend(page))
        radio.click.assert_awaited_once()

    def test_failure_non_fatal(self):
        p = _mk_platform()
        page = _mk_page()
        radio = _loc(page, '.el-radio:has-text("是否被推荐")').first
        radio.wait_for = AsyncMock(side_effect=TimeoutError('no radio'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            _run(p._set_recommend(page))  # 无异常即通过


# ── 发布: _click_submit(URL 跳转判定) ───────────────────────────────────

class TestClickSubmit:
    def test_redirect_after_click(self):
        p = _mk_platform()
        page = _mk_page(urls=[
            'https://mp.csdn.net/mp_others/creation/videoUpload',
            'https://mp.csdn.net/mp_others/creation/articleList',
        ])
        publish_btn = _loc(page, 'button.form-button.el-button--primary:has-text("发布")').first
        publish_btn.wait_for = AsyncMock()
        publish_btn.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            assert _run(p._click_submit(page)) is True
        publish_btn.click.assert_awaited_once_with(timeout=5000)

    def test_click_fails_then_js_evaluate(self):
        p = _mk_platform()
        page = _mk_page(urls=[
            'https://mp.csdn.net/mp_others/creation/videoUpload',
            'https://mp.csdn.net/mp_others/creation/articleList',
        ])
        publish_btn = _loc(page, 'button.form-button.el-button--primary:has-text("发布")').first
        publish_btn.wait_for = AsyncMock()
        publish_btn.click = AsyncMock(side_effect=[TimeoutError('a'), TimeoutError('b')])
        publish_btn.evaluate = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            assert _run(p._click_submit(page)) is True
        publish_btn.evaluate.assert_awaited_once_with('el => el.click()')

    def test_both_fail_returns_false(self):
        p = _mk_platform()
        page = _mk_page(urls=[
            'https://mp.csdn.net/mp_others/creation/videoUpload',
            'https://mp.csdn.net/mp_others/creation/videoUpload',  # 不跳转
        ])
        publish_btn = _loc(page, 'button.form-button.el-button--primary:has-text("发布")').first
        publish_btn.wait_for = AsyncMock()
        publish_btn.click = AsyncMock(side_effect=[TimeoutError('a'), TimeoutError('b')])
        publish_btn.evaluate = AsyncMock(side_effect=TimeoutError('js fail'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            assert _run(p._click_submit(page)) is False

    def test_no_redirect_treated_as_success(self):
        p = _mk_platform()
        page = _mk_page()  # url 固定不跳转
        publish_btn = _loc(page, 'button.form-button.el-button--primary:has-text("发布")').first
        publish_btn.wait_for = AsyncMock()
        publish_btn.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            assert _run(p._click_submit(page)) is True

    def test_exception_returns_false(self):
        p = _mk_platform()
        page = _mk_page()
        publish_btn = _loc(page, 'button.form-button.el-button--primary:has-text("发布")').first
        publish_btn.wait_for = AsyncMock(side_effect=TimeoutError('no btn'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.csdn.platform.logger'):
            assert _run(p._click_submit(page)) is False


# ── 补充防御分支 ─────────────────────────────────────────────────────────

class TestDefensiveBranches:
    def test_sync_profile_empty_result(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('impl.csdn.platform.logger'):
            page.evaluate = AsyncMock(return_value={})
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': []}

    def test_open_creator_center_close_error_swallowed(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t35_csdn_occ3.json')
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError('close boom'))
        context = MagicMock()
        page = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.csdn.platform.create_browser_sync', return_value=browser), \
                 patch('impl.csdn.platform.create_context_sync', return_value=context):
                _run(p.open_creator_center(cookie.name))
                _time.sleep(0.2)  # 线程内 close 抛错被吞
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_upload_video_file_screenshot_error_continues(self):
        p = _mk_platform()
        page = _mk_page()
        page.screenshot = AsyncMock(side_effect=TimeoutError('shot fail'))
        video_sel = ('input[type="file"][accept*="mp4"], '
                     'input[type="file"][accept*="video"], '
                     'input[type="file"][accept*="mov"]')
        candidate = _loc(page, video_sel).first
        candidate.wait_for = AsyncMock()
        candidate.set_input_files = AsyncMock()
        with patch('impl.csdn.platform.logger'):
            _run(p._upload_video_file(page, '/v/a.mp4'))
        candidate.set_input_files.assert_awaited_once_with('/v/a.mp4')

    def test_set_thumbnail_fallback_failure_raises(self):
        p = _mk_platform()
        page = _mk_page()
        img = _mk_img_file('t35_csdn_cover.png')
        try:
            cover_sel = ('.essential-uploader input[type="file"][accept*="png"], '
                         '.essential-uploader input[type="file"][accept*="image"], '
                         '.essential-uploader input[type="file"]')
            _loc(page, cover_sel).first.wait_for = AsyncMock(side_effect=TimeoutError('a'))
            fb_sel = ('input[type="file"][accept*="png"], '
                      'input[type="file"][accept*="jpg"], '
                      'input[type="file"][accept*="image"]')
            _loc(page, fb_sel).first.wait_for = AsyncMock(side_effect=TimeoutError('b'))
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.csdn.platform.logger'):
                _run(p._set_thumbnail(page, img))  # RuntimeError 被外层 catch 吞掉(非致命)
            page.keyboard.press.assert_awaited_once_with('Escape')
            page.screenshot.assert_awaited()
        finally:
            import os as _os
            _os.remove(img)

    def test_thumbnail_dialog_close_polls(self):
        p = _mk_platform()
        page = _mk_page()
        img = _mk_img_file('t35_csdn_cover.png')
        try:
            cover_sel = ('.essential-uploader input[type="file"][accept*="png"], '
                         '.essential-uploader input[type="file"][accept*="image"], '
                         '.essential-uploader input[type="file"]')
            candidate = _loc(page, cover_sel).first
            candidate.wait_for = AsyncMock()
            candidate.set_input_files = AsyncMock()
            confirm_sel = ('.dialog-footer .el-button--primary:has-text("确认"), '
                           '.el-dialog__footer .el-button--primary:has-text("确认")')
            confirm = _loc(page, confirm_sel).first
            confirm.wait_for = AsyncMock()
            confirm.click = AsyncMock()
            still_open = _loc(page, '.el-dialog__wrapper:not([style*="display: none"])')
            still_open.count = AsyncMock(side_effect=[1, 0])  # 第 1 轮仍开,第 2 轮关闭
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.csdn.platform.logger'):
                _run(p._set_thumbnail(page, img))
            assert still_open.count.await_count == 2
        finally:
            import os as _os
            _os.remove(img)
