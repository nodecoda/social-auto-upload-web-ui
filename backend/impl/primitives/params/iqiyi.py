"""iqiyi 平台原语参数表（数据，非逻辑）。来源: impl/iqiyi/platform.py。"""
SCHEDULE = {
    "strategy": "text",
    "enable_kind": "click",
    "enable_selector": '.form-publish-block .el-radio-group label:has-text("定时发布")',
    "input_selector": '.form-publish-block input[placeholder*="选择日期"], .form-publish-block input[placeholder*="时间"]',
    "input_format": "%Y-%m-%d %H:%M",
    "press_enter": True,
}
FILL_TITLE = {
    "strategy": "fill",
    "selector": 'input[placeholder*="标题字数"], .catalog-desc-title-input input[type="text"]',
}
THUMBNAIL = {
    "strategy": "file_chooser",
    "trigger_selector": "div.main-edit-bar",
    "modal_selector": ".image-crop-dialog",
    "orientations": [
        {"key": "portrait", "path_key": "portrait",
         "panel_selector": '.crop-content:not([style*="display: none"])',
         "trigger_selector": ".upload-btn-wrap", "upload_sleep": 3.0},
        {"key": "landscape", "path_key": "landscape",
         "tab_selector": '.tab-item:has-text("4:3")',
         "panel_selector": '.crop-content:not([style*="display: none"])',
         "trigger_selector": ".upload-btn-wrap", "upload_sleep": 2.0},
        {"key": "landscape_169", "path_key": "landscape_169",
         "tab_selector": '.tab-item:has-text("16:9")',
         "panel_selector": '.crop-content:not([style*="display: none"])',
         "trigger_selector": ".upload-btn-wrap", "upload_sleep": 2.0},
    ],
    "confirm_selector": 'button:has-text("完成")',
    "dialog_sleep": 10.0,
}
