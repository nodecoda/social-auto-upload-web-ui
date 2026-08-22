"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_youtube_profile(page):
    """YouTube-specific scraper.

    Navigates to YouTube Studio, waits for redirect to the channel page,
    then extracts the channel name and avatar from the navigation drawer.

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        # Wait for redirect to channel-specific URL
        await page.wait_for_url("**/channel/**", timeout=15000)
        await page.wait_for_load_state('networkidle', timeout=15000)
        await asyncio.sleep(3)

        # Extract nickname from navigation drawer
        name_el = page.locator('div#entity-name').first
        if await name_el.count():
            name = (await name_el.text_content() or '').strip()

        # Extract avatar from navigation drawer
        avatar_el = page.locator('img.image-thumbnail').first
        if await avatar_el.count():
            avatar = (await avatar_el.get_attribute('src') or '').strip()

        # Fallback: avatar button in Studio header
        if not avatar:
            avatar_btn = page.locator('button[id="avatar-button"]')
            if await avatar_btn.count():
                btn_img = avatar_btn.locator('img')
                if await btn_img.count():
                    avatar = (await btn_img.get_attribute('src') or '').strip()

        # Fallback: scan all images for Google profile URLs
        if not avatar:
            all_imgs = page.locator('img')
            count = await all_imgs.count()
            for i in range(count):
                img = all_imgs.nth(i)
                src = (await img.get_attribute('src') or '')
                if 'ggpht.com' in src or 'googleusercontent.com' in src:
                    avatar = src
                    if not name:
                        alt = (await img.get_attribute('alt') or '').strip()
                        if alt and len(alt) < 50:
                            name = alt
                    break

        # Fallback: page title ("Channel Name - YouTube Studio")
        if not name:
            title = await page.title()
            if ' - ' in title:
                candidate = title.split(' - ')[0].strip()
                if candidate and candidate != 'YouTube':
                    name = candidate

        logger.info(f"[youtube] profile scraped - name={name!r} avatar={avatar[:50] if avatar else 'None'}")
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[youtube] profile scrape error: {e}")
    return name, avatar
