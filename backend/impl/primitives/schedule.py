"""定时发布原语（Phase A1）——统一 14 处平台实现的“设置定时发布时间”交互。

策略收敛（与 params/<platform>.py 数据表一一对应）:

- ``text``:     直接向日期时间输入框填文本
                 (alipay / vivo / jd / xiaohongshu / iqiyi / kuaishou)
- ``calendar``: 打开日历点选日期 + 时间选择器选时/分
                 (douyin / bilibili / tencent_video / channels /
                  taobao_guanghe / zhihu / tiktok)
- ``select``:   三个独立下拉选择 日/时/分 (toutiao)

平台专属选择器/交互参数全部落在 ``params/<platform>.py`` 数据表
（数据，非逻辑），本文件不出现平台名字符串（A1.1 参数显性化守卫）。
"""
import asyncio
import contextlib

from util._logger import get_channel_logger

from ._datetime import parse_publish_dt

logger = get_channel_logger("primitives")

# ── 策略常量 ──────────────────────────────────────────────────────────────
STRATEGY_TEXT = "text"
STRATEGY_CALENDAR = "calendar"
STRATEGY_SELECT = "select"

# 开关交互方式（enable_kind）
_ENABLE_CLICK = "click"            # 直接点击开关元素
_ENABLE_SWITCH = "switch"          # button[role=switch]，aria-checked 判断
_ENABLE_CHECKBOX = "checkbox"      # input[type=checkbox]，is_checked 判断
_ENABLE_RADIO_CHECK = "radio_check"  # label[role=radio]，aria-checked/is-checked 判断
_ENABLE_RADIO_LABEL = "radio_label"  # input[value=..] 点 ancestor label
_ENABLE_JS_RADIO = "js_radio"      # 按文本定位 label.next-radio-wrapper（JS 兜底）

# 时间选择方式（calendar 策略的 time_kind）
_TIME_WHEEL = "wheel"          # 滚轮列表 li（douyin Semi）
_TIME_PANEL = "panel"          # 两面板 span 项（bilibili）/ 时-分菜单 title（taobao_guanghe）
_TIME_POPOVER = "popover"      # 下拉 combobox + 选项（zhihu）
_TIME_LEFT_RIGHT = "left_right"  # 左时分栏 span（tiktok）
_TIME_LIST = "list"            # 弹层内列表项（tencent_video）
_TIME_INPUT = "input"          # 时间输入框文本填充（channels）


class _Ctx:
    """共享操作上下文：封装 page / frame 差异与统一日志。"""

    def __init__(self, page, params, dt, frame=None):
        self.page = page
        self.frame = frame
        self.params = params
        self.dt = dt

    def locator(self, selector):
        """统一选择器入口：frame 优先（京东微前端 iframe 场景）。"""
        if self.frame is not None:
            return self.frame.locator(selector)
        return self.page.locator(selector)

    async def wait_for_selector(self, selector, timeout=10_000, state="visible"):
        if self.frame is not None:
            return await self.frame.wait_for_selector(selector, timeout=timeout, state=state)
        return await self.page.wait_for_selector(selector, timeout=timeout, state=state)

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


async def set_schedule(page, publish_dt, params, frame=None):
    """统一定时发布原语入口。

    Args:
        page: Playwright Page
        publish_dt: datetime | str(ISO/本地) | 0(int 表示不设置,短路跳过)
        params: ``params/<platform>.py`` 中的 SCHEDULE 数据表条目
        frame: 可选 Playwright Frame（京东微前端发布表单在 iframe 内）
    """
    if isinstance(publish_dt, int) and publish_dt == 0:
        return
    dt = parse_publish_dt(publish_dt)
    if dt is None:
        logger.warning("[定时发布] 无法解析定时时间,跳过: %r", publish_dt)
        return

    ctx = _Ctx(page, params, dt, frame)
    try:
        logger.info(
            "[定时发布] 开始设置定时发布时间: %s (strategy=%s)",
            dt.strftime("%Y-%m-%d %H:%M"), params.get("strategy"),
        )
        if not await _ensure_enabled(ctx):
            return
        strategy = params.get("strategy", STRATEGY_TEXT)
        if strategy == STRATEGY_TEXT:
            await _apply_text(ctx)
        elif strategy == STRATEGY_CALENDAR:
            await _apply_calendar(ctx)
        elif strategy == STRATEGY_SELECT:
            await _apply_select(ctx)
        else:
            logger.warning("[定时发布] 未知策略 %r,跳过", strategy)
            return
        await _confirm(ctx)
        await _close_picker(ctx)
        logger.info("[定时发布] 定时发布时间已设置")
    except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码(与原平台实现一致:设置失败非致命)
        logger.warning("[定时发布] 设置定时发布时间失败(非致命): %s", exc)


# ── 开关 ──────────────────────────────────────────────────────────────────
async def _ensure_enabled(ctx) -> bool:
    p = ctx.params
    selector = p.get("enable_selector")
    kind = p.get("enable_kind", _ENABLE_CLICK)
    if not selector and kind != _ENABLE_JS_RADIO:
        return True
    nth = p.get("enable_nth", 0)
    try:
        base = ctx.locator(selector)
        if p.get("enable_filter_text"):
            base = base.filter(has_text=p["enable_filter_text"])
        el = base.nth(nth) if nth else base.first
        await el.wait_for(state="attached", timeout=10_000)
        child_sel = p.get("enable_child_selector")
        if child_sel:
            el = el.locator(child_sel).first
        if kind == _ENABLE_CLICK:
            await el.click()
        elif kind == _ENABLE_SWITCH:
            checked = await el.get_attribute("aria-checked")
            if checked != "true":
                await el.click()
        elif kind == _ENABLE_CHECKBOX:
            checked = await el.is_checked()
            if not checked:
                await el.click()
        elif kind == _ENABLE_RADIO_CHECK:
            if not await _radio_is_checked(el):
                await el.click()
        elif kind == _ENABLE_RADIO_LABEL:
            label = el.locator("xpath=ancestor::label[1]")
            await label.click(force=True)
        elif kind == _ENABLE_JS_RADIO:
            clicked = await _js_click_radio(ctx, p.get("enable_label_text", "定时发布"))
            if not clicked:
                await _js_click_radio_fallback(ctx, p.get("enable_picker_selector"))
        else:
            await el.click()
        await ctx.sleep(p.get("enable_sleep", 1.0))
        logger.info("[定时发布] 已启用定时发布开关")
        return True
    except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.warning("[定时发布] 切换定时发布失败: %s", exc)
        return False


async def _radio_is_checked(el) -> bool:
    try:
        attr = await el.get_attribute("aria-checked")
        if attr == "true":
            return True
        cls = await el.get_attribute("class") or ""
        return "is-checked" in cls
    except Exception:  # noqa: BLE001 -- DOM 探测兜底,失败按未选中处理
        return False


async def _js_click_radio(ctx, label_text: str) -> bool:
    """按文本定位 radio（taobao_guanghe 场景：文字与 radio 是兄弟节点）。"""
    try:
        return await ctx.page.evaluate(
            """(labelText) => {
                const spans = document.querySelectorAll('span');
                for (const sp of spans) {
                    if ((sp.textContent || '').trim() === labelText) {
                        const prev = sp.previousElementSibling;
                        if (prev && prev.classList.contains('next-radio-wrapper')) {
                            prev.click();
                            return true;
                        }
                        const parent = sp.parentElement;
                        if (parent) {
                            const radio = parent.querySelector('.next-radio-wrapper');
                            if (radio) { radio.click(); return true; }
                        }
                    }
                }
                return false;
            }""",
            label_text,
        )
    except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info("[定时发布] JS 点击 radio 失败: %s", exc)
        return False


async def _js_click_radio_fallback(ctx, picker_selector):
    """兜底：直接对 radio input 派发 click（taobao_guanghe 第二重兜底）。"""
    try:
        return await ctx.page.evaluate(
            """() => {
                const radios = document.querySelectorAll('input[type="radio"]');
                for (const r of radios) {
                    const wrap = r.closest('.next-radio-wrapper');
                    const parent = wrap ? wrap.parentElement : null;
                    if (parent && parent.textContent.includes('定时发布')) {
                        wrap.click();
                        return true;
                    }
                }
                return false;
            }""",
        )
    except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info("[定时发布] 兜底 radio 点击失败: %s", exc)
        return False


# ── text 策略 ─────────────────────────────────────────────────────────────
async def _apply_text(ctx):
    p = ctx.params
    dt = ctx.dt
    fmt = p.get("input_format", "%Y-%m-%d %H:%M")
    # 单输入框（日期+时间一体）
    if p.get("input_selector"):
        await _fill_text_input(ctx, p["input_selector"], dt.strftime(fmt))
    # 双输入框（日期、时间分开，如 vivo Element-plus）
    if p.get("input_selector2"):
        fmt2 = p.get("input_format2", "%Y-%m-%d")
        await _fill_text_input(ctx, p["input_selector2"], dt.strftime(fmt2))
    if p.get("press_enter"):
        await ctx.page.keyboard.press("Enter")
        await ctx.sleep(0.5)


async def _fill_text_input(ctx, selector, text):
    p = ctx.params
    method = p.get("input_method", "fill")
    el = ctx.locator(selector).first
    await el.wait_for(state="visible", timeout=10_000)
    await el.click()
    await ctx.sleep(0.3)
    if method == "clear_and_type":
        await _clear_and_type(ctx, text)
    elif method == "type":
        await el.fill("")
        await el.type(text, delay=p.get("input_delay", 0))
    else:
        await el.fill("")
        await el.fill(text)
    await ctx.sleep(0.5)
    logger.info("[定时发布] 已填定时时间: %s", text)


async def _clear_and_type(ctx, text):
    """跨平台清空输入框（Mac Cmd+A / 其他 Ctrl+A）+ 键入。"""
    from .._utils import clear_and_type

    if ctx.frame is not None:
        # frame 场景回退到定位元素清空
        return await clear_and_type(ctx.page, text)
    return await clear_and_type(ctx.page, text)


# ── calendar 策略 ─────────────────────────────────────────────────────────
async def _apply_calendar(ctx):
    p = ctx.params
    dt = ctx.dt
    # 1. 打开日期选择器
    if p.get("date_trigger_selector"):
        nth = p.get("date_trigger_nth", 0)
        trigger = ctx.locator(p["date_trigger_selector"]).nth(nth) if nth else ctx.locator(p["date_trigger_selector"]).first
        await trigger.wait_for(state="visible", timeout=10_000)
        await trigger.click()
        await ctx.sleep(1)

    # 2. 选日期
    if p.get("date_list_selector"):
        # 弹层列表项模式（tencent_video）：按完整日期文本命中
        item = ctx.locator(
            f'{p["date_list_selector"]}:has-text("{dt.strftime("%Y-%m-%d")}")'
        ).first
        if await item.count() > 0:
            await item.click()
            await ctx.sleep(0.3)
    elif p.get("day_cell_selector"):
        if p.get("day_cell_title"):
            # 按 title 属性精确命中（douyin ISO / taobao_guanghe YYYY/MM/DD）
            title_fmt = p.get("day_cell_title_format", "%Y-%m-%d")
            cell = ctx.locator(
                f'{p["day_cell_selector"]}[title="{dt.strftime(title_fmt)}"]'
            ).first
            if await cell.count():
                await cell.click()
            else:
                logger.warning("[定时发布] 未找到可选日期，跳过日期选择")
        else:
            await _navigate_month(ctx)
            await _click_day_cell(ctx)
        await ctx.sleep(0.5)

    # 3. 选时间
    await _pick_time(ctx)


async def _navigate_month(ctx):
    p = ctx.params
    nav = p.get("month_nav")
    if not nav:
        return
    dt = ctx.dt
    match = nav.get("match", "none")
    limit = nav.get("limit", 24)
    for _ in range(limit):
        if match == "none":
            break
        if match == "ym_title":
            tool_text = ""
            try:
                tool = ctx.locator(nav["label_selector"]).first
                if await tool.count() > 0:
                    tool_text = (await tool.text_content() or "").strip()
            except Exception:  # noqa: S110, BLE001 -- DOM 探测兜底
                pass
            cur = _extract_year_month(tool_text) if tool_text else None
            if cur is None:
                await ctx.locator(nav["next_selector"]).first.click()
                await ctx.sleep(0.5)
                continue
            if cur == (dt.year, dt.month):
                break
            if cur < (dt.year, dt.month):
                await ctx.locator(nav["next_selector"]).first.click()
            else:
                await ctx.locator(nav["prev_selector"]).first.click()
            await ctx.sleep(0.5)
        elif match == "cn_month":
            # tiktok：中文月份标题，仅翻相邻月
            label = ctx.locator(nav["label_selector"]).first
            try:
                text = (await label.inner_text()).strip()
            except Exception:  # noqa: BLE001 -- DOM 探测兜底
                text = ""
            cur_month = _CN_MONTHS.get(text)
            if cur_month is None:
                try:
                    from datetime import datetime as _dt
                    from zoneinfo import ZoneInfo as _ZI

                    cur_month = _dt.strptime(text, "%B").replace(
                        tzinfo=_ZI("Asia/Shanghai")
                    ).month
                except ValueError:
                    cur_month = dt.month
            if cur_month != dt.month:
                with contextlib.suppress(Exception):  # UI 操作兜底,失败走后续逻辑
                    await ctx.locator(nav["next_selector"]).nth(1).click(timeout=2_000)
            break
        elif match == "label_text":
            # channels：标签含“X月”，不同点右箭头
            label = ctx.locator(nav["label_selector"]).first
            try:
                text = (await label.inner_text()) or ""
            except Exception:  # noqa: BLE001 -- DOM 探测兜底
                text = ""
            target = f"{dt.month}月"
            if text.strip() != target:
                await ctx.locator(nav["next_selector"]).first.click()
            break


async def _click_day_cell(ctx):
    p = ctx.params
    dt = ctx.dt
    target_day = str(dt.day)
    cells = ctx.locator(p["day_cell_selector"])
    count = await cells.count()
    for i in range(count):
        el = cells.nth(i)
        # 跳过禁用格（可选）
        exclude = p.get("day_cell_exclude")
        if exclude:
            classes = await el.get_attribute("class") or ""
            if exclude in classes:
                continue
        text = (await el.text_content() or "").strip()
        if text == target_day:
            await el.click()
            return
    logger.info("[定时发布] 找不到可点击日期 %s", target_day)


async def _pick_time(ctx):
    p = ctx.params
    dt = ctx.dt
    kind = p.get("time_kind", _TIME_PANEL)
    hour = dt.strftime("%H")
    minute = dt.strftime("%M")
    if p.get("time_trigger_selector"):
        nth = p.get("time_trigger_nth", 0)
        trig = ctx.locator(p["time_trigger_selector"]).nth(nth) if nth else ctx.locator(p["time_trigger_selector"]).first
        if await trig.count() > 0:
            await trig.click()
            await ctx.sleep(1)
    if kind == _TIME_WHEEL:
        # douyin Semi：切时间滚轮，选时/分 li
        switch_sel = p.get("time_switch_selector")
        if switch_sel:
            sw = ctx.locator(switch_sel).first
            if await sw.count():
                await sw.click()
                await ctx.sleep(1)
        for sel, val in ((p.get("hour_wheel_selector"), hour), (p.get("minute_wheel_selector"), minute)):
            if not sel:
                continue
            item = ctx.locator(sel).filter(has_text=val)
            if await item.count():
                await item.first.click()
            await ctx.sleep(0.4)
    elif kind == _TIME_PANEL:
        # bilibili 双面板 / taobao_guanghe 时-分菜单
        if p.get("panel_selector"):
            panels = ctx.locator(p["panel_selector"])
            for idx, val in ((0, hour), (1, minute)):
                item = panels.nth(idx).locator(p.get("panel_item_selector", "span")).filter(has_text=val)
                if await item.count() > 0:
                    await item.first.click()
                await ctx.sleep(0.3)
        else:
            for sel, val in ((p.get("hour_menu_selector"), hour), (p.get("minute_menu_selector"), minute)):
                if not sel:
                    continue
                item = ctx.locator(f'{sel}[title="{val}"]').first
                if await item.count() > 0:
                    await item.click()
                await ctx.sleep(0.5)
    elif kind == _TIME_POPOVER:
        # zhihu：时/分下拉 combobox + 选项
        for trig_sel, opt_sel, val in (
            (p.get("hour_trigger_selector"), p.get("hour_option_selector"), hour),
            (p.get("minute_trigger_selector"), p.get("minute_option_selector"), minute),
        ):
            if not trig_sel:
                continue
            try:
                nth = p.get("hour_nth", 0) if "hour" in trig_sel else p.get("minute_nth", 1)
                await ctx.locator(trig_sel).nth(nth).click(timeout=5_000)
            except Exception:  # noqa: BLE001 -- 捕获后恢复默认状态,防御性编码
                await ctx.locator(p.get("hour_trigger_fallback_selector", trig_sel)).nth(0).click(timeout=5_000)
            await ctx.sleep(0.5)
            opt = ctx.locator(f'{opt_sel}:has-text("{val}")').first
            if await opt.count() > 0:
                await opt.click()
            await ctx.sleep(0.5)
    elif kind == _TIME_LEFT_RIGHT:
        # tiktok：左时分栏 span
        for sel, val in ((p.get("hour_left_selector"), hour), (p.get("minute_right_selector"), minute)):
            if not sel:
                continue
            item = ctx.locator(f'{sel}:has-text("{val}")').first
            if await item.count():
                await item.click()
    elif kind == _TIME_LIST:
        # tencent_video：弹层列表项（“X时”/“X分”）
        for sel, val in (
            (p.get("hour_list_selector"), f"{dt.hour}时"),
            (p.get("minute_list_selector"), f"{dt.minute}分"),
        ):
            if not sel:
                continue
            item = ctx.locator(f'{sel}:has-text("{val}")').first
            if await item.count() > 0:
                await item.click()
                await ctx.sleep(0.3)
    elif kind == _TIME_INPUT:
        # channels：时间输入框 Ctrl+A Del + type HH:MM
        sel = p.get("time_input_selector")
        if sel:
            await ctx.locator(sel).first.click()
            await ctx.page.keyboard.press("Control+KeyA")
            await ctx.page.keyboard.press("Delete")
            await ctx.page.keyboard.type(dt.strftime("%H:%M"))
            if p.get("time_close_selector"):
                await ctx.locator(p["time_close_selector"]).first.click()


# ── select 策略（toutiao 三下拉） ─────────────────────────────────────────
async def _apply_select(ctx):
    p = ctx.params
    dt = ctx.dt
    selectors = p.get("selectors", {})
    for key, value in (
        ("day", dt.strftime("%m月%d日")),
        ("hour", str(dt.hour)),
        ("minute", str(dt.minute)),
    ):
        sel = selectors.get(key)
        if not sel:
            continue
        trigger = ctx.locator(sel["trigger"]).first
        if await trigger.count():
            await trigger.click()
            await ctx.sleep(1)
            option = ctx.locator(f'{sel["option"]}:has-text("{value}")').first
            if await option.count():
                await option.click()
                await ctx.sleep(0.5)


# ── 确认 & 关闭 ───────────────────────────────────────────────────────────
async def _confirm(ctx):
    p = ctx.params
    selector = p.get("confirm_selector")
    role = p.get("confirm_role")
    fallback_enter = p.get("confirm_enter_fallback", False)
    confirmed = False
    try:
        if selector:
            btn = ctx.locator(selector).first
            if await btn.count() > 0:
                await btn.click()
                confirmed = True
                await ctx.sleep(0.5)
            elif p.get("confirm_selector_fallback"):
                btn2 = ctx.locator(p["confirm_selector_fallback"]).first
                if await btn2.count() > 0:
                    await btn2.click()
                    confirmed = True
                    await ctx.sleep(0.5)
        elif role:
            btn = ctx.page.get_by_role(role[0], name=role[1], exact=True).first
            if await btn.count() > 0:
                await btn.click()
                confirmed = True
                await ctx.sleep(0.5)
    except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info("[定时发布] 点击确定失败(可能已关闭): %s", exc)
    if not confirmed and fallback_enter:
        await ctx.page.keyboard.press("Enter")


async def _close_picker(ctx):
    if ctx.params.get("close_escape"):
        with contextlib.suppress(Exception):  # UI 操作兜底,失败走后续逻辑
            await ctx.page.keyboard.press("Escape")
        await ctx.sleep(0.5)


# ── 工具 ──────────────────────────────────────────────────────────────────
_CN_MONTHS = {
    "一月": 1, "二月": 2, "三月": 3, "四月": 4,
    "五月": 5, "六月": 6, "七月": 7, "八月": 8,
    "九月": 9, "十月": 10, "十一月": 11, "十二月": 12,
}


def _extract_year_month(text: str):
    """从日历标题提取 (year, month)（zhihu 场景：'2026年7月'）。"""
    import re

    m = re.search(r"(\d{4})年\s*(\d{1,2})月", text)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = re.search(r"(\d{4})[年/.\-](\d{1,2})", text)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None
