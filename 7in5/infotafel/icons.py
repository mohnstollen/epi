"""Icons, mit PIL-Grundformen gezeichnet (skalierbar, rein schwarz/weiß).

Wetter-Icons nach WMO-Code 4677 (wie Open-Meteo sie liefert; übernommen aus
dashboard/icons.py), dazu kleine Symbole für die Ansichten.
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
            ("r", (x + w * 0.24, y + h * (0.60 if g >= 0 else 0.50), x + w * 0.78, y + h * 0.98 + g)),
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


# --- Symbole für die Ansichten ---------------------------------------------------
# Alle zeichnen in das Quadrat (x, y, s) in der Farbe ``c`` (Linien, keine Flächen
# in der Gegenfarbe), damit sie auch auf schwarzem Grund (Kopfzeile) funktionieren.

def _lw(s):
    return max(2, round(s / 11))


def car(draw, x, y, s, c=BLACK):
    lw = _lw(s)
    draw.line([(x + s * .12, y + s * .66), (x + s * .24, y + s * .36), (x + s * .76, y + s * .36),
               (x + s * .88, y + s * .66)], fill=c, width=lw, joint="curve")
    draw.rectangle((x + s * .06, y + s * .62, x + s * .94, y + s * .78), outline=c, width=lw)
    for cx in (.27, .73):
        r = s * .1
        draw.ellipse((x + s * cx - r, y + s * .78 - r, x + s * cx + r, y + s * .78 + r), fill=c)


def cloud(draw, x, y, s, c=BLACK):
    lw = _lw(s)
    draw.arc((x + s * .08, y + s * .42, x + s * .44, y + s * .82), 90, 270, fill=c, width=lw)
    draw.arc((x + s * .24, y + s * .2, x + s * .72, y + s * .68), 180, 340, fill=c, width=lw)
    draw.arc((x + s * .56, y + s * .4, x + s * .94, y + s * .82), 270, 90, fill=c, width=lw)
    draw.line((x + s * .26, y + s * .82, x + s * .75, y + s * .82), fill=c, width=lw)


def newspaper(draw, x, y, s, c=BLACK):
    lw = _lw(s)
    draw.rectangle((x + s * .12, y + s * .18, x + s * .88, y + s * .84), outline=c, width=lw)
    for i, w in enumerate((.6, .6, .4)):
        yy = y + s * (.36 + i * .16)
        draw.line((x + s * .26, yy, x + s * (.26 + w), yy), fill=c, width=lw)


def calendar(draw, x, y, s, c=BLACK):
    lw = _lw(s)
    draw.rectangle((x + s * .12, y + s * .2, x + s * .88, y + s * .88), outline=c, width=lw)
    draw.line((x + s * .12, y + s * .4, x + s * .88, y + s * .4), fill=c, width=lw)
    for cx in (.32, .68):
        draw.line((x + s * cx, y + s * .1, x + s * cx, y + s * .28), fill=c, width=lw)


def warning(draw, x, y, s, c=BLACK):
    lw = _lw(s)
    pts = [(x + s * .5, y + s * .08), (x + s * .95, y + s * .88), (x + s * .05, y + s * .88)]
    draw.polygon(pts, outline=c, width=lw)
    draw.line((x + s * .5, y + s * .38, x + s * .5, y + s * .6), fill=c, width=lw)
    r = lw * .7
    draw.ellipse((x + s * .5 - r, y + s * .72 - r, x + s * .5 + r, y + s * .72 + r), fill=c)


def roadworks(draw, x, y, s, c=BLACK):
    lw = _lw(s)
    draw.line((x + s * .1, y + s * .88, x + s * .9, y + s * .88), fill=c, width=lw)
    draw.line([(x + s * .25, y + s * .88), (x + s * .45, y + s * .12), (x + s * .55, y + s * .12),
               (x + s * .75, y + s * .88)], fill=c, width=lw)
    draw.line((x + s * .36, y + s * .45, x + s * .64, y + s * .45), fill=c, width=lw)
    draw.line((x + s * .31, y + s * .66, x + s * .69, y + s * .66), fill=c, width=lw)


def no_entry(draw, x, y, s, c=BLACK):
    lw = _lw(s)
    draw.ellipse((x + s * .1, y + s * .1, x + s * .9, y + s * .9), outline=c, width=lw)
    draw.line((x + s * .28, y + s * .5, x + s * .72, y + s * .5), fill=c, width=lw + 1)


def jam(draw, x, y, s, c=BLACK):
    car(draw, x - s * .12, y - s * .12, s * .68, c)
    car(draw, x + s * .38, y + s * .3, s * .62, c)


def crash(draw, x, y, s, c=BLACK):
    """Unfall: Warndreieck."""
    warning(draw, x, y, s, c)


def cake(draw, x, y, s, c=BLACK):
    lw = _lw(s)
    draw.rectangle((x + s * .14, y + s * .5, x + s * .86, y + s * .9), outline=c, width=lw)
    draw.line((x + s * .14, y + s * .68, x + s * .86, y + s * .68), fill=c, width=lw)
    draw.line((x + s * .5, y + s * .28, x + s * .5, y + s * .5), fill=c, width=lw)
    draw.ellipse((x + s * .44, y + s * .08, x + s * .56, y + s * .24), fill=c)


def bin_(draw, x, y, s, c=BLACK):
    lw = _lw(s)
    draw.line((x + s * .12, y + s * .24, x + s * .88, y + s * .24), fill=c, width=lw)
    draw.line([(x + s * .38, y + s * .24), (x + s * .38, y + s * .1), (x + s * .62, y + s * .1),
               (x + s * .62, y + s * .24)], fill=c, width=lw)
    draw.line([(x + s * .2, y + s * .3), (x + s * .27, y + s * .9), (x + s * .73, y + s * .9),
               (x + s * .8, y + s * .3)], fill=c, width=lw)


def umbrella(draw, x, y, s, c=BLACK):
    """Ferien: Sonnenschirm."""
    lw = _lw(s)
    draw.pieslice((x + s * .06, y + s * .1, x + s * .94, y + s * .84), 180, 360, outline=c, width=lw)
    draw.line((x + s * .5, y + s * .47, x + s * .5, y + s * .92), fill=c, width=lw)
    draw.line((x + s * .2, y + s * .92, x + s * .8, y + s * .92), fill=c, width=lw)


def sun_rise_set(draw, x, y, s, rising, c=BLACK):
    lw = _lw(s)
    draw.line((x + s * .06, y + s * .8, x + s * .94, y + s * .8), fill=c, width=lw)
    draw.arc((x + s * .26, y + s * .56, x + s * .74, y + s * 1.04), 180, 360, fill=c, width=lw)
    top, bottom = y + s * .08, y + s * .44
    draw.line((x + s * .5, top, x + s * .5, bottom), fill=c, width=lw)
    tip = top if rising else bottom
    d = s * .13 * (1 if rising else -1)
    draw.line([(x + s * .5 - abs(d), tip + d), (x + s * .5, tip), (x + s * .5 + abs(d), tip + d)],
              fill=c, width=lw)


def bus(draw, x, y, s, c=BLACK):
    lw = _lw(s)
    draw.rounded_rectangle((x + s * .16, y + s * .08, x + s * .84, y + s * .8), radius=s * .1,
                           outline=c, width=lw)
    draw.line((x + s * .16, y + s * .5, x + s * .84, y + s * .5), fill=c, width=lw)
    for cx in (.3, .7):
        draw.line((x + s * cx, y + s * .8, x + s * cx, y + s * .92), fill=c, width=lw + 1)


def moon_phase(draw, x, y, s, age, synodic=29.530588853):
    """Mond mit beleuchtetem (weißem) und dunklem (schwarzem) Teil."""
    r = s / 2
    cx, cy = x + r, y + r
    t = math.cos(2 * math.pi * age / synodic)
    waxing = age < synodic / 2
    draw.ellipse((x, y, x + s, y + s), fill=BLACK)
    for i in range(int(s) + 1):
        dy = i - r
        if abs(dy) >= r:
            continue
        w = math.sqrt(r * r - dy * dy)
        x0, x1 = (t * w, w) if waxing else (-w, -t * w)
        if x1 - x0 >= 1:
            draw.line((cx + x0, cy + dy, cx + x1, cy + dy), fill=WHITE)
    draw.ellipse((x, y, x + s, y + s), outline=BLACK, width=2)


INCIDENT_ICONS = {"unfall": crash, "stau": jam, "sperrung": no_entry,
                  "baustelle": roadworks, "sonstiges": warning}
