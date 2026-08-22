"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_tencent_profile(page):
    """WeChat Channels (视频号) specific scraper.

    登录成功后创作中心首页（``/platform``）会渲染一张 ``div.finder-card``
    资料卡，内含 ``img.avatar``（头像）和 ``h2.finder-nickname``（昵称）。
    这里显式等待该卡片就绪后再读取，避免页面未渲染完抓不到。

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state('domcontentloaded', timeout=10000)
        # 显式等待 finder-card 资料卡渲染（取代固定 sleep）
        try:
            await page.locator('div.finder-card').first.wait_for(
                state="visible", timeout=15000,
            )
        except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[channels] finder-card 未就绪, 当前 url={page.url}")
        # 头像: div.finder-card img.avatar
        avatar_el = page.locator('div.finder-card img.avatar').first
        if await avatar_el.count():
            avatar = (await avatar_el.get_attribute('src') or '').strip()
        # 昵称: div.finder-card h2.finder-nickname
        name_el = page.locator('div.finder-card h2.finder-nickname').first
        if await name_el.count():
            name = (await name_el.text_content() or '').strip()
        if name:
            logger.info(f"[channels] profile scraped - name: {name}, avatar: {avatar[:50] if avatar else 'N/A'}")
        else:
            logger.info("[channels] profile scrape failed, will use default name")
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[channels] profile scrape error: {e}")
    return name, avatar
