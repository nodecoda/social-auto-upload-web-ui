# mypy: ignore-errors
# 运行时注入 utils.files_times fake, 类型不可静态解析
"""impl/_utils 调度与账号名契约测试（T26）。

- parse_schedule_time: 全平台共享的定时解析核心
  (UTC ISO→东八 / 本地直接标注 / 解析失败落回自动生成 / 未开启→[0]*n)
- _parse_vivo_count: VIVO 数字显示格式解析 ('1.2万'/'1.2w'/'亿' → int)
- get_account_name_by_cookie_file: cookie 文件名 → user_info.userName
"""
import sqlite3
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl._utils import (
    _parse_vivo_count,
    get_account_name_by_cookie_file,
    parse_schedule_time,
)

# utils.files_times 是运行时外部依赖(仓库无此模块), 注入 fake 供 patch 使用
_pkg = types.ModuleType('utils')
_ft = types.ModuleType('utils.files_times')
_ft.generate_schedule_time_next_day = lambda *a, **k: None
_pkg.files_times = _ft
sys.modules.setdefault('utils', _pkg)
sys.modules.setdefault('utils.files_times', _ft)

_CN = ZoneInfo("Asia/Shanghai")
_NEXT_DAY = datetime(2026, 8, 22, 9, 0, tzinfo=_CN)


def _auto_gen():
    return _NEXT_DAY


# ── parse_schedule_time: 用户指定时间 ───────────────────────────────────────

class TestParseUserSpecifiedTime:
    def test_utc_iso_millis(self):
        result = parse_schedule_time("2026-05-16T13:00:00.000Z", 1, True, 1, None, 0)
        assert result == [datetime(2026, 5, 16, 21, 0, tzinfo=_CN)]

    def test_utc_iso_seconds(self):
        result = parse_schedule_time("2026-05-16T13:00:00Z", 1, True, 1, None, 0)
        assert result == [datetime(2026, 5, 16, 21, 0, tzinfo=_CN)]

    def test_utc_with_plus_zero_offset(self):
        result = parse_schedule_time("2026-05-16T13:00:00+00:00", 1, True, 1, None, 0)
        assert result == [datetime(2026, 5, 16, 21, 0, tzinfo=_CN)]

    def test_plus_eight_offset_stripped_no_conversion(self):
        """+08:00 后缀剥离, 按本地东八直接标注(无偏移转换)。"""
        result = parse_schedule_time("2026-05-16T13:00:00+08:00", 1, True, 1, None, 0)
        assert result == [datetime(2026, 5, 16, 13, 0, tzinfo=_CN)]

    def test_local_iso_no_zone(self):
        result = parse_schedule_time("2026-05-16T13:00:00", 1, True, 1, None, 0)
        assert result == [datetime(2026, 5, 16, 13, 0, tzinfo=_CN)]

    def test_local_space_format(self):
        result = parse_schedule_time("2026-05-16 13:00:00", 1, True, 1, None, 0)
        assert result == [datetime(2026, 5, 16, 13, 0, tzinfo=_CN)]

    def test_local_minutes_only(self):
        result = parse_schedule_time("2026-05-16 13:00", 1, True, 1, None, 0)
        assert result == [datetime(2026, 5, 16, 13, 0, tzinfo=_CN)]

    def test_repeated_per_file(self):
        result = parse_schedule_time("2026-05-16T13:00:00Z", 3, True, 1, None, 0)
        assert len(result) == 3
        assert result == [datetime(2026, 5, 16, 21, 0, tzinfo=_CN)] * 3

    def test_parse_failure_falls_back_to_auto(self):
        with patch('utils.files_times.generate_schedule_time_next_day', return_value=_NEXT_DAY) as gen:
            result = parse_schedule_time("not-a-date", 2, True, 2, ["09:00"], 1)
        gen.assert_called_once_with(2, 2, ["09:00"], 1)
        assert result == _NEXT_DAY

    def test_strptime_exception_falls_back_to_auto(self):
        fake_dt = MagicMock()
        fake_dt.strptime = MagicMock(side_effect=ValueError("boom"))
        with patch('impl._utils.datetime', fake_dt), \
             patch('utils.files_times.generate_schedule_time_next_day', return_value=_NEXT_DAY) as gen:
            result = parse_schedule_time("2026-05-16T13:00:00Z", 1, True, 1, None, 0)
        gen.assert_called_once()
        assert result == _NEXT_DAY


# ── parse_schedule_time: 未开启 / 自动生成 ──────────────────────────────────

class TestParseAutoGenerate:
    def test_timer_disabled_returns_zeros(self):
        result = parse_schedule_time("2026-05-16 13:00", 3, False, 1, None, 0)
        assert result == [0, 0, 0]

    def test_timer_enabled_no_time_auto_generates(self):
        with patch('utils.files_times.generate_schedule_time_next_day', return_value=_NEXT_DAY) as gen:
            result = parse_schedule_time("", 2, True, 2, ["09:00"], 1)
        gen.assert_called_once_with(2, 2, ["09:00"], 1)
        assert result == _NEXT_DAY

    def test_timer_enabled_empty_time_auto_generates(self):
        with patch('utils.files_times.generate_schedule_time_next_day', return_value=_NEXT_DAY) as gen:
            result = parse_schedule_time("   ", 1, True, 1, None, 0)
        gen.assert_called_once()
        assert result == _NEXT_DAY


# ── _parse_vivo_count ───────────────────────────────────────────────────────

class TestParseVivoCount:
    def test_wan_suffix(self):
        assert _parse_vivo_count('1.2万') == 12000

    def test_w_suffix(self):
        assert _parse_vivo_count('1.2w') == 12000

    def test_uppercase_w_suffix(self):
        assert _parse_vivo_count('1.2W') == 12000

    def test_yi_suffix(self):
        assert _parse_vivo_count('2.5亿') == 250000000

    def test_plain_number(self):
        assert _parse_vivo_count('12345') == 12345

    def test_whitespace_trimmed(self):
        assert _parse_vivo_count(' 1.5万 ') == 15000

    def test_empty_returns_zero(self):
        assert _parse_vivo_count('') == 0

    def test_none_returns_zero(self):
        assert _parse_vivo_count(None) == 0

    def test_invalid_returns_zero(self):
        assert _parse_vivo_count('abc') == 0

    def test_decimal_plain(self):
        assert _parse_vivo_count('12.5') == 12


# ── get_account_name_by_cookie_file ─────────────────────────────────────────

class TestGetAccountNameByCookieFile:
    def test_empty_filename_returns_empty(self):
        assert get_account_name_by_cookie_file('') == ''

    def test_none_filename_returns_empty(self):
        assert get_account_name_by_cookie_file(None) == ''

    def test_found_returns_nickname(self):
        cookie = 't26-uuid-001.json'
        db_path = Path(BASE_DIR / "db" / "database.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO user_info (type, filePath, userName) VALUES (?, ?, ?)",
                (1, cookie, '测试昵称'),
            )
        assert get_account_name_by_cookie_file(cookie) == '测试昵称'

    def test_not_found_returns_empty(self):
        assert get_account_name_by_cookie_file('no-such-cookie.json') == ''

    def test_db_error_returns_empty_and_logs(self):
        with patch('impl._utils.logger') as logger, \
             patch('impl._utils.sqlite3.connect', side_effect=sqlite3.OperationalError("locked")):
            assert get_account_name_by_cookie_file('x.json') == ''
            assert any(
                c.args[0] == '查询账号昵称失败 (%s): %s'
                for c in logger.warning.call_args_list
            )
