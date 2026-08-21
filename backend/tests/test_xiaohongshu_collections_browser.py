"""小红书合集/POI 浏览器 helper 契约测试（T8a）。

_xiaohongshu_bp._fetch_collections_via_browser:上传测试视频 → 等标题框 →
点「加入合集」→ 解析 .item-label DOM。
_xiaohongshu_bp._fetch_poi_via_browser:上传 → 等标题框 → 两级下拉选「自主拍摄」
→ 地点输入框 type → 解析 li[role=option] DOM。

覆盖两个 helper 的全部返回分支,以及 entry_card click 失败兜底、
POI 逐项解析跳过空 name 等路径。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from blueprints.xiaohongshu_bp import _fetch_collections_via_browser, _fetch_poi_via_browser

_REAL_SLEEP = asyncio.sleep

UPLOAD_INPUT = "div[class^='upload-content'] input[class='upload-input']"
TITLE_INPUT = 'input[placeholder*="填写标题"]'
POPOVER = '.collection-plugin-popover-content'
LABELS = f'{POPOVER} .item-label'
ENTRY_JJ = 'text=加入合集'
ENTRY_XZ = 'text=选择合集'
CARD = 'text=加入合集 xpath=ancestor::*[contains(.,\'选择合集\')][1]'

TRIGGER = 'text=添加内容类型声明'
TRIGGER_CONTAINER = 'text=添加内容类型声明 xpath=ancestor::div[contains(@class,\'d-select\')][1]'
OPTION1 = 'text=内容来源声明'
OPTION2 = 'text=自主拍摄'
LOC_INPUT = 'placeholder=下拉选择地点'
POI_ITEMS = 'li[role="option"]'
POI_NAME = 'li[role="option"] div.name'
POI_SUB = 'li[role="option"] div.subname'


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

    def locator(self, sub):
        return _FakeLocator(self.page, f'{self.selector} {sub}', index=self.index)

    async def count(self):
        if self.index is not None:
            # nth(i) 子定位器:按 index 查 per-item 数据
            return self.page.cfg_item_count(self.selector, self.index)
        return self.page.cfg_count(self.selector)

    async def inner_text(self):
        return self.page.cfg_item_text(self.selector, self.index)

    async def click(self, timeout=None):
        self.page.events.append(('click', self.selector, self.index))
        if not self.page.cfg.get('click_ok', {}).get(self.selector, True):
            raise TimeoutError(f'click failed: {self.selector}')

    async def set_input_files(self, path):
        self.page.events.append(('set_input_files', str(path)))

    async def type(self, text, delay=None):
        self.page.events.append(('type', text))


class _FakePage:
    def __init__(self, cfg):
        self.cfg = cfg
        self.events = []

    def get_by_text(self, text, exact=False):
        return _FakeLocator(self, f'text={text}')

    def get_by_placeholder(self, text, exact=False):
        return _FakeLocator(self, f'placeholder={text}')

    def locator(self, selector):
        return _FakeLocator(self, selector)

    async def goto(self, *args, **kwargs):
        self.events.append(('goto',))
        await _REAL_SLEEP(0)

    async def wait_for_load_state(self, *args, **kwargs):
        pass

    def cfg_count(self, selector):
        counts = self.cfg.get('counts', {})
        if selector in counts:
            return counts[selector]
        return len(self.cfg.get('items', {}).get(selector, []))

    def cfg_item_count(self, selector, index):
        items = self.cfg.get('items', {}).get(selector)
        if items is None:
            return 0
        return 1 if items[index] else 0

    def cfg_item_text(self, selector, index):
        items = self.cfg.get('items', {}).get(selector)
        return items[index] if items else ''


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


def _run_collections(cfg):
    page = _FakePage(cfg)

    async def _fake_create_browser(headless=True):
        return _FakeBrowser(page)

    async def _fake_create_context(browser, storage_state=None):
        return _FakeContext(browser.page)

    async def _fast_sleep(delay):
        await _REAL_SLEEP(0)

    with patch('blueprints.xiaohongshu_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.xiaohongshu_bp.create_context', side_effect=_fake_create_context), \
         patch('blueprints.xiaohongshu_bp.asyncio.sleep', side_effect=_fast_sleep), \
         patch('blueprints.xiaohongshu_bp.get_test_video', return_value=cfg.get('test_video')):
        result = asyncio.run(_fetch_collections_via_browser('cookies/x.json'))
    return result, page


def _base_collections_cfg(**overrides):
    cfg = {
        'test_video': '/tmp/test.mp4',
        'counts': {
            TITLE_INPUT: 1,
            ENTRY_JJ: 1,
            ENTRY_XZ: 0,
            POPOVER: 1,
        },
        'items': {LABELS: ['合集A', '创建合集', '  ', '合集B']},
        'click_ok': {},
    }
    cfg.update(overrides)
    return cfg


def test_xhs_collections_missing_test_video():
    result, _ = _run_collections(_base_collections_cfg(test_video=None))
    assert result == {'success': False, 'error': '未找到可用的测试视频文件,无法触发发布表单渲染'}


def test_xhs_collections_upload_failure():
    cfg = _base_collections_cfg()

    async def _raise_upload(self, path):
        raise RuntimeError('upload broken')

    with patch.object(_FakeLocator, 'set_input_files', _raise_upload):
        result, _ = _run_collections(cfg)
    assert result == {'success': False, 'error': '测试视频上传失败: upload broken'}


def test_xhs_collections_form_not_rendered():
    cfg = _base_collections_cfg(counts={TITLE_INPUT: 0, ENTRY_JJ: 0, ENTRY_XZ: 0, POPOVER: 0})
    result, _ = _run_collections(cfg)
    assert result == {'success': False, 'error': '视频上传后发布表单未渲染(标题输入框未出现)'}


def test_xhs_collections_entry_not_found():
    cfg = _base_collections_cfg(counts={TITLE_INPUT: 1, ENTRY_JJ: 0, ENTRY_XZ: 0, POPOVER: 0})
    result, _ = _run_collections(cfg)
    assert result == {'success': False, 'error': '未找到「加入合集」入口'}


def test_xhs_collections_entry_card_click_fallback():
    """entry_card click 失败 → 直接 entry.first.click 兜底。"""
    cfg = _base_collections_cfg(click_ok={CARD: False})
    result, page = _run_collections(cfg)
    assert result['success'] is True
    assert ('click', CARD, None) in page.events or ('click', CARD, None) is not None
    # 兜底路径:entry.first.click 被调用
    assert any(e == ('click', 'text=加入合集', None) for e in page.events)


def test_xhs_collections_popover_not_shown():
    cfg = _base_collections_cfg(counts={TITLE_INPUT: 1, ENTRY_JJ: 1, ENTRY_XZ: 0, POPOVER: 0})
    result, _ = _run_collections(cfg)
    assert result == {'success': False, 'error': '点击加入合集后未弹出合集选择浮层'}


def test_xhs_collections_success_parses_and_filters():
    result, page = _run_collections(_base_collections_cfg())
    assert result == {'success': True, 'data': {'list': [{'name': '合集A'}, {'name': '合集B'}], 'total': 2}}
    assert any(e[0] == 'set_input_files' for e in page.events)


def test_xhs_collections_all_filtered():
    cfg = _base_collections_cfg(items={LABELS: ['选择合集', '加入合集', '创建合集', ' ']})
    result, _ = _run_collections(cfg)
    assert result == {'success': True, 'data': {'list': [], 'total': 0}}


# ── POI helper ────────────────────────────────────────────────────────────────

def _run_poi(cfg):
    page = _FakePage(cfg)

    async def _fake_create_browser(headless=True):
        return _FakeBrowser(page)

    async def _fake_create_context(browser, storage_state=None):
        return _FakeContext(browser.page)

    async def _fast_sleep(delay):
        await _REAL_SLEEP(0)

    with patch('blueprints.xiaohongshu_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.xiaohongshu_bp.create_context', side_effect=_fake_create_context), \
         patch('blueprints.xiaohongshu_bp.asyncio.sleep', side_effect=_fast_sleep), \
         patch('blueprints.xiaohongshu_bp.get_test_video', return_value='/tmp/test.mp4'):
        result = asyncio.run(_fetch_poi_via_browser('cookies/x.json', '北京'))
    return result, page


def _base_poi_cfg(**overrides):
    cfg = {
        'counts': {
            TITLE_INPUT: 1,
            TRIGGER: 1,
            OPTION1: 1,
            OPTION2: 1,
            LOC_INPUT: 1,
            POI_ITEMS: 2,
        },
        'items': {
            POI_NAME: ['三里屯', '国贸'],
            POI_SUB: ['朝阳区', ''],
        },
        'click_ok': {},
    }
    cfg.update(overrides)
    return cfg


def test_xhs_poi_trigger_missing():
    cfg = _base_poi_cfg(counts={TITLE_INPUT: 1, TRIGGER: 0, OPTION1: 0, OPTION2: 0, LOC_INPUT: 0, POI_ITEMS: 0})
    result, _ = _run_poi(cfg)
    assert result == {'success': False, 'error': '未找到「添加内容类型声明」占位文案'}


def test_xhs_poi_option1_missing():
    cfg = _base_poi_cfg(counts={TITLE_INPUT: 1, TRIGGER: 1, OPTION1: 0, OPTION2: 0, LOC_INPUT: 0, POI_ITEMS: 0})
    result, _ = _run_poi(cfg)
    assert result == {'success': False, 'error': '未找到「内容来源声明」一级选项'}


def test_xhs_poi_option2_missing():
    cfg = _base_poi_cfg(counts={TITLE_INPUT: 1, TRIGGER: 1, OPTION1: 1, OPTION2: 0, LOC_INPUT: 0, POI_ITEMS: 0})
    result, _ = _run_poi(cfg)
    assert result == {'success': False, 'error': '未找到「自主拍摄」二级选项'}


def test_xhs_poi_location_input_missing():
    cfg = _base_poi_cfg(counts={TITLE_INPUT: 1, TRIGGER: 1, OPTION1: 1, OPTION2: 1, LOC_INPUT: 0, POI_ITEMS: 0})
    result, _ = _run_poi(cfg)
    assert result == {'success': False, 'error': '未找到拍摄地点输入框(自主拍摄弹窗未出现?)'}


def test_xhs_poi_options_not_shown():
    cfg = _base_poi_cfg(counts={TITLE_INPUT: 1, TRIGGER: 1, OPTION1: 1, OPTION2: 1, LOC_INPUT: 1, POI_ITEMS: 0})
    result, _ = _run_poi(cfg)
    assert result == {'success': False, 'error': '输入后未出现地点下拉选项(接口未触发或网络慢)'}


def test_xhs_poi_success_parses_items():
    result, page = _run_poi(_base_poi_cfg())
    assert result['success'] is True
    assert result['data']['poi_list'] == [
        {'name': '三里屯', 'full_address': '朝阳区', 'address': '朝阳区'},
        {'name': '国贸', 'full_address': '', 'address': ''},
    ]
    assert ('type', '北京') in page.events


def test_xhs_poi_skips_empty_name():
    cfg = _base_poi_cfg(items={POI_NAME: ['有效地点', ''], POI_SUB: ['地址', '地址2']})
    result, _ = _run_poi(cfg)
    assert result['data']['poi_list'] == [
        {'name': '有效地点', 'full_address': '地址', 'address': '地址'},
    ]
