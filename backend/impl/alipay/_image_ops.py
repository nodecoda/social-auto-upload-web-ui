"""支付宝平台 — 图集发布子模块（A8 拆分）。

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

logger = get_channel_logger("alipay")

_ALIPAY_SHORT_CONTENT_URL = (
    "https://c.alipay.com/page/content-creation/publish/short-content"
)


class AlipayImageOps:
    # A8 拆分: 下列成员由宿主平台类绑定(_dom_ops staticmethod)或
    # BasePlatform 提供,经 MRO 运行时可达;此处仅作 mypy 类型声明(Any 放宽),
    # 不产生运行时属性(纯注解)。
    _click_publish: Any
    _set_author_statement: Any
    _set_description_and_tags: Any
    _set_music: Any
    _set_title: Any
    _upload_images: Any
    _wait_for_image_form: Any
    _wait_for_publish_success: Any
    close_browser: Any
    create_browser: Any
    create_context: Any


    async def publish_image(self, **kwargs) -> bool:
            """支付宝图集发布（R6 起 async，与 publish_video 契约一致）。

            Accepted keyword arguments:

            - ``title`` (*str*)        — 标题(≤30 字)
            - ``files`` (*list[str]*)  — 图片绝对路径列表(多图)
            - ``tags`` (*list[str]*)   — 话题
            - ``account_file`` (*list[str]*) — cookie 文件名列表
            - ``desc`` (*str*)         — 描述
            - ``author_statement`` (*str*) — 作者声明(默认「内容由AI生成」)
            - ``music_title`` (*str*)  — 选中的音乐名(可选)
            - ``music_id`` (*str*)     — 选中的音乐 id(可选,保留)
            """
            await self._upload_all_images(**kwargs)
            return True

    async def _upload_all_images(self, **kwargs):
            """图片集 × 账号 笛卡尔积,每个组合一个 browser。"""
            logger.info("=" * 60)
            logger.info("[发布图集] 开始支付宝图集发布流程")
            logger.info("=" * 60)

            # 打印所有接收到的参数
            logger.info("[发布参数] 接收到的所有参数:")
            for key, value in kwargs.items():
                logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

            title = kwargs.get("title", "")
            files = kwargs.get("files", []) or []
            tags = kwargs.get("tags", []) or []
            account_file = kwargs.get("account_file", []) or []
            desc = kwargs.get("desc", "") or ""
            # 图集作者声明下拉只有「内容由AI生成」一个选项,空则兜底填它
            author_statement = (
                kwargs.get("author_statement", "")
                or kwargs.get("author_declaration", "")
                or "内容由AI生成"
            )
            music_title = kwargs.get("music_title", "") or ""

            # 打印发布参数摘要
            logger.info("[发布参数] 标题: %s", title)
            logger.info("[发布参数] 图片数量: %d", len(files))
            logger.info("[发布参数] 标签: %s", tags)
            logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
            logger.info("[发布参数] 账号数量: %d", len(account_file))
            logger.info("[发布参数] 作者声明: %s", author_statement or "无")
            logger.info("[发布参数] 音乐: %s", music_title or "无")

            account_paths = [
                str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
            ]
            file_paths = [str(f) for f in files]

            for cookie_index, cookie_path in enumerate(account_paths):
                cookie_name = Path(cookie_path).name
                nick = get_account_name_by_cookie_file(cookie_name)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
                    await self._upload_one_image_set(
                        title=title,
                        file_paths=file_paths,
                        tags=tags,
                        account_file=cookie_path,
                        desc=desc,
                        author_statement=author_statement,
                        music_title=music_title,
                    )

            logger.info("=" * 60)
            logger.info("[发布图集] 图集发布流程完成!")
            logger.info("=" * 60)

    async def _upload_one_image_set(
            self,
            title: str,
            file_paths: list,
            tags: list,
            account_file: str,
            desc: str = "",
            author_statement: str = "内容由AI生成",
            music_title: str = "",
        ):
            """一组图片上传到单个账号的完整流程。"""
            logger.info("[上传图集] 开始上传图集 (%d 张图片)", len(file_paths))
            logger.info("[上传图集] 标题: %s", title)
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
                    await page.goto(_ALIPAY_SHORT_CONTENT_URL, timeout=60000)
                    await page.wait_for_load_state("domcontentloaded", timeout=30000)
                    logger.info("[上传图集] 正在上传图片: %s", title)

                    # 1. 上传图片(多图)
                    await self._upload_images(page, file_paths)

                    # 2. 等待表单可交互(标题输入框可见)
                    await self._wait_for_image_form(page)

                    # 3. 填标题
                    await self._set_title(page, title)

                    # 4. 填描述 + 话题
                    await self._set_description_and_tags(page, desc, title, tags)

                    # 5. 音乐(可选)
                    if music_title:
                        await self._set_music(page, music_title)

                    # 6. 作者声明(必填,默认「内容由AI生成」)
                    await self._set_author_statement(page, author_statement)

                    # 7. 点击「确认发布」
                    await self._click_publish(page)

                    # 8. 等待发布成功(图集走 short-content 跳转判据)
                    await self._wait_for_publish_success(page, page_type="image")

                    # 9. 保存 cookie
                    await context.storage_state(path=account_file)
                    logger.info("[上传图集] cookie 已更新")
                    await asyncio.sleep(2)
                finally:
                    await context.close()
            finally:
                await self.close_browser(browser, is_close_by_code=True)
