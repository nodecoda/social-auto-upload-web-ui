"""微信公众号平台 — 图集发布子模块（A8 拆分）。

从 platform.py 拆出的 publish_image 流程 mixin: 图集发布编排 +
图片 DOM 操作。仅依赖 self 基类能力与 _dom_ops 绑定方法(MRO 解析),
不与 platform.py 互相引用(避免循环导入)。
"""
import asyncio
from pathlib import Path
from typing import Any

from conf import BASE_DIR
from util._logger import bind_account_name, get_channel_logger

from .._utils import get_account_name_by_cookie_file

logger = get_channel_logger("weixin_gzh")

class WeixinGzhImageOps:
    # A8 拆分: 下列成员由 WeixinGzhPlatform 类绑定(_dom_ops staticmethod)或
    # BasePlatform 提供,经 MRO 在运行时可达;此处仅作 mypy 类型声明(Any 放宽),
    # 不产生运行时属性(纯注解)。
    create_browser: Any
    create_context: Any
    close_browser: Any
    _resolve_token: Any
    _build_home_url: Any
    _fill_publish_title: Any
    _fill_description: Any
    _set_collection: Any
    _set_claim_source: Any
    _build_publish_datetime: Any
    _publish_scheduled: Any
    _publish_immediate: Any
    _IMAGE_MENU_TEXT = "贴图"
    _IMAGE_TITLE_MAX = 20
    _IMAGE_DESC_MAX = 1000

    async def publish_image(self, **kwargs) -> bool:
            """发布图集(贴图)到公众号（R6 起 async）。

            流程: 创作中心首页点「贴图」→ 新 tab(appmsg_edit_v2 type=77)
            → 上传多图 → 复用 video 的标题/描述/合集/创作来源/发表 helpers。

            入口仅做 dry-run 早返回 + 调 _upload_all_images。
            """
            dry_run = kwargs.get("dry_run", False)
            if dry_run:
                logger.info("[发布图集] dry-run 模式, 跳过实际发布 (publish_image)")
                return True
            await self._upload_all_images(**kwargs)
            return True

    async def _upload_all_images(self, **kwargs):
            """图集编排:**单层账号循环**(一账号一次发完所有图),非笛卡尔积。"""
            logger.info("=" * 60)
            logger.info("[发布图集] 开始微信公众号图集发布流程")
            logger.info("=" * 60)

            logger.info("[发布参数] 接收到的所有参数:")
            for key, value in kwargs.items():
                logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

            files = kwargs.get("files", []) or []
            account_file = kwargs.get("account_file", []) or []
            title = kwargs.get("title", "")
            tags = kwargs.get("tags", []) or []
            desc = kwargs.get("desc", "") or ""
            is_original = kwargs.get("is_original", False)
            gzh_collection_name = kwargs.get("gzh_collection_name", "") or ""
            gzh_claim_source = kwargs.get("gzh_claim_source", "") or ""
            enable_timer = kwargs.get("enableTimer", False)
            schedule_time_str = kwargs.get("schedule_time_str", "")

            # 忽略字段(公众号图集不支持)
            _ = kwargs.get("cover_path")
            _ = kwargs.get("music_name")
            _ = kwargs.get("ai_content")

            logger.info("[发布参数] 标题: %s", title)
            logger.info("[发布参数] 图片数量: %d", len(files))
            logger.info("[发布参数] 标签: %s", tags)
            logger.info("[发布参数] 描述: %s", desc[:50] if desc else "无")
            logger.info("[发布参数] 账号数量: %d", len(account_file))
            logger.info("[发布参数] 原创: %s", is_original)
            logger.info("[发布参数] 合集: %s", gzh_collection_name or "无")
            logger.info("[发布参数] 创作来源: %s", gzh_claim_source or "无")

            file_path_list = [str(f) for f in files]
            account_paths = [str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file]

            for cookie_index, cookie_path in enumerate(account_paths):
                cookie_name = Path(cookie_path).name
                nick = get_account_name_by_cookie_file(cookie_name)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
                    await self._upload_one_image(
                        title=title,
                        file_path_list=file_path_list,
                        tags=tags,
                        account_file=cookie_path,
                        desc=desc,
                        is_original=is_original,
                        gzh_collection_name=gzh_collection_name,
                        gzh_claim_source=gzh_claim_source,
                        enable_timer=enable_timer,
                        schedule_time_str=schedule_time_str,
                    )

            logger.info("=" * 60)
            logger.info("[发布图集] 图集发布流程完成!")
            logger.info("=" * 60)

    async def _upload_one_image(
            self,
            title: str,
            file_path_list: list,
            tags: list,
            account_file: str,
            desc: str = "",
            is_original: bool = False,
            gzh_collection_name: str = "",
            gzh_claim_source: str = "",
            enable_timer: bool = False,
            schedule_time_str: str = "",
        ):
            """单账号图集发布完整流程。

            与 video 的区别:图集只有一阶段 —— 创作中心首页点「贴图」直接进
            appmsg_edit_v2(type=77)编辑页,在该页上传图片 + 填写 + 发表。
            video 的素材上传页(videomsg_edit)→保存并发表→新 tab 两阶段,
            图集直接进编辑页,更简单。

            复用 video 的阶段②helpers(标题/描述/合集/创作来源/发表/定时)。
            """
            logger.info("[上传图集] 开始上传图集 (%d 张图片)", len(file_path_list))
            browser = await self.create_browser(headless=False)
            try:
                context = await self.create_context(
                    browser,
                    storage_state=account_file,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/127.0.4324.150 Safari/537.36"
                    ),
                )
                try:
                    page = await context.new_page()

                    # 1. 解析 token + 进创作中心首页
                    token = await self._resolve_token(page)
                    if not token:
                        raise RuntimeError("[发布图集] 未能获取 token,cookie 可能已失效")
                    logger.info("[发布图集] 获取到 token: %s", token)
                    home_url = self._build_home_url(token)
                    logger.info("[发布图集] 打开创作中心首页: %s", home_url)
                    await page.goto(home_url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(3)

                    # 2. 点击「贴图」菜单 → 捕获新 tab
                    page2 = await self._click_image_menu(page, context)
                    logger.info("[发布图集] 贴图编辑页已打开: %s", page2.url)
                    await page2.wait_for_load_state("domcontentloaded", timeout=30000)
                    await asyncio.sleep(2)

                    # 3. 上传多图
                    logger.info("[发布图集] 开始上传 %d 张图片...", len(file_path_list))
                    await self._upload_images(page2, file_path_list)
                    logger.info("[发布图集] 图片上传完成!")

                    # 4. 标题(图集≤20字)
                    logger.info("[发布图集] 填写标题: %s", title)
                    await self._fill_publish_title(page2, title, max_len=self._IMAGE_TITLE_MAX)

                    # 5. 描述(图集≤1000字)
                    logger.info("[发布图集] 填写描述/标签...")
                    await self._fill_description(
                        page2, desc, title, tags, max_len=self._IMAGE_DESC_MAX,
                    )

                    # 6. 合集(可选)
                    if gzh_collection_name:
                        logger.info("[发布图集] 选择合集: %s", gzh_collection_name)
                        await self._set_collection(page2, gzh_collection_name)
                    else:
                        logger.info("[发布图集] 未选择合集,跳过")

                    # 7. 创作来源(可选)
                    if gzh_claim_source:
                        logger.info("[发布图集] 设置创作来源: %s", gzh_claim_source)
                        await self._set_claim_source(page2, gzh_claim_source)
                    else:
                        logger.info("[发布图集] 未设置创作来源,跳过")

                    # 8. 发表(立即/定时,与视频完全一致)
                    if enable_timer and schedule_time_str:
                        publish_dt = self._build_publish_datetime(schedule_time_str, 1)
                        if publish_dt and not (isinstance(publish_dt, int) and publish_dt == 0):
                            logger.info("[发布图集] 定时发布: %s", publish_dt)
                            await self._publish_scheduled(page2, publish_dt)
                        else:
                            logger.info("[发布图集] 定时时间解析失败,改为立即发表")
                            await self._publish_immediate(page2)
                    else:
                        logger.info("[发布图集] 立即发表...")
                        await self._publish_immediate(page2)

                    logger.info("[发布图集] 图集发布成功!")

                    # 保存 cookie
                    await context.storage_state(path=account_file)
                    logger.info("[发布图集] Cookie 状态已更新")
                    await asyncio.sleep(2)
                finally:
                    await context.close()
            finally:
                await self.close_browser(browser, is_close_by_code=True)

    async def _click_image_menu(self, page, context):
            """点击创作中心首页的「贴图」菜单,返回打开的新 tab page。

            DOM(用户文档): ``.new-creation__menu-item`` 内 ``.new-creation__menu-title``
            文字为「贴图」。点击后打开新 tab(appmsg_edit_v2 type=77 createType=8)。
            用 context.on("page") 捕获新 tab,过滤 about:blank。
            """
            new_page_holder = {"page": None}

            def _on_new_page(new_page):
                try:
                    url = new_page.url or ""
                except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    url = ""
                logger.info("[发布图集] 检测到新 tab: %s", url or "(about:blank)")
                if "appmsg_edit" in url:
                    new_page_holder["page"] = new_page

            context.on("page", _on_new_page)
            try:
                # 找「贴图」菜单项(用文案定位,避免 svg 路径匹配)
                # 定位含「贴图」文案的菜单标题元素,再点它(或其父级 menu-item)
                menu_title = page.locator(
                    ".new-creation__menu-title",
                    has_text=self._IMAGE_MENU_TEXT,
                ).first
                await menu_title.wait_for(state="visible", timeout=15000)
                # 点击 menu-title 的父级 menu-item(整个卡片可点)
                menu = menu_title.locator("xpath=ancestor::div[contains(@class,'new-creation__menu-item')][1]")
                await menu.wait_for(state="visible", timeout=15000)
                await menu.click()
                logger.info("[发布图集] 已点击「贴图」菜单,等待新 tab...")

                # 轮询等待目标新 tab 导航到 appmsg_edit
                deadline = asyncio.get_running_loop().time() + 30
                target_page = None
                while asyncio.get_running_loop().time() < deadline:
                    if new_page_holder["page"] is not None:
                        target_page = new_page_holder["page"]
                        break
                    # 兜底:从 context.pages 找已导航到 appmsg_edit 的 tab
                    for p in context.pages:
                        try:
                            if p is page:
                                continue
                            if "appmsg_edit" in (p.url or ""):
                                target_page = p
                                new_page_holder["page"] = p
                                break
                        except Exception:  # noqa: S112, BLE001 -- 单次探测失败,跳过继续
                            continue
                    if target_page is not None:
                        break
                    await asyncio.sleep(1)

                if target_page is None:
                    raise RuntimeError("[发布图集] 点击「贴图」后未捕获到编辑页新 tab")
                try:
                    await target_page.wait_for_url("**/appmsg_edit*", timeout=30000)
                except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info("[发布图集] 新 tab URL 等待(非致命): %s, 当前: %s", e, target_page.url)
                await target_page.bring_to_front()
                return target_page
            finally:
                context.remove_listener("page", _on_new_page)

    @staticmethod
    async def _upload_images(page, file_path_list: list):
            """上传多张图片(一次性 set_input_files)。

            贴图编辑页(appmsg_edit_v2 type=77)的图片上传 input(DOM 实测):
              ``.js_upload_btn_container input[type='file'][accept*='image']``
              (带 multiple, style display:none 隐藏但 set_input_files 仍可用)

            一次性把所有图片路径传进去,再等待上传完成(轮询图片预览项数量)。
            """
            if not file_path_list:
                logger.warning("[发布图集] 无图片可上传")
                return

            # 找图片上传 input —— 多选择器兜底
            input_selectors = [
                ".js_upload_btn_container input[type='file']",
                "input[type='file'][accept*='image']",
                "input[type='file'][multiple]",
            ]
            img_input = None
            for sel in input_selectors:
                loc = page.locator(sel).first
                try:
                    await loc.wait_for(state="attached", timeout=8000)
                    img_input = loc
                    logger.info("[发布图集] 找到图片上传 input, 选择器: %s", sel)
                    break
                except Exception:  # noqa: S112, BLE001 -- 单次探测失败,跳过继续
                    continue
            if img_input is None:
                raise RuntimeError("[发布图集] 未找到图片上传 input")

            await img_input.set_input_files(file_path_list)
            logger.info("[发布图集] 已提交 %d 张图片,等待上传...", len(file_path_list))

            # 等待上传完成:已上传的图片项数量达到预期(轮询,最多 5 分钟)
            # 贴图编辑页每张图会生成一个预览项(li/div 含 img 或上传进度条)
            target_count = len(file_path_list)
            deadline = asyncio.get_running_loop().time() + 300
            last_info = ""
            while asyncio.get_running_loop().time() < deadline:
                info = await page.evaluate(
                    """(target) => {
                        // 已上传图片的预览项(公众号贴图页多种可能结构)
                        // 1. 含已上传缩略图的列表项
                        // 2. 上传进度项(上传中)/ 完成项
                        const sels = [
                            '.appmsg_edit_item img',
                            '.js_appmsg_list img',
                            '.weui-desktop-card .appmsg_edit_item',
                            'img[data-src]',
                            '.upload_item',
                        ];
                        let best = 0;
                        for (const sel of sels) {
                            const els = document.querySelectorAll(sel);
                            let visible = 0;
                            for (const el of els) {
                                const r = el.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0) visible++;
                            }
                            if (visible > best) best = visible;
                        }
                        // 上传中检测:是否有进度条/上传中文案
                        const uploading = document.querySelectorAll(
                            '.weui-desktop-upload__file__progress, [class*="upload"][class*="progress"]'
                        ).length;
                        return {best, uploading, target};
                    }""",
                    target_count,
                )
                cur = f"已上传预览={info.get('best', 0)}/目标={target_count} 上传中={info.get('uploading', 0)}"
                if cur != last_info:
                    logger.info("[发布图集] 上传进度: %s", cur)
                    last_info = cur
                # 完成: 预览数达到目标;或(有预览且无上传中=上传已结束)
                best = info.get("best", 0)
                uploading = info.get("uploading", 0)
                if best >= target_count:
                    logger.info("[发布图集] 全部 %d 张图片已上传", target_count)
                    return
                if best > 0 and uploading == 0:
                    logger.info("[发布图集] 上传已结束(预览 %d 张,目标 %d)", best, target_count)
                    return
                await asyncio.sleep(3)
            logger.warning("[发布图集] 图片上传等待超时(可能部分未完成),继续后续操作")
