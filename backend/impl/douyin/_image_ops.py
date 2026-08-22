"""抖音平台 — 图集(图文笔记)发布子模块（A8 拆分）。

从 platform.py 拆出的 publish_image 流程 mixin: 图集发布编排 +
图片 DOM 操作。仅依赖 self 基类能力与 _dom_ops 绑定方法(MRO 解析),
不与 platform.py 互相引用(避免循环导入)。
"""
import asyncio
from pathlib import Path
from typing import Any

from conf import BASE_DIR
from util._logger import bind_account_name, get_channel_logger

from .._utils import get_account_name_by_cookie_file, parse_schedule_time
from ..primitives import get_params, set_schedule

logger = get_channel_logger("douyin")

class DouyinImageOps:
    # A8 拆分: 下列成员由宿主平台类绑定(_dom_ops staticmethod)或
    # BasePlatform 提供,经 MRO 运行时可达;此处仅作 mypy 类型声明(Any 放宽),
    # 不产生运行时属性(纯注解)。
    _select_music: Any
    _set_declaration: Any
    _set_hotspot: Any
    _set_image_cover: Any
    _set_image_mix: Any
    _set_tag: Any
    close_browser: Any
    create_browser: Any
    create_context: Any


    async def publish_image(self, **kwargs) -> bool:
            """Publish an image note to Douyin via CloakBrowser.

            Accepted keyword arguments:

            - ``title`` (*str*) -- note title (max 20 chars)
            - ``files`` (*list[str]*) -- image absolute file paths (resolved by image_publish_bp)
            - ``tags`` (*list[str]*) -- hashtags
            - ``account_file`` (*list[str]*) -- cookie file names
            - ``desc`` (*str*, optional) -- description (max 1000 chars)
            - ``cover_path`` (*str*, optional) -- cover image file name
            - ``mix_id`` (*str*, optional) -- mix/collection ID
            - ``music_name`` (*str*, optional) -- music name to search and select
            - ``hotspot`` (*str*, optional) -- hotspot keyword to search and select
            - ``tag_type`` (*str*, optional) -- tag type: 'location' | 'miniapp' | 'gamepad' | 'mark'
            - ``tag_value`` (*str*, optional) -- tag value (keyword or link)
            - ``mini_link`` (*str*, optional) -- mini app link (for miniapp type)
            - ``enableTimer`` (*bool*, optional)
            - ``schedule_time_str`` (*str*, optional)
            - ``ai_content`` (*str*, optional) -- AI content declaration
            - ``activities`` (*list[str]*, optional) -- official activities (appended as #tags)
            - ``dry_run`` (*bool*, optional) -- if True, skip publish button click (default True)
            """
            logger.info("=" * 60)
            logger.info("[发布图集] 开始抖音图集发布流程")
            logger.info("=" * 60)

            # 打印所有接收到的参数
            logger.info("[发布参数] 接收到的所有参数:")
            for key, value in kwargs.items():
                logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

            title = kwargs.get("title", "")
            files = kwargs.get("files", [])
            tags = kwargs.get("tags", []) or []
            account_file = kwargs.get("account_file", [])
            desc = kwargs.get("desc", "")
            cover_path = kwargs.get("cover_path", "")
            mix_id = kwargs.get("mix_id", "")
            music_name = kwargs.get("music_name", "")
            hotspot = kwargs.get("hotspot", "")
            tag_type = kwargs.get("tag_type", "")
            tag_value = kwargs.get("tag_value", "")
            mini_link = kwargs.get("mini_link", "")
            enable_timer = kwargs.get("enableTimer", False)
            schedule_time_str = kwargs.get("schedule_time_str", "")
            ai_content = kwargs.get("ai_content", "")
            activities = kwargs.get("activities", []) or []
            dry_run = kwargs.get("dry_run", True)  # Default to dry run for safety

            # 打印发布参数摘要
            logger.info("[发布参数] 标题: %s", title)
            logger.info("[发布参数] 图片数量: %d", len(files))
            logger.info("[发布参数] 标签: %s", tags)
            logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
            logger.info("[发布参数] 账号数量: %d", len(account_file))
            logger.info("[发布参数] 封面: %s", cover_path or "无")
            logger.info("[发布参数] 合集ID: %s", mix_id or "无")
            logger.info("[发布参数] 音乐: %s", music_name or "无")
            logger.info("[发布参数] 热点词: %s", hotspot or "无")
            logger.info("[发布参数] 定时发布: %s", enable_timer)
            logger.info("[发布参数] AI内容声明: %s", ai_content or "无")
            logger.info("[发布策略] 模式: %s", "演练(dry_run)" if dry_run else "正式发布")

            # Resolve full paths
            account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
            # files 已是绝对路径（image_publish_bp 通过 _resolve_material_path 处理过）
            file_paths = [str(f) for f in files]

            # cover_path 已是绝对路径，无需拼接
            if cover_path and not Path(cover_path).is_file():
                logger.warning("[发布参数] 封面文件不存在: %s", cover_path)
                cover_path = ""

            # Append activities as hashtags to description
            if activities:
                activity_tags = " ".join([f"#{act}" for act in activities])
                desc = f"{desc} {activity_tags}".strip()

            for cookie_index, cookie_path in enumerate(account_paths):
                cookie_name = Path(cookie_path).name
                nick = get_account_name_by_cookie_file(cookie_name)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
                    await self._upload_image_note(
                        title=title,
                        file_paths=file_paths,
                        tags=tags,
                        account_file=cookie_path,
                        desc=desc,
                        cover_path=cover_path,
                        mix_id=mix_id,
                        music_name=music_name,
                        hotspot=hotspot,
                        tag_type=tag_type,
                        tag_value=tag_value,
                        mini_link=mini_link,
                        enable_timer=enable_timer,
                        schedule_time_str=schedule_time_str,
                        ai_content=ai_content,
                        dry_run=dry_run,
                    )

            logger.info("=" * 60)
            logger.info("[发布图集] 图集发布流程完成!")
            logger.info("=" * 60)
            return True

    async def _upload_image_note(
            self,
            title: str,
            file_paths: list,
            tags: list,
            account_file: str,
            desc: str = "",
            cover_path: str = "",
            mix_id: str = "",
            music_name: str = "",
            hotspot: str = "",
            tag_type: str = "",
            tag_value: str = "",
            mini_link: str = "",
            enable_timer: bool = False,
            schedule_time_str: str = "",
            ai_content: str = "",
            dry_run: bool = True,
        ):
            """Upload image note to one Douyin account."""
            logger.info("[上传图集] 开始上传图集 (%d 张图片)", len(file_paths))
            browser = await self.create_browser(headless=False)
            try:
                context = await self.create_context(browser, storage_state=account_file)
                try:
                    await context.grant_permissions(["geolocation"])
                    page = await context.new_page()

                    # Navigate to image upload page
                    # 抖音创作者中心是 SPA，永远不会触发 load 事件。
                    # 用 domcontentloaded + URL 匹配即可，避免 30s 等待
                    logger.info("[上传图集] 正在打开图集上传页面...")
                    await page.goto(
                        "https://creator.douyin.com/creator-micro/content/upload?default-tab=3",
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    await page.wait_for_url(
                        "https://creator.douyin.com/creator-micro/content/upload?default-tab=3",
                        timeout=60000,
                    )
                    logger.info("[上传图集] 图集上传页面已打开")

                    # Upload images via hidden input
                    logger.info("[上传图集] 正在上传 %d 张图片...", len(file_paths))
                    file_input = page.locator("div[class^='container'] input[type='file']")
                    await file_input.set_input_files(file_paths)

                    # Wait for redirect to image publish page
                    logger.info("[上传图集] 等待跳转到发布页面...")
                    max_wait = 120  # seconds - longer timeout for many images
                    start_time = asyncio.get_running_loop().time()
                    while (asyncio.get_running_loop().time() - start_time) < max_wait:
                        current_url = page.url
                        if "content/upload" not in current_url:
                            logger.info("[上传图集] 已跳转到: %s", current_url)
                            break
                        await asyncio.sleep(1)
                    else:
                        logger.warning("[上传图集] 等待跳转超时")

                    # Wait for all images to upload successfully
                    # Calculate timeout based on image count: 30s per image, min 120s, max 600s
                    upload_timeout_per_image = 30
                    max_upload_wait = max(120, min(len(file_paths) * upload_timeout_per_image, 600))
                    logger.info("[上传图集] 等待全部 %d 张图片上传完成 (超时: %ds)...", len(file_paths), max_upload_wait)
                    uploaded_count = 0
                    upload_start = asyncio.get_running_loop().time()
                    while (asyncio.get_running_loop().time() - upload_start) < max_upload_wait:
                        # Check for uploaded image count in the UI
                        image_items = page.locator('div[class*="img-"][draggable="true"]')
                        uploaded_count = await image_items.count()
                        logger.info("[上传图集] 已上传图片: %d/%d", uploaded_count, len(file_paths))
                        if uploaded_count >= len(file_paths):
                            logger.info("[上传图集] 全部 %d 张图片上传成功!", len(file_paths))
                            break
                        await asyncio.sleep(3)
                    else:
                        logger.warning("[上传图集] 等待图片上传超时. 已上传: %d/%d", uploaded_count, len(file_paths))

                    await asyncio.sleep(5)  # 等待更长时间确保页面加载完成

                    # 逐字输入标题
                    logger.info("[填写标题] 开始填写标题: %s", title[:20])
                    title_input = page.get_by_placeholder("添加作品标题")
                    await title_input.wait_for(state="visible", timeout=10000)
                    await title_input.click()
                    await title_input.fill('')
                    await page.keyboard.type(title[:20])

                    # 逐字输入描述，一次性注入标签
                    logger.info("[填写简介] 开始填写简介与标签...")
                    desc_editor = page.locator(
                        'div[data-zone-container="*"][contenteditable="true"]'
                    ).first
                    await desc_editor.wait_for(state="visible", timeout=10000)
                    await desc_editor.click()
                    await page.keyboard.press("Control+KeyA")
                    await page.keyboard.press("Delete")

                    await page.keyboard.type(desc[:1000])
                    await asyncio.sleep(0.2)

                    for tag in tags:
                        await page.keyboard.insert_text(" #" + tag)
                        await page.keyboard.press("Space")
                    await asyncio.sleep(0.3)

                    # Set cover if provided
                    if cover_path:
                        logger.info("[设置封面] 开始设置封面图片...")
                        await self._set_image_cover(page, cover_path)

                    # Set mix/collection if provided
                    if mix_id:
                        logger.info("[设置合集] 开始设置合集: %s", mix_id)
                        await self._set_image_mix(page, mix_id)

                    # Set music if provided
                    if music_name:
                        logger.info("[选择音乐] 开始选择音乐: %s", music_name)
                        await self._select_music(page, music_name)

                    # Set hotspot if provided
                    if hotspot:
                        logger.info("[设置热点] 开始设置热点词: %s", hotspot)
                        await self._set_hotspot(page, hotspot)

                    # Set tag (位置/小程序/游戏手柄/标记万物) if provided
                    if tag_type and tag_value:
                        logger.info("[设置标签] 开始设置标签: 类型=%s, 值=%s, 小程序链接=%s", tag_type, tag_value, mini_link)
                        await self._set_tag(page, tag_type, tag_value, mini_link)

                    # Set AI content declaration
                    if ai_content:
                        logger.info("[内容声明] 开始设置内容声明: %s", ai_content)
                        await self._set_declaration(page, ai_content)

                    # Set schedule time if needed
                    if enable_timer and schedule_time_str:
                        publish_date = parse_schedule_time(
                            schedule_time_str, 1, enable_timer, 1, None, 0
                        )[0]
                        if publish_date != 0:
                            logger.info("[定时发布] 开始设置定时发布...")
                            await set_schedule(page, publish_date, get_params("douyin", "SCHEDULE"))
                            logger.info("[定时发布] 定时发布设置完成")

                    logger.info("[填写完成] 表单填写完成, 模式: %s", "演练(dry_run)" if dry_run else "正式发布")

                    if not dry_run:
                        # Click publish button
                        # 使用稳定的文本匹配：精确匹配"发布"按钮，排除"暂存离开"
                        logger.info("[发布] 正在点击发布按钮...")
                        publish_btn = page.get_by_role("button", name="发布", exact=True)
                        await publish_btn.wait_for(state="visible", timeout=10000)
                        await publish_btn.click()
                        logger.info("[发布] 发布按钮已点击, 等待页面跳转...")

                        # 等待页面跳转 - 跳转到 manage 页面才是发布成功
                        try:
                            await page.wait_for_url(
                                "https://creator.douyin.com/creator-micro/content/manage*",
                                timeout=60000
                            )
                            logger.info("[发布] 图集发布成功! 已跳转到管理页面")
                        except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                            # 检查当前URL
                            current_url = page.url
                            if "content/manage" in current_url:
                                logger.info("[发布] 图集发布成功! 已在管理页面")
                            else:
                                logger.warning("[发布] 图集发布可能失败 - 当前URL: %s", current_url)

                        # Save cookie state
                        await context.storage_state(path=account_file)
                        logger.info("[发布] Cookie状态已更新")
                    else:
                        # Dry run mode - simulate publish
                        logger.info("=" * 40)
                        logger.info("[发布] [演练模式] 模拟点击发布! 发布成功!")
                        logger.info("=" * 40)

                finally:
                    await context.close()
            finally:
                await self.close_browser(browser, is_close_by_code=True)
