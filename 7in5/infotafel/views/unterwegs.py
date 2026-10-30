"""Ansicht "Unterwegs": Fahrtzeit, Verkehrslage, Busabfahrten, Spritpreise."""
from .. import icons
from ..render import PAD, W, de_num, mono, sans
from ..sources.mobility import filter_departures

TOP = 64
MID = 400          # Trennung der Spalten
LEFT_R = MID - 14
RIGHT_L = MID + 14
RIGHT_R = W - PAD


def _route(cv, ctx, y):
    routes = ctx.data.get("routes")
    if not routes:
        y = cv.label(PAD, y, LEFT_R, "Fahrtzeit")
        cv.unavailable((PAD, y, LEFT_R, y + 90),
                       "nicht eingerichtet" if not ctx.data.sources["routes"].configured else "keine Daten")
        return y + 100
    r = routes[0]
    y = cv.label(PAD, y, LEFT_R, r.name)
    big = mono(72)
    num = str(r.minutes)
    cv.text((PAD, y + 62), num, big, "ls")
    x = PAD + cv.width(num, big) + 4
    cv.text((x, y + 62), "min", mono(28), "ls")
    x += cv.width("min", mono(28)) + 18
    if r.typical_minutes:
        diff = r.extra_minutes
        if abs(diff) >= 2:
            cv.badge(x, y + 10, f"{'+' if diff > 0 else '−'}{abs(diff)} min", sans(21, "bold"))
        else:
            cv.badge(x, y + 10, "wie üblich", sans(21, "bold"), inverted=False)
        cv.text((x, y + 62), f"sonst {r.typical_minutes} min", sans(17), "ls")
    y += 72
    if r.arrival:
        cv.text((PAD, y), f"Ankunft ca. {r.arrival:%H:%M}", sans(17))
        y += 26
    for extra in routes[1:2]:   # zweite Strecke kompakt
        diff = extra.extra_minutes
        more = f"  ({'+' if diff >= 0 else '−'}{abs(diff)})" if extra.typical_minutes and abs(diff) >= 2 else ""
        line = f"{extra.name}: {extra.minutes} min{more}"
        cv.text((PAD, y), cv.fit(line, sans(17, "semibold"), LEFT_R - PAD), sans(17, "semibold"))
        y += 26
    return y + 6


def _incidents(cv, ctx, y, bottom):
    y = cv.label(PAD, y, LEFT_R, "Verkehrslage")
    items = ctx.data.get("incidents")
    if items is None:
        cv.unavailable((PAD, y, LEFT_R, bottom),
                       "nicht eingerichtet" if not ctx.data.sources["incidents"].configured else "keine Daten")
        return
    if not items:
        cv.text((PAD, y + 6), "Keine Meldungen in der Nähe", sans(18))
        return
    row_h = 52
    shown = items[: min(ctx.cfg["traffic"]["max_items"], max(1, (bottom - y) // row_h))]
    for i, inc in enumerate(shown):
        icons.INCIDENT_ICONS[inc.kind](cv.draw, PAD, y + 4, 22)
        tx = PAD + 32
        cv.text((tx, y), cv.fit(inc.title, sans(18, "bold"), LEFT_R - tx), sans(18, "bold"))
        cv.text((tx, y + 23), cv.fit(inc.text, sans(16), LEFT_R - tx), sans(16))
        y += row_h
        if i < len(shown) - 1:
            cv.hline(PAD, LEFT_R, y - 6)
    if len(items) > len(shown):
        cv.text((LEFT_R, bottom), f"+{len(items) - len(shown)} weitere", sans(14), "rd")


def _departures(cv, ctx, y, bottom):
    tc = ctx.cfg["transit"]
    right = "gefiltert" if tc["lines"] or tc["directions"] else None
    y = cv.label(RIGHT_L, y, RIGHT_R, f"Bus · {tc['stop_name']}", right)
    deps = ctx.data.get("departures")
    if deps is None:
        cv.unavailable((RIGHT_L, y, RIGHT_R, bottom),
                       "nicht eingerichtet" if not ctx.data.sources["departures"].configured else "keine Daten")
        return
    deps = filter_departures(deps, ctx.cfg, ctx.now)[: tc["count"]]
    if not deps:
        cv.text((RIGHT_L, y + 6), "Keine Abfahrten in den nächsten 90 min", sans(18))
        return
    row_h = 30
    f_line, f_dir = mono(18), sans(19)
    for d in deps:
        if y + row_h > bottom:
            break
        cv.badge(RIGHT_L, y, d.line, f_line, pad_x=4, pad_y=3, min_width=54, inverted=not d.cancelled)
        tx = RIGHT_L + 66
        time_font = mono(20, bold=d.realtime is not None)
        time_text = "fällt aus" if d.cancelled else f"{d.when:%H:%M}"
        delay = "" if d.cancelled or d.delay_minutes < 1 else f"+{d.delay_minutes}"
        delay_w = 40
        cv.text((RIGHT_R - delay_w, y + 22), time_text, time_font if not d.cancelled else sans(18), "rs")
        if delay:
            cv.text((RIGHT_R, y + 22), delay, sans(17, "bold"), "rs")
        tw = cv.width(time_text, time_font) + delay_w + 10
        direction = cv.fit(d.direction, f_dir, RIGHT_R - tw - tx)
        cv.text((tx, y + 22), direction, f_dir, "ls")
        if d.cancelled:
            w = cv.width(direction, f_dir)
            cv.hline(tx, tx + w, y + 14, 2)
        y += row_h
    cv.text((RIGHT_L, y + 2), "fett = Echtzeit · +n = Verspätung in min", sans(13))


def _fuel(cv, ctx, y, bottom):
    fc = ctx.cfg["fuel"]
    types = fc["types"]
    names = {"e5": "Super", "e10": "E10", "diesel": "Diesel"}
    col_w = 72
    cv.label(RIGHT_L, y, RIGHT_R, "Sprit in der Nähe")
    for i, t in enumerate(reversed(types)):
        cv.text((RIGHT_R - i * (col_w + 8) - col_w / 2, y), names[t].upper(), sans(15, "bold"), "ma")
    y += 30
    stations = ctx.data.get("fuel")
    if stations is None:
        cv.unavailable((RIGHT_L, y, RIGHT_R, bottom),
                       "nicht eingerichtet" if not ctx.data.sources["fuel"].configured else "keine Daten")
        return
    cheapest = {t: min((s.prices[t] for s in stations if s.prices[t]), default=None) for t in types}
    row_h = 34
    for i, s in enumerate(stations):
        if y + row_h > bottom + 6:
            break
        price_x = RIGHT_R - len(types) * (col_w + 8)
        name = s.brand or s.name
        detail = f" · {de_num(s.distance_km, 1)} km"
        f_name = sans(18, "bold")
        name = cv.fit(name, f_name, price_x - RIGHT_L - 60)
        cv.text((RIGHT_L, y + 21), name, f_name, "ls")
        cv.text((RIGHT_L + cv.width(name, f_name), y + 21), detail, sans(16), "ls")
        for j, t in enumerate(reversed(types)):
            p = s.prices[t]
            cx = RIGHT_R - j * (col_w + 8) - col_w / 2
            if p is None:
                cv.text((cx, y + 21), "–", mono(19), "ms")
                continue
            main, last = f"{p:.3f}"[:-1].replace(".", ","), f"{p:.3f}"[-1]
            f_p = mono(19)
            tw = cv.width(main, f_p) + cv.width(last, mono(12))
            x0 = cx - tw / 2
            if p == cheapest[t] and len(stations) > 1:
                cv.draw.rectangle((x0 - 4, y + 1, x0 + tw + 4, y + 27), fill=0)
                fill = 255
            else:
                fill = 0
            cv.text((x0, y + 21), main, f_p, "ls", fill)
            cv.text((x0 + cv.width(main, f_p), y + 12), last, mono(12), "ls", fill)
        y += row_h
        if i < len(stations) - 1:
            cv.hline(RIGHT_L, RIGHT_R, y - 3)


def draw(cv, ctx):
    stale = ctx.data.stale("routes", "incidents", "departures", "fuel")
    cv.header(ctx, "Unterwegs", icons.car, stale)
    y = _route(cv, ctx, TOP)
    _incidents(cv, ctx, y, 464)
    _departures(cv, ctx, TOP, 300)
    _fuel(cv, ctx, 318, 464)
