"""Ein-Seiten-Dashboard für das 7.5inch e-Paper HAT V2 (800x480, Querformat).

Links: aktuelles Wetter, Temperaturkurve der nächsten 24 Stunden, 3-Tage-Vorhersage.
Rechts: tagesschau-Schlagzeilen und darunter die drei günstigsten E10-Tankstellen.
"""
from datetime import datetime

from PIL import Image, ImageDraw

from .icons import BLACK, WHITE, describe, draw_icon
from .screens import WEEKDAYS, de_number, fit, font, temp, wrap

W, H = 800, 480
HEADER = 44
LEFT = 340          # Breite der Wetterspalte
PAD = 14
FUEL_TOP = 330      # Oberkante des Spritkastens

WEEKDAYS_LONG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]


def _t(draw, xy, text, f, anchor="la", fill=BLACK):
    draw.text(xy, text, font=f, fill=fill, anchor=anchor)


def _label(draw, x, y, text):
    _t(draw, (x, y), text.upper(), font(14, bold=True))


def _header(draw, cfg, now, stale):
    draw.rectangle((0, 0, W - 1, HEADER - 1), fill=BLACK)
    if cfg.location_name:
        _t(draw, (PAD, HEADER // 2), cfg.location_name, font(24, bold=True), "lm", WHITE)
    date = f"{WEEKDAYS_LONG[now.weekday()]}, {now.day}. {MONTHS[now.month - 1]} {now.year}"
    _t(draw, (W // 2, HEADER // 2), date, font(20), "mm", WHITE)
    stand = f"{'! ' if stale else ''}Stand {now:%H:%M}"
    _t(draw, (W - PAD, HEADER // 2), stand, font(18), "rm", WHITE)


def _unavailable(draw, box, text):
    x0, y0, x1, y1 = box
    _t(draw, ((x0 + x1) / 2, (y0 + y1) / 2), text, font(16), "mm")


def _current(draw, cw, top, bottom):
    if cw is None:
        _unavailable(draw, (0, top, LEFT, bottom), "Wetterdaten nicht verfügbar")
        return
    draw_icon(draw, cw.weather_code, PAD, top, 104, cw.is_day)
    cx = 124 + (LEFT - 124) / 2
    _t(draw, (cx, top + 40), temp(cw.temperature), font(66, bold=True), "mm")
    desc = fit(draw, describe(cw.weather_code), font(19), LEFT - 128)
    _t(draw, (cx, top + 90), desc, font(19), "mm")
    details = []
    if cw.apparent_temperature is not None:
        details.append(f"gefühlt {temp(cw.apparent_temperature)}")
    if cw.wind_speed is not None:
        details.append(f"Wind {round(cw.wind_speed)} km/h")
    if cw.humidity is not None:
        details.append(f"{round(cw.humidity)} %")
    _t(draw, (LEFT / 2, bottom - 10), "  ·  ".join(details), font(15), "mm")


def _dashed(draw, x0, x1, y, dash=3):
    for x in range(int(x0), int(x1), dash * 2):
        draw.line((x, y, min(x + dash, x1), y), fill=BLACK)


def _chart(draw, hours, top, bottom):
    """Temperaturkurve (Linie) mit stündlichem Niederschlag (Balken)."""
    _label(draw, PAD, top, "Nächste 24 h")
    if len(hours) < 2:
        _unavailable(draw, (0, top, LEFT, bottom), "Keine Stundenwerte verfügbar")
        return
    x0, x1 = PAD + 4, LEFT - PAD - 4
    y0, y1 = top + 44, bottom - 20            # Zeichenfläche; y1 = Grundlinie
    curve_bottom = y1 - 20                    # Platz für die Minimum-Beschriftung
    temps = [h.temperature for h in hours]
    tmin, tmax = min(temps), max(temps)
    span = max(tmax - tmin, 4.0)              # flache Tage nicht übertrieben steil zeigen
    mid = (tmin + tmax) / 2
    lo, hi = mid - span / 2, mid + span / 2
    step = (x1 - x0) / (len(hours) - 1)

    def px(i):
        return x0 + i * step

    def py(t):
        return curve_bottom - (t - lo) / (hi - lo) * (curve_bottom - y0)

    # Niederschlag: Balken von der Grundlinie, voll ab 2 mm/h (oder dem Maximum)
    rain_max = max(h.precipitation for h in hours)
    scale = max(rain_max, 2.0)
    bar_w = max(2, int(step) - 3)
    for i, h in enumerate(hours):
        if h.precipitation >= 0.1:
            bh = max(2, h.precipitation / scale * (y1 - y0) * 0.6)
            draw.rectangle((px(i) - bar_w / 2, y1 - bh, px(i) + bar_w / 2, y1), fill=BLACK)
    if rain_max >= 0.1:
        _t(draw, (LEFT - PAD, top + 1), f"Regen max. {de_number(rain_max, 1)} mm/h",
           font(12), "ra")

    draw.line((x0, y1, x1, y1), fill=BLACK)
    if lo < 0 < hi:
        _dashed(draw, x0, x1, py(0))

    points = [(px(i), py(t)) for i, t in enumerate(temps)]
    draw.line(points, fill=BLACK, width=3, joint="curve")

    # Extremwerte beschriften
    imax, imin = temps.index(tmax), temps.index(tmin)
    for i, above in ((imax, True), (imin, False)):
        x, y = points[i]
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=BLACK)
        x = min(max(x, x0 + 16), x1 - 16)
        _t(draw, (x, y - 8 if above else y + 8), temp(temps[i]), font(15, bold=True),
           "md" if above else "ma")

    # Zeitachse: alle 6 Stunden ab der nächsten durch 6 teilbaren Stunde
    for i, h in enumerate(hours):
        if h.time.hour % 6 == 0 and x0 + 18 < px(i) < x1 - 18:
            draw.line((px(i), y1, px(i), y1 + 4), fill=BLACK)
            _t(draw, (px(i), y1 + 6), f"{h.time:%H} Uhr", font(12), "ma")


def _forecast(draw, days, top, bottom):
    _label(draw, PAD, top, "Vorhersage")
    if not days:
        _unavailable(draw, (0, top, LEFT, bottom), "Vorhersage nicht verfügbar")
        return
    col = (LEFT - 2 * PAD) / len(days)
    for i, d in enumerate(days):
        cx = PAD + col * i + col / 2
        if i:
            draw.line((PAD + col * i, top + 24, PAD + col * i, bottom - 4), fill=BLACK)
        _t(draw, (cx, top + 32), f"{WEEKDAYS[d.day.weekday()]} {d.day:%d.%m.}",
           font(16, bold=True), "mm")
        draw_icon(draw, d.weather_code, cx - 29, top + 42, 58)
        _t(draw, (cx - 4, top + 118), temp(d.temp_max), font(24, bold=True), "rm")
        _t(draw, (cx + 4, top + 120), temp(d.temp_min), font(18), "lm")
        if d.precipitation is not None:
            _t(draw, (cx, top + 142), f"{de_number(d.precipitation, 1)} mm", font(13), "mm")


def _news(draw, cfg, titles, left, top, bottom):
    _label(draw, left, top, "tagesschau")
    if not titles:
        _unavailable(draw, (left, top, W, bottom), "Schlagzeilen nicht verfügbar")
        return
    f, line_h, gap = font(19), 24, 13
    width = W - left - PAD - 18
    y = top + 26
    for i, title in enumerate(titles[:cfg.max_headlines]):
        lines = wrap(draw, title, f, width)
        if len(lines) > 2:
            lines = lines[:2]
            lines[-1] = fit(draw, lines[-1] + " …", f, width)
        if y + len(lines) * line_h > bottom:
            break
        if i:
            draw.line((left, y - gap / 2 - 1, W - PAD, y - gap / 2 - 1), fill=BLACK)
        draw.rectangle((left, y + 8, left + 6, y + 14), fill=BLACK)
        for line in lines:
            _t(draw, (left + 18, y), line, f)
            y += line_h
        y += gap


def _price(draw, x, y, price):
    p = f"{price:.3f}".replace(".", ",")
    fb, fs = font(36, bold=True), font(19, bold=True)
    _t(draw, (x, y), p[:-1], fb)
    _t(draw, (x + draw.textlength(p[:-1], font=fb) + 2, y + 2), p[-1], fs)


def _fuel(draw, cfg, stations, box):
    x0, y0, x1, y1 = box
    draw.rectangle(box, outline=BLACK, width=2)
    _label(draw, x0 + 12, y0 + 10, "E10 · günstigste Tankstellen")
    if stations is None:
        _unavailable(draw, (x0, y0 + 20, x1, y1), "Spritpreise nicht verfügbar")
        return
    if not stations:
        _unavailable(draw, (x0, y0 + 20, x1, y1),
                     f"Keine geöffnete Tankstelle im Umkreis von {cfg.fuel_radius_km:g} km")
        return
    col = (x1 - x0 - 12) / 3
    for i, s in enumerate(stations):
        x = x0 + 12 + i * col
        w = col - 16
        if i:
            draw.line((x - 8, y0 + 36, x - 8, y1 - 12), fill=BLACK)
        _price(draw, x, y0 + 38, s.price)
        _t(draw, (x, y0 + 84), fit(draw, s.brand or s.name, font(17, bold=True), w),
           font(17, bold=True))
        _t(draw, (x, y0 + 106), fit(draw, s.street, font(13), w), font(13))
        loc = f"{s.place} · {de_number(s.distance_km, 1)} km" if s.place else \
            f"{de_number(s.distance_km, 1)} km"
        _t(draw, (x, y0 + 123), fit(draw, loc, font(13), w), font(13))


def render(cfg, data, now=None):
    """``data``: dict mit den Cached-Objekten weather, hourly, forecast, fuel, news."""
    now = now or datetime.now()
    img = Image.new("1", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    _header(draw, cfg, now, any(c.stale for c in data.values()))

    draw.line((LEFT, HEADER + 12, LEFT, H - PAD), fill=BLACK, width=2)
    _current(draw, data["weather"].value, HEADER + 6, 176)
    draw.line((PAD, 180, LEFT - PAD, 180), fill=BLACK)
    _chart(draw, data["hourly"].value or [], 188, 316)
    draw.line((PAD, 322, LEFT - PAD, 322), fill=BLACK)
    _forecast(draw, data["forecast"].value, 330, H - 6)

    right = LEFT + 22
    _news(draw, cfg, data["news"].value, right, HEADER + 14, FUEL_TOP - 10)
    _fuel(draw, cfg, data["fuel"].value, (right - 8, FUEL_TOP, W - 8, H - 8))
    return img
