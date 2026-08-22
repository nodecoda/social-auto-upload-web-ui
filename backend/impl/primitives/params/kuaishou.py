"""kuaishou 平台原语参数表（数据，非逻辑）。来源: impl/kuaishou/platform.py。"""
SCHEDULE = {
    "strategy": "text",
    "enable_kind": "click",
    "enable_selector": 'label:text("发布时间") + div .ant-radio-input',
    "enable_nth": 1,
    "input_selector": 'div.ant-picker-input input[placeholder="选择日期时间"]',
    "input_method": "clear_and_type",
    "input_format": "%Y-%m-%d %H:%M:%S",
    "press_enter": True,
}
THUMBNAIL = {
    "strategy": "hover_modal",
    "trigger_selector": "div[class*='default-cover']",
    "trigger_sleep": 1.5,
    "file_input_selector": 'input[type="file"][accept*="image"]',
    "confirm_selector": 'button:has-text("确定")',
}
