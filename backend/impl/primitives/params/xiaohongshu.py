"""xiaohongshu 平台原语参数表（数据，非逻辑）。来源: impl/xiaohongshu/platform.py。"""
SCHEDULE = {
    "strategy": "text",
    "enable_kind": "click",
    "enable_selector": ".custom-switch-card",
    "enable_filter_text": "定时发布",
    "enable_child_selector": ".d-switch",
    "input_selector": ".d-datepicker-input-filter input.d-text",
    "input_format": "%Y-%m-%d %H:%M",
}
FILL_TITLE = {
    "strategy": "fill",
    "selector": 'input[placeholder*="填写标题"]',
    "max_len": 20,
}
THUMBNAIL = {
    "strategy": "click_modal",
    "hover_trigger_selector": 'div[style*="background-image"]',
    "hover_sleep": 1.0,
    "trigger_selector": "div.operator.pointer",
    "trigger_sleep": 3.0,
    "modal_selector": "div.d-modal.cover-modal, div.cover-modal, div[class*='cover-modal'], div.d-modal",
    "file_input_selector": 'input[type=file][accept*="image"]',
    "upload_sleep": 3.0,
    "confirm_selector": "button.mojito-button:has-text('确定'), button:has-text('确定'), .d-modal-footer button:has-text('确定')",
}

