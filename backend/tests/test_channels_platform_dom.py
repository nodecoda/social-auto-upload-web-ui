"""视频号(channels) platform.py DOM 交互层契约测试（T37 批次）。

覆盖 impl/channels/platform.py（973 stmts，基线 18%）—— 与
test_channels_publish.py（编排层）/ test_channels_collections_browser.py /
test_channels_search_browser.py（浏览器 helper）互补，目标合并 ~100%：

- 纯函数: _format_short_title（特殊字符保留/逗号→空格/超长截断/不足补空格）
  / _is_login_completed（platform 且非 login） / _parse_cookie_to_storage_state
  （.qq.com 域/7d expires/跳过无效对）
- 上传/填写: _upload_video_file / _fill_title_and_tags（每个 tag 前导 # + Space）
  / _fill_description（空 desc 早返回） / _set_short_title（主/兜底/legacy 选择器）
- 页面设置: _apply_collection（入口缺失/无合集/按名匹配/未匹配/默认选第二个）
  / _apply_location（空值/卡片缺失/搜索框缺失/精确匹配/未匹配/探测异常）
  / _apply_activity（空值/缺失/搜索框缺失/下拉超时/按 name/按 creator/复合兜底/未匹配）
  / _apply_original_statement（简单勾选/条款勾选+声明/高级分类下拉/各探测异常）
- 视频标注: _select_mark_tag_option（入口缺失/已展开/点击展开/未找到/探测异常）
  / _fill_shoot_date_in_dialog（空/非法格式/输入框缺失/同月/翻月/禁用格跳过/未找到）
  / _fill_shoot_region_in_dialog（空/级联缺失/无法展开/逐级选择成功/各级失败/菜单未收起）
  / _confirm_mark_tag_dialog（未找到/命中即点/禁用等待/超时仍点/点击异常/隐藏等待）
  / _fill_shoot_info_dialog（弹窗缺失/成功串联） / _fill_repost_source_dialog
  （弹窗缺失/主/兜底 textarea/未找到输入框/空来源直接确认） / _apply_mark_tag
  （默认无需标注/未选中/自行拍摄/转载/其他）
- 上传等待/封面/发布: _wait_for_upload_complete（已就绪/轮询成功/错误重传/异常继续）
  / _wait_for_cover_ready（无阻塞/等待消失/10s 节流日志/探测异常）
  / _set_thumbnail（无图早返回/竖版/横版 popover/兜底图/重试出弹窗/无入口/无文件输入/
  裁剪异常/确认缺失/悬停异常/popover 异常） / _set_schedule_time（同月/翻月/禁用格）
  / _dismiss_i_know_dialog（命中/未命中/异常） / _submit_publish（草稿/发表/弹窗重发表/
  异常 URL 判定/重试）
- 类方法: login（成功回首页/成功子页导航/导航异常/整体异常 failed/资源清理异常吞掉）
  / check_cookie（文件缺失/有效/失效/内层异常/外层异常） / sync_profile（成功/异常兜底）
  / _scrape_channels_stats（label 映射/千分位/非法数字/超时仍抓/异常空）
  / _login_stats_fn（正常/导航异常/抓取异常） / open_creator_center（线程/事件异常吞掉）
  / publish_video 剩余分支（DRY_RUN 提前 return/wait_for_url 异常/finally 异常吞掉）

fake Playwright page/frame 对象驱动：locator 按选择器分派、filter/nth/locator
子级可独立配置；轮询类函数 patch asyncio.sleep 避免真等待。
"""
import asyncio
import json
import os
import sys
import tempfile
import time as _time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, call, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.channels.platform import (
    _REPOST_TAG,
    _SHOOT_TAG,
    TENCENT_LOGIN_URL,
    TENCENT_MANAGE_URL,
    TENCENT_PLATFORM_URL,
    TENCENT_UPLOAD_URL,
    ChannelsPlatform,
    _apply_activity,
    _apply_collection,
    _apply_location,
    _apply_mark_tag,
    _apply_original_statement,
    _confirm_mark_tag_dialog,
    _dismiss_i_know_dialog,
    _fill_description,
    _fill_repost_source_dialog,
    _fill_shoot_date_in_dialog,
    _fill_shoot_info_dialog,
    _fill_shoot_region_in_dialog,
    _fill_title_and_tags,
    _format_short_title,
    _is_login_completed,
    _select_mark_tag_option,
    _set_schedule_time,
    _set_short_title,
    _set_thumbnail,
    _submit_publish,
    _upload_video_file,
    _wait_for_cover_ready,
    _wait_for_upload_complete,
)

_PLATFORM_HOME = "https://channels.weixin.qq.com/platform"


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return ChannelsPlatform()


class _AutoSubs(dict):
    """dict 缺失键自动注册 _mk_locator（与 locator(sel) 的 setdefault 同对象）。"""

    def __missing__(self, key):
        self[key] = _mk_locator()
        return self[key]


def _mk_leaf():
    """叶子 locator：所有异步方法默认成功；count 默认 0（=元素不存在）。"""
    loc = MagicMock()
    loc.count = AsyncMock(return_value=0)
    loc.click = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.set_input_files = AsyncMock()
    loc.get_attribute = AsyncMock(return_value=None)
    loc.inner_text = AsyncMock(return_value="")
    loc.text_content = AsyncMock(return_value="")
    loc.is_visible = AsyncMock(return_value=True)
    loc.is_disabled = AsyncMock(return_value=False)
    loc.is_checked = AsyncMock(return_value=False)
    loc.check = AsyncMock()
    loc.fill = AsyncMock()
    loc.press = AsyncMock()
    loc.type = AsyncMock()
    loc.evaluate = AsyncMock(return_value="")
    loc.hover = AsyncMock()
    subs = _AutoSubs()
    loc.locator = MagicMock(side_effect=lambda sel, **kw: subs.setdefault(sel, _mk_locator()))
    loc.subs = subs
    filters = _AutoSubs()
    loc.filter = MagicMock(
        side_effect=lambda **kw: filters.setdefault(repr(sorted(kw.items())), _mk_locator())
    )
    loc.filters = filters
    nth_subs = _AutoSubs()
    loc.nth = MagicMock(side_effect=lambda i: nth_subs.setdefault(i, _mk_leaf()))
    loc.nth_subs = nth_subs
    return loc


def _mk_locator():
    loc = _mk_leaf()
    loc.first = _mk_leaf()
    loc.last = _mk_leaf()
    return loc


class _SeqUrlPage(MagicMock):
    """按顺序返回 url 的 page；序列耗尽重复末值。"""

    def __init__(self, urls):
        super().__init__()
        self._url_seq = list(urls)

    @property
    def url(self):
        val = self._url_seq.pop(0) if len(self._url_seq) > 1 else self._url_seq[0]
        return val


def _mk_page(url=TENCENT_UPLOAD_URL, urls=None):
    """通用 fake page：locator 按选择器分派，get_by_text/label/role 独立分派。"""
    if urls is not None:
        page = _SeqUrlPage(urls)
    else:
        page = MagicMock()
        page.url = url
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.mouse = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock(return_value=[])
    page.query_selector_all = AsyncMock(return_value=[])
    page.click = AsyncMock()
    page.inner_text = AsyncMock(return_value="")
    page.on = MagicMock()
    page.close = AsyncMock()
    locators = _AutoSubs()
    page.locator = MagicMock(side_effect=lambda sel, **kw: locators.setdefault(sel, _mk_locator()))
    page.locators = locators
    by_text = _AutoSubs()
    page.get_by_text = MagicMock(
        side_effect=lambda text, exact=False: by_text.setdefault(text, _mk_locator())
    )
    page.by_text = by_text
    by_label = _AutoSubs()
    page.get_by_label = MagicMock(
        side_effect=lambda label: by_label.setdefault(label, _mk_locator())
    )
    page.by_label = by_label
    by_role = _AutoSubs()
    page.get_by_role = MagicMock(
        side_effect=lambda role, name=None, exact=False: by_role.setdefault(
            (role, name, exact), _mk_locator()
        )
    )
    page.by_role = by_role
    return page


def _loc(page, sel):
    """取按选择器分派的 locator（不存在则创建）。"""
    page.locator(sel)
    return page.locators[sel]


def _floc(page, sel, has_text):
    """取 selector.filter(has_text=...) 分派的 locator。"""
    page.locator(sel).filter(has_text=has_text)
    return page.locators[sel].filters[repr(sorted([("has_text", has_text)]))]


@contextmanager
def _no_sleep():
    with patch("asyncio.sleep", AsyncMock()):
        yield


@contextmanager
def _mk_browser_chain(platform, page=None, url=TENCENT_UPLOAD_URL, urls=None):
    """create_browser/create_context 链 mocks（with 内生效）。"""
    if page is None:
        page = _mk_page(url=url, urls=urls)
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.storage_state = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    browser.is_connected = MagicMock(return_value=False)
    with patch.object(platform, "create_browser", AsyncMock(return_value=browser)) as _cb, \
         patch.object(platform, "create_context", AsyncMock(return_value=context)) as _cc:
        yield page, context, browser, _cb, _cc


def _mk_cookie_file(name="t37_channels_cookie.json"):
    d = Path(BASE_DIR) / "cookiesFile"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text("{}", encoding="utf-8")
    return p


def _mk_cover_file(prefix="sau_channels_cover_"):
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".png")
    os.close(fd)
    return path


# ── 纯函数 ────────────────────────────────────────────────────────────────

class TestFormatShortTitle:
    def test_keeps_alnum_and_special(self):
        assert _format_short_title("ABC《》“”:+?%°123") == "ABC《》“”:+?%°123"

    def test_comma_to_space_and_drop_other(self):
        assert _format_short_title("a,b！c") == "a bc  "  # ！被删除, 不足 6 补空格

    def test_truncates_over_16(self):
        out = _format_short_title("中" * 30)
        assert len(out) == 16

    def test_pads_under_6(self):
        out = _format_short_title("ab")
        assert out == "ab    "
        assert len(out) == 6

    def test_empty(self):
        assert _format_short_title("") == "      "


class TestIsLoginCompleted:
    def test_platform_url_true(self):
        page = _mk_page(url=_PLATFORM_HOME)
        assert _run(_is_login_completed(page)) is True

    def test_platform_subpage_true(self):
        page = _mk_page(url=TENCENT_UPLOAD_URL)
        assert _run(_is_login_completed(page)) is True

    def test_login_url_false(self):
        page = _mk_page(url=TENCENT_LOGIN_URL)
        assert _run(_is_login_completed(page)) is False

    def test_unrelated_url_false(self):
        page = _mk_page(url="https://example.com/")
        assert _run(_is_login_completed(page)) is False


class TestParseCookieToStorageState:
    def test_happy_parse(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state("a=1; b = 2")
        assert origins == []
        assert [c["name"] for c in cookies] == ["a", "b"]
        for c in cookies:
            assert c["domain"] == ".qq.com"
            assert c["path"] == "/"
            assert c["httpOnly"] is True
            assert c["secure"] is False
            assert c["sameSite"] == "Lax"
            assert c["expires"] > _time.time()

    def test_skips_invalid_pairs(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state("a=1; ; novalue")
        assert [c["name"] for c in cookies] == ["a"]

    def test_empty(self):
        p = _mk_platform()
        cookies, origins = p._parse_cookie_to_storage_state("")
        assert cookies == []
        assert origins == []

    def test_expires_window(self):
        p = _mk_platform()
        cookies, _ = p._parse_cookie_to_storage_state("a=1")
        delta = cookies[0]["expires"] - _time.time()
        assert 6 * 24 * 3600 < delta < 8 * 24 * 3600


# ── 上传 / 填写 ────────────────────────────────────────────────────────────

class TestUploadVideoFile:
    def test_set_input_files(self):
        page = _mk_page()
        with _no_sleep():
            _run(_upload_video_file(page, "/v/video.mp4"))
        _loc(page, 'input[type="file"]').set_input_files.assert_awaited_once_with("/v/video.mp4")


class TestFillTitleAndTags:
    def test_types_each_tag_with_hash_and_space(self):
        page = _mk_page()
        with _no_sleep():
            _run(_fill_title_and_tags(page, "标题", ["t1", "t2"]))
        _loc(page, "div.input-editor").click.assert_awaited_once()
        assert page.keyboard.type.await_args_list[0].args[0] == "#t1"
        assert page.keyboard.type.await_args_list[1].args[0] == "#t2"
        assert page.keyboard.type.await_args_list[0].kwargs.get("delay") == 30
        assert page.keyboard.press.await_count == 2
        page.keyboard.press.assert_has_awaits([call("Space"), call("Space")])

    def test_no_tags_only_click(self):
        page = _mk_page()
        with _no_sleep():
            _run(_fill_title_and_tags(page, "标题", []))
        _loc(page, "div.input-editor").click.assert_awaited_once()
        assert page.keyboard.type.await_count == 0


class TestFillDescription:
    def test_empty_desc_returns(self):
        page = _mk_page()
        with patch("impl.channels.platform.clear_and_type", AsyncMock()) as ct, _no_sleep():
            _run(_fill_description(page, ""))
        assert not _loc(page, "div.input-editor").click.called
        ct.assert_not_called()

    def test_types_description(self):
        page = _mk_page()
        with patch("impl.channels.platform.clear_and_type", AsyncMock()) as ct, _no_sleep():
            _run(_fill_description(page, "hello 描述"))
        _loc(page, "div.input-editor").click.assert_awaited_once()
        ct.assert_awaited_once_with(page, "hello 描述")


class TestSetShortTitle:
    def test_primary_selector(self):
        page = _mk_page()
        _loc(page, 'input[placeholder*="填写短标题"]').first.count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_set_short_title(page, "标题"))
        _loc(page, 'input[placeholder*="填写短标题"]').first.fill.assert_awaited_once_with("标题    ")

    def test_fallback_selector(self):
        page = _mk_page()
        _loc(page, 'input[placeholder*="短标题"]').first.count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_set_short_title(page, "标题"))
        _loc(page, 'input[placeholder*="短标题"]').first.fill.assert_awaited_once()

    def test_short_title_param_takes_precedence(self):
        page = _mk_page()
        _loc(page, 'input[placeholder*="填写短标题"]').first.count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_set_short_title(page, "长标题", short_title="短"))
        _loc(page, 'input[placeholder*="填写短标题"]').first.fill.assert_awaited_once_with("短")

    def test_legacy_selector(self):
        page = _mk_page()
        legacy = page.by_text["短标题"].subs[".."].subs["xpath=following-sibling::div"] \
            .subs['span input[type="text"]']
        legacy.count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_set_short_title(page, "标题"))
        legacy.fill.assert_awaited_once_with("标题    ")

    def test_legacy_exception_falls_through(self):
        page = _mk_page()
        page.by_text["短标题"].locator = MagicMock(side_effect=RuntimeError("boom"))
        with _no_sleep():
            _run(_set_short_title(page, "标题"))  # 不抛异常,只记日志

    def test_not_found_skips(self):
        page = _mk_page()
        with _no_sleep():
            _run(_set_short_title(page, "标题"))
        assert not _loc(page, 'input[placeholder*="填写短标题"]').first.fill.called

# ── 合集 / 位置 / 活动 / 原创声明 ─────────────────────────────────────────

class TestApplyCollection:
    def test_entry_missing_skips(self):
        page = _mk_page()
        with _no_sleep():
            _run(_apply_collection(page, "合集A"))
        assert not page.by_text["选择合集"].first.click.called

    def test_no_options_skips(self):
        page = _mk_page()
        page.by_text["选择合集"].count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_apply_collection(page, "合集A"))
        page.by_text["选择合集"].first.click.assert_awaited_once()

    def test_match_by_name(self):
        page = _mk_page()
        page.by_text["选择合集"].count = AsyncMock(return_value=1)
        names = _loc(page, ".option-item .item .name")
        names.count = AsyncMock(return_value=3)
        names.nth(0).inner_text = AsyncMock(return_value="合集A")
        names.nth(1).inner_text = AsyncMock(return_value="合集B")
        with _no_sleep():
            _run(_apply_collection(page, "合集B"))
        names.nth(1).locator(
            "xpath=ancestor::div[contains(@class,'option-item')][1]"
        ).first.click.assert_awaited_once()

    def test_name_not_found_warning(self):
        page = _mk_page()
        page.by_text["选择合集"].count = AsyncMock(return_value=1)
        names = _loc(page, ".option-item .item .name")
        names.count = AsyncMock(return_value=1)
        names.nth(0).inner_text = AsyncMock(return_value="合集X")
        with _no_sleep():
            _run(_apply_collection(page, "合集B"))
        assert not names.nth(0).locator(
            "xpath=ancestor::div[contains(@class,'option-item')][1]"
        ).first.click.called

    def test_no_name_picks_second(self):
        page = _mk_page()
        page.by_text["选择合集"].count = AsyncMock(return_value=1)
        names = _loc(page, ".option-item .item .name")
        names.count = AsyncMock(return_value=2)
        with _no_sleep():
            _run(_apply_collection(page))
        names.nth(1).locator(
            "xpath=ancestor::div[contains(@class,'option-item')][1]"
        ).first.click.assert_awaited_once()

    def test_no_name_single_option_no_click(self):
        page = _mk_page()
        page.by_text["选择合集"].count = AsyncMock(return_value=1)
        _loc(page, ".option-item .item .name").count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_apply_collection(page))
        assert not _loc(page, ".option-item .item .name").nth(1).click.called


class TestApplyLocation:
    def test_empty_returns(self):
        page = _mk_page()
        with _no_sleep():
            _run(_apply_location(page, ""))
        assert not _loc(page, "div.position-display-wrap").first.click.called

    def test_wrap_missing_skips(self):
        page = _mk_page()
        with _no_sleep():
            _run(_apply_location(page, "北京"))
        assert not _loc(page, 'input[placeholder="搜索附近位置"]').first.click.called

    def test_search_input_missing_warning(self):
        page = _mk_page()
        _loc(page, "div.position-display-wrap").first.count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_apply_location(page, "北京"))

    def test_match_and_click(self):
        page = _mk_page()
        _loc(page, "div.position-display-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索附近位置"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        options.nth(1).locator(".location-item-info .name").first.count = \
            AsyncMock(return_value=1)
        options.nth(1).locator(".location-item-info .name").first.inner_text = \
            AsyncMock(return_value="北京")
        with patch("impl.channels.platform.clear_and_type", AsyncMock()) as ct, _no_sleep():
            _run(_apply_location(page, "北京"))
        ct.assert_awaited_once_with(page, "北京", delay=50)
        options.nth(1).click.assert_awaited_once()

    def test_name_el_missing_continues(self):
        page = _mk_page()
        _loc(page, "div.position-display-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索附近位置"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        options.nth(1).locator(".location-item-info .name").first.count = \
            AsyncMock(return_value=0)
        with _no_sleep():
            _run(_apply_location(page, "北京"))
        assert not options.nth(1).click.called

    def test_inner_text_exception_continues(self):
        page = _mk_page()
        _loc(page, "div.position-display-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索附近位置"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        options.nth(1).locator(".location-item-info .name").first.count = \
            AsyncMock(return_value=1)
        options.nth(1).locator(".location-item-info .name").first.inner_text = \
            AsyncMock(side_effect=RuntimeError("detach"))
        with _no_sleep():
            _run(_apply_location(page, "北京"))
        assert not options.nth(1).click.called

    def test_not_found_warning(self):
        page = _mk_page()
        _loc(page, "div.position-display-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索附近位置"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        options.nth(1).locator(".location-item-info .name").first.count = \
            AsyncMock(return_value=1)
        options.nth(1).locator(".location-item-info .name").first.inner_text = \
            AsyncMock(return_value="上海")
        with _no_sleep():
            _run(_apply_location(page, "北京"))
        assert not options.nth(1).click.called


class TestApplyActivity:
    def test_empty_returns(self):
        page = _mk_page()
        with _no_sleep():
            _run(_apply_activity(page, ""))
        assert not _loc(page, "div.post-activity-wrap").first.click.called

    def test_wrap_missing_skips(self):
        page = _mk_page()
        with _no_sleep():
            _run(_apply_activity(page, "活动X", "活动X|发起人"))
        assert not _loc(page, 'input[placeholder="搜索活动"]').first.fill.called

    def test_search_input_missing_warning(self):
        page = _mk_page()
        _loc(page, "div.post-activity-wrap").first.count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_apply_activity(page, "活动X"))

    def test_dropdown_timeout_continues(self):
        page = _mk_page()
        _loc(page, "div.post-activity-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索活动"]').first.count = AsyncMock(return_value=1)
        real_option = _loc(
            page, "div.common-option-list-wrap .option-item .activity-item-info .name"
        ).first
        real_option.wait_for = AsyncMock(side_effect=TimeoutError("slow"))
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        options.nth(1).locator(".activity-item-info").first.count = AsyncMock(return_value=1)
        options.nth(1).locator(".activity-item-info").first.locator(".name").first.count = \
            AsyncMock(return_value=1)
        options.nth(1).locator(".activity-item-info").first.locator(".name").first.inner_text = \
            AsyncMock(return_value="活动X")
        with _no_sleep():
            _run(_apply_activity(page, "活动X"))
        options.nth(1).click.assert_awaited_once()

    def test_match_by_name_only(self):
        page = _mk_page()
        _loc(page, "div.post-activity-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索活动"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        options.nth(1).locator(".activity-item-info").first.count = AsyncMock(return_value=1)
        options.nth(1).locator(".activity-item-info").first.locator(".name").first.count = \
            AsyncMock(return_value=1)
        options.nth(1).locator(".activity-item-info").first.locator(".name").first.inner_text = \
            AsyncMock(return_value="活动X")
        with _no_sleep():
            _run(_apply_activity(page, "活动X"))
        options.nth(1).click.assert_awaited_once()

    def test_match_by_creator(self):
        page = _mk_page()
        _loc(page, "div.post-activity-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索活动"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        info = options.nth(1).locator(".activity-item-info").first
        info.count = AsyncMock(return_value=1)
        info.locator(".name").first.count = AsyncMock(return_value=1)
        info.locator(".name").first.inner_text = AsyncMock(return_value="活动X")
        info.locator(".creator-name").first.count = AsyncMock(return_value=1)
        info.locator(".creator-name").first.inner_text = AsyncMock(return_value="发起人")
        with _no_sleep():
            _run(_apply_activity(page, "活动X", "活动X|发起人"))
        options.nth(1).click.assert_awaited_once()

    def test_creator_mismatch_falls_back_to_name(self):
        page = _mk_page()
        _loc(page, "div.post-activity-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索活动"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        info = options.nth(1).locator(".activity-item-info").first
        info.count = AsyncMock(return_value=1)
        info.locator(".name").first.count = AsyncMock(return_value=1)
        info.locator(".name").first.inner_text = AsyncMock(return_value="活动X")
        info.locator(".creator-name").first.count = AsyncMock(return_value=1)
        info.locator(".creator-name").first.inner_text = AsyncMock(return_value="其他人")
        with _no_sleep():
            _run(_apply_activity(page, "活动X", "活动X|发起人"))
        options.nth(1).click.assert_awaited_once()  # 兜底点击 name 匹配项

    def test_creator_inner_text_exception_uses_empty(self):
        page = _mk_page()
        _loc(page, "div.post-activity-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索活动"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        info = options.nth(1).locator(".activity-item-info").first
        info.count = AsyncMock(return_value=1)
        info.locator(".name").first.count = AsyncMock(return_value=1)
        info.locator(".name").first.inner_text = AsyncMock(return_value="活动X")
        info.locator(".creator-name").first.count = AsyncMock(return_value=1)
        info.locator(".creator-name").first.inner_text = \
            AsyncMock(side_effect=RuntimeError("boom"))
        with _no_sleep():
            _run(_apply_activity(page, "活动X", "活动X|发起人"))
        options.nth(1).click.assert_awaited_once()

    def test_info_or_name_missing_continues(self):
        page = _mk_page()
        _loc(page, "div.post-activity-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索活动"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        options.nth(1).locator(".activity-item-info").first.count = AsyncMock(return_value=0)
        with _no_sleep():
            _run(_apply_activity(page, "活动X"))
        assert not options.nth(1).click.called

    def test_not_found_warning(self):
        page = _mk_page()
        _loc(page, "div.post-activity-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索活动"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        options.nth(1).locator(".activity-item-info").first.count = AsyncMock(return_value=1)
        options.nth(1).locator(".activity-item-info").first.locator(".name").first.count = \
            AsyncMock(return_value=1)
        options.nth(1).locator(".activity-item-info").first.locator(".name").first.inner_text = \
            AsyncMock(return_value="其他活动")
        with _no_sleep():
            _run(_apply_activity(page, "活动X"))
        assert not options.nth(1).click.called

    def test_name_el_missing_continues(self):
        page = _mk_page()
        _loc(page, "div.post-activity-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索活动"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        info = options.nth(1).locator(".activity-item-info").first
        info.count = AsyncMock(return_value=1)
        info.locator(".name").first.count = AsyncMock(return_value=0)  # name 元素缺失
        with _no_sleep():
            _run(_apply_activity(page, "活动X"))
        assert not options.nth(1).click.called

    def test_name_inner_text_exception_continues(self):
        page = _mk_page()
        _loc(page, "div.post-activity-wrap").first.count = AsyncMock(return_value=1)
        _loc(page, 'input[placeholder="搜索活动"]').first.count = AsyncMock(return_value=1)
        options = _loc(page, "div.common-option-list-wrap .option-item")
        options.count = AsyncMock(return_value=2)
        info = options.nth(1).locator(".activity-item-info").first
        info.count = AsyncMock(return_value=1)
        info.locator(".name").first.count = AsyncMock(return_value=1)
        info.locator(".name").first.inner_text = AsyncMock(side_effect=RuntimeError("detach"))
        with _no_sleep():
            _run(_apply_activity(page, "活动X"))
        assert not options.nth(1).click.called


class TestApplyOriginalStatement:
    def test_simple_checkbox_only(self):
        page = _mk_page()
        page.by_label["视频为原创"].count = AsyncMock(return_value=1)
        _loc(page, 'label:has-text("我已阅读并同意 《视频号原创声明使用条款》")') \
            .is_visible = AsyncMock(return_value=False)
        with _no_sleep():
            _run(_apply_original_statement(page))
        page.by_label["视频为原创"].check.assert_awaited_once()

    def test_terms_visible_checks_and_declares(self):
        page = _mk_page()
        page.by_label["视频为原创"].count = AsyncMock(return_value=1)
        _loc(page, 'label:has-text("我已阅读并同意 《视频号原创声明使用条款》")') \
            .is_visible = AsyncMock(return_value=True)
        page.by_role[("button", "声明原创", False)].count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_apply_original_statement(page))
        page.by_label["我已阅读并同意 《视频号原创声明使用条款》"].check.assert_awaited_once()
        page.by_role[("button", "声明原创", False)].click.assert_awaited_once()

    def test_label_visible_exception_false(self):
        page = _mk_page()
        _loc(page, 'label:has-text("我已阅读并同意 《视频号原创声明使用条款》")') \
            .is_visible = AsyncMock(side_effect=RuntimeError("boom"))
        terms = page.by_label["我已阅读并同意 《视频号原创声明使用条款》"]
        with _no_sleep():
            _run(_apply_original_statement(page))
        assert not terms.check.called

    def test_advanced_full_flow(self):
        page = _mk_page()
        _loc(page, 'div.label span:has-text("声明原创")').count = AsyncMock(return_value=1)
        checkbox = _loc(page, "div.declare-original-checkbox input.ant-checkbox-input")
        checkbox.is_disabled = AsyncMock(return_value=False)
        checked = _loc(
            page,
            "div.declare-original-dialog "
            "label.ant-checkbox-wrapper.ant-checkbox-wrapper-checked:visible",
        )
        checked.count = AsyncMock(return_value=0)
        original_type_form = _loc(
            page, 'div.original-type-form > div.form-label:has-text("原创类型"):visible'
        )
        original_type_form.count = AsyncMock(return_value=1)
        dropdown_item = _loc(
            page,
            "div.form-content:visible "
            "ul.weui-desktop-dropdown__list "
            'li.weui-desktop-dropdown__list-ele:has-text("科技")',
        )
        dropdown_item.first.count = AsyncMock(return_value=1)
        declare_button = _loc(page, 'button:has-text("声明原创"):visible')
        declare_button.count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_apply_original_statement(page, category="科技"))
        checkbox.click.assert_awaited_once()
        _loc(page, "div.declare-original-dialog input.ant-checkbox-input:visible") \
            .click.assert_awaited_once()
        _loc(page, "div.form-content:visible").click.assert_awaited_once()
        dropdown_item.first.click.assert_awaited_once()
        page.wait_for_timeout.assert_awaited_once_with(1000)
        declare_button.click.assert_awaited_once()

    def test_advanced_checked_already_skips_second_click(self):
        page = _mk_page()
        _loc(page, 'div.label span:has-text("声明原创")').count = AsyncMock(return_value=1)
        _loc(
            page,
            "div.declare-original-dialog "
            "label.ant-checkbox-wrapper.ant-checkbox-wrapper-checked:visible",
        ).count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_apply_original_statement(page, category="科技"))
        _loc(page, "div.declare-original-dialog input.ant-checkbox-input:visible") \
            .click.assert_not_called()

    def test_advanced_checkbox_disabled_skips(self):
        page = _mk_page()
        _loc(page, 'div.label span:has-text("声明原创")').count = AsyncMock(return_value=1)
        _loc(page, "div.declare-original-checkbox input.ant-checkbox-input") \
            .is_disabled = AsyncMock(return_value=True)
        with _no_sleep():
            _run(_apply_original_statement(page, category="科技"))
        _loc(page, "div.declare-original-checkbox input.ant-checkbox-input") \
            .click.assert_not_called()

    def test_advanced_no_type_form_and_no_declare_btn(self):
        page = _mk_page()
        _loc(page, 'div.label span:has-text("声明原创")').count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_apply_original_statement(page, category="科技"))
        assert not _loc(page, "div.form-content:visible").click.called

    def test_no_category_skips_advanced(self):
        page = _mk_page()
        _loc(page, 'div.label span:has-text("声明原创")').count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_apply_original_statement(page, category=None))
        _loc(page, "div.declare-original-checkbox input.ant-checkbox-input") \
            .click.assert_not_called()

# ── 视频标注(mark tag) ────────────────────────────────────────────────────

class TestSelectMarkTagOption:
    def test_entry_missing_false(self):
        page = _mk_page()
        with _no_sleep():
            assert _run(_select_mark_tag_option(page, _SHOOT_TAG)) is False

    def test_already_open_no_display_click(self):
        page = _mk_page()
        _loc(page, ".mark-tag-select").first.count = AsyncMock(return_value=1)
        _loc(page, ".mark-tag-select").first.get_attribute = \
            AsyncMock(return_value="mark-tag-select is-open")
        options = _loc(page, ".mark-tag-options .mark-tag-option")
        options.count = AsyncMock(return_value=1)
        options.nth(0).locator(".option-main").first.inner_text = \
            AsyncMock(return_value=_SHOOT_TAG)
        with _no_sleep():
            assert _run(_select_mark_tag_option(page, _SHOOT_TAG)) is True
        _loc(page, ".mark-tag-select").first.subs[".select-display"].first \
            .click.assert_not_called()
        options.nth(0).click.assert_awaited_once()

    def test_closed_clicks_display(self):
        page = _mk_page()
        _loc(page, ".mark-tag-select").first.count = AsyncMock(return_value=1)
        options = _loc(page, ".mark-tag-options .mark-tag-option")
        options.count = AsyncMock(return_value=1)
        options.nth(0).locator(".option-main").first.inner_text = \
            AsyncMock(return_value=_SHOOT_TAG)
        with _no_sleep():
            assert _run(_select_mark_tag_option(page, _SHOOT_TAG)) is True
        _loc(page, ".mark-tag-select").first.subs[".select-display"].first \
            .click.assert_awaited_once()

    def test_get_attribute_exception_opens(self):
        page = _mk_page()
        _loc(page, ".mark-tag-select").first.count = AsyncMock(return_value=1)
        _loc(page, ".mark-tag-select").first.get_attribute = \
            AsyncMock(side_effect=RuntimeError("boom"))
        options = _loc(page, ".mark-tag-options .mark-tag-option")
        options.count = AsyncMock(return_value=1)
        options.nth(0).locator(".option-main").first.inner_text = \
            AsyncMock(return_value=_SHOOT_TAG)
        with _no_sleep():
            assert _run(_select_mark_tag_option(page, _SHOOT_TAG)) is True
        _loc(page, ".mark-tag-select").first.subs[".select-display"].first \
            .click.assert_awaited_once()

    def test_not_found_false(self):
        page = _mk_page()
        _loc(page, ".mark-tag-select").first.count = AsyncMock(return_value=1)
        options = _loc(page, ".mark-tag-options .mark-tag-option")
        options.count = AsyncMock(return_value=1)
        options.nth(0).locator(".option-main").first.inner_text = \
            AsyncMock(return_value="其他标注")
        with _no_sleep():
            assert _run(_select_mark_tag_option(page, _SHOOT_TAG)) is False

    def test_inner_text_exception_continues(self):
        page = _mk_page()
        _loc(page, ".mark-tag-select").first.count = AsyncMock(return_value=1)
        options = _loc(page, ".mark-tag-options .mark-tag-option")
        options.count = AsyncMock(return_value=2)
        options.nth(0).locator(".option-main").first.inner_text = \
            AsyncMock(side_effect=RuntimeError("detach"))
        options.nth(1).locator(".option-main").first.inner_text = \
            AsyncMock(return_value=_SHOOT_TAG)
        with _no_sleep():
            assert _run(_select_mark_tag_option(page, _SHOOT_TAG)) is True
        options.nth(1).click.assert_awaited_once()


class TestFillShootDateInDialog:
    def test_empty_date_skips(self):
        dialog = _mk_locator()
        with _no_sleep():
            _run(_fill_shoot_date_in_dialog(dialog, ""))
        assert not dialog.subs['input[placeholder="请选择拍摄时间"]'].first.click.called

    def test_invalid_format_warning(self):
        dialog = _mk_locator()
        with _no_sleep():
            _run(_fill_shoot_date_in_dialog(dialog, "2026/08/01"))

    def test_date_input_missing_warning(self):
        dialog = _mk_locator()
        with _no_sleep():
            _run(_fill_shoot_date_in_dialog(dialog, "2026-08-21"))
        assert not dialog.subs["table.weui-desktop-picker__table a"].count.called

    def test_same_month_picks_day(self):
        dialog = _mk_locator()
        dialog.subs['input[placeholder="请选择拍摄时间"]'].first.count = \
            AsyncMock(return_value=1)
        labels = dialog.subs["span.weui-desktop-picker__panel__label"]
        labels.count = AsyncMock(return_value=2)
        labels.nth(0).inner_text = AsyncMock(return_value="2026年")
        labels.nth(1).inner_text = AsyncMock(return_value="08月")
        cells = dialog.subs["table.weui-desktop-picker__table a"]
        cells.count = AsyncMock(return_value=1)
        cells.nth(0).evaluate = AsyncMock(return_value="weui-desktop-picker__date")
        cells.nth(0).inner_text = AsyncMock(return_value="21")
        with _no_sleep():
            _run(_fill_shoot_date_in_dialog(dialog, "2026-08-21"))
        cells.nth(0).click.assert_awaited_once()
        assert not dialog.subs["button.weui-desktop-btn__icon__right"].first.click.called

    def test_navigates_month_then_picks(self):
        dialog = _mk_locator()
        dialog.subs['input[placeholder="请选择拍摄时间"]'].first.count = \
            AsyncMock(return_value=1)
        labels = dialog.subs["span.weui-desktop-picker__panel__label"]
        labels.count = AsyncMock(return_value=2)
        labels.nth(0).inner_text = AsyncMock(side_effect=["2026年", "2026年"])
        labels.nth(1).inner_text = AsyncMock(side_effect=["07月", "08月"])
        dialog.subs["button.weui-desktop-btn__icon__right"].first.count = \
            AsyncMock(return_value=1)
        cells = dialog.subs["table.weui-desktop-picker__table a"]
        cells.count = AsyncMock(return_value=1)
        cells.nth(0).evaluate = AsyncMock(return_value="weui-desktop-picker__date")
        cells.nth(0).inner_text = AsyncMock(return_value="21")
        with _no_sleep():
            _run(_fill_shoot_date_in_dialog(dialog, "2026-08-21"))
        dialog.subs["button.weui-desktop-btn__icon__right"].first.click.assert_awaited_once()
        cells.nth(0).click.assert_awaited_once()

    def test_disabled_cell_skipped(self):
        dialog = _mk_locator()
        dialog.subs['input[placeholder="请选择拍摄时间"]'].first.count = \
            AsyncMock(return_value=1)
        labels = dialog.subs["span.weui-desktop-picker__panel__label"]
        labels.count = AsyncMock(return_value=2)
        labels.nth(0).inner_text = AsyncMock(return_value="2026年")
        labels.nth(1).inner_text = AsyncMock(return_value="08月")
        cells = dialog.subs["table.weui-desktop-picker__table a"]
        cells.count = AsyncMock(return_value=1)
        cells.nth(0).evaluate = AsyncMock(
            return_value="weui-desktop-picker__disabled weui-desktop-picker__date"
        )
        with _no_sleep():
            _run(_fill_shoot_date_in_dialog(dialog, "2026-08-21"))
        assert not cells.nth(0).click.called

    def test_no_matching_day_warning(self):
        dialog = _mk_locator()
        dialog.subs['input[placeholder="请选择拍摄时间"]'].first.count = \
            AsyncMock(return_value=1)
        labels = dialog.subs["span.weui-desktop-picker__panel__label"]
        labels.count = AsyncMock(return_value=2)
        labels.nth(0).inner_text = AsyncMock(return_value="2026年")
        labels.nth(1).inner_text = AsyncMock(return_value="08月")
        cells = dialog.subs["table.weui-desktop-picker__table a"]
        cells.count = AsyncMock(return_value=1)
        cells.nth(0).evaluate = AsyncMock(return_value="weui-desktop-picker__date")
        cells.nth(0).inner_text = AsyncMock(return_value="22")
        with _no_sleep():
            _run(_fill_shoot_date_in_dialog(dialog, "2026-08-21"))
        assert not cells.nth(0).click.called

    def test_label_read_exception_navigates(self):
        dialog = _mk_locator()
        dialog.subs['input[placeholder="请选择拍摄时间"]'].first.count = \
            AsyncMock(return_value=1)
        labels = dialog.subs["span.weui-desktop-picker__panel__label"]
        labels.count = AsyncMock(return_value=2)
        labels.nth(0).inner_text = AsyncMock(side_effect=RuntimeError("detach"))
        dialog.subs["button.weui-desktop-btn__icon__right"].first.count = \
            AsyncMock(return_value=0)  # 翻月按钮缺失 → break
        with _no_sleep():
            _run(_fill_shoot_date_in_dialog(dialog, "2026-08-21"))

    def test_cell_evaluate_exception_continues(self):
        dialog = _mk_locator()
        dialog.subs['input[placeholder="请选择拍摄时间"]'].first.count = \
            AsyncMock(return_value=1)
        labels = dialog.subs["span.weui-desktop-picker__panel__label"]
        labels.count = AsyncMock(return_value=2)
        labels.nth(0).inner_text = AsyncMock(return_value="2026年")
        labels.nth(1).inner_text = AsyncMock(return_value="08月")
        cells = dialog.subs["table.weui-desktop-picker__table a"]
        cells.count = AsyncMock(return_value=1)
        cells.nth(0).evaluate = AsyncMock(side_effect=RuntimeError("boom"))
        with _no_sleep():
            _run(_fill_shoot_date_in_dialog(dialog, "2026-08-21"))
        assert not cells.nth(0).click.called


class TestFillShootRegionInDialog:
    def test_empty_region_skips(self):
        dialog = _mk_locator()
        with _no_sleep():
            _run(_fill_shoot_region_in_dialog(dialog, []))
        assert not dialog.subs[".location-cascader"].first.count.called

    def test_cascader_missing_warning(self):
        dialog = _mk_locator()
        with _no_sleep():
            _run(_fill_shoot_region_in_dialog(dialog, ["中国", "广东"]))

    def test_trigger_click_exception_warning(self):
        dialog = _mk_locator()
        dialog.subs[".location-cascader"].first.count = AsyncMock(return_value=1)
        dialog.subs[".location-cascader"].first.subs[
            ".weui-desktop-form__dropdowncascade__dt__inner-button"
        ].first.click = AsyncMock(side_effect=RuntimeError("boom"))
        with _no_sleep():
            _run(_fill_shoot_region_in_dialog(dialog, ["中国", "广东"]))
        assert dialog.subs[".location-cascader"].first.subs.get(
            ".weui-desktop-dropdown__list-ele__text"
        ) is None

    def test_full_path_success(self):
        dialog = _mk_locator()
        dialog.subs[".location-cascader"].first.count = AsyncMock(return_value=1)
        menu = dialog.subs[".location-cascader"].first.subs[
            ".weui-desktop-dropdown-menu"
        ].first
        menu.count = AsyncMock(return_value=0)
        with _no_sleep():
            _run(_fill_shoot_region_in_dialog(dialog, ["中国", "广东", "深圳"]))
        for name in ("中国", "广东", "深圳"):
            item = dialog.subs[".location-cascader"].first.subs[
                ".weui-desktop-dropdown__list-ele__text"
            ].filters[repr(sorted([("has_text", name)]))].first
            item.wait_for.assert_awaited_once_with(state="visible", timeout=3000)
            item.click.assert_awaited_once()

    def test_level_wait_timeout_warning(self):
        dialog = _mk_locator()
        dialog.subs[".location-cascader"].first.count = AsyncMock(return_value=1)
        item = dialog.subs[".location-cascader"].first.subs[
            ".weui-desktop-dropdown__list-ele__text"
        ].filters[repr(sorted([("has_text", "中国")]))].first
        item.wait_for = AsyncMock(side_effect=TimeoutError("slow"))
        with _no_sleep():
            _run(_fill_shoot_region_in_dialog(dialog, ["中国", "广东"]))
        assert not item.click.called

    def test_level_click_exception_warning(self):
        dialog = _mk_locator()
        dialog.subs[".location-cascader"].first.count = AsyncMock(return_value=1)
        item = dialog.subs[".location-cascader"].first.subs[
            ".weui-desktop-dropdown__list-ele__text"
        ].filters[repr(sorted([("has_text", "中国")]))].first
        item.click = AsyncMock(side_effect=RuntimeError("boom"))
        with _no_sleep():
            _run(_fill_shoot_region_in_dialog(dialog, ["中国", "广东"]))
        assert dialog.subs[".location-cascader"].first.subs.get(
            ".weui-desktop-dropdown-menu"
        ) is None

    def test_menu_still_visible_after_timeout(self):
        dialog = _mk_locator()
        dialog.subs[".location-cascader"].first.count = AsyncMock(return_value=1)
        menu = dialog.subs[".location-cascader"].first.subs[
            ".weui-desktop-dropdown-menu"
        ].first
        menu.count = AsyncMock(return_value=1)
        menu.is_visible = AsyncMock(return_value=True)
        with _no_sleep():
            _run(_fill_shoot_region_in_dialog(dialog, ["中国"]))  # 20 轮后仍可见 → 继续

    def test_menu_probe_exception_returns(self):
        dialog = _mk_locator()
        dialog.subs[".location-cascader"].first.count = AsyncMock(return_value=1)
        menu = dialog.subs[".location-cascader"].first.subs[
            ".weui-desktop-dropdown-menu"
        ].first
        menu.count = AsyncMock(side_effect=RuntimeError("boom"))
        with _no_sleep():
            _run(_fill_shoot_region_in_dialog(dialog, ["中国"]))

class TestConfirmMarkTagDialog:
    _FT = 'div.weui-desktop-dialog__ft button:has-text("完成")'

    def _mk_btn(self, page, selector=_FT, count=1):
        btn = _loc(page, selector).first
        btn.count = AsyncMock(return_value=count)
        btn.is_visible = AsyncMock(return_value=True)
        return btn

    def test_no_button_false(self):
        page = _mk_page()
        with _no_sleep():
            assert _run(_confirm_mark_tag_dialog(page)) is False

    def test_found_enabled_click(self):
        page = _mk_page()
        btn = self._mk_btn(page)
        btn.get_attribute = AsyncMock(return_value="weui-desktop-btn")
        with _no_sleep():
            assert _run(_confirm_mark_tag_dialog(page)) is True
        btn.click.assert_awaited_once()
        _loc(page, "div.weui-desktop-dialog").first.wait_for.assert_awaited_once_with(
            state="hidden", timeout=5000
        )

    def test_disabled_then_enabled(self):
        page = _mk_page()
        btn = self._mk_btn(page)
        btn.get_attribute = AsyncMock(
            side_effect=["weui-desktop-btn_disabled", "weui-desktop-btn"]
        )
        with _no_sleep():
            assert _run(_confirm_mark_tag_dialog(page)) is True
        btn.click.assert_awaited_once()

    def test_still_disabled_after_timeout_still_clicks(self):
        page = _mk_page()
        btn = self._mk_btn(page)
        btn.get_attribute = AsyncMock(return_value="weui-desktop-btn_disabled")
        with _no_sleep():
            assert _run(_confirm_mark_tag_dialog(page)) is True  # else 分支后仍尝试点击
        assert btn.click.await_count == 1

    def test_get_attribute_exception_breaks(self):
        page = _mk_page()
        btn = self._mk_btn(page)
        btn.get_attribute = AsyncMock(side_effect=RuntimeError("boom"))
        with _no_sleep():
            assert _run(_confirm_mark_tag_dialog(page)) is True
        btn.click.assert_awaited_once()

    def test_click_exception_false(self):
        page = _mk_page()
        btn = self._mk_btn(page)
        btn.get_attribute = AsyncMock(return_value="weui-desktop-btn")
        btn.click = AsyncMock(side_effect=RuntimeError("boom"))
        with _no_sleep():
            assert _run(_confirm_mark_tag_dialog(page)) is False

    def test_hidden_wait_exception_still_true(self):
        page = _mk_page()
        btn = self._mk_btn(page)
        btn.get_attribute = AsyncMock(return_value="weui-desktop-btn")
        _loc(page, "div.weui-desktop-dialog").first.wait_for = \
            AsyncMock(side_effect=TimeoutError("slow"))
        with _no_sleep():
            assert _run(_confirm_mark_tag_dialog(page)) is True

    def test_probe_exception_continues_to_next_selector(self):
        page = _mk_page()
        btn1 = _loc(page, self._FT).first
        btn1.count = AsyncMock(side_effect=RuntimeError("boom"))
        btn2 = _loc(page, 'div.weui-desktop-dialog__ft button:has-text("确定")').first
        btn2.count = AsyncMock(return_value=1)
        btn2.is_visible = AsyncMock(return_value=True)
        btn2.get_attribute = AsyncMock(return_value="weui-desktop-btn")
        with _no_sleep():
            assert _run(_confirm_mark_tag_dialog(page)) is True
        btn2.click.assert_awaited_once()

    def test_scope_dialog_used_for_target(self):
        page = _mk_page()
        dialog = _mk_locator()
        dialog.subs[self._FT].first.count = AsyncMock(return_value=1)
        dialog.subs[self._FT].first.is_visible = AsyncMock(return_value=True)
        dialog.subs[self._FT].first.get_attribute = AsyncMock(return_value="weui-desktop-btn")
        with _no_sleep():
            assert _run(_confirm_mark_tag_dialog(page, dialog)) is True
        dialog.subs[self._FT].first.click.assert_awaited_once()
        dialog.wait_for.assert_awaited_once_with(state="hidden", timeout=5000)


class TestFillShootInfoDialog:
    def test_dialog_missing_warning(self):
        page = _mk_page()
        _floc(page, "div.weui-desktop-dialog", "添加拍摄时间和地点").first.wait_for = \
            AsyncMock(side_effect=TimeoutError("no dialog"))
        with _no_sleep(), \
             patch("impl.channels.platform._fill_shoot_date_in_dialog", AsyncMock()) as fd, \
             patch("impl.channels.platform._fill_shoot_region_in_dialog", AsyncMock()) as fr, \
             patch("impl.channels.platform._confirm_mark_tag_dialog", AsyncMock()) as _fc:
            _run(_fill_shoot_info_dialog(page, "2026-08-21", ["中国"]))
        fd.assert_not_called()
        fr.assert_not_called()
        _fc.assert_not_called()

    def test_happy_flow(self):
        page = _mk_page()
        dialog = _floc(page, "div.weui-desktop-dialog", "添加拍摄时间和地点").first
        with _no_sleep(), \
             patch("impl.channels.platform._fill_shoot_date_in_dialog", AsyncMock()) as fd, \
             patch("impl.channels.platform._fill_shoot_region_in_dialog", AsyncMock()) as fr, \
             patch("impl.channels.platform._confirm_mark_tag_dialog", AsyncMock()) as _fc:
            _run(_fill_shoot_info_dialog(page, "2026-08-21", ["中国", "广东"]))
        dialog.wait_for.assert_awaited_once_with(state="visible", timeout=5000)
        fd.assert_awaited_once_with(dialog, "2026-08-21")
        fr.assert_awaited_once_with(dialog, ["中国", "广东"])
        _fc.assert_awaited_once_with(page, dialog)


class TestFillRepostSourceDialog:
    _TA = "textarea.repost-textarea"
    _FT = 'div.weui-desktop-dialog__ft button:has-text("完成")'

    def _mk_dialog(self, page, wait_for_exc=None):
        dialog = _floc(page, "div.weui-desktop-dialog", "添加转载来源").first
        if wait_for_exc is not None:
            dialog.wait_for = AsyncMock(side_effect=wait_for_exc)
        return dialog

    def test_dialog_missing_fallback_missing_warning(self):
        page = _mk_page()
        self._mk_dialog(page, wait_for_exc=TimeoutError("no dialog"))
        with _no_sleep(), \
             patch("impl.channels.platform._confirm_mark_tag_dialog", AsyncMock()) as _fc:
            _run(_fill_repost_source_dialog(page, "来源"))
        _fc.assert_not_called()

    def test_primary_textarea_filled(self):
        page = _mk_page()
        dialog = self._mk_dialog(page)
        ta = dialog.subs[self._TA].first
        ta.count = AsyncMock(return_value=1)
        with _no_sleep(), \
             patch("impl.channels.platform._confirm_mark_tag_dialog", AsyncMock()) as _fc:
            _run(_fill_repost_source_dialog(page, "https://src"))
        ta.click.assert_awaited_once()
        ta.fill.assert_awaited_once_with("")
        ta.type.assert_awaited_once_with("https://src", delay=20)
        _fc.assert_awaited_once_with(page, dialog)

    def test_fallback_textarea(self):
        page = _mk_page()
        dialog = self._mk_dialog(page)
        ta = dialog.subs['textarea[placeholder*="转载来源"]'].first
        ta.count = AsyncMock(return_value=1)
        with _no_sleep(), \
             patch("impl.channels.platform._confirm_mark_tag_dialog", AsyncMock()) as _fc:
            _run(_fill_repost_source_dialog(page, "来源"))
        ta.click.assert_awaited_once()
        _fc.assert_awaited_once()

    def test_no_textarea_warning_confirm_only(self):
        page = _mk_page()
        dialog = self._mk_dialog(page)
        with _no_sleep(), \
             patch("impl.channels.platform._confirm_mark_tag_dialog", AsyncMock()) as _fc:
            _run(_fill_repost_source_dialog(page, "来源"))
        _fc.assert_awaited_once_with(page, dialog)

    def test_textarea_probe_exception_continues(self):
        page = _mk_page()
        dialog = self._mk_dialog(page)
        ta1 = dialog.subs[self._TA].first
        ta1.count = AsyncMock(side_effect=RuntimeError("boom"))
        ta2 = dialog.subs['textarea[placeholder*="转载来源"]'].first
        ta2.count = AsyncMock(return_value=1)
        with _no_sleep(), \
             patch("impl.channels.platform._confirm_mark_tag_dialog", AsyncMock()) as _fc:
            _run(_fill_repost_source_dialog(page, "来源"))
        ta2.click.assert_awaited_once()

    def test_empty_source_direct_confirm(self):
        page = _mk_page()
        dialog = self._mk_dialog(page)
        with _no_sleep(), \
             patch("impl.channels.platform._confirm_mark_tag_dialog", AsyncMock()) as _fc:
            _run(_fill_repost_source_dialog(page, ""))
        _fc.assert_awaited_once_with(page, dialog)
        assert dialog.subs.get(self._TA) is None


class TestApplyMarkTag:
    def test_defaults_to_no_tag_when_empty(self):
        page = _mk_page()
        with _no_sleep(), \
             patch("impl.channels.platform._select_mark_tag_option", AsyncMock(return_value=True)) as sel:
            _run(_apply_mark_tag(page, ""))
        sel.assert_awaited_once_with(page, "无需标注")

    def test_not_selected_returns(self):
        page = _mk_page()
        with _no_sleep(), \
             patch("impl.channels.platform._select_mark_tag_option", AsyncMock(return_value=False)) as _sel, \
             patch("impl.channels.platform._fill_shoot_info_dialog", AsyncMock()) as si:
            _run(_apply_mark_tag(page, _SHOOT_TAG, "2026-08-21", ["中国"]))
        si.assert_not_called()

    def test_shoot_tag_fills_info(self):
        page = _mk_page()
        with _no_sleep(), \
             patch("impl.channels.platform._select_mark_tag_option", AsyncMock(return_value=True)) as sel, \
             patch("impl.channels.platform._fill_shoot_info_dialog", AsyncMock()) as si:
            _run(_apply_mark_tag(page, _SHOOT_TAG, "2026-08-21", ["中国", "广东"]))
        sel.assert_awaited_once_with(page, _SHOOT_TAG)
        si.assert_awaited_once_with(page, "2026-08-21", ["中国", "广东"])

    def test_repost_tag_fills_source(self):
        page = _mk_page()
        with _no_sleep(), \
             patch("impl.channels.platform._select_mark_tag_option", AsyncMock(return_value=True)) as sel, \
             patch("impl.channels.platform._fill_repost_source_dialog", AsyncMock()) as rs:
            _run(_apply_mark_tag(page, _REPOST_TAG, repost_source="来源"))
        sel.assert_awaited_once_with(page, _REPOST_TAG)
        rs.assert_awaited_once_with(page, "来源")

    def test_other_tag_no_dialog(self):
        page = _mk_page()
        with _no_sleep(), \
             patch("impl.channels.platform._select_mark_tag_option", AsyncMock(return_value=True)) as sel, \
             patch("impl.channels.platform._fill_shoot_info_dialog", AsyncMock()) as si, \
             patch("impl.channels.platform._fill_repost_source_dialog", AsyncMock()) as rs:
            _run(_apply_mark_tag(page, "无需标注"))
        sel.assert_awaited_once_with(page, "无需标注")
        si.assert_not_called()
        rs.assert_not_called()


# ── 上传等待 / 封面等待 ───────────────────────────────────────────────────

class TestWaitForUploadComplete:
    def test_already_ready_breaks(self):
        page = _mk_page()
        page.by_role[("button", "发表", False)].get_attribute = \
            AsyncMock(return_value="weui-desktop-btn")
        with _no_sleep(), \
             patch("impl.channels.platform._upload_video_file", AsyncMock()) as up:
            _run(_wait_for_upload_complete(page, "/v.mp4"))
        up.assert_not_called()

    def test_polls_until_ready(self):
        page = _mk_page()
        pub = page.by_role[("button", "发表", False)]
        pub.get_attribute = AsyncMock(
            side_effect=["weui-desktop-btn_disabled", "weui-desktop-btn"]
        )
        with _no_sleep():
            _run(_wait_for_upload_complete(page, "/v.mp4"))
        assert pub.get_attribute.await_count == 2

    def test_upload_error_retries(self):
        page = _mk_page()
        pub = page.by_role[("button", "发表", False)]
        pub.get_attribute = AsyncMock(
            side_effect=["weui-desktop-btn_disabled", "weui-desktop-btn"]
        )
        _loc(page, "div.status-msg.error").count = AsyncMock(return_value=1)
        _loc(page, 'div.media-status-content div.tag-inner:has-text("删除")').count = \
            AsyncMock(return_value=1)
        with _no_sleep(), \
             patch("impl.channels.platform._upload_video_file", AsyncMock()) as up:
            _run(_wait_for_upload_complete(page, "/v.mp4"))
        _loc(page, 'div.media-status-content div.tag-inner:has-text("删除")') \
            .click.assert_awaited_once()
        page.by_role[("button", "删除", True)].click.assert_awaited_once()
        up.assert_awaited_once_with(page, "/v.mp4")

    def test_probe_exception_continues(self):
        page = _mk_page()
        pub = page.by_role[("button", "发表", False)]
        pub.get_attribute = AsyncMock(
            side_effect=[RuntimeError("boom"), "weui-desktop-btn"]
        )
        with _no_sleep():
            _run(_wait_for_upload_complete(page, "/v.mp4"))
        assert pub.get_attribute.await_count == 2


class TestWaitForCoverReady:
    def test_no_blocking_returns(self):
        page = _mk_page()
        with _no_sleep():
            _run(_wait_for_cover_ready(page, action="点击前"))
        _loc(page, "div.weui-desktop-popover__desc").count.assert_awaited_once()

    def test_blocking_then_cleared(self):
        page = _mk_page()
        popover = _loc(page, "div.weui-desktop-popover__desc")
        popover.count = AsyncMock(side_effect=[1, 1])
        popover.nth(0).inner_text = AsyncMock(side_effect=["文件上传中...", "ok"])
        with _no_sleep():
            _run(_wait_for_cover_ready(page, action="点击前"))

    def test_preview_keyword_variant(self):
        page = _mk_page()
        popover = _loc(page, "div.weui-desktop-popover__desc")
        popover.count = AsyncMock(side_effect=[1, 1])
        popover.nth(0).inner_text = AsyncMock(
            side_effect=["预览图生成中，请稍候", "ok"]
        )
        with _no_sleep():
            _run(_wait_for_cover_ready(page))

    def test_throttle_log_every_10s(self):
        page = _mk_page()
        popover = _loc(page, "div.weui-desktop-popover__desc")
        blocking_seq = ["文件上传中..."] * 11 + ["ok"]
        popover.count = AsyncMock(side_effect=[1] * 12)
        popover.nth(0).inner_text = AsyncMock(side_effect=blocking_seq)
        with _no_sleep():
            _run(_wait_for_cover_ready(page, action="hover"))

    def test_inner_text_exception_ignored(self):
        page = _mk_page()
        popover = _loc(page, "div.weui-desktop-popover__desc")
        popover.count = AsyncMock(side_effect=[1, 1])
        popover.nth(0).inner_text = AsyncMock(
            side_effect=[RuntimeError("detach"), "ok"]
        )
        with _no_sleep():
            _run(_wait_for_cover_ready(page))

    def test_count_exception_no_blocking(self):
        page = _mk_page()
        _loc(page, "div.weui-desktop-popover__desc").count = \
            AsyncMock(side_effect=RuntimeError("boom"))
        with _no_sleep():
            _run(_wait_for_cover_ready(page))

    def test_waiting_loop_inner_exception_then_clear(self):
        """等待循环中 inner_text 探测异常 → 视为未阻塞 → 返回。"""
        page = _mk_page()
        popover = _loc(page, "div.weui-desktop-popover__desc")
        popover.count = AsyncMock(side_effect=[1, 1])
        popover.nth(0).inner_text = AsyncMock(
            side_effect=["文件上传中", RuntimeError("detach")]
        )
        with _no_sleep():
            _run(_wait_for_cover_ready(page))

    def test_waiting_loop_count_exception_returns(self):
        """等待循环中 count 探测异常 → still_blocking None → 返回。"""
        page = _mk_page()
        popover = _loc(page, "div.weui-desktop-popover__desc")
        popover.count = AsyncMock(side_effect=[1, RuntimeError("boom")])
        popover.nth(0).inner_text = AsyncMock(return_value="文件上传中")
        with _no_sleep():
            _run(_wait_for_cover_ready(page))

# ── 封面设置 ──────────────────────────────────────────────────────────────

class TestSetThumbnail:
    _VERT = "div.vertical-cover-wrap"
    _HORIZ = "div.horizon-cover-wrap"
    _CONFIRM = 'div.weui-desktop-dialog__ft button.weui-desktop-btn_primary:has-text("确认")'

    def _mk_dialog(self, page, count=1):
        dialog = _floc(page, "div.weui-desktop-dialog", "封面").first
        dialog.count = AsyncMock(return_value=count)
        dialog.is_visible = AsyncMock(return_value=True)
        return dialog

    def _mk_file_input(self, dialog, count=1, selector='.single-cover-uploader-wrap input[type="file"]'):
        fi = dialog.subs[selector].first
        fi.count = AsyncMock(return_value=count)
        return fi

    def _mk_confirm(self, dialog, count=1):
        btn = dialog.subs[self._CONFIRM].first
        btn.count = AsyncMock(return_value=count)
        btn.is_visible = AsyncMock(return_value=True)
        return btn

    def _mk_entry(self, page, selector, count=1):
        entry = _loc(page, selector).first
        entry.count = AsyncMock(return_value=count)
        return entry

    def test_none_returns(self):
        page = _mk_page()
        with _no_sleep(), patch("impl.channels.platform.logger") as logger:
            _run(_set_thumbnail(page, None))
        assert not logger.info.called

    def test_vertical_success(self):
        path = _mk_cover_file("sau_c_v_")
        try:
            page = _mk_page()
            _loc(page, 'div:has(> .label):has-text("封面预览")').first.count = \
                AsyncMock(return_value=1)
            dialog = self._mk_dialog(page)
            fi = self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._VERT)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            fi.set_input_files.assert_awaited_once_with(path)
            _loc(page, self._VERT).first.click.assert_awaited_once()
            _loc(page, self._HORIZ).first.count.assert_called_once()  # 横版入口探测过
        finally:
            os.unlink(path)

    def test_preview_wait_exception_falls_through(self):
        path = _mk_cover_file("sau_c_pv_")
        try:
            page = _mk_page()
            preview = _loc(page, 'div:has(> .label):has-text("封面预览")').first
            preview.count = AsyncMock(return_value=1)
            preview.wait_for = AsyncMock(side_effect=TimeoutError("slow"))
            dialog = self._mk_dialog(page)
            fi = self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._VERT)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            fi.set_input_files.assert_awaited_once_with(path)
        finally:
            os.unlink(path)

    def test_horizontal_with_popover(self):
        path = _mk_cover_file("sau_c_h_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._HORIZ)
            popover = _loc(
                page,
                '.ant-popover .btn-directly-edit button, '
                '.ant-popover button:has-text("直接编辑")',
            ).first
            popover.count = AsyncMock(return_value=1)
            popover.is_visible = AsyncMock(return_value=True)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_landscape_path=path))
            popover.click.assert_awaited_once()
            _loc(page, self._HORIZ).first.click.assert_awaited_once()
        finally:
            os.unlink(path)

    def test_thumbnail_fallback_for_missing_direction(self):
        path = _mk_cover_file("sau_c_fb_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._VERT)
            self._mk_entry(page, self._HORIZ)
            with _no_sleep():
                _run(_set_thumbnail(page, path))  # 无方向图 → 两入口都用兜底图
            fi = dialog.subs['.single-cover-uploader-wrap input[type="file"]'].first
            assert fi.set_input_files.await_count == 2
            assert fi.set_input_files.await_args_list[0].args[0] == path
        finally:
            os.unlink(path)

    def test_no_visible_entries_skips(self):
        path = _mk_cover_file("sau_c_ne_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)  # 弹窗存在但无封面入口 → 不会进入 _do_one_cover
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            assert dialog.subs.get('.single-cover-uploader-wrap input[type="file"]') is None
        finally:
            os.unlink(path)

    def test_entry_without_thumbnail_skipped(self):
        path = _mk_cover_file("sau_c_es_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._VERT)   # vertical 有图
            self._mk_entry(page, self._HORIZ)  # horizontal 无图 → 跳过
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            assert dialog.subs['.single-cover-uploader-wrap input[type="file"]'] \
                .first.set_input_files.await_count == 1
        finally:
            os.unlink(path)

    def test_dialog_appears_after_retries(self):
        path = _mk_cover_file("sau_c_rt_")
        try:
            page = _mk_page()
            dialog = _floc(page, "div.weui-desktop-dialog", "封面").first
            dialog.count = AsyncMock(side_effect=[0, 0, 1])
            dialog.is_visible = AsyncMock(return_value=True)
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._VERT)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            assert _loc(page, self._VERT).first.click.await_count == 3
        finally:
            os.unlink(path)

    def test_file_input_not_found_skips_cover(self):
        path = _mk_cover_file("sau_c_fn_")
        try:
            page = _mk_page()
            _dialog = self._mk_dialog(page)
            self._mk_entry(page, self._VERT)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            # 弹窗内 4 个 file input 选择器都探测过 + page 级兜底探测 → 均未命中 → 跳过
            fallback = _loc(page, "div.weui-desktop-dialog input[type='file']").first
            assert fallback.count.await_count == 1
            assert fallback.set_input_files.await_count == 0
        finally:
            os.unlink(path)

    def test_file_input_page_fallback(self):
        path = _mk_cover_file("sau_c_pf_")
        try:
            page = _mk_page()
            _dialog = self._mk_dialog(page)
            self._mk_entry(page, self._VERT)
            page_fi = _loc(page, "div.weui-desktop-dialog input[type='file']").first
            page_fi.count = AsyncMock(return_value=1)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            page_fi.set_input_files.assert_awaited_once_with(path)
        finally:
            os.unlink(path)

    def test_crop_error_swallowed(self):
        path = _mk_cover_file("sau_c_ce_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._VERT)
            crop = _floc(page, "div.weui-desktop-dialog", "裁剪封面图").first
            crop.count = AsyncMock(return_value=1)
            crop.wait_for = AsyncMock(side_effect=TimeoutError("slow"))
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            dialog.subs[self._CONFIRM].first.click.assert_awaited_once()
        finally:
            os.unlink(path)

    def test_crop_confirm_clicked(self):
        path = _mk_cover_file("sau_c_cc_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._VERT)
            crop = _floc(page, "div.weui-desktop-dialog", "裁剪封面图").first
            crop.count = AsyncMock(return_value=1)
            crop_btn = crop.subs[
                'div.weui-desktop-dialog__ft button.weui-desktop-btn_primary:has-text("确定")'
            ].first
            crop_btn.count = AsyncMock(return_value=1)
            crop_btn.is_visible = AsyncMock(return_value=True)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            crop_btn.click.assert_awaited_once()
        finally:
            os.unlink(path)

    def test_confirm_not_found_warning(self):
        path = _mk_cover_file("sau_c_cn_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_entry(page, self._VERT)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            assert dialog.subs[self._CONFIRM].first.click.call_count == 0
        finally:
            os.unlink(path)

    def test_hover_exception_swallowed(self):
        path = _mk_cover_file("sau_c_hv_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            entry = self._mk_entry(page, self._VERT)
            entry.hover = AsyncMock(side_effect=RuntimeError("boom"))
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            entry.click.assert_awaited_once()
        finally:
            os.unlink(path)

    def test_popover_exception_swallowed(self):
        path = _mk_cover_file("sau_c_pe_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._HORIZ)
            popover = _loc(
                page,
                '.ant-popover .btn-directly-edit button, '
                '.ant-popover button:has-text("直接编辑")',
            ).first
            popover.count = AsyncMock(side_effect=RuntimeError("boom"))
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_landscape_path=path))
            dialog.subs[self._CONFIRM].first.click.assert_awaited_once()
        finally:
            os.unlink(path)

    def test_dialog_probe_exception_continues(self):
        """_find_cover_dialog 第一个文本探测异常 → 继续下一个选择器。"""
        path = _mk_cover_file("sau_c_dpe_")
        try:
            page = _mk_page()
            _floc(page, "div.weui-desktop-dialog", "编辑个人主页卡片").first.count = \
                AsyncMock(side_effect=RuntimeError("boom"))
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._VERT)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            dialog.subs[self._CONFIRM].first.click.assert_awaited_once()
        finally:
            os.unlink(path)

    def test_dialog_fallback_probe_exception(self):
        """封面对话框选择器全 miss + 兜底探测异常 → 重试后命中。"""
        path = _mk_cover_file("sau_c_fpe_")
        try:
            page = _mk_page()
            dialog = _floc(page, "div.weui-desktop-dialog", "封面").first
            dialog.count = AsyncMock(side_effect=[0, 1])
            dialog.is_visible = AsyncMock(return_value=True)
            _loc(page, "div.weui-desktop-dialog").first.count = \
                AsyncMock(side_effect=RuntimeError("boom"))
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._VERT)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            assert _loc(page, self._VERT).first.click.await_count == 2
        finally:
            os.unlink(path)

    def test_dialog_fallback_match_used(self):
        """四个封面文本选择器全 miss → 兜底第一个可见 dialog 被采用。"""
        path = _mk_cover_file("sau_c_fbm_")
        try:
            page = _mk_page()
            _dialog = self._mk_dialog(page, count=0)  # 「封面」文本不命中
            fallback = _loc(page, "div.weui-desktop-dialog").first
            fallback.count = AsyncMock(return_value=1)
            fallback.is_visible = AsyncMock(return_value=True)
            self._mk_file_input(fallback)
            self._mk_confirm(fallback)
            self._mk_entry(page, self._VERT)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            fallback.subs[self._CONFIRM].first.click.assert_awaited_once()
        finally:
            os.unlink(path)

    def test_click_retry_exception(self):
        """封面入口 click 抛异常 → 重试后命中弹窗。"""
        path = _mk_cover_file("sau_c_cre_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            entry = self._mk_entry(page, self._VERT)
            entry.click = AsyncMock(side_effect=[RuntimeError("boom"), None])
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            assert entry.click.await_count == 2
        finally:
            os.unlink(path)

    def test_file_input_probe_exception_continues(self):
        """弹窗内第一个 file input 选择器探测异常 → 继续下一个。"""
        path = _mk_cover_file("sau_c_fipe_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            fi1 = dialog.subs['.single-cover-uploader-wrap input[type="file"]'].first
            fi1.count = AsyncMock(side_effect=RuntimeError("boom"))
            fi2 = dialog.subs['input[type="file"][accept*="image"]'].first
            fi2.count = AsyncMock(return_value=1)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._VERT)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            fi2.set_input_files.assert_awaited_once_with(path)
        finally:
            os.unlink(path)

    def test_page_fallback_probe_exception_returns(self):
        """page 级 file input 兜底探测异常 → 直接跳过封面。"""
        path = _mk_cover_file("sau_c_pfpe_")
        try:
            page = _mk_page()
            _dialog = self._mk_dialog(page)
            self._mk_entry(page, self._VERT)
            page_fi = _loc(page, "div.weui-desktop-dialog input[type='file']").first
            page_fi.count = AsyncMock(side_effect=RuntimeError("boom"))
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            assert page_fi.set_input_files.await_count == 0
        finally:
            os.unlink(path)

    def test_crop_confirm_probe_exception_continues(self):
        """裁剪确认按钮探测异常 → 继续下一个按钮选择器。"""
        path = _mk_cover_file("sau_c_cpc_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_confirm(dialog)
            self._mk_entry(page, self._VERT)
            crop = _floc(page, "div.weui-desktop-dialog", "裁剪封面图").first
            crop.count = AsyncMock(return_value=1)
            crop_btn1 = crop.subs[
                'div.weui-desktop-dialog__ft button.weui-desktop-btn_primary:has-text("确定")'
            ].first
            crop_btn1.count = AsyncMock(side_effect=RuntimeError("boom"))
            crop_btn2 = crop.subs['button:has-text("确定")'].first
            crop_btn2.count = AsyncMock(return_value=1)
            crop_btn2.is_visible = AsyncMock(return_value=True)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            crop_btn2.click.assert_awaited_once()
        finally:
            os.unlink(path)

    def test_confirm_probe_exception_continues(self):
        """封面确认按钮探测异常 → 继续下一个确认按钮选择器。"""
        path = _mk_cover_file("sau_c_cnpe_")
        try:
            page = _mk_page()
            dialog = self._mk_dialog(page)
            self._mk_file_input(dialog)
            self._mk_entry(page, self._VERT)
            btn1 = dialog.subs[self._CONFIRM].first
            btn1.count = AsyncMock(side_effect=RuntimeError("boom"))
            btn2 = dialog.subs['div.weui-desktop-dialog__ft button:has-text("确认")'].first
            btn2.count = AsyncMock(return_value=1)
            btn2.is_visible = AsyncMock(return_value=True)
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            btn2.click.assert_awaited_once()
        finally:
            os.unlink(path)

    def test_entry_wait_exception_skips(self):
        """封面入口 wait_for visible 异常 → 跳过该入口。"""
        path = _mk_cover_file("sau_c_ewe_")
        try:
            page = _mk_page()
            self._mk_dialog(page)
            entry = self._mk_entry(page, self._VERT)
            entry.wait_for = AsyncMock(side_effect=TimeoutError("slow"))
            with _no_sleep():
                _run(_set_thumbnail(page, None, thumbnail_portrait_path=path))
            assert not entry.click.called  # 入口不可见 → 未处理
        finally:
            os.unlink(path)


# ── 定时发布 / 弹窗关闭 / 提交 ────────────────────────────────────────────

class TestSetScheduleTime:
    _DT = datetime(2026, 8, 21, 10, 5, tzinfo=ZoneInfo("Asia/Shanghai"))

    def _mk_elements(self, page, texts):
        els = []
        for cls, text in texts:
            el = MagicMock()
            el.evaluate = AsyncMock(return_value=cls)
            el.inner_text = AsyncMock(return_value=text)
            el.click = AsyncMock()
            els.append(el)
        page.query_selector_all = AsyncMock(return_value=els)
        return els

    def test_same_month_flow(self):
        page = _mk_page()
        page.inner_text = AsyncMock(return_value="08月")
        els = self._mk_elements(page, [
            ("weui-desktop-picker__disabled weui-desktop-picker__date", "20"),
            ("weui-desktop-picker__date", "21"),
        ])
        with _no_sleep():
            _run(_set_schedule_time(page, self._DT))
        page.locator("label").filter(has_text="定时").nth(1).click.assert_awaited_once()
        page.click.assert_any_await("input[placeholder=\"请选择发表时间\"]")
        assert "button.weui-desktop-btn__icon__right" not in \
            [c.args[0] for c in page.click.await_args_list]
        els[0].click.assert_not_called()
        els[1].click.assert_awaited_once()
        page.keyboard.press.assert_has_awaits([call("Control+KeyA"), call("Delete")])
        page.keyboard.type.assert_awaited_once_with("10:05")
        _loc(page, "div.input-editor").click.assert_awaited_once()

    def test_different_month_clicks_next(self):
        page = _mk_page()
        page.inner_text = AsyncMock(return_value="07月")
        els = self._mk_elements(page, [("weui-desktop-picker__date", "21")])
        with _no_sleep():
            _run(_set_schedule_time(page, self._DT))
        assert "button.weui-desktop-btn__icon__right" in \
            [c.args[0] for c in page.click.await_args_list]
        els[0].click.assert_awaited_once()

    def test_no_matching_day_no_click(self):
        page = _mk_page()
        page.inner_text = AsyncMock(return_value="08月")
        els = self._mk_elements(page, [("weui-desktop-picker__date", "30")])
        with _no_sleep():
            _run(_set_schedule_time(page, self._DT))
        assert not els[0].click.called


class TestDismissIKnowDialog:
    def test_found_clicked(self):
        page = _mk_page()
        btn = _loc(page, 'div.weui-desktop-dialog button:has-text("我知道了")').first
        btn.count = AsyncMock(return_value=1)
        with _no_sleep():
            assert _run(_dismiss_i_know_dialog(page)) is True
        btn.click.assert_awaited_once()

    def test_not_found_false(self):
        page = _mk_page()
        with _no_sleep():
            assert _run(_dismiss_i_know_dialog(page)) is False

    def test_probe_exception_continues(self):
        page = _mk_page()
        btn = _loc(page, 'div.weui-desktop-dialog button:has-text("我知道了")').first
        btn.count = AsyncMock(side_effect=RuntimeError("boom"))
        with _no_sleep():
            assert _run(_dismiss_i_know_dialog(page)) is False


class TestSubmitPublish:
    def test_draft_with_button(self):
        page = _mk_page()
        draft = _loc(page, 'div.form-btns button:has-text("保存草稿")')
        draft.count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_submit_publish(page, is_draft=True))
        draft.click.assert_awaited_once()
        page.wait_for_url.assert_awaited_once_with("**/post/list**", timeout=30000)

    def test_draft_without_button(self):
        page = _mk_page()
        with _no_sleep():
            _run(_submit_publish(page, is_draft=True))
        assert not _loc(page, 'div.form-btns button:has-text("保存草稿")').click.called
        page.wait_for_url.assert_awaited_once_with("**/post/list**", timeout=30000)

    def test_draft_exception_url_break(self):
        page = _mk_page(url="https://channels.weixin.qq.com/platform/post/list")
        page.wait_for_url = AsyncMock(side_effect=TimeoutError("slow"))
        with _no_sleep():
            _run(_submit_publish(page, is_draft=True))  # url 含 post/list → break

    def test_draft_exception_retries(self):
        page = _mk_page()
        page.wait_for_url = AsyncMock(side_effect=[TimeoutError("slow"), None])
        with _no_sleep():
            _run(_submit_publish(page, is_draft=True))
        assert page.wait_for_url.await_count == 2

    def test_publish_normal(self):
        page = _mk_page()
        pub = _loc(page, 'div.form-btns button:has-text("发表")')
        pub.count = AsyncMock(return_value=1)
        with _no_sleep():
            _run(_submit_publish(page))
        pub.click.assert_awaited_once()
        page.wait_for_url.assert_awaited_once_with(TENCENT_MANAGE_URL, timeout=30000)

    def test_publish_with_iknow_dialog_reclicks(self):
        page = _mk_page()
        pub = _loc(page, 'div.form-btns button:has-text("发表")')
        pub.count = AsyncMock(return_value=1)
        with _no_sleep(), \
             patch("impl.channels.platform._dismiss_i_know_dialog",
                   AsyncMock(return_value=True)):
            _run(_submit_publish(page))
        assert pub.click.await_count == 2  # 弹窗关掉后再次点击发表

    def test_publish_exception_retries_then_success(self):
        page = _mk_page(url=TENCENT_UPLOAD_URL)  # 非 manage URL → 重试
        page.wait_for_url = AsyncMock(side_effect=[TimeoutError("slow"), None])
        with _no_sleep():
            _run(_submit_publish(page))
        assert page.wait_for_url.await_count == 2

    def test_publish_exception_url_break(self):
        page = _mk_page(url=TENCENT_MANAGE_URL)
        page.wait_for_url = AsyncMock(side_effect=TimeoutError("slow"))
        with _no_sleep():
            _run(_submit_publish(page))  # url 已是 manage → break
        assert page.wait_for_url.await_count == 1

# ── 类方法: login / check_cookie / sync_profile / stats ───────────────────

class TestLogin:
    def test_success_lands_on_home(self):
        p = _mk_platform()
        queue = MagicMock()
        with _mk_browser_chain(
            p, urls=[TENCENT_LOGIN_URL, _PLATFORM_HOME]
        ) as (page, context, browser, _cb, _cc), \
             patch("impl.channels.platform.save_login_result", AsyncMock()) as save, \
             _no_sleep():
            _run(p.login("acc1", queue, account_id="acc1"))
        save.assert_awaited_once()
        args = save.await_args.args
        kwargs = save.await_args.kwargs
        assert args[0] is context
        assert args[1] is page
        assert kwargs["platform_id"] == 2
        assert kwargs["platform_name"] == "视频号"
        assert kwargs["status_queue"] is queue
        assert kwargs["account_id"] == "acc1"
        assert kwargs["stats_fn"].__func__ is ChannelsPlatform._login_stats_fn
        page.goto.assert_awaited_once_with(TENCENT_LOGIN_URL)
        browser.close.assert_called_once()
        context.close.assert_called_once()

    def test_success_subpage_navigates_home(self):
        p = _mk_platform()
        with _mk_browser_chain(
            p, urls=[TENCENT_LOGIN_URL, TENCENT_UPLOAD_URL]
        ) as (page, _context, _browser, _cb, _cc), \
             patch("impl.channels.platform.save_login_result", AsyncMock()) as save, \
             _no_sleep():
            _run(p.login("acc1", MagicMock()))
        save.assert_awaited_once()
        page.goto.assert_any_await(TENCENT_PLATFORM_URL, timeout=15000)

    def test_nav_home_exception_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(
            p, urls=[TENCENT_LOGIN_URL, TENCENT_UPLOAD_URL]
        ) as (page, _context, browser, _cb, _cc), \
             patch("impl.channels.platform.save_login_result", AsyncMock()) as save, \
             _no_sleep():
            page.goto = AsyncMock(
                side_effect=[None, RuntimeError("nav boom")]  # login 页 ok, 回首页失败
            )
            _run(p.login("acc1", MagicMock()))
        save.assert_awaited_once()  # 导航失败仍继续抓取
        browser.close.assert_called_once()

    def test_polls_until_completed(self):
        p = _mk_platform()
        with _mk_browser_chain(
            p, urls=[TENCENT_LOGIN_URL, TENCENT_LOGIN_URL, _PLATFORM_HOME]
        ) as (_page, _context, _browser, _cb, _cc), \
             patch("impl.channels.platform.save_login_result", AsyncMock()) as save, \
             patch("asyncio.sleep", AsyncMock()) as sleep:
            _run(p.login("acc1", MagicMock()))
        assert sleep.await_count >= 2  # 前两轮未登录 → sleep 轮询
        save.assert_awaited_once()

    def test_error_puts_failed_status(self):
        p = _mk_platform()
        queue = MagicMock()
        with _mk_browser_chain(p, urls=[TENCENT_LOGIN_URL, _PLATFORM_HOME]) \
                as (_page, _context, browser, _cb, _cc), \
             patch("impl.channels.platform.save_login_result",
                   AsyncMock(side_effect=RuntimeError("boom"))), \
             _no_sleep():
            _run(p.login("acc1", queue))
        assert queue.put.call_count == 1
        payload = json.loads(queue.put.call_args[0][0])
        assert payload["status"] == "failed"
        assert "boom" in payload["message"]
        browser.close.assert_not_called()  # 失败不关浏览器,留现场

    def test_context_close_exception_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p, urls=[TENCENT_LOGIN_URL, _PLATFORM_HOME]) \
                as (_page, context, browser, _cb, _cc), \
             patch("impl.channels.platform.save_login_result", AsyncMock()), \
             _no_sleep():
            context.close = AsyncMock(side_effect=RuntimeError("close boom"))
            _run(p.login("acc1", MagicMock()))  # 不抛异常
        browser.close.assert_called_once()

    def test_browser_close_exception_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p, urls=[TENCENT_LOGIN_URL, _PLATFORM_HOME]) \
                as (_page, _context, browser, _cb, _cc), \
             patch("impl.channels.platform.save_login_result", AsyncMock()), \
             _no_sleep():
            browser.close = AsyncMock(side_effect=RuntimeError("close boom"))
            _run(p.login("acc1", MagicMock()))  # 不抛异常


class TestCheckCookie:
    def test_file_missing_false(self):
        p = _mk_platform()
        with patch.object(p, "create_browser", AsyncMock()) as cb:
            assert _run(p.check_cookie("no_such_cookie_file.json")) is False
            cb.assert_not_called()

    def test_valid_cookie_true(self):
        p = _mk_platform()
        cookie = _mk_cookie_file("t37_cc_valid.json")
        try:
            with _mk_browser_chain(p, url=_PLATFORM_HOME) \
                    as (page, context, browser, _cb, cc), _no_sleep():
                assert _run(p.check_cookie(cookie.name)) is True
            cc.assert_awaited_once_with(browser, storage_state=str(cookie))
            page.goto.assert_awaited_once_with(
                _PLATFORM_HOME, wait_until="domcontentloaded"
            )
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_redirected_to_login_false(self):
        p = _mk_platform()
        cookie = _mk_cookie_file("t37_cc_login.json")
        try:
            with _mk_browser_chain(p, url="https://channels.weixin.qq.com/login.html") \
                    as (_page, _context, browser, _cb, _cc), _no_sleep():
                assert _run(p.check_cookie(cookie.name)) is False
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_inner_exception_false(self):
        p = _mk_platform()
        cookie = _mk_cookie_file("t37_cc_inner.json")
        try:
            with _mk_browser_chain(p) as (page, context, browser, _cb, _cc), _no_sleep():
                page.goto = AsyncMock(side_effect=RuntimeError("goto boom"))
                assert _run(p.check_cookie(cookie.name)) is False
            context.close.assert_awaited_once()
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_outer_exception_false(self):
        p = _mk_platform()
        cookie = _mk_cookie_file("t37_cc_outer.json")
        browser = MagicMock()
        browser.close = AsyncMock()
        try:
            with patch.object(p, "create_browser", AsyncMock(return_value=browser)) as _cb, \
                 patch.object(p, "create_context",
                              AsyncMock(side_effect=RuntimeError("ctx boom"))), \
                 _no_sleep():
                assert _run(p.check_cookie(cookie.name)) is False
            browser.close.assert_awaited_once()
        finally:
            cookie.unlink(missing_ok=True)


class TestSyncProfile:
    def test_success(self):
        p = _mk_platform()
        stats = [{"ICON": "video", "COUNT": 11, "NAME": "视频", "SORT": 1}]
        with _mk_browser_chain(p, url=_PLATFORM_HOME) \
                as (page, context, browser, _cb, _cc), \
             patch("impl.channels.platform.scrape_tencent_profile",
                   AsyncMock(return_value=("昵称", "avatar.png"))), \
             patch.object(p, "_scrape_channels_stats", AsyncMock(return_value=stats)):
            result = _run(p.sync_profile("t37_sync.json"))
        assert result == {"name": "昵称", "avatar": "avatar.png", "stats": stats}
        page.goto.assert_awaited_once_with(TENCENT_PLATFORM_URL)
        page.close.assert_awaited_once()
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()

    def test_exception_returns_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser, _cb, _cc), \
             patch("impl.channels.platform.scrape_tencent_profile",
                   AsyncMock(side_effect=RuntimeError("boom"))):
            result = _run(p.sync_profile("t37_sync2.json"))
        assert result == {"name": "", "avatar": "", "stats": []}

    def test_browser_close_exception_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, browser, _cb, _cc), \
             patch("impl.channels.platform.scrape_tencent_profile",
                   AsyncMock(return_value=("n", "a"))), \
             patch.object(p, "_scrape_channels_stats", AsyncMock(return_value=[])):
            browser.close = AsyncMock(side_effect=RuntimeError("boom"))
            result = _run(p.sync_profile("t37_sync3.json"))
        assert result["name"] == "n"


class TestScrapeChannelsStats:
    _RAW: ClassVar[list] = [
        {"label": "视频", "num": "11"},
        {"label": "关注者", "num": "2"},
        {"label": "未知", "num": "9"},
    ]

    def test_happy_mapping_and_sort(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=self._RAW)
        with _no_sleep():
            stats = _run(p._scrape_channels_stats(page))
        assert stats == [
            {"ICON": "video", "COUNT": 11, "NAME": "视频", "SORT": 1},
            {"ICON": "follow", "COUNT": 2, "NAME": "关注者", "SORT": 2},
        ]
        page.wait_for_selector.assert_awaited_once_with(".finder-info-num", timeout=8000)

    def test_thousands_separator_and_invalid(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[
            {"label": "视频", "num": "1,234"},
            {"label": "关注者", "num": "abc"},
        ])
        with _no_sleep():
            stats = _run(p._scrape_channels_stats(page))
        assert stats[0]["COUNT"] == 1234
        assert stats[1]["COUNT"] == 0

    def test_selector_timeout_still_scrapes(self):
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError("slow"))
        page.evaluate = AsyncMock(return_value=self._RAW)
        with _no_sleep():
            stats = _run(p._scrape_channels_stats(page))
        assert len(stats) == 2

    def test_evaluate_exception_empty(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError("boom"))
        with _no_sleep():
            assert _run(p._scrape_channels_stats(page)) == []

    def test_empty_raw(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=[])
        with _no_sleep():
            assert _run(p._scrape_channels_stats(page)) == []


class TestLoginStatsFn:
    def test_success(self):
        p = _mk_platform()
        stats = [{"ICON": "video", "COUNT": 1, "NAME": "视频", "SORT": 1}]
        page = _mk_page()
        with patch.object(p, "_scrape_channels_stats", AsyncMock(return_value=stats)), \
             _no_sleep():
            assert _run(p._login_stats_fn(page, "acc1")) == stats
        page.goto.assert_awaited_once_with(TENCENT_PLATFORM_URL, timeout=15000)

    def test_goto_exception_swallowed(self):
        p = _mk_platform()
        stats = [{"ICON": "video", "COUNT": 1, "NAME": "视频", "SORT": 1}]
        page = _mk_page()
        page.goto = AsyncMock(side_effect=RuntimeError("boom"))
        with patch.object(p, "_scrape_channels_stats", AsyncMock(return_value=stats)), \
             _no_sleep():
            assert _run(p._login_stats_fn(page, "acc1")) == stats

    def test_scrape_exception_empty(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, "_scrape_channels_stats",
                          AsyncMock(side_effect=RuntimeError("boom"))), _no_sleep():
            assert _run(p._login_stats_fn(page, "acc1")) == []


class TestOpenCreatorCenter:
    def test_starts_thread(self):
        p = _mk_platform()
        cookie = _mk_cookie_file("t37_occ1.json")
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch("impl.channels.platform.create_browser_sync",
                       return_value=browser) as cbs, \
                 patch("impl.channels.platform.create_context_sync",
                       return_value=context) as ccs, \
                 patch("impl.channels.platform.logger"):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            cbs.assert_called_once_with(headless=False)
            ccs.assert_called_once_with(browser, storage_state=str(cookie))
            page.goto.assert_called_once_with(_PLATFORM_HOME)
            page.wait_for_event.assert_called_once_with("close", timeout=0)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_wait_event_error_swallowed(self):
        p = _mk_platform()
        cookie = _mk_cookie_file("t37_occ2.json")
        browser = MagicMock()
        browser.close = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError("boom"))
        context.new_page = MagicMock(return_value=page)
        try:
            with patch("impl.channels.platform.create_browser_sync",
                       return_value=browser), \
                 patch("impl.channels.platform.create_context_sync",
                       return_value=context), \
                 patch("impl.channels.platform.logger"):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)

    def test_browser_close_error_swallowed(self):
        p = _mk_platform()
        cookie = _mk_cookie_file("t37_occ3.json")
        browser = MagicMock()
        browser.close = MagicMock(side_effect=RuntimeError("boom"))
        context = MagicMock()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        context.new_page = MagicMock(return_value=page)
        try:
            with patch("impl.channels.platform.create_browser_sync",
                       return_value=browser), \
                 patch("impl.channels.platform.create_context_sync",
                       return_value=context), \
                 patch("impl.channels.platform.logger"):
                _run(p.open_creator_center(cookie.name))
                for _ in range(200):
                    if browser.close.called:
                        break
                    _time.sleep(0.02)
            browser.close.assert_called_once()
        finally:
            cookie.unlink(missing_ok=True)


# ── publish_video 剩余分支（DRY_RUN / wait_for_url 异常 / finally 异常） ────

class TestPublishVideoRemaining:
    _HELPERS: ClassVar[list] = [
        "_upload_video_file", "_fill_description", "_fill_title_and_tags",
        "_apply_collection", "_apply_location", "_apply_activity",
        "_apply_original_statement", "_apply_mark_tag", "_wait_for_upload_complete",
        "_set_thumbnail", "_set_schedule_time", "_set_short_title", "_submit_publish",
    ]

    def _run(self, platform, browser, context, page, dry_run=False,
             close_browser_exc=None, **kwargs):
        helper_mocks = {name: AsyncMock() for name in self._HELPERS}
        close_browser = AsyncMock(side_effect=close_browser_exc)
        patches = [
            patch("impl.channels.platform." + name, helper_mocks[name])
            for name in self._HELPERS
        ]
        patches += [
            patch.object(platform, "create_browser", AsyncMock(return_value=browser)),
            patch.object(platform, "create_context", AsyncMock(return_value=context)),
            patch.object(platform, "close_browser", close_browser),
        ]
        pst = MagicMock(return_value=[
            datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        ] * max(len(kwargs.get("files") or []), 1))
        for p in patches:
            p.start()
        try:
            with patch("impl.channels.platform.parse_schedule_time", pst), \
                 patch("impl.channels.platform.get_account_name_by_cookie_file",
                       return_value="昵称"), \
                 patch("impl.channels.platform.bind_account_name", MagicMock()), \
                 patch("impl.channels.platform._PUBLISH_DRY_RUN", dry_run), \
                 _no_sleep():
                result = platform.publish_video(**kwargs)
        finally:
            for p in patches:
                p.stop()
        return result, helper_mocks, close_browser

    def test_dry_run_returns_early(self):
        """DRY_RUN 开启：不点发布，等浏览器关闭后提前 return。"""
        p = _mk_platform()
        page = _mk_page()
        browser = MagicMock()
        browser.is_connected = MagicMock(side_effect=[True, False])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock(side_effect=RuntimeError("close boom"))
        context.storage_state = AsyncMock()
        result, mocks, close_browser = self._run(
            p, browser, context, page, dry_run=True, close_browser_exc=RuntimeError("boom"),
            title="T", files=["/v.mp4"], account_file=["a.json"],
        )
        assert result is True
        mocks["_submit_publish"].assert_not_called()
        context.close.assert_awaited_once()  # finally 仍清理
        close_browser.assert_awaited_once()  # close 抛异常被吞掉

    def test_dry_run_is_connected_exception_swallowed(self):
        """DRY_RUN 等待循环中 is_connected 探测异常被吞掉。"""
        p = _mk_platform()
        page = _mk_page()
        browser = MagicMock()
        browser.is_connected = MagicMock(side_effect=[True, RuntimeError("boom")])
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        context.storage_state = AsyncMock()
        result, mocks, _ = self._run(
            p, browser, context, page, dry_run=True,
            title="T", files=["/v.mp4"], account_file=["a.json"],
        )
        assert result is True
        mocks["_submit_publish"].assert_not_called()

    def test_wait_for_url_exception_swallowed(self):
        """wait_for_url 超时被吞掉，流程继续。"""
        p = _mk_platform()
        page = _mk_page()
        page.wait_for_url = AsyncMock(side_effect=TimeoutError("slow"))
        browser = MagicMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        context.storage_state = AsyncMock()
        result, mocks, _ = self._run(
            p, browser, context, page,
            title="T", files=["/v.mp4"], account_file=["a.json"],
        )
        assert result is True
        assert mocks["_submit_publish"].await_count == 1
        assert page.wait_for_url.await_count >= 1

    def test_thumbnail_str_conversion_and_schedule(self):
        """thumbnail 非空时 str() 转换 + enable_timer 定时路径被调用。"""
        p = _mk_platform()
        page = _mk_page()
        browser = MagicMock()
        browser.is_connected = MagicMock(return_value=False)
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        context.storage_state = AsyncMock()
        result, mocks, _ = self._run(
            p, browser, context, page,
            title="T", files=["/v.mp4"], account_file=["a.json"],
            thumbnail_path="/t.png", thumbnail_landscape_path="/tl.png",
            thumbnail_portrait_path="/tp.png",
            enableTimer=True, schedule_time_str="2026-08-21 10:00",
        )
        assert result is True
        mocks["_set_thumbnail"].assert_awaited_once()
        mocks["_set_schedule_time"].assert_awaited_once()
        mocks["_submit_publish"].assert_awaited_once()
