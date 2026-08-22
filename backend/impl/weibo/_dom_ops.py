"""微博平台 — 视频/图集 DOM 交互、表单构造 子模块（A8 拆分）。

从 platform.py 拆出的平台专属 DOM 操作: 原 WeiboPlatform 的 staticmethod,
现为模块级函数, 由 platform.py 以 `_x = staticmethod(_x)` 类属性绑定,
保持 `self._x(...)` / `WeiboPlatform._x(...)` 调用语义不变(零行为变更)。
"""
import asyncio
import os

from util._logger import get_channel_logger

from .._utils import clear_and_type

logger = get_channel_logger("weibo")

_VIDEO_TYPE_MAP = {
    "原创": "0",
    "转载": "1",
    "二创": "2",
}


async def _upload_images(page, files: list):
        """上传图集多张图 — 多重兜底(2026-06-17 v1)。

        selector 策略:input[type=file][accept^='image/'][multiple]
        (用户提供的 DOM 行 9-10:accept 以 image/* 开头,且带 multiple)
        注意:input 祖父是 display:none,但 Playwright set_input_files 不要求
        visible,只要求 attached + enabled。

        多重兜底:
        1. 直接 set_input_files(files) 命中 input
        2. 失败则 expect_file_chooser + 点击「图片」trigger
        3. 再失败则 patch click/dispatchEvent/showPicker + MutationObserver

        等待完成:轮询「发送」按钮的 disabled 属性为 None(上传+表单就绪
        → 启用);最多 5 分钟。
        """
        if not files:
            logger.warning("[上传图集] 无图片可上传")
            return

        logger.info("[上传图集] 准备上传 %d 张图片", len(files))

        # 0. 安装 MutationObserver 兜底(参考 video 版 _upload_video_file)
        await page.evaluate(r"""() => {
            if (window.__weiboImgObserverInstalled) return;
            window.__weiboImgObserverInstalled = true;
            window.__weiboImgInitialInputCount =
                document.querySelectorAll('input[type="file"]').length;
            const observer = new MutationObserver(() => {
                const inputs = document.querySelectorAll('input[type="file"]');
                if (inputs.length > window.__weiboImgInitialInputCount) {
                    for (let i = window.__weiboImgInitialInputCount;
                         i < inputs.length; i++) {
                        inputs[i].setAttribute('data-weibo-img-new', '1');
                    }
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        }""")

        # 1. Patch 三个入口(参考 video 版)
        patch_status = await page.evaluate(r"""() => {
            if (window.__weiboImgAllPatched) return 'already-patched';
            window.__weiboImgAllPatched = true;
            const markInput = function (input) {
                try {
                    input.setAttribute('data-weibo-img-upload', '1');
                    if (!input.isConnected) {
                        input.style.display = 'none';
                        document.body.appendChild(input);
                    }
                } catch (e) {}
            };
            const origClick = HTMLInputElement.prototype.click;
            HTMLInputElement.prototype.click = function () {
                if (this && this.type === 'file') {
                    markInput(this);
                } else {
                    return origClick.apply(this, arguments);
                }
            };
            const origDispatch = EventTarget.prototype.dispatchEvent;
            EventTarget.prototype.dispatchEvent = function (event) {
                if (this && this.type === 'file' && event &&
                    event.type === 'click' && event instanceof MouseEvent) {
                    markInput(this);
                    return true;
                }
                return origDispatch.apply(this, arguments);
            };
            if (HTMLInputElement.prototype.showPicker) {
                const origShow = HTMLInputElement.prototype.showPicker;
                HTMLInputElement.prototype.showPicker = function () {
                    if (this && this.type === 'file') {
                        markInput(this);
                    } else {
                        return origShow.apply(this, arguments);
                    }
                };
            }
            return 'patched';
        }""")
        logger.info("[发布] img patch status: %s", patch_status)

        # 2. 找「图片」trigger
        # selector:文本 "图片" 在 woo-pop-wrap 内,且 sibling 包含 image upload input
        img_trigger = page.get_by_text("图片", exact=True).first
        if await img_trigger.count() == 0:
            raise RuntimeError("[发布] 未找到「图片」工具图标")

        # 3. 优先直接 set_input_files(接受 hidden input)
        target_input_sel = (
            "input[type='file'][accept^='image/'][multiple]"
        )
        try:
            target_input = page.locator(target_input_sel).first
            await target_input.wait_for(state="attached", timeout=10000)
            await target_input.set_input_files(files)
            logger.info("[发布] 已通过 set_input_files 提交 %d 张图", len(files))
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info("[发布] 直接 set_input_files 失败: %s", e)

            # 兜底 1: expect_file_chooser + 点击 trigger
            try:
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    await img_trigger.click(force=True)
                fc = await fc_info.value
                await fc.set_files(files)
                logger.info("[发布] 已通过 expect_file_chooser 提交")
            except Exception as e2:  # 统一兜底并记录调试日志,防御性编码
                logger.info("[发布] expect_file_chooser 失败: %s", e2)
                # 兜底 2: 等带标记的 input 出现(patch 命中)
                marked_sel = (
                    "input[type='file'][data-weibo-img-upload='1'],"
                    "input[type='file'][data-weibo-img-new='1']"
                )
                deadline = asyncio.get_running_loop().time() + 30
                found = None
                while asyncio.get_running_loop().time() < deadline:
                    count = await page.locator(marked_sel).count()
                    if count > 0:
                        found = page.locator(marked_sel).first
                        break
                    await asyncio.sleep(0.5)
                if found is not None:
                    await found.set_input_files(files)
                    logger.info("[发布] 已通过 patched input 提交")
                else:
                    raise RuntimeError(
                        "[发布] 30s 内未找到可用的 file input"
                    ) from e2

        # 4. 等待上传完成 — 轮询「发送」按钮 enabled(最稳判定)
        send_btn = page.get_by_role("button", name="发送", exact=True).first
        deadline = asyncio.get_running_loop().time() + 300  # 5 分钟
        while asyncio.get_running_loop().time() < deadline:
            try:
                disabled = await send_btn.get_attribute("disabled")
                if disabled is None:
                    logger.info("[发布] 图片已上传,发送按钮已启用")
                    return
            except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                pass
            await asyncio.sleep(2)

        raise RuntimeError("[发布] 5 分钟内图片未上传完成(发送按钮未启用)")


async def _click_send(page):
        """点击「发送」按钮(图集版,视频版是「发布」)。

        与 video 版 _click_publish 同构,只是 button name 不同。
        初始 disabled,表单就绪后启用 — 轮询 disabled 属性(最长 60s)。
        """
        send_btn = page.get_by_role("button", name="发送", exact=True).first
        try:
            await send_btn.wait_for(state="visible", timeout=10000)
        except Exception as e:  # 捕获后重新抛出,统一异常出口
            raise RuntimeError(f"[发布] 未找到「发送」按钮: {e}") from e

        # 轮询 disabled(最长 60s)
        for _ in range(60):
            disabled = await send_btn.get_attribute("disabled")
            if disabled is None:
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("[发布] 「发送」按钮一直 disabled,表单未就绪")

        await send_btn.click()
        logger.info("[发布] 已点击「发送」按钮")


async def _wait_for_image_publish_success(page, timeout_s: int = 60):
        """等待图集发布完成。

        微博图集发送后**无明显 toast**(与 video 版的「视频已上传成功」
        不同)。判定成功靠 2 个条件 OR:
        1. textarea 内容清空
        2. 创作卡片回到初始态(「发送」按钮重新 disabled)

        60s 内任一命中即视为成功。
        """
        deadline = asyncio.get_running_loop().time() + timeout_s
        textarea = page.locator("textarea[placeholder*='有什么新鲜事']").first
        send_btn = page.get_by_role("button", name="发送", exact=True).first

        while asyncio.get_running_loop().time() < deadline:
            try:
                # 条件 1: textarea 清空
                textarea_empty = await textarea.input_value() == ""
                # 条件 2: 发送按钮重新 disabled
                disabled = await send_btn.get_attribute("disabled")
                send_disabled = disabled is not None
                if textarea_empty or send_disabled:
                    logger.info("[发布] 图集发布成功(textarea 空=%s, send 禁用=%s)",
                                textarea_empty, send_disabled)
                    return
            except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                pass
            await asyncio.sleep(2)

        raise RuntimeError(
            f"[发布] 等待图集发布完成超时({timeout_s}s)"
        )


async def _upload_video_file(page, file_path: str):
        """上传视频主文件 — 多重兜底(2026-06-16 v3)。

        CloakBrowser + 微博前端组合下,单一的 patch 路径不稳定:
        22:21 那次走 ``input.click()`` 命中;22:25、22:29 那次 patch 三个
        入口(click / dispatchEvent / showPicker)全不命中,但手动点击按钮
        能触发 file picker。说明 CloakBrowser 在某些会话里会屏蔽 button
        click 的副作用(不调任何 input API)。

        多重兜底:
        1. ``expect_file_chooser`` — Playwright 原生 API,优先用这个
        2. Patch click / dispatchEvent / showPicker — 三大入口
        3. MutationObserver 检测新 file input — 兜底(动态 input 加到 DOM)
        4. 多种点击方式 — force=True / mouse.move+click / JS .click()
        """
        file_size = os.path.getsize(file_path)
        logger.info(
            "[上传视频] 准备上传视频: %s (%.1f MB)",
            os.path.basename(file_path), file_size / 1024 / 1024,
        )

        # 0. 安装 MutationObserver 兜底: 任何新加到 DOM 的 file input 都自动标记
        await page.evaluate(r"""() => {
            if (window.__weiboObserverInstalled) return;
            window.__weiboObserverInstalled = true;
            window.__weiboInitialInputCount =
                document.querySelectorAll('input[type="file"]').length;
            const observer = new MutationObserver(() => {
                const inputs = document.querySelectorAll('input[type="file"]');
                if (inputs.length > window.__weiboInitialInputCount) {
                    for (let i = window.__weiboInitialInputCount;
                         i < inputs.length; i++) {
                        inputs[i].setAttribute('data-weibo-new', '1');
                    }
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        }""")

        # 1. Patch 三个入口
        patch_status = await page.evaluate(r"""() => {
            if (window.__weiboAllPatched) return 'already-patched';
            window.__weiboAllPatched = true;
            const markInput = function (input) {
                try {
                    input.setAttribute('data-weibo-upload', '1');
                    if (!input.isConnected) {
                        input.style.display = 'none';
                        document.body.appendChild(input);
                    }
                } catch (e) {}
            };
            // click
            const origClick = HTMLInputElement.prototype.click;
            HTMLInputElement.prototype.click = function () {
                if (this && this.type === 'file') {
                    markInput(this);
                } else {
                    return origClick.apply(this, arguments);
                }
            };
            // dispatchEvent(MouseEvent click)
            const origDispatch = EventTarget.prototype.dispatchEvent;
            EventTarget.prototype.dispatchEvent = function (event) {
                if (this && this.type === 'file' && event &&
                    event.type === 'click' && event instanceof MouseEvent) {
                    markInput(this);
                    return true;
                }
                return origDispatch.apply(this, arguments);
            };
            // showPicker
            if (HTMLInputElement.prototype.showPicker) {
                const origShow = HTMLInputElement.prototype.showPicker;
                HTMLInputElement.prototype.showPicker = function () {
                    if (this && this.type === 'file') {
                        markInput(this);
                    } else {
                        return origShow.apply(this, arguments);
                    }
                };
            }
            return 'patched';
        }""")
        logger.info("[上传视频] patch status: %s", patch_status)

        # 2. 找上传按钮
        upload_btn = page.locator("button[id^='video_button_upload']").first
        if await upload_btn.count() == 0:
            upload_btn = page.get_by_role(
                "button", name="上传视频", exact=True,
            ).first
        if await upload_btn.count() == 0:
            raise RuntimeError("[上传视频] 未找到「上传视频」按钮")

        await upload_btn.wait_for(state="visible", timeout=10000)

        # 3. 触发按钮 — 多重尝试,任一成功即可
        triggered = False

        # 方式 A: expect_file_chooser 优先(原生 Playwright API)
        try:
            async with page.expect_file_chooser(timeout=5000) as fc_info:
                await upload_btn.click(force=True)
            fc = await fc_info.value
            await fc.set_files(file_path)
            logger.info("[上传视频] 已通过 expect_file_chooser 提交视频")
            triggered = True
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info("[上传视频] expect_file_chooser 方式失败: %s", e)

        # 方式 B: 普通 click + 等带标记 input (patch 命中)
        if not triggered:
            try:
                await upload_btn.click(force=True)
                logger.info("[上传视频] 已点击「上传视频」按钮(force=True)")
            except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
                logger.warning("[上传视频] force=True click 失败: %s", e)
                await upload_btn.evaluate("el => el.click()")
                logger.info("[上传视频] 已点击「上传视频」按钮(JS .click())")

        # 4. 等带标记的 input 出现(patch 命中 或 MutationObserver 命中)
        marked_sel = (
            "input[type='file'][data-weibo-upload='1'],"
            "input[type='file'][data-weibo-new='1']"
        )
        deadline = asyncio.get_running_loop().time() + 30
        found_input = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                count = await page.locator(marked_sel).count()
                if count > 0:
                    found_input = page.locator(marked_sel).first
                    logger.info("[上传视频] 检测到标记的 file input(count=%d)", count)
                    break
            except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
                logger.warning("[上传视频] locator count 异常: %s", e)
            await asyncio.sleep(0.5)

        if found_input is not None:
            await found_input.set_input_files(file_path)
            logger.info(
                "[上传视频] 视频文件已通过 patched input 提交: %s",
                os.path.basename(file_path),
            )
            return

        # 5. 三重都失败
        all_count = await page.locator("input[type='file']").count()
        raise RuntimeError(
            "[上传视频] 30s 内未检测到带标记的 file input。"
            f"input[type=file] 总数: {all_count}。"
            "CloakBrowser 屏蔽了所有 click 路径,需要换策略。"
        )


async def _wait_for_upload_form(page, timeout_s: int = 14400):
        """等待视频上传完成、表单可交互。

        **权威锚点**(2026-06-17 调整): 两个信号中任一为真即返回。

        1. 「上传中」spinner DOM 消失 — 直接信号
        2. 发布按钮文字从「自动发布」变成「发布」 — 上传中按钮文案是
           「自动发布」,上传完成后变为「发布」。检测 ``button[name=发布]``
           可见即视为上传完成。

        用 OR 不用 AND 的原因: weibo 在文件传输完成(``check.json`` 200)
        后,「上传中」spinner DOM 仍会持续存在较长时间(可能用于转码阶段,
        实测 7+ 分钟仍未消失),仅看 spinner 会导致函数长时间挂起,所有
        后续表单操作全部阻塞。OR 逻辑下一旦发布按钮文字变更为「发布」
        就放行,避免误判。

        DOM 结构(spinner):
        ```html
        <div class="woo-box-flex woo-box-alignCenter _info_xxx_135">
            <svg class="woo-spinner-main">...</svg>
            <span>上传中</span>
            <span>3.01MB/14.33MB</span>
            <a>暂停</a><a>删除</a>
        </div>
        ```

        class 名是 CSS-modules 生成、会随构建变化 — 用「上传中」文本
        (exact match) 检测这个 DOM 是否还在。

        上传未完成之前,所有后续表单设置操作(_set_video_type /
        _set_title / _set_cover / _set_category / _set_description /
        _set_content_statement / _click_publish) 全部阻塞在此函数,
        等任一信号命中才继续。

        **超时默认 4 小时**(14400s):大视频(几 GB)+ 慢网络上传可能
        需要 1 小时甚至更久,留足余量。
        """
        # 检测「上传中」spinner DOM 是否还存在 + 发布按钮文字是否变成「发布」
        uploading_locator = page.get_by_text("上传中", exact=True)
        publish_btn = page.get_by_role("button", name="发布", exact=True).first
        deadline = asyncio.get_running_loop().time() + timeout_s

        while asyncio.get_running_loop().time() < deadline:
            # 1. 「上传中」DOM 消失 或 发布按钮可见(文字已从「自动发布」变成「发布」)
            try:
                uploading_gone = await uploading_locator.count() == 0
                publish_visible = await publish_btn.is_visible()
                if uploading_gone or publish_visible:
                    if uploading_gone and publish_visible:
                        logger.info(
                            "[发布] 「上传中」DOM 已消失且「发布」按钮可见,"
                            "上传完成、表单可交互"
                        )
                    elif uploading_gone:
                        logger.info(
                            "[发布] 「上传中」DOM 已消失,上传完成"
                        )
                    else:
                        logger.info(
                            "[发布] 「上传中」DOM 仍存在,但「发布」按钮已可见,"
                            "视为上传完成、表单可交互(转码阶段 spinner 暂未消失)"
                        )
                    return
            except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                pass

            # 2. 上传失败检测
            try:
                if await page.get_by_text("上传失败", exact=True).count() > 0:
                    raise RuntimeError(
                        "[发布] 视频上传失败(页面检测到「上传失败」文本)"
                    )
            except RuntimeError:
                raise
            except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                pass

            # 3. 进度旁证(每 30s 一次,避免刷屏)
            try:
                remaining = int(deadline - asyncio.get_running_loop().time())
                if remaining % 60 < 5 or remaining < 60:
                    uploading_count = await uploading_locator.count()
                    logger.info(
                        "[发布] 等待「上传中」消失或「发布」按钮可见... "
                        "上传中=%d (剩余 %ds)",
                        uploading_count, remaining,
                    )
            except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                pass

            await asyncio.sleep(5)

        # 超时
        try:
            url = page.url
        except Exception:  # noqa: BLE001 -- 捕获后重新抛出,统一异常出口
            url = "(unknown)"
        raise RuntimeError(
            f"[发布] 等待视频上传完成超时({timeout_s}s = "
            f"{timeout_s // 60}min),「上传中」未消失且「发布」按钮未可见。"
            f"当前 URL: {url}"
        )


async def _set_video_type(page, ai_content: str):
        """选择类型单选(原创/二创/转载)。ai_content 传的是 UI 标签文本。"""
        if not ai_content:
            return  # 默认值由微博控制,不强选
        # 取出 spec 里的 _VIDEO_TYPE_MAP 的 key (原创/转载/二创)
        target = None
        for label in _VIDEO_TYPE_MAP:
            if label in ai_content or ai_content in label:
                target = label
                break
        if not target:
            logger.warning("[发布] 未知类型声明值: %s,跳过", ai_content)
            return
        # DOM: <label><input type="radio"><span>原创</span></label>
        # 标签内的 radio 的无障碍名取自兄弟 span 文本
        radio = page.get_by_role("radio", name=target, exact=True).first
        try:
            await radio.wait_for(state="visible", timeout=5000)
            await radio.click(force=True)
            logger.info("[发布] 已选类型: %s", target)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[发布] 选择类型失败(%s): %s", target, e)


async def _set_title(page, title: str):
        """填充标题(0~30 字)。"""
        if not title:
            return
        # 微博标题 placeholder: 填写标题(0～30个字)
        title_input = page.locator("input[placeholder*='填写标题']").first
        await title_input.wait_for(state="visible", timeout=10000)
        # 标题最多 30 字
        truncated = title.strip()[:30]
        await title_input.fill(truncated)
        logger.info("[发布] 已填标题: %s", truncated)


async def _pick_cover_by_aspect(
        page,
        landscape_path=None,
        portrait_path=None,
    ):
        """根据当前页面封面框的宽高比,选横版还是竖版封面。

        微博封面框用 ``<div style="padding-bottom: X%;"></div>`` 实现
        宽高比(X = height/width × 100):
        - X < 100 → 横版(landscape),16:9 时 X=56.25
        - X > 100 → 竖版(portrait),9:16 时 X≈177.78
        - X == 100 → 正方形(本函数按横版走)

        实现思路:从「上传封面」/「裁剪封面」链接反向查找,沿祖先
        找包含 ``div[style*="padding-bottom"]`` 的容器 — 该容器就是
        当前实际的封面框,里面的 aspect div 给出宽高比。读不到(还没
        渲染 / 解析失败)默认横版,向后兼容。

        注意:检测时机必须在表单渲染完成之后,否则 cover 区域 DOM
        不完整(2026-06-17 实测)。这里先 wait_for 「上传封面」链接
        attached 再跑 JS。
        """
        # 先等封面区域 DOM 完整 — 2026-06-17 实测:链接先于 picture 出现,
        # walk-up 14 层都找不到 aspect div(整个页面 totalAspects=0)。
        # 关键等待:link 所在 inner 容器(link 的祖父)里出现 <img>,这才是
        # picture 真正渲染好的直接信号,比等 abstract 的 "div[style*=
        # padding-bottom]" 可靠(后者会假阳性命中 padding-bottom:0 的
        # 无关 div)。
        try:
            await page.get_by_text("上传封面").first.wait_for(
                state="attached", timeout=10000,
            )
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[发布] 等「上传封面」链接超时: %s", e)

        try:
            # link 的 xpath=../.. 是 inner 容器
            # (_box_1ant3_2 / _a5lt_1gx9k_203),内含 picture + 链接区
            inner = page.get_by_text("上传封面", exact=True).first.locator(
                "xpath=../.."
            )
            await inner.locator("img").first.wait_for(
                state="attached", timeout=10000,
            )
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[发布] 等封面 picture(img) 超时: %s", e)

        try:
            aspect, debug = await page.evaluate(r"""() => {
                // 反向:从「上传封面」/「裁剪封面」链接向上找含 aspect div 的祖先
                // aspect div 选择器收紧到要带 %,避开 padding-bottom:0 的假阳性
                const ASPECT_SEL = 'div[style*="padding-bottom"][style*="%"]';
                const links = document.querySelectorAll('a');
                let coverLink = null;
                for (const a of links) {
                    const t = (a.textContent || '').trim();
                    if (t === '上传封面' || t === '裁剪封面') {
                        coverLink = a;
                        break;
                    }
                }
                if (!coverLink) {
                    return [null, {
                        reason: 'no cover link found',
                        allLinkTexts: Array.from(links)
                            .map(a => (a.textContent || '').trim())
                            .filter(s => s.length > 0 && s.length < 20)
                            .slice(0, 30),
                    }];
                }

                // 调试:aspect div 全局统计 + 第一个 aspect div 的 style
                const allAspects = document.querySelectorAll(ASPECT_SEL);
                const debug = {
                    totalAspects: allAspects.length,
                    firstAspectStyle: allAspects[0]
                        ? allAspects[0].getAttribute('style')
                        : null,
                    linkParentTag: coverLink.parentElement
                        ? coverLink.parentElement.tagName
                        : null,
                    linkParentClass: coverLink.parentElement
                        ? (coverLink.parentElement.className || '').substring(0, 80)
                        : null,
                    ancestorChain: [],
                };

                let p = coverLink.parentElement;
                let depth = 0;
                while (p && p !== document.body && depth < 20) {
                    const aspectDiv = p.querySelector(ASPECT_SEL);
                    const hasAspect = aspectDiv !== null;
                    debug.ancestorChain.push({
                        depth,
                        tag: p.tagName,
                        className: (p.className || '').substring(0, 80),
                        hasAspect,
                    });
                    if (hasAspect) {
                        const m = (
                            aspectDiv.getAttribute('style') || ''
                        ).match(
                            /padding-bottom:\s*([0-9.]+)\s*%/i
                        );
                        if (m) {
                            debug.matchedAt = depth;
                            debug.matchedStyle = aspectDiv.getAttribute('style');
                            return [parseFloat(m[1]), null];
                        }
                    }
                    p = p.parentElement;
                    depth++;
                }
                return [null, { reason: 'aspect div not found in ancestors', ...debug }];
            }""")
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[发布] 读取封面区域宽高比失败: %s", e)
            aspect = None
            debug = None

        if debug:
            logger.info("[发布] 封面宽高比调试: %s", debug)

        if aspect is None:
            logger.info("[发布] 读不到封面框宽高比,默认横版")
            return landscape_path or portrait_path

        if aspect < 100:
            logger.info(
                "[发布] 封面框为横版(padding-bottom=%.2f%%),用横版封面",
                aspect,
            )
            return landscape_path or portrait_path
        else:
            logger.info(
                "[发布] 封面框为竖版(padding-bottom=%.2f%%),用竖版封面",
                aspect,
            )
            return portrait_path or landscape_path


async def _set_cover(
        page,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_landscape_169_path=None,
        thumbnail_portrait_916_path=None,
    ):
        """上传封面。

        流程(spec ~/1.txt:12-19):
        1. 根据页面封面框宽高比选横版/竖版封面
           (见 ``_pick_cover_by_aspect``)
        2. 点击「上传封面」链接(自动打开系统原生文件选择器)
        3. 按 ESC 关闭原生选择器
        4. 等待「编辑封面」弹层出现
        5. 找到弹层内的隐藏 ``input[type=file]`` 上传图片
        6. 点击「完成」按钮

        封面尺寸优先级:微博封面框实际是 16:9 / 9:16,优先用
        ``thumbnail_landscape_169_path``(16:9) / ``thumbnail_portrait_916_path``
        (9:16);没有时回退到 4:3 / 3:4。
        """
        cover_path = await _pick_cover_by_aspect(
            page,
            landscape_path=thumbnail_landscape_169_path or thumbnail_landscape_path,
            portrait_path=thumbnail_portrait_916_path or thumbnail_portrait_path,
        )
        if not cover_path or not os.path.exists(cover_path):
            logger.info("[发布] 无封面文件,跳过封面上传")
            return

        # 1. 点击「上传封面」(注意 a 标签无 href,用文本匹配)
        upload_cover_link = page.get_by_text("上传封面").first
        try:
            await upload_cover_link.wait_for(state="visible", timeout=10000)
        except Exception:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[发布] 未找到「上传封面」入口,跳过封面")
            return

        # 2. 点击 + 立即 ESC 关掉原生选择器(spec 强调此坑)
        await upload_cover_link.click()
        await asyncio.sleep(0.5)
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.8)
        logger.info("[发布] 已点击上传封面并 ESC 关闭原生选择器")

        # 3. 等待「编辑封面」弹层出现
        try:
            await page.get_by_text("编辑封面").first.wait_for(
                state="visible", timeout=10000
            )
            logger.info("[发布] 封面编辑弹层已出现")
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[发布] 等待封面弹层超时: %s", e)
            return

        # 4. 找到隐藏 input[type=file] 上传
        # spec 弹层里有两个 file input,accept 都是 ".jpg, .jpeg, .bmp, ..."
        # 关键: **不能** 用 [accept*='jpg'] — 微博正文区也有一个 image
        # 上传 input,accept 是 "image/*, .jpg, .jpeg, ..."(以 image/*
        # 开头),会被一起匹配,导致 .first 选错。
        # 用 [accept^='.jpg'] 严格匹配"以 .jpg 开头",只命中封面弹层。
        file_inputs = page.locator("input[type='file'][accept^='.jpg']")
        count = await file_inputs.count()
        if not count:
            logger.warning("[发布] 封面弹层未找到 input[type=file][accept^='.jpg']")
            return
        logger.info("[发布] 找到 %d 个封面 file input", count)
        await file_inputs.first.set_input_files(cover_path)
        logger.info("[发布] 已上传封面文件: %s", os.path.basename(cover_path))
        # 等图片处理完(上传到 weibo + 裁剪器加载预览)。2s 实测不够,
        # 经常「完成」点了之后弹层关掉但封面没存上(2026-06-17)。
        await asyncio.sleep(4)

        # 5. 点击「完成」按钮 (封面编辑弹层右下角)
        # 用 role+name 定位,避免 class 哈希漂移
        done_btn = page.get_by_role("button", name="完成", exact=True).first
        try:
            await done_btn.wait_for(state="visible", timeout=5000)
            # force=True 兜底:封面弹层是 fixed 定位,偶尔有透明遮罩
            # 拦截 pointer events,导致普通 click 一直 retry(2026-06-17 实测)
            await done_btn.click(force=True)
            logger.info("[发布] 已点击封面完成按钮")
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[发布] 点击封面完成按钮失败: %s", e)

        # 6. 关键: 等待「编辑封面」弹层真正关闭,否则它会盖住下面的
        #    「请选择合适的频道」下拉触发器和微博正文 textarea,导致后续步骤
        #    全部因元素 hidden 而失败。
        try:
            await page.get_by_text(
                "编辑封面", exact=True,
            ).first.wait_for(state="hidden", timeout=15000)
            logger.info("[发布] 封面编辑弹层已关闭")
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning(
                "[发布] 等待封面弹层关闭超时,尝试 ESC 强制关闭: %s", e,
            )
            # ESC 兜底
            for _ in range(2):
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
        await asyncio.sleep(1)


async def _set_collection(page, collection_name: str):
        """选择微博视频合集。

        DOM(参考 weibo_bp.py 合集列表解析):
          - 合集开关: label.woo-switch-main(默认关闭,需点击开启)
            注意:页面有多个 woo-switch-main(允许划重点/允许他人剪辑/关联原视频等),
            合集开关是「合集」标题旁边那个 —— 用文案定位其容器再定位开关。
          - 开启后展开合集列表,每项: div._top2_* > label.woo-checkbox-main
            + input[type=text][value="合集名(共N集)"]

        流程:
          1. 定位「合集」标题所在行 → 找该行内的 woo-switch-main → 点击开启
          2. 等合集列表展开(input[type=text][value*="集"] 出现)
          3. 遍历合集项,找到 value 匹配 collection_name 的 → 勾选其 checkbox
        """
        # 1. 定位合集开关:在「合集」文案所在的设置行内找 woo-switch-main
        #    合集行的结构:div._switch_* > div(含「合集」文案) + div > label.woo-switch-main
        logger.info("[设置合集] 定位合集开关...")
        switch_clicked = False
        try:
            # 找所有含「合集」文本的行容器,再在其内部找开关
            switch_labels = page.locator("label.woo-switch-main")
            count = await switch_labels.count()
            logger.info("[设置合集] 页面共 %d 个 woo-switch-main 开关", count)
            # 合集开关特征:它的祖先行包含「合集」文案
            for i in range(count):
                label = switch_labels.nth(i)
                # 向上找到包含「合集」文案的容器
                has_collection_text = await label.evaluate(
                    """el => {
                        let node = el;
                        for (let depth = 0; depth < 6 && node; depth++) {
                            if (node.textContent && node.textContent.includes('合集') && !node.textContent.includes('允许')) {
                                return true;
                            }
                            node = node.parentElement;
                        }
                        return false;
                    }"""
                )
                if has_collection_text:
                    await label.click()
                    logger.info("[设置合集] 已点击第 %d 个开关(合集开关)", i)
                    switch_clicked = True
                    break
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[设置合集] 点击合集开关失败: %s", e)

        if not switch_clicked:
            logger.warning("[设置合集] 未找到合集开关,跳过合集设置")
            return

        # 2. 等合集列表展开
        await asyncio.sleep(1.5)
        album_inputs = page.locator('input[type="text"][value*="集"]')
        try:
            await album_inputs.first.wait_for(state="attached", timeout=10000)
        except Exception:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[设置合集] 切换开关后合集列表未展开,跳过")
            return

        # 3. 遍历合集项,找到名称匹配的勾选其 checkbox
        #    DOM 结构:每个合集项是一个 div._top2_*,内部:
        #      <label class="woo-checkbox-main">...</label>  ← 复选框(第一个子元素)
        #      <div class="woo-box-item-flex">...<input value="合集名(共N集)">...</div>
        #    用 xpath:先定位 value 匹配的 input → 向上找到 _top2_* 行 → 找行内 woo-checkbox-main
        total = await album_inputs.count()
        logger.info("[设置合集] 展开共 %d 个合集,查找: %s", total, collection_name)
        for i in range(total):
            try:
                raw = await album_inputs.nth(i).get_attribute("value")
                if not raw:
                    continue
                # value 形如 "AI(共0集)",取括号前的名称
                name = raw.split("(")[0].split("（")[0].strip() if raw else ""
                if name == collection_name:
                    # 用 xpath 定位同行内的 checkbox:从 input 向上找祖先 _top2_* 行,
                    # 再找该行内的 label.woo-checkbox-main
                    checkbox = album_inputs.nth(i).locator(
                        "xpath=ancestor::div[contains(@class,'_top2_')]"
                        "//label[contains(@class,'woo-checkbox-main')]"
                    ).first
                    await checkbox.click()
                    logger.info("[设置合集] 已勾选合集: %s", collection_name)
                    await asyncio.sleep(0.5)
                    return
            except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
                logger.warning("[设置合集] 勾选第 %d 项失败: %s", i, e)
                continue

        logger.warning("[设置合集] 未找到匹配的合集: %s", collection_name)


async def _set_description(page, desc: str, title: str, tags: list):
        """填充微博正文 textarea。

        若 desc 为空,回落到 title;tags 拼成 #话题 形式追加。
        """
        # textarea placeholder: 有什么新鲜事想分享给大家?
        textarea = page.locator(
            "textarea[placeholder*='有什么新鲜事']"
        ).first
        await textarea.wait_for(state="visible", timeout=10000)

        text = (desc or title or "").strip()
        if tags:
            tag_str = " ".join(f"#{t}" for t in tags)
            text = f"{text} {tag_str}".strip() if text else tag_str
        if not text:
            return

        # 微博 textarea 不是标准 input,fill 不一定生效,用 click+type
        await textarea.click()
        await asyncio.sleep(0.2)
        # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
        await clear_and_type(page, text, delay=30)
        await page.keyboard.press("Space")
        logger.info("[发布] 已填正文(长度=%d)", len(text))


async def _set_content_statement(page, v1_stmt: str = "", v2_required: str = "", v2_optional: str = ""):
        """选择发布页的「内容声明」。

        微博有两种内容声明 UI,对不同账号/场景展示其中一种,运行时自动探测:

        版本1(老):底部工具栏「内容声明」文本触发弹窗,5 选项单选
            (无/内容为自主创作/内容为转载/内容由AI生成/内容为虚构演绎)。
        版本2(新):「请进行内容声明（必填）」触发下拉,分「必选」6 项 +
            「可选」4 项两组,选完点「确定」。

        前端用 3 个独立下拉分别承载两套声明,后端探测到哪种 UI 就用对应那套值:
        - 版本1 UI → 用 v1_stmt
        - 版本2 UI → 用 v2_required(必选) + v2_optional(可选)

        Args:
            v1_stmt: 版本1 声明值(5 选 1,或「无」/空=不设置)。
            v2_required: 版本2「必选」区声明值(6 选 1)。空或「内容无需标注」
                时点「内容无需标注」(必选区必须选一个)。
            v2_optional: 版本2「可选」区声明值。空=不选。
        """
        # 先探测版本2 trigger「请进行内容声明（必填）」是否存在
        # 注意:不能用 exact=True,实际 DOM 文本可能含全角括号或前后空白,
        # 用 contains 匹配更稳。探测全程打日志,绝不静默吞异常。
        logger.info(
            "[内容声明] 开始探测页面 UI 版本(v2_required=%s)",
            v2_required or "(空)",
        )
        v2_detected = False
        try:
            # 多个候选文本:全角括号 / 半角括号 / 含空白
            v2_trigger = page.get_by_text("请进行内容声明", exact=False).first
            cnt = await v2_trigger.count()
            logger.info("[内容声明] 探测「请进行内容声明」count=%d", cnt)
            if cnt > 0:
                v2_detected = True
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            # 探测本身异常:打印详情,不静默吞
            logger.warning("[内容声明] 探测版本2 trigger 异常: %s", e)

        if v2_detected:
            logger.info("[内容声明] ✓ 检测到版本2 UI(必填下拉),走 v2 逻辑")
            try:
                await _set_content_statement_v2(
                    page, v2_required, v2_optional
                )
            except Exception as e:
                logger.exception("[内容声明] 版本2 处理异常: %s", e)
            return

        # 否则走版本1(老弹窗)
        logger.info("[内容声明] 未检测到版本2,走版本1(弹窗)逻辑")
        try:
            await _set_content_statement_v1(page, v1_stmt)
        except Exception as e:
            logger.exception("[内容声明] 版本1 处理异常: %s", e)


async def _set_content_statement_v1(page, statement: str):
        """版本1:底部工具栏「内容声明」弹窗单选。

        spec line 7206: 5 个选项 — 无(默认)、内容为自主创作、内容为转载、
        内容由AI生成、内容为虚构演绎。
        空值或「无」视为不设置(微博默认就是「无」)。
        """
        if not statement or statement.strip() == "无":
            return

        stmt_text = statement.strip()
        # trigger 是「内容声明」文本节点,click 冒泡到父级 woo-pop-ctrl
        # 但父级 <span class="woo-pop-ctrl"> 在 actionability 检查里
        # 会被判为「intercept pointer events」(2026-06-17 实测:50+ 次
        # retry → 页面上下弹),必须 force=True 跳过这个检查。
        trigger = page.get_by_text("内容声明", exact=True).first
        try:
            await trigger.wait_for(state="visible", timeout=5000)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[发布] 未找到内容声明入口: %s", e)
            return

        await trigger.click(force=True)
        await asyncio.sleep(0.5)

        # 弹窗里的选项是 button,文本就是选项值
        option = page.get_by_role("button", name=stmt_text, exact=True).first
        try:
            await option.wait_for(state="visible", timeout=5000)
            await option.click()
            logger.info("[发布] 已选内容声明(版本1): %s", stmt_text)
            await asyncio.sleep(0.5)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning(
                "[发布] 选择内容声明失败(%s): %s", stmt_text, e,
            )
            # ESC 关闭弹出的内容声明面板
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)


async def _set_content_statement_v2(page, required_stmt: str, optional_stmt: str = ""):
        """版本2:「请进行内容声明（必填）」下拉,分必选/可选两组。

        DOM 结构(用户提供):
          trigger: <div class="_triggerText...">请进行内容声明（必填）</div>
          面板: <div class="_panel...">
                   <div class="_sectionTitle">必选</div>
                   <button>...内容无需标注 / 内容为转载 / 含AI生成内容 /
                           含虚构演绎内容 / 个人观点，仅供参考 / 内容含营销信息</button>
                   <div class="_sectionTitle">可选</div>
                   <button>...内容可能引人不适... / 内容含有高危险行为... /
                           请理性适度消费 / 未成年人请在监护人指导下浏览</button>
                   <div class="_footer"><button>确定</button></div>
                </div>

        Args:
            required_stmt: 必选声明值。空或「内容无需标注」时点「内容无需标注」
                (必选区必须选一个)。
            optional_stmt: 可选声明值。空=不选。
        """
        # 必选区:空或「内容无需标注」默认选「内容无需标注」(必选必填一个)
        required_text = (required_stmt or "").strip()
        if not required_text or required_text == "无":
            required_text = "内容无需标注"

        # 点 trigger 展开「必填」下拉(woo-pop-ctrl 同样有 intercept 问题,force)
        # exact=False:实际文本可能含全角括号/前后空白,用包含匹配
        trigger = page.get_by_text("请进行内容声明", exact=False).first
        try:
            await trigger.wait_for(state="visible", timeout=5000)
            logger.info("[内容声明v2] 找到 trigger「请进行内容声明」")
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[内容声明v2] 未找到 trigger 入口: %s", e)
            return

        await trigger.click(force=True)
        logger.info("[内容声明v2] 已点击 trigger,等待面板展开")
        # 面板展开是动画,实测 0.5s 偶尔不够,给 1s 让 _panel 完整渲染
        await asyncio.sleep(1)

        # 校验面板是否真正展开(区分"没展开"和"展开了没点到")
        panel = page.locator("._panel_nsgmr_114, [class*='_panel_']").first
        try:
            await panel.wait_for(state="visible", timeout=3000)
            logger.info("[发布] 内容声明(版本2)面板已展开")
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[发布] 内容声明(版本2)面板未展开(trigger 点击无效?): %s", e)
            return

        # 通用:在弹出面板里点某个选项
        # 关键:不用 get_by_role(button, name=) — 选项 button 内部是
        # <span class="_check"><!----></span> + <span class="_optionLabel">文案</span>,
        # accessible name 计算不稳定。改为用 CSS 类直接定位 _optionLabel 文案,
        # 再点其父级 button。
        async def _click_option(text, timeout=5000):
            """点面板里文案为 text 的选项,返回是否成功。"""
            # 定位文案 span,再点其所在 button(用 force 跳过 intercept)
            label = page.locator(
                f"[class*='_optionLabel']:has-text('{text}')"
            ).first
            try:
                await label.wait_for(state="visible", timeout=timeout)
                # 点 label 的父级 button(label 本身不是可点击区,button 才是)
                btn = label.locator("xpath=ancestor::button[1]")
                if await btn.count() == 0:
                    # 兜底:直接点 label
                    await label.click(force=True)
                else:
                    await btn.first.click(force=True)
                return True
            except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
                logger.warning("[发布] 内容声明(版本2)点击选项「%s」失败: %s", text, e)
                return False

        # 选必选项(必选区必须选一个,失败则 ESC 退出)
        ok = await _click_option(required_text, timeout=5000)
        if not ok:
            logger.warning("[发布] 内容声明(版本2)必选项「%s」选择失败,放弃", required_text)
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
            return
        logger.info("[发布] 已选内容声明(版本2必选): %s", required_text)
        await asyncio.sleep(0.4)

        # 选可选项(可选,空则跳过;失败不中断,继续点确定)
        if optional_stmt and optional_stmt.strip():
            opt_text = optional_stmt.strip()
            if await _click_option(opt_text, timeout=3000):
                logger.info("[发布] 已选内容声明(版本2可选): %s", opt_text)
                await asyncio.sleep(0.4)

        # 点「确定」按钮提交选择(必点,否则选择不生效)
        # DOM:<button class="woo-button-..."><span class="woo-button-content"> 确定 </span></button>
        # 用 woo-button-content 文本定位,不依赖 accessible name
        try:
            confirm_btn = page.locator(
                ".woo-button-content:has-text('确定')"
            ).first
            await confirm_btn.wait_for(state="visible", timeout=3000)
            # 点 button(woo-button-content 的父级),force 跳过 intercept
            confirm_button = confirm_btn.locator("xpath=ancestor::button[1]")
            if await confirm_button.count() > 0:
                await confirm_button.first.click(force=True)
            else:
                await confirm_btn.click(force=True)
            logger.info("[发布] 内容声明(版本2)已点确定,选择提交")
            await asyncio.sleep(0.5)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[发布] 点内容声明(版本2)确定按钮失败: %s", e)
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)


async def _click_publish(page):
        """点击页面右下角「发布」按钮。

        初始 disabled,表单填好后启用。用 role+name 定位避免 class 哈希漂移。
        """
        # get_by_role 只匹配可访问性树里的元素,hidden 元素(如未来 toast 的
        # 「再发一条视频」按钮)默认被排除,所以 .first 就是当前可见的发布按钮
        publish_btn = page.get_by_role("button", name="发布", exact=True).first
        try:
            await publish_btn.wait_for(state="visible", timeout=10000)
        except Exception as e:  # 捕获后重新抛出,统一异常出口
            raise RuntimeError(f"[发布] 未找到发布按钮: {e}") from e

        # 轮询 disabled 属性(最长 60s)
        for _ in range(60):
            disabled = await publish_btn.get_attribute("disabled")
            if disabled is None:
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("[发布] 发布按钮一直 disabled,表单未就绪")

        await publish_btn.click()
        logger.info("[发布] 已点击发布按钮")


async def _wait_for_publish_success(page, timeout_s: int = 60):
        """等待发布完成的信号。

        微博点发布后会显示 toast:「视频已上传成功,将在转码后发布」,
        或 URL 变化到视频管理页。两者满足其一即视为成功。
        """
        try:
            # 优先等 toast 文案
            await page.locator(
                "text=视频已上传成功"
            ).first.wait_for(state="visible", timeout=timeout_s * 1000)
            logger.info("[发布] 发布成功(检测到「视频已上传成功」toast)")
        except Exception:  # noqa: BLE001 -- 捕获后恢复默认状态,防御性编码
            # 兜底: 看 URL 是否跳走
            await asyncio.sleep(3)
            current = page.url
            if "weibo.com/upload/channel" not in current:
                logger.info("[发布] 发布成功(URL 已跳转: %s)", current)
            else:
                raise RuntimeError(
                    f"[发布] 发布后未检测到成功信号,当前 URL: {current}"
                ) from None
