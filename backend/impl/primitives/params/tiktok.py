"""tiktok 平台原语参数表（数据，非逻辑）。来源: impl/tiktok/platform.py::_set_schedule_time。"""
SCHEDULE = {
    "strategy": "calendar",
    "enable_kind": "click",
    "enable_selector": 'label.Radio__root:has-text("预约发布")',
    "date_trigger_selector": "div.TUXFormField.TUXTextInput input.TUXTextInputCore-input",
    "date_trigger_nth": 1,
    "day_cell_selector": "span.day.valid",
    "month_nav": {
        "match": "cn_month",
        "label_selector": "span.month-title",
        "next_selector": "span.arrow",
        "limit": 1,
    },
    "time_kind": "left_right",
    "time_trigger_selector": "div.TUXFormField.TUXTextInput input.TUXTextInputCore-input",
    "time_trigger_nth": 0,
    "hour_left_selector": "span.tiktok-timepicker-left",
    "minute_right_selector": "span.tiktok-timepicker-right",
    "close_escape": True,
}
