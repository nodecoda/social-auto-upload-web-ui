"""平台专属 profile scraper（A7/R9-3 从 impl/_utils.py 迁出）。

原 _utils.py 承载 13 个平台专属 scrape_* 后达 1472 行；按「平台专属逻辑
归平台目录」原则迁移，_utils 只保留通用工具。函数体与原 _utils 一致，
依赖仅标准库 asyncio + 本地 logger。
"""
import asyncio

from util._logger import get_channel_logger

logger = get_channel_logger("platform-profile")

async def scrape_alipay_profile(page):
    """支付宝内容创作平台专用 scraper。

    抓取依据:登录后的创作中心首页
    (``c.alipay.com/page/life-account/index``)会渲染账号信息容器。
    login() 和 sync_profile() 都调用此方法,保证逻辑一致。

    **定位策略:不依赖 class 名**(支付宝用 CSS modules,hash 类名如
    ``name___mAiik`` 会随发版漂移)。改用业务文案锚点 + DOM 结构:

    - 昵称:页面里必然有 ``生活号ID：xxx`` 文案(业务字段,稳定)。
      从该叶子节点向上找到包含它的「信息区」div(同时含昵称/粉丝/获赞/
      生活号ID 文本),该 div 的第一个子元素(昵称区)的第一个子文本
      节点 = 昵称。
    - 头像:账号头像走 ``mdn.alipayobjects.com/open_content/afts/...``
      CDN 路径(用户上传内容),区别于平台 UI 图标(``huamei_*`` / ``rms``)。
      在信息区附近(兄弟节点)找该路径的 img。

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)

        # 显式等待「生活号ID：」文案出现(它出现 = 账号信息已渲染完成)
        # 这是比等 container class 更可靠的就绪信号 —— 业务文案稳定
        info_ready = False
        for _ in range(20):  # 最多等 10s
            try:
                found = await page.evaluate(
                    """() => {
                        const els = document.querySelectorAll('*');
                        for (const el of els) {
                            if (el.children.length === 0
                                && (el.textContent || '').includes('生活号ID')) {
                                return true;
                            }
                        }
                        return false;
                    }"""
                )
                if found:
                    info_ready = True
                    break
            except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                pass
            await asyncio.sleep(0.5)

        if not info_ready:
            logger.warning(
                f"[alipay] 账号信息未渲染 (url={page.url}, "
                "可能 cookie 失效跳转了登录页)"
            )
        await asyncio.sleep(0.5)

        result = await page.evaluate("""() => {
            let name = '', avatar = '';

            // ---- 昵称: 用「生活号ID：」文案锚点 + DOM 结构回溯 ----
            // 1. 找到「生活号ID」叶子节点
            const allEls = document.querySelectorAll('*');
            let idLeaf = null;
            for (const el of allEls) {
                if (el.children.length === 0
                    && (el.textContent || '').includes('生活号ID')) {
                    idLeaf = el; break;
                }
            }
            // 2. 向上找到「信息区」(nameBox + numBox 的共同父级)
            //    结构:infoArea > [nameBox, numBox], numBox 含「生活号ID」
            //
            //    区分 infoArea vs numBox(两者都含生活号ID):
            //    - numBox 的第一个子元素是「粉丝N」(含"粉丝")
            //    - infoArea 的第一个子元素是 nameBox(昵称,不含"粉丝"也不含"生活号ID")
            //    所以 infoArea 的判据:firstChild 不含「生活号ID」也不含「粉丝」
            let infoArea = null;
            if (idLeaf) {
                let cur = idLeaf;
                for (let i = 0; i < 6 && cur; i++) {
                    const txt = (cur.textContent || '');
                    const fcTxt = cur.firstElementChild
                        ? (cur.firstElementChild.textContent || '') : '';
                    if (txt.includes('生活号ID')
                        && cur.children.length >= 2
                        && !fcTxt.includes('生活号ID')
                        && !fcTxt.includes('粉丝')) {
                        infoArea = cur; break;
                    }
                    cur = cur.parentElement;
                }
            }
            // 3. infoArea 的第一个子元素 = nameBox,
            //    nameBox 第一个子元素(纯文本,无子节点)= 昵称
            if (infoArea && infoArea.firstElementChild) {
                const nameBox = infoArea.firstElementChild;
                // 在 nameBox 子树里找第一个「无子节点 + 非空文本」的元素
                const walker = document.createTreeWalker(
                    nameBox, NodeFilter.SHOW_ELEMENT
                );
                let node = nameBox;
                while (node) {
                    if (node.children.length === 0) {
                        const t = (node.textContent || '').trim();
                        // 排除描述语(带引号的,如 " 又是充满创作力的一天 ")
                        // 昵称通常 2-20 字,不含引号/书名号
                        if (t && !t.startsWith('"') && !t.startsWith('"')
                            && !t.startsWith('「') && t.length <= 30) {
                            name = t; break;
                        }
                    }
                    node = walker.nextNode();
                }
                // 兜底:若上面没取到,直接取 nameBox 的第一个 leaf 文本
                if (!name) {
                    const firstLeaf = nameBox.querySelector('*:not(:has(*))')
                        || nameBox.firstElementChild;
                    if (firstLeaf) name = (firstLeaf.textContent || '').trim();
                }

                // ---- 头像: 在 infoArea 的父级范围内找 open_content img ----
                // 头像与信息区是兄弟(都在 accountContainer 下),
                // 头像区在前,信息区在后
                const scope = infoArea.parentElement || infoArea;
                const imgs = scope.querySelectorAll('img');
                for (const img of imgs) {
                    const src = img.src || '';
                    // 用户头像走 open_content CDN 路径
                    // (区别于平台 UI 图标 huamei_*/rms)
                    if (src.includes('/open_content/')
                        && src.includes('alipayobjects.com')) {
                        avatar = src; break;
                    }
                }
                // 兜底:任意 alipay CDN 图片(排除明显的小图标)
                if (!avatar) {
                    for (const img of imgs) {
                        const src = img.src || '';
                        if (src.includes('alipayobjects.com')
                            && (img.naturalWidth >= 80
                                || img.naturalHeight >= 80)) {
                            avatar = src; break;
                        }
                    }
                }
            }

            return { name, avatar };
        }""")
        name = (result.get("name") or "").strip()
        avatar = (result.get("avatar") or "").strip()
        logger.info(
            f"[alipay] profile scraped - name={name!r} "
            f"avatar={avatar[:80] if avatar else 'None'}"
        )
    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
        logger.info(f"[alipay] profile scrape error: {e}")

    return name, avatar
