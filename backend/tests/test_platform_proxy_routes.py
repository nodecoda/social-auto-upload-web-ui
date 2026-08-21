"""平台薄代理 blueprint 路由契约测试（T3a）。

这些路由是统一模式：_get_account_cookie_file → 404(无 cookie) →
run_async(_xxx_via_browser) → success ? 200 : 500。
参数化覆盖 10 个 blueprint、12 条路由的 404/200/500 三类路径，
mock 浏览器协程，不依赖真实浏览器。
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from app import app

# (bp 前缀, 完整 query 路径, 是否需要 keyword 参数)
CASES = [
    ('alipay_bp', '/api/alipay/compilation-search?account_id=a1&keyword=合集', True),
    ('alipay_bp', '/api/alipay/music-list?account_id=a1', False),
    ('xiaohongshu_bp', '/api/xiaohongshu/collections?account_id=a1', False),
    ('xiaohongshu_bp', '/api/xiaohongshu/search-poi?account_id=a1&keyword=上海', True),
    ('bilibili_bp', '/api/bilibili/collections?account_id=a1', False),
    ('weibo_bp', '/api/weibo/collections?account_id=a1', False),
    ('weixin_gzh_bp', '/api/weixin_gzh/collections?account_id=a1', False),
    ('toutiao_bp', '/api/toutiao/compilation-search?account_id=a1&keyword=合集', False),  # keyword 可选(空则返回全部),无 400 分支
    ('vivo_bp', '/api/vivo/search-position?account_id=a1&keyword=北京', True),
    ('channels_bp', '/api/channels/collections?account_id=a1', False),
    ('channels_bp', '/api/channels/locations?account_id=a1&keyword=北京', True),
    ('channels_bp', '/api/channels/activities?account_id=a1&keyword=活动', True),
]

IDS = [f"{bp}|{path.split('?')[0]}" for bp, path, _ in CASES]


@pytest.mark.parametrize("bp,path,has_kw", CASES, ids=IDS)
def test_missing_keyword_400(bp, path, has_kw):
    """需要 keyword 的路由: 缺 keyword 时 400(先于 cookie 404)。"""
    app.config['TESTING'] = True
    if not has_kw:
        pytest.skip("该路由不要求 keyword")
    no_kw_path = '&'.join(p for p in path.split('?')[1].split('&') if not p.startswith('keyword='))
    r = app.test_client().get(f"{path.split('?')[0]}?{no_kw_path}")
    assert r.status_code == 400


@pytest.mark.parametrize("bp,path,has_kw", CASES, ids=IDS)
def test_no_cookie_404(bp, path, has_kw):
    app.config['TESTING'] = True
    with patch(f'blueprints.{bp}._get_account_cookie_file', return_value=None):
        r = app.test_client().get(path)
    body = r.get_json()
    assert body['code'] == 404
    assert '账号' in body['msg']


@pytest.mark.parametrize("bp,path,has_kw", CASES, ids=IDS)
def test_success_200(bp, path, has_kw):
    app.config['TESTING'] = True
    with patch(f'blueprints.{bp}._get_account_cookie_file', return_value='cookies/x.json'), \
         patch(f'blueprints.{bp}.run_async', return_value={"success": True, "data": {"list": [], "total": 0}}):
        r = app.test_client().get(path)
    body = r.get_json()
    assert body['code'] == 200
    assert body['data']['total'] == 0


@pytest.mark.parametrize("bp,path,has_kw", CASES, ids=IDS)
def test_browser_failure_500(bp, path, has_kw):
    app.config['TESTING'] = True
    with patch(f'blueprints.{bp}._get_account_cookie_file', return_value='cookies/x.json'), \
         patch(f'blueprints.{bp}.run_async', return_value={"success": False, "error": "browser crashed"}):
        r = app.test_client().get(path)
    body = r.get_json()
    assert body['code'] == 500
    assert 'browser crashed' in body['msg']
