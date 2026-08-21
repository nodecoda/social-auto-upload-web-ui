"""支付宝合集搜索/音乐列表浏览器 helper 契约测试（T8b）。

_search_compilation_via_browser:空视频 → 上传 → 等标题框 → fill 合集搜索框
→ 拦截 queryCompilationsByPublicId.json 响应。
_fetch_music_list_via_browser:等「添加音乐」按钮(3s) → 未出现则上传测试图 →
点开 modal → 拦截 queryAllMaterial.json → 解析 music 分类。
"""
import asyncio
import inspect
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
from blueprints.alipay_bp import _fetch_music_list_via_browser, _search_compilation_via_browser

_REAL_SLEEP = asyncio.sleep

FILE_INPUT = "input[type='file']"
TITLE_INPUT = "input[placeholder*='好的标题']"
COMPILATION_INPUT = "input[id$='_compilationInfo']"
IMG_INPUT = "input[type='file'][accept*='image']"
ADD_MUSIC = "button.ant-btn:has-text('添加音乐')"
MODAL = 'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")'


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
        if self.selector == ADD_MUSIC:
            self.page.fire_captured()

    async def fill(self, text):
        self.page.events.append(('fill', text))
        if self.selector == COMPILATION_INPUT:
            self.page.fire_captured()

    async def set_input_files(self, path):
        self.page.events.append(('set_input_files', str(path)))


class _FakeResponse:
    def __init__(self, url, data):
        self.url = url
        self._data = data

    async def json(self):
        return self._data


class _FakePage:
    def __init__(self, cfg):
        self.cfg = cfg
        self.events = []
        self._handlers = []

    def on(self, event, handler):
        if event == 'response':
            self._handlers.append(handler)

    def locator(self, selector):
        return _FakeLocator(self, selector)

    async def goto(self, *args, **kwargs):
        self.events.append(('goto',))
        await _REAL_SLEEP(0)

    async def wait_for_load_state(self, *args, **kwargs):
        pass

    def fire_captured(self):
        if not self.cfg.get('captured'):
            return
        resp = _FakeResponse(self.cfg['captured_url'], self.cfg['captured_data'])
        for h in self._handlers:
            asyncio.get_event_loop().create_task(h(resp))

    def cfg_visible_at(self, selector):
        if selector in self.cfg.get('visible', set()):
            return True
        # 上传测试图后「添加音乐」按钮出现
        return bool(
            selector == ADD_MUSIC and self.cfg.get('btn_after_upload')
            and any(e[0] == 'set_input_files' for e in self.events)
        )


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

    with patch('blueprints.alipay_bp.create_browser', side_effect=_fake_create_browser), \
         patch('blueprints.alipay_bp.create_context', side_effect=_fake_create_context), \
         patch('blueprints.alipay_bp.asyncio.sleep', side_effect=_fast_sleep):
        if len(inspect.signature(fn).parameters) == 1:
            result = asyncio.run(fn('cookies/x.json'))
        else:
            result = asyncio.run(fn('cookies/x.json', '关键词'))
    return result, page


# ── 合集搜索 ──────────────────────────────────────────────────────────────────

COMP_URL = 'https://qurey/api/queryCompilationsByPublicId.json'
COMP_CAPTURED = {
    'stat': 'ok',
    'result': {
        'list': [{'compilationId': 'c1', 'title': '合集1', 'coverUrl': 'u', 'category': 'cat', 'total': 5}],
        'total': 1,
        'hasMore': False,
    },
}


def _comp_cfg(**overrides):
    cfg = {
        'visible': {FILE_INPUT, TITLE_INPUT, COMPILATION_INPUT},
        'captured': True,
        'captured_url': COMP_URL,
        'captured_data': COMP_CAPTURED,
    }
    cfg.update(overrides)
    return cfg


def _patch_mp4_ok():
    return patch('blueprints.alipay_bp._create_minimal_mp4', side_effect=lambda p: p.write_bytes(b''))


def test_compilation_create_video_failure():
    with _patch_mp4_ok() if False else patch('blueprints.alipay_bp._create_minimal_mp4', side_effect=RuntimeError('no ffmpeg')):
        result, _ = _run(_search_compilation_via_browser, _comp_cfg())
    assert result == {'success': False, 'error': '创建空视频失败: no ffmpeg'}


def test_compilation_form_render_timeout():
    cfg = _comp_cfg(visible={FILE_INPUT, COMPILATION_INPUT})  # 标题框不可见
    with _patch_mp4_ok():
        result, _ = _run(_search_compilation_via_browser, cfg)
    assert result['success'] is False
    assert '等待表单渲染超时' in result['error']


def test_compilation_search_box_missing():
    cfg = _comp_cfg(visible={FILE_INPUT, TITLE_INPUT})  # 合集搜索框不可见
    with _patch_mp4_ok():
        result, _ = _run(_search_compilation_via_browser, cfg)
    assert result['success'] is False
    assert '未找到合集搜索框' in result['error']


def test_compilation_no_captured_response():
    cfg = _comp_cfg(captured=False)
    with _patch_mp4_ok():
        result, _ = _run(_search_compilation_via_browser, cfg)
    assert result == {'success': False, 'error': '未能拦截到合集搜索结果'}


def test_compilation_stat_not_ok():
    cfg = _comp_cfg(captured_data={'stat': 'fail', 'result': {}})
    with _patch_mp4_ok():
        result, _ = _run(_search_compilation_via_browser, cfg)
    assert result['success'] is False
    assert '接口返回 stat=fail' in result['error']
    assert result['data']['stat'] == 'fail'


def test_compilation_success():
    with _patch_mp4_ok():
        result, page = _run(_search_compilation_via_browser, _comp_cfg())
    assert result == {'success': True, 'data': {
        'list': [{'compilationId': 'c1', 'title': '合集1', 'coverUrl': 'u', 'category': 'cat', 'total': 5}],
        'total': 1,
        'hasMore': False,
    }}
    assert ('fill', '关键词') in page.events


# ── 音乐列表 ──────────────────────────────────────────────────────────────────

MUSIC_URL = 'https://alipay/queryAllMaterial.json'
MUSIC_CAPTURED = {
    'stat': 'ok',
    'result': {
        'materialTypes': [
            {'type': 'video', 'materials': []},
            {'type': 'music', 'materials': [{'materialDetails': [
                {'code': 'm1', 'name': '歌一', 'author': '甲',
                 'configs': '{"audioTime": 24}', 'snapshotImageUrl': 'c.png',
                 'resourceAccessUrl': 'a.mp3'},
            ]}]},
        ],
    },
}


def _music_cfg(**overrides):
    cfg = {
        'visible': {ADD_MUSIC, MODAL},
        'btn_after_upload': False,
        'captured': True,
        'captured_url': MUSIC_URL,
        'captured_data': MUSIC_CAPTURED,
    }
    cfg.update(overrides)
    return cfg


def _patch_jpeg_ok():
    return patch('blueprints.alipay_bp._create_test_jpeg', side_effect=lambda p: p.write_bytes(b'jpeg'))


def test_music_list_success_direct_click():
    with _patch_jpeg_ok():
        result, page = _run(_fetch_music_list_via_browser, _music_cfg())
    assert result['success'] is True
    assert result['data']['total'] == 1
    assert result['data']['list'][0]['musicId'] == 'm1'
    assert ('click', ADD_MUSIC) in page.events


def test_music_list_test_image_create_failed():
    """按钮未出现 + 测试图创建失败 → 直接报错。"""
    # 删除缓存测试图,确保 helper 真的调用 _create_test_jpeg
    from conf import BASE_DIR
    (BASE_DIR / '.alipay_music_test.jpg').unlink(missing_ok=True)
    cfg = _music_cfg(visible={MODAL}, btn_after_upload=False)
    with patch('blueprints.alipay_bp._create_test_jpeg', side_effect=RuntimeError('no PIL')):
        result, _ = _run(_fetch_music_list_via_browser, cfg)
    assert result == {'success': False, 'error': '「添加音乐」按钮未出现,且测试图创建失败'}


def test_music_list_upload_failure():
    """按钮未出现 → 上传测试图失败(img input 不可见)。"""
    cfg = _music_cfg(visible=set(), btn_after_upload=False)
    with _patch_jpeg_ok():
        result, _ = _run(_fetch_music_list_via_browser, cfg)
    assert result['success'] is False
    assert '上传测试图失败' in result['error']


def test_music_list_btn_still_missing_after_upload():
    """上传后按钮仍未出现 → 报错。"""
    cfg = _music_cfg(visible=set(), btn_after_upload=False)
    cfg['visible'] = {IMG_INPUT}
    with _patch_jpeg_ok():
        result, _ = _run(_fetch_music_list_via_browser, cfg)
    assert result['success'] is False
    assert '上传测试图后仍未出现「添加音乐」按钮' in result['error']


def test_music_list_upload_flow_success():
    """按钮未直接出现 → 上传测试图 → 按钮出现 → 成功。"""
    cfg = _music_cfg(visible={IMG_INPUT, MODAL}, btn_after_upload=True)
    with _patch_jpeg_ok():
        result, page = _run(_fetch_music_list_via_browser, cfg)
    assert result['success'] is True
    assert ('set_input_files',) in [e[:1] for e in page.events] or any(e[0] == 'set_input_files' for e in page.events)


def test_music_list_modal_not_open():
    cfg = _music_cfg(visible={ADD_MUSIC}, btn_after_upload=False)  # modal 不可见
    with _patch_jpeg_ok():
        result, _ = _run(_fetch_music_list_via_browser, cfg)
    assert result['success'] is False
    assert '音乐 modal 未打开' in result['error']


def test_music_list_no_captured():
    cfg = _music_cfg(captured=False)
    with _patch_jpeg_ok():
        result, _ = _run(_fetch_music_list_via_browser, cfg)
    assert result['success'] is False
    assert '未能拦截到 queryAllMaterial.json' in result['error']


def test_music_list_zero_music():
    """捕获到响应但 music 分类下无素材 → 报错。"""
    cfg = _music_cfg(captured_data={'stat': 'ok', 'result': {'materialTypes': [{'type': 'video', 'materials': []}]}})
    with _patch_jpeg_ok():
        result, _ = _run(_fetch_music_list_via_browser, cfg)
    assert result['success'] is False
    assert '解析出 0 首音乐' in result['error']
