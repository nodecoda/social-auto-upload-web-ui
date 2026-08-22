"""封面/缩略图上传原语（Phase A1）——统一 8 处 set_thumbnail + 2 处 upload_cover。

策略:
- ``file_input``:   直接定位隐藏 ``input[type=file]`` set_input_files
                    (csdn / xiaohongshu / bilibili 探测① / channels)
- ``click_modal``:  点入口按钮打开弹窗 → 弹窗内 file input 上传 → 确认
                    (douyin / bilibili / tencent_video cover / iqiyi cover)
- ``hover_modal``:  hover 封面区触发入口 → 弹窗 → 上传 → 确认 (kuaishou)
- ``file_chooser``: 拦截原生文件选择器 (zhihu)

多方向(横/竖/16:9)通过 ``orientations`` 参数化；确认/裁剪弹窗通过
``confirm_selector`` 参数化。平台专属选择器全部落在 params/<platform>.py。
"""
import asyncio
import contextlib
import os

from util._logger import get_channel_logger

logger = get_channel_logger("primitives")

# 策略常量
_STRATEGY_FILE_INPUT = "file_input"
_STRATEGY_CLICK_MODAL = "click_modal"
_STRATEGY_HOVER_MODAL = "hover_modal"
_STRATEGY_FILE_CHOOSER = "file_chooser"


async def set_thumbnail(page, params, paths=None, thumbnail_path=None, frame=None):
    """上传封面原语入口。

    Args:
        page: Playwright Page
        params: ``params/<platform>.py`` 中的 THUMBNAIL 数据表条目
        paths: dict[str, str] 多方向路径映射（如 {"landscape": ..., "portrait": ...}）
        thumbnail_path: 单方向路径（缺省时回退用）
        frame: 可选 Playwright Frame
    """
    paths = dict(paths or {})
    if thumbnail_path:
        paths.setdefault("default", thumbnail_path)
    if not paths or all(not p for p in paths.values()):
        return
    for key, path in list(paths.items()):
        if path and not os.path.exists(path):
            logger.info("[封面] 封面文件不存在: %s, 跳过", path)
            paths.pop(key, None)
    if not paths:
        return

    logger.info("[封面] 开始设置封面: %s", list(paths.values()))
    strategy = params.get("strategy", _STRATEGY_FILE_INPUT)
    orientations = params.get("orientations") or [{"key": "default", "path_key": "default"}]

    try:
        await _do_upload(page, params, paths, frame, strategy, orientations)
    except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码(与原平台实现一致:失败非致命)
        logger.warning("[封面] 设置封面失败(非致命): %s", exc)


async def _do_upload(page, params, paths, frame, strategy, orientations):
    # 打开封面入口（click / hover 两种触发方式）
    if params.get("direct_file_first"):
        # bilibili 探测①：页面上直接存在封面 file input，无需点任何按钮
        direct = await _find_file_input(page, params, None)
        if direct is not None:
            for path in paths.values():
                if path:
                    await direct.first.set_input_files(path)
                    await asyncio.sleep(params.get("upload_sleep", 1.0))
            await _confirm(page, params)
            return
    opened = await _open_trigger(page, params, strategy)
    if not opened and strategy in (_STRATEGY_CLICK_MODAL, _STRATEGY_HOVER_MODAL):
        # 触发元素缺失但存在直接 file input（bilibili 探测①兜底）
        if params.get("file_input_selector") or params.get("file_input_candidates"):
            await _upload_file_input(page, params, paths, frame)
        return

    for orient in orientations:
        key = orient.get("path_key", "default")
        path = paths.get(key)
        if not path:
            continue
        if not await _switch_orientation(page, params, orient):
            continue
        if strategy == _STRATEGY_FILE_CHOOSER:
            await _upload_via_file_chooser(page, params, {key: path}, orient)
        elif strategy in (_STRATEGY_CLICK_MODAL, _STRATEGY_HOVER_MODAL):
            await _upload_file_input(page, params, {key: path}, frame, modal=True)
        else:
            await _upload_file_input(page, params, {key: path}, frame)
        await _confirm(page, params)

    if params.get("close_escape"):
        with contextlib.suppress(Exception):  # UI 操作兜底,失败走后续逻辑
            await page.keyboard.press("Escape")


async def _switch_orientation(page, params, orient) -> bool:
    """切换到指定方向：tab_selector(CSS) 或 tab_text(文本探测，douyin)。"""
    tab_sel = orient.get("tab_selector")
    tab_text = orient.get("tab_text")
    if tab_sel:
        tab = page.locator(tab_sel).first
        if await tab.count():
            await tab.click()
            await asyncio.sleep(0.5)
            return True
        return False
    if tab_text and params.get("tab_scope_selector"):
        scope = page.locator(params["tab_scope_selector"])
        count = await scope.count()
        for i in range(count):
            text = (await scope.nth(i).inner_text()) or ""
            if tab_text in text:
                await scope.nth(i).click()
                await asyncio.sleep(1.0)
                return True
        return False
    return True


async def upload_cover(page, params, cover_path=None, paths=None, aspect=None):
    """上传封面图（tencent_video / iqiyi）——set_thumbnail 引擎的薄封装。"""
    if cover_path:
        paths = dict(paths or {})
        paths["default"] = cover_path
    await set_thumbnail(page, params, paths=paths)


async def _open_trigger(page, params, strategy) -> bool:
    selector = params.get("trigger_selector")
    if not selector:
        # 无触发入口：直接文件输入模式
        return strategy == _STRATEGY_FILE_INPUT
    el = page.locator(selector).first
    try:
        if strategy == _STRATEGY_HOVER_MODAL:
            await el.hover()
        else:
            await el.wait_for(state="visible", timeout=10_000)
            await el.click()
        await asyncio.sleep(params.get("trigger_sleep", 1.0))
        return True
    except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info("[封面] 封面入口触发失败: %s", exc)
        return False


async def _upload_file_input(page, params, paths, frame=None, modal=False):
    target = await _find_file_input(page, params, modal)
    if target is None:
        logger.warning("[封面] 未找到封面 file input,跳过上传")
        return
    for path in paths.values():
        if not path:
            continue
        try:
            await target.first.set_input_files(path)
            logger.info("[封面] 已上传封面: %s", path)
            await asyncio.sleep(params.get("upload_sleep", 1.0))
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.warning("[封面] 封面上传失败: %s", exc)


async def _find_file_input(page, params, modal):
    """定位 file input：单选择器优先，candidates 候选数组兜底（channels）。"""
    selector = params.get("file_input_selector")
    if not selector and params.get("file_input_candidates"):
        for cand in params["file_input_candidates"]:
            if modal and params.get("modal_selector"):
                loc = page.locator(params["modal_selector"]).first.locator(cand)
            else:
                loc = page.locator(cand)
            try:
                if await loc.first.count() > 0:
                    return loc
            except Exception as exc:  # noqa: BLE001 -- 单候选探测失败,记录后继续
                logger.info("[封面] file input 候选探测失败: %s", exc)
                continue
        return None
    if not selector:
        return None
    if modal and params.get("modal_selector"):
        modal_el = page.locator(params["modal_selector"]).first
        await modal_el.wait_for(state="visible", timeout=10_000)
        return modal_el.locator(selector)
    return page.locator(selector)


async def _upload_via_file_chooser(page, params, paths, orient=None):
    """拦截原生文件选择器（zhihu / iqiyi 逐面板上传）。"""
    trigger_sel = (orient or {}).get("trigger_selector") or params.get("trigger_selector")
    panel_sel = (orient or {}).get("panel_selector")
    for path in paths.values():
        if not path:
            continue
        try:
            async with page.expect_file_chooser(timeout=10_000) as fc_info:
                if panel_sel:
                    panel = page.locator(panel_sel).first
                    await panel.wait_for(state="visible", timeout=5_000)
                    await panel.locator(trigger_sel).first.click()
                else:
                    await page.locator(trigger_sel).first.click()
            fc = await fc_info.value
            await fc.set_files(path)
            logger.info("[封面] 已通过文件选择器上传: %s", path)
            await asyncio.sleep((orient or {}).get("upload_sleep", 1.0))
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.warning("[封面] 文件选择器上传失败: %s", exc)


async def _confirm(page, params):
    selector = params.get("confirm_selector")
    if not selector:
        return
    try:
        btn = page.locator(selector).first
        if await btn.count() > 0:
            await btn.click()
            logger.info("[封面] 已确认封面")
            await asyncio.sleep(0.5)
    except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info("[封面] 确认按钮点击失败(可能已关闭): %s", exc)
