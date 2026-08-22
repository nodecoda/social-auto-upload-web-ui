"""发布原语库（Phase A1）。

将 20 平台重复的发布交互（定时发布 / 填写标题 / 设置封面 / 上传封面图）
收敛为共享函数库。平台专属选择器/交互参数全部落在 ``params/<platform>.py``
数据表，逻辑函数不出现平台名字符串（A1.1 参数显性化守卫）。
"""
from ._datetime import parse_publish_dt
from .fill_title import fill_title, sanitize_title
from .params import PARAMS, get_params
from .schedule import set_schedule
from .thumbnail import set_thumbnail, upload_cover

__all__ = [
    "PARAMS",
    "fill_title",
    "get_params",
    "parse_publish_dt",
    "sanitize_title",
    "set_schedule",
    "set_thumbnail",
    "upload_cover",
]
