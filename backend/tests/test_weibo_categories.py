"""weibo/categories.py 纯静态数据查找测试（频道 → 子分类）。"""


from impl.weibo.categories import CHANNELS, find_channel, lookup_sub_channel


def test_data_file_integrity():
    """数据文件自检：25 个频道，且每个频道都有 id 与子分类。"""
    assert len(CHANNELS) == 25
    for ch in CHANNELS:
        assert ch["name"]
        assert ch["channel_id"]
        assert isinstance(ch["sub_channels"], list)
        assert len(ch["sub_channels"]) > 0


def test_find_channel_existing():
    ch = find_channel("VLOG")
    assert ch is not None
    assert ch["name"] == "VLOG"
    assert ch["channel_id"]


def test_find_channel_missing():
    assert find_channel("不存在的频道") is None


def test_lookup_sub_channel_roundtrip():
    # 从真实数据取第一对 频道→子分类 验证字段映射
    first = CHANNELS[0]
    sub = first["sub_channels"][0]
    got = lookup_sub_channel(first["name"], sub["name"])
    assert got == {
        "channel_name": first["name"],
        "channel_id": first["channel_id"],
        "sub_name": sub["name"],
        "sub_channel_id": sub["sub_channel_id"],
    }


def test_lookup_sub_channel_unknown_channel():
    assert lookup_sub_channel("不存在", "任意") is None


def test_lookup_sub_channel_unknown_sub():
    ch = CHANNELS[0]
    assert lookup_sub_channel(ch["name"], "不存在的子分类") is None
