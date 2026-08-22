"""平台原语参数注册表（Phase A1.1 参数显性化守卫）。

每个平台一个数据文件（数据，非逻辑）：只含该平台真实存在的原语参数。
逻辑函数（schedule.py / fill_title.py / thumbnail.py）不出现平台名字符串，
一律通过本注册表取值。
"""
from . import (
    alipay,
    bilibili,
    channels,
    csdn,
    douyin,
    iqiyi,
    jd,
    kuaishou,
    taobao_guanghe,
    tencent_video,
    tiktok,
    toutiao,
    vivo,
    xiaohongshu,
    zhihu,
)

# 平台 → {原语: 参数} 注册表。缺省为空 dict（该平台无对应原语）。
_PARAMS_SOURCE = {
    "alipay": alipay,
    "bilibili": bilibili,
    "channels": channels,
    "csdn": csdn,
    "douyin": douyin,
    "iqiyi": iqiyi,
    "jd": jd,
    "kuaishou": kuaishou,
    "taobao_guanghe": taobao_guanghe,
    "tencent_video": tencent_video,
    "tiktok": tiktok,
    "toutiao": toutiao,
    "vivo": vivo,
    "xiaohongshu": xiaohongshu,
    "zhihu": zhihu,
}

PARAMS = {
    name: {
        key: getattr(mod, key)
        for key in ("SCHEDULE", "FILL_TITLE", "THUMBNAIL")
        if hasattr(mod, key)
    }
    for name, mod in _PARAMS_SOURCE.items()
}


def get_params(platform: str, primitive: str):
    """取平台原语参数；不存在返回 None（调用方跳过）。"""
    return PARAMS.get(platform, {}).get(primitive)
