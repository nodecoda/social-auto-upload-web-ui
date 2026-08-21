"""ffmpeg_service 单元测试：二进制发现 / 元数据解析 / 帧提取。

纯函数（stderr 解析、orientation）直接测；subprocess 全 mock；
模块级 FFMPEG/FFPROBE/_extraction_tasks 状态每个测试后重置。
"""
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from services import ffmpeg_service as fs


@pytest.fixture(autouse=True)
def _reset_module_state():
    """每个测试后重置惰性二进制缓存与帧任务表，避免跨测试污染。"""
    yield
    fs.FFMPEG = None
    fs.FFPROBE = None
    fs._extraction_tasks.clear()


# ── stderr 解析（纯函数） ─────────────────────────────────────────────────────

class TestParseDurationFromStderr:
    def test_standard(self):
        assert fs._parse_duration_from_stderr("  Duration: 00:01:23.45, start: 0") == 83.45

    def test_with_hours(self):
        assert fs._parse_duration_from_stderr("Duration: 01:02:03.00") == 3723.0

    def test_no_match(self):
        assert fs._parse_duration_from_stderr("Output #0, mp4") == 0.0

    def test_empty(self):
        assert fs._parse_duration_from_stderr("") == 0.0


class TestParseDimensionsFromStderr:
    def test_standard(self):
        assert fs._parse_dimensions_from_stderr(
            "Stream #0:0: Video: h264, 1920x1080, 25 fps"
        ) == (1920, 1080)

    def test_no_match(self):
        assert fs._parse_dimensions_from_stderr("Duration: 00:01:00") == (0, 0)


class TestCalculateOrientation:
    def test_horizontal(self):
        assert fs.calculate_orientation(1920, 1080) == 'horizontal'

    def test_vertical(self):
        assert fs.calculate_orientation(1080, 1920) == 'vertical'

    def test_square(self):
        assert fs.calculate_orientation(1000, 1000) == 'square'

    def test_zero_width(self):
        assert fs.calculate_orientation(0, 1080) == ''

    def test_zero_height(self):
        assert fs.calculate_orientation(1920, 0) == ''


# ── 二进制发现 ─────────────────────────────────────────────────────────────────

class TestValidateBinary:
    def test_ok(self):
        with patch('services.ffmpeg_service.subprocess.run') as m:
            m.return_value.returncode = 0
            assert fs._validate_binary('/usr/bin/ffmpeg') is True

    def test_nonzero(self):
        with patch('services.ffmpeg_service.subprocess.run') as m:
            m.return_value.returncode = 1
            assert fs._validate_binary('/usr/bin/ffmpeg') is False

    def test_oserror(self):
        with patch('services.ffmpeg_service.subprocess.run', side_effect=OSError('no such file')):
            assert fs._validate_binary('/nonexistent') is False

    def test_timeout(self):
        with patch('services.ffmpeg_service.subprocess.run', side_effect=subprocess.TimeoutExpired(['ffmpeg'], 5)):
            assert fs._validate_binary('/usr/bin/ffmpeg') is False


class TestFindBinary:
    def test_path_valid_wins(self):
        with patch('services.ffmpeg_service.shutil.which', return_value='/usr/bin/ffmpeg'), \
             patch('services.ffmpeg_service._validate_binary', return_value=True):
            assert fs._find_binary('ffmpeg') == '/usr/bin/ffmpeg'

    def test_path_invalid_falls_to_bundle(self, tmp_path, monkeypatch):
        """PATH 上有但无效 → 走本地 bundle。"""
        monkeypatch.setattr(sys, '_MEIPASS', None, raising=False)
        with patch('services.ffmpeg_service.shutil.which', return_value='/usr/bin/ffmpeg'), \
             patch('services.ffmpeg_service._validate_binary', return_value=False), pytest.raises(FileNotFoundError):
            fs._find_binary('ffmpeg')

    def test_bundle_valid(self, monkeypatch):
        bin_dir = Path(__file__).resolve().parent.parent / "bin"
        with patch('services.ffmpeg_service.shutil.which', return_value=None), \
             patch('services.ffmpeg_service._validate_binary', return_value=True), \
             patch('services.ffmpeg_service.Path.exists', return_value=True):
            # 候选列表先试 name,再试 name.exe; 都"存在且有效"时返回第一个
            result = fs._find_binary('ffprobe')
            assert result == str(bin_dir / 'ffprobe')

    def test_meipass_bundle(self, monkeypatch):
        monkeypatch.setattr(sys, '_MEIPASS', '/pkg', raising=False)
        with patch('services.ffmpeg_service.shutil.which', return_value=None), \
             patch('services.ffmpeg_service._validate_binary', return_value=True), \
             patch('services.ffmpeg_service.Path.exists', return_value=False), \
             patch('services.ffmpeg_service.os.path.isfile', return_value=True):
            assert fs._find_binary('ffmpeg') == '/pkg/bin/ffmpeg'

    def test_all_fail(self, monkeypatch):
        monkeypatch.setattr(sys, '_MEIPASS', None, raising=False)
        with patch('services.ffmpeg_service.shutil.which', return_value=None), \
             patch('services.ffmpeg_service._validate_binary', return_value=False), \
             patch('services.ffmpeg_service.Path.exists', return_value=False), pytest.raises(FileNotFoundError):
            fs._find_binary('ffmpeg')


class TestEnsureBinaries:
    def test_found(self):
        with patch('services.ffmpeg_service._find_ffmpeg', return_value='/usr/bin/ffmpeg'), \
             patch('services.ffmpeg_service._find_ffprobe', return_value='/usr/bin/ffprobe'):
            fs._ensure_binaries()
        assert fs.FFMPEG == '/usr/bin/ffmpeg'
        assert fs.FFPROBE == '/usr/bin/ffprobe'

    def test_missing_keeps_none(self):
        with patch('services.ffmpeg_service._find_ffmpeg', side_effect=FileNotFoundError('x')), \
             patch('services.ffmpeg_service._find_ffprobe', side_effect=FileNotFoundError('x')):
            fs._ensure_binaries()
        assert fs.FFMPEG is None
        assert fs.FFPROBE is None


# ── 元数据读取 ─────────────────────────────────────────────────────────────────

class TestGetVideoDuration:
    def test_normal(self):
        with patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch.object(fs, 'FFPROBE', '/usr/bin/ffprobe'), \
             patch('services.ffmpeg_service.subprocess.run') as m:
            m.return_value.stdout = '12.5\n'
            assert fs.get_video_duration('/v.mp4') == 12.5

    def test_no_ffprobe(self):
        with patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch.object(fs, 'FFPROBE', None):
            assert fs.get_video_duration('/v.mp4') == 0.0

    def test_called_process_error_propagates(self):
        """非 _safe 版本不吞异常,冒泡给调用方兜底。"""
        with patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch.object(fs, 'FFPROBE', '/usr/bin/ffprobe'), \
             patch('services.ffmpeg_service.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'ffprobe')), \
             pytest.raises(subprocess.CalledProcessError):
            fs.get_video_duration('/v.mp4')


class TestGetVideoDimensions:
    def test_normal(self):
        with patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch.object(fs, 'FFPROBE', '/usr/bin/ffprobe'), \
             patch('services.ffmpeg_service.subprocess.run') as m:
            m.return_value.stdout = '1920,1080\n'
            assert fs.get_video_dimensions('/v.mp4') == (1920, 1080)

    def test_no_ffprobe(self):
        with patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch.object(fs, 'FFPROBE', None):
            assert fs.get_video_dimensions('/v.mp4') == (0, 0)

    def test_bad_output(self):
        with patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch.object(fs, 'FFPROBE', '/usr/bin/ffprobe'), \
             patch('services.ffmpeg_service.subprocess.run') as m:
            m.return_value.stdout = ''
            assert fs.get_video_dimensions('/v.mp4') == (0, 0)


class TestGetVideoDurationSafe:
    def test_ffprobe_wins(self):
        with patch('services.ffmpeg_service.get_video_duration', return_value=8.25):
            assert fs.get_video_duration_safe('/v.mp4') == 8.25

    def test_fallback_ffmpeg_stderr(self):
        with patch('services.ffmpeg_service.get_video_duration', return_value=0.0), \
             patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch('services.ffmpeg_service.subprocess.run') as m:
            m.return_value.stderr = '  Duration: 00:00:03.50, start: 0'
            assert fs.get_video_duration_safe('/v.mp4') == 3.5

    def test_ffprobe_raises_then_fallback(self):
        with patch('services.ffmpeg_service.get_video_duration', side_effect=RuntimeError('boom')), \
             patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch('services.ffmpeg_service.subprocess.run') as m:
            m.return_value.stderr = 'Duration: 00:00:01.00'
            assert fs.get_video_duration_safe('/v.mp4') == 1.0

    def test_no_ffmpeg_returns_zero(self):
        with patch('services.ffmpeg_service.get_video_duration', return_value=0.0), \
             patch.object(fs, 'FFMPEG', None):
            assert fs.get_video_duration_safe('/v.mp4') == 0.0

    def test_timeout_returns_zero(self):
        with patch('services.ffmpeg_service.get_video_duration', return_value=0.0), \
             patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch('services.ffmpeg_service.subprocess.run',
                   side_effect=subprocess.TimeoutExpired(['ffmpeg'], 10)):
            assert fs.get_video_duration_safe('/v.mp4') == 0.0


class TestGetVideoDimensionsSafe:
    def test_ffprobe_wins(self):
        with patch('services.ffmpeg_service.get_video_dimensions', return_value=(1920, 1080)):
            assert fs.get_video_dimensions_safe('/v.mp4') == (1920, 1080)

    def test_fallback_ffmpeg_stderr(self):
        with patch('services.ffmpeg_service.get_video_dimensions', return_value=(0, 0)), \
             patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch('services.ffmpeg_service.subprocess.run') as m:
            m.return_value.stderr = 'Video: h264, 1280x720, 30 fps'
            assert fs.get_video_dimensions_safe('/v.mp4') == (1280, 720)

    def test_no_ffmpeg_returns_zero(self):
        with patch('services.ffmpeg_service.get_video_dimensions', return_value=(0, 0)), \
             patch.object(fs, 'FFMPEG', None):
            assert fs.get_video_dimensions_safe('/v.mp4') == (0, 0)


# ── 帧提取 ─────────────────────────────────────────────────────────────────────

class TestFramesDir:
    def test_structure(self):
        assert fs._frames_dir(Path('/data'), '/data/uploads/a.mp4') == Path('/data/frames/a')


class TestGetFrameImagePath:
    def test_thumbnail_exists(self, tmp_path):
        out = tmp_path / 'frames' / 'a'
        out.mkdir(parents=True)
        (out / 'frame_2.jpg').write_bytes(b'jpg')
        p = fs.get_frame_image_path(tmp_path, '/data/a.mp4', 1, thumbnail=True)
        assert p == str(out / 'frame_2.jpg')

    def test_thumbnail_missing(self, tmp_path):
        assert fs.get_frame_image_path(tmp_path, '/data/a.mp4', 1, thumbnail=True) is None

    def test_hd_cache_hit(self, tmp_path):
        out = tmp_path / 'frames' / 'a'
        out.mkdir(parents=True)
        (out / 'hd_5.jpg').write_bytes(b'jpg')
        p = fs.get_frame_image_path(tmp_path, '/data/a.mp4', 5)
        assert p == str(out / 'hd_5.jpg')

    def test_no_ffmpeg(self, tmp_path):
        with patch.object(fs, 'FFMPEG', None), \
             patch('services.ffmpeg_service._ensure_binaries'):
            assert fs.get_frame_image_path(tmp_path, '/data/a.mp4', 0) is None

    def test_extract_failure(self, tmp_path):
        with patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch('services.ffmpeg_service._ensure_binaries'), \
             patch('services.ffmpeg_service.subprocess.run',
                   side_effect=subprocess.CalledProcessError(1, 'ffmpeg')):
            assert fs.get_frame_image_path(tmp_path, '/data/a.mp4', 0) is None

    def test_extract_success(self, tmp_path):
        with patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch('services.ffmpeg_service._ensure_binaries'), \
             patch('services.ffmpeg_service.subprocess.run'):
            p = fs.get_frame_image_path(tmp_path, '/data/a.mp4', 0)
            assert p is not None and Path(p).name == 'hd_0.jpg'


class TestGetFrameList:
    def _make_frames(self, tmp_path, names):
        out = tmp_path / 'frames' / 'a'
        out.mkdir(parents=True)
        for n in names:
            (out / n).write_bytes(b'jpg')

    def test_with_frames(self, tmp_path):
        self._make_frames(tmp_path, ['frame_1.jpg', 'frame_2.jpg', 'frame_3.jpg'])
        fs._extraction_tasks['/data/a.mp4'] = {'status': 'done', 'total_frames': 3, 'duration': 3.0}
        result = fs.get_frame_list(tmp_path, '/data/a.mp4')
        assert result['duration'] == 3.0
        assert [f['seconds'] for f in result['frames']] == [0, 1, 2]
        assert '/api/frame-image?video_path=/data/a.mp4&seconds=0&thumbnail=1' in result['frames'][0]['url']

    def test_no_frames(self, tmp_path):
        result = fs.get_frame_list(tmp_path, '/data/a.mp4')
        assert result == {'frames': [], 'duration': 0.0}


class TestExtractFramesSync:
    def test_success(self, tmp_path):
        out = tmp_path / 'frames' / 'a'
        out.mkdir(parents=True)
        (out / 'frame_1.jpg').write_bytes(b'jpg')
        (out / 'frame_2.jpg').write_bytes(b'jpg')
        with patch.object(fs, 'FFMPEG', '/usr/bin/ffmpeg'), \
             patch('services.ffmpeg_service._ensure_binaries'), \
             patch('services.ffmpeg_service.get_video_duration', return_value=2.0), \
             patch('services.ffmpeg_service.subprocess.run'):
            fs._extract_frames_sync(tmp_path, '/data/a.mp4')
        task = fs._extraction_tasks['/data/a.mp4']
        assert task['status'] == 'done'
        assert task['total_frames'] == 2
        assert task['duration'] == 2.0

    def test_no_ffmpeg_error(self, tmp_path):
        with patch.object(fs, 'FFMPEG', None), \
             patch('services.ffmpeg_service._ensure_binaries'):
            fs._extract_frames_sync(tmp_path, '/data/a.mp4')
        assert fs._extraction_tasks['/data/a.mp4']['status'] == 'error'


class TestStartFrameExtraction:
    def test_idempotent_when_processing(self):
        fs._extraction_tasks['/v.mp4'] = {'status': 'processing', 'total_frames': 0, 'duration': 0.0}
        with patch('services.ffmpeg_service._extract_frames_sync') as m:
            assert fs.start_frame_extraction('/data', '/v.mp4') == '/v.mp4'
            m.assert_not_called()

    def test_idempotent_when_done(self):
        fs._extraction_tasks['/v.mp4'] = {'status': 'done', 'total_frames': 2, 'duration': 2.0}
        with patch('services.ffmpeg_service._extract_frames_sync') as m:
            assert fs.start_frame_extraction('/data', '/v.mp4') == '/v.mp4'
            m.assert_not_called()

    def test_starts_new_task(self):
        with patch('services.ffmpeg_service._extract_frames_sync') as m:
            assert fs.start_frame_extraction('/data', '/v.mp4') == '/v.mp4'
            m.assert_called_once()
