"""平台 cookie 字符串 → storage_state 解析测试。

16 个平台实现同构（split ';' + partition '=' + 归属 platform_cookie_domain），
用 baijiahao（文档标注的典型实现）锁模式 + 边界。
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from impl.baijiahao.platform import BaijiahaoPlatform
from impl.base_platform import BasePlatform


@pytest.fixture()
def parser():
    return BaijiahaoPlatform()._parse_cookie_to_storage_state


def test_parses_basic_pairs(parser):
    cookies, origins = parser("name1=value1; name2=value2")
    assert origins == []
    assert len(cookies) == 2
    assert cookies[0]["name"] == "name1"
    assert cookies[0]["value"] == "value1"


def test_cookies_attach_to_platform_domain(parser):
    cookies, _ = parser("k=v")
    assert cookies[0]["domain"] == BaijiahaoPlatform.platform_cookie_domain
    assert cookies[0]["path"] == "/"
    assert cookies[0]["httpOnly"] is True
    assert cookies[0]["sameSite"] == "Lax"


def test_expires_is_future_placeholder(parser):
    cookies, _ = parser("k=v")
    now = time.time()
    expected = now + BasePlatform._IMPORT_COOKIE_EXPIRES_SECONDS
    # 7 天占位，允许执行间隙误差
    assert expected - 5 <= cookies[0]["expires"] <= expected + 5


def test_skips_empty_and_malformed_segments(parser):
    cookies, _ = parser(" a=1 ; ; b = 2 ; noequal ")
    assert [c["name"] for c in cookies] == ["a", "b"]


def test_strips_whitespace_from_name_and_value(parser):
    cookies, _ = parser("  key  =  spaced  ")
    assert cookies[0]["name"] == "key"
    assert cookies[0]["value"] == "spaced"


def test_empty_string_returns_empty(parser):
    cookies, origins = parser("")
    assert cookies == []
    assert origins == []
