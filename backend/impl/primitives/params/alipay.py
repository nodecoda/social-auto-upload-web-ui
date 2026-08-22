"""alipay 平台原语参数表（数据，非逻辑）。来源: impl/alipay/_dom_ops.py::_set_schedule_time。"""
SCHEDULE = {
    "strategy": "text",
    "enable_kind": "radio_label",
    "enable_selector": 'input[name="publishType"][value="regularly"]',
    "enable_sleep": 0.8,
    "input_selector": "input[id$='_scheduleTime']",
    "input_method": "type",
    "input_delay": 50,
    "confirm_role": ("button", "确 定"),
    "confirm_enter_fallback": True,
}
