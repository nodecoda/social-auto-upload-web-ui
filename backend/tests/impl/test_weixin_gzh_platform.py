"""微信公众号平台抽测:注册表/类属性/签名 + 纯函数断言。

只测静态纯函数(_extract_token/_build_home_url/_build_publish_datetime/
_resolve_date_label),不触发浏览器/CloakBrowser 流程(模块惰性导入已验证)。
"""
import sys
import inspect
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from pathlib import Path

# 把 backend 目录加进 sys.path（与项目其他测试一致）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from impl.registry import is_supported, get_platform  # noqa: E402
from app import PLATFORM_MAP, PLATFORM_ID_TO_KEY  # noqa: E402


# ----- 注册表 / 类属性 / app 映射(weibo 范本) -----

def test_weixin_gzh_class_attributes():
    """WeixinGzhPlatform 的 platform_id/key/name 必须与 spec 一致。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    p = WeixinGzhPlatform()
    assert p.platform_id == 17
    assert p.platform_key == "weixin_gzh"
    assert p.platform_name == "微信公众号"


def test_weixin_gzh_registered_in_registry():
    """Registry 必须能用 id=17 拿到 WeixinGzhPlatform。"""
    assert is_supported(17) is True
    platform = get_platform(17)
    assert platform is not None
    assert platform.__class__.__name__ == "WeixinGzhPlatform"


def test_weixin_gzh_mappings_in_app():
    """app.py 的 PLATFORM_MAP / PLATFORM_ID_TO_KEY 必须包含 17。"""
    assert PLATFORM_MAP[17] == "微信公众号"
    assert PLATFORM_ID_TO_KEY[17] == "weixin_gzh"


def test_weixin_gzh_publish_video_signature():
    """publish_video 接受 **kwargs 并返回 bool(同步包装器),签名契约。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    p = WeixinGzhPlatform()
    sig = inspect.signature(p.publish_video)
    assert any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in sig.parameters.values()
    ), "publish_video should accept **kwargs"
    assert sig.return_annotation is bool


# ----- 纯函数: _extract_token -----

def test_extract_token_from_home_url():
    """从带 token 的创作中心首页 URL 解析出 token 字符串。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    page = SimpleNamespace(
        url="https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=124257639"
    )
    assert WeixinGzhPlatform._extract_token(page) == "124257639"


def test_extract_token_no_match_returns_empty():
    """URL 里没有 token 参数时返回空串。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    assert WeixinGzhPlatform._extract_token(SimpleNamespace(url="https://mp.weixin.qq.com/")) == ""
    assert WeixinGzhPlatform._extract_token(SimpleNamespace(url="")) == ""


def test_extract_token_page_url_raises_returns_empty():
    """page.url 抛异常(页面已销毁等)时返回空串而非冒泡。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform

    class _RaisingPage:
        @property
        def url(self):
            raise RuntimeError("page closed")

    assert WeixinGzhPlatform._extract_token(_RaisingPage()) == ""


# ----- 纯函数: _build_home_url -----

def test_build_home_url_with_token():
    """带 token 时拼装完整的创作中心首页 URL。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    url = WeixinGzhPlatform._build_home_url("124257639")
    assert url == (
        "https://mp.weixin.qq.com/cgi-bin/home"
        "?t=home/index&lang=zh_CN&token=124257639"
    )


def test_build_home_url_empty_token_falls_back_to_login():
    """无 token 时回退到公众号首页入口(不带 token,由 cookie 触发跳转)。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    assert WeixinGzhPlatform._build_home_url("") == "https://mp.weixin.qq.com/"
    assert WeixinGzhPlatform._build_home_url(None) == "https://mp.weixin.qq.com/"


# ----- 纯函数: _build_publish_datetime -----

def test_build_publish_datetime_local_iso():
    """本地 ISO 字符串解析为对应 datetime(取第一条,重复 total_files 份)。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    dt = WeixinGzhPlatform._build_publish_datetime("2026-09-01T10:30:00", 3)
    assert isinstance(dt, datetime)
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == (2026, 9, 1, 10, 30)


def test_build_publish_datetime_utc_iso_adds_8h():
    """UTC ISO 字符串(带 Z)解析后 +8 小时转北京时间。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    dt = WeixinGzhPlatform._build_publish_datetime("2026-05-16T13:00:00.000Z", 1)
    assert isinstance(dt, datetime)
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == (2026, 5, 16, 21, 0)


# ----- 纯函数: _resolve_date_label -----

def test_resolve_date_label_today():
    """目标日期为今天 → 「今天」。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    now = datetime.combine(date.today(), datetime.min.time())
    assert WeixinGzhPlatform._resolve_date_label(now) == "今天"


def test_resolve_date_label_tomorrow():
    """目标日期为明天 → 「明天」。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    dt = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
    assert WeixinGzhPlatform._resolve_date_label(dt) == "明天"


def test_resolve_date_label_other_day_uses_month_day():
    """其他日期 → 「M月D日」文案(公众号下拉 7 天内选项)。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    dt = datetime.combine(date.today() + timedelta(days=2), datetime.min.time())
    label = WeixinGzhPlatform._resolve_date_label(dt)
    assert label == f"{dt.month}月{dt.day}日"


# ----- 纯函数: _parse_cookie_to_storage_state(实例方法,stub 实例) -----

def _stub_weixin_gzh():
    """object.__new__ stub:提供 platform_cookie_domain,不触发 __init__。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    return object.__new__(WeixinGzhPlatform)


def test_parse_cookie_basic_pairs():
    """'k=v; k=v' 解析为 cookies 列表,全部归属 .qq.com。"""
    cookies, origins = _stub_weixin_gzh()._parse_cookie_to_storage_state(
        "a=1; b=2"
    )
    assert origins == []
    assert [(c["name"], c["value"]) for c in cookies] == [("a", "1"), ("b", "2")]
    assert all(c["domain"] == ".qq.com" for c in cookies)
    assert all(c["httpOnly"] is True for c in cookies)
    assert all(c["sameSite"] == "Lax" for c in cookies)


def test_parse_cookie_skips_malformed_pairs():
    """空段与不含 '=' 的段被跳过。"""
    cookies, _ = _stub_weixin_gzh()._parse_cookie_to_storage_state("a=1; ; naked; b= 2 ;")
    assert [(c["name"], c["value"]) for c in cookies] == [("a", "1"), ("b", "2")]


def test_parse_cookie_expires_in_future():
    """expires 使用保守占位(当前时间 + 7 天),必须晚于 now。"""
    import time as _time
    cookies, _ = _stub_weixin_gzh()._parse_cookie_to_storage_state("a=1")
    assert cookies[0]["expires"] > _time.time()


# ----- 纯函数: 时间滚轮 JS 片段生成 -----

def test_find_visible_picker_dl_js_returns_js():
    """返回的 JS 片段必须包含可见 dl 筛选逻辑,而非空串。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    js = WeixinGzhPlatform._find_visible_picker_dl_js()
    assert isinstance(js, str) and js
    assert "weui-desktop-picker__time" in js
    assert "getComputedStyle" in js


def test_wheel_items_js_body_kind_suffix():
    """hour/minute 分别生成对应滚轮选择器的 JS 片段。"""
    from impl.weixin_gzh.platform import WeixinGzhPlatform
    hour_js = WeixinGzhPlatform._wheel_items_js_body("hour")
    minute_js = WeixinGzhPlatform._wheel_items_js_body("minute")
    assert "__hour li" in hour_js
    assert "__minute li" in minute_js
    # 非 hour/minute 兜底为 minute
    assert "__minute li" in WeixinGzhPlatform._wheel_items_js_body("other")
