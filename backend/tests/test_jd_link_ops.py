"""京东关联商品/小说链接操作契约测试（T27）。

impl/jd/_jd_link_ops.py 是纯 DOM 交互层(frame mock 驱动):
- 纯函数: trace_signature / _page_of / LocateResult
- 商品抓取: scrape_total / scrape_products (skuId 提取优先级)
- 抽屉与 radio: switch_radio / click_add_card / wait_panel_ready
- 发布 iframe 识别: wait_publish_frame
- 小说: scrape_novels / search_novels / select_novel
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from impl.jd._jd_link_ops import (
    LocateResult,
    _page_of,
    click_add_card,
    scrape_novels,
    scrape_products,
    scrape_total,
    search_novels,
    select_novel,
    switch_radio,
    trace_signature,
    wait_for_selector,
    wait_panel_ready,
    wait_publish_frame,
)


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def _make_el(inner_text='', attr=None, value=None):
    """fake DOM element: inner_text / get_attribute / query_selector。"""
    el = MagicMock()
    el.inner_text = AsyncMock(return_value=inner_text)
    if attr is not None:
        el.get_attribute = AsyncMock(return_value=attr)
    else:
        el.get_attribute = AsyncMock(return_value=value)
    return el


class _FakePage:
    """真实对象模拟 Page:不可调用,可挂 keyboard 等属性。"""


def _make_frame():
    frame = MagicMock()
    el = MagicMock()
    el.click = AsyncMock()
    frame.wait_for_selector = AsyncMock(return_value=el)
    frame.query_selector = AsyncMock(return_value=None)
    frame.query_selector_all = AsyncMock(return_value=[])
    frame.evaluate = AsyncMock(return_value=True)
    loc_el = MagicMock()
    loc_el.click = AsyncMock()
    loc_el.press_sequentially = AsyncMock()
    frame.locator = MagicMock(return_value=loc_el)
    return frame


# ── 纯函数 ─────────────────────────────────────────────────────────────────

class TestPureFunctions:
    def test_trace_signature_full(self):
        assert trace_signature({'keyword': '手机', 'page': 3}) == ('手机', 3)

    def test_trace_signature_defaults(self):
        assert trace_signature({}) == ('', 1)

    def test_trace_signature_missing_keys(self):
        assert trace_signature({'keyword': '电脑'}) == ('电脑', 1)

    def test_page_of_returns_page_directly(self):
        page = MagicMock()
        page.keyboard = MagicMock()
        assert _page_of(page) is page

    def test_page_of_uses_frame_page_property(self):
        # 真实 Page 不可调用,必须用非 callable 对象模拟(MagicMock 自身可调用,
        # 会误触发 _page_of 的 callable 兜底)
        frame = MagicMock()
        del frame.keyboard  # MagicMock 自动生成 keyboard,删掉模拟无 keyboard 的 Frame
        page = object()
        frame.page = page
        assert _page_of(frame) is page

    def test_page_of_callable_fallback(self):
        frame = MagicMock()
        del frame.keyboard
        page = MagicMock()
        frame.page = lambda: page
        assert _page_of(frame) is page

    def test_locate_result_defaults(self):
        r = LocateResult()
        assert r.checked == []
        assert r.already == []
        assert r.disabled == []
        assert r.missing == []


# ── 商品抓取 ───────────────────────────────────────────────────────────────

class TestScrapeTotal:
    def test_parses_count(self):
        frame = _make_frame()
        frame.query_selector = AsyncMock(return_value=_make_el(inner_text='共 12 条'))
        assert _run(scrape_total(frame)) == 12

    def test_single_count(self):
        frame = _make_frame()
        frame.query_selector = AsyncMock(return_value=_make_el(inner_text='共 1 条'))
        assert _run(scrape_total(frame)) == 1

    def test_no_element_returns_zero(self):
        frame = _make_frame()
        frame.query_selector = AsyncMock(return_value=None)
        assert _run(scrape_total(frame)) == 0

    def test_no_digits_returns_zero(self):
        frame = _make_frame()
        frame.query_selector = AsyncMock(return_value=_make_el(inner_text='无数据'))
        assert _run(scrape_total(frame)) == 0


class TestScrapeProducts:
    def test_extracts_sku_id_from_image_url(self):
        card = MagicMock()
        card.query_selector = AsyncMock(side_effect=lambda sel: {
            '._sku-name_jvzh5_204': _make_el(inner_text='商品A'),
            '._sku-card-img_jvzh5_154': _make_el(attr='//m.360buyimg.com/jfs/123/abc.png'),
            '._price-value_jvzh5_277': _make_el(inner_text='99.9'),
            '._shop-name_jvzh5_295': _make_el(inner_text='店铺X'),
            '.jd-checkbox-input': None,
        }[sel])
        frame = _make_frame()
        frame.query_selector_all = AsyncMock(return_value=[card])
        items = _run(scrape_products(frame))
        assert items == [{
            'title': '商品A', 'image': '//m.360buyimg.com/jfs/123/abc.png',
            'id': 'abc', 'price': '99.9', 'shop_name': '店铺X',
        }]

    def test_sku_id_fallback_checkbox_value(self):
        card = MagicMock()
        card.query_selector = AsyncMock(side_effect=lambda sel: {
            '._sku-name_jvzh5_204': _make_el(inner_text='B'),
            '._sku-card-img_jvzh5_154': _make_el(attr=''),
            '._price-value_jvzh5_277': _make_el(inner_text=''),
            '._shop-name_jvzh5_295': _make_el(inner_text=''),
            '.jd-checkbox-input': _make_el(value='SKU999'),
        }[sel])
        frame = _make_frame()
        frame.query_selector_all = AsyncMock(return_value=[card])
        items = _run(scrape_products(frame))
        assert items[0]['id'] == 'SKU999'

    def test_sku_id_fallback_data_sku(self):
        card = MagicMock()
        cb = MagicMock()
        cb.get_attribute = AsyncMock(side_effect=lambda name: None if name == 'value' else 'DSKU1')
        card.query_selector = AsyncMock(side_effect=lambda sel: {
            '._sku-name_jvzh5_204': _make_el(inner_text='C'),
            '._sku-card-img_jvzh5_154': _make_el(attr=''),
            '._price-value_jvzh5_277': _make_el(inner_text=''),
            '._shop-name_jvzh5_295': _make_el(inner_text=''),
            '.jd-checkbox-input': cb,
        }[sel])
        frame = _make_frame()
        frame.query_selector_all = AsyncMock(return_value=[card])
        items = _run(scrape_products(frame))
        assert items[0]['id'] == 'DSKU1'

    def test_no_cards_returns_empty(self):
        frame = _make_frame()
        frame.query_selector_all = AsyncMock(return_value=[])
        assert _run(scrape_products(frame)) == []


# ── radio / 抽屉 ───────────────────────────────────────────────────────────

class TestRadioAndDrawer:
    def test_switch_radio_product(self):
        frame = _make_frame()
        _run(switch_radio(frame, 'product'))
        selector = frame.wait_for_selector.await_args.args[0]
        assert "value='1'" in selector

    def test_switch_radio_novel(self):
        frame = _make_frame()
        _run(switch_radio(frame, 'novel'))
        selector = frame.wait_for_selector.await_args.args[0]
        assert "value='3'" in selector

    def test_click_add_card_ok(self):
        frame = _make_frame()
        frame.evaluate = AsyncMock(return_value=True)
        _run(click_add_card(frame))
        assert frame.evaluate.await_count == 1

    def test_click_add_card_not_found_raises(self):
        frame = _make_frame()
        frame.evaluate = AsyncMock(return_value=False)
        try:
            _run(click_add_card(frame))
        except RuntimeError as e:
            assert 'addgoods-upload' in str(e)
        else:
            raise AssertionError('expected RuntimeError')

    def test_wait_panel_ready(self):
        frame = _make_frame()
        with patch('impl.jd._jd_link_ops.sleep', AsyncMock()):
            _run(wait_panel_ready(frame, timeout=1))
        selectors = [c.args[0] for c in frame.wait_for_selector.await_args_list]
        assert '.jd-drawer-wrapper-body' in selectors
        assert '._sku-card-mygoods-con_jvzh5_77' in selectors


# ── 发布 iframe 识别 ───────────────────────────────────────────────────────

class TestWaitPublishFrame:
    def test_finds_iframe_by_url(self):
        main = MagicMock()
        main.url = 'https://dr.jd.com/jm/#/n/publish-video.html'
        target = MagicMock()
        target.url = 'https://dr.jd.com/n/publish-video.html'
        page = MagicMock()
        page.main_frame = main
        page.frames = [main, target]
        with patch('asyncio.sleep', AsyncMock()):
            result = _run(wait_publish_frame(page, timeout=1))
        assert result is target

    def test_skips_main_frame(self):
        main = MagicMock()
        main.url = 'https://dr.jd.com/n/publish-video.html'  # 即使 URL 匹配也跳过
        target = MagicMock()
        target.url = 'https://dr.jd.com/n/publish-video.html'
        page = MagicMock()
        page.main_frame = main
        page.frames = [main, target]
        with patch('asyncio.sleep', AsyncMock()):
            result = _run(wait_publish_frame(page, timeout=1))
        assert result is target

    def test_timeout_raises(self):
        page = MagicMock()
        page.main_frame = MagicMock()
        page.main_frame.url = 'x'
        page.frames = [page.main_frame]
        with patch('asyncio.sleep', AsyncMock()):
            try:
                _run(wait_publish_frame(page, timeout=0.3))
            except RuntimeError as e:
                assert '未找到发布表单 iframe' in str(e)
            else:
                raise AssertionError('expected RuntimeError')


# ── 小说 ───────────────────────────────────────────────────────────────────

class TestNovelScraping:
    def test_scrape_novels_parses_info(self):
        opt = MagicMock()
        name_el = _make_el(inner_text='小说名')
        img_el = _make_el(attr='/img/cover.png')
        info_el = _make_el(inner_text='音乐舞蹈 | 142人已读')
        opt.query_selector = AsyncMock(side_effect=lambda sel: {
            '.related-book-item-right-name': name_el,
            '.crefe-custom-image': img_el,
            '.related-book-item-right-info': info_el,
        }[sel])
        frame = _make_frame()
        frame.query_selector_all = AsyncMock(return_value=[opt])
        items = _run(scrape_novels(frame))
        assert items == [{
            'id': '', 'title': '小说名', 'image': '/img/cover.png',
            'category': '音乐舞蹈', 'read_count': '142',
        }]

    def test_scrape_novels_skips_bad_option(self):
        bad = MagicMock()
        bad.query_selector = AsyncMock(side_effect=Exception('boom'))
        frame = _make_frame()
        frame.query_selector_all = AsyncMock(return_value=[bad])
        assert _run(scrape_novels(frame)) == []

    def test_search_novels_flow(self):
        frame = _make_frame()
        select = MagicMock()
        select.evaluate = AsyncMock(return_value=False)  # aria-expanded='false' -> bool False
        select.click = AsyncMock()
        frame.wait_for_selector = AsyncMock(side_effect=[select, None])
        search_input = MagicMock()
        search_input.click = AsyncMock()
        search_input.press_sequentially = AsyncMock()
        frame.locator.return_value = search_input
        keyboard = MagicMock()
        keyboard.press = AsyncMock()
        page = _FakePage()  # 真实对象不可调用(MagicMock 可调用会误触发 callable 兜底)
        page.keyboard = keyboard
        del frame.keyboard  # 模拟 Frame(无 keyboard),让 _page_of 走 frame.page
        frame.page = page
        frame.query_selector_all = AsyncMock(return_value=[])
        with patch('impl.jd._jd_link_ops.sleep', AsyncMock()):
            items = _run(search_novels(frame, '修仙'))
        assert items == []
        assert select.click.await_count == 1
        search_input.press_sequentially.assert_awaited_once_with('修仙', delay=100)

    def test_select_novel_clicks_matching_option(self):
        opt = MagicMock()
        name_el = _make_el(inner_text='目标小说')
        opt.query_selector = AsyncMock(return_value=name_el)
        opt.click = AsyncMock()
        frame = _make_frame()
        frame.query_selector_all = AsyncMock(return_value=[opt])
        with patch('impl.jd._jd_link_ops.sleep', AsyncMock()):  # 生产真实 sleep 累积 2.5s
            _run(select_novel(frame, '目标小说'))
        opt.click.assert_awaited_once()


# ── 等待工具 ───────────────────────────────────────────────────────────────

class TestWaitTools:
    def test_wait_for_selector_visible(self):
        frame = _make_frame()
        _run(wait_for_selector(frame, '.sel', timeout=5))
        frame.wait_for_selector.assert_awaited_once_with('.sel', timeout=5000, state='visible')
