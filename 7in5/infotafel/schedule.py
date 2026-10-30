"""Welche Ansicht wann gezeigt wird und wie lange der ESP32 danach schlafen soll.

Die Zeit wird in Abschnitte von ``interval_minutes`` geteilt; jeder Abschnitt zeigt
eine Ansicht reihum. So braucht der Server keinen Zustand: Wer zu einer Zeit fragt,
bekommt immer dieselbe Ansicht, und der ESP32 schläft bis zum nächsten Abschnitt.

Vorrang: Nachtruhe > erste passende Regel (z. B. werktags morgens nur "unterwegs")
> Standard-Rotation.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .config import DAYS

LEAD_SECONDS = 15     # Wer bis zu so viel zu früh fragt (ungenauer ESP32-Timer), bekommt schon den nächsten Abschnitt
MARGIN_SECONDS = 3    # ESP32 erst kurz nach dem Wechsel wecken
MIN_SLEEP = 60
MAX_SLEEP = 3600


@dataclass
class Plan:
    view: str
    views: list           # Ansichten im aktuellen Modus (für die Punkte)
    sleep_seconds: int
    mode: str             # "nacht", Name der Regel oder "standard"
    night: bool = False


def _t(text):
    h, m = map(int, text.split(":"))
    return time(h, m)


def in_window(now, start, end):
    """Liegt die Uhrzeit von ``now`` in [start, end)? Fenster über Mitternacht erlaubt."""
    t = now.time()
    s, e = _t(start), _t(end)
    if s == e:
        return False
    if s < e:
        return s <= t < e
    return t >= s or t < e


def _rule_matches(rule, now):
    days = rule.get("days", list(DAYS))
    if DAYS[now.weekday()] not in days:
        # Bei Fenstern über Mitternacht zählt der Starttag
        if not (_t(rule["from"]) > _t(rule["to"]) and now.time() < _t(rule["to"])
                and DAYS[(now.weekday() - 1) % 7] in days):
            return False
    return in_window(now, rule["from"], rule["to"])


def _boundaries(cfg, now):
    """Alle Zeitpunkte in den nächsten 2 Tagen, an denen ein Fenster beginnt oder endet."""
    sch = cfg["schedule"]
    times = [r[k] for r in sch["rules"] for k in ("from", "to")]
    if sch["night"]["enabled"]:
        times += [sch["night"]["from"], sch["night"]["to"]]
    result = []
    for day in range(3):
        base = (now + timedelta(days=day)).date()
        for t in times:
            dt = datetime.combine(base, _t(t), tzinfo=now.tzinfo)
            if dt > now:
                result.append(dt)
    return sorted(result)


def _next_midnight(now):
    return datetime.combine(now.date() + timedelta(days=1), time(0, 0), tzinfo=now.tzinfo)


def plan(cfg, now, night_warning=False):
    """Plan für den Zeitpunkt ``now`` (zeitzonenbewusst)."""
    sch = cfg["schedule"]
    probe = now + timedelta(seconds=LEAD_SECONDS)
    boundaries = _boundaries(cfg, probe)
    next_boundary = boundaries[0] if boundaries else probe + timedelta(seconds=MAX_SLEEP)

    night = sch["night"]
    if night["enabled"] and in_window(probe, night["from"], night["to"]):
        view = "wetter" if night_warning and night["warnings_wake"] else night["view"]
        wake = min(next_boundary, _next_midnight(probe),
                   now + timedelta(minutes=night["check_minutes"]))
        return Plan(view, [view], _sleep(wake, now), "nacht", night=True)

    views, interval, mode = sch["views"], sch["interval_minutes"], "standard"
    for i, rule in enumerate(sch["rules"]):
        if _rule_matches(rule, probe):
            views = rule.get("views", views)
            interval = rule.get("interval_minutes", interval)
            mode = rule.get("name", f"regel{i + 1}")
            break
    seconds = interval * 60
    slot = int(probe.timestamp() // seconds)
    view = views[slot % len(views)]
    slot_end = datetime.fromtimestamp((slot + 1) * seconds, tz=now.tzinfo)
    wake = min(slot_end, next_boundary)
    return Plan(view, list(views), _sleep(wake, now), mode)


def _sleep(wake, now):
    seconds = int((wake - now).total_seconds()) + MARGIN_SECONDS
    return max(MIN_SLEEP, min(MAX_SLEEP, seconds))
