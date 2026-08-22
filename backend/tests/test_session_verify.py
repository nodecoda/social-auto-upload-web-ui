"""Phase B1/B2：基类会话探针 4 态分类器 + check_cookie 模板单测。

覆盖 active/stale/revoked/unknown 四态判定路径：
URL 黑名单 / 正向 URL / 正向 selector / 失效文本 / 失效 selector /
期望 URL / 业务域白名单 / 探针异常 / cookie 文件缺失 / bool 兼容。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.base_platform import (
    SESSION_ACTIVE,
    SESSION_REVOKED,
    SESSION_STALE,
    SESSION_UNKNOWN,
    BasePlatform,
)


class _ProbePage:
    """最小探针页：url 可变 + wait_for_url/get_by_text/locator/wait_for_selector。"""

    def __init__(self, url="", revoked_texts=(), revoked_selectors=(),
                 selector_counts=None):
        self.url = url
        self.revoked_texts = set(revoked_texts)
        self.revoked_selectors = set(revoked_selectors)
        self.selector_counts = selector_counts or {}
        self.goto_calls = []
        self._exc_after_goto = False

    async def goto(self, url, **kwargs):
        self.goto_calls.append(url)
        if self._exc_after_goto:
            raise TimeoutError("goto timeout")

    async def wait_for_load_state(self, state, timeout=None):
        pass

    def get_by_text(self, text):
        return _TextLocator(text in self.revoked_texts)

    async def wait_for_url(self, url, timeout=None):
        if self.url == url:
            return None
        raise TimeoutError(f"did not reach {url}")

    def locator(self, selector):
        return _CountLocator(self.selector_counts.get(selector, 1))

    async def wait_for_selector(self, selector, timeout=None):
        if selector in self.revoked_selectors:
            return _CountLocator(1)
        raise TimeoutError(f"selector {selector} not found")


class _TextLocator:
    def __init__(self, present):
        self._present = present

    async def wait_for(self, timeout=None):
        if self._present:
            return self
        raise TimeoutError("text not found")


class _CountLocator:
    def __init__(self, count):
        self._count = count

    async def count(self):
        return self._count

    @property
    def first(self):
        return self


import pytest


@pytest.fixture(autouse=True)
def _fake_cookie_exists(monkeypatch):
    """session_verify 前置的 cookie 文件存在性检查统一 mock 为存在。"""
    monkeypatch.setattr("impl.base_platform.os.path.exists", lambda p: True)


class _TestPlatform(BasePlatform):
    platform_id = 90
    platform_key = "t"
    platform_name = "T"

    CHECK_URL = "https://example.com/home"
    CHECK_SLEEP = 0.0

    async def login(self, id, status_queue, account_id=None):
        pass

    async def open_creator_center(self, cookie_file):
        pass

    async def publish_video(self, **kwargs):
        return True

    async def sync_profile(self, cookie_file):
        return {}


class _UrlBlacklistPlatform(_TestPlatform):
    CHECK_INVALID_URL_MARKERS = ("passport.example.com/login",)


class _ValidSelectorPlatform(_TestPlatform):
    CHECK_VALID_SELECTOR = "div.user-panel"


class _ValidUrlPlatform(_TestPlatform):
    CHECK_VALID_URL = ("example.com/home", "id=")


class _ValidHostPlatform(_TestPlatform):
    CHECK_VALID_HOST = "https://example.com/"


class _RevokedTextPlatform(_TestPlatform):
    CHECK_REVOKED_TEXT = ("扫码登录",)
    CHECK_VALID_URL = ("example.com/home",)


class _RevokedSelectorPlatform(_TestPlatform):
    CHECK_REVOKED_SELECTOR = "div.login-page"


class _ExpectUrlPlatform(_TestPlatform):
    CHECK_EXPECT_URL = "https://example.com/home"


class _NetworkIdlePlatform(_TestPlatform):
    CHECK_NETWORKIDLE = True
    CHECK_VALID_SELECTOR = "div.user-panel"


def _make_platform(plat, page):
    browser = MagicMock()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    plat.create_browser = AsyncMock(return_value=browser)
    plat.create_context = AsyncMock(return_value=context)
    plat.close_browser = AsyncMock()
    return plat, browser, context


def _verify(plat, page):
    plat, _b, _c = _make_platform(plat, page)
    return asyncio.run(plat.session_verify("u1.json"))


class TestProbeStates:
    def test_url_blacklist_miss_active(self):
        plat, page = _TestPlatform(), _ProbePage(url="https://example.com/home")
        assert _verify(plat, page)["state"] == SESSION_ACTIVE

    def test_url_blacklist_hit_stale(self):
        plat, page = _UrlBlacklistPlatform(), _ProbePage(url="https://passport.example.com/login?redirect=1")
        assert _verify(plat, page)["state"] == SESSION_STALE

    def test_valid_selector_present_active(self):
        plat, page = _ValidSelectorPlatform(), _ProbePage(
            url="https://example.com/home", selector_counts={"div.user-panel": 1})
        assert _verify(plat, page)["state"] == SESSION_ACTIVE

    def test_valid_selector_missing_stale(self):
        plat, page = _ValidSelectorPlatform(), _ProbePage(
            url="https://example.com/home", selector_counts={"div.user-panel": 0})
        assert _verify(plat, page)["state"] == SESSION_STALE

    def test_valid_url_all_match_active(self):
        plat, page = _ValidUrlPlatform(), _ProbePage(
            url="https://example.com/home?id=123")
        assert _verify(plat, page)["state"] == SESSION_ACTIVE

    def test_valid_url_partial_miss_stale(self):
        plat, page = _ValidUrlPlatform(), _ProbePage(url="https://example.com/home")
        assert _verify(plat, page)["state"] == SESSION_STALE

    def test_valid_host_stay_active(self):
        plat, page = _ValidHostPlatform(), _ProbePage(url="https://example.com/home")
        assert _verify(plat, page)["state"] == SESSION_ACTIVE

    def test_valid_host_redirect_stale(self):
        plat, page = _ValidHostPlatform(), _ProbePage(url="https://other.com/login")
        assert _verify(plat, page)["state"] == SESSION_STALE

    def test_revoked_text_hit(self):
        plat, page = _RevokedTextPlatform(), _ProbePage(
            url="https://example.com/home", revoked_texts=("扫码登录",))
        assert _verify(plat, page)["state"] == SESSION_REVOKED

    def test_revoked_text_miss_active(self):
        plat, page = _RevokedTextPlatform(), _ProbePage(url="https://example.com/home")
        assert _verify(plat, page)["state"] == SESSION_ACTIVE

    def test_revoked_selector_hit(self):
        plat, page = _RevokedSelectorPlatform(), _ProbePage(
            url="https://example.com/login", revoked_selectors=("div.login-page",))
        assert _verify(plat, page)["state"] == SESSION_REVOKED

    def test_expect_url_miss_stale(self):
        plat, page = _ExpectUrlPlatform(), _ProbePage(url="https://example.com/login")
        assert _verify(plat, page)["state"] == SESSION_STALE

    def test_expect_url_hit_active(self):
        plat, page = _ExpectUrlPlatform(), _ProbePage(url="https://example.com/home")
        assert _verify(plat, page)["state"] == SESSION_ACTIVE

    def test_probe_exception_unknown(self):
        plat, page = _TestPlatform(), _ProbePage(url="")
        page._exc_after_goto = True
        assert _verify(plat, page)["state"] == SESSION_UNKNOWN

    def test_networkidle_then_valid(self):
        plat, page = _NetworkIdlePlatform(), _ProbePage(
            url="https://example.com/home", selector_counts={"div.user-panel": 1})
        assert _verify(plat, page)["state"] == SESSION_ACTIVE


class TestCheckCookieCompat:
    def test_missing_cookie_file_revoked(self, monkeypatch):
        plat, page = _TestPlatform(), _ProbePage(url="https://example.com/home")
        plat, _b, _c = _make_platform(plat, page)
        monkeypatch.setattr("impl.base_platform.os.path.exists", lambda p: False)
        result = asyncio.run(plat.session_verify("no_such.json"))
        assert result["state"] == SESSION_REVOKED
        # 不触发浏览器
        plat.create_browser.assert_not_called()

    def test_check_cookie_bool_active_true(self):
        plat, page = _TestPlatform(), _ProbePage(url="https://example.com/home")
        plat, _b, _c = _make_platform(plat, page)
        assert asyncio.run(plat.check_cookie("u1.json")) is True

    def test_check_cookie_bool_stale_false(self):
        plat, page = _UrlBlacklistPlatform(), _ProbePage(
            url="https://passport.example.com/login")
        plat, _b, _c = _make_platform(plat, page)
        assert asyncio.run(plat.check_cookie("u1.json")) is False

    def test_browser_chain_closed(self):
        plat, page = _TestPlatform(), _ProbePage(url="https://example.com/home")
        plat, browser, context = _make_platform(plat, page)
        asyncio.run(plat.check_cookie("u1.json"))
        plat.create_browser.assert_awaited_once()
        plat.create_context.assert_awaited_once_with(browser, storage_state=str(Path(BASE_DIR / "cookiesFile" / "u1.json")))
        context.close.assert_awaited_once()
        plat.close_browser.assert_awaited_once_with(browser)
