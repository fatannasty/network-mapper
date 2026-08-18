"""Engineering-style topology diagram export.

Builds a drawing-sheet scene from topology nodes/links in the style of the
Amtrak station reference drawings (white sheet, black frame, Amtrak logo
top-left, centered site title, hierarchical layers, angled link elbows with
port labels, medium color-coding, and a legend/title block at the bottom),
then renders it to PDF, PNG, Visio (.vsdx) or Word (.docx).

Links are angled (orthogonal-elbow) lines riding stacked horizontal channels;
where two links cross, a small line-break (jump) is drawn so the overlap reads
cleanly. Endpoints are glued to device connection points so they follow the
devices when dragged.

Scene units are points (1/72"), origin top-left, y grows downward.
"""

from __future__ import annotations

import io
import math
import os
import re
import zipfile
from xml.sax.saxutils import escape as _xml_escape

# --------------------------------------------------------------------------
# Style constants (match the reference drawing)
# --------------------------------------------------------------------------

MARGIN = 36
HEADER_H = 140            # logo + title band
LAYER_GAP = 230           # vertical distance between device rows
GLYPH_W, GLYPH_H = 120, 26
CLOUD_W, CLOUD_H = 150, 56
UNKNOWN_W, UNKNOWN_H = 100, 22
SLOT_W = 260              # horizontal slot per device (spaced for readability)
MAX_PER_ROW = 8           # rows wrap downward past this (uniform vertical flow)
LEGEND_H = 130            # legend / title block height
TOP_PAD = 20              # extra headroom above the first row (keeps labels clear)

# Hierarchy: Internet -> VeloCloud -> Router/Firewall -> Core -> Distribution
# -> Access -> End Users & Devices, drawn top to bottom. Each band is a row of
# devices; no zone boxes are drawn, keeping the sheet clean and readable.
LAYER_KEYS = ("internet", "velocloud", "router", "core", "distribution",
              "access", "endpoint")
LAYER_NAMES = {
    "internet": "INTERNET",
    "velocloud": "VELOCLOUD / SD-WAN",
    "router": "ROUTER / FIREWALL",
    "core": "CORE",
    "distribution": "DISTRIBUTION",
    "access": "ACCESS",
    "endpoint": "END USERS & DEVICES",
}
ZONE_H = 150              # per-row height of a layer enclosure
ZONE_ROW_CY = 70          # device-center offset from the zone top (per row)

# Link-routing: connectors are simple angled lines (orthogonal elbows) modeled
# on the reference drawing. Links use a single horizontal channel level
# between device rows, and use Visio's native line-jump settings for clarity.

# Role-based link color coding (WAN / core backbone / LAN / security /
# management); the matching legend entries use these exact colors.
LINK_COLORS = {
    "wan": "#1E88E5",
    "core": "#2E7D32",
    "lan": "#7CB342",
    "fiber": "#E6C200",
    "management": "#8E24AA",
}

C_FRAME = "#000000"
C_TEXT = "#000000"
C_CORE = "#C00000"        # role label red
C_PORT = "#444444"        # port labels
C_LINK = "#333333"        # default link
C_GLYPH = "#2F3542"       # switch faceplate
C_GLYPH_EDGE = "#111318"
C_GLYPH_TICK = "#9AA3B2"
C_UNKNOWN = "#F2F2F2"
C_SUBNET_FILL = "#F5F8FC"
C_SUBNET_STROKE = "#B7C7DD"
C_SUBNET_TEXT = "#4A6A8A"

AMTRAK_BLUE = "#003A70"
PROPRIETARY = "AMTRAK - Proprietary\nUse Pursuant to Company\nInstructions"

DEFAULT_LEGEND = [
    {"key": "wan", "label": "WAN / Internet", "color": LINK_COLORS["wan"]},
    {"key": "core", "label": "Core Backbone", "color": LINK_COLORS["core"]},
    {"key": "lan", "label": "LAN", "color": LINK_COLORS["lan"]},
    {"key": "fiber", "label": "Fiber", "color": LINK_COLORS["fiber"]},
    {"key": "management", "label": "Management", "color": LINK_COLORS["management"]},
]

# Visio layer for connectors: a single "Connector" layer, like the reference
# drawing, so all links can be shown/hidden together.
LINK_LAYERS = {
    "wan": "Connector",
    "management": "Connector",
    "core": "Connector",
    "lan": "Connector",
    "fiber": "Connector",
}

ASSET_LOGO = os.path.join(os.path.dirname(__file__), "assets", "amtrak-logo.png")
ICON_DIR = os.path.join(os.path.dirname(__file__), "assets", "icons")
EMF_DIR = os.path.join(os.path.dirname(__file__), "assets", "emf")

# Abbreviations match the app's frontend `shortenInterface` helper so port
# labels stay short (e.g. "TwentyFiveGigE1/1/1" -> "25G1/1/1").
_IFACE_SHORT = (
    ("AppGigabitEthernet", "AppGi"),
    ("TwentyFiveGigE", "25G"),
    ("FortyGigabitEthernet", "Fo"),
    ("HundredGigE", "100G"),
    ("TenGigabitEthernet", "Te"),
    ("GigabitEthernet", "Gi"),
    ("FastEthernet", "Fa"),
    ("Port-channel", "Po"),
    ("Loopback", "Lo"),
    ("Tunnel", "Tu"),
    ("Serial", "Se"),
    ("Bluetooth", "BT"),
    ("Management", "Mgmt"),
    ("Vlan", "Vl"),
    ("Ethernet", "Eth"),
)


def _shorten_interface(name: str) -> str:
    if not name:
        return ""
    for long, short in _IFACE_SHORT:
        name = name.replace(long, short)
    return name


def _port_label(interfaces) -> str:
    """Concise port label for a link's interfaces: '25G1/0/23' for one,
    '25G1/0/23-24' for a consecutive run, '(4x)' for non-consecutive ports."""
    ifs = [i for i in interfaces if i]
    if not ifs:
        return ""
    if len(ifs) == 1:
        return _shorten_interface(ifs[0])
    short = [_shorten_interface(i) for i in ifs]
    mm = [re.match(r"^(.*?)(\d+)$", s) for s in short]
    if all(mm) and len({m.group(1) for m in mm}) == 1:
        nums = sorted(int(m.group(2)) for m in mm)
        if nums == list(range(nums[0], nums[0] + len(nums))):
            return f"{mm[0].group(1)}{nums[0]}-{nums[-1]}"
    return f"({len(ifs)}x)"


def _icon_kind(device_type: str, model: str, hostname: str) -> str:
    dt, m, h = device_type.lower(), model.lower(), hostname.lower()
    if "access point" in dt or "accesspoint" in dt or m.startswith("mr") or m.startswith("air-"):
        return "ap"
    if "router" in dt or m.startswith(("isr", "asr")):
        return "router"
    return "switch"


def _icon_path(device_type: str, model: str, hostname: str) -> str | None:
    """Find the icon image for a device — conventional, readable shapes.

    Uses a consistent Cisco-style icon per device category (model names stay in
    the text label under each icon) so large diagrams read cleanly instead of
    showing flat front-panel "brick" images.
    """
    dt, m, h = device_type.lower(), model.lower(), hostname.lower()
    if not m and not dt:
        return None
    m_slug = re.sub(r"[^a-z0-9]+", "-", m).strip("-")

    # Access points: prefer the accurate Meraki MR icon
    if m.startswith("mr"):
        p = os.path.join(ICON_DIR, f"meraki-{m_slug}.png")
        if os.path.exists(p):
            return p
        p = os.path.join(ICON_DIR, "ap.png")
        return p if os.path.exists(p) else None
    if "access point" in dt or "accesspoint" in dt:
        p = os.path.join(ICON_DIR, "ap.png")
        return p if os.path.exists(p) else None

    # SD-WAN / VeloCloud edges
    if "velocloud" in dt or m.startswith("velocloud"):
        p = os.path.join(ICON_DIR, "velocloud.png")
        return p if os.path.exists(p) else None

    # Cloud / Internet
    if "cloud" in dt or "internet" in dt:
        p = os.path.join(ICON_DIR, "cloud-cisco.png")
        return p if os.path.exists(p) else None

    # Firewalls
    if "firewall" in dt or m.startswith("mx"):
        p = os.path.join(ICON_DIR, "firewall-cisco.png")
        return p if os.path.exists(p) else None

    # Routers (ISR / ASR / generic)
    if "router" in dt or m.startswith(("isr", "asr", "1921", "2921", "3925")):
        p = os.path.join(ICON_DIR, "router.png")
        return p if os.path.exists(p) else None

    # Switches — prefer the actual model icon (shows the real hardware), with a
    # conventional boxy icon only as a fallback for unknown models.
    if m_slug:
        p = os.path.join(ICON_DIR, f"{m_slug}.png")
        if os.path.exists(p):
            return p
    if m.startswith("c9500"):
        p = os.path.join(ICON_DIR, "c9500-24y4c.png")
        if os.path.exists(p):
            return p
    if m.startswith("c9300"):
        p = os.path.join(ICON_DIR, "c9300l-48p.png")
        if os.path.exists(p):
            return p
    if m.startswith("c9200"):
        p = os.path.join(ICON_DIR, "c9200l-48p.png")
        if os.path.exists(p):
            return p
    p = os.path.join(ICON_DIR, "layer3-switch.png")
    return p if os.path.exists(p) else None


def _icon_png_bytes(path: str, size: tuple[int, int]) -> bytes | None:
    try:
        from PIL import Image
        with Image.open(path) as img:
            img = img.resize(size, Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        return None


def _png_to_emf(data: bytes) -> bytes | None:
    """Convert PNG bytes to EMF bytes using Pillow + pyemf or similar?
    Actually, we just return the PNG if we can't convert, but for VSDX we need EMF.
    In this environment, we'll assume pre-rendered EMFs exist in assets/emf."""
    return None


def _read_emf_for_image(path: str) -> tuple[bytes | None, int, int]:
    """Find the matching EMF for an icon path."""
    name = os.path.basename(path).replace(".png", ".emf")
    emf_path = os.path.join(EMF_DIR, name)
    if os.path.exists(emf_path):
        data = open(emf_path, "rb").read()
        return data, 1000, 1000 # Dummy extent
    return None, 0, 0


def _icon_size(path: str, max_w: float, max_h: float) -> tuple[float, float]:
    try:
        from PIL import Image
        with Image.open(path) as img:
            w, h = img.size
            # Clamp the aspect ratio so wide flat front-panel icons don't
            # render as paper-thin slivers (unreadable, breaks cable attach).
            aspect = max(0.6, min(2.2, w / h))
            if w / h > aspect:
                w = h * aspect
            elif h / w > 1.0 / aspect:
                h = w / aspect
            f = min(max_w / w, max_h / h)
            return w * f, h * f
    except Exception:
        return max_w, max_h


def _icon_visible_insets(path: str) -> tuple[float, float, float, float]:
    return (0.0, 0.0, 0.0, 0.0)


def _medium_key(ia: str, ib: str) -> str:
    s = (ia + " " + ib).lower()
    if "fiber" in s or "sfp" in s: return "fiber"
    return "copper"


def _layer_of(node: dict) -> str:
    dt = (node.get("device_type") or "").lower()
    m = (node.get("model") or "").lower()
    if "cloud" in dt or "internet" in dt: return "internet"
    if "velocloud" in dt or "velo" in m: return "velocloud"
    if "firewall" in dt or "mx" in m: return "router"
    if "router" in dt or "isr" in m or "asr" in m: return "router"
    if "core" in m or "9500" in m or "9400" in m: return "core"
    if "9300" in m or "9200" in m: return "distribution"
    if "switch" in dt: return "access"
    return "endpoint"


def _subnet24(ip: str) -> str | None:
    """Return the /24 subnet prefix for an IPv4 address, or None."""
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return None
        for p in parts:
            int(p)
        return ".".join(parts[:3]) + ".0/24"
    except (ValueError, AttributeError):
        return None


def _link_color_key(a, b, layer_of, ia, ib):
    la, lb = layer_of.get(a), layer_of.get(b)
    if not la or not lb: return "lan"
    if "internet" in (la, lb): return "wan"
    if "velocloud" in (la, lb): return "wan"
    if "core" in (la, lb): return "core"
    if _medium_key(ia, ib) == "fiber": return "fiber"
    return "lan"


class Scene:
    def __init__(self, w, h):
        self.width, self.height = w, h
        self.prims = []
        self.devices = []
        self.vlinks = []

    def rect(self, x, y, w, h, fill=None, stroke=None, sw=1.0, tag=None):
        self.prims.append({"k": "rect", "x": x, "y": y, "w": w, "h": h, "fill": fill, "stroke": stroke, "sw": sw, "tag": tag})

    def line(self, pts, color="#000000", width=1.0, tag=None):
        self.prims.append({"k": "line", "pts": pts, "color": color, "width": width, "tag": tag})

    def text(self, x, y, v, size=10, bold=False, italic=False, color="#000000", align="center", tag=None, angle=0.0):
        self.prims.append({"k": "text", "x": x, "y": y, "v": v, "size": size, "bold": bold, "italic": italic, "color": color, "align": align, "tag": tag, "angle": angle})

    def image(self, x, y, w, h, path, tag=None):
        self.prims.append({"k": "image", "x": x, "y": y, "w": w, "h": h, "path": path, "tag": tag})

    def ellipse(self, cx, cy, rx, ry, fill=None, stroke=None, sw=1.0, tag=None):
        self.prims.append({"k": "ellipse", "cx": cx, "cy": cy, "rx": rx, "ry": ry, "fill": fill, "stroke": stroke, "sw": sw, "tag": tag})


def _build_ap_scene(aps: list[dict], opts: dict) -> Scene:
    """Build a simple dedicated sheet listing the access points."""
    title = (opts.get("title") or "AMTRAK NETWORK DIAGRAM").upper()
    n = len(aps)
    PER_ROW = 8
    SLOT = 170.0
    rows = -(-n // PER_ROW)
    content_top = MARGIN + HEADER_H
    width = max(1150, MARGIN * 2 + PER_ROW * SLOT)
    legend_y = content_top + rows * 96 + 40
    height = legend_y + LEGEND_H + MARGIN
    scene = Scene(width, height)
    scene.rect(MARGIN / 2, MARGIN / 2, width - MARGIN, height - MARGIN, stroke=C_FRAME, sw=1.5)
    if os.path.exists(ASSET_LOGO): scene.image(MARGIN + 6, MARGIN / 2 + 8, 170.0, 170.0 * 394 / 700, ASSET_LOGO)
    scene.text(width / 2, MARGIN + 26, f"{title} - ACCESS POINTS", size=24)
    for i, node in enumerate(aps):
        ip = node.get("ip") or ""
        hn = (node.get("hostname") or "").split(".")[0] or ip
        dt = (node.get("device_type") or "").lower()
        icon_path = _icon_path(dt, node.get("model") or "", hn)
        kind = _icon_kind(dt, node.get("model") or "", hn)
        w, h = (_icon_size(icon_path, 56, 56) if icon_path else (GLYPH_W, GLYPH_H))
        row, col = divmod(i, PER_ROW)
        x = MARGIN + col * SLOT + SLOT / 2
        y = content_top + row * 96 + 60
        if icon_path:
            scene.image(x - w / 2, y - h / 2, w, h, icon_path, tag=("dev", ip))
        scene.text(x, y + h / 2 + 7, hn, size=8, bold=True, tag=("dev", ip))
        if ip:
            scene.text(x, y + h / 2 + 17, ip, size=7, tag=("dev", ip))
        scene.devices.append({"ip": ip, "cx": x, "cy": y, "kind": kind,
                              "labels": [(hn, 8, True, C_TEXT), (ip, 7, False, C_TEXT)],
                              "icon_path": icon_path, "icon_w": w, "icon_h": h})
    if opts.get("title_block", True):
        bx = MARGIN + 24; bw = (width - MARGIN / 2) - bx; by = legend_y
        scene.rect(bx, by, bw, LEGEND_H, stroke=C_FRAME, sw=1.2); c1, c2 = bx + 210, bx + 510
        scene.line([(c1, by), (c1, by + LEGEND_H)], color=C_FRAME, width=1.0); scene.line([(c2, by), (c2, by + LEGEND_H)], color=C_FRAME, width=1.0)
        scene.text((bx + c1) / 2, by + 8, "LEGEND", size=9, bold=True, align="center")
        ey = by + 28
        for e in (opts.get("legend") or DEFAULT_LEGEND):
            scene.rect(bx + 10, ey + 3, 48, 5, fill=e.get("color") or C_LINK, stroke=None, sw=0)
            scene.text(66 + bx, ey, e.get("label") or "", size=8.5, align="left"); ey += 16
        rows_data = [[("Drawn By: ", opts.get("drawn_by") or ""), ("Drawn Date: ", opts.get("drawn_date") or "08142026")], [("Drawing Title: ", opts.get("drawing_title") or title)], [("Document Name: ", opts.get("document_name") or "")], [("Revision: ", opts.get("revision") or ""), ("Rev. Date: ", "14 Aug 26"), ("Rev. Time: ", "07:45 PM")]]
        rh = LEGEND_H / 4
        for i, row in enumerate(rows_data):
            ry = by + i * rh
            if i: scene.line([(c2, ry), (bx + bw, ry)], color=C_FRAME, width=1.0)
            cw = (bx + bw - c2) / len(row)
            for j, (label, val) in enumerate(row):
                if j: scene.line([(c2 + j * cw, ry), (c2 + j * cw, ry + rh)], color=C_FRAME, width=1.0)
                scene.text(c2 + j * cw + cw / 2, ry + rh / 2 - 4, label + val, size=9, align="center")
    return scene


def _layout_tree(layers, order, valid, _max_dev_w):
    """Hierarchical top-to-bottom tiers, barycenter-ordered, wrapped into rows."""
    MAX_PER_ROW = 6
    SLOT_W = _max_dev_w + 120.0
    neigh = {}
    for l in valid:
        a, b = l["source"], l["target"]
        neigh.setdefault(a, []).append(b)
        neigh.setdefault(b, []).append(a)
    content_top = MARGIN + HEADER_H
    GAP = 95.0
    ROW_H = ZONE_H + GAP
    y_0 = content_top + GAP + ZONE_ROW_CY + TOP_PAD
    width = max(1150, MARGIN * 2 + MAX_PER_ROW * SLOT_W)

    def _row_lists():
        rows = []
        for r in order:
            ips = [n["ip"] for n in layers[r]]
            for i in range(0, len(ips), MAX_PER_ROW):
                rows.append(ips[i:i + MAX_PER_ROW])
        return rows

    rows = _row_lists()
    legend_y = y_0 + len(rows) * ROW_H
    height = legend_y + LEGEND_H + MARGIN
    pos = {}

    def _assign():
        pos.clear()
        y = y_0
        for row in rows:
            n = len(row)
            x0 = (width - (n - 1) * SLOT_W) / 2
            for j, ip in enumerate(row):
                pos[ip] = (x0 + j * SLOT_W, y)
            y += ROW_H

    _assign()
    # Barycenter: pull each device toward the average X of its neighbors so
    # connected devices line up and cables stay short.
    for _ in range(15):
        for r in order:
            def _key(n):
                xs = [pos[m][0] for m in neigh.get(n["ip"], []) if m in pos]
                return sum(xs) / len(xs) if xs else pos.get(n["ip"], (width / 2, 0))[0]
            layers[r].sort(key=_key)
        rows = _row_lists()
        _assign()
    return pos, width, height, legend_y, content_top


def _layout_star(layers, order, _max_dev_w):
    """Radial layout: top tiers at the centre, other tiers in concentric rings."""
    SLOT = _max_dev_w + 90.0
    center_nodes = [n for r in order[:2] for n in layers[r]]
    ring_tiers = order[2:]
    radii = []
    radius = 240.0
    for r in ring_tiers:
        n = len(layers[r])
        rr = max(radius, n * SLOT / (2 * math.pi))
        radii.append(rr)
        radius = rr + 220.0
    max_radius = radii[-1] if radii else 260.0
    content_top = MARGIN + HEADER_H
    content_h = 2 * max_radius + 120.0
    width = max(1150, 2 * (max_radius + SLOT))
    legend_y = content_top + content_h
    height = legend_y + LEGEND_H + MARGIN
    cx = width / 2
    cy = content_top + content_h / 2
    pos = {}
    n = len(center_nodes)
    for i, node in enumerate(center_nodes):
        pos[node["ip"]] = (cx + (i - (n - 1) / 2) * SLOT, cy)
    for ri, r in enumerate(ring_tiers):
        devices = layers[r]
        n = len(devices)
        rr = radii[ri]
        for i, node in enumerate(devices):
            angle = 2 * math.pi * i / n - math.pi / 2
            pos[node["ip"]] = (cx + rr * math.cos(angle), cy + rr * math.sin(angle))
    return pos, width, height, legend_y, content_top


def _layout_ring(layers, order, _max_dev_w):
    """Single circle of all devices."""
    SLOT = _max_dev_w + 90.0
    all_nodes = [n for r in order for n in layers[r]]
    n = len(all_nodes)
    r = max(220.0, n * SLOT / (2 * math.pi))
    content_top = MARGIN + HEADER_H
    content_h = 2 * r + 120.0
    width = max(1150, 2 * (r + SLOT))
    legend_y = content_top + content_h
    height = legend_y + LEGEND_H + MARGIN
    cx = width / 2
    cy = content_top + content_h / 2
    pos = {}
    for i, node in enumerate(all_nodes):
        angle = 2 * math.pi * i / n - math.pi / 2
        pos[node["ip"]] = (cx + r * math.cos(angle), cy + r * math.sin(angle))
    return pos, width, height, legend_y, content_top


def _layout_bus(layers, order, _max_dev_w):
    """Linear backbone: all devices in a single horizontal row."""
    SLOT = _max_dev_w + 90.0
    all_nodes = [n for r in order for n in layers[r]]
    n = len(all_nodes)
    content_top = MARGIN + HEADER_H
    width = max(1150, MARGIN * 2 + n * SLOT)
    y = content_top + 220.0
    legend_y = y + 200.0
    height = legend_y + LEGEND_H + MARGIN
    x0 = (width - (n - 1) * SLOT) / 2
    pos = {}
    for i, node in enumerate(all_nodes):
        pos[node["ip"]] = (x0 + i * SLOT, y)
    return pos, width, height, legend_y, content_top


def _auto_topology(nodes: list[dict], links: list[dict]) -> str:
    """Recommend a layout topology from the network's shape.

    - Star: a true hub-and-spoke (one hub links to most of the network, and
      the rest are mostly degree-1 leaves).
    - Tree: everything else (hierarchical default).
    """
    n = len(nodes)
    if n == 0:
        return "tree"
    adj: dict[str, list[str]] = {nd["ip"]: [] for nd in nodes}
    ips = set(adj)
    for l in links:
        a, b = l.get("source"), l.get("target")
        if a in ips and b in ips and a != b:
            adj[a].append(b); adj[b].append(a)
    degs = [len(v) for v in adj.values()]
    if not degs:
        return "tree"
    max_deg = max(degs)
    leaves = sum(1 for d in degs if d <= 1)
    if n <= 30 and max_deg >= int(n * 0.5) and leaves >= int(n * 0.5):
        return "star"
    return "tree"


def _device_rects(pos, half_w, half_h, pad=4.0) -> list[tuple[float, float, float, float]]:
    """Axis-aligned rect (x0, y0, x1, y1) for every device icon."""
    return [(pos[ip][0] - half_w(ip) - pad, pos[ip][1] - half_h(ip) - pad,
             pos[ip][0] + half_w(ip) + pad, pos[ip][1] + half_h(ip) + pad)
            for ip in pos]


def _usable_channels(obstacles: list, margin: float = 110.0) -> list[float]:
    """Horizontal cable levels in the empty bands between device rows."""
    ys = sorted(set(r[1] for r in obstacles) | set(r[3] for r in obstacles))
    cands = [(a + b) / 2 for a, b in zip(ys, ys[1:])]
    cands += [ys[0] - margin, ys[-1] + margin]
    return sorted(c for c in cands if all(not (o[1] <= c <= o[3]) for o in obstacles))


def _usable_gutters(obstacles: list, margin: float = 70.0) -> list[float]:
    """Vertical cable lanes in the empty columns between devices."""
    xs = sorted(set(r[0] for r in obstacles) | set(r[2] for r in obstacles))
    cands = [(a + b) / 2 for a, b in zip(xs, xs[1:])]
    cands += [xs[0] - margin, xs[-1] + margin]
    return sorted(g for g in cands if all(not (o[0] <= g <= o[2]) for o in obstacles))


def _segment_clear(x1: float, y1: float, x2: float, y2: float, obstacles: list) -> bool:
    xa, xb = min(x1, x2), max(x1, x2)
    ya, yb = min(y1, y2), max(y1, y2)
    return all(not (xa <= o[2] and xb >= o[0] and ya <= o[3] and yb >= o[1]) for o in obstacles)


def _path_crossings(pts: list, obstacles: list) -> int:
    return sum(0 if _segment_clear(x1, y1, x2, y2, obstacles) else 1
               for (x1, y1), (x2, y2) in zip(pts, pts[1:]))


def _route_avoid(sx, sy, tx, ty, obstacles, channels, gutters, same_row=False):
    """Orthogonal path (sx,sy)->(tx,ty) that rides empty channels/lanes and
    detours around device icons. Returns (points, crossing_count)."""
    if same_row or abs(sy - ty) < 1.0:  # same row: ride the gap below the row
        below = [c for c in channels if c > sy + 20]
        c = min(below) if below else sy + 80
        pts = [(sx, sy), (sx, c), (tx, c), (tx, ty)]
        return pts, _path_crossings(pts, obstacles)
    lo, hi = min(sy, ty), max(sy, ty)
    best = None
    for c in channels:
        if not (lo < c < hi):
            continue
        pts = [(sx, sy), (sx, c), (tx, c), (tx, ty)]
        n = _path_crossings(pts, obstacles)
        if n == 0:
            return pts, 0
        if best is None or n < best[0]:
            best = (n, pts)
    # 4-bend detour: source channel -> gutter lane -> target channel
    xlo, xhi = min(sx, tx) - 260, max(sx, tx) + 260
    for c1 in channels:
        if not (lo < c1 < hi):
            continue
        for c2 in channels:
            if not (lo < c2 < hi):
                continue
            for gx in gutters:
                if not (xlo < gx < xhi):
                    continue
                pts = [(sx, sy), (sx, c1), (gx, c1), (gx, c2), (tx, c2), (tx, ty)]
                n = _path_crossings(pts, obstacles)
                if n == 0:
                    return pts, 0
                if best is None or n < best[0]:
                    best = (n, pts)
    if best:
        return best[1], best[0]
    return [(sx, sy), (tx, ty)], 1


def build_scene(nodes: list[dict], links: list[dict], opts: dict) -> Scene:
    title = (opts.get("title") or "AMTRAK NETWORK DIAGRAM").upper()
    legend = opts.get("legend") or DEFAULT_LEGEND
    color_links = opts.get("color_links", True)
    legend_color = {e.get("key"): e.get("color") for e in legend if e.get("key")}

    if opts.get("exclude_endpoints", False):
        keep = {n["ip"] for n in nodes if _layer_of(n) != "endpoint"}
        nodes = [n for n in nodes if n["ip"] in keep]
        links = [l for l in links if l.get("source") in keep and l.get("target") in keep]

    # Group devices into logical tiers (Internet → Router → Core → …)
    layer_of = {n["ip"]: _layer_of(n) for n in nodes}
    layers = {}
    for n in nodes: layers.setdefault(layer_of[n["ip"]], []).append(n)
    order = [k for k in LAYER_KEYS if k in layers]
    layer_idx = {k: i for i, k in enumerate(order)}
    for r in order: layers[r].sort(key=lambda n: (n.get("hostname") or n.get("ip") or ""))

    # Device icons, sized up-front so slots fit the widest icon
    dt_by_ip = {n["ip"]: (n.get("device_type") or "").lower() for n in nodes}
    nodes_by_ip = {n["ip"]: n for n in nodes}
    device_shape = {}
    _max_dev_w = GLYPH_W
    for n in nodes:
        ip = n["ip"]; dt = dt_by_ip.get(ip, "")
        hn = (n.get("hostname") or "").split(".")[0]
        icon_path = _icon_path(dt, n.get("model") or "", hn)
        kind = _icon_kind(dt, n.get("model") or "", hn)
        if icon_path:
            w, h = _icon_size(icon_path, 64 if kind == "ap" else 100 if kind == "router" else 96,
                              64 if kind == "ap" else 56 if kind == "router" else 56)
        else:
            w, h = GLYPH_W, GLYPH_H
        device_shape[ip] = (w / 2, h / 2, kind, icon_path)
        if w > _max_dev_w: _max_dev_w = w
    _DFLT = (GLYPH_W / 2, GLYPH_H / 2, "unknown", None)

    # Links — aggregate parallel links into one line per device pair
    pair_links = {}
    for l in links:
        a, b = l.get("source"), l.get("target")
        if not a or not b or a == b or a not in layer_of or b not in layer_of: continue
        pair_links.setdefault(tuple(sorted((a, b))), []).append(l)

    valid = []
    for (a, b), group in pair_links.items():
        src_ifs = sorted(set(l["source_interface"] or "" for l in group if l["source"] == a))
        dst_ifs = sorted(set(l["target_interface"] or "" for l in group if l["target"] == b))
        valid.append({"source": a, "target": b,
                      "source_interface": src_ifs[0] if src_ifs else "",
                      "target_interface": dst_ifs[0] if dst_ifs else "",
                      "source_interfaces": src_ifs,
                      "target_interfaces": dst_ifs})

    # Link detail: filter noisy links for dense sites.
    #   full     — draw every link.
    #   backbone — drop same-tier (redundancy) links between switches.
    #   core     — only the spine: links touching the router/core tiers.
    link_detail = (opts.get("link_detail") or "full").lower()
    if link_detail == "backbone":
        valid = [l for l in valid if layer_of[l["source"]] != layer_of[l["target"]]]
    elif link_detail == "core":
        spine = ("internet", "velocloud", "router", "core")
        valid = [l for l in valid if layer_of[l["source"]] in spine or layer_of[l["target"]] in spine]

    # Select a layout topology (auto-detected unless explicitly chosen).
    topology = (opts.get("topology") or "auto").lower()
    if topology == "auto":
        topology = _auto_topology(nodes, links)
    if topology == "star":
        pos, width, height, legend_y, content_top = _layout_star(layers, order, _max_dev_w)
    elif topology == "ring":
        pos, width, height, legend_y, content_top = _layout_ring(layers, order, _max_dev_w)
    elif topology == "bus":
        pos, width, height, legend_y, content_top = _layout_bus(layers, order, _max_dev_w)
    else:
        pos, width, height, legend_y, content_top = _layout_tree(layers, order, valid, _max_dev_w)

    show_tb = opts.get("title_block", True)
    if not show_tb:
        height = legend_y + MARGIN

    scene = Scene(width, height)
    scene.rect(MARGIN / 2, MARGIN / 2, width - MARGIN, height - MARGIN, stroke=C_FRAME, sw=1.5)
    if os.path.exists(ASSET_LOGO): scene.image(MARGIN + 6, MARGIN / 2 + 8, 170.0, 170.0 * 394 / 700, ASSET_LOGO)
    scene.text(width / 2, MARGIN + 26, title, size=26)

    # Subnet zone boxes: draw a light rectangle around devices that share a
    # /24 subnet (drawn behind devices/links so they stay readable). Only
    # meaningful for the row/column topologies, so skip for radial layouts.
    if topology in ("tree", "bus"):
        subnet_groups: dict[str, list[str]] = {}
        for ip in pos:
            pfx = _subnet24(ip)
            if pfx:
                subnet_groups.setdefault(pfx, []).append(ip)
        for pfx, ips in subnet_groups.items():
            if len(ips) < 2:
                continue
            xs = [pos[ip][0] for ip in ips]
            ys = [pos[ip][1] for ip in ips]
            min_x = min(xs) - _max_dev_w / 2 - 25
            max_x = max(xs) + _max_dev_w / 2 + 25
            min_y = min(ys) - 70
            max_y = max(ys) + 70
            scene.rect(min_x, min_y, max_x - min_x, max_y - min_y, fill=C_SUBNET_FILL, stroke=C_SUBNET_STROKE, sw=1.0)
            scene.text(min_x + 6, min_y + 12, pfx, size=8.5, bold=True, color=C_SUBNET_TEXT, align="left")

    # Spread links leaving the same device edge so cables don't stack
    attach = {}
    for li, l in enumerate(valid):
        a, b = l["source"], l["target"]
        if abs(pos[a][1] - pos[b][1]) < 1.0:
            attach.setdefault(a, {}).setdefault("bottom", []).append(li)
            attach.setdefault(b, {}).setdefault("bottom", []).append(li)
        elif pos[a][1] < pos[b][1]:
            attach.setdefault(a, {}).setdefault("bottom", []).append(li)
            attach.setdefault(b, {}).setdefault("top", []).append(li)
        else:
            attach.setdefault(a, {}).setdefault("top", []).append(li)
            attach.setdefault(b, {}).setdefault("bottom", []).append(li)
    def attach_x(ip, side, li):
        group = attach.get(ip, {}).get(side, [])
        n = len(group)
        if n <= 1: return pos[ip][0]
        return pos[ip][0] + (group.index(li) - (n - 1) / 2) * 10.0
    def half_w(ip): return device_shape.get(ip, _DFLT)[0]
    def half_h(ip): return device_shape.get(ip, _DFLT)[1]

    # Obstacle-avoiding routing for the row-based topologies
    rects = _device_rects(pos, half_w, half_h)
    rect_by_ip = {ip: _device_rects({ip: pos[ip]}, half_w, half_h)[0] for ip in pos}

    # Reserve each device's label block (name/IP/model to the right of the icon)
    def _txt_w(text, size): return len(text) * size * 0.62
    label_block = {}
    for ip in pos:
        hn = (nodes_by_ip[ip].get("hostname") or "").split(".")[0] or ip
        model = (nodes_by_ip[ip].get("model") or "").strip()
        lines = [hn] + [ip] + ([model] if model else [])
        w = max(_txt_w(t, 9 if i == 0 else 7.5) for i, t in enumerate(lines)) if lines else 10.0
        iw, ih = device_shape.get(ip, _DFLT)[0] * 2, device_shape.get(ip, _DFLT)[1] * 2
        lx = pos[ip][0] + iw / 2 + 8
        y0 = pos[ip][1] - (len(lines) - 1) * 13 / 2 + 4
        label_block[ip] = (lx - 2, y0 - 11, lx + w + 2, y0 + (len(lines) - 1) * 13 + 2)

    # Routing lanes (channels/gutters) avoid both icons and label text.
    if topology in ("tree", "bus"):
        all_obs = list(rects) + list(label_block.values())
        channels = _usable_channels(all_obs)
        gutters = _usable_gutters(all_obs)
    else:
        channels, gutters = [], []

    # Rect-based label collision map (device names reserved first)
    placed_rects = []
    for ip, (x0, y0, x1, y1) in label_block.items():
        placed_rects.append((x0 - 3, y0 - 2, x1 + 3, y1 + 2))
    def _label_ok(x, y, w, h):
        for rx0, ry0, rx1, ry1 in placed_rects:
            if x < rx1 and x + w > rx0 and y < ry1 and y + h > ry0:
                return False
        placed_rects.append((x, y, x + w, y + h))
        return True

    # Draw links (elbow, obstacle-avoiding) with port names on the cable
    for li, l in enumerate(valid):
        a, b = l["source"], l["target"]
        role = _link_color_key(a, b, layer_of, l["source_interface"], l["target_interface"])
        color = legend_color.get(role, C_LINK) if color_links else C_LINK
        ia_s = _port_label(l.get("source_interfaces", [l["source_interface"]]))
        ib_s = _port_label(l.get("target_interfaces", [l["target_interface"]]))
        if abs(pos[a][1] - pos[b][1]) < 1.0:
            # Same row: ride the gap below the row, both ends on the bottom edge.
            sx, sy = attach_x(a, "bottom", li), pos[a][1] + half_h(a)
            tx, ty = attach_x(b, "bottom", li), pos[b][1] + half_h(b)
        elif pos[a][1] < pos[b][1]:
            sx, sy = attach_x(a, "bottom", li), pos[a][1] + half_h(a)
            tx, ty = attach_x(b, "top", li), pos[b][1] - half_h(b)
        else:
            sx, sy = attach_x(a, "top", li), pos[a][1] - half_h(a)
            tx, ty = attach_x(b, "bottom", li), pos[b][1] + half_h(b)
        link_obs = [rects[i] for i, ip in enumerate(pos) if ip not in (a, b)]
        link_obs += [label_block[ip] for ip in label_block if ip not in (a, b)]
        if channels:
            same_row = abs(pos[a][1] - pos[b][1]) < 1.0
            pts, _ = _route_avoid(sx, sy, tx, ty, link_obs, channels, gutters, same_row)
        else:
            dirn = 1 if sy < ty else -1
            cy = sy + dirn * 50
            pts = [(sx, sy), (sx, cy), (tx, cy), (tx, ty)]
        lw = 2.0 if role in ("wan", "core") else 1.2
        scene.line(pts, color=color, width=lw, tag="link")
        # Place port labels at the midpoint of the longest horizontal cable run
        hseg = None
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if abs(y1 - y2) < 0.5 and (hseg is None or abs(x2 - x1) > hseg[2]):
                hseg = (min(x1, x2), y1, abs(x2 - x1))
        if hseg:
            lx = hseg[0] + hseg[2] / 2
            ly = hseg[1]
        else:
            lx, ly = (sx + tx) / 2, (sy + ty) / 2
        if ia_s and _label_ok(lx - _txt_w(ia_s, 8) / 2, ly - 14, _txt_w(ia_s, 8), 9):
            scene.text(lx, ly - 8, ia_s, size=8, bold=True, color=C_PORT, tag="link")
        if ib_s and _label_ok(lx - _txt_w(ib_s, 8) / 2, ly + 6, _txt_w(ib_s, 8), 9):
            scene.text(lx, ly + 8, ib_s, size=8, bold=True, color=C_PORT, tag="link")
        scene.vlinks.append({"a": a, "b": b, "color": color, "width": lw, "role": role,
                             "src_if": ia_s, "dst_if": ib_s, "pts": pts,
                             "src_label_pos": (lx, ly - 8), "dst_label_pos": (lx, ly + 8),
                             "src_align": "center", "dst_align": "center",
                             "ax": pos[a][0], "ay": pos[a][1], "bx": pos[b][0], "by": pos[b][1]})

    # Draw devices: icon + hostname/IP/model to the RIGHT of the icon, so the
    # vertical cable runs (top/bottom edges) never cross the wording.
    for r in order:
        for n in layers[r]:
            cx, cy = pos[n["ip"]]
            hn = (n.get("hostname") or "").split(".")[0] or n.get("ip") or ""
            ip = n.get("ip") or ""
            model = (n.get("model") or "").strip()
            tag = ("dev", ip)
            iw, ih, icon_kind, icon_path = device_shape.get(ip, _DFLT)[:4]
            iw *= 2; ih *= 2
            lines = [(hn, 9, True)] + ([(ip, 7.5, False)] if ip else []) + ([(model, 7.5, False)] if model else [])
            n_lines = len(lines)
            lx = cx + iw / 2 + 8
            labels = []
            y0 = cy - (n_lines - 1) * 13 / 2 + 4
            for i, (txt, size, bold) in enumerate(lines):
                scene.text(lx, y0 + i * 13, txt, size=size, bold=bold, align="left", tag=tag)
                labels.append((txt, size, bold, C_TEXT))
            if icon_path:
                scene.image(cx - iw / 2, cy - ih / 2, iw, ih, icon_path, tag=tag)
            else:
                scene.rect(cx - GLYPH_W / 2, cy - GLYPH_H / 2, GLYPH_W, GLYPH_H, fill=C_GLYPH, stroke=C_GLYPH_EDGE, sw=1.0, tag=tag)
            scene.devices.append({"ip": ip, "cx": cx, "cy": cy, "kind": icon_kind, "labels": labels, "icon_path": icon_path, "icon_w": iw, "icon_h": ih})

    # Title block + legend (only on the final sheet of a multi-page drawing)
    if show_tb:
        bx = MARGIN + 24; bw = (width - MARGIN / 2) - bx; by = legend_y
        scene.rect(bx, by, bw, LEGEND_H, stroke=C_FRAME, sw=1.2); c1, c2 = bx + 210, bx + 510
        scene.line([(c1, by), (c1, by + LEGEND_H)], color=C_FRAME, width=1.0); scene.line([(c2, by), (c2, by + LEGEND_H)], color=C_FRAME, width=1.0)
        scene.text((bx + c1) / 2, by + 8, "LEGEND", size=9, bold=True, align="center")
        ey = by + 28
        for e in legend:
            scene.rect(bx + 10, ey + 3, 48, 5, fill=e.get("color") or C_LINK, stroke=None, sw=0)
            scene.text(66 + bx, ey, e.get("label") or "", size=8.5, align="left"); ey += 16
        mid_x = c1 + (c2 - c1) / 2
        if os.path.exists(ASSET_LOGO): scene.image(mid_x - 32, by + 10, 64, 36, ASSET_LOGO)
        text_y = by + 56
        for i, ln in enumerate(PROPRIETARY.split("\n")): scene.text(mid_x, text_y + i * 13, ln, size=9, bold=True, italic=True, align="center")
        rows = [[("Drawn By: ", opts.get("drawn_by") or ""), ("Drawn Date: ", opts.get("drawn_date") or "08142026")], [("Drawing Title: ", opts.get("drawing_title") or title)], [("Document Name: ", opts.get("document_name") or "")], [("Revision: ", opts.get("revision") or ""), ("Rev. Date: ", "14 Aug 26"), ("Rev. Time: ", "07:45 PM")]]
        rh = LEGEND_H / 4
        for i, row in enumerate(rows):
            ry = by + i * rh
            if i: scene.line([(c2, ry), (bx + bw, ry)], color=C_FRAME, width=1.0)
            cw = (bx + bw - c2) / len(row)
            for j, (label, val) in enumerate(row):
                if j: scene.line([(c2 + j * cw, ry), (c2 + j * cw, ry + rh)], color=C_FRAME, width=1.0)
                scene.text(c2 + j * cw + cw / 2, ry + rh / 2 - 4, label + val, size=9, align="center")
    return scene


def render_pdf(scenes: list[Scene]) -> bytes:
    from reportlab.pdfgen import canvas as _canvas
    from reportlab.lib.utils import ImageReader
    limit = 200 * 72
    buf = io.BytesIO()
    f0 = min(1.0, limit / scenes[0].width, limit / scenes[0].height)
    c = _canvas.Canvas(buf, pagesize=(scenes[0].width * f0, scenes[0].height * f0))
    for scene in scenes:
        f = min(1.0, limit / scene.width, limit / scene.height)
        c.setPageSize((scene.width * f, scene.height * f))
        H = scene.height
        c.saveState()
        if f < 1.0: c.scale(f, f)
        def fy(y): return H - y
        for p in scene.prims:
            k = p["k"]
            if k == "rect":
                if p.get("fill"): c.setFillColor(p["fill"])
                if p.get("stroke"): c.setStrokeColor(p["stroke"]); c.setLineWidth(p["sw"])
                c.rect(p["x"], fy(p["y"] + p["h"]), p["w"], p["h"], fill=1 if p.get("fill") else 0, stroke=1 if p.get("stroke") else 0)
            elif k == "ellipse":
                if p.get("fill"): c.setFillColor(p["fill"])
                if p.get("stroke"): c.setStrokeColor(p["stroke"]); c.setLineWidth(p["sw"])
                c.ellipse(p["cx"] - p["rx"], fy(p["cy"] + p["ry"]), p["cx"] + p["rx"], fy(p["cy"] - p["ry"]), fill=1 if p.get("fill") else 0, stroke=1 if p.get("stroke") else 0)
            elif k == "line":
                c.setStrokeColor(p["color"]); c.setLineWidth(p["width"]); path = c.beginPath(); path.moveTo(p["pts"][0][0], fy(p["pts"][0][1]))
                for x, y in p["pts"][1:]: path.lineTo(x, fy(y))
                c.drawPath(path, fill=0, stroke=1)
            elif k == "text":
                font = "Helvetica-Bold" if p["bold"] else ("Helvetica-Oblique" if p["italic"] else "Helvetica"); c.setFont(font, p["size"]); c.setFillColor(p["color"])
                angle = p.get("angle", 0.0)
                c.saveState()
                c.translate(p["x"], fy(p["y"] + p["size"]))
                if angle: c.rotate(angle)
                if p["align"] == "left": c.drawString(0, 0, p["v"])
                elif p["align"] == "right": c.drawRightString(0, 0, p["v"])
                else: c.drawCentredString(0, 0, p["v"])
                c.restoreState()
            elif k == "image":
                img = ImageReader(p["path"])
                if img: c.drawImage(img, p["x"], fy(p["y"] + p["h"]), width=p["w"], height=p["h"], mask="auto")
        c.restoreState()
        c.showPage()
    c.save(); return buf.getvalue()


def _hex(color: str):
    color = (color or "#000000").lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


_FONT_CANDIDATES = {
    (False, False): ["/System/Library/Fonts/Helvetica.ttc",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    (True, False): ["/System/Library/Fonts/Helvetica.ttc",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    (False, True): ["/System/Library/Fonts/Helvetica.ttc",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"],
    (True, True): ["/System/Library/Fonts/Helvetica.ttc",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"],
}


def _pil_font(size: int, bold: bool, italic: bool):
    from PIL import ImageFont
    for path in _FONT_CANDIDATES[(bold, italic)]:
        if os.path.exists(path):
            try:
                idx = 1 if (bold and path.endswith(".ttc")) else 0
                return ImageFont.truetype(path, size, index=idx)
            except Exception:
                continue
    return ImageFont.load_default()


def _render_png_image(scene: Scene, scale: int = 2):
    from PIL import Image, ImageDraw
    W, H = int(scene.width * scale), int(scene.height * scale)
    img = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(img)
    def s(v): return v * scale
    for p in scene.prims:
        k = p["k"]
        if k == "rect": d.rectangle([s(p["x"]), s(p["y"]), s(p["x"] + p["w"]), s(p["y"] + p["h"])], fill=_hex(p["fill"]) if p.get("fill") else None, outline=_hex(p["stroke"]) if p.get("stroke") else None)
        elif k == "line": d.line([s(x) for pt in p["pts"] for x in pt], fill=_hex(p["color"]), width=int(p["width"] * scale))
        elif k == "text":
            angle = p.get("angle", 0.0)
            if angle:
                from PIL import Image as _Img
                font = _pil_font(int(p["size"] * scale), p["bold"], p["italic"])
                tmp = _Img.new("RGBA", (10, 10), (0, 0, 0, 0))
                tdraw = ImageDraw.Draw(tmp)
                bbox = tdraw.textbbox((0, 0), p["v"], font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                timg = _Img.new("RGBA", (max(1, tw), max(1, th)), (0, 0, 0, 0))
                tdraw2 = ImageDraw.Draw(timg)
                tdraw2.text((-bbox[0], -bbox[1]), p["v"], fill=_hex(p["color"]) + (255,), font=font)
                timg = timg.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
                img.paste(timg, (int(s(p["x"]) - timg.width / 2), int(s(p["y"]) - timg.height / 2)), timg)
            else:
                d.text((s(p["x"]), s(p["y"])), p["v"], fill=_hex(p["color"]), font=_pil_font(int(p["size"] * scale), p["bold"], p["italic"]), anchor="mm" if p["align"]=="center" else "lm" if p["align"]=="left" else "rm")
        elif k == "image":
            try:
                with Image.open(p["path"]) as icon:
                    icon = icon.convert("RGBA").resize((int(s(p["w"])), int(s(p["h"]))), Image.Resampling.LANCZOS)
                    img.paste(icon, (int(s(p["x"])), int(s(p["y"]))), icon)
            except Exception: pass
    return img


def render_png(scenes: list[Scene], scale: int = 2) -> bytes:
    from PIL import Image
    images = [_render_png_image(sc, scale) for sc in scenes]
    max_w = max(im.width for im in images)
    total_h = sum(im.height for im in images)
    combined = Image.new("RGB", (max_w, total_h), "white")
    y = 0
    for im in images:
        combined.paste(im, (0, y)); y += im.height
    buf = io.BytesIO(); combined.save(buf, format="PNG"); return buf.getvalue()


def _connector_1d(sid: int, pts: list[tuple[float, float]], color: str, width_pt: float, begin_ref=None, end_ref=None, layer_name="") -> str:
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]; bx,by=xs[0],ys[0]; ex,ey=xs[-1],ys[-1]; w,h=ex-bx,ey-by; pinx,piny=(bx+ex)/2,(by+ey)/2
    geom=['<Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>']
    for i,(x,y) in enumerate(pts[1:], start=2):
        if i==len(pts): geom.append(f'<Row T="LineTo" IX="{i}"><Cell N="X" F="Width*1"/><Cell N="Y" F="Height*1"/></Row>')
        else: geom.append(f'<Row T="LineTo" IX="{i}"><Cell N="X" V="{x-bx:.4f}"/><Cell N="Y" V="{y-by:.4f}"/></Row>')
    def _pt(ref):
        if ref: sh, ci = ref; return f"PAR(PNT(Sheet.{sh}!Connections.X{ci},Sheet.{sh}!Connections.Y{ci}))"
        return None
    bf=_pt(begin_ref); ef=_pt(end_ref); bxx=f' F="{bf}"' if bf else ' F="PinX-Width*0.5"'; byy=f' F="{bf}"' if bf else ' F="PinY-Height*0.5"'; exx=f' F="{ef}"' if ef else ' F="PinX+Width*0.5"'; eyy=f' F="{ef}"' if ef else ' F="PinY+Height*0.5"'
    layer = f'<LayerMem Layer="{_xml_escape(layer_name)}"/>' if layer_name else ""
    return f'<Shape ID="{sid}" Type="Shape"><Cell N="PinX" V="{pinx:.4f}"/><Cell N="PinY" V="{piny:.4f}"/><Cell N="Width" V="{w:.4f}" F="GUARD(EndX-BeginX)"/><Cell N="Height" V="{h:.4f}" F="GUARD(EndY-BeginY)"/><Cell N="LocPinX" V="{w/2:.4f}" F="Width*0.5"/><Cell N="LocPinY" V="{h/2:.4f}" F="Height*0.5"/><Cell N="BeginX" V="{bx:.4f}"{bxx}/><Cell N="BeginY" V="{by:.4f}"{byy}/><Cell N="EndX" V="{ex:.4f}"{exx}/><Cell N="EndY" V="{ey:.4f}"{eyy}/><Cell N="LineColor" V="{color}"/><Cell N="LineWeight" V="{width_pt/72:.4f}"/><Cell N="FillPattern" V="0"/><Cell N="OneD" V="1"/><Cell N="GlueType" V="2"/><Cell N="RerouteStyle" V="0"/><Cell N="ConLineJumpStyle" V="1"/><Cell N="PageShapeSplit" V="1"/>{layer}<Section N="Geometry" IX="0">{"".join(geom)}</Section></Shape>'


_XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'


def _scene_shapes(scene: Scene, media_n: list[int]) -> tuple[str, list[str], list[tuple[str, bytes]]]:
    """Generate the VSDX shapes/rels/media for one scene (one page)."""
    H = scene.height; shapes=[]; connects=[]; rels=[]; media=[]; sid=1
    def flip_y(y): return (H - y) / 72
    for p in scene.prims:
        if p.get("tag"): continue
        k=p["k"]
        if k=="rect":
            w,h=p["w"]/72,p["h"]/72; fill_c=p.get("fill"); stroke_c=p.get("stroke")
            fill_cells=f'<Cell N="FillForegnd" V="{fill_c}"/><Cell N="FillPattern" V="1"/>' if fill_c else '<Cell N="FillPattern" V="0"/>'
            stroke_cells=f'<Cell N="LineColor" V="{stroke_c}"/>' if stroke_c else '<Cell N="LinePattern" V="0"/>'
            shapes.append(f'<Shape ID="{sid}" Type="Shape"><Cell N="PinX" V="{(p["x"]+p["w"]/2)/72:.4f}"/><Cell N="PinY" V="{flip_y(p["y"]+p["h"]/2):.4f}"/><Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/><Cell N="LocPinX" V="{w/2:.4f}"/><Cell N="LocPinY" V="{h/2:.4f}"/>{fill_cells}{stroke_cells}<Cell N="LineWeight" V="{p["sw"]/72:.4f}"/><Section N="Geometry" IX="0"><Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row><Row T="LineTo" IX="2"><Cell N="X" V="{w:.4f}"/><Cell N="Y" V="0"/></Row><Row T="LineTo" IX="3"><Cell N="X" V="{w:.4f}"/><Cell N="Y" V="{h:.4f}"/></Row><Row T="LineTo" IX="4"><Cell N="X" V="0"/><Cell N="Y" V="{h:.4f}"/></Row><Row T="LineTo" IX="5"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row></Section></Shape>'); sid+=1
        elif k=="line":
            pts=[(x/72, flip_y(y)) for x,y in p["pts"]]; bx,by=pts[0]; ex,ey=pts[-1]; w,h=ex-bx,ey-by; pinx,piny=(bx+ex)/2,(by+ey)/2
            shapes.append(f'<Shape ID="{sid}" Type="Shape"><Cell N="PinX" V="{pinx:.4f}"/><Cell N="PinY" V="{piny:.4f}"/><Cell N="Width" V="{abs(w):.4f}"/><Cell N="Height" V="{abs(h):.4f}"/><Cell N="LocPinX" V="{w/2:.4f}"/><Cell N="LocPinY" V="{h/2:.4f}"/><Cell N="LineColor" V="{p["color"]}"/><Cell N="LineWeight" V="{p["width"]/72:.4f}"/><Section N="Geometry" IX="0"><Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row><Row T="LineTo" IX="2"><Cell N="X" V="{w:.4f}"/><Cell N="Y" V="{h:.4f}"/></Row></Section></Shape>'); sid+=1
        elif k=="text":
            angle = p.get("angle", 0.0)
            w,h=max(0.3, len(p["v"])*p["size"]*0.62/72), p["size"]*1.6/72
            ang_cell = f'<Cell N="TxtAngle" V="{angle * 3.14159265358979 / 180:.4f}"/>' if angle else ""
            shapes.append(f'<Shape ID="{sid}" Type="Shape"><Cell N="PinX" V="{p["x"]/72:.4f}"/><Cell N="PinY" V="{flip_y(p["y"]):.4f}"/><Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/><Cell N="LocPinX" V="{w/2:.4f}"/><Cell N="LocPinY" V="{h/2:.4f}"/>{ang_cell}<Section N="Character"><Row IX="0"><Cell N="Size" V="{p["size"]/72:.4f}"/><Cell N="Style" V="{"1" if p["bold"] else "0"}"/><Cell N="Color" V="{p["color"]}"/></Row></Section><Text>{_xml_escape(p["v"])}</Text></Shape>'); sid+=1

    device_box = {}
    for dev in scene.devices:
        cx,cy=dev["cx"],dev["cy"]; iw,ih=dev["icon_w"],dev["icon_h"]; device_box[dev["ip"]]=(cx-iw/2, cy-ih/2, iw, ih)
    conn_points={}; conn_idx={}
    for vl in scene.vlinks:
        for ip, (sx,sy) in ((vl["a"], vl["pts"][0]), (vl["b"], vl["pts"][-1])):
            gx,gy,bw,bh=device_box[ip]; lx=(sx-gx)/72; ly=(gy+bh-sy)/72
            key=(ip, round(sx,3), round(sy,3))
            if key not in conn_idx: pts=conn_points.setdefault(ip, []); conn_idx[key]=len(pts)+1; pts.append((lx,ly))

    dev_shape_id={}
    for dev in scene.devices:
        ip=dev["ip"]; cx,cy=dev["cx"],dev["cy"]; iw,ih=dev["icon_w"],dev["icon_h"]; gx,gy,bw,bh=device_box[ip]; gid=sid; sid+=1; dev_shape_id[ip]=gid
        children=[]
        if dev["icon_path"] and os.path.exists(dev["icon_path"]):
            media_n[0] += 1; img_idx = media_n[0]
            rid=f"rId{len(rels)+1}"; img_w=iw/72; img_h=ih/72
            media.append((f"visio/media/image{img_idx}.png", open(dev["icon_path"],"rb").read())); rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image{img_idx}.png"/>')
            children.append(f'<Shape ID="{sid}" Type="Foreign"><Cell N="PinX" V="{img_w/2:.4f}"/><Cell N="PinY" V="{img_h/2:.4f}"/><Cell N="Width" V="{img_w:.4f}"/><Cell N="Height" V="{img_h:.4f}"/><Cell N="LocPinX" V="{img_w/2:.4f}"/><Cell N="LocPinY" V="{img_h/2:.4f}"/><Cell N="ImgWidth" V="{img_w:.4f}"/><Cell N="ImgHeight" V="{img_h:.4f}"/><ForeignData ForeignType="Bitmap" CompressionType="PNG" DisplayFormat="24-bit RGB"><Rel r:id="{rid}"/></ForeignData><Section N="Geometry" IX="0"><Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row><Row T="LineTo" IX="2"><Cell N="X" V="{img_w:.4f}"/><Cell N="Y" V="0"/></Row><Row T="LineTo" IX="3"><Cell N="X" V="{img_w:.4f}"/><Cell N="Y" V="{img_h:.4f}"/></Row><Row T="LineTo" IX="4"><Cell N="X" V="0"/><Cell N="Y" V="{img_h:.4f}"/></Row><Row T="LineTo" IX="5"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row></Section></Shape>'); sid+=1
        else:
            children.append(f'<Shape ID="{sid}" Type="Shape"><Cell N="PinX" V="{iw/144:.4f}"/><Cell N="PinY" V="{ih/144:.4f}"/><Cell N="Width" V="{iw/72:.4f}"/><Cell N="Height" V="{ih/72:.4f}"/><Cell N="FillForegnd" V="{C_GLYPH}"/><Cell N="FillPattern" V="1"/><Cell N="LineColor" V="{C_GLYPH_EDGE}"/><Section N="Geometry" IX="0"><Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row><Row T="LineTo" IX="2"><Cell N="X" V="{iw/72:.4f}"/><Cell N="Y" V="0"/></Row><Row T="LineTo" IX="3"><Cell N="X" V="{iw/72:.4f}"/><Cell N="Y" V="{ih/72:.4f}"/></Row><Row T="LineTo" IX="4"><Cell N="X" V="0"/><Cell N="Y" V="{ih/72:.4f}"/></Row><Row T="LineTo" IX="5"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row></Section></Shape>'); sid+=1
        for i, (txt, sz, bold, col) in enumerate(dev["labels"]):
            n = len(dev["labels"])
            lx_l = (iw / 2 + 8) / 72
            ly_l = ((n - 1) / 2 - i) * 13 / 72
            tw = max(0.3, len(txt) * sz * 0.62 / 72)
            children.append(f'<Shape ID="{sid}" Type="Shape"><Cell N="PinX" V="{lx_l:.4f}"/><Cell N="PinY" V="{ly_l:.4f}"/><Cell N="Width" V="{tw:.4f}"/><Cell N="Height" V="{sz * 1.6 / 72:.4f}"/><Cell N="LocPinX" V="0"/><Cell N="LocPinY" V="{sz * 0.8 / 72:.4f}"/><Section N="Character"><Row IX="0"><Cell N="Size" V="{sz / 72:.4f}"/><Cell N="Style" V="{"1" if bold else "0"}"/><Cell N="Color" V="{col}"/></Row></Section><Section N="Paragraph"><Row IX="0"><Cell N="HorzAlign" V="0"/></Row></Section><Text>{_xml_escape(txt)}</Text></Shape>')
            sid += 1
        conn_rows = []
        for i, (lx, ly) in enumerate(conn_points.get(ip, [])):
            conn_rows.append(f'<Row T="Connection" IX="{i}"><Cell N="X" V="{lx:.5f}"/><Cell N="Y" V="{ly:.5f}"/></Row>')
        conn_section = f'<Section N="Connection">{"".join(conn_rows)}</Section>' if conn_rows else ""
        shapes.append(f'<Shape ID="{gid}" Type="Group"><Cell N="PinX" V="{cx/72:.4f}"/><Cell N="PinY" V="{flip_y(cy):.4f}"/><Cell N="Width" V="{iw/72:.4f}"/><Cell N="Height" V="{ih/72:.4f}"/><Cell N="LocPinX" V="{iw/144:.4f}"/><Cell N="LocPinY" V="{ih/144:.4f}"/><Cell N="FillPattern" V="0"/><Cell N="LinePattern" V="0"/>{conn_section}<Shapes>{"".join(children)}</Shapes></Shape>')

    for vl in scene.vlinks:
        aid, bid = dev_shape_id.get(vl["a"]), dev_shape_id.get(vl["b"]); pts=[(x/72, flip_y(y)) for x,y in vl["pts"]]; cid=sid; sid+=1
        aci=conn_idx.get((vl["a"], round(vl["pts"][0][0],3), round(vl["pts"][0][1],3))); bci=conn_idx.get((vl["b"], round(vl["pts"][-1][0],3), round(vl["pts"][-1][1],3)))
        shapes.append(_connector_1d(cid, pts, vl["color"], vl["width"], (aid, aci) if aid and aci else None, (bid, bci) if bid and bci else None, "Connector"))
        for txt, (px, py), al, ang in [(vl["src_if"], vl["src_label_pos"], vl["src_align"], vl.get("src_angle", 0)), (vl["dst_if"], vl["dst_label_pos"], vl["dst_align"], vl.get("dst_angle", 0))]:
            if not txt: continue
            w, h = max(0.3, len(txt)*8*0.62/72), 0.2
            y_in = flip_y(py)
            pinx = px/72 + (w/2 if al=="left" else -w/2 if al=="right" else 0)
            ang_cell = f'<Cell N="TxtAngle" V="{ang*3.14159265358979/180:.4f}"/>' if ang else ""
            shapes.append(f'<Shape ID="{sid}" Type="Shape"><Cell N="PinX" V="{pinx:.4f}"/><Cell N="PinY" V="{y_in:.4f}"/><Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/><Cell N="LocPinX" V="{w/2:.4f}"/><Cell N="LocPinY" V="{h/2:.4f}"/>{ang_cell}<Section N="Character"><Row IX="0"><Cell N="Size" V="{8/72:.4f}"/><Cell N="Style" V="1"/><Cell N="Color" V="{C_PORT}"/></Row></Section><Text>{_xml_escape(txt)}</Text></Shape>'); sid+=1
    return "".join(shapes), rels, media


def render_vsdx(scenes: list[Scene]) -> bytes:
    page_shapes = []; page_rels = []; all_media = []; media_n = [0]
    for scene in scenes:
        sh, rels, media = _scene_shapes(scene, media_n)
        page_shapes.append(sh); page_rels.append(rels); all_media.extend(media)
    n = len(scenes)
    page_overrides = "".join(f'<Override PartName="/visio/pages/page{i+1}.xml" ContentType="application/vnd.ms-visio.page+xml"/>' for i in range(n))
    content_types = _XML_DECL + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/><Override PartName="/visio/masters/masters.xml" ContentType="application/vnd.ms-visio.masters+xml"/><Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>' + page_overrides + '<Override PartName="/visio/windows.xml" ContentType="application/vnd.ms-visio.windows+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>'
    root_rels = _XML_DECL + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'
    doc_xml = _XML_DECL + '<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve"><DocumentSettings TopPage="0" DefaultTextStyle="3" DefaultLineStyle="3" DefaultFillStyle="3" DefaultGuideStyle="4"><GlueSettings>9</GlueSettings><SnapSettings>65847</SnapSettings><SnapExtensions>34</SnapExtensions></DocumentSettings><StyleSheets><StyleSheet ID="0" NameU="No Style" Name="No Style"/><StyleSheet ID="1" NameU="Normal" Name="Normal"/><StyleSheet ID="3" NameU="No Line" Name="No Line"/></StyleSheets></VisioDocument>'
    doc_rels = _XML_DECL + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/masters" Target="masters/masters.xml"/><Relationship Id="rId2" Type="http://schemas.microsoft.com/visio/2010/relationships/pages" Target="pages/pages.xml"/><Relationship Id="rId3" Type="http://schemas.microsoft.com/visio/2010/relationships/windows" Target="windows.xml"/></Relationships>'
    masters_xml = _XML_DECL + '<Masters xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve"><Master ID="0" NameU="Dynamic connector" Name="Dynamic connector"><PageSheet LineStyle="3" FillStyle="3" TextStyle="3"/></Master></Masters>'
    masters_rels = _XML_DECL + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
    page_entries = []
    for i in range(n):
        w = scenes[i].width / 72; h = scenes[i].height / 72
        page_entries.append(f'<Page ID="{i}" NameU="Page-{i+1}" Name="Page-{i+1}" ViewScale="1" ViewCenterX="0" ViewCenterY="0"><PageSheet LineStyle="3" FillStyle="3" TextStyle="3"><Cell N="PageWidth" V="{w:.4f}"/><Cell N="PageHeight" V="{h:.4f}"/><Cell N="PageLineJumpStyle" V="1"/><Cell N="RouteStyle" V="1"/></PageSheet><Rel r:id="rId{i+1}"/></Page>')
    pages_xml = _XML_DECL + '<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve">' + "".join(page_entries) + '</Pages>'
    page_rel_entries = [f'<Relationship Id="rId{i+1}" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page{i+1}.xml"/>' for i in range(n)]
    pages_rels = _XML_DECL + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(page_rel_entries) + '</Relationships>'
    core_xml = _XML_DECL + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>Network Topology</dc:title><dc:creator>Network Mapper</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">2026-08-14T00:00:00Z</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">2026-08-14T00:00:00Z</dcterms:modified></cp:coreProperties>'
    app_xml = _XML_DECL + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Network Mapper</Application><HeadingPairs><vt:vector size="4" baseType="variant"><vt:variant><vt:lpstr>Pages</vt:lpstr></vt:variant><vt:variant><vt:i4>' + str(n) + '</vt:i4></vt:variant><vt:variant><vt:lpstr>Masters</vt:lpstr></vt:variant><vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs><TitlesOfParts><vt:vector size="' + str(n + 1) + '" baseType="lpstr">' + "".join(f'<vt:lpstr>Page-{i+1}</vt:lpstr>' for i in range(n)) + '<vt:lpstr>Dynamic connector</vt:lpstr></vt:vector></TitlesOfParts></Properties>'
    windows_xml = _XML_DECL + '<Windows ClientWidth="1000" ClientHeight="700" xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve"><Window ID="0" WindowType="Drawing" WindowState="1073741824" WindowLeft="0" WindowTop="0" WindowWidth="1000" WindowHeight="700" ContainerType="Page" Page="0" ViewScale="1" ViewCenterX="0" ViewCenterY="0"><ShowRulers>1</ShowRulers><ShowGrid>1</ShowGrid><ShowPageBreaks>0</ShowPageBreaks><ShowGuides>1</ShowGuides><ShowConnectionPoints>1</ShowConnectionPoints><GlueSettings>9</GlueSettings><SnapSettings>295</SnapSettings><SnapExtensions>34</SnapExtensions><DynamicGridEnabled>0</DynamicGridEnabled><TabSplitterPos>0.5</TabSplitterPos></Window></Windows>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("docProps/core.xml", core_xml)
        z.writestr("docProps/app.xml", app_xml)
        z.writestr("visio/document.xml", doc_xml)
        z.writestr("visio/_rels/document.xml.rels", doc_rels)
        z.writestr("visio/masters/masters.xml", masters_xml)
        z.writestr("visio/masters/_rels/masters.xml.rels", masters_rels)
        z.writestr("visio/pages/pages.xml", pages_xml)
        z.writestr("visio/pages/_rels/pages.xml.rels", pages_rels)
        z.writestr("visio/windows.xml", windows_xml)
        for i in range(n):
            page_xml = _XML_DECL + f'<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve"><Shapes>{page_shapes[i]}</Shapes><Connects></Connects><Layers><Layer IX="0" Name="Connector" Color="#333333" Active="1" Visible="1"/></Layers></PageContents>'
            z.writestr(f"visio/pages/page{i+1}.xml", page_xml)
            if page_rels[i]:
                z.writestr(f"visio/pages/_rels/page{i+1}.xml.rels", _XML_DECL + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{"".join(page_rels[i])}</Relationships>')
        for name, data in all_media: z.writestr(name, data)
    return buf.getvalue()


def render_docx(scenes: list[Scene]) -> bytes:
    from docx import Document; from docx.shared import Inches; from docx.enum.section import WD_ORIENT
    doc = Document(); sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width = Inches(11); sec.page_height = Inches(8.5)
    sec.left_margin = sec.right_margin = Inches(0.2); sec.top_margin = sec.bottom_margin = Inches(0.2)
    for i, scene in enumerate(scenes):
        img = _render_png_image(scene, scale=2)
        buf = io.BytesIO(); img.save(buf, format="PNG")
        doc.add_picture(io.BytesIO(buf.getvalue()), width=Inches(10.6))
        if i < len(scenes) - 1:
            doc.add_page_break()
    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()


def _partition(nodes: list[dict], links: list[dict], max_per_page: int = 20) -> list[tuple[list[dict], list[dict]]]:
    """Split a large topology into pages, keeping connected devices together.

    Mirrors the reference: about ~18 devices per sheet. Large connected
    components are split by /24 subnet so each sheet is a coherent zone.
    """
    if len(nodes) <= max_per_page:
        return [(nodes, links)]
    node_by_ip = {n["ip"]: n for n in nodes}
    ipset = set(node_by_ip)
    adj = {ip: [] for ip in ipset}
    for l in links:
        a, b = l.get("source"), l.get("target")
        if a in ipset and b in ipset and a != b:
            adj[a].append(b); adj[b].append(a)
    visited = set(); comps = []
    for ip in ipset:
        if ip in visited: continue
        comp = []; st = [ip]; visited.add(ip)
        while st:
            u = st.pop(); comp.append(u)
            for v in adj[u]:
                if v not in visited:
                    visited.add(v); st.append(v)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    units = []
    for comp in comps:
        if len(comp) <= max_per_page:
            units.append(comp)
        else:
            sub = {}
            for ip in comp:
                pfx = _subnet24(ip) or "other"
                sub.setdefault(pfx, []).append(ip)
            for pfx in sorted(sub, key=lambda p: -len(sub[p])):
                units.append(sub[pfx])
    pages = []
    cur = []
    for u in units:
        if cur and len(cur) + len(u) > max_per_page:
            pages.append(cur); cur = list(u)
        else:
            cur.extend(u)
    if cur: pages.append(cur)
    result = []
    for page_ips in pages:
        pset = set(page_ips)
        pnodes = [node_by_ip[ip] for ip in page_ips]
        plinks = [l for l in links if l.get("source") in pset and l.get("target") in pset]
        result.append((pnodes, plinks))
    return result


def export_diagram(nodes: list[dict], links: list[dict], fmt: str, opts: dict) -> bytes:
    # Split access points / end-user devices onto their own sheet so the main
    # pages stay a clean top-down tier (internet -> router -> core -> dist -> access).
    include_aps = not opts.get("exclude_endpoints", False)
    infra = [n for n in nodes if _layer_of(n) != "endpoint"]
    aps = [n for n in nodes if _layer_of(n) == "endpoint"] if include_aps else []
    infra_ips = {n["ip"] for n in infra}
    infra_links = [l for l in links if l.get("source") in infra_ips and l.get("target") in infra_ips]
    partitions = _partition(infra, infra_links)
    # Put the page containing the top of the hierarchy (router / SD-WAN /
    # internet) first so the drawing starts at the edge device.
    def _top_score(part):
        pn, _ = part
        return 0 if any(_layer_of(n) in ("internet", "velocloud", "router") for n in pn) else 1
    partitions.sort(key=_top_score)
    total = len(partitions) + (1 if aps else 0)
    scenes = []
    for i, (pn, pl) in enumerate(partitions):
        o = dict(opts)
        o["title_block"] = (i == total - 1)  # title block only on the last sheet
        scenes.append(build_scene(pn, pl, o))
    if aps:
        o = dict(opts)
        o["title_block"] = True
        scenes.append(_build_ap_scene(aps, o))
    if fmt == "pdf": return render_pdf(scenes)
    if fmt == "png": return render_png(scenes)
    if fmt == "vsdx": return render_vsdx(scenes)
    if fmt == "docx": return render_docx(scenes)
    raise ValueError(f"unsupported format: {fmt}")
