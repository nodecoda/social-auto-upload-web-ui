"""公众号合集列表浏览器 helper 契约测试（T9）。

_fetch_collections_via_browser:首页解析 token → 打开管理页 → 点类型 tab
→ 解析表格 .album-title。tab 缺失/表格空 = 账号无合集,返回空 success。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from blueprints.weixin_gzh_bp import _fetch_collections_via_browser

_REAL_SLEEP = asyncio.sleep

TAB = "li.weui-desktop-tag:has-text(视频合集)"
ALBUM_TITLE = "table.weui-desktop-table tbody tr .album-title"
TIPS = ".album-title-tips"


class _FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    async def wait_for(self, state=None, timeout=None):
        if not self.page.cfg_visible_at(self.selector):
            raise TimeoutError(f'wait_for timeout: {self.selector}')

    async def click(self):
        self.page.events.append(('click', self.selector))

    async def count(self):
        if self.selector == ALBUM_TITLE:
            return len(self.page.cfg.get('titles', []))
        if self.selector == TIPS:
            return 1 if self.page.cfg.get('tips_visible', True) else 0
        return 1 if self.page.cfg_visible_at(self.selector) else 0

    async def inner_text(self):
        idx = getattr(self, '_idx', 0)
        titles = self.page.cfg.get('titles', [])
        return titles[idx] if idx < len(titles) else ''

    def locator(self, sub):
        inner = _FakeLocator(self.page, sub)
        inner._idx = getattr(self, '_idx', 0)
        return inner

    def nth(self, i):
        nth = _FakeLocator(self.page, self.selector)
        nth._idx = i
        return nth


class _FakePage:
    def __init__(self, cfg):
        self.cfg = cfg
        self.events = []

    @property
    def url(self):
        return self.cfg.get('url', '')

    def locator(self, selector, has_text=None):
        if has_text is not None:
            selector = f"{selector}:has-text({has_text})"
        return _FakeLocator(self, selector)

    async def goto(self, url, **kwargs):
        self.events.append(('goto', url))

    def cfg_visible_at(self, selector):
        return selector in self.cfg.get('visible', set())


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

    with patch('blueprints.weixin_gzh_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.weixin_gzh_bp.create_context', side_effect=_fake_create_context), \
         patch('blueprints.weixin_gzh_bp.asyncio.sleep', side_effect=_fast_sleep):
        result = asyncio.run(fn('cookies/x.json'))
    return result, page


TOKEN_URL = "https://mp.weixin.qq.com/?token=888888"


def _cfg(**overrides):
    cfg = {
        'url': TOKEN_URL,
        'visible': {TAB},
        'titles': ['AI 工具实战', 'Vlog 日常', ''],
    }
    cfg.update(overrides)
    return cfg


def test_token_parse_fail():
    """首页 URL 无 token → 报错。"""
    result, _ = _run(_fetch_collections_via_browser, _cfg(url='https://mp.weixin.qq.com/'))
    assert result['success'] is False
    assert '未能解析 token' in result['error']


def test_tab_missing_returns_empty():
    """找不到对应类型 tab = 账号无该类型合集 → 空 success。"""
    result, _ = _run(_fetch_collections_via_browser, _cfg(visible=set()))
    assert result == {'success': True, 'data': {'list': [], 'total': 0}}


def test_table_empty_returns_empty():
    """tab 找到但表格无行 → 空 success。"""
    result, _ = _run(_fetch_collections_via_browser, _cfg(titles=[]))
    assert result == {'success': True, 'data': {'list': [], 'total': 0}}


def test_success_parse():
    """解析表格合集名,跳过空行。"""
    result, page = _run(_fetch_collections_via_browser, _cfg())
    assert result['success'] is True
    assert result['data']['total'] == 2
    assert result['data']['list'] == [
        {'name': 'AI 工具实战'},
        {'name': 'Vlog 日常'},
    ]
    assert ('click', TAB) in page.events
    assert page.events[0] == ('goto', 'https://mp.weixin.qq.com/')


def test_goto_uses_resolved_token():
    """管理页 URL 拼装了解析出的 token。"""
    _, page = _run(_fetch_collections_via_browser, _cfg())
    mgr = [e for e in page.events if e[0] == 'goto' and 'appmsgalbummgr' in e[1]]
    assert mgr and 'token=888888' in mgr[0][1]
