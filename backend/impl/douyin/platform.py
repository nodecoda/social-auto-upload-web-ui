"""
Douyin platform implementation — 100% CloakBrowser.

All browser operations go through ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` which delegate to CloakBrowser (stealth
Chromium) with automatic Playwright fallback.
"""

import asyncio
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR
from util._logger import bind_account_name, get_channel_logger

from .._utils import (
    get_account_name_by_cookie_file,
    parse_schedule_time,
    save_login_result,
    scrape_user_profile,
)
from ..base_platform import BasePlatform
from ..primitives import get_params, set_schedule, set_thumbnail
from ._dom_ops import (
    _count_hashtags,
    _fill_title_and_description,
    _handle_auto_video_cover,
    _select_music,
    _set_declaration,
    _set_hotspot,
    _set_image_cover,
    _set_image_mix,
    _set_location_tag,
    _set_product_link,
    _set_tag,
    _validate_publish_params,
)
from ._image_ops import DouyinImageOps

logger = get_channel_logger("douyin")

DOUYIN_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
DOUYIN_PUBLISH_STRATEGY_SCHEDULED = "scheduled"

# 调试开关:True = 走到发布按钮时只输出参数日志、不实际点击发布(便于检查内容);
# False = 正常点击发布。验证完发布内容无误后改回 False 即可。
_PUBLISH_DRY_RUN = False


class DouyinPlatform(DouyinImageOps, BasePlatform):

    _count_hashtags = staticmethod(_count_hashtags)
    _validate_publish_params = staticmethod(_validate_publish_params)
    _fill_title_and_description = staticmethod(_fill_title_and_description)
    _set_product_link = staticmethod(_set_product_link)
    _handle_auto_video_cover = staticmethod(_handle_auto_video_cover)
    _set_image_cover = staticmethod(_set_image_cover)
    _set_image_mix = staticmethod(_set_image_mix)
    _select_music = staticmethod(_select_music)
    _set_hotspot = staticmethod(_set_hotspot)
    _set_tag = staticmethod(_set_tag)
    _set_location_tag = staticmethod(_set_location_tag)
    _set_declaration = staticmethod(_set_declaration)

    platform_id = 3
    platform_key = "douyin"
    platform_name = "抖音"
    supports_image = True  # 图集发布能力（A4 门控）

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    # 抖音 cookie 全部由 .douyin.com 域下发，覆盖 creator.douyin.com 子域
    platform_cookie_domain = ".douyin.com"

    # ------------------------------------------------------------------
    # login — QR code scan via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Douyin login.

        直接打开 ``https://creator.douyin.com/``，由用户在浏览器里扫码完成
        登录。后端通过监听主框架 URL 变化判断登录成功（不设超时，浏览器由
        用户自己关），随后抓取用户资料并落库。不再提取/推送二维码——前端
        只等 ``status:200``。
        """
        url_changed_event = asyncio.Event()

        async def _on_url_change():
            if page.url != original_url:
                url_changed_event.set()

        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto("https://creator.douyin.com/")
                original_url = page.url

                # Monitor URL change via framenavigated
                page.on(
                    "framenavigated",
                    lambda frame: asyncio.create_task(_on_url_change())
                    if frame == page.main_frame
                    else None,
                )

                # 不设超时——扫码登录可能耗时几分钟，浏览器由用户自己关
                await url_changed_event.wait()
                logger.info("Page navigation detected — login successful")

                # Scrape profile & save via shared utility
                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_user_profile,
                    account_id=account_id,
                    # 登录成功后在同一个 session 内补抓 stats(关注/粉丝/获赞),
                    # 与 sync_profile 共用同一份抓取逻辑
                    stats_fn=self._login_stats_fn,
                )
                success = True
            finally:
                # 释放 context 资源
                await context.close()
        finally:
            # 成功才关浏览器（失败/异常时留着让用户看现场）
            if success:
                await self.close_browser(browser)

    # ------------------------------------------------------------------
    # check_cookie — verify stored cookie is still valid
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid.

        Opens ``https://creator.douyin.com/creator-micro/content/upload`` with
        the stored cookies.  If the page shows "扫码登录" within 5 seconds the
        cookie is considered invalid.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(
                    "https://creator.douyin.com/creator-micro/content/upload"
                )
                try:
                    await page.wait_for_url(
                        "https://creator.douyin.com/creator-micro/content/upload",
                        timeout=5000,
                    )
                except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info("cookie check: page did not reach target URL")
                    return False

                # If "扫码登录" is visible the cookie has expired
                try:
                    await page.get_by_text("扫码登录").wait_for(timeout=5000)
                    logger.info("cookie check: 扫码登录 visible — cookie invalid")
                    return False
                except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info("cookie check: no login prompt — cookie valid")
                    return True
            finally:
                await context.close()
        finally:
            await self.close_browser(browser)

    # ------------------------------------------------------------------
    # sync_profile — refresh user name / avatar
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> dict:
        """同步抖音昵称、头像、运营数据(stats)。

        创作中心首页 (creator.douyin.com/) 同一个容器里有
        头像 / 昵称 / 3 项 stats(关注/粉丝/获赞)。
        抖音 CSS-in-JS class 名带 hash 后缀,易变,
        用 .statics-item-MDWoNA 容器 + 文本节点(关注/粉丝/获赞)定位。
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                try:  # noqa: SIM105
                    await page.goto(
                        "https://creator.douyin.com/",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                    pass
                # 等用户卡片渲染(短超时)
                try:
                    await page.wait_for_selector(
                        "[class*='statics-'], [class*='statics-item-']",
                        timeout=8000,
                    )
                except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info("[douyin stats] 等待 statics 超时")

                name, avatar = await scrape_user_profile(page)

                # 抓 3 项 stats(关注/粉丝/获赞),用文本节点匹配而非 id/class hash
                result = await page.evaluate(
                    '''() => {
                        const out = [];
                        document.querySelectorAll('[class*="statics-item-"]').forEach(item => {
                            // textContent 包含 "关注"/"粉丝"/"获赞" + 数字 (在 <span> 里)
                            const spans = item.querySelectorAll('span');
                            if (!spans.length) return;
                            // 取最后一个 span(数字)
                            const numEl = spans[spans.length - 1];
                            const num = (numEl.textContent || '').trim();
                            // textContent 是 label + 数字拼接,识别 label
                            const full = (item.textContent || '').trim();
                            let label = '';
                            if (full.startsWith('关注')) label = '关注';
                            else if (full.startsWith('粉丝')) label = '粉丝';
                            else if (full.startsWith('获赞')) label = '获赞';
                            if (label && num) {
                                out.push({label, num});
                            }
                        });
                        return out;
                    }'''
                )

                label_map = {
                    "关注": ("follow", 1, "关注"),
                    "粉丝": ("user",   2, "粉丝"),
                    "获赞": ("like",   3, "获赞"),
                }
                stats = []
                for item in (result or []):
                    lbl = item.get('label', '')
                    num_str = str(item.get('num', '0'))
                    if lbl in label_map:
                        icon, sort_no, std_name = label_map[lbl]
                        try:
                            count = int(num_str.replace(',', '').replace(' ', '') or '0')
                        except (ValueError, TypeError):
                            count = 0
                        stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})

                if not name and not avatar and not stats:
                    logger.info(f"[douyin] sync_profile 抓取为空,url={page.url}")

                return {"name": name, "avatar": avatar, "stats": stats}
            finally:
                await context.close()
        finally:
            await self.close_browser(browser)

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口(供 save_login_result 调用)。

        与 sync_profile 内部共用同一份 evaluate 抓取逻辑。
        """
        try:
            await page.wait_for_selector(
                "[class*='statics-item-']",
                timeout=8000,
            )
        except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info("[douyin login] 等待 statics 超时")

        result = await page.evaluate(
            '''() => {
                const out = [];
                document.querySelectorAll('[class*="statics-item-"]').forEach(item => {
                    const spans = item.querySelectorAll('span');
                    if (!spans.length) return;
                    const numEl = spans[spans.length - 1];
                    const num = (numEl.textContent || '').trim();
                    const full = (item.textContent || '').trim();
                    let label = '';
                    if (full.startsWith('关注')) label = '关注';
                    else if (full.startsWith('粉丝')) label = '粉丝';
                    else if (full.startsWith('获赞')) label = '获赞';
                    if (label && num) out.push({label, num});
                });
                return out;
            }'''
        )

        label_map = {
            "关注": ("follow", 1, "关注"),
            "粉丝": ("user",   2, "粉丝"),
            "获赞": ("like",   3, "获赞"),
        }
        stats = []
        for item in (result or []):
            lbl = item.get('label', '')
            num_str = str(item.get('num', '0'))
            if lbl in label_map:
                icon, sort_no, std_name = label_map[lbl]
                try:
                    count = int(num_str.replace(',', '').replace(' ', '') or '0')
                except (ValueError, TypeError):
                    count = 0
                stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})
        return stats

    # ------------------------------------------------------------------
    # open_creator_center — visible browser window (sync CloakBrowser)
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Douyin creator centre in a visible browser window.

        打开后立即返回，不做任何等待或关闭 —— 浏览器由用户自己关。
        线程仅负责启动浏览器，启动完就结束（browser 对象保留在闭包里，
        CloakBrowser 子进程会随主进程存活）。
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://creator.douyin.com/"

        def _launch():
            browser = self.create_browser_sync(headless=False)
            context = self.create_context_sync(browser, storage_state=cookie_path)
            page = context.new_page()
            page.goto(url)

        thread = threading.Thread(target=_launch, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # publish_video — full Douyin upload pipeline
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to Douyin via CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
        - ``tags`` (*list[str]*) -- hashtags
        - ``activities`` (*list[str]*, optional) -- official activities (appended as #tags to description)
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``category`` (*int*, optional)
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``thumbnail_landscape_path`` (*str*, optional)
        - ``thumbnail_portrait_path`` (*str*, optional)
        - ``productLink`` (*str*, optional)
        - ``productTitle`` (*str*, optional)
        - ``desc`` (*str*, optional) -- 描述里的 ``#xxx`` 会计入话题总数,
          与 ``tags``、官方活动 ``activities`` 合并上限 5 个,超过将被前置校验拦截。
        - ``schedule_time_str`` (*str*, optional)
        - ``ai_content`` (*str*, optional)
        """
        logger.info("=" * 60)
        logger.info("[发布视频] 开始抖音视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        activities = kwargs.get("activities", []) or []

        # ===== 前置校验:话题总数 ≤ 5(描述里的 #xxx + 标签 + 官方活动) =====
        desc = kwargs.get("desc", "") or ""
        ok, err = self._validate_publish_params(desc, tags, activities)
        if not ok:
            logger.error("[发布视频] 抖音前置校验失败: %s", err)
            raise ValueError(err)

        account_file = kwargs.get("account_file", [])
        enableTimer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path", "")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path", "")
        product_link = kwargs.get("productLink", "")
        product_title = kwargs.get("productTitle", "")
        schedule_time_str = kwargs.get("schedule_time_str", "")
        ai_content = kwargs.get("ai_content", "")
        hotspot = kwargs.get("hotspot", "")
        tag_type = kwargs.get("tag_type", "")
        tag_value = kwargs.get("tag_value", "")
        mini_link = kwargs.get("mini_link", "")
        mix_id = kwargs.get("mix_id", "")

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 定时发布: %s", enableTimer)
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")
        logger.info("[发布参数] 商品链接: %s (标题: %s)", product_link or "无", product_title or "无")
        logger.info("[发布参数] 合集ID: %s", mix_id or "无")
        logger.info("[发布参数] 热点词: %s", hotspot or "无")
        logger.info("[发布参数] AI内容声明: %s", ai_content or "无")

        # Resolve full paths
        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        # files 已是绝对路径（app.py 通过 _resolve_material_path 处理过）
        file_paths = [str(f) for f in files]
        if thumbnail_landscape_path:
            # thumbnail_landscape_path 已是绝对路径
            thumbnail_landscape_path = str(thumbnail_landscape_path)
        if thumbnail_portrait_path:
            # thumbnail_portrait_path 已是绝对路径
            thumbnail_portrait_path = str(thumbnail_portrait_path)

        # Determine publish strategy and schedule times
        publish_strategy = (
            DOUYIN_PUBLISH_STRATEGY_SCHEDULED
            if enableTimer and schedule_time_str
            else DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
        )
        logger.info("[发布策略] 发布策略: %s", publish_strategy)
        if schedule_time_str:
            logger.info("[发布策略] 定时发布时间: %s", schedule_time_str)

        publish_datetimes = parse_schedule_time(
            schedule_time_str,
            len(file_paths),
            enableTimer,
            videos_per_day,
            daily_times,
            start_days,
        )

        for file_index, file_path in enumerate(file_paths):
            logger.info("-" * 40)
            logger.info("[发布进度] 处理第 %d/%d 个视频: %s", file_index + 1, len(file_paths), file_path)
            for cookie_index, cookie_path in enumerate(account_paths):
                cookie_name = Path(cookie_path).name
                nick = get_account_name_by_cookie_file(cookie_name)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
                    await self._upload_one_video(
                        title=title,
                        file_path=file_path,
                        tags=tags,
                        publish_date=publish_datetimes[file_index],
                        account_file=cookie_path,
                        publish_strategy=publish_strategy,
                        activities=activities,
                        thumbnail_landscape_path=thumbnail_landscape_path or None,
                        thumbnail_portrait_path=thumbnail_portrait_path or None,
                        product_link=product_link,
                        product_title=product_title,
                        desc=desc,
                        ai_content=ai_content,
                        hotspot=hotspot,
                        tag_type=tag_type,
                        tag_value=tag_value,
                        mini_link=mini_link,
                        mix_id=mix_id,
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)
        return True

    # ------------------------------------------------------------------
    # Internal helpers (ported from DouYinVideo / DouYinBaseUploader)
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        publish_strategy: str,
        activities: list | None = None,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        product_link="",
        product_title="",
        desc="",
        ai_content="",
        hotspot="",
        tag_type="",
        tag_value="",
        mini_link="",
        mix_id="",
    ):
        """Upload a single video to one Douyin account."""
        logger.info("[上传视频] 开始上传视频: %s", file_path)
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser, storage_state=account_file
            )
            try:
                await context.grant_permissions(["geolocation"])
                page = await context.new_page()
                logger.info("[上传视频] 正在打开发布页面...")
                await page.goto(
                    "https://creator.douyin.com/creator-micro/content/upload"
                )
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/upload"
                )
                logger.info("[上传视频] 发布页面已打开")

                # Upload video file
                logger.info("[上传视频] 正在上传视频文件...")
                await page.locator(
                    "div[class^='container'] input"
                ).set_input_files(file_path)
                logger.info("[上传视频] 视频文件已选择，等待上传完成...")

                # Wait for redirect to publish page (version 1 or version 2)
                while True:
                    try:
                        await page.wait_for_url(
                            "https://creator.douyin.com/creator-micro/content/publish?enter_from=publish_page",
                            timeout=3000,
                        )
                        break
                    except Exception:  # noqa: BLE001 -- 捕获后恢复默认状态,防御性编码
                        try:
                            await page.wait_for_url(
                                "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
                                timeout=3000,
                            )
                            break
                        except Exception:  # noqa: BLE001 -- 捕获后恢复默认状态,防御性编码
                            await asyncio.sleep(0.5)

                await asyncio.sleep(1)

                # Append activities as hashtags to description (与图文发布一致)
                if activities:
                    activity_tags = " ".join([f"#{act}" for act in activities])
                    desc = f"{desc or title} {activity_tags}".strip()

                # Fill title, description, tags
                logger.info("[填写标题] 开始填写标题与简介...")
                await self._fill_title_and_description(
                    page, title, desc or title, tags
                )
                logger.info("[填写标题] 标题与简介填写完成")
                logger.info("[填写标题] 标题: %s", title)

                # Wait for upload to complete
                while True:
                    try:
                        number = await page.locator(
                            '[class^="long-card"] div:has-text("重新上传")'
                        ).count()
                        if number > 0:
                            break
                        await asyncio.sleep(2)
                        if await page.locator(
                            'div.progress-div > div:has-text("上传失败")'
                        ).count():
                            logger.warning("[上传视频] 上传失败，正在重试")
                            await page.locator(
                                "div.progress-div [class^='upload-btn-input']"
                            ).set_input_files(file_path)
                    except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                        await asyncio.sleep(2)
                logger.info("[上传视频] 视频上传成功!")

                # Set product link
                if product_link and product_title:
                    logger.info("[商品链接] 开始设置商品链接: %s", product_link)
                    await self._set_product_link(page, product_link, product_title)

                # Set thumbnail / cover
                logger.info("[设置封面] 开始设置视频封面...")
                await set_thumbnail(
                    page,
                    get_params("douyin", "THUMBNAIL"),
                    paths={
                        "landscape": thumbnail_landscape_path,
                        "portrait": thumbnail_portrait_path,
                    },
                )
                logger.info("[设置封面] 封面设置完成")

                # Toggle third-party content switch
                third_part_element = (
                    '[class^="info"] > [class^="first-part"] div div.semi-switch'
                )
                if (
                    await page.locator(third_part_element).count()
                    and "semi-switch-checked" not in await page.eval_on_selector(
                        third_part_element, "div => div.className"
                    )
                ):
                    await page.locator(
                        third_part_element
                    ).locator("input.semi-switch-native-control").click()

                
                # Set mix/collection if provided (与图文发布一致)
                if mix_id:
                    logger.info("[设置合集] 开始设置合集: %s", mix_id)
                    await self._set_image_mix(page, mix_id)

                # Set AI content declaration
                if ai_content:
                    logger.info("[内容声明] 开始设置AI内容声明: %s", ai_content)
                    await self._set_declaration(page, ai_content)


                # Set tag (位置/小程序/游戏手柄/标记万物) if provided (与图文发布一致)
                if tag_type and tag_value:
                    logger.info("[设置标签] 开始设置标签: 类型=%s, 值=%s, 小程序链接=%s", tag_type, tag_value, mini_link)
                    await self._set_tag(page, tag_type, tag_value, mini_link)


                # Set hotspot if provided (与图文发布一致)
                if hotspot:
                    logger.info("[设置热点] 开始设置热点词: %s", hotspot)
                    await self._set_hotspot(page, hotspot)

                # Schedule if needed
                if (
                    publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED
                    and publish_date != 0
                ):
                    logger.info("[定时发布] 开始设置定时发布...")
                    await set_schedule(page, publish_date, get_params("douyin", "SCHEDULE"))
                    logger.info("[定时发布] 定时发布设置完成")

                # 调试:输出本次发布的全部参数(便于人工核对填写是否正确)
                logger.info("=" * 60)
                logger.info("[发布调试] ===== 本次发布参数汇总 (dry_run=%s) =====", _PUBLISH_DRY_RUN)
                logger.info("[发布调试] 标题(title)       : %s", title)
                logger.info("[发布调试] 视频文件(file_path): %s", file_path)
                logger.info("[发布调试] 描述(desc)        : %s", desc[:100] if desc else "(无)")
                logger.info("[发布调试] 标签(tags)        : %s (共 %d 个)", tags, len(tags))
                logger.info("[发布调试] 横版封面(landscape): %s", thumbnail_landscape_path or "(无)")
                logger.info("[发布调试] 竖版封面(portrait) : %s", thumbnail_portrait_path or "(无)")
                logger.info("[发布调试] 发布策略(strategy): %s", publish_strategy)
                logger.info("[发布调试] 定时时间(publish_date): %s", publish_date)
                logger.info("[发布调试] 官方活动(activities): %s", activities or "(无)")
                logger.info("[发布调试] 热点(hotspot)     : %s", hotspot or "(无)")
                logger.info("[发布调试] 标签类型(tag_type): %s", tag_type or "(无)")
                logger.info("[发布调试] ========================================")
                logger.info("=" * 60)

                if _PUBLISH_DRY_RUN:
                    logger.warning("[发布调试] DRY_RUN 已开启 —— 跳过实际点击发布,流程到此结束(不发布)")
                    logger.info("[发布调试] DRY_RUN: 浏览器保持打开,等待你手动关闭窗口后再结束...")
                    try:
                        while browser.is_connected():
                            await asyncio.sleep(1)
                        logger.info("[发布调试] 检测到浏览器已关闭,流程结束")
                    except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                        pass
                    return

                # Click publish and wait for redirect
                logger.info("[发布] 正在点击发布按钮...")
                while True:
                    try:
                        publish_button = page.get_by_role(
                            "button", name="发布", exact=True
                        )
                        if await publish_button.count():
                            await publish_button.click()
                        await page.wait_for_url(
                            "https://creator.douyin.com/creator-micro/content/manage**",
                            timeout=3000,
                        )
                        logger.info("[发布] 视频发布成功! 页面跳转到: %s", page.url)
                        break
                    except Exception:  # noqa: BLE001 -- 捕获后恢复默认状态,防御性编码
                        # Maybe a cover selection is required
                        await self._handle_auto_video_cover(page)
                        await asyncio.sleep(0.5)

                # Save updated cookie state
                await context.storage_state(path=account_file)
                logger.info("[发布] Cookie状态已更新")
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)
