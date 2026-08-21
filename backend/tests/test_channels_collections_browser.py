"""视频号合集列表浏览器 helper 契约测试（T8a）。

_channels_bp._fetch_collections_via_browser:goto → 点「选择合集」→
解析 .option-item .item .name DOM。覆盖分支:
1. 页面加载超时(入口未出现)
2. 点击后浮层未弹出
3. 成功解析(跳过空名/「创建新合集」/「选择合集」)
4. 全部被过滤 → 空列表
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from blueprints.channels_bp import _fetch_collections_via_browser

_REAL_SLEEP = asyncio.sleep


class _FakeLocator:
    def __init__(self, page, selector, index=None):
        self.page = page
        self.selector = selector
        self.index = index

    @property
    def first(self):
        return self

    def nth(self, i):
        return _FakeLocator(self.page, self.selector, index=i)

    async def count(self):
        return self.page.cfg_count(self.selector)

    async def inner_text(self):
        return self.page.cfg_text(self.selector, self.index)

    async def click(self):
        self.page.events.append(('click', self.selector))


class _FakePage:
    def __init__(self, cfg):
        self.cfg = cfg
        self.url = 'https://channels.weixin.qq.com/platform/post/edit'
        self.events = []

    def get_by_text(self, text, exact=False):
        return _FakeLocator(self, f'text={text}')

    def locator(self, selector):
        return _FakeLocator(self, selector)

    async def goto(self, *args, **kwargs):
        self.events.append(('goto',))
        await _REAL_SLEEP(0)

    async def wait_for_load_state(self, *args, **kwargs):
        pass

    def cfg_count(self, selector):
        return self.cfg.get('counts', {}).get(selector, 0)

    def cfg_text(self, selector, index):
        return self.cfg.get('texts', {}).get(selector, [])[index]


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


ENTRY = 'text=选择合集'
NAMES = '.option-item .item .name'


def _run(cfg):
    page = _FakePage(cfg)

    async def _fake_create_browser(headless=True):
        return _FakeBrowser(page)

    async def _fake_create_context(browser, storage_state=None):
        return _FakeContext(browser.page)

    async def _fast_sleep(delay):
        await _REAL_SLEEP(0)

    with patch('blueprints.channels_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.channels_bp.create_context', side_effect=_fake_create_context), \
         patch('blueprints.channels_bp.asyncio.sleep', side_effect=_fast_sleep):
        result = asyncio.run(_fetch_collections_via_browser('cookies/x.json'))
    return result, page


def test_channels_entry_timeout():
    cfg = {'counts': {ENTRY: 0, NAMES: 0}}
    result, _ = _run(cfg)
    assert result == {'success': False, 'error': '页面加载超时,未找到「选择合集」入口'}


def test_channels_popover_not_shown():
    cfg = {'counts': {ENTRY: 1, NAMES: 0}}
    result, _ = _run(cfg)
    assert result == {'success': False, 'error': '点击后未弹出合集选择浮层'}


def test_channels_success_parses_and_filters():
    cfg = {
        'counts': {ENTRY: 1, NAMES: 4},
        'texts': {NAMES: ['合集A', ' ', '创建新合集', '合集B']},
    }
    result, page = _run(cfg)
    assert result == {'success': True, 'data': {'list': [{'name': '合集A'}, {'name': '合集B'}], 'total': 2}}
    assert ('click', ENTRY) in page.events


def test_channels_all_filtered_out():
    cfg = {
        'counts': {ENTRY: 1, NAMES: 3},
        'texts': {NAMES: ['创建新合集', '选择合集', '  ']},
    }
    result, _ = _run(cfg)
    assert result == {'success': True, 'data': {'list': [], 'total': 0}}
