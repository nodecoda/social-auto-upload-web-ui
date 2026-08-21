"""淘宝光合「关联商品/店铺」DOM 操作契约测试（T29）。

impl/taobao_guanghe/_link_ops.py 是纯 DOM 交互层(frame mock 驱动):
- 抓取: scrape_products / scrape_shops / scrape / scrape_filters (evaluate 驱动)
- 面板: switch_radio / click_add_card / wait_panel_ready / switch_tab
- 筛选/搜索/翻页: click_filter / search / load_more
- 勾选: _click_item_by_id (evaluate 状态透传)

locate_and_check 已有 test_guanghe_link_ops_locate.py 覆盖,这里不重复。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from impl.taobao_guanghe import _link_ops


def _run(coro):
    return asyncio.run(coro)


def _mk_frame(evaluate_return=None):
    frame = MagicMock()
    frame.evaluate = AsyncMock(return_value=evaluate_return)
    frame.wait_for_function = AsyncMock()
    return frame


def _mk_locator():
    """frame.locator(...).first / get_by_text(...).first 链的可控 locator。"""
    first = MagicMock()
    first.wait_for = AsyncMock()
    first.evaluate = AsyncMock(return_value=False)
    first.click = AsyncMock()
    first.count = AsyncMock(return_value=1)
    first.fill = AsyncMock()
    first.press = AsyncMock()
    first.scroll_into_view_if_needed = AsyncMock()
    loc = MagicMock()
    loc.first = first
    return loc


# ── 抓取 ───────────────────────────────────────────────────────────────────

class TestScrape:
    def test_scrape_products_parses(self):
        data = {"items": [{"id": "111", "title": "A", "disabled": False}], "has_more": True}
        frame = _mk_frame(data)
        items, has_more = _run(_link_ops.scrape_products(frame))
        assert items == data["items"]
        assert has_more is True

    def test_scrape_products_missing_keys(self):
        frame = _mk_frame({})
        assert _run(_link_ops.scrape_products(frame)) == ([], False)

    def test_scrape_products_exception_fallback(self):
        frame = _mk_frame()
        frame.evaluate = AsyncMock(side_effect=RuntimeError('boom'))
        assert _run(_link_ops.scrape_products(frame)) == ([], False)

    def test_scrape_shops_parses(self):
        data = {"items": [{"id": "s1", "title": "店A"}], "has_more": False}
        frame = _mk_frame(data)
        items, has_more = _run(_link_ops.scrape_shops(frame))
        assert items == data["items"]
        assert has_more is False

    def test_scrape_shops_exception_fallback(self):
        frame = _mk_frame()
        frame.evaluate = AsyncMock(side_effect=RuntimeError('boom'))
        assert _run(_link_ops.scrape_shops(frame)) == ([], False)

    def test_scrape_dispatch_product(self):
        frame = _mk_frame()
        with patch.object(_link_ops, 'scrape_products', AsyncMock(return_value=([1], False))) as sp, \
             patch.object(_link_ops, 'scrape_shops', AsyncMock(return_value=([2], True))):
            assert _run(_link_ops.scrape(frame, 'product')) == ([1], False)
            assert _run(_link_ops.scrape(frame, 'shop')) == ([2], True)
            sp.assert_awaited_once()
        # 未知 type 走 shop 分支
        with patch.object(_link_ops, 'scrape_shops', AsyncMock(return_value=([], False))) as ss:
            assert _run(_link_ops.scrape(frame, 'other')) == ([], False)
            ss.assert_awaited_once()

    def test_scrape_filters_parses(self):
        data = {"rules": ["智能推荐"], "categories": ["服饰"]}
        frame = _mk_frame(data)
        assert _run(_link_ops.scrape_filters(frame)) == data

    def test_scrape_filters_none_and_exception(self):
        frame = _mk_frame(None)
        assert _run(_link_ops.scrape_filters(frame)) == {"rules": [], "categories": []}
        frame2 = _mk_frame()
        frame2.evaluate = AsyncMock(side_effect=RuntimeError('boom'))
        assert _run(_link_ops.scrape_filters(frame2)) == {"rules": [], "categories": []}


# ── 面板操作 ───────────────────────────────────────────────────────────────

class TestPanelOps:
    def test_switch_radio_unchecked_clicks(self):
        frame = _mk_frame()
        loc = _mk_locator()
        frame.locator.return_value = loc
        with patch('asyncio.sleep', AsyncMock()):
            _run(_link_ops.switch_radio(frame, 'product'))
        frame.locator.assert_called_once_with('.next-radio-label:has-text("商品")')
        loc.first.wait_for.assert_awaited_once_with(state="visible", timeout=10000)
        loc.first.click.assert_awaited_once()

    def test_switch_radio_checked_no_click(self):
        frame = _mk_frame()
        loc = _mk_locator()
        loc.first.evaluate = AsyncMock(return_value=True)
        frame.locator.return_value = loc
        _run(_link_ops.switch_radio(frame, 'shop'))
        frame.locator.assert_called_once_with('.next-radio-label:has-text("店铺")')
        loc.first.click.assert_not_called()

    def test_click_add_card(self):
        frame = _mk_frame()
        loc = _mk_locator()
        frame.get_by_text.return_value = loc
        with patch('asyncio.sleep', AsyncMock()):
            _run(_link_ops.click_add_card(frame, 'product'))
        frame.get_by_text.assert_called_once_with('添加商品', exact=True)
        loc.first.wait_for.assert_awaited_once_with(state="visible", timeout=8000)
        loc.first.click.assert_awaited_once()

    def test_wait_panel_ready_product(self):
        frame = _mk_frame()
        loc = _mk_locator()
        frame.locator.return_value = loc
        _run(_link_ops.wait_panel_ready(frame, 'product'))
        frame.locator.assert_called_once_with(
            '.next-tabs-tab:has-text("已购商品"), .next-tabs-tab:has-text("平台优选")'
        )
        loc.first.wait_for.assert_awaited_once_with(state="visible", timeout=10000)

    def test_wait_panel_ready_shop(self):
        frame = _mk_frame()
        loc = _mk_locator()
        frame.locator.return_value = loc
        _run(_link_ops.wait_panel_ready(frame, 'shop'))
        frame.locator.assert_called_once_with('input[placeholder*="店铺"]')
        loc.first.wait_for.assert_awaited_once_with(state="visible", timeout=10000)

    def test_switch_tab_invalid_returns(self):
        frame = _mk_frame()
        _run(_link_ops.switch_tab(frame, 'bogus'))
        frame.locator.assert_not_called()

    def test_switch_tab_wait_timeout_returns(self):
        frame = _mk_frame()
        loc = _mk_locator()
        loc.first.wait_for = AsyncMock(side_effect=TimeoutError('nope'))
        frame.locator.return_value = loc
        _run(_link_ops.switch_tab(frame, 'bought'))
        loc.first.click.assert_not_called()

    def test_switch_tab_active_no_click(self):
        frame = _mk_frame()
        loc = _mk_locator()
        loc.first.evaluate = AsyncMock(return_value=True)
        frame.locator.return_value = loc
        _run(_link_ops.switch_tab(frame, 'preferred'))
        frame.locator.assert_called_once_with('.next-tabs-tab:has-text("平台优选")')
        loc.first.click.assert_not_called()

    def test_switch_tab_inactive_clicks_and_waits(self):
        frame = _mk_frame()
        loc = _mk_locator()
        frame.locator.return_value = loc
        with patch('asyncio.sleep', AsyncMock()):
            _run(_link_ops.switch_tab(frame, 'bought'))
        loc.first.click.assert_awaited_once()
        frame.wait_for_function.assert_awaited_once()

    def test_switch_tab_wait_function_exception_ok(self):
        """click 后 wait_for_function 超时 → 兜底不抛。"""
        frame = _mk_frame()
        frame.wait_for_function = AsyncMock(side_effect=TimeoutError('slow'))
        loc = _mk_locator()
        frame.locator.return_value = loc
        with patch('asyncio.sleep', AsyncMock()):
            _run(_link_ops.switch_tab(frame, 'bought'))
        loc.first.click.assert_awaited_once()

    def test_click_filter_no_label_returns(self):
        frame = _mk_frame()
        panel = _mk_locator()
        label = _mk_locator()
        label.first.count = AsyncMock(return_value=0)
        panel.get_by_text.return_value = label
        frame.locator.return_value = panel
        _run(_link_ops.click_filter(frame, '推荐规则', '智能推荐'))
        frame.evaluate.assert_not_called()

    def test_click_filter_evaluates(self):
        frame = _mk_frame()
        panel = _mk_locator()
        label = _mk_locator()
        label.first.count = AsyncMock(return_value=1)
        panel.get_by_text.return_value = label
        frame.locator.return_value = panel
        with patch('asyncio.sleep', AsyncMock()):
            _run(_link_ops.click_filter(frame, '品类筛选', '服饰'))
        frame.locator.assert_called_once_with('[role="tabpanel"][aria-hidden="false"]')
        label.first.evaluate.assert_awaited_once()
        assert label.first.evaluate.await_args.args[1] == '服饰'

    def test_search_fills_and_presses(self):
        frame = _mk_frame()
        panel = _mk_locator()
        inp = _mk_locator()
        panel.locator.return_value = inp
        frame.locator.return_value = panel
        with patch('asyncio.sleep', AsyncMock()):
            _run(_link_ops.search(frame, '连衣裙'))
        inp.first.fill.assert_awaited()  # 至少两次: 清空 + 填入
        assert inp.first.fill.await_count == 2
        inp.first.press.assert_awaited_once_with('Enter')

    def test_search_empty_keyword_clears_only(self):
        frame = _mk_frame()
        panel = _mk_locator()
        inp = _mk_locator()
        panel.locator.return_value = inp
        frame.locator.return_value = panel
        with patch('asyncio.sleep', AsyncMock()):
            _run(_link_ops.search(frame, ''))
        assert inp.first.fill.await_count == 1
        inp.first.press.assert_awaited_once_with('Enter')

    def test_load_more_button_clicked(self):
        frame = _mk_frame()
        btn = _mk_locator()
        frame.get_by_text.return_value = btn
        with patch('asyncio.sleep', AsyncMock()):
            assert _run(_link_ops.load_more(frame)) is True
        btn.first.click.assert_awaited_once()

    def test_load_more_scroll_failure_still_clicks(self):
        frame = _mk_frame()
        btn = _mk_locator()
        btn.first.scroll_into_view_if_needed = AsyncMock(side_effect=RuntimeError('nope'))
        frame.get_by_text.return_value = btn
        with patch('asyncio.sleep', AsyncMock()):
            assert _run(_link_ops.load_more(frame)) is True
        btn.first.click.assert_awaited_once()

    def test_load_more_no_button_scrolls(self):
        frame = _mk_frame()
        btn = _mk_locator()
        btn.first.count = AsyncMock(return_value=0)
        frame.get_by_text.return_value = btn
        with patch('asyncio.sleep', AsyncMock()):
            assert _run(_link_ops.load_more(frame)) is False
        frame.evaluate.assert_awaited_once()

    def test_load_more_no_button_scroll_exception(self):
        frame = _mk_frame()
        btn = _mk_locator()
        btn.first.count = AsyncMock(return_value=0)
        frame.get_by_text.return_value = btn
        frame.evaluate = AsyncMock(side_effect=RuntimeError('boom'))
        with patch('asyncio.sleep', AsyncMock()):
            assert _run(_link_ops.load_more(frame)) is False

    def test_click_item_by_id_passthrough(self):
        frame = _mk_frame('clicked')
        assert _run(_link_ops._click_item_by_id(frame, 'product', '111')) == 'clicked'
        assert frame.evaluate.await_args.args[1] == {'id': '111', 'type': 'product'}
