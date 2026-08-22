"""tencent_video 平台原语参数表（数据，非逻辑）。来源: impl/tencent_video/platform.py。"""
SCHEDULE = {
    "strategy": "calendar",
    "enable_kind": "switch",
    "enable_selector": 'button[role="switch"]',
    "date_trigger_selector": 'div[class*="dateTimeSelect"]',
    "date_list_selector": 'div[class*="popupWrap"] div[class*="itemWrap"]',
    "time_kind": "list",
    "hour_list_selector": 'div[class*="popupWrap"] div[class*="itemWrap"]',
    "minute_list_selector": 'div[class*="popupWrap"] div[class*="itemWrap"]',
    "confirm_selector": 'div[class*="popupWrap"] button:has-text("确定")',
}
FILL_TITLE = {
    "strategy": "rich_text",
    "selector": 'div[data-field-name="videos.0.title"]',
}
THUMBNAIL = {
    "strategy": "click_modal",
    "trigger_selector": '[role="button"]:has-text("上传横版封面"), [role="button"]:has-text("替换")',
    "trigger_sleep": 1.0,
    "modal_selector": '[class*="ReactModal"]',
    "file_input_selector": 'input#uploadCoverBtn',
    "upload_sleep": 3.0,
    "confirm_selector": 'button[dt-mpid="上传封面确定"], button:has-text("使用")',
}

