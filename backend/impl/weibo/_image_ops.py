"""微博平台 — 图集发布子模块（A8 拆分）。

从 platform.py 拆出的 publish_image 流程 mixin: 图集发布编排 +
图片 DOM 操作。仅依赖 self 基类能力与 _dom_ops 绑定方法(MRO 解析),
不与 platform.py 互相引用(避免循环导入)。
"""
import asyncio
from pathlib import Path

from conf import BASE_DIR
from util._logger import bind_account_name, get_channel_logger

from .._utils import get_account_name_by_cookie_file

logger = get_channel_logger("weibo")

class WeiboImageOps:

    async def publish_image(self, **kwargs) -> bool:
            """Publish an image album to Weibo（R6 起 async）。

            入口仅做 kwargs 解包 + dry-run 早返回 + 调 _upload_all_images。
            实际浏览器操作在 _upload_one_image。
            """
            dry_run = kwargs.get("dry_run", False)
            if dry_run:
                logger.info("[发布图集] dry-run 模式, 跳过实际发布 (publish_image)")
                return True
            await self._upload_all_images(**kwargs)
            return True

    async def _upload_all_images(self, **kwargs):
            """Create a browser per account, upload all images in the batch.

            与 video 版 _upload_all 的关键区别:**单层账号循环** (图集是一账号
            一次发完所有图),不是 files × accounts 笛卡尔积。
            """
            logger.info("=" * 60)
            logger.info("[发布图集] 开始微博图集发布流程")
            logger.info("=" * 60)

            # 打印所有接收到的参数
            logger.info("[发布参数] 接收到的所有参数:")
            for key, value in kwargs.items():
                logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

            files = kwargs.get("files", []) or []
            account_file = kwargs.get("account_file", []) or []
            title = kwargs.get("title", "")
            tags = kwargs.get("tags", []) or []
            desc = kwargs.get("desc", "") or ""
            ai_content = kwargs.get("ai_content", "") or ""
            content_statement = kwargs.get("content_statement", "") or ""
            content_statement2 = kwargs.get("content_statement2", "") or ""
            content_statement2_optional = kwargs.get("content_statement2_optional", "") or ""
            # 忽略字段(微博图集不支持)
            # is_original / enableTimer / schedule_time_str / cover_path
            _ = kwargs.get("is_original")
            _ = kwargs.get("enableTimer")
            _ = kwargs.get("schedule_time_str")
            _ = kwargs.get("cover_path")

            # 打印发布参数摘要
            logger.info("[发布参数] 标题: %s", title)
            logger.info("[发布参数] 图片数量: %d", len(files))
            logger.info("[发布参数] 标签: %s", tags)
            logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
            logger.info("[发布参数] 账号数量: %d", len(account_file))
            logger.info("[发布参数] 类型声明: %s", ai_content or "无")

            # 入口校验:微博图集服务端硬上限 18 张
            if len(files) > 18:
                raise ValueError(
                    f"[发布图集] 图集最多 18 张,当前 {len(files)} 张"
                )

            file_path_list = [str(f) for f in files]
            account_paths = [
                str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
            ]

            # 单层账号循环(不是笛卡尔积!)
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
                        ai_content=ai_content,
                        content_statement=content_statement,
                        content_statement2=content_statement2,
                        content_statement2_optional=content_statement2_optional,
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
            ai_content: str = "",
            content_statement: str = "",
            content_statement2: str = "",
            content_statement2_optional: str = "",
        ):
            """Upload one image album to one Weibo account.

            流程:
            1. 创建 browser + context + 走 weibo.com 主页(不是 /upload/channel)
            2. wait_for 创作卡片(发送按钮) — cookie 失效检测
            3. _upload_images 上传多图
            4. _set_description 填正文 + 标签(复用 video 版)
            5. _set_content_statement 选 5 选项内容声明(复用 video 版)
            6. _click_send 点击发送
            7. _wait_for_image_publish_success 等成功信号
            8. 保存 cookie
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
                    # 关键: 走主页而不是 /upload/channel
                    await page.goto("https://weibo.com", timeout=60000)
                    await page.wait_for_load_state("domcontentloaded", timeout=30000)

                    # 关键: wait_for 创作卡片(发送按钮) — cookie 失效/未登录会抛
                    try:
                        await page.get_by_role(
                            "button", name="发送", exact=True
                        ).first.wait_for(state="attached", timeout=15000)
                    except Exception as e:  # 捕获后重新抛出,统一异常出口
                        raise RuntimeError(
                            f"[发布图集] 创作卡片未渲染(cookie 失效/未登录?): {e}"
                        ) from e
                    await asyncio.sleep(2)  # 等图片工具/声明 trigger 完全渲染

                    # 1. 上传图片
                    logger.info("[上传图集] 开始上传图片...")
                    await self._upload_images(page, file_path_list)

                    # 2. 填正文 + 标签
                    logger.info("[填写简介] 开始填写微博正文...")
                    await self._set_description(page, desc, title, tags)

                    # 3. 内容声明 (复用 video 版,自动探测版本1/版本2 UI)
                    # 版本1:优先用 content_statement(前端下拉),为空时回退到
                    # ai_content(兼容旧图集流程把类型声明当内容声明用的历史行为)
                    v1_stmt = content_statement or ai_content
                    logger.info(
                        "[内容声明] 开始设置内容声明: 版本1=%s, 版本2必选=%s, 版本2可选=%s",
                        v1_stmt or "无", content_statement2 or "无", content_statement2_optional or "无",
                    )
                    await self._set_content_statement(
                        page, v1_stmt, content_statement2, content_statement2_optional
                    )

                    # 4. 发送
                    logger.info("[发布] 正在点击发送按钮...")
                    await self._click_send(page)

                    # 5. 等成功信号
                    await self._wait_for_image_publish_success(page)
                    logger.info("[发布] 图集发布成功!")

                    # 6. 保存 cookie
                    await context.storage_state(path=account_file)
                    logger.info("[发布] Cookie状态已更新")
                    await asyncio.sleep(2)
                finally:
                    await context.close()
            finally:
                await self.close_browser(browser, is_close_by_code=True)
