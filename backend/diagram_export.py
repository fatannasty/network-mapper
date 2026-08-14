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
SLOT_W = 186              # horizontal slot per device
MAX_PER_ROW = 6           # rows wrap downward past this (uniform vertical flow)
LEGEND_H = 130            # legend / title block height

# Hierarchy: Internet/Cloud -> Edge -> Security -> Core -> Distribution ->
# Access -> Endpoints, drawn top to bottom as full-width "swimlane" zones so
# the logical flow reads cleanly down the sheet with minimal crossings.
LAYER_KEYS = ("internet", "edge", "security", "core", "distribution",
              "access", "endpoint")
LAYER_NAMES = {
    "internet": "INTERNET / CLOUD",
    "edge": "EDGE",
    "security": "SECURITY",
    "core": "CORE",
    "distribution": "DISTRIBUTION",
    "access": "ACCESS",
    "endpoint": "ENDPOINTS",
}
LAYER_FILL = {
    "internet": "#EAF3FB",
    "edge": "#E9ECF8",
    "security": "#FBEAE6",
    "core": "#E8F2E9",
    "distribution": "#E6F4F3",
    "access": "#FFF6E5",
    "endpoint": "#F5ECF7",
}
LAYER_STROKE = {
    "internet": "#8FB8DE",
    "edge": "#AAB4DE",
    "security": "#E5A79A",
    "core": "#9CC7A0",
    "distribution": "#7FB8B0",
    "access": "#E8C98C",
    "endpoint": "#CDB0D6",
}
ZONE_H = 140              # per-row height of a layer enclosure
ZONE_ROW_CY = 64          # device-center offset from the zone top (per row)

# Link-routing: each inter-layer link rides a horizontal channel in the
# gutter below its source zone; channels are stacked CH_SP apart so parallel
# runs never overlap, and each gutter is grown only as tall as it needs.
CH_SP = 11                # vertical spacing between stacked channel lines
CH_PAD = 5                # clearance between a zone box and the nearest channel
MIN_ZONE_GAP = 16         # smallest visible (box-to-box) gutter left between zones
BOX_PAD = 24              # padding the zone boxes consume inside a zone_gap (12 top + 12 bottom)

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

AMTRAK_BLUE = "#003A70"
PROPRIETARY = "AMTRAK - Proprietary\nUse Pursuant to Company\nInstructions"

DEFAULT_LEGEND = [
    {"key": "wan", "label": "WAN / Internet", "color": LINK_COLORS["wan"]},
    {"key": "core", "label": "Core Backbone", "color": LINK_COLORS["core"]},
    {"key": "lan", "label": "LAN", "color": LINK_COLORS["lan"]},
    {"key": "fiber", "label": "Fiber", "color": LINK_COLORS["fiber"]},
    {"key": "management", "label": "Management", "color": LINK_COLORS["management"]},
]

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
    for pfx, abbr in _IFACE_SHORT:
        if name.startswith(pfx):
            return abbr + name[len(pfx):]
    return name


def _icon_kind(device_type: str, model: str, hostname: str) -> str:
    """Classify a device into a generic icon family."""
    dt = (device_type or "").lower()
    mo = (model or "").lower()
    hn = (hostname or "").lower()
    if "velocloud" in dt or "velo" in mo or "velo" in hn or mo.startswith("edge"):
        return "velocloud"
    if "access point" in dt or "access_point" in dt or "accesspoint" in dt or "ap" in dt \
            or mo.startswith("mr") or mo.startswith("air-cap") or mo.startswith("air-lap"):
        return "ap"
    if "firewall" in dt or "security" in dt or mo.startswith("mx"):
        return "firewall"
    if "router" in dt or mo.startswith("isr") or mo.startswith("asr") or mo.startswith("cisco") \
            or "router" in mo:
        return "router"
    if "switch" in dt or "switch" in mo or mo.startswith("ms") or mo.startswith("ws-c"):
        return "switch"
    return "unknown"


def _icon_path(device_type: str, model: str, hostname: str) -> str | None:
    """Return the path of a device icon if one is present in ICON_DIR.

    Search order: exact hostname, model-derived names, generic kind.
    Accepts both PNG and SVG files.
    """
    os.makedirs(ICON_DIR, exist_ok=True)
    kind = _icon_kind(device_type, model, hostname)
    candidates: list[str] = []

    # Kind-specific aliases (user-friendly filenames from common icon packs)
    kind_aliases = {
        "ap": ["ap", "accesspoint", "accesspoint-cisco", "wireless-ap", "wifi", "aironet-ap"],
        "router": ["router", "cloud-cisco", "cloud"],
        "switch": ["switch", "layer3-switch"],
        "firewall": ["firewall", "firewall-cisco"],
        "velocloud": ["velocloud", "velocloud-edge-510", "velocloud-edge-rackmount", "sdwan"],
        "unknown": ["unknown", "server", "pc", "device"],
    }

    def _variants(text: str) -> list[str]:
        """Return filename variants for a label (spaces, hyphens, underscores)."""
        t = (text or "").lower().strip()
        return [t, t.replace(" ", "-"), t.replace(" ", "_"), t.replace("-", ""), t.replace("_", ""), t.replace("-", " ")]

    def _tokenize(text: str) -> list[str]:
        return [tok for tok in re.split(r"[-_/\s]+", text.strip().lower()) if tok]

    def _prefixes(text: str) -> list[str]:
        """Progressively shorter hyphenated prefixes (e.g. C9300L-24P-4X -> C9300L, C9300L-24P)."""
        tokens = _tokenize(text)
        return ["-".join(tokens[:i]) for i in range(1, len(tokens) + 1)]

    def _model_names(text: str) -> list[str]:
        """Candidate filenames for a model string."""
        names: list[str] = []
        variants = _variants(text)
        for v in variants:
            names.extend([f"{v}.png", f"{v}.svg"])
        for prefix in _prefixes(text):
            for v in _variants(prefix):
                names.extend([f"{v}.png", f"{v}.svg"])
        # If the last token has a trailing alphabetic suffix after digits
        # (e.g. 24CY or 4X), strip it and try common suffixes.
        tokens = _tokenize(text)
        if tokens:
            m = re.match(r"^([0-9]+)([a-zA-Z]+)$", tokens[-1])
            if m:
                digits, trailing = m.group(1), m.group(2)
                stripped = tokens[:-1] + [digits]
                for prefix in _prefixes("-".join(stripped)):
                    for v in _variants(prefix):
                        names.extend([f"{v}.png", f"{v}.svg"])
                        if "meraki" not in v and (v.startswith("mr") or v.startswith("ms") or v.startswith("mx")):
                            names.extend([f"meraki-{v}.png", f"meraki-{v}.svg"])
                        if "cisco" not in v:
                            names.extend([f"cisco-{v}.png", f"cisco-{v}.svg"])
                for sfx in ("p", "y", "c", "x", "t", "z", "e", "s", "k", "n"):
                    replaced = tokens[:-1] + [digits + sfx]
                    for prefix in _prefixes("-".join(replaced)):
                        for v in _variants(prefix):
                            names.extend([f"{v}.png", f"{v}.svg"])
                            if "meraki" not in v and (v.startswith("mr") or v.startswith("ms") or v.startswith("mx")):
                                names.extend([f"meraki-{v}.png", f"meraki-{v}.svg"])
                            if "cisco" not in v:
                                names.extend([f"cisco-{v}.png", f"cisco-{v}.svg"])
        # Models stored with a "cisco" prefix (CISCO1921, CISCO2921, CISCO3925)
        # map to "cisco-1921" style filenames.
        low = text.lower()
        if low.startswith("cisco") and len(low) > 5 and low[5].isdigit():
            rest = re.sub(r"^[^a-z0-9]+", "", low[5:])
            for p in _prefixes(rest):
                for v in _variants(p):
                    names.extend([f"cisco-{v}.png", f"cisco-{v}.svg"])
        # Brand / kind prefixed variants (e.g. meraki-mr76, cisco-c9300x-24p).
        for v in list(variants) + [p for p in _prefixes(text) if p not in variants]:
            if not v:
                continue
            for alias in kind_aliases.get(kind, [kind]):
                names.extend([f"{alias}-{v}.png", f"{alias}-{v}.svg"])
            if "meraki" not in v and (v.startswith("mr") or v.startswith("ms") or v.startswith("mx")):
                names.extend([f"meraki-{v}.png", f"meraki-{v}.svg"])
            if "cisco" not in v:
                names.extend([f"cisco-{v}.png", f"cisco-{v}.svg"])
        # Meraki brand-prefixed models with a letter after the digits
        # (MX67C-NA -> meraki-mx67) map to the base numeric icon. Runs AFTER the
        # exact brand match so MR46E prefers meraki-mr46e over meraki-mr46.
        m = re.match(r"^(mr|ms|mx)([0-9]+)[a-z].*$", low)
        if m:
            for p in _prefixes(m.group(1) + m.group(2)):
                for v in _variants(p):
                    names.extend([f"meraki-{v}.png", f"meraki-{v}.svg"])
        # Cisco Aironet models (AIR-CAP/AIR-LAP/AIR-CT) use the generic Aironet AP icon.
        if kind == "ap" and re.match(r"^air-(cap|lap|ct)", text.lower()):
            names.extend([f"aironet-ap.png", f"aironet-ap.svg"])
        # VeloCloud edge models map to "velocloud-edge-<model>" (e.g. edge610 -> velocloud-edge-610).
        if kind == "velocloud":
            for v in variants:
                if v.startswith("edge"):
                    names.extend([f"velocloud-{v}.png", f"velocloud-{v}.svg"])
                    rest = v[4:]
                    if rest:
                        names.extend([f"velocloud-edge-{rest}.png", f"velocloud-edge-{rest}.svg"])
                    num = re.sub(r"[^0-9a-z].*$", "", v.replace("edge", ""))
                    if num:
                        names.extend([f"velocloud-edge-{num}.png", f"velocloud-edge-{num}.svg"])
        # Fallback: progressive alphanumeric prefixes and series name.
        base = "".join(c for c in text.lower() if c.isalnum())
        for i in (12, 11, 10, 9, 8, 7, 6, 5, 4):
            if len(base) > i:
                names.extend([f"{base[:i]}.png", f"{base[:i]}.svg"])
        series = base.rstrip("0123456789")
        if series and series != base:
            names.extend([f"{series}.png", f"{series}.svg"])
        return names

    for text in {hostname, model}:
        if not text:
            continue
        if text == hostname:
            for v in _variants(text):
                candidates.extend([f"{v}.png", f"{v}.svg"])
        else:
            # Some models are stored as comma-separated lists (duplicates or
            # multi-slot results); try each component separately.
            for part in re.split(r"[,\n;]+", text):
                part = part.strip()
                if part:
                    candidates.extend(_model_names(part))

    for alias in kind_aliases.get(kind, [kind]):
        candidates.extend([f"{alias}.png", f"{alias}.svg"])

    for name in candidates:
        path = os.path.join(ICON_DIR, name)
        if os.path.exists(path):
            return path
    return None


def _svg_to_png(path: str, size: tuple[int, int]) -> bytes | None:
    """Convert an SVG icon to a PNG blob using cairosvg if available."""
    try:
        import cairosvg
    except Exception:
        return None
    try:
        return cairosvg.svg2png(url=path, output_width=size[0], output_height=size[1])
    except Exception:
        return None


def _icon_png_bytes(path: str, size: tuple[int, int]) -> bytes | None:
    """Return PNG bytes for an icon file, converting SVG to PNG if needed."""
    if path.lower().endswith(".svg"):
        return _svg_to_png(path, size)
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _png_px(data: bytes) -> tuple[int, int]:
    """Return the pixel dimensions of PNG bytes (used for Visio ExtentX/Y)."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:
        return 0, 0


def _png_to_emf(data: bytes) -> bytes | None:
    """Wrap PNG bytes in a minimal EMF metafile (8-bit palette StretchDIBits).

    Real Visio renders bitmap images only when they are packaged as EMF
    metafiles, so the vsdx exporter embeds each PNG as a single-image EMF.
    Visio's own stencils use 8-bit palette DIBs, so we match that format.
    """
    import struct
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            bg.alpha_composite(im)
            rgb = bg.convert("RGB")
            w, h = rgb.size
            pal = rgb.quantize(colors=256, method=Image.MEDIANCUT)
            indices = pal.tobytes()  # 1 byte per pixel, palette index
            palette = pal.getpalette()  # 256 * 3 bytes (R, G, B)
    except Exception:
        return None

    # 8-bit bottom-up DIB rows, padded to a 4-byte boundary.
    row = ((w + 3) // 4) * 4
    dib = bytearray()
    for y in range(h - 1, -1, -1):
        s = y * w
        dib += indices[s:s + w]
        dib += b"\x00" * (row - w)

    # BITMAPINFOHEADER (40) + palette (256 RGBQUAD) + indices.
    bi = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 8, 0, row * h, 0, 0, 256, 0)
    # RGBQUAD is (blue, green, red, reserved). PIL palette is (R, G, B).
    palette = palette + [0] * (768 - len(palette))
    quads = bytearray()
    for i in range(256):
        quads += bytes((palette[i * 3 + 2], palette[i * 3 + 1], palette[i * 3], 0))

    # EMR_STRETCHDIBITS record.
    rcl_bounds = struct.pack("<4i", 0, 0, w - 1, h - 1)
    fx = int(w * 2540 / 96)
    fy = int(h * 2540 / 96)
    rcl_frame = struct.pack("<4i", 0, 0, fx, fy)
    bitmapinfo = bi + bytes(quads)      # BITMAPINFOHEADER + palette (no bits)
    off_bmi = 96
    cb_bmi = len(bitmapinfo)            # 40 + 1024
    off_bits = off_bmi + cb_bmi         # 1160
    cb_bits = len(dib)
    body = (
        struct.pack("<I", 0x00CC0020)          # iModeSrc = SRCCOPY
        + struct.pack("<4i", 0, 0, w, h)       # xSrc, ySrc, cxSrc, cySrc
        + struct.pack("<4i", 0, 0, w, h)       # xDest, yDest, cxDest, cyDest
        + struct.pack("<IIII", cb_bmi, off_bmi, cb_bits, off_bits)
        + struct.pack("<I", 0)                 # dwUsage = DIB_RGB_COLORS
        + bitmapinfo + bytes(dib)
    )
    rec_size = 8 + 16 + 16 + len(body)
    stretch = struct.pack("<II", 81, rec_size) + rcl_bounds + rcl_frame + body

    # EMR_EOF record (20 bytes).
    eof = struct.pack("<II", 14, 20) + b"\x00" * 12

    total = 88 + rec_size + len(eof)
    szl_mm = struct.pack("<2i", int(round(w * 25.4 / 96)), int(round(h * 25.4 / 96)))
    header = (
        struct.pack("<II", 1, 88)
        + rcl_bounds
        + rcl_frame
        + struct.pack("<II", 0x464D4520, 0x00010000)
        + struct.pack("<II", total, 2)
        + struct.pack("<HH", 1, 0)
        + struct.pack("<II", 0, 0)
        + struct.pack("<I", 0)
        + struct.pack("<2i", w, h)
        + szl_mm
    )
    return header + stretch + eof


def _emf_extent(emf: bytes) -> tuple[int, int]:
    """Return the EMF rclBounds size (device units) for ExtentX/ExtentY."""
    import struct
    try:
        rcl = struct.unpack("<4i", emf[8:24])
        return rcl[2] - rcl[0], rcl[3] - rcl[1]
    except Exception:
        return 0, 0


def _read_emf_for_image(path: str) -> tuple[bytes | None, int, int]:
    """Return a pre-converted EMF (and its extent) for an image path.

    Real Visio renders embedded pictures only as EMF metafiles, so the vsdx
    exporter prefers the EMF version of each icon (in assets/emf/) over the
    raw PNG. Returns (None, 0, 0) when no EMF is available.
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    emf_path = os.path.join(EMF_DIR, stem + ".emf")
    if os.path.exists(emf_path):
        try:
            with open(emf_path, "rb") as fh:
                data = fh.read()
        except OSError:
            return None, 0, 0
        ew, eh = _emf_extent(data)
        return data, ew, eh
    return None, 0, 0


def _icon_size(path: str, max_w: float, max_h: float) -> tuple[float, float]:
    """Return icon display size preserving aspect ratio within the bounds."""
    try:
        from PIL import Image
        with Image.open(path) as img:
            iw, ih = img.size
    except Exception:
        return max_w, max_h
    scale = min(max_w / iw, max_h / ih)
    return iw * scale, ih * scale


# Cache of transparent-padding (alpha) insets per icon, as fractions of the
# image dimensions: (top, bottom, left, right) in [0,1). Many icon packs ship
# with transparent margins, so the connector -- and the Visio glue box -- must
# reach the *visible* graphic edge, not the empty image-box edge.
_ICON_INSET_CACHE: dict[str, tuple[float, float, float, float]] = {}


def _icon_visible_insets(path: str) -> tuple[float, float, float, float]:
    """Return (top, bottom, left, right) transparent padding fractions."""
    if path in _ICON_INSET_CACHE:
        return _ICON_INSET_CACHE[path]
    try:
        from PIL import Image
        with Image.open(path) as img:
            if img.mode not in ("RGBA", "LA") and "transparency" not in img.info:
                insets = (0.0, 0.0, 0.0, 0.0)
            else:
                a = img.getchannel("A") if img.mode in ("RGBA", "LA") else img.convert("RGBA").getchannel("A")
                bbox = a.getbbox()  # (left, upper, right, lower) of non-zero alpha
                if not bbox or not img.size:
                    insets = (0.0, 0.0, 0.0, 0.0)
                else:
                    W, H = img.size
                    l, u, r, lw = bbox
                    insets = (u / H, (H - lw) / H, l / W, (W - r) / W)
    except Exception:
        insets = (0.0, 0.0, 0.0, 0.0)
    _ICON_INSET_CACHE[path] = insets
    return insets


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

def _layer_of(node: dict) -> str:
    """Assign a device to one of the LAYER_KEYS hierarchy bands so the
    diagram flows Internet -> Edge -> Security -> Core -> Distribution ->
    Access -> Endpoints from top to bottom."""
    dt = (node.get("device_type") or "").lower()
    model = (node.get("model") or "").lower()
    hn = (node.get("hostname") or "").lower()
    if "cloud" in dt or "internet" in dt or "inet" in dt or "inet" in hn:
        return "internet"
    if "velocloud" in dt or "velo" in model or "sdwan" in dt or model.startswith("edge"):
        return "edge"
    if "firewall" in dt or "security" in dt or model.startswith("mx") \
            or "asa" in model or "firepower" in model:
        return "security"
    if "router" in dt or "router" in model or model.startswith(("isr", "asr")):
        return "edge"
    if "core" in dt or "core" in model or model.startswith(("c9500", "c9400")):
        return "core"
    if "access point" in dt or "accesspoint" in dt or "access_point" in dt \
            or model.startswith(("mr", "air-cap", "air-lap")) or "printer" in dt:
        return "endpoint"
    if "switch" in dt or "switch" in model or model.startswith(("ms", "ws-c")):
        if model.startswith(("c9300x", "c9200x", "c9300-")):
            return "distribution"
        return "access"
    return "endpoint"


def _link_color_key(src: str, dst: str, layer_by_ip: dict[str, str],
                    src_if: str, dst_if: str) -> str:
    """Pick the link color (wan/fiber/core/lan/management).

    Priority keeps the legend honest: management trumps everything, the WAN
    stays blue at the edge, then fiber (10G+ uplinks/backbone) shows yellow,
    remaining core/lan links get their role greens."""
    s = layer_by_ip.get(src, "access")
    d = layer_by_ip.get(dst, "access")
    iface = (src_if + " " + dst_if).lower()
    if "mgmt" in iface or "management" in iface:
        return "management"
    if s == "internet" or d == "internet" or s == "edge" or d == "edge":
        return "wan"
    if _medium_key(src_if, dst_if) in ("smf", "mmf"):
        return "fiber"
    if "core" in (s, d):
        return "core"
    return "lan"


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
    layer_of: dict[str, str] = {n["ip"]: _layer_of(n) for n in nodes}
    layers: dict[str, list[dict]] = {}
    for n in nodes:
        layers.setdefault(layer_of[n["ip"]], []).append(n)
    order = [k for k in LAYER_KEYS if k in layers]
    layer_idx = {k: i for i, k in enumerate(order)}
    for r in order:
        layers[r].sort(key=lambda n: (n.get("hostname") or n.get("ip") or ""))

    # Rows wrap downward: each layer occupies ceil(count / MAX_PER_ROW) rows
    # so wide layers flow down the sheet instead of sprawling sideways.
    rows_per_rank = {r: max(1, -(-len(layers[r]) // MAX_PER_ROW)) for r in order}
    widest = min(max((len(v) for v in layers.values()), default=1), MAX_PER_ROW)
    width = max(1150, MARGIN * 2 + widest * SLOT_W)
    content_top = MARGIN + HEADER_H

    # Fixed gap between layers - enough for connections to route cleanly
    TOP_GAP = BOTTOM_GAP = 24
    zone_gap: dict[str, float] = {}
    for i, r in enumerate(order):
        zone_gap[r] = 80  # Fixed gap between layers

    y_cursor = content_top + TOP_GAP
    for r in order:
        y_cursor += rows_per_rank[r] * ZONE_H + zone_gap[r]
    legend_y = y_cursor + 30
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
    rank_y: dict[str, float] = {}
    y_cursor = content_top + TOP_GAP
    for r in order:
        rank_y[r] = y_cursor
        y_cursor += rows_per_rank[r] * ZONE_H + zone_gap[r]

    pos: dict[str, tuple[float, float]] = {}   # ip -> glyph center (cx, cy)

    def assign(group: list[dict], base_y: float):
        for i, n in enumerate(group):
            row, col = divmod(i, MAX_PER_ROW)
            row_count = min(MAX_PER_ROW, len(group) - row * MAX_PER_ROW)
            x0 = (width - row_count * SLOT_W) / 2 + SLOT_W / 2
            pos[n["ip"]] = (x0 + col * SLOT_W, base_y + row * ZONE_H + ZONE_ROW_CY)

    for r in order:
        assign(layers[r], rank_y[r])

    # Barycenter sweeps: pull each device toward the average x of its
    # already-placed neighbours so connected devices end up adjacent and the
    # horizontal channels between them stay short (fewer crossings, shorter links).
    neigh: dict[str, list[str]] = {}
    for l in links:
        a, b = l.get("source"), l.get("target")
        if a in pos and b in pos:
            neigh.setdefault(a, []).append(b)
            neigh.setdefault(b, []).append(a)
    for _ in range(6):
        for r in order[1:]:
            def key(n, r=r):
                xs = [pos[m][0] for m in neigh.get(n["ip"], [])
                      if layer_idx.get(layer_of.get(m, ""), 0) < layer_idx[r] and m in pos]
                return sum(xs) / len(xs) if xs else pos[n["ip"]][0]
            layers[r].sort(key=key)
            assign(layers[r], rank_y[r])
    # A final downward pass lets lower layers respond to the refined upper layers.
    for r in reversed(order[:-1]):
        def key(n, r=r):
            xs = [pos[m][0] for m in neigh.get(n["ip"], [])
                  if layer_idx.get(layer_of.get(m, ""), 0) > layer_idx[r] and m in pos]
            return sum(xs) / len(xs) if xs else pos[n["ip"]][0]
        layers[r].sort(key=key)
        assign(layers[r], rank_y[r])

    # --- links (orthogonal elbows, port labels, medium colors) ------------
    dt_by_ip = {n["ip"]: (n.get("device_type") or "").lower() for n in nodes}

    # Precompute device shape half-height so icon-driven and generic devices
    # use the same attachment surface during link layout and rendering.
    # Each entry: (half_w, half_h, kind, icon_path, top_pad, bot_pad, left_pad, right_pad)
    # pads are the transparent-padding distance (scene pt) from the image-box
    # edge to the *visible* graphic edge, so connectors land on the graphic.
    device_shape: dict[str, tuple[float, float, str, str | None, float, float, float, float]] = {}
    for n in nodes:
        ip = n["ip"]
        dt = dt_by_ip.get(ip, "")
        hn = (n.get("hostname") or "").split(".")[0]
        model = n.get("model") or ""
        icon_path = _icon_path(dt, model, hn)
        kind = _icon_kind(dt, model, hn)
        if icon_path:
            if kind == "ap":
                w, h = _icon_size(icon_path, 64, 64)
            elif kind == "router":
                w, h = _icon_size(icon_path, 120, 70)
            else:
                w, h = _icon_size(icon_path, 170, 34)
            itf, ibf, ilf, irf = _icon_visible_insets(icon_path)
            tp, bp, lp, rp = itf * h, ibf * h, ilf * w, irf * w
        elif "router" in dt:
            w, h = CLOUD_W, CLOUD_H
            tp = bp = lp = rp = 0.0
        elif dt == "unknown" and not model and not hn:
            w, h = UNKNOWN_W, UNKNOWN_H
            tp = bp = lp = rp = 0.0
        else:
            w, h = GLYPH_W, GLYPH_H
            tp = bp = lp = rp = 0.0
        device_shape[ip] = (w / 2, h / 2, kind, icon_path, tp, bp, lp, rp)

    _DFLT = (GLYPH_W / 2, GLYPH_H / 2, "unknown", None, 0.0, 0.0, 0.0, 0.0)

    def half_h(ip: str) -> float:
        return device_shape.get(ip, _DFLT)[1]

    def half_w(ip: str) -> float:
        return device_shape.get(ip, _DFLT)[0]

    # Distances from the device center to the *visible* graphic edges -- used
    # so connector endpoints sit on the icon graphic, not in its transparent
    # margin, and so the Visio glue box wraps the visible region.
    def top_edge(ip: str) -> float:
        s = device_shape.get(ip, _DFLT)
        return s[1] - s[4]

    def bot_edge(ip: str) -> float:
        s = device_shape.get(ip, _DFLT)
        return s[1] - s[5]

    def half_w_vis(ip: str) -> float:
        s = device_shape.get(ip, _DFLT)
        return max(8.0, s[0] - s[6] - s[7])

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
        hw = half_w_vis(ip)
        idx = group.index(li)
        step = min(12.0, 2 * hw / (n - 1))
        return cx - hw + idx * step

    # Build attachment lists for fan-out
    attach: dict[str, dict[str, list[int]]] = {}
    for li, l in enumerate(valid):
        a, b = l["source"], l["target"]
        ya = pos[a][1]
        yb = pos[b][1]
        if abs(ya - yb) < 1:
            # Same row - attach to top of both
            attach.setdefault(a, {}).setdefault("top", []).append(li)
            attach.setdefault(b, {}).setdefault("top", []).append(li)
        else:
            # Different rows - upper gets bottom, lower gets top
            if ya < yb:
                upper, lower = a, b
            else:
                upper, lower = b, a
            attach.setdefault(upper, {}).setdefault("bottom", []).append(li)
            attach.setdefault(lower, {}).setdefault("top", []).append(li)

    # Simple direct connections between devices.
    # Links spanning more than one layer are routed down a dedicated vertical
    # "spine" on the right of the sheet so their long vertical run never
    # crosses the intermediate layers' own links.
    spine_x = max((cx + half_w(ip) for ip, (cx, _cy) in pos.items()), default=width - MARGIN) + 46
    spine_used = 0
    pair_count: dict[tuple, int] = {}
    src_count: dict[str, int] = {}
    tgt_count: dict[str, int] = {}
    for li, l in enumerate(valid):
        a, b = l["source"], l["target"]
        x1, y1 = pos[a]
        x2, y2 = pos[b]
        color = C_LINK
        if color_links:
            role = _link_color_key(a, b, layer_of,
                                   l.get("source_interface", ""), l.get("target_interface", ""))
            if legend_color.get(role):
                color = legend_color[role]

        ia_s = _shorten_interface(l.get("source_interface") or "")
        ib_s = _shorten_interface(l.get("target_interface") or "")

        pair = tuple(sorted((a, b)))
        dup = pair_count.get(pair, 0)
        pair_count[pair] = dup + 1
        s_idx = src_count.get(a, 0)
        src_count[a] = s_idx + 1
        t_idx = tgt_count.get(b, 0)
        tgt_count[b] = t_idx + 1

        # Determine upper/lower device
        if abs(y1 - y2) < 1:
            # Same row - simple horizontal or vertical connection
            sax = attach_x(a, "top", li)
            tax = attach_x(b, "top", li)
            cy = y1 - 40  # Channel above the row
            pts = [(sax, y1 - 20), (sax, cy), (tax, cy), (tax, y2 - 20)]
            a_label, b_label = ia_s, ib_s
            a_pos = (sax + 4, cy - 14)
            b_pos = (tax + 4, cy - 14)
            a_align = b_align = "left"
        elif y1 < y2:
            # Different rows - a is upper, b is lower
            la, lb = layer_of.get(a, ""), layer_of.get(b, "")
            sax = attach_x(a, "bottom", li)
            tax = attach_x(b, "top", li)
            if layer_idx.get(la, 0) + 1 < layer_idx.get(lb, 0):
                # Multi-layer: route down the side spine to avoid crossings.
                # Horizontal runs ride exactly along the device-row edges so
                # they only graze (never cross) the shorter links' verticals.
                sx = spine_x + spine_used * 12
                spine_used += 1
                y_top = y1 + bot_edge(a)
                y_bot = y2 - top_edge(b)
                pts = [(sax, y_top), (sx, y_top), (sx, y_bot), (tax, y_bot)]
                a_label, b_label = ia_s, ib_s
                a_pos = (sax + 4, y_top - 12); a_align = "left"
                b_pos = (tax - 4, y_bot - 12); b_align = "right"
            else:
                cy = (y1 + bot_edge(a) + y2 - top_edge(b)) / 2
                off = dup * 10 + max(s_idx, t_idx) * 8
                cy += off
                pts = [(sax, y1 + bot_edge(a)),
                       (sax, cy),
                       (tax, cy),
                       (tax, y2 - top_edge(b))]
                a_label, b_label = ia_s, ib_s
                if tax >= sax:
                    a_pos = (sax - 4, cy - 13); a_align = "right"
                    b_pos = (tax + 4, cy - 13); b_align = "left"
                else:
                    a_pos = (sax + 4, cy - 13); a_align = "left"
                    b_pos = (tax - 4, cy - 13); b_align = "right"
        else:
            # Different rows - b is upper, a is lower
            la, lb = layer_of.get(a, ""), layer_of.get(b, "")
            sax = attach_x(b, "bottom", li)
            tax = attach_x(a, "top", li)
            if layer_idx.get(lb, 0) + 1 < layer_idx.get(la, 0):
                # Multi-layer: route down the side spine to avoid crossings
                sx = spine_x + spine_used * 12
                spine_used += 1
                y_top = y2 + bot_edge(b)
                y_bot = y1 - top_edge(a)
                pts = [(sax, y_top), (sx, y_top), (sx, y_bot), (tax, y_bot)]
                a_label, b_label = ib_s, ia_s
                a_pos = (tax - 4, y_bot - 12); a_align = "right"
                b_pos = (sax + 4, y_top - 12); b_align = "left"
            else:
                cy = (y2 + bot_edge(b) + y1 - top_edge(a)) / 2
                off = dup * 10 + max(s_idx, t_idx) * 8
                cy += off
                pts = [(sax, y2 + bot_edge(b)),
                       (sax, cy),
                       (tax, cy),
                       (tax, y1 - top_edge(a))]
                a_label, b_label = ib_s, ia_s
                if tax >= sax:
                    a_pos = (tax + 4, cy - 13); a_align = "left"
                    b_pos = (sax - 4, cy - 13); b_align = "right"
                else:
                    a_pos = (tax - 4, cy - 13); a_align = "right"
                    b_pos = (sax + 4, cy - 13); b_align = "left"

        scene.line(pts, color=color, width=1.4, tag="link")
        if a_label:
            scene.text(a_pos[0], a_pos[1], a_label, size=8, bold=True,
                       color=C_PORT, align=a_align, tag="link")
        if b_label:
            scene.text(b_pos[0], b_pos[1], b_label, size=8, bold=True,
                       color=C_PORT, align=b_align, tag="link")
        scene.vlinks.append({"a": a, "b": b, "color": color, "width": 1.4,
                             "src_if": a_label, "dst_if": b_label,
                             "pts": pts,
                             "src_label_pos": a_pos, "dst_label_pos": b_pos,
                             "src_align": a_align, "dst_align": b_align,
                             "ax": pos[a][0], "ay": pos[a][1],
                             "bx": pos[b][0], "by": pos[b][1]})

    # --- node glyphs + label stacks ---------------------------------------
    for r in order:
        for n in layers[r]:
            cx, cy = pos[n["ip"]]
            hn = (n.get("hostname") or "").split(".")[0] or n.get("ip") or ""
            model = n.get("model") or ""
            ip = n.get("ip") or ""
            dt = (n.get("device_type") or "").lower()
            tag = ("dev", ip)
            _, _, icon_kind, icon_path = device_shape.get(ip, _DFLT)[:4]

            if icon_path:
                # icon-driven device; label stack sits below the icon
                # use the same size computed during link layout
                iw, ih = device_shape[ip][0] * 2, device_shape[ip][1] * 2
                _tp, _bp, _lp, _rp = device_shape[ip][4], device_shape[ip][5], device_shape[ip][6], device_shape[ip][7]
                labels: list[tuple] = []
                ly = cy + ih / 2 + 8
                scene.text(cx, ly, hn, size=9, bold=True, tag=tag)
                labels.append((hn, 9, True, C_TEXT)); ly += 12
                if model:
                    scene.text(cx, ly, model, size=8, tag=tag)
                    labels.append((model, 8, False, C_TEXT)); ly += 11
                if ip:
                    scene.text(cx, ly, ip, size=8, tag=tag)
                    labels.append((ip, 8, False, C_TEXT))
                scene.image(cx - iw / 2, cy - ih / 2, iw, ih, icon_path, tag=tag)
                scene.devices.append({
                    "ip": ip, "cx": cx, "cy": cy, "kind": icon_kind,
                    "icon_path": icon_path, "icon_w": iw, "icon_h": ih,
                    "pad": (_tp, _bp, _lp, _rp),
                    "labels": labels,
                })
            elif "router" in dt:
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
                labels.reverse()   # top-to-bottom order
                is_endpoint = layer_of.get(ip, "endpoint") == "endpoint"
                if is_endpoint:
                    # plain endpoint box (printers/clients/Meraki devices with
                    # no icon) -- not a switch faceplate
                    scene.rect(cx - GLYPH_W / 2, cy - GLYPH_H / 2, GLYPH_W, GLYPH_H,
                               fill=C_UNKNOWN, stroke=C_GLYPH_TICK, sw=0.75, tag=tag)
                    scene.devices.append({
                        "ip": ip, "cx": cx, "cy": cy, "kind": "unknown",
                        "labels": labels,
                    })
                else:
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
    # The whole block is inset from the left frame edge so the legend sits
    # clear of the border instead of being flush against it.
    bx = MARGIN + 24
    bw = (width - MARGIN / 2) - bx
    by = legend_y
    scene.rect(bx, by, bw, LEGEND_H, sw=1.2)
    c1 = bx + 210
    c2 = c1 + 300
    scene.line([(c1, by), (c1, by + LEGEND_H)], color=C_FRAME, width=1.0)
    scene.line([(c2, by), (c2, by + LEGEND_H)], color=C_FRAME, width=1.0)

    # legend swatches, centered horizontally within the column so the writing
    # sits in the middle of its box instead of hugging the left edge
    def _tw(s: str, size: float) -> float:
        return len(s) * size * 0.62

    max_lw = max((_tw(e.get("label") or "", 8.5) for e in legend), default=0.0)
    col_w = c1 - bx
    swatch_w = 48.0
    gap = 8.0
    off = max(0.0, (col_w - (swatch_w + gap + max_lw)) / 2)
    scene.text((bx + c1) / 2, by + 8, "LEGEND", size=9, bold=True, align="center")
    ey = by + 28
    for e in legend:
        scene.rect(bx + off, ey + 3, swatch_w, 5,
                   fill=e.get("color") or C_LINK, stroke=None, sw=0)
        scene.text(bx + off + swatch_w + gap, ey, e.get("label") or "", size=8.5, align="left")
        ey += 16

    # small Amtrak logo centered above the proprietary notice
    lw = 64.0
    lh = lw * 394.0 / 700.0
    mid_x = c1 + (c2 - c1) / 2
    notice = PROPRIETARY.split("\n")
    start_y = by + max(6, (LEGEND_H - lh - 10 - len(notice) * 13) / 2)
    if os.path.exists(ASSET_LOGO):
        scene.image(mid_x - lw / 2, start_y, lw, lh, ASSET_LOGO)
    text_y = start_y + lh + 10
    for i, ln in enumerate(notice):
        scene.text(mid_x, text_y + i * 13, ln, size=9, bold=True, italic=True, align="center")

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
            scene.text(c2 + j * cw + cw / 2, ry + rh / 2 - 4, label + val, size=9, align="center")

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
            if p["path"].lower().endswith(".svg"):
                data = _icon_png_bytes(p["path"], (int(p["w"]), int(p["h"])))
                img = ImageReader(io.BytesIO(data)) if data else None
            else:
                img = ImageReader(p["path"])
            if img:
                c.drawImage(img, p["x"], fy(p["y"] + p["h"]),
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


def _rgb_formula(color: str) -> str:
    """'#1E88E5' -> 'RGB(30,136,229)' for use inside ShapeSheet formulas."""
    r, g, b = _hex(color)
    return f"RGB({r},{g},{b})"


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
                if p["path"].lower().endswith(".svg"):
                    data = _icon_png_bytes(p["path"], (int(s(p["w"])), int(s(p["h"]))))
                    logo = Image.open(io.BytesIO(data)).convert("RGBA") if data else None
                else:
                    logo = Image.open(p["path"]).convert("RGBA")
                if logo:
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


def _geom_foreign(w: float, h: float) -> str:
    """Geometry for a Foreign (image) shape. Matches the structure Visio emits
    for pictures: a rectangle outline plus NoFill/NoLine/NoShow flags so the
    image shape has a real geometry path (required for Visio to draw it)."""
    return (
        '<Section N="Geometry" IX="0">'
        '<Cell N="NoFill" V="1"/><Cell N="NoLine" V="1"/><Cell N="NoShow" V="0"/>'
        '<Cell N="NoSnap" V="0"/><Cell N="NoQuickDrag" V="0"/>'
        '<Row T="MoveTo" IX="1"><Cell N="X" V="0" F="Width*0"/><Cell N="Y" V="0" F="Height*0"/></Row>'
        f'<Row T="LineTo" IX="2"><Cell N="X" V="{w:.4f}" F="Width*1"/><Cell N="Y" V="0" F="Height*0"/></Row>'
        f'<Row T="LineTo" IX="3"><Cell N="X" V="{w:.4f}" F="Width*1"/><Cell N="Y" V="{h:.4f}" F="Height*1"/></Row>'
        f'<Row T="LineTo" IX="4"><Cell N="X" V="0" F="Width*0"/><Cell N="Y" V="{h:.4f}" F="Height*1"/></Row>'
        f'<Row T="LineTo" IX="5"><Cell N="X" V="0" F="Width*0"/><Cell N="Y" V="0" F="Height*0"/></Row>'
        '</Section>'
    )


def _connector_1d(sid: int, pts: list[tuple[float, float]],
                  color: str, width_pt: float) -> str:
    """Orthogonal 1-D connector. Points are already in scene inches (Visio
    y-up). A 1-D shape's local frame runs from (0,0) at Begin to
    (Width,Height) at End; Width and Height are SIGNED (= End - Begin) so the
    frame points from Begin toward End no matter the direction. Geometry
    coordinates are expressed relative to the Begin point (lx = x - bx,
    ly = y - by), which keeps the polyline exact for connectors that run left
    or up as well as right/down."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    bx, by = xs[0], ys[0]
    ex, ey = xs[-1], ys[-1]
    w, h = ex - bx, ey - by           # signed: lets the formulas below place
    pinx, piny = (bx + ex) / 2, (by + ey) / 2   # Begin/End correctly either direction
    geom_rows = [
        '<Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>'
    ]
    for i, (x, y) in enumerate(pts[1:], start=2):
        geom_rows.append(
            f'<Row T="LineTo" IX="{i}"><Cell N="X" V="{x - bx:.4f}"/><Cell N="Y" V="{y - by:.4f}"/></Row>'
        )
    return (
        f'<Shape ID="{sid}" Type="Shape">'
        f'<Cell N="PinX" V="{pinx:.4f}"/><Cell N="PinY" V="{piny:.4f}"/>'
        f'<Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/>'
        f'<Cell N="LocPinX" V="{w / 2:.4f}" F="Width*0.5"/>'
        f'<Cell N="LocPinY" V="{h / 2:.4f}" F="Height*0.5"/>'
        f'<Cell N="BeginX" V="{bx:.4f}" F="PinX-Width*0.5"/>'
        f'<Cell N="BeginY" V="{by:.4f}" F="PinY-Height*0.5"/>'
        f'<Cell N="EndX" V="{ex:.4f}" F="PinX+Width*0.5"/>'
        f'<Cell N="EndY" V="{ey:.4f}" F="PinY+Height*0.5"/>'
        # Right-click -> "Highlight"/"Clear highlight" flips a user cell that
        # the LineColor/LineWeight formulas read, so a connector can be made
        # thick amber on demand to trace where a device connects. Macro-free.
        f'<Cell N="LineColor" V="{color}" F="IF(User.Highlight,RGB(255,193,7),{_rgb_formula(color)})"/>'
        f'<Cell N="LineWeight" V="{width_pt / 72:.4f}" F="IF(User.Highlight,0.0694,{width_pt / 72:.4f})"/>'
        '<Cell N="FillPattern" V="0"/><Cell N="OneD" V="1"/>'
        '<Cell N="GlueType" V="2"/>'          # glue to whole shape
        '<Section N="User"><Row N="Highlight"><Cell N="Value" V="0"/></Row></Section>'
        '<Section N="Actions">'
        '<Row IX="0"><Cell N="Action" V="1" F="SETF(GetRef(User.Highlight),1)"/><Cell N="Menu" V="Highlight"/></Row>'
        '<Row IX="1"><Cell N="Action" V="0" F="SETF(GetRef(User.Highlight),0)"/><Cell N="Menu" V="Clear highlight"/></Row>'
        '</Section>'
        '<Section N="Geometry" IX="0">'
        + "".join(geom_rows)
        + '</Section></Shape>'
    )


def _static_line(sid: int, pts: list[tuple[float, float]],
                 color: str, width_pt: float) -> str:
    (bx, by), (ex, ey) = pts[0], pts[-1]
    pinx, piny = (bx + ex) / 2, (by + ey) / 2
    w, h = ex - bx, ey - by
    geom = ('<Section N="Geometry" IX="0">'
            '<Row T="MoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>'
            f'<Row T="LineTo" IX="2"><Cell N="X" V="{w:.4f}"/><Cell N="Y" V="{h:.4f}"/></Row>'
            '</Section>')
    return (
        f'<Shape ID="{sid}" Type="Shape">'
        f'<Cell N="PinX" V="{pinx:.4f}"/><Cell N="PinY" V="{piny:.4f}"/>'
        f'<Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/>'
        f'<Cell N="LocPinX" V="{w / 2:.4f}" F="Width*0.5"/>'
        f'<Cell N="LocPinY" V="{h / 2:.4f}" F="Height*0.5"/>'
        f'<Cell N="LineColor" V="{color}"/>'
        f'<Cell N="LineWeight" V="{width_pt / 72:.4f}"/>'
        '<Cell N="FillPattern" V="0"/>'
        + geom + '</Shape>'
    )


def _polyline_2d(sid: int, pts: list[tuple[float, float]],
                 color: str, width_pt: float) -> str:
    """Render a multi-point link as a plain 2-D shape. 2-D geometry uses the
    standard (non-rotated) local frame, exactly like the device glyphs that
    already render correctly in Visio, so the polyline lands precisely where
    intended. Points are in page inches (y-up)."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    w = max(maxx - minx, 0.01)
    h = max(maxy - miny, 0.01)
    pinx = (minx + maxx) / 2
    piny = (miny + maxy) / 2
    rows = []
    for i, (x, y) in enumerate(pts, start=1):
        t = "MoveTo" if i == 1 else "LineTo"
        rows.append(
            f'<Row T="{t}" IX="{i}"><Cell N="X" V="{x - minx:.4f}"/><Cell N="Y" V="{y - miny:.4f}"/></Row>'
        )
    return (
        f'<Shape ID="{sid}" Type="Shape">'
        f'<Cell N="PinX" V="{pinx:.4f}"/><Cell N="PinY" V="{piny:.4f}"/>'
        f'<Cell N="Width" V="{w:.4f}"/><Cell N="Height" V="{h:.4f}"/>'
        f'<Cell N="LocPinX" V="{w / 2:.4f}" F="Width*0.5"/>'
        f'<Cell N="LocPinY" V="{h / 2:.4f}" F="Height*0.5"/>'
        f'<Cell N="LineColor" V="{color}"/>'
        f'<Cell N="LineWeight" V="{width_pt / 72:.4f}"/>'
        '<Cell N="FillPattern" V="0"/><Cell N="LinePattern" V="1"/>'
        '<Section N="Geometry" IX="0">'
        + "".join(rows)
        + '</Section></Shape>'
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
    h_in = size_pt * 1.6 / 72
    align = p.get("align", "center")
    # The text box is centered on its PinX; offset it so the text's anchor
    # (left/center/right) lands exactly on p["x"].
    if align == "left":
        pinx = (p["x"] - ox) / 72 + w_in / 2
    elif align == "right":
        pinx = (p["x"] - ox) / 72 - w_in / 2
    else:
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
            pts = [(x / 72, flip_y(y)) for x, y in p["pts"]]
            shapes.append(_static_line(sid, pts, p["color"], p["width"]))
            sid += 1
        elif k == "text":
            shapes.append(_vsdx_text(sid, p, H))
            sid += 1
        elif k == "image":
            emf, ext_w, ext_h = _read_emf_for_image(p["path"])
            if emf is None:
                try:
                    with open(p["path"], "rb") as fh:
                        data = fh.read()
                except OSError:
                    continue
                emf = _png_to_emf(data)
                if emf is None:
                    continue
                ext_w, ext_h = _emf_extent(emf)
            if ext_w <= 0:
                continue
            rid = f"rId{len(media) + 1}"
            media.append((f"visio/media/image{len(media) + 1}.emf", emf))
            rels.append(f'<Relationship Id="{rid}" '
                        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                        f'Target="../media/image{len(media)}.emf"/>')
            w, h = p["w"] / 72, p["h"] / 72
            shapes.append(
                f'<Shape ID="{sid}" Type="Foreign">'
                + _xform((p["x"] + p["w"] / 2) / 72, flip_y(p["y"] + p["h"] / 2), w, h)
                + f'<Cell N="ImgWidth" V="{w:.4f}" F="Width*1"/>'
                + f'<Cell N="ImgHeight" V="{h:.4f}" F="Height*1"/>'
                + '<Cell N="ImgOffsetX" V="0"/><Cell N="ImgOffsetY" V="0"/>'
                + '<Cell N="ClippingPath" V=""/>'
                + '<Cell N="FillPattern" V="0"/><Cell N="LinePattern" V="0"/>'
                + _geom_foreign(w, h)
                + f'<ForeignData ForeignType="EnhMetaFile" MappingMode="8" '
                + f'ExtentX="{ext_w}" ExtentY="{ext_h}">'
                + f'<Rel r:id="{rid}"/>'
                + '</ForeignData></Shape>')
            sid += 1

    # --- devices: one draggable group per device ---------------------------
    dev_shape_id: dict[str, int] = {}
    for dev in scene.devices:
        kind = dev["kind"]
        cx, cy = dev["cx"], dev["cy"]
        labels = dev.get("labels", [])
        icon_path = dev.get("icon_path")
        icon_w = dev.get("icon_w", 0)
        icon_h = dev.get("icon_h", 0)
        # bounding box of the group in scene coords (y-down). For icon devices the
        # box wraps the *visible* graphic (transparent padding trimmed away)
        # so glued connector endpoints land on the visible edge -- no gap --
        # while the full padded icon image is drawn behind it centered on the
        # device, its empty margin overflowing the box invisibly.
        if icon_path:
            label_w = max((len(t) * s * 0.62 for t, s, _, _ in labels), default=0)
            tp, bp, lp, rp = dev.get("pad", (0.0, 0.0, 0.0, 0.0))
            bw = max(icon_w - lp - rp, label_w)
            bh = icon_h - tp - bp
            gy0 = cy - icon_h / 2 + tp           # visible top edge
            gx0 = cx - icon_w / 2 + lp            # visible left edge
        elif kind == "cloud":
            bw, bh = CLOUD_W, CLOUD_H
            gy0 = cy - bh / 2
            gx0 = cx - bw / 2
        elif kind == "unknown":
            bw, bh = UNKNOWN_W, UNKNOWN_H
            gy0 = cy - bh / 2
            gx0 = cx - bw / 2
        else:
            label_w = max((len(t) * s * 0.62 for t, s, _, _ in labels), default=0)
            bw = max(GLYPH_W, label_w)
            bh = GLYPH_H
            gy0 = cy - GLYPH_H / 2
            gx0 = cx - bw / 2
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

        if icon_path:
            emf, ext_w, ext_h = _read_emf_for_image(icon_path)
            if emf is None:
                data = _icon_png_bytes(icon_path, (int(icon_w), int(icon_h)))
                if data:
                    emf = _png_to_emf(data)
                    if emf is not None:
                        ext_w, ext_h = _emf_extent(emf)
            if emf is not None and ext_w > 0:
                rid = f"rId{len(media) + 1}"
                media.append((f"visio/media/image{len(media) + 1}.emf", emf))
                rels.append(f'<Relationship Id="{rid}" '
                            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                            f'Target="../media/image{len(media)}.emf"/>')
                w_in, h_in = icon_w / 72, icon_h / 72
                cx_l, cy_l = to_local(cx, cy)
                children.append(
                    f'<Shape ID="{sid}" Type="Foreign">'
                    + _xform(cx_l, cy_l, w_in, h_in)
                    + f'<Cell N="ImgWidth" V="{w_in:.4f}" F="Width*1"/>'
                    + f'<Cell N="ImgHeight" V="{h_in:.4f}" F="Height*1"/>'
                    + '<Cell N="ImgOffsetX" V="0"/><Cell N="ImgOffsetY" V="0"/>'
                    + '<Cell N="ClippingPath" V=""/>'
                    + '<Cell N="FillPattern" V="0"/><Cell N="LinePattern" V="0"/>'
                    + _geom_foreign(w_in, h_in)
                    + f'<ForeignData ForeignType="EnhMetaFile" MappingMode="8" '
                    + f'ExtentX="{ext_w}" ExtentY="{ext_h}">'
                    + f'<Rel r:id="{rid}"/>'
                    + '</ForeignData></Shape>')
                sid += 1
        elif kind == "cloud":
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
            h_in = size_pt * 1.6 / 72
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

    # --- links: plain 2-D polylines (renders reliably in Visio) ------------
    for vl in scene.vlinks:
        pts = [(x / 72, flip_y(y)) for x, y in vl["pts"]]
        cid = sid
        sid += 1
        shapes.append(_polyline_2d(cid, pts, vl["color"], vl["width"]))
        # port labels as free text near the endpoints
        for txt, (px, py), anch, al in (
            (vl["src_if"], vl["src_label_pos"], "begin", vl.get("src_align", "left")),
            (vl["dst_if"], vl["dst_label_pos"], "end", vl.get("dst_align", "left")),
        ):
            if not txt:
                continue
            size_pt = 7.0
            w_in = max(0.3, len(txt) * size_pt * 0.62 / 72)
            h_in = size_pt * 1.6 / 72
            p = {"v": txt, "size": size_pt, "bold": False, "italic": False,
                 "color": C_PORT, "align": al}
            # text baseline sits just above/below the elbow so it is legible
            y_in = flip_y(py) - (0.10 if anch == "end" else -0.06)
            if al == "left":
                pinx = px / 72 + w_in / 2
            elif al == "right":
                pinx = px / 72 - w_in / 2
            else:
                pinx = px / 72
            shapes.append(
                f'<Shape ID="{sid}" Type="Shape">'
                + _xform(pinx, y_in, w_in, h_in)
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
<Default Extension="emf" ContentType="image/x-emf"/>
<Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>
<Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>
<Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>
<Override PartName="/visio/windows.xml" ContentType="application/vnd.ms-visio.windows+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''
    core_props = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Amtrak Network Diagram</dc:title><dc:creator>Amtrak</dc:creator>
<cp:lastModifiedBy>Amtrak</cp:lastModifiedBy>
</cp:coreProperties>'''
    app_props = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>Microsoft Visio</Application><AppVersion>16.0</AppVersion>
</Properties>'''
    doc_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xml:space="preserve">
<DocumentSettings TopPage="0" DefaultTextStyle="3" DefaultLineStyle="3" DefaultFillStyle="3" DefaultGuideStyle="4">
<GlueSettings>9</GlueSettings><SnapSettings>65847</SnapSettings><SnapExtensions>34</SnapExtensions><SnapAngles/>
<DynamicGridEnabled>1</DynamicGridEnabled><ProtectStyles>0</ProtectStyles><ProtectShapes>0</ProtectShapes><ProtectMasters>0</ProtectMasters><ProtectBkgnds>0</ProtectBkgnds>
</DocumentSettings>
<Colors/>
<FaceNames/>
<StyleSheets>
<StyleSheet ID="0" NameU="No Style" Name="No Style"/>
<StyleSheet ID="1" NameU="Normal" Name="Normal"/>
<StyleSheet ID="2" NameU="Text Only" Name="Text Only"/>
<StyleSheet ID="3" NameU="No Line" Name="No Line"/>
<StyleSheet ID="4" NameU="Guide" Name="Guide"/>
</StyleSheets>
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
        z.writestr("visio/document.xml", doc_xml)
        z.writestr("visio/_rels/document.xml.rels", doc_rels)
        z.writestr("visio/windows.xml", windows_xml)
        z.writestr("visio/pages/pages.xml", pages_xml)
        z.writestr("visio/pages/_rels/pages.xml.rels", pages_rels)
        z.writestr("visio/pages/page1.xml", page1_xml)
        if rels:
            z.writestr("visio/pages/_rels/page1.xml.rels", page1_rels)
        z.writestr("docProps/core.xml", core_props)
        z.writestr("docProps/app.xml", app_props)
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
