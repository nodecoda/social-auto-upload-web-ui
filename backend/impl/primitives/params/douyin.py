"""douyin 平台原语参数表（数据，非逻辑）。来源: impl/douyin/_dom_ops.py。"""
SCHEDULE = {
    "strategy": "calendar",
    "enable_kind": "click",
    "enable_selector": "[class^='radio']:has-text('定时发布')",
    "date_trigger_selector": '.semi-input[placeholder="日期和时间"]',
    "day_cell_selector": ".semi-datepicker-day:not(.semi-datepicker-day-disabled)",
    "day_cell_title": True,
    "time_kind": "wheel",
    "time_switch_selector": ".semi-datepicker-switch-time",
    "hour_wheel_selector": ".semi-scrolllist-item-wheel.undefined-list-hour li",
    "minute_wheel_selector": ".semi-scrolllist-item-wheel.undefined-list-minute li",
    "confirm_selector": '.semi-popover button:has-text("确定")',
    "confirm_enter_fallback": True,
}
THUMBNAIL = {
    "strategy": "click_modal",
    "trigger_selector": 'text="选择封面"',
    "modal_selector": 'div[id*="creator-content-modal"]',
    "tab_scope_selector": "div[class*='steps'] div",
    "file_input_selector": "div[class^='semi-upload upload'] >> input.semi-upload-hidden-input",
    "orientations": [
        {"key": "portrait", "path_key": "portrait", "tab_text": "竖"},
        {"key": "landscape", "path_key": "landscape", "tab_text": "横"},
    ],
    "confirm_selector": 'button:visible:has-text("完成")',
    "upload_sleep": 2.0,
}
