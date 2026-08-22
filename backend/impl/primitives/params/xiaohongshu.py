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
    "trigger_selector": "div.operator.pointer",
    "modal_selector": 'div[class*="upload-modal"]',
    "file_input_selector": 'input[type=file][accept*="image"]',
}
