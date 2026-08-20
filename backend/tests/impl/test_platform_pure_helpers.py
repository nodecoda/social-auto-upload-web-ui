"""跨平台纯逻辑抽测(支撑 backend 覆盖率门槛 19%)。

只测已存在的纯函数/静态方法: 各平台 _parse_cookie_to_storage_state、
标题/字符工具、stats 构建等。不新增任何生产符号,不触发浏览器流程。
"""
import sys
from pathlib import Path

# 把 backend 目录加进 sys.path（与项目其他测试一致）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from impl.registry import get_platform

# 拥有自有 _parse_cookie_to_storage_state 实现的平台(registry id, 期望 domain)
_COOKIE_PLATFORMS = [
    (1, ".xiaohongshu.com"),
    (2, ".qq.com"),
    (3, ".douyin.com"),
    (4, ".kuaishou.com"),
    (5, ".bilibili.com"),
    (6, ".baidu.com"),
    (7, ".tiktok.com"),
    (8, ".youtube.com"),
    (9, ".qq.com"),
    (10, ".iqiyi.com"),
    (11, ".weibo.com"),
    (12, ".alipay.com"),
    (13, ".toutiao.com"),
]


# ----- 各平台 _parse_cookie_to_storage_state 契约一致 -----

def test_cookie_parser_basic_pairs():
    """'k=v; k=v' → 2 条 cookie,domain 归属各自平台域。"""
    for pid, domain in _COOKIE_PLATFORMS:
        platform = get_platform(pid)
        cookies, origins = platform._parse_cookie_to_storage_state("z_c0=abc; d_c0=xyz")
        assert origins == []
        assert [c["name"] for c in cookies] == ["z_c0", "d_c0"]
        assert [c["value"] for c in cookies] == ["abc", "xyz"]
        assert all(c["domain"] == domain for c in cookies)
        assert all(c["path"] == "/" for c in cookies)
        assert all(c["httpOnly"] is True for c in cookies)
        assert all(c["sameSite"] == "Lax" for c in cookies)


def test_cookie_parser_skips_malformed_pairs():
    """空段与不含 '=' 的段被跳过,值两边空白被 trim。"""
    for pid, _domain in _COOKIE_PLATFORMS:
        platform = get_platform(pid)
        cookies, origins = platform._parse_cookie_to_storage_state("a=1; ; naked; b= 2 ;")
        assert origins == []
        assert [(c["name"], c["value"]) for c in cookies] == [("a", "1"), ("b", "2")]


def test_cookie_parser_empty_string():
    """空串 → 空 cookies / 空 origins。"""
    for pid, _domain in _COOKIE_PLATFORMS:
        platform = get_platform(pid)
        assert platform._parse_cookie_to_storage_state("") == ([], [])


def test_cookie_parser_expires_in_future():
    """expires 为保守占位,晚于当前时间。"""
    import time as _time
    for pid, _domain in _COOKIE_PLATFORMS:
        platform = get_platform(pid)
        cookies, _ = platform._parse_cookie_to_storage_state("a=1")
        assert cookies[0]["expires"] > _time.time()


# ----- CSDN 特殊映射(cookie 域/secure/httpOnly/SESSION 复制) -----

def test_csdn_cookie_parser_basic_pairs():
    """CSDN 普通 cookie 归属 .csdn.net,httpOnly/secure 按名单默认 False。"""
    from impl.csdn.platform import CsdnPlatform
    cookies, origins = CsdnPlatform()._parse_cookie_to_storage_state("a=1; b=2")
    assert origins == []
    assert [c["name"] for c in cookies] == ["a", "b"]
    assert all(c["domain"] == ".csdn.net" for c in cookies)
    assert all(c["httpOnly"] is False for c in cookies)
    assert all(c["secure"] is False for c in cookies)


def test_csdn_cookie_domain_map_and_session():
    """CSDN 按 cookie 名映射子域;SESSION 额外复制一份到 msg.csdn.net。"""
    from impl.csdn.platform import CsdnPlatform
    cookies, _ = CsdnPlatform()._parse_cookie_to_storage_state(
        "https_waf_cookie=w; bc_bot_session=b; SESSION=s; plain=x"
    )
    by_name = {c["name"]: c for c in cookies}
    assert by_name["https_waf_cookie"]["domain"] == "passport.csdn.net"
    assert by_name["https_waf_cookie"]["secure"] is True
    assert by_name["bc_bot_session"]["domain"] == ".blog.csdn.net"
    assert by_name["SESSION"]["httpOnly"] is True
    assert by_name["plain"]["domain"] == ".csdn.net"
    session_domains = sorted(c["domain"] for c in cookies if c["name"] == "SESSION")
    assert session_domains == [".csdn.net", "msg.csdn.net"]


# ----- bilibili: 标题清理 / 简介截断 -----

def test_bilibili_sanitize_title():
    """emoji 与 HTML 危险字符被清除,普通字符保留。"""
    from impl.bilibili.platform import _sanitize_title
    assert _sanitize_title("") == ""
    assert _sanitize_title("普通标题123") == "普通标题123"
    assert _sanitize_title("a<b>c") == "abc"
    assert _sanitize_title('a"b\'c&d') == "abcd"
    assert "😀" not in _sanitize_title("标题😀")


def test_bilibili_truncate_desc_by_length():
    """按 emoji=3 规则截断,总字符数不超过 max_len。"""
    from impl.bilibili.platform import _truncate_desc_by_length
    assert _truncate_desc_by_length("") == ""
    assert _truncate_desc_by_length("abc", 2) == "ab"
    assert _truncate_desc_by_length("a😀b", 3) == "a"      # 😀 占 3,放不下即截断
    assert _truncate_desc_by_length("a😀b", 4) == "a😀"     # a(1)+😀(3)=4 恰好
    assert _truncate_desc_by_length("abcdef", 5) == "abcde"


# ----- channels: 短标题格式化 -----

def test_channels_format_short_title():
    """逗号转空格、其他特殊字符过滤、>16 截断、<6 补空格。"""
    from impl.channels.platform import _format_short_title
    assert _format_short_title("ab") == "ab    "
    assert _format_short_title("a" * 20) == "a" * 16
    assert _format_short_title("a,b") == "a b   "
    assert _format_short_title("abc!") == "abc   "


# ----- baijiahao: 字符计数 / 发布参数校验 -----

def test_baijiahao_count_chars():
    """中文/字母=1,emoji(>0xFFFF)=3。"""
    from impl.baijiahao.platform import BaijiahaoPlatform
    p = BaijiahaoPlatform()
    assert p._count_chars("abc") == 3
    assert p._count_chars("中文") == 2
    assert p._count_chars("😀") == 3


def test_baijiahao_validate_publish_params():
    """标签 >10 拒绝;描述+标签总字符 >50(emoji=3)拒绝;合法放行。"""
    from impl.baijiahao.platform import BaijiahaoPlatform
    ok, msg = BaijiahaoPlatform._validate_publish_params("hello", [])
    assert ok is True and msg == ""
    ok, msg = BaijiahaoPlatform._validate_publish_params(
        "", ["t%d" % i for i in range(11)]
    )
    assert ok is False and "最多 10 个标签" in msg
    ok, msg = BaijiahaoPlatform._validate_publish_params("x" * 51, [])
    assert ok is False and "超过 50" in msg


# ----- jingmai / taobao_guanghe: stats 构建 -----

def test_build_stats_maps_and_cleans_counts():
    """raw [{name,num}] → 标准 stats,逗号/空格清理,未知 label 跳过。"""
    from impl.jingmai.platform import JingmaiPlatform
    from impl.taobao_guanghe.platform import TaobaoGuanghePlatform
    label_map = {"播放量": (1, 1, "播放量")}
    raw = [
        {"name": "播放量", "num": "1,234"},
        {"name": "播放量", "num": "1 234.5"},
        {"name": "未知字段", "num": "9"},
    ]
    for cls in (JingmaiPlatform, TaobaoGuanghePlatform):
        stats = cls._build_stats(raw, label_map)
        assert len(stats) == 2
        assert [s["COUNT"] for s in stats] == [1234, 1234]
        assert all(s["ICON"] == 1 and s["SORT"] == 1 for s in stats)
        assert all(s["NAME"] == "播放量" for s in stats)


def test_build_stats_bad_num_falls_back_zero():
    """num 无法转 int 时按 0 计。"""
    from impl.jingmai.platform import JingmaiPlatform
    stats = JingmaiPlatform._build_stats(
        [{"name": "播放量", "num": "abc"}], {"播放量": (1, 1, "播放量")}
    )
    assert stats[0]["COUNT"] == 0


# ----- taobao_guanghe: trace 分组 -----

def test_group_by_trace_groups_and_preserves_order():
    """按 trace 签名分组,保留首次出现顺序。"""
    from impl.taobao_guanghe.platform import _group_by_trace
    items = [
        {"trace": {"tab": "bought", "keyword": "k1", "rule": "r1", "category": "c1"}, "id": 1},
        {"trace": {"tab": "bought", "keyword": "k2", "rule": "r1", "category": "c1"}, "id": 2},
        {"trace": {"tab": "bought", "keyword": "k1", "rule": "r1", "category": "c1"}, "id": 3},
        {"id": 4},  # 无 trace → 空签名分组
    ]
    groups = _group_by_trace(items)
    assert len(groups) == 3
    assert [g[1][0]["id"] for g in groups] == [1, 2, 4]
    assert [it["id"] for it in groups[0][1]] == [1, 3]
    assert groups[2][0] == {}  # 空 trace 兜底为空 dict 签名
    assert groups[2][1][0]["id"] == 4


# ----- youtube: _msg 恒等 -----

def test_youtube_msg_identity():
    """_msg 原样返回文本。"""
    from impl.youtube.platform import _msg
    assert _msg("测试消息") == "测试消息"


# ----- jd: 封面上传大小前置处理(纯文件逻辑,无浏览器) -----

def test_jd_ensure_cover_min_size_missing_and_ok(tmp_path):
    """不存在 → None;原文件已达标 → None(直接用原文件)。"""
    from impl.jd.platform import _ensure_cover_min_size
    assert _ensure_cover_min_size(tmp_path / "nope.jpg") is None
    big = tmp_path / "big.jpg"
    big.write_bytes(b"\0" * (200 * 1024))
    assert _ensure_cover_min_size(big) is None
    assert big.read_bytes() == b"\0" * (200 * 1024)


def test_jd_ensure_cover_min_size_small_image_returns_temp(tmp_path):
    """小封面经 PIL 重编码后返回临时文件(原文件不被改动)。"""
    from PIL import Image

    from impl.jd.platform import _ensure_cover_min_size
    small = tmp_path / "small.jpg"
    Image.new("RGB", (64, 64), "red").save(small, "JPEG", quality=90)
    before = small.read_bytes()
    out = _ensure_cover_min_size(small)
    # 放大后仍可能不达 200KB → 允许 None(退化直传),但不得抛异常/改原文件
    if out is not None:
        assert Path(out).exists()
    assert small.read_bytes() == before
