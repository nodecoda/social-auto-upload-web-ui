"""淘宝光合 platform.py DOM 交互层契约测试（T38）。

覆盖 impl/taobao_guanghe/platform.py（934 stmts，基线 13%）—— 与
test_taobao_guanghe_publish.py（编排层）/ test_taobao_picker_routes.py（picker 路由）
互补，目标合并覆盖率 ~100%：

- 模块级纯逻辑/helper: _group_by_trace（分组保序/空 trace 归并）
  / _replay_groups（legacy 回退/多组重现/tab/筛选/搜索/加载更多/disabled/
  未找到/确认按钮全分支） / _legacy_link_by_title（radio/trigger/平台优选 tab/
  span[title] 匹配 disabled/clicked/already/not_found/异常包装/确认按钮）
- 登录/校验/同步: login（URL 回跳成功/URL 读取异常清理/save_login_result 异常/
  close 异常吞掉） / check_cookie（失效 marker/有效/其他 URL/load_state 超时/
  close 异常吞掉） / sync_profile（正常/全空日志/抓取异常/goto 异常/close 异常吞掉）
  / _login_stats_fn / _scrape_profile_and_stats（正常/None/evaluate 异常）
  / _build_stats（千分位/小数/空串/非法数字/未知项跳过）
- 编排: publish_video 长参数截断 / _upload_single_video 全流程（happy 全参数/
  最小流/发布失败/cookie 失效 raise/截图异常/storage_state 异常/close_browser 异常/
  DRY_RUN 分支）
- DOM 辅助: _dismiss_guide_modal（无引导/我知道了/下一步/关闭按钮/残留/外层异常）
  / _navigate_to_publish_page（hover/click/JS dispatch 三策略/新 tab 捕获/
  URL 就绪/兜底返回/全失败 raise） / _find_publish_frame（找到/about:blank 诊断/
  locator 异常/主 frame 兜底） / _upload_video_file（三策略/全失败 raise/
  容器未出现） / _wait_upload_complete（成功封面/上传失败 raise/进度出现再消失/
  封面已生成/进度日志/状态检查异常/进度文本异常）
  / _set_cover（文件缺失早退/happy/编辑按钮兜底/本地上传缺失 raise/file chooser/
  file chooser 失败回退/勾选已选中/选择图片异常/确定下一步异常/Escape 兜底）
  / _fill_title（空/截断 30/异常） / _fill_desc_and_tags（空/标签解析/预算截断/
  happy/异常） / _set_claim（非法值默认/合法值/异常）
  / _set_schedule_time（非 datetime 早退/JS radio/兜底 radio/双双失败/disabled 日志/
  ymd/hms/确定/异常兜底） / _link_products_or_shops（空/委托）
  / _click_publish（主 page 跳转成功/60s 超时按成功/evaluate 点击/全失败 False/
  wait_for 异常 False/main_page=None 用 frame.url）
  / open_creator_center（线程启动/wait_for_event 异常/browser.close 异常）
"""
import asyncio
import os
import sys
import tempfile
import time as _time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from impl.taobao_guanghe import _link_ops
from impl.taobao_guanghe.platform import (
    _COOKIE_INVALID_MARKERS,
    _GUANGHE_HOME_URL,
    _HOME_HOST,
    TaobaoGuanghePlatform,
    _group_by_trace,
    _legacy_link_by_title,
    _replay_groups,
    scrape_taobao_guanghe_profile,
)

_LOGIN_URL = "https://login.taobao.com/member/login.jhtml"
_PUBLISH_URL = (
    "https://creator.guanghe.taobao.com/page/pubNew/video?pub_url=xxx&pub_scene=gg"
)
_SUCCESS_URL = (
    "https://creator.guanghe.taobao.com/page/workspace/tb?type=video"
)
_CONFIRM_SEL = (
    '.next-btn-primary:has-text("确定"), '
    '.next-btn-primary:has-text("完成"), '
    '.next-btn-primary:has-text("确认")'
)


def _run(coro):
    return asyncio.run(coro)


def _mk_platform():
    return TaobaoGuanghePlatform()


def _mk_leaf():
    """叶子 locator：所有异步方法默认成功；locator(sel) 返回稳定可预配置对象。"""
    loc = MagicMock()
    loc.count = AsyncMock(return_value=0)
    loc.click = AsyncMock()
    loc.hover = AsyncMock()
    loc.wait_for = AsyncMock()
    loc.set_input_files = AsyncMock()
    loc.get_attribute = AsyncMock(return_value=None)
    loc.inner_text = AsyncMock(return_value='')
    loc.text_content = AsyncMock(return_value='')
    loc.is_visible = AsyncMock(return_value=True)
    loc.is_checked = AsyncMock(return_value=False)
    loc.fill = AsyncMock()
    loc.press = AsyncMock()
    loc.press_sequentially = AsyncMock()
    loc.evaluate = AsyncMock(return_value='')
    loc.scroll_into_view_if_needed = AsyncMock()
    subs = defaultdict(_mk_leaf)
    nth_subs = defaultdict(_mk_leaf)
    loc.locator = MagicMock(
        side_effect=lambda sel, **kw: subs.setdefault(sel, _mk_leaf())
    )
    loc.subs = subs
    loc.nth = MagicMock(side_effect=lambda i: nth_subs.setdefault(i, _mk_leaf()))
    loc.nth_subs = nth_subs
    filters = defaultdict(_mk_leaf)
    loc.filter = MagicMock(
        side_effect=lambda **kw: filters.setdefault(repr(sorted(kw.items())), _mk_leaf())
    )
    loc.filters = filters
    return loc


def _mk_locator():
    loc = _mk_leaf()
    loc.first = _mk_leaf()
    loc.last = _mk_leaf()
    return loc


def _mk_page(url=_PUBLISH_URL):
    """页面/frame 通用 fake：locator/get_by_text 返回稳定可配置对象。"""
    page = MagicMock()
    page.url = url
    page.page = page
    page.main_frame = MagicMock()
    page.context = MagicMock()
    page.context.pages = []
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_event = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.query_selector_all = AsyncMock(return_value=[])
    page.frame_locator = MagicMock()
    page.frames = []
    page.evaluate = AsyncMock(return_value={})
    page.close = AsyncMock()
    page.screenshot = AsyncMock()
    page.on = MagicMock()
    page.expect_file_chooser = MagicMock()
    by_text = {}
    page.get_by_text = MagicMock(
        side_effect=lambda text, exact=False: by_text.setdefault(text, _mk_locator())
    )
    page.by_text = by_text
    page.get_by_role = MagicMock(return_value=_mk_locator())
    locators = {}
    page.locator = MagicMock(
        side_effect=lambda sel, **kw: locators.setdefault(sel, _mk_locator())
    )
    page.locators = locators
    return page


def _loc(page, sel):
    page.locator(sel)
    return page.locators[sel]


def _txt(page, text):
    page.get_by_text(text, exact=True)
    return page.by_text[text]


class _ChangedUrl:
    """page.url 替身：与原地址比较恒不相等（驱动跳转判据）。"""

    def __ne__(self, other):
        return True


class _HomeUrl:
    """登录轮询替身：判定 home host 命中、login marker 不命中。"""

    def __contains__(self, other):
        return other == _HOME_HOST


class _SeqUrlPage(MagicMock):
    """url 按读取顺序返回序列值；序列耗尽重复末值。"""

    def __init__(self, urls):
        super().__init__()
        self._url_seq = list(urls)

    @property
    def url(self):
        return self._url_seq.pop(0) if len(self._url_seq) > 1 else self._url_seq[0]


class _RaiseUrlPage(MagicMock):
    """读取 url 时抛异常（驱动 login 轮询异常清理分支）。"""

    @property
    def url(self):
        raise RuntimeError('url read failed')


class _AwaitableValue:
    """可 await 的值容器:模拟 Playwright FileChooserInfo.value(coroutine)。"""

    def __init__(self, value):
        self._value = value

    def __await__(self):
        yield
        return self._value


class _FakeLoop:
    """时间序列控制：所有 deadline 轮询都依赖 loop.time()。"""

    def __init__(self, times):
        self._times = list(times)

    def time(self):
        return self._times.pop(0) if len(self._times) > 1 else self._times[0]


@contextmanager
def _mk_time(*times):
    """注入 fake loop.time() 序列 + patch asyncio.sleep。"""
    loop = _FakeLoop(list(times))
    with patch('impl.taobao_guanghe.platform.asyncio.get_event_loop', return_value=loop), \
         patch('asyncio.sleep', AsyncMock()):
        yield loop


@contextmanager
def _mk_browser_chain(platform, url=_PUBLISH_URL):
    """patch create_browser/create_context,返回 (page, context, browser)。"""
    page = _mk_page(url=url)
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.storage_state = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    with patch.object(platform, 'create_browser', AsyncMock(return_value=browser)), \
         patch.object(platform, 'create_context', AsyncMock(return_value=context)):
        yield page, context, browser


def _mk_cover_file():
    fd, path = tempfile.mkstemp(prefix='sau_tbg_cover_', suffix='.png')
    os.close(fd)
    return path


@contextmanager
def _mk_upload_flow(p, page_url=_PUBLISH_URL, sub_steps=None):
    """_upload_single_video 编排测试:mock 全部子步骤 + browser chain。"""
    page = _mk_page(url=page_url)
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.storage_state = AsyncMock()
    browser = MagicMock()
    browser.close = AsyncMock()
    steps = dict(
        dismiss_guide_modal=AsyncMock(),
        find_publish_frame=AsyncMock(return_value=page),
        upload_video_file=AsyncMock(),
        wait_upload_complete=AsyncMock(),
        set_cover=AsyncMock(),
        fill_title=AsyncMock(),
        fill_desc_and_tags=AsyncMock(),
        set_claim=AsyncMock(),
        set_schedule_time=AsyncMock(),
        link_products_or_shops=AsyncMock(),
        click_publish=AsyncMock(return_value=True),
        close_browser=AsyncMock(),
    )
    if sub_steps:
        steps.update(sub_steps)
    patches = [
        patch.object(p, '_dismiss_guide_modal', steps['dismiss_guide_modal']),
        patch.object(p, '_find_publish_frame', steps['find_publish_frame']),
        patch.object(p, '_upload_video_file', steps['upload_video_file']),
        patch.object(p, '_wait_upload_complete', steps['wait_upload_complete']),
        patch.object(p, '_set_cover', steps['set_cover']),
        patch.object(p, '_fill_title', steps['fill_title']),
        patch.object(p, '_fill_desc_and_tags', steps['fill_desc_and_tags']),
        patch.object(p, '_set_claim', steps['set_claim']),
        patch.object(p, '_set_schedule_time', steps['set_schedule_time']),
        patch.object(p, '_link_products_or_shops', steps['link_products_or_shops']),
        patch.object(p, '_click_publish', steps['click_publish']),
        patch.object(p, 'close_browser', steps['close_browser']),
        patch.object(p, 'create_browser', AsyncMock(return_value=browser)),
        patch.object(p, 'create_context', AsyncMock(return_value=context)),
        patch('asyncio.sleep', AsyncMock()),
        patch('impl.taobao_guanghe.platform.logger'),
    ]
    for pm in patches:
        pm.start()
    try:
        yield page, context, browser, steps
    finally:
        for pm in reversed(patches):
            pm.stop()


# ── 模块级纯逻辑: _group_by_trace ─────────────────────────────────────────

class TestGroupByTrace:
    def test_groups_by_signature_preserves_order(self):
        items = [
            {'id': 1, 'trace': {'tab': 'preferred', 'keyword': 'k'}},
            {'id': 2, 'trace': {'tab': 'bought'}},
            {'id': 3, 'trace': {'tab': 'preferred', 'keyword': 'k'}},
        ]
        groups = _group_by_trace(items)
        assert [g[1][0]['id'] for g in groups] == [1, 2]
        assert groups[0][1] == [items[0], items[2]]
        assert groups[0][0] == {'tab': 'preferred', 'keyword': 'k'}

    def test_trace_none_merged_into_empty_signature(self):
        items = [
            {'id': 1},
            {'id': 2, 'trace': None},
            {'id': 3, 'trace': {'tab': 'preferred'}},
        ]
        groups = _group_by_trace(items)
        # id 1/2 无 trace → 同一空签名组
        assert groups[0][1] == [items[0], items[1]]
        assert groups[0][0] == {}
        assert groups[1][0] == {'tab': 'preferred'}

    def test_empty_items(self):
        assert _group_by_trace([]) == []


# ── 模块级: _replay_groups ────────────────────────────────────────────────

class TestReplayGroups:
    @contextmanager
    def _patch_link_ops(self):
        """patch _link_ops 的 DOM 原子操作,返回 (locate, load_more, ctx)。"""
        with patch.object(_link_ops, 'switch_radio', AsyncMock()) as sr, \
             patch.object(_link_ops, 'click_add_card', AsyncMock()) as cac, \
             patch.object(_link_ops, 'wait_panel_ready', AsyncMock()) as wpr, \
             patch.object(_link_ops, 'switch_tab', AsyncMock()) as st, \
             patch.object(_link_ops, 'click_filter', AsyncMock()) as cf, \
             patch.object(_link_ops, 'search', AsyncMock()) as se, \
             patch.object(_link_ops, 'locate_and_check', AsyncMock()) as locate, \
             patch.object(_link_ops, 'load_more', AsyncMock(return_value=False)) as lm, \
             patch('impl.taobao_guanghe.platform.logger'):
            yield locate, lm, sr, cac, wpr, st, cf, se

    def _items(self):
        return [
            {'id': '1', 'trace': {'tab': 'preferred', 'keyword': 'kw', 'rule': '全部', 'category': '全部'}},
            {'id': '2', 'trace': {'tab': 'preferred', 'keyword': 'kw', 'rule': '全部', 'category': '全部'}},
        ]

    def test_product_single_group_all_found_and_confirm_clicked(self):
        frame = _mk_page()
        with self._patch_link_ops() as (locate, _lm, sr, cac, wpr, st, cf, se):
            captured = []

            def _loc_side(_frame, _type, pending):
                captured.append(set(pending))
                return {'checked': ['1'], 'already': ['2'], 'disabled': [], 'missing': []}

            locate.side_effect = _loc_side
            _loc(frame, _CONFIRM_SEL).first.count = AsyncMock(return_value=1)
            _loc(frame, _CONFIRM_SEL).first.is_visible = AsyncMock(return_value=True)
            _run(_replay_groups(frame, 'product', self._items()))
        sr.assert_awaited_once_with(frame, 'product')
        cac.assert_awaited_once_with(frame, 'product')
        wpr.assert_awaited_once_with(frame, 'product')
        st.assert_awaited_once_with(frame, 'preferred')
        assert cf.await_count == 2
        se.assert_awaited_once_with(frame, 'kw')
        _loc(frame, _CONFIRM_SEL).first.click.assert_awaited_once()
        assert captured == [{'1', '2'}]

    def test_legacy_path_without_trace(self):
        frame = _mk_page()
        items = [{'id': '1', 'title': '旧商品'}]
        with self._patch_link_ops() as (_locate, _lm, _sr, _cac, _wpr, _st, _cf, _se), \
             patch('impl.taobao_guanghe.platform._legacy_link_by_title', AsyncMock()) as legacy:
            _run(_replay_groups(frame, 'product', items))
        legacy.assert_awaited_once_with(frame, 'product', items)
        # legacy 路径不应打开面板
        _sr.assert_not_awaited()

    def test_shop_skips_tab_and_filter(self):
        frame = _mk_page()
        items = [{'id': 's1', 'trace': {'keyword': '店铺名'}}]
        with self._patch_link_ops() as (locate, _lm, _sr, cac, _wpr, st, cf, se):
            locate.return_value = {'checked': ['s1'], 'already': [], 'disabled': [], 'missing': []}
            _run(_replay_groups(frame, 'shop', items))
        st.assert_not_awaited()
        cf.assert_not_awaited()
        se.assert_awaited_once_with(frame, '店铺名')
        cac.assert_awaited_once_with(frame, 'shop')

    def test_empty_rule_category_skips_filters(self):
        frame = _mk_page()
        items = [{'id': '1', 'trace': {'tab': 'bought', 'keyword': ''}}]
        with self._patch_link_ops() as (locate, _lm, _sr, _cac, _wpr, st, cf, se):
            locate.return_value = {'checked': ['1'], 'already': [], 'disabled': [], 'missing': []}
            _run(_replay_groups(frame, 'product', items))
        st.assert_awaited_once_with(frame, 'bought')
        cf.assert_not_awaited()
        se.assert_awaited_once_with(frame, '')

    def test_tab_missing_defaults_preferred(self):
        frame = _mk_page()
        items = [{'id': '1', 'trace': {'keyword': ''}}]
        with self._patch_link_ops() as (locate, _lm, _sr, _cac, _wpr, st, _cf, _se):
            locate.return_value = {'checked': ['1'], 'already': [], 'disabled': [], 'missing': []}
            _run(_replay_groups(frame, 'product', items))
        st.assert_awaited_once_with(frame, 'preferred')

    def test_disabled_raises(self):
        frame = _mk_page()
        with self._patch_link_ops() as (locate, _lm, _sr, _cac, _wpr, _st, _cf, _se):
            locate.return_value = {'checked': [], 'already': [], 'disabled': ['9'], 'missing': []}
            with pytest.raises(RuntimeError, match='商品不可选'):
                _run(_replay_groups(frame, 'product', self._items()))

    def test_not_found_load_more_then_found(self):
        frame = _mk_page()
        with self._patch_link_ops() as (locate, lm, _sr, _cac, _wpr, _st, _cf, _se):
            locate.side_effect = [
                {'checked': [], 'already': [], 'disabled': [], 'missing': ['1', '2']},
                {'checked': ['1'], 'already': ['2'], 'disabled': [], 'missing': []},
            ]
            lm.return_value = True
            _run(_replay_groups(frame, 'product', self._items()))
        assert lm.await_count == 1

    def test_not_found_no_more_button_raises(self):
        frame = _mk_page()
        with self._patch_link_ops() as (locate, lm, _sr, _cac, _wpr, _st, _cf, _se):
            locate.return_value = {'checked': [], 'already': [], 'disabled': [], 'missing': ['1']}
            lm.return_value = False
            with pytest.raises(RuntimeError, match='未找到的商品 id'):
                _run(_replay_groups(frame, 'product', self._items()))
        lm.assert_awaited_once()

    def test_max_load_more_exhausted_raises(self):
        frame = _mk_page()
        with self._patch_link_ops() as (locate, lm, _sr, _cac, _wpr, _st, _cf, _se):
            locate.return_value = {'checked': [], 'already': [], 'disabled': [], 'missing': ['1']}
            lm.return_value = True
            with pytest.raises(RuntimeError, match='超过 2 次加载更多'):
                _run(_replay_groups(frame, 'product', self._items(), max_load_more=2))
        assert lm.await_count == 2

    def test_confirm_button_missing_ok(self):
        frame = _mk_page()
        with self._patch_link_ops() as (locate, _lm, _sr, _cac, _wpr, _st, _cf, _se):
            locate.return_value = {'checked': ['1', '2'], 'already': [], 'disabled': [], 'missing': []}
            _run(_replay_groups(frame, 'product', self._items()))
        _loc(frame, _CONFIRM_SEL).first.click.assert_not_awaited()

    def test_confirm_exception_logged(self):
        frame = _mk_page()
        with self._patch_link_ops() as (locate, _lm, _sr, _cac, _wpr, _st, _cf, _se), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            locate.return_value = {'checked': ['1', '2'], 'already': [], 'disabled': [], 'missing': []}
            _loc(frame, _CONFIRM_SEL).first.count = AsyncMock(side_effect=RuntimeError('boom'))
            _run(_replay_groups(frame, 'product', self._items()))
        assert any('确定按钮异常' in str(c) for c in logger.info.call_args_list)

    def test_multi_group_replays_each(self):
        frame = _mk_page()
        items = [
            {'id': '1', 'trace': {'tab': 'preferred', 'keyword': 'k1', 'rule': '全部', 'category': '全部'}},
            {'id': '2', 'trace': {'tab': 'bought', 'keyword': 'k2'}},
        ]
        with self._patch_link_ops() as (locate, _lm, _sr, _cac, _wpr, st, cf, se):
            locate.side_effect = [
                {'checked': ['1'], 'already': [], 'disabled': [], 'missing': []},
                {'checked': ['2'], 'already': [], 'disabled': [], 'missing': []},
            ]
            _run(_replay_groups(frame, 'product', items))
        assert st.await_count == 2
        assert [c.args[1] for c in se.await_args_list] == ['k1', 'k2']
        assert cf.await_count == 2  # 仅第一组有 rule+category 两项筛选


# ── 模块级: _legacy_link_by_title ─────────────────────────────────────────

class TestLegacyLinkByTitle:
    def test_no_names_early_return(self):
        frame = _mk_page()
        with patch('impl.taobao_guanghe.platform.logger'):
            _run(_legacy_link_by_title(frame, 'product', [{'id': '1'}]))
        frame.locator.assert_not_called()

    def test_radio_timeout_returns(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("商品")').first.wait_for = AsyncMock(
            side_effect=TimeoutError('slow')
        )
        with patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))
        assert any('radio 切换失败' in str(c) for c in logger.info.call_args_list)
        _loc(frame, '.next-radio-label:has-text("商品")').first.click.assert_not_awaited()

    def test_radio_already_checked_skips_click(self):
        frame = _mk_page()
        radio = _loc(frame, '.next-radio-label:has-text("商品")').first
        radio.evaluate = AsyncMock(return_value=True)
        _txt(frame, '添加商品')
        frame.evaluate = AsyncMock(return_value='clicked')
        with patch('asyncio.sleep', AsyncMock()), patch('impl.taobao_guanghe.platform.logger'):
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))
        radio.click.assert_not_awaited()
        assert radio.evaluate.await_count == 1

    def test_radio_unchecked_clicks(self):
        frame = _mk_page()
        radio = _loc(frame, '.next-radio-label:has-text("商品")').first
        radio.evaluate = AsyncMock(return_value='')
        frame.evaluate = AsyncMock(return_value='clicked')
        with patch('asyncio.sleep', AsyncMock()), patch('impl.taobao_guanghe.platform.logger'):
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))
        radio.click.assert_awaited_once()

    def test_trigger_timeout_returns(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("商品")').first.evaluate = AsyncMock(return_value=True)
        _txt(frame, '添加商品').first.wait_for = AsyncMock(side_effect=TimeoutError('slow'))
        with patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))
        assert any('添加卡点击失败' in str(c) for c in logger.info.call_args_list)

    def test_product_tab_inactive_clicks(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("商品")').first.evaluate = AsyncMock(return_value=True)
        tab = _loc(frame, '.next-tabs-tab:has-text("平台优选")').first
        tab.count = AsyncMock(return_value=1)
        tab.evaluate = AsyncMock(return_value='')
        inp = _loc(frame, 'input[role="searchbox"]').first
        frame.evaluate = AsyncMock(return_value='clicked')
        with patch('asyncio.sleep', AsyncMock()), patch('impl.taobao_guanghe.platform.logger'):
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))
        tab.click.assert_awaited_once()
        inp.fill.assert_awaited()
        inp.press.assert_awaited_with('Enter')
        assert frame.evaluate.await_count == 1

    def test_product_tab_active_skips_click(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("商品")').first.evaluate = AsyncMock(return_value=True)
        tab = _loc(frame, '.next-tabs-tab:has-text("平台优选")').first
        tab.count = AsyncMock(return_value=1)
        tab.evaluate = AsyncMock(return_value=True)
        frame.evaluate = AsyncMock(return_value='already')
        with patch('asyncio.sleep', AsyncMock()), patch('impl.taobao_guanghe.platform.logger'):
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))
        tab.click.assert_not_awaited()

    def test_product_tab_exception_swallowed(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("商品")').first.evaluate = AsyncMock(return_value=True)
        _loc(frame, '.next-tabs-tab:has-text("平台优选")').first.count = AsyncMock(
            side_effect=RuntimeError('boom')
        )
        frame.evaluate = AsyncMock(return_value='clicked')
        with patch('asyncio.sleep', AsyncMock()), patch('impl.taobao_guanghe.platform.logger'):
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))
        assert frame.evaluate.await_count == 1  # tab 异常后继续搜索循环

    def test_shop_type_no_tab_and_radio_checked(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("店铺")').first.evaluate = AsyncMock(return_value=True)
        frame.evaluate = AsyncMock(return_value='already')
        with patch('asyncio.sleep', AsyncMock()), patch('impl.taobao_guanghe.platform.logger'):
            _run(_legacy_link_by_title(frame, 'shop', [{'title': '店铺A'}]))
        _loc(frame, '.next-tabs-tab:has-text("平台优选")').first.count.assert_not_awaited()
        assert frame.evaluate.await_count == 1

    def test_loop_clicked_and_already_counts(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("商品")').first.evaluate = AsyncMock(return_value=True)
        frame.evaluate = AsyncMock(side_effect=['clicked', 'already'])
        with patch('asyncio.sleep', AsyncMock()), patch('impl.taobao_guanghe.platform.logger'):
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}, {'title': 'B'}]))
        assert frame.evaluate.await_count == 2

    def test_disabled_raises(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("商品")').first.evaluate = AsyncMock(return_value=True)
        frame.evaluate = AsyncMock(return_value='disabled')
        with patch('asyncio.sleep', AsyncMock()), \
                patch('impl.taobao_guanghe.platform.logger'), \
                pytest.raises(RuntimeError, match='商品不可选'):
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))

    def test_not_found_raises(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("商品")').first.evaluate = AsyncMock(return_value=True)
        frame.evaluate = AsyncMock(return_value='not_found')
        with patch('asyncio.sleep', AsyncMock()), \
                patch('impl.taobao_guanghe.platform.logger'), \
                pytest.raises(RuntimeError, match='未找到匹配'):
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))

    def test_evaluate_exception_wrapped(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("商品")').first.evaluate = AsyncMock(return_value=True)
        frame.evaluate = AsyncMock(side_effect=ValueError('js boom'))
        with patch('asyncio.sleep', AsyncMock()), \
                patch('impl.taobao_guanghe.platform.logger'), \
                pytest.raises(RuntimeError, match='关联异常'):
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))

    def test_confirm_clicked(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("商品")').first.evaluate = AsyncMock(return_value=True)
        frame.evaluate = AsyncMock(return_value='clicked')
        confirm = _loc(frame, _CONFIRM_SEL).first
        confirm.count = AsyncMock(return_value=1)
        confirm.is_visible = AsyncMock(return_value=True)
        with patch('asyncio.sleep', AsyncMock()), patch('impl.taobao_guanghe.platform.logger'):
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))
        confirm.click.assert_awaited_once()

    def test_confirm_exception_swallowed(self):
        frame = _mk_page()
        _loc(frame, '.next-radio-label:has-text("商品")').first.evaluate = AsyncMock(return_value=True)
        frame.evaluate = AsyncMock(return_value='clicked')
        _loc(frame, _CONFIRM_SEL).first.count = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), patch('impl.taobao_guanghe.platform.logger'):
            _run(_legacy_link_by_title(frame, 'product', [{'title': 'A'}]))  # 不抛异常


# ── login ─────────────────────────────────────────────────────────────────

class TestLogin:
    def _chain(self, page):
        browser = MagicMock()
        browser.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        return browser, context

    def test_success_url_back_home(self):
        p = _mk_platform()
        page = _mk_page(url=_LOGIN_URL)
        page.url = _HomeUrl()
        queue = MagicMock()
        browser, context = self._chain(page)
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.save_login_result', AsyncMock()) as slr, \
             patch('impl.taobao_guanghe.platform.logger'):
            _run(p.login('u1', queue, account_id='acc1'))
        page.goto.assert_awaited_once_with(_GUANGHE_HOME_URL)
        slr.assert_awaited_once()
        kw = slr.await_args.kwargs
        assert kw['platform_id'] == 18
        assert kw['platform_name'] == '淘宝光合'
        assert kw['account_id'] == 'acc1'
        assert kw['scrape_fn'] is scrape_taobao_guanghe_profile
        assert kw['stats_fn'].__func__ is TaobaoGuanghePlatform._login_stats_fn
        browser.close.assert_awaited_once()  # 成功才关
        page.close.assert_awaited_once()
        context.close.assert_awaited_once()

    def test_url_read_exception_cleans_up_without_browser_close(self):
        p = _mk_platform()
        page = _RaiseUrlPage()
        page.goto = AsyncMock()
        page.close = AsyncMock()
        queue = MagicMock()
        browser, context = self._chain(page)
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.save_login_result', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'), pytest.raises(RuntimeError, match='url read failed'):
            _run(p.login('u1', queue))
        page.close.assert_awaited_once()
        context.close.assert_awaited_once()
        browser.close.assert_not_awaited()

    def test_save_login_result_error_no_browser_close(self):
        p = _mk_platform()
        page = _mk_page(url=_LOGIN_URL)
        page.url = _HomeUrl()
        queue = MagicMock()
        browser, context = self._chain(page)
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.save_login_result',
                   AsyncMock(side_effect=RuntimeError('db fail'))), \
             patch('impl.taobao_guanghe.platform.logger'), pytest.raises(RuntimeError, match='db fail'):
            _run(p.login('u1', queue))
        browser.close.assert_not_awaited()
        page.close.assert_awaited_once()
        context.close.assert_awaited_once()

    def test_close_errors_swallowed(self):
        p = _mk_platform()
        page = _mk_page(url=_LOGIN_URL)
        page.url = _HomeUrl()
        page.close = AsyncMock(side_effect=RuntimeError('boom'))
        queue = MagicMock()
        browser, context = self._chain(page)
        context.close = AsyncMock(side_effect=RuntimeError('boom'))
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.save_login_result', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            _run(p.login('u1', queue))  # 不抛异常
        browser.close.assert_awaited_once()


# ── check_cookie ──────────────────────────────────────────────────────────

class TestCheckCookie:
    def _check(self, p, page, wait_timeout=False):
        browser = MagicMock()
        browser.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        if wait_timeout:
            page.wait_for_load_state = AsyncMock(side_effect=TimeoutError('slow'))
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            result = _run(p.check_cookie('ck.json'))
        return result, browser, page, context

    def test_invalid_marker_redirect(self):
        p = _mk_platform()
        page = _mk_page(url=_COOKIE_INVALID_MARKERS[0] + '/x')
        result, browser, _page, _ctx = self._check(p, page)
        assert result is False
        browser.close.assert_awaited_once()

    def test_home_valid(self):
        p = _mk_platform()
        page = _mk_page(url=_GUANGHE_HOME_URL)
        result, _browser, page, _ctx = self._check(p, page)
        assert result is True
        page.goto.assert_awaited_once_with(_GUANGHE_HOME_URL)

    def test_other_url_invalid(self):
        p = _mk_platform()
        page = _mk_page(url='https://example.com/weird')
        result, _browser, _page, _ctx = self._check(p, page)
        assert result is False

    def test_load_state_timeout_still_checks_url(self):
        p = _mk_platform()
        page = _mk_page(url=_GUANGHE_HOME_URL)
        result, _browser, page, _ctx = self._check(p, page, wait_timeout=True)
        assert result is True

    def test_close_errors_swallowed(self):
        p = _mk_platform()
        page = _mk_page(url=_GUANGHE_HOME_URL)
        page.close = AsyncMock(side_effect=RuntimeError('boom'))
        browser = MagicMock()
        browser.close = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock(side_effect=RuntimeError('boom'))
        with patch.object(p, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(p, 'create_context', AsyncMock(return_value=context)), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            assert _run(p.check_cookie('ck.json')) is True
        browser.close.assert_awaited_once()


# ── sync_profile ──────────────────────────────────────────────────────────

class TestSyncProfile:
    _RAW: ClassVar[list] = [
        {'name': '粉丝', 'num': '1,234'},
        {'name': '关注', 'num': '56'},
        {'name': '获赞', 'num': '999'},
        {'name': '未知项', 'num': '9'},
    ]

    def test_happy(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser), \
             patch.object(p, '_scrape_profile_and_stats',
                          AsyncMock(return_value=('昵称', 'http://a.png', self._RAW))), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            res = _run(p.sync_profile('ck.json'))
        assert res['name'] == '昵称'
        assert res['avatar'] == 'http://a.png'
        by_name = {s['NAME']: s for s in res['stats']}
        assert by_name['粉丝']['COUNT'] == 1234
        assert by_name['关注']['COUNT'] == 56
        assert by_name['获赞']['COUNT'] == 999
        assert len(res['stats']) == 3  # 未知项被丢弃
        page.goto.assert_awaited_once()
        browser.close.assert_awaited_once()

    def test_all_empty_logs_and_returns(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser), \
             patch.object(p, '_scrape_profile_and_stats',
                          AsyncMock(return_value=('', '', []))), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': []}
        assert any('抓取为空' in str(c) for c in logger.info.call_args_list)

    def test_scrape_exception_returns_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (_page, _context, _browser), \
             patch.object(p, '_scrape_profile_and_stats',
                          AsyncMock(side_effect=RuntimeError('boom'))), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': []}
        assert any('同步资料失败' in str(c) for c in logger.info.call_args_list)

    def test_goto_exception_returns_empty(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, _browser), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            page.goto = AsyncMock(side_effect=RuntimeError('net'))
            res = _run(p.sync_profile('ck.json'))
        assert res == {'name': '', 'avatar': '', 'stats': []}

    def test_load_state_timeout_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, _context, browser), \
             patch.object(p, '_scrape_profile_and_stats',
                          AsyncMock(return_value=('n', 'a', []))), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            page.wait_for_load_state = AsyncMock(side_effect=TimeoutError('slow'))
            res = _run(p.sync_profile('ck.json'))
        assert res['name'] == 'n'
        browser.close.assert_awaited_once()

    def test_close_errors_swallowed(self):
        p = _mk_platform()
        with _mk_browser_chain(p) as (page, context, browser), \
             patch.object(p, '_scrape_profile_and_stats',
                          AsyncMock(return_value=('n', '', []))), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            page.close = AsyncMock(side_effect=RuntimeError('boom'))
            context.close = AsyncMock(side_effect=RuntimeError('boom'))
            res = _run(p.sync_profile('ck.json'))
        assert res['name'] == 'n'  # 不抛异常
        browser.close.assert_awaited_once()


# ── _login_stats_fn / _scrape_profile_and_stats / _build_stats ─────────────

class TestLoginStatsFn:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        with patch.object(p, '_scrape_profile_and_stats',
                          AsyncMock(return_value=('', '', [{'name': '获赞', 'num': '999'}]))), \
             patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            stats = _run(p._login_stats_fn(page, 'acc1'))
        assert stats == [{'ICON': 'like', 'COUNT': 999, 'NAME': '获赞', 'SORT': 3}]


class TestScrapeProfileAndStats:
    def test_happy(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value={
            'name': '昵称', 'avatar': 'http://a.png',
            'stats': [{'name': '粉丝', 'num': '0'}],
        })
        name, avatar, stats = _run(p._scrape_profile_and_stats(page))
        assert name == '昵称'
        assert avatar == 'http://a.png'
        assert stats == [{'name': '粉丝', 'num': '0'}]

    def test_result_none(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=None)
        assert _run(p._scrape_profile_and_stats(page)) == ('', '', [])

    def test_partial_result(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value={'stats': []})
        assert _run(p._scrape_profile_and_stats(page)) == ('', '', [])

    def test_evaluate_exception_empty(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('impl.taobao_guanghe.platform.logger') as logger:
            assert _run(p._scrape_profile_and_stats(page)) == ('', '', [])
        assert any('evaluate 失败' in str(c) for c in logger.info.call_args_list)


class TestBuildStats:
    LABEL_MAP: ClassVar[dict] = {
        '粉丝': ('user', 1, '粉丝'),
        '关注': ('follow', 2, '关注'),
        '获赞': ('like', 3, '获赞'),
    }

    def test_cleanup_and_parsing(self):
        raw = [
            {'name': '粉丝', 'num': '1,234'},
            {'name': '关注', 'num': '56'},
            {'name': '获赞', 'num': '12.7'},
            {'name': '未知', 'num': '9'},
        ]
        stats = TaobaoGuanghePlatform._build_stats(raw, self.LABEL_MAP)
        by_name = {s['NAME']: s['COUNT'] for s in stats}
        assert by_name == {'粉丝': 1234, '关注': 56, '获赞': 12}

    def test_empty_num_zero(self):
        stats = TaobaoGuanghePlatform._build_stats(
            [{'name': '粉丝', 'num': ''}], self.LABEL_MAP
        )
        assert stats[0]['COUNT'] == 0

    def test_missing_num_zero(self):
        stats = TaobaoGuanghePlatform._build_stats(
            [{'name': '关注'}], self.LABEL_MAP
        )
        assert stats[0]['COUNT'] == 0

    def test_invalid_number_zero(self):
        stats = TaobaoGuanghePlatform._build_stats(
            [{'name': '粉丝', 'num': 'abc'}, {'name': '粉丝', 'num': '12 3 '}],
            self.LABEL_MAP,
        )
        assert [s['COUNT'] for s in stats] == [0, 123]

    def test_unknown_label_skipped(self):
        stats = TaobaoGuanghePlatform._build_stats(
            [{'name': '不认识的', 'num': '9'}], self.LABEL_MAP
        )
        assert stats == []

    def test_empty_raw(self):
        assert TaobaoGuanghePlatform._build_stats([], self.LABEL_MAP) == []


# ── publish_video 长参数截断(585 行) ───────────────────────────────────────

class TestPublishVideoLongKwarg:
    def test_long_kwarg_repr_truncated(self):
        inst = _mk_platform()
        upload = AsyncMock()
        with patch.object(inst, '_upload_single_video', upload), \
             patch('impl.taobao_guanghe.platform.parse_schedule_time', MagicMock(return_value=[])), \
             patch('impl.taobao_guanghe.platform.get_account_name_by_cookie_file',
                   return_value='昵称'), \
             patch('impl.taobao_guanghe.platform.bind_account_name', MagicMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            asyncio.run(inst.publish_video(title='T', files=[], guangheProducts=['x' * 200]))
        assert upload.await_count == 0
        logged = ' '.join(str(c) for c in logger.info.call_args_list)
        assert '...' in logged  # 长 repr 截断分支

    def test_multi_files_accounts_shop_string_items(self):
        """多视频 × 多账号循环 + shop 类型 + 字符串 item 规范化。"""
        inst = _mk_platform()
        upload = AsyncMock()
        datetimes = [
            datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai')),
            datetime(2026, 8, 21, 12, 0, tzinfo=ZoneInfo('Asia/Shanghai')),
        ]
        with patch.object(inst, '_upload_single_video', upload), \
             patch('impl.taobao_guanghe.platform.parse_schedule_time',
                   MagicMock(return_value=datetimes)), \
             patch('impl.taobao_guanghe.platform.get_account_name_by_cookie_file',
                   return_value='昵称'), \
             patch('impl.taobao_guanghe.platform.bind_account_name', MagicMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            asyncio.run(inst.publish_video(
                title='T', files=['/a.mp4', '/b.mp4'],
                account_file=['u1.json', 'u2.json'],
                guangheLinkType='shop',
                guangheShops=['店铺A', {'title': '店铺B', 'id': '9'}],
                video_format='landscape',
                thumbnail_landscape_169_path='/l169.png',
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        # 2 视频 × 2 账号 = 4 次上传
        assert upload.await_count == 4
        calls = upload.await_args_list
        # 循环顺序：file0→acc0, file0→acc1, file1→acc0, file1→acc1
        assert calls[0].kwargs['file_path'] == '/a.mp4'
        assert calls[0].kwargs['publish_date'] == datetimes[0]
        assert calls[1].kwargs['file_path'] == '/a.mp4'
        assert calls[2].kwargs['file_path'] == '/b.mp4'
        assert calls[2].kwargs['publish_date'] == datetimes[1]
        # shop 类型 + 字符串规范化
        assert calls[0].kwargs['link_type'] == 'shop'
        assert calls[0].kwargs['link_items'] == [
            {'title': '店铺A'}, {'title': '店铺B', 'id': '9'}
        ]
        # 横版 → 16:9 封面
        assert calls[0].kwargs['thumbnail_path'] == '/l169.png'


    def test_product_link_and_portrait_cover(self):
        """product 类型 raw 取值 + 竖版封面兜底链。"""
        inst = _mk_platform()
        upload = AsyncMock()
        with patch.object(inst, '_upload_single_video', upload), \
             patch('impl.taobao_guanghe.platform.parse_schedule_time',
                   MagicMock(return_value=None)), \
             patch('impl.taobao_guanghe.platform.get_account_name_by_cookie_file',
                   return_value='昵称'), \
             patch('impl.taobao_guanghe.platform.bind_account_name', MagicMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            asyncio.run(inst.publish_video(
                title='T', files=['/v.mp4'], account_file=['u1.json'],
                guangheLinkType='product',
                guangheProducts=[{'title': 'P1', 'id': '1'}],
                video_format='portrait',
                thumbnail_portrait_path='/p.png',
            ))
        assert upload.await_count == 1
        call = upload.await_args_list[0]
        assert call.kwargs['link_type'] == 'product'
        assert call.kwargs['link_items'] == [{'title': 'P1', 'id': '1'}]
        assert call.kwargs['thumbnail_path'] == '/p.png'


# ── 编排: _upload_single_video ────────────────────────────────────────────

class TestUploadSingleVideo:
    DT = datetime(2026, 8, 21, 10, 30, tzinfo=ZoneInfo('Asia/Shanghai'))

    def _run_flow(self, p, sub_steps=None, **kwargs):
        defaults = dict(
            title='标题', file_path='/m/v.mp4', tags=['t1'], publish_date=None,
            account_file='/c/u1.json', desc='描述', claim='', thumbnail_path=None,
            link_type='', link_items=None,
        )
        defaults.update(kwargs)
        with _mk_upload_flow(p, sub_steps=sub_steps) as (page, context, browser, steps):
            _run(p._upload_single_video(**defaults))
        return page, context, browser, steps

    def test_happy_full_flow(self):
        p = _mk_platform()
        page, context, browser, steps = self._run_flow(
            p, thumbnail_path='/tmp/c.png', claim='含AI生成内容',
            publish_date=self.DT, link_type='product',
            link_items=[{'id': '1', 'trace': {'keyword': 'k'}}],
        )
        frame = steps['find_publish_frame'].return_value
        steps['dismiss_guide_modal'].assert_awaited_once_with(page)
        steps['upload_video_file'].assert_awaited_once_with(frame, '/m/v.mp4')
        steps['wait_upload_complete'].assert_awaited_once_with(frame)
        steps['set_cover'].assert_awaited_once_with(frame, '/tmp/c.png')
        steps['fill_title'].assert_awaited_once_with(frame, '标题')
        steps['fill_desc_and_tags'].assert_awaited_once_with(frame, '描述', ['t1'])
        steps['set_claim'].assert_awaited_once_with(frame, '含AI生成内容')
        steps['set_schedule_time'].assert_awaited_once_with(frame, self.DT)
        steps['link_products_or_shops'].assert_awaited_once_with(
            frame, 'product', [{'id': '1', 'trace': {'keyword': 'k'}}]
        )
        steps['click_publish'].assert_awaited_once_with(frame, page)
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')
        context.close.assert_awaited_once()
        steps['close_browser'].assert_awaited_once_with(browser, is_close_by_code=True)
        assert page.screenshot.await_count >= 2  # before + after submit

    def test_minimal_flow_skips_optionals(self):
        p = _mk_platform()
        _page, _context, _browser, steps = self._run_flow(p)
        steps['set_cover'].assert_not_awaited()
        steps['set_schedule_time'].assert_not_awaited()
        steps['link_products_or_shops'].assert_not_awaited()
        steps['click_publish'].assert_awaited_once()
        steps['close_browser'].assert_awaited_once()

    def test_publish_failed_still_saves_cookie(self):
        p = _mk_platform()
        page, context, _browser, _steps = self._run_flow(
            p, sub_steps={'click_publish': AsyncMock(return_value=False)}
        )
        context.storage_state.assert_awaited_once_with(path='/c/u1.json')
        assert page.screenshot.await_count >= 2  # before + failed

    def test_cookie_invalid_raises(self):
        p = _mk_platform()
        with _mk_upload_flow(p, page_url=_COOKIE_INVALID_MARKERS[0] + '/x') as \
                (_page, context, _browser, steps), \
                pytest.raises(RuntimeError, match='cookie 失效'):
                _run(p._upload_single_video(
                    title='T', file_path='/m/v.mp4', tags=[], publish_date=None,
                    account_file='/c/u1.json',
                ))
        context.storage_state.assert_not_awaited()
        steps['close_browser'].assert_awaited_once()

    def test_screenshot_errors_swallowed(self):
        p = _mk_platform()
        with _mk_upload_flow(p) as (page, context, _browser, _steps):
            page.screenshot = AsyncMock(side_effect=RuntimeError('shot fail'))
            _run(p._upload_single_video(
                title='T', file_path='/m/v.mp4', tags=[], publish_date=None,
                account_file='/c/u1.json',
            ))
        context.storage_state.assert_awaited_once()

    def test_storage_and_context_close_errors_swallowed(self):
        p = _mk_platform()
        with _mk_upload_flow(p) as (_page, context, _browser, steps):
            context.storage_state = AsyncMock(side_effect=RuntimeError('boom'))
            context.close = AsyncMock(side_effect=RuntimeError('boom'))
            _run(p._upload_single_video(
                title='T', file_path='/m/v.mp4', tags=[], publish_date=None,
                account_file='/c/u1.json',
            ))
        steps['close_browser'].assert_awaited_once()

    def test_close_browser_error_swallowed(self):
        p = _mk_platform()
        with _mk_upload_flow(
            p, sub_steps={'close_browser': AsyncMock(side_effect=RuntimeError('boom'))}
        ) as (_page, _context, _browser, _steps):
            _run(p._upload_single_video(
                title='T', file_path='/m/v.mp4', tags=[], publish_date=None,
                account_file='/c/u1.json',
            ))

    def test_dry_run_screenshot_error_swallowed(self):
        p = _mk_platform()
        with _mk_upload_flow(p) as (page, _context, _browser, steps), \
             patch('impl.taobao_guanghe.platform._DRY_RUN_PUBLISH', True):
            page.screenshot = AsyncMock(side_effect=RuntimeError('shot fail'))
            _run(p._upload_single_video(
                title='T', file_path='/m/v.mp4', tags=[], publish_date=None,
                account_file='/c/u1.json',
            ))
        steps['click_publish'].assert_not_awaited()

    def test_publish_failed_screenshot_error_swallowed(self):
        p = _mk_platform()
        with _mk_upload_flow(
            p, sub_steps={'click_publish': AsyncMock(return_value=False)}
        ) as (page, _context, _browser, _steps):
            page.screenshot = AsyncMock(side_effect=RuntimeError('shot fail'))
            _run(p._upload_single_video(
                title='T', file_path='/m/v.mp4', tags=[], publish_date=None,
                account_file='/c/u1.json',
            ))

    def test_dry_run_skips_publish_waits_close(self):
        p = _mk_platform()
        with _mk_upload_flow(p) as (page, context, _browser, steps), \
             patch('impl.taobao_guanghe.platform._DRY_RUN_PUBLISH', True):
            _run(p._upload_single_video(
                title='T', file_path='/m/v.mp4', tags=[], publish_date=None,
                account_file='/c/u1.json',
            ))
        steps['click_publish'].assert_not_awaited()
        page.wait_for_event.assert_awaited_once_with('close', timeout=0)
        context.storage_state.assert_awaited_once()

    def test_dry_run_wait_close_exception_swallowed(self):
        p = _mk_platform()
        with _mk_upload_flow(p) as (page, context, _browser, _steps), \
             patch('impl.taobao_guanghe.platform._DRY_RUN_PUBLISH', True):
            page.wait_for_event = AsyncMock(side_effect=RuntimeError('user closed'))
            _run(p._upload_single_video(
                title='T', file_path='/m/v.mp4', tags=[], publish_date=None,
                account_file='/c/u1.json',
            ))
        context.storage_state.assert_awaited_once()


# ── DOM: _dismiss_guide_modal ─────────────────────────────────────────────

class TestDismissGuideModal:
    def test_no_guide_returns(self):
        _p = _mk_platform()
        page = _mk_page()
        guide = _loc(page, '.guide-modal').first
        guide.wait_for = AsyncMock(side_effect=TimeoutError('slow'))
        with patch('impl.taobao_guanghe.platform.logger'):
            _run(TaobaoGuanghePlatform._dismiss_guide_modal(page))
        guide.wait_for.assert_awaited_once_with(state='visible', timeout=3000)

    def test_skip_button_clicked(self):
        _p = _mk_platform()
        page = _mk_page()
        skip = _loc(page, '.my-guide-skip').first
        skip.count = AsyncMock(return_value=1)
        skip.is_visible = AsyncMock(return_value=True)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._dismiss_guide_modal(page))
        skip.click.assert_awaited_once()
        assert any('已点击「我知道了」' in str(c) for c in logger.info.call_args_list)

    def test_next_button_loop_three_times(self):
        _p = _mk_platform()
        page = _mk_page()
        skip = _loc(page, '.my-guide-skip').first
        skip.count = AsyncMock(return_value=0)
        nxt = _loc(page, '.guide-modal-footer-next-btn').first
        nxt.count = AsyncMock(return_value=1)
        nxt.is_visible = AsyncMock(return_value=True)
        _loc(page, '.guide-modal').count = AsyncMock(return_value=1)
        close = _loc(page, '.guide-modal-close-icon').first
        close.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._dismiss_guide_modal(page))
        assert nxt.click.await_count == 3
        assert any('仍有 1 个引导弹窗' in str(c) for c in logger.info.call_args_list)

    def test_close_icon_fallback(self):
        _p = _mk_platform()
        page = _mk_page()
        skip = _loc(page, '.my-guide-skip').first
        skip.count = AsyncMock(return_value=0)
        nxt = _loc(page, '.guide-modal-footer-next-btn').first
        nxt.count = AsyncMock(return_value=0)
        modal = _loc(page, '.guide-modal')
        modal.count = AsyncMock(side_effect=[1, 0, 0])
        close = _loc(page, '.guide-modal-close-icon').first
        close.count = AsyncMock(return_value=1)
        close.is_visible = AsyncMock(return_value=True)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._dismiss_guide_modal(page))
        close.click.assert_awaited_once()
        assert any('引导弹窗已关闭' in str(c) for c in logger.info.call_args_list)

    def test_outer_exception_logged(self):
        _p = _mk_platform()
        page = _mk_page()
        skip = _loc(page, '.my-guide-skip').first
        skip.count = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._dismiss_guide_modal(page))
        assert any('处理异常' in str(c) for c in logger.info.call_args_list)


# ── DOM: _navigate_to_publish_page ────────────────────────────────────────

class TestNavigateToPublishPage:
    def _page(self, pages):
        page = _mk_page(url=_GUANGHE_HOME_URL)
        page.context.pages = pages
        page.context.on = MagicMock()
        page.context.remove_listener = MagicMock()
        return page

    def test_hover_strategy_then_url_ready(self):
        page = self._page([_mk_page(url=_PUBLISH_URL)])
        menu_item = _loc(page, 'li[role="menuitem"]:has-text("发视频")').first
        menu_item.hover = AsyncMock(side_effect=RuntimeError('boom'))
        with _mk_time(0.0, 0.5), patch('impl.taobao_guanghe.platform.logger'):
            out = _run(TaobaoGuanghePlatform._navigate_to_publish_page(page))
        assert out is page.context.pages[0]
        pub_btn = _loc(page, '[data-autolog*="text=发布作品"]').first
        assert pub_btn.hover.await_count >= 1
        assert menu_item.click.await_count == 1
        assert page.context.on.call_count == 1
        assert page.context.remove_listener.call_count == 1

    def test_new_tab_captured_via_callback(self):
        np = _mk_page(url='https://huodong.taobao.com/publish/xyz')
        page = self._page([_mk_page(url=_GUANGHE_HOME_URL), np])
        page.context.on = MagicMock(side_effect=lambda event, fn: fn(np))
        np.wait_for_load_state = AsyncMock(side_effect=RuntimeError('boom'))
        with _mk_time(0.0, 0.5), patch('impl.taobao_guanghe.platform.logger'):
            out = _run(TaobaoGuanghePlatform._navigate_to_publish_page(page))
        assert out is np
        np.wait_for_load_state.assert_awaited_once_with(
            'domcontentloaded', timeout=15000
        )

    def test_strategy1_click_exception_falls_to_strategy2(self):
        page = self._page([_mk_page(url=_PUBLISH_URL)])
        menu_item = _loc(page, 'li[role="menuitem"]:has-text("发视频")').first
        menu_item.click = AsyncMock(side_effect=TimeoutError('no click'))
        video_item = _loc(page, '[data-autolog*="text=发视频"]').first
        with _mk_time(0.0, 0.5), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            out = _run(TaobaoGuanghePlatform._navigate_to_publish_page(page))
        assert out is page.context.pages[0]
        assert video_item.click.await_count == 1
        assert any('策略 1 attempt=1 失败' in str(c) for c in logger.info.call_args_list)
        assert any('策略 1 attempt=2 失败' in str(c) for c in logger.info.call_args_list)

    def test_click_strategy_fallback(self):
        page = self._page([_mk_page(url=_PUBLISH_URL)])
        menu_item = _loc(page, 'li[role="menuitem"]:has-text("发视频")').first
        menu_item.wait_for = AsyncMock(side_effect=TimeoutError('no menu'))
        video_item = _loc(page, '[data-autolog*="text=发视频"]').first
        video_item.hover = AsyncMock(side_effect=RuntimeError('boom'))
        with _mk_time(0.0, 0.5), patch('impl.taobao_guanghe.platform.logger'):
            out = _run(TaobaoGuanghePlatform._navigate_to_publish_page(page))
        assert out is page.context.pages[0]
        assert video_item.click.await_count == 1

    def test_click_timeout_then_hover_inside_strategy1(self):
        page = self._page([_mk_page(url=_PUBLISH_URL)])
        pub_btn = _loc(page, '[data-autolog*="text=发布作品"]').first
        pub_btn.click = AsyncMock(side_effect=TimeoutError('busy'))
        menu_item = _loc(page, 'li[role="menuitem"]:has-text("发视频")').first
        menu_item.wait_for = AsyncMock(side_effect=TimeoutError('no menu'))
        video_item = _loc(page, '[data-autolog*="text=发视频"]').first
        with _mk_time(0.0, 0.5), patch('impl.taobao_guanghe.platform.logger'):
            _run(TaobaoGuanghePlatform._navigate_to_publish_page(page))
        assert pub_btn.click.await_count == 1  # 第一次点击超时后 hover 兜底
        assert video_item.click.await_count == 1  # 最终策略 2 成功

    def test_js_dispatch_strategy(self):
        page = self._page([_mk_page(url=_PUBLISH_URL)])
        _loc(page, 'li[role="menuitem"]:has-text("发视频")').first.wait_for = AsyncMock(
            side_effect=TimeoutError('no menu')
        )
        _loc(page, '[data-autolog*="text=发视频"]').first.wait_for = AsyncMock(
            side_effect=TimeoutError('no item')
        )
        page.evaluate = AsyncMock(side_effect=[True, True])
        with _mk_time(0.0, 0.5), patch('impl.taobao_guanghe.platform.logger'):
            out = _run(TaobaoGuanghePlatform._navigate_to_publish_page(page))
        assert out is page.context.pages[0]
        assert page.evaluate.await_count == 2

    def test_all_strategies_fail_raises(self):
        page = self._page([])
        _loc(page, 'li[role="menuitem"]:has-text("发视频")').first.wait_for = AsyncMock(
            side_effect=TimeoutError('no menu')
        )
        _loc(page, '[data-autolog*="text=发视频"]').first.wait_for = AsyncMock(
            side_effect=TimeoutError('no item')
        )
        page.evaluate = AsyncMock(side_effect=[False])
        with _mk_time(0.0, 21.0), \
                patch('impl.taobao_guanghe.platform.logger'), \
                pytest.raises(RuntimeError, match='无法进入视频发布页'):
            _run(TaobaoGuanghePlatform._navigate_to_publish_page(page))

    def test_js_dispatch_exception_logged_then_raise(self):
        page = self._page([])
        _loc(page, 'li[role="menuitem"]:has-text("发视频")').first.wait_for = AsyncMock(
            side_effect=TimeoutError('no menu')
        )
        _loc(page, '[data-autolog*="text=发视频"]').first.wait_for = AsyncMock(
            side_effect=TimeoutError('no item')
        )
        page.evaluate = AsyncMock(side_effect=RuntimeError('js boom'))
        with _mk_time(0.0, 21.0), \
                patch('impl.taobao_guanghe.platform.logger') as logger, \
                pytest.raises(RuntimeError, match='无法进入视频发布页'):
            _run(TaobaoGuanghePlatform._navigate_to_publish_page(page))
        assert any('策略 3 失败' in str(c) for c in logger.info.call_args_list)

    def test_fallback_returns_original_page_after_deadline(self):
        page = self._page([_mk_page(url=_GUANGHE_HOME_URL)])
        with _mk_time(0.0, 1.0, 21.0), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            out = _run(TaobaoGuanghePlatform._navigate_to_publish_page(page))
        assert out is page
        assert any('未精确匹配发布页 URL' in str(c) for c in logger.info.call_args_list)


# ── DOM: _find_publish_frame ──────────────────────────────────────────────

class TestFindPublishFrame:
    _UPLOAD_SEL = (
        'input[type="file"][accept*="mp4"], '
        'input[type="file"][name="file"], '
        '.video-upload, .creator-add-video-v2'
    )

    def test_found_frame(self):
        _p = _mk_platform()
        page = _mk_page()
        f1 = _mk_page(url='https://huodong.taobao.com/wow/z/guang/gg_publish')
        _loc(f1, self._UPLOAD_SEL).count = AsyncMock(return_value=1)
        page.frames = [page.main_frame, f1]
        with _mk_time(0.0, 0.5), patch('impl.taobao_guanghe.platform.logger'):
            out = _run(TaobaoGuanghePlatform._find_publish_frame(page))
        assert out is f1

    def test_blank_frame_skips_diagnostic_log(self):
        _p = _mk_platform()
        page = _mk_page()
        blank = _mk_page(url='about:blank')
        f1 = _mk_page(url='https://huodong.taobao.com/x')
        _loc(f1, self._UPLOAD_SEL).count = AsyncMock(return_value=1)
        page.frames = [blank, f1]
        with _mk_time(0.0, 0.5), patch('impl.taobao_guanghe.platform.logger'):
            out = _run(TaobaoGuanghePlatform._find_publish_frame(page))
        assert out is f1

    def test_locator_exception_then_fallback_main_frame(self):
        _p = _mk_platform()
        page = _mk_page()
        bad = _mk_page(url='https://huodong.taobao.com/broken')
        bad.locator = MagicMock(side_effect=RuntimeError('boom'))
        page.frames = [bad]
        with _mk_time(0.0, 1.0, 21.0), patch('impl.taobao_guanghe.platform.logger'):
            out = _run(TaobaoGuanghePlatform._find_publish_frame(page))
        assert out is page.main_frame

    def test_fallback_main_frame_after_deadline(self):
        _p = _mk_platform()
        page = _mk_page()
        page.frames = [page.main_frame]
        with _mk_time(0.0, 21.0), patch('impl.taobao_guanghe.platform.logger'):
            out = _run(TaobaoGuanghePlatform._find_publish_frame(page))
        assert out is page.main_frame


# ── DOM: _upload_video_file ───────────────────────────────────────────────

class TestUploadVideoFile:
    _SEL1 = ('input[type="file"][accept*="mp4"], '
             'input[type="file"][accept*="video"], '
             'input[type="file"][accept*="mov"]')
    _SEL3 = ('.video-upload input[type="file"], '
             '.creator-add-video-v2 input[type="file"]')

    def test_strategy1_video_input(self):
        frame = _mk_page()
        cand = _loc(frame, self._SEL1).first
        with patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._upload_video_file(frame, '/m/v.mp4'))
        cand.set_input_files.assert_awaited_once_with('/m/v.mp4')
        assert any('video input 命中' in str(c) for c in logger.info.call_args_list)

    def test_strategy2_name_file(self):
        frame = _mk_page()
        _loc(frame, self._SEL1).first.wait_for = AsyncMock(side_effect=TimeoutError('x'))
        cand2 = _loc(frame, 'input[type="file"][name="file"]').first
        with patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._upload_video_file(frame, '/m/v.mp4'))
        cand2.set_input_files.assert_awaited_once_with('/m/v.mp4')
        assert any('name=file input 命中' in str(c) for c in logger.info.call_args_list)

    def test_strategy3_container_input(self):
        frame = _mk_page()
        _loc(frame, self._SEL1).first.wait_for = AsyncMock(side_effect=TimeoutError('x'))
        _loc(frame, 'input[type="file"][name="file"]').first.wait_for = AsyncMock(
            side_effect=TimeoutError('x')
        )
        cand3 = _loc(frame, self._SEL3).first
        with patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._upload_video_file(frame, '/m/v.mp4'))
        cand3.set_input_files.assert_awaited_once_with('/m/v.mp4')
        assert any('上传区 file input 命中' in str(c) for c in logger.info.call_args_list)

    def test_all_strategies_fail_raises(self):
        frame = _mk_page()
        _loc(frame, self._SEL1).first.wait_for = AsyncMock(side_effect=TimeoutError('x'))
        _loc(frame, 'input[type="file"][name="file"]').first.wait_for = AsyncMock(
            side_effect=TimeoutError('x')
        )
        _loc(frame, self._SEL3).first.wait_for = AsyncMock(side_effect=TimeoutError('x'))
        with patch('impl.taobao_guanghe.platform.logger'), \
                pytest.raises(RuntimeError, match='未找到视频上传 input'):
            _run(TaobaoGuanghePlatform._upload_video_file(frame, '/m/v.mp4'))

    def test_upload_area_not_rendered_logged(self):
        frame = _mk_page()
        frame.wait_for_selector = AsyncMock(side_effect=TimeoutError('slow'))
        with patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._upload_video_file(frame, '/m/v.mp4'))
        assert any('上传区容器未出现' in str(c) for c in logger.info.call_args_list)


# ── DOM: _wait_upload_complete ────────────────────────────────────────────

class TestWaitUploadComplete:
    _FAIL_SEL = 'text=上传失败'
    _SUCCESS_SEL = '[class*="successStatus"] img'
    _WAIT_SEL = 'text=等待视频上传'
    _PROGRESS_SEL = '[class*="upload-progress"]'
    _PROGRESS_TEXT_SEL = (
        '[class*="upload-progress"] [class*="text"], [class*="upload-progress-text"]'
    )

    def test_success_cover_immediate(self):
        page = _mk_page()
        _loc(page, self._SUCCESS_SEL).count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            _run(TaobaoGuanghePlatform._wait_upload_complete(page))

    def test_upload_failed_raises(self):
        page = _mk_page()
        fail = _loc(page, self._FAIL_SEL)
        fail.count = AsyncMock(return_value=1)
        fail.first.is_visible = AsyncMock(return_value=True)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'), pytest.raises(RuntimeError, match='视频上传失败'):
            _run(TaobaoGuanghePlatform._wait_upload_complete(page))

    def test_progress_seen_then_gone(self):
        page = _mk_page()
        _loc(page, self._FAIL_SEL).count = AsyncMock(return_value=0)
        _loc(page, self._SUCCESS_SEL).count = AsyncMock(return_value=0)
        _loc(page, self._WAIT_SEL).count = AsyncMock(side_effect=[1, 0])
        progress = _loc(page, self._PROGRESS_SEL)
        progress.count = AsyncMock(side_effect=[1, 0])
        _loc(page, self._PROGRESS_TEXT_SEL).count = AsyncMock(return_value=1)
        _loc(page, self._PROGRESS_TEXT_SEL).first.text_content = AsyncMock(
            return_value='45%'
        )
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._wait_upload_complete(page))
        assert any('进度条已消失' in str(c) for c in logger.info.call_args_list)

    def test_progress_seen_then_cover_generated(self):
        page = _mk_page()
        _loc(page, self._FAIL_SEL).count = AsyncMock(return_value=0)
        _loc(page, self._SUCCESS_SEL).count = AsyncMock(side_effect=[0, 0, 1])
        _loc(page, self._WAIT_SEL).count = AsyncMock(side_effect=[1, 0])
        _loc(page, self._PROGRESS_SEL).count = AsyncMock(side_effect=[1, 0])
        _loc(page, self._PROGRESS_TEXT_SEL).count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._wait_upload_complete(page))
        assert any('封面已生成' in str(c) for c in logger.info.call_args_list)

    def test_progress_text_exception_logged(self):
        page = _mk_page()
        _loc(page, self._FAIL_SEL).count = AsyncMock(return_value=0)
        _loc(page, self._SUCCESS_SEL).count = AsyncMock(side_effect=[0, 1])
        _loc(page, self._WAIT_SEL).count = AsyncMock(side_effect=[1, 0])
        _loc(page, self._PROGRESS_SEL).count = AsyncMock(side_effect=[1, 0])
        _loc(page, self._PROGRESS_TEXT_SEL).count = AsyncMock(return_value=1)
        _loc(page, self._PROGRESS_TEXT_SEL).first.text_content = AsyncMock(
            side_effect=ValueError('boom')
        )
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._wait_upload_complete(page))
        assert any('等待中' in str(c) for c in logger.info.call_args_list)

    def test_state_check_exception_continues(self):
        page = _mk_page()
        _loc(page, self._FAIL_SEL).count = AsyncMock(return_value=0)
        _loc(page, self._SUCCESS_SEL).count = AsyncMock(side_effect=[0, 1])
        _loc(page, self._WAIT_SEL).count = AsyncMock(
            side_effect=[ValueError('boom'), 0]
        )
        _loc(page, self._PROGRESS_SEL).count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._wait_upload_complete(page))
        assert any('状态检查异常' in str(c) for c in logger.info.call_args_list)

    def test_waiting_no_progress_logged(self):
        page = _mk_page()
        _loc(page, self._FAIL_SEL).count = AsyncMock(return_value=0)
        _loc(page, self._SUCCESS_SEL).count = AsyncMock(side_effect=[0, 1])
        _loc(page, self._WAIT_SEL).count = AsyncMock(side_effect=[0, 0])
        _loc(page, self._PROGRESS_SEL).count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(TaobaoGuanghePlatform._wait_upload_complete(page))
        assert any('等待上传开始' in str(c) for c in logger.info.call_args_list)


# ── DOM: _set_cover ───────────────────────────────────────────────────────

class TestSetCover:
    _EDIT_SEL = '[data-autolog-container="coverOperate_edit"]'
    _EDIT_FALLBACK = '[class*="cover"]:has-text("编辑")'
    _UPLOAD_SEL = '[class*="uploadImage"]'
    _IMG_SEL = 'input[type="file"][accept*="image"]'
    _MEDIA_SEL = '.media-item-check .next-checkbox-input'
    _MEDIA_LABEL = '.media-item-check label'
    _CONFIRM1 = ('.space-footer button:has-text("确定"), '
                 '.next-dialog button:has-text("确定")')
    _NEXT = ('.next-dialog-footer button:has-text("下一步"), '
             'button:has-text("下一步")')
    _CONFIRM2 = ('.next-dialog-footer button:has-text("确定"), '
                 'button:has-text("确定")')

    def test_file_missing_early_return(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_cover(page, '/nonexistent/x.png'))
        page.locator.assert_not_called()
        assert any('封面文件不存在' in str(c) for c in logger.info.call_args_list)

    def test_happy_flow(self):
        p = _mk_platform()
        page = _mk_page()
        cover = _mk_cover_file()
        try:
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.taobao_guanghe.platform.logger'):
                _run(p._set_cover(page, cover))
        finally:
            os.unlink(cover)
        edit = _loc(page, self._EDIT_SEL).first
        edit.click.assert_awaited_once()
        _loc(page, self._UPLOAD_SEL).first.click.assert_awaited_once()
        img = _loc(page, self._IMG_SEL).first
        img.set_input_files.assert_awaited_once_with(cover)
        _loc(page, self._CONFIRM1).first.click.assert_awaited_once()
        _loc(page, self._NEXT).first.click.assert_awaited_once()
        _loc(page, self._CONFIRM2).first.click.assert_awaited_once()

    def test_edit_button_fallback_selector(self):
        p = _mk_platform()
        page = _mk_page()
        cover = _mk_cover_file()
        try:
            _loc(page, self._EDIT_SEL).first.wait_for = AsyncMock(
                side_effect=TimeoutError('slow')
            )
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.taobao_guanghe.platform.logger'):
                _run(p._set_cover(page, cover))
        finally:
            os.unlink(cover)
        _loc(page, self._EDIT_FALLBACK).first.click.assert_awaited_once()

    def test_local_upload_missing_raises(self):
        p = _mk_platform()
        page = _mk_page()
        cover = _mk_cover_file()
        try:
            _loc(page, self._UPLOAD_SEL).first.wait_for = AsyncMock(
                side_effect=TimeoutError('slow')
            )
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.taobao_guanghe.platform.logger') as logger:
                _run(p._set_cover(page, cover))
        finally:
            os.unlink(cover)
        # 内层 RuntimeError 被外层 except 吞掉 → 只记录日志 + Escape 兜底
        assert any('本地上传按钮未找到' in str(c) for c in logger.info.call_args_list)
        assert any('设置封面失败' in str(c) for c in logger.info.call_args_list)
        assert page.keyboard.press.await_count == 2

    def test_file_chooser_path(self):
        p = _mk_platform()
        page = _mk_page()
        cover = _mk_cover_file()
        chooser = MagicMock()
        chooser.set_files = AsyncMock()
        fc_mgr = MagicMock()
        fc_mgr.__aenter__ = AsyncMock(return_value=fc_mgr)
        fc_mgr.__aexit__ = AsyncMock(return_value=False)
        fc_mgr.value = _AwaitableValue(chooser)
        page.expect_file_chooser = MagicMock(return_value=fc_mgr)
        try:
            _loc(page, self._IMG_SEL).first.wait_for = AsyncMock(
                side_effect=TimeoutError('not attached')
            )
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.taobao_guanghe.platform.logger'):
                _run(p._set_cover(page, cover))
        finally:
            os.unlink(cover)
        chooser.set_files.assert_awaited_once_with(cover)
        # 跳过直接注入路径
        _loc(page, self._IMG_SEL).first.set_input_files.assert_not_awaited()

    def test_file_chooser_fail_falls_back_to_generic_input(self):
        p = _mk_platform()
        page = _mk_page()
        cover = _mk_cover_file()
        try:
            _loc(page, self._IMG_SEL).first.wait_for = AsyncMock(
                side_effect=TimeoutError('not attached')
            )
            select_new = page.locator('button:has-text("选择新封面")').first
            select_new.click = AsyncMock(side_effect=RuntimeError('boom'))
            generic = page.locator('input[type="file"]').first
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.taobao_guanghe.platform.logger') as logger:
                _run(p._set_cover(page, cover))
        finally:
            os.unlink(cover)
        generic.set_input_files.assert_awaited_once_with(cover)
        assert any('file chooser 方式失败' in str(c) for c in logger.info.call_args_list)

    def test_media_item_already_checked_no_click(self):
        p = _mk_platform()
        page = _mk_page()
        cover = _mk_cover_file()
        try:
            _loc(page, self._MEDIA_SEL).first.count = AsyncMock(return_value=1)
            _loc(page, self._MEDIA_LABEL).first.evaluate = AsyncMock(return_value=True)
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.taobao_guanghe.platform.logger'):
                _run(p._set_cover(page, cover))
        finally:
            os.unlink(cover)
        _loc(page, self._MEDIA_LABEL).first.click.assert_not_awaited()

    def test_media_item_unchecked_clicks_label(self):
        p = _mk_platform()
        page = _mk_page()
        cover = _mk_cover_file()
        try:
            _loc(page, self._MEDIA_SEL).first.count = AsyncMock(return_value=1)
            _loc(page, self._MEDIA_LABEL).first.evaluate = AsyncMock(return_value='')
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.taobao_guanghe.platform.logger'):
                _run(p._set_cover(page, cover))
        finally:
            os.unlink(cover)
        _loc(page, self._MEDIA_LABEL).first.click.assert_awaited_once()

    def test_media_check_exception_logged(self):
        p = _mk_platform()
        page = _mk_page()
        cover = _mk_cover_file()
        try:
            _loc(page, self._MEDIA_SEL).first.count = AsyncMock(
                side_effect=RuntimeError('boom')
            )
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.taobao_guanghe.platform.logger') as logger:
                _run(p._set_cover(page, cover))
        finally:
            os.unlink(cover)
        assert any('选择图片异常' in str(c) for c in logger.info.call_args_list)

    def test_footer_buttons_missing_logged(self):
        p = _mk_platform()
        page = _mk_page()
        cover = _mk_cover_file()
        try:
            _loc(page, self._CONFIRM1).first.wait_for = AsyncMock(
                side_effect=TimeoutError('no btn')
            )
            _loc(page, self._NEXT).first.wait_for = AsyncMock(
                side_effect=TimeoutError('no btn')
            )
            _loc(page, self._CONFIRM2).first.wait_for = AsyncMock(
                side_effect=TimeoutError('no btn')
            )
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.taobao_guanghe.platform.logger') as logger:
                _run(p._set_cover(page, cover))
        finally:
            os.unlink(cover)
        assert any('下一步按钮异常' in str(c) for c in logger.info.call_args_list)
        assert any('最终确定按钮异常' in str(c) for c in logger.info.call_args_list)

    def test_outer_exception_presses_escape(self):
        p = _mk_platform()
        page = _mk_page()
        cover = _mk_cover_file()
        try:
            _loc(page, self._EDIT_SEL).first.click = AsyncMock(
                side_effect=RuntimeError('boom')
            )
            page.keyboard.press = AsyncMock(side_effect=RuntimeError('boom'))
            with patch('asyncio.sleep', AsyncMock()), \
                 patch('impl.taobao_guanghe.platform.logger'):
                _run(p._set_cover(page, cover))
        finally:
            os.unlink(cover)
        # 第一次 Escape 抛异常 → 第二次不执行,内层 except 吞掉
        assert page.keyboard.press.await_count == 1
        assert page.keyboard.press.await_args.args == ('Escape',)


# ── DOM: _fill_title ──────────────────────────────────────────────────────

class TestFillTitle:
    _SEL = 'input[placeholder*="标题"], input[maxlength="30"]'

    def test_empty_title_returns(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.taobao_guanghe.platform.logger'):
            _run(p._fill_title(page, ''))
        page.locator.assert_not_called()

    def test_happy_truncated_to_30(self):
        p = _mk_platform()
        page = _mk_page()
        title = '很' * 40
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            _run(p._fill_title(page, title))
        inp = _loc(page, self._SEL).first
        assert inp.fill.await_count == 2  # 先清空再填
        assert inp.fill.await_args.args == ('很' * 30,)
        inp.click.assert_awaited_once()

    def test_exception_logged(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, self._SEL).first.wait_for = AsyncMock(side_effect=TimeoutError('x'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._fill_title(page, '标题'))
        assert any('填写标题] 失败' in str(c) for c in logger.info.call_args_list)


# ── DOM: _fill_desc_and_tags ──────────────────────────────────────────────

class TestFillDescAndTags:
    _EDITOR_SEL = '[data-cangjie-content="true"]'

    def test_empty_returns(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.taobao_guanghe.platform.logger'):
            _run(p._fill_desc_and_tags(page, '', []))
        page.locator.assert_not_called()

    def test_tag_parsing_and_budget(self):
        p = _mk_platform()
        page = _mk_page()
        desc = '长' * 2000
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            _run(p._fill_desc_and_tags(page, desc, ['A，B', '#C']))
        editor = _loc(page, self._EDITOR_SEL).first
        calls = [c.args[0] for c in editor.press_sequentially.await_args_list]
        # 标签总长 = (#A,#B,#C 各 len+1=3) = 9 → desc 预算 1000-9-1=990
        assert calls[0] == '长' * 990
        assert calls[1:] == ['#A', '#B', '#C']
        assert page.keyboard.press.await_count == 6  # 每个标签前后各一个空格

    def test_desc_only_no_tags(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            _run(p._fill_desc_and_tags(page, '描述', []))
        editor = _loc(page, self._EDITOR_SEL).first
        assert editor.press_sequentially.await_args.args == ('描述',)

    def test_tags_only_no_desc(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            _run(p._fill_desc_and_tags(page, '', ['t1']))
        editor = _loc(page, self._EDITOR_SEL).first
        assert editor.press_sequentially.await_args.args == ('#t1',)
        assert page.keyboard.press.await_count == 2

    def test_exception_logged(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, self._EDITOR_SEL).first.wait_for = AsyncMock(
            side_effect=TimeoutError('x')
        )
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._fill_desc_and_tags(page, '描述', ['t1']))
        assert any('填写描述] 失败' in str(c) for c in logger.info.call_args_list)


# ── DOM: _set_claim ───────────────────────────────────────────────────────

class TestSetClaim:
    def test_invalid_defaults(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_claim(page, '不存在的声明'))
        radio = _loc(page, '.next-radio-label:has-text("内容无需标注")').first
        radio.click.assert_awaited_once()
        assert any('内容无需标注' in str(c) for c in logger.info.call_args_list)

    def test_valid_claim(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            _run(p._set_claim(page, '含AI生成内容'))
        _loc(page, '.next-radio-label:has-text("含AI生成内容")').first \
            .click.assert_awaited_once()

    def test_exception_logged(self):
        p = _mk_platform()
        page = _mk_page()
        _loc(page, '.next-radio-label:has-text("内容无需标注")').first.wait_for = AsyncMock(
            side_effect=TimeoutError('x')
        )
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_claim(page, ''))
        assert any('选择失败' in str(c) for c in logger.info.call_args_list)


# ── DOM: _set_schedule_time ───────────────────────────────────────────────

class TestSetScheduleTime:
    DT = datetime(2026, 8, 21, 10, 30, tzinfo=ZoneInfo('Asia/Shanghai'))

    def test_non_datetime_returns(self):
        p = _mk_platform()
        page = _mk_page()
        with patch('impl.taobao_guanghe.platform.logger'):
            _run(p._set_schedule_time(page, None))
        page.evaluate.assert_not_awaited()

    def test_js_radio_clicked_happy(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        _loc(page, '.next-date-picker-panel-input input[placeholder="YYYY/MM/DD"]') \
            .first.count = AsyncMock(return_value=1)
        _loc(page, '.next-calendar-cell[title="2026/08/21"]').first.wait_for = AsyncMock()
        _loc(page, '.next-date-picker-panel-input input[placeholder="HH:mm"]') \
            .first.count = AsyncMock(return_value=1)
        _loc(page, '.next-time-picker-menu-hour .next-time-picker-menu-item[title="10"]') \
            .first.count = AsyncMock(return_value=1)
        _loc(page, '.next-time-picker-menu-minute .next-time-picker-menu-item[title="30"]') \
            .first.count = AsyncMock(return_value=1)
        _loc(page, '.next-date-picker-panel button:has-text("确定"), '
                   '.next-btn-primary:has-text("确定")').first.count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_schedule_time(page, self.DT))
        assert page.evaluate.await_count == 1  # 仅 JS 主路径
        _loc(page, '#date-picker input').first.click.assert_awaited_once_with(force=True)
        _loc(page, '.next-time-picker-menu-hour .next-time-picker-menu-item[title="10"]') \
            .first.click.assert_awaited_once()
        _loc(page, '.next-time-picker-menu-minute .next-time-picker-menu-item[title="30"]') \
            .first.click.assert_awaited_once()
        assert any('已选时间 10:30' in str(c) for c in logger.info.call_args_list)

    def test_js_fail_fallback_radio(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[False, True])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_schedule_time(page, self.DT))
        assert page.evaluate.await_count == 2
        assert any('兜底 radio 点击已执行' in str(c) for c in logger.info.call_args_list)

    def test_fallback_radio_exception_returns(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[False, RuntimeError('boom')])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_schedule_time(page, self.DT))
        assert any('无法启用定时发布 radio' in str(c) for c in logger.info.call_args_list)
        page.wait_for_function.assert_not_awaited()

    def test_js_radio_exception_falls_to_fallback(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(side_effect=[RuntimeError('js boom'), True])
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_schedule_time(page, self.DT))
        assert page.evaluate.await_count == 2
        assert any('JS 点击 radio 失败' in str(c) for c in logger.info.call_args_list)

    def test_date_picker_still_disabled_logged(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        page.wait_for_function = AsyncMock(side_effect=TimeoutError('disabled'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_schedule_time(page, self.DT))
        assert any('日期选择器仍 disabled' in str(c) for c in logger.info.call_args_list)

    def test_ymd_and_hms_missing_skipped(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        # ymd/hms 输入框都不存在 → 直接跳到确定
        _loc(page, '.next-calendar-cell[title="2026/08/21"]').first.wait_for = AsyncMock()
        _loc(page, '.next-date-picker-panel button:has-text("确定"), '
                   '.next-btn-primary:has-text("确定")').count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            _run(p._set_schedule_time(page, self.DT))

    def test_calendar_cell_timeout_logged(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        _loc(page, '.next-calendar-cell[title="2026/08/21"]').first.wait_for = AsyncMock(
            side_effect=TimeoutError('no cell')
        )
        _loc(page, '.next-date-picker-panel button:has-text("确定"), '
                   '.next-btn-primary:has-text("确定")').count = AsyncMock(return_value=1)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_schedule_time(page, self.DT))
        assert any('日历选日失败' in str(c) for c in logger.info.call_args_list)

    def test_ymd_click_exception_swallowed(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        _loc(page, '.next-date-picker-panel-input input[placeholder="YYYY/MM/DD"]') \
            .first.count = AsyncMock(return_value=1)
        _loc(page, '.next-date-picker-panel-input input[placeholder="YYYY/MM/DD"]') \
            .first.click = AsyncMock(side_effect=RuntimeError('boom'))
        _loc(page, '.next-calendar-cell[title="2026/08/21"]').first.wait_for = AsyncMock()
        _loc(page, '.next-date-picker-panel button:has-text("确定"), '
                   '.next-btn-primary:has-text("确定")').first.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            _run(p._set_schedule_time(page, self.DT))  # 异常吞掉,继续选日历

    def test_hms_selection_exception_logged(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        _loc(page, '.next-date-picker-panel-input input[placeholder="HH:mm"]') \
            .first.count = AsyncMock(return_value=1)
        _loc(page, '.next-date-picker-panel-input input[placeholder="HH:mm"]') \
            .first.click = AsyncMock(side_effect=RuntimeError('boom'))
        _loc(page, '.next-date-picker-panel button:has-text("确定"), '
                   '.next-btn-primary:has-text("确定")').first.count = AsyncMock(return_value=0)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_schedule_time(page, self.DT))
        assert any('时分选择异常' in str(c) for c in logger.info.call_args_list)

    def test_ok_button_exception_logged(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        ok = _loc(page, '.next-date-picker-panel button:has-text("确定"), '
                        '.next-btn-primary:has-text("确定")')
        ok.first.count = AsyncMock(return_value=1)
        ok.first.click = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_schedule_time(page, self.DT))
        assert any('确定按钮异常' in str(c) for c in logger.info.call_args_list)

    def test_outer_exception_logged(self):
        p = _mk_platform()
        page = _mk_page()
        page.evaluate = AsyncMock(return_value=True)
        _loc(page, '#date-picker input').first.wait_for = AsyncMock(
            side_effect=TimeoutError('no input')
        )
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            _run(p._set_schedule_time(page, self.DT))
        assert any('定时发布] 设置失败' in str(c) for c in logger.info.call_args_list)


# ── DOM: _link_products_or_shops ──────────────────────────────────────────

class TestLinkProductsOrShops:
    def test_empty_items_returns(self):
        p = _mk_platform()
        frame = _mk_page()
        with patch('impl.taobao_guanghe.platform._replay_groups', AsyncMock()) as rg:
            _run(p._link_products_or_shops(frame, 'product', []))
        rg.assert_not_awaited()

    def test_delegates_to_replay_groups(self):
        p = _mk_platform()
        frame = _mk_page()
        items = [{'id': '1', 'trace': {'keyword': 'k'}}]
        with patch('impl.taobao_guanghe.platform._replay_groups', AsyncMock()) as rg:
            _run(p._link_products_or_shops(frame, 'shop', items))
        rg.assert_awaited_once_with(frame, 'shop', items, max_load_more=5)


# ── DOM: _click_publish ───────────────────────────────────────────────────

class TestClickPublish:
    _SEL = ('.next-btn-primary:has-text("立即发布"), '
            '.next-btn-primary:has-text("定时发布")')

    def _frame(self):
        frame = _mk_page()
        return frame

    def test_success_url_jump(self):
        main = _SeqUrlPage([_PUBLISH_URL, _SUCCESS_URL])
        frame = self._frame()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            ok = _run(TaobaoGuanghePlatform._click_publish(frame, main))
        assert ok is True
        _loc(frame, self._SEL).first.click.assert_awaited_once_with(timeout=5000)

    def test_url_never_changes_treated_success(self):
        main = _mk_page(url=_PUBLISH_URL)
        frame = self._frame()
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            ok = _run(TaobaoGuanghePlatform._click_publish(frame, main))
        assert ok is True
        assert any('60s 内页面未跳转' in str(c) for c in logger.info.call_args_list)

    def test_click_retry_then_evaluate(self):
        main = _mk_page(url=_PUBLISH_URL)
        frame = self._frame()
        btn = _loc(frame, self._SEL).first
        btn.click = AsyncMock(side_effect=[TimeoutError('x'), TimeoutError('y')])
        btn.evaluate = AsyncMock(return_value=True)
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            ok = _run(TaobaoGuanghePlatform._click_publish(frame, main))
        assert ok is True
        assert btn.click.await_count == 2
        assert any('JS evaluate click 命中' in str(c) for c in logger.info.call_args_list)

    def test_all_click_fail_returns_false(self):
        main = _mk_page(url=_PUBLISH_URL)
        frame = self._frame()
        btn = _loc(frame, self._SEL).first
        btn.click = AsyncMock(side_effect=[TimeoutError('x'), TimeoutError('y')])
        btn.evaluate = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            ok = _run(TaobaoGuanghePlatform._click_publish(frame, main))
        assert ok is False
        assert any('JS evaluate click 失败' in str(c) for c in logger.info.call_args_list)

    def test_wait_for_timeout_returns_false(self):
        main = _mk_page(url=_PUBLISH_URL)
        frame = self._frame()
        _loc(frame, self._SEL).first.wait_for = AsyncMock(
            side_effect=TimeoutError('no btn')
        )
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger') as logger:
            ok = _run(TaobaoGuanghePlatform._click_publish(frame, main))
        assert ok is False
        assert any('点击发布失败' in str(c) for c in logger.info.call_args_list)

    def test_no_main_page_uses_frame_url(self):
        frame = _SeqUrlPage([_PUBLISH_URL, _SUCCESS_URL])
        frame.locator = MagicMock(
            side_effect=lambda sel, **kw: _mk_locator()
        )
        with patch('asyncio.sleep', AsyncMock()), \
             patch('impl.taobao_guanghe.platform.logger'):
            ok = _run(TaobaoGuanghePlatform._click_publish(frame))
        assert ok is True


# ── open_creator_center ───────────────────────────────────────────────────

class TestOpenCreatorCenter:
    def _run_occ(self, p, cookie_name, page=None, browser_close_side_effect=None):
        browser = MagicMock()
        browser.close = MagicMock(side_effect=browser_close_side_effect)
        context = MagicMock()
        page = page or MagicMock()
        context.new_page = MagicMock(return_value=page)
        with patch('impl.taobao_guanghe.platform.create_browser_sync',
                   return_value=browser) as cbs, \
             patch('impl.taobao_guanghe.platform.create_context_sync',
                   return_value=context) as ccs, \
             patch('impl.taobao_guanghe.platform.logger'):
            _run(p.open_creator_center(cookie_name))
            for _ in range(200):
                if browser.close.called:
                    break
                _time.sleep(0.02)
        return browser, context, page, cbs, ccs

    def test_starts_thread(self):
        p = _mk_platform()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        browser, _context, page, cbs, ccs = self._run_occ(
            p, 'occ.json', page=page
        )
        cbs.assert_called_once_with(headless=False)
        ccs.assert_called_once()
        page.goto.assert_called_once_with(_GUANGHE_HOME_URL)
        page.wait_for_event.assert_called_once_with('close', timeout=0)
        browser.close.assert_called_once()

    def test_wait_event_error_swallowed(self):
        p = _mk_platform()
        page = MagicMock()
        page.wait_for_event = MagicMock(side_effect=RuntimeError('boom'))
        browser, _context, _page, _cbs, _ccs = self._run_occ(
            p, 'occ2.json', page=page
        )
        browser.close.assert_called_once()

    def test_browser_close_error_swallowed(self):
        p = _mk_platform()
        page = MagicMock()
        page.wait_for_event = MagicMock()
        browser, _context, _page, _cbs, _ccs = self._run_occ(
            p, 'occ3.json', page=page, browser_close_side_effect=RuntimeError('boom')
        )
        browser.close.assert_called_once()
