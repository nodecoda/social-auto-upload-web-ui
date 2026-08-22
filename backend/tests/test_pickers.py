"""picker 会话/池契约测试（T29）。

impl/jd/picker.py 与 impl/taobao_guanghe/picker.py:
- cookie 路径解析(_get_cookie_path_by_account_id / _resolve_cookie_path)
- 会话生命周期(open / search / go_page / novel_search / switch_type / switch_tab /
  apply_filter / load_more / close / _init_browser_and_frame / _teardown)
- 会话池(get_or_create / create / get / release / has / remove)

浏览器全部 mock 驱动(_browser 工厂已 T28 全覆盖),link_ops 委托打桩。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from impl.jd import picker as jd_picker
from impl.jd.picker import JdPickerSession
from impl.jd.picker import _SessionPool as JdPool
from impl.taobao_guanghe import picker as gh_picker
from impl.taobao_guanghe.picker import GuanghePickerSession
from impl.taobao_guanghe.picker import _SessionPool as GhPool


def _run(coro):
    return asyncio.run(coro)


def _patch_loop_time():
    """打桩当前 running loop 的 time()（get_running_loop 是 C 函数无法直接 patch）。

    背景：_find_publish_frame 用 asyncio.get_running_loop().time() 算 20s deadline；
    旧测试 patch 了 get_event_loop（死代码），while 在真实时间下紧循环空转
    （asyncio.sleep 已 mock 为即时返回），20s 内 mock 分配爆炸触发 OOM
    （本机 3.7GB 内存，曾拖垮整机）。本打桩：前 WINDOW 次调用返回真实时间
    （deadline 与首轮 while 检查都落在窗口内，保证至少扫一遍 frame），之后
    返回 t0+1000 使 while 立即超时退出。asyncio 内部对 time() 的调用不受影响
    （返回偏移值不影响事件循环的相对时序）。
    """
    from contextlib import asynccontextmanager

    WINDOW = 200
    calls = {"n": 0}

    @asynccontextmanager
    async def _ctx():
        loop = asyncio.get_running_loop()
        orig_time = loop.time
        t0 = orig_time()

        def _time():
            calls["n"] += 1
            if calls["n"] <= WINDOW:
                return t0
            return t0 + 1000

        loop.time = _time
        try:
            yield
        finally:
            loop.time = orig_time

    return _ctx()


def _fake_db_conn(row):
    conn = MagicMock()
    cur = conn.cursor.return_value
    cur.fetchone.return_value = row
    return conn


# ── cookie 路径解析（两个 picker 同构） ────────────────────────────────────

class TestCookiePaths:
    def test_jd_cookie_path_hit(self):
        conn = _fake_db_conn(('/cookies/jd.json',))
        with patch('impl.jd.picker.sqlite3.connect', return_value=conn):
            assert jd_picker._get_cookie_path_by_account_id('42') == '/cookies/jd.json'
        conn.close.assert_called_once()

    def test_jd_cookie_path_miss(self):
        conn = _fake_db_conn(None)
        with patch('impl.jd.picker.sqlite3.connect', return_value=conn):
            assert jd_picker._get_cookie_path_by_account_id('42') is None

    def test_jd_cookie_path_empty_id(self):
        assert jd_picker._get_cookie_path_by_account_id('') is None

    def test_jd_resolve_cookie_path(self):
        p = jd_picker._resolve_cookie_path('jd_cookie.json')
        assert p.name == 'jd_cookie.json'
        assert 'cookiesFile' in p.parts

    def test_gh_cookie_path_hit(self):
        conn = _fake_db_conn(('/cookies/gh.json',))
        with patch('impl.taobao_guanghe.picker.sqlite3.connect', return_value=conn):
            assert gh_picker._get_cookie_path_by_account_id('7') == '/cookies/gh.json'

    def test_gh_cookie_path_miss(self):
        conn = _fake_db_conn(None)
        with patch('impl.taobao_guanghe.picker.sqlite3.connect', return_value=conn):
            assert gh_picker._get_cookie_path_by_account_id('7') is None

    def test_gh_cookie_path_empty_id(self):
        assert gh_picker._get_cookie_path_by_account_id('') is None

    def test_gh_resolve_cookie_path(self):
        p = gh_picker._resolve_cookie_path('gh_cookie.json')
        assert p.endswith('cookiesFile/gh_cookie.json')


# ── JdPickerSession ────────────────────────────────────────────────────────

def _jd_browser_and_page():
    frame = MagicMock()
    frame.url = 'https://dr.jd.com/n/publish-video.html'
    page = MagicMock()
    page.url = 'https://dr.jd.com/jm/#/n/publish-video.html'
    page.goto = AsyncMock()
    page.evaluate = AsyncMock(return_value={'url': 'x', 'radio_count': 1, 'drawer_count': 0, 'file_inputs': 1, 'texts': '', 'classes': []})
    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=page)
    ctx.close = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    browser.new_context = AsyncMock(return_value=ctx)
    return browser, page, frame


class TestJdSession:
    def test_init_fields(self):
        s = JdPickerSession('acc-1')
        assert s.account_id == 'acc-1'
        assert s.browser is None and s.page is None and s.frame is None

    def test_wait_publish_frame_delegates(self):
        s = JdPickerSession('a')
        s.page = MagicMock()
        target = MagicMock()
        with patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(return_value=target)) as wp:
            assert _run(s._wait_publish_frame(timeout=9)) is target
        wp.assert_awaited_once_with(s.page, timeout=9)

    def test_init_browser_happy_with_cookie(self):
        browser, page, frame = _jd_browser_and_page()
        ctx = MagicMock()
        ctx.new_page = AsyncMock(return_value=page)
        cp = MagicMock()
        cp.exists.return_value = True
        s = JdPickerSession('a')
        with patch('impl.jd.picker.create_browser', AsyncMock(return_value=browser)) as cb, \
             patch('impl.jd.picker.create_context', AsyncMock(return_value=ctx)) as cc, \
             patch('impl.jd.picker._get_cookie_path_by_account_id', return_value='jd.json'), \
             patch('impl.jd.picker._resolve_cookie_path', return_value=cp), \
             patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(return_value=frame)):
            _run(s._init_browser_and_frame())
        cb.assert_awaited_once_with(headless=True)
        cc.assert_awaited_once_with(browser, storage_state=str(cp))
        page.goto.assert_awaited_once()
        assert page.goto.await_args.kwargs['wait_until'] == 'domcontentloaded'
        assert s.frame is frame

    def test_init_browser_without_cookie_uses_new_context(self):
        browser, _page, _frame = _jd_browser_and_page()
        s = JdPickerSession('a')
        with patch('impl.jd.picker.create_browser', AsyncMock(return_value=browser)), \
             patch('impl.jd.picker._get_cookie_path_by_account_id', return_value=None), \
             patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(return_value=_frame)):
            _run(s._init_browser_and_frame())
        browser.new_context.assert_awaited_once()
        s.browser = None  # 清理

    def test_init_browser_double_raises(self):
        s = JdPickerSession('a')
        s.browser = MagicMock()
        try:
            _run(s._init_browser_and_frame())
        except RuntimeError as e:
            assert '已存在' in str(e)
        else:
            raise AssertionError('expected RuntimeError')

    def test_init_browser_cookie_invalid_raises(self):
        browser, page, _frame = _jd_browser_and_page()
        page.url = 'https://passport.jd.com/login'
        s = JdPickerSession('a')
        ctx2 = MagicMock()
        ctx2.new_page = AsyncMock(return_value=page)
        with patch('impl.jd.picker.create_browser', AsyncMock(return_value=browser)), \
             patch('impl.jd.picker.create_context', AsyncMock(return_value=ctx2)), \
             patch('impl.jd.picker._get_cookie_path_by_account_id', return_value='x.json'), \
             patch('impl.jd.picker._resolve_cookie_path', return_value=MagicMock()):
            try:
                _run(s._init_browser_and_frame())
            except RuntimeError as e:
                assert 'cookie 失效' in str(e)
            else:
                raise AssertionError('expected RuntimeError')

    def test_init_browser_iframe_failure_dumps_and_raises(self):
        browser, page, _frame = _jd_browser_and_page()
        page.url = 'https://dr.jd.com/jm/#/n/publish-video.html'
        page.frames = [page.main_frame]
        f1 = MagicMock()
        f1.url = 'https://dr.jd.com/x'
        f1.evaluate = AsyncMock(return_value={'url': 'u', 'radio_count': 0, 'file_inputs': 0, 'addgoods_count': 0, 'text_head': ''})
        f2 = MagicMock()
        f2.url = 'https://dr.jd.com/cross-origin'
        f2.evaluate = AsyncMock(side_effect=RuntimeError('cross-origin'))
        page.frames = [f1, f2]
        ctx2 = MagicMock()
        ctx2.new_page = AsyncMock(return_value=page)
        s = JdPickerSession('a')
        with patch('impl.jd.picker.create_browser', AsyncMock(return_value=browser)), \
             patch('impl.jd.picker.create_context', AsyncMock(return_value=ctx2)), \
             patch('impl.jd.picker._get_cookie_path_by_account_id', return_value='x.json'), \
             patch('impl.jd.picker._resolve_cookie_path', return_value=MagicMock()), \
             patch('impl.jd._jd_link_ops.wait_publish_frame', AsyncMock(side_effect=RuntimeError('timeout'))):
            try:
                _run(s._init_browser_and_frame())
            except RuntimeError as e:
                assert '未找到发布表单 iframe' in str(e)
            else:
                raise AssertionError('expected RuntimeError')

    def test_open_happy_path(self):
        s = JdPickerSession('a')
        s._init_browser_and_frame = AsyncMock()
        s.frame = MagicMock()
        s.frame.wait_for_selector = AsyncMock()
        products = [{'id': '1', 'title': 'A'}]
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()) as sr, \
             patch('impl.jd._jd_link_ops.click_add_card', AsyncMock()) as cac, \
             patch('impl.jd._jd_link_ops.wait_panel_ready', AsyncMock()) as wpr, \
             patch('impl.jd._jd_link_ops.scrape_products', AsyncMock(return_value=products)) as sp, \
             patch('impl.jd._jd_link_ops.scrape_total', AsyncMock(return_value=12)) as st:
            result = _run(s.open())
        assert result == {'products': products, 'total': 12}
        s.frame.wait_for_selector.assert_awaited_once_with(
            '.addgoods-upload', timeout=20000, state='attached')
        sr.assert_awaited_once_with(s.frame, 'product')
        cac.assert_awaited_once_with(s.frame)
        wpr.assert_awaited_once_with(s.frame)
        sp.assert_awaited_once_with(s.frame)
        st.assert_awaited_once_with(s.frame)

    def test_novel_search_reuses_session(self):
        s = JdPickerSession('a')
        s._init_browser_and_frame = AsyncMock()
        s.frame = MagicMock()
        novels = [{'title': '修仙'}]
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()) as sr, \
             patch('impl.jd._jd_link_ops.search_novels', AsyncMock(return_value=novels)) as sn, \
             patch('asyncio.sleep', AsyncMock()):
            result = _run(s.novel_search('修仙'))
        assert result == {'novels': novels}
        s._init_browser_and_frame.assert_not_called()  # frame 已存在 → 复用
        sr.assert_awaited_once_with(s.frame, 'novel')
        sn.assert_awaited_once_with(s.frame, '修仙')

    def test_novel_search_first_time_inits(self):
        s = JdPickerSession('a')
        s.frame = None
        s._init_browser_and_frame = AsyncMock()
        s._init_browser_and_frame.side_effect = lambda: setattr(s, 'frame', MagicMock())
        with patch('impl.jd._jd_link_ops.switch_radio', AsyncMock()), \
             patch('impl.jd._jd_link_ops.search_novels', AsyncMock(return_value=[])), \
             patch('asyncio.sleep', AsyncMock()):
            _run(s.novel_search('x'))
        s._init_browser_and_frame.assert_awaited_once()

    def test_dismiss_help_dialog_found(self):
        s = JdPickerSession('a')
        s.page = MagicMock()
        s.page.evaluate = AsyncMock(return_value='我知道了')
        s.page.keyboard = MagicMock()
        with patch('asyncio.sleep', AsyncMock()):
            _run(s._dismiss_help_dialog())
        s.page.keyboard.press.assert_not_called()

    def test_dismiss_help_dialog_esc_fallback(self):
        s = JdPickerSession('a')
        s.page = MagicMock()
        s.page.evaluate = AsyncMock(return_value=None)
        s.page.keyboard.press = AsyncMock()
        with patch('asyncio.sleep', AsyncMock()):
            _run(s._dismiss_help_dialog())
        s.page.keyboard.press.assert_awaited_once_with('Escape')

    def test_dismiss_help_dialog_exception_ignored(self):
        s = JdPickerSession('a')
        s.page = MagicMock()
        s.page.evaluate = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('impl.jd.picker.logger') as lg:
            _run(s._dismiss_help_dialog())  # 不抛
        lg.info.assert_called()

    def test_search_requires_open(self):
        s = JdPickerSession('a')
        try:
            _run(s.search('kw'))
        except RuntimeError as e:
            assert '先调用 open' in str(e)
        else:
            raise AssertionError('expected RuntimeError')

    def test_search_happy(self):
        s = JdPickerSession('a')
        s.frame = MagicMock()
        products, total = [{'id': '1'}], 3
        with patch('impl.jd._jd_link_ops.search', AsyncMock()) as se, \
             patch('impl.jd._jd_link_ops.scrape_products', AsyncMock(return_value=products)), \
             patch('impl.jd._jd_link_ops.scrape_total', AsyncMock(return_value=total)):
            assert _run(s.search('kw')) == {'products': products, 'total': total}
        se.assert_awaited_once_with(s.frame, 'kw')

    def test_go_page_requires_open(self):
        s = JdPickerSession('a')
        try:
            _run(s.go_page(2))
        except RuntimeError as e:
            assert '未打开' in str(e)
        else:
            raise AssertionError('expected RuntimeError')

    def test_go_page_happy(self):
        s = JdPickerSession('a')
        s.frame = MagicMock()
        products, total = [{'id': '2'}], 5
        with patch('impl.jd._jd_link_ops.go_page', AsyncMock()) as gp, \
             patch('impl.jd._jd_link_ops.scrape_products', AsyncMock(return_value=products)), \
             patch('impl.jd._jd_link_ops.scrape_total', AsyncMock(return_value=total)):
            assert _run(s.go_page(2)) == {'products': products, 'total': total}
        gp.assert_awaited_once_with(s.frame, 2)

    def test_close_clears_refs(self):
        s = JdPickerSession('a')
        b = MagicMock()
        s.browser, s.page, s.frame = b, MagicMock(), MagicMock()
        with patch('impl.jd.picker.close_browser', AsyncMock()) as cb:
            _run(s.close())
        cb.assert_awaited_once_with(b, is_close_by_code=True)
        assert s.browser is None and s.page is None and s.frame is None

    def test_close_no_browser(self):
        s = JdPickerSession('a')
        with patch('impl.jd.picker.close_browser', AsyncMock()) as cb:
            _run(s.close())
        cb.assert_not_called()

    def test_close_close_browser_error_swallowed(self):
        s = JdPickerSession('a')
        s.browser = MagicMock()
        with patch('impl.jd.picker.close_browser', AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('impl.jd.picker.logger') as lg:
            _run(s.close())  # 不抛
        lg.warning.assert_called()
        assert s.browser is None


# ── JdPickerSession 池 ─────────────────────────────────────────────────────

class TestJdPool:
    def test_get_or_create_singleton(self):
        p = JdPool()
        s1 = p.get_or_create('a')
        s2 = p.get_or_create('a')
        assert s1 is s2
        assert p.has('a')
        assert p.get('a') is s1

    def test_get_or_create_distinct_accounts(self):
        p = JdPool()
        assert p.get_or_create('a') is not p.get_or_create('b')

    def test_create_async_closes_old(self):
        p = JdPool()
        old = p.create('a')
        # 生产代码改用 get_running_loop() 探测运行中循环(弃用 get_event_loop)
        with patch('asyncio.ensure_future') as ef, patch('asyncio.get_running_loop') as grl:
            grl.return_value = MagicMock()
            new = p.create('a')
        assert p.get('a') is new and new is not old
        ef.assert_called_once()
        coro = ef.call_args.args[0]
        asyncio.run(coro)  # 消耗协程,避免 RuntimeWarning

    def test_create_no_running_loop(self):
        p = JdPool()
        old = p.create('a')
        with patch('asyncio.ensure_future') as ef, patch('asyncio.get_running_loop', side_effect=RuntimeError('no loop')):
            new = p.create('a')
        assert p.get('a') is new and new is not old
        ef.assert_not_called()

    def test_release_pops(self):
        p = JdPool()
        s = p.get_or_create('a')
        assert p.release('a') is s
        assert not p.has('a')
        assert p.release('a') is None

    def test_get_missing_returns_none(self):
        assert JdPool().get('nope') is None


# ── GuanghePickerSession ───────────────────────────────────────────────────

def _gh_browser_and_page():
    frame = MagicMock()
    page = MagicMock()
    page.goto = AsyncMock()
    page.url = 'https://creator.guanghe.taobao.com/page/pubNew/video'
    page.frames = [page.main_frame, frame]
    frame.locator.return_value.count = AsyncMock(return_value=1)
    frame.page = page
    ctx = MagicMock()
    ctx.new_page = AsyncMock(return_value=page)
    ctx.close = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    return browser, ctx, page, frame


class TestGuangheSession:
    def test_init_fields(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        assert s.session_id == 'sid'
        assert s.cookie_path == '/cookies/x.json'
        assert s.current_type is None

    def test_open_happy(self):
        browser, ctx, page, frame = _gh_browser_and_page()
        s = GuanghePickerSession('sid', '/cookies/x.json')
        items = [{'id': '1'}]
        with patch('impl.taobao_guanghe.picker.create_browser', AsyncMock(return_value=browser)) as cb, \
             patch('impl.taobao_guanghe.picker.create_context', AsyncMock(return_value=ctx)) as cc, \
             patch.object(s, '_find_publish_frame', AsyncMock(return_value=frame)), \
             patch.object(s, '_open_picker_panel', AsyncMock()), \
             patch.object(s, '_scrape', AsyncMock(return_value=(items, True))), \
             patch.object(s, '_scrape_filters', AsyncMock(return_value={'rules': ['智能推荐']})) as sf, \
             patch('asyncio.sleep', AsyncMock()):
            result = _run(s.open('product'))
        assert result == {'items': items, 'has_more': True,
                          'filters': {'rules': ['智能推荐']}, 'type': 'product'}
        cb.assert_awaited_once_with(headless=True)
        cc.assert_awaited_once_with(browser, storage_state='/cookies/x.json')
        page.goto.assert_awaited_once()
        assert s.current_type == 'product'
        sf.assert_awaited_once()

    def test_open_invalid_type(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        try:
            _run(s.open('bogus'))
        except ValueError as e:
            assert 'unknown type' in str(e)
        else:
            raise AssertionError('expected ValueError')

    def test_open_failure_tears_down(self):
        browser, ctx, _page, _frame = _gh_browser_and_page()
        s = GuanghePickerSession('sid', '/cookies/x.json')
        with patch('impl.taobao_guanghe.picker.create_browser', AsyncMock(return_value=browser)), \
             patch('impl.taobao_guanghe.picker.create_context', AsyncMock(return_value=ctx)), \
             patch.object(s, '_find_publish_frame', AsyncMock(side_effect=RuntimeError('no iframe'))):
            try:
                _run(s.open('product'))
            except RuntimeError:
                pass
            else:
                raise AssertionError('expected RuntimeError')
        browser.close.assert_awaited_once()
        assert s.browser is None

    def test_open_cookie_invalid_raises(self):
        browser, ctx, page, _frame = _gh_browser_and_page()
        page.url = 'https://login.taobao.com/'
        s = GuanghePickerSession('sid', '/cookies/x.json')
        with patch('impl.taobao_guanghe.picker.create_browser', AsyncMock(return_value=browser)), \
             patch('impl.taobao_guanghe.picker.create_context', AsyncMock(return_value=ctx)), \
             patch('asyncio.sleep', AsyncMock()):
            try:
                _run(s.open('product'))
            except RuntimeError as e:
                assert 'cookie 失效' in str(e)
            else:
                raise AssertionError('expected RuntimeError')

    def test_switch_type_same_returns_snapshot(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        s.current_type = 'product'
        items = [{'id': '1'}]
        with patch.object(s, '_scrape', AsyncMock(return_value=(items, False))) as sc:
            result = _run(s.switch_type('product'))
        assert result == {'items': items, 'has_more': False, 'type': 'product'}
        sc.assert_awaited_once()
        s.frame.page.keyboard.press.assert_not_called()

    def test_switch_type_esc_failure_continues(self):
        """Esc 关闭弹窗失败 → 兜底继续走 _open_picker_panel。"""
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        s.frame.page.keyboard.press = AsyncMock(side_effect=RuntimeError('no keyboard'))
        s.current_type = 'product'
        items = [{'id': 's1'}]
        with patch.object(s, '_open_picker_panel', AsyncMock()) as op, \
             patch.object(s, '_scrape', AsyncMock(return_value=(items, True))), \
             patch('asyncio.sleep', AsyncMock()):
            result = _run(s.switch_type('shop'))
        assert result == {'items': items, 'has_more': True, 'type': 'shop'}
        op.assert_awaited_once_with('shop')

    def test_switch_type_different(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        s.frame.page.keyboard.press = AsyncMock()
        s.current_type = 'product'
        items = [{'id': 's1'}]
        with patch.object(s, '_open_picker_panel', AsyncMock()) as op, \
             patch.object(s, '_scrape', AsyncMock(return_value=(items, True))), \
             patch('asyncio.sleep', AsyncMock()):
            result = _run(s.switch_type('shop'))
        assert result == {'items': items, 'has_more': True, 'type': 'shop'}
        s.frame.page.keyboard.press.assert_awaited_once_with('Escape')
        op.assert_awaited_once_with('shop')
        assert s.current_type == 'shop'

    def test_switch_type_invalid(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        try:
            _run(s.switch_type('bogus'))
        except ValueError:
            pass
        else:
            raise AssertionError('expected ValueError')

    def test_switch_tab_non_product_raises(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.current_type = 'shop'
        try:
            _run(s.switch_tab('bought'))
        except RuntimeError as e:
            assert '仅商品模式' in str(e)
        else:
            raise AssertionError('expected RuntimeError')

    def test_switch_tab_invalid_tab(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.current_type = 'product'
        try:
            _run(s.switch_tab('bogus'))
        except ValueError as e:
            assert 'unknown tab' in str(e)
        else:
            raise AssertionError('expected ValueError')

    def test_switch_tab_ok(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        s.current_type = 'product'
        items = [{'id': '1'}]
        with patch('impl.taobao_guanghe._link_ops.switch_tab', AsyncMock()) as st, \
             patch.object(s, '_scrape', AsyncMock(return_value=(items, False))):
            result = _run(s.switch_tab('preferred'))
        assert result == {'items': items, 'has_more': False}
        st.assert_awaited_once_with(s.frame, 'preferred')

    def test_apply_filter_non_product_raises(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.current_type = 'shop'
        try:
            _run(s.apply_filter(rule='智能推荐'))
        except RuntimeError as e:
            assert '仅商品模式' in str(e)
        else:
            raise AssertionError('expected RuntimeError')

    def test_apply_filter_ok(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        s.current_type = 'product'
        items = [{'id': '1'}]
        filters = {'rules': ['A'], 'categories': ['B']}
        with patch('impl.taobao_guanghe._link_ops.click_filter', AsyncMock()) as cf, \
             patch.object(s, '_scrape', AsyncMock(return_value=(items, True))), \
             patch.object(s, '_scrape_filters', AsyncMock(return_value=filters)), \
             patch('asyncio.sleep', AsyncMock()):
            result = _run(s.apply_filter(rule='智能推荐', category='服饰'))
        assert result == {'items': items, 'has_more': True, 'filters': filters}
        assert cf.await_count == 2
        assert cf.await_args_list[0].args == (s.frame, '推荐规则', '智能推荐')
        assert cf.await_args_list[1].args == (s.frame, '品类筛选', '服饰')

    def test_search_strips_and_filters(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        s.current_type = 'product'
        items = [{'id': '1'}]
        with patch('impl.taobao_guanghe._link_ops.search', AsyncMock()) as se, \
             patch.object(s, '_scrape', AsyncMock(return_value=(items, False))), \
             patch.object(s, '_scrape_filters', AsyncMock(return_value={})) as sf:
            result = _run(s.search('  连衣裙  '))
        assert result == {'items': items, 'has_more': False, 'filters': {}}
        se.assert_awaited_once_with(s.frame, '连衣裙')
        sf.assert_awaited_once()

    def test_search_shop_skips_filters(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        s.current_type = 'shop'
        with patch('impl.taobao_guanghe._link_ops.search', AsyncMock()), \
             patch.object(s, '_scrape', AsyncMock(return_value=([], False))), \
             patch.object(s, '_scrape_filters', AsyncMock()) as sf:
            _run(s.search(None))
        sf.assert_not_called()

    def test_load_more(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        s.current_type = 'product'
        items = [{'id': '1'}]
        with patch('impl.taobao_guanghe._link_ops.load_more', AsyncMock(return_value=True)) as lm, \
             patch.object(s, '_scrape', AsyncMock(return_value=(items, True))):
            result = _run(s.load_more())
        assert result == {'items': items, 'has_more': True}
        lm.assert_awaited_once_with(s.frame)

    def test_close_teardown(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.browser = MagicMock()
        s.context = MagicMock()
        s.page = MagicMock()
        s.frame = MagicMock()
        s.current_type = 'product'
        with patch.object(s, '_teardown', AsyncMock()) as td:
            _run(s.close())
        td.assert_awaited_once()

    def test_find_publish_frame_found(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        page = MagicMock()
        frame = MagicMock()
        frame.locator.return_value.count = AsyncMock(return_value=1)
        page.main_frame = MagicMock()
        page.frames = [page.main_frame, frame]
        s.page = page
        async def _scenario():
            with patch('asyncio.sleep', AsyncMock()):  # 紧循环不真实等待
                async with _patch_loop_time():  # deadline + 首轮检查即命中
                    return await s._find_publish_frame()
        assert _run(_scenario()) is frame

    def test_find_publish_frame_timeout_returns_main(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        page = MagicMock()
        page.main_frame = MagicMock()
        page.frames = [page.main_frame]
        page.main_frame.locator.return_value.count = AsyncMock(return_value=0)
        s.page = page
        async def _scenario():
            with patch('asyncio.sleep', AsyncMock()):  # 紧循环不真实等待
                async with _patch_loop_time():  # 首轮进入扫描，超时后退出
                    return await s._find_publish_frame()
        assert _run(_scenario()) is page.main_frame

    def test_find_publish_frame_locator_exception_falls_back(self):
        """非 main frame 的 locator.count 异常 → 跳过并继续,超时兜底返回 main_frame。"""
        s = GuanghePickerSession('sid', '/cookies/x.json')
        page = MagicMock()
        page.main_frame = MagicMock()
        page.main_frame.locator.return_value.count = AsyncMock(return_value=0)
        bad = MagicMock()
        bad.locator.return_value.count = AsyncMock(side_effect=RuntimeError('boom'))
        page.frames = [page.main_frame, bad]
        s.page = page
        async def _scenario():
            with patch('asyncio.sleep', AsyncMock()):  # 紧循环不真实等待
                async with _patch_loop_time():  # 首轮进入扫描，超时后退出
                    return await s._find_publish_frame()
        assert _run(_scenario()) is page.main_frame

    def test_scrape_delegates(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        s.current_type = 'product'
        with patch('impl.taobao_guanghe._link_ops.scrape', AsyncMock(return_value=([1], True))) as sc:
            assert _run(s._scrape()) == ([1], True)
        sc.assert_awaited_once_with(s.frame, 'product')

    def test_scrape_filters_delegates(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        with patch('impl.taobao_guanghe._link_ops.scrape_filters', AsyncMock(return_value={'rules': []})) as sf:
            assert _run(s._scrape_filters()) == {'rules': []}
        sf.assert_awaited_once_with(s.frame)

    def test_open_picker_panel_product(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        with patch('impl.taobao_guanghe._link_ops.switch_radio', AsyncMock()) as sr, \
             patch('impl.taobao_guanghe._link_ops.click_add_card', AsyncMock()) as cac, \
             patch('impl.taobao_guanghe._link_ops.wait_panel_ready', AsyncMock()) as wpr, \
             patch.object(s, 'switch_tab', AsyncMock()) as st:
            _run(s._open_picker_panel('product'))
        sr.assert_awaited_once_with(s.frame, 'product')
        cac.assert_awaited_once_with(s.frame, 'product')
        wpr.assert_awaited_once_with(s.frame, 'product')
        st.assert_awaited_once_with('preferred')

    def test_open_picker_panel_shop_no_tab(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        with patch('impl.taobao_guanghe._link_ops.switch_radio', AsyncMock()), \
             patch('impl.taobao_guanghe._link_ops.click_add_card', AsyncMock()), \
             patch('impl.taobao_guanghe._link_ops.wait_panel_ready', AsyncMock()), \
             patch.object(s, 'switch_tab', AsyncMock()) as st:
            _run(s._open_picker_panel('shop'))
        st.assert_not_called()

    def test_open_picker_panel_errors_logged(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.frame = MagicMock()
        with patch('impl.taobao_guanghe._link_ops.switch_radio', AsyncMock(side_effect=RuntimeError('radio'))), \
             patch('impl.taobao_guanghe._link_ops.click_add_card', AsyncMock(side_effect=RuntimeError('card'))), \
             patch('impl.taobao_guanghe._link_ops.wait_panel_ready', AsyncMock(side_effect=RuntimeError('panel'))), \
             patch('impl.taobao_guanghe.picker.logger') as lg:
            _run(s._open_picker_panel('product'))
        assert lg.info.call_count >= 3  # 三个失败都记日志,不抛

    def test_teardown_closes_and_clears(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        b, c = MagicMock(), MagicMock()
        b.close = AsyncMock()
        c.close = AsyncMock()
        s.browser, s.context = b, c
        s.page = MagicMock()
        s.frame = MagicMock()
        s.current_type = 'product'
        _run(s._teardown())
        b.close.assert_awaited_once()
        c.close.assert_awaited_once()
        assert s.browser is None and s.context is None
        assert s.page is None and s.frame is None and s.current_type is None

    def test_teardown_swallows_errors(self):
        s = GuanghePickerSession('sid', '/cookies/x.json')
        s.browser = MagicMock()
        s.browser.close = AsyncMock(side_effect=RuntimeError('boom'))
        s.context = MagicMock()
        _run(s._teardown())  # 不抛
        assert s.browser is None


# ── GuanghePickerSession 池 ────────────────────────────────────────────────

class TestGuanghePool:
    def test_get_create_remove(self):
        p = GhPool()
        s = p.create('sid', '/cookies/x.json')
        assert p.get('sid') is s
        assert p.remove('sid') is s
        assert p.get('sid') is None
        assert p.remove('sid') is None

    def test_create_closes_old_outside_lock(self):
        p = GhPool()
        old = p.create('sid', '/cookies/a.json')
        with patch('asyncio.ensure_future') as ef:
            new = p.create('sid', '/cookies/b.json')
        assert p.get('sid') is new and new is not old
        assert new.cookie_path == '/cookies/b.json'
        ef.assert_called_once()
        asyncio.run(ef.call_args.args[0])  # 消耗协程,避免 RuntimeWarning
