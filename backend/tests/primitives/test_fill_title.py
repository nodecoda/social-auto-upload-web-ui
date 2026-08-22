"""fill_title 原语单测（Phase A1）：fill / rich_text 策略 + 截断 + 净化。"""
import asyncio
from unittest.mock import AsyncMock, patch

from impl.primitives import PARAMS, fill_title, sanitize_title
from tests.primitives.conftest import FakePage


def _run(fn, *args, **kwargs):
    with patch("impl.primitives.fill_title.asyncio.sleep", AsyncMock()):
        return asyncio.run(fn(*args, **kwargs))


class TestSanitizeTitle:
    def test_strips_emoji(self):
        assert sanitize_title("标题👍好") == "标题好"

    def test_strips_html_danger(self):
        assert sanitize_title('a<b>"c"') == "abc"

    def test_none_returns_none(self):
        assert sanitize_title(None) is None


class TestFillStrategy:
    def test_fill_plain_and_truncate(self):
        page = FakePage()
        title = "长" * 60
        _run(fill_title, page, title, PARAMS["zhihu"]["FILL_TITLE"])
        fills = [c for c in page.calls if c[0] == "fill"]
        assert fills[-1][2] == "长" * 50

    def test_empty_title_shortcircuit(self):
        page = FakePage()
        _run(fill_title, page, "", PARAMS["zhihu"]["FILL_TITLE"])
        assert page.calls == []

    def test_jd_frame_path(self):
        page = FakePage()
        frame = FakePage()
        _run(fill_title, page, "标题", PARAMS["jd"]["FILL_TITLE"], frame=frame)
        # frame.wait_for_selector 被调用
        assert any("input#title" in str(c[1]) for c in frame.calls)

    def test_bilibili_sanitize_and_truncate(self):
        page = FakePage()
        _run(fill_title, page, "标题👍" + "长" * 90, PARAMS["bilibili"]["FILL_TITLE"])
        fills = [c for c in page.calls if c[0] == "fill"]
        assert fills[-1][2] == "标题" + "长" * 78  # 80 - 2 个字符


class TestRichTextStrategy:
    def test_tencent_contenteditable(self):
        page = FakePage()
        _run(fill_title, page, "腾讯标题", PARAMS["tencent_video"]["FILL_TITLE"])
        assert any(c[0] == "keyboard.type" and c[1] == "腾讯标题" for c in page.calls)
