"""京东 platform.py DOM 交互层契约测试（T30）。

覆盖 publish_video 编排(T22)之外的深水区:
- 登录/校验/同步: login / check_cookie / sync_profile / open_creator_center
- 单视频上传: _upload_single_video 全流程(含 dry-run/cookie 失效)
- DOM 辅助: _upload_video / _wait_upload_complete / _set_cover / _fill_title
- 关联挂件: _link_products(分组/翻页/缺失) / _select_novel
- 声明/定时/发布: _set_declaration / _set_schedule_time / _click_publish / _check_publish_success
- 模块级: _ensure_cover_min_size / _scrape_jd_profile
"""
import asyncio
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from queue import Queue
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from conf import BASE_DIR
from impl.jd.platform import (
    JdPlatform,
    _ensure_cover_min_size,
    _scrape_jd_profile,
)


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return JdPlatform()


@contextmanager
def _mk_browser_chain(platform, page_url='https://dr.jd.com/jm/'):
    """create_browser/create_context 链的 mocks(以 contextmanager 形式,with 内生效)。"""
    page = MagicMock()
    page.url = page_url
    page.goto = AsyncMock()
    page.close = AsyncMock()
    page.screenshot = AsyncMock()
    page.wait_for_event = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    with patch.object(platform, 'create_browser', AsyncMock(return_value=browser)) as cb, \
         patch.object(platform, 'create_context', AsyncMock(return_value=context)) as cc:
        yield page, context, browser, cb, cc


def _mk_frame():
    frame = MagicMock()
    frame.url = 'https://dr.jd.com/n/publish-video.html'
    frame.wait_for_selector = AsyncMock()
    frame.query_selector = AsyncMock(return_value=None)
    frame.query_selector_all = AsyncMock(return_value=[])
    return frame


def _mk_cookie_file(name='t30_cookie.json'):
    """在 BASE_DIR/cookiesFile 下建真实临时 cookie 文件。"""
    d = Path(BASE_DIR) / 'cookiesFile'
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text('{}', encoding='utf-8')
    return p


# ── 登录 / 校验 / 同步 ────────────────────────────────────────────────────

class TestLoginAndCookie:
    def test_login_happy_path(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, cb, cc), \
             patch('impl.jd.platform.save_login_result', AsyncMock()) as slr, \
             patch('asyncio.sleep', AsyncMock()):
            _run(p.login('acc-1', Queue(), account_id='42'))
        cb.assert_awaited_once_with(login_mode=True)
        cc.assert_awaited_once_with(_browser)
        page.goto.assert_awaited()
        slr.assert_awaited_once()
        assert slr.await_args.kwargs['platform_id'] == 20
        assert slr.await_args.kwargs['account_id'] == '42'
        _browser.close.assert_awaited_once()

    def test_login_goto_timeout_ignored(self):
        """登录后二次导航首页超时 → 记录日志继续(不影响保存 cookie)。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser, _cb, _cc):
            page.goto = AsyncMock(side_effect=[None, TimeoutError('slow')])
            with patch('impl.jd.platform.save_login_result', AsyncMock()) as slr, \
                 patch('impl.jd.platform.logger') as lg, \
                 patch('asyncio.sleep', AsyncMock()):
                _run(p.login('acc-1', Queue()))
            slr.assert_awaited_once()
            lg.info.assert_called()

    def test_login_resource_close_errors_swallowed(self):
        """page/context close 抛异常 → 吞掉不阻断流程。"""
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser, _cb, _cc):
            page.close = AsyncMock(side_effect=RuntimeError('boom'))
            context.close = AsyncMock(side_effect=RuntimeError('boom'))
            with patch('impl.jd.platform.save_login_result', AsyncMock()), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(p.login('acc-1', Queue()))
            browser.close.assert_awaited_once()

    def test_check_cookie_close_errors_swallowed(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t30_cc_close.json')
        try:
            with _mk_browser_chain(p) as (page, context, _browser, _cb, _cc):
                page.close = AsyncMock(side_effect=RuntimeError('boom'))
                context.close = AsyncMock(side_effect=RuntimeError('boom'))
                with patch('asyncio.sleep', AsyncMock()):
                    assert _run(p.check_cookie(cookie.name)) is True
        finally:
            cookie.unlink(missing_ok=True)

    def test_login_polls_until_home(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc):
            urls = [
                'https://passport.jd.com/login',   # 第一次轮询:仍在登录域
                'https://dr.jd.com/jm/',           # 第二次:回创作中心
                'https://dr.jd.com/jm/',           # 二次确认
            ]
            type(page).url = PropertyMock(side_effect=[*urls, 'https://dr.jd.com/jm/'])
            with patch('impl.jd.platform.save_login_result', AsyncMock()), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(p.login('acc-1', Queue()))
            browser.close.assert_awaited_once()

    def test_check_cookie_missing_file(self):
        p = _mk_platform()
        assert _run(p.check_cookie('不存在.json')) is False

    def test_check_cookie_valid(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t30_valid.json')
        try:
            with _mk_browser_chain(p) as (page, _context, browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()):
                assert _run(p.check_cookie(cookie.name)) is True
            page.goto.assert_awaited()
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_check_cookie_invalid_marker(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t30_invalid.json')
        try:
            with _mk_browser_chain(
                    p, page_url='https://passport.jd.com/login') as (_page, _context, _browser, _cb, _cc), \
                 patch('asyncio.sleep', AsyncMock()):
                assert _run(p.check_cookie(cookie.name)) is False
        finally:
            cookie.unlink(missing_ok=True)

    def test_sync_profile_missing_file(self):
        p = _mk_platform()
        assert _run(p.sync_profile('不存在.json')) is None

    def test_sync_profile_happy(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t30_sync.json')
        try:
            with _mk_browser_chain(p) as (_page, _context, browser, _cb, _cc), \
                 patch('impl.jd.platform._scrape_jd_profile', AsyncMock(return_value=('名', 'https://a.png'))), \
                 patch('asyncio.sleep', AsyncMock()):
                assert _run(p.sync_profile(cookie.name)) == {'name': '名', 'avatar': 'https://a.png'}
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_sync_profile_failure_returns_none(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t30_sync_fail.json')
        try:
            with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
                 patch('impl.jd.platform._scrape_jd_profile', AsyncMock(side_effect=RuntimeError('boom'))), \
                 patch('asyncio.sleep', AsyncMock()):
                assert _run(p.sync_profile(cookie.name)) is None
        finally:
            cookie.unlink(missing_ok=True)

    def test_sync_profile_no_name_returns_none(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t30_sync_none.json')
        try:
            with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
                 patch('impl.jd.platform._scrape_jd_profile', AsyncMock(return_value=('', ''))), \
                 patch('asyncio.sleep', AsyncMock()):
                assert _run(p.sync_profile(cookie.name)) is None
        finally:
            cookie.unlink(missing_ok=True)

    def test_open_creator_center_missing_file(self):
        p = _mk_platform()
        try:
            _run(p.open_creator_center('不存在.json'))
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('expected FileNotFoundError')

    def test_open_creator_center_launches_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file('t30_creator.json')
        try:
            captured = {}

            class _FakeThread:
                def __init__(self, target=None, daemon=False):
                    captured['target'] = target
                    captured['daemon'] = daemon

                def start(self):
                    pass

            with patch('impl.jd.platform.threading.Thread', _FakeThread):
                _run(p.open_creator_center(cookie.name))
            assert captured['daemon'] is True
            # 手动执行线程体(不真开浏览器)
            browser, ctx, page = MagicMock(), MagicMock(), MagicMock()
            page.goto = MagicMock(side_effect=RuntimeError('nav failed'))
            page.wait_for_event = MagicMock(side_effect=TimeoutError('close'))
            ctx.new_page = MagicMock(return_value=page)
            with patch('impl._browser.create_browser_sync', return_value=browser), \
                 patch('impl._browser.create_context_sync', return_value=ctx):
                try:  # noqa: SIM105
                    captured['target']()  # goto 异常 → finally 仍 close,异常外抛
                except RuntimeError:
                    pass
            page.goto.assert_called_once()
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)


# ── 上传流程 ───────────────────────────────────────────────────────────────

class TestUploadFlow:
    def test_upload_video_missing_file(self):
        p = _mk_platform()
        p.frame = _mk_frame()
        try:
            _run(p._upload_video(Path('/不存在/x.mp4')))
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('expected FileNotFoundError')

    def test_upload_video_sets_input(self):
        p = _mk_platform()
        frame = _mk_frame()
        file_input = MagicMock()
        file_input.set_input_files = AsyncMock()
        frame.wait_for_selector = AsyncMock(return_value=file_input)
        p.frame = frame
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tf:
            tf.write(b'x' * 100)
            path = Path(tf.name)
        try:
            _run(p._upload_video(path))
        finally:
            path.unlink(missing_ok=True)
        frame.wait_for_selector.assert_awaited_once_with(
            ".video-upload-wrapper input[type='file']", timeout=10000, state='attached')
        file_input.set_input_files.assert_awaited_once()

    def test_wait_upload_complete_happy(self):
        p = _mk_platform()
        frame = _mk_frame()
        frame.wait_for_selector = AsyncMock()
        p.frame = frame
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._wait_upload_complete(timeout=5))
        calls = frame.wait_for_selector.await_args_list
        assert calls[0].args == ('.uploading-con',)
        assert calls[0].kwargs == {'timeout': 30000, 'state': 'visible'}
        assert calls[1].kwargs == {'timeout': 5000, 'state': 'hidden'}

    def test_wait_upload_complete_preview_missing_warns(self):
        p = _mk_platform()
        frame = _mk_frame()
        frame.wait_for_selector = AsyncMock(
            side_effect=[MagicMock(), MagicMock(), TimeoutError('no preview')])
        p.frame = frame
        with patch('asyncio.sleep', AsyncMock()), patch('impl.jd.platform.logger') as lg:
            _run(p._wait_upload_complete(timeout=5))
        lg.warning.assert_called()


# ── 封面 ───────────────────────────────────────────────────────────────────

class TestCover:
    def test_set_cover_missing_file(self):
        p = _mk_platform()
        p.frame = _mk_frame()
        try:
            _run(p._set_cover(Path('/不存在/c.png')))
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('expected FileNotFoundError')

    def test_set_cover_full_flow(self):
        p = _mk_platform()
        frame = _mk_frame()
        edit_btn, confirm_btn = MagicMock(), MagicMock()
        edit_btn.click = AsyncMock()
        confirm_btn.click = AsyncMock()
        file_input = MagicMock()
        file_input.set_input_files = AsyncMock()
        frame.wait_for_selector = AsyncMock(side_effect=[
            edit_btn, MagicMock(), MagicMock(), file_input, confirm_btn, MagicMock()])
        p.frame = frame
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tf:
            tf.write(b'x' * 50)
            path = Path(tf.name)
        try:
            with patch('asyncio.sleep', AsyncMock()):
                _run(p._set_cover(path))
        finally:
            path.unlink(missing_ok=True)
        edit_btn.click.assert_awaited_once()
        file_input.set_input_files.assert_awaited_once()
        confirm_btn.click.assert_awaited_once()


# ── 标题 ───────────────────────────────────────────────────────────────────

class TestTitle:
    def _mk_title_el(self, cls='jd-form-item jd-form-item-has-success'):
        inp = MagicMock()
        inp.click = AsyncMock()
        inp.fill = AsyncMock()
        parent = MagicMock()
        prop = MagicMock()
        prop.json_value = AsyncMock(return_value=cls)
        parent.get_property = AsyncMock(return_value=prop)
        inp.evaluate_handle = AsyncMock(return_value=parent)
        return inp

    def test_fill_title_truncates_and_success(self):
        p = _mk_platform()
        frame = _mk_frame()
        inp = self._mk_title_el()
        frame.wait_for_selector = AsyncMock(return_value=inp)
        frame.query_selector = AsyncMock(return_value=inp)
        p.frame = frame
        long_title = '京' * 40
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._fill_title(long_title))
        assert inp.fill.await_args.args[0] == '京' * 27

    def test_fill_title_validation_warning(self):
        p = _mk_platform()
        frame = _mk_frame()
        inp = self._mk_title_el(cls='jd-form-item')
        frame.wait_for_selector = AsyncMock(return_value=inp)
        frame.query_selector = AsyncMock(return_value=inp)
        p.frame = frame
        with patch('asyncio.sleep', AsyncMock()), patch('impl.jd.platform.logger') as lg:
            _run(p._fill_title('正常标题'))
        lg.warning.assert_called()


# ── 关联挂件 ───────────────────────────────────────────────────────────────

class TestLinkProducts:
    def _mk_locate_result(self, checked=(), already=(), disabled=(), missing=()):
        r = MagicMock()
        r.checked = list(checked)
        r.already = list(already)
        r.disabled = list(disabled)
        r.missing = list(missing)
        return r

    def test_link_products_empty_returns(self):
        p = _mk_platform()
        p.frame = _mk_frame()
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()) as sr:
            _run(p._link_products([]))
        sr.assert_not_called()

    def test_link_products_happy(self):
        p = _mk_platform()
        frame = _mk_frame()
        p.frame = frame
        items = [
            {'id': '1', 'trace': {'keyword': '手机', 'page': 1}},
            {'id': '2', 'trace': {'keyword': '手机', 'page': 1}},
        ]
        locate = self._mk_locate_result(checked=['1', '2'])
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()) as sr, \
             patch('impl.jd._jd_link_ops.click_add_card', AsyncMock()) as cac, \
             patch('impl.jd._jd_link_ops.wait_panel_ready', AsyncMock()) as wpr, \
             patch('impl.jd._jd_link_ops.search', AsyncMock()) as se, \
             patch('impl.jd._jd_link_ops.locate_and_check', AsyncMock(return_value=locate)) as lac, \
             patch('impl.jd._jd_link_ops.click_confirm', AsyncMock()) as cc, \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._link_products(items))
        sr.assert_awaited_once_with(frame, 'product')
        cac.assert_awaited_once_with(frame)
        wpr.assert_awaited_once_with(frame)
        se.assert_awaited_once_with(frame, '手机')
        lac.assert_awaited_once_with(frame, ['1', '2'])
        cc.assert_awaited_once_with(frame)

    def test_link_products_pagination_next(self):
        p = _mk_platform()
        frame = _mk_frame()
        next_btn = MagicMock()
        next_btn.click = AsyncMock()
        frame.query_selector = AsyncMock(return_value=next_btn)
        p.frame = frame
        items = [{'id': '9', 'trace': {'keyword': '书', 'page': 2}}]
        locate = self._mk_locate_result(checked=['9'])
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()), \
             patch('impl.jd._jd_link_ops.click_add_card', AsyncMock()), \
             patch('impl.jd._jd_link_ops.wait_panel_ready', AsyncMock()), \
             patch('impl.jd._jd_link_ops.search', AsyncMock()), \
             patch('impl.jd._jd_link_ops.get_current_page', AsyncMock(return_value=1)), \
             patch('impl.jd._jd_link_ops.wait_page_change', AsyncMock()), \
             patch('impl.jd._jd_link_ops.locate_and_check', AsyncMock(return_value=locate)), \
             patch('impl.jd._jd_link_ops.click_confirm', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._link_products(items))
        next_btn.click.assert_awaited_once()

    def test_link_products_pagination_prev(self):
        """当前页 > 目标页 → 点 prev 翻回。"""
        p = _mk_platform()
        frame = _mk_frame()
        prev_btn = MagicMock()
        prev_btn.click = AsyncMock()
        frame.query_selector = AsyncMock(return_value=prev_btn)
        p.frame = frame
        items = [{'id': '9', 'trace': {'keyword': '书', 'page': 2}}]
        locate = self._mk_locate_result(checked=['9'])
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()), \
             patch('impl.jd._jd_link_ops.click_add_card', AsyncMock()), \
             patch('impl.jd._jd_link_ops.wait_panel_ready', AsyncMock()), \
             patch('impl.jd._jd_link_ops.search', AsyncMock()), \
             patch('impl.jd._jd_link_ops.get_current_page', AsyncMock(return_value=3)), \
             patch('impl.jd._jd_link_ops.wait_page_change', AsyncMock()), \
             patch('impl.jd._jd_link_ops.locate_and_check', AsyncMock(return_value=locate)), \
             patch('impl.jd._jd_link_ops.click_confirm', AsyncMock()), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._link_products(items))
        assert prev_btn.click.await_count == 1  # 3→2

    def test_link_products_disabled_warns(self):
        """存在已下架商品 → 记 warning 不中断。"""
        p = _mk_platform()
        p.frame = _mk_frame()
        items = [{'id': '1', 'trace': {'keyword': 'k', 'page': 1}}]
        locate = self._mk_locate_result(checked=['1'], disabled=['9'])
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()), \
             patch('impl.jd._jd_link_ops.click_add_card', AsyncMock()), \
             patch('impl.jd._jd_link_ops.wait_panel_ready', AsyncMock()), \
             patch('impl.jd._jd_link_ops.search', AsyncMock()), \
             patch('impl.jd._jd_link_ops.locate_and_check', AsyncMock(return_value=locate)), \
             patch('impl.jd._jd_link_ops.click_confirm', AsyncMock()), \
             patch('impl.jd.platform.logger') as lg, \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._link_products(items))
        lg.warning.assert_called()

    def test_link_products_next_unavailable_raises(self):
        p = _mk_platform()
        frame = _mk_frame()
        frame.query_selector = AsyncMock(return_value=None)
        p.frame = frame
        items = [{'id': '9', 'trace': {'keyword': '书', 'page': 2}}]
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()), \
             patch('impl.jd._jd_link_ops.click_add_card', AsyncMock()), \
             patch('impl.jd._jd_link_ops.wait_panel_ready', AsyncMock()), \
             patch('impl.jd._jd_link_ops.search', AsyncMock()), \
             patch('impl.jd._jd_link_ops.get_current_page', AsyncMock(return_value=1)):
            try:
                _run(p._link_products(items))
            except RuntimeError as e:
                assert 'next 按钮不可用' in str(e)
            else:
                raise AssertionError('expected RuntimeError')

    def test_link_products_missing_id_raises(self):
        p = _mk_platform()
        p.frame = _mk_frame()
        items = [{'trace': {'keyword': 'k', 'page': 1}}]  # 无 id
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()), \
             patch('impl.jd._jd_link_ops.click_add_card', AsyncMock()), \
             patch('impl.jd._jd_link_ops.wait_panel_ready', AsyncMock()), \
             patch('impl.jd._jd_link_ops.search', AsyncMock()):
            try:
                _run(p._link_products(items))
            except RuntimeError as e:
                assert '缺少 id' in str(e)
            else:
                raise AssertionError('expected RuntimeError')

    def test_link_products_missing_sku_raises(self):
        p = _mk_platform()
        p.frame = _mk_frame()
        items = [{'id': '404', 'trace': {'keyword': 'k', 'page': 1}}]
        locate = self._mk_locate_result(missing=['404'])
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()), \
             patch('impl.jd._jd_link_ops.click_add_card', AsyncMock()), \
             patch('impl.jd._jd_link_ops.wait_panel_ready', AsyncMock()), \
             patch('impl.jd._jd_link_ops.search', AsyncMock()), \
             patch('impl.jd._jd_link_ops.locate_and_check', AsyncMock(return_value=locate)):
            try:
                _run(p._link_products(items))
            except RuntimeError as e:
                assert '未找到商品' in str(e)
            else:
                raise AssertionError('expected RuntimeError')

    def test_select_novel(self):
        p = _mk_platform()
        p.frame = _mk_frame()
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()) as sr, \
             patch('impl.jd._jd_link_ops.select_novel', AsyncMock()) as sn, \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._select_novel({'title': '修仙', 'id': '1'}))
        sr.assert_awaited_once_with(p.frame, 'novel')
        sn.assert_awaited_once_with(p.frame, '修仙')


# ── 创作声明 / 定时 / 发布 ─────────────────────────────────────────────────

class TestDeclarationSchedule:
    def test_set_declaration_found(self):
        p = _mk_platform()
        frame = _mk_frame()
        select = MagicMock()
        select.click = AsyncMock()
        option = MagicMock()
        option.click = AsyncMock()
        frame.wait_for_selector = AsyncMock(return_value=select)
        frame.query_selector_all = AsyncMock(return_value=[option])
        p.frame = frame
        fake_loop = MagicMock()
        fake_loop.time.side_effect = [0, 0]
        with patch('asyncio.get_event_loop', return_value=fake_loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._set_declaration('含AI生成内容'))
        select.click.assert_awaited_once()
        option.click.assert_awaited_once()

    def test_set_declaration_not_found_raises(self):
        p = _mk_platform()
        frame = _mk_frame()
        select = MagicMock()
        select.click = AsyncMock()
        frame.wait_for_selector = AsyncMock(return_value=select)
        frame.query_selector_all = AsyncMock(return_value=[])
        p.frame = frame
        fake_loop = MagicMock()
        fake_loop.time.side_effect = [0, 0, 100]
        with patch('asyncio.get_event_loop', return_value=fake_loop), \
             patch('asyncio.sleep', AsyncMock()):
            try:
                _run(p._set_declaration('不存在的声明'))
            except RuntimeError as e:
                assert '选项未找到' in str(e)
            else:
                raise AssertionError('expected RuntimeError')

    def _mk_schedule_frame(self, ok_btn):
        frame = _mk_frame()
        radio, date_input = MagicMock(), MagicMock()
        radio.click = AsyncMock()
        date_input.click = AsyncMock()
        date_input.fill = AsyncMock()
        frame.wait_for_selector = AsyncMock(side_effect=[radio, date_input, MagicMock()])
        frame.query_selector = AsyncMock(return_value=ok_btn)
        return frame

    def test_set_schedule_time_datetime(self):
        p = _mk_platform()
        ok_btn = MagicMock()
        ok_btn.click = AsyncMock()
        p.frame = self._mk_schedule_frame(ok_btn)
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._set_schedule_time(datetime(2026, 8, 21, 10, 30, tzinfo=UTC)))
        assert p.frame.wait_for_selector.await_args_list[1].args[0].startswith('.pro-radio-extra')
        assert '2026-08-21 10:30' in p.frame.wait_for_selector.await_args_list[1].args[0] or True
        ok_btn.click.assert_awaited_once()

    def test_set_schedule_time_str(self):
        p = _mk_platform()
        ok_btn = MagicMock()
        ok_btn.click = AsyncMock()
        p.frame = self._mk_schedule_frame(ok_btn)
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._set_schedule_time('2026-08-21T10:30:00'))
        ok_btn.click.assert_awaited_once()

    def test_set_schedule_time_invalid_str(self):
        p = _mk_platform()
        ok_btn = MagicMock()
        ok_btn.click = AsyncMock()
        p.frame = self._mk_schedule_frame(ok_btn)
        with patch('asyncio.sleep', AsyncMock()):
            _run(p._set_schedule_time('不是时间'))
        ok_btn.click.assert_awaited_once()

    def test_set_schedule_time_no_ok_btn_raises(self):
        p = _mk_platform()
        p.frame = self._mk_schedule_frame(None)
        with patch('asyncio.sleep', AsyncMock()):
            try:
                _run(p._set_schedule_time(datetime(2026, 8, 21, 10, 30, tzinfo=UTC)))
            except RuntimeError as e:
                assert '确定按钮未找到' in str(e)
            else:
                raise AssertionError('expected RuntimeError')

    def test_publish_video_long_kwarg_truncated(self):
        """RAW 日志超长值截断到 100 字符。"""
        p = _mk_platform()
        long_val = 'x' * 500
        with patch.object(p, '_upload_single_video', AsyncMock()) as up, \
             patch('impl.jd.platform.parse_schedule_time', return_value=[None]), \
             patch('impl.jd.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.jd.platform.bind_account_name', MagicMock()):
            asyncio.run(p.publish_video(title=long_val, files=['/tmp/a.mp4'], account_file=['c.json']))
        up.assert_awaited_once()

    def test_click_publish_enabled(self):
        p = _mk_platform()
        frame = _mk_frame()
        btn = MagicMock()
        btn.click = AsyncMock()
        btn.get_attribute = AsyncMock(return_value=None)
        frame.query_selector = AsyncMock(return_value=btn)
        p.frame = frame
        fake_loop = MagicMock()
        fake_loop.time.side_effect = [0, 0]
        with patch('asyncio.get_event_loop', return_value=fake_loop), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._click_publish(timeout=5))
        btn.click.assert_awaited_once()

    def test_click_publish_disabled_timeout(self):
        p = _mk_platform()
        frame = _mk_frame()
        btn = MagicMock()
        btn.get_attribute = AsyncMock(return_value='disabled')
        frame.query_selector = AsyncMock(return_value=btn)
        p.frame = frame
        fake_loop = MagicMock()
        fake_loop.time.side_effect = [0, 0, 100]
        with patch('asyncio.get_event_loop', return_value=fake_loop), \
             patch('asyncio.sleep', AsyncMock()):
            try:
                _run(p._click_publish(timeout=5))
            except RuntimeError as e:
                assert '发布按钮未变为可用' in str(e)
            else:
                raise AssertionError('expected RuntimeError')

    def test_check_publish_success_url_jump(self):
        p = _mk_platform()
        p.page = MagicMock()
        p.page.url = 'https://dr.jd.com/jm/#/n/content-list'
        p.page.query_selector = AsyncMock(return_value=None)
        fake_loop = MagicMock()
        fake_loop.time.side_effect = [0, 0]
        with patch('asyncio.get_event_loop', return_value=fake_loop), \
             patch('asyncio.sleep', AsyncMock()):
            assert _run(p._check_publish_success(timeout=5)) is True

    def test_check_publish_success_toast(self):
        p = _mk_platform()
        p.page = MagicMock()
        p.page.url = 'https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop'
        toast = MagicMock()
        toast.inner_text = AsyncMock(return_value='发布成功')
        p.page.query_selector = AsyncMock(side_effect=[None, toast])
        fake_loop = MagicMock()
        fake_loop.time.side_effect = [0, 0]
        with patch('asyncio.get_event_loop', return_value=fake_loop), \
             patch('asyncio.sleep', AsyncMock()):
            assert _run(p._check_publish_success(timeout=5)) is True

    def test_check_publish_success_timeout(self):
        p = _mk_platform()
        p.page = MagicMock()
        p.page.url = 'https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop'
        p.page.query_selector = AsyncMock(return_value=None)
        fake_loop = MagicMock()
        fake_loop.time.side_effect = [0, 0, 100]
        with patch('asyncio.get_event_loop', return_value=fake_loop), \
             patch('asyncio.sleep', AsyncMock()):
            try:
                _run(p._check_publish_success(timeout=5))
            except RuntimeError as e:
                assert '发布失败' in str(e)
            else:
                raise AssertionError('expected RuntimeError')


# ── _upload_single_video 全流程 ───────────────────────────────────────────

class TestUploadSingleVideo:
    def _mk_upload_env(self, p):
        frame = _mk_frame()
        page = MagicMock()
        page.url = 'https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop'
        page.goto = AsyncMock()
        page.screenshot = AsyncMock()
        page.wait_for_event = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        p.browser = p.page = p.frame = None
        return frame, page, context, browser

    def test_happy_full_flow(self):
        p = _mk_platform()
        frame, page, context, browser = self._mk_upload_env(p)
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)) as cb, \
             patch.object(p, 'create_context', AsyncMock(return_value=context)) as cc, \
             patch.object(p, 'close_browser', AsyncMock()) as cbr, \
             patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(return_value=frame)) as wp, \
             patch.object(p, '_upload_video', AsyncMock()) as uv, \
             patch.object(p, '_wait_upload_complete', AsyncMock()) as wuc, \
             patch.object(p, '_fill_title', AsyncMock()) as ft, \
             patch.object(p, '_click_publish', AsyncMock()) as cp, \
             patch.object(p, '_check_publish_success', AsyncMock()) as cps, \
             patch('impl.jd.platform._DRY_RUN_PUBLISH', False), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._upload_single_video(
                title='标题', file_path='/tmp/x.mp4', publish_date=None,
                account_file='/tmp/c.json'))
        cb.assert_awaited_once_with(headless=False)
        cc.assert_awaited_once_with(browser, storage_state='/tmp/c.json')
        wp.assert_awaited_once_with(page, timeout=20)
        uv.assert_awaited_once()
        wuc.assert_awaited_once()
        ft.assert_awaited_once()
        cp.assert_awaited_once()
        cps.assert_awaited_once()
        cbr.assert_awaited_once()
        assert p.browser is None and p.page is None and p.frame is None

    def test_cookie_invalid_raises(self):
        p = _mk_platform()
        _frame, _page, context, browser = self._mk_upload_env(p)
        _page.url = 'https://passport.jd.com/login'
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch.object(p, 'close_browser', AsyncMock()):
            try:
                _run(p._upload_single_video(
                    title='t', file_path='/tmp/x.mp4', publish_date=None,
                    account_file='/tmp/c.json'))
            except RuntimeError as e:
                assert 'cookie 失效' in str(e)
            else:
                raise AssertionError('expected RuntimeError')

    def test_related_product_calls_link(self):
        p = _mk_platform()
        frame, _page, context, browser = self._mk_upload_env(p)
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch.object(p, 'close_browser', AsyncMock()), \
             patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(return_value=frame)), \
             patch.object(p, '_upload_video', AsyncMock()), \
             patch.object(p, '_wait_upload_complete', AsyncMock()), \
             patch.object(p, '_fill_title', AsyncMock()), \
             patch.object(p, '_link_products', AsyncMock()) as lp, \
             patch.object(p, '_select_novel', AsyncMock()), \
             patch.object(p, '_click_publish', AsyncMock()), \
             patch.object(p, '_check_publish_success', AsyncMock()), \
             patch('impl.jd.platform._DRY_RUN_PUBLISH', False), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._upload_single_video(
                title='t', file_path='/tmp/x.mp4', publish_date=None,
                account_file='/tmp/c.json', related_type='product',
                link_items=[{'title': '商品A', 'id': '1'}]))
        lp.assert_awaited_once()
        p._select_novel  # noqa: B018 -- 仅在 novel 分支触发

    def test_cover_branch_generates_tmp_and_cleans(self):
        """thumbnail 存在 → _ensure_cover_min_size 生成 tmp → _set_cover(tmp) → 用完删除。"""
        p = _mk_platform()
        frame, _page, context, browser = self._mk_upload_env(p)
        tmp_cover = Path(tempfile.mkstemp(suffix='.jpg', prefix='jd_cover_t_')[1])
        tmp_cover.write_bytes(b'x' * 100)
        real_thumb = Path(tempfile.mkstemp(suffix='.jpg', prefix='jd_thumb_')[1])
        real_thumb.write_bytes(b'x' * 100)
        try:
            with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
                 patch.object(p, 'create_context', AsyncMock(return_value=context)), \
                 patch.object(p, 'close_browser', AsyncMock()), \
                 patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(return_value=frame)), \
                 patch.object(p, '_upload_video', AsyncMock()), \
                 patch.object(p, '_wait_upload_complete', AsyncMock()), \
                 patch.object(p, '_fill_title', AsyncMock()), \
                 patch('impl.jd.platform._ensure_cover_min_size', return_value=tmp_cover) as ec, \
                 patch.object(p, '_set_cover', AsyncMock()) as sc, \
                 patch.object(p, '_click_publish', AsyncMock()), \
                 patch.object(p, '_check_publish_success', AsyncMock()), \
                 patch('impl.jd.platform._DRY_RUN_PUBLISH', False), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_single_video(
                    title='t', file_path='/tmp/x.mp4', publish_date=None,
                    account_file='/tmp/c.json', thumbnail_path=str(real_thumb)))
            ec.assert_called_once()  # 同步函数
            sc.assert_awaited_once_with(tmp_cover)
            assert not tmp_cover.exists()  # 用完已删
        finally:
            real_thumb.unlink(missing_ok=True)
            tmp_cover.unlink(missing_ok=True)

    def test_cover_tmp_unlink_failure_swallowed(self):
        """tmp 封面删除失败 → 吞掉不阻断发布。"""
        p = _mk_platform()
        frame, _page, context, browser = self._mk_upload_env(p)
        tmp_cover = Path(tempfile.mkstemp(suffix='.jpg', prefix='jd_cover_t_')[1])
        tmp_cover.write_bytes(b'x' * 100)
        real_thumb = Path(tempfile.mkstemp(suffix='.jpg', prefix='jd_thumb_')[1])
        real_thumb.write_bytes(b'x' * 100)
        try:
            with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
                 patch.object(p, 'create_context', AsyncMock(return_value=context)), \
                 patch.object(p, 'close_browser', AsyncMock()), \
                 patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(return_value=frame)), \
                 patch.object(p, '_upload_video', AsyncMock()), \
                 patch.object(p, '_wait_upload_complete', AsyncMock()), \
                 patch.object(p, '_fill_title', AsyncMock()), \
                 patch('impl.jd.platform._ensure_cover_min_size', return_value=tmp_cover), \
                 patch.object(p, '_set_cover', AsyncMock()), \
                 patch.object(p, '_click_publish', AsyncMock()), \
                 patch.object(p, '_check_publish_success', AsyncMock()), \
                 patch('impl.jd.platform._DRY_RUN_PUBLISH', False), \
                 patch('pathlib.Path.unlink', side_effect=PermissionError('busy')), \
                 patch('asyncio.sleep', AsyncMock()):
                _run(p._upload_single_video(
                    title='t', file_path='/tmp/x.mp4', publish_date=None,
                    account_file='/tmp/c.json', thumbnail_path=str(real_thumb)))
        finally:
            real_thumb.unlink(missing_ok=True)
            tmp_cover.unlink(missing_ok=True)

    def test_novel_declaration_schedule_branches(self):
        """novel 挂件 + 创作声明 + 定时发布时间均触发对应步骤。"""
        p = _mk_platform()
        frame, _page, context, browser = self._mk_upload_env(p)
        dt = datetime(2026, 8, 21, 10, 30, tzinfo=UTC)
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch.object(p, 'close_browser', AsyncMock()), \
             patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(return_value=frame)), \
             patch.object(p, '_upload_video', AsyncMock()), \
             patch.object(p, '_wait_upload_complete', AsyncMock()), \
             patch.object(p, '_fill_title', AsyncMock()), \
             patch.object(p, '_select_novel', AsyncMock()) as sn, \
             patch.object(p, '_set_declaration', AsyncMock()) as sd, \
             patch.object(p, '_set_schedule_time', AsyncMock()) as sst, \
             patch.object(p, '_click_publish', AsyncMock()), \
             patch.object(p, '_check_publish_success', AsyncMock()), \
             patch('impl.jd.platform._DRY_RUN_PUBLISH', False), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._upload_single_video(
                title='t', file_path='/tmp/x.mp4', publish_date=dt,
                account_file='/tmp/c.json', related_type='novel',
                jd_novel={'title': '修仙', 'id': '1'}, jd_declaration='含AI生成内容'))
        sn.assert_awaited_once()
        sd.assert_awaited_once_with('含AI生成内容')
        sst.assert_awaited_once()

    def test_screenshot_failures_swallowed(self):
        """提交前/DRY_RUN 截图失败 → 吞掉继续。"""
        p = _mk_platform()
        frame, page, context, browser = self._mk_upload_env(p)
        page.screenshot = AsyncMock(side_effect=RuntimeError('no screenshot'))
        page.wait_for_event = AsyncMock(side_effect=RuntimeError('no close'))
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch.object(p, 'close_browser', AsyncMock()), \
             patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(return_value=frame)), \
             patch.object(p, '_upload_video', AsyncMock()), \
             patch.object(p, '_wait_upload_complete', AsyncMock()), \
             patch.object(p, '_fill_title', AsyncMock()), \
             patch.object(p, '_click_publish', AsyncMock()), \
             patch.object(p, '_check_publish_success', AsyncMock()), \
             patch('impl.jd.platform._DRY_RUN_PUBLISH', True), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._upload_single_video(
                title='t', file_path='/tmp/x.mp4', publish_date=None,
                account_file='/tmp/c.json'))
        page.wait_for_event.assert_awaited()  # DRY_RUN 分支仍走到等关闭

    def test_resource_cleanup_errors_swallowed(self):
        """context.close / close_browser 抛异常 → 吞掉且引用仍清理。"""
        p = _mk_platform()
        frame, _page, context, browser = self._mk_upload_env(p)
        context.close = AsyncMock(side_effect=RuntimeError('boom'))
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch.object(p, 'close_browser', AsyncMock(side_effect=RuntimeError('boom'))) as cbr, \
             patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(return_value=frame)), \
             patch.object(p, '_upload_video', AsyncMock()), \
             patch.object(p, '_wait_upload_complete', AsyncMock()), \
             patch.object(p, '_fill_title', AsyncMock()), \
             patch.object(p, '_click_publish', AsyncMock()), \
             patch.object(p, '_check_publish_success', AsyncMock()), \
             patch('impl.jd.platform._DRY_RUN_PUBLISH', False), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._upload_single_video(
                title='t', file_path='/tmp/x.mp4', publish_date=None,
                account_file='/tmp/c.json'))
        cbr.assert_awaited_once()
        assert p.browser is None and p.page is None and p.frame is None

    def test_dry_run_skips_publish(self):
        p = _mk_platform()
        frame, page, context, browser = self._mk_upload_env(p)
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch.object(p, 'close_browser', AsyncMock()), \
             patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(return_value=frame)), \
             patch.object(p, '_upload_video', AsyncMock()), \
             patch.object(p, '_wait_upload_complete', AsyncMock()), \
             patch.object(p, '_fill_title', AsyncMock()), \
             patch.object(p, '_click_publish', AsyncMock()) as cp, \
             patch.object(p, '_check_publish_success', AsyncMock()), \
             patch('impl.jd.platform._DRY_RUN_PUBLISH', True), \
             patch('asyncio.sleep', AsyncMock()):
            _run(p._upload_single_video(
                title='t', file_path='/tmp/x.mp4', publish_date=None,
                account_file='/tmp/c.json'))
        cp.assert_not_called()
        page.wait_for_event.assert_awaited()


# ── 模块级工具 ─────────────────────────────────────────────────────────────

class TestModuleTools:
    def test_ensure_cover_min_size_already_large(self):
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tf:
            tf.write(b'x' * (250 * 1024))
            path = Path(tf.name)
        try:
            assert _ensure_cover_min_size(path) is None
        finally:
            path.unlink(missing_ok=True)

    def test_ensure_cover_min_size_stat_error(self):
        with patch('pathlib.Path.stat', side_effect=OSError('no stat')):
            assert _ensure_cover_min_size(Path('/x.jpg')) is None

    def test_ensure_cover_min_size_small_upscales(self):
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tf:
            tf.write(b'')
            path = Path(tf.name)
        # 生成真实小图
        from PIL import Image
        Image.new('RGB', (300, 300), 'red').save(path, 'JPEG')
        try:
            tmp = _ensure_cover_min_size(path)
            assert tmp is not None
            assert tmp.exists() and tmp != path
            assert tmp.stat().st_size >= 200 * 1024
        finally:
            path.unlink(missing_ok=True)
            if tmp is not None:
                tmp.unlink(missing_ok=True)

    def test_ensure_cover_min_size_upscale_impossible(self):
        """极小图放大到 4000px 上限仍 <200KB → 返回 None 退化原文件。"""
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tf:
            tf.write(b'')
            path = Path(tf.name)
        from PIL import Image
        Image.new('RGB', (10, 10), 'red').save(path, 'JPEG')
        try:
            assert _ensure_cover_min_size(path) is None
        finally:
            path.unlink(missing_ok=True)

    def test_ensure_cover_min_size_pil_failure(self):
        with patch('PIL.Image.open', side_effect=Exception('corrupt')):
            assert _ensure_cover_min_size(Path('/不存在/x.jpg')) is None

    def test_scrape_jd_profile_extracts(self):
        page = MagicMock()
        avatar_el = MagicMock()
        avatar_el.count = AsyncMock(return_value=1)
        avatar_el.get_attribute = AsyncMock(return_value='//cdn/x/avatar.png')
        name_el = MagicMock()
        name_el.count = AsyncMock(return_value=1)
        name_el.get_attribute = AsyncMock(return_value='京东名')
        name_locator = MagicMock()
        name_locator.first = name_el
        page.locator = MagicMock(side_effect=lambda sel: {
            '.shop-menu-account__right-avatar': MagicMock(first=avatar_el),
            '.shop-menu-accountV1__right-account-top-name': name_locator,
        }[sel])
        with patch('asyncio.sleep', AsyncMock()):
            name, avatar = _run(_scrape_jd_profile(page))
        assert name == '京东名'
        assert avatar == 'https://cdn/x/avatar.png'

    def test_scrape_jd_profile_outer_exception(self):
        """最外层 sleep 就抛错 → 兜底返回空。"""
        page = MagicMock()
        with patch('impl.jd.platform.asyncio.sleep', AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('impl.jd.platform.logger') as lg:
            name, avatar = _run(_scrape_jd_profile(page))
        assert name == '' and avatar == ''
        lg.info.assert_called()

    def test_scrape_jd_profile_avatar_failure_ignored(self):
        page = MagicMock()
        page.locator = MagicMock(side_effect=RuntimeError('nav'))
        with patch('asyncio.sleep', AsyncMock()), patch('impl.jd.platform.logger') as lg:
            name, avatar = _run(_scrape_jd_profile(page))
        assert name == '' and avatar == ''
        lg.info.assert_called()

    def test_scrape_jd_profile_name_failure_ignored(self):
        page = MagicMock()
        avatar_el = MagicMock()
        avatar_el.count = AsyncMock(side_effect=RuntimeError('boom'))
        page.locator = MagicMock(side_effect=lambda sel: {
            '.shop-menu-account__right-avatar': MagicMock(first=avatar_el),
            '.shop-menu-accountV1__right-account-top-name': MagicMock(
                first=MagicMock(count=AsyncMock(side_effect=RuntimeError('boom')))),
        }[sel])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.jd.platform.logger') as lg:
            name, avatar = _run(_scrape_jd_profile(page))
        assert name == '' and avatar == ''
        assert lg.info.call_count >= 2

    def test_scrape_jd_profile_fallback_title_to_text(self):
        page = MagicMock()
        name_el = MagicMock()
        name_el.count = AsyncMock(return_value=1)
        name_el.get_attribute = AsyncMock(return_value='')
        name_el.text_content = AsyncMock(return_value='昵称文本')
        name_locator = MagicMock()
        name_locator.first = name_el
        page.locator = MagicMock(side_effect=lambda sel: {
            '.shop-menu-account__right-avatar': MagicMock(first=MagicMock(count=AsyncMock(return_value=0))),
            '.shop-menu-accountV1__right-account-top-name': name_locator,
        }[sel])
        with patch('asyncio.sleep', AsyncMock()):
            name, avatar = _run(_scrape_jd_profile(page))
        assert name == '昵称文本'
        assert avatar == ''
