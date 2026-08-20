"""平台注册表测试：register / get_platform / get_platform_by_key / is_supported。

_populate_registry 在 import 时执行（19 个平台晚加载，失败会被吞掉并告警），
本测试验证注册表契约 + 关键平台可达性。
"""

import impl.registry as registry
from impl.base_platform import BasePlatform


class StubPlatform(BasePlatform):
    platform_id = 999
    platform_key = "stub"
    platform_name = "Stub"

    # BasePlatform 的抽象方法：测试桩置为无操作
    async def login(self, id, status_queue, account_id=None): ...
    async def check_cookie(self, cookie_file): ...
    async def open_creator_center(self, cookie_file): ...
    async def sync_profile(self, cookie_file): ...
    def publish_video(self, **kwargs): ...


def test_register_and_get_platform():
    registry.register(999, StubPlatform)
    inst = registry.get_platform(999)
    assert isinstance(inst, StubPlatform)
    # 每次 get 返回新实例
    assert registry.get_platform(999) is not inst


def test_get_platform_unknown_id_returns_none():
    assert registry.get_platform(123456) is None


def test_get_platform_by_key():
    registry.register(999, StubPlatform)
    inst = registry.get_platform_by_key("stub")
    assert isinstance(inst, StubPlatform)


def test_get_platform_by_key_unknown_returns_none():
    assert registry.get_platform_by_key("no_such_platform") is None


def test_is_supported():
    registry.register(999, StubPlatform)
    assert registry.is_supported(999) is True
    assert registry.is_supported(777777) is False


def test_populated_registry_has_all_platforms():
    """启动时注册了 19 个平台；jd 走 jingmai 委托不单独注册。"""
    for pid in range(1, 20):           # 1..19 全部注册
        assert registry.is_supported(pid), f'platform {pid} missing'
    assert registry.is_supported(20) is False  # jd 未单独注册（委托 jingmai）


def test_known_platform_keys_lookup():
    inst = registry.get_platform_by_key("douyin")
    assert inst is not None and inst.platform_name
    assert registry.get_platform_by_key("xiaohongshu") is not None
    assert registry.get_platform_by_key("bilibili") is not None
