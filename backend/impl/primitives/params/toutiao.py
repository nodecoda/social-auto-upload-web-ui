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
    "file_input_selector": 'input[type="file"][accept*="image"], input[type="file"]',
    "confirm_selector": "button:has-text('完成裁剪')",
    "close_escape": True,
}
