"""vivo 平台原语参数表（数据，非逻辑）。来源: impl/vivo/platform.py::_set_schedule_time。"""
SCHEDULE = {
    "strategy": "text",
    "enable_kind": "radio_check",
    "enable_selector": 'label[role="radio"]:has(span.el-radio__label:has-text("定时发布"))',
    "enable_sleep": 1.5,
    "input_selector": '.el-date-picker__editor-wrap input[placeholder="选择日期"]',
    "input_format": "%Y-%m-%d",
    "input_selector2": '.el-date-picker__editor-wrap input[placeholder="选择时间"]',
    "input_format2": "%H:%M",
    "confirm_selector": ".el-picker-panel__footer button.is-plain",
}
