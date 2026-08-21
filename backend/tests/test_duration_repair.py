"""duration_repair 服务测试：并发锁 / 单条 probe / 批量补全 / 提交兜底。

DB 访问全部用 _FakeConn 隔离(不碰真实测试库);文件识别依赖
resolve_material_path / get_video_duration_safe 等全部 mock。
"""
from unittest.mock import patch

import pytest

from services import duration_repair as dr


class _FakeConn:
    """最小 sqlite3.Connection 替身:记录 execute/commit,返回预设 rows/row。"""

    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row
        self.executed = []
        self.row_factory = None
        self.commit_count = 0

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row

    def commit(self):
        self.commit_count += 1

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _clean_inflight():
    """每个测试后清空全局 inflight 集合。"""
    yield
    dr._inflight_ids.clear()


# ── 并发锁 ────────────────────────────────────────────────────────────────────

class TestInflight:
    def test_acquire_release_cycle(self):
        assert dr._acquire('m1') is True
        assert dr._acquire('m1') is False  # 重复 acquire 拒绝
        dr._release('m1')
        assert dr._acquire('m1') is True
        dr._release('m1')

    def test_independent_ids(self):
        assert dr._acquire('a') is True
        assert dr._acquire('b') is True
        dr._release('a')
        dr._release('b')


# ── 单条识别 ──────────────────────────────────────────────────────────────────

class TestProbeOne:
    def test_file_missing(self):
        with patch('storage.resolve_material_path', return_value=None):
            assert dr._probe_one(_FakeConn(), 'm1', 'x.mp4') == 0.0

    def test_local_not_file(self, tmp_path):
        with patch('storage.resolve_material_path', return_value=str(tmp_path)):
            assert dr._probe_one(_FakeConn(), 'm1', 'x.mp4') == 0.0

    def test_success_writes_db(self, tmp_path):
        f = tmp_path / 'v.mp4'
        f.write_bytes(b'x')
        conn = _FakeConn()
        with patch('storage.resolve_material_path', return_value=str(f)), \
             patch('services.duration_repair.get_video_duration_safe', return_value=5.5):
            assert dr._probe_one(conn, 'm1', 'v.mp4') == 5.5
        assert conn.commit_count == 1
        assert conn.executed[0][0].startswith('UPDATE materials SET duration')
        assert conn.executed[0][1] == (5.5, 'm1')

    def test_zero_duration_no_write(self, tmp_path):
        f = tmp_path / 'v.mp4'
        f.write_bytes(b'x')
        conn = _FakeConn()
        with patch('storage.resolve_material_path', return_value=str(f)), \
             patch('services.duration_repair.get_video_duration_safe', return_value=0.0):
            assert dr._probe_one(conn, 'm1', 'v.mp4') == 0.0
        assert conn.commit_count == 0


# ── 提交发布同步兜底 ──────────────────────────────────────────────────────────

class TestEnsureDurationOrProbe:
    def test_already_valid_returns_as_is(self):
        assert dr.ensure_duration_or_probe('x.mp4', 3.0) == 3.0

    def test_empty_path_returns_zero(self):
        assert dr.ensure_duration_or_probe('', 0) == 0.0

    def test_no_matching_row(self):
        conn = _FakeConn(row=None)
        with patch('services.duration_repair.sqlite3.connect', return_value=conn):
            assert dr.ensure_duration_or_probe('missing.mp4', 0) == 0.0
        assert 'WHERE stored_path = ?' in conn.executed[0][0]

    def test_db_duration_used(self):
        conn = _FakeConn(row={'id': 'm1', 'duration': 7.0})
        with patch('services.duration_repair.sqlite3.connect', return_value=conn):
            assert dr.ensure_duration_or_probe('v.mp4', 0) == 7.0
        # 已有时长:不触发 probe
        assert len(conn.executed) == 1

    def test_inflight_returns_zero(self):
        dr._acquire('m1')
        conn = _FakeConn(row={'id': 'm1', 'duration': 0})
        with patch('services.duration_repair.sqlite3.connect', return_value=conn), \
             patch('services.duration_repair._probe_one', return_value=3.3) as probe:
            assert dr.ensure_duration_or_probe('v.mp4', 0) == 0.0
        probe.assert_not_called()

    def test_probe_flow(self, tmp_path):
        f = tmp_path / 'v.mp4'
        f.write_bytes(b'x')
        conn = _FakeConn(row={'id': 'm1', 'duration': 0})
        with patch('services.duration_repair.sqlite3.connect', return_value=conn), \
             patch('storage.resolve_material_path', return_value=str(f)), \
             patch('services.duration_repair.get_video_duration_safe', return_value=4.2):
            assert dr.ensure_duration_or_probe('v.mp4', 0) == 4.2
        assert conn.commit_count == 1

    def test_exception_returns_zero(self):
        conn = _FakeConn(row={'id': 'm1', 'duration': 0})
        with patch('services.duration_repair.sqlite3.connect', return_value=conn), \
             patch('services.duration_repair._probe_one', side_effect=RuntimeError('boom')):
            assert dr.ensure_duration_or_probe('v.mp4', 0) == 0.0

    def test_invalid_current_duration_zero_float(self):
        """0.0 视为无效,走 probe 路径。"""
        conn = _FakeConn(row={'id': 'm1', 'duration': 0})
        with patch('services.duration_repair.sqlite3.connect', return_value=conn), \
             patch('services.duration_repair._probe_one', return_value=1.1):
            assert dr.ensure_duration_or_probe('v.mp4', 0.0) == 1.1


# ── 批量补全 ──────────────────────────────────────────────────────────────────

class TestRepairZeroDurations:
    def test_no_rows(self):
        conn = _FakeConn()
        with patch('time.sleep'), \
             patch('services.duration_repair.sqlite3.connect', return_value=conn):
            dr.repair_zero_durations()  # 不抛异常即通过
        assert len(conn.executed) >= 1  # 执行了扫描查询

    def test_batch_flow_counts(self):
        rows = [{'id': 'ok1', 'stored_path': 'a.mp4', 'original_filename': 'A'},
                {'id': 'bad1', 'stored_path': 'b.mp4', 'original_filename': 'B'},
                {'id': 'skip1', 'stored_path': 'c.mp4', 'original_filename': 'C'}]
        conn = _FakeConn(rows=rows)
        logs = []

        def _fake_probe(conn_, material_id, stored_path):
            if material_id == 'ok1':
                return 5.0
            return 0.0

        dr._acquire('skip1')  # 预占 → 走 skip 分支
        try:
            with patch('time.sleep'), \
                 patch('services.duration_repair.sqlite3.connect', return_value=conn), \
                 patch('services.duration_repair._probe_one', side_effect=_fake_probe), \
                 patch('services.duration_repair.logger.info', side_effect=lambda *a, **k: logs.append((a[0], a[1:]))):
                dr.repair_zero_durations()
        finally:
            dr._release('skip1')
        assert ('[DurationRepair] 补全完成: 共 %d 个，成功 %d，失败 %d，跳过 %d', (3, 1, 1, 1)) in logs

    def test_probe_exception_counts_as_fail(self):
        rows = [{'id': 'ex1', 'stored_path': 'a.mp4', 'original_filename': 'A'}]
        conn = _FakeConn(rows=rows)
        logs = []
        with patch('time.sleep'), \
             patch('services.duration_repair.sqlite3.connect', return_value=conn), \
             patch('services.duration_repair._probe_one', side_effect=RuntimeError('boom')), \
             patch('services.duration_repair.logger.info', side_effect=lambda *a, **k: logs.append((a[0], a[1:]))):
            dr.repair_zero_durations()
        assert ('[DurationRepair] 补全完成: 共 %d 个，成功 %d，失败 %d，跳过 %d', (1, 0, 1, 0)) in logs

    def test_db_missing_skips(self, tmp_path):
        with patch('time.sleep'), \
             patch('conf.BASE_DIR', tmp_path):
            dr.repair_zero_durations()  # 不抛异常


# ── orientation 补全 ──────────────────────────────────────────────────────────

class TestProbeOrientationOne:
    def test_file_missing(self):
        with patch('storage.resolve_material_path', return_value=None):
            assert dr._probe_orientation_one(_FakeConn(), 'm1', 'x.mp4', 'video') == (False, '', 0, 0)

    def test_video_zero_dims(self, tmp_path):
        f = tmp_path / 'v.mp4'
        f.write_bytes(b'x')
        with patch('storage.resolve_material_path', return_value=str(f)), \
             patch('services.duration_repair.get_video_dimensions_safe', return_value=(0, 0)):
            assert dr._probe_orientation_one(_FakeConn(), 'm1', 'v.mp4', 'video') == (False, '', 0, 0)

    def test_video_success(self, tmp_path):
        f = tmp_path / 'v.mp4'
        f.write_bytes(b'x')
        conn = _FakeConn()
        with patch('storage.resolve_material_path', return_value=str(f)), \
             patch('services.duration_repair.get_video_dimensions_safe', return_value=(1920, 1080)):
            ok, orientation, w, h = dr._probe_orientation_one(conn, 'm1', 'v.mp4', 'video')
        assert (ok, orientation, w, h) == (True, 'horizontal', 1920, 1080)
        assert conn.commit_count == 1
        assert conn.executed[0][1] == (1920, 1080, 'horizontal', 'm1')

    def test_image_success(self, tmp_path):
        f = tmp_path / 'i.png'
        f.write_bytes(b'x')
        conn = _FakeConn()
        with patch('storage.resolve_material_path', return_value=str(f)), \
             patch('services.image_service.get_image_dimensions', return_value=(800, 1200)):
            ok, orientation, w, h = dr._probe_orientation_one(conn, 'm1', 'i.png', 'image')
        assert (ok, orientation, w, h) == (True, 'vertical', 800, 1200)


class TestRepairMissingOrientation:
    def test_batch_flow(self):
        rows = [{'id': 'o1', 'stored_path': 'a.mp4', 'original_filename': 'A', 'file_type': 'video'}]
        conn = _FakeConn(rows=rows)
        logs = []
        with patch('time.sleep'), \
             patch('services.duration_repair.sqlite3.connect', return_value=conn), \
             patch('services.duration_repair._probe_orientation_one',
                   return_value=(True, 'horizontal', 1920, 1080)), \
             patch('services.duration_repair.logger.info', side_effect=lambda *a, **k: logs.append((a[0], a[1:]))):
            dr.repair_missing_orientation()
        assert ('[OrientationRepair] 补全完成: 共 %d 个，成功 %d，失败 %d，跳过 %d', (1, 1, 0, 0)) in logs


# ── 后台启动 ──────────────────────────────────────────────────────────────────

class TestStartRepairInBackground:
    def test_starts_two_daemon_threads(self):
        started = []

        class _FakeThread:
            def __init__(self, target=None, daemon=None, name=None):
                self.target = target
                self.name = name

            def start(self):
                started.append(self.name)

        with patch('services.duration_repair.threading.Thread', _FakeThread):
            threads = dr.start_repair_in_background()
        assert len(threads) == 2
        assert started == ['duration-repair', 'orientation-repair']
