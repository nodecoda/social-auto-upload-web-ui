"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_weibo_profile(page):
    """Weibo-specific scraper.

    抓取依据：微博创作中心顶部导航栏登录后会出现
    ``a[href^="/u/"]``（最后一个 tab，带 ``title`` 属性和头像 img）。
    直接跑 JS eval 取属性，避免 locator API 链的兼容问题。

    1. 昵称：``a[href^="/u/"]`` 的 ``title`` 属性
    2. 头像：``a[href^="/u/"] img[src*="sinaimg.cn"]`` 的 ``src`` 属性

    失败兜底：返回 ("", "")，由 save_login_result 兜底用户名。

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
        await asyncio.sleep(2)

        result = await page.evaluate("""() => {
            let name = '', avatar = '';
            // 必须限定到顶部导航栏 .woo-tab-nav，否则未登录态主页面
            // 热门博主链接也是 a[href^="/u/"] img[src*="sinaimg.cn"]
            const link = document.querySelector('.woo-tab-nav a[href^="/u/"]');
            if (link) {
                name = link.getAttribute('title') || '';
                const img = link.querySelector('img');
                if (img) avatar = img.src || '';
            }
            return { name, avatar };
        }""")
        name = (result.get("name") or "").strip()
        avatar = (result.get("avatar") or "").strip()
        logger.info(f"[weibo] profile scraped - name={name!r} avatar={avatar[:80] if avatar else 'None'} (result={result})")
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[weibo] profile scrape error: {e}")

    return name, avatar
