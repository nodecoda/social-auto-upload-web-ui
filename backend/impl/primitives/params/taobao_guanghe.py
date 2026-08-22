"""taobao_guanghe 平台原语参数表（数据，非逻辑）。来源: impl/taobao_guanghe/platform.py。"""
SCHEDULE = {
    "strategy": "calendar",
    "enable_kind": "js_radio",
    "enable_label_text": "定时发布",
    "enable_picker_selector": "#date-picker",
    "date_trigger_selector": "#date-picker input",
    "day_cell_selector": ".next-calendar-cell",
    "day_cell_title": True,
    "day_cell_title_format": "%Y/%m/%d",
    "time_kind": "panel",
    "time_trigger_selector": '.next-date-picker-panel-input input[placeholder="HH:mm"]',
    "hour_menu_selector": ".next-time-picker-menu-hour .next-time-picker-menu-item",
    "minute_menu_selector": ".next-time-picker-menu-minute .next-time-picker-menu-item",
    "confirm_selector": '.next-date-picker-panel button:has-text("确定"), .next-btn-primary:has-text("确定")',
}
FILL_TITLE = {
    "strategy": "fill",
    "selector": 'input[placeholder*="标题"], input[maxlength="30"]',
    "max_len": 30,
}
