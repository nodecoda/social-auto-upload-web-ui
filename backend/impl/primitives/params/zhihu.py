"""zhihu 平台原语参数表（数据，非逻辑）。来源: impl/zhihu/platform.py。"""
SCHEDULE = {
    "strategy": "calendar",
    "enable_kind": "checkbox",
    "enable_selector": '.VideoUploadForm-scheduledPublish--switch input[type="checkbox"], .VideoUploadForm-scheduledPublish label',
    "date_trigger_selector": ".DatePicker-Button",
    "day_cell_selector": "td.Calendar-day:not(.is-disabled):not(.is-not-this-month)",
    "month_nav": {
        "match": "ym_title",
        "label_selector": ".Calendar-topToolDate",
        "next_selector": ".Calendar-topToolButton--nextMonth",
        "prev_selector": ".Calendar-topToolButton--prevMonth",
        "limit": 24,
    },
    "time_kind": "popover",
    "hour_trigger_selector": '.DateTimePicker .Popover:has(.DatePicker) ~ .Popover .Select-button, .DateTimePicker button[role="combobox"]',
    "hour_trigger_fallback_selector": '.DateTimePicker button[role="combobox"]',
    "hour_option_selector": '.DateTimePicker-selectList .Select-option:not([disabled])',
    "minute_trigger_selector": '.DateTimePicker button[role="combobox"]',
    "minute_option_selector": '.DateTimePicker-selectList .Select-option:not([disabled])',
    "close_escape": True,
}
FILL_TITLE = {
    "strategy": "fill",
    "selector": 'textarea[name="title"], textarea[placeholder*="标题"], .TitleArea textarea',
    "max_len": 50,
}
THUMBNAIL = {
    "strategy": "file_chooser",
    "trigger_selector": '.VideoUploadForm-imageEditButton, [class*="VideoUploadForm-imageEditButton"]',
    "confirm_selector": 'button:has-text("保存"), [class*="confirm"]',
    "close_escape": True,
}
