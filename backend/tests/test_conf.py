"""conf.py 环境变量驱动的配置加载测试。

conftest 已在 import 前设置 SAU_DATA_DIR 指向临时目录；
本模块通过 importlib.reload 重新执行 conf.py 验证不同环境变量下的行为，
并在 teardown 恢复原始环境 + 重新加载 conf，避免污染其他测试。
"""
import importlib
import os

import pytest

import conf

_ORIG_ENV = {k: v for k, v in os.environ.items() if k.startswith(('SAU_', 'FEEDBACK_'))}


@pytest.fixture(autouse=True)
def _restore_conf(monkeypatch):
    yield
    # 恢复原始 SAU_/FEEDBACK_ 环境变量并重载 conf，保证其他模块所见一致
    for k in list(os.environ):
        if k.startswith(('SAU_', 'FEEDBACK_')):
            monkeypatch.delenv(k, raising=False)
    for k, v in _ORIG_ENV.items():
        monkeypatch.setenv(k, v)
    importlib.reload(conf)


def _reload(monkeypatch, env: dict):
    for k in list(os.environ):
        if k.startswith(('SAU_', 'FEEDBACK_')):
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return importlib.reload(conf)


def test_default_config_points_to_repo_data(monkeypatch):
    c = _reload(monkeypatch, {})
    assert c.BASE_DIR.name == 'data'
    assert c.FEEDBACK_API_BASE_URL == 'https://feedback.cjxch.com'
    assert c.FEEDBACK_APP_KEY == ''
    assert c.FEEDBACK_APP_SECRET == ''
    assert c.FEEDBACK_API_TIMEOUT == 10


def test_sau_data_dir_overrides_base_dir(monkeypatch, tmp_path):
    target = tmp_path / 'custom_data'
    c = _reload(monkeypatch, {'SAU_DATA_DIR': str(target)})
    assert c.BASE_DIR == target


def test_sau_data_dir_creates_required_subdirs(monkeypatch, tmp_path):
    target = tmp_path / 'nested' / 'data'
    c = _reload(monkeypatch, {'SAU_DATA_DIR': str(target)})
    for sub in ['db', 'logs', 'cookies', 'cookiesFile', 'uploads', 'thumbnails', 'upload_chunks']:
        assert (c.BASE_DIR / sub).is_dir(), f'missing {sub}'


def test_feedback_credentials_from_env(monkeypatch):
    c = _reload(monkeypatch, {
        'FEEDBACK_APP_KEY': 'ak_env',
        'FEEDBACK_APP_SECRET': 'sk_env',
        'FEEDBACK_API_TIMEOUT': '25',
    })
    assert c.FEEDBACK_APP_KEY == 'ak_env'
    assert c.FEEDBACK_APP_SECRET == 'sk_env'
    assert c.FEEDBACK_API_TIMEOUT == 25


def test_headless_flags_are_stable(monkeypatch):
    c = _reload(monkeypatch, {})
    # 登录扫码必须有头模式，验证/发布可用无头模式（防误改）
    assert c.LOCAL_CHROME_HEADLESS is True
    assert c.LOGIN_HEADLESS is False
