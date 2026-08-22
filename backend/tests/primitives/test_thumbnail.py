"""set_thumbnail 原语单测（Phase A1）：file_input / click_modal / hover_modal /
file_chooser / direct_file_first 策略 + 多方向 + 确认。"""
import asyncio
from unittest.mock import AsyncMock, patch

from impl.primitives import PARAMS, set_thumbnail
from tests.primitives.conftest import FakePage

_EXISTS = __file__  # 用测试文件自身作为“存在的文件”路径


def _run(fn, *args, **kwargs):
    with patch("impl.primitives.thumbnail.asyncio.sleep", AsyncMock()):
        return asyncio.run(fn(*args, **kwargs))


class TestFileInputStrategy:
    def test_csdn_direct_upload_and_confirm(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["csdn"]["THUMBNAIL"], thumbnail_path=_EXISTS)
        assert any(c[0] == "set_input_files" for c in page.calls)
        assert any("el-button--primary" in c[1] for c in page.calls)

    def test_missing_file_skipped(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["csdn"]["THUMBNAIL"], thumbnail_path="/no/such.png")
        assert page.calls == []

    def test_no_paths_returns(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["csdn"]["THUMBNAIL"], paths={})
        assert page.calls == []

    def test_channels_candidates_fallback(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["channels"]["THUMBNAIL"],
             paths={"portrait": _EXISTS})
        assert any(c[0] == "set_input_files" for c in page.calls)


class TestClickModalStrategy:
    def test_douyin_trigger_modal_and_orientations(self):
        page = FakePage(attributes={"div[class*='steps'] div": {"nth_texts": ["竖版封面", "横版封面"]}})
        _run(set_thumbnail, page, PARAMS["douyin"]["THUMBNAIL"],
             paths={"portrait": _EXISTS, "landscape": _EXISTS})
        assert any(c[0] == "click" and "选择封面" in c[1] for c in page.calls)
        assert sum(1 for c in page.calls if c[0] == "set_input_files") == 2
        assert any("完成" in c[1] for c in page.calls)

    def test_bilibili_direct_file_first(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["bilibili"]["THUMBNAIL"],
             thumbnail_path=_EXISTS)
        assert any(c[0] == "set_input_files" for c in page.calls)


class TestHoverModalStrategy:
    def test_kuaishou_hover_trigger(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["kuaishou"]["THUMBNAIL"],
             thumbnail_path=_EXISTS)
        assert any(c[0] == "hover" for c in page.calls)
        assert any(c[0] == "set_input_files" for c in page.calls)


class TestFileChooserStrategy:
    def test_zhihu_file_chooser(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["zhihu"]["THUMBNAIL"],
             thumbnail_path=_EXISTS)
        assert any(c[0] == "file_chooser.set_files" for c in page.calls)


class TestOrientations:
    def test_portrait_only_path(self):
        page = FakePage(attributes={"div[class*='steps'] div": {"nth_texts": ["竖版封面", "横版封面"]}})
        _run(set_thumbnail, page, PARAMS["douyin"]["THUMBNAIL"],
             paths={"portrait": _EXISTS})
        assert sum(1 for c in page.calls if c[0] == "set_input_files") == 1
