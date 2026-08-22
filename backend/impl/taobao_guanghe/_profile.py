"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_taobao_guanghe_profile(page):
    """淘宝光合平台专用 scraper。

    当前页应为 ``https://creator.guanghe.taobao.com/`` 创作中心首页，已登录。

    DOM 说明：淘宝光合使用 CSS Modules，class 带随机哈希后缀
    (如 ``user--J5npn8g_``、``count-num--MjNr4IXK``)，**极不稳定**。
    这里一律改用稳定的埋点属性 ``data-autolog-container`` 定位：

    - 头像：``img[data-autolog-container="user_content_account"]`` 的 ``src``
    - 昵称：账号管理 info 块内第一个文本节点
      (该块 ``data-autolog`` 含 ``text=用户模块-账号管理``)

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        await asyncio.sleep(2)

        result = await page.evaluate(
            '''() => {
                const out = {name: '', avatar: ''};
                // 头像：账号管理埋点容器内的 img
                const avatarImg = document.querySelector('img[data-autolog-container="user_content_account"]');
                if (avatarImg) out.avatar = avatarImg.getAttribute('src') || '';

                // 昵称：data-autolog 含 "text=用户模块-账号管理" 的 info 块
                const infoEls = document.querySelectorAll('[data-autolog*="text=用户模块-账号管理"]');
                for (const el of infoEls) {
                    // info 块内第一个非空文本即为昵称
                    const walker = document.createTreeWalker(el, NodeFilter.SHOW_ELEMENT);
                    let node = walker.nextNode();
                    while (node) {
                        // 跳过含二维码/标签的子元素，取第一个有纯文本内容的块级元素
                        const directText = Array.from(node.childNodes)
                            .filter(n => n.nodeType === Node.TEXT_NODE)
                            .map(n => n.textContent.trim())
                            .join('').trim();
                        if (directText && directText.length >= 1 && directText.length <= 30
                            && !directText.includes('账号正常') && !directText.includes('逛逛号')) {
                            out.name = directText;
                            break;
                        }
                        node = walker.nextNode();
                    }
                    if (out.name) break;
                }
                return out;
            }'''
        )
        name = (result or {}).get('name', '')
        avatar = (result or {}).get('avatar', '')

        logger.info(
            f"[taobao_guanghe] profile scraped - name={name!r} "
            f"avatar={avatar[:80] if avatar else 'None'}"
        )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[taobao_guanghe] profile scrape error: {e}")

    return name, avatar
