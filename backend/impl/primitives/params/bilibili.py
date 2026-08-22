"""bilibili 平台原语参数表（数据，非逻辑）。来源: impl/bilibili/platform.py。"""
SCHEDULE = {
    "strategy": "calendar",
    "enable_kind": "click",
    "enable_selector": ".switch-container",
    "date_trigger_selector": "div.date-picker-date",
    "day_cell_selector": "div.date-picker-body-item.date-item",
    "day_cell_exclude": "date-item-disabled",
    "time_kind": "panel",
    "panel_selector": ".time-picker-panel-select-wrp",
    "panel_item_selector": "span.time-picker-panel-select-item",
    "close_escape": True,
}
FILL_TITLE = {
    "strategy": "fill",
    "selector": 'input[placeholder*="标题"], input[placeholder*="Title"], .video-title input, [class*="title"] input[type="text"]',
    "max_len": 80,
    "sanitize": True,
}
THUMBNAIL = {
    "strategy": "click_modal",
    "direct_file_first": True,
    "trigger_selector": 'button:has-text("编辑封面"), [class*="cover"]:has-text("编辑封面")',
    "file_input_selector": '.cover-upload input[type="file"], input[accept*="image"]',
    "confirm_selector": "div.button.submit",
    "confirm_selector2": "button.bcc-button--primary",
    "upload_sleep": 3.0,
    "close_escape": True,
}
