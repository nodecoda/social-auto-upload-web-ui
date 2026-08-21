"""微博合集列表浏览器 helper 契约测试（T9）。

_fetch_collections_via_browser:上传测试视频(WeiboPlatform._upload_video_file
→ patch 掉) → 等合集开关 label.woo-switch-main → 点击 → 解析
input[value*="集"] 的合集名("AI(共0集)" / "AI（共0集）" 两种格式)。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from blueprints.weibo_bp import _fetch_collections_via_browser

_REAL_SLEEP = asyncio.sleep

SWITCH = "label.woo-switch-main"
ALBUM_INPUT = 'input[type="text"][value*="集"]'


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
        return len(self.page.cfg.get('album_values', []))

    async def get_attribute(self, name):
        idx = getattr(self, '_idx', 0)
        values = self.page.cfg.get('album_values', [])
        if idx >= len(values):
            return None
        if name == 'value':
            return values[idx]
        return None

    def nth(self, i):
        nth = _FakeLocator(self.page, self.selector)
        nth._idx = i
        return nth


class _FakePage:
    def __init__(self, cfg):
        self.cfg = cfg
        self.events = []

    def locator(self, selector):
        return _FakeLocator(self, selector)

    async def goto(self, *args, **kwargs):
        self.events.append(('goto',))

    async def wait_for_load_state(self, *args, **kwargs):
        pass

    def cfg_visible_at(self, selector):
        if selector == SWITCH:
            return self.cfg.get('switch_visible', True)
        if selector == ALBUM_INPUT:
            return len(self.cfg.get('album_values', [])) > 0
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


def _run(fn, cfg, test_video='/tmp/test.mp4'):
    page = _FakePage(cfg)

    async def _fake_create_browser(headless=True):
        return _FakeBrowser(page)

    async def _fake_create_context(browser, storage_state=None):
        return _FakeContext(browser.page)

    async def _fast_sleep(delay):
        await _REAL_SLEEP(0)

    async def _fake_upload(page_obj, file_path):
        page_obj.events.append(('platform_upload', str(file_path)))

    with patch('blueprints.weibo_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.weibo_bp.create_context', side_effect=_fake_create_context), \
         patch('blueprints.weibo_bp.asyncio.sleep', side_effect=_fast_sleep), \
         patch('blueprints.weibo_bp.get_test_video', side_effect=lambda: test_video), \
         patch('blueprints.weibo_bp.WeiboPlatform._upload_video_file', side_effect=_fake_upload):
        result = asyncio.run(fn('cookies/x.json'))
    return result, page


def _cfg(**overrides):
    cfg = {
        'switch_visible': True,
        'album_values': ['AI(共0集)', 'Vlog（共3集）', ''],
    }
    cfg.update(overrides)
    return cfg


def test_no_test_video():
    """无测试视频 → 报错。"""
    result, _ = _run(_fetch_collections_via_browser, _cfg(), test_video=None)
    assert result == {'success': False, 'error': '未找到测试视频文件'}


def test_switch_missing():
    """合集开关未出现 = 表单未渲染 → 报错。"""
    result, page = _run(_fetch_collections_via_browser, _cfg(switch_visible=False))
    assert result['success'] is False
    assert '未找到合集开关' in result['error']
    assert ('platform_upload', '/tmp/test.mp4') in page.events


def test_no_album_empty():
    """无合集 → 空 success(正常情况)。"""
    result, _ = _run(_fetch_collections_via_browser, _cfg(album_values=[]))
    assert result == {'success': True, 'data': {'list': [], 'total': 0}}


def test_success_parse():
    """解析合集名,兼容 (共N集) 与 （共N集） 两种格式,跳过空值。"""
    result, page = _run(_fetch_collections_via_browser, _cfg())
    assert result['success'] is True
    assert result['data']['total'] == 2
    assert result['data']['list'] == [
        {'name': 'AI', 'raw': 'AI(共0集)'},
        {'name': 'Vlog', 'raw': 'Vlog（共3集）'},
    ]
    assert ('click', SWITCH) in page.events
    assert ('platform_upload', '/tmp/test.mp4') in page.events


def test_parse_item_failure_skipped():
    """get_attribute 返回空 → 跳过该项。"""
    result, _ = _run(_fetch_collections_via_browser, _cfg(
        album_values=['美食(共2集)', None, '旅行(共1集)']))
    assert result['success'] is True
    assert result['data']['list'] == [
        {'name': '美食', 'raw': '美食(共2集)'},
        {'name': '旅行', 'raw': '旅行(共1集)'},
    ]
