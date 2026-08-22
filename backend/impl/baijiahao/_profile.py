"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_baijiahao_profile(page):
    """Baijiahao (百家号) specific scraper.

    Navigates to the account settings page and targets
    ``img[class*="userImg"]`` for the avatar and
    ``div[class*="userName"]`` for the username.

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        # Navigate to account settings page where avatar and name are rendered
        await page.goto(
            "https://baijiahao.baidu.com/builder/rc/settings/accountSet",
            timeout=20000,
        )
        await page.wait_for_load_state('domcontentloaded', timeout=15000)

        # 等待用户信息节点出现（SPA 异步渲染）
        # userName 容器比 userImg 先就绪，先等 name
        try:
            await page.locator('div[class*="userName"]').first.wait_for(
                state="visible", timeout=12000,
            )
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            # 未在 12s 内出现：可能 cookie 失效跳转到了登录页，记录后继续
            logger.info(f"[baijiahao] userName 元素等待超时: {e}; 当前 url={page.url}")

        await asyncio.sleep(1)

        # Avatar: img with class containing "userImg"
        avatar_el = page.locator('img[class*="userImg"]').first
        if await avatar_el.count():
            avatar = (await avatar_el.get_attribute('src') or '').strip()

        # Username: div with class containing "userName"
        name_el = page.locator('div[class*="userName"]').first
        if await name_el.count():
            # 优先取 title 兜底 text
            name = (await name_el.get_attribute('title') or '').strip()
            if not name:
                name = (await name_el.text_content() or '').strip()

        logger.info(f"[baijiahao] profile scraped - name={name!r} avatar={avatar[:50] if avatar else 'None'}")
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[baijiahao] profile scrape error: {e}")
    return name, avatar
