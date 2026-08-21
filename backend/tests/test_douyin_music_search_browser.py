"""抖音图文 _search_music_via_browser 浏览器自动化 helper 契约测试（T7 试点）。

用 fake Playwright 页面驱动完整流程，覆盖关键分支：
1. 未找到文件上传入口
2. 未找到选择音乐按钮（上传成功）
3. 未找到搜索框（音乐按钮成功）
4. 未拦截到搜索结果（搜索成功但无响应）
5. 成功拦截并返回音乐数据
6. 发布按钮流程（url 停留 upload 页时点发布）
7. 选择音乐按钮的坐标兜底分支（第一个选择器不可见时）

fake page 的 locator 行为由 cfg 驱动（visible/countable 选择器集合），
captured 模式在注册 response handler 时立即异步触发，模拟已捕获的响应。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from blueprints.douyin_image_bp import _search_music_via_browser


class _FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    async def count(self):
        return 1 if self.selector in self.page.cfg['countable'] else 0

    async def is_visible(self, timeout=None):
        return self.selector in self.page.cfg['visible']

    async def set_input_files(self, *args, **kwargs):
        self.page.events.append(('upload', self.selector))

    async def clear(self):
        pass

    async def fill(self, text):
        self.page.events.append(('fill', text))

    async def press(self, key):
        self.page.events.append(('press', key))

    async def click(self):
        self.page.events.append(('click', self.selector))


class _FakeResponse:
    def __init__(self, url, data):
        self.url = url
        self._data = data

    async def json(self):
        return self._data


class _FakePage:
    def __init__(self, cfg):
        self.cfg = cfg
        self.url = cfg.get('url', 'https://creator.douyin.com/creator-micro/content/publish')
        self.events = []
        self._handlers = []

    def on(self, event, handler):
        if event != 'response':
            return
        self._handlers.append(handler)
        if self.cfg.get('captured'):
            resp = _FakeResponse(
                'https://tsearch.amemv.com/openapi/aweme/v1/music/search?keyword=x',
                self.cfg['captured_data'],
            )
            asyncio.get_event_loop().create_task(handler(resp))

    def locator(self, selector):
        return _FakeLocator(self, selector)

    async def goto(self, *args, **kwargs):
        self.events.append(('goto', args[0] if args else None))
        await asyncio.sleep(0)  # 让出事件循环,让 response handler task 有机会跑

    async def wait_for_timeout(self, ms):
        await asyncio.sleep(0)  # 同上:必须真实挂起,否则 handler task 到 run 关闭才执行


class _FakeContext:
    def __init__(self, page):
        self.page = page

    async def new_page(self):
        return self.page

    async def close(self):
        await asyncio.sleep(0)


class _FakeBrowser:
    def __init__(self, page):
        self.page = page

    async def close(self):
        await asyncio.sleep(0)


def _run(cfg):
    page = _FakePage(cfg)
    async def _fake_create_browser(headless=True):
        return _FakeBrowser(page)

    async def _fake_create_context(browser, storage_state=None):
        return _FakeContext(browser.page)

    with patch('blueprints.douyin_image_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.douyin_image_bp.create_context', side_effect=_fake_create_context):
        result = asyncio.run(_search_music_via_browser('cookies/x.json', '关键词'))
    return result, page


# 上传 input 选择器（按代码顺序）
UPLOAD_SELECTORS = [
    'input[type="file"]',
    'input[accept*="image"]',
    '.upload-btn input[type="file"]',
]
# 选择音乐按钮选择器
MUSIC_SELECTORS = [
    '.action-Q1y01k',
    'span:has-text("选择音乐")',
    '[class*="container-right"]:has-text("选择音乐")',
    'text="选择音乐"',
]
# 搜索框选择器
SEARCH_SELECTORS = [
    'input[placeholder="搜索音乐"]',
    'input[placeholder*="搜索音乐"]',
    '.music-search-jpUg0G input',
    '.semi-input[placeholder*="搜索"]',
    'input.semi-input',
]

CAPTURED_DATA = {'status_code': 0, 'music': [{'title': '歌1', 'author': '甲'}]}


def test_music_search_upload_not_found():
    cfg = {'countable': set(), 'visible': set()}
    result, _ = _run(cfg)
    assert result == {'success': False, 'error': '未找到文件上传入口'}


def test_music_search_music_button_not_found():
    cfg = {'countable': {UPLOAD_SELECTORS[0]}, 'visible': set()}
    result, _ = _run(cfg)
    assert result == {'success': False, 'error': '未找到选择音乐按钮'}


def test_music_search_search_box_not_found():
    cfg = {'countable': {UPLOAD_SELECTORS[0]}, 'visible': {MUSIC_SELECTORS[0]}}
    result, _ = _run(cfg)
    assert result == {'success': False, 'error': '未找到搜索框'}


def test_music_search_no_captured_response():
    cfg = {
        'countable': {UPLOAD_SELECTORS[0]},
        'visible': {MUSIC_SELECTORS[0], SEARCH_SELECTORS[0]},
        'captured': False,
    }
    result, _ = _run(cfg)
    assert result == {'success': False, 'error': '未能拦截到搜索结果'}


def test_music_search_success():
    cfg = {
        'countable': {UPLOAD_SELECTORS[0]},
        'visible': {MUSIC_SELECTORS[0], SEARCH_SELECTORS[0]},
        'captured': True,
        'captured_data': CAPTURED_DATA,
    }
    result, page = _run(cfg)
    assert result == {'success': True, 'data': CAPTURED_DATA}
    # 全流程事件验证：上传 → 点击音乐 → 输入关键词 → 回车
    event_kinds = [e[0] for e in page.events]
    assert 'upload' in event_kinds
    assert ('click', MUSIC_SELECTORS[0]) in page.events
    assert ('fill', '关键词') in page.events
    assert ('press', 'Enter') in page.events


def test_music_search_publish_button_flow():
    """url 停留在 upload 页时，应先点击发布按钮再继续。"""
    cfg = {
        'url': 'https://creator.douyin.com/creator-micro/content/upload?default-tab=3',
        'countable': {UPLOAD_SELECTORS[1]},  # 第二个上传选择器生效
        'visible': {
            'button:has-text("发布"), .publish-btn, [class*="publish"]',
            MUSIC_SELECTORS[1],
            SEARCH_SELECTORS[1],
        },
        'captured': True,
        'captured_data': CAPTURED_DATA,
    }
    result, page = _run(cfg)
    assert result['success'] is True
    clicked = [e for e in page.events if e[0] == 'click']
    assert ('click', 'button:has-text("发布"), .publish-btn, [class*="publish"]') in clicked
    assert ('click', MUSIC_SELECTORS[1]) in clicked


def test_music_search_music_text_fallback():
    """首个音乐选择器不可见时，走 'text=选择音乐' 坐标兜底。"""
    cfg = {
        'countable': {UPLOAD_SELECTORS[0]},
        'visible': {'text="选择音乐"', SEARCH_SELECTORS[0]},
        'captured': True,
        'captured_data': CAPTURED_DATA,
    }
    result, page = _run(cfg)
    assert result['success'] is True
    assert ('click', 'text="选择音乐"') in page.events
