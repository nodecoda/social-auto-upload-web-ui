"""toutiao 平台原语参数表（数据，非逻辑）。来源: impl/toutiao/platform.py。"""
SCHEDULE = {
    "strategy": "select",
    "enable_kind": "click",
    "enable_selector": 'button.action-footer-btn.timer:has-text("定时发布")',
    "enable_sleep": 2.0,
    "selectors": {
        "day": {"trigger": ".day-select .byte-select-view", "option": ".byte-select-option"},
        "hour": {"trigger": ".hour-select .byte-select-view", "option": ".byte-select-popup-inner .byte-select-option"},
        "minute": {"trigger": ".minute-select .byte-select-view", "option": ".byte-select-popup-inner .byte-select-option"},
    },
}
THUMBNAIL = {
    "strategy": "click_modal",
    "trigger_selector": "div.xigua-poster-editor",
    "trigger_sleep": 2.0,
    "open_tab_selector": "li:has-text('本地上传')",
    "open_tab_sleep": 1.0,
    "file_input_selector": 'input[type="file"][accept*="image"], input[type="file"]',
    "upload_sleep": 2.0,
    # 三级确认: 完成裁剪(可选) → 确定(必点关编辑弹窗) → 二次确认弹窗确定
    "confirm_selector": [
        "button:has-text('完成裁剪')",
        "button:has-text('确定')",
        "xpath=//*[contains(normalize-space(.), '完成后无法继续编辑') and .//button[normalize-space()='取消'] and .//button[normalize-space()='确定'] and not(.//*[contains(normalize-space(.), '完成后无法继续编辑') and .//button[normalize-space()='取消'] and .//button[normalize-space()='确定']])]//div[button[normalize-space()='取消'] and button[normalize-space()='确定']]//button[normalize-space()='确定']",
    ],
    "close_escape": True,
}

