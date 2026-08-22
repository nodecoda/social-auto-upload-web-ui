"""
微信公众号平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

创作中心地址：https://mp.weixin.qq.com/

公众号的特殊点：登录成功后跳转的 URL 形如
  https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=124257639
其中的 ``token`` 是本次会话的临时令牌，所有后续功能（同步、状态检查、
创作中心跳转）都要带上。token 每次会话会变，因此**不存储陈旧 token**，
而是每次操作都先访问 ``https://mp.weixin.qq.com/``，让 cookie 自动触发跳转
到 ``/cgi-bin/home?...&token=XXX``，再从 URL 解析出最新 token 使用。
"""

import asyncio
import json
import os
import re
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
from ._dom_ops import (
    _build_home_url,
    _build_publish_datetime,
    _check_service_rule,
    _click_dialog_primary,
    _click_primary_when_enabled,
    _click_save_and_send,
    _click_time_wheel_item,
    _dismiss_upload_notice,
    _extract_token,
    _fill_description,
    _fill_material_title,
    _fill_publish_title,
    _find_visible_picker_dl_js,
    _is_wheel_item_selected,
    _publish_immediate,
    _publish_scheduled,
    _resolve_date_label,
    _resolve_token,
    _select_schedule_date,
    _select_schedule_time,
    _set_claim_source,
    _set_collection,
    _set_cover,
    _set_original,
    _upload_video_file,
    _wait_for_home,
    _wait_for_video_uploaded,
    _wheel_items_js_body,
)
from ._image_ops import WeixinGzhImageOps
from ._profile import scrape_weixin_gzh_profile

logger = get_channel_logger("weixin_gzh")

# 公众号首页入口（不带 token，访问后由 cookie 触发自动跳转到带 token 的 home）
_LOGIN_URL = "https://mp.weixin.qq.com/"
_HOME_PATH = "/cgi-bin/home"
_TOKEN_RE = re.compile(r"[?&]token=(\d+)")

# 素材上传页（token 由 _resolve_token 拼装）。
# 对应文档：cgi-bin/appmsg?t=media/videomsg_edit&action=video_edit&type=15&isNew=1
_MATERIAL_UPLOAD_PATH = (
    "https://mp.weixin.qq.com/cgi-bin/appmsg"
    "?t=media/videomsg_edit&action=video_edit&type=15&isNew=1"
    "&token={token}&lang=zh_CN"
)
# 合集管理页（合集数据来源，type=5 为视频合集），token 由 _resolve_token 拼装。
_ALBUM_MGR_PATH = (
    "https://mp.weixin.qq.com/cgi-bin/appmsgalbummgr"
    "?action=list&token={token}&lang=zh_CN&type=5"
)

# 创作来源声明：前端文案 → 公众号弹窗内 radio 的 value。
# 文档要求「素材来源官方媒体/网络新闻」(value=2) 暂时从选项里移除，故不在此映射。
_CLAIM_SOURCE_MAP = {
    "内容由AI生成": "1",
    "内容剧情演绎，仅供娱乐": "3",
    "个人观点，仅供参考": "4",
    "健康医疗分享，仅供参考": "5",
    "投资观点，仅供参考": "6",
    "无需声明": "0",
}

# Cookie 失效时公众号会跳转/渲染的登录页或失效提示标记。
# 任一命中即视为失效，不再依赖单一精确业务登录 URL。
_COOKIE_INVALID_URL_MARKERS = (
    "/cgi-bin/bizlogin",
    "/cgi-bin/loginpage",
)


class WeixinGzhPlatform(WeixinGzhImageOps, BasePlatform):

    _extract_token = staticmethod(_extract_token)
    _build_home_url = staticmethod(_build_home_url)
    _resolve_token = staticmethod(_resolve_token)
    _build_publish_datetime = staticmethod(_build_publish_datetime)
    _upload_video_file = staticmethod(_upload_video_file)
    _dismiss_upload_notice = staticmethod(_dismiss_upload_notice)
    _wait_for_video_uploaded = staticmethod(_wait_for_video_uploaded)
    _set_cover = staticmethod(_set_cover)
    _click_primary_when_enabled = staticmethod(_click_primary_when_enabled)
    _fill_material_title = staticmethod(_fill_material_title)
    _set_original = staticmethod(_set_original)
    _check_service_rule = staticmethod(_check_service_rule)
    _click_save_and_send = staticmethod(_click_save_and_send)
    _fill_publish_title = staticmethod(_fill_publish_title)
    _fill_description = staticmethod(_fill_description)
    _set_collection = staticmethod(_set_collection)
    _set_claim_source = staticmethod(_set_claim_source)
    _click_dialog_primary = staticmethod(_click_dialog_primary)
    _publish_immediate = staticmethod(_publish_immediate)
    _publish_scheduled = staticmethod(_publish_scheduled)
    _resolve_date_label = staticmethod(_resolve_date_label)
    _select_schedule_date = staticmethod(_select_schedule_date)
    _find_visible_picker_dl_js = staticmethod(_find_visible_picker_dl_js)
    _select_schedule_time = staticmethod(_select_schedule_time)
    _wheel_items_js_body = staticmethod(_wheel_items_js_body)
    _click_time_wheel_item = staticmethod(_click_time_wheel_item)
    _is_wheel_item_selected = staticmethod(_is_wheel_item_selected)
    _wait_for_home = staticmethod(_wait_for_home)

    # ---- Cookie 校验参数（基类探针 session_verify 使用, 提炼自原 check_cookie）----
    CHECK_URL = "https://mp.weixin.qq.com/"
    CHECK_SLEEP = 3.0
    CHECK_INVALID_URL_MARKERS = (
        "/cgi-bin/bizlogin",
        "/cgi-bin/loginpage",
    )
    CHECK_VALID_URL = (
        "/cgi-bin/home",
        "token=",
    )
    platform_id = 17
    platform_key = "weixin_gzh"
    platform_name = "微信公众号"
    supports_image = True  # 图集发布能力（A4 门控）

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    # 微信系 cookie 全部由 mp.weixin.qq.com 下发，通配 .qq.com 后对公众号
    # 创作中心及子域都生效（视频号 channels 同样用 .qq.com，cookie 文件
    # 各自独立存储，互不影响）。
    platform_cookie_domain = ".qq.com"

    # ------------------------------------------------------------------
    # helpers — token 提取与首页 URL 拼装
    # ------------------------------------------------------------------




    # ------------------------------------------------------------------
    # login — QR code scan via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """微信公众号扫码登录。

        打开 ``https://mp.weixin.qq.com/``，把页面二维码图片推送给前端；
        轮询 URL 检测登录成功（跳到 ``/cgi-bin/home`` 且带 ``token=``），
        成功后从 URL 提取最新 token 跳转到首页，再抓昵称/头像/运营数据写库。
        """
        logger.info("=" * 60)
        logger.info("[登录] 开始微信公众号登录流程")
        logger.info("=" * 60)

        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                logger.info("[登录] 正在打开微信公众号主页...")
                await page.goto(_LOGIN_URL, wait_until="domcontentloaded")
                await asyncio.sleep(3)

                # 提取页面二维码图片推给前端展示
                src = None
                qr_selectors = [
                    'img[class*="qrcode"]',
                    'img[class*="qr_code"]',
                    'img[class*="QRCode"]',
                    'img[id*="qr"]',
                    'div[class*="qrcode"] img',
                    'div.login_box img',
                    'img.weui-desktop-account__img',
                ]
                for selector in qr_selectors:
                    try:
                        img_locator = page.locator(selector).first
                        if await img_locator.count():
                            src = await img_locator.get_attribute("src")
                            if src and src.startswith(("http", "data:")):
                                logger.info("[登录] 找到二维码图片，选择器: %s", selector)
                                break
                            src = None
                    except Exception:  # noqa: S112, BLE001 -- 单次探测失败,跳过继续
                        continue

                if src:
                    logger.info("[登录] 二维码图片已发送到前端")
                    status_queue.put(src)
                else:
                    logger.warning("[登录] 未找到二维码图片（用户可在打开的浏览器中手动扫码）")
                    status_queue.put(json.dumps({"error": "无法找到登录二维码，请在打开的浏览器中手动扫码"}))

                # 等待登录：URL 跳到 /cgi-bin/home 且带 token=
                logger.info("[登录] 等待用户扫码...")
                max_wait = 300  # 5 minutes
                start_time = asyncio.get_running_loop().time()
                logged_in = False
                while (asyncio.get_running_loop().time() - start_time) < max_wait:
                    try:
                        current_url = page.url or ""
                        if _HOME_PATH in current_url and "token=" in current_url:
                            logger.info("[登录] 检测到页面跳转到首页，登录成功!")
                            logged_in = True
                            break
                    except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                        pass
                    await asyncio.sleep(1)

                if not logged_in:
                    logger.warning("[登录] 登录等待超时（5 分钟），未检测到登录成功")
                    return

                # 跳转到带 token 的首页，确保 DOM 完整渲染用于抓取
                token = self._extract_token(page)
                home_url = self._build_home_url(token)
                logger.info("[登录] 跳转到首页: %s", home_url)
                try:
                    await page.goto(home_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                    logger.info("[登录] 跳转首页超时(忽略，继续抓取): %s", e)
                await asyncio.sleep(3)

                # 抓昵称/头像并保存登录结果，登录后补抓 stats
                logger.info("[登录] 正在获取用户信息...")
                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_weixin_gzh_profile,
                    account_id=account_id,
                    stats_fn=self._login_stats_fn,
                )
                logger.info("[登录] 登录流程完成!")
                success = True
            finally:
                await context.close()
        finally:
            if success:
                await self.close_browser(browser)

    # ------------------------------------------------------------------
    # check_cookie — verify stored cookie is still valid
    # ------------------------------------------------------------------


    async def sync_profile(self, cookie_file: str) -> dict:
        """同步公众号昵称、头像、运营数据(stats)。

        用 cookie 打开 ``https://mp.weixin.qq.com/`` 自动跳转到带 token 的
        首页，从首页 DOM 抓取：
          - 昵称：.weui-desktop_name
          - 头像：.weui-desktop-account__img 的 src
          - 运营数据：原创内容(.original_cnt span)、总用户数(.weui-desktop-user_num
            .weui-desktop-user_sum span)
        """
        logger.info("[同步资料] 开始同步用户资料: %s", cookie_file)
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # 跳转到带 token 的首页（cookie 触发自动跳转后 token 已在 URL）
                token = self._extract_token(page)
                home_url = self._build_home_url(token)
                logger.info("[同步资料] 跳转到首页: %s", home_url)
                try:  # noqa: SIM105
                    await page.goto(home_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:  # noqa: S110, BLE001 -- 页面加载兜底,超时继续后续逻辑
                    pass
                await asyncio.sleep(3)

                # 抓昵称/头像
                name, avatar = await scrape_weixin_gzh_profile(page)
                logger.info(
                    "[同步资料] 获取到用户信息 - 昵称: %s, 头像: %s",
                    name, avatar[:50] if avatar else "无"
                )

                # 抓运营数据
                stats = await self._scrape_stats(page)

                if not name and not avatar and not stats:
                    logger.info(f"[weixin_gzh] sync_profile 抓取为空, url={page.url}")

                return {"name": name, "avatar": avatar, "stats": stats}
            finally:
                await context.close()
        finally:
            await self.close_browser(browser)

    async def _scrape_stats(self, page) -> list:
        """从公众号首页 DOM 抓取运营数据。

        DOM 结构（用户提供）：
          <div class="weui-desktop-content">原创内容
            <div class="weui-desktop-user_sum original_cnt"><span>2</span></div>
          </div>
          <div class="weui-desktop-user_num">总用户数
            <div class="weui-desktop-user_sum"><span>11</span></div>
          </div>
        """
        try:
            current_url = ""
            try:  # noqa: SIM105
                current_url = page.url or ""
            except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                pass
            logger.info("[stats] 开始抓取运营数据, 当前页面: %s", current_url)

            try:
                await page.wait_for_selector(".weui-desktop-user_sum", timeout=8000)
                logger.info("[stats] .weui-desktop-user_sum 元素已就绪")
            except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
                logger.warning("[stats] 等待 .weui-desktop-user_sum 超时: %s", e)

            result = await page.evaluate(
                '''() => {
                    const out = [];
                    // 原创内容数
                    const originalEl = document.querySelector('.original_cnt span')
                        || document.querySelector('.original_cnt');
                    if (originalEl) {
                        out.push({title: '原创内容', num: (originalEl.textContent || '').trim()});
                    }
                    // 总用户数
                    const userNumWrap = document.querySelector('.weui-desktop-user_num');
                    if (userNumWrap) {
                        const numEl = userNumWrap.querySelector('.weui-desktop-user_sum span')
                            || userNumWrap.querySelector('.weui-desktop-user_sum');
                        if (numEl) {
                            out.push({title: '总用户数', num: (numEl.textContent || '').trim()});
                        }
                    }
                    return out;
                }'''
            )
            logger.info("[stats] DOM 抓取原始结果: %s", result)

            # label_map: 标题文 -> (ICON, SORT, 标准化 NAME)
            label_map = {
                "原创内容": ("edit", 1, "原创内容"),
                "总用户数": ("user",  2, "总用户数"),
            }
            stats = []
            for item in (result or []):
                title = item.get('title', '')
                num_str = str(item.get('num', '0'))
                if title in label_map:
                    icon, sort_no, std_name = label_map[title]
                    cleaned = num_str.replace(',', '').replace(' ', '').strip()
                    try:
                        count = int(float(cleaned)) if '.' in cleaned else int(cleaned) if cleaned else 0
                    except (ValueError, TypeError):
                        count = 0
                    stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})
            logger.info("[stats] 解析得到 %d 项运营数据: %s", len(stats), stats)
            return stats
        except Exception as e:
            logger.exception("[stats] 抓取运营数据异常: %s", e)
            return []

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口（供 save_login_result 调用）。

        与 sync_profile._scrape_stats 共用同一份抓取逻辑，保证登录后同步
        与同步按钮看到的运营数据一致。
        """
        logger.info("[登录stats] 开始补抓运营数据, account_id=%s", account_id)
        try:
            # 登录路径下页面已在首页，但有时 DOM 还未渲染完，额外等待兜底
            await asyncio.sleep(2)
            stats = await self._scrape_stats(page)
            logger.info("[登录stats] 补抓完成, 共 %d 项", len(stats))
            return stats
        except Exception as e:
            logger.exception("[登录stats] 补抓异常: %s", e)
            return []

    # ------------------------------------------------------------------
    # open_creator_center — visible browser window
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """用可见浏览器打开微信公众号创作中心首页。

        cookie 自动带上，访问 ``https://mp.weixin.qq.com/`` 后会自动跳转到
        带 token 的首页。
        """
        logger.info("[打开创作中心] 正在打开创作中心...")
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _LOGIN_URL

        def _launch():
            browser = self.create_browser_sync(headless=False)
            try:
                context = self.create_context_sync(browser, storage_state=cookie_path)
                page = context.new_page()
                page.goto(url)
                logger.info("[打开创作中心] 创作中心已打开")
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
    # publish_video — 公众号视频发布（同步入口）
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to WeChat Official Account (sync wrapper).

        Accepted keyword arguments (与其它平台保持一致):

        - ``title`` (*str*) -- 视频标题(≤64 字)
        - ``files`` (*list[str]*) -- 视频绝对路径(app.py 解析过)
        - ``tags`` (*list[str]*) -- 话题,拼成 #话题 写进描述(占位)
        - ``account_file`` (*list[str]*) -- cookie 文件名列表
        - ``thumbnail_landscape_169_path`` (*str*, optional) -- 16:9 封面(公众号固定用 16:9)
        - ``thumbnail_landscape_path`` / ``thumbnail_portrait_path`` -- 兜底封面
        - ``desc`` (*str*, optional) -- 视频介绍(≤300 字, 含 # 标签)
        - ``is_original`` (*bool*, optional) -- 声明原创
        - ``gzh_collection_name`` (*str*, optional) -- 合集名
        - ``gzh_claim_source`` (*str*, optional) -- 创作来源(文案)
        - ``enableTimer`` (*bool*, optional) -- 定时发布
        - ``schedule_time_str`` (*str*, optional) -- 定时时间
        """
        try:
            await self._upload_all(**kwargs)
        except Exception as e:
            logger.exception("[发布失败] 微信公众号 publish_video 异常: %s", e)
            return False
        return True

    # ------------------------------------------------------------------
    # Internal: upload all (files × accounts)
    # ------------------------------------------------------------------

    async def _upload_all(self, **kwargs):
        """files × accounts 笛卡尔积编排(与微博保持一致)。"""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始微信公众号视频发布流程")
        logger.info("=" * 60)

        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", []) or []
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", []) or []
        thumbnail_169 = kwargs.get("thumbnail_landscape_169_path")
        thumbnail_landscape = kwargs.get("thumbnail_landscape_path")
        thumbnail_portrait = kwargs.get("thumbnail_portrait_path")
        desc = kwargs.get("desc", "") or ""
        is_original = kwargs.get("is_original", False)
        gzh_collection_name = kwargs.get("gzh_collection_name", "") or ""
        gzh_claim_source = kwargs.get("gzh_claim_source", "") or ""
        enable_timer = kwargs.get("enableTimer", False)
        schedule_time_str = kwargs.get("schedule_time_str", "")

        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 16:9 封面: %s", thumbnail_169 or "无")
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait or "无")
        logger.info("[发布参数] 原创: %s", is_original)
        logger.info("[发布参数] 合集: %s", gzh_collection_name or "无")
        logger.info("[发布参数] 创作来源: %s", gzh_claim_source or "无")
        logger.info("[发布参数] 定时发布: %s", enable_timer)

        # 公众号封面固定使用 16:9;前端没传 169 时用横版兜底
        cover_path = thumbnail_169 or thumbnail_landscape or thumbnail_portrait

        account_paths = [str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file]
        file_paths = [str(f) for f in files]
        if cover_path:
            cover_path = str(cover_path)

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
                        cover_path=cover_path,
                        desc=desc,
                        is_original=is_original,
                        gzh_collection_name=gzh_collection_name,
                        gzh_claim_source=gzh_claim_source,
                        enable_timer=enable_timer,
                        schedule_time_str=schedule_time_str,
                        files_count=len(file_paths),
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Internal: upload one video to one account (two-stage flow)
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        account_file: str,
        cover_path=None,
        desc="",
        is_original=False,
        gzh_collection_name="",
        gzh_claim_source="",
        enable_timer=False,
        schedule_time_str="",
        files_count=1,
    ):
        """单视频单账号完整两阶段发布。

        阶段① 素材上传页 videomsg_edit: 传视频→封面→标题→原创→服务规则→保存并发表
        阶段② 发布编辑页 appmsg_edit_v2(新 tab): 标题/描述→合集→创作来源→发表/定时
        """
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

                # 解析当前会话 token
                token = await self._resolve_token(page)
                if not token:
                    raise RuntimeError("[发布] 未能获取 token,cookie 可能已失效")
                logger.info("[发布] 获取到 token: %s", token)

                # ===== 阶段① 素材上传页 =====
                material_url = _MATERIAL_UPLOAD_PATH.format(token=token)
                logger.info("[阶段①] 打开素材上传页: %s", material_url)
                await page.goto(material_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                # 1. 上传视频文件
                logger.info("[阶段①] 上传视频文件: %s", os.path.basename(file_path))
                await self._upload_video_file(page, file_path)

                # 2. 等待视频上传完成
                logger.info("[阶段①] 等待视频上传完成...")
                await self._wait_for_video_uploaded(page)
                logger.info("[阶段①] 视频上传成功!")
                # 关闭上传成功通知("知道了"弹窗)
                await self._dismiss_upload_notice(page)

                # 3. 封面(公众号固定 16:9)
                if cover_path:
                    logger.info("[阶段①] 开始设置封面...")
                    await self._set_cover(page, cover_path)
                    logger.info("[阶段①] 封面设置完成")
                else:
                    logger.info("[阶段①] 未提供封面,跳过")

                # 4. 标题
                logger.info("[阶段①] 填写标题: %s", title)
                await self._fill_material_title(page, title)

                # 5. 原创声明
                if is_original:
                    logger.info("[阶段①] 开启原创声明...")
                    await self._set_original(page)
                else:
                    logger.info("[阶段①] 未开启原创,跳过")

                # 6. 勾选服务规则
                logger.info("[阶段①] 勾选服务规则...")
                await self._check_service_rule(page)

                # 7. 保存并发表(打开新 tab 进入阶段②)
                logger.info("[阶段①] 点击「保存并发表」,等待新页面打开...")
                page2 = await self._click_save_and_send(page, context)
                logger.info("[阶段②] 新页面已打开: %s", page2.url)

                # ===== 阶段② 发布编辑页 =====
                await page2.wait_for_load_state("domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                # 1. 再次填标题(发布页标题独立于素材标题)
                logger.info("[阶段②] 填写发布页标题: %s", title)
                await self._fill_publish_title(page2, title)

                # 2. 描述(含 # 标签)
                logger.info("[阶段②] 填写描述/标签...")
                await self._fill_description(page2, desc, title, tags)

                # 3. 合集
                if gzh_collection_name:
                    logger.info("[阶段②] 选择合集: %s", gzh_collection_name)
                    await self._set_collection(page2, gzh_collection_name)
                else:
                    logger.info("[阶段②] 未选择合集,跳过")

                # 4. 创作来源
                if gzh_claim_source:
                    logger.info("[阶段②] 设置创作来源: %s", gzh_claim_source)
                    await self._set_claim_source(page2, gzh_claim_source)
                else:
                    logger.info("[阶段②] 未设置创作来源,跳过")

                # 5. 发表(立即 / 定时)
                if enable_timer and schedule_time_str:
                    publish_dt = self._build_publish_datetime(schedule_time_str, files_count)
                    if publish_dt and not (isinstance(publish_dt, int) and publish_dt == 0):
                        logger.info("[阶段②] 定时发布: %s", publish_dt)
                        await self._publish_scheduled(page2, publish_dt)
                    else:
                        logger.info("[阶段②] 定时时间解析失败,改为立即发表")
                        await self._publish_immediate(page2)
                else:
                    logger.info("[阶段②] 立即发表...")
                    await self._publish_immediate(page2)

                logger.info("[发布] 视频发布成功!")

                # 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[发布] Cookie 状态已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)
