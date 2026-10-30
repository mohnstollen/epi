"""Ansicht "Termine & Countdowns": Geburtstag, Ferien, Feiertage, Kalender."""
from datetime import timedelta

from .. import icons
from ..render import PAD, WEEKDAYS, W, mono, sans, short_date
from ..sources.info import Event, upcoming_birthdays, upcoming_holidays, vacation_status

TOP = 64
MID = 400
LEFT_R = MID - 14
RIGHT_L = MID + 14


def _genitive(name):
    return f"{name}'" if name[-1:].lower() in "sßxz" else f"{name}s"


def _tile(cv, box, symbol, number, unit, text, inverted):
    x0, y0, x1, y1 = box
    fg = 255 if inverted else 0
    if inverted:
        cv.draw.rectangle(box, fill=0)
    else:
        cv.draw.rectangle(box, outline=0, width=3)
    symbol(cv.draw, x0 + 12, y0 + 10, 28, fg)
    big = mono(64 if len(number) <= 3 else 40)
    cv.text((x0 + 12, y0 + 104), number, big, "ls", fg)
    if unit:
        cv.text((x0 + 14 + cv.width(number, big), y0 + 104), unit.upper(), sans(17, "bold"), "ls", fg)
    for i, line in enumerate(cv.wrap(text, sans(16), x1 - x0 - 24, 2)):
        cv.text((x0 + 12, y0 + 112 + i * 20), line, sans(16), "la", fg)


def _countdown(days):
    if days == 0:
        return "Heute", ""
    if days == 1:
        return "1", "Tag"
    return str(days), "Tage"


def _tiles(cv, ctx, y):
    today = ctx.now.date()
    gap = 12
    w = (LEFT_R - PAD - gap) / 2
    boxes = [(PAD, y, PAD + w, y + 160), (PAD + w + gap, y, LEFT_R, y + 160)]

    birthdays = upcoming_birthdays(ctx.cfg, today)
    if birthdays:
        b = birthdays[0]
        num, unit = _countdown((b.day - today).days)
        what = f"{_genitive(b.name)} {f'{b.age}. ' if b.age else ''}Geburtstag"
        text = (f"{what}!" if num == "Heute" else f"bis {what} · {short_date(b.day)}")
        _tile(cv, boxes[0], icons.cake, num, unit, text, False)
    else:
        cv.draw.rectangle(boxes[0], outline=0, width=3)
        cv.unavailable(boxes[0], "keine Geburtstage")

    vac, running = vacation_status(ctx.data.get("vacations"), today)
    if vac and running:
        left = (vac.end - today).days + 1
        _tile(cv, boxes[1], icons.umbrella, str(left), "Tag" if left == 1 else "Tage",
              f"{vac.name} – bis {short_date(vac.end)}", True)
    elif vac:
        num, unit = _countdown((vac.start - today).days)
        _tile(cv, boxes[1], icons.umbrella, num, unit, f"bis zu den {vac.name} · ab {short_date(vac.start)}", True)
    else:
        cv.draw.rectangle(boxes[1], fill=0)
        cv.unavailable(boxes[1], "")
        cv.text(((boxes[1][0] + boxes[1][2]) / 2, y + 80), "Ferien: keine Daten", sans(17), "mm", 255)
    return y + 176


def _holidays(cv, ctx, y, bottom):
    y = cv.label(PAD, y, LEFT_R, "Feiertage Bayern")
    today = ctx.now.date()
    f_name, f_date = sans(18, "bold"), mono(17, bold=False)
    for h in upcoming_holidays(ctx.cfg, today, 4):
        if y + 26 > bottom:
            break
        days = (h.day - today).days
        rest = "heute" if days == 0 else f"{days} T"
        cv.text((LEFT_R, y), rest, mono(17), "ra")
        date_x = LEFT_R - 62
        cv.text((date_x, y), short_date(h.day), f_date, "ra")
        name_max = date_x - cv.width(short_date(h.day), f_date) - 12 - PAD
        name = cv.fit(h.name, f_name, name_max)
        cv.text((PAD, y), name, f_name)
        if h.school_only:
            cv.text((PAD + cv.width(name, f_name) + 6, y + 4), "schulfrei", sans(13))
        y += 28


def _day_label(day, today):
    delta = (day - today).days
    names = {0: "Heute", 1: "Morgen", 2: "Übermorgen"}
    if delta in names:
        return f"{names[delta]} · {short_date(day)}"
    return short_date(day) if delta > 6 else f"{WEEKDAYS[day.weekday()]} {day.day:02d}.{day.month:02d}."


def _calendar(cv, ctx, x0, x1, bottom):
    y = cv.label(x0, TOP, x1, "Kalender")
    today = ctx.now.date()
    events = ctx.data.get("calendar")
    if events is None and ctx.data.sources["calendar"].configured:
        cv.unavailable((x0, y, x1, bottom), "keine Daten")
        return
    events = list(events or [])
    # Geburtstage im Zeitraum mit anzeigen
    horizon = today + timedelta(days=ctx.cfg["calendar"]["days"])
    for b in upcoming_birthdays(ctx.cfg, today):
        if b.day <= horizon:
            start = ctx.now.replace(year=b.day.year, month=b.day.month, day=b.day.day,
                                    hour=0, minute=0, second=0, microsecond=0)
            events.append(Event(f"{_genitive(b.name)} Geburtstag", start, True, "geburtstag"))
    # Vergangene Termine von heute ausblenden (ganztägige bleiben)
    events = [e for e in events
              if e.start.date() > today or (e.start.date() == today and (e.all_day or e.start >= ctx.now))]
    events.sort(key=lambda e: (e.start.date(), not e.all_day, e.start))
    if not events:
        cv.text((x0, y + 6), "Keine Termine in den nächsten Tagen", sans(18))
        return
    f_day, f_time, f_title = sans(15, "bold"), mono(18, bold=False), sans(19)
    current = None
    shown = 0
    for e in events:
        new_day = e.start.date() != current
        need = (24 if new_day else 0) + 27
        if y + need > bottom:
            break
        if new_day:
            if current is not None:
                cv.hline(x0, x1, y - 3)
                y += 4
            current = e.start.date()
            cv.text((x0, y), _day_label(current, today).upper(), f_day)
            y += 24
        tx = x0 + 64
        if e.symbol == "tonne":
            icons.bin_(cv.draw, x0 + 2, y + 1, 22)
        elif e.symbol == "geburtstag":
            icons.cake(cv.draw, x0 + 2, y + 1, 22)
        elif not e.all_day:
            cv.text((x0, y + 1), f"{e.start:%H:%M}", f_time)
        f = sans(19, "bold") if e.symbol else f_title
        cv.text((tx, y), cv.fit(e.title, f, x1 - tx), f)
        y += 27
        shown += 1
    if shown < len(events):
        cv.text((x1, bottom), f"+{len(events) - shown} weitere", sans(14), "rd")


def draw(cv, ctx):
    cv.header(ctx, "Termine & Countdowns", icons.calendar, ctx.data.stale("calendar", "vacations"))
    y = _tiles(cv, ctx, TOP + 4)
    _holidays(cv, ctx, y, 466)
    _calendar(cv, ctx, RIGHT_L, W - PAD, 466)
