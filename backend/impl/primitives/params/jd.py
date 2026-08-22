"""jd 平台原语参数表（数据，非逻辑）。来源: impl/jd/platform.py::_set_schedule_time/_fill_title。

京东发布表单在微前端 iframe(self.frame) 内，调用时传 frame。
"""
SCHEDULE = {
    "strategy": "text",
    "enable_kind": "click",
    "enable_selector": ".jd-radio-wrapper input[value='2']",
    "input_selector": ".pro-radio-extra input[placeholder='请选择日期'], .pro-radio-extra input",
    "input_format": "%Y-%m-%d %H:%M",
    "confirm_selector": ".jd-picker-ok .jd-btn-primary",
    "confirm_selector_fallback": ".jd-picker-ok button",
}
FILL_TITLE = {
    "strategy": "fill",
    "selector": "input#title",
    "max_len": 27,
}
