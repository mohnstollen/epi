"""Ansicht "Wetter": aktuelles Wetter, 4 Tage, Warnungen, Pollen, Sonne, Mond."""
from .. import icons
from ..icons import describe, draw_icon
from ..render import PAD, WEEKDAYS, W, de_num, mono, sans, temp
from ..sources.weather import moon

COMPASS = ["N", "NO", "O", "SO", "S", "SW", "W", "NW"]


def _current(cv, ctx, w, y):
    draw_icon(cv.draw, w.weather_code, PAD, y, 108, w.is_day)
    x = PAD + 122
    cv.text((x, y + 74), temp(w.temperature), mono(80), "ls")
    cv.text((x, y + 102), cv.fit(describe(w.weather_code), sans(20, "semibold"), 330 - x), sans(20, "semibold"), "ls")
    parts = []
    if w.apparent_temperature is not None:
        parts.append(f"gefühlt {temp(w.apparent_temperature)}")
    if w.wind_speed is not None:
        wind = f"Wind {COMPASS[round((w.wind_direction or 0) / 45) % 8]} {round(w.wind_speed)}"
        if w.wind_gusts and w.wind_gusts >= w.wind_speed + 15:
            wind += f", Böen {round(w.wind_gusts)}"
        parts.append(wind + " km/h")
    cv.text((PAD, y + 132), cv.fit(" · ".join(parts), sans(17), 330), sans(17), "ls")


def _days(cv, ctx, w, x0, x1, y):
    days = w.days[:4]
    if not days:
        return
    cw = (x1 - x0) / len(days)
    for i, d in enumerate(days):
        cx = x0 + i * cw + cw / 2
        if i:
            cv.draw.rectangle((x0 + i * cw, y, x0 + i * cw, y + 132), fill=0)
        label = "Heute" if d.day == ctx.now.date() else WEEKDAYS[d.day.weekday()]
        cv.text((cx, y), label.upper(), sans(17, "bold"), "ma")
        draw_icon(cv.draw, d.weather_code, cx - 25, y + 26, 50)
        hi, lo = temp(d.temp_max), temp(d.temp_min)
        f_hi, f_lo = mono(21), mono(19, bold=False)
        tw = cv.width(hi, f_hi) + 8 + cv.width(lo, f_lo)
        cv.text((cx - tw / 2, y + 104), hi, f_hi, "ls")
        cv.text((cx + tw / 2, y + 104), lo, f_lo, "rs")
        p = d.precipitation
        rain = "trocken" if p is None or p < 0.1 else f"{de_num(p, 1)} mm"
        cv.text((cx, y + 128), rain, sans(15), "ms")
    cv.draw.rectangle((x0, y, x0 + 1, y + 132), fill=0)


def _warning(cv, ctx, y):
    warnings = ctx.warnings
    if not warnings:
        src = ctx.data.sources["warnings"]
        if not src.configured:
            return y
        text = "Keine amtlichen Wetterwarnungen" if ctx.data.get("warnings") is not None \
            else "Warnungen: keine Daten"
        cv.draw.rectangle((PAD, y, W - PAD, y + 40), outline=0, width=2)
        cv.text((PAD + 14, y + 20), text, sans(18), "lm")
        cv.text((W - PAD - 14, y + 20), "DWD", sans(14, "semibold"), "rm")
        return y + 52
    w = warnings[0]
    h = 62
    cv.draw.rectangle((PAD, y, W - PAD, y + h), fill=0)
    icons.warning(cv.draw, PAD + 12, y + 14, 34, 255)
    tx = PAD + 60
    title = w.headline or f"Warnung vor {w.event}"
    cv.text((tx, y + 6), cv.fit(title.upper(), sans(20, "bold"), W - PAD - 70 - tx), sans(20, "bold"), "la", 255)
    when = ""
    if w.onset and w.expires:
        same = w.onset.date() == w.expires.date()
        def fmt(dt):
            day = "" if dt.date() == ctx.now.date() else f"{WEEKDAYS[dt.weekday()]} "
            return f"{day}{dt:%H:%M}"
        when = f"{fmt(w.onset)} bis {fmt(w.expires) if not same else f'{w.expires:%H:%M}'}"
    detail = " · ".join(x for x in (when, w.description) if x)
    cv.text((tx, y + 34), cv.fit(detail, sans(16), W - PAD - 14 - tx), sans(16), "la", 255)
    more = f"+{len(warnings) - 1}" if len(warnings) > 1 else "DWD"
    cv.text((W - PAD - 12, y + 8), more, sans(14, "semibold"), "ra", 255)
    return y + h + 12


def _pollen(cv, ctx, x0, x1, y):
    y = cv.label(x0, y, x1, "Pollenflug heute")
    pollen = ctx.data.get("pollen")
    if pollen is None:
        cv.unavailable((x0, y, x1, y + 80),
                       "nicht eingerichtet" if not ctx.data.sources["pollen"].configured else "keine Daten")
        return
    for name in ctx.cfg["pollen"]["types"][:4]:
        today, _ = pollen.get(name, (None, None))
        cv.text((x0, y + 18), name, sans(17), "ls")
        bx = x1 - 3 * 19
        for k in range(3):
            box = (bx + k * 19, y + 5, bx + k * 19 + 15, y + 17)
            cv.draw.rectangle(box, outline=0, width=2)
            if today is not None and today >= k + 1:
                cv.draw.rectangle(box, fill=0)
            elif today is not None and today >= k + 0.5:
                cv.draw.rectangle((box[0], box[1], box[0] + 7, box[3]), fill=0)
        if today is None:
            cv.text((bx - 8, y + 18), "–", sans(17), "rs")
        y += 23


def _sun(cv, ctx, w, x0, x1, y):
    y = cv.label(x0, y, x1, "Sonne")
    today = next((d for d in (w.days if w else []) if d.day == ctx.now.date()), None)
    if not today or not today.sunrise:
        cv.unavailable((x0, y, x1, y + 80))
        return
    for rising, t in ((True, today.sunrise), (False, today.sunset)):
        icons.sun_rise_set(cv.draw, x0, y, 28, rising)
        cv.text((x0 + 38, y + 24), f"{t:%H:%M}", mono(24), "ls")
        y += 33
    length = (today.sunset - today.sunrise).total_seconds() / 60
    cv.text((x0, y + 14), f"Tageslänge {int(length // 60)} h {int(length % 60):02d} min", sans(15), "ls")


def _moon(cv, ctx, x0, x1, y):
    y = cv.label(x0, y, x1, "Mond")
    m = moon(ctx.now)
    icons.moon_phase(cv.draw, x0, y + 6, 58, m.age)
    tx = x0 + 72
    name_f = sans(19, "bold")
    lines = cv.wrap(m.name, name_f, x1 - tx, 2)
    for i, line in enumerate(lines):
        cv.text((tx, y + 4 + i * 22), line, name_f)
    ny = y + 4 + len(lines) * 22 + 2
    if m.name == "Vollmond":
        nxt = f"Neumond in {m.days_to_new} T."
    elif m.days_to_full <= m.days_to_new:
        nxt = f"Vollmond in {m.days_to_full} T." if m.days_to_full else "Vollmond heute"
    else:
        nxt = f"Neumond in {m.days_to_new} T." if m.days_to_new else "Neumond heute"
    cv.text((tx, ny), nxt, sans(15))


def draw(cv, ctx):
    stale = ctx.data.stale("weather", "warnings", "pollen")
    cv.header(ctx, f"Wetter · {ctx.cfg['location_name']}" if ctx.cfg["location_name"] else "Wetter",
              icons.cloud, stale)
    w = ctx.data.get("weather")
    y = 62
    if w:
        _current(cv, ctx, w, y)
        _days(cv, ctx, w, 356, W - PAD, y)
    else:
        cv.unavailable((PAD, y, W - PAD, y + 140), "Wetterdaten nicht verfügbar")
    y = _warning(cv, ctx, y + 150)
    col = (W - 2 * PAD - 40) / 3
    xs = [PAD + i * (col + 20) for i in range(3)]
    _pollen(cv, ctx, xs[0], xs[0] + col, y)
    _sun(cv, ctx, w, xs[1], xs[1] + col, y)
    _moon(cv, ctx, xs[2], xs[2] + col, y)
