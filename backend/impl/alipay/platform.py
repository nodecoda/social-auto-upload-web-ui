"""支付宝内容创作平台 (Alipay Creator Center) — CloakBrowser 实现。

platform_id = 12
platform_key = "alipay"
platform_name = "支付宝"

关键 URL:
- 创作中心首页(登录/资料抓取): https://c.alipay.com/page/life-account/index
- 视频发布页:                   https://c.alipay.com/page/content-creation/publish/short-video

文档 ``~/zfb.md`` 的强约束:**尽量不要用 CLASS 定位元素**(antd5 + CSS modules
hash 类名会随构建漂移)。本实现优先用 placeholder / role / text / aria /
``label[title]`` 定位,不得已时才用 ``[class*="xxx"]`` 前缀匹配。

发布页表单结构(2026-06-22 抓取):
- 标题:    ``input[placeholder*="好的标题"]`` (≤30 字)
- 描述:    ``textarea.mentions-textarea__input[placeholder*="作品描述"]``
- 话题:    描述区输入 ``#xxx`` → ``.mentions-textarea__suggestions__list`` 弹联想
- 封面:    点击"上传封面"区 → tab 切到"上传封面" → 隐藏 input[type=file] → "完成"
- 合集:    ``input[placeholder*="请选择要加入到的合集"]`` 搜索 → 等
           ``[role="option"]`` 渲染 → 点击 title 匹配项
- 作者声明(必填): ``input#*_tagList`` 父级 antd5-select → ``[role="option"]``
           → 点 title=statement
- 定时发布: ``input[name="publishType"][value="regularly"]`` → antd5-picker 选日期时间
- 发布按钮: ``button`` 文本"确认发布"
"""

import asyncio
import os
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR
from util._logger import bind_account_name, get_channel_logger

from .._browser import close_browser
from .._utils import (
    get_account_name_by_cookie_file,
    save_login_result,
)
from ..base_platform import BasePlatform
from ..primitives import get_params, parse_publish_dt, set_schedule

# A8 拆分后模块级函数 re-export, 兼容 tests/test_alipay_platform_dom.py 导入
from ._dom_ops import (
    _click_publish,
    _set_author_statement,
    _set_compilation,
    _set_cover,
    _set_description_and_tags,
    _set_music,
    _set_reprint_url,
    _set_title,
    _upload_images,
    _upload_video_file,
    _wait_for_image_form,
    _wait_for_publish_success,
    _wait_for_upload_form,
)
from ._image_ops import AlipayImageOps
from ._profile import scrape_alipay_profile

__all__ = ["_parse_schedule_dt"]

# 解析器收编至原语库 parse_publish_dt，此处 re-export 保持向后兼容
_parse_schedule_dt = parse_publish_dt

logger = get_channel_logger("alipay")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALIPAY_CREATOR_URL = "https://c.alipay.com/page/life-account/index"
_ALIPAY_PUBLISH_URL = (
    "https://c.alipay.com/page/content-creation/publish/short-video"
)
# 图集(图文)发布页 — 与视频页 short-video 独立,文档 ~/ZFB-tuji.md


# ======================================================================
# AlipayPlatform
# ======================================================================

class AlipayPlatform(AlipayImageOps, BasePlatform):

    _upload_images = staticmethod(_upload_images)
    _wait_for_image_form = staticmethod(_wait_for_image_form)
    _set_music = staticmethod(_set_music)
    _upload_video_file = staticmethod(_upload_video_file)
    _wait_for_upload_form = staticmethod(_wait_for_upload_form)
    _set_title = staticmethod(_set_title)
    _set_description_and_tags = staticmethod(_set_description_and_tags)
    _set_cover = staticmethod(_set_cover)
    _set_compilation = staticmethod(_set_compilation)
    _set_author_statement = staticmethod(_set_author_statement)
    _set_reprint_url = staticmethod(_set_reprint_url)
    _click_publish = staticmethod(_click_publish)
    _wait_for_publish_success = staticmethod(_wait_for_publish_success)

    supports_image = True  # 图集发布能力（A4 门控）
    # ---- Cookie 校验参数（基类探针 session_verify 使用, 提炼自原 check_cookie）----
    CHECK_URL = "https://c.alipay.com/page/life-account/index"
    CHECK_SLEEP = 0.0
    CHECK_VALID_URL = (
        "c.alipay.com/page/life-account/index",
    )
    platform_id = 12
    platform_key = "alipay"
    platform_name = "支付宝"

    # 支持 cookie 字符串导入账号（支付宝登录态依赖 ctoken 等动态字段 + localStorage，
    # 仅灌 cookie 可能拉不到资料，需用户自行验证）
    supports_cookie_import = True
    platform_cookie_domain = ".alipay.com"

    # ------------------------------------------------------------------
    # login()
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """支付宝扫码登录流程。

        1. 打开创作中心首页 ``c.alipay.com/page/life-account/index``
        2. 用户自行完成登录(扫码/账密)
        3. 登录后页面渲染账号信息(``accountContainer`` 区块出现昵称 + 头像)
        4. ``save_login_result`` 走统一后登录流程(scrape + cookie + DB + SSE)

        无超时:用户可能耗时较长。浏览器关闭由 ``login_mode=True`` 处理。
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(_ALIPAY_CREATOR_URL)

                # 等待账号信息容器出现(昵称节点) — 登录完成的标志
                # 用 [class*="accountContainer"] 前缀匹配,避免完整 hash 漂移
                await page.locator(
                    'div[class*="accountContainer"] div[class*="name"]'
                ).first.wait_for(timeout=999999999)
                logger.info("[alipay] 登录成功(检测到账号信息容器)")

                # 等渲染稳定
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

                await save_login_result(
                    context, page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_alipay_profile,
                    account_id=account_id,
                    # 登录成功后在同一个 session 内补抓 stats(粉丝/获赞),
                    # 与 sync_profile 共用同一份抓取逻辑
                    stats_fn=self._login_stats_fn,
                )
                success = True
            finally:
                await context.close()
        finally:
            if success:
                await self.close_browser(browser)

    # ------------------------------------------------------------------
    # check_cookie()
    # ------------------------------------------------------------------


    async def open_creator_center(self, cookie_file: str) -> None:
        """打开支付宝创作中心首页(可见浏览器,线程内同步 API)。"""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _ALIPAY_CREATOR_URL

        def _launch():
            browser = self.create_browser_sync(headless=False)
            try:
                context = self.create_context_sync(browser, storage_state=cookie_path)
                page = context.new_page()
                page.goto(url)
                try:  # noqa: SIM105
                    page.wait_for_event("close", timeout=0)
                except Exception:  # noqa: S110, BLE001 -- DOM/页面探测兜底,元素可能不存在
                    pass
            finally:
                try:  # noqa: SIM105
                    asyncio.run(close_browser(browser))
                except Exception:  # noqa: S110, BLE001 -- 资源清理兜底,失败可忽略
                    pass

        thread = threading.Thread(target=_launch, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # sync_profile()
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> dict:
        """同步昵称 + 头像 + 运营数据(stats)。

        访问 https://c.alipay.com/page/life-account/index,同一个 DOM 里同时抓
        name/avatar 和 stats(粉丝/获赞)。
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _ALIPAY_CREATOR_URL

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                name, avatar = await scrape_alipay_profile(page)
                # stats 与 name/avatar 在同一个 DOM 区块(.numBox),不用 goto 第二次
                stats = await self._scrape_alipay_stats(page)
                return {"name": name, "avatar": avatar, "stats": stats}
            except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                logger.info(f"[alipay] 同步资料失败: {e}")
                return {"name": "", "avatar": "", "stats": []}
            finally:
                await context.close()
        finally:
            await self.close_browser(browser)

    async def _scrape_alipay_stats(self, page) -> list:
        """抓取支付宝创作中心 .numBox 区块里的运营数据。

        页面 DOM 结构(参见用户提供的 2026-07-21 抓取样本):
            <div class="numBox___BlEq0">
                <span class="cntBox___HEIqZ">粉丝<span class="cnt___PTXo2">0</span></span>
                <span class="cntBox___HEIqZ">获赞<span class="cnt___PTXo2">0</span></span>
                <div class="ant-divider ant-divider-vertical" role="separator"></div>
                <div class="appId___lVu45">生活号ID:...</div>
            </div>

        每块 .cntBox 包含一个中文 label + 一个 .cnt 数值 span。

        Returns:
            list[dict]: 按 SORT 排序的运营数据列表
        """
        stats = []
        # label_map: 区块里的纯文本 label -> (ICON, SORT, 标准化 NAME)
        label_map = {
            "粉丝": ("user", 1, "粉丝"),
            "获赞": ("like", 2, "获赞"),
        }

        try:
            try:
                await page.wait_for_selector(".cntBox___HEIqZ, [class*='cntBox_']", timeout=8000)
            except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                logger.info("[alipay stats] 等待 .cntBox 超时")

            raw = await page.evaluate(
                '''() => {
                    const out = [];
                    // CSS modules class 名带 hash,用属性选择器更稳:[class*="cntBox_"]
                    document.querySelectorAll('[class*="cntBox_"]').forEach(item => {
                        // 数值 span:[class*="cnt_"] 开头(排除 cntBox_)
                        const numEl = item.querySelector('[class^="cnt_"]:not([class*="cntBox_"])');
                        if (!numEl) return;
                        // label 是 .cntBox 里的纯文本节点(去掉嵌套 span 后)
                        const clone = item.cloneNode(true);
                        clone.querySelectorAll('span').forEach(s => s.remove());
                        const label = (clone.textContent || '').trim();
                        const num = (numEl.textContent || '').trim();
                        if (label && num) out.push({label, num});
                    });
                    return out;
                }'''
            )

            for item in raw:
                label = item.get('label', '')
                if label in label_map:
                    icon, sort_no, name = label_map[label]
                    try:
                        count = int(str(item.get('num', '0')).replace(',', '').replace(' ', '') or '0')
                    except (ValueError, TypeError):
                        count = 0
                    stats.append({"ICON": icon, "COUNT": count, "NAME": name, "SORT": sort_no})
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[alipay stats] 抓取失败: {exc}")

        stats.sort(key=lambda x: x.get("SORT", 999))
        return stats

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口(供 save_login_result 调用)。

        与 sync_profile 内部共用 _scrape_alipay_stats 抓取逻辑。
        """
        try:
            return await self._scrape_alipay_stats(page)
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[alipay login] _login_stats_fn 抓取失败: {exc}")
            return []

    # ------------------------------------------------------------------
    # publish_video -- sync entry point
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """支付宝视频发布(sync wrapper)。

        Accepted keyword arguments:

        - ``title`` (*str*)        — 标题(≤30 字)
        - ``files`` (*list[str]*)  — 视频绝对路径
        - ``tags`` (*list[str]*)   — 话题(描述区以 #xxx 触发联想)
        - ``account_file`` (*list[str]*) — cookie 文件名列表
        - ``thumbnail_landscape_path`` / ``thumbnail_portrait_path`` (*str*)
        - ``desc`` (*str*)         — 描述
        - ``author_statement`` (*str*) — 作者声明(必填,6 选 1)
        - ``compilation`` (*str*)  — 合集名称(可选,精确匹配)
        - ``enableTimer`` (*bool*) / ``schedule_time_str`` (*str*) — 定时发布
        - ``reprint_url`` (*str*)  — 转载来源地址(author_statement=内容为转载 时必填)
        """
        try:
            await self._upload_all(**kwargs)
        except Exception as e:
            logger.exception("[发布失败] 支付宝 publish_video 异常: %s", e)
            return False
        return True

    # ------------------------------------------------------------------
    # Internal: orchestrate all file × account uploads
    # ------------------------------------------------------------------

    async def _upload_all(self, **kwargs):
        """文件 × 账号 笛卡尔积,每个组合一个 browser。"""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始支付宝视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", []) or []
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", []) or []
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path")
        video_format = kwargs.get("video_format", "") or ""
        desc = kwargs.get("desc", "") or ""
        author_statement = kwargs.get("author_statement", "") or ""
        compilation = kwargs.get("compilation", "") or ""
        enable_timer = kwargs.get("enableTimer")
        schedule_time_str = kwargs.get("schedule_time_str", "") or ""
        reprint_url = kwargs.get("reprint_url", "") or ""

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")
        logger.info("[发布参数] 视频格式: %s", video_format or "未指定")
        logger.info("[发布参数] 作者声明: %s", author_statement or "无")
        logger.info("[发布参数] 转载来源: %s", reprint_url or "无")
        logger.info("[发布参数] 合集: %s", compilation or "无")
        logger.info("[发布策略] 发布策略: %s", "scheduled" if enable_timer and schedule_time_str else "immediate")

        account_paths = [
            str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
        ]
        file_paths = [str(f) for f in files]
        if thumbnail_landscape_path:
            thumbnail_landscape_path = str(thumbnail_landscape_path)
        if thumbnail_portrait_path:
            thumbnail_portrait_path = str(thumbnail_portrait_path)

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
                        account_file=cookie_path,
                        thumbnail_landscape_path=thumbnail_landscape_path,
                        thumbnail_portrait_path=thumbnail_portrait_path,
                        video_format=video_format,
                        desc=desc,
                        author_statement=author_statement,
                        compilation=compilation,
                        enable_timer=enable_timer,
                        schedule_time_str=schedule_time_str,
                        reprint_url=reprint_url,
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Image (图集) publishing — 图文发布页 short-content
    # 文档 ~/ZFB-tuji.md
    # ------------------------------------------------------------------




    # ------------------------------------------------------------------
    # Helper (image): upload multiple images via hidden input[type=file]
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Helper (image): wait for form interactive
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Helper (image): select music (添加音乐 → hover → 使用)
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Internal: upload one video to one account
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        account_file: str,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        video_format: str = "",
        desc: str = "",
        author_statement: str = "",
        compilation: str = "",
        enable_timer=None,
        schedule_time_str: str = "",
        reprint_url: str = "",
    ):
        """单个视频上传到单个账号的完整流程。"""
        # 打印完整上送参数,便于排查(与其他渠道日志风格一致)
        logger.info(
            "[上传视频] ===== 上送参数 =====\n"
            "  title=%r\n"
            "  file_path=%r\n"
            "  tags=%r\n"
            "  account_file=%r\n"
            "  desc=%r\n"
            "  thumbnail_landscape=%r\n"
            "  thumbnail_portrait=%r\n"
            "  video_format=%r\n"
            "  author_statement=%r\n"
            "  compilation=%r\n"
            "  enable_timer=%r\n"
            "  schedule_time_str=%r\n"
            "  reprint_url=%r\n"
            "========================",
            title, file_path, tags,
            os.path.basename(account_file),
            desc,
            thumbnail_landscape_path,
            thumbnail_portrait_path,
            video_format,
            author_statement,
            compilation,
            enable_timer,
            schedule_time_str,
            reprint_url,
        )
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
                await page.goto(_ALIPAY_PUBLISH_URL, timeout=60000)
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
                logger.info("[上传视频] 正在上传-------%s", title)

                # 1. 上传视频文件
                await self._upload_video_file(page, file_path)

                # 2. 等待上传完成 + 表单渲染
                await self._wait_for_upload_form(page)

                # 3. 填标题
                await self._set_title(page, title)

                # 4. 填描述 + 话题
                await self._set_description_and_tags(page, desc, title, tags)

                # 5. 上传封面(按视频格式选择对应封面)
                #    竖版视频(portrait)→竖版封面;横版视频(landscape)→横版封面
                #    未指定格式时横版优先兜底
                if video_format == "portrait":
                    cover_path = (
                        thumbnail_portrait_path or thumbnail_landscape_path
                    )
                elif video_format == "landscape":
                    cover_path = (
                        thumbnail_landscape_path or thumbnail_portrait_path
                    )
                else:
                    cover_path = (
                        thumbnail_landscape_path or thumbnail_portrait_path
                    )
                logger.info(
                    "[上传视频] 封面选择: 格式=%s → %s",
                    video_format or "未指定",
                    os.path.basename(cover_path) if cover_path else "无",
                )
                await self._set_cover(page, cover_path)

                # 6. 合集(可选)
                if compilation:
                    await self._set_compilation(page, compilation)

                # 7. 作者声明(必填) + 转载来源(声明=内容为转载 时必填,下方出现输入框)
                await self._set_author_statement(page, author_statement)
                if author_statement.strip() == "内容为转载":
                    await self._set_reprint_url(page, reprint_url)

                # 8. 定时发布(可选)
                if enable_timer and schedule_time_str:
                    await set_schedule(page, schedule_time_str, get_params("alipay", "SCHEDULE"))

                # 9. 点击"确认发布"
                await self._click_publish(page)

                # 10. 等待发布成功
                await self._wait_for_publish_success(page)

                # 11. 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[上传视频] cookie 已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)
