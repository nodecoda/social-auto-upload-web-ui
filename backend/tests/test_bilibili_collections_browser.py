"""B 站合集列表浏览器 helper 契约测试（T9）。

_fetch_collections_via_browser:iframe 探测(fallback 主页面 input) →
上传测试视频 → 等标题输入框(发布表单就绪) → 点「请选择合集」 →
解析 .season-item-title(跳过 创建合集/请选择合集)。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from blueprints.bilibili_bp import _fetch_collections_via_browser

_REAL_SLEEP = asyncio.sleep

FILE_INPUT = 'input[type="file"][accept*="video"], input[type="file"]'
TITLE_INPUT = 'input[placeholder*="标题"]'
ENTRY = "请选择合集"
SEASON_TITLE = ".season-item-title"


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
        if self.selector == SEASON_TITLE:
            return len(self.page.cfg.get('titles', []))
        if self.selector == TITLE_INPUT:
            return 1 if self.page.cfg.get('form_ready', True) else 0
        if self.selector == ENTRY:
            return 1 if self.page.cfg.get('entry_visible', True) else 0
        if self.selector == FILE_INPUT:
            return 1 if self.page.cfg.get('file_visible', True) else 0
        return 1 if self.page.cfg_visible_at(self.selector) else 0

    async def set_input_files(self, path):
        self.page.events.append(('set_input_files', str(path)))

    async def inner_text(self):
        idx = getattr(self, '_idx', 0)
        titles = self.page.cfg.get('titles', [])
        return titles[idx] if idx < len(titles) else ''

    def nth(self, i):
        nth = _FakeLocator(self.page, self.selector)
        nth._idx = i
        return nth


class _FakeFrameLocator:
    def __init__(self, page):
        self.page = page

    def locator(self, selector):
        loc = _FakeLocator(self.page, selector)

        async def _fail(state=None, timeout=None):
            raise TimeoutError('frame probe miss')
        loc.wait_for = _fail
        return loc


class _FakePage:
    def __init__(self, cfg):
        self.cfg = cfg
        self.events = []

    def locator(self, selector):
        return _FakeLocator(self, selector)

    def frame_locator(self, selector):
        self.events.append(('frame_locator', selector))
        return _FakeFrameLocator(self)

    def get_by_text(self, text, exact=False):
        return _FakeLocator(self, text)

    async def goto(self, *args, **kwargs):
        self.events.append(('goto',))

    async def wait_for_load_state(self, *args, **kwargs):
        pass

    def cfg_visible_at(self, selector):
        if selector in self.cfg.get('visible', set()):
            return True
        if selector == ENTRY:
            return self.cfg.get('entry_visible', True)
        return False


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


def _run(fn, cfg, test_video='/tmp/test.mp4'):
    page = _FakePage(cfg)

    async def _fake_create_browser(headless=True):
        return _FakeBrowser(page)

    async def _fake_create_context(browser, storage_state=None):
        return _FakeContext(browser.page)

    async def _fast_sleep(delay):
        await _REAL_SLEEP(0)

    with patch('blueprints.bilibili_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.bilibili_bp.create_context', side_effect=_fake_create_context), \
         patch('blueprints.bilibili_bp.asyncio.sleep', side_effect=_fast_sleep), \
         patch('blueprints.bilibili_bp.get_test_video', side_effect=lambda: test_video):
        result = asyncio.run(fn('cookies/x.json'))
    return result, page


def _cfg(**overrides):
    cfg = {
        'visible': {FILE_INPUT, TITLE_INPUT},
        'entry_visible': True,
        'form_ready': True,
        'titles': ['AI 工具实战', 'Vlog 日常', '创建合集', ''],
    }
    cfg.update(overrides)
    return cfg


def test_no_test_video():
    """无测试视频文件 → 报错。"""
    result, _ = _run(_fetch_collections_via_browser, _cfg(), test_video=None)
    assert result == {'success': False, 'error': '未找到测试视频文件'}


def test_form_not_ready():
    """标题输入框始终未出现 → 页面未跳转。"""
    result, _ = _run(_fetch_collections_via_browser, _cfg(form_ready=False))
    assert result['success'] is False
    assert '页面未跳转到发布表单' in result['error']


def test_entry_missing():
    """「请选择合集」入口缺失 → 报错。"""
    result, _ = _run(_fetch_collections_via_browser, _cfg(entry_visible=False))
    assert result['success'] is False
    assert '未找到「请选择合集」入口' in result['error']


def test_overlay_not_open():
    """点击后浮层无 .season-item-title → 报错。"""
    result, page = _run(_fetch_collections_via_browser, _cfg(titles=[]))
    assert result['success'] is False
    assert '点击后未弹出合集选择浮层' in result['error']
    assert ('click', ENTRY) in page.events


def test_success_parse():
    """解析合集名,跳过「创建合集」/「请选择合集」/空行。"""
    result, page = _run(_fetch_collections_via_browser, _cfg())
    assert result['success'] is True
    assert result['data']['total'] == 2
    assert result['data']['list'] == [{'name': 'AI 工具实战'}, {'name': 'Vlog 日常'}]
    # iframe 探测 + 主页面上传都发生了
    assert ('frame_locator', 'iframe[name="videoUpload"]') in page.events
    assert ('set_input_files', '/tmp/test.mp4') in page.events
