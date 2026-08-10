"""Path tracer tests (Sprint 10)."""

from path_tracer import build_path


def _link(src, tgt, iface_s="", iface_t="", proto="lldp", host_s="", host_t=""):
    return {
        "source": src, "target": tgt,
        "source_interface": iface_s, "target_interface": iface_t,
        "protocol": proto,
        "source_hostname": host_s, "target_hostname": host_t,
    }


def test_direct_path():
    links = [
        _link("10.0.0.1", "10.0.0.2", "Gi1/1", "Gi1/1"),
    ]
    result = build_path(links, "10.0.0.1", "10.0.0.2")
    assert result["hops"] == 1
    assert result["path"][0]["source"] == "10.0.0.1"


def test_multi_hop_path():
    links = [
        _link("10.0.0.1", "10.0.0.2"),
        _link("10.0.0.2", "10.0.0.3"),
        _link("10.0.0.1", "10.0.0.4"),  # longer path
    ]
    result = build_path(links, "10.0.0.1", "10.0.0.3")
    assert result["hops"] == 2  # 1→2→3


def test_no_path():
    links = [
        _link("10.0.0.1", "10.0.0.2"),
        _link("10.0.0.3", "10.0.0.4"),
    ]
    result = build_path(links, "10.0.0.1", "10.0.0.4")
    assert result["hops"] == 0
    assert "no route" in (result.get("error") or "")


def test_source_not_found():
    links = [_link("10.0.0.1", "10.0.0.2")]
    result = build_path(links, "10.0.0.99", "10.0.0.1")
    assert "source" in (result.get("error") or "")


def test_same_source_target():
    result = build_path([], "10.0.0.1", "10.0.0.1")
    assert "same" in (result.get("error") or "")
