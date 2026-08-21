"""账号管理域业务路由契约测试（T4，account_bp 剩余面）。

目标：account_bp 从 39% 拉高——覆盖此前未测的业务路由：
getValidAccounts / updateUserinfo / checkAccount / syncProfile / openCreatorCenter /
login(SSE) / platforms/import-supported / importAccount(启动+stream) /
uploadCookie 成功路径 / downloadCookie 成功路径 / deleteAccount 删 cookie 文件分支。

手法：mock `blueprints.account_bp.get_platform` 返回假平台对象（check_cookie /
sync_profile / open_creator_center / login / import_cookie 均为同步假实现），
数据库用 conftest 的临时 SAU_DATA_DIR（session 级 init_database），
cookie 文件落在 BASE_DIR/cookiesFile 下，测试内自清理。
"""
import io
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from app import app
from blueprints.account_bp import BASE_DIR, DB_PATH


class _FakePlatform:
    """同步假平台：满足 check_cookie / sync_profile / open_creator_center / login / import_cookie 签名。"""

    platform_name = '测试平台'
    platform_key = 'fake'

    def __init__(self, check_result=True, profile=None, supports_cookie_import=True):
        self._check = check_result
        self._profile = profile
        self.supports_cookie_import = supports_cookie_import
        self.login_called = False

    async def check_cookie(self, *args, **kwargs):
        return self._check

    async def sync_profile(self, *args, **kwargs):
        return self._profile

    async def open_creator_center(self, *args, **kwargs):
        return None

    async def login(self, id_str, status_queue, account_id=None):
        self.login_called = True
        status_queue.put('200')

    async def import_cookie(self, cookie_str, status_queue, account_id=None):
        status_queue.put(json.dumps({'status': '200', 'step': 99, 'msg': 'ok'}))


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _insert_account(conn, account_id, platform_type=3, file_path='t4_cookie.json', user_name='测试'):
    conn.execute(
        'INSERT OR REPLACE INTO user_info (id, type, filePath, userName) VALUES (?, ?, ?, ?)',
        (account_id, platform_type, file_path, user_name),
    )
    conn.commit()


def _cleanup_account(account_id, file_path=None):
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute('DELETE FROM user_info WHERE id = ?', (account_id,))
        conn.execute('DELETE FROM account_tags WHERE account_id = ?', (account_id,))
        conn.commit()
    finally:
        conn.close()
    if file_path:
        p = Path(BASE_DIR / 'cookiesFile' / file_path)
        if p.exists():
            p.unlink()


# ── getValidAccounts ─────────────────────────────────────────────────────────

def test_get_valid_accounts_marks_valid(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 901, platform_type=3, file_path='t4_v1.json')
    try:
        fake = _FakePlatform(check_result=True)
        with patch('blueprints.account_bp.get_platform', return_value=fake):
            r = client.get('/getValidAccounts')
        body = r.get_json()
        assert body['code'] == 200
        conn = sqlite3.connect(str(DB_PATH))
        try:
            status = conn.execute('SELECT status FROM user_info WHERE id = 901').fetchone()[0]
        finally:
            conn.close()
        assert status == 1
    finally:
        _cleanup_account(901, 't4_v1.json')


def test_get_valid_accounts_invalid_cookie_sets_zero(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 902, platform_type=3, file_path='t4_v2.json')
    try:
        fake = _FakePlatform(check_result=False)
        with patch('blueprints.account_bp.get_platform', return_value=fake):
            r = client.get('/getValidAccounts')
        assert r.get_json()['code'] == 200
        conn = sqlite3.connect(str(DB_PATH))
        try:
            status = conn.execute('SELECT status FROM user_info WHERE id = 902').fetchone()[0]
        finally:
            conn.close()
        assert status == 0
    finally:
        _cleanup_account(902, 't4_v2.json')


# ── updateUserinfo ───────────────────────────────────────────────────────────

def test_update_userinfo_success(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 903, platform_type=3)
    try:
        r = client.post('/updateUserinfo', json={'id': 903, 'type': 4, 'userName': '新昵称'})
        assert r.get_json()['code'] == 200
        conn = sqlite3.connect(str(DB_PATH))
        try:
            row = conn.execute('SELECT type, userName FROM user_info WHERE id = 903').fetchone()
        finally:
            conn.close()
        assert row == (4, '新昵称')
    finally:
        _cleanup_account(903)


def test_update_userinfo_db_error_500(client):
    with patch('blueprints.account_bp.sqlite3.connect', side_effect=RuntimeError('boom')):
        r = client.post('/updateUserinfo', json={'id': 1, 'type': 3, 'userName': 'x'})
    body = r.get_json()
    assert body['code'] == 500
    assert body['msg'] == 'update failed!'


# ── checkAccount ─────────────────────────────────────────────────────────────

def test_check_account_invalid_id_400(client):
    r = client.get('/checkAccount?id=abc')
    body = r.get_json()
    assert body['code'] == 400
    assert '无效的账号ID' in body['msg']


def test_check_account_not_found_404(client):
    r = client.get('/checkAccount?id=999991')
    assert r.get_json()['code'] == 404


def test_check_account_unsupported_platform_400(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 904, platform_type=99)
    try:
        with patch('blueprints.account_bp.get_platform', return_value=None):
            r = client.get('/checkAccount?id=904')
        assert r.get_json()['code'] == 400
    finally:
        _cleanup_account(904)


def test_check_account_valid_200(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 905, platform_type=3, file_path='t4_c.json')
    try:
        with patch('blueprints.account_bp.get_platform', return_value=_FakePlatform(check_result=True)):
            r = client.get('/checkAccount?id=905')
        body = r.get_json()
        assert body['code'] == 200
        assert body['data']['valid'] is True
        assert body['data']['status'] == 1
    finally:
        _cleanup_account(905, 't4_c.json')


def test_check_account_invalid_200(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 906, platform_type=3, file_path='t4_c2.json')
    try:
        with patch('blueprints.account_bp.get_platform', return_value=_FakePlatform(check_result=False)):
            r = client.get('/checkAccount?id=906')
        body = r.get_json()
        assert body['code'] == 200
        assert body['data']['valid'] is False
        assert body['data']['status'] == 0
    finally:
        _cleanup_account(906, 't4_c2.json')


# ── syncProfile ──────────────────────────────────────────────────────────────

def test_sync_profile_missing_id_400(client):
    r = client.post('/syncProfile', json={})
    assert r.get_json()['code'] == 400


def test_sync_profile_not_found_404(client):
    r = client.post('/syncProfile', json={'id': 999992})
    assert r.get_json()['code'] == 404


def test_sync_profile_unsupported_platform_400(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 907, platform_type=99)
    try:
        with patch('blueprints.account_bp.get_platform', return_value=None):
            r = client.post('/syncProfile', json={'id': 907})
        assert r.get_json()['code'] == 400
    finally:
        _cleanup_account(907)


def test_sync_profile_dict_result_updates_db(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 908, platform_type=3, user_name='旧名')
    try:
        fake = _FakePlatform(profile={'name': '新名', 'avatar': 'a.png', 'stats': [1, 2]})
        with patch('blueprints.account_bp.get_platform', return_value=fake):
            r = client.post('/syncProfile', json={'id': 908})
        body = r.get_json()
        assert body['code'] == 200
        assert body['data']['name'] == '新名'
        assert body['data']['stats'] == [1, 2]
        conn = sqlite3.connect(str(DB_PATH))
        try:
            row = conn.execute('SELECT userName, avatar FROM user_info WHERE id = 908').fetchone()
        finally:
            conn.close()
        assert row == ('新名', 'a.png')
    finally:
        _cleanup_account(908)


def test_sync_profile_tuple_result_stats_empty(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 909, platform_type=3)
    try:
        fake = _FakePlatform(profile=('名', 'av.png'))
        with patch('blueprints.account_bp.get_platform', return_value=fake):
            r = client.post('/syncProfile', json={'id': 909})
        body = r.get_json()
        assert body['data']['name'] == '名'
        assert body['data']['stats'] == []
    finally:
        _cleanup_account(909)


def test_sync_profile_empty_result_no_update(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 910, platform_type=3, user_name='保持')
    try:
        fake = _FakePlatform(profile=None)
        with patch('blueprints.account_bp.get_platform', return_value=fake):
            r = client.post('/syncProfile', json={'id': 910})
        body = r.get_json()
        assert body['data'] == {'name': '', 'avatar': '', 'stats': []}
        conn = sqlite3.connect(str(DB_PATH))
        try:
            user_name = conn.execute('SELECT userName FROM user_info WHERE id = 910').fetchone()[0]
        finally:
            conn.close()
        assert user_name == '保持'
    finally:
        _cleanup_account(910)


# ── openCreatorCenter ────────────────────────────────────────────────────────

def test_open_creator_center_missing_id_400(client):
    r = client.post('/openCreatorCenter', json={})
    assert r.get_json()['code'] == 400


def test_open_creator_center_not_found_404(client):
    r = client.post('/openCreatorCenter', json={'id': 999993})
    assert r.get_json()['code'] == 404


def test_open_creator_center_unsupported_400(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 911, platform_type=99)
    try:
        with patch('blueprints.account_bp.get_platform', return_value=None):
            r = client.post('/openCreatorCenter', json={'id': 911})
        assert r.get_json()['code'] == 400
    finally:
        _cleanup_account(911)


def test_open_creator_center_starts_thread_200(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 912, platform_type=3, file_path='t4_o.json')
    try:
        with patch('blueprints.account_bp.get_platform', return_value=_FakePlatform()):
            r = client.post('/openCreatorCenter', json={'id': 912})
        assert r.get_json()['code'] == 200
    finally:
        _cleanup_account(912, 't4_o.json')


# ── login (SSE) ──────────────────────────────────────────────────────────────

def test_login_missing_params_400(client):
    r = client.get('/login?type=1')
    assert r.get_json()['code'] == 400


def test_login_unsupported_platform_400(client):
    with patch('blueprints.account_bp.get_platform', return_value=None):
        r = client.get('/login?type=99&id=t4x')
    assert r.get_json()['code'] == 400


def test_login_sse_stream_200(client):
    fake = _FakePlatform()
    with patch('blueprints.account_bp.get_platform', return_value=fake):
        r = client.get('/login?type=3&id=t4-login-1&account_id=1')
    assert r.status_code == 200
    assert r.mimetype == 'text/event-stream'
    data = r.get_data(as_text=True)
    assert 'data: 200' in data
    assert fake.login_called is True
    # 流结束后 active_queues 应清理（call_on_close 触发）;Werkzeug 需显式 close
    import blueprints.account_bp as ab
    r.close()
    assert 't4-login-1' not in ab.active_queues


# ── platforms/import-supported ───────────────────────────────────────────────

def test_platforms_import_supported_lists_platforms(client):
    fake = _FakePlatform(supports_cookie_import=True)
    with patch('blueprints.account_bp.get_platform', return_value=fake):
        r = client.get('/platforms/import-supported')
    body = r.get_json()
    assert body['code'] == 200
    assert len(body['data']) > 0
    item = body['data'][0]
    assert {'id', 'key', 'name'} <= set(item)


def test_platforms_import_supported_all_filtered_out(client):
    fake = _FakePlatform(supports_cookie_import=False)
    with patch('blueprints.account_bp.get_platform', return_value=fake):
        r = client.get('/platforms/import-supported')
    assert r.get_json()['data'] == []


# ── uploadCookie / downloadCookie ────────────────────────────────────────────

def test_upload_cookie_success(client):
    _insert_account(sqlite3.connect(str(DB_PATH)), 913, platform_type=3, file_path='t4_up.json')
    try:
        data = {'id': '913', 'platform': 'douyin'}
        data['file'] = (io.BytesIO(b'{"k":"v"}'), 't4_up.json')
        r = client.post('/uploadCookie', data=data, content_type='multipart/form-data')
        assert r.get_json()['code'] == 200
        assert (Path(BASE_DIR / 'cookiesFile' / 't4_up.json')).exists()
    finally:
        _cleanup_account(913, 't4_up.json')


def test_upload_cookie_account_not_found_404(client):
    data = {'id': '999994', 'platform': 'douyin'}
    data['file'] = (io.BytesIO(b'{}'), 'nf.json')
    r = client.post('/uploadCookie', data=data, content_type='multipart/form-data')
    assert r.get_json()['code'] == 404


def test_download_cookie_missing_param_400(client):
    r = client.get('/downloadCookie')
    assert r.get_json()['code'] == 400


def test_download_cookie_not_found_404(client):
    r = client.get('/downloadCookie?filePath=t4_no_such.json')
    assert r.get_json()['code'] == 404


def test_download_cookie_success(client):
    p = Path(BASE_DIR / 'cookiesFile' / 't4_dl.json')
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"k":"v"}', encoding='utf-8')
    try:
        r = client.get('/downloadCookie?filePath=t4_dl.json')
        assert r.status_code == 200
        assert b'k' in r.data
    finally:
        if p.exists():
            p.unlink()


# ── deleteAccount 删 cookie 文件分支 ─────────────────────────────────────────

def test_delete_account_removes_cookie_file(client):
    p = Path(BASE_DIR / 'cookiesFile' / 't4_del.json')
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{}', encoding='utf-8')
    _insert_account(sqlite3.connect(str(DB_PATH)), 914, platform_type=3, file_path='t4_del.json')
    try:
        r = client.delete('/deleteAccount?id=914')
        assert r.get_json()['code'] == 200
        assert not p.exists()
        conn = sqlite3.connect(str(DB_PATH))
        try:
            row = conn.execute('SELECT id FROM user_info WHERE id = 914').fetchone()
        finally:
            conn.close()
        assert row is None
    finally:
        _cleanup_account(914, 't4_del.json')


# ── importAccount（启动 + stream 404）────────────────────────────────────────

def test_import_account_missing_params_400(client):
    r = client.post('/importAccount', json={'type': 3})
    assert r.get_json()['code'] == 400


def test_import_account_type_not_int_400(client):
    r = client.post('/importAccount', json={'type': 'abc', 'cookie_str': 'k=v'})
    assert r.get_json()['code'] == 400


def test_import_account_unsupported_platform_400(client):
    with patch('blueprints.account_bp.get_platform', return_value=None):
        r = client.post('/importAccount', json={'type': 99, 'cookie_str': 'k=v'})
    assert r.get_json()['code'] == 400


def test_import_account_platform_no_cookie_import_400(client):
    with patch('blueprints.account_bp.get_platform', return_value=_FakePlatform(supports_cookie_import=False)):
        r = client.post('/importAccount', json={'type': 3, 'cookie_str': 'k=v'})
    assert r.get_json()['code'] == 400


def test_import_account_bad_account_id_400(client):
    with patch('blueprints.account_bp.get_platform', return_value=_FakePlatform()):
        r = client.post('/importAccount', json={'type': 3, 'cookie_str': 'k=v', 'account_id': 'x'})
    assert r.get_json()['code'] == 400


def test_import_account_start_200(client):
    fake = _FakePlatform()
    with patch('blueprints.account_bp.get_platform', return_value=fake):
        r = client.post('/importAccount', json={'type': 3, 'cookie_str': 'k=v'})
    body = r.get_json()
    assert body['code'] == 200
    assert 'task_id' in body['data']
    import blueprints.account_bp as ab
    assert body['data']['task_id'] in ab.import_active_queues


def test_import_account_stream_unknown_task_404(client):
    r = client.get('/importAccount/stream?task_id=no-such-task')
    assert r.get_json()['code'] == 404


def test_import_account_stream_full_flow(client):
    """POST 启动任务 → SSE stream 读到终态并清理队列。"""
    fake = _FakePlatform()
    with patch('blueprints.account_bp.get_platform', return_value=fake):
        r = client.post('/importAccount', json={'type': 3, 'cookie_str': 'k=v'})
    task_id = r.get_json()['data']['task_id']
    with patch('blueprints.account_bp.get_platform', return_value=fake):
        sse = client.get(f'/importAccount/stream?task_id={task_id}')
    assert sse.status_code == 200
    data = sse.get_data(as_text=True)
    assert '"status": "200"' in data
    import blueprints.account_bp as ab
    sse.close()
    assert task_id not in ab.import_active_queues


# ── getAccounts 兜底 500 ─────────────────────────────────────────────────────

def test_get_accounts_db_error_500(client):
    with patch('blueprints.account_bp.sqlite3.connect', side_effect=RuntimeError('boom')):
        r = client.get('/getAccounts')
    body = r.get_json()
    assert body['code'] == 500
    assert '获取账号列表失败' in body['msg']
