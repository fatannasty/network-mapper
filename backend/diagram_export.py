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
LAYER_GAP = 175           # vertical distance between device layers
GLYPH_W, GLYPH_H = 120, 26
CLOUD_W, CLOUD_H = 150, 56
UNKNOWN_W, UNKNOWN_H = 100, 22
SLOT_W = 175              # horizontal slot per device
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


def _medium_key(interface_a: str, interface_b: str) -> str:
    """Guess the physical medium from interface names (10G+ => single-mode)."""
    name = (interface_a or interface_b or "").strip().upper()
    for pfx in ("TWE", "TE", "FO", "HU"):
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

    def rect(self, x, y, w, h, fill=None, stroke=C_FRAME, sw=1.0):
        self.prims.append({"k": "rect", "x": x, "y": y, "w": w, "h": h,
                           "fill": fill, "stroke": stroke, "sw": sw})

    def ellipse(self, cx, cy, rx, ry, fill=None, stroke=C_FRAME, sw=1.0):
        self.prims.append({"k": "ellipse", "cx": cx, "cy": cy, "rx": rx, "ry": ry,
                           "fill": fill, "stroke": stroke, "sw": sw})

    def line(self, pts, color=C_LINK, width=1.2):
        self.prims.append({"k": "line", "pts": pts, "color": color, "width": width})

    def text(self, x, y, value, size=10, bold=False, italic=False,
             color=C_TEXT, align="center"):
        if value:
            self.prims.append({"k": "text", "x": x, "y": y, "v": str(value),
                               "size": size, "bold": bold, "italic": italic,
                               "color": color, "align": align})

    def image(self, x, y, w, h, path):
        self.prims.append({"k": "image", "x": x, "y": y, "w": w, "h": h, "path": path})


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

    max_per_layer = max((len(v) for v in layers.values()), default=1)
    width = max(1150, MARGIN * 2 + max_per_layer * SLOT_W)
    n_layers = len(order)
    content_top = MARGIN + HEADER_H
    legend_y = content_top + n_layers * LAYER_GAP + 60
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
    pos: dict[str, tuple[float, float]] = {}   # ip -> glyph center (cx, cy)
    layer_idx = {r: i for i, r in enumerate(order)}
    for r in order:
        group = layers[r]
        span = len(group) * SLOT_W
        x0 = (width - span) / 2 + SLOT_W / 2
        gy = content_top + layer_idx[r] * LAYER_GAP + 70
        for i, n in enumerate(group):
            pos[n["ip"]] = (x0 + i * SLOT_W, gy)

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
            span = len(layers[r]) * SLOT_W
            x0 = (width - span) / 2 + SLOT_W / 2
            for i, n in enumerate(layers[r]):
                pos[n["ip"]] = (x0 + i * SLOT_W, pos[n["ip"]][1])

    # --- links (orthogonal elbows, port labels, medium colors) ------------
    dt_by_ip = {n["ip"]: (n.get("device_type") or "").lower() for n in nodes}

    def half_h(ip: str) -> float:
        dt = dt_by_ip.get(ip, "")
        if "router" in dt:
            return CLOUD_H / 2
        if dt == "unknown":
            return UNKNOWN_H / 2
        return GLYPH_H / 2

    seen: set[tuple] = set()
    pair_count: dict[tuple, int] = {}
    label_slots: dict[tuple[str, str], int] = {}   # (ip, "top"|"bottom") -> count

    def port_label(ip: str, x: float, y: float, side: str, text: str):
        slot = label_slots.get((ip, side), 0)
        label_slots[(ip, side)] = slot + 1
        dy = slot * 8 if side == "bottom" else -slot * 8
        scene.text(x + 5, y + dy, text, size=7, color=C_PORT, align="left")

    for l in links:
        a, b = l.get("source"), l.get("target")
        if a not in pos or b not in pos or a == b:
            continue
        k = (a, b, l.get("source_interface"), l.get("target_interface"))
        if k in seen:
            continue
        seen.add(k)
        pair = tuple(sorted((a, b)))
        dup = pair_count.get(pair, 0)
        pair_count[pair] = dup + 1

        x1, y1 = pos[a]
        x2, y2 = pos[b]
        h1, h2 = half_h(a), half_h(b)
        med = _medium_key(l.get("source_interface", ""), l.get("target_interface", ""))
        color = C_LINK
        if color_links and med and legend_color.get(med):
            color = legend_color[med]

        same_layer = abs(y1 - y2) < 1
        off = dup * 9
        if same_layer:
            # channel runs above the whole label stack (stack ≈ 46pt tall)
            top = min(y1 - h1, y2 - h2) - 58 - off
            pts = [(x1, y1 - h1), (x1, top), (x2, top), (x2, y2 - h2)]
        else:
            if y1 > y2:
                x1, y1, x2, y2 = x2, y2, x1, y1
                h1, h2 = h2, h1
                a, b = b, a
            mid = (y1 + y2) / 2 + off - 4
            pts = [(x1, y1 + h1), (x1, mid), (x2, mid), (x2, y2 - h2)]
        scene.line(pts, color=color, width=1.4)

        ia, ib = l.get("source_interface") or "", l.get("target_interface") or ""
        if same_layer:
            port_label(a, x1, y1 - h1 - 10, "top", ia)
            port_label(b, x2, y2 - h2 - 10, "top", ib)
        else:
            src_if = ia if (a, b) == (l.get("source"), l.get("target")) else ib
            dst_if = ib if src_if == ia else ia
            port_label(a, x1, y1 + h1 + 2, "bottom", src_if)
            port_label(b, x2, y2 - h2 - 10, "top", dst_if)

    # --- node glyphs + label stacks ---------------------------------------
    for r in order:
        for n in layers[r]:
            cx, cy = pos[n["ip"]]
            hn = (n.get("hostname") or "").split(".")[0] or n.get("ip") or ""
            model = n.get("model") or ""
            ip = n.get("ip") or ""
            dt = (n.get("device_type") or "").lower()

            if "router" in dt:
                scene.ellipse(cx, cy, CLOUD_W / 2, CLOUD_H / 2, fill="#FFFFFF", sw=1.2)
                scene.text(cx, cy - 20, hn, size=8, bold=True)
                scene.text(cx, cy - 9, model, size=7.5)
                scene.text(cx, cy + 2, ip, size=7.5)
            elif dt == "unknown" and not model and not hn:
                scene.rect(cx - UNKNOWN_W / 2, cy - UNKNOWN_H / 2, UNKNOWN_W, UNKNOWN_H,
                           fill=C_UNKNOWN, stroke=C_GLYPH_TICK, sw=0.75)
                scene.text(cx, cy - 5, ip, size=8)
            else:
                # label stack above the faceplate
                ly = cy - GLYPH_H / 2 - 12
                if ip:
                    scene.text(cx, ly - 10, ip, size=8.5); ly -= 10
                if model:
                    scene.text(cx, ly - 10, model, size=8.5); ly -= 10
                scene.text(cx, ly - 11, hn, size=9.5, bold=True); ly -= 11
                if n["ip"] in core_num:
                    scene.text(cx, ly - 11, f"CORE{core_num[n['ip']]}",
                               size=10, bold=True, color=C_CORE)
                # switch faceplate
                gx, gy = cx - GLYPH_W / 2, cy - GLYPH_H / 2
                scene.rect(gx, gy, GLYPH_W, GLYPH_H, fill=C_GLYPH, stroke=C_GLYPH_EDGE, sw=1.0)
                for t in range(12):
                    tx = gx + 8 + t * (GLYPH_W - 16) / 12
                    scene.rect(tx, gy + 6, 6, 4, fill=C_GLYPH_TICK, stroke=None, sw=0)
                    scene.rect(tx, gy + 15, 6, 4, fill=C_GLYPH_TICK, stroke=None, sw=0)

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
# --------------------------------------------------------------------------

def _vdx_text_shape(sid: int, p: dict, H: float) -> str:
    size_pt = p["size"]
    w_in = max(0.3, len(p["v"]) * size_pt * 0.62 / 72)
    h_in = size_pt * 1.4 / 72
    pinx = p["x"] / 72
    piny = (H - p["y"]) / 72 - h_in / 2
    style = ("1" if p["bold"] else "0") if not p["italic"] else ("3" if p["bold"] else "2")
    halign = {"left": "0", "center": "1", "right": "2"}[p["align"]]
    # box width: for centered/right text, give the box room and align within it
    return f'''<Shape ID="{sid}" Type="Shape" LineStyle="3" FillStyle="3" TextStyle="3">
<Cell N="PinX" V="{pinx:.4f}"/><Cell N="PinY" V="{piny:.4f}"/>
<Cell N="Width" V="{w_in:.4f}"/><Cell N="Height" V="{h_in:.4f}"/>
<Cell N="LocPinX" V="{w_in / 2:.4f}"/><Cell N="LocPinY" V="{h_in / 2:.4f}"/>
<Cell N="FillPattern" V="0"/><Cell N="LinePattern" V="0"/><Cell N="VerticalAlign" V="1"/>
<Section N="Character"><Row IX="0"><Cell N="Color" V="{p['color']}"/><Cell N="Size" V="{size_pt / 72:.4f}"/><Cell N="Style" V="{style}"/></Row></Section>
<Section N="Paragraph"><Row IX="0"><Cell N="HorzAlign" V="{halign}"/></Row></Section>
<Geom IX="0"><NoFill V="1"/><NoLine V="1"/>
<MoveTo IX="1"><X V="0"/><Y V="0"/></MoveTo>
<LineTo IX="2"><X V="{w_in:.4f}"/><Y V="0"/></LineTo>
<LineTo IX="3"><X V="{w_in:.4f}"/><Y V="{h_in:.4f}"/></LineTo>
<LineTo IX="4"><X V="0"/><Y V="{h_in:.4f}"/></LineTo>
<LineTo IX="5"><X V="0"/><Y V="0"/></LineTo>
</Geom>
<Text>{_xml_escape(p["v"])}</Text>
</Shape>'''


def render_vsdx(scene: Scene) -> bytes:
    """Hand-rolled minimal .vsdx: native shapes/connectors, editable in Visio."""
    H = scene.height
    shapes: list[str] = []
    rels: list[str] = []
    sid = 1
    media: list[tuple[str, bytes]] = []

    def flip_y(y_pt):
        return (H - y_pt) / 72

    for p in scene.prims:
        k = p["k"]
        if k == "rect":
            w, h = p["w"] / 72, p["h"] / 72
            pinx, piny = (p["x"] + p["w"] / 2) / 72, flip_y(p["y"] + p["h"] / 2)
            fill = p.get("fill")
            stroke = p.get("stroke")
            geom_rows = (f'<MoveTo IX="1"><X V="0"/><Y V="0"/></MoveTo>'
                         f'<LineTo IX="2"><X V="{w:.4f}"/><Y V="0"/></LineTo>'
                         f'<LineTo IX="3"><X V="{w:.4f}"/><Y V="{h:.4f}"/></LineTo>'
                         f'<LineTo IX="4"><X V="0"/><Y V="{h:.4f}"/></LineTo>'
                         f'<LineTo IX="5"><X V="0"/><Y V="0"/></LineTo>')
            cells = [f'<Cell N="PinX" V="{pinx:.4f}"/><Cell N="PinY" V="{piny:.4f}"/>',
                     f'<Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/>',
                     f'<Cell N="LocPinX" V="{w / 2:.4f}"/><Cell N="LocPinY" V="{h / 2:.4f}"/>']
            if fill:
                cells.append(f'<Cell N="FillForegnd" V="{fill}"/><Cell N="FillPattern" V="1"/>')
            else:
                cells.append('<Cell N="FillPattern" V="0"/>')
            if stroke:
                cells.append(f'<Cell N="LineColor" V="{stroke}"/><Cell N="LineWeight" V="{p["sw"] / 72:.4f}"/>')
            else:
                cells.append('<Cell N="LinePattern" V="0"/>')
            shapes.append(f'<Shape ID="{sid}" Type="Shape" LineStyle="3" FillStyle="3" TextStyle="3">'
                          + "".join(cells) + f'<Geom IX="0">{geom_rows}</Geom></Shape>')
            sid += 1
        elif k == "ellipse":
            w, h = p["rx"] * 2 / 72, p["ry"] * 2 / 72
            pinx, piny = p["cx"] / 72, flip_y(p["cy"])
            shapes.append(
                f'<Shape ID="{sid}" Type="Shape" LineStyle="3" FillStyle="3" TextStyle="3">'
                f'<Cell N="PinX" V="{pinx:.4f}"/><Cell N="PinY" V="{piny:.4f}"/>'
                f'<Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/>'
                f'<Cell N="LocPinX" V="{w / 2:.4f}"/><Cell N="LocPinY" V="{h / 2:.4f}"/>'
                f'<Cell N="FillForegnd" V="{p.get("fill") or "#FFFFFF"}"/><Cell N="FillPattern" V="1"/>'
                f'<Cell N="LineColor" V="{p.get("stroke") or "#000000"}"/><Cell N="LineWeight" V="{p["sw"] / 72:.4f}"/>'
                f'<Geom IX="0">'
                f'<MoveTo IX="1"><X V="0"/><Y V="{h / 2:.4f}"/></MoveTo>'
                f'<Ellipse IX="2"><X V="{w / 2:.4f}"/><Y V="{h / 2:.4f}"/>'
                f'<A V="{w:.4f}"/><B V="{h / 2:.4f}"/></Ellipse>'
                f'</Geom></Shape>')
            sid += 1
        elif k == "line":
            pts = p["pts"]
            # one straight 1-D connector per segment
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                bx, by = x1 / 72, flip_y(y1)
                ex, ey = x2 / 72, flip_y(y2)
                wdt, hgt = ex - bx, ey - by
                shapes.append(
                    f'<Shape ID="{sid}" Type="Shape" LineStyle="3" FillStyle="3" TextStyle="3">'
                    f'<Cell N="PinX" V="{(bx + ex) / 2:.4f}"/><Cell N="PinY" V="{(by + ey) / 2:.4f}"/>'
                    f'<Cell N="Width" V="{wdt:.4f}"/><Cell N="Height" V="{hgt:.4f}"/>'
                    f'<Cell N="LocPinX" V="{wdt / 2:.4f}"/><Cell N="LocPinY" V="{hgt / 2:.4f}"/>'
                    f'<Cell N="BeginX" V="{bx:.4f}"/><Cell N="BeginY" V="{by:.4f}"/>'
                    f'<Cell N="EndX" V="{ex:.4f}"/><Cell N="EndY" V="{ey:.4f}"/>'
                    f'<Cell N="LineColor" V="{p["color"]}"/><Cell N="LineWeight" V="{p["width"] / 72:.4f}"/>'
                    f'<Cell N="FillPattern" V="0"/><Cell N="OneD" V="1"/>'
                    f'<Geom IX="0"><NoFill V="1"/>'
                    f'<MoveTo IX="1"><X V="0"/><Y V="0"/></MoveTo>'
                    f'<LineTo IX="2"><X V="{wdt:.4f}" F="Width*1"/><Y V="{hgt:.4f}" F="Height*1"/></LineTo>'
                    f'</Geom></Shape>')
                sid += 1
        elif k == "text":
            shapes.append(_vdx_text_shape(sid, p, H))
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
                        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                        f'Target="../media/image{len(media)}.png"/>')
            w, h = p["w"] / 72, p["h"] / 72
            pinx, piny = (p["x"] + p["w"] / 2) / 72, flip_y(p["y"] + p["h"] / 2)
            shapes.append(
                f'<Shape ID="{sid}" Type="Foreign" LineStyle="3" FillStyle="3" TextStyle="3">'
                f'<Cell N="PinX" V="{pinx:.4f}"/><Cell N="PinY" V="{piny:.4f}"/>'
                f'<Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/>'
                f'<Cell N="LocPinX" V="{w / 2:.4f}"/><Cell N="LocPinY" V="{h / 2:.4f}"/>'
                f'<Cell N="FillPattern" V="0"/><Cell N="LinePattern" V="0"/>'
                f'<ForeignData ForeignType="Bitmap" MappingMode="96" ExtentX="{int(p["w"] * 2540)}" ExtentY="{int(p["h"] * 2540)}">'
                f'<Rel xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="{rid}"/>'
                f'</ForeignData></Shape>')
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
                 f'<Shapes>{"".join(shapes)}</Shapes></PageContents>')
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
