"""settings 读写测试（SQLite settings 表，conftest 已隔离临时 DB）。"""
import sqlite3

import pytest

from conf import BASE_DIR
import impl.settings as settings_mod


@pytest.fixture(autouse=True)
def _cleanup_keys():
    yield
    conn = sqlite3.connect(str(BASE_DIR / "db" / "database.db"))
    conn.execute("DELETE FROM settings WHERE key IN ('proxyUrl', 'storage')")
    conn.commit()
    conn.close()


def test_write_read_roundtrip_scalar():
    settings_mod.write_setting("t_scalar", "hello")
    assert settings_mod.read_settings()["t_scalar"] == "hello"


def test_write_read_roundtrip_json_structures():
    settings_mod.write_setting("t_dict", {"a": 1, "b": [2, 3]})
    settings_mod.write_setting("t_list", [1, 2, 3])
    data = settings_mod.read_settings()
    assert data["t_dict"] == {"a": 1, "b": [2, 3]}
    assert data["t_list"] == [1, 2, 3]


def test_read_settings_handles_corrupt_json():
    conn = sqlite3.connect(str(BASE_DIR / "db" / "database.db"))
    conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('t_bad', 'not-json{{{', '2026-01-01')")
    conn.commit()
    conn.close()
    # 损坏 JSON 兜底为原始字符串（不抛异常）
    assert settings_mod.read_settings()["t_bad"] == "not-json{{{"


def test_get_proxy_url_default_none():
    assert settings_mod.get_proxy_url() is None


def test_get_proxy_url_returns_value():
    settings_mod.write_setting("proxyUrl", "http://127.0.0.1:10809")
    assert settings_mod.get_proxy_url() == "http://127.0.0.1:10809"


def test_get_storage_config_default_local():
    cfg = settings_mod.get_storage_config()
    assert cfg == {"type": "local", "s3": {}}


def test_get_storage_config_roundtrip():
    settings_mod.write_setting("storage", {"type": "s3", "s3": {"bucket": "b"}})
    assert settings_mod.get_storage_config() == {"type": "s3", "s3": {"bucket": "b"}}


def test_get_storage_config_corrupt_falls_back():
    conn = sqlite3.connect(str(BASE_DIR / "db" / "database.db"))
    conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('storage', 'garbage', '2026-01-01')")
    conn.commit()
    conn.close()
    assert settings_mod.get_storage_config() == {"type": "local", "s3": {}}
