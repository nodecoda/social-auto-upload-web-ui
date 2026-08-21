"""VIVO 位置搜索浏览器 helper 契约测试（T9）。

_fetch_positions_via_browser:上传测试视频 → 等 .short-video-edit-component
表单就绪 → 点 .sel-position-module → keyboard.type 逐字符输入 →
等 .position-list li 下拉 → 解析 .position-name/.position-info。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from blueprints.vivo_bp import _fetch_positions_via_browser

_REAL_SLEEP = asyncio.sleep

VIDEO_INPUT = 'input[type="file"][accept*="video"]'
GENERIC_FILE = 'input[type="file"]'
EDIT_COMPONENT = ".short-video-edit-component"
SUCCESS_TEXT = '.success-text:has-text("上传成功")'
POS_MODULE = ".sel-position-module"
POS_ITEM = ".position-list li"
POS_NAME = ".position-name"
POS_INFO = ".position-info"


class _FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    async def count(self):
        if self.selector == EDIT_COMPONENT:
            return 1 if self.page.cfg.get('form_ready', True) else 0
        if self.selector == SUCCESS_TEXT:
            if self.page.cfg.get('success_text_count', 0):
                self.page.cfg['form_ready'] = True  # 上传成功 → 表单随之就绪
            return self.page.cfg.get('success_text_count', 0)
        if self.selector == POS_ITEM:
            return len(self.page.cfg.get('positions', []))
        if self.selector == POS_MODULE:
            return 1 if self.page.cfg.get('pos_module_visible', True) else 0
        if self.selector in (POS_NAME, POS_INFO):
            # 子元素:默认存在,由 items 结构决定
            return 1
        return 1 if self.page.cfg_visible_at(self.selector) else 0

    async def set_input_files(self, path):
        if self.page.cfg.get('upload_fail'):
            raise TimeoutError('upload timeout')
        self.page.events.append(('set_input_files', str(path)))

    async def click(self):
        self.page.events.append(('click', self.selector))

    async def inner_text(self):
        idx = getattr(self, '_idx', 0)
        items = self.page.cfg.get('positions', [])
        if idx >= len(items):
            return ''
        item = items[idx]
        if self.selector == POS_INFO:
            return item.get('address', '')
        return item.get('name', '')

    def nth(self, i):
        nth = _FakeLocator(self.page, self.selector)
        nth._idx = i
        return nth

    def locator(self, sub):
        inner = _FakeLocator(self.page, sub)
        inner._idx = getattr(self, '_idx', 0)
        return inner


class _FakeKeyboard:
    def __init__(self, page):
        self.page = page

    async def type(self, text, delay=0):
        self.page.events.append(('type', text))


class _FakePage:
    def __init__(self, cfg):
        self.cfg = cfg
        self.events = []
        self.keyboard = _FakeKeyboard(self)

    def locator(self, selector):
        return _FakeLocator(self, selector)

    async def goto(self, *args, **kwargs):
        self.events.append(('goto',))

    async def wait_for_load_state(self, *args, **kwargs):
        pass

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


def _run(fn, cfg, test_video='/tmp/test.mp4'):
    page = _FakePage(cfg)

    async def _fake_create_browser(headless=True):
        return _FakeBrowser(page)

    async def _fake_create_context(browser, storage_state=None):
        return _FakeContext(browser.page)

    async def _fast_sleep(delay):
        await _REAL_SLEEP(0)

    with patch('blueprints.vivo_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.vivo_bp.create_context', side_effect=_fake_create_context), \
         patch('blueprints.vivo_bp.asyncio.sleep', side_effect=_fast_sleep), \
         patch('blueprints.vivo_bp.get_test_video', side_effect=lambda: test_video):
        result = asyncio.run(fn('cookies/x.json', '北京'))
    return result, page


def _cfg(**overrides):
    cfg = {
        'visible': {VIDEO_INPUT, GENERIC_FILE},
        'form_ready': True,
        'pos_module_visible': True,
        'positions': [{'name': '北京西站', 'address': '丰台区'}, {'name': '北京南站', 'address': '丰台区'}],
    }
    cfg.update(overrides)
    return cfg


def test_no_test_video():
    """无测试视频 → 报错。"""
    result, _ = _run(_fetch_positions_via_browser, _cfg(), test_video=None)
    assert result['success'] is False
    assert '未找到可用的测试视频文件' in result['error']


def test_upload_failure():
    """上传测试视频失败 → 报错。"""
    result, _ = _run(_fetch_positions_via_browser, _cfg(upload_fail=True))
    assert result['success'] is False
    assert '测试视频上传失败' in result['error']


def test_form_not_rendered():
    """表单始终未渲染 → 报错。"""
    result, _ = _run(_fetch_positions_via_browser, _cfg(form_ready=False, success_text_count=0))
    assert result['success'] is False
    assert '发布表单未渲染' in result['error']


def test_success_text_path():
    """先出现上传成功标记,再等表单 → 就绪。"""
    result, _ = _run(_fetch_positions_via_browser, _cfg(form_ready=False, success_text_count=1))
    assert result['success'] is True


def test_pos_module_missing():
    """位置入口缺失 → 报错。"""
    result, _ = _run(_fetch_positions_via_browser, _cfg(pos_module_visible=False))
    assert result['success'] is False
    assert '未找到位置入口' in result['error']


def test_no_dropdown():
    """输入后无下拉选项 → 报错。"""
    result, page = _run(_fetch_positions_via_browser, _cfg(positions=[]))
    assert result['success'] is False
    assert '输入后未出现位置下拉选项' in result['error']
    assert ('type', '北京') in page.events


def test_success_parse():
    """解析下拉,返回 position_list。"""
    result, page = _run(_fetch_positions_via_browser, _cfg())
    assert result['success'] is True
    assert result['data']['position_list'] == [
        {'name': '北京西站', 'address': '丰台区'},
        {'name': '北京南站', 'address': '丰台区'},
    ]
    assert ('click', POS_MODULE) in page.events
    assert ('type', '北京') in page.events


def test_skip_empty_name():
    """name 为空的下拉项跳过。"""
    cfg = _cfg(positions=[{'name': '', 'address': 'xx'}, {'name': '天安门', 'address': ''}])
    result, _ = _run(_fetch_positions_via_browser, cfg)
    assert result['success'] is True
    assert result['data']['position_list'] == [{'name': '天安门', 'address': ''}]
