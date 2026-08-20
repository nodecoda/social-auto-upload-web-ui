import os
from pathlib import Path

# 打包模式使用 SAU_DATA_DIR，开发模式回退到 repo/data
_data_dir = os.environ.get("SAU_DATA_DIR")
BASE_DIR = Path(_data_dir) if _data_dir else Path(__file__).parent.parent / "data"

# 确保 data/ 及所有必要子目录在启动时就存在
for _sub in ["db", "logs", "cookies", "cookiesFile", "uploads", "thumbnails", "upload_chunks"]:
    (BASE_DIR / _sub).mkdir(parents=True, exist_ok=True)

# 登录（扫码）必须有头模式，验证/发布可用无头模式
LOCAL_CHROME_HEADLESS = True
LOGIN_HEADLESS = False

# 反馈系统对接（凭据必须通过环境变量提供，仓库不含任何密钥；
# 未配置时反馈功能优雅降级为 503，不影响其他功能）
FEEDBACK_API_BASE_URL = os.environ.get('FEEDBACK_API_BASE_URL', 'https://feedback.cjxch.com')
FEEDBACK_APP_KEY = os.environ.get('FEEDBACK_APP_KEY', '')
FEEDBACK_APP_SECRET = os.environ.get('FEEDBACK_APP_SECRET', '')
FEEDBACK_API_TIMEOUT = int(os.environ.get('FEEDBACK_API_TIMEOUT', '10'))

# 平台 id → 中文名 / key 映射(账号导入、发布记录等共用;由 app/ext_api/services 从 conf 导入)
PLATFORM_MAP = {1: "小红书", 2: "视频号", 3: "抖音", 4: "快手", 5: "B站", 6: "百家号", 7: "TikTok", 8: "YouTube", 9: "腾讯视频", 10: "爱奇艺", 11: "微博", 12: "支付宝", 13: "今日头条", 14: "知乎", 15: "CSDN", 16: "VIVO", 17: "微信公众号", 18: "淘宝光合", 19: "京东京麦"}
PLATFORM_ID_TO_KEY = {
    1: 'xiaohongshu', 2: 'channels', 3: 'douyin', 4: 'kuaishou', 5: 'bilibili',
    6: 'baijiahao', 7: 'tiktok', 8: 'youtube', 9: 'tencent_video', 10: 'iqiyi',
    11: 'weibo', 12: 'alipay', 13: 'toutiao', 14: 'zhihu', 15: 'csdn', 16: 'vivo',
    17: 'weixin_gzh', 18: 'taobao_guanghe', 19: 'jingmai', 20: 'jd',
}
