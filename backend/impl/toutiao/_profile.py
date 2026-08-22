"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_toutiao_profile(page):
    """Toutiao-specific scraper.

    抓取依据：今日头条创作中心登录后会出现 user-panel 结构。
    从 user-panel 中提取头像和昵称。

    定位策略：
    1. 昵称：auth-avator-name 类名的元素
    2. 头像：auth-avator-img 类名的 img 元素

    失败兜底：返回 ("", "")，由 save_login_result 兜底用户名。

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
        await asyncio.sleep(3)

        result = await page.evaluate("""() => {
            let name = '', avatar = '';

            // Strategy 1: Look for user-panel structure
            const userPanel = document.querySelector('.user-panel .information');
            if (userPanel) {
                // Avatar: img inside auth-avator-img-wrap
                const avatarImg = userPanel.querySelector('.auth-avator-img');
                if (avatarImg) {
                    avatar = avatarImg.src || '';
                }
                // Name: text in auth-avator-name
                const nameEl = userPanel.querySelector('.auth-avator-name');
                if (nameEl) {
                    name = nameEl.textContent.trim();
                }
            }

            // Strategy 2: Look for menu-title (e.g., "晚上好，菜鸡")
            if (!name) {
                const menuTitle = document.querySelector('.menu-title');
                if (menuTitle) {
                    const text = menuTitle.textContent.trim();
                    // Extract name after comma
                    const match = text.match(/[，,](.+)$/);
                    if (match) {
                        name = match[1].trim();
                    }
                }
            }

            // Strategy 3: Look for title attribute on links
            if (!name) {
                const userLink = document.querySelector('.user-panel a[title]');
                if (userLink) {
                    const title = userLink.getAttribute('title');
                    // Extract name from "菜鸡的个人主页"
                    const match = title.match(/^(.+?)的个人主页$/);
                    if (match) {
                        name = match[1].trim();
                    }
                }
            }

            return { name, avatar };
        }""")

        name = (result.get("name") or "").strip()
        avatar = (result.get("avatar") or "").strip()
        logger.info(
            f"[toutiao] profile scraped - name={name!r} "
            f"avatar={avatar[:80] if avatar else 'None'}"
        )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[toutiao] profile scrape error: {e}")

    return name, avatar
