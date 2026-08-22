"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_zhihu_profile(page):
    """知乎专用 scraper。

    抓取流程（详见对接文档）：
    1. 当前页应该是 ``https://www.zhihu.com/settings/account`` 或类似页面，
       页面右上角已有头像按钮。
    2. 点击右上角头像按钮 (``.AppHeader-profileEntry``) 弹出下拉菜单。
    3. 点击菜单中的「我的主页」链接 (``a[href^="/people/"]``)。
    4. 等待跳转到 ``https://www.zhihu.com/people/<id>`` 后：
       - 昵称：``span.ProfileHeader-name``
       - 头像：``.UserAvatar-inner`` 或 ``img.Avatar`` 的 ``src``

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
        await asyncio.sleep(2)

        # 1. 点击右上角头像按钮展开下拉菜单
        try:
            avatar_btn = page.locator(
                'button.AppHeader-profileEntry, .AppHeader-userInfo .AppHeader-profileEntry'
            ).first
            if await avatar_btn.count() == 0:
                avatar_btn = page.locator('.AppHeader-profileEntry').first
            await avatar_btn.wait_for(state="visible", timeout=8000)
            await avatar_btn.click()
            await asyncio.sleep(1)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[zhihu] 点击头像下拉失败 (可能已在主页): {e}")

        # 2. 点击「我的主页」链接
        # href 在 DOM 里是完整 URL (https://www.zhihu.com/people/xxx)，
        # 不能用 [href^="/people/"] 匹配；用文案「我的主页」+ 排除关怀版
        # (/aria/people/) 最稳。
        profile_link = page.locator(
            '.AppHeaderProfileMenu-item:has-text("我的主页"), '
            'a.Menu-item:has-text("我的主页")'
        ).first
        navigated = False
        try:
            await profile_link.wait_for(state="visible", timeout=5000)
            href = await profile_link.get_attribute("href") or ""
            await profile_link.click()
            logger.info(f"[zhihu] 点击「我的主页」成功，href={href}")
            navigated = True
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[zhihu] 点击「我的主页」失败: {e}")

        # 3. 等待跳转完成（URL 应包含 /people/）
        if navigated:
            try:  # noqa: SIM105
                await page.wait_for_url("**/people/**", timeout=15000)
            except Exception:  # noqa: S110, BLE001 -- DOM/页面探测兜底,元素可能不存在
                pass
        try:  # noqa: SIM105
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:  # noqa: S110, BLE001 -- DOM/页面探测兜底,元素可能不存在
            pass

        # 4. 抓取昵称和头像
        # 知乎「我的主页」是 SPA，跳转后异步渲染。先等昵称容器出现再读。
        try:
            name_el = page.locator(
                'span.ProfileHeader-name, h1.ProfileHeader-title, '
                'h1.UserHeaderName, .ProfileHeader-name'
            ).first
            try:
                await name_el.wait_for(state="visible", timeout=10000)
            except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                logger.info(f"[zhihu] 昵称容器等待超时 (url={page.url}): {e}")
            if await name_el.count() > 0:
                name = (await name_el.text_content() or "").strip()
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[zhihu] 昵称抓取失败: {e}")

        # 兜底：从 URL / 页面 title 提取昵称
        if not name:
            try:
                title = (await page.title() or "").strip()
                # title 一般是 "xxx - 知乎" 或 "xxx的主页"
                if title and "知乎" in title:
                    cand = title.split("-")[0].split("的")[0].strip()
                    if cand and cand != "知乎":
                        name = cand
                        logger.info(f"[zhihu] 从 title 兜底昵称: {name!r}")
            except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                pass

        try:
            avatar_el = page.locator(
                '.UserAvatar-inner img, .ProfileHeader-avatar img.Avatar, '
                '.UserAvatar-inner, img.Avatar'
            ).first
            try:  # noqa: SIM105
                await avatar_el.wait_for(state="attached", timeout=8000)
            except Exception:  # noqa: S110, BLE001 -- DOM/页面探测兜底,元素可能不存在
                pass
            if await avatar_el.count() > 0:
                avatar = (await avatar_el.get_attribute("src") or "").strip()
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[zhihu] 头像抓取失败: {e}")

        logger.info(
            f"[zhihu] profile scraped - name={name!r} "
            f"avatar={avatar[:80] if avatar else 'None'}"
        )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[zhihu] profile scrape error: {e}")

    return name, avatar
