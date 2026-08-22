"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_csdn_profile(page):
    """CSDN 专用 scraper。

    抓取流程（详见对接文档）：
    1. 当前页应该是 ``https://mp.csdn.net/`` 创作者首页，已登录。
    2. 等待 ``div.user-info-box``（用户信息卡）出现。
    3. 昵称：``div.user-info-box p.name``（优先取 ``title`` 属性，兜底 text）。
    4. 头像：``div.user-info-box .avatar-box img`` 的 ``src``。

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        try:  # noqa: SIM105
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:  # noqa: S110, BLE001 -- DOM/页面探测兜底,元素可能不存在
            pass
        try:
            await page.locator("div.user-info-box").first.wait_for(
                state="visible", timeout=15000
            )
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[csdn] 用户信息卡未出现 (可能未登录): {e}")
        await asyncio.sleep(2)

        # 昵称：优先 title 属性（完整名），兜底 text_content
        try:
            name_el = page.locator("div.user-info-box p.name").first
            if await name_el.count() > 0:
                name = (await name_el.get_attribute("title") or "").strip()
                if not name:
                    name = (await name_el.text_content() or "").strip()
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[csdn] 昵称抓取失败: {e}")

        # 头像
        try:
            avatar_el = page.locator(
                "div.user-info-box .avatar-box img"
            ).first
            if await avatar_el.count() > 0:
                avatar = (await avatar_el.get_attribute("src") or "").strip()
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[csdn] 头像抓取失败: {e}")

        logger.info(
            f"[csdn] profile scraped - name={name!r} "
            f"avatar={avatar[:80] if avatar else 'None'}"
        )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[csdn] profile scrape error: {e}")

    return name, avatar
