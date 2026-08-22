"""set_thumbnail 原语单测（Phase A1）：file_input / click_modal / hover_modal /
file_chooser / direct_file_first 策略 + 多方向 + 确认。"""
import asyncio
from unittest.mock import AsyncMock, patch

from impl.primitives import PARAMS, set_thumbnail, upload_cover
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
             paths={"landscape": _EXISTS})
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


class TestHoverTrigger:
    """hover_trigger_selector：先悬停封面预览再点击操作按钮（xiaohongshu）。"""

    def test_xiaohongshu_hover_then_click_trigger(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["xiaohongshu"]["THUMBNAIL"],
             thumbnail_path=_EXISTS)
        hovers = [c for c in page.calls if c[0] == "hover"]
        assert any("background-image" in c[1] for c in hovers)
        clicks = [c for c in page.calls if c[0] == "click"]
        assert any("operator.pointer" in c[1] for c in clicks)
        assert any(c[0] == "set_input_files" for c in page.calls)


class TestOpenTab:
    """open_tab_selector：多方向循环前先切换一次上传 tab（kuaishou/toutiao/zhihu）。"""

    def test_kuaishou_open_tab_before_upload(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["kuaishou"]["THUMBNAIL"],
             paths={"portrait": _EXISTS})
        clicks = [c for c in page.calls if c[0] == "click"]
        assert any("header-title-item" in c[1] for c in clicks)
        assert any("3:4" in c[1] for c in clicks)  # 竖版→3:4 裁剪比例
        assert any(c[0] == "set_input_files" for c in page.calls)

    def test_toutiao_open_tab(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["toutiao"]["THUMBNAIL"],
             thumbnail_path=_EXISTS)
        clicks = [c for c in page.calls if c[0] == "click"]
        assert any("本地上传" in c[1] for c in clicks)


class TestEntryMode:
    """entry_selector：每个方向独立点开封面入口（channels 横/竖封面）。"""

    def test_channels_two_entries_uploaded(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["channels"]["THUMBNAIL"],
             paths={"portrait": _EXISTS, "landscape": _EXISTS})
        entry_clicks = [
            c for c in page.calls if c[0] == "click"
            and ("vertical-cover-wrap" in c[1] or "horizon-cover-wrap" in c[1])
        ]
        assert len(entry_clicks) == 2
        assert sum(1 for c in page.calls if c[0] == "set_input_files") == 2

    def test_channels_missing_entry_skipped(self):
        page = FakePage(counters={"div.vertical-cover-wrap": 0})
        _run(set_thumbnail, page, PARAMS["channels"]["THUMBNAIL"],
             paths={"portrait": _EXISTS, "landscape": _EXISTS})
        assert sum(1 for c in page.calls if c[0] == "set_input_files") == 1

    def test_channels_portrait_only_path(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["channels"]["THUMBNAIL"],
             paths={"portrait": _EXISTS})
        entry_clicks = [
            c for c in page.calls if c[0] == "click"
            and "vertical-cover-wrap" in c[1]
        ]
        assert len(entry_clicks) == 1


class TestConfirmList:
    """confirm_selector 列表：多级确认依次执行。"""

    def test_bilibili_two_stage_confirm(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["bilibili"]["THUMBNAIL"],
             thumbnail_path=_EXISTS)
        clicks = [c for c in page.calls if c[0] == "click"]
        assert any("div.button.submit" in c[1] for c in clicks)
        assert any("bcc-button--primary" in c[1] for c in clicks)

    def test_toutiao_three_stage_confirm(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["toutiao"]["THUMBNAIL"],
             thumbnail_path=_EXISTS)
        clicks = [c for c in page.calls if c[0] == "click"]
        assert any("完成裁剪" in c[1] for c in clicks)
        assert any(c[1] == "button:has-text('确定')" for c in clicks)


class TestTriggerCandidates:
    """trigger_candidates：direct_file_first 探测失败后回退触发链（bilibili）。"""

    def test_bilibili_direct_missing_falls_back_to_candidates(self):
        # 直接 file input 不存在 → 逐候选触发 → 弹窗上传
        page = FakePage(counters={
            '.cover-upload input[type="file"], input[accept*="image"]': 0,
            '[data-reporter-id="80"] .cover-empty-pill .add-text': 0,
            '[data-reporter-id="80"] .cover-empty-pill .add-icon': 0,
            '.cover-empty-pill .add-text': 0,
            '.cover-empty-pill .add-icon': 0,
            '.cover-empty-pill': 1,
        })
        _run(set_thumbnail, page, PARAMS["bilibili"]["THUMBNAIL"],
             thumbnail_path=_EXISTS)
        clicks = [c for c in page.calls if c[0] == "click"]
        # 候选链由稳到脆逐级探测, 命中最稳可用候选（本用例中 .cover-empty-pill）
        assert any("cover-empty-pill" in c[1] for c in clicks)
        assert any(c[0] == "set_input_files" for c in page.calls)
        assert any(c[0] == "keyboard.press" for c in page.calls)  # close_escape


class TestCoverRegression:
    """引擎扩展后既有策略回归（A1 已测场景不退化）。"""

    def test_csdn_still_works(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["csdn"]["THUMBNAIL"],
             thumbnail_path=_EXISTS)
        assert any(c[0] == "set_input_files" for c in page.calls)
        assert any("el-button--primary" in c[1] for c in page.calls)

    def test_tencent_video_cover_input_by_id(self):
        page = FakePage()
        _run(upload_cover, page, PARAMS["tencent_video"]["THUMBNAIL"],
             cover_path=_EXISTS, aspect="16:9")
        uploads = [c for c in page.calls if c[0] == "set_input_files"]
        assert len(uploads) == 1
        assert "uploadCoverBtn" in uploads[0][1]

    def test_zhihu_confirm_select(self):
        page = FakePage()
        _run(set_thumbnail, page, PARAMS["zhihu"]["THUMBNAIL"],
             thumbnail_path=_EXISTS)
        clicks = [c for c in page.calls if c[0] == "click"]
        assert any("确认选择" in c[1] for c in clicks)
