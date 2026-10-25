"""Wetter-Icons, mit PIL-Grundformen gezeichnet (skalierbar, rein schwarz/weiß).

Wettercodes nach WMO 4677, wie sie Open-Meteo für ICON-D2 liefert.
"""
import math

BLACK = 0
WHITE = 255

DESCRIPTIONS = {
    0: "Klar", 1: "Überwiegend klar", 2: "Teils bewölkt", 3: "Bedeckt",
    45: "Nebel", 48: "Nebel mit Reif",
    51: "Leichter Niesel", 53: "Nieselregen", 55: "Starker Niesel",
    56: "Gefrierender Niesel", 57: "Gefrierender Niesel",
    61: "Leichter Regen", 63: "Regen", 65: "Starker Regen",
    66: "Gefrierender Regen", 67: "Gefrierender Regen",
    71: "Leichter Schneefall", 73: "Schneefall", 75: "Starker Schneefall",
    77: "Schneegriesel",
    80: "Leichte Schauer", 81: "Regenschauer", 82: "Starke Schauer",
    85: "Schneeschauer", 86: "Starke Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "Gewitter mit Hagel",
}


def describe(code):
    return DESCRIPTIONS.get(code, f"Wettercode {code}")


def _kind(code):
    if code == 0:
        return "clear"
    if code in (1, 2):
        return "partly"
    if code == 3:
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 57:
        return "drizzle"
    if 61 <= code <= 67:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if 80 <= code <= 82:
        return "showers"
    if code >= 95:
        return "thunder"
    return "cloudy"


def _sun(draw, cx, cy, r, lw):
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=BLACK)
    for i in range(8):
        a = i * math.pi / 4
        x1, y1 = cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35
        x2, y2 = cx + math.cos(a) * r * 1.85, cy + math.sin(a) * r * 1.85
        draw.line((x1, y1, x2, y2), fill=BLACK, width=lw)


def _moon(draw, cx, cy, r):
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=BLACK)
    o = r * 0.55
    draw.ellipse((cx - r + o, cy - r - o * 0.5, cx + r + o, cy + r - o * 0.5), fill=WHITE)


def _cloud(draw, x, y, w, h, lw, fill=WHITE):
    """Wolke im Rechteck (x, y, w, h) mit schwarzer Kontur der Breite ``lw``."""
    def parts(grow):
        g = grow
        return [
            ("e", (x + w * 0.06 - g, y + h * 0.42 - g, x + w * 0.46 + g, y + h * 0.98 + g)),
            ("e", (x + w * 0.26 - g, y + h * 0.04 - g, x + w * 0.74 + g, y + h * 0.80 + g)),
            ("e", (x + w * 0.56 - g, y + h * 0.36 - g, x + w * 0.96 + g, y + h * 0.98 + g)),
            ("r", (x + w * 0.24, y + h * 0.60 - g, x + w * 0.78, y + h * 0.98 + g)),
        ]
    for color, grow in ((BLACK, 0), (fill, -lw)):
        for kind, box in parts(grow):
            if kind == "e":
                draw.ellipse(box, fill=color)
            else:
                draw.rectangle(box, fill=color)


def _rain(draw, x, y, w, h, lw, n=3):
    for i in range(n):
        px = x + w * (i + 0.5) / n
        draw.line((px + h * 0.25, y, px - h * 0.25, y + h), fill=BLACK, width=lw)


def _drizzle(draw, x, y, w, h, lw, n=3):
    r = max(1.5, lw * 0.8)
    for i in range(n):
        px = x + w * (i + 0.5) / n
        for py in (y + h * 0.2, y + h * 0.8):
            off = h * 0.12 if py > y + h / 2 else 0
            draw.ellipse((px - off - r, py - r, px - off + r, py + r), fill=BLACK)


def _snow(draw, x, y, w, h, lw, n=3):
    s = min(h, w / n) * 0.42
    for i in range(n):
        cx = x + w * (i + 0.5) / n
        cy = y + h * (0.35 if i % 2 == 0 else 0.65)
        for k in range(3):
            a = k * math.pi / 3 + math.pi / 2
            dx, dy = math.cos(a) * s, math.sin(a) * s
            draw.line((cx - dx, cy - dy, cx + dx, cy + dy), fill=BLACK, width=max(1, lw - 1))


def _bolt(draw, x, y, w, h):
    pts = [(0.55, 0.0), (0.15, 0.55), (0.45, 0.55), (0.30, 1.0), (0.85, 0.40), (0.55, 0.40), (0.75, 0.0)]
    draw.polygon([(x + px * w, y + py * h) for px, py in pts], fill=BLACK)


def draw_icon(draw, code, x, y, size, is_day=True):
    """Zeichnet das Icon zum Wettercode in das Quadrat (x, y, size)."""
    s = size
    lw = max(2, round(s / 22))
    kind = _kind(code)

    def sky(cx, cy, r):
        if is_day:
            _sun(draw, cx, cy, r, lw)
        else:
            _moon(draw, cx, cy, r * 1.25)

    if kind == "clear":
        sky(x + s / 2, y + s / 2, s * 0.22)
        return
    if kind == "fog":
        _cloud(draw, x + s * 0.1, y + s * 0.08, s * 0.8, s * 0.5, lw)
        for i, (a, b) in enumerate(((0.1, 0.8), (0.2, 0.9), (0.05, 0.7))):
            py = y + s * (0.68 + i * 0.12)
            draw.line((x + s * a, py, x + s * b, py), fill=BLACK, width=lw)
        return

    with_sky = kind in ("partly", "showers")
    if with_sky:
        sky(x + s * 0.34, y + s * 0.3, s * 0.15)
    precip = kind not in ("partly", "cloudy")
    if precip:
        cx, cy, cw, ch = x + s * 0.08, y + s * 0.12, s * 0.84, s * 0.54
    elif with_sky:
        cx, cy, cw, ch = x + s * 0.18, y + s * 0.34, s * 0.8, s * 0.52
    else:
        cx, cy, cw, ch = x + s * 0.05, y + s * 0.2, s * 0.9, s * 0.6
    if with_sky and precip:
        cx, cy = x + s * 0.16, y + s * 0.24
        cw, ch = s * 0.8, s * 0.48
    _cloud(draw, cx, cy, cw, ch, lw)

    px, pw = cx + cw * 0.18, cw * 0.66
    py = cy + ch + s * 0.05
    ph = y + s - py - s * 0.02
    if kind in ("rain", "showers"):
        _rain(draw, px, py, pw, ph, lw)
    elif kind == "drizzle":
        _drizzle(draw, px, py, pw, ph, lw)
    elif kind == "snow":
        _snow(draw, px, py, pw, ph, lw)
    elif kind == "thunder":
        _bolt(draw, cx + cw * 0.32, cy + ch * 0.55, cw * 0.36, y + s - (cy + ch * 0.55))
