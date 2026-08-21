"""taobao_guanghe_bp picker 路由契约测试（mock 后台浏览器与 cookie 解析）。

覆盖：open / switch_type / tab / filter / search / load_more / close 的
参数校验(400)、session 缺失(404)、账号缺失(404)、成功(200)、异常(500) 路径。
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from app import app  # noqa: E402


def _client():
    app.config['TESTING'] = True
    return app.test_client()


def _fake_session(session_id="sess-1"):
    s = MagicMock()
    s.session_id = session_id
    s.open.return_value = {"items": [], "has_more": False}
    s.switch_type.return_value = {"ok": True}
    s.switch_tab.return_value = {"ok": True}
    s.apply_filter.return_value = {"items": []}
    s.search.return_value = {"items": []}
    s.load_more.return_value = {"items": [], "has_more": False}
    s.close.return_value = True
    return s


# ── picker/open ──

def test_open_missing_account_id_400():
    r = _client().post('/api/taobao_guanghe/picker/open', json={"type": "product"})
    assert r.status_code == 400
    assert 'account_id' in r.get_json()['msg']


def test_open_invalid_type_400():
    r = _client().post('/api/taobao_guanghe/picker/open', json={"account_id": "a1", "type": "bad"})
    assert r.status_code == 400
    assert 'product 或 shop' in r.get_json()['msg']


def test_open_account_not_found_404():
    with patch('blueprints.taobao_guanghe_bp._get_cookie_path_by_account_id', return_value=""):
        r = _client().post('/api/taobao_guanghe/picker/open', json={"account_id": "a-x", "type": "product"})
    assert r.status_code == 404
    assert '账号不存在' in r.get_json()['msg']


def test_open_success():
    with patch('blueprints.taobao_guanghe_bp._get_cookie_path_by_account_id', return_value="cookies/x.json"), \
         patch('blueprints.taobao_guanghe_bp._resolve_cookie_path', return_value="/tmp/cookies/x.json"), \
         patch('blueprints.taobao_guanghe_bp.pool') as pool_mock, \
         patch('blueprints.taobao_guanghe_bp.run_picker_async', return_value={"items": [{"id": "g1"}], "has_more": True}):
        pool_mock.create.return_value = _fake_session()
        r = _client().post('/api/taobao_guanghe/picker/open', json={"account_id": "a1", "type": "shop"})
    assert r.status_code == 200
    body = r.get_json()
    assert body['code'] == 200
    assert body['data']['session_id'] == 'sess-1'
    assert body['data']['has_more'] is True


def test_open_exception_500_removes_session():
    with patch('blueprints.taobao_guanghe_bp._get_cookie_path_by_account_id', return_value="cookies/x.json"), \
         patch('blueprints.taobao_guanghe_bp._resolve_cookie_path', return_value="/tmp/cookies/x.json"), \
         patch('blueprints.taobao_guanghe_bp.pool') as pool_mock, \
         patch('blueprints.taobao_guanghe_bp.run_picker_async', side_effect=RuntimeError("open failed")):
        pool_mock.create.return_value = _fake_session()
        r = _client().post('/api/taobao_guanghe/picker/open', json={"account_id": "a1", "type": "product"})
    assert r.status_code == 500
    assert '打开选择面板失败' in r.get_json()['msg']
    pool_mock.remove.assert_called_once_with('a1')


# ── picker/switch_type ──

def test_switch_type_no_session_404():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock:
        pool_mock.get.return_value = None
        r = _client().post('/api/taobao_guanghe/picker/switch_type', json={"session_id": "sess-x", "type": "product"})
    assert r.status_code == 404


def test_switch_type_invalid_type_400():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock:
        pool_mock.get.return_value = _fake_session()
        r = _client().post('/api/taobao_guanghe/picker/switch_type', json={"session_id": "sess-1", "type": "bad"})
    assert r.status_code == 400
    assert 'product 或 shop' in r.get_json()['msg']


def test_switch_type_success():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock, \
         patch('blueprints.taobao_guanghe_bp.run_picker_async', return_value={"ok": True}):
        pool_mock.get.return_value = _fake_session()
        r = _client().post('/api/taobao_guanghe/picker/switch_type', json={"session_id": "sess-1", "type": "product"})
    assert r.status_code == 200
    assert r.get_json()['data']['ok'] is True


# ── picker/tab ──

def test_tab_invalid_tab_400():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock:
        pool_mock.get.return_value = _fake_session()
        r = _client().post('/api/taobao_guanghe/picker/tab', json={"session_id": "sess-1", "tab": "bad"})
    assert r.status_code == 400
    assert 'bought 或 preferred' in r.get_json()['msg']


def test_tab_success():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock, \
         patch('blueprints.taobao_guanghe_bp.run_picker_async', return_value={"ok": True}):
        pool_mock.get.return_value = _fake_session()
        r = _client().post('/api/taobao_guanghe/picker/tab', json={"session_id": "sess-1", "tab": "bought"})
    assert r.status_code == 200


# ── picker/filter ──

def test_filter_missing_both_400():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock:
        pool_mock.get.return_value = _fake_session()
        r = _client().post('/api/taobao_guanghe/picker/filter', json={"session_id": "sess-1"})
    assert r.status_code == 400
    assert '至少传一个' in r.get_json()['msg']


def test_filter_success():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock, \
         patch('blueprints.taobao_guanghe_bp.run_picker_async', return_value={"items": []}):
        pool_mock.get.return_value = _fake_session()
        r = _client().post('/api/taobao_guanghe/picker/filter', json={"session_id": "sess-1", "rule": "新品"})
    assert r.status_code == 200


# ── picker/search / load_more ──

def test_search_success():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock, \
         patch('blueprints.taobao_guanghe_bp.run_picker_async', return_value={"items": [{"id": "s1"}]}):
        pool_mock.get.return_value = _fake_session()
        r = _client().post('/api/taobao_guanghe/picker/search', json={"session_id": "sess-1", "keyword": "女装"})
    assert r.status_code == 200
    assert r.get_json()['data']['items'][0]['id'] == 's1'


def test_load_more_no_session_404():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock:
        pool_mock.get.return_value = None
        r = _client().post('/api/taobao_guanghe/picker/load_more', json={"session_id": "sess-x"})
    assert r.status_code == 404


def test_load_more_success():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock, \
         patch('blueprints.taobao_guanghe_bp.run_picker_async', return_value={"items": [], "has_more": False}):
        pool_mock.get.return_value = _fake_session()
        r = _client().post('/api/taobao_guanghe/picker/load_more', json={"session_id": "sess-1"})
    assert r.status_code == 200


# ── picker/close ──

def test_close_no_session_idempotent():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock:
        pool_mock.remove.return_value = None
        r = _client().post('/api/taobao_guanghe/picker/close', json={"session_id": "sess-x"})
    assert r.status_code == 200
    assert r.get_json()['data']['closed'] is True


def test_close_success():
    with patch('blueprints.taobao_guanghe_bp.pool') as pool_mock, \
         patch('blueprints.taobao_guanghe_bp.run_picker_async', return_value=True):
        pool_mock.remove.return_value = _fake_session()
        r = _client().post('/api/taobao_guanghe/picker/close', json={"session_id": "sess-1"})
    assert r.status_code == 200
    assert r.get_json()['data']['closed'] is True
