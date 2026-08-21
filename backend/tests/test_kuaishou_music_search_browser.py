"""快手图文 _search_music_via_browser 浏览器自动化 helper 契约测试（T7b）。

fake Playwright 页面驱动完整流程，覆盖关键分支：
1. 成功拦截并返回规范化 musicList（duration //1000、cover 取首图 url）
2. 空 musicList
3. 音乐抽屉未出现 → error
4. 搜索框点击失败 → input 枚举兜底 → error
5. 输入关键词后未拦截到响应 → error
6. 「添加音乐」wait_for 失败 → JS evaluate 兜底点击 → 流程继续成功

asyncio.sleep 被替换为立即返回（仍让出事件循环），避免真实等待。
captured 在 keyboard.type 后由 fake 触发，模拟搜索接口响应。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from blueprints.kuaishou_image_bp import KUAISHOU_MUSIC_SEARCH_URL, _search_music_via_browser

_REAL_SLEEP = asyncio.sleep  # patch kib.asyncio.sleep 前先捕获真实引用


class _FakeLocator:
    def __init__(self, page, selector, parent=None):
        self.page = page
        self.selector = selector
        self.parent = parent

    @property
    def first(self):
        return self

    def nth(self, index):
        return self

    def locator(self, sub):
        return _FakeLocator(self.page, f'{self.selector} {sub}', parent=self)

    async def wait_for(self, state=None, timeout=None):
        if not self.page.cfg_visible(self.selector):
            raise TimeoutError(f'wait_for timeout: {self.selector}')

    async def click(self):
        self.page.events.append(('click', self.selector))

    async def count(self):
        return self.page.cfg_count(self.selector)

    async def evaluate(self, js):
        return {'tag': 'DIV', 'cls': 'btn', 'text': '添加音乐', 'visible': True}

    async def get_attribute(self, name):
        return self.page.cfg_attr(self.selector, name)

    async def is_visible(self):
        return self.page.cfg_visible(self.selector)

    async def set_files(self, *args):
        self.page.events.append(('set_files',))


class _FakeResponse:
    def __init__(self, url, method, data):
        self.url = url
        self.request = type('R', (), {'method': method})()
        self._data = data

    async def json(self):
        return self._data


class _FakeKeyboard:
    def __init__(self, page):
        self.page = page

    async def press(self, key):
        self.page.events.append(('press', key))

    async def type(self, text):
        self.page.events.append(('type', text))
        # 模拟搜索接口响应在输入后到达
        if self.page.cfg['captured_after_type']:
            resp = _FakeResponse(
                KUAISHOU_MUSIC_SEARCH_URL + '?keyword=x',
                'POST',
                self.page.cfg['captured_data'],
            )
            for handler in self.page._handlers:
                asyncio.get_event_loop().create_task(handler(resp))
        await _REAL_SLEEP(0)


class _FakeFC:
    def __init__(self, page):
        self.page = page

    async def set_files(self, path):
        self.page.events.append(('set_files', str(path)))


class _FakeExpectFC:
    def __init__(self, page):
        self._fc = _FakeFC(page)
        # Playwright 语义:fc_info.value 是 awaitable 属性(不是方法)
        self.value = self._value_coro()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _value_coro(self):
        return self._fc


class _FakePage:
    def __init__(self, cfg):
        self.cfg = cfg
        self.url = 'https://cp.kuaishou.com/article/publish/video?tabType=2'
        self.events = []
        self.keyboard = _FakeKeyboard(self)
        self._handlers = []

    def on(self, event, handler):
        if event == 'response':
            self._handlers.append(handler)

    def locator(self, selector):
        return _FakeLocator(self, selector)

    def expect_file_chooser(self):
        return _FakeExpectFC(self)

    async def goto(self, *args, **kwargs):
        self.events.append(('goto', args[0] if args else None))
        await _REAL_SLEEP(0)

    async def screenshot(self, path=None, full_page=False):
        self.events.append(('screenshot', str(path)))

    async def evaluate(self, js):
        self.events.append(('evaluate',))
        return None

    def cfg_visible(self, selector):
        return selector in self.cfg['visible']

    def cfg_count(self, selector):
        return self.cfg.get('counts', {}).get(selector, 0)

    def cfg_attr(self, selector, name):
        return self.cfg.get('attrs', {}).get(selector, {}).get(name)


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


UPLOAD_BTN = "button[class^='_upload-btn']:visible, button[class*='upload-btn']:visible"
ADD_MUSIC = "div:text-is('添加音乐')"
DRAWER = 'div.ant-drawer-content-wrapper:visible'
SEARCH_INPUT = "div.ant-drawer-content-wrapper:visible input[placeholder='搜索音乐']"
MUSIC_LIST = [
    {'musicId': 'm1', 'title': '歌一', 'author': '甲', 'duration': 234000, 'cover': [{'url': 'http://c/1.png'}]},
    {'musicId': 'm2', 'title': '歌二', 'author': '乙', 'duration': 90000, 'cover': []},
]
CAPTURED = {'data': {'musicList': MUSIC_LIST}}


def _run(cfg):
    page = _FakePage(cfg)

    async def _fake_create_browser(headless=True):
        return _FakeBrowser(page)

    async def _fake_create_context(browser, storage_state=None):
        return _FakeContext(browser.page)

    async def _fast_sleep(delay):
        await _REAL_SLEEP(0)  # 立即返回但仍让出事件循环

    with patch('blueprints.kuaishou_image_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.kuaishou_image_bp.create_context', side_effect=_fake_create_context), \
         patch('blueprints.kuaishou_image_bp.asyncio.sleep', side_effect=_fast_sleep):
        result = asyncio.run(_search_music_via_browser('cookies/x.json', '关键词'))
    return result, page


def _base_cfg(**overrides):
    cfg = {
        'visible': {UPLOAD_BTN, ADD_MUSIC, DRAWER, SEARCH_INPUT},
        'counts': {'*:has-text(\'添加音乐\')': 2},
        'attrs': {},
        'captured_after_type': True,
        'captured_data': CAPTURED,
    }
    cfg.update(overrides)
    return cfg


def test_kuaishou_music_search_success():
    result, page = _run(_base_cfg())
    assert result['success'] is True
    assert result['data']['musicList'] == [
        {'musicId': 'm1', 'title': '歌一', 'author': '甲', 'duration': 234, 'cover': 'http://c/1.png'},
        {'musicId': 'm2', 'title': '歌二', 'author': '乙', 'duration': 90, 'cover': ''},
    ]
    assert result['data']['has_more'] is False
    # 流程事件：上传文件 → 输入关键词
    kinds = [e[0] for e in page.events]
    assert 'set_files' in kinds
    assert ('type', '关键词') in page.events


def test_kuaishou_music_search_empty_list():
    cfg = _base_cfg(captured_data={'data': {'musicList': []}})
    result, _ = _run(cfg)
    assert result == {'success': True, 'data': {'musicList': [], 'has_more': False, 'cursor': '0'}}


def test_kuaishou_music_search_drawer_missing():
    cfg = _base_cfg(visible={UPLOAD_BTN, ADD_MUSIC})  # drawer 不可见
    result, _ = _run(cfg)
    assert result['success'] is False
    assert '音乐抽屉未出现' in result['error']


def test_kuaishou_music_search_search_click_fails():
    class _ClickError(TimeoutError):
        pass

    original = _FakeLocator.click

    async def _click_raises(self):
        if self.selector == SEARCH_INPUT:
            raise _ClickError('search input not visible')
        return await original(self)

    with patch.object(_FakeLocator, 'click', _click_raises):
        result, _page = _run(_base_cfg())
    assert result['success'] is False
    assert '搜索框点击失败' in result['error']


def test_kuaishou_music_search_no_captured():
    cfg = _base_cfg(captured_after_type=False)
    result, _ = _run(cfg)
    assert result == {'success': False, 'error': '未捕获到音乐搜索响应'}


def test_kuaishou_music_search_add_music_js_fallback():
    """「添加音乐」父级按钮 click 失败 → JS evaluate 兜底点击，流程仍成功。"""
    original = _FakeLocator.click

    async def _click_raises(self):
        if self.selector == f"{ADD_MUSIC} xpath=..":
            raise TimeoutError('parent click failed')
        return await original(self)

    with patch.object(_FakeLocator, 'click', _click_raises):
        result, page = _run(_base_cfg())
    assert result['success'] is True
    assert ('evaluate',) in page.events
