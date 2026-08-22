"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")


def _parse_vivo_count(text: str) -> int:
    """解析 VIVO 数字显示格式: '1.2万' / '1.2w' / '12345' → int。"""
    if not text:
        return 0
    text = text.strip().lower()
    multi = 1
    if text.endswith(('万', 'w')):
        multi = 10000
        text = text[:-1]
    elif text.endswith('亿'):
        multi = 100000000
        text = text[:-1]
    try:
        return int(float(text) * multi)
    except ValueError:
        return 0

async def scrape_vivo_profile(page):
    """VIVO 内容创作平台专用 scraper。

    创作者中心 ``https://www.kaixinkan.com.cn/#/home`` 登录后会渲染一张
    ``.user-info-area`` 资料卡。DOM 结构(产品语义 class,非 data-v 随机串):

      <div class="user-info-area">
        <div class="user-info-area-left">
          <div class="user-icon"><img src="头像URL"></div>
          <div class="info">
            <div class="user-name"> 昵称 </div>
          </div>
        </div>
        <div class="user-detail">
          <div class="item-detail">
            <div class="item-detail-title">粉丝</div>
            <div class="item-detail-number">0</div>
          </div>
          <div class="item-detail">
            <div class="item-detail-title">获赞</div>
            <div class="item-detail-number">0</div>
          </div>
        </div>
      </div>

    VIVO 没有「关注数」概念,follows 固定为 0。

    Returns:
        tuple[str, str, int, int, int]:
            ``(user_name, avatar_url, fans, likes, follows)``
    """
    name = ""
    avatar = ""
    fans = 0
    likes = 0
    follows = 0  # VIVO 无关注数概念,固定 0
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
        await asyncio.sleep(3)

        # 昵称 / 头像
        name_el = page.locator(".user-info-area .user-name").first
        if await name_el.count():
            name = (await name_el.text_content() or "").strip()
        avatar_el = page.locator(".user-info-area .user-icon img").first
        if await avatar_el.count():
            avatar = (await avatar_el.get_attribute("src") or "").strip()

        # 粉丝 / 获赞:遍历 .item-detail,按 title 文本匹配对应 number
        # (避免依赖 DOM 顺序,平台后续增删字段也能正确取值)
        detail_items = page.locator(".user-info-area .user-detail .item-detail")
        count = await detail_items.count()
        for i in range(count):
            item = detail_items.nth(i)
            title_el = item.locator(".item-detail-title").first
            number_el = item.locator(".item-detail-number").first
            if not await title_el.count() or not await number_el.count():
                continue
            title = (await title_el.text_content() or "").strip()
            number_text = (await number_el.text_content() or "").strip()
            try:
                # 处理 "1.2万" / "1.2w" / 纯数字 三种格式
                number = _parse_vivo_count(number_text)
            except Exception:  # noqa: BLE001 -- 捕获后恢复默认状态,防御性编码
                number = 0
            if title == "粉丝":
                fans = number
            elif title == "获赞":
                likes = number

        logger.info(
            f"[vivo] profile scraped - name={name!r} "
            f"avatar={avatar[:80] if avatar else 'None'} "
            f"fans={fans} likes={likes}"
        )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[vivo] profile scrape error: {e}")

    return name, avatar, fans, likes, follows
