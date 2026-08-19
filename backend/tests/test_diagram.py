"""Topology diagram export — engineering drawing sheet in pdf/vsdx/docx/png."""

from conftest import make_client

client = make_client("admin")

NODES = [
    {"ip": "10.41.36.1", "hostname": "USNRPCMIAFL01H", "model": "Cisco 1921",
     "device_type": "router"},
    {"ip": "10.41.36.2", "hostname": "MIFLST1SWC4", "model": "C9300X-24CY",
     "device_type": "switch"},
    {"ip": "10.41.36.3", "hostname": "MIFLST1SWC5", "model": "C9300X-24CY",
     "device_type": "switch"},
    {"ip": "10.41.36.4", "hostname": "AMTRMIAFL02S", "model": "C9300L-24P-4X",
     "device_type": "switch"},
]
LINKS = [
    {"source": "10.41.36.1", "target": "10.41.36.2",
     "source_interface": "GigabitEthernet0/0", "target_interface": "TwentyFiveGigE1/1/1"},
    {"source": "10.41.36.1", "target": "10.41.36.3",
     "source_interface": "GigabitEthernet0/1", "target_interface": "TwentyFiveGigE1/1/1"},
    {"source": "10.41.36.2", "target": "10.41.36.4",
     "source_interface": "TwentyFiveGigE1/0/3", "target_interface": "TenGigabitEthernet1/1/1"},
    {"source": "10.41.36.2", "target": "10.41.36.4",
     "source_interface": "TwentyFiveGigE1/0/4", "target_interface": "TenGigabitEthernet1/1/2"},
]


def _post(fmt: str, **extra):
    payload = {"format": fmt, "nodes": NODES, "links": LINKS,
               "title": "AMTRAK MIAMI STATION", **extra}
    return client.post("/api/topology/diagram", json=payload)


def test_diagram_pdf():
    resp = _post("pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert "attachment" in resp.headers.get("content-disposition", "")


def test_diagram_vsdx_is_valid_zip_with_visio_parts():
    resp = _post("vsdx")
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"

    import io
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(z.namelist())
    assert "[Content_Types].xml" in names
    assert "visio/document.xml" in names
    assert "visio/pages/page1.xml" in names
    assert "visio/media/image1.png" in names  # Amtrak logo embedded as PNG
    assert "visio/media/image2.png" in names  # device icon embedded as PNG
    page = z.read("visio/pages/page1.xml").decode()
    assert "MIFLST1SWC4" in page
    assert "25G1/1/1" in page  # abbreviated port label
    assert "C9300X-24CY" in page  # device model shown under hostname


def test_diagram_vsdx_xml_wellformed_font_and_rels():
    """The .vsdx must be structurally valid: well-formed XML everywhere, the
    text font pinned, and every relationship target resolvable."""
    resp = _post("vsdx")
    assert resp.status_code == 200

    import io
    import zipfile
    import xml.etree.ElementTree as ET

    z = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(z.namelist())

    # 1. Every XML/.rels part must parse as well-formed XML.
    for name in names:
        if name.endswith(".xml") or name.endswith(".rels"):
            ET.fromstring(z.read(name))

    # 2. Text must pin an explicit font so it renders consistently in Visio.
    page = z.read("visio/pages/page1.xml").decode()
    assert 'N="Font" V="Arial"' in page

    # 3. Every relationship target must resolve to a part that exists.
    NS_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    for rels_name in [n for n in names if n.endswith(".rels")]:
        if rels_name == "_rels/.rels":
            base_dir = ""
        else:
            part_name = rels_name.replace("/_rels/", "/")[: -len(".rels")]
            base_dir = part_name.rsplit("/", 1)[0] if "/" in part_name else ""
        root = ET.fromstring(z.read(rels_name))
        for rel in root:
            target = rel.get("Target")
            if not target or rel.get("TargetMode") == "External":
                continue
            segments = (base_dir.split("/") if base_dir else []) + target.split("/")
            resolved = []
            for seg in segments:
                if seg in ("", "."):
                    continue
                if seg == "..":
                    if resolved:
                        resolved.pop()
                else:
                    resolved.append(seg)
            assert "/".join(resolved) in names, f"broken rel {rels_name} -> {target}"


def test_diagram_docx():
    resp = _post("docx")
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"
    assert "wordprocessingml" in resp.headers["content-type"]


def test_diagram_png():
    resp = _post("png")
    assert resp.status_code == 200
    assert resp.content.startswith(b"\x89PNG")


def test_diagram_custom_legend_and_title_block():
    resp = _post("pdf", drawn_by="Michael Speed", document_name="HIALEIGH YARD",
                 legend=[{"key": "smf", "label": "SMF", "color": "#E6D200"}])
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


def test_diagram_rejects_bad_format():
    resp = _post("exe")
    assert resp.status_code == 400


def test_diagram_rejects_empty_graph():
    resp = client.post("/api/topology/diagram", json={"format": "pdf", "nodes": [], "links": []})
    assert resp.status_code == 400


def test_diagram_rejects_oversized_input(monkeypatch):
    import main

    monkeypatch.setattr(main, "MAX_DIAGRAM_NODES", 3)
    many = [{"ip": f"10.0.0.{i}", "hostname": f"h{i}", "model": "C9300", "device_type": "switch"} for i in range(4)]
    resp = client.post("/api/topology/diagram", json={"format": "pdf", "nodes": many, "links": []})
    assert resp.status_code == 400


def test_diagram_executive_package_zip():
    resp = client.post("/api/topology/package", json={
        "nodes": NODES, "links": LINKS, "title": "AMTRAK MIAMI STATION",
    })
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"
    assert resp.headers["content-type"] == "application/zip"

    import io
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    names = z.namelist()
    assert any(n.endswith(".pdf") for n in names)
    assert any(n.endswith(".docx") for n in names)
    assert any(n.endswith("-port-table.csv") for n in names)
    csv_data = z.read([n for n in names if n.endswith(".csv")][0]).decode()
    assert "device_hostname" in csv_data
    assert "MIFLST1SWC4" in csv_data


def test_diagram_render_cache_serves_repeat_requests(monkeypatch):
    """Identical requests must be served from the render cache without
    re-rendering."""
    import diagram_export

    calls = {"n": 0}
    real_export = diagram_export.export_diagram

    def counting_export(*args, **kwargs):
        calls["n"] += 1
        return real_export(*args, **kwargs)

    monkeypatch.setattr(diagram_export, "export_diagram", counting_export)

    payload = {"format": "pdf", "nodes": NODES, "links": LINKS, "title": "CACHE TEST"}
    r1 = client.post("/api/topology/diagram", json=payload)
    r2 = client.post("/api/topology/diagram", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.content == r2.content
    assert calls["n"] == 1  # second request served from cache


def test_diagram_legibility_no_obstructions():
    """A dense fat-tree site must render with no cable-through-icon,
    cable-through-label, or label-label overlaps (visual regression guard)."""
    from diagram_export import build_scene, analyze_scene

    nodes = [{"ip": "10.0.0.1", "hostname": "EDGE-ROUTER", "model": "ISR4331",
              "device_type": "router"}]
    for i in range(2):
        nodes.append({"ip": f"10.0.0.{10 + i}", "hostname": f"CORE-{i + 1}",
                      "model": "C9500-24Y4C", "device_type": "switch"})
    for i in range(8):
        nodes.append({"ip": f"10.0.1.{11 + i}", "hostname": f"DIST-{i + 1}",
                      "model": "C9300X-24Y", "device_type": "switch"})
    for i in range(6):
        nodes.append({"ip": f"10.0.2.{21 + i}", "hostname": f"ACCESS-{i + 1}",
                      "model": "WS-C3560CX-8PC-S", "device_type": "switch"})

    links = [
        {"source": "10.0.0.1", "target": "10.0.0.10", "source_interface": "Gi0/0/0", "target_interface": "Te1/0/1"},
        {"source": "10.0.0.1", "target": "10.0.0.11", "source_interface": "Gi0/0/1", "target_interface": "Te1/0/1"},
        {"source": "10.0.0.10", "target": "10.0.0.11", "source_interface": "Te1/0/2", "target_interface": "Te1/0/2"},
    ]
    for i in range(8):
        dist_ip = f"10.0.1.{11 + i}"
        links.append({"source": "10.0.0.10", "target": dist_ip,
                      "source_interface": "Te1/0/3", "target_interface": "Te1/0/1"})
        links.append({"source": "10.0.0.11", "target": dist_ip,
                      "source_interface": "Te1/0/3", "target_interface": "Te1/0/2"})
    for i in range(6):
        acc_ip = f"10.0.2.{21 + i}"
        dist_ip = f"10.0.1.{11 + (i % 8)}"
        links.append({"source": dist_ip, "target": acc_ip,
                      "source_interface": "Te1/1/1", "target_interface": "Te1/1/1"})

    scene = build_scene(nodes, links, {"title": "TEST", "exclude_endpoints": False,
                                       "topology": "tree", "link_detail": "full",
                                       "title_block": False})
    m = analyze_scene(scene)
    assert m["cable_switch_crossings"] == 0, m
    assert m["cable_label_crossings"] == 0, m
    assert m["label_label_overlaps"] == 0, m
