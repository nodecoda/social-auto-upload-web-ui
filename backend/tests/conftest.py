"""共享 pytest fixtures + Flask before_request 清理。

Flask 在装饰器注册时捕获函数引用，monkeypatch `app._ensure_db` 无效。
我们在 autouse fixture 里仅移除 `_ensure_db`（按函数名识别），让 monkeypatch
真的能拦截。其他 before_request 钩子（如 `_before_publish`）保留。

测试数据隔离：所有测试共用独立临时 SAU_DATA_DIR（conf.BASE_DIR / 各 blueprint
的模块级常量在 import 时绑定，因此必须在本文件顶部、任何 app/blueprint/init_db
import 之前设置）。session 级 fixture 初始化完整 schema（init_database），
依赖 DB 表的路由测试（如 /api/tags、/getAccounts）即可直接运行。
"""
import os
import tempfile

_TEST_DATA_DIR = tempfile.mkdtemp(prefix='sau_pytest_')
os.environ['SAU_DATA_DIR'] = _TEST_DATA_DIR

# 反馈测试凭据：conf.py 不再含硬编码默认值，测试环境提供假凭据（真实环境变量优先）
os.environ.setdefault('FEEDBACK_APP_KEY', 'ak_test')
os.environ.setdefault('FEEDBACK_APP_SECRET', 'sk_test')

import pytest


@pytest.fixture(scope='session', autouse=True)
def _init_test_database():
    """全量 schema（tags/account_tags/user_info/upload_*）在共享临时 DB 初始化一次。"""
    from init_db import init_database
    init_database()
    yield


@pytest.fixture(autouse=True)
def _drop_ensure_db_before_request_hook():
    """所有测试默认不走 `_ensure_db`（它会试图 init_database 覆盖测试 schema）。
    其他 before_request 钩子（如 `_before_publish`）保留原状。"""
    from app import app as flask_app
    saved_hooks = list(flask_app.before_request_funcs.get(None, []))
    flask_app.before_request_funcs[None] = [
        fn for fn in saved_hooks
        if getattr(fn, '__name__', None) != '_ensure_db'
    ]
    yield
    flask_app.before_request_funcs[None] = saved_hooks