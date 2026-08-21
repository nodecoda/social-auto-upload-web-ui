"""jd_bp picker 路由契约测试（mock 后台浏览器，只测 HTTP 层）。

覆盖：open / search / novel/search / go_page / close 的
参数校验(400)、session 缺失(404)、成功(200)、异常(500) 四类路径。
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from app import app


def _client():
    app.config['TESTING'] = True
    return app.test_client()


def _fake_session(products=None, total=0, novels=None):
    """模拟 jd picker session: open/search/go_page/novel_search/close 返回固定结构。"""
    s = MagicMock()
    s.open.return_value = {"products": products if products is not None else [], "total": total}
    s.search.return_value = {"products": products if products is not None else [], "total": total}
    s.go_page.return_value = {"products": products if products is not None else [], "total": total}
    s.novel_search.return_value = {"novels": novels if novels is not None else []}
    s.close.return_value = True
    return s


# ── picker/open ──

def test_open_missing_account_id_400():
    r = _client().post('/api/jd/picker/open', json={})
    assert r.status_code == 400
    body = r.get_json()
    assert body['code'] == 400
    assert 'accountId' in body['msg']


def test_open_success_returns_products():
    session = _fake_session(products=[{"id": "p1"}], total=1)
    with patch('blueprints.jd_bp.pool') as pool_mock, \
         patch('blueprints.jd_bp.run_picker_async', return_value={"products": [{"id": "p1"}], "total": 1}):
        pool_mock.create.return_value = session
        r = _client().post('/api/jd/picker/open', json={"accountId": "acc-1"})
    assert r.status_code == 200
    body = r.get_json()
    assert body['code'] == 200
    assert body['data']['total'] == 1
    assert body['data']['sessionId'] == 'acc-1'


def test_open_exception_returns_500_and_releases_session():
    with patch('blueprints.jd_bp.pool') as pool_mock, \
         patch('blueprints.jd_bp.run_picker_async', side_effect=RuntimeError("browser died")):
        pool_mock.create.return_value = _fake_session()
        pool_mock.release.return_value = _fake_session()
        r = _client().post('/api/jd/picker/open', json={"accountId": "acc-1"})
    assert r.status_code == 500
    body = r.get_json()
    assert body['code'] == 500
    assert '打开选择面板失败' in body['msg']
    pool_mock.release.assert_called_once_with('acc-1')


# ── picker/search ──

def test_search_missing_account_id_400():
    r = _client().post('/api/jd/picker/search', json={"keyword": "耳机"})
    assert r.status_code == 400
    assert r.get_json()['msg'] == 'accountId 不能为空'


def test_search_no_session_404():
    with patch('blueprints.jd_bp.pool') as pool_mock:
        pool_mock.get.return_value = None
        r = _client().post('/api/jd/picker/search', json={"accountId": "acc-x", "keyword": "耳机"})
    assert r.status_code == 404
    assert '重新打开' in r.get_json()['msg']


def test_search_success():
    with patch('blueprints.jd_bp.pool') as pool_mock, \
         patch('blueprints.jd_bp.run_picker_async', return_value={"products": [{"id": "p2"}], "total": 1}):
        pool_mock.get.return_value = _fake_session()
        r = _client().post('/api/jd/picker/search', json={"accountId": "acc-1", "keyword": "耳机"})
    assert r.status_code == 200
    assert r.get_json()['data']['total'] == 1


def test_search_exception_500():
    with patch('blueprints.jd_bp.pool') as pool_mock, \
         patch('blueprints.jd_bp.run_picker_async', side_effect=RuntimeError("timeout")):
        pool_mock.get.return_value = _fake_session()
        r = _client().post('/api/jd/picker/search', json={"accountId": "acc-1", "keyword": "x"})
    assert r.status_code == 500


# ── novel/search ──

def test_novel_search_missing_account_id_400():
    r = _client().post('/api/jd/novel/search', json={"keyword": "三体"})
    assert r.status_code == 400
    assert 'accountId' in r.get_json()['msg']


def test_novel_search_creates_session_when_missing():
    """小说搜索不要求已 open: pool.get 为空时自动 pool.create。"""
    with patch('blueprints.jd_bp.pool') as pool_mock, \
         patch('blueprints.jd_bp.run_picker_async', return_value={"novels": [{"id": "n1", "title": "三体"}]}):
        pool_mock.get.return_value = None
        pool_mock.create.return_value = _fake_session(novels=[{"id": "n1", "title": "三体"}])
        r = _client().post('/api/jd/novel/search', json={"accountId": "acc-1", "keyword": "三体"})
    assert r.status_code == 200
    pool_mock.create.assert_called_once_with('acc-1')
    assert r.get_json()['data']['novels'][0]['title'] == '三体'


def test_novel_search_exception_500():
    with patch('blueprints.jd_bp.pool') as pool_mock, \
         patch('blueprints.jd_bp.run_picker_async', side_effect=RuntimeError("boom")):
        pool_mock.get.return_value = None
        pool_mock.create.return_value = _fake_session()
        r = _client().post('/api/jd/novel/search', json={"accountId": "acc-1", "keyword": "x"})
    assert r.status_code == 500
    assert '搜索小说失败' in r.get_json()['msg']


# ── picker/go_page ──

def test_go_page_no_session_404():
    with patch('blueprints.jd_bp.pool') as pool_mock:
        pool_mock.get.return_value = None
        r = _client().post('/api/jd/picker/go_page', json={"accountId": "acc-x", "page": 2})
    assert r.status_code == 404


def test_go_page_success():
    with patch('blueprints.jd_bp.pool') as pool_mock, \
         patch('blueprints.jd_bp.run_picker_async', return_value={"products": [], "total": 0}):
        pool_mock.get.return_value = _fake_session()
        r = _client().post('/api/jd/picker/go_page', json={"accountId": "acc-1", "page": 2})
    assert r.status_code == 200
    assert r.get_json()['data']['total'] == 0


# ── picker/close ──

def test_close_missing_account_id_400():
    r = _client().post('/api/jd/picker/close', json={})
    assert r.status_code == 400


def test_close_no_session_idempotent():
    """session 已不存在时 close 幂等成功。"""
    with patch('blueprints.jd_bp.pool') as pool_mock:
        pool_mock.release.return_value = None
        r = _client().post('/api/jd/picker/close', json={"accountId": "acc-x"})
    assert r.status_code == 200
    assert r.get_json()['data']['closed'] is True


def test_close_success():
    with patch('blueprints.jd_bp.pool') as pool_mock, \
         patch('blueprints.jd_bp.run_picker_async', return_value=True):
        pool_mock.release.return_value = _fake_session()
        r = _client().post('/api/jd/picker/close', json={"accountId": "acc-1"})
    assert r.status_code == 200
    assert r.get_json()['data']['closed'] is True
