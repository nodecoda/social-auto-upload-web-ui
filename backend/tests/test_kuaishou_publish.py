"""快手 publish_video 编排层契约测试（T22）。

publish_video(同步) → _publish_video_async: 标签≤4 前置校验 → 封面
竖版>横版>通用 → 排期(越界兜底 0) → 文件×账号笛卡尔积 → _upload_single。
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.kuaishou.platform import KuaishouPlatform


def _make_platform():
    return KuaishouPlatform()


def _run_publish(platform, **kwargs):
    """以 mock _upload_single / 排期 / 账号名 运行 publish_video,返回 (result, upload, pst)。"""
    upload = AsyncMock()
    n_files = len(kwargs.get('files') or [])
    pst = MagicMock(return_value=[
        datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
    ] * max(n_files, 1))
    with patch.object(platform, '_upload_single', upload), \
         patch('impl.kuaishou.platform.parse_schedule_time', pst), \
         patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value='昵称'), \
         patch('impl.kuaishou.platform.bind_account_name', MagicMock()):
        result = asyncio.run(platform.publish_video(**kwargs))
    return result, upload, pst


# ── 标签上限校验(≤4) ───────────────────────────────────────────────────────

class TestTagPreflight:
    def test_tags_over_4_raises(self):
        inst = _make_platform()
        with pytest.raises(ValueError, match="标签最多 4 个"):
            _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'], tags=['t1', 't2', 't3', 't4', 't5'])

    def test_exactly_4_tags_ok(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            tags=['t1', 't2', 't3', 't4'],
        )
        assert result is True
        assert upload.await_count == 1
        assert upload.await_args.kwargs['tags'] == ['t1', 't2', 't3', 't4']

    def test_fail_logs_error(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.kuaishou.platform.logger', logger):
            with pytest.raises(ValueError):
                _run_publish(inst, title='T', files=['/v.mp4'], account_file=['a.json'], tags=['t'] * 5)
            assert any(
                c.args[0] == '[发布校验] 快手标签超过上限: 当前 %d 个, 最多 %d 个'
                and c.args[1:] == (5, 4)
                for c in logger.error.call_args_list
            )


# ── publish_video 编排 ──────────────────────────────────────────────────────

class TestPublishVideoOrchestration:
    def test_cartesian_product_2files_2accounts(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(
            inst, title='T', files=['/v1.mp4', '/v2.mp4'],
            account_file=['a.json', 'b.json'], desc='d',
        )
        assert result is True
        assert upload.await_count == 4
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['video_path'] == f'/v{i // 2 + 1}.mp4'
            assert call.kwargs['cookie_path'].endswith(f'{"ab"[i % 2]}.json')

    def test_cover_priority_portrait(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_portrait_path='/p.png', thumbnail_landscape_path='/l.png',
            thumbnail_path='/legacy.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/p.png'

    def test_cover_fallback_landscape(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_landscape_path='/l.png', thumbnail_path='/legacy.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/l.png'

    def test_cover_fallback_legacy(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            thumbnail_path='/legacy.png',
        )
        assert upload.await_args.kwargs['thumbnail_path'] == '/legacy.png'

    def test_author_declaration_ai_content_preferred(self):
        """ai_content 优先于 author_declaration 别名。"""
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            ai_content='AI生成', author_declaration='旧别名',
        )
        assert upload.await_args.kwargs['author_declaration'] == 'AI生成'

    def test_author_declaration_alias_fallback(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst, title='T', files=['/v.mp4'], account_file=['a.json'],
            author_declaration='旧别名',
        )
        assert upload.await_args.kwargs['author_declaration'] == '旧别名'

    def test_param_passthrough(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(
            inst,
            title='标题', files=['/v.mp4'], tags=['t1'], account_file=['a.json'],
            desc='描述', video_format='portrait', enableTimer=True,
        )
        call = upload.await_args
        assert call.kwargs['title'] == '标题'
        assert call.kwargs['desc'] == '描述'
        assert call.kwargs['video_format'] == 'portrait'
        assert call.kwargs['enable_timer'] is True

    def test_cookie_path_resolution(self):
        inst = _make_platform()
        _, upload, _ = _run_publish(inst, title='T', files=['/v.mp4'], account_file=['u1.json'])
        assert upload.await_args.kwargs['cookie_path'] == str(Path(BASE_DIR / 'cookiesFile' / 'u1.json'))

    def test_schedule_time_per_file_index(self):
        inst = _make_platform()
        dt1 = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        dt2 = datetime(2026, 8, 22, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        pst = MagicMock(return_value=[dt1, dt2])
        upload = AsyncMock()
        with patch.object(inst, '_upload_single', upload), \
             patch('impl.kuaishou.platform.parse_schedule_time', pst), \
             patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.kuaishou.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4'], account_file=['a.json', 'b.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        for i, call in enumerate(upload.await_args_list):
            assert call.kwargs['publish_date'] == pst.return_value[i // 2]

    def test_publish_date_out_of_range_falls_back_zero(self):
        """排期列表短于文件数时, 越界文件 publish_date=0。"""
        inst = _make_platform()
        dt1 = datetime(2026, 8, 21, 10, 0, tzinfo=ZoneInfo('Asia/Shanghai'))
        pst = MagicMock(return_value=[dt1])  # 只有 1 个时间, 3 个文件
        upload = AsyncMock()
        with patch.object(inst, '_upload_single', upload), \
             patch('impl.kuaishou.platform.parse_schedule_time', pst), \
             patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.kuaishou.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(
                title='T', files=['/v1.mp4', '/v2.mp4', '/v3.mp4'], account_file=['a.json'],
                enableTimer=True, schedule_time_str='2026-08-21 10:00',
            ))
        dates = [c.kwargs['publish_date'] for c in upload.await_args_list]
        assert dates == [dt1, 0, 0]

    def test_strategy_log_immediate(self):
        inst = _make_platform()
        logger = MagicMock()
        with patch('impl.kuaishou.platform.logger', logger), \
             patch.object(inst, '_upload_single', AsyncMock()), \
             patch('impl.kuaishou.platform.parse_schedule_time', MagicMock(return_value=[None])), \
             patch('impl.kuaishou.platform.get_account_name_by_cookie_file', return_value='昵称'), \
             patch('impl.kuaishou.platform.bind_account_name', MagicMock()):
            asyncio.run(inst.publish_video(title='T', files=['/v.mp4'], account_file=['a.json']))
        assert any(
            c.args[0] == '[发布策略] 发布策略: %s' and c.args[1:] == ('immediate',)
            for c in logger.info.call_args_list
        )

    def test_defaults_no_files_no_accounts(self):
        inst = _make_platform()
        result, upload, _ = _run_publish(inst, title='T')
        assert result is True
        assert upload.await_count == 0
