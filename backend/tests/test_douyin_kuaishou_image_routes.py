"""抖音/快手图片发布域 blueprint 路由契约测试（T3b）。

统一模式：_get_account_cookie_file → 404(无 cookie) →
run_async(_fetch_with_browser/_search_music_via_browser) → success ? 200 : 500。
部分路由带前置参数校验(缺 account_id/keyword/link → 400,先于 cookie 404)。
参数化覆盖 douyin_image_bp 9 条 + kuaishou_image_bp 2 条路由的 400/404/200/500 路径，
mock 浏览器协程，不依赖真实浏览器。

注意：业务错误 = HTTP 200 亦可携带 code，本域路由实际返回 HTTP 4xx/5xx，
故同时断言 status_code 与 body.code。
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from app import app

# (bp 前缀, 完整 query 路径, 需要去除的前置参数名; None 表示该路由无 400 分支)
CASES = [
    ('douyin_image_bp', '/api/douyin-image/mix-list?account_id=a1', 'account_id'),
    ('douyin_image_bp', '/api/douyin-image/activity-list?account_id=a1', None),
    ('douyin_image_bp', '/api/douyin-image/hotspot-search?account_id=a1', None),  # keyword 默认空,无 400 分支
    ('douyin_image_bp', '/api/douyin-image/music-search?account_id=a1&keyword=歌', 'keyword'),
    ('douyin_image_bp', '/api/douyin-image/search-poi?account_id=a1&keyword=北京', 'keyword'),
    ('douyin_image_bp', '/api/douyin-image/search-miniapp?account_id=a1&link=https://x', 'link'),
    ('douyin_image_bp', '/api/douyin-image/search-game?account_id=a1&keyword=游戏', 'keyword'),
    ('douyin_image_bp', '/api/douyin-image/search-mark-spu?account_id=a1&keyword=商品', 'keyword'),
    ('douyin_image_bp', '/api/douyin-image/search-medium?account_id=a1&keyword=影视', 'keyword'),
    ('kuaishou_image_bp', '/api/kuaishou-image/music-search?account_id=a1&keyword=歌', 'keyword'),
]

IDS = [f"{bp}|{path.split('?')[0]}" for bp, path, _ in CASES]


def _strip_query_param(path: str, param: str) -> str:
    """从 query string 中移除指定参数，其余保留。"""
    route, _, qs = path.partition('?')
    kept = [p for p in qs.split('&') if p and not p.startswith(f'{param}=')]
    return f'{route}?{"&".join(kept)}'


@pytest.mark.parametrize("bp,path,need_param", CASES, ids=IDS)
def test_missing_param_400(bp, path, need_param):
    """带前置校验的路由: 缺必填参数时 400(先于 cookie 404)。"""
    app.config['TESTING'] = True
    if not need_param:
        pytest.skip("该路由无前置参数校验")
    r = app.test_client().get(_strip_query_param(path, need_param))
    body = r.get_json()
    assert r.status_code == 400
    assert body['code'] == 400
    assert '缺少' in body['msg'] and '参数' in body['msg']


@pytest.mark.parametrize("bp,path,need_param", CASES, ids=IDS)
def test_no_cookie_404(bp, path, need_param):
    app.config['TESTING'] = True
    with patch(f'blueprints.{bp}._get_account_cookie_file', return_value=None):
        r = app.test_client().get(path)
    body = r.get_json()
    assert r.status_code == 404
    assert body['code'] == 404
    assert '账号' in body['msg']


@pytest.mark.parametrize("bp,path,need_param", CASES, ids=IDS)
def test_success_200(bp, path, need_param):
    app.config['TESTING'] = True
    with patch(f'blueprints.{bp}._get_account_cookie_file', return_value='cookies/x.json'), \
         patch(f'blueprints.{bp}.run_async', return_value={"success": True, "data": {"list": [], "total": 0}}):
        r = app.test_client().get(path)
    body = r.get_json()
    assert r.status_code == 200
    assert body['code'] == 200
    assert body['data']['total'] == 0


@pytest.mark.parametrize("bp,path,need_param", CASES, ids=IDS)
def test_browser_failure_500(bp, path, need_param):
    app.config['TESTING'] = True
    with patch(f'blueprints.{bp}._get_account_cookie_file', return_value='cookies/x.json'), \
         patch(f'blueprints.{bp}.run_async', return_value={"success": False, "error": "browser crashed"}):
        r = app.test_client().get(path)
    body = r.get_json()
    assert r.status_code == 500
    assert body['code'] == 500
    assert 'browser crashed' in body['msg']


def test_kuaishou_ping_200():
    """快手图集 blueprint 存活探针。"""
    app.config['TESTING'] = True
    r = app.test_client().get('/api/kuaishou-image/ping')
    body = r.get_json()
    assert r.status_code == 200
    assert body['code'] == 200
    assert body['msg'] == 'kuaishou-image bp ok'
