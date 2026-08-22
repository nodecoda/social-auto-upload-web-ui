"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_weixin_gzh_profile(page):
    """微信公众号专用 scraper。

    当前页应为 ``https://mp.weixin.qq.com/cgi-bin/home?...&token=XXX`` 首页，
    已登录。DOM 结构（用户提供）：
      <div class="weui-personal_info">
        <img class="weui-desktop-account__img" src="https://wx.qlogo.cn/...">
        <div class="weui-desktop_name">czy个人测试</div>
      </div>

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        try:
            await page.locator(".weui-desktop_name").first.wait_for(
                state="visible", timeout=12000
            )
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[weixin_gzh] 昵称容器等待超时 (url={page.url}): {e}")
        await asyncio.sleep(1)

        # 头像：.weui-desktop-account__img 的 src
        try:
            avatar_el = page.locator(".weui-desktop-account__img").first
            if await avatar_el.count() > 0:
                avatar = (await avatar_el.get_attribute("src") or "").strip()
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[weixin_gzh] 头像抓取失败: {e}")

        # 昵称：.weui-desktop_name（优先 title 兜底 text）
        try:
            name_el = page.locator(".weui-desktop_name").first
            if await name_el.count() > 0:
                name = (await name_el.get_attribute("title") or "").strip()
                if not name:
                    name = (await name_el.text_content() or "").strip()
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[weixin_gzh] 昵称抓取失败: {e}")

        logger.info(
            f"[weixin_gzh] profile scraped - name={name!r} "
            f"avatar={avatar[:80] if avatar else 'None'}"
        )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[weixin_gzh] profile scrape error: {e}")

    return name, avatar
