"""
Bilibili platform implementation — 100% CloakBrowser.

All browser operations go through the BasePlatform browser entry points
(``self.create_browser()``, ``self.create_context()``) which delegate to
CloakBrowser via ``_browser.py``.
"""

import asyncio
import re
import threading
from pathlib import Path
from queue import Queue
from typing import Any

from conf import BASE_DIR
from util._logger import bind_account_name, get_channel_logger

logger = get_channel_logger("bilibili")

from .._browser import close_browser
from .._utils import (
    clear_and_type,
    get_account_name_by_cookie_file,
    parse_schedule_time,
    save_login_result,
)
from ..base_platform import BasePlatform
from ..primitives import fill_title, get_params, set_schedule, set_thumbnail
from ._profile import scrape_bilibili_profile

BILIBILI_UPLOAD_URL = "https://member.bilibili.com/platform/upload/video/frame"
BILIBILI_MANAGE_URL = "https://member.bilibili.com/platform/upload-manager/article"
BILIBILI_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
BILIBILI_PUBLISH_STRATEGY_SCHEDULED = "scheduled"

# B 站视频上传/表单渲染的最大等待时长 —— 视频可能很大、网络可能很慢,
# 给足 4 小时(14400s),按 0.5s 轮询即 28800 次。宁可久等也不误判超时。
_UPLOAD_WAIT_SECONDS = 4 * 60 * 60  # 4 小时
_UPLOAD_WAIT_POLLS = _UPLOAD_WAIT_SECONDS * 2  # 0.5s/次 → 28800 次

# 调试开关:True = 走到提交按钮时只输出参数日志、不实际点击提交(便于检查内容);
# False = 正常点击提交。验证完发布内容无误后改回 False 即可。
_PUBLISH_DRY_RUN = False

# B 站标题禁止的字符:emoji(非 BMP 字符) + HTML 危险字符(<>\"'&)。
# 其他字符(中文、英文、数字、全角/半角标点、常见符号)全部允许。
_BILI_TITLE_FORBIDDEN_RE = re.compile(
    '[\u2600-\u27bf\ufe00-\ufe0f\u200d\u20e3\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufff0-\uffff'
    '\U0001f000-\U0001faff'
    '<>"\'&]',
)


def _sanitize_title(text: str) -> str:
    """去掉 B 站标题里的 emoji 和 HTML 危险字符,其他字符保留。"""
    if not text:
        return text
    return _BILI_TITLE_FORBIDDEN_RE.sub('', text)


def _truncate_desc_by_length(text: str, max_len: int = 2000) -> str:
    """按 emoji=3 规则截断简介,确保总字符数 ≤ max_len。"""
    if not text:
        return text
    result = []
    total = 0
    for ch in text:
        cost = 3 if ord(ch) > 0xFFFF else 1
        if total + cost > max_len:
            break
        result.append(ch)
        total += cost
    return "".join(result)

# Default category tid (music)
BILIBILI_DEFAULT_TID = 3

# tid -> Chinese name mapping (matches Bilibili's upload page)
_TID_CN_NAME = {
    1: "动画", 13: "番剧", 23: "电影", 167: "国创", 11: "电视剧",
    177: "纪录片", 4: "游戏", 119: "鬼畜", 3: "音乐", 129: "舞蹈",
    181: "影视", 5: "娱乐", 36: "知识", 188: "科技", 202: "资讯",
    211: "美食", 160: "生活", 223: "汽车", 155: "时尚", 234: "运动",
    217: "动物圈", 19: "VLOG",
    21: "日常", 28: "原创音乐", 31: "翻唱", 33: "连载动画",
    32: "完结动画", 95: "数码", 96: "星海", 122: "野生技术协会",
    207: "资讯", 251: "三农", 76: "游戏人物", 75: "单机游戏",
    65: "网络游戏", 163: "手机游戏", 164: "桌游棋牌",
    171: "电子竞技", 172: "MAD·AMV", 173: "MMD·3D",
}


class BilibiliPlatform(BasePlatform):
    # ---- Cookie 校验参数（基类探针 session_verify 使用, 提炼自原 check_cookie）----
    CHECK_URL = "https://member.bilibili.com/platform/home"
    CHECK_SLEEP = 2.0
    CHECK_INVALID_URL_MARKERS = (
        "passport.bilibili.com/login",
    )
    platform_id = 5
    platform_key = "bilibili"
    platform_name = "B站"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    # B站 cookie 全部由 .bilibili.com 域下发，覆盖 account/member 子域
    platform_cookie_domain = ".bilibili.com"

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Bilibili login via QR code scan.

        Opens ``passport.bilibili.com/login``, finds the QR image via
        multi-selector, waits for the user to scan, then navigates to the
        account home page to scrape profile info.
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

                await page.goto("https://passport.bilibili.com/login")
                original_url = page.url

                # Locate QR code image with multiple selectors
                src = None
                try:
                    qr_img = page.locator(
                        '.qrcode-img img, img[src*="qrcode"], .login-scan img'
                    ).first
                    src = await qr_img.get_attribute("src")
                    if not src:
                        qr_img = page.get_by_role("img").nth(0)
                        src = await qr_img.get_attribute("src")
                except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info(f"[bilibili] failed to locate QR code: {e}")

                if src:
                    logger.info(f"[bilibili] QR code URL: {src[:80]}")
                    status_queue.put(src)
                else:
                    logger.info("[bilibili] QR code image not found")
                    status_queue.put("500")
                    await page.close()
                    await context.close()
                    return

                # Monitor page navigation for login completion
                page.on(
                    "framenavigated",
                    lambda frame: asyncio.create_task(_on_url_change())
                    if frame == page.main_frame
                    else None,
                )

                # 不设超时——扫码登录可能耗时几分钟，浏览器由用户自己关
                await url_changed_event.wait()
                logger.info("[bilibili] login page navigation detected")

                # Navigate to account home and scrape profile
                await page.goto("https://account.bilibili.com/account/home")
                await asyncio.sleep(2)

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_bilibili_profile,
                    account_id=account_id,
                    # 登录成功后在同一个 session 内补抓 stats(粉丝/点赞/收藏/投币/...),
                    # 避免登录后还需用户再点"同步"才能看到运营数据。
                    # 与 sync_profile 内部抓取逻辑共用同一个 _scrape_bilibili_stats 方法。
                    stats_fn=self._login_stats_fn,
                )
                success = True
            finally:
                # 释放 context + page 资源
                await page.close()
                await context.close()
        finally:
            # 成功才关浏览器（失败/异常时留着让用户看现场）
            if success:
                await self.close_browser(browser)

    # ------------------------------------------------------------------
    # Cookie check
    # ------------------------------------------------------------------


    async def sync_profile(self, cookie_file: str) -> dict:
        """Sync profile info (name, avatar, stats) from Bilibili creator centre.

        抓取流程(无头模式):
        1. 访问 https://account.bilibili.com/account/home 抓 name/avatar
        2. 跳转到 https://member.bilibili.com/platform/home 抓 8 项 stats
           (播放量/评论/弹幕/点赞/分享/收藏/投币/粉丝总数)

        共 8 项运营数据。前端会按 SORT 排序后展示前 3 项(粉丝/点赞/收藏),
        其余进入"更多"悬浮窗展示全部 8 项。
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                # Step 1: 抓 name/avatar
                try:
                    await page.goto("https://account.bilibili.com/account/home",
                                    wait_until="networkidle", timeout=30000)
                    name, avatar = await scrape_bilibili_profile(page)
                except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info(f"[bilibili] 抓 name/avatar 失败: {exc}")
                    name, avatar = "", ""

                # Step 2: 跳到创作中心抓 stats
                try:
                    await page.goto("https://member.bilibili.com/platform/home",
                                    wait_until="networkidle", timeout=30000)
                    stats = await self._scrape_bilibili_stats(page)
                except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info(f"[bilibili] 抓 stats 失败(不影响 name/avatar): {exc}")
                    stats = []

                return {"name": name, "avatar": avatar, "stats": stats}
            except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                logger.info(f"[bilibili] sync profile failed: {e}")
                return {"name": "", "avatar": "", "stats": []}
            finally:
                try:  # noqa: SIM105
                    await page.close()
                except Exception:  # noqa: S110, BLE001 -- 资源清理兜底,失败可忽略
                    pass
                try:  # noqa: SIM105
                    await context.close()
                except Exception:  # noqa: S110, BLE001 -- 资源清理兜底,失败可忽略
                    pass
        finally:
            try:  # noqa: SIM105
                await self.close_browser(browser)
            except Exception:  # noqa: S110, BLE001 -- 资源清理兜底,失败可忽略
                pass

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口(供 save_login_result 调用)。

        与 sync_profile 内部共用同一个 _scrape_bilibili_stats 抓取逻辑,
        保证"登录后同步"和"同步按钮"看到的运营数据完全一致。
        """
        try:
            await page.goto(
                "https://member.bilibili.com/platform/home",
                wait_until="networkidle",
                timeout=30000,
            )
            return await self._scrape_bilibili_stats(page)
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[bilibili login] _login_stats_fn 抓取失败: {exc}")
            return []


    async def _scrape_bilibili_stats(self, page) -> list:
            """抓取 B 站创作中心首页的 8 项运营数据。

            页面 DOM 结构(参见用户提供的 2026-07-19 抓取样本):
                <div class="video section">
                  <div class="section-row first">
                    <div class="data-card ct-info-card"><div class="name">播放量</div><div class="value">1,114</div></div>
                    <div class="data-card ct-info-card"><div class="name">评论</div><div class="value">15</div></div>
                    <div class="data-card ct-info-card"><div class="name">弹幕</div><div class="value">2</div></div>
                  </div>
                  <div class="section-row">
                    <div class="data-card"><div class="name">点赞</div><div class="value">83</div></div>
                    <div class="data-card"><div class="name">分享</div><div class="value">2</div></div>
                    <div class="data-card"><div class="name">收藏</div><div class="value">21</div></div>
                    <div class="data-card"><div class="name">投币</div><div class="value">24</div></div>
                  </div>
                </div>
                <div class="data-right">
                  <div class="fan-overview">
                    <div class="fan-item">
                      <div class="fan-label"><span>粉丝总数</span></div>
                      <div class="fan-num">1</div>
                    </div>
                  </div>
                </div>

            Returns:
                list[dict]: 按 SORT 排序的运营数据列表
            """
            stats: list[dict[str, Any]] = []
            # label_map: B 站页面上的中文名 -> (ICON, SORT, 标准化 NAME)
            # 8 项全部写入 stats;卡片只展示前 3 项(粉丝/点赞/收藏),
            # 鼠标悬停"更多"占位时通过悬浮窗展示全部 8 项。
            label_map = {
                "播放量":  ("play",  5, "播放量"),
                "评论":    ("chat",  6, "评论"),
                "弹幕":    ("chat",  7, "弹幕"),
                "点赞":    ("like",  2, "点赞"),
                "分享":    ("share", 8, "分享"),
                "收藏":    ("star",  3, "收藏"),
                "投币":    ("coin",  4, "投币"),
                "粉丝总数": ("user",  1, "粉丝"),
            }

            def _parse_int(text: str) -> int:
                try:
                    return int(str(text or '0').replace(',', '').replace(' ', '') or '0')
                except (ValueError, TypeError):
                    return 0

            try:
                try:
                    await page.wait_for_selector(".data-card .value, .fan-num", timeout=10000)
                except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info("[bilibili stats] 等待 .data-card/.fan-num 超时")

                raw = await page.evaluate(
                    '''() => {
                        const out = [];
                        // 视频数据 section: 每个 .data-card 里有 .name 和 .value
                        document.querySelectorAll('.data-card').forEach(card => {
                            const nameEl = card.querySelector('.name');
                            const valEl = card.querySelector('.value');
                            if (!nameEl || !valEl) return;
                            const name = nameEl.textContent.trim();
                            // 去掉图标和空格,只留文字
                            const clean = name.replace(/\\s+/g, '');
                            out.push({label: clean, num: valEl.textContent.trim()});
                        });
                        // 粉丝概览: .fan-item .fan-label .fan-num
                        document.querySelectorAll('.fan-item').forEach(item => {
                            const labelEl = item.querySelector('.fan-label');
                            const numEl = item.querySelector('.fan-num');
                            if (!labelEl || !numEl) return;
                            // fan-label 第一个 span 是文字
                            const span = labelEl.querySelector('span');
                            const label = span ? span.textContent.trim() : '';
                            out.push({label, num: numEl.textContent.trim()});
                        });
                        return out;
                    }'''
                )

                for item in raw:
                    label = item.get('label', '')
                    if label in label_map:
                        icon, sort_no, name = label_map[label]
                        count = _parse_int(item.get('num', '0'))
                        stats.append({"ICON": icon, "COUNT": count, "NAME": name, "SORT": sort_no})
            except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                logger.info(f"[bilibili stats] 抓取失败: {exc}")

            stats.sort(key=lambda x: x.get("SORT", 999))
            return stats

    # ------------------------------------------------------------------
    # Open creator center
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Bilibili creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://member.bilibili.com/platform/upload-manager/article"

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
    # Publish video
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to Bilibili.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``category`` (*int*, optional)
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``desc`` (*str*, optional)
        - ``thumbnail_landscape_path`` (*str*, optional) -- landscape cover
        - ``thumbnail_portrait_path`` (*str*, optional) -- portrait cover
        - ``schedule_time_str`` (*str*, optional)
        - ``creation_declaration`` (*str*, optional)
        """

        async def _run():
            logger.info("=" * 60)
            logger.info("[发布视频] 开始B站视频发布流程")
            logger.info("=" * 60)

            # 打印所有接收到的参数
            logger.info("[发布参数] 接收到的所有参数:")
            for key, value in kwargs.items():
                logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

            title = kwargs.get("title", "")
            files = kwargs.get("files", [])
            tags = kwargs.get("tags", [])
            account_files = kwargs.get("account_file", [])
            category = kwargs.get("category")
            enable_timer = kwargs.get("enableTimer", False)
            videos_per_day = kwargs.get("videos_per_day", 1)
            daily_times = kwargs.get("daily_times")
            start_days = kwargs.get("start_days", 0)
            desc = kwargs.get("desc", "")
            thumbnail_landscape = kwargs.get("thumbnail_landscape_path", "")
            schedule_time_str = kwargs.get("schedule_time_str", "")
            # ai_content 字段已废弃：B 站新版去掉了"更多设置/声明与权益"，
            # 创作声明直接在主页面设置（kwargs 兼容接收，忽略即可）
            creation_declaration = kwargs.get("creation_declaration", "")
            # B 站转载来源(创作声明=转载 时必填)
            bili_repost_source = kwargs.get("bili_repost_source", "")
            logger.info("[发布参数] B 站转载来源: %r", bili_repost_source or "(空)")
            # B 站合集(账号级)
            bili_collection_name = kwargs.get("bili_collection_name", "")

            # 打印发布参数摘要
            logger.info("[发布参数] 标题: %s", title)
            logger.info("[发布参数] 文件数量: %d", len(files))
            logger.info("[发布参数] 标签: %s", tags)
            logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
            logger.info("[发布参数] 账号数量: %d", len(account_files))
            logger.info("[发布参数] 定时发布: %s", enable_timer)
            logger.info("[发布参数] 横版封面: %s", thumbnail_landscape or "无")
            logger.info("[发布参数] 创作声明: %s", creation_declaration or "无")
            logger.info("[发布策略] 发布策略: %s", "scheduled" if enable_timer and schedule_time_str else "immediate")

            # Resolve full paths
            cookie_paths = [
                str(Path(BASE_DIR / "cookiesFile") / f) for f in account_files
            ]
            # files 已是绝对路径（app.py 调用 _resolve_material_path 处理过）
            file_paths = [str(f) for f in files]

            # Bilibili uses landscape cover
            thumbnail_path = None
            if thumbnail_landscape:
                # thumbnail_landscape 已是绝对路径
                thumbnail_path = str(thumbnail_landscape)

            # Parse schedule times
            publish_datetimes = parse_schedule_time(
                schedule_time_str,
                len(file_paths),
                enable_timer,
                videos_per_day,
                daily_times,
                start_days,
            )

            for index, file_path in enumerate(file_paths):
                logger.info("-" * 40)
                logger.info("[发布进度] 处理第 %d/%d 个视频: %s", index + 1, len(file_paths), file_path)
                publish_date = (
                    publish_datetimes[index]
                    if isinstance(publish_datetimes, list)
                    else publish_datetimes
                )
                for cookie_index, cookie_path in enumerate(cookie_paths):
                    cookie_name = Path(cookie_path).name
                    nick = get_account_name_by_cookie_file(cookie_name)
                    with bind_account_name(nick or "-"):
                        logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(cookie_paths), nick or "未知")
                        await self._upload_single_video(
                            title=title,
                            file_path=file_path,
                            tags=tags,
                            publish_date=publish_date,
                            account_file=cookie_path,
                            category=category,
                            desc=desc,
                            thumbnail_path=thumbnail_path,
                            creation_declaration=creation_declaration,
                            bili_collection_name=bili_collection_name,
                            bili_repost_source=bili_repost_source,
                        )

            logger.info("=" * 60)
            logger.info("[发布视频] 视频发布流程完成!")
            logger.info("=" * 60)

        try:
            await _run()
        except Exception as e:
            logger.exception("[发布失败] 哔哩哔哩 publish_video 异常: %s", e)
            return False
        return True

    # ------------------------------------------------------------------
    # Internal upload helpers
    # ------------------------------------------------------------------

    async def _upload_single_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        category=None,
        desc: str = "",
        thumbnail_path: str | None = None,
        creation_declaration: str = "",
        bili_collection_name: str = "",
        bili_repost_source: str = "",
    ):
        """Upload a single video to Bilibili using CloakBrowser."""
        log_dir = Path(BASE_DIR / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser, storage_state=account_file
            )

            upload_success = False
            try:
                page = await context.new_page()
                logger.info(f"[上传视频] 开始上传视频: {title}")
                await page.goto(BILIBILI_UPLOAD_URL)
                await page.wait_for_url(
                    "**/platform/upload/**", timeout=30000
                )

                if "passport.bilibili.com" in page.url:
                    raise RuntimeError(
                        "Bilibili cookie expired, please re-login"
                    )

                # 1. Upload video file
                await self._upload_video_file(page, file_path)

                # 2. Wait for upload to complete
                await self._wait_upload_complete(page)
                await asyncio.sleep(3)

                # 2.5 等待页面就绪：标题输入框出现即代表表单已渲染完整。
                # 用 placeholder 定位(禁用 class)，超时 4 小时。
                logger.info("[上传视频] 等待发布表单渲染(标题输入框,最多 4 小时)...")
                title_input = page.locator('input[placeholder*="标题"]').first
                form_ready = False
                for _ in range(_UPLOAD_WAIT_POLLS):
                    if await title_input.count() > 0:
                        form_ready = True
                        break
                    await asyncio.sleep(0.5)
                if not form_ready:
                    raise TimeoutError("发布表单未渲染(标题输入框未出现,超 4 小时)")
                logger.info(
                    "[上传视频] 发布表单已渲染(标题输入框就绪)"
                )

                # Pre-form screenshot
                await page.screenshot(
                    path=str(log_dir / "bilibili_before_form.png"),
                    full_page=True,
                )

                # 3. Fill title
                await fill_title(page, title, get_params("bilibili", "FILL_TITLE"))

                # 4. Set category
                await self._set_category(page, category)

                # 5. Fill tags
                await self._fill_tags(page, tags)

                # 6. Fill description
                await self._fill_desc(page, desc)

                # 7. Set cover/thumbnail
                await set_thumbnail(page, get_params("bilibili", "THUMBNAIL"), thumbnail_path=thumbnail_path)

                # 8. Set creation declaration (bcc-select dropdown)
                # B 站新版已废弃"更多设置/声明与权益"，保留创作声明即可
                # 创作声明=转载 时, 选完后会展开转载来源输入框, 一并填入
                await self._set_creation_declaration(page, creation_declaration, bili_repost_source)

                # 9. Set scheduled publish
                if (
                    isinstance(publish_date, int)
                    and publish_date == 0
                ):
                    publish_strategy = BILIBILI_PUBLISH_STRATEGY_IMMEDIATE
                elif publish_date != 0:
                    publish_strategy = BILIBILI_PUBLISH_STRATEGY_SCHEDULED
                else:
                    publish_strategy = BILIBILI_PUBLISH_STRATEGY_IMMEDIATE

                if (
                    publish_strategy == BILIBILI_PUBLISH_STRATEGY_SCHEDULED
                    and publish_date != 0
                ):
                    await set_schedule(page, publish_date, get_params("bilibili", "SCHEDULE"))

                # Pre-submit screenshot
                await page.screenshot(
                    path=str(log_dir / "bilibili_before_submit.png"),
                    full_page=True,
                )

                # 9.5 Set collection (合集)
                if bili_collection_name:
                    logger.info("[设置合集] 开始设置合集: %s", bili_collection_name)
                    await self._set_collection(page, bili_collection_name)

                # 调试:输出本次发布的全部参数(便于人工核对填写是否正确)
                logger.info("=" * 60)
                logger.info("[发布调试] ===== 本次发布参数汇总 (dry_run=%s) =====", _PUBLISH_DRY_RUN)
                logger.info("[发布调试] 标题(title)       : %s", title)
                logger.info("[发布调试] 视频文件(file_path): %s", file_path)
                logger.info("[发布调试] 简介(desc)        : %s", desc[:100] if desc else "(无)")
                logger.info("[发布调试] 标签(tags)        : %s (共 %d 个)", tags, len(tags))
                logger.info("[发布调试] 分区(category)    : %s", category)
                logger.info("[发布调试] 封面(thumbnail)   : %s", thumbnail_path or "(无)")
                logger.info("[发布调试] 创作声明(creation): %s", creation_declaration or "(无)")
                logger.info("[发布调试] 定时时间(publish_date): %s", publish_date)
                logger.info("[发布调试] 发布策略(strategy): %s", publish_strategy)
                logger.info("[发布调试] 合集(collection)  : %s", bili_collection_name or "(无)")
                logger.info("[发布调试] ========================================")
                logger.info("=" * 60)

                if _PUBLISH_DRY_RUN:
                    logger.warning("[发布调试] DRY_RUN 已开启 —— 跳过实际点击提交,流程到此结束(不发布)")
                    logger.info("[发布调试] DRY_RUN: 浏览器保持打开,等待你手动关闭窗口后再结束...")
                    try:
                        while browser.is_connected():
                            await asyncio.sleep(1)
                        logger.info("[发布调试] 检测到浏览器已关闭,流程结束")
                    except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                        pass
                    return

                # 10. Submit
                logger.info("[上传视频] submitting video")
                await page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight)"
                )
                await asyncio.sleep(1)

                submitted = False
                for attempt in range(10):
                    try:
                        submit_span = page.locator("span.submit-add")
                        if await submit_span.count() > 0:
                            await submit_span.first.scroll_into_view_if_needed()
                            await submit_span.first.click()
                            logger.info("[上传视频] clicked submit button")
                        else:
                            logger.info(
                                f"[上传视频] submit button not found, "
                                f"retry {attempt + 1}/10"
                            )
                            await asyncio.sleep(3)
                            continue

                        await asyncio.sleep(3)
                        for _ in range(15):
                            await asyncio.sleep(2)
                            btn_exists = (
                                await page.locator("span.submit-add").count()
                                > 0
                            )
                            if not btn_exists:
                                logger.info(
                                    "[上传视频] submit success "
                                    "(button disappeared)"
                                )
                                submitted = True
                                break
                            if (
                                page.url != BILIBILI_UPLOAD_URL
                                and "/platform/upload/" not in page.url
                            ):
                                logger.info(
                                    f"[上传视频] submit success, "
                                    f"redirected to: {page.url}"
                                )
                                submitted = True
                                break

                        if submitted:
                            break

                        logger.info(
                            f"[上传视频] page unchanged after click, "
                            f"retry {attempt + 1}/10"
                        )
                        await page.screenshot(
                            path=str(
                                log_dir / f"bilibili_submit_{attempt}.png"
                            ),
                            full_page=True,
                        )
                    except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                        logger.info(
                            f"[上传视频] submit retry {attempt + 1}/10: {exc}"
                        )
                        await page.screenshot(
                            path=str(
                                log_dir / f"bilibili_submit_{attempt}.png"
                            ),
                            full_page=True,
                        )
                        await asyncio.sleep(2)

                if not submitted:
                    logger.info(
                        "[上传视频] could not confirm submission, "
                        "but it may have succeeded"
                    )

                if submitted:
                    logger.info("[上传视频] waiting 10s for processing")
                    await asyncio.sleep(10)
                    try:  # noqa: SIM105
                        await page.screenshot(
                            path=str(
                                log_dir / "bilibili_after_submit.png"
                            ),
                            full_page=True,
                        )
                    except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                        pass

                upload_success = True
            finally:
                if upload_success:
                    try:
                        await context.storage_state(path=account_file)
                        logger.info("[上传视频] cookie updated")
                    except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                        pass
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)
            logger.info("[上传视频] browser closed")

    # ------------------------------------------------------------------
    # Upload sub-steps
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_video_file(page, file_path: str):
        """Select the video file via iframe or direct file input."""
        logger.info("[上传视频] 正在上传视频文件...")

        file_input = None
        try:
            upload_frame = page.frame_locator('iframe[name="videoUpload"]')
            input_in_frame = upload_frame.locator('input[type="file"]')
            await input_in_frame.wait_for(state="attached", timeout=5000)
            file_input = input_in_frame
        except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info("[上传视频] upload iframe not found, trying main page")

        if file_input is None:
            file_input = page.locator(
                'input[type="file"][accept*="video"], input[type="file"]'
            ).first
            await file_input.wait_for(state="attached", timeout=10000)

        await file_input.set_input_files(file_path)
        logger.info("[上传视频] 视频文件已选择, 等待上传完成")

    @staticmethod
    async def _wait_upload_complete(page):
        """Wait until the video upload is fully complete.

        唯一就绪标志:必须出现「上传完成」文案(DOM 里的 <span>上传完成</span>)。
        用 get_by_text("上传完成") 定位,禁用 class/data-v 定位。
        超时 4 小时,0.5s 轮询。
        """
        logger.info("[上传视频] 等待视频上传完成(最多 4 小时)...")
        done_text = page.get_by_text("上传完成", exact=True)
        for i in range(_UPLOAD_WAIT_POLLS):
            try:
                if await done_text.count() > 0:
                    await asyncio.sleep(2)  # 等稳定
                    elapsed = i * 0.5
                    logger.info(
                        "[上传视频] 检测到「上传完成」,上传成功 (耗时 %.0f 秒)",
                        elapsed,
                    )
                    return
                # 检测上传失败
                fail_text = page.get_by_text("上传失败", exact=True)
                if await fail_text.count() > 0:
                    raise RuntimeError("视频上传失败:检测到「上传失败」文案")  # noqa: TRY301 -- try 内主动 raise 为语义错误/快速失败,刻意不被吞,抽象改造ROI低
                if i % 60 == 0 and i > 0:  # 每 30 秒打一次日志
                    logger.info(
                        "[上传视频] 仍在上传中... (%.0f 秒)", i * 0.5
                    )
            except RuntimeError:
                raise
            except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                if i % 60 == 0 and i > 0:
                    logger.info("[上传视频] 上传状态检查: %s", exc)
            await asyncio.sleep(0.5)
        raise TimeoutError("视频上传超时(超过 4 小时):未检测到「上传完成」")


    @staticmethod
    async def _set_category(page, category):
        """Set the video category (partition) via dropdown."""
        # 修：严格判 None（category=0 不再被早退）
        if category is None or category == '':
            return

        # Resolve Chinese name from tid OR Chinese name
        if isinstance(category, int):
            cn_name = _TID_CN_NAME.get(category)
        elif isinstance(category, str):
            s = category.strip()
            # 反向映射：中文名 → 找是否在 _TID_CN_NAME 里
            rev = {v: k for k, v in _TID_CN_NAME.items()}
            if s in rev:
                cn_name = s  # 直接用中文名（点击下拉按 title 即可）
            elif s.isdigit() and int(s) in _TID_CN_NAME:
                cn_name = _TID_CN_NAME[int(s)]
            else:
                cn_name = s  # 兜底：直接用原字符串（UI 显示的中文名）
        else:
            cn_name = None

        logger.info(
            f"[上传视频] setting category: category={category}, "
            f"cn_name={cn_name}"
        )

        if not cn_name:
            logger.info(
                f"[上传视频] unknown category: {category}, skipping"
            )
            return

        log_dir = Path(BASE_DIR / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            # 策略 1：按 .section-title-content-main 模糊匹配 "分区"
            title = page.locator('.section-title-content-main', has_text='分区').first
            if await title.count() == 0:
                logger.error("[设置分区] 找不到 '分区' section 标题")
                await page.screenshot(path=str(log_dir / "bili_no_partition_title.png"), full_page=True)
                return

            # 2. 沿 xpath 找到 .selector-container（分区 section 的兄弟节点）
            selector_container = title.locator(
                "xpath=ancestor::div[contains(@class,'section-title-container')][1]/following-sibling::div[contains(@class,'selector-container')][1]"
            )
            if await selector_container.count() == 0:
                # 兜底：直接父 div（兼容老 DOM）
                selector_container = title.locator("xpath=ancestor::div[2]")
                logger.warning("[设置分区] 用 ancestor::div[2] 兜底定位 selector-container")

            # 3. 在该 selector-container 内找 .select-controller
            select_controller = selector_container.locator(".select-controller").first
            await select_controller.wait_for(state="visible", timeout=10000)

            # 4. force=True 避开遮挡（CSS hover 弹层/动画都可能拦截）
            await select_controller.click(force=True)
            logger.info("[设置分区] clicked select-controller (in 分区 section, force=True)")

            # 5. 等下拉项出现（drop-list-v2-container 是 B 站下拉容器）
            try:
                await page.locator(".drop-list-v2-container").first.wait_for(
                    state="visible", timeout=5000
                )
            except Exception:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
                # 兜底：可能已经开了但选择器未匹配，再点一次
                logger.warning("[设置分区] 下拉未出现，尝试再点一次")
                await select_controller.click(force=True)
                await asyncio.sleep(1)

            # 6. 按 title 属性点击目标项
            target_item = page.locator(
                f'.drop-list-v2-item[title="{cn_name}"]'
            )
            if await target_item.count() > 0:
                await target_item.first.click(force=True)
                logger.info(f"[设置分区] category set: {cn_name}")
            else:
                logger.error(
                    f"[上传视频] partition not found in dropdown: {cn_name}"
                )
                await page.screenshot(
                    path=str(log_dir / "bilibili_partition_not_found.png"),
                    full_page=True,
                )

            await asyncio.sleep(1)
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[设置分区] category setting failed (non-fatal): {exc}")

    @staticmethod
    async def _fill_tags(page, tags: list):
        """Fill video tags (up to 10 tags)."""
        if not tags:
            return

        # Parse tags: support "#tag1 #tag2" or "tag1,tag2" or mixed
        parsed: list = []
        for t in tags:
            if isinstance(t, str) and t.strip():
                parsed.extend(
                    s.strip() for s in re.split(r"[,，#]", t) if s.strip()
                )
            elif isinstance(t, str):
                parsed.append(t)
        tags = parsed

        logger.info(f"[填写标签] adding {len(tags)} tags")

        log_dir = Path(BASE_DIR / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        # Try multiple selectors for the tag input
        selectors = [
            'input[placeholder*="回车键Enter创建标签"]',
            'input[placeholder*="Enter创建标签"]',
            'input[placeholder*="按回车"]',
            'input[placeholder*="标签"]',
            ".tag-input input",
            '[class*="tag"] input[type="text"]',
        ]

        tag_input = None
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    tag_input = loc
                    logger.info(f"[填写标签] found tag input: {sel}")
                    break
            except Exception:  # noqa: S112, BLE001 -- 单次探测失败,跳过继续
                continue

        if tag_input is None:
            logger.info("[填写标签] tag input not found, taking debug screenshot")
            await page.screenshot(
                path=str(log_dir / "bilibili_tag_input_not_found.png"),
                full_page=True,
            )
            return

        for i, tag in enumerate(tags[:10]):
            try:
                # Re-locate input after each tag (DOM may change)
                current_input = None
                for sel in selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            current_input = loc
                            break
                    except Exception:  # noqa: S112, BLE001 -- 单次探测失败,跳过继续
                        continue
                if current_input is None:
                    logger.info("[填写标签] tag input lost, stopping")
                    break

                # click 后等输入框真正可编辑(比固定 sleep 可靠, 避免焦点未稳定
                # 就输入导致前几个字符被吞——曾出现"杨氏之子"只输入"杨"或"氏之子")。
                await current_input.click()
                try:  # noqa: SIM105
                    await current_input.wait_for(state="editable", timeout=3000)
                except Exception:  # noqa: S110, BLE001 -- DOM/页面探测兜底,元素可能不存在
                    pass
                # 第一个标签前多等一会(输入框刚展开, React 渲染未稳定)
                await asyncio.sleep(0.5 if i == 0 else 0.3)

                # press_sequentially 自动 focus 且逐字符触发 input 事件,
                # 比 type 更稳(CLAUDE.md L74-82 推荐)。delay=100 给 B 站 React
                # 充分反应时间, 避免快打丢字。
                await current_input.press_sequentially(str(tag), delay=100)
                await asyncio.sleep(0.3)
                await current_input.press("Enter")
                await asyncio.sleep(0.5)
                logger.info(
                    f"[上传视频] added tag ({i + 1}/{min(len(tags), 10)}): "
                    f"{tag}"
                )
            except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                logger.info(f"[填写标签] failed to add tag '{tag}': {exc}")

    @staticmethod
    async def _fill_desc(page, desc: str):
        """Fill the video description (max 2000 chars, emoji=3)."""
        if not desc:
            return
        # 按 emoji=3 规则截断到 2000 字
        safe_desc = _truncate_desc_by_length(desc, 2000)
        if len(safe_desc) != len(desc):
            logger.info("[填写简介] 简介已截断(emoji=3): %d -> %d 字符", len(desc), len(safe_desc))

        logger.info("[填写简介] filling description")
        desc_editor = page.locator(
            '[contenteditable="true"][class*="editor"], '
            ".ql-editor, "
            '[class*="desc"] textarea, '
            '[class*="desc"] [contenteditable="true"]'
        ).first
        if await desc_editor.count() > 0 and await desc_editor.is_visible():
            await desc_editor.click()
            # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
            await clear_and_type(page, safe_desc, delay=10)
        else:
            logger.info("[填写简介] description editor not found")


    @staticmethod
    async def _set_creation_declaration(page, creation_declaration: str, repost_source: str = ""):
        """Set creation declaration via bcc-select dropdown.

        Only shown for some accounts. Silently skipped when not found.
        创作声明选「内容为转载」时, B 站会展开转载来源输入框(.statement-source
        input.input-val), 此处一并填入 repost_source(转载来源, B 站要求必填)。
        """
        if not creation_declaration:
            return

        logger.info(
            f"[上传视频] setting creation declaration: "
            f"{creation_declaration}"
        )
        try:
            # Close any popover that may be obscuring
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            select_input = page.locator(
                'input.bcc-select-input-inner[placeholder*="创作声明"]'
            )
            if await select_input.count() == 0:
                # 兼容：用 section title "创作声明" 定位所在容器的 select input
                scoped = page.locator(
                    'div.statement-content, '
                    'div[class*="statement-content"]'
                ).first
                scoped_input = scoped.locator(
                    'input.bcc-select-input-inner'
                ).first
                if await scoped_input.count() > 0:
                    select_input = scoped_input
                else:
                    logger.info(
                        "[上传视频] creation declaration dropdown not "
                        "present, skipping"
                    )
                    return

            await select_input.first.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            await select_input.first.click(force=True)
            await asyncio.sleep(1)

            # 等下拉打开：检测 bcc-select-list-wrap 从 display:none 变为可见
            # 用户给的 DOM 里 .bcc-select-list-wrap 默认 display: none，
            # 展开后 inline style 被去除（display: block / 默认）。用
            # 内联 style 判定更准确（避免 :visible 在 display:none 时失效）
            list_wrap = page.locator(
                '.bcc-select-list-wrap:not([style*="display: none"])'
            )
            try:
                await list_wrap.first.wait_for(
                    state="attached", timeout=5000
                )
            except Exception:  # noqa: BLE001 -- 捕获后恢复默认状态,防御性编码
                # 兜底：bcc-select 容器加 'is-open'/'is-focus' 类
                fallback = page.locator(
                    '.bcc-select.is-open, .bcc-select.is-focus, '
                    '.bcc-select[class*="open"], .bcc-select[class*="focus"]'
                )
                await fallback.first.wait_for(state="attached", timeout=3000)

            # 在创作声明容器内查选项（避免命中页面其他 bcc-select）
            scoped_options = page.locator(
                'div.statement-content, '
                'div[class*="statement-content"]'
            ).first.locator('li.bcc-option')
            try:  # noqa: SIM105
                await scoped_options.first.wait_for(
                    state="attached", timeout=5000
                )
            except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                pass

            count = await scoped_options.count()

            target_text = creation_declaration.strip()
            clicked = False
            for i in range(count):
                opt = scoped_options.nth(i)
                span = opt.locator("span").first
                opt_text = (await span.text_content() or "").strip()
                if opt_text == target_text:
                    await opt.click()
                    logger.info(
                        f"[上传视频] selected creation declaration: "
                        f"{opt_text}"
                    )
                    clicked = True
                    break

            if not clicked:
                logger.info(
                    f"[上传视频] creation declaration option not found: "
                    f"{target_text}"
                )

            await asyncio.sleep(1)

            # 创作声明=转载 时, B 站会展开转载来源输入框(B 站要求必填)。
            # DOM: div.statement-source input.input-val
            #      (placeholder 含「转载视频请注明来源」)
            # 选的不是转载则没有该输入框, 自然跳过。
            if clicked and target_text == "内容为转载" and repost_source:
                try:
                    repost_input = page.locator(
                        'div.statement-source input.input-val'
                    ).first
                    # 注意: wait_for 成功返回 None(不能作 if 条件!),
                    # 否则填入块被静默跳过。失败才抛异常 → 走 except。
                    await repost_input.wait_for(state="visible", timeout=3000)
                    await repost_input.click()
                    await repost_input.fill("")
                    await repost_input.press_sequentially(repost_source, delay=30)
                    logger.info(
                        f"[上传视频] repost source filled: "
                        f"{repost_source}"
                    )
                    await asyncio.sleep(0.5)
                except Exception as repost_exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info(
                        f"[上传视频] repost source fill failed (non-fatal): "
                        f"{repost_exc}"
                    )
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(
                f"[上传视频] creation declaration failed (non-fatal): "
                f"{exc}"
            )

    @staticmethod
    async def _set_collection(page, collection_name: str) -> None:
        """点击「请选择合集」并选择指定合集。

        DOM 定位(禁用 data-v 随机串):
          - 入口:「请选择合集」文案(get_by_text)
          - 下拉选项:season-item-title 是组件库固定语义 class(非随机串),
            按合集名称文本匹配后点击该选项。
          - 失败不阻塞发布(合集是可选项)。
        """
        if not collection_name:
            return

        try:
            # 1. 点击「请选择合集」入口
            entry = page.get_by_text("请选择合集", exact=True)
            if await entry.count() == 0:
                logger.warning("[设置合集] 未找到「请选择合集」入口,跳过")
                return
            await entry.first.click()
            await asyncio.sleep(1.5)
            logger.info("[设置合集] 已点击「请选择合集」")

            # 2. 在下拉浮层里按合集名称匹配选项
            # season-item-title 是组件库固定语义 class(非 data-v 随机串)
            option_items = page.locator(".season-item-title")
            # 等下拉出现(最多 10s)
            ready = False
            for _ in range(20):
                if await option_items.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                logger.warning("[设置合集] 下拉浮层未出现,跳过")
                return

            count = await option_items.count()
            for i in range(count):
                name = (await option_items.nth(i).inner_text()).strip()
                if name == collection_name:
                    # 点击合集项(点 season-item-title 的父级 season-item 更稳)
                    parent = option_items.nth(i).locator("xpath=ancestor::div[contains(@class,'season-item')][1]")
                    try:
                        await parent.first.click(timeout=3000)
                    except Exception:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                        await option_items.nth(i).click()
                    logger.info("[设置合集] 已选择合集: %s", collection_name)
                    await asyncio.sleep(1)
                    return

            logger.warning("[设置合集] 未找到合集: %s", collection_name)
            # 关闭下拉
            await page.keyboard.press("Escape")
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[设置合集] 合集设置失败(非致命): %s", e)

