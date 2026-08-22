"""测试 jingmai 平台 DOM/生命周期契约（impl/jingmai/platform.py 19%→~100%）。

覆盖：login / check_cookie / sync_profile / _login_stats_fn / _scrape_stats /
_build_stats / publish_video 委托 / open_creator_center 线程。
fake browser/context/page 驱动，patch asyncio.sleep 加速轮询。
"""
import asyncio
import sys
import threading
import unittest
from pathlib import Path
from queue import Queue
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from impl.jingmai import platform as jm

# ---------- fake Playwright 对象 ----------

class _FakeFrame:
    def __init__(self, url=''):
        self.url = url
        self.closed = False

    async def wait_for_selector(self, selector, timeout=None):
        return self

    async def evaluate(self, js):
        return []


class _FakePage:
    def __init__(self, url='https://dr.jd.com/jm/'):
        self._url = url
        self.main_frame = _FakeFrame()
        self.frames = [self.main_frame]
        self.closed = False

    @property
    def url(self):
        return self._url() if callable(self._url) else self._url

    async def goto(self, *args, **kwargs):
        pass

    async def wait_for_load_state(self, *args, **kwargs):
        pass

    async def wait_for_selector(self, selector, timeout=None):
        return self

    async def evaluate(self, js):
        return []

    async def close(self):
        self.closed = True


class _FakeContext:
    def __init__(self, page=None):
        self._page = page or _FakePage()
        self.closed = False

    async def new_page(self):
        return self._page

    async def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self, page=None):
        self.closed = False

    async def close(self):
        self.closed = True


class _Url:
    """可变 URL 替身。"""

    def __init__(self, initial):
        self.value = initial

    def __call__(self):
        return self.value


# ---------- 工具 ----------

def _make_platform():
    return jm.JingmaiPlatform()


def _install_fake_browser(page):
    """让 platform.create_browser/create_context 返回 fake。"""
    platform = _make_platform()
    browser = _FakeBrowser(page=page)
    ctx = _FakeContext(page=page)
    platform.create_browser = mock.AsyncMock(return_value=browser)
    platform.create_context = mock.AsyncMock(return_value=ctx)
    return platform, browser, ctx


def _patch_sleep():
    return mock.patch('impl.jingmai.platform.asyncio.sleep', new=mock.AsyncMock())


# ---------- 纯函数 ----------

class TestJingmaiBuildStats(unittest.TestCase):
    def test_build_stats_hit_and_miss(self):
        label_map = {"粉丝": ("user", 1, "粉丝"), "获赞": ("like", 2, "获赞")}
        raw = [
            {"name": "粉丝", "num": "1,234"},
            {"name": "获赞", "num": "5.5k"},
            {"name": "未知", "num": "9"},
            {"name": "粉丝", "num": ""},
        ]
        stats = jm.JingmaiPlatform._build_stats(raw, label_map)
        # 1,234 → 1234；5.5k 非法 → 0（float('5.5k') 失败）；空 → 0
        self.assertEqual(stats, [
            {"ICON": "user", "COUNT": 1234, "NAME": "粉丝", "SORT": 1},
            {"ICON": "like", "COUNT": 0, "NAME": "获赞", "SORT": 2},
            {"ICON": "user", "COUNT": 0, "NAME": "粉丝", "SORT": 1},
        ])

    def test_build_stats_decimal_and_cleaning(self):
        label_map = {"粉丝": ("user", 1, "粉丝")}
        raw = [{"name": "粉丝", "num": "1.5"}]
        stats = jm.JingmaiPlatform._build_stats(raw, label_map)
        self.assertEqual(stats[0]["COUNT"], 1)
        raw2 = [{"name": "粉丝", "num": " 1 000 "}]
        stats2 = jm.JingmaiPlatform._build_stats(raw2, label_map)
        self.assertEqual(stats2[0]["COUNT"], 1000)

    def test_build_stats_missing_fields(self):
        stats = jm.JingmaiPlatform._build_stats([{}], {"粉丝": ("u", 1, "粉丝")})
        self.assertEqual(stats, [])


class TestJingmaiScrapeStats(unittest.TestCase):
    def test_scrape_stats_main_frame_scope(self):
        page = _FakePage()

        async def _evaluate(js):
            return [{"name": "粉丝", "num": "100"}, {"name": "获赞", "num": "50"}]

        async def _wait_for_selector(selector, timeout=None):
            return self

        page.evaluate = _evaluate
        page.main_frame.wait_for_selector = _wait_for_selector
        with _patch_sleep():
            result = asyncio.run(jm.JingmaiPlatform._scrape_stats(page))
        self.assertEqual(result, [{"name": "粉丝", "num": "100"}, {"name": "获赞", "num": "50"}])

    def test_scrape_stats_child_frame_fallback(self):
        page = _FakePage()
        child = _FakeFrame()
        page.frames = [page.main_frame, child]

        async def _page_wait(selector, timeout=None):
            raise Exception('main page miss')  # noqa: TRY002 -- 测试桩模拟页面失败,非生产异常

        async def _child_wait(selector, timeout=None):
            return child

        page.wait_for_selector = _page_wait
        child.wait_for_selector = _child_wait

        async def _evaluate_child(js):
            return [{"name": "粉丝", "num": "7"}]

        child.evaluate = _evaluate_child
        with _patch_sleep():
            result = asyncio.run(jm.JingmaiPlatform._scrape_stats(page))
        self.assertEqual(result, [{"name": "粉丝", "num": "7"}])

    def test_scrape_stats_no_scope_returns_empty(self):
        page = _FakePage()
        page.frames = [page.main_frame, _FakeFrame()]

        async def _page_wait(selector, timeout=None):
            raise Exception('always miss')  # noqa: TRY002 -- 测试桩模拟页面失败,非生产异常

        async def _child_wait(selector, timeout=None):
            raise Exception('child miss')  # noqa: TRY002 -- 测试桩模拟页面失败,非生产异常

        page.wait_for_selector = _page_wait
        page.frames[1].wait_for_selector = _child_wait
        with _patch_sleep():
            result = asyncio.run(jm.JingmaiPlatform._scrape_stats(page))
        self.assertEqual(result, [])

    def test_scrape_stats_evaluate_error_returns_empty(self):
        page = _FakePage()

        async def _wait(selector, timeout=None):
            return self

        async def _evaluate(js):
            raise RuntimeError('evaluate boom')

        page.main_frame.wait_for_selector = _wait
        page.evaluate = _evaluate
        with _patch_sleep():
            result = asyncio.run(jm.JingmaiPlatform._scrape_stats(page))
        self.assertEqual(result, [])


# ---------- 生命周期 ----------

class TestJingmaiLogin(unittest.TestCase):
    def test_login_success_flow(self):
        page = _FakePage(url='https://passport.jd.com/login')
        platform, _browser, _ctx = _install_fake_browser(page)

        # 首轮登录页，随后回到创作中心（命中 + 二次确认各读一次）
        urls = iter(['https://passport.jd.com/login',
                     'https://dr.jd.com/jm/', 'https://dr.jd.com/jm/'])
        page._url = lambda: next(urls)

        with _patch_sleep(), mock.patch('impl.jingmai.platform.save_login_result',
                        new=mock.AsyncMock()) as m_save:
            asyncio.run(platform.login('1', Queue(), account_id=5))
        m_save.assert_awaited_once()
        self.assertTrue(_browser.closed)

    def test_login_nav_and_card_timeout_ignored(self):
        page = _FakePage(url='https://dr.jd.com/jm/')
        platform, _browser, _ctx = _install_fake_browser(page)

        gotos = iter([None, Exception('nav timeout')])

        async def _goto(*a, **k):
            nxt = next(gotos)
            if isinstance(nxt, Exception):
                raise nxt
            return None

        async def _wait_sel(*a, **k):
            raise TimeoutError('card timeout')

        page.goto = _goto
        page.wait_for_selector = _wait_sel

        with _patch_sleep(), mock.patch('impl.jingmai.platform.save_login_result',
                        new=mock.AsyncMock()) as m_save:
            asyncio.run(platform.login('1', Queue()))
        m_save.assert_awaited_once()

    def test_login_page_close_errors_ignored(self):
        page = _FakePage(url='https://dr.jd.com/jm/')
        platform, _browser, _ctx = _install_fake_browser(page)

        async def _close_page():
            raise RuntimeError('page close boom')

        async def _close_ctx():
            raise RuntimeError('ctx close boom')

        page.close = _close_page
        _ctx.close = _close_ctx
        with _patch_sleep(), mock.patch('impl.jingmai.platform.save_login_result',
                        new=mock.AsyncMock()):
            asyncio.run(platform.login('1', Queue()))
        # 不抛异常即通过


class TestJingmaiCheckCookie(unittest.TestCase):
    def test_cookie_valid(self):
        page = _FakePage(url='https://dr.jd.com/jm/')
        platform, _browser, _ctx = _install_fake_browser(page)
        with _patch_sleep():
            result = asyncio.run(platform.check_cookie('any.json'))
        self.assertTrue(result)
        self.assertTrue(_browser.closed)

    def test_cookie_invalid_marker(self):
        page = _FakePage(url='https://passport.shop.jd.com/login')
        platform, _browser, _ = _install_fake_browser(page)
        with _patch_sleep():
            result = asyncio.run(platform.check_cookie('any.json'))
        self.assertFalse(result)

    def test_cookie_other_url_invalid(self):
        page = _FakePage(url='https://example.com/other')
        platform, _browser, _ = _install_fake_browser(page)
        with _patch_sleep():
            result = asyncio.run(platform.check_cookie('any.json'))
        self.assertFalse(result)

    def test_cookie_load_state_timeout_ignored(self):
        """wait_for_load_state 超时被吞掉，仍按 URL 判定。"""
        page = _FakePage(url='https://dr.jd.com/jm/')

        async def _load_state(*a, **k):
            raise TimeoutError('load timeout')

        page.wait_for_load_state = _load_state
        platform, _browser, _ctx = _install_fake_browser(page)
        with _patch_sleep():
            result = asyncio.run(platform.check_cookie('any.json'))
        self.assertTrue(result)

    def test_cookie_page_context_close_errors_ignored(self):
        """page.close/context.close 抛异常被吞掉，不影响判定。"""
        page = _FakePage(url='https://dr.jd.com/jm/')
        platform, _browser, ctx = _install_fake_browser(page)

        async def _close_page():
            raise RuntimeError('page close boom')

        async def _close_ctx():
            raise RuntimeError('ctx close boom')

        page.close = _close_page
        ctx.close = _close_ctx
        with _patch_sleep():
            result = asyncio.run(platform.check_cookie('any.json'))
        self.assertTrue(result)


class TestJingmaiSyncProfile(unittest.TestCase):
    def test_sync_profile_ok(self):
        page = _FakePage()
        platform, _browser, _ = _install_fake_browser(page)

        async def _scrape(page):
            return ('昵称', 'http://avatar')

        async def _stats(page):
            return [{"name": "粉丝", "num": "100"}]

        with mock.patch('impl.jingmai.platform.scrape_jingmai_profile', _scrape), \
                mock.patch.object(platform, '_scrape_stats', _stats), _patch_sleep():
            result = asyncio.run(platform.sync_profile('c.json'))
        self.assertEqual(result['name'], '昵称')
        self.assertEqual(result['avatar'], 'http://avatar')
        self.assertEqual(result['stats'][0]['COUNT'], 100)

    def test_sync_profile_empty_logged(self):
        page = _FakePage()
        platform, _browser, _ = _install_fake_browser(page)

        async def _scrape(page):
            return ('', '')

        async def _stats(page):
            return []

        with mock.patch('impl.jingmai.platform.scrape_jingmai_profile', _scrape), \
                mock.patch.object(platform, '_scrape_stats', _stats), _patch_sleep():
            result = asyncio.run(platform.sync_profile('c.json'))
        self.assertEqual(result, {'name': '', 'avatar': '', 'stats': []})

    def test_sync_profile_error_fallback(self):
        page = _FakePage()
        platform, _browser, _ = _install_fake_browser(page)

        async def _goto(*a, **k):
            raise RuntimeError('goto boom')

        page.goto = _goto
        with _patch_sleep():
            result = asyncio.run(platform.sync_profile('c.json'))
        self.assertEqual(result, {'name': '', 'avatar': '', 'stats': []})

    def test_login_stats_fn(self):
        page = _FakePage()
        platform = _make_platform()

        async def _stats(page):
            return [{"name": "获赞", "num": "2,000"}]

        with mock.patch.object(platform, '_scrape_stats', _stats):
            result = asyncio.run(platform._login_stats_fn(page, account_id=1))
        self.assertEqual(result[0], {"ICON": "like", "COUNT": 2000, "NAME": "获赞", "SORT": 2})


# ---------- publish_video 委托 ----------

class TestJingmaiPublishVideo(unittest.TestCase):
    def test_publish_video_delegates_to_jd(self):
        platform = _make_platform()
        with mock.patch('impl.jd.platform.JdPlatform') as m_jd:
            m_jd.return_value.publish_video.return_value = True
            result = asyncio.run(platform.publish_video(title='T'))
        self.assertTrue(result)
        m_jd.return_value.publish_video.assert_called_once_with(title='T')


# ---------- open_creator_center ----------

class TestJingmaiOpenCreatorCenter(unittest.TestCase):
    def test_open_creator_center_starts_thread(self):
        platform = _make_platform()
        launched = threading.Event()

        class _FakeSyncBrowser:
            def close(self):
                pass

        class _FakeSyncContext:
            def new_page(self):
                return _FakeSyncPage()

            def close(self):
                pass

        class _FakeSyncPage:
            def goto(self, url):
                pass

            def wait_for_event(self, event, timeout=None):
                raise RuntimeError('wait interrupted')

        def _create_sync(*a, **k):
            launched.set()
            return _FakeSyncBrowser()

        def _create_ctx(*a, **k):
            return _FakeSyncContext()

        with mock.patch('impl.jingmai.platform.create_browser_sync', _create_sync), \
                mock.patch('impl.jingmai.platform.create_context_sync', _create_ctx):
            asyncio.run(platform.open_creator_center('c.json'))
        # 线程启动（daemon），主线程不阻塞
        self.assertTrue(launched.wait(3))
        # 给线程内逻辑一点时间执行完（wait_for_event 抛异常被吞）
        threading.Event().wait(0.2)


class TestJingmaiSyncProfileDefensive(unittest.TestCase):
    def test_sync_profile_load_state_timeout_ignored(self):
        """wait_for_load_state 超时被吞掉，资料仍正常返回。"""
        page = _FakePage()
        platform, _browser, _ = _install_fake_browser(page)

        async def _load_state(*a, **k):
            raise TimeoutError('load timeout')

        async def _scrape(page):
            return ('昵称', 'http://avatar')

        async def _stats(page):
            return [{"name": "粉丝", "num": "100"}]

        page.wait_for_load_state = _load_state
        with mock.patch('impl.jingmai.platform.scrape_jingmai_profile', _scrape), \
                mock.patch.object(platform, '_scrape_stats', _stats), _patch_sleep():
            result = asyncio.run(platform.sync_profile('c.json'))
        self.assertEqual(result['name'], '昵称')

    def test_sync_profile_close_errors_ignored(self):
        """page.close/context.close 抛异常被吞掉。"""
        page = _FakePage()
        platform, _browser, ctx = _install_fake_browser(page)

        async def _scrape(page):
            return ('昵称', 'http://avatar')

        async def _stats(page):
            return [{"name": "粉丝", "num": "100"}]

        async def _close_page():
            raise RuntimeError('page close boom')

        async def _close_ctx():
            raise RuntimeError('ctx close boom')

        page.close = _close_page
        ctx.close = _close_ctx
        with mock.patch('impl.jingmai.platform.scrape_jingmai_profile', _scrape), \
                mock.patch.object(platform, '_scrape_stats', _stats), _patch_sleep():
            result = asyncio.run(platform.sync_profile('c.json'))
        self.assertEqual(result['name'], '昵称')


class TestJingmaiOpenCreatorCenterDefensive(unittest.TestCase):
    def test_creator_center_browser_close_error_ignored(self):
        """线程内 browser.close 抛异常被吞掉。"""
        platform = _make_platform()
        launched = threading.Event()

        class _FakeSyncBrowser:
            def close(self):
                raise RuntimeError('close boom')

        class _FakeSyncContext:
            def new_page(self):
                class _Pg:
                    def goto(self, url):
                        pass

                    def wait_for_event(self, event, timeout=None):
                        raise RuntimeError('wait interrupted')

                return _Pg()

            def close(self):
                pass

        def _create_sync(*a, **k):
            launched.set()
            return _FakeSyncBrowser()

        with mock.patch('impl.jingmai.platform.create_browser_sync', _create_sync), \
                mock.patch('impl.jingmai.platform.create_context_sync',
                           lambda *a, **k: _FakeSyncContext()):
            asyncio.run(platform.open_creator_center('c.json'))
        self.assertTrue(launched.wait(3))
        threading.Event().wait(0.2)


if __name__ == '__main__':
    unittest.main()
