"""Engineering-style topology diagram export.

Builds a drawing-sheet scene from topology nodes/links in the style of the
Amtrak station reference drawings (white sheet, black frame, Amtrak logo
top-left, centered site title, hierarchical layers, orthogonal links with
port labels, medium color-coding, and a legend/title block at the bottom),
then renders it to PDF, PNG, Visio (.vsdx) or Word (.docx).

Scene units are points (1/72"), origin top-left, y grows downward.
"""

from __future__ import annotations

import io
import os
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
SLOT_W = 230              # horizontal slot per device
MAX_PER_ROW = 6           # rows wrap downward past this (uniform vertical flow)
LEGEND_H = 110

C_FRAME = "#000000"
C_TEXT = "#000000"
C_CORE = "#C00000"        # role label red
C_PORT = "#444444"        # port labels
C_LINK = "#333333"        # default link
C_GLYPH = "#2F3542"       # switch faceplate
C_GLYPH_EDGE = "#111318"
C_GLYPH_TICK = "#9AA3B2"
C_UNKNOWN = "#F2F2F2"

AMTRAK_BLUE = "#003A70"
PROPRIETARY = "AMTRAK - Proprietary\nUse Pursuant to Company\nInstructions"

DEFAULT_LEGEND = [
    {"key": "mmf", "label": "Multi-mode Fiber", "color": "#F58220"},
    {"key": "copper", "label": "Copper", "color": "#8BC34A"},
    {"key": "smf", "label": "Single-mode Fiber", "color": "#E6D200"},
]

ASSET_LOGO = os.path.join(os.path.dirname(__file__), "assets", "amtrak-logo.png")

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
    for pfx, abbr in _IFACE_SHORT:
        if name.startswith(pfx):
            return abbr + name[len(pfx):]
    return name


def _medium_key(interface_a: str, interface_b: str) -> str:
    """Guess the physical medium from interface names (10G+ => single-mode)."""
    name = (interface_a or interface_b or "").strip().upper()
    for pfx in ("TWE", "TE", "FO", "HU", "25G", "100G"):
        if name.startswith(pfx):
            return "smf"
    for pfx in ("GI", "FA", "ETH", "ET"):
        if name.startswith(pfx):
            return "copper"
    return ""


# --------------------------------------------------------------------------
# Scene model
# --------------------------------------------------------------------------

class Scene:
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height
        self.prims: list[dict] = []
        # Structured model used by the Visio renderer for editable output:
        # each device becomes one draggable group shape; each link a glued
        # connector that follows the devices when they are dragged.
        self.devices: list[dict] = []
        self.vlinks: list[dict] = []

    def rect(self, x, y, w, h, fill=None, stroke=C_FRAME, sw=1.0, tag=None):
        self.prims.append({"k": "rect", "x": x, "y": y, "w": w, "h": h,
                           "fill": fill, "stroke": stroke, "sw": sw, "tag": tag})

    def ellipse(self, cx, cy, rx, ry, fill=None, stroke=C_FRAME, sw=1.0, tag=None):
        self.prims.append({"k": "ellipse", "cx": cx, "cy": cy, "rx": rx, "ry": ry,
                           "fill": fill, "stroke": stroke, "sw": sw, "tag": tag})

    def line(self, pts, color=C_LINK, width=1.2, tag=None):
        self.prims.append({"k": "line", "pts": pts, "color": color,
                           "width": width, "tag": tag})

    def text(self, x, y, value, size=10, bold=False, italic=False,
             color=C_TEXT, align="center", tag=None):
        if value:
            self.prims.append({"k": "text", "x": x, "y": y, "v": str(value),
                               "size": size, "bold": bold, "italic": italic,
                               "color": color, "align": align, "tag": tag})

    def image(self, x, y, w, h, path, tag=None):
        self.prims.append({"k": "image", "x": x, "y": y, "w": w, "h": h,
                           "path": path, "tag": tag})


# --------------------------------------------------------------------------
# Layout engine
# --------------------------------------------------------------------------

def _rank_of(node: dict, core_ips: set[str]) -> int:
    dt = (node.get("device_type") or "").lower()
    if "router" in dt:
        return 0
    if "switch" in dt and node.get("ip") in core_ips:
        return 1
    if "switch" in dt:
        return 2
    return 3


def _find_cores(nodes: list[dict], links: list[dict]) -> set[str]:
    """Core switches: those adjacent to a router; if none, the two most
    connected switches (mirrors how station drawings mark CORE1/CORE2)."""
    router_ips = {n["ip"] for n in nodes if "router" in (n.get("device_type") or "").lower()}
    switch_ips = {n["ip"] for n in nodes if "switch" in (n.get("device_type") or "").lower()}
    deg: dict[str, int] = {}
    adj: set[str] = set()
    for l in links:
        a, b = l.get("source"), l.get("target")
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
        if a in router_ips and b in switch_ips:
            adj.add(b)
        if b in router_ips and a in switch_ips:
            adj.add(a)
    if adj:
        return adj
    ranked = sorted((ip for ip in switch_ips if deg.get(ip, 0) >= 2),
                    key=lambda ip: -deg[ip])
    return set(ranked[:2])


DEFAULT_OPTS = {
    "title": "AMTRAK NETWORK DIAGRAM",
    "drawn_by": "",
    "drawn_date": "",
    "drawing_title": "",
    "document_name": "",
    "revision": "",
    "rev_date": "",
    "rev_time": "",
    "color_links": True,
    "legend": DEFAULT_LEGEND,
}


def build_scene(nodes: list[dict], links: list[dict], opts: dict) -> Scene:
    title = (opts.get("title") or "AMTRAK NETWORK DIAGRAM").upper()
    legend = opts.get("legend") or DEFAULT_LEGEND
    color_links = opts.get("color_links", True)
    legend_color = {e.get("key"): e.get("color") for e in legend if e.get("key")}

    # --- layer assignment -------------------------------------------------
    core_ips = _find_cores(nodes, links)
    core_num: dict[str, int] = {}

    def rank(n):
        return _rank_of(n, core_ips)

    layers: dict[int, list[dict]] = {}
    for n in nodes:
        layers.setdefault(rank(n), []).append(n)
    order = sorted(layers)
    for r in order:
        layers[r].sort(key=lambda n: (n.get("hostname") or n.get("ip") or ""))
    for i, n in enumerate(layers.get(1, [])):
        core_num[n["ip"]] = i + 1

    # Rows wrap downward: each rank occupies ceil(count / MAX_PER_ROW) rows
    # so wide layers flow down the sheet instead of sprawling sideways.
    rows_per_rank = {r: max(1, -(-len(layers[r]) // MAX_PER_ROW)) for r in order}
    total_rows = sum(rows_per_rank.values())
    widest = min(max((len(v) for v in layers.values()), default=1), MAX_PER_ROW)
    width = max(1150, MARGIN * 2 + widest * SLOT_W)
    content_top = MARGIN + HEADER_H
    legend_y = content_top + total_rows * LAYER_GAP + 60
    height = legend_y + LEGEND_H + MARGIN

    scene = Scene(width, height)

    # --- frame, header ----------------------------------------------------
    scene.rect(MARGIN / 2, MARGIN / 2, width - MARGIN, height - MARGIN, sw=1.5)
    logo_w = 170.0
    logo_h = logo_w * 394.0 / 700.0     # asset aspect
    if os.path.exists(ASSET_LOGO):
        scene.image(MARGIN + 6, MARGIN / 2 + 8, logo_w, logo_h, ASSET_LOGO)
    scene.text(width / 2, MARGIN + 26, title, size=26, bold=False)

    # --- node positions ---------------------------------------------------
    rank_y: dict[int, float] = {}
    y_cursor = content_top + 70
    for r in order:
        rank_y[r] = y_cursor
        y_cursor += rows_per_rank[r] * LAYER_GAP

    pos: dict[str, tuple[float, float]] = {}   # ip -> glyph center (cx, cy)

    def assign(group: list[dict], base_y: float):
        for i, n in enumerate(group):
            row, col = divmod(i, MAX_PER_ROW)
            row_count = min(MAX_PER_ROW, len(group) - row * MAX_PER_ROW)
            x0 = (width - row_count * SLOT_W) / 2 + SLOT_W / 2
            pos[n["ip"]] = (x0 + col * SLOT_W, base_y + row * LAYER_GAP)

    for r in order:
        assign(layers[r], rank_y[r])

    # Barycenter sweeps to reduce crossings.
    rank_by_ip = {n["ip"]: rank(n) for n in nodes}
    neigh: dict[str, list[str]] = {}
    for l in links:
        a, b = l.get("source"), l.get("target")
        if a in pos and b in pos:
            neigh.setdefault(a, []).append(b)
            neigh.setdefault(b, []).append(a)
    for _ in range(3):
        for r in order[1:]:
            def key(n, r=r):
                xs = [pos[m][0] for m in neigh.get(n["ip"], [])
                      if rank_by_ip.get(m, r) < r and m in pos]
                return sum(xs) / len(xs) if xs else pos[n["ip"]][0]
            layers[r].sort(key=key)
            assign(layers[r], rank_y[r])

    # --- links (orthogonal elbows, port labels, medium colors) ------------
    dt_by_ip = {n["ip"]: (n.get("device_type") or "").lower() for n in nodes}

    def half_h(ip: str) -> float:
        dt = dt_by_ip.get(ip, "")
        if "router" in dt:
            return CLOUD_H / 2
        if dt == "unknown":
            return UNKNOWN_H / 2
        return GLYPH_H / 2

    # Deduplicate identical links first so attachment fan-out counts matches.
    valid: list[dict] = []
    seen: set[tuple] = set()
    for l in links:
        a, b = l.get("source"), l.get("target")
        if a not in pos or b not in pos or a == b:
            continue
        k = (a, b, l.get("source_interface"), l.get("target_interface"))
        if k in seen:
            continue
        seen.add(k)
        valid.append(l)

    # Assign each link a spread-out attachment point on each device edge so
    # lines leaving a core or switch don't stack on top of each other.
    attach: dict[str, dict[str, list[int]]] = {}  # ip -> "top"|"bottom" -> link idx
    for li, l in enumerate(valid):
        a, b = l["source"], l["target"]
        same = abs(pos[a][1] - pos[b][1]) < 1
        if same:
            attach.setdefault(a, {}).setdefault("top", []).append(li)
            attach.setdefault(b, {}).setdefault("top", []).append(li)
        else:
            upper, lower = (a, b) if pos[a][1] < pos[b][1] else (b, a)
            attach.setdefault(upper, {}).setdefault("bottom", []).append(li)
            attach.setdefault(lower, {}).setdefault("top", []).append(li)

    def attach_x(ip: str, side: str, li: int) -> float:
        group = attach.get(ip, {}).get(side, [])
        n = len(group)
        cx, _ = pos[ip]
        if n <= 1:
            return cx
        hw = (CLOUD_W / 2 if "router" in dt_by_ip.get(ip, "") else GLYPH_W / 2) - 12
        idx = group.index(li)
        step = min(14.0, 2 * hw / (n - 1))
        return cx - hw + idx * step

    pair_count: dict[tuple, int] = {}
    for li, l in enumerate(valid):
        a, b = l["source"], l["target"]
        x1, y1 = pos[a]
        x2, y2 = pos[b]
        h1, h2 = half_h(a), half_h(b)
        med = _medium_key(l.get("source_interface", ""), l.get("target_interface", ""))
        color = C_LINK
        if color_links and med and legend_color.get(med):
            color = legend_color[med]

        ia, ib = l.get("source_interface") or "", l.get("target_interface") or ""
        ia_s, ib_s = _shorten_interface(ia), _shorten_interface(ib)

        same_layer = abs(y1 - y2) < 1
        pair = tuple(sorted((a, b)))
        dup = pair_count.get(pair, 0)
        pair_count[pair] = dup + 1
        off = dup * 10
        scene.vlinks.append({"a": a, "b": b, "color": color, "width": 1.4,
                             "src_if": ia_s, "dst_if": ib_s,
                             "ax": pos[a][0], "ay": pos[a][1],
                             "bx": pos[b][0], "by": pos[b][1]})
        if same_layer:
            # channel runs above the whole label stack (stack ≈ 46pt tall)
            sax = attach_x(a, "top", li)
            tax = attach_x(b, "top", li)
            top = min(y1 - h1, y2 - h2) - 58 - off
            pts = [(sax, y1 - h1), (sax, top), (tax, top), (tax, y2 - h2)]
            scene.line(pts, color=color, width=1.4, tag="link")
            scene.text(sax + 4, y1 - h1 - 10, ia_s, size=7, color=C_PORT, align="left", tag="link")
            scene.text(tax + 4, y2 - h2 - 10, ib_s, size=7, color=C_PORT, align="left", tag="link")
        else:
            if y1 > y2:
                x1, y1, x2, y2 = x2, y2, x1, y1
                h1, h2 = h2, h1
                a, b = b, a
                ia_s, ib_s = ib_s, ia_s
            sax = attach_x(a, "bottom", li)
            tax = attach_x(b, "top", li)
            # horizontal channel rides in the empty gap just above the target
            # device's row, so long runs never cross an intermediate glyph row
            mid = (y2 - h2) - 58 - off
            pts = [(sax, y1 + h1), (sax, mid), (tax, mid), (tax, y2 - h2)]
            scene.line(pts, color=color, width=1.4, tag="link")
            scene.text(sax + 4, y1 + h1 + 2, ia_s, size=7, color=C_PORT, align="left", tag="link")
            scene.text(tax + 4, y2 - h2 - 10, ib_s, size=7, color=C_PORT, align="left", tag="link")

    # --- node glyphs + label stacks ---------------------------------------
    for r in order:
        for n in layers[r]:
            cx, cy = pos[n["ip"]]
            hn = (n.get("hostname") or "").split(".")[0] or n.get("ip") or ""
            model = n.get("model") or ""
            ip = n.get("ip") or ""
            dt = (n.get("device_type") or "").lower()
            tag = ("dev", ip)

            if "router" in dt:
                scene.ellipse(cx, cy, CLOUD_W / 2, CLOUD_H / 2, fill="#FFFFFF", sw=1.2, tag=tag)
                scene.text(cx, cy - 20, hn, size=8, bold=True, tag=tag)
                scene.text(cx, cy - 9, model, size=7.5, tag=tag)
                scene.text(cx, cy + 2, ip, size=7.5, tag=tag)
                scene.devices.append({
                    "ip": ip, "cx": cx, "cy": cy, "kind": "cloud",
                    "labels": [(hn, 8, True, C_TEXT), (model, 7.5, False, C_TEXT),
                               (ip, 7.5, False, C_TEXT)],
                })
            elif dt == "unknown" and not model and not hn:
                scene.rect(cx - UNKNOWN_W / 2, cy - UNKNOWN_H / 2, UNKNOWN_W, UNKNOWN_H,
                           fill=C_UNKNOWN, stroke=C_GLYPH_TICK, sw=0.75, tag=tag)
                scene.text(cx, cy - 5, ip, size=8, tag=tag)
                scene.devices.append({
                    "ip": ip, "cx": cx, "cy": cy, "kind": "unknown",
                    "labels": [(ip, 8, False, C_TEXT)],
                })
            else:
                # label stack above the faceplate
                labels: list[tuple] = []
                ly = cy - GLYPH_H / 2 - 12
                if ip:
                    scene.text(cx, ly - 10, ip, size=8.5, tag=tag)
                    labels.append((ip, 8.5, False, C_TEXT)); ly -= 10
                if model:
                    scene.text(cx, ly - 10, model, size=8.5, tag=tag)
                    labels.append((model, 8.5, False, C_TEXT)); ly -= 10
                scene.text(cx, ly - 11, hn, size=9.5, bold=True, tag=tag)
                labels.append((hn, 9.5, True, C_TEXT)); ly -= 11
                if n["ip"] in core_num:
                    core_label = f"CORE{core_num[n['ip']]}"
                    scene.text(cx, ly - 11, core_label, size=10, bold=True,
                               color=C_CORE, tag=tag)
                    labels.append((core_label, 10, True, C_CORE))
                labels.reverse()   # top-to-bottom order
                # switch faceplate
                gx, gy = cx - GLYPH_W / 2, cy - GLYPH_H / 2
                scene.rect(gx, gy, GLYPH_W, GLYPH_H, fill=C_GLYPH, stroke=C_GLYPH_EDGE,
                           sw=1.0, tag=tag)
                for t in range(12):
                    tx = gx + 8 + t * (GLYPH_W - 16) / 12
                    scene.rect(tx, gy + 6, 6, 4, fill=C_GLYPH_TICK, stroke=None, sw=0, tag=tag)
                    scene.rect(tx, gy + 15, 6, 4, fill=C_GLYPH_TICK, stroke=None, sw=0, tag=tag)
                scene.devices.append({
                    "ip": ip, "cx": cx, "cy": cy, "kind": "switch",
                    "labels": labels,
                })

    # --- legend / title block ----------------------------------------------
    bx, bw = MARGIN / 2, width - MARGIN
    by = legend_y
    scene.rect(bx, by, bw, LEGEND_H, sw=1.2)
    c1 = bx + 210
    c2 = c1 + 300
    scene.line([(c1, by), (c1, by + LEGEND_H)], color=C_FRAME, width=1.0)
    scene.line([(c2, by), (c2, by + LEGEND_H)], color=C_FRAME, width=1.0)

    # legend swatches
    scene.text(bx + 10, by + 8, "LEGEND", size=9, bold=True, align="left")
    ey = by + 28
    for e in legend:
        scene.line([(bx + 12, ey + 4), (bx + 60, ey + 4)], color=e.get("color") or C_LINK, width=2.2)
        scene.text(bx + 66, ey, e.get("label") or "", size=8.5, align="left")
        ey += 16

    # logo + proprietary notice
    lw = 120.0
    lh = lw * 394.0 / 700.0
    if os.path.exists(ASSET_LOGO):
        scene.image(c1 + 10, by + 10, lw, lh, ASSET_LOGO)
    for i, ln in enumerate(PROPRIETARY.split("\n")):
        scene.text(c1 + 145, by + 22 + i * 13, ln, size=9, bold=True, italic=True, align="left")

    # title-block rows
    rows = [
        [("Drawn By: ", opts.get("drawn_by") or ""), ("Drawn Date: ", opts.get("drawn_date") or "")],
        [("Drawing Title: ", opts.get("drawing_title") or title)],
        [("Document Name: ", opts.get("document_name") or "")],
        [("Revision: ", opts.get("revision") or ""),
         ("Rev. Date: ", opts.get("rev_date") or ""),
         ("Rev. Time: ", opts.get("rev_time") or "")],
    ]
    rh = LEGEND_H / 4
    for i, row in enumerate(rows):
        ry = by + i * rh
        if i:
            scene.line([(c2, ry), (bx + bw, ry)], color=C_FRAME, width=1.0)
        cw = (bx + bw - c2) / len(row)
        for j, (label, val) in enumerate(row):
            if j:
                scene.line([(c2 + j * cw, ry), (c2 + j * cw, ry + rh)], color=C_FRAME, width=1.0)
            scene.text(c2 + j * cw + 6, ry + rh / 2 - 4, label + val, size=9, align="left")

    return scene


# --------------------------------------------------------------------------
# PDF renderer (reportlab)
# --------------------------------------------------------------------------

def render_pdf(scene: Scene) -> bytes:
    from reportlab.pdfgen import canvas as _canvas
    from reportlab.lib.utils import ImageReader

    # PDF viewers cap page size at 200" — scale oversized sheets down to fit.
    limit = 200 * 72
    factor = min(1.0, limit / scene.width, limit / scene.height)

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=(scene.width * factor, scene.height * factor))
    if factor < 1.0:
        c.scale(factor, factor)
    H = scene.height

    def fy(y):  # flip y
        return H - y

    for p in scene.prims:
        k = p["k"]
        if k == "rect":
            if p.get("fill"):
                c.setFillColor(p["fill"])
            if p.get("stroke"):
                c.setStrokeColor(p["stroke"]); c.setLineWidth(p["sw"])
            c.rect(p["x"], fy(p["y"] + p["h"]), p["w"], p["h"],
                   fill=1 if p.get("fill") else 0, stroke=1 if p.get("stroke") else 0)
        elif k == "ellipse":
            if p.get("fill"):
                c.setFillColor(p["fill"])
            if p.get("stroke"):
                c.setStrokeColor(p["stroke"]); c.setLineWidth(p["sw"])
            c.ellipse(p["cx"] - p["rx"], fy(p["cy"] + p["ry"]),
                      p["cx"] + p["rx"], fy(p["cy"] - p["ry"]),
                      fill=1 if p.get("fill") else 0, stroke=1 if p.get("stroke") else 0)
        elif k == "line":
            c.setStrokeColor(p["color"]); c.setLineWidth(p["width"])
            path = c.beginPath()
            path.moveTo(p["pts"][0][0], fy(p["pts"][0][1]))
            for x, y in p["pts"][1:]:
                path.lineTo(x, fy(y))
            c.drawPath(path, fill=0, stroke=1)
        elif k == "text":
            font = "Helvetica-Bold" if p["bold"] else ("Helvetica-Oblique" if p["italic"] else "Helvetica")
            c.setFont(font, p["size"])
            c.setFillColor(p["color"])
            if p["align"] == "left":
                c.drawString(p["x"], fy(p["y"] + p["size"]), p["v"])
            elif p["align"] == "right":
                c.drawRightString(p["x"], fy(p["y"] + p["size"]), p["v"])
            else:
                c.drawCentredString(p["x"], fy(p["y"] + p["size"]), p["v"])
        elif k == "image":
            c.drawImage(ImageReader(p["path"]), p["x"], fy(p["y"] + p["h"]),
                        width=p["w"], height=p["h"], mask="auto")
    c.showPage()
    c.save()
    return buf.getvalue()


# --------------------------------------------------------------------------
# PNG renderer (Pillow) — used for the Word document
# --------------------------------------------------------------------------

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


def _hex(color: str):
    color = (color or "#000000").lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def render_png(scene: Scene, scale: int = 2) -> bytes:
    from PIL import Image, ImageDraw

    W, H = int(scene.width * scale), int(scene.height * scale)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    def s(v):
        return v * scale

    for p in scene.prims:
        k = p["k"]
        if k == "rect":
            d.rectangle([s(p["x"]), s(p["y"]), s(p["x"] + p["w"]), s(p["y"] + p["h"])],
                        fill=_hex(p["fill"]) if p.get("fill") else None,
                        outline=_hex(p["stroke"]) if p.get("stroke") else None,
                        width=max(1, int(s(p["sw"]))))
        elif k == "ellipse":
            d.ellipse([s(p["cx"] - p["rx"]), s(p["cy"] - p["ry"]),
                       s(p["cx"] + p["rx"]), s(p["cy"] + p["ry"])],
                      fill=_hex(p["fill"]) if p.get("fill") else None,
                      outline=_hex(p["stroke"]) if p.get("stroke") else None,
                      width=max(1, int(s(p["sw"]))))
        elif k == "line":
            d.line([(s(x), s(y)) for x, y in p["pts"]],
                   fill=_hex(p["color"]), width=max(1, int(s(p["width"]))))
        elif k == "text":
            f = _pil_font(int(s(p["size"])), p["bold"], p["italic"])
            x, y = s(p["x"]), s(p["y"])
            if p["align"] != "left":
                w = d.textlength(p["v"], font=f)
                x -= w / 2 if p["align"] == "center" else w
            d.text((x, y), p["v"], font=f, fill=_hex(p["color"]))
        elif k == "image":
            try:
                logo = Image.open(p["path"]).convert("RGBA")
                logo = logo.resize((int(s(p["w"])), int(s(p["h"]))))
                img.paste(logo, (int(s(p["x"])), int(s(p["y"]))), logo)
            except Exception:
                pass
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------
# Visio (.vsdx) renderer — minimal Open Packaging Convention package
#
# Visio 2013+ XML shape geometry uses <Section N="Geometry"><Row T="MoveTo">
# elements (not the legacy VDX <Geom>/<MoveTo> form). Each device is emitted
# as a group shape so the glyph + label stack drags as one unit, and links
# are glued 1-D connectors that follow the devices when they are moved.
# --------------------------------------------------------------------------

def _geom_rect(w: float, h: float) -> str:
    return (
        '<Section N="Geometry" IX="0">'
        '<Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>'
        f'<Row T="LineTo" IX="2"><Cell N="X" V="{w:.4f}"/><Cell N="Y" V="0"/></Row>'
        f'<Row T="LineTo" IX="3"><Cell N="X" V="{w:.4f}"/><Cell N="Y" V="{h:.4f}"/></Row>'
        f'<Row T="LineTo" IX="4"><Cell N="X" V="0"/><Cell N="Y" V="{h:.4f}"/></Row>'
        f'<Row T="LineTo" IX="5"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>'
        '</Section>'
    )


def _geom_ellipse(w: float, h: float) -> str:
    return (
        '<Section N="Geometry" IX="0">'
        f'<Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="{h / 2:.4f}"/></Row>'
        f'<Row T="Ellipse" IX="2"><Cell N="X" V="{w / 2:.4f}"/><Cell N="Y" V="{h / 2:.4f}"/>'
        f'<Cell N="A" V="{w:.4f}"/><Cell N="B" V="{h / 2:.4f}"/></Row>'
        '</Section>'
    )


def _connector_1d(sid: int, bx: float, by: float, ex: float, ey: float,
                  color: str, width_pt: float) -> str:
    """Straight 1-D connector. For 1-D shapes the transform lives in the
    BeginX/BeginY/EndX/EndY cells and Width is the connector length; the
    geometry's local X axis runs from Begin toward End."""
    dist = max(((ex - bx) ** 2 + (ey - by) ** 2) ** 0.5, 0.0001)
    return (
        f'<Shape ID="{sid}" Type="Shape">'
        f'<Cell N="BeginX" V="{bx:.4f}"/><Cell N="BeginY" V="{by:.4f}"/>'
        f'<Cell N="EndX" V="{ex:.4f}"/><Cell N="EndY" V="{ey:.4f}"/>'
        f'<Cell N="Width" V="{dist:.4f}"/>'
        f'<Cell N="LineColor" V="{color}"/>'
        f'<Cell N="LineWeight" V="{width_pt / 72:.4f}"/>'
        '<Cell N="FillPattern" V="0"/><Cell N="OneD" V="1"/>'
        '<Section N="Geometry" IX="0">'
        '<Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>'
        f'<Row T="LineTo" IX="2"><Cell N="X" V="{dist:.4f}" F="Width"/><Cell N="Y" V="0"/></Row>'
        '</Section></Shape>'
    )


def _xform(pinx: float, piny: float, w: float, h: float) -> str:
    return (f'<Cell N="PinX" V="{pinx:.4f}"/><Cell N="PinY" V="{piny:.4f}"/>'
            f'<Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/>'
            f'<Cell N="LocPinX" V="{w / 2:.4f}"/><Cell N="LocPinY" V="{h / 2:.4f}"/>')


def _fill_line(fill: str | None, stroke: str | None, sw: float) -> str:
    out = []
    if fill:
        out.append(f'<Cell N="FillForegnd" V="{fill}"/><Cell N="FillPattern" V="1"/>')
    else:
        out.append('<Cell N="FillPattern" V="0"/>')
    if stroke:
        out.append(f'<Cell N="LineColor" V="{stroke}"/><Cell N="LineWeight" V="{sw / 72:.4f}"/>')
    else:
        out.append('<Cell N="LinePattern" V="0"/>')
    return "".join(out)


def _char_para(p: dict) -> str:
    size_pt = p["size"]
    style = "0"
    if p.get("bold") and p.get("italic"):
        style = "3"
    elif p.get("bold"):
        style = "1"
    elif p.get("italic"):
        style = "2"
    halign = {"left": "0", "center": "1", "right": "2"}.get(p.get("align", "center"), "1")
    return (f'<Section N="Character"><Row IX="0"><Cell N="Color" V="{p["color"]}"/>'
            f'<Cell N="Size" V="{size_pt / 72:.4f}"/><Cell N="Style" V="{style}"/></Row></Section>'
            f'<Section N="Paragraph"><Row IX="0"><Cell N="HorzAlign" V="{halign}"/></Row></Section>')


def _vsdx_text(sid: int, p: dict, H: float, ox: float = 0.0, oy: float = 0.0) -> str:
    """Text shape. ox/oy shift the local origin (used inside groups)."""
    size_pt = p["size"]
    w_in = max(0.3, len(p["v"]) * size_pt * 0.62 / 72)
    h_in = size_pt * 1.4 / 72
    pinx = (p["x"] - ox) / 72
    piny = (H - p["y"] - oy) / 72 - h_in / 2
    return (f'<Shape ID="{sid}" Type="Shape">'
            + _xform(pinx, piny, w_in, h_in)
            + '<Cell N="FillPattern" V="0"/><Cell N="LinePattern" V="0"/>'
            + '<Cell N="VerticalAlign" V="1"/>'
            + _char_para(p)
            + _geom_rect(w_in, h_in)
            + f'<Text>{_xml_escape(p["v"])}</Text></Shape>')


def render_vsdx(scene: Scene) -> bytes:
    """Hand-rolled .vsdx: grouped device shapes + glued connectors."""
    H = scene.height
    shapes: list[str] = []
    connects: list[str] = []
    rels: list[str] = []
    media: list[tuple[str, bytes]] = []
    sid = 1

    def flip_y(y_pt: float) -> float:
        return (H - y_pt) / 72

    # --- static chrome (frame, legend, title block) from untagged prims ----
    for p in scene.prims:
        if p.get("tag"):
            continue
        k = p["k"]
        if k == "rect":
            w, h = p["w"] / 72, p["h"] / 72
            shapes.append(f'<Shape ID="{sid}" Type="Shape">'
                          + _xform((p["x"] + p["w"] / 2) / 72, flip_y(p["y"] + p["h"] / 2), w, h)
                          + _fill_line(p.get("fill"), p.get("stroke"), p["sw"])
                          + _geom_rect(w, h) + '</Shape>')
            sid += 1
        elif k == "line":
            pts = p["pts"]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                shapes.append(_connector_1d(sid, x1 / 72, flip_y(y1),
                                            x2 / 72, flip_y(y2),
                                            p["color"], p["width"]))
                sid += 1
        elif k == "text":
            shapes.append(_vsdx_text(sid, p, H))
            sid += 1
        elif k == "image":
            try:
                with open(p["path"], "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            rid = f"rId{len(media) + 1}"
            media.append((f"media/image{len(media) + 1}.png", data))
            rels.append(f'<Relationship Id="{rid}" '
                        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                        f'Target="../media/image{len(media)}.png"/>')
            w, h = p["w"] / 72, p["h"] / 72
            shapes.append(
                f'<Shape ID="{sid}" Type="Foreign">'
                + _xform((p["x"] + p["w"] / 2) / 72, flip_y(p["y"] + p["h"] / 2), w, h)
                + '<Cell N="FillPattern" V="0"/><Cell N="LinePattern" V="0"/>'
                + f'<ForeignData ForeignType="Bitmap" MappingMode="96" '
                + f'ExtentX="{int(p["w"] * 2540)}" ExtentY="{int(p["h"] * 2540)}">'
                + f'<Rel xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="{rid}"/>'
                + '</ForeignData></Shape>')
            sid += 1

    # --- devices: one draggable group per device ---------------------------
    dev_shape_id: dict[str, int] = {}
    for dev in scene.devices:
        kind = dev["kind"]
        cx, cy = dev["cx"], dev["cy"]
        labels = dev.get("labels", [])
        # bounding box of the group in scene coords (y-down)
        if kind == "cloud":
            bw, bh = CLOUD_W, CLOUD_H
        elif kind == "unknown":
            bw, bh = UNKNOWN_W, UNKNOWN_H
        else:
            label_w = max((len(t) * s * 0.62 for t, s, _, _ in labels), default=0)
            stack_h = sum(s * 1.25 for _, s, _, _ in labels) + 12
            bw = max(GLYPH_W, label_w)
            bh = GLYPH_H + stack_h
        gx0 = cx - bw / 2            # group box top-left in scene coords
        if kind == "switch":
            gy0 = (cy + GLYPH_H / 2) - bh   # glyph bottom is the box bottom
        else:
            gy0 = cy - bh / 2
        gw, gh = bw / 72, bh / 72
        group_pin_x = (gx0 + bw / 2) / 72
        group_pin_y = flip_y(gy0 + bh / 2)
        gid = sid
        sid += 1
        dev_shape_id[dev["ip"]] = gid

        children: list[str] = []

        def to_local(x_pt: float, y_pt: float) -> tuple[float, float]:
            # scene coords (y-down, pt) -> group-local (y-up, inches)
            return (x_pt - gx0) / 72, (gy0 + bh - y_pt) / 72

        if kind == "cloud":
            w_in, h_in = CLOUD_W / 72, CLOUD_H / 72
            cx_l, cy_l = to_local(cx, cy)
            children.append(f'<Shape ID="{sid}" Type="Shape">'
                            + _xform(cx_l, cy_l, w_in, h_in)
                            + _fill_line("#FFFFFF", "#000000", 1.2)
                            + _geom_ellipse(w_in, h_in) + '</Shape>')
            sid += 1
        elif kind == "unknown":
            w_in, h_in = UNKNOWN_W / 72, UNKNOWN_H / 72
            cx_l, cy_l = to_local(cx, cy)
            children.append(f'<Shape ID="{sid}" Type="Shape">'
                            + _xform(cx_l, cy_l, w_in, h_in)
                            + _fill_line(C_UNKNOWN, C_GLYPH_TICK, 0.75)
                            + _geom_rect(w_in, h_in) + '</Shape>')
            sid += 1
        else:
            w_in, h_in = GLYPH_W / 72, GLYPH_H / 72
            cx_l, cy_l = to_local(cx, cy)
            children.append(f'<Shape ID="{sid}" Type="Shape">'
                            + _xform(cx_l, cy_l, w_in, h_in)
                            + _fill_line(C_GLYPH, C_GLYPH_EDGE, 1.0)
                            + _geom_rect(w_in, h_in) + '</Shape>')
            sid += 1

        # Label texts for this device (from the tagged prims), in group-local
        # coordinates.
        dev_texts = [p for p in scene.prims
                     if p.get("tag") == ("dev", dev["ip"]) and p["k"] == "text"]
        for p in dev_texts:
            size_pt = p["size"]
            w_in = max(0.3, len(p["v"]) * size_pt * 0.62 / 72)
            h_in = size_pt * 1.4 / 72
            lx, ly = to_local(p["x"], p["y"] + size_pt)
            children.append(
                f'<Shape ID="{sid}" Type="Shape">'
                + _xform(lx, ly, w_in, h_in)
                + '<Cell N="FillPattern" V="0"/><Cell N="LinePattern" V="0"/>'
                + '<Cell N="VerticalAlign" V="1"/>'
                + _char_para(p)
                + _geom_rect(w_in, h_in)
                + f'<Text>{_xml_escape(p["v"])}</Text></Shape>')
            sid += 1

        shapes.append(
            f'<Shape ID="{gid}" Type="Group">'
            + _xform(group_pin_x, group_pin_y, gw, gh)
            + '<Cell N="FillPattern" V="0"/><Cell N="LinePattern" V="0"/>'
            + f'<Shapes>{"".join(children)}</Shapes></Shape>')

    # --- links: glued straight 1-D connectors ------------------------------
    for vl in scene.vlinks:
        a_id = dev_shape_id.get(vl["a"])
        b_id = dev_shape_id.get(vl["b"])
        if not a_id or not b_id:
            continue
        bx, by = vl["ax"] / 72, flip_y(vl["ay"])
        ex, ey = vl["bx"] / 72, flip_y(vl["by"])
        cid = sid
        sid += 1
        shapes.append(_connector_1d(cid, bx, by, ex, ey, vl["color"], vl["width"]))
        # glue both endpoints to the device groups (whole-shape glue)
        connects.append(f'<Connect FromSheet="{cid}" FromPart="9" ToSheet="{a_id}" ToPart="3"/>')
        connects.append(f'<Connect FromSheet="{cid}" FromPart="12" ToSheet="{b_id}" ToPart="3"/>')
        # port labels as free text near the endpoints
        for txt, px, py, anch in (
            (vl["src_if"], vl["ax"] + 6, vl["ay"], "begin"),
            (vl["dst_if"], vl["bx"] + 6, vl["by"], "end"),
        ):
            if not txt:
                continue
            size_pt = 7.0
            w_in = max(0.3, len(txt) * size_pt * 0.62 / 72)
            h_in = size_pt * 1.4 / 72
            p = {"v": txt, "size": size_pt, "bold": False, "italic": False,
                 "color": C_PORT, "align": "left"}
            shapes.append(
                f'<Shape ID="{sid}" Type="Shape">'
                + _xform(px / 72, flip_y(py) - (0.08 if anch == "end" else -0.02), w_in, h_in)
                + '<Cell N="FillPattern" V="0"/><Cell N="LinePattern" V="0"/>'
                + '<Cell N="VerticalAlign" V="1"/>'
                + _char_para(p)
                + _geom_rect(w_in, h_in)
                + f'<Text>{_xml_escape(txt)}</Text></Shape>')
            sid += 1

    w_in, h_in = scene.width / 72, scene.height / 72
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/doc.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>
<Override PartName="/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>
<Override PartName="/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>
<Override PartName="/windows.xml" ContentType="application/vnd.ms-visio.windows+xml"/>
</Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="doc.xml"/>
</Relationships>'''
    doc_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve">
<DocumentSettings TopPage="0" DefaultTextStyle="3" DefaultLineStyle="3" DefaultFillStyle="3" DefaultGuideStyle="3"/>
<Colors/><FaceNames/><StyleSheets/>
</VisioDocument>'''
    doc_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/pages" Target="pages/pages.xml"/>
<Relationship Id="rId2" Type="http://schemas.microsoft.com/visio/2010/relationships/windows" Target="windows.xml"/>
</Relationships>'''
    pages_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve">
<Page ID="0" NameU="Page-1" Name="Page-1" ViewScale="1" ViewCenterX="0" ViewCenterY="0">
<PageSheet LineStyle="3" FillStyle="3" TextStyle="3">
<Cell N="PageWidth" V="%(w).4f"/><Cell N="PageHeight" V="%(h).4f"/>
<Cell N="ShdwOffsetX" V="0.125"/><Cell N="ShdwOffsetY" V="-0.125"/>
<Cell N="PageScale" V="1"/><Cell N="DrawingScale" V="1"/>
<Cell N="DrawingSizeType" V="0"/><Cell N="DrawingScaleType" V="0"/>
<Cell N="InhibitSnap" V="0"/><Cell N="PageLockReplace" V="0"/><Cell N="PageLockDuplicate" V="0"/>
<Cell N="UIVisibility" V="0"/><Cell N="ShdwType" V="0"/><Cell N="ShdwObliqueAngle" V="0"/>
<Cell N="ShdwScaleFactor" V="1"/><Cell N="DrawingResizeType" V="1"/>
</PageSheet>
<Rel r:id="rId1"/>
</Page>
</Pages>''' % {"w": w_in, "h": h_in}
    pages_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page1.xml"/>
</Relationships>'''
    page1_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                 '<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main" '
                 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve">'
                 f'<Shapes>{"".join(shapes)}</Shapes>'
                 f'<Connects>{"".join(connects)}</Connects></PageContents>')
    page1_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                  + "".join(rels) + '</Relationships>')
    windows_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Windows xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ClientWidth="1024" ClientHeight="768">
<Window ID="0" WindowType="Drawing" WindowState="1073741824" WindowLeft="0" WindowTop="0" WindowWidth="1024" WindowHeight="768" ContainerType="Page" Page="0" ViewScale="1" ViewCenterX="5" ViewCenterY="5"/>
</Windows>'''

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("doc.xml", doc_xml)
        z.writestr("_rels/doc.xml.rels", doc_rels)
        z.writestr("windows.xml", windows_xml)
        z.writestr("pages/pages.xml", pages_xml)
        z.writestr("pages/_rels/pages.xml.rels", pages_rels)
        z.writestr("pages/page1.xml", page1_xml)
        if rels:
            z.writestr("pages/_rels/page1.xml.rels", page1_rels)
        for name, data in media:
            z.writestr(name, data)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Word (.docx) renderer — full-sheet diagram image on a sized page
# --------------------------------------------------------------------------

def render_docx(scene: Scene) -> bytes:
    from docx import Document
    from docx.shared import Inches
    from docx.enum.section import WD_ORIENT

    png = render_png(scene, scale=2)
    doc = Document()
    sec = doc.sections[0]
    # Word caps page dimensions at 22" — scale oversized sheets down to fit.
    w_in = min(scene.width / 72, 22)
    h_in = min(scene.height / 72, 22)
    if w_in >= h_in:
        sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width = Inches(w_in)
    sec.page_height = Inches(h_in)
    sec.left_margin = sec.right_margin = Inches(0.2)
    sec.top_margin = sec.bottom_margin = Inches(0.2)
    doc.add_picture(io.BytesIO(png), width=Inches(w_in - 0.4))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def export_diagram(nodes: list[dict], links: list[dict], fmt: str, opts: dict) -> bytes:
    scene = build_scene(nodes, links, opts)
    if fmt == "pdf":
        return render_pdf(scene)
    if fmt == "png":
        return render_png(scene)
    if fmt == "vsdx":
        return render_vsdx(scene)
    if fmt == "docx":
        return render_docx(scene)
    raise ValueError(f"unsupported diagram format: {fmt}")
