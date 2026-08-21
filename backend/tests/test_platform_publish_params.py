"""平台发布参数校验纯函数契约测试（T13）。

抖音 _count_hashtags/_validate_publish_params、小红书 _count_hashtags、
百家号 _count_chars/_validate_publish_params —— 全部纯函数直接测。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from impl.baijiahao.platform import BaijiahaoPlatform
from impl.douyin.platform import DouyinPlatform
from impl.xiaohongshu.platform import _count_hashtags as xhs_count_hashtags

# ── 抖音话题计数 ────────────────────────────────────────────────────────────

class TestDouyinCountHashtags:
    def test_empty(self):
        assert DouyinPlatform._count_hashtags('') == 0
        assert DouyinPlatform._count_hashtags(None) == 0

    def test_no_hashtag(self):
        assert DouyinPlatform._count_hashtags('今天天气不错') == 0

    def test_single(self):
        assert DouyinPlatform._count_hashtags('看看 #旅游 视频') == 1

    def test_line_start(self):
        assert DouyinPlatform._count_hashtags('#美食 视频') == 1

    def test_multiple_newlines(self):
        assert DouyinPlatform._count_hashtags('#a\n#b\n#c') == 3

    def test_embedded_hash_not_counted(self):
        """a#b / http://x#anchor 不算话题。"""
        assert DouyinPlatform._count_hashtags('abc#def') == 0
        assert DouyinPlatform._count_hashtags('看 http://x.com#anchor 链接') == 0

    def test_double_hash_not_counted(self):
        assert DouyinPlatform._count_hashtags('##标签') == 0

    def test_trailing_lone_hash(self):
        assert DouyinPlatform._count_hashtags('文本 #') == 0

    def test_mixed(self):
        text = '开头 #旅行 中间 #美食\n结尾 #Vlog 嵌入a#b 双##x'
        assert DouyinPlatform._count_hashtags(text) == 3


# ── 抖音发布参数校验 ────────────────────────────────────────────────────────

class TestDouyinValidatePublishParams:
    def test_ok_empty(self):
        assert DouyinPlatform._validate_publish_params('', [], []) == (True, '')

    def test_ok_within_limit(self):
        assert DouyinPlatform._validate_publish_params('#a #b', ['t1', 't2'], ['act1']) == (True, '')

    def test_over_limit(self):
        ok, msg = DouyinPlatform._validate_publish_params('#a', ['t1', 't2', 't3', 't4'], ['act1'])
        assert ok is False
        assert '超过 5 个' in msg
        assert '描述 #xxx 1' in msg

    def test_none_inputs(self):
        assert DouyinPlatform._validate_publish_params(None, None, None) == (True, '')

    def test_only_desc_over(self):
        ok, _ = DouyinPlatform._validate_publish_params('#a #b #c #d #e #f', [], [])
        assert ok is False

    def test_only_activities_over(self):
        ok, msg = DouyinPlatform._validate_publish_params('', [], ['a', 'b', 'c', 'd', 'e', 'f'])
        assert ok is False
        assert '官方活动 6' in msg


# ── 小红书话题计数(同语义) ─────────────────────────────────────────────────

class TestXiaohongshuCountHashtags:
    def test_empty(self):
        assert xhs_count_hashtags('') == 0

    def test_basic(self):
        assert xhs_count_hashtags('#穿搭 分享') == 1

    def test_embedded_not_counted(self):
        assert xhs_count_hashtags('www.x.com#anchor') == 0

    def test_double_hash(self):
        assert xhs_count_hashtags('##x') == 0

    def test_multiple(self):
        assert xhs_count_hashtags('#a #b\n#c') == 3


# ── 百家号字符计数 ──────────────────────────────────────────────────────────

class TestBaijiahaoCountChars:
    def test_ascii(self):
        assert BaijiahaoPlatform._count_chars('abc123') == 6

    def test_chinese(self):
        assert BaijiahaoPlatform._count_chars('中文') == 2

    def test_emoji_wide(self):
        # \U0001F600 😀 超出 BMP → 按 3 计
        assert BaijiahaoPlatform._count_chars('\U0001F600') == 3

    def test_empty(self):
        assert BaijiahaoPlatform._count_chars('') == 0


# ── 百家号发布参数校验 ─────────────────────────────────────────────────────

class TestBaijiahaoValidatePublishParams:
    def test_ok_empty(self):
        assert BaijiahaoPlatform._validate_publish_params('', []) == (True, '')

    def test_too_many_tags(self):
        tags = [f't{i}' for i in range(11)]
        ok, msg = BaijiahaoPlatform._validate_publish_params('', tags)
        assert ok is False
        assert '最多 10 个标签' in msg

    def test_char_count_over(self):
        ok, msg = BaijiahaoPlatform._validate_publish_params('x' * 49, [])
        assert ok is True  # 49 ≤ 50
        ok, msg = BaijiahaoPlatform._validate_publish_params('x' * 51, [])
        assert ok is False
        assert '超过 50' in msg

    def test_desc_plus_tags_counted(self):
        """描述 + #标签 拼接后计总字符。"""
        ok, _ = BaijiahaoPlatform._validate_publish_params('x' * 45, ['长标签一'])
        assert ok is False  # 45 + 1 + #长标签一(5) = 51 > 50

    def test_emoji_counts_three(self):
        ok, _ = BaijiahaoPlatform._validate_publish_params('\U0001F600' * 16, [])
        assert ok is True  # 16*3 = 48 ≤ 50
        ok, msg = BaijiahaoPlatform._validate_publish_params('\U0001F600' * 17, [])
        assert ok is False  # 17*3 = 51 > 50
        assert '超过 50' in msg
