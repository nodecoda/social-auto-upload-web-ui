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
    "trigger_candidates": [
        '[data-reporter-id="80"] .cover-empty-pill .add-text',
        '[data-reporter-id="80"] .cover-empty-pill .add-icon',
        '.cover-empty-pill .add-text',
        '.cover-empty-pill .add-icon',
        '.cover-empty-pill',
        'div[class*="cover-empty"]:has-text("封面")',
        'span[class*="edit-text"]:has-text("封面设置")',
        'span:has-text("封面设置")',
        'button:has-text("封面设置")',
        'div.cover-item',
        '.cover-item',
        'div[class*="cover"] >> text=选择封面',
    ],
    "trigger_sleep": 1.0,
    "modal_selector": (
        "div.bcc-dialog:has-text('封面制作'), div.bcc-dialog:has-text('封面设置'), "
        "div.bcc-dialog, div[class*='cover-editor']:visible, "
        "div[class*='cover-dialog']:visible, div[class*='upload-cover']:visible"
    ),
    "file_input_selector": '.cover-upload input[type="file"], input[accept*="image"]',
    "upload_sleep": 3.0,
    # 两级确认: 先点「完成」(div.button.submit), 再点弹窗内确认按钮
    "confirm_selector": ["div.button.submit", "button.bcc-button--primary"],
    "close_escape": True,
}

