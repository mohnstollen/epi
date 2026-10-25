"""Rendern der vier Dashboard-Ansichten als 264x176-Schwarzweißbild."""
from datetime import datetime
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .icons import BLACK, WHITE, describe, draw_icon

W, H = 264, 176
HEADER = 22
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu/"]


@lru_cache(maxsize=None)
def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in FONT_DIRS:
        try:
            return ImageFont.truetype(d + name, size)
        except OSError:
            continue
    raise RuntimeError(f"Schrift {name} nicht gefunden – bitte 'fonts-dejavu-core' installieren")


def temp(value):
    t = round(value)
    return f"{'−' if t < 0 else ''}{abs(t)}°"


def de_number(value, digits):
    return f"{value:.{digits}f}".replace(".", ",")


def _canvas():
    img = Image.new("1", (W, H), WHITE)
    return img, ImageDraw.Draw(img)


def _header(draw, title, now, stale=False):
    draw.rectangle((0, 0, W - 1, HEADER - 1), fill=BLACK)
    f = font(13, bold=True)
    draw.text((5, HEADER // 2), title, font=f, fill=WHITE, anchor="lm")
    right = now.strftime("%H:%M")
    if stale:
        right = "! " + right
    draw.text((W - 5, HEADER // 2), right, font=font(13), fill=WHITE, anchor="rm")


def _centered(draw, xy, text, f):
    draw.text(xy, text, font=f, fill=BLACK, anchor="mm")


def _message(draw, text):
    lines = wrap(draw, text, font(14), W - 20)
    y = (HEADER + H) / 2 - len(lines) * 9
    for line in lines:
        _centered(draw, (W / 2, y + 9), line, font(14))
        y += 18


def wrap(draw, text, f, width):
    """Bricht Text wortweise auf die Breite ``width`` um."""
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if draw.textlength(candidate, font=f) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        while draw.textlength(word, font=f) > width:  # überlange Wörter hart trennen
            cut = len(word)
            while cut > 1 and draw.textlength(word[:cut] + "-", font=f) > width:
                cut -= 1
            lines.append(word[:cut] + "-")
            word = word[cut:]
        line = word
    if line:
        lines.append(line)
    return lines


def _title(cfg, base):
    return f"{base} · {cfg.location_name}" if cfg.location_name else base


def render_current(cfg, cached, now=None):
    now = now or datetime.now()
    img, draw = _canvas()
    _header(draw, _title(cfg, "Wetter jetzt"), now, cached.stale)
    cw = cached.value
    if cw is None:
        _message(draw, "Wetterdaten nicht verfügbar")
        return img

    draw_icon(draw, cw.weather_code, 6, HEADER + 10, 108, cw.is_day)

    cx = 120 + (W - 120) / 2
    _centered(draw, (cx, HEADER + 42), temp(cw.temperature), font(54, bold=True))
    lines = wrap(draw, describe(cw.weather_code), font(15), W - 124)[:2]
    for i, line in enumerate(lines):
        _centered(draw, (cx, HEADER + 88 + i * 18), line, font(15))

    details = []
    if cw.apparent_temperature is not None:
        details.append(f"gefühlt {temp(cw.apparent_temperature)}")
    if cw.wind_speed is not None:
        details.append(f"Wind {round(cw.wind_speed)} km/h")
    if cw.humidity is not None:
        details.append(f"{round(cw.humidity)} %")
    draw.line((8, H - 26, W - 8, H - 26), fill=BLACK)
    _centered(draw, (W / 2, H - 13), "  ·  ".join(details), font(13))
    return img


def render_forecast(cfg, cached, now=None):
    now = now or datetime.now()
    img, draw = _canvas()
    _header(draw, _title(cfg, "Vorhersage"), now, cached.stale)
    days = cached.value
    if not days:
        _message(draw, "Vorhersage nicht verfügbar")
        return img

    col = W / len(days)
    for i, d in enumerate(days):
        cx = col * i + col / 2
        if i:
            draw.line((col * i, HEADER + 6, col * i, H - 6), fill=BLACK)
        _centered(draw, (cx, HEADER + 13), f"{WEEKDAYS[d.day.weekday()]} {d.day:%d.%m.}",
                  font(14, bold=True))
        size = 60
        draw_icon(draw, d.weather_code, cx - size / 2, HEADER + 26, size)
        _centered(draw, (cx, HEADER + 104), temp(d.temp_max), font(22, bold=True))
        _centered(draw, (cx, HEADER + 128), temp(d.temp_min), font(17))
        if d.precipitation is not None:
            _centered(draw, (cx, HEADER + 145), f"{de_number(d.precipitation, 1)} mm", font(11))
    return img


def _price(draw, x, y, price):
    """Preis im Tankstellenformat, z. B. 1,73⁹ – linksbündig ab (x, y oben)."""
    main = f"{price:.3f}".replace(".", ",")
    big, small = main[:-1], main[-1]
    fb, fs = font(28, bold=True), font(15, bold=True)
    draw.text((x, y), big, font=fb, fill=BLACK, anchor="la")
    bx = x + draw.textlength(big, font=fb) + 1
    draw.text((bx, y + 1), small, font=fs, fill=BLACK, anchor="la")
    return bx + draw.textlength(small, font=fs)


def fit(draw, text, f, width):
    if draw.textlength(text, font=f) <= width:
        return text
    while text and draw.textlength(text + "…", font=f) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def render_fuel(cfg, cached, now=None):
    now = now or datetime.now()
    img, draw = _canvas()
    _header(draw, "E10 · günstigste Preise", now, cached.stale)
    stations = cached.value
    if stations is None:
        _message(draw, "Spritpreise nicht verfügbar")
        return img
    if not stations:
        _message(draw, f"Keine geöffnete Tankstelle im Umkreis von {cfg.fuel_radius_km:g} km")
        return img

    row = (H - HEADER) / 3
    tx = 100
    for i, s in enumerate(stations):
        y = HEADER + i * row
        if i:
            draw.line((6, y, W - 6, y), fill=BLACK)
        _price(draw, 6, y + 8, s.price)
        tw = W - tx - 6
        draw.text((tx, y + 6), fit(draw, s.brand or s.name, font(14, bold=True), tw),
                  font=font(14, bold=True), fill=BLACK)
        draw.text((tx, y + 23), fit(draw, s.street, font(12), tw), font=font(12), fill=BLACK)
        loc = f"{s.place} · {de_number(s.distance_km, 1)} km"
        draw.text((tx, y + 37), fit(draw, loc, font(12), tw), font=font(12), fill=BLACK)
    return img


def render_news(cfg, cached, now=None):
    now = now or datetime.now()
    img, draw = _canvas()
    _header(draw, "tagesschau", now, cached.stale)
    titles = cached.value
    if not titles:
        _message(draw, "Schlagzeilen nicht verfügbar")
        return img

    f = font(13)
    line_h, gap, indent = 15, 6, 10
    y = HEADER + 5
    shown = 0
    for title in titles[:cfg.max_headlines]:
        lines = wrap(draw, title, f, W - indent - 6)
        if len(lines) > 3:  # sehr lange Schlagzeilen kürzen
            lines = lines[:3]
            lines[-1] = fit(draw, lines[-1] + " …", f, W - indent - 6)
        if y + len(lines) * line_h > H - 2:
            break
        if shown:
            draw.line((indent, y - gap / 2 - 1, W - 6, y - gap / 2 - 1), fill=BLACK)
        draw.rectangle((3, y + 6, 6, y + 9), fill=BLACK)
        for line in lines:
            draw.text((indent, y), line, font=f, fill=BLACK)
            y += line_h
        y += gap
        shown += 1
    return img
