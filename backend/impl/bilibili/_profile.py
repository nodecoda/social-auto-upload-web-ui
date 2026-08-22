"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_bilibili_profile(page):
    """Bilibili-specific scraper.

    Targets ``span.home-top-msg-name`` for the username and
    ``div.home-head img`` for the avatar.

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        await asyncio.sleep(2)
        # Username: span.home-top-msg-name
        name_el = page.locator('span.home-top-msg-name').first
        if await name_el.count():
            name = (await name_el.text_content() or '').strip()
        # Avatar: div.home-head img
        avatar_el = page.locator('div.home-head img').first
        if await avatar_el.count():
            avatar = (await avatar_el.get_attribute('src') or '').strip()
        if name:
            logger.info(f"[bilibili] profile scraped - name: {name}, avatar: {avatar[:50] if avatar else 'N/A'}")
        else:
            logger.info("[bilibili] profile scrape failed, will use default name")
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[bilibili] profile scrape error: {e}")
    return name, avatar
