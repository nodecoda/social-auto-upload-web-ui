"""upload_cover 原语单测（Phase A1）：tencent_video / iqiyi 封面图上传。"""
import asyncio
from unittest.mock import AsyncMock, patch

from impl.primitives import PARAMS, upload_cover
from tests.primitives.conftest import FakePage

_EXISTS = __file__  # 用测试文件自身作为“存在的文件”路径


def _run(fn, *args, **kwargs):
    with patch("impl.primitives.thumbnail.asyncio.sleep", AsyncMock()):
        return asyncio.run(fn(*args, **kwargs))


class TestUploadCover:
    def test_tencent_video_single_cover(self):
        page = FakePage()
        _run(upload_cover, page, PARAMS["tencent_video"]["THUMBNAIL"],
             cover_path=_EXISTS, aspect="16:9")
        assert any(c[0] == "set_input_files" for c in page.calls)

    def test_iqiyi_multi_panel_chooser(self):
        page = FakePage()
        _run(upload_cover, page, PARAMS["iqiyi"]["THUMBNAIL"],
             paths={"portrait": _EXISTS, "landscape": _EXISTS})
        chooser_calls = [c for c in page.calls if c[0] == "file_chooser.set_files"]
        assert len(chooser_calls) == 2

    def test_iqiyi_done_button(self):
        page = FakePage()
        _run(upload_cover, page, PARAMS["iqiyi"]["THUMBNAIL"],
             paths={"portrait": _EXISTS})
        assert any("完成" in c[1] for c in page.calls if c[0] == "click")
