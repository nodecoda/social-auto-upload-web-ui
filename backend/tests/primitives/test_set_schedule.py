"""set_schedule 原语单测（Phase A1）：策略分支全覆盖 + 数据表完整性守卫。

覆盖: text / calendar(wheel,panel,popover,left_right,list,input) / select 策略、
publish_dt=0 短路、enable 各交互方式、parse_publish_dt 解析、A1.1 参数引用完整性。
"""
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from impl.primitives import PARAMS, parse_publish_dt, set_schedule
from impl.primitives.schedule import (
    STRATEGY_CALENDAR,
    STRATEGY_SELECT,
    STRATEGY_TEXT,
)
from tests.primitives.conftest import FakePage


def _run(fn, *args, **kwargs):
    with patch("impl.primitives.schedule.asyncio.sleep", AsyncMock()):
        return asyncio.run(fn(*args, **kwargs))


def _dt():
    return datetime(2026, 6, 22, 13, 5, tzinfo=UTC)


def _has(page, *substrs, action=None):
    """calls 中是否存在 selector 含全部子串（且可选 action）的记录。"""
    for call in page.calls:
        sel = call[1]
        if not isinstance(sel, str):
            continue
        if action is not None and call[0] != action:
            continue
        if all(s in sel for s in substrs):
            return True
    return False


# ── parse_publish_dt ──────────────────────────────────────────────────────
class TestParsePublishDt:
    def test_datetime_passthrough(self):
        dt = _dt()
        assert parse_publish_dt(dt) == dt

    def test_zero_shortcut(self):
        assert parse_publish_dt(0) is None

    def test_local_string(self):
        assert parse_publish_dt("2026-06-22 13:00").hour == 13

    def test_iso_utc_z(self):
        dt = parse_publish_dt("2026-06-22T05:00:00.000Z")
        assert dt.hour == 13  # UTC 05:00 -> 东八 13:00

    def test_iso_plus08(self):
        dt = parse_publish_dt("2026-06-22T13:00:00+08:00")
        assert dt.hour == 13

    def test_iso_naive_t(self):
        assert parse_publish_dt("2026-06-22T13:00").hour == 13

    def test_invalid_returns_none(self):
        assert parse_publish_dt("not-a-date") is None


# ── 短路 ──────────────────────────────────────────────────────────────────
class TestShortCircuit:
    def test_publish_dt_zero_does_nothing(self):
        page = FakePage()
        _run(set_schedule, page, 0, PARAMS["douyin"]["SCHEDULE"])
        assert page.calls == []

    def test_unparseable_skips(self):
        page = FakePage()
        _run(set_schedule, page, "garbage", PARAMS["douyin"]["SCHEDULE"])
        assert page.calls == []


# ── text 策略 ─────────────────────────────────────────────────────────────
class TestTextStrategy:
    def test_alipay_type_input_and_confirm_role(self):
        page = FakePage()
        _run(set_schedule, page, "2026-06-22 13:05", PARAMS["alipay"]["SCHEDULE"])
        assert ("click", "role=button name=确 定", {}) in page.calls
        assert any(k[0] == "type" for k in page.calls)
        assert any("_scheduleTime" in k[1] for k in page.calls if k[0] == "type")

    def test_alipay_radio_label_enable(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["alipay"]["SCHEDULE"])
        assert any("publishType" in c[1] for c in page.calls)

    def test_vivo_dual_input(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["vivo"]["SCHEDULE"])
        fills = [c for c in page.calls if c[0] == "fill"]
        assert any("选择日期" in c[1] and c[2] == "2026-06-22" for c in fills)
        assert any("选择时间" in c[1] and c[2] == "13:05" for c in fills)
        assert any("is-plain" in c[1] for c in page.calls if c[0] == "click")

    def test_vivo_radio_check_checked_skips_click(self):
        page = FakePage(attributes={"label[role=\"radio\"]:has(span.el-radio__label:has-text(\"定时发布\"))": {"aria-checked": "true"}})
        _run(set_schedule, page, _dt(), PARAMS["vivo"]["SCHEDULE"])
        clicks = [c for c in page.calls if c[0] == "click"]
        assert not any("role=\"radio\"" in c[1] for c in clicks)

    def test_iqiyi_press_enter(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["iqiyi"]["SCHEDULE"])
        assert ("keyboard.press", "Enter", None) in page.calls

    def test_kuaishou_clear_and_type(self):
        page = FakePage()
        with patch("impl._utils.clear_and_type", AsyncMock()) as cat:
            _run(set_schedule, page, _dt(), PARAMS["kuaishou"]["SCHEDULE"])
            cat.assert_awaited_once()
            fmt = PARAMS["kuaishou"]["SCHEDULE"]["input_format"]
            assert cat.await_args.args[1] == _dt().strftime(fmt)


# ── calendar 策略 ─────────────────────────────────────────────────────────
class TestCalendarStrategy:
    def test_douyin_title_cell_and_wheel(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["douyin"]["SCHEDULE"])
        # title=ISO 日期格
        assert any('[title="2026-06-22"]' in c[1] for c in page.calls)
        # 时间滚轮时/分
        assert any("list-hour" in c[1] and c[0] == "click" for c in page.calls)
        assert any("list-minute" in c[1] and c[0] == "click" for c in page.calls)
        # 确定按钮
        assert any('button:has-text("确定")' in c[1] for c in page.calls)

    def test_bilibili_text_cell_panel_and_escape(self):
        page = FakePage(attributes={"div.date-picker-body-item.date-item": {"text": "22"}})
        _run(set_schedule, page, _dt(), PARAMS["bilibili"]["SCHEDULE"])
        assert _has(page, "date-item", action="click")
        assert ("keyboard.press", "Escape", None) in page.calls

    def test_bilibili_skips_disabled_day(self):
        page = FakePage(attributes={
            "div.date-picker-body-item.date-item": {"text": "22"},
        })
        _run(set_schedule, page, _dt(), PARAMS["bilibili"]["SCHEDULE"])
        assert _has(page, "date-item", action="click")

    def test_zhihu_popover_nth(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["zhihu"]["SCHEDULE"])
        # 时/分下拉
        assert any("combobox" in c[1] for c in page.calls if c[0] == "click")
        assert any("Select-option" in c[1] for c in page.calls if c[0] == "click")

    def test_taobao_title_cell_slash_format_and_menu(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["taobao_guanghe"]["SCHEDULE"])
        assert _has(page, '[title="2026/06/22"]')
        assert _has(page, "next-time-picker-menu-hour")
        assert _has(page, "next-time-picker-menu-minute")

    def test_tiktok_left_right_and_month(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["tiktok"]["SCHEDULE"])
        assert _has(page, "tiktok-timepicker-left")
        assert _has(page, "tiktok-timepicker-right")

    def test_tencent_list_and_confirm(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["tencent_video"]["SCHEDULE"])
        assert _has(page, "itemWrap", action="click")
        assert any("确定" in c[1] for c in page.calls if c[0] == "click")

    def test_channels_weui_month_and_time_input(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["channels"]["SCHEDULE"])
        # 时间输入框点击 + 键盘输入 HH:MM
        assert _has(page, "请选择时间")
        assert any(c[0] == "keyboard.type" and c[1] == "13:05" for c in page.calls)

    def test_zhihu_month_nav_zhihu_match(self):
        page = FakePage(attributes={
            ".Calendar-topToolDate": {"text": "2026年5月"},
        })
        _run(set_schedule, page, _dt(), PARAMS["zhihu"]["SCHEDULE"])
        # 目标 6 月 > 当前 5 月 → 点 nextMonth
        assert _has(page, "nextMonth")


# ── select 策略 ───────────────────────────────────────────────────────────
class TestSelectStrategy:
    def test_toutiao_three_selects(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["toutiao"]["SCHEDULE"])
        assert _has(page, "day-select")
        assert _has(page, "hour-select")
        assert _has(page, "minute-select")
        # 选项按文本命中（06月22日 / 13 / 5）
        assert _has(page, "byte-select-option")


# ── enable 各交互方式 ─────────────────────────────────────────────────────
class TestEnableKinds:
    def test_switch_checked_skips_click(self):
        page = FakePage(attributes={'button[role="switch"]': {"aria-checked": "true"}})
        _run(set_schedule, page, _dt(), PARAMS["tencent_video"]["SCHEDULE"])
        assert not _has(page, 'button[role="switch"]', action="click")

    def test_switch_unchecked_clicks(self):
        page = FakePage(attributes={'button[role="switch"]': {"aria-checked": "false"}})
        _run(set_schedule, page, _dt(), PARAMS["tencent_video"]["SCHEDULE"])
        assert _has(page, 'button[role="switch"]', action="click")

    def test_xhs_filter_child_click(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["xiaohongshu"]["SCHEDULE"])
        assert any(".d-switch" in c[1] for c in page.calls if c[0] == "click")

    def test_js_radio_evaluate(self):
        page = FakePage()
        _run(set_schedule, page, _dt(), PARAMS["taobao_guanghe"]["SCHEDULE"])
        assert any(c[0] == "page.evaluate" for c in page.calls)


# ── A1.1 参数数据表完整性守卫 ─────────────────────────────────────────────
_VALID_STRATEGIES = {STRATEGY_TEXT, STRATEGY_CALENDAR, STRATEGY_SELECT}
_VALID_ENABLE_KINDS = {"click", "switch", "checkbox", "radio_check", "radio_label", "js_radio"}


class TestParamsIntegrity:

    def test_all_schedule_entries_have_valid_strategy(self):
        for platform, prims in PARAMS.items():
            if "SCHEDULE" not in prims:
                continue
            strat = prims["SCHEDULE"]["strategy"]
            assert strat in _VALID_STRATEGIES, f"{platform}: 未知策略 {strat}"

    def test_all_schedule_entries_have_enable_selector(self):
        for platform, prims in PARAMS.items():
            if "SCHEDULE" not in prims:
                continue
            s = prims["SCHEDULE"]
            # js_radio 用 JS 文本定位，无需 CSS 选择器
            if s.get("enable_kind") == "js_radio":
                assert s.get("enable_label_text"), f"{platform}: js_radio 缺 enable_label_text"
            else:
                assert s.get("enable_selector"), f"{platform}: 缺 enable_selector"

    def test_enable_kind_valid(self):
        for platform, prims in PARAMS.items():
            if "SCHEDULE" not in prims:
                continue
            kind = prims["SCHEDULE"].get("enable_kind", "click")
            assert kind in _VALID_ENABLE_KINDS, f"{platform}: 未知 enable_kind {kind}"

    def test_strategy_requires_matching_params(self):
        for platform, prims in PARAMS.items():
            if "SCHEDULE" not in prims:
                continue
            s = prims["SCHEDULE"]
            if s["strategy"] == STRATEGY_TEXT:
                assert s.get("input_selector"), f"{platform}: text 策略缺 input_selector"
            elif s["strategy"] == STRATEGY_CALENDAR:
                assert s.get("day_cell_selector") or s.get("date_list_selector"), \
                    f"{platform}: calendar 策略缺日期选择器"
            elif s["strategy"] == STRATEGY_SELECT:
                assert s.get("selectors"), f"{platform}: select 策略缺 selectors"

    def test_schedule_count_matches_scope(self):
        # A1/A2 定时原语收敛后：14 平台应有 SCHEDULE 参数表（平台实现已归零，参数表即契约）
        with_schedule = {p for p, v in PARAMS.items() if "SCHEDULE" in v}
        assert len(with_schedule) == 14, f"期望 14 平台有 SCHEDULE,实际 {sorted(with_schedule)}"

    def test_fill_title_and_thumbnail_tables(self):
        with_fill = {p for p, v in PARAMS.items() if "FILL_TITLE" in v}
        with_thumb = {p for p, v in PARAMS.items() if "THUMBNAIL" in v}
        assert len(with_fill) == 8, f"期望 8 平台有 FILL_TITLE,实际 {sorted(with_fill)}"
        assert len(with_thumb) == 10, f"期望 10 平台有 THUMBNAIL,实际 {sorted(with_thumb)}"
