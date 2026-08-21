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
# R4/A3: 唯一真源收敛到 impl.registry 类属性 —— 本模块不再硬编码，改为惰性派生。
# 用模块级 __getattr__ (PEP 562) 兼容既有 `from conf import PLATFORM_MAP` 引用，
# 避免顶层 import registry 造成循环依赖(平台模块反向 import conf.BASE_DIR)与
# 全平台重加载(registry._populate_registry 会 import 20 个平台模块)。
_PLATFORM_MAPS_CACHE: dict = {}


def get_platform_maps():
    """返回 (PLATFORM_MAP, PLATFORM_ID_TO_KEY)，由 registry 类属性惰性派生。

    - PLATFORM_MAP: 注册平台 id → platform_name（1-19，无 20）
    - PLATFORM_ID_TO_KEY: id → platform_key，含 20 → 'jd'（jd 不单独注册，
      由 jingmai 委托实现，但 id→key 映射保留供账号导入/发布记录使用）
    """
    if not _PLATFORM_MAPS_CACHE:
        from impl.registry import _registry
        platform_map = {pid: cls.platform_name for pid, cls in _registry.items()}
        id_to_key = {pid: cls.platform_key for pid, cls in _registry.items()}
        id_to_key[20] = 'jd'
        _PLATFORM_MAPS_CACHE['platform_map'] = platform_map
        _PLATFORM_MAPS_CACHE['id_to_key'] = id_to_key
    return _PLATFORM_MAPS_CACHE['platform_map'], _PLATFORM_MAPS_CACHE['id_to_key']


def __getattr__(name):
    if name in ("PLATFORM_MAP", "PLATFORM_ID_TO_KEY"):
        platform_map, id_to_key = get_platform_maps()
        return platform_map if name == "PLATFORM_MAP" else id_to_key
    raise AttributeError(f"module 'conf' has no attribute {name!r}")
