"""原语库日期工具：统一解析发布/定时时间（Phase A1）。

收编 alipay/_dom_ops.py::_parse_schedule_dt（UTC ISO / 本地字符串兼容），
作为全部 14 处定时发布实现的统一入口解析器。
"""
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from util._logger import get_channel_logger

logger = get_channel_logger("primitives")

_PARSABLE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


def parse_publish_dt(publish_dt):
    """解析为本地时区 datetime；不可解析返回 None。

    兼容:
    - datetime 对象: 原样返回
    - int 0: 表示“不设置定时”,返回 None(调用方短路跳过)
    - ISO UTC: ``2026-06-22T13:00:00.000Z`` / ``+08:00``
    - 本地: ``2026-06-22 13:00:00`` / ``2026-06-22 13:00`` / ``2026-06-22T13:00``
    """
    if publish_dt is None:
        return None
    if isinstance(publish_dt, datetime):
        return publish_dt
    if isinstance(publish_dt, int):
        if publish_dt == 0:
            return None
        return None
    if isinstance(publish_dt, str):
        try:
            raw = publish_dt
            is_utc = raw.endswith("Z") or "+00:00" in raw
            raw_clean = raw.replace("+08:00", "").replace("+00:00", "")
            for fmt in _PARSABLE_FORMATS:
                try:
                    dt = datetime.strptime(raw_clean, fmt).replace(
                        tzinfo=UTC if is_utc else ZoneInfo("Asia/Shanghai")
                    )
                    if is_utc:
                        dt = dt.astimezone(ZoneInfo("Asia/Shanghai"))
                    return dt
                except ValueError:
                    continue
        except Exception as exc:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info("[原语] 解析定时时间失败: %s", exc)
    return None
