"""csdn 平台原语参数表（数据，非逻辑）。来源: impl/csdn/platform.py。"""
FILL_TITLE = {
    "strategy": "fill",
    "selector": '#title.el-input__inner, input#title, .Management-content input.el-input__inner',
    "max_len": 30,
}
THUMBNAIL = {
    "strategy": "file_input",
    "file_input_selector": '.essential-uploader input[type="file"][accept*="image"], input[type="file"]',
    "upload_sleep": 2.0,
    "confirm_selector": '.dialog-footer .el-button--primary:has-text("确认")',
    "close_escape": True,
}

