"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_jingmai_profile(page):
    """京东京麦专用 scraper。

    当前页应为 ``https://dr.jd.com/jm/`` 创作中心，已登录。

    DOM 说明：京麦顶栏用无哈希的 BEM class（``shop-menu-accountV1__xxx``），
    稳定可用；Vue scoped 属性 ``data-v-xxxx`` 带哈希，**不用**。

    - 头像：``.shop-menu-account__right-avatar`` 的 ``src``
    - 昵称：``.shop-menu-accountV1__right-account-top-name`` 的 ``title`` 属性
      (兜底 text_content)

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        await asyncio.sleep(2)

        # 头像
        try:
            avatar_el = page.locator(".shop-menu-account__right-avatar").first
            if await avatar_el.count() > 0:
                avatar = (await avatar_el.get_attribute("src") or "").strip()
                if avatar.startswith("//"):
                    avatar = "https:" + avatar
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[jingmai] 头像抓取失败: {e}")

        # 昵称
        try:
            name_el = page.locator(
                ".shop-menu-accountV1__right-account-top-name"
            ).first
            if await name_el.count() > 0:
                name = (await name_el.get_attribute("title") or "").strip()
                if not name:
                    name = (await name_el.text_content() or "").strip()
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[jingmai] 昵称抓取失败: {e}")

        logger.info(
            f"[jingmai] profile scraped - name={name!r} "
            f"avatar={avatar[:80] if avatar else 'None'}"
        )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[jingmai] profile scrape error: {e}")

    return name, avatar
