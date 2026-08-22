"""channels 平台原语参数表（数据，非逻辑）。来源: impl/channels/platform.py。"""
SCHEDULE = {
    "strategy": "calendar",
    "enable_kind": "click",
    "enable_selector": "label",
    "enable_nth": 1,
    "enable_filter_text": "定时",
    "date_trigger_selector": 'input[placeholder="请选择发表时间"]',
    "day_cell_selector": "table.weui-desktop-picker__table a",
    "day_cell_exclude": "weui-desktop-picker__disabled",
    "month_nav": {
        "match": "label_text",
        "label_selector": 'span.weui-desktop-picker__panel__label:has-text("月")',
        "next_selector": "button.weui-desktop-btn__icon__right",
        "limit": 1,
    },
    "time_kind": "input",
    "time_input_selector": 'input[placeholder="请选择时间"]',
    "time_close_selector": "div.input-editor",
}
THUMBNAIL = {
    "strategy": "file_input",
    "file_input_candidates": [
        '.single-cover-uploader-wrap input[type="file"]',
        'input[type="file"][accept*="image"]',
        '.cover-uploader-wrap input[type="file"]',
        'input[type="file"]',
    ],
    "orientations": [
        {"key": "vertical", "path_key": "portrait"},
        {"key": "horizontal", "path_key": "landscape"},
    ],
    "confirm_selector": '.weui-desktop-dialog button:has-text("确定")',
}
