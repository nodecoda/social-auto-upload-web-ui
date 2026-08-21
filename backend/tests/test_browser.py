"""CloakBrowser 工厂契约测试（T28）。

impl/_browser.py 是所有平台浏览器入口的唯一装配点:
- init / _download_binary: 二进制预下载
- create_browser: launch_async + login 监听（disconnected 回调 / watchdog 轮询 / safe_close 包装）
- create_context / create_persistent_context: 异步 context 创建
- close_browser: 统一关闭（is_close_by_code 标志）
- create_browser_sync / create_context_sync: 同步入口

cloakbrowser 是懒加载第三方依赖,全部通过 sys.modules 注入 fake 模块驱动。
"""
import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from impl._browser import (
    close_browser,
    create_browser,
    create_browser_sync,
    create_context,
    create_context_sync,
    create_persistent_context,
    init,
)


def _run(coro):
    return asyncio.run(coro)


def _fake_browser():
    b = MagicMock()
    b.on = MagicMock()
    b.is_connected = MagicMock(return_value=True)
    b.close = AsyncMock()
    return b


def _fake_cloak(launch_ret=None, persistent_ret=None):
    cloak = types.ModuleType('cloakbrowser')
    cloak.launch_async = AsyncMock(return_value=launch_ret)
    cloak.launch = MagicMock(return_value=launch_ret)
    cloak.ensure_binary = MagicMock()
    cloak.launch_persistent_context_async = AsyncMock(return_value=persistent_ret)
    return cloak


# ── 二进制预下载 ───────────────────────────────────────────────────────────

class TestDownloadAndInit:
    def test_download_binary_calls_ensure(self):
        cloak = _fake_cloak()
        with patch.dict(sys.modules, {'cloakbrowser': cloak}):
            from impl._browser import _download_binary
            _download_binary()
        cloak.ensure_binary.assert_called_once()

    def test_init_success_logs_info(self):
        with patch('impl._browser._download_binary') as db, \
             patch('impl._browser.logger') as lg:
            init()
        db.assert_called_once()
        lg.info.assert_called()

    def test_init_failure_logs_warning(self):
        with patch('impl._browser._download_binary', side_effect=RuntimeError('net down')), \
             patch('impl._browser.logger') as lg:
            init()  # 不抛异常
        lg.warning.assert_called()


# ── create_browser: 启动参数 ───────────────────────────────────────────────

class TestCreateBrowserLaunch:
    def test_plain_headless_no_watchdog(self):
        """headless=True 且非 login: 不注册任何关闭监听。"""
        fake = _fake_browser()
        cloak = _fake_cloak(launch_ret=fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), \
             patch('impl._browser.asyncio.create_task', MagicMock()) as ct:
            b = _run(create_browser(headless=True, login_mode=False))
        assert b is fake
        cloak.launch_async.assert_awaited_once_with(
            headless=True, args=['--start-maximized'],
            humanize=False, human_preset='default',
        )
        fake.on.assert_not_called()
        ct.assert_not_called()

    def test_headless_resolved_from_conf(self):
        """headless=None: 非 login 用 LOCAL_CHROME_HEADLESS(True)。"""
        fake = _fake_browser()
        cloak = _fake_cloak(launch_ret=fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), \
             patch('impl._browser.asyncio.create_task', MagicMock()):
            _run(create_browser())
        cloak.launch_async.assert_awaited_once()
        assert cloak.launch_async.await_args.kwargs['headless'] is True

    def test_login_mode_uses_login_headless(self):
        """login_mode=True 用 LOGIN_HEADLESS(False,可见扫码)。"""
        fake = _fake_browser()
        cloak = _fake_cloak(launch_ret=fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), \
             patch('impl._browser.asyncio.create_task', MagicMock()):
            _run(create_browser(login_mode=True))
        assert cloak.launch_async.await_args.kwargs['headless'] is False

    def test_humanize_passthrough(self):
        fake = _fake_browser()
        cloak = _fake_cloak(launch_ret=fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), \
             patch('impl._browser.asyncio.create_task', MagicMock()):
            _run(create_browser(headless=True, humanize=True, human_preset='careful'))
        cloak.launch_async.assert_awaited_once_with(
            headless=True, args=['--start-maximized'],
            humanize=True, human_preset='careful',
        )


# ── create_browser: 关闭监听（login / 有头） ───────────────────────────────

class TestCreateBrowserWatchdog:
    def test_visible_browser_wires_listeners(self):
        """headless=False → 注册 disconnected 监听 + 包装 close + 起 watchdog。"""
        fake = _fake_browser()
        orig_close = fake.close
        cloak = _fake_cloak(launch_ret=fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), \
             patch('impl._browser.asyncio.create_task', MagicMock()) as ct:
            b = _run(create_browser(headless=False))
        fake.on.assert_called_once()
        assert fake.on.call_args.args[0] == 'disconnected'
        ct.assert_called_once()
        assert b._is_close_by_code is False
        assert b.close is not orig_close  # 已被 safe_close 包装

    def test_disconnected_cancels_current_task(self):
        """用户手动关浏览器 → disconnected 回调 cancel 当前 task。"""
        fake = _fake_browser()
        cloak = _fake_cloak(launch_ret=fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), \
             patch('impl._browser.asyncio.create_task', MagicMock()):
            async def _main():
                await create_browser(headless=False)
                cb = fake.on.call_args.args[1]
                cb()  # 模拟 disconnected 事件
                try:
                    await asyncio.sleep(0)
                    raise AssertionError('expected CancelledError')
                except asyncio.CancelledError:
                    pass
            _run(_main())

    def test_disconnected_no_cancel_when_code_close(self):
        """is_close_by_code=True(代码收尾)→ disconnected 不 cancel。"""
        fake = _fake_browser()
        cloak = _fake_cloak(launch_ret=fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), \
             patch('impl._browser.asyncio.create_task', MagicMock()):
            async def _main():
                browser = await create_browser(headless=False)
                browser._is_close_by_code = True
                cb = fake.on.call_args.args[1]
                cb()
                await asyncio.sleep(0)  # 正常完成,无 CancelledError
            _run(_main())

    def test_safe_close_sets_flag_before_close(self):
        """代码主动 close → 先置 is_close_by_code=True 再调原 close。"""
        fake = _fake_browser()
        orig_close = fake.close
        cloak = _fake_cloak(launch_ret=fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), \
             patch('impl._browser.asyncio.create_task', MagicMock()):
            async def _main():
                browser = await create_browser(headless=False)
                assert browser._is_close_by_code is False
                await browser.close()
                assert browser._is_close_by_code is True
            _run(_main())
        orig_close.assert_awaited_once()

    def test_register_failure_falls_back_to_polling(self):
        """on() 注册失败 → 记日志但 watchdog 仍启用。"""
        fake = _fake_browser()
        fake.on = MagicMock(side_effect=RuntimeError('no event emitter'))
        cloak = _fake_cloak(launch_ret=fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), \
             patch('impl._browser.logger') as lg, \
             patch('impl._browser.asyncio.create_task', MagicMock()) as ct:
            _run(create_browser(headless=False))
        lg.info.assert_called()
        ct.assert_called_once()


# ── create_browser: watchdog 轮询 ──────────────────────────────────────────

def _capture_watchdog(fake):
    """patch create_task 捕获 watchdog 协程,手动驱动验证。"""
    captured = {}

    def _capture(coro, *a, **k):
        captured['coro'] = coro
        return MagicMock()

    ctx = patch('impl._browser.asyncio.create_task', side_effect=_capture)
    return captured, ctx


class TestWatchdog:
    def test_watchdog_cancels_when_browser_closed(self):
        """watchdog 检测 is_connected=False(非代码关闭)→ cancel 当前 task。"""
        fake = _fake_browser()
        cloak = _fake_cloak(launch_ret=fake)
        captured, ctx = _capture_watchdog(fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), ctx:
            async def _main():
                await create_browser(headless=False)
                fake.is_connected.return_value = False
                with patch('impl._browser.asyncio.sleep', AsyncMock()):
                    await captured['coro']
                try:
                    await asyncio.sleep(0)
                    raise AssertionError('expected CancelledError')
                except asyncio.CancelledError:
                    pass
            _run(_main())

    def test_watchdog_exits_when_code_close(self):
        """is_close_by_code=True → watchdog 首轮即退出,不 cancel。"""
        fake = _fake_browser()
        cloak = _fake_cloak(launch_ret=fake)
        captured, ctx = _capture_watchdog(fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), ctx:
            async def _main():
                browser = await create_browser(headless=False)
                browser._is_close_by_code = True
                with patch('impl._browser.asyncio.sleep', AsyncMock()):
                    await captured['coro']  # 立即 return
                await asyncio.sleep(0)  # 正常完成
            _run(_main())

    def test_watchdog_cancelled_is_silent(self):
        """watchdog 自身被取消(CancelledError)→ 静默退出不刷错误。"""
        fake = _fake_browser()
        cloak = _fake_cloak(launch_ret=fake)
        captured, ctx = _capture_watchdog(fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), ctx:
            async def _main():
                await create_browser(headless=False)
                wd = asyncio.ensure_future(captured['coro'])
                await asyncio.sleep(0.01)  # 让 watchdog 进入 sleep 悬挂
                wd.cancel()
                await asyncio.gather(wd, return_exceptions=True)  # 吞掉 CancelledError
            _run(_main())

    def test_watchdog_exception_treated_as_disconnect(self):
        """is_connected 抛异常(对象释放)且非代码关闭 → 也 cancel。"""
        fake = _fake_browser()
        cloak = _fake_cloak(launch_ret=fake)
        captured, ctx = _capture_watchdog(fake)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}), ctx:
            async def _main():
                await create_browser(headless=False)
                fake.is_connected.side_effect = RuntimeError('released')
                with patch('impl._browser.asyncio.sleep', AsyncMock()):
                    await captured['coro']
                try:
                    await asyncio.sleep(0)
                    raise AssertionError('expected CancelledError')
                except asyncio.CancelledError:
                    pass
            _run(_main())


# ── 异步 context / 关闭 ────────────────────────────────────────────────────

class TestContextAndClose:
    def test_create_context_passes_params(self):
        browser = MagicMock()
        browser.new_context = AsyncMock()
        _run(create_context(browser, storage_state='s.json', user_agent='UA'))
        browser.new_context.assert_awaited_once_with(
            storage_state='s.json', user_agent='UA', no_viewport=True,
        )

    def test_create_context_defaults(self):
        browser = MagicMock()
        browser.new_context = AsyncMock()
        _run(create_context(browser))
        browser.new_context.assert_awaited_once_with(
            storage_state=None, user_agent=None, no_viewport=True,
        )

    def test_create_persistent_context(self):
        ret = MagicMock()
        cloak = _fake_cloak(persistent_ret=ret)
        with patch.dict(sys.modules, {'cloakbrowser': cloak}):
            result = _run(create_persistent_context('/tmp/ud', headless=True))
        assert result is ret
        cloak.launch_persistent_context_async.assert_awaited_once_with(
            '/tmp/ud', headless=True, no_viewport=True,
            args=['--window-size=1920,1080', '--start-maximized'],
        )

    def test_close_sets_flag_and_closes(self):
        browser = MagicMock()
        browser.close = AsyncMock()
        _run(close_browser(browser))
        assert browser._is_close_by_code is True
        browser.close.assert_awaited_once()

    def test_close_flag_false(self):
        browser = MagicMock()
        browser.close = AsyncMock()
        _run(close_browser(browser, is_close_by_code=False))
        assert browser._is_close_by_code is False

    def test_close_swallows_errors(self):
        browser = MagicMock()
        browser.close = AsyncMock(side_effect=RuntimeError('boom'))
        _run(close_browser(browser))  # 不抛

    def test_close_flag_set_failure_falls_back(self):
        """_is_close_by_code 赋值失败(只读对象)→ 走 fallback 仍尝试 close。"""
        class _ReadOnlyAttr(MagicMock):
            def __setattr__(self, name, value):
                if name == '_is_close_by_code':
                    raise AttributeError('readonly')
                return super().__setattr__(name, value)

        browser = _ReadOnlyAttr()
        browser.close = AsyncMock()
        _run(close_browser(browser))  # 不抛
        browser.close.assert_awaited_once()


# ── 同步入口 ───────────────────────────────────────────────────────────────

class TestSyncEntries:
    def test_create_browser_sync(self):
        cloak = _fake_cloak(launch_ret='B')
        with patch.dict(sys.modules, {'cloakbrowser': cloak}):
            assert create_browser_sync(headless=True) == 'B'
        cloak.launch.assert_called_once_with(headless=True)

    def test_create_context_sync(self):
        browser = MagicMock()
        browser.new_context = MagicMock(return_value='CTX')
        assert create_context_sync(browser, storage_state='s', user_agent='ua') == 'CTX'
        browser.new_context.assert_called_once_with(
            storage_state='s', user_agent='ua', no_viewport=True,
        )
