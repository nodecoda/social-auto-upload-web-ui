"""知乎平台抽测:注册表/类属性/签名 + 纯函数断言。

覆盖 _parse_cookie_to_storage_state(实例方法,用 object.__new__ stub 提供
platform_cookie_domain,不触发 __init__/浏览器)与模块级纯函数
_extract_year / _extract_month。不含 sqlite 依赖的 _get_video_orientation。
"""
import inspect
import sys
import time
from pathlib import Path

# 把 backend 目录加进 sys.path（与项目其他测试一致）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from conf import PLATFORM_ID_TO_KEY, PLATFORM_MAP
from impl.registry import get_platform, is_supported

# ----- 注册表 / 类属性 / app 映射(weibo 范本) -----

def test_zhihu_class_attributes():
    """ZhihuPlatform 的 platform_id/key/name 必须与 spec 一致。"""
    from impl.zhihu.platform import ZhihuPlatform
    p = ZhihuPlatform()
    assert p.platform_id == 14
    assert p.platform_key == "zhihu"
    assert p.platform_name == "知乎"


def test_zhihu_registered_in_registry():
    """Registry 必须能用 id=14 拿到 ZhihuPlatform。"""
    assert is_supported(14) is True
    platform = get_platform(14)
    assert platform is not None
    assert platform.__class__.__name__ == "ZhihuPlatform"


def test_zhihu_mappings_in_app():
    """app.py 的 PLATFORM_MAP / PLATFORM_ID_TO_KEY 必须包含 14。"""
    assert PLATFORM_MAP[14] == "知乎"
    assert PLATFORM_ID_TO_KEY[14] == "zhihu"


def test_zhihu_publish_video_signature():
    """publish_video 接受 **kwargs 并返回 bool(同步包装器),签名契约。"""
    from impl.zhihu.platform import ZhihuPlatform
    p = ZhihuPlatform()
    sig = inspect.signature(p.publish_video)
    assert any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in sig.parameters.values()
    ), "publish_video should accept **kwargs"
    assert sig.return_annotation is bool


# ----- 纯函数: _parse_cookie_to_storage_state -----

def _stub_zhihu():
    """object.__new__ stub:提供 platform_cookie_domain,不触发 __init__。"""
    from impl.zhihu.platform import ZhihuPlatform
    return object.__new__(ZhihuPlatform)


def test_parse_cookie_basic_pairs():
    """'k=v; k=v' 解析为 cookies 列表,全部归属 .zhihu.com。"""
    cookies, origins = _stub_zhihu()._parse_cookie_to_storage_state(
        "z_c0=abc123; d_c0=xyz789"
    )
    assert origins == []
    assert [c["name"] for c in cookies] == ["z_c0", "d_c0"]
    assert [c["value"] for c in cookies] == ["abc123", "xyz789"]
    assert all(c["domain"] == ".zhihu.com" for c in cookies)
    assert all(c["path"] == "/" for c in cookies)
    assert all(c["httpOnly"] is True for c in cookies)
    assert all(c["sameSite"] == "Lax" for c in cookies)


def test_parse_cookie_expires_in_future():
    """expires 使用保守占位(当前时间 + 导入有效期),必须晚于 now。"""
    cookies, _ = _stub_zhihu()._parse_cookie_to_storage_state("z_c0=abc")
    assert cookies[0]["expires"] > time.time()


def test_parse_cookie_skips_malformed_pairs():
    """空段与不含 '=' 的段被跳过,值两边的空白被 trim。"""
    cookies, _ = _stub_zhihu()._parse_cookie_to_storage_state(
        "z_c0=abc; ; naked; d_c0=  123  ;"
    )
    assert [c["name"] for c in cookies] == ["z_c0", "d_c0"]
    assert [c["value"] for c in cookies] == ["abc", "123"]


def test_parse_cookie_empty_string():
    """空串 → 空 cookies / 空 origins,不报错。"""
    cookies, origins = _stub_zhihu()._parse_cookie_to_storage_state("")
    assert cookies == []
    assert origins == []


# ----- 纯函数: _extract_year / _extract_month -----

def test_extract_year_chinese_date():
    """中文日期里提取 4 位年份。"""
    from impl.zhihu.platform import _extract_year
    assert _extract_year("2025年1月") == "2025"
    assert _extract_year("2026-05-16") == "2026"


def test_extract_year_missing_returns_zero():
    """无年份时返回 '0'。"""
    from impl.zhihu.platform import _extract_year
    assert _extract_year("abc") == "0"
    assert _extract_year("") == "0"
    assert _extract_year(None) == "0"


def test_extract_month_chinese_date():
    r"""中文日期 '2025年1月' → '1'(先匹配 \d+月,再回退年格式)。"""
    from impl.zhihu.platform import _extract_month
    assert _extract_month("2025年1月") == "1"
    assert _extract_month("2025年12月") == "12"
    assert _extract_month("2025年12 月") == "12"


def test_extract_month_missing_returns_zero():
    """无月份时返回 '0'。"""
    from impl.zhihu.platform import _extract_month
    assert _extract_month("no month here") == "0"
    assert _extract_month("") == "0"
