"""Path tracer tests (Sprint 10)."""

from path_tracer import build_path, articulation_points


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


def test_articulation_points_line_topology():
    # A---B---C---D : B and C are SPOFs, A and D are leaves.
    links = [_link("A", "B"), _link("B", "C"), _link("C", "D")]
    aps = articulation_points(["A", "B", "C", "D"], links)
    assert aps == {"B", "C"}


def test_articulation_points_ring_has_none():
    # A---B---C---D---A : a ring has no articulation point.
    links = [_link("A", "B"), _link("B", "C"), _link("C", "D"), _link("D", "A")]
    aps = articulation_points(["A", "B", "C", "D"], links)
    assert aps == set()


def test_articulation_points_star_center_is_spof():
    # hub-and-spoke: the center is a SPOF, the leaves are not.
    links = [_link("hub", "s1"), _link("hub", "s2"), _link("hub", "s3")]
    aps = articulation_points(["hub", "s1", "s2", "s3"], links)
    assert aps == {"hub"}


def test_articulation_points_ignores_unknown_links():
    # Links to nodes outside the provided set are ignored.
    links = [_link("A", "B"), _link("B", "C"), _link("B", "X")]  # X not in nodes
    aps = articulation_points(["A", "B", "C"], links)
    assert aps == {"B"}
