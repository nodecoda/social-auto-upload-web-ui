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
    "trigger_sleep": 1.0,
    "open_tab_selector": "text=本地上传",
    "open_tab_sleep": 1.0,
    "orientations": [
        {"key": "default", "path_key": "default",
         "trigger_selector": '.Modal-content [class*="Dropzone"], .Modal-content [class*="dropzone"], .Modal-content [class*="upload"], [role="dialog"] [class*="Dropzone"], [role="dialog"] [class*="upload"]',
         "upload_sleep": 5.0},
    ],
    "confirm_selector": '.Modal-content button:has-text("确认选择"), [role="dialog"] button:has-text("确认选择"), .Modal-content button.Button--primary:has-text("确认"), [role="dialog"] button.Button--primary:has-text("确认")',
    "close_escape": True,
}

