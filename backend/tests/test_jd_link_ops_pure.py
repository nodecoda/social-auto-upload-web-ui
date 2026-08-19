"""jd/_jd_link_ops.py 纯函数测试（trace 签名 / 结果数据类）。"""
from impl.jd._jd_link_ops import LocateResult, trace_signature


def test_trace_signature_defaults():
    assert trace_signature({}) == ("", 1)
    assert trace_signature({"keyword": "小米"}) == ("小米", 1)


def test_trace_signature_explicit():
    assert trace_signature({"keyword": "手机", "page": 3}) == ("手机", 3)


def test_trace_signature_page_none_is_preserved():
    # page 键存在但为 None 时原样返回（缺键才用默认 1）
    assert trace_signature({"keyword": "x", "page": None}) == ("x", None)


def test_locate_result_defaults():
    r = LocateResult()
    assert r.checked == []
    assert r.already == []
    assert r.disabled == []
    assert r.missing == []


def test_locate_result_accumulates():
    r = LocateResult()
    r.checked.append("a")
    r.missing.append("b")
    assert r.checked == ["a"]
    assert r.missing == ["b"]
