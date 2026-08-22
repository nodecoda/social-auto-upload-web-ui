"""抖音 platform.py DOM 交互层契约测试（T33）。

覆盖 publish_video 编排(T16b)之外的深水区:
- 登录/校验/同步: login(URL 变化事件) / check_cookie / sync_profile / open_creator_center
- 数据抓取: _login_stats_fn / _parse_cookie_to_storage_state
- 单视频上传: _upload_one_video 全流程(含 activities 拼接/dry_run/发布循环)
- 单图集上传: _upload_image_note 全流程(发布/dry_run)
- DOM 辅助: _fill_title_and_description / _set_schedule_time(8 步)
  _set_product_link / _set_thumbnail / _handle_auto_video_cover
  _set_image_cover / _set_image_mix / _select_music / _set_hotspot
  _set_tag(5 类型) / _set_location_tag / _set_declaration
- 纯函数: _count_hashtags / _validate_publish_params
"""
import asyncio
import os
import sys
import tempfile
import time as _time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from queue import Queue
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from conf import BASE_DIR
from impl.douyin.platform import DouyinPlatform


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return DouyinPlatform()


@contextmanager
def _mk_browser_chain(platform, urls=None):
    """create_browser/create_context 链的 mocks(以 contextmanager 形式,with 内生效)。

    page 使用 _mk_page() 的 locator 按 selector 分派,便于逐测试配置。
    urls: 可选 URL 序列(login 等需要观察 URL 变化的场景)。
    """
    page = _mk_page(urls=urls)
    page.wait_for_url = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.eval_on_selector = AsyncMock(return_value='')
    page.input_value = AsyncMock()
    page.locator('[class^="info"] > [class^="first-part"] div div.semi-switch').count = AsyncMock(return_value=0)
    page.locator("div[class^='container'] input").set_input_files = AsyncMock()
    page.get_by_text('扫码登录').wait_for = AsyncMock(side_effect=TimeoutError('no prompt'))
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
    """通用 fake page:locator 按 selector 分派到独立 MagicMock。

    urls: 可选 URL 序列(逐次访问弹出,留最后一个兜底)。
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
                pass

        page = _SeqUrlPage()
    else:
        page = MagicMock()
        page.url = 'https://creator.douyin.com/'
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.insert_text = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock(return_value='')
    page.on = MagicMock()
    page.main_frame = MagicMock()
    page.input_value = AsyncMock()
    page.click = AsyncMock()

    locators = {}

    def _mk_leaf():
        """locator fake:常用 async 方法默认可 await,无 first/last 递归。"""
        loc = MagicMock()
        loc.count = AsyncMock(return_value=0)
        loc.click = AsyncMock()
        loc.wait_for = AsyncMock()
        loc.fill = AsyncMock()
        loc.set_input_files = AsyncMock()
        loc.evaluate = AsyncMock(return_value='')
        loc.hover = AsyncMock()
        loc.press = AsyncMock()
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
        """根 locator:默认带 .first/.last(leaf 级)。"""
        loc = _mk_leaf()
        loc.first = _mk_leaf()
        loc.last = _mk_leaf()
        return loc

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
    """确保 selector 已在 locator 分派表注册,返回 .first。"""
    page.locator(sel)
    return page.locators[sel].first


def _mk_cookie_file(name='t33_cookie.json'):
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


def _mk_img_file(name='t33_img.png', size=1024):
    fd, path = tempfile.mkstemp(prefix=name, suffix='.png')
    with os.fdopen(fd, 'wb') as f:
        f.write(b'x' * size)
    return path


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLoginAndCookie:
    def test_login_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p, urls=[
            'https://creator.douyin.com/',
            'https://creator.douyin.com/creator-micro/content/upload',
            'https://creator.douyin.com/creator-micro/content/upload',
        ]) as (page, _context, browser, cb, cc), \
             patch('impl.douyin.platform.save_login_result', AsyncMock()) as slr, \
             patch('asyncio.sleep', AsyncMock()):
            # 注册 framenavigated 后立即触发 URL 变化(h 内部 create_task)
            page.on = MagicMock(side_effect=lambda ev, h: h(page.main_frame))
            _run(p.login('acc-1', Queue(), account_id='42'))
        cb.assert_awaited_once_with(login_mode=True)
        cc.assert_awaited_once_with(browser)
        page.goto.assert_awaited_once_with('https://creator.douyin.com/')
        slr.assert_awaited_once()
        assert slr.await_args.kwargs['platform_id'] == 3
        assert slr.await_args.kwargs['account_id'] == '42'
        assert slr.await_args.kwargs['stats_fn'] == p._login_stats_fn
        browser.close.assert_awaited_once()

    def test_login_subframe_event_ignored(self):
        """非主 frame 的 framenavigated → 不创建 URL 监听 task(事件不 set)。"""
        real_sleep = asyncio.sleep  # patch 前捕获真实 sleep,用于让出事件循环
        p = _mk_platform()
        with _mk_browser_chain(p, urls=['https://creator.douyin.com/', 'https://creator.douyin.com/']) as (page, _context, _browser, _cb, _cc), \
             patch('impl.douyin.platform.save_login_result', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()):
            page.on = MagicMock(side_effect=lambda ev, h: None)

            async def _probe():
                task = asyncio.create_task(p.login('acc-1', Queue()))
                await real_sleep(0.01)  # 让 login 跑到 page.on 注册
                assert page.on.call_args.args[0] == 'framenavigated'
                handler = page.on.call_args.args[1]
                # 非主 frame → 不创建 task
                other = MagicMock()
                assert handler(other) is None
                # 主 frame → 创建监听 task;URL 未变 → 事件不 set → login 挂起
                t = handler(page.main_frame)
                assert t is not None
                await real_sleep(0.02)
                assert not task.done()
                task.cancel()

            _run(_probe())

    def test_login_wait_event_never_set_blocks(self):
        """URL 永不变化 → login 挂起(不设超时,浏览器由用户关)。"""
        # 验证:事件未触发时 login 不返回 —— 用 short timeout 探测挂起
        p = _mk_platform()
        with _mk_browser_chain(p, urls=['https://creator.douyin.com/']) as (page, _context, _browser, _cb, _cc), \
             patch('impl.douyin.platform.save_login_result', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()):
            page.url = 'https://creator.douyin.com/'
            page.on = MagicMock(side_effect=lambda ev, h: None)

            async def _probe():
                task = asyncio.create_task(p.login('acc-1', Queue()))
                await asyncio.sleep(0.05)
                # 未完成 = 挂起(等待 URL 变化)
                assert not task.done()
                task.cancel()

            _run(_probe())

    def test_check_cookie_valid(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t33_cc_v.json')
        try:
            with _mk_browser_chain(p) as (page, _ctx, _b, _cb, _cc):
                page.wait_for_url = AsyncMock()
                assert _run(p.check_cookie(cookie.name)) is True
        finally:
            cookie.unlink(missing_ok=True)

    def test_check_cookie_invalid_redirect(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t33_cc_r.json')
        try:
            with _mk_browser_chain(p) as (page, _ctx, _b, _cb, _cc):
                page.wait_for_url = AsyncMock(side_effect=TimeoutError('redirected'))
                assert _run(p.check_cookie(cookie.name)) is False
        finally:
            cookie.unlink(missing_ok=True)

    def test_check_cookie_login_prompt_visible(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t33_cc_l.json')
        try:
            with _mk_browser_chain(p) as (page, _ctx, _b, _cb, _cc):
                page.wait_for_url = AsyncMock()
                page.get_by_text('扫码登录').wait_for = AsyncMock()  # 登录提示可见
                assert _run(p.check_cookie(cookie.name)) is False
        finally:
            cookie.unlink(missing_ok=True)

    def test_check_cookie_close_errors_propagate(self):
        """context.close 在 finally 无保护 → 异常冒泡。"""
        p = _mk_platform()
        cookie = _mk_cookie_file('t33_cc_c.json')
        try:
            with _mk_browser_chain(p) as (page, context, _b, _cb, _cc):
                page.wait_for_url = AsyncMock()
                context.close = AsyncMock(side_effect=RuntimeError('boom'))
                with pytest.raises(RuntimeError):
                    _run(p.check_cookie(cookie.name))
        finally:
            cookie.unlink(missing_ok=True)


class TestSyncProfileAndStats:
    def test_sync_profile_happy(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t33_sp.json')
        try:
            with _mk_browser_chain(p) as (page, _ctx, _b, _cb, _cc), \
                 patch('impl.douyin.platform.scrape_user_profile', AsyncMock(return_value=('昵称', 'a.png'))) as sup:
                page.evaluate = AsyncMock(return_value=[
                    {'label': '粉丝', 'num': '1,234'},
                    {'label': '关注', 'num': '10'},
                    {'label': '其他', 'num': '9'},
                ])
                res = _run(p.sync_profile(cookie.name))
            assert res['name'] == '昵称' and res['avatar'] == 'a.png'
            # 代码未排序 → 顺序与 evaluate 结果一致
            assert [s['NAME'] for s in res['stats']] == ['粉丝', '关注']
            assert res['stats'][0]['COUNT'] == 1234
            sup.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_sync_profile_empty_log(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t33_sp2.json')
        try:
            with _mk_browser_chain(p) as (page, _ctx, _b, _cb, _cc), \
                 patch('impl.douyin.platform.scrape_user_profile', AsyncMock(return_value=('', ''))), \
                 patch('impl.douyin.platform.logger') as lg:
                page.evaluate = AsyncMock(return_value=[])
                res = _run(p.sync_profile(cookie.name))
            assert res == {'name': '', 'avatar': '', 'stats': []}
            lg.info.assert_called()
        finally:
            cookie.unlink(missing_ok=True)

    def test_sync_profile_bad_count_zero(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t33_sp3.json')
        try:
            with _mk_browser_chain(p) as (page, _ctx, _b, _cb, _cc), \
                 patch('impl.douyin.platform.scrape_user_profile', AsyncMock(return_value=('n', ''))):
                page.evaluate = AsyncMock(return_value=[{'label': '粉丝', 'num': 'abc'}])
                res = _run(p.sync_profile(cookie.name))
            assert res['stats'][0]['COUNT'] == 0
        finally:
            cookie.unlink(missing_ok=True)

    def test_login_stats_fn_happy(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[{'label': '获赞', 'num': '5'}])
        res = _run(p._login_stats_fn(page, 'acc-1'))
        assert res == [{'ICON': 'like', 'COUNT': 5, 'NAME': '获赞', 'SORT': 3}]

    def test_login_stats_fn_wait_timeout_continues(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        page.evaluate = AsyncMock(return_value=[])
        with patch('impl.douyin.platform.logger') as lg:
            res = _run(p._login_stats_fn(page, 'acc-1'))
        assert res == []
        lg.info.assert_called()

    def test_login_stats_fn_evaluate_exception(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('js boom'))
        with patch('impl.douyin.platform.logger'), pytest.raises(RuntimeError):
            _run(p._login_stats_fn(page, 'acc-1'))
        # evaluate 异常未被吞 → 冒泡(save_login_result 兜底)

    def test_open_creator_center_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t33_occ.json')
        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch('impl.douyin.platform.create_browser_sync', return_value=browser) as cbs, \
                 patch('impl.douyin.platform.create_context_sync', return_value=context) as ccs:
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if page.goto.called:
                        break
                    _time.sleep(0.02)
            cbs.assert_called_once_with(headless=False)
            ccs.assert_called_once()
            page.goto.assert_called_once()
            # 抖音不关浏览器(用户自己关)
            browser.close.assert_not_called()
        finally:
            cookie.unlink(missing_ok=True)

    def test_parse_cookie_to_storage_state(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state('k1=v1;;k2=v2')
        assert len(cookies) == 2
        assert cookies[0]['name'] == 'k1' and cookies[0]['domain'] == '.douyin.com'
        assert origins == []
        assert cookies[1]['name'] == 'k2'


# ── 纯函数: 话题计数 / 发布参数校验 ───────────────────────────────────────

class TestHashtagValidation:
    def test_count_empty(self):
        assert DouyinPlatform._count_hashtags('') == 0
        assert DouyinPlatform._count_hashtags(None) == 0

    def test_count_basic(self):
        assert DouyinPlatform._count_hashtags('#a #b #c') == 3
        assert DouyinPlatform._count_hashtags('前缀 #话题1 后缀 #话题2') == 2

    def test_count_ignores_false_positives(self):
        assert DouyinPlatform._count_hashtags('a#b http://x#anchor ## 孤立#') == 0

    def test_count_multiline(self):
        assert DouyinPlatform._count_hashtags('第一行 #a\n第二行 #b') == 2

    def test_validate_ok_at_limit(self):
        ok, msg = DouyinPlatform._validate_publish_params('#a #b', ['c'], ['d', 'e'])
        assert ok is True and msg == ''

    def test_validate_over_limit(self):
        ok, msg = DouyinPlatform._validate_publish_params('#a #b #c', ['d', 'e'], ['f'])
        assert ok is False and '超过 5 个' in msg

    def test_validate_none_lists(self):
        ok, _ = DouyinPlatform._validate_publish_params(None, None, None)
        assert ok is True


# ── 编排层: 单视频上传 ─────────────────────────────────────────────────────

class TestUploadOneVideo:
    def test_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, cb, _cc):
            for name in ('_fill_title_and_description', '_set_thumbnail',
                         '_set_product_link', '_set_schedule_time', '_set_tag',
                         '_set_hotspot', '_handle_auto_video_cover', '_set_image_mix',
                         '_set_declaration'):
                setattr(p, name, AsyncMock())
            # 上传完成检测:long-card 出现
            long_card = page.locator('[class^="long-card"] div:has-text("重新上传")')
            long_card.count = AsyncMock(return_value=1)
            # 发布按钮
            publish_btn = page.get_by_role('button', name='发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.douyin.platform._PUBLISH_DRY_RUN', False):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=['t1'], publish_date=0,
                    account_file='ck.json', publish_strategy='immediate',
                    desc='D', product_link='https://x', product_title='商品',
                    ai_content='AI', hotspot='热点', tag_type='location', tag_value='北京',
                ))
            cb.assert_awaited_once_with(headless=False)
            context.grant_permissions.assert_awaited_once()
            page.goto.assert_awaited_once()
            long_card.count.assert_awaited()
            p._fill_title_and_description.assert_awaited_once()
            p._set_product_link.assert_awaited_once_with(page, 'https://x', '商品')
            p._set_thumbnail.assert_awaited_once_with(page, None, None)
            p._set_tag.assert_awaited_once()
            p._set_hotspot.assert_awaited_once()
            p._set_schedule_time.assert_not_awaited()
            publish_btn.click.assert_awaited_once()
            context.storage_state.assert_awaited_once()
            browser.close.assert_awaited_once()

    def test_activities_appended_to_desc(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
            for name in ('_fill_title_and_description', '_set_thumbnail',
                         '_set_product_link', '_set_schedule_time', '_set_tag',
                         '_set_hotspot', '_handle_auto_video_cover', '_set_image_mix',
                         '_set_declaration'):
                setattr(p, name, AsyncMock())
            long_card = page.locator('[class^="long-card"] div:has-text("重新上传")')
            long_card.count = AsyncMock(return_value=1)
            publish_btn = page.get_by_role('button', name='发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.douyin.platform._PUBLISH_DRY_RUN', False):
                _run(p._upload_one_video(
                    title='标题', file_path='/v/a.mp4', tags=[], publish_date=0,
                    account_file='ck.json', publish_strategy='immediate',
                    desc='', activities=['A1', 'A2'],
                ))
            # activities 拼接: desc or title + #A1 #A2
            called_desc = p._fill_title_and_description.await_args.args[2]
            assert '#A1' in called_desc and '#A2' in called_desc

    def test_scheduled_calls_set_schedule_time(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
            for name in ('_fill_title_and_description', '_set_thumbnail',
                         '_set_product_link', '_set_schedule_time', '_set_tag',
                         '_set_hotspot', '_handle_auto_video_cover', '_set_image_mix',
                         '_set_declaration'):
                setattr(p, name, AsyncMock())
            long_card = page.locator('[class^="long-card"] div:has-text("重新上传")')
            long_card.count = AsyncMock(return_value=1)
            publish_btn = page.get_by_role('button', name='发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.douyin.platform._PUBLISH_DRY_RUN', False):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], publish_date=1730000000000,
                    account_file='ck.json', publish_strategy='scheduled',
                ))
            p._set_schedule_time.assert_awaited_once()

    def test_dry_run_skips_publish(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc):
            for name in ('_fill_title_and_description', '_set_thumbnail',
                         '_set_product_link', '_set_schedule_time', '_set_tag',
                         '_set_hotspot', '_handle_auto_video_cover', '_set_image_mix',
                         '_set_declaration'):
                setattr(p, name, AsyncMock())
            long_card = page.locator('[class^="long-card"] div:has-text("重新上传")')
            long_card.count = AsyncMock(return_value=1)
            browser.is_connected = MagicMock(return_value=False)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.douyin.platform._PUBLISH_DRY_RUN', True), \
                 patch('impl.douyin.platform.logger') as lg:
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                    account_file='ck.json', publish_strategy='immediate',
                ))
            publish_btn = page.get_by_role('button', name='发布', exact=True)
            publish_btn.click.assert_not_awaited()
            lg.warning.assert_called()  # DRY_RUN 警告

    def test_upload_retry_on_failure(self):
        """上传失败文本出现 → 重新 set_input_files 重试。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
            for name in ('_fill_title_and_description', '_set_thumbnail',
                         '_set_product_link', '_set_schedule_time', '_set_tag',
                         '_set_hotspot', '_handle_auto_video_cover', '_set_image_mix',
                         '_set_declaration'):
                setattr(p, name, AsyncMock())
            long_card = page.locator('[class^="long-card"] div:has-text("重新上传")')
            long_card.count = AsyncMock(side_effect=[0, 1])  # 第一轮失败
            fail_text = page.locator('div.progress-div > div:has-text("上传失败")')
            fail_text.count = AsyncMock(return_value=1)
            upload_input = page.locator("div.progress-div [class^='upload-btn-input']")
            upload_input.set_input_files = AsyncMock()
            publish_btn = page.get_by_role('button', name='发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.douyin.platform._PUBLISH_DRY_RUN', False), \
                 patch('impl.douyin.platform.logger') as lg:
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                    account_file='ck.json', publish_strategy='immediate',
                ))
            upload_input.set_input_files.assert_awaited_once_with('/v/a.mp4')
            lg.warning.assert_called()

    def test_publish_retry_auto_cover(self):
        """发布循环 wait_for_url 失败 → 自动封面 → 重试成功。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
            for name in ('_fill_title_and_description', '_set_thumbnail',
                         '_set_product_link', '_set_schedule_time', '_set_tag',
                         '_set_hotspot', '_set_image_mix', '_set_declaration'):
                setattr(p, name, AsyncMock())
            p._handle_auto_video_cover = AsyncMock()
            long_card = page.locator('[class^="long-card"] div:has-text("重新上传")')
            long_card.count = AsyncMock(return_value=1)
            publish_btn = page.get_by_role('button', name='发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            page.wait_for_url = AsyncMock(side_effect=[None, None, TimeoutError('slow'), None])
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.douyin.platform._PUBLISH_DRY_RUN', False):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                    account_file='ck.json', publish_strategy='immediate',
                ))
            p._handle_auto_video_cover.assert_awaited()
            publish_btn.click.assert_awaited()

    def test_context_close_error_propagates(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc):
            for name in ('_fill_title_and_description', '_set_thumbnail',
                         '_set_product_link', '_set_schedule_time', '_set_tag',
                         '_set_hotspot', '_handle_auto_video_cover', '_set_image_mix',
                         '_set_declaration'):
                setattr(p, name, AsyncMock())
            long_card = page.locator('[class^="long-card"] div:has-text("重新上传")')
            long_card.count = AsyncMock(return_value=1)
            publish_btn = page.get_by_role('button', name='发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            context.close = AsyncMock(side_effect=RuntimeError('boom'))
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.douyin.platform._PUBLISH_DRY_RUN', False), \
                 pytest.raises(RuntimeError):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                    account_file='ck.json', publish_strategy='immediate',
                ))
            browser.close.assert_awaited_once()


# ── 图集上传: _upload_image_note ────────────────────────────────────────

def _mk_fake_loop(times):
    """fake event loop:time() 按序列返回(用于绕开真实墙钟时间的等待循环)。"""
    loop = MagicMock()
    loop.time.side_effect = list(times)
    return loop


class TestUploadImageNote:
    def _mk(self, p, page, file_count=2, **kw):
        img_items = page.locator('div[class*="img-"][draggable="true"]')
        img_items.count = AsyncMock(return_value=file_count)
        return kw

    def test_dry_run_happy(self):
        p = _mk_platform()
        imgs = [_mk_img_file('t33_img_a.png'), _mk_img_file('t33_img_b.png')]
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc):
            self._mk(p, page, file_count=2)
            publish_btn = page.get_by_role('button', name='发布', exact=True)
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_image_note(
                    title='我的图集', file_paths=imgs, tags=['旅行', '风景'],
                    account_file='ck.json', desc='描述文字', dry_run=True,
                ))
            file_input = page.locator("div[class^='container'] input[type='file']")
            file_input.set_input_files.assert_awaited_once_with(imgs)
            page.keyboard.type.assert_awaited()
            publish_btn.click.assert_not_awaited()
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()

    def test_publish_real_flow(self):
        p = _mk_platform()
        imgs = [_mk_img_file('t33_img_c.png')]
        with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc):
            self._mk(p, page, file_count=1)
            publish_btn = page.get_by_role('button', name='发布', exact=True)
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_image_note(
                    title='T', file_paths=imgs, tags=[], account_file='ck.json',
                    dry_run=False,
                ))
            publish_btn.wait_for.assert_awaited()
            publish_btn.click.assert_awaited()
            page.wait_for_url.assert_awaited()
            context.storage_state.assert_awaited_once_with(path='ck.json')

    def test_all_optional_helpers_called(self):
        p = _mk_platform()
        imgs = [_mk_img_file('t33_img_d.png')]
        for name in ('_set_image_cover', '_set_image_mix', '_select_music',
                     '_set_hotspot', '_set_tag', '_set_declaration',
                     '_set_schedule_time'):
            setattr(p, name, AsyncMock())
        with _mk_browser_chain(p) as (page, _context, _b, _cb, _cc):
            self._mk(p, page, file_count=1)
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_image_note(
                    title='T', file_paths=imgs, tags=[], account_file='ck.json',
                    cover_path='/tmp/cover.png', mix_id='mix-1',
                    music_name='晴天', hotspot='旅行', tag_type='location',
                    tag_value='杭州', ai_content='AI生成内容',
                    enable_timer=True, schedule_time_str='2026-08-25 14:30',
                    dry_run=True,
                ))
            p._set_image_cover.assert_awaited_once()
            p._set_image_mix.assert_awaited_once()
            p._select_music.assert_awaited_once()
            p._set_hotspot.assert_awaited_once()
            p._set_tag.assert_awaited_once()
            p._set_declaration.assert_awaited_once()
            p._set_schedule_time.assert_awaited_once()

    def test_upload_wait_timeout_warns(self):
        """图片数量始终不足 → 等到 max_upload_wait 超时(用 fake loop 时间推进)。"""
        p = _mk_platform()
        imgs = [_mk_img_file('t33_img_e.png'), _mk_img_file('t33_img_f.png')]
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=_mk_fake_loop([0.0, 121.0, 0.0, 121.0])), \
             patch('impl.douyin.platform.logger') as lg:
            img_items = page.locator('div[class*="img-"][draggable="true"]')
            img_items.count = AsyncMock(return_value=0)  # 一直 0 张
            _run(p._upload_image_note(
                title='T', file_paths=imgs, tags=[], account_file='ck.json',
                dry_run=True,
            ))
            lg.warning.assert_called()  # 等待图片上传超时警告

    def test_redirect_wait_timeout_warns(self):
        """URL 一直停留在 upload 页 → 跳转等待超时。"""
        p = _mk_platform()
        imgs = [_mk_img_file('t33_img_g.png')]
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('asyncio.get_event_loop', return_value=_mk_fake_loop([0.0, 0.0, 121.0, 0.0, 121.0])), \
             patch('impl.douyin.platform.logger') as lg:
            page.url = 'https://creator.douyin.com/creator-micro/content/upload?default-tab=3'
            self._mk(p, page, file_count=1)
            _run(p._upload_image_note(
                title='T', file_paths=imgs, tags=[], account_file='ck.json',
                dry_run=True,
            ))
            assert any('跳转超时' in str(c) for c in lg.warning.call_args_list)


# ── 图集编排: publish_image ─────────────────────────────────────────────

class TestPublishImage:
    def test_single_account_activities_appended(self):
        p = _mk_platform()
        with patch.object(p, '_upload_image_note', AsyncMock()) as uin, \
             patch('impl.douyin.platform.get_account_name_by_cookie_file',
                   return_value='测试号'):
            _run(p.publish_image(
                title='T', files=['/img/1.png'], tags=['x'],
                account_file=['ck.json'], desc='描述',
                activities=['A1', 'A2'], dry_run=False,
            ))
        uin.assert_awaited_once()
        kw = uin.await_args.kwargs
        assert kw['desc'] == '描述 #A1 #A2'
        assert kw['account_file'].endswith('ck.json')
        assert kw['dry_run'] is False

    def test_multi_account_calls_each(self):
        p = _mk_platform()
        with patch.object(p, '_upload_image_note', AsyncMock()) as uin, \
             patch('impl.douyin.platform.get_account_name_by_cookie_file', return_value=''):
            _run(p.publish_image(
                title='T', files=['/img/1.png'], tags=[],
                account_file=['a.json', 'b.json'], dry_run=True,
            ))
        assert uin.await_count == 2

    def test_missing_cover_reset_to_empty(self):
        p = _mk_platform()
        with patch.object(p, '_upload_image_note', AsyncMock()) as uin, \
             patch('impl.douyin.platform.get_account_name_by_cookie_file', return_value=''):
            _run(p.publish_image(
                title='T', files=['/img/1.png'], tags=[],
                account_file=['ck.json'], cover_path='/no/such/cover.png',
                dry_run=True,
            ))
        assert uin.await_args.kwargs['cover_path'] == ''


# ── 标题/简介填写: _fill_title_and_description ──────────────────────────

class TestFillTitleAndDescription:
    @staticmethod
    def _mk_desc_chain(page, title_chain, desc_chain):
        """接通 作品描述 -> ancestor div[2] -> following-sibling div[1] -> input/editor。"""
        desc_section = page.get_by_text('作品描述', exact=True)
        level_b = MagicMock()  # following-sibling::div[1]
        level_b.locator = MagicMock(side_effect=lambda sel, **kw: {
            'input[type="text"]': title_chain,
            '.zone-container[contenteditable="true"]': desc_chain,
        }.get(sel, MagicMock()))
        level_a = MagicMock()  # ancestor::div[2]
        level_a.locator = MagicMock(side_effect=lambda sel, **kw: (
            level_b if sel == 'xpath=following-sibling::div[1]' else MagicMock()))
        desc_section.locator = MagicMock(side_effect=lambda sel, **kw: (
            level_a if sel == 'xpath=ancestor::div[2]' else MagicMock()))
        return desc_section

    def test_basic_flow(self):
        p = _mk_platform()
        page = _mk_page()
        title_chain = MagicMock()
        title_chain.first.wait_for = AsyncMock()
        title_chain.first.fill = AsyncMock()
        desc_chain = MagicMock()
        desc_chain.first.wait_for = AsyncMock()
        desc_chain.first.click = AsyncMock()
        self._mk_desc_chain(page, title_chain, desc_chain)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.clear_and_type', AsyncMock()) as cat:
            _run(p._fill_title_and_description(
                page, '标题' * 10, '简介内容', tags=['a', '', 'b'],
            ))
        assert title_chain.first.fill.await_args.args[0] == ('标题' * 10)[:30]
        cat.assert_awaited_once()
        assert cat.await_args.args[1] == '简介内容'
        # 空格 + 每个非空 tag 前加 #(空 tag 跳过)
        insert_calls = [c.args[0] for c in page.keyboard.insert_text.call_args_list]
        assert ' #a' in insert_calls and ' #b' in insert_calls
        assert page.keyboard.insert_text.call_count == 2
        # End 键把光标移到末尾(每 tag 一次)
        end_presses = [c for c in page.keyboard.press.call_args_list
                       if c.args[0] == 'End']
        assert len(end_presses) == 2

    def test_empty_description_and_tags(self):
        p = _mk_platform()
        page = _mk_page()
        title_chain = MagicMock()
        title_chain.first.wait_for = AsyncMock()
        title_chain.first.fill = AsyncMock()
        desc_chain = MagicMock()
        desc_chain.first.wait_for = AsyncMock()
        desc_chain.first.click = AsyncMock()
        self._mk_desc_chain(page, title_chain, desc_chain)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.clear_and_type', AsyncMock()) as cat:
            _run(p._fill_title_and_description(page, 'T', '', None))
        assert cat.await_args.args[1] == ''  # rstrip 后空串
        assert page.keyboard.insert_text.call_count == 0



# ── 定时发布: _set_schedule_time(8 步) ─────────────────────────────────

class TestScheduleTime:
    @staticmethod
    def _pre_reg(page, selectors):
        return {sel: page.locator(sel) for sel in selectors}

    def test_zero_returns_early(self):
        p = _mk_platform()
        page = _mk_page()
        _run(p._set_schedule_time(page, 0))
        page.locator.assert_not_called()

    def test_happy_path_8_steps(self):
        p = _mk_platform()
        page = _mk_page()
        dt = datetime(2026, 8, 25, 14, 30, tzinfo=UTC)
        sels = self._pre_reg(page, [
            "[class^='radio']:has-text('定时发布')",
            '.semi-input[placeholder="日期和时间"]',
            '.semi-datepicker-day:not(.semi-datepicker-day-disabled)[title="2026-08-25"]',
            '.semi-datepicker-switch-time',
            '.semi-scrolllist-item-wheel.undefined-list-hour li',
            '.semi-scrolllist-item-wheel.undefined-list-minute li',
            '.semi-popover button:has-text("确定")',
        ])
        sels['.semi-datepicker-day:not(.semi-datepicker-day-disabled)[title="2026-08-25"]'].count = AsyncMock(return_value=1)
        sels['.semi-datepicker-switch-time'].count = AsyncMock(return_value=1)
        hour_item = MagicMock()
        hour_item.count = AsyncMock(return_value=1)
        hour_item.first.click = AsyncMock()
        sels['.semi-scrolllist-item-wheel.undefined-list-hour li'].filter = MagicMock(side_effect=lambda **kw: hour_item)
        minute_item = MagicMock()
        minute_item.count = AsyncMock(return_value=1)
        minute_item.first.click = AsyncMock()
        sels['.semi-scrolllist-item-wheel.undefined-list-minute li'].filter = MagicMock(side_effect=lambda **kw: minute_item)
        sels['.semi-popover button:has-text("确定")'].count = AsyncMock(return_value=1)
        page.input_value = AsyncMock(return_value='2026-08-25 14:30')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_schedule_time(page, dt))
        sels["[class^='radio']:has-text('定时发布')"].click.assert_awaited_once()
        sels['.semi-datepicker-day:not(.semi-datepicker-day-disabled)[title="2026-08-25"]'].first.click.assert_awaited_once()
        sels['.semi-datepicker-switch-time'].first.click.assert_awaited_once()
        hour_item.first.click.assert_awaited_once()
        minute_item.first.click.assert_awaited_once()
        sels['.semi-popover button:has-text("确定")'].first.click.assert_awaited_once()
        page.keyboard.press.assert_not_awaited()  # 确认按钮存在,不走 Enter
        assert any('校验成功' in str(c) for c in lg.info.call_args_list)

    def test_missing_confirm_uses_enter(self):
        p = _mk_platform()
        page = _mk_page()
        dt = datetime(2026, 8, 25, 14, 30, tzinfo=UTC)
        sels = self._pre_reg(page, [
            '.semi-datepicker-day:not(.semi-datepicker-day-disabled)[title="2026-08-25"]',
            '.semi-scrolllist-item-wheel.undefined-list-hour li',
            '.semi-scrolllist-item-wheel.undefined-list-minute li',
            '.semi-popover button:has-text("确定")',
        ])
        sels['.semi-datepicker-day:not(.semi-datepicker-day-disabled)[title="2026-08-25"]'].count = AsyncMock(return_value=1)
        hour_item = MagicMock()
        hour_item.count = AsyncMock(return_value=1)
        hour_item.first.click = AsyncMock()
        sels['.semi-scrolllist-item-wheel.undefined-list-hour li'].filter = MagicMock(side_effect=lambda **kw: hour_item)
        minute_item = MagicMock()
        minute_item.count = AsyncMock(return_value=1)
        minute_item.first.click = AsyncMock()
        sels['.semi-scrolllist-item-wheel.undefined-list-minute li'].filter = MagicMock(side_effect=lambda **kw: minute_item)
        sels['.semi-popover button:has-text("确定")'].count = AsyncMock(return_value=0)
        page.input_value = AsyncMock(return_value='2026-08-25 14:30')
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_schedule_time(page, dt))
        page.keyboard.press.assert_awaited_once_with('Enter')

    def test_exception_logs_error(self):
        p = _mk_platform()
        page = _mk_page()
        dt = datetime(2026, 8, 25, 14, 30, tzinfo=UTC)
        radio = page.locator("[class^='radio']:has-text('定时发布')")
        radio.click = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_schedule_time(page, dt))
        assert any('设置定时发布时间失败' in str(c) for c in lg.error.call_args_list)


# ── 商品链接: _set_product_link ────────────────────────────────────────

class TestProductLink:
    @staticmethod
    def _mk_dropdown(add_tag):
        """三层 `..` 后到 .semi-select 的链,返回 (dropdown_chain,)。"""
        dropdown_chain = MagicMock()
        dropdown_chain.first.count = AsyncMock(return_value=1)
        dropdown_chain.first.click = AsyncMock()
        lvl3 = MagicMock()
        lvl3.locator = MagicMock(side_effect=lambda sel, **kw: (
            dropdown_chain if sel == '.semi-select' else MagicMock()))
        lvl2 = MagicMock()
        lvl2.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl3 if sel == '..' else MagicMock()))
        lvl1 = MagicMock()
        lvl1.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl2 if sel == '..' else MagicMock()))
        add_tag.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl1 if sel == '..' else MagicMock()))
        return dropdown_chain

    def test_happy_path(self):
        p = _mk_platform()
        page = _mk_page()
        add_tag = page.get_by_text('添加标签', exact=True)
        self._mk_dropdown(add_tag)
        shop_option = page.locator('[role="option"]:has-text("购物车")')
        shop_option.click = AsyncMock()
        input_field = page.locator('input[placeholder="粘贴商品链接"]')
        input_field.fill = AsyncMock()
        add_button = page.locator('span:has-text("添加链接")')
        add_button.get_attribute = AsyncMock(return_value='semi-button')
        add_button.click = AsyncMock()
        short_title = page.locator('input[placeholder="请输入商品短标题"]')
        short_title.count = AsyncMock(return_value=1)
        short_title.fill = AsyncMock()
        finish = page.locator('button:has-text("完成编辑")')
        finish.get_attribute = AsyncMock(return_value='semi-button-primary')
        finish.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            result = _run(p._set_product_link(page, 'https://item.com/1', '好物'))
        assert result is True
        input_field.fill.assert_awaited_once_with('https://item.com/1')
        short_title.fill.assert_awaited_once_with('好物'[:10])
        finish.click.assert_awaited_once()
        page.wait_for_selector.assert_awaited()

    def test_no_dropdown_returns_false(self):
        p = _mk_platform()
        page = _mk_page()
        add_tag = page.get_by_text('添加标签', exact=True)
        dropdown_chain = MagicMock()
        dropdown_chain.first.count = AsyncMock(return_value=0)
        lvl3 = MagicMock()
        lvl3.locator = MagicMock(side_effect=lambda sel, **kw: (
            dropdown_chain if sel == '.semi-select' else MagicMock()))
        lvl2 = MagicMock()
        lvl2.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl3 if sel == '..' else MagicMock()))
        lvl1 = MagicMock()
        lvl1.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl2 if sel == '..' else MagicMock()))
        add_tag.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl1 if sel == '..' else MagicMock()))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            result = _run(p._set_product_link(page, 'https://x', 't'))
        assert result is False
        assert any('未找到标签下拉框' in str(c) for c in lg.warning.call_args_list)

    def test_error_modal_path(self):
        p = _mk_platform()
        page = _mk_page()
        add_tag = page.get_by_text('添加标签', exact=True)
        self._mk_dropdown(add_tag)
        page.locator('[role="option"]:has-text("购物车")').click = AsyncMock()
        page.locator('input[placeholder="粘贴商品链接"]').fill = AsyncMock()
        add_button = page.locator('span:has-text("添加链接")')
        add_button.get_attribute = AsyncMock(return_value='')
        add_button.click = AsyncMock()
        error_modal = page.locator('text=未搜索到对应商品')
        error_modal.count = AsyncMock(return_value=1)
        confirm = page.locator('button:has-text("确定")')
        confirm.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            result = _run(p._set_product_link(page, 'https://x', 't'))
        assert result is False
        confirm.click.assert_awaited_once()

    def test_disabled_finish_closes_dialog(self):
        p = _mk_platform()
        page = _mk_page()
        add_tag = page.get_by_text('添加标签', exact=True)
        self._mk_dropdown(add_tag)
        page.locator('[role="option"]:has-text("购物车")').click = AsyncMock()
        page.locator('input[placeholder="粘贴商品链接"]').fill = AsyncMock()
        add_button = page.locator('span:has-text("添加链接")')
        add_button.get_attribute = AsyncMock(return_value='')
        add_button.click = AsyncMock()
        short_title = page.locator('input[placeholder="请输入商品短标题"]')
        short_title.count = AsyncMock(return_value=1)
        short_title.fill = AsyncMock()
        finish = page.locator('button:has-text("完成编辑")')
        finish.get_attribute = AsyncMock(return_value='semi-button-disabled')
        cancel = page.locator('button:has-text("取消")')
        cancel.count = AsyncMock(return_value=1)
        cancel.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            result = _run(p._set_product_link(page, 'https://x', 't'))
        assert result is False
        finish.click.assert_not_awaited()
        cancel.click.assert_awaited_once()

    def test_exception_returns_false(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            result = _run(p._set_product_link(page, 'https://x', 't'))
        assert result is False
        assert any('设置失败' in str(c) for c in lg.warning.call_args_list)


# ── 视频封面: _set_thumbnail ───────────────────────────────────────────

class TestThumbnail:
    @staticmethod
    def _mk_cover(cover, tab_loc=None, upload_input=None, finish=None):
        """cover.locator 分派:steps tab / upload input / 完成按钮。"""
        mapping = {}
        if tab_loc is not None:
            mapping["div[class*='steps'] div"] = tab_loc
        if upload_input is not None:
            mapping["div[class^='semi-upload upload'] >> input.semi-upload-hidden-input"] = upload_input
        if finish is not None:
            mapping['button:visible:has-text("完成")'] = finish
        cover.locator = MagicMock(side_effect=lambda sel, **kw: (
            mapping.get(sel, MagicMock())))
        return mapping

    def test_no_paths_returns(self):
        p = _mk_platform()
        page = _mk_page()
        _run(p._set_thumbnail(page))
        page.click.assert_not_called()

    def test_portrait_only_default_tab(self):
        p = _mk_platform()
        page = _mk_page()
        cover = page.locator('div[id*="creator-content-modal"]')
        tab_loc = MagicMock()
        tab_loc.count = AsyncMock(return_value=0)  # 找不到 tab → 默认分支
        upload_input = MagicMock()
        upload_input.first.set_input_files = AsyncMock()
        finish = MagicMock()
        finish.click = AsyncMock()
        self._mk_cover(cover, tab_loc, upload_input, finish)
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._set_thumbnail(page, thumbnail_portrait_path='/v/p.png'))
        page.click.assert_awaited_once_with('text="选择封面"')
        upload_input.first.set_input_files.assert_awaited_once_with('/v/p.png')

    def test_happy_with_tabs(self):
        p = _mk_platform()
        page = _mk_page()
        cover = page.locator('div[id*="creator-content-modal"]')
        tabs = {0: MagicMock(), 1: MagicMock()}
        tabs[0].inner_text = AsyncMock(return_value='竖版')
        tabs[0].click = AsyncMock()
        tabs[1].inner_text = AsyncMock(return_value='横版')
        tabs[1].click = AsyncMock()
        tab_loc = MagicMock()
        tab_loc.count = AsyncMock(return_value=2)
        tab_loc.nth = MagicMock(side_effect=lambda i: tabs[i])
        upload_input = MagicMock()
        upload_input.first.set_input_files = AsyncMock()
        finish = MagicMock()
        finish.click = AsyncMock()
        self._mk_cover(cover, tab_loc, upload_input, finish)
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._set_thumbnail(
                page,
                thumbnail_landscape_path='/v/l.png',
                thumbnail_portrait_path='/v/p.png',
            ))
        tabs[0].click.assert_awaited_once()
        tabs[1].click.assert_awaited_once()
        assert upload_input.first.set_input_files.await_count == 2
        finish.click.assert_awaited_once()

    def test_tab_probe_exception_continues(self):
        p = _mk_platform()
        page = _mk_page()
        cover = page.locator('div[id*="creator-content-modal"]')
        bad = MagicMock()
        bad.inner_text = AsyncMock(side_effect=RuntimeError('detach'))
        good = MagicMock()
        good.inner_text = AsyncMock(return_value='横版')
        good.click = AsyncMock()
        tab_loc = MagicMock()
        tab_loc.count = AsyncMock(return_value=2)
        tab_loc.nth = MagicMock(side_effect=lambda i: bad if i == 0 else good)
        upload_input = MagicMock()
        upload_input.first.set_input_files = AsyncMock()
        finish = MagicMock()
        finish.click = AsyncMock()
        self._mk_cover(cover, tab_loc, upload_input, finish)
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._set_thumbnail(page, thumbnail_landscape_path='/v/l.png'))
        # 竖版探测失败跳过,横版成功上传
        assert upload_input.first.set_input_files.await_count == 1
        good.click.assert_awaited_once()


# ── 自动封面: _handle_auto_video_cover ─────────────────────────────────

class TestAutoVideoCover:
    def test_prompt_absent_returns_false(self):
        p = _mk_platform()
        page = _mk_page()
        prompt = page.get_by_text('请设置封面后再发布', exact=True)
        prompt.first.is_visible = AsyncMock(return_value=False)
        result = _run(p._handle_auto_video_cover(page))
        assert result is False

    def test_happy_path(self):
        p = _mk_platform()
        page = _mk_page()
        prompt = page.get_by_text('请设置封面后再发布', exact=True)
        prompt.first.is_visible = AsyncMock(return_value=True)
        recommend = page.locator('[class^="recommendCover-"]')
        recommend.first.count = AsyncMock(return_value=1)
        recommend.first.click = AsyncMock()
        confirm_text = page.get_by_text('是否确认应用此封面？', exact=True)
        confirm_text.first.is_visible = AsyncMock(return_value=True)
        confirm_btn = page.get_by_role('button', name='确定')
        confirm_btn.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            result = _run(p._handle_auto_video_cover(page))
        assert result is True
        recommend.first.click.assert_awaited_once()
        confirm_btn.click.assert_awaited_once()

    def test_no_recommend_returns_false(self):
        p = _mk_platform()
        page = _mk_page()
        prompt = page.get_by_text('请设置封面后再发布', exact=True)
        prompt.first.is_visible = AsyncMock(return_value=True)
        recommend = page.locator('[class^="recommendCover-"]')
        recommend.first.count = AsyncMock(return_value=0)
        result = _run(p._handle_auto_video_cover(page))
        assert result is False

    def test_click_error_falls_back_false(self):
        p = _mk_platform()
        page = _mk_page()
        prompt = page.get_by_text('请设置封面后再发布', exact=True)
        prompt.first.is_visible = AsyncMock(return_value=True)
        recommend = page.locator('[class^="recommendCover-"]')
        recommend.first.count = AsyncMock(return_value=1)
        recommend.first.click = AsyncMock(side_effect=RuntimeError('stale'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            result = _run(p._handle_auto_video_cover(page))
        assert result is False
        assert any('自动封面选择失败' in str(c) for c in lg.warning.call_args_list)


# ── 图集封面: _set_image_cover ─────────────────────────────────────────

class TestImageCover:
    def test_happy_path(self):
        p = _mk_platform()
        page = _mk_page()
        edit_btn = page.get_by_text('编辑封面', exact=True)
        edit_btn.click = AsyncMock()
        upload_tab = page.get_by_role('tab', name='上传封面')
        upload_tab.click = AsyncMock()
        cover_input = page.locator('input[type="file"][accept*="image"]')
        cover_input.first.count = AsyncMock(return_value=1)
        cover_input.first.set_input_files = AsyncMock()
        confirm_buttons = page.locator('button:has-text("确定")')
        confirm_buttons.count = AsyncMock(return_value=1)
        confirm_buttons.last.click = AsyncMock()
        final_confirm = page.locator('button:has-text("确定")')
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._set_image_cover(page, '/v/cover.png'))
        edit_btn.click.assert_awaited_once()
        upload_tab.click.assert_awaited_once()
        cover_input.first.set_input_files.assert_awaited_once_with('/v/cover.png')
        assert confirm_buttons.last.click.await_count == 2  # 裁剪确认 + 编辑器最终确认
        final_confirm.last.click.assert_awaited()

    def test_fallback_file_input(self):
        p = _mk_platform()
        page = _mk_page()
        page.get_by_text('编辑封面', exact=True).click = AsyncMock()
        page.get_by_role('tab', name='上传封面').click = AsyncMock()
        accept_input = page.locator('input[type="file"][accept*="image"]')
        accept_input.first.count = AsyncMock(return_value=0)
        plain_input = page.locator('input[type="file"]')
        plain_input.first.count = AsyncMock(return_value=1)
        plain_input.first.set_input_files = AsyncMock()
        page.locator('button:has-text("确定")').count = AsyncMock(return_value=1)
        page.locator('button:has-text("确定")').last.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._set_image_cover(page, '/v/cover.png'))
        plain_input.first.set_input_files.assert_awaited_once_with('/v/cover.png')
        assert accept_input.first.set_input_files.await_count == 0

    def test_exception_warns(self):
        p = _mk_platform()
        page = _mk_page()
        page.get_by_text('编辑封面', exact=True).click = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_image_cover(page, '/v/cover.png'))
        assert any('封面设置失败' in str(c) for c in lg.warning.call_args_list)


# ── 合集: _set_image_mix ───────────────────────────────────────────────

class TestImageMix:
    def test_happy_path(self):
        p = _mk_platform()
        page = _mk_page()
        dropdown = page.locator('div.semi-select:has-text("不选择合集")')
        dropdown.first.count = AsyncMock(return_value=1)
        dropdown.first.click = AsyncMock()
        option = page.locator('div.semi-select-option:has-text("我的合集")')
        option.first.count = AsyncMock(return_value=1)
        option.first.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_image_mix(page, '我的合集'))
        dropdown.first.click.assert_awaited_once()
        option.first.click.assert_awaited_once()
        assert any('已选择合集' in str(c) for c in lg.info.call_args_list)

    def test_no_dropdown_warns(self):
        p = _mk_platform()
        page = _mk_page()
        for label in ('不选择合集', '选择合集', '添加合集'):
            page.locator(f'div.semi-select:has-text("{label}")').first.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_image_mix(page, '我的合集'))
        assert any('未找到合集下拉框' in str(c) for c in lg.warning.call_args_list)

    def test_option_missing_escape(self):
        p = _mk_platform()
        page = _mk_page()
        dropdown = page.locator('div.semi-select:has-text("选择合集")')
        dropdown.first.count = AsyncMock(return_value=1)
        dropdown.first.click = AsyncMock()
        option = page.locator('div.semi-select-option:has-text("我的合集")')
        option.first.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_image_mix(page, '我的合集'))
        page.keyboard.press.assert_awaited_once_with('Escape')
        assert any('未找到合集' in str(c) for c in lg.warning.call_args_list)


# ── 音乐: _select_music ────────────────────────────────────────────────

class TestSelectMusic:
    def _mk_cards(self, page, cards):
        music_cards = page.locator('div.card-container-tmocjc')
        music_cards.count = AsyncMock(return_value=len(cards))
        music_cards.nth = MagicMock(side_effect=lambda i: cards[i])
        if cards:
            first = MagicMock()
            first.hover = AsyncMock()
            first.locator = MagicMock(side_effect=cards[0].locator)
            music_cards.first = first
        return music_cards

    def test_xpath_happy_path(self):
        p = _mk_platform()
        page = _mk_page()
        music_btn = page.locator('xpath=//div[contains(@class, "container-right")]//span[text()="选择音乐"]')
        music_btn.count = AsyncMock(return_value=1)
        music_btn.click = AsyncMock()
        search = page.locator('input[placeholder="搜索音乐"]')
        search.wait_for = AsyncMock()
        search.fill = AsyncMock()
        card = MagicMock()
        card.text_content = AsyncMock(return_value='晴天 - 周杰伦')
        card.hover = AsyncMock()
        use_btn = MagicMock()
        use_btn.count = AsyncMock(return_value=1)
        use_btn.click = AsyncMock()
        card.locator = MagicMock(side_effect=lambda sel, **kw: use_btn if sel == 'button:has-text("使用")' else MagicMock())
        self._mk_cards(page, [card])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._select_music(page, '晴天'))
        music_btn.click.assert_awaited_once()
        search.fill.assert_awaited_once_with('晴天')
        card.hover.assert_awaited_once()
        use_btn.click.assert_awaited_once_with(force=True)

    def test_xpath_missing_fallback_text(self):
        p = _mk_platform()
        page = _mk_page()
        music_btn = page.locator('xpath=//div[contains(@class, "container-right")]//span[text()="选择音乐"]')
        music_btn.count = AsyncMock(return_value=0)
        text_btn = page.get_by_text('选择音乐', exact=True)
        text_btn.last.click = AsyncMock()
        search = page.locator('input[placeholder="搜索音乐"]')
        search.wait_for = AsyncMock()
        search.fill = AsyncMock()
        self._mk_cards(page, [])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._select_music(page, '晴天'))
        text_btn.last.click.assert_awaited_once()

    def test_no_match_uses_first_card(self):
        p = _mk_platform()
        page = _mk_page()
        music_btn = page.locator('xpath=//div[contains(@class, "container-right")]//span[text()="选择音乐"]')
        music_btn.count = AsyncMock(return_value=1)
        music_btn.click = AsyncMock()
        search = page.locator('input[placeholder="搜索音乐"]')
        search.wait_for = AsyncMock()
        search.fill = AsyncMock()
        card = MagicMock()
        card.text_content = AsyncMock(return_value='其他歌曲')
        card.hover = AsyncMock()
        use_btn = MagicMock()
        use_btn.count = AsyncMock(return_value=0)
        card.locator = MagicMock(side_effect=lambda sel, **kw: use_btn)
        self._mk_cards(page, [card])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._select_music(page, '晴天'))
        # 未命中文本 → 兜底使用第一张卡片
        first = page.locator('div.card-container-tmocjc').first
        first.hover.assert_awaited_once()
        assert any('未找到使用按钮' in str(c) for c in lg.warning.call_args_list)


# ── 热点: _set_hotspot ─────────────────────────────────────────────────

class TestHotspot:
    def test_exact_match(self):
        p = _mk_platform()
        page = _mk_page()
        hotspot_text = page.get_by_text('点击输入热点词', exact=True)
        hotspot_text.click = AsyncMock()
        opts = page.locator('div[role="option"]:not([aria-disabled="true"])')
        opt = MagicMock()
        opt.text_content = AsyncMock(return_value='旅行攻略')
        opt.click = AsyncMock()
        opts.count = AsyncMock(return_value=1)
        opts.nth = MagicMock(side_effect=lambda i: opt)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_hotspot(page, '旅行'))
        hotspot_text.click.assert_awaited_once()
        page.keyboard.insert_text.assert_awaited_once_with('旅行')
        opt.click.assert_awaited_once()

    def test_fallback_selector_and_first_option(self):
        p = _mk_platform()
        page = _mk_page()
        page.get_by_text('点击输入热点词', exact=True).click = AsyncMock()
        # 前两个 selector count=0 → 用第三个
        s1 = page.locator('div[role="option"]:not([aria-disabled="true"])')
        s1.count = AsyncMock(return_value=0)
        s2 = page.locator('[role="option"]:not([aria-disabled="true"])')
        s2.count = AsyncMock(return_value=0)
        s3 = page.locator('[class*="option"]:not([aria-disabled="true"])')
        s3.count = AsyncMock(return_value=1)
        opt = MagicMock()
        opt.text_content = AsyncMock(return_value='无关选项')
        s3.nth = MagicMock(side_effect=lambda i: opt)
        s3.first.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_hotspot(page, '旅行'))
        s3.first.click.assert_awaited_once()

    def test_no_options_enter_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        page.get_by_text('点击输入热点词', exact=True).click = AsyncMock()
        s1 = page.locator('div[role="option"]:not([aria-disabled="true"])')
        s1.count = AsyncMock(return_value=0)
        s2 = page.locator('[role="option"]:not([aria-disabled="true"])')
        s2.count = AsyncMock(return_value=0)
        s3 = page.locator('[class*="option"]:not([aria-disabled="true"])')
        s3.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_hotspot(page, '旅行'))
        page.keyboard.press.assert_awaited_once_with('Enter')
        assert any('未找到热点' in str(c) for c in lg.warning.call_args_list)

# ── 标签: _set_tag(位置/小程序/游戏手柄/标记万物/影视) ──────────────────

class TestSetTag:
    def _mk_selects(self, page, texts):
        """div.semi-select 列表:跳过含「合集」的,返回第一个非合集选择器。"""
        all_selects = page.locator('div.semi-select')
        mocks = []
        for t in texts:
            m = MagicMock()
            m.text_content = AsyncMock(return_value=t)
            m.click = AsyncMock()
            mocks.append(m)
        all_selects.count = AsyncMock(return_value=len(mocks))
        all_selects.nth = MagicMock(side_effect=lambda i: mocks[i])
        return mocks

    def _mk_options(self, page, texts, sel='[role="option"]'):
        opts = page.locator(sel)
        mocks = []
        for t in texts:
            m = MagicMock()
            m.text_content = AsyncMock(return_value=t)
            m.click = AsyncMock()
            mocks.append(m)
        opts.count = AsyncMock(return_value=len(mocks))
        opts.nth = MagicMock(side_effect=lambda i: mocks[i])
        if mocks:
            opts.first = mocks[0]
        return mocks

    def _mk_type_option(self, page, type_text):
        to = page.get_by_role('option', name=type_text)
        to.wait_for = AsyncMock()
        to.click = AsyncMock()
        return to

    def test_location_happy(self):
        p = _mk_platform()
        page = _mk_page()
        selects = self._mk_selects(page, ['选择合集', '添加位置标签'])
        self._mk_options(page, ['杭州'], sel='div[role="option"]')
        self._mk_type_option(page, '位置')
        loc = page.get_by_text('输入相关位置，让更多人看到你的作品', exact=True)
        loc.count = AsyncMock(return_value=1)
        loc.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_tag(page, 'location', '杭州'))
        selects[1].click.assert_awaited_once()
        loc.click.assert_awaited_once()
        page.keyboard.insert_text.assert_awaited_once_with('杭州')
        # find_and_click_option 完全匹配
        opt = page.locator('div[role="option"]').nth(0)
        opt.click.assert_awaited_once()

    def test_location_fallback_text(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_selects(page, ['标签'])
        self._mk_options(page, ['上海'], sel='div[role="option"]')
        self._mk_type_option(page, '位置')
        loc1 = page.get_by_text('输入相关位置，让更多人看到你的作品', exact=True)
        loc1.count = AsyncMock(return_value=0)
        loc2 = page.get_by_text('输入地理位置', exact=True)
        loc2.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_tag(page, 'location', '上海'))
        loc2.click.assert_awaited_once()

    def test_miniapp(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_selects(page, ['标签类型'])
        self._mk_options(page, ['抖音小程序'], sel='div[role="option"]:not([aria-disabled="true"])')
        self._mk_type_option(page, '小程序')
        mini = page.get_by_text('粘贴抖音小程序链接', exact=True)
        mini.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_tag(page, 'miniapp', 'xxx', mini_link='https://mini'))
        mini.click.assert_awaited_once()
        assert page.keyboard.insert_text.await_args.args[0] == 'xxx'

    def test_gamepad(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_selects(page, ['标签'])
        self._mk_type_option(page, '游戏手柄')
        game = page.get_by_text('添加作品同款游戏', exact=True)
        game.click = AsyncMock()
        game_opts = page.locator('div.semi-popover [class*="anchor-game-option"]')
        opt = MagicMock()
        opt.text_content = AsyncMock(return_value='我的世界：中国版')
        opt.click = AsyncMock()
        game_opts.count = AsyncMock(return_value=1)
        game_opts.nth = MagicMock(side_effect=lambda i: opt)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_tag(page, 'gamepad', '我的世界'))
        game.click.assert_awaited_once()
        opt.click.assert_awaited_once()

    def test_mark(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_selects(page, ['标签'])
        self._mk_type_option(page, '标记万物')
        mark_input = page.get_by_placeholder('请输入或选择标记的物品')
        mark_input.click = AsyncMock()
        mark_opts = page.locator('div.semi-popover [class*="option-"]')
        opt = MagicMock()
        opt.text_content = AsyncMock(return_value='镜头特写')
        opt.click = AsyncMock()
        mark_opts.count = AsyncMock(return_value=1)
        mark_opts.nth = MagicMock(side_effect=lambda i: opt)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_tag(page, 'mark', '镜头'))
        mark_input.click.assert_awaited_once()
        opt.click.assert_awaited_once()

    def test_film(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_selects(page, ['标签'])
        self._mk_type_option(page, '影视演艺')
        film_input = page.get_by_text('输入IP名称, 如 “少年的你”', exact=True)
        film_input.click = AsyncMock()
        film_opts = page.locator('[role="option"]')
        opt = MagicMock()
        opt.text_content = AsyncMock(return_value='少年的你')
        opt.click = AsyncMock()
        film_opts.count = AsyncMock(return_value=1)
        film_opts.nth = MagicMock(side_effect=lambda i: opt)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_tag(page, 'film', '少年'))
        film_input.click.assert_awaited_once()
        page.wait_for_selector.assert_awaited()
        opt.click.assert_awaited_once()

    def test_unknown_type_defaults_text_but_no_branch(self):
        """未知 tag_type:类型文本默认「位置」,但分支判断需精确匹配 → 不进入任何流程。"""
        p = _mk_platform()
        page = _mk_page()
        self._mk_selects(page, ['标签'])
        self._mk_type_option(page, '位置')  # 未知类型 → 下拉默认「位置」
        loc = page.get_by_text('输入相关位置，让更多人看到你的作品', exact=True)
        loc.count = AsyncMock(return_value=1)
        loc.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_tag(page, 'weird', '北京'))
        to = page.get_by_role('option', name='位置')
        to.click.assert_awaited_once()
        loc.click.assert_not_awaited()  # 未匹配分支,不进入位置流程

    def test_no_dropdown_warns(self):
        p = _mk_platform()
        page = _mk_page()
        all_selects = page.locator('div.semi-select')
        all_selects.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_tag(page, 'location', '杭州'))
        assert any('未找到标签类型选择器' in str(c) for c in lg.warning.call_args_list)

    def test_no_type_option_escape(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_selects(page, ['标签'])
        to = page.get_by_role('option', name='位置')
        to.wait_for = AsyncMock(side_effect=TimeoutError('no option'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_tag(page, 'location', '杭州'))
        page.keyboard.press.assert_awaited_once_with('Escape')
        assert any('未找到标签类型选项' in str(c) for c in lg.warning.call_args_list)

    def test_find_option_fallback_first(self):
        p = _mk_platform()
        page = _mk_page()
        self._mk_selects(page, ['标签'])
        opts = self._mk_options(page, ['完全不相关'], sel='div[role="option"]')
        self._mk_type_option(page, '位置')
        loc = page.get_by_text('输入相关位置，让更多人看到你的作品', exact=True)
        loc.count = AsyncMock(return_value=1)
        loc.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_tag(page, 'location', '杭州'))
        opts[0].click.assert_awaited_once()  # 无精确/包含匹配 → 第一个选项


# ── 位置标签: _set_location_tag ────────────────────────────────────────

class TestLocationTag:
    def test_happy_path(self):
        p = _mk_platform()
        page = _mk_page()
        loc_input = page.get_by_placeholder('输入相关位置，让更多人看到你的作品')
        loc_input.count = AsyncMock(return_value=1)
        loc_input.click = AsyncMock()
        option = page.locator('div[role="option"]')
        option.first.count = AsyncMock(return_value=1)
        option.first.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_location_tag(page, '杭州'))
        loc_input.click.assert_awaited_once()
        page.keyboard.type.assert_awaited_once_with('杭州')
        option.first.click.assert_awaited_once()

    def test_fallback_placeholder(self):
        p = _mk_platform()
        page = _mk_page()
        loc1 = page.get_by_placeholder('输入相关位置，让更多人看到你的作品')
        loc1.count = AsyncMock(return_value=0)
        loc2 = page.get_by_placeholder('输入地理位置')
        loc2.click = AsyncMock()
        option = page.locator('div[role="option"]')
        option.first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger'):
            _run(p._set_location_tag(page, '杭州'))
        loc2.click.assert_awaited_once()

    def test_no_result_escape(self):
        p = _mk_platform()
        page = _mk_page()
        loc_input = page.get_by_placeholder('输入相关位置，让更多人看到你的作品')
        loc_input.count = AsyncMock(return_value=1)
        loc_input.click = AsyncMock()
        option = page.locator('div[role="option"]')
        option.first.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_location_tag(page, '杭州'))
        page.keyboard.press.assert_awaited_once_with('Escape')
        assert any('未找到位置' in str(c) for c in lg.warning.call_args_list)


# ── AI 内容声明: _set_declaration ──────────────────────────────────────

class TestDeclaration:
    def test_happy_path(self):
        p = _mk_platform()
        page = _mk_page()
        select_box = page.locator('.selectBox-buZRzi')
        select_box.first.wait_for = AsyncMock()
        select_box.first.click = AsyncMock()
        page.evaluate = AsyncMock(side_effect=['AI生成内容', 'ok'])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_declaration(page, 'AI生成内容'))
        select_box.first.click.assert_awaited_once()
        assert page.evaluate.await_count == 2
        assert any('声明已确认' in str(c) for c in lg.info.call_args_list)

    def test_not_found_closes_modal(self):
        p = _mk_platform()
        page = _mk_page()
        select_box = page.locator('.selectBox-buZRzi')
        select_box.first.wait_for = AsyncMock()
        select_box.first.click = AsyncMock()
        page.evaluate = AsyncMock(return_value=None)
        close_btn = page.locator('.semi-modal-close')
        close_btn.count = AsyncMock(return_value=1)
        close_btn.first.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_declaration(page, 'AI生成内容'))
        close_btn.first.click.assert_awaited_once()
        assert any('未找到声明选项' in str(c) for c in lg.warning.call_args_list)

    def test_exception_warns(self):
        p = _mk_platform()
        page = _mk_page()
        select_box = page.locator('.selectBox-buZRzi')
        select_box.first.wait_for = AsyncMock(side_effect=TimeoutError('gone'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_declaration(page, 'AI生成内容'))
        assert any('声明设置失败' in str(c) for c in lg.warning.call_args_list)

# ── 深水区补充:视频第三方开关/合集、定时缺失告警、商品链接缺失分支 ─────

class TestVideoEdgeBranches:
    def test_third_party_switch_on_and_mix(self):
        """第三方内容开关打开 + 提供 mix_id → 点击开关并调用合集设置。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
            for name in ('_fill_title_and_description', '_set_thumbnail',
                         '_set_product_link', '_set_schedule_time', '_set_tag',
                         '_set_hotspot', '_handle_auto_video_cover', '_set_image_mix',
                         '_set_declaration'):
                setattr(p, name, AsyncMock())
            long_card = page.locator('[class^="long-card"] div:has-text("重新上传")')
            long_card.count = AsyncMock(return_value=1)
            switch = page.locator('[class^="info"] > [class^="first-part"] div div.semi-switch')
            switch.count = AsyncMock(return_value=1)
            switch_input = MagicMock()
            switch_input.click = AsyncMock()
            switch.locator = MagicMock(side_effect=lambda sel, **kw: (
                switch_input if sel == 'input.semi-switch-native-control' else MagicMock()))
            page.eval_on_selector = AsyncMock(return_value='semi-switch')  # 未选中
            publish_btn = page.get_by_role('button', name='发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.douyin.platform._PUBLISH_DRY_RUN', False):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                    account_file='ck.json', publish_strategy='immediate',
                    mix_id='mix-9',
                ))
            switch_input.click.assert_awaited_once()
            p._set_image_mix.assert_awaited_once()
            publish_btn.click.assert_awaited()

    def test_third_party_switch_already_checked_skips_click(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
            for name in ('_fill_title_and_description', '_set_thumbnail',
                         '_set_product_link', '_set_schedule_time', '_set_tag',
                         '_set_hotspot', '_handle_auto_video_cover', '_set_image_mix',
                         '_set_declaration'):
                setattr(p, name, AsyncMock())
            long_card = page.locator('[class^="long-card"] div:has-text("重新上传")')
            long_card.count = AsyncMock(return_value=1)
            switch = page.locator('[class^="info"] > [class^="first-part"] div div.semi-switch')
            switch.count = AsyncMock(return_value=1)
            switch_input = MagicMock()
            switch_input.click = AsyncMock()
            switch.locator = MagicMock(side_effect=lambda sel, **kw: (
                switch_input if sel == 'input.semi-switch-native-control' else MagicMock()))
            page.eval_on_selector = AsyncMock(return_value='semi-switch-checked semi-switch')
            publish_btn = page.get_by_role('button', name='发布', exact=True)
            publish_btn.count = AsyncMock(return_value=1)
            publish_btn.click = AsyncMock()
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.douyin.platform._PUBLISH_DRY_RUN', False):
                _run(p._upload_one_video(
                    title='T', file_path='/v/a.mp4', tags=[], publish_date=0,
                    account_file='ck.json', publish_strategy='immediate',
                ))
            switch_input.click.assert_not_awaited()

    def test_schedule_missing_all_warns(self):
        """日期格/时间开关/时/分/确认均缺失 → 逐项告警 + Enter 兜底 + 校验告警。"""
        p = _mk_platform()
        page = _mk_page()
        dt = datetime(2026, 8, 25, 14, 30, tzinfo=UTC)
        sels = {sel: page.locator(sel) for sel in [
            '.semi-datepicker-day:not(.semi-datepicker-day-disabled)[title="2026-08-25"]',
            '.semi-datepicker-switch-time',
            '.semi-scrolllist-item-wheel.undefined-list-hour li',
            '.semi-scrolllist-item-wheel.undefined-list-minute li',
            '.semi-popover button:has-text("确定")',
        ]}
        sels['.semi-datepicker-day:not(.semi-datepicker-day-disabled)[title="2026-08-25"]'].count = AsyncMock(return_value=0)
        sels['.semi-datepicker-switch-time'].count = AsyncMock(return_value=0)
        hour_item = MagicMock()
        hour_item.count = AsyncMock(return_value=0)
        sels['.semi-scrolllist-item-wheel.undefined-list-hour li'].filter = MagicMock(side_effect=lambda **kw: hour_item)
        minute_item = MagicMock()
        minute_item.count = AsyncMock(return_value=0)
        sels['.semi-scrolllist-item-wheel.undefined-list-minute li'].filter = MagicMock(side_effect=lambda **kw: minute_item)
        sels['.semi-popover button:has-text("确定")'].count = AsyncMock(return_value=0)
        page.input_value = AsyncMock(return_value='2026-08-25')  # 无 HH:MM → 校验告警
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            _run(p._set_schedule_time(page, dt))
        page.keyboard.press.assert_awaited_once_with('Enter')
        warns = ' '.join(str(c) for c in lg.warning.call_args_list)
        assert '未找到可选日期' in warns
        assert '未找到时间切换开关' in warns
        assert '未找到小时项' in warns
        assert '未找到分钟项' in warns
        assert '校验异常' in warns


class TestProductLinkEdge:
    def test_short_title_missing_returns_false(self):
        p = _mk_platform()
        page = _mk_page()
        add_tag = page.get_by_text('添加标签', exact=True)
        dropdown_chain = MagicMock()
        dropdown_chain.first.count = AsyncMock(return_value=1)
        dropdown_chain.first.click = AsyncMock()
        lvl3 = MagicMock()
        lvl3.locator = MagicMock(side_effect=lambda sel, **kw: (
            dropdown_chain if sel == '.semi-select' else MagicMock()))
        lvl2 = MagicMock()
        lvl2.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl3 if sel == '..' else MagicMock()))
        lvl1 = MagicMock()
        lvl1.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl2 if sel == '..' else MagicMock()))
        add_tag.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl1 if sel == '..' else MagicMock()))
        page.locator('[role="option"]:has-text("购物车")').click = AsyncMock()
        page.locator('input[placeholder="粘贴商品链接"]').fill = AsyncMock()
        page.locator('span:has-text("添加链接")').get_attribute = AsyncMock(return_value='')
        page.locator('span:has-text("添加链接")').click = AsyncMock()
        short_title = page.locator('input[placeholder="请输入商品短标题"]')
        short_title.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.douyin.platform.logger') as lg:
            result = _run(p._set_product_link(page, 'https://x', 't'))
        assert result is False
        assert any('未找到商品短标题输入框' in str(c) for c in lg.warning.call_args_list)

    def test_finish_disabled_close_button(self):
        """完成按钮 disabled 且无取消按钮 → 用 .semi-modal-close 关闭。"""
        p = _mk_platform()
        page = _mk_page()
        add_tag = page.get_by_text('添加标签', exact=True)
        dropdown_chain = MagicMock()
        dropdown_chain.first.count = AsyncMock(return_value=1)
        dropdown_chain.first.click = AsyncMock()
        lvl3 = MagicMock()
        lvl3.locator = MagicMock(side_effect=lambda sel, **kw: (
            dropdown_chain if sel == '.semi-select' else MagicMock()))
        lvl2 = MagicMock()
        lvl2.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl3 if sel == '..' else MagicMock()))
        lvl1 = MagicMock()
        lvl1.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl2 if sel == '..' else MagicMock()))
        add_tag.locator = MagicMock(side_effect=lambda sel, **kw: (
            lvl1 if sel == '..' else MagicMock()))
        page.locator('[role="option"]:has-text("购物车")').click = AsyncMock()
        page.locator('input[placeholder="粘贴商品链接"]').fill = AsyncMock()
        page.locator('span:has-text("添加链接")').get_attribute = AsyncMock(return_value='')
        page.locator('span:has-text("添加链接")').click = AsyncMock()
        short_title = page.locator('input[placeholder="请输入商品短标题"]')
        short_title.count = AsyncMock(return_value=1)
        short_title.fill = AsyncMock()
        finish = page.locator('button:has-text("完成编辑")')
        finish.get_attribute = AsyncMock(return_value='semi-button-disabled')
        cancel = page.locator('button:has-text("取消")')
        cancel.count = AsyncMock(return_value=0)
        close_btn = page.locator('.semi-modal-close')
        close_btn.click = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            result = _run(p._set_product_link(page, 'https://x', 't'))
        assert result is False
        close_btn.click.assert_awaited_once()
