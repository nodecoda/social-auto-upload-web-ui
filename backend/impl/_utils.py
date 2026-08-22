"""
Shared utilities for all platform implementations.

Provides profile scraping helpers, schedule-time parsing, and a unified
post-login flow (scrape profile -> save cookie -> write DB -> send SSE status).

All functions use standard Playwright Page/Context APIs only.
"""
import asyncio
import json
import platform as _platform
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from conf import BASE_DIR
from util._logger import get_channel_logger

# A7/R9-3: 平台专属 scraper 已迁至各平台目录, 此处 re-export 保持向后兼容
# (tests/impl/test_weibo_scraper.py 等从 impl._utils 导入)
from .alipay._profile import scrape_alipay_profile
from .baijiahao._profile import scrape_baijiahao_profile
from .bilibili._profile import scrape_bilibili_profile
from .channels._profile import scrape_tencent_profile
from .csdn._profile import scrape_csdn_profile
from .jingmai._profile import scrape_jingmai_profile
from .taobao_guanghe._profile import scrape_taobao_guanghe_profile
from .toutiao._profile import scrape_toutiao_profile
from .vivo._profile import _parse_vivo_count, scrape_vivo_profile
from .weibo._profile import scrape_weibo_profile
from .weixin_gzh._profile import scrape_weixin_gzh_profile
from .youtube._profile import scrape_youtube_profile
from .zhihu._profile import scrape_zhihu_profile

__all__ = [
    "_parse_vivo_count",
    "scrape_alipay_profile",
    "scrape_baijiahao_profile",
    "scrape_bilibili_profile",
    "scrape_csdn_profile",
    "scrape_jingmai_profile",
    "scrape_taobao_guanghe_profile",
    "scrape_tencent_profile",
    "scrape_toutiao_profile",
    "scrape_vivo_profile",
    "scrape_weibo_profile",
    "scrape_weixin_gzh_profile",
    "scrape_youtube_profile",
    "scrape_zhihu_profile",
]
logger = get_channel_logger('utils')



# ---------------------------------------------------------------------------
# 平台 profile 抓取 JS 注入脚本(原 _utils 模块级常量)
# ---------------------------------------------------------------------------
_SCRAPE_JS = '''() => {
    let name = '';
    let avatar = '';
    const candidates = [];

    // ====== 头像查找 ======
    function isAvatarUrl(url) {
        if (!url || !url.startsWith('http')) return false;
        const lower = url.toLowerCase();
        return !lower.endsWith('.svg') && !lower.includes('.svg') &&
            !lower.includes('icon') && !lower.includes('logo') &&
            !lower.includes('qrcode') && !lower.includes('placeholder') &&
            !lower.includes('default') && !lower.includes('blank') &&
            !lower.includes('sprite') && !lower.includes('bg');
    }

    const avatarCdnPatterns = [
        'aweme-avatar', 'douyinpic.com/avatar',
        'xhscdn.com/avatar', 'qlogo.cn', 'finderhead',
        'kuaishoucdn.com/avatar', 'head_url'
    ];
    const imgs = [...document.querySelectorAll('img')];

    // ====== 工具函数 ======
    const excludeTexts = ['登录','注册','密码','手机','首页','上传','数据','管理',
        '发布','创作','视频','直播','消息','设置','帮助','退出','更多','搜索',
        '扫码','关注','粉丝','获赞','作品','动态','喜欢','收藏',
        '共创','中心','工具','服务','收益','任务','课程','通知','评论',
        '互动','权限','认证','申请','开通','绑定','电商','带货',
        '网址','链接','复制','分享','下载','打开','全部','菜单',
        '内容','素材','流量','分析','商品','订单','结算','功能',
        '主页','首页','个人','专栏','活动','热门','推荐',
        '播放量','点赞数','评论数','转发数','浏览量','阅读量','新增','昨日'];

    function isValidName(text) {
        if (!text || text.length < 2 || text.length > 30) return false;
        if (/^\\d+(\\.\\d+)?[万亿]$/.test(text)) return false;
        if (/^\\d+$/.test(text)) return false;
        for (const ex of excludeTexts) {
            if (text.includes(ex)) return false;
        }
        return true;
    }

    // ====== 策略0 (最高优先级): 平台精确匹配，找到直接返回 ======
    // 抖音: container-xxx > avatar-xxx > img + name-xxx
    const dyAllContainers = document.querySelectorAll('div[class^="container-"]');
    for (const dyContainer of dyAllContainers) {
        const dyAvImg = dyContainer.querySelector(':scope > div[class^="avatar-"] > img');
        const dyNameEl = dyContainer.querySelector('div[class^="name-"]');
        if (dyAvImg && dyNameEl && isValidName(dyNameEl.textContent.trim())) {
            return {
                name: dyNameEl.textContent.trim(),
                avatar: dyAvImg.src || '',
                debug: [{text: dyNameEl.textContent.trim(), method: 'douyin-profile-container'}]
            };
        }
    }
    // 视频号: img[alt*="头像"] + h2.finder-nickname
    const wxAvatar = document.querySelector('img[alt*="头像"]');
    const wxName = document.querySelector('h2.finder-nickname') || document.querySelector('[class*="nickname"]');
    if (wxAvatar && wxName && isValidName(wxName.textContent.trim())) {
        return {
            name: wxName.textContent.trim(),
            avatar: wxAvatar.src || '',
            debug: [{text: wxName.textContent.trim(), method: 'wechat-profile'}]
        };
    }

    // ====== 以下为兜底策略 ======

    // 头像: 优先匹配平台头像 CDN（精确匹配）
    for (const img of imgs) {
        const src = img.src || '';
        if (isAvatarUrl(src) && !src.includes('cover') && !src.includes('video')) {
            for (const p of avatarCdnPatterns) {
                if (src.includes(p)) { avatar = src; break; }
            }
            if (avatar) break;
        }
    }
    // 兜底：尺寸匹配
    if (!avatar) {
        for (const img of imgs) {
            const rect = img.getBoundingClientRect();
            const w = rect.width, h = rect.height;
            if (w >= 24 && w <= 80 && h >= 24 && h <= 80 &&
                Math.abs(w - h) < Math.max(w, h) * 0.3 && isAvatarUrl(img.src)) {
                avatar = img.src;
                break;
            }
        }
    }

    // 昵称查找
    // 策略A: 找到头像后，找头像旁边的 name 元素
    if (avatar) {
        const avatarImg = imgs.find(i => i.src === avatar);
        if (avatarImg) {
            let parent = avatarImg.parentElement;
            if (parent) {
                const sibling = parent.nextElementSibling;
                if (sibling && sibling.className && sibling.className.startsWith('name-')) {
                    const text = sibling.textContent.trim();
                    if (isValidName(text)) {
                        candidates.push({text, method: 'avatar-sibling', level: 0});
                    }
                }
            }
            let container = avatarImg.parentElement;
            for (let i = 0; i < 5 && container; i++) {
                const leaves = container.querySelectorAll('span, div, p, a');
                for (const leaf of leaves) {
                    if (leaf.childElementCount > 0) continue;
                    const text = leaf.textContent.trim();
                    if (isValidName(text)) {
                        candidates.push({text, method: 'near-avatar', level: i});
                    }
                }
                container = container.parentElement;
            }
        }
    }

    // 策略B: class 选择器
    const selectors = [
        'div[class^="avatar-"] + div[class^="name-"]',
        'h2.finder-nickname', 'img.avatar[alt]',
        '[class*="user-name"]', '[class*="userName"]', '[class*="username"]',
        '[class*="nick-name"]', '[class*="nickname"]', '[class*="nickName"]',
        '[class*="NickName"]', '[class*="nick_name"]',
        '[class*="UserInfo"]', '[class*="userInfo"]', '[class*="user-info"]',
        '[class*="profile-name"]', '[class*="profileName"]',
        '[class*="name-text"]', '[class*="nameText"]',
    ];
    for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            const text = el.textContent.trim();
            if (isValidName(text)) {
                candidates.push({text, method: 'class:' + sel});
            }
        }
    }

    // 策略C: img alt 属性
    for (const img of imgs) {
        if (img.alt && isValidName(img.alt)) {
            candidates.push({text: img.alt, method: 'img-alt'});
        }
    }

    const best = candidates[0];
    name = best ? best.text : '';

    return { name, avatar, debug: candidates.slice(0, 10) };
}'''



# ---------------------------------------------------------------------------
# Cross-platform input helpers
# ---------------------------------------------------------------------------

_IS_MAC = _platform.system() == "Darwin"

# 全选快捷键:Mac 用 Meta(Cmd)+A,其他系统用 Control+A
_SELECT_ALL_KEY = "Meta+a" if _IS_MAC else "Control+a"

def get_account_name_by_cookie_file(cookie_filename: str) -> str:
    """根据 cookie 文件名查询账号昵称 (user_info.userName)。

    cookie 文件名即 user_info.filePath 的值（如 ``xxx-uuid.json``）。
    查询失败或未找到时返回空字符串，调用方应做兜底处理。

    仅用于日志打印，不参与任何业务逻辑判断。
    """
    if not cookie_filename:
        return ""
    try:
        db_path = Path(BASE_DIR / "db" / "database.db")
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT userName FROM user_info WHERE filePath = ?",
                (cookie_filename,),
            ).fetchone()
        return row[0] if row else ""
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
        logger.warning("查询账号昵称失败 (%s): %s", cookie_filename, e)
        return ""
async def scrape_user_profile(page):
    """Generic scraper using _SCRAPE_JS injection.

    Works for Douyin, Kuaishou, Xiaohongshu, and most platforms.

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""

    try:
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        await asyncio.sleep(3)
    except Exception:  # noqa: S110, BLE001 -- DOM/页面探测兜底,元素可能不存在
        pass

    try:
        result = await page.evaluate(_SCRAPE_JS)
        name = result.get('name', '')
        avatar = result.get('avatar', '')
        debug = result.get('debug', [])
        logger.info(f"[scrape] candidates: {debug}")
        if name:
            logger.info(f"[scrape] found profile - name: {name}, avatar: {avatar[:50] if avatar else 'N/A'}")
        else:
            logger.info("[scrape] could not find user name, will use default")
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[scrape] failed to scrape user profile: {e}")

    return name, avatar
def parse_schedule_time(schedule_time_str, total_files, enableTimer,
                       videos_per_day, daily_times, start_days):
    """Parse a user-specified schedule time string.

    If *enableTimer* is True and *schedule_time_str* can be parsed, returns
    that datetime repeated for every file.  Otherwise falls back to
    auto-generated times via ``generate_schedule_time_next_day``.

    Args:
        schedule_time_str: ISO-ish datetime string from the frontend.
        total_files: Number of files to schedule.
        enableTimer: Whether timed publishing is enabled.
        videos_per_day: Videos per day for auto-generation.
        daily_times: List of daily publish times for auto-generation.
        start_days: Offset in days for auto-generation.

    Returns:
        list[int | datetime]: One entry per file.
    """
    if enableTimer and schedule_time_str:
        try:
            raw = str(schedule_time_str)
            # Handle UTC ISO format (frontend may send 2026-05-16T13:00:00.000Z)
            is_utc = raw.endswith("Z") or "+00:00" in raw
            raw_clean = raw.replace("+08:00", "").replace("+00:00", "")

            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
            ):
                try:
                    # UTC 输入标注 UTC 再转东八;本地输入(东八)直接标注
                    dt = datetime.strptime(raw_clean, fmt).replace(
                        tzinfo=UTC if is_utc else ZoneInfo("Asia/Shanghai")
                    )
                    if is_utc:
                        dt = dt.astimezone(ZoneInfo("Asia/Shanghai"))
                    logger.info(f"[schedule] using user-specified time: {dt}")
                    return [dt] * total_files
                except ValueError:
                    continue
            logger.info(f"[schedule] cannot parse time '{schedule_time_str}', falling back to auto-generation")
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[schedule] error parsing time: {e}, falling back to auto-generation")

    # No user-specified time: auto-generate
    if enableTimer:
        # Lazy import to avoid circular dependency
        from utils.files_times import generate_schedule_time_next_day
        return generate_schedule_time_next_day(total_files, videos_per_day, daily_times, start_days)
    else:
        return [0 for _ in range(total_files)]
async def save_login_result(
    context,
    page,
    platform_id: int,
    platform_name: str,
    status_queue,
    scrape_fn=None,
    account_id=None,
    stats_fn=None,
):
    """Shared post-login flow: scrape profile, save cookie, write DB, send SSE.

    This consolidates the repeated pattern found in every platform's login
    handler (Douyin, Bilibili, Xiaohongshu, Kuaishou, Channels, Baijiahao,
    YouTube, TikTok).

    新增 stats_fn 参数:登录成功写入 DB 后,在同一个 session 内调用
    stats_fn(page, account_id) 抓运营数据,把结果写入 user_info.stats JSON 列。
    stats_fn 自己负责 page.goto 等所有动作;返回 list[dict] 或 []。
    失败不阻塞登录成功流程。与 platform.sync_profile 内部用同一份抓取逻辑,
    保证"登录后同步"和"同步按钮"看到的运营数据完全一致。

    Args:
        context: Playwright BrowserContext (used for cookie storage).
        page: Playwright Page (used for profile scraping).
        platform_id: Numeric platform identifier (matches ``user_info.type``).
        platform_name: Human-readable platform name for default usernames.
        status_queue: Queue for sending SSE status messages back to the
            frontend.
        scrape_fn: Optional async ``async (page) -> (name, avatar)`` callable.
            Defaults to :func:`scrape_user_profile` (the generic JS scraper).
        account_id: Optional existing account ID for re-login. When provided,
            updates the existing record instead of creating a new one.
    """
    if scrape_fn is None:
        scrape_fn = scrape_user_profile

    # 1. Scrape user profile
    # scrape_fn 约定:
    #   2 元组 (name, avatar) — 旧平台
    #   5 元组 (name, avatar, fans, likes, follows) — 新平台(如 VIVO)同步运营数据
    profile = await scrape_fn(page)
    user_name, avatar_url = profile[0], profile[1]
    # 新平台同步账号运营数据;旧平台 scrape_fn 不返回,fans/likes/follows 默认 0
    if not user_name:
        user_name = f"{platform_name}用户{int(asyncio.get_running_loop().time())}"

    cookies_dir = Path(BASE_DIR / "cookiesFile")
    cookies_dir.mkdir(exist_ok=True)
    db_path = Path(BASE_DIR / "db" / "database.db")

    if account_id:
        # Re-login: update existing record's cookie file
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                'SELECT filePath FROM user_info WHERE id = ?', (account_id,)
            ).fetchone()
            cookie_filename = row[0] if row else None

        if not cookie_filename:
            logger.info(f"[login] account {account_id} not found, creating new")
            account_id = None

    if not account_id:
        # New login: generate new cookie filename
        uuid_v1 = uuid.uuid1()
        logger.info(f"UUID v1: {uuid_v1}")
        cookie_filename = f"{uuid_v1}.json"

    # 2. Save cookie file
    # 兜底: 上方 !cookie_filename → account_id=None → 必走重新生成分支
    assert cookie_filename is not None
    await context.storage_state(path=cookies_dir / cookie_filename)

    # 3. Write to database
    # 注意:不再写入 fans/likes/follows 旧字段(已废弃),仅写 userName/avatar/stats。
    # 旧的 fans/likes/follows 保留在表中以备历史数据,但新数据不再更新。
    with sqlite3.connect(db_path) as conn:
        if account_id:
            conn.execute(
                '''
                UPDATE user_info
                SET userName = ?, status = 1, avatar = ?
                WHERE id = ?
                ''',
                (user_name, avatar_url, account_id),
            )
            conn.commit()
            logger.info(f"[login] account {account_id} updated (re-login)")
        else:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO user_info (type, filePath, userName, status, avatar)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (platform_id, cookie_filename, user_name, 1, avatar_url),
            )
            conn.commit()
            # 回填 account_id(新登录场景下原 account_id 为 None),供后续 stats 抓取使用
            account_id = cursor.lastrowid
            logger.info(f"[login] {platform_name} user record saved (id={account_id})")

    # 4. 可选:补抓运营数据(stats)。
    # 注意顺序:stats 必须在「推 SSE 200」之前写库,否则前端收到 200 立即刷新
    # 账号列表时 DB 里还没有 stats,导致登录瞬间运营数据为空。
    # stats_fn 自己负责 goto + 抓取,返回 [{ICON, COUNT, NAME, SORT}, ...];
    # 失败不阻塞登录成功。
    if stats_fn and account_id:
        try:
            stats = await stats_fn(page, account_id)
            if stats:
                import json as _json
                with sqlite3.connect(db_path) as conn:
                    conn.execute(
                        'UPDATE user_info SET stats = ? WHERE id = ?',
                        (_json.dumps(stats, ensure_ascii=False), account_id),
                    )
                    conn.commit()
                logger.info(f"[login] account {account_id} stats 已补抓({len(stats)} 项)")
            else:
                logger.info(f"[login] account {account_id} stats 抓取为空,跳过")
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[login] 补抓 stats 失败(不影响登录成功): {exc}")

    # 5. Send SSE status (放在 stats 之后,确保前端刷新时 DB 已有运营数据)
    status_queue.put(json.dumps({
        "status": "200",
        "name": user_name,
        "avatar": avatar_url,
    }))

    # 返回 account_id,供调用方(login)做后续处理(如公众号自己掌控 stats 时序)
    return account_id
async def clear_input(page, element=None):
    """清空输入框内容(跨平台兼容)。

    对 input/textarea 元素用 fill("") 清空(最稳定);
    对 contenteditable 元素用 Ctrl/Cmd+A + Delete 清空。

    Args:
        page: Playwright page 对象
        element: 可选,要清空的元素 locator。为 None 时对当前焦点元素操作。
    """
    if element is not None:
        # 尝试用 fill("") 清空(input/textarea 最稳定)
        try:
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            if tag in ("input", "textarea"):
                await element.fill("")
                return
        except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
            pass
        # contenteditable 或其他:点击聚焦 + 全选 + 删除
        await element.click()
        await asyncio.sleep(0.1)

    # 全选 + 删除(跨平台)
    await page.keyboard.press(_SELECT_ALL_KEY)
    await asyncio.sleep(0.05)
    await page.keyboard.press("Delete")
    await asyncio.sleep(0.05)
async def clear_and_type(page, text: str, element=None, delay: int = 0):
    """清空输入框后输入新内容(跨平台兼容)。

    先调用 clear_input 清空,再用 keyboard.type 输入。

    Args:
        page: Playwright page 对象
        text: 要输入的文本
        element: 可选,要操作的元素 locator
        delay: 每字符延迟(ms),0 表示瞬间输入
    """
    await clear_input(page, element)
    if text:
        if delay > 0:
            await page.keyboard.type(text, delay=delay)
        else:
            await page.keyboard.type(text)
