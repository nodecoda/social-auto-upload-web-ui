"""视频号活动/位置搜索浏览器 helper 契约测试（T8b）。

_fetch_activities_via_browser / _fetch_locations_via_browser 同构:
点卡片 → 搜索框输入 → 等下拉(>1 项) → 跳过 index 0 → 解析。差异在
选择器与字段(活动: .activity-item-info .name/.creator-name;位置: .name/.desc)。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from blueprints.channels_bp import _fetch_activities_via_browser, _fetch_locations_via_browser

_REAL_SLEEP = asyncio.sleep

ACTIVITY_WRAP = 'div.post-activity-wrap'
POSITION_WRAP = 'div.position-display-wrap'
ACTIVITY_INPUT = 'input[placeholder="搜索活动"]'
POSITION_INPUT = 'input[placeholder="搜索附近位置"]'
OPTIONS = 'div.common-option-list-wrap .option-item'


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
            return 1 if self.page.cfg_item_text(self.selector, self.index) else 0
        return self.page.cfg_count(self.selector)

    async def inner_text(self):
        return self.page.cfg_item_text(self.selector, self.index)

    async def click(self):
        self.page.events.append(('click', self.selector))


class _FakePage:
    def __init__(self, cfg):
        self.cfg = cfg
        self.url = 'https://channels.weixin.qq.com/platform/post/edit'
        self.events = []

    def locator(self, selector):
        return _FakeLocator(self, selector)

    async def goto(self, *args, **kwargs):
        self.events.append(('goto',))
        await _REAL_SLEEP(0)

    async def wait_for_load_state(self, *args, **kwargs):
        pass

    def cfg_count(self, selector):
        return self.cfg.get('counts', {}).get(selector, 0)

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


def _run(fn, cfg):
    page = _FakePage(cfg)

    async def _fake_create_browser(headless=True):
        return _FakeBrowser(page)

    async def _fake_create_context(browser, storage_state=None):
        return _FakeContext(browser.page)

    async def _fast_sleep(delay):
        await _REAL_SLEEP(0)

    async def _fake_clear_and_type(page, text, delay=None):
        page.events.append(('typed', text))

    with patch('blueprints.channels_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.channels_bp.create_context', side_effect=_fake_create_context), \
         patch('blueprints.channels_bp.asyncio.sleep', side_effect=_fast_sleep), \
         patch('blueprints.channels_bp.clear_and_type', side_effect=_fake_clear_and_type):
        result = asyncio.run(fn('cookies/x.json', '关键词'))
    return result, page


# ── 活动搜索 ──────────────────────────────────────────────────────────────────

ACT_NAME = f'{OPTIONS} .activity-item-info .name'
ACT_CREATOR = f'{OPTIONS} .activity-item-info .creator-name'


def _act_cfg(**overrides):
    cfg = {
        'counts': {ACTIVITY_WRAP: 1, ACTIVITY_INPUT: 1, OPTIONS: 3},
        'items': {
            ACT_NAME: ['跳过项', '活动甲', '活动乙'],
            ACT_CREATOR: ['', '创作者A', '创作者B · '],
        },
    }
    cfg.update(overrides)
    return cfg


def test_activities_wrap_timeout():
    cfg = _act_cfg(counts={ACTIVITY_WRAP: 0, ACTIVITY_INPUT: 0, OPTIONS: 0})
    result, _ = _run(_fetch_activities_via_browser, cfg)
    assert result == {'success': False, 'error': '页面加载超时,未找到活动卡(div.post-activity-wrap)'}


def test_activities_input_missing():
    cfg = _act_cfg(counts={ACTIVITY_WRAP: 1, ACTIVITY_INPUT: 0, OPTIONS: 0})
    result, _ = _run(_fetch_activities_via_browser, cfg)
    assert result == {'success': False, 'error': '未找到活动搜索框(input[placeholder=搜索活动])'}


def test_activities_dropdown_missing():
    cfg = _act_cfg(counts={ACTIVITY_WRAP: 1, ACTIVITY_INPUT: 1, OPTIONS: 1})
    result, _ = _run(_fetch_activities_via_browser, cfg)
    assert result == {'success': False, 'error': '输入关键字后未出现活动下拉'}


def test_activities_success_skips_index0():
    result, page = _run(_fetch_activities_via_browser, _act_cfg())
    assert result == {'success': True, 'data': {'list': [
        {'activity_id': '活动甲|创作者A', 'name': '活动甲', 'creator_name': '创作者A'},
        {'activity_id': '活动乙|创作者B', 'name': '活动乙', 'creator_name': '创作者B'},
    ], 'total': 2}}
    assert ('typed', '关键词') in page.events


def test_activities_skips_empty_name():
    cfg = _act_cfg(items={ACT_NAME: ['跳过项', '', '活动丙'], ACT_CREATOR: ['', '', '创作者C']})
    result, _ = _run(_fetch_activities_via_browser, cfg)
    assert result['data']['list'] == [
        {'activity_id': '活动丙|创作者C', 'name': '活动丙', 'creator_name': '创作者C'},
    ]


# ── 位置搜索 ──────────────────────────────────────────────────────────────────

LOC_NAME = f'{OPTIONS} .location-item-info .name'
LOC_DESC = f'{OPTIONS} .location-item-info .desc'


def _loc_cfg(**overrides):
    cfg = {
        'counts': {POSITION_WRAP: 1, POSITION_INPUT: 1, OPTIONS: 3},
        'items': {
            LOC_NAME: ['跳过项', '三里屯', '国贸'],
            LOC_DESC: ['', '朝阳区', ''],
        },
    }
    cfg.update(overrides)
    return cfg


def test_locations_wrap_timeout():
    cfg = _loc_cfg(counts={POSITION_WRAP: 0, POSITION_INPUT: 0, OPTIONS: 0})
    result, _ = _run(_fetch_locations_via_browser, cfg)
    assert result == {'success': False, 'error': '页面加载超时,未找到位置卡(div.position-display-wrap)'}


def test_locations_input_missing():
    cfg = _loc_cfg(counts={POSITION_WRAP: 1, POSITION_INPUT: 0, OPTIONS: 0})
    result, _ = _run(_fetch_locations_via_browser, cfg)
    assert result == {'success': False, 'error': '未找到位置搜索框(input[placeholder=搜索附近位置])'}


def test_locations_dropdown_missing():
    cfg = _loc_cfg(counts={POSITION_WRAP: 1, POSITION_INPUT: 1, OPTIONS: 1})
    result, _ = _run(_fetch_locations_via_browser, cfg)
    assert result == {'success': False, 'error': '输入关键字后未出现位置下拉'}


def test_locations_success_skips_index0():
    result, page = _run(_fetch_locations_via_browser, _loc_cfg())
    assert result == {'success': True, 'data': {'list': [
        {'name': '三里屯', 'desc': '朝阳区'},
        {'name': '国贸', 'desc': ''},
    ], 'total': 2}}
    assert ('typed', '关键词') in page.events


def test_locations_skips_empty_name():
    cfg = _loc_cfg(items={LOC_NAME: ['跳过项', '', '望京'], LOC_DESC: ['', '', '朝阳']})
    result, _ = _run(_fetch_locations_via_browser, cfg)
    assert result['data']['list'] == [{'name': '望京', 'desc': '朝阳'}]
