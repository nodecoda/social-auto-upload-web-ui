"""Weibo platform implementation — CloakBrowser."""

import asyncio
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR
from util._logger import bind_account_name, get_channel_logger

from .._utils import (
    get_account_name_by_cookie_file,
    save_login_result,
)
from ..base_platform import BasePlatform
from . import categories as _weibo_categories
from ._dom_ops import (
    _click_publish,
    _click_send,
    _pick_cover_by_aspect,
    _set_collection,
    _set_content_statement,
    _set_content_statement_v1,
    _set_content_statement_v2,
    _set_cover,
    _set_description,
    _set_title,
    _set_video_type,
    _upload_images,
    _upload_video_file,
    _wait_for_image_publish_success,
    _wait_for_publish_success,
    _wait_for_upload_form,
)
from ._image_ops import WeiboImageOps
from ._profile import scrape_weibo_profile

logger = get_channel_logger("weibo")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WEIBO_CREATOR_URL = "https://weibo.com/n/微博创作者中心"
_WEIBO_LOGIN_HOST = "passport.weibo.com"
_WEIBO_LOGIN_PATH = "/sso/signin"
_WEIBO_UPLOAD_URL = "https://weibo.com/upload/channel"

#: 类型 radio 文本 → weibo 内部 video_type 编码
_VIDEO_TYPE_MAP = {
    "原创": "0",
    "转载": "1",
    "二创": "2",
}


# ======================================================================
# WeiboPlatform
# ======================================================================

class WeiboPlatform(WeiboImageOps, BasePlatform):

    _upload_images = staticmethod(_upload_images)
    _click_send = staticmethod(_click_send)
    _wait_for_image_publish_success = staticmethod(_wait_for_image_publish_success)
    _upload_video_file = staticmethod(_upload_video_file)
    _wait_for_upload_form = staticmethod(_wait_for_upload_form)
    _set_video_type = staticmethod(_set_video_type)
    _set_title = staticmethod(_set_title)
    _pick_cover_by_aspect = staticmethod(_pick_cover_by_aspect)
    _set_cover = staticmethod(_set_cover)
    _set_collection = staticmethod(_set_collection)
    _set_description = staticmethod(_set_description)
    _set_content_statement = staticmethod(_set_content_statement)
    _set_content_statement_v1 = staticmethod(_set_content_statement_v1)
    _set_content_statement_v2 = staticmethod(_set_content_statement_v2)
    _click_publish = staticmethod(_click_publish)
    _wait_for_publish_success = staticmethod(_wait_for_publish_success)

    # ---- Cookie 校验参数（基类探针 session_verify 使用, 提炼自原 check_cookie）----
    CHECK_URL = "https://weibo.com/n/微博创作者中心"
    CHECK_NETWORKIDLE = True
    CHECK_VALID_SELECTOR = '.woo-tab-nav a[href^="/u/"] img[src*="sinaimg.cn"]'
    CHECK_SLEEP = 0.0
    platform_id = 11
    platform_key = "weibo"
    platform_name = "微博"
    supports_image = True  # 图集发布能力（A4 门控）

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    platform_cookie_domain = ".weibo.com"

    # ------------------------------------------------------------------
    # login()
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Weibo login.

        Real flow (per user testing, 2026-06-15):
        1. Goto ``weibo.com/n/微博创作者中心`` (the creator centre home).
        2. The "登录" link is in the top-right of the page; click it.
        3. Clicking triggers a popup / new tab / redirect to
           ``passport.weibo.com/sso/signin``.
        4. User completes login in the popup (QR scan, phone, password, etc.).
        5. After login, the main page auto-refreshes and shows the user's avatar
           and nickname in the top nav (rendered as ``a[href^="/u/"]`` containing
           an ``img[src*="sinaimg.cn"]``).
        6. ``save_login_result`` runs on the now-authenticated main page.

        No timeout: the user may take as long as needed. Browser close → task
        cancel (handled by ``login_mode=True`` in ``_browser.py``).
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()

                await page.goto(_WEIBO_CREATOR_URL)

                # Scroll a small amount (200px) just in case, but rely on text selector
                await page.evaluate("window.scrollTo(0, 200)")
                await asyncio.sleep(0.5)

                # Click the "登录" link by text (robust against hash class changes).
                # NB: <a> 不带 href 在现代浏览器中没有 link role，所以不能用
                # get_by_role("link", ...)。get_by_text 匹配文本节点，不依赖角色。
                login_link = page.get_by_text("登录").first
                await login_link.click(timeout=15000)
                logger.info("[weibo] login link clicked, waiting for user to complete login")

                # Wait indefinitely for the post-login profile link. The user
                # may take as long as needed; browser close → task cancel
                # (handled by login_mode=True in _browser.py).
                # 等待登录成功标志（无限等）：浏览器关闭由 login_mode=True 处理
                # 必须限定到顶部导航栏 .woo-tab-nav，否则未登录态主页面有热门博主
                # 链接（同样 a[href^="/u/"] img[src*="sinaimg.cn"]）会误判已登录
                await page.locator(
                    '.woo-tab-nav a[href^="/u/"] img[src*="sinaimg.cn"]'
                ).first.wait_for(timeout=999999999)
                logger.info("[weibo] login detected (profile link in top nav)")

                # Give the page a moment to render authenticated content
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

                await save_login_result(
                    context, page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_weibo_profile,
                    account_id=account_id,
                    # 登录成功后在同一个 session 内补抓 stats(粉丝/关注/转评赞),
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
        """Open the Weibo creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _WEIBO_CREATOR_URL

        from .._browser import close_browser

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
        """同步微博昵称、头像、运营数据(stats)。

        抓取流程:
        1. 访问 weibo.com 首页,点击右上角头像 → 跳转到个人主页 weibo.com/u/<id>
        2. 在个人主页抓 name/avatar/stats(粉丝/关注/转评赞)

        与 login 路径(使用 scrape_weibo_profile)独立,stats 不在原 scraper 里,
        这里新实现抓取。从个人主页一个 DOM 一次抓全 3 项 stats + 昵称头像。
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                # 1. 访问微博首页
                await page.goto("https://weibo.com/", wait_until="domcontentloaded", timeout=20000)
                try:  # noqa: SIM105
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:  # noqa: S110, BLE001 -- DOM/页面探测兜底,元素可能不存在
                    pass
                await asyncio.sleep(1)

                # 2. 点击右上角用户头像 → 跳转到个人主页
                try:
                    avatar_btn = page.locator('.woo-badge-box img').first
                    await avatar_btn.wait_for(state="visible", timeout=8000)
                    await avatar_btn.click()
                    # 等跳转到 /u/<id>
                    await page.wait_for_url("**/u/**", timeout=10000)
                except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info(f"[weibo] 点击头像跳转个人主页失败: {exc}")

                try:  # noqa: SIM105
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:  # noqa: S110, BLE001 -- DOM/页面探测兜底,元素可能不存在
                    pass
                await asyncio.sleep(1)

                # 3. 抓 name/avatar/stats(都在同一个 ._h3_/._h4_ 区块附近)
                result = await page.evaluate(
                    '''() => {
                        const out = {name: '', avatar: '', stats: []};
                        // 头像:.woo-avatar-img
                        const av = document.querySelector('.woo-avatar-img');
                        if (av) out.avatar = av.getAttribute('src') || '';
                        // 昵称:._name_1yc79_291(后端 hash 改了,用 [class*="_name_"] 兜底)
                        const nameEl = document.querySelector('[class*="_name_"]');
                        if (nameEl) out.name = (nameEl.textContent || '').trim();
                        // stats:3 个 _h5_ span,分别是 粉丝 / 关注 / 转评赞
                        document.querySelectorAll('[class*="_h5_"]').forEach(el => {
                            const numEl = el.querySelector('span');
                            const text = (el.textContent || '').trim();
                            if (!numEl) return;
                            const num = (numEl.textContent || '').trim();
                            // label 在 num 之后的文本里(例如 "2粉丝" 或 "粉丝 2")
                            // 简单规则:含"粉丝"→粉丝;含"关注"→关注;含"转评赞"→转评赞
                            if (text.includes('粉丝')) {
                                out.stats.push({name: '粉丝', num});
                            } else if (text.includes('转评赞')) {
                                out.stats.push({name: '转评赞', num});
                            } else if (text.includes('关注')) {
                                out.stats.push({name: '关注', num});
                            }
                        });
                        return out;
                    }'''
                )
                name = (result or {}).get('name', '')
                avatar = (result or {}).get('avatar', '')
                stats_raw = (result or {}).get('stats', [])

                # 组装 stats JSON
                stats = []
                label_map = {
                    "粉丝":   ("user",   1, "粉丝"),
                    "关注":   ("follow", 2, "关注"),
                    "转评赞": ("like",   3, "转评赞"),
                }
                for item in stats_raw:
                    label = item.get('name', '')
                    num = item.get('num', '0')
                    if label in label_map:
                        icon, sort_no, std_name = label_map[label]
                        try:
                            count = int(str(num).replace(',', '').replace(' ', '') or '0')
                        except (ValueError, TypeError):
                            count = 0
                        stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})

                if not name and not avatar and not stats:
                    logger.info(f"[weibo] sync_profile 抓取为空,url={page.url}")

                return {"name": name, "avatar": avatar, "stats": stats}
            except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                logger.info(f"[weibo] sync profile failed: {e}")
                return {"name": "", "avatar": "", "stats": []}
            finally:
                await context.close()
        finally:
            await self.close_browser(browser)

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口(供 save_login_result 调用)。

        与 sync_profile 内部共用同一套 js evaluate 抓取逻辑。
        """
        try:
            await asyncio.sleep(1)
            result = await page.evaluate(
                '''() => {
                    const out = [];
                    document.querySelectorAll('[class*="_h5_"]').forEach(el => {
                        const numEl = el.querySelector('span');
                        const text = (el.textContent || '').trim();
                        if (!numEl) return;
                        const num = (numEl.textContent || '').trim();
                        if (text.includes('粉丝')) out.push({name:'粉丝', num});
                        else if (text.includes('转评赞')) out.push({name:'转评赞', num});
                        else if (text.includes('关注')) out.push({name:'关注', num});
                    });
                    return out;
                }'''
            )
            label_map = {
                "粉丝":   ("user",   1, "粉丝"),
                "关注":   ("follow", 2, "关注"),
                "转评赞": ("like",   3, "转评赞"),
            }
            stats = []
            for item in (result or []):
                label = item.get('name', '')
                num = item.get('num', '0')
                if label in label_map:
                    icon, sort_no, std_name = label_map[label]
                    try:
                        count = int(str(num).replace(',', '').replace(' ', '') or '0')
                    except (ValueError, TypeError):
                        count = 0
                    stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})
            return stats
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[weibo login] _login_stats_fn 抓取失败: {exc}")
            return [] 

    # ------------------------------------------------------------------
    # publish_video -- full Weibo upload pipeline (sync entry point)
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to Weibo (sync wrapper).

        Accepted keyword arguments (与百家号保持一致):

        - ``title`` (*str*) -- 视频标题(0~30 字)
        - ``files`` (*list[str]*) -- 视频绝对路径(app.py 解析过)
        - ``tags`` (*list[str]*) -- 话题(暂未支持,占位)
        - ``account_file`` (*list[str]*) -- cookie 文件名列表
        - ``thumbnail_landscape_path`` (*str*, optional) -- 横版封面
        - ``thumbnail_portrait_path`` (*str*, optional) -- 竖版封面
        - ``desc`` (*str*, optional) -- 微博正文
        - ``category`` (*list[str]*|*str*, optional) -- 级联分类
          ``[channel_name, sub_name]``;也兼容 ``"channel|sub"`` 字符串
        - ``ai_content`` (*str*, optional) -- 类型声明(原创/二创/转载)

        V1 暂不支持定时发布;``schedule_time_str`` 等参数被忽略。
        """
        try:
            await self._upload_all(**kwargs)
        except Exception as e:
            logger.exception("[发布失败] 微博 publish_video 异常: %s", e)
            return False
        return True

    # ------------------------------------------------------------------
    # publish_image -- full Weibo image-album pipeline (sync entry point)
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Internal: orchestrate all account uploads (one batch per account)
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Internal: upload one image album to one account
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Helper: upload image files via hidden input[type=file]
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Helper: click 发送 button
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Helper: wait for image publish success signal
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Internal: orchestrate all file × account uploads
    # ------------------------------------------------------------------

    async def _upload_all(self, **kwargs):
        """Create a browser per file+account combo and upload."""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始微博视频发布流程")
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
        # 16:9 / 9:16 封面(微博封面框实际比例,优先于 4:3 / 3:4 使用)
        thumbnail_landscape_169_path = kwargs.get("thumbnail_landscape_169_path")
        thumbnail_portrait_916_path = kwargs.get("thumbnail_portrait_916_path")
        desc = kwargs.get("desc", "") or ""
        category = kwargs.get("category")
        ai_content = kwargs.get("ai_content", "") or ""
        content_statement = kwargs.get("content_statement", "") or ""
        content_statement2 = kwargs.get("content_statement2", "") or ""
        content_statement2_optional = kwargs.get("content_statement2_optional", "") or ""
        weibo_collection = kwargs.get("weibo_collection", "") or ""

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")
        logger.info("[发布参数] 分类: %s", category or "无")
        logger.info("[发布参数] 类型声明: %s", ai_content or "无")
        logger.info("[发布参数] 内容声明: %s", content_statement or "无")
        logger.info("[发布参数] 微博合集: %s", weibo_collection or "无")
        logger.info("[发布策略] 发布策略: immediate")

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
                        thumbnail_landscape_169_path=thumbnail_landscape_169_path,
                        thumbnail_portrait_916_path=thumbnail_portrait_916_path,
                        desc=desc,
                        category=category,
                        ai_content=ai_content,
                        content_statement=content_statement,
                        content_statement2=content_statement2,
                        content_statement2_optional=content_statement2_optional,
                        weibo_collection=weibo_collection,
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)

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
        thumbnail_landscape_169_path=None,
        thumbnail_portrait_916_path=None,
        desc="",
        category=None,
        ai_content="",
        content_statement="",
        content_statement2="",
        content_statement2_optional="",
        weibo_collection="",
    ):
        """Upload a single video to one Weibo account."""
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
                await page.goto(_WEIBO_UPLOAD_URL, timeout=60000)
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
                logger.info("[上传视频] 开始上传视频: %s", title)

                # 注册 weibocdn 上传请求监听(spec line 7215-7216)
                # 这是上传完成的权威信号; 同时打印每个分块请求便于诊断
                upload_req_count = {"n": 0}
                upload_resp_count = {"n": 0}

                def _on_upload_request(request):
                    url = request.url
                    # 监听所有 fileplatform 相关请求(不只 upload.json)
                    # 看 drop 上传完成后是否缺了某个"完成/合并"请求
                    if "fileplatform" in url or (
                        "weibocdn.com" in url and "upload" in url.lower()
                    ):
                        upload_req_count["n"] += 1
                        logger.info(
                            "[上传视频] ▲ 请求 #%d %s %s",
                            upload_req_count["n"], request.method, url[:200],
                        )

                async def _on_upload_response(response):
                    url = response.url
                    if "fileplatform" in url or (
                        "weibocdn.com" in url and "upload" in url.lower()
                    ):
                        upload_resp_count["n"] += 1
                        # 读响应 body,看协议字段(最后一个分块可能有特殊标记)
                        body_preview = ""
                        try:
                            body = await response.text()
                            body_preview = body[:500].replace("\n", " ")
                        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                            body_preview = f"<body 读取失败: {e}>"
                        logger.info(
                            "[上传视频] ▼ 响应 #%d status=%d body=%s",
                            upload_resp_count["n"], response.status,
                            body_preview,
                        )

                page.on("request", _on_upload_request)
                page.on("response", _on_upload_response)

                # 上传视频文件
                logger.info("[上传视频] 正在上传视频文件...")
                await self._upload_video_file(page, file_path)

                # 等待视频真正上传完成(「上传中」spinner DOM 消失 = 上传完成)
                await self._wait_for_upload_form(page)
                logger.info("[上传视频] 视频上传成功!")

                # 类型(原创/二创/转载)
                logger.info("[类型声明] 开始设置类型(原创/二创/转载): %s", ai_content or "无")
                await self._set_video_type(page, ai_content)

                # 标题
                logger.info("[填写标题] 开始填写标题: %s", title)
                await self._set_title(page, title)
                logger.info("[填写标题] 标题填写完成")

                # 封面(ESC 关闭原生选择器 + 隐藏 input)
                logger.info("[设置封面] 开始设置视频封面...")
                await self._set_cover(
                    page,
                    thumbnail_landscape_path,
                    thumbnail_portrait_path,
                    thumbnail_landscape_169_path,
                    thumbnail_portrait_916_path,
                )
                logger.info("[设置封面] 封面设置完成")

                # 分类(两级级联)
                logger.info("[设置分类] 开始设置分类: %s", category or "无")
                await self._set_category(page, category)

                # 合集(可选):切换「加入合集」开关 + 勾选对应合集项
                if weibo_collection:
                    logger.info("[设置合集] 开始选择微博合集: %s", weibo_collection)
                    await self._set_collection(page, weibo_collection)
                else:
                    logger.info("[设置合集] 未选择合集,跳过")

                # 微博正文
                logger.info("[填写简介] 开始填写微博正文...")
                await self._set_description(page, desc, title, tags)

                # 内容声明(可选):自动探测版本1弹窗 / 版本2必选+可选下拉
                logger.info(
                    "[内容声明] 开始设置内容声明: 版本1=%s, 版本2必选=%s, 版本2可选=%s",
                    content_statement or "无", content_statement2 or "无", content_statement2_optional or "无",
                )
                await self._set_content_statement(
                    page, content_statement, content_statement2, content_statement2_optional
                )

                # 点发布
                logger.info("[发布] 正在点击发布按钮...")
                await self._click_publish(page)

                # 等待发布成功标志
                await self._wait_for_publish_success(page)
                logger.info("[发布] 视频发布成功!")

                # 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[发布] Cookie状态已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

    # ------------------------------------------------------------------
    # Helper: upload the video file via hidden input[type=file]
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Helper: wait for upload to finish and the form to appear
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Helper: select video type (原创/二创/转载)
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Helper: fill video title
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Helper: 根据页面封面区域宽高比选横版/竖版封面
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Helper: upload cover (click 上传封面 → ESC → hidden file input → 完成)
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # Helper: set category via 2-level cascade selector
    # ------------------------------------------------------------------

    async def _set_category(self, page, category):
        """选择分类(两级级联)。

        ``category`` 可为:
        - ``["VLOG", "旅行"]`` (前端 cascader 默认传数组)
        - ``"VLOG|旅行"`` (兼容字符串)
        - ``None`` (跳过,使用默认)
        """
        if not category:
            logger.info("[发布] 未传分类,使用默认")
            return

        if isinstance(category, str):
            parts = [p.strip() for p in category.split("|")]
            if len(parts) != 2:
                logger.warning("[发布] 分类字符串格式错误: %s", category)
                return
            channel_name, sub_name = parts
        elif isinstance(category, (list, tuple)) and len(category) == 2:
            channel_name, sub_name = category[0], category[1]
        else:
            logger.warning("[发布] 分类参数无法识别: %r", category)
            return

        # 查表验证
        found = _weibo_categories.lookup_sub_channel(channel_name, sub_name)
        if not found:
            logger.warning(
                "[发布] 分类未在静态表里命中: %s/%s,仍尝试在页面上点",
                channel_name, sub_name,
            )

        # 级联下拉触发器: 初始有「请选择合适的频道」占位文本
        # 2026-06-17 实测:占位文本所在 inner div(woo-box-item-flex)
        # 被 Playwright 判 hidden(24× retry → timeout),不能直接点它,
        # 也不要用 wait_for(state="visible")。改用:
        # 1. wait_for(state="attached") — 只要在 DOM 里就行
        # 2. 点父级 trigger (wbpro-select 元素)
        # 3. force=True 绕过任何拦截检查
        trigger_text = page.get_by_text("请选择合适的频道", exact=True)
        try:
            await trigger_text.first.wait_for(state="attached", timeout=10000)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[发布] 未找到分类下拉触发器(占位文本): %s", e)
            return

        # 1. 点开下拉 — 点父级 trigger (xpath=.. 是 Playwright 的"父节点"语法)
        trigger = trigger_text.first.locator("xpath=..")
        await trigger.click(force=True)
        await asyncio.sleep(0.5)

        # 下拉面板有两列: 左=频道,右=子分类。左列在 DOM 中先渲染,
        # 所以同名条目(如「美食」既是频道又是 VLOG 的子分类)取 first 得到频道,
        # 取 last 得到子分类。
        try:
            # 2. 等下拉打开: 已知频道「VLOG」必然在第一列
            await page.get_by_text("VLOG", exact=True).first.wait_for(
                state="visible", timeout=5000,
            )
            # 点目标频道(取 first: 频道列在前)
            await page.get_by_text(
                channel_name, exact=True,
            ).first.click()
            logger.info("[发布] 已选一级频道: %s", channel_name)
            await asyncio.sleep(0.5)

            # 3. 等子分类列渲染: 目标 sub_name 应可见
            # 取 last: 子分类列在频道列之后,避免点到同名的频道
            sub_locator = page.get_by_text(sub_name, exact=True)
            await sub_locator.last.wait_for(state="visible", timeout=5000)
            await sub_locator.last.click()
            logger.info("[发布] 已选二级子分类: %s", sub_name)
            await asyncio.sleep(0.5)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning(
                "[发布] 级联选择失败(channel=%s sub=%s): %s",
                channel_name, sub_name, e,
            )
            # ESC 关掉下拉避免挡住后续操作
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
