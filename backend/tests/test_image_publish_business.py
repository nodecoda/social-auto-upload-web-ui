"""图片发布域业务路由契约测试（T5，image_publish_bp 剩余面）。

覆盖：
- 纯函数 helper：_extract_image_draft_title / _extract_image_draft_cover /
  _extract_image_channels_summary（多分支参数化）
- /drafts POST save_draft：新建 / 更新(含 cover 保留) / 404 / 400 / DB 异常 500
- /drafts/<id> DELETE delete_draft：200 / 404 / DB 异常 500
- /execute-publish 前置校验 400 三连

注意：test_image_publish_endpoint.py 模块级会覆盖 SAU_DATA_DIR，
image_publish_bp.DB_PATH 的绑定取决于收集顺序。这里用 autouse fixture
把 DB_PATH 钉到 conftest 会话库（conf.BASE_DIR 由 app 早期导入固化，稳定）。
"""
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import blueprints.image_publish_bp as ipb
from app import app
from blueprints.image_publish_bp import (
    _extract_image_channels_summary,
    _extract_image_draft_cover,
    _extract_image_draft_title,
)


@pytest.fixture(autouse=True)
def _pin_image_publish_db():
    """把 image_publish_bp.DB_PATH 钉到 conftest 会话库。

    test_image_publish_endpoint.py 模块级覆盖 SAU_DATA_DIR，且 pytest 收集顺序
    不保证字母序，image_publish_bp.DB_PATH 的 import 时绑定不稳定。conftest 的
    _TEST_DATA_DIR 在其 import 时固化，是最稳定锚点。
    """
    from tests.conftest import _TEST_DATA_DIR
    ipb.DB_PATH = Path(_TEST_DATA_DIR) / 'db' / 'database.db'
    yield


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _conn():
    return sqlite3.connect(str(ipb.DB_PATH))


def _insert_draft(conn, draft_id=None, title='草稿', cover='c.png',
                  draft_data='{}', channels='[]', type_='image'):
    if draft_id is None:
        cur = conn.execute(
            "INSERT INTO drafts (type, title, cover_path, draft_data, channels_summary) VALUES (?,?,?,?,?)",
            (type_, title, cover, draft_data, channels),
        )
        conn.commit()
        return cur.lastrowid
    conn.execute(
        "INSERT INTO drafts (id, type, title, cover_path, draft_data, channels_summary) VALUES (?,?,?,?,?,?)",
        (draft_id, type_, title, cover, draft_data, channels),
    )
    conn.commit()
    return draft_id


def _delete_draft(draft_id):
    conn = _conn()
    try:
        conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
        conn.commit()
    finally:
        conn.close()


# ── 纯函数 helper：标题 ───────────────────────────────────────────────────────

def test_extract_title_prefers_account_overrides():
    data = {
        'accountOverrides': {'1': {'title': '  账号标题  '}, '2': {'title': '  第二个'}},
        'platformConfigs': {'douyin': {'title': '渠道标题'}},
    }
    assert _extract_image_draft_title(data) == '账号标题'


def test_extract_title_falls_back_to_platform_configs():
    data = {'platformConfigs': {'xiaohongshu': {'title': '小红书标题'}}}
    assert _extract_image_draft_title(data) == '小红书标题'


def test_extract_title_truncates_to_100():
    data = {'accountOverrides': {'1': {'title': '长' * 200}}}
    assert len(_extract_image_draft_title(data)) == 100


def test_extract_title_default():
    assert _extract_image_draft_title({}) == '无标题'
    assert _extract_image_draft_title({'platformConfigs': {'douyin': {'title': '  '}}}) == '无标题'


# ── 纯函数 helper：封面 ───────────────────────────────────────────────────────

def test_extract_cover_prefers_stored_path():
    data = {'commonConfig': {'coverImage': {'stored_path': '/data/c.png', 'url': 'http://x/y.png'}}}
    assert _extract_image_draft_cover(data) == '/data/c.png'


def test_extract_cover_url_strips_host():
    data = {'commonConfig': {'coverImage': {'url': 'http://localhost:5409/uploads/a.png'}}}
    assert _extract_image_draft_cover(data) == '/uploads/a.png'


def test_extract_cover_relative_url_kept():
    data = {'commonConfig': {'coverImage': {'url': '/uploads/b.png'}}}
    assert _extract_image_draft_cover(data) == '/uploads/b.png'


def test_extract_cover_path_or_name():
    assert _extract_image_draft_cover({'commonConfig': {'coverImage': {'path': '/p.jpg'}}}) == '/p.jpg'
    assert _extract_image_draft_cover({'commonConfig': {'coverImage': {'name': 'n.jpg'}}}) == 'n.jpg'


def test_extract_cover_falls_back_to_first_image():
    data = {'commonConfig': {'images': [{'stored_path': '/img/1.png'}, {'path': '/img/2.png'}]}}
    assert _extract_image_draft_cover(data) == '/img/1.png'
    data2 = {'commonConfig': {'images': [{'path': '/img/2.png'}]}}
    assert _extract_image_draft_cover(data2) == '/img/2.png'
    data3 = {'commonConfig': {'images': ['/img/legacy.png']}}
    assert _extract_image_draft_cover(data3) == ''


def test_extract_cover_empty():
    assert _extract_image_draft_cover({}) == ''


# ── 纯函数 helper：渠道摘要 ───────────────────────────────────────────────────

def test_extract_channels_summary_empty_ids():
    assert _extract_image_channels_summary({'publishAccountIds': []}) == []


def test_extract_channels_summary_aggregates_by_platform():
    conn = _conn()
    try:
        conn.execute('INSERT OR REPLACE INTO user_info (id, type, filePath, userName) VALUES (9501, 3, "t5_1.json", "甲")')
        conn.execute('INSERT OR REPLACE INTO user_info (id, type, filePath, userName) VALUES (9502, 3, "t5_2.json", "乙")')
        conn.execute('INSERT OR REPLACE INTO user_info (id, type, filePath, userName) VALUES (9503, 4, "t5_3.json", "丙")')
        conn.commit()
    finally:
        conn.close()
    try:
        out = _extract_image_channels_summary({'publishAccountIds': [9501, 9502, 9503]})
        by_key = {item['platform']: item['count'] for item in out}
        assert by_key == {'douyin': 2, 'kuaishou': 1}
        names = {item['platform']: item['name'] for item in out}
        assert names['douyin'] == '抖音'
    finally:
        conn = _conn()
        try:
            conn.execute('DELETE FROM user_info WHERE id IN (9501, 9502, 9503)')
            conn.commit()
        finally:
            conn.close()


def test_extract_channels_summary_db_error_returns_empty():
    with patch('blueprints.image_publish_bp._get_db', side_effect=RuntimeError('boom')):
        assert _extract_image_channels_summary({'publishAccountIds': [1]}) == []


# ── save_draft ───────────────────────────────────────────────────────────────

def test_save_draft_empty_body_400(client):
    r = client.post('/api/image-publish/drafts', json={})
    body = r.get_json()
    assert r.status_code == 400
    assert body['code'] == 400


def test_save_draft_missing_draft_data_400(client):
    r = client.post('/api/image-publish/drafts', json={'id': 1})
    assert r.get_json()['code'] == 400


def test_save_draft_create_200(client):
    r = client.post('/api/image-publish/drafts', json={
        'draft_data': {'title': '新图集', 'platformConfigs': {'douyin': {'title': '新图集'}}},
    })
    body = r.get_json()
    assert body['code'] == 200
    draft_id = body['data']['id']
    conn = _conn()
    try:
        row = conn.execute("SELECT type, title FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == 'image'
    assert row[1] == '新图集'
    _delete_draft(draft_id)


def test_save_draft_update_200(client):
    draft_id = _insert_draft(_conn(), title='旧标题', cover='old.png', draft_data=json.dumps({'t': 1}))
    try:
        r = client.post('/api/image-publish/drafts', json={
            'id': draft_id,
            'draft_data': {'title': '新标题', 'platformConfigs': {'douyin': {'title': '新标题'}}, 'commonConfig': {'coverImage': {'stored_path': '/new.png'}}},
        })
        assert r.get_json()['code'] == 200
        conn = _conn()
        try:
            row = conn.execute('SELECT title, cover_path FROM drafts WHERE id = ?', (draft_id,)).fetchone()
        finally:
            conn.close()
        assert row == ('新标题', '/new.png')
    finally:
        _delete_draft(draft_id)


def test_save_draft_update_keeps_cover_when_absent(client):
    draft_id = _insert_draft(_conn(), title='旧', cover='keep.png')
    try:
        r = client.post('/api/image-publish/drafts', json={
            'id': draft_id,
            'draft_data': {'platformConfigs': {'douyin': {'title': '新'}}},
        })
        assert r.get_json()['code'] == 200
        conn = _conn()
        try:
            row = conn.execute('SELECT title, cover_path FROM drafts WHERE id = ?', (draft_id,)).fetchone()
        finally:
            conn.close()
        assert row == ('新', 'keep.png')
    finally:
        _delete_draft(draft_id)


def test_save_draft_update_missing_404(client):
    r = client.post('/api/image-publish/drafts', json={'id': 999901, 'draft_data': {'title': 'x'}})
    assert r.get_json()['code'] == 404


def test_save_draft_db_error_500(client):
    with patch('blueprints.image_publish_bp._get_db', side_effect=RuntimeError('boom')):
        r = client.post('/api/image-publish/drafts', json={'draft_data': {'title': 'x'}})
    body = r.get_json()
    assert body['code'] == 500
    assert '保存失败' in body['msg']


# ── delete_draft ─────────────────────────────────────────────────────────────

def test_delete_draft_200(client):
    draft_id = _insert_draft(_conn())
    try:
        r = client.delete(f'/api/image-publish/drafts/{draft_id}')
        assert r.get_json()['code'] == 200
        conn = _conn()
        try:
            row = conn.execute('SELECT id FROM drafts WHERE id = ?', (draft_id,)).fetchone()
        finally:
            conn.close()
        assert row is None
    finally:
        _delete_draft(draft_id)


def test_delete_draft_not_found_404(client):
    r = client.delete('/api/image-publish/drafts/999902')
    assert r.get_json()['code'] == 404


def test_delete_draft_db_error_500(client):
    with patch('blueprints.image_publish_bp._get_db', side_effect=RuntimeError('boom')):
        r = client.delete('/api/image-publish/drafts/1')
    body = r.get_json()
    assert body['code'] == 500
    assert '删除失败' in body['msg']


# ── execute_publish 前置校验 ─────────────────────────────────────────────────

def test_execute_publish_empty_body_400(client):
    r = client.post('/api/image-publish/execute-publish', json={})
    assert r.get_json()['code'] == 400


def test_execute_publish_missing_platform_type_400(client):
    r = client.post('/api/image-publish/execute-publish', json={'image_ids': [1]})
    assert r.get_json()['code'] == 400


def test_execute_publish_missing_image_ids_400(client):
    r = client.post('/api/image-publish/execute-publish', json={'platform_type': 3})
    assert r.get_json()['code'] == 400
