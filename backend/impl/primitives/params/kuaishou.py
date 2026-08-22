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
    "strategy": "click_modal",
    "hover_trigger_selector": "div[class*='default-cover']",
    "hover_sleep": 1.5,
    "trigger_selector": "div[class*='cover-full-editor']",
    "trigger_sleep": 1.0,
    "modal_selector": 'div[role="document"].ant-modal:visible',
    "modal_timeout": 30000,
    "open_tab_selector": "div[class*='header-title-item'] >> nth=1",
    "open_tab_sleep": 1.0,
    # 按视频方向选裁剪比例: 竖版→3:4, 横版→4:3
    "orientations": [
        {"key": "portrait", "path_key": "portrait",
         "tab_selector": "div[class*='_ratio-item']:has(span:text-is('3:4'))"},
        {"key": "landscape", "path_key": "landscape",
         "tab_selector": "div[class*='_ratio-item']:has(span:text-is('4:3'))"},
    ],
    "file_input_selector": 'input[type="file"]',
    "upload_sleep": 3.0,
    "confirm_selector": "button:has-text('确认'), button:has-text('完成')",
}

