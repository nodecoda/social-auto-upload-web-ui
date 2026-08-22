"""抖音平台 — 视频/图集 DOM 交互、表单构造 子模块（A8 拆分）。

从 platform.py 拆出的平台专属 DOM 操作: 原 DouyinPlatform 的
staticmethod/classmethod, 现为模块级函数, 由 platform.py 以
`_x = staticmethod(_x)` 类属性绑定, 保持 `self._x(...)` /
`DouyinPlatform._x(...)` 调用语义不变(零行为变更)。
"""
import asyncio
import re

from util._logger import get_channel_logger

from .._utils import clear_and_type

logger = get_channel_logger("douyin")

_HASHTAG_PATTERN = re.compile(r"(?:^|\s)#[^\s#]+", re.MULTILINE)


def _count_hashtags(text: str) -> int:
        """统计描述文本里独立的 #xxx 话题数量。

        - 行首或空白后的 ``#`` 才算话题开头(避免 ``a#b``、``http://x#anchor`` 误判)。
        - ``##``、孤立 ``#`` 不计数。
        """
        if not text:
            return 0
        return len(_HASHTAG_PATTERN.findall(text))


def _validate_publish_params(desc: str, tags: list, activities: list) -> tuple[bool, str]:
        """校验话题总数,返回 (ok, msg)。

        规则:描述里的 ``#xxx`` + 标签数 + 官方活动数 ≤ 5
        (抖音一条视频最多 5 个话题,超出发布页会拒绝)。
        """
        desc = desc or ""
        tags = tags or []
        activities = activities or []
        total = (
            _count_hashtags(desc)
            + len(tags)
            + len(activities)
        )
        if total > 5:
            return False, (
                f"抖音话题总数 {total} 超过 5 个"
                f"(描述 #xxx {_count_hashtags(desc)} + 标签 {len(tags)}"
                f" + 官方活动 {len(activities)}),请删减"
            )
        return True, ""


async def _fill_title_and_description(
        page, title: str, description: str, tags: list | None = None
    ):
        description_section = (
            page.get_by_text("作品描述", exact=True)
            .locator("xpath=ancestor::div[2]")
            .locator("xpath=following-sibling::div[1]")
        )

        title_input = description_section.locator('input[type="text"]').first
        await title_input.wait_for(state="visible", timeout=10000)
        await title_input.fill(title[:30])

        description_editor = description_section.locator(
            '.zone-container[contenteditable="true"]'
        ).first
        await description_editor.wait_for(state="visible", timeout=10000)
        await description_editor.click()
        # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
        # 只输入一次,不要重复输入
        clean_description = (description or "").rstrip()
        await clear_and_type(page, clean_description)

        await page.keyboard.press("Space")
        # 修：标签循环用单空格分隔，首 tag 前明确加一个空格
        for tag in tags or []:
            if not tag:
                continue
            # 用 insert_text 不会触发 IME 干扰
            await page.keyboard.insert_text(" " + "#" + tag)
            # Space 让抖音把 " #tag" 识别为 hashtag chip
            await page.keyboard.press("Space")
            # 修：移动光标到内容末尾，避免下次插入位置错乱
            await page.keyboard.press("End")


async def _set_schedule_time(page, publish_date):
        # 抖音使用字节 Semi Design 的 dateTime 选择器：日期与时间分属两个视图，
        # 由 .semi-datepicker-switch 切换；dateTime 模式需手动确认(needConfirm)。
        # 仅往输入框敲文本+回车只能可靠设置日期，时间(HH:MM)会被丢弃，
        # 因此必须切到时间滚轮(.semi-datepicker-switch-time)分别选时/分。
        if isinstance(publish_date, int) and publish_date == 0:
            return

        dt = publish_date
        expected = dt.strftime("%Y-%m-%d %H:%M")
        logger.info("[定时发布] 开始设置定时发布时间: %s", expected)
        try:
            # 1. 选择「定时发布」单选项
            await page.locator("[class^='radio']:has-text('定时发布')").click()
            await asyncio.sleep(1)

            # 2. 打开日期时间选择面板
            await page.locator('.semi-input[placeholder="日期和时间"]').click()
            await asyncio.sleep(1)

            # 3. 选择日期：点击对应日期格(title=YYYY-MM-DD，排除禁用日期)
            iso_date = dt.strftime("%Y-%m-%d")
            day_cell = page.locator(
                f'.semi-datepicker-day:not(.semi-datepicker-day-disabled)[title="{iso_date}"]'
            )
            if await day_cell.count():
                await day_cell.first.click()
                logger.info("[定时发布] 日期已选择: %s", iso_date)
            else:
                logger.warning("[定时发布] 未找到可选日期 %s，跳过日期选择", iso_date)
            await asyncio.sleep(0.5)

            # 4. 切换到时间选择滚轮
            switch_time = page.locator('.semi-datepicker-switch-time')
            if await switch_time.count():
                await switch_time.first.click()
                logger.info("[定时发布] 已切换到时间选择滚轮")
                await asyncio.sleep(1)
            else:
                logger.warning("[定时发布] 未找到时间切换开关 .semi-datepicker-switch-time")

            # 5. 选择小时(滚轮内 li 文本为纯数字；选中项带「时」后缀，has_text 均可命中)
            hour = dt.strftime("%H")
            hour_item = (
                page.locator('.semi-scrolllist-item-wheel.undefined-list-hour li')
                .filter(has_text=hour)
            )
            if await hour_item.count():
                await hour_item.first.click()
                logger.info("[定时发布] 小时已选择: %s", hour)
            else:
                logger.warning("[定时发布] 未找到小时项 %s", hour)
            await asyncio.sleep(0.4)

            # 6. 选择分钟
            minute = dt.strftime("%M")
            minute_item = (
                page.locator('.semi-scrolllist-item-wheel.undefined-list-minute li')
                .filter(has_text=minute)
            )
            if await minute_item.count():
                await minute_item.first.click()
                logger.info("[定时发布] 分钟已选择: %s", minute)
            else:
                logger.warning("[定时发布] 未找到分钟项 %s", minute)
            await asyncio.sleep(0.4)

            # 7. 确认(dateTime 模式需点「确定」；找不到则回车兜底)
            confirmed = False
            confirm_btn = page.locator('.semi-popover button:has-text("确定")')
            if await confirm_btn.count():
                await confirm_btn.first.click()
                confirmed = True
                logger.info("[定时发布] 已点击「确定」确认")
            if not confirmed:
                await page.keyboard.press("Enter")
                logger.info("[定时发布] 未找到确认按钮，已按 Enter 兜底")
            await asyncio.sleep(1)

            # 8. 校验输入框最终值，便于排查时间是否真的生效
            try:
                final_val = await page.input_value(
                    '.semi-input[placeholder="日期和时间"]'
                )
                if final_val and dt.strftime("%H:%M") in final_val:
                    logger.info("[定时发布] 校验成功，输入框值: %s", final_val)
                else:
                    logger.warning(
                        "[定时发布] 校验异常，输入框值: %s（期望含 %s）",
                        final_val, dt.strftime("%H:%M"),
                    )
            except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                pass
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.error("[定时发布] 设置定时发布时间失败: %s", exc)


async def _set_product_link(page, product_link: str, product_title: str):
        await page.wait_for_timeout(2000)
        try:
            await page.wait_for_selector("text=添加标签", timeout=10000)
            dropdown = (
                page.get_by_text("添加标签")
                .locator("..")
                .locator("..")
                .locator("..")
                .locator(".semi-select")
                .first
            )
            if not await dropdown.count():
                logger.warning("[商品链接] 未找到标签下拉框")
                return False

            await dropdown.click()
            await page.wait_for_selector('[role="listbox"]', timeout=5000)
            await page.locator('[role="option"]:has-text("购物车")').click()

            await page.wait_for_selector(
                'input[placeholder="粘贴商品链接"]', timeout=5000
            )
            input_field = page.locator('input[placeholder="粘贴商品链接"]')
            await input_field.fill(product_link)

            add_button = page.locator('span:has-text("添加链接")')
            button_class = await add_button.get_attribute("class")
            if "disable" in button_class:
                logger.warning("[商品链接] 添加链接按钮不可用")
                return False
            await add_button.click()

            await page.wait_for_timeout(2000)
            error_modal = page.locator("text=未搜索到对应商品")
            if await error_modal.count():
                confirm_button = page.locator('button:has-text("确定")')
                await confirm_button.click()
                logger.warning("[商品链接] 商品链接无效")
                return False

            # Fill product short title
            await page.wait_for_timeout(2000)
            await page.wait_for_selector(
                'input[placeholder="请输入商品短标题"]', timeout=10000
            )
            short_title_input = page.locator(
                'input[placeholder="请输入商品短标题"]'
            )
            if not await short_title_input.count():
                logger.warning("[商品链接] 未找到商品短标题输入框")
                return False

            await short_title_input.fill(product_title[:10])
            await page.wait_for_timeout(1000)

            finish_button = page.locator('button:has-text("完成编辑")')
            if "disabled" not in await finish_button.get_attribute("class"):
                await finish_button.click()
                await page.wait_for_selector(
                    ".semi-modal-content", state="hidden", timeout=5000
                )
                return True

            # Button is disabled — close dialog
            cancel_button = page.locator('button:has-text("取消")')
            if await cancel_button.count():
                await cancel_button.click()
            else:
                close_button = page.locator(".semi-modal-close")
                await close_button.click()
            await page.wait_for_selector(
                ".semi-modal-content", state="hidden", timeout=5000
            )
            return False
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[商品链接] 设置失败: %s", e)
            return False


async def _set_thumbnail(
        page, thumbnail_landscape_path=None, thumbnail_portrait_path=None
    ):
        if not thumbnail_landscape_path and not thumbnail_portrait_path:
            return

        logger.info("[封面] 开始设置视频封面")
        await page.click('text="选择封面"')
        cover_locator_str = 'div[id*="creator-content-modal"]'
        cover_locator = page.locator(cover_locator_str)
        await page.wait_for_selector(cover_locator_str)
        logger.info("[封面] 封面编辑器已打开")

        # 读取 tab 文本识别横版/竖版各自在第几个 tab
        tab_locator = cover_locator.locator("div[class*='steps'] div")
        tab_count = await tab_locator.count()
        portrait_tab_idx = None
        landscape_tab_idx = None
        for i in range(tab_count):
            try:
                text = await tab_locator.nth(i).inner_text()
                if "竖" in text:
                    portrait_tab_idx = i
                if "横" in text:
                    landscape_tab_idx = i
            except Exception:  # noqa: S112, BLE001 -- 单次探测失败,跳过继续
                continue
        logger.info("[封面] 封面tab索引 - 竖版: %s, 横版: %s", portrait_tab_idx, landscape_tab_idx)

        # 通用函数：切换到指定 tab → 取当前可见的 upload input → 上传
        async def _upload_to_tab(tab_index, file_path):
            await cover_locator.locator("div[class*='steps'] div").nth(tab_index).click()
            await page.wait_for_timeout(1500)
            # 每次切 tab 后重新定位，当前 tab 只有一个可见的 upload input
            inp = cover_locator.locator(
                "div[class^='semi-upload upload'] >> input.semi-upload-hidden-input"
            ).first
            await inp.set_input_files(file_path)
            await page.wait_for_timeout(2000)

        if thumbnail_portrait_path and portrait_tab_idx is not None:
            await _upload_to_tab(portrait_tab_idx, thumbnail_portrait_path)
            logger.info("[封面] 竖版封面上传成功 (tab %s)", portrait_tab_idx)
        elif thumbnail_portrait_path:
            # 没找到竖版 tab，尝试默认第一个
            await page.wait_for_timeout(1000)
            await cover_locator.locator(
                "div[class^='semi-upload upload'] >> input.semi-upload-hidden-input"
            ).first.set_input_files(thumbnail_portrait_path)
            await page.wait_for_timeout(2000)
            logger.info("[封面] 竖版封面上传成功 (默认)")

        if thumbnail_landscape_path and landscape_tab_idx is not None:
            await _upload_to_tab(landscape_tab_idx, thumbnail_landscape_path)
            logger.info("[封面] 横版封面上传成功 (tab %s)", landscape_tab_idx)

        await cover_locator.locator('button:visible:has-text("完成")').click()
        logger.info("[封面] 封面设置完成")
        await page.wait_for_selector("div.extractFooter", state="detached")


async def _handle_auto_video_cover(page):
        try:
            if await page.get_by_text("请设置封面后再发布").first.is_visible():
                recommend_cover = page.locator(
                    '[class^="recommendCover-"]'
                ).first
                if await recommend_cover.count():
                    try:
                        await recommend_cover.click()
                        await asyncio.sleep(1)
                        confirm_text = "是否确认应用此封面？"
                        if await page.get_by_text(
                            confirm_text
                        ).first.is_visible():
                            await page.get_by_role(
                                "button", name="确定"
                            ).click()
                            await asyncio.sleep(1)
                        return True
                    except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
                        logger.warning("[封面] 自动封面选择失败: %s", e)
        except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
            pass
        return False


async def _set_image_cover(page, cover_path: str):
        """Set cover image for image note."""
        try:
            # Click edit cover button - use text content for stability
            edit_cover_btn = page.get_by_text("编辑封面", exact=True)
            await edit_cover_btn.click()
            await asyncio.sleep(2)

            # Click upload cover tab
            upload_tab = page.get_by_role("tab", name="上传封面")
            await upload_tab.click()
            await asyncio.sleep(1)

            # Find hidden input=file in the upload area
            # Look for input[type="file"] that accepts images
            cover_input = page.locator('input[type="file"][accept*="image"]').first
            if not await cover_input.count():
                # Fallback: find any hidden file input
                cover_input = page.locator('input[type="file"]').first

            await cover_input.set_input_files(cover_path)
            await asyncio.sleep(3)

            # Click confirm in crop dialog - find button with text "确定"
            # Wait for crop dialog to appear
            await page.wait_for_selector('button:has-text("确定")', timeout=5000)
            # Click the confirm button (not the cancel button)
            confirm_buttons = page.locator('button:has-text("确定")')
            count = await confirm_buttons.count()
            logger.info("[封面] 找到 %d 个确定按钮", count)
            # Click the last one (should be the crop confirm)
            await confirm_buttons.last.click()
            await asyncio.sleep(2)

            # Click final confirm in cover editor
            final_confirm = page.locator('button:has-text("确定")').last
            await final_confirm.click()
            await asyncio.sleep(2)

            logger.info("[封面] 封面图片设置成功")
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[封面] 封面设置失败: %s", e)


async def _set_image_mix(page, mix_id: str):
        """Set mix/collection for image note."""
        try:
            # Click mix dropdown（视频页面可能用不同的文字）
            mix_labels = ["不选择合集", "选择合集", "添加合集"]
            mix_dropdown = None
            for label in mix_labels:
                d = page.locator(f'div.semi-select:has-text("{label}")').first
                if await d.count():
                    mix_dropdown = d
                    break
            if mix_dropdown is None:
                logger.warning("[设置合集] 未找到合集下拉框: %s", mix_id)
                return
            await mix_dropdown.click()
            await asyncio.sleep(2)

            # Select mix by ID or text
            mix_option = page.locator(
                f'div.semi-select-option:has-text("{mix_id}")'
            ).first
            if await mix_option.count():
                await mix_option.click()
                logger.info("[设置合集] 已选择合集: %s", mix_id)
            else:
                logger.warning("[设置合集] 未找到合集: %s", mix_id)
                # Close dropdown
                await page.keyboard.press("Escape")

            await asyncio.sleep(1)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[设置合集] 合集设置失败: %s", e)


async def _select_music(page, music_name: str):
        """Search and select music."""
        try:
            # Click select music button - find the one in the music section
            # Use XPath to find the specific "选择音乐" button
            music_btn = page.locator('xpath=//div[contains(@class, "container-right")]//span[text()="选择音乐"]')
            if not await music_btn.count():
                # Fallback: find by text and click the visible one
                music_btn = page.get_by_text("选择音乐", exact=True).last
            await music_btn.click()
            await asyncio.sleep(3)

            # Search music - use placeholder for stability
            search_input = page.locator('input[placeholder="搜索音乐"]')
            await search_input.wait_for(state="visible", timeout=5000)
            await search_input.fill(music_name)
            await page.keyboard.press("Enter")
            await asyncio.sleep(3)

            # Find matching music card
            music_cards = page.locator('div.card-container-tmocjc')
            count = await music_cards.count()
            logger.info("[选择音乐] 找到 %d 个音乐卡片", count)

            # Find the card that matches the search text
            target_card = None
            for i in range(count):
                card = music_cards.nth(i)
                card_text = await card.text_content()
                if music_name in card_text:
                    target_card = card
                    logger.info("[选择音乐] 找到匹配音乐: %s", card_text[:50])
                    break

            if not target_card and count > 0:
                # Fallback: use first card
                target_card = music_cards.first
                logger.info("[选择音乐] 使用第一个音乐卡片作为兜底")

            if target_card:
                # Hover to show "使用" button
                await target_card.hover()
                await asyncio.sleep(1)

                # Click use button within this card
                use_btn = target_card.locator('button:has-text("使用")')
                if await use_btn.count():
                    await use_btn.click(force=True)
                    logger.info("[选择音乐] 已选择音乐: %s", music_name)
                else:
                    logger.warning("[选择音乐] 未找到使用按钮: %s", music_name)
            else:
                logger.warning("[选择音乐] 未找到音乐卡片: %s", music_name)

            await asyncio.sleep(2)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[选择音乐] 选择音乐失败: %s", e)


async def _set_hotspot(page, hotspot: str):
        """Search and select hotspot."""
        try:
            # Click hotspot - use text for stability (it's a span, not input)
            hotspot_text = page.get_by_text("点击输入热点词", exact=True)
            await hotspot_text.click()
            await asyncio.sleep(1)

            # Type hotspot keyword
            await page.keyboard.insert_text(hotspot)
            await asyncio.sleep(3)

            # Find matching hotspot option in dropdown
            hotspot_options = page.locator('div[role="option"]:not([aria-disabled="true"])')
            count = await hotspot_options.count()
            # 视频页面可能使用不同的下拉组件，尝试更多选择器
            if count == 0:
                hotspot_options = page.locator('[role="option"]:not([aria-disabled="true"])')
                count = await hotspot_options.count()
            if count == 0:
                # 尝试找任意可见的搜索结果项
                hotspot_options = page.locator('[class*="option"]:not([aria-disabled="true"])')
                count = await hotspot_options.count()
            logger.info("[设置热点] 找到 %d 个热点选项", count)

            # Click the option that matches the search text
            clicked = False
            for i in range(count):
                option = hotspot_options.nth(i)
                option_text = await option.text_content()
                if hotspot in option_text:
                    await option.click()
                    logger.info("[设置热点] 已选择热点: %s (匹配: %s)", hotspot, option_text[:50])
                    clicked = True
                    break

            if not clicked:
                # Fallback: click first option if no exact match
                if count > 0:
                    await hotspot_options.first.click()
                    logger.info("[设置热点] 已选择热点: %s (第一个选项)", hotspot)
                else:
                    logger.warning("[设置热点] 未找到热点: %s, 尝试回车", hotspot)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(1)

            await asyncio.sleep(1)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[设置热点] 设置热点失败: %s", e)


async def _set_tag(page, tag_type: str, tag_value: str, mini_link: str = ""):
        """Set tag with type and value.

        tag_type: 'location' | 'miniapp' | 'gamepad' | 'mark'
        tag_value: the search keyword or link
        mini_link: mini app link (for miniapp type)
        """
        try:
            # Tag type mapping
            type_map = {
                'location': '位置',
                'miniapp': '小程序',
                'gamepad': '游戏手柄',
                'mark': '标记万物',
                'film': '影视演艺',
            }
            type_text = type_map.get(tag_type, '位置')

            # 遍历所有 .semi-select，排除合集那个，找到标签类型选择器
            all_selects = page.locator('div.semi-select')
            select_count = await all_selects.count()
            tag_dropdown = None
            for i in range(select_count):
                sel = all_selects.nth(i)
                text = await sel.text_content()
                if "合集" not in text:
                    tag_dropdown = sel
                    break
            if tag_dropdown is None:
                logger.warning("[设置标签] 未找到标签类型选择器, 跳过")
                return
            await tag_dropdown.click()
            await asyncio.sleep(1)

            # Select tag type
            logger.info("[设置标签] 查找标签类型选项: %s", type_text)
            # 打印下拉中所有可见选项
            all_opts = page.locator('[role="option"]')
            opt_count = await all_opts.count()
            for oi in range(opt_count):
                try:
                    t = await all_opts.nth(oi).text_content()
                    logger.info("[设置标签]   option[%s]: %s", oi, t.strip()[:50] if t else "(空)")
                except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                    pass
            try:
                type_option = page.get_by_role("option", name=type_text)
                await type_option.wait_for(state="visible", timeout=5000)
            except Exception:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
                logger.warning("[设置标签] 未找到标签类型选项: %s", type_text)
                await page.keyboard.press("Escape")
                return
            await type_option.click()
            await asyncio.sleep(1)

            # Helper function to find and click matching option
            async def find_and_click_option(page, tag_value, option_selector='div[role="option"]'):
                options = page.locator(option_selector)
                count = await options.count()
                logger.info("[设置标签] 找到 %d 个选项", count)

                # 先尝试完全匹配
                for i in range(count):
                    option = options.nth(i)
                    option_text = (await option.text_content() or '').strip()
                    if option_text == tag_value:
                        await option.click()
                        logger.info("[设置标签] 已设置标签: %s (完全匹配)", tag_value)
                        return True

                # 再尝试包含匹配
                for i in range(count):
                    option = options.nth(i)
                    option_text = (await option.text_content() or '').strip()
                    if tag_value in option_text:
                        await option.click()
                        logger.info("[设置标签] 已设置标签: %s (包含匹配: %s)", tag_value, option_text[:50])
                        return True

                # Fallback: click first option
                if count > 0:
                    await options.first.click()
                    logger.info("[设置标签] 已设置标签: %s (第一个选项)", tag_value)
                    return True
                return False

            # Based on tag type, handle differently
            if tag_type == 'location':
                # Location: click to activate, then input search keyword
                location_select = page.get_by_text("输入相关位置，让更多人看到你的作品", exact=True)
                if await location_select.count() == 0:
                    location_select = page.get_by_text("输入地理位置", exact=True)
                await location_select.click()
                await asyncio.sleep(1)

                # Use keyboard to type directly since input is already focused
                await page.keyboard.insert_text(tag_value)
                logger.info("[设置标签] 已输入位置关键词: %s", tag_value)
                await asyncio.sleep(5)  # 位置查询可能有延迟，等待更长时间

                # Select matching result
                await find_and_click_option(page, tag_value)

            elif tag_type == 'miniapp':
                # Mini app: click to activate, then paste link
                miniapp_select = page.get_by_text("粘贴抖音小程序链接", exact=True)
                await miniapp_select.click()
                await asyncio.sleep(1)

                # Use mini_link if provided, otherwise use tag_value
                link_to_use = mini_link if mini_link else tag_value
                await page.keyboard.insert_text(tag_value)
                logger.info("[设置标签] 已输入小程序链接: %s", link_to_use)
                await asyncio.sleep(2)

                # Select matching result
                await find_and_click_option(page, tag_value, 'div[role="option"]:not([aria-disabled="true"])')

            elif tag_type == 'gamepad':
                # Game: click the semi-select component by placeholder text
                game_select = page.get_by_text("添加作品同款游戏", exact=True)
                await game_select.click()
                await asyncio.sleep(1)

                # Use keyboard to type directly since input is already focused
                await page.keyboard.insert_text(tag_value)
                logger.info("[设置标签] 已输入游戏标签值: %s", tag_value)
                await asyncio.sleep(3)

                # Find matching game option in dropdown
                game_options = page.locator('div.semi-popover [class*="anchor-game-option"]')
                count = await game_options.count()
                logger.info("[设置标签] 找到 %d 个游戏选项", count)

                # Click the option that matches the search text
                clicked = False
                # 先完全匹配
                for i in range(count):
                    option = game_options.nth(i)
                    option_text = (await option.text_content() or '').strip()
                    if option_text == tag_value:
                        await option.click()
                        logger.info("[设置标签] 已设置游戏标签: %s (完全匹配)", tag_value)
                        clicked = True
                        break
                if not clicked:
                    # 再包含匹配
                    for i in range(count):
                        option = game_options.nth(i)
                        option_text = (await option.text_content() or '').strip()
                        if tag_value in option_text:
                            await option.click()
                            logger.info("[设置标签] 已设置游戏标签: %s (包含: %s)", tag_value, option_text[:50])
                            clicked = True
                            break

            elif tag_type == 'mark':
                # Mark: input search keyword
                mark_input = page.get_by_placeholder("请输入或选择标记的物品")
                await mark_input.click()
                await asyncio.sleep(1)
                await page.keyboard.insert_text(tag_value)
                await asyncio.sleep(3)

                # Find matching mark option in dropdown
                mark_options = page.locator('div.semi-popover [class*="option-"]')
                count = await mark_options.count()
                logger.info("[设置标签] 找到 %d 个标记选项", count)

                # Click the option that matches the search text
                clicked = False
                for i in range(count):
                    option = mark_options.nth(i)
                    option_text = (await option.text_content() or '').strip()
                    if option_text == tag_value:
                        await option.click()
                        logger.info("[设置标签] 已设置标记标签: %s (完全匹配)", tag_value)
                        clicked = True
                        break
                if not clicked:
                    for i in range(count):
                        option = mark_options.nth(i)
                        option_text = (await option.text_content() or '').strip()
                        if tag_value in option_text:
                            await option.click()
                            logger.info("[设置标签] 已设置标记标签: %s (包含: %s)", tag_value, option_text[:50])
                            clicked = True
                            break

            elif tag_type == 'film':
                # Film/Media: input search keyword
                film_input = page.get_by_text("输入IP名称, 如 “少年的你”", exact=True)
                await film_input.click()
                await asyncio.sleep(1)
                await page.keyboard.insert_text(tag_value)
                logger.info("[设置标签] 已输入影视关键词: %s", tag_value)
                await asyncio.sleep(1)
                try:
                    await page.wait_for_selector('[role="option"]', timeout=8000)
                except Exception:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
                    logger.warning("[设置标签] 影视搜索选项未出现")
                film_options = page.locator('[role="option"]')
                count = await film_options.count()
                logger.info("[设置标签] 找到 %d 个影视选项", count)
                for oi in range(count):
                    try:
                        ot = await film_options.nth(oi).text_content()
                        logger.info("[设置标签]   影视option[%s]: %s", oi, (ot or '').strip()[:80])
                    except Exception:  # noqa: S110, BLE001 -- 探测性操作兜底,失败走 fallback
                        pass
                clicked = False
                for i in range(count):
                    option = film_options.nth(i)
                    option_text = (await option.text_content() or '').strip()
                    if option_text == tag_value:
                        await option.click()
                        logger.info("[设置标签] 已设置影视标签: %s (完全匹配)", tag_value)
                        clicked = True
                        break
                if not clicked:
                    for i in range(count):
                        option = film_options.nth(i)
                        option_text = (await option.text_content() or '').strip()
                        if tag_value in option_text:
                            await option.click()
                            logger.info("[设置标签] 已设置影视标签: %s (包含: %s)", tag_value, option_text[:50])
                            clicked = True
                            break

            await asyncio.sleep(1)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[设置标签] 设置标签失败: %s", e)


async def _set_location_tag(page, location: str):
        """Search and select location tag."""
        try:
            # Click location input
            location_input = page.get_by_placeholder("输入相关位置，让更多人看到你的作品")
            if await location_input.count() == 0:
                location_input = page.get_by_placeholder("输入地理位置")
            await location_input.click()
            await asyncio.sleep(1)

            # Type location keyword
            await page.keyboard.type(location)
            await asyncio.sleep(2)

            # Select first result
            location_option = page.locator(
                'div[role="option"]'
            ).first
            if await location_option.count():
                await location_option.click()
                logger.info("[设置位置] 已选择位置: %s", location)
            else:
                logger.warning("[设置位置] 未找到位置: %s", location)
                await page.keyboard.press("Escape")

            await asyncio.sleep(1)
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning("[设置位置] 设置位置失败: %s", e)


async def _set_declaration(page, ai_content: str):
        logger.info("[内容声明] 开始设置内容声明: %s", ai_content)
        try:
            select_box = page.locator(".selectBox-buZRzi").first
            await select_box.wait_for(state="visible", timeout=10000)
            await select_box.click()
            await asyncio.sleep(2)

            clicked = await page.evaluate(
                """(targetText) => {
                const addons = document.querySelectorAll('.semi-radio-addon');
                for (const addon of addons) {
                    if (addon.textContent.trim() === targetText) {
                        addon.closest('label').click();
                        return addon.textContent.trim();
                    }
                }
                return null;
            }""",
                ai_content,
            )

            if clicked:
                logger.info("[内容声明] 已选择声明: %s", clicked)
                await asyncio.sleep(1)

                await page.evaluate(
                    """() => {
                    const btns = document.querySelectorAll('.btnWrapper-LtGF4z button');
                    for (const btn of btns) {
                        if (btn.textContent.trim() === '确定') {
                            btn.disabled = false;
                            btn.className = btn.className.replace('semi-button-disabled', '');
                            btn.click();
                        }
                    }
                }"""
                )
                logger.info("[内容声明] 声明已确认")
            else:
                logger.warning("[内容声明] 未找到声明选项: %s", ai_content)
                close_btn = page.locator(".semi-modal-close")
                if await close_btn.count() > 0:
                    await close_btn.first.click()

            await asyncio.sleep(1)
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录日志,防御性编码
            logger.warning(
                "[内容声明] 声明设置失败 (非阻断): %s", exc
            )
