"""填写标题原语（Phase A1）——统一 8 处平台实现。

策略:
- ``fill``:      标准 input/textarea 定位 + 清空 + 填充 (7 平台)
- ``rich_text``: contenteditable 富文本 div 定位 + 键入 (tencent_video)

平台专属选择器/截断长度等参数落在 ``params/<platform>.py`` 数据表。
京东(iframe)场景通过 ``frame`` 参数复用同一 fill 路径。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("primitives")

# 通用标题净化（收编 bilibili/_sanitize_title：emoji + HTML 危险字符）
import re  # noqa: E402

_TITLE_FORBIDDEN_RE = re.compile(
    '[\u2600-\u27bf\ufe00-\ufe0f\u200d\u20e3\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufff0-\uffff'
    '\U0001f000-\U0001faff'
    '<>"\'&]',
)


def sanitize_title(text: str) -> str:
    """去掉 emoji 与 HTML 危险字符，其他字符保留。"""
    if not text:
        return text
    return _TITLE_FORBIDDEN_RE.sub("", text)


async def fill_title(page, title, params, frame=None):
    """填写标题原语入口。

    Args:
        page: Playwright Page
        title: 原始标题
        params: ``params/<platform>.py`` 中的 FILL_TITLE 数据表条目
        frame: 可选 Playwright Frame（京东发布表单在 iframe 内）
    """
    if not title:
        return
    text = title.strip()
    if params.get("sanitize"):
        text = sanitize_title(text)
    max_len = params.get("max_len")
    if max_len:
        text = text[:max_len]
    if text != title:
        logger.info("[填写标题] 标题已过滤/截断: %r -> %r", title, text)
    logger.info("[填写标题] 开始填写标题: %s", text[:30])

    strategy = params.get("strategy", "fill")
    selector = params.get("selector")
    if not selector:
        logger.warning("[填写标题] 参数表缺少 selector,跳过")
        return

    try:
        if strategy == "rich_text":
            await _fill_rich_text(page, selector, text)
        else:
            await _fill_plain(page, selector, text, frame)
    except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码(与原平台实现一致:失败非致命)
        logger.warning("[填写标题] 填写标题失败(非致命): %s", exc)


async def _fill_plain(page, selector, text, frame=None):
    if frame is not None:
        el = await frame.wait_for_selector(selector, timeout=15_000)
        await el.click()
        await el.fill("")
        await asyncio.sleep(0.3)
        await el.fill(text)
        await asyncio.sleep(0.5)
        return
    el = page.locator(selector).first
    await el.wait_for(state="visible", timeout=15_000)
    await el.click()
    await el.fill("")
    await el.fill(text)
    await asyncio.sleep(0.5)


async def _fill_rich_text(page, selector, text):
    """contenteditable 富文本标题（tencent_video ProseMirror）。"""
    container = page.locator(selector).first
    if await container.count() == 0:
        logger.warning("[填写标题] 标题字段未找到")
        return
    title_div = container.locator(
        "div.ProseMirror.ExEditor-cc-title-input"
    ).first
    if await title_div.count() == 0:
        logger.warning("[填写标题] contenteditable 标题 div 未找到")
        return
    await title_div.wait_for(state="visible", timeout=10_000)
    await title_div.click()
    await page.keyboard.type(text, delay=20)
    await asyncio.sleep(0.5)
