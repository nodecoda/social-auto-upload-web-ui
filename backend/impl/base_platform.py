"""
Abstract base class for all social media platform implementations.

Each platform (Douyin, Xiaohongshu, Bilibili, etc.) must subclass BasePlatform
and implement the abstract methods. Browser entry points delegate to
``_browser.py`` (CloakBrowser stealth layer).
"""

import asyncio
import json
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from queue import Queue

from conf import BASE_DIR
from util._logger import get_channel_logger

from ._browser import (
    close_browser as _close_browser,
)
from ._browser import (
    create_browser as _create_browser,
)
from ._browser import (
    create_browser_sync as _create_browser_sync,
)
from ._browser import (
    create_context as _create_context,
)
from ._browser import (
    create_context_sync as _create_context_sync,
)
from ._browser import (
    create_persistent_context as _create_persistent_context,
)

_base_logger = get_channel_logger("base_platform")


class BasePlatform(ABC):
    """Abstract base for platform-specific automation logic."""

    platform_id: int = 0
    platform_key: str = ""
    platform_name: str = ""

    # ------------------------------------------------------------------
    # Cookie import capability
    # ------------------------------------------------------------------

    #: True if this platform supports importing accounts from a raw cookie
    #: string (e.g. pasted from browser DevTools).  Subclasses override.
    supports_cookie_import: bool = False

    #: True if this platform implements publish_image (图集发布能力)。
    #: 契约测试锁定与 publish_image 实现一致性；task_queue 分发前校验，
    #: 不支持的平台任务直接 failed（不抛 NotImplementedError 进队列）。
    supports_image: bool = False

    #: The wildcard domain to attach imported cookies to, e.g. ``".baidu.com"``
    #: for Baijiahao (cookie issued by passport.baidu.com also applies to
    #: baijiahao.baidu.com).  Subclasses override; most platforms can simply
    #: set this to ``f".{platform_key}.com"`` or similar.
    platform_cookie_domain: str = ""

    # ------------------------------------------------------------------
    # Unified browser entry points (delegate to _browser.py / CloakBrowser)
    # ------------------------------------------------------------------

    async def create_browser(
        self,
        headless: bool | None = None,
        login_mode: bool = False,
        humanize: bool = False,
        human_preset: str = "default",
    ):
        """Create a stealth Chromium browser via CloakBrowser.

        humanize=True 启用 CloakBrowser 拟人化操作层，仅建议在发布动作
        开启（会让操作明显变慢，login/cookie 校验等场景保持默认关闭）。
        """
        return await _create_browser(
            headless=headless,
            login_mode=login_mode,
            humanize=humanize,
            human_preset=human_preset,
        )

    async def create_context(
        self,
        browser,
        storage_state: str | None = None,
        user_agent: str | None = None,
    ):
        """Create a browser context (optionally with stored auth state)."""
        return await _create_context(
            browser,
            storage_state=storage_state,
            user_agent=user_agent,
        )

    async def close_browser(self, browser, is_close_by_code: bool = True) -> None:
        """统一关闭浏览器入口（发布/图集收尾用）。

        Args:
            browser: create_browser 返回的 browser 对象。
            is_close_by_code: True=代码主动关闭（发布成功/失败收尾），
                此时 _browser.py 的 watchdog/disconnected 监听不会 cancel
                当前 task（正常收尾）；False 仅用于特殊场景，一般不需要。
                默认 True，因为只有发布收尾才会调本方法。

        各平台发布/图集上传方法在成功/失败 finally 里关闭浏览器时，
        应统一调用本方法（而非直接 browser.close()），确保 watchdog
        不会把「代码主动关闭」误判为「用户手动关闭」而触发 task cancel。

        模块级发布函数（无 self，如 xiaohongshu._publish_single_video）
        直接调用 _browser.close_browser；本方法为其提供类内调用入口。
        """
        await _close_browser(browser, is_close_by_code=is_close_by_code)

    def create_browser_sync(self, headless: bool = False):
        """同步创建浏览器入口（A5: 收敛 20/20 平台直调 _browser.create_browser_sync）。

        与 close_browser 对齐：平台发布/图集收尾只调 self.* 统一入口，
        不再直接 import .._browser 的函数，保证生命周期入口单一。
        """
        return _create_browser_sync(headless=headless)

    def create_context_sync(
        self,
        browser,
        storage_state: str | None = None,
        user_agent: str | None = None,
    ):
        """同步创建 context 入口（A5，同上收敛理由）。"""
        return _create_context_sync(
            browser,
            storage_state=storage_state,
            user_agent=user_agent,
        )

    async def create_persistent_context(
        self,
        user_data_dir: str,
        headless: bool = False,
    ):
        """Create a persistent browser context with a local user data dir."""
        return await _create_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
        )

    # ------------------------------------------------------------------
    # Abstract operations (every platform must implement)
    # ------------------------------------------------------------------

    @abstractmethod
    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform platform login, pushing progress updates to *status_queue*."""
        ...

    @abstractmethod
    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid."""
        ...

    @abstractmethod
    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the platform creator / upload centre page."""
        ...

    @abstractmethod
    async def sync_profile(self, cookie_file: str):
        """Sync profile information from the platform.

        新约定:返回 dict,包含 name/avatar/stats 三项:
          {
            "name":   str,   # 昵称,失败为空字符串
            "avatar": str,   # 头像 URL,失败为空字符串
            "stats":  [      # 运营数据列表,失败或未实现为 []
              {"ICON": "user", "COUNT": 12345, "NAME": "粉丝", "SORT": 1},
              {"ICON": "like", "COUNT": 678,   "NAME": "获赞", "SORT": 2},
              ...
            ],
          }

        兼容旧实现:若仍返回 2 元组 ``(name, avatar)``,路由层会把 stats 视为 []。
        调用方:写入 user_info.stats(JSON 字符串)。
        """
        ...

    @abstractmethod
    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to the platform.  Returns True on success."""
        ...

    # ------------------------------------------------------------------
    # Sync bridge (legacy callers in request threads)
    # ------------------------------------------------------------------

    def run_publish_sync(self, **kwargs) -> bool:
        """同步桥接：在请求线程内调用 async publish_video。

        R5 后 publish_video 全量 async 化；旧同步调用方（postVideoBatch 已随 R6 移除）
        通过本包装逐次驱动事件循环，避免拿到未执行的 coroutine。
        """
        return asyncio.run(self.publish_video(**kwargs))

    # ------------------------------------------------------------------
    # Cookie import (default skeleton + per-platform hook)
    # ------------------------------------------------------------------

    # 注意：_parse_cookie_to_storage_state 不是 @abstractmethod，否则会强制
    # 所有平台实现它。仅当 supports_cookie_import=True 时由子类重写。

    def _parse_cookie_to_storage_state(
        self, cookie_str: str
    ) -> tuple[list[dict], list[dict]]:
        """把 'k=v; k=v' 解析为 Playwright storage_state 的 (cookies, origins)。

        A6/R9-2: 通用实现上移基类 —— 全部 cookie 归属 ``platform_cookie_domain``，
        expires 给 7 天保守占位（sync_profile 跑完后回写真实 expires）。
        带特殊规则的平台（如 csdn 的按名域名映射 + SESSION 双域）自行重写；
        其余 supports_cookie_import=True 的平台无需再写本地副本。

        Returns:
            ``(cookies, origins)`` —— ``import_cookie`` 会原样写入 storage_state。
        """
        cookies: list[dict] = []
        expires = time.time() + self._IMPORT_COOKIE_EXPIRES_SECONDS
        for chunk in cookie_str.split(";"):
            pair = chunk.strip()
            if not pair or "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": self.platform_cookie_domain,
                "path": "/",
                "expires": expires,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            })
        _base_logger.info(
            "[%s] cookie 解析: %d 条, domain=%s",
            self.platform_key, len(cookies), self.platform_cookie_domain,
        )
        return cookies, []

    # Cookie import expires 保守占位（7 天）: 手工导入的 cookie 没有真实 expires，
    # Chromium 对 expires=-1（session）部分平台不收；sync_profile 跑完后会
    # 把 storage_state 回写刷新成真实 expires。
    _IMPORT_COOKIE_EXPIRES_SECONDS = 7 * 24 * 3600

    async def import_cookie(
        self,
        cookie_str: str,
        status_queue: Queue,
        account_id: int | None = None,
    ) -> dict:
        """Default cookie-import flow (4-step progress).

        Subclasses do NOT override this; they only set
        ``supports_cookie_import = True`` and implement
        :meth:`_parse_cookie_to_storage_state`.

        status_queue contract (JSON-per-line):
            ``{"step": 1|2|3, "status": "running", "msg": "..."}``
            ``{"step": 4, "status": "done", "msg": "...", "account_id": int,
              "userName": str, "avatar": str}``
            ``{"status": "error", "step": int, "msg": str}``

        Returns:
            ``{"account_id": int, "userName": str, "avatar": str}`` on success.
        """
        # ---- Step 1: parse cookie string ----
        try:
            status_queue.put(json.dumps({
                "step": 1, "status": "running", "msg": "解析 cookie 字符串",
            }))
            cookies, origins = self._parse_cookie_to_storage_state(cookie_str)
            if not cookies:
                raise ValueError("未解析到任何 cookie")  # noqa: TRY301 -- try 内主动 raise 为语义错误/快速失败,刻意不被吞,抽象改造ROI低
            _base_logger.info(
                "[import_cookie] %s 解析到 %d 个 cookie",
                self.platform_name, len(cookies),
            )
        except Exception as e:
            status_queue.put(json.dumps({
                "status": "error", "step": 1, "msg": f"解析失败: {e}",
            }))
            raise

        # ---- Step 2: 写入临时 cookie 文件（不写 user_info，先验证有效性）----
        cookie_filename: str = ""
        cookie_path: Path | None = None
        try:
            status_queue.put(json.dumps({
                "step": 2, "status": "running", "msg": "生成 cookie 文件",
            }))
            cookies_dir = Path(BASE_DIR / "cookiesFile")
            cookies_dir.mkdir(parents=True, exist_ok=True)
            cookie_filename = f"{uuid.uuid1()}.json"
            storage = {"cookies": cookies, "origins": origins}
            cookie_path = cookies_dir / cookie_filename
            cookie_path.write_text(
                json.dumps(storage, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            status_queue.put(json.dumps({
                "status": "error", "step": 2, "msg": f"生成失败: {e}",
            }))
            raise

        # ---- Step 3: sync_profile（与账号列表「同步」按钮完全一致的调用）----
        # 复用 platform.sync_profile —— 就是 /syncProfile 路由里调的同一个方法，
        # 同一套 scrape 逻辑、同样的 headless 配置，不做任何特殊处理。
        #
        # sync_profile 返回值存在两种形态（与 /syncProfile 路由保持同一套兼容逻辑）：
        #   - 新约定: dict{"name", "avatar", "stats"}    （主流平台，含运营数据）
        #   - 旧约定: tuple(name, avatar)                 （少数旧实现，stats 视为 []）
        # 不能直接 `name, avatar = await sync_profile(...)`: dict 会迭代出 3 个 key
        # 触发 "too many values to unpack (expected 2)"。
        name, avatar, stats = "", "", []
        try:
            status_queue.put(json.dumps({
                "step": 3, "status": "running", "msg": "同步用户资料",
            }))
            result = await self.sync_profile(cookie_filename)
            if isinstance(result, dict):
                name = result.get('name', '') or ''
                avatar = result.get('avatar', '') or ''
                stats = result.get('stats', []) or []
                if not isinstance(stats, list):
                    stats = []
            elif isinstance(result, tuple):
                name = result[0] if len(result) > 0 else ''
                avatar = result[1] if len(result) > 1 else ''
                stats = []
            else:
                name, avatar, stats = '', '', []
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            _base_logger.info(
                "[import_cookie] %s sync_profile 失败: %s",
                self.platform_name, e,
            )
            status_queue.put(json.dumps({
                "step": 3, "status": "running",
                "msg": f"同步失败: {e}",
            }))

        # ---- Step 4: 创建账号记录 ----
        # 策略:
        #   a) account_id 已存在 (re-import) → 直接 UPDATE, 任何结果都接受
        #   b) account_id 不存在:
        #      - sync 抓到 name/avatar → INSERT 真账号
        #      - sync 拿到空 (cookie 失效) → 删临时 cookie 文件, 报错让用户重试
        if not name and not avatar and not account_id:
            # cookie 验证失败,清理临时文件
            if cookie_path and cookie_path.exists():
                try:  # noqa: SIM105
                    cookie_path.unlink()
                except Exception:  # noqa: S110, BLE001 -- 文件/资源清理兜底,失败可忽略
                    pass
            status_queue.put(json.dumps({
                "status": "error", "step": 4,
                "msg": "cookie 已失效,无法同步到用户资料。请确认 cookie 是否过期后重试。",
            }))
            raise RuntimeError("cookie 同步失败: 抓取到空的昵称/头像")

        status_queue.put(json.dumps({
            "step": 4, "status": "running", "msg": "创建账号记录",
        }))
        account_id_saved: int = 0
        stats_json = json.dumps(stats, ensure_ascii=False)
        try:
            db_path = Path(BASE_DIR) / "db" / "database.db"
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.cursor()
                if account_id:
                    cursor.execute(
                        "UPDATE user_info SET filePath=?, status=1, userName=?, avatar=?, stats=? "
                        "WHERE id=?",
                        (cookie_filename, name, avatar, stats_json, account_id),
                    )
                    account_id_saved = int(account_id)
                    _base_logger.info(
                        "[import_cookie] %s re-import 更新 id=%s",
                        self.platform_name, account_id,
                    )
                else:
                    cursor.execute(
                        "INSERT INTO user_info (type, filePath, userName, status, avatar, stats) "
                        "VALUES (?, ?, ?, 1, ?, ?)",
                        (self.platform_id, cookie_filename, name, avatar, stats_json),
                    )
                    account_id_saved = cursor.lastrowid
                    _base_logger.info(
                        "[import_cookie] %s 新建账号 id=%s, name=%r, stats=%d项",
                        self.platform_name, account_id_saved, name, len(stats),
                    )
                conn.commit()
        except Exception as e:
            status_queue.put(json.dumps({
                "status": "error", "step": 4, "msg": f"写入数据库失败: {e}",
            }))
            raise

        status_queue.put(json.dumps({
            "step": 4, "status": "done", "msg": "导入完成",
            "account_id": account_id_saved,
            "userName": name, "avatar": avatar, "stats": stats,
        }))
        return {
            "account_id": account_id_saved,
            "userName": name, "avatar": avatar,
            "stats": stats,
            "cookie_filename": cookie_filename,
        }

    # ------------------------------------------------------------------
    # Optional stubs (override if the platform supports these)
    # ------------------------------------------------------------------

    async def publish_note(self, **kwargs) -> bool:
        """Publish an image note (default: not supported)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support note publishing"
        )

    async def publish_image(self, **kwargs) -> bool:
        """Publish an image post (default: not supported)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support image publishing"
        )

    async def get_statistics(self, **kwargs) -> dict:
        """Fetch account statistics (default: not supported)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support statistics"
        )
