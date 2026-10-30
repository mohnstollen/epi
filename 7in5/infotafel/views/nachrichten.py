"""Ansicht "Nachrichten & Märkte": Schlagzeilen und Kurse mit Verlaufslinie."""
from .. import icons
from ..render import PAD, WEEKDAYS, W, de_num, mono, sans

TOP = 64
SPLIT = 452       # linke Kante der Kursspalte


def _headlines(cv, ctx, x0, x1, bottom):
    nc = ctx.cfg["news"]
    y = cv.label(x0, TOP, x1, nc["title"], f"neueste {nc['count']}")
    items = ctx.data.get("news")
    if items is None:
        cv.unavailable((x0, y, x1, bottom),
                       "nicht eingerichtet" if not ctx.data.sources["news"].configured else "keine Daten")
        return
    f_time, f_first, f_rest = mono(15, bold=False), sans(19, "bold"), sans(19)
    tx = x0 + 52
    line_h = 23
    for i, h in enumerate(items[: nc["count"]]):
        f = f_first if i == 0 else f_rest
        lines = cv.wrap(h.title, f, x1 - tx, 2)
        need = len(lines) * line_h + 12
        if y + need > bottom:
            break
        if h.published:
            stamp = f"{h.published:%H:%M}" if h.published.date() == ctx.now.date() \
                else f"{h.published.day:02d}.{h.published.month:02d}."
            cv.text((x0, y + 3), stamp, f_time)
        for k, line in enumerate(lines):
            cv.text((tx, y + k * line_h), line, f)
        y += need
        if i < nc["count"] - 1:
            cv.hline(x0, x1, y - 7)


def _sparkline(cv, values, x, y, w, h):
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pts = [(x + i * w / (len(values) - 1), y + h - (v - lo) / span * h) for i, v in enumerate(values)]
    cv.draw.line(pts, fill=0, width=2, joint="curve")
    lx, ly = pts[-1]
    cv.draw.ellipse((lx - 3, ly - 3, lx + 3, ly + 3), fill=0)


def _markets(cv, ctx, x0, x1, bottom):
    y = cv.label(x0, TOP, x1, "Märkte", "10 Tage")
    quotes = ctx.data.get("markets")
    if quotes is None:
        cv.unavailable((x0, y, x1, bottom),
                       "nicht eingerichtet" if not ctx.data.sources["markets"].configured else "keine Daten")
        return
    row_h = min(66, (bottom - 26 - y) // max(1, len(quotes)))
    spark_w = 78
    for i, q in enumerate(quotes):
        if y + row_h > bottom - 20:
            break
        tx1 = x1 - spark_w - 14
        f_name, f_price = sans(19, "bold"), mono(19)
        price = de_num(q.price, q.decimals)
        name = cv.fit(q.name, f_name, tx1 - x0 - cv.width(price, f_price) - 10)
        cv.text((x0, y + 20), name, f_name, "ls")
        if q.unit:
            cv.text((x0 + cv.width(name, f_name) + 5, y + 20), q.unit, sans(13), "ls")
        cv.text((tx1, y + 20), price, f_price, "rs")
        pct = q.change_pct
        if pct is not None:
            text = f"{de_num(pct, 1, sign=True)} %"
            f_pct = mono(15, bold=False)
            cv.text((tx1, y + 42), text, f_pct, "rs")
            ax = tx1 - cv.width(text, f_pct) - 16
            if pct > 0.005:
                cv.draw.polygon([(ax, y + 41), (ax + 10, y + 41), (ax + 5, y + 32)], fill=0)
            elif pct < -0.005:
                cv.draw.polygon([(ax, y + 32), (ax + 10, y + 32), (ax + 5, y + 41)], fill=0)
        if len(q.history) >= 2:
            _sparkline(cv, q.history, x1 - spark_w, y + 6, spark_w, row_h - 22)
        y += row_h
        if i < len(quotes) - 1:
            cv.hline(x0, x1, y - 8)
    times = [q.time for q in quotes if q.time]
    if times:
        t = max(times)
        day = "heute" if t.date() == ctx.now.date() else WEEKDAYS[t.weekday()]
        cv.text((x0, bottom), f"Stand {day} {t:%H:%M} · verzögert", sans(13), "ld")


def draw(cv, ctx):
    cv.header(ctx, "Nachrichten & Märkte", icons.newspaper, ctx.data.stale("news", "markets"))
    _headlines(cv, ctx, PAD, SPLIT - 24, 466)
    _markets(cv, ctx, SPLIT, W - PAD, 466)
