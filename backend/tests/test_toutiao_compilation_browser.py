"""头条合集搜索浏览器 helper 契约测试（T9）。

_search_compilation_via_browser:goto 创作中心 → page.evaluate 直调
simpleGetAlbumInfoByMediaId 接口 → 解析 status/data → 关键词过滤。
无 DOM 交互,只需 fake page.evaluate。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from blueprints.toutiao_bp import _search_compilation_via_browser

_REAL_SLEEP = asyncio.sleep

API_URL = "https://mp.toutiao.com/xigua/api/pSeries/simpleGetAlbumInfoByMediaId/"


class _FakePage:
    def __init__(self, cfg):
        self.cfg = cfg
        self.events = []

    async def goto(self, *args, **kwargs):
        self.events.append(('goto', args[0] if args else None))

    async def wait_for_load_state(self, *args, **kwargs):
        pass

    async def evaluate(self, js, *args):
        self.events.append(('evaluate', js.split('\n')[0]))
        return self.cfg['evaluate_result']


class _FakeContext:
    def __init__(self, page):
        self.page = page

    async def new_page(self):
        return self.page

    async def close(self):
        await _REAL_SLEEP(0)


class _FakeBrowser:
    def __init__(self, page):
        self.page = page

    async def close(self):
        await _REAL_SLEEP(0)


def _run(fn, cfg):
    page = _FakePage(cfg)

    async def _fake_create_browser(headless=True):
        return _FakeBrowser(page)

    async def _fake_create_context(browser, storage_state=None):
        return _FakeContext(browser.page)

    async def _fast_sleep(delay):
        await _REAL_SLEEP(0)

    with patch('blueprints.toutiao_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.toutiao_bp.create_context', side_effect=_fake_create_context), \
         patch('blueprints.toutiao_bp.asyncio.sleep', side_effect=_fast_sleep):
        result = asyncio.run(fn('cookies/x.json', 'AI'))
    return result, page


def _ok_cfg(**overrides):
    cfg = {
        'evaluate_result': {
            'status': 0,
            'data': {
                's1': {'Title': 'AI 工具实战', 'CoverUrl': 'c1.png', 'SeqsCount': 3},
                's2': {'Title': 'Vlog 日常', 'CoverUrl': 'c2.png', 'SeqsCount': 5},
            },
        },
    }
    cfg.update(overrides)
    return cfg


def test_request_error():
    """evaluate 返回 {error} → 接口请求失败。"""
    result, page = _run(_search_compilation_via_browser, _ok_cfg(
        evaluate_result={'error': 'net::ERR_CONNECTION_RESET'}))
    assert result == {'success': False, 'error': '接口请求失败: net::ERR_CONNECTION_RESET'}
    assert ('evaluate', "async (url) => {") in page.events


def test_status_not_zero():
    """status != 0 → 报错并回显原始响应。"""
    data = {'status': 403, 'data': {'err': 'no auth'}}
    result, _ = _run(_search_compilation_via_browser, _ok_cfg(evaluate_result=data))
    assert result['success'] is False
    assert '接口返回 status=403' in result['error']
    assert result['data'] == data


def test_success_keyword_filter():
    """关键词过滤(大小写不敏感):标题含关键词的保留。"""
    result, _ = _run(_search_compilation_via_browser, _ok_cfg())
    assert result['success'] is True
    assert result['data']['total'] == 1
    assert result['data']['list'][0]['compilationId'] == 's1'
    assert result['data']['list'][0]['title'] == 'AI 工具实战'
    assert result['data']['list'][0]['coverUrl'] == 'c1.png'
    assert result['data']['list'][0]['total'] == 3


def test_success_no_match_empty():
    """关键词无匹配 → 空列表 success。"""
    result, _ = _run(_search_compilation_via_browser, _ok_cfg(
        evaluate_result={'status': 0, 'data': {'s1': {'Title': '美食探店', 'SeqsCount': 1}}}))
    assert result == {'success': True, 'data': {'list': [], 'total': 0}}


def test_success_non_dict_skipped():
    """data 里的非 dict 值跳过。"""
    result, _ = _run(_search_compilation_via_browser, _ok_cfg(
        evaluate_result={'status': 0, 'data': {'s1': {'Title': 'AI 测试', 'SeqsCount': 2}, 'bad': 'oops'}}))
    assert result['success'] is True
    assert result['data']['total'] == 1
    assert result['data']['list'][0]['compilationId'] == 's1'


def test_goto_creates_center():
    """先打开头条创作中心确保 cookie 生效。"""
    _, page = _run(_search_compilation_via_browser, _ok_cfg())
    assert page.events[0][0] == 'goto'
    assert 'mp.toutiao.com' in page.events[0][1]
