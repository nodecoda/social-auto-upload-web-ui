"""视频号(channels) publish_video 编排层契约测试（T24）。

channels 无独立 _upload_one_video: DOM 操作内联在 async _do_upload 中,
依赖模块级 helper。本批 patch 全部 helper + browser/context 链,
只测编排契约: 文件×账号笛卡尔积 / 参数透传 / 定时条件调用 / 草稿提交。
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.channels.platform import ChannelsPlatform

# _do_upload 内 await 的模块级 helper
_HELPERS = [
    '_upload_video_file', '_fill_description', '_fill_title_and_tags',
    '_apply_collection', '_apply_location', '_apply_activity',
    '_apply_original_statement', '_apply_mark_tag', '_wait_for_upload_complete',
    'set_thumbnail', 'set_schedule', '_set_short_title', '_submit_publish',
]


def _make_platform():
    return ChannelsPlatform()


def _make_browser_chain():
    """构建 browser → context → page 的 async mock 链。"""
    browser = MagicMock()
    browser.is_connected = lambda: False
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_url = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    context.storage_state = AsyncMock()
    return browser, context, page


def _run_publish(platform, **kwargs):
    """patch helper + browser 链运行 publish_video, 返回 (result, helper_mocks, page)。"""
    browser, context, page = _make_browser_chain()
    helper_mocks = {name: AsyncMock() for name in _HELPERS}
    patches = [
        patch('impl.channels.platform.' + name, helper_mocks[name])
        for name in _HELPERS
    ]
    patches += [
        patch.object(platform, 'create_browser', AsyncMock(return_value=browser)),
        patch.object(platform, 'create_context', AsyncMock(return_value=context)),
        patch.object(platform, 'close_browser', AsyncMock()),
    ]
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch('impl.channels.platform.parse_schedule_time', pst), \
         patch('impl.channels.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.channels.platform.bind_account_name', MagicMock()), \
         patch.multiple('impl.channels.platform', **{n: m for n, m in helper_mocks.items()}):
        for p in patches:
            p.start()
        try:
            result = asyncio.run(platform.publish_video(**kwargs))
        finally:
            for p in patches:
                p.stop()
    return result, helper_mocks, page


# ── publish_video 编排 ──────────────────────────────────────────────────────

class TestPublishVideoOrchestration:
    def test_cartesian_product_2files_2accounts(self):
        inst = _make_platform()
        result, mocks, _ = _run_publish(
            inst, title='T', files=['/v1.mp4', '/v2.mp4'],
            account_file=['a.json', 'b.json'], desc='d',
        )
        assert result is True
        assert mocks['_submit_publish'].await_count == 4
        uploads = mocks['_upload_video_file'].await_args_list
        assert len(uploads) == 4
        for i, call in enumerate(uploads):
            assert call.args[1] == f'/v{i // 2 + 1}.mp4'

    def test_param_passthrough(self):
        inst = _make_platform()
        _, mocks, _ = _run_publish(
            inst,
            title='标题', files=['/v.mp4'], tags=['t1'], account_file=['a.json'],
            desc='描述', category='原创',
            channels_collection_name='合集A', channels_location_name='北京',
            channels_activity_name='活动X', channels_activity_id='活动X|发起人',
            channels_mark_tag='自行拍摄', channels_shoot_date='2026-08-01',
            channels_shoot_region=['中国', '北京'], channels_repost_source='https://example.com',
        )
        mocks['_fill_title_and_tags'].assert_awaited_once()
        fill_call = mocks['_fill_title_and_tags'].await_args
        assert fill_call.args[1] == '标题'
        assert fill_call.args[2] == ['t1']
        assert mocks['_fill_description'].await_args.args[1] == '描述'
        assert mocks['_apply_collection'].await_args.args[1] == '合集A'
        assert mocks['_apply_location'].await_args.args[1] == '北京'
        assert mocks['_apply_activity'].await_args.args[1:] == ('活动X', '活动X|发起人')
        assert mocks['_apply_original_statement'].await_args.args[1] == '原创'
        assert mocks['_apply_mark_tag'].await_args.args[1:] == (
            '自行拍摄', '2026-08-01', ['中国', '北京'], 'https://example.com')

    def test_cover_passthrough(self):
        inst = _make_platform()
        _, mocks, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_path='/legacy.png', thumbnail_landscape_path='/l.png',
            thumbnail_portrait_path='/p.png',
        )
        call = mocks['set_thumbnail'].await_args
        # 方向图优先, thumbnail_path 作兜底: 有横竖图时直接透传
        assert call.kwargs['paths'] == {'portrait': '/p.png', 'landscape': '/l.png'}

    def test_cover_thumbnail_path_fallback(self):
        """方向图缺失时用 thumbnail_path 兜底（与原实现 cover_entry_defs 一致）。"""
        inst = _make_platform()
        _, mocks, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_path='/legacy.png',
        )
        call = mocks['set_thumbnail'].await_args
        assert call.kwargs['paths'] == {'portrait': '/legacy.png', 'landscape': '/legacy.png'}

    def test_cover_missing_skips(self):
        """无任何封面参数时 paths 为空, 原语内部跳过上传。"""
        inst = _make_platform()
        _, mocks, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
        )
        call = mocks['set_thumbnail'].await_args
        assert call.kwargs['paths'] == {}

    def test_schedule_time_conditional(self):
        """enableTimer + publish_date != 0 → 调原语 set_schedule; immediate → 不调。"""
        inst = _make_platform()
        _, mocks, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            enableTimer=True, schedule_time_str='2026-08-21 10:00',
        )
        assert mocks['set_schedule'].await_count == 1
        assert mocks['set_schedule'].await_args.args[1] == datetime(
            2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))

    def test_no_schedule_no_timer_call(self):
        inst = _make_platform()
        _, mocks, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert mocks['set_schedule'].await_count == 0

    def test_submit_publish_draft_flag(self):
        inst = _make_platform()
        _, mocks, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'], is_draft=True,
        )
        assert mocks['_submit_publish'].await_args.args[1] is True

    def test_submit_publish_normal(self):
        inst = _make_platform()
        _, mocks, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'])
        assert mocks['_submit_publish'].await_args.args[1] is False

    def test_cookie_storage_state_path(self):
        inst = _make_platform()
        browser, context, _ = _make_browser_chain()
        with patch.object(inst, 'create_browser', AsyncMock(return_value=browser)), \
             patch.object(inst, 'create_context', AsyncMock(return_value=context)), \
             patch.object(inst, 'close_browser', AsyncMock()), \
             patch('impl.channels.platform._upload_video_file', AsyncMock()), \
             patch('impl.channels.platform._fill_description', AsyncMock()), \
             patch('impl.channels.platform._fill_title_and_tags', AsyncMock()), \
             patch('impl.channels.platform._apply_collection', AsyncMock()), \
             patch('impl.channels.platform._apply_location', AsyncMock()), \
             patch('impl.channels.platform._apply_activity', AsyncMock()), \
             patch('impl.channels.platform._apply_original_statement', AsyncMock()), \
             patch('impl.channels.platform._apply_mark_tag', AsyncMock()), \
             patch('impl.channels.platform._wait_for_upload_complete', AsyncMock()), \
             patch('impl.channels.platform.set_thumbnail', AsyncMock()), \
             patch('impl.channels.platform.set_schedule', AsyncMock()), \
             patch('impl.channels.platform._set_short_title', AsyncMock()), \
             patch('impl.channels.platform._submit_publish', AsyncMock()), \
             patch('impl.channels.platform.parse_schedule_time', MagicMock(return_value=[0])), \
             patch('impl.channels.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.channels.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], account_file=['u1.json']))
            expected = str(Path(BASE_DIR / 'cookiesFile' / 'u1.json'))
            inst.create_context.assert_awaited_once_with(browser, storage_state=expected)
            context.storage_state.assert_awaited_once_with(path=expected)

    def test_defaults_no_files_no_accounts(self):
        inst = _make_platform()
        result, mocks, _ = _run_publish(inst, title='T')
        assert result is True
        assert mocks['_submit_publish'].await_count == 0
