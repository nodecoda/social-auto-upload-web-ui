"""账号管理 API 测试（覆盖 blueprints/account_bp.py 迁移后的路由）。"""
import sqlite3

import pytest

from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _insert_account(conn, account_id=1, platform_type=3, file_path='test_cookie.json'):
    conn.execute(
        'INSERT OR REPLACE INTO user_info (id, type, filePath, userName) VALUES (?, ?, ?, ?)',
        (account_id, platform_type, file_path, f'测试账号{account_id}'),
    )
    conn.commit()


def _cleanup_account(conn, account_id):
    conn.execute('DELETE FROM user_info WHERE id = ?', (account_id,))
    conn.execute('DELETE FROM account_tags WHERE account_id = ?', (account_id,))
    conn.commit()


def test_get_accounts_returns_list_with_tags(client):
    from app import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    _insert_account(conn, 9001)
    try:
        r = client.get('/getAccounts')
        assert r.status_code == 200
        data = r.get_json()['data']
        assert isinstance(data, list)
        account = next(a for a in data if a[0] == 9001)
        # 行结构: [id, type, filePath, userName, status, avatar, tags...]
        assert account[2] == 'test_cookie.json'
        assert isinstance(account[-1], list)  # tags
    finally:
        _cleanup_account(conn, 9001)
        conn.close()


def test_delete_account_requires_delete_method(client):
    """删除是副作用操作，必须走 DELETE；GET 应 405。"""
    r = client.get('/deleteAccount?id=9001')
    assert r.status_code == 405


def test_delete_account_not_found(client):
    r = client.delete('/deleteAccount?id=999999')
    assert r.status_code == 404
    assert r.get_json()['msg'] == 'account not found'


def test_delete_account_success_removes_record(client):
    from app import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    _insert_account(conn, 9002)
    try:
        r = client.delete('/deleteAccount?id=9002')
        assert r.status_code == 200
        row = conn.execute('SELECT COUNT(*) FROM user_info WHERE id = 9002').fetchone()
        assert row[0] == 0
    finally:
        conn.close()


def test_delete_account_invalid_id(client):
    r = client.delete('/deleteAccount?id=abc')
    assert r.status_code == 400


def test_create_and_delete_tag_flow(client):
    r = client.post('/api/tags', json={'name': '迁移测试标签', 'color': '#123456'})
    assert r.status_code == 200
    tag_id = r.get_json()['data']['id']

    try:
        r = client.get('/api/tags')
        tags = r.get_json()['data']
        assert any(t['name'] == '迁移测试标签' for t in tags)
    finally:
        r = client.delete(f'/api/tags/{tag_id}')
        assert r.status_code == 200


def test_duplicate_tag_returns_409(client):
    client.post('/api/tags', json={'name': '唯一标签x'})
    r = client.post('/api/tags', json={'name': '唯一标签x'})
    assert r.status_code == 409
    # cleanup
    tags = client.get('/api/tags').get_json()['data']
    for t in tags:
        if t['name'] == '唯一标签x':
            client.delete(f"/api/tags/{t['id']}")


def test_set_account_tags_put(client):
    from app import DB_PATH
    conn = sqlite3.connect(str(DB_PATH))
    _insert_account(conn, 9003)
    try:
        r = client.post('/api/tags', json={'name': '打标标签'})
        tag_id = r.get_json()['data']['id']
        try:
            r = client.put('/api/accounts/9003/tags', json={'tag_ids': [tag_id]})
            assert r.status_code == 200
            r = client.get('/api/accounts/9003/tags')
            tags = r.get_json()['data']
            assert any(t['name'] == '打标标签' for t in tags)
        finally:
            client.delete(f'/api/tags/{tag_id}')
    finally:
        _cleanup_account(conn, 9003)
        conn.close()


def test_upload_cookie_validation(client):
    """无文件/非 JSON 文件名 → 400。"""
    r = client.post('/uploadCookie', data={'id': '1', 'platform': 'douyin'})
    assert r.status_code == 400
    r = client.post('/uploadCookie', data={
        'id': '1', 'platform': 'douyin',
    }, buffered=True, content_type='multipart/form-data')
    # 无文件字段
    assert r.status_code in (400, 500)


def test_download_cookie_path_traversal_blocked(client):
    r = client.get('/downloadCookie?filePath=../../etc/passwd')
    assert r.status_code == 400
