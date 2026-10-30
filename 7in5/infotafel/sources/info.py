"""Schlagzeilen (RSS/Atom), Kurse (Yahoo Finance), Kalender (ICS), Geburtstage,
Feiertage (Bayern, lokal berechnet) und Schulferien (OpenHolidays API)."""
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from .base import BROWSER_UA, NotConfigured, get, get_json

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
OPENHOLIDAYS = "https://openholidaysapi.org/SchoolHolidays"


# --- Nachrichten ---------------------------------------------------------------

@dataclass
class Headline:
    title: str
    published: datetime | None


def _parse_date(text, tz):
    if not text:
        return None
    text = text.strip()
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def parse_feed(raw, tz):
    root = ET.fromstring(raw)
    items = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        title = date_text = None
        for child in el:
            ctag = child.tag.rsplit("}", 1)[-1]
            if ctag == "title":
                title = child.text
            elif ctag in ("pubDate", "published", "updated", "date") and not date_text:
                date_text = child.text
        title = " ".join(html.unescape(title or "").split())
        if title:
            items.append(Headline(title, _parse_date(date_text, tz)))
    return items


def fetch_news(cfg):
    nc = cfg["news"]
    if not nc["feeds"]:
        raise NotConfigured("news.feeds leer")
    tz = ZoneInfo(cfg["timezone"])
    items = []
    for url in nc["feeds"]:
        items += parse_feed(get(url), tz)
    seen, result = set(), []
    for h in items:
        if h.title not in seen:
            seen.add(h.title)
            result.append(h)
    if len(nc["feeds"]) > 1:
        far_past = datetime(1970, 1, 1, tzinfo=tz)
        result.sort(key=lambda h: h.published or far_past, reverse=True)
    return result[:20]


# --- Kurse ---------------------------------------------------------------------

@dataclass
class Quote:
    name: str
    unit: str
    decimals: int
    price: float
    previous: float | None
    history: list[float]        # Schlusskurse, letzter Wert = aktueller Kurs
    time: datetime | None

    @property
    def change_pct(self):
        if not self.previous:
            return None
        return (self.price / self.previous - 1) * 100


def parse_chart(d, item, tz, points=10):
    r = d["chart"]["result"][0]
    meta = r["meta"]
    price = meta.get("regularMarketPrice")
    t_market = meta.get("regularMarketTime")
    market_time = datetime.fromtimestamp(t_market, tz) if t_market else None
    closes = r.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    stamps = r.get("timestamp", [])
    series = [(datetime.fromtimestamp(t, tz).date(), c) for t, c in zip(stamps, closes) if c is not None]
    if price is None and series:
        price = series[-1][1]
    previous = None
    if market_time:
        earlier = [c for day, c in series if day < market_time.date()]
        previous = earlier[-1] if earlier else meta.get("chartPreviousClose")
    history = [c for day, c in series if not market_time or day < market_time.date()][-(points - 1):]
    history.append(price)
    return Quote(
        name=item.get("name", item["symbol"]), unit=item.get("unit", ""),
        decimals=int(item.get("decimals", 2)), price=float(price),
        previous=previous, history=history, time=market_time,
    )


def fetch_markets(cfg):
    items = cfg["markets"]["items"]
    if not items:
        raise NotConfigured("markets.items leer")
    tz = ZoneInfo(cfg["timezone"])
    result = []
    for item in items:
        d = get_json(YAHOO_CHART.format(symbol=item["symbol"].replace("^", "%5E")),
                     {"range": "1mo", "interval": "1d"}, headers={"User-Agent": BROWSER_UA})
        result.append(parse_chart(d, item, tz))
    return result


# --- Kalender -----------------------------------------------------------------

@dataclass
class Event:
    title: str
    start: datetime
    all_day: bool
    symbol: str = ""   # "tonne", "geburtstag" oder leer


def parse_ics(raw, tz, start, end, symbol=""):
    import icalendar
    import recurring_ical_events

    cal = icalendar.Calendar.from_ical(raw)
    result = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        dt = ev.get("DTSTART").dt
        all_day = not isinstance(dt, datetime)
        if all_day:
            dt = datetime(dt.year, dt.month, dt.day, tzinfo=tz)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        title = " ".join(str(ev.get("SUMMARY", "")).split()) or "(ohne Titel)"
        result.append(Event(title, dt.astimezone(tz), all_day, symbol))
    return result


def fetch_calendar(cfg):
    cc = cfg["calendar"]
    feeds = [f for f in cc["feeds"] if f.get("url")]
    if not feeds:
        raise NotConfigured("calendar.feeds leer")
    tz = ZoneInfo(cfg["timezone"])
    today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    end = today + timedelta(days=int(cc["days"]) + 1)
    events = []
    for f in feeds:
        url = f["url"].replace("webcal://", "https://", 1)
        events += parse_ics(get(url, timeout=30), tz, today, end, f.get("symbol", ""))
    events.sort(key=lambda e: (e.start.date(), not e.all_day, e.start))
    return events


# --- Geburtstage -------------------------------------------------------------

@dataclass
class Birthday:
    name: str
    day: date          # nächster Geburtstag (heute oder später)
    age: int | None    # Alter an diesem Tag, falls Geburtsjahr bekannt


def _parse_birthdate(text):
    text = str(text).strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text) or None
    if m:
        return int(m[1]), int(m[2]), int(m[3])
    m = re.fullmatch(r"(?:--)?(\d{1,2})-(\d{1,2})", text)
    if m:
        return None, int(m[1]), int(m[2])
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})?", text)
    if m:
        return (int(m[3]) if m[3] else None), int(m[2]), int(m[1])
    raise ValueError(f"Geburtsdatum {text!r}: JJJJ-MM-TT, MM-TT oder TT.MM.[JJJJ]")


def _on(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:      # 29. Februar in Nicht-Schaltjahren -> 28.
        return date(year, month, day - 1)


def upcoming_birthdays(cfg, today):
    result = []
    for b in cfg["birthdays"]:
        year, month, day = _parse_birthdate(b["date"])
        nxt = _on(today.year, month, day)
        if nxt < today:
            nxt = _on(today.year + 1, month, day)
        result.append(Birthday(b["name"], nxt, nxt.year - year if year else None))
    result.sort(key=lambda b: b.day)
    return result


# --- Feiertage und Ferien ------------------------------------------------------

@dataclass
class Holiday:
    name: str
    day: date
    school_only: bool = False   # z. B. Buß- und Bettag: schulfrei, kein Feiertag


def easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def bavarian_holidays(year, cfg):
    hc = cfg["holidays"]
    e = easter(year)
    days = [
        ("Neujahr", date(year, 1, 1)),
        ("Heilige Drei Könige", date(year, 1, 6)),
        ("Karfreitag", e - timedelta(days=2)),
        ("Ostermontag", e + timedelta(days=1)),
        ("Tag der Arbeit", date(year, 5, 1)),
        ("Christi Himmelfahrt", e + timedelta(days=39)),
        ("Pfingstmontag", e + timedelta(days=50)),
        ("Fronleichnam", e + timedelta(days=60)),
        ("Tag der Deutschen Einheit", date(year, 10, 3)),
        ("Allerheiligen", date(year, 11, 1)),
        ("1. Weihnachtstag", date(year, 12, 25)),
        ("2. Weihnachtstag", date(year, 12, 26)),
    ]
    if hc["mariae_himmelfahrt"]:
        days.append(("Mariä Himmelfahrt", date(year, 8, 15)))
    if hc["augsburger_friedensfest"]:
        days.append(("Friedensfest", date(year, 8, 8)))
    result = [Holiday(n, d) for n, d in days]
    # Buß- und Bettag: Mittwoch vor dem 23. November, in Bayern schulfrei
    nov22 = date(year, 11, 22)
    result.append(Holiday("Buß- und Bettag", nov22 - timedelta(days=(nov22.weekday() - 2) % 7), True))
    return sorted(result, key=lambda h: h.day)


def upcoming_holidays(cfg, today, count=3):
    days = bavarian_holidays(today.year, cfg) + bavarian_holidays(today.year + 1, cfg)
    return [h for h in days if h.day >= today][:count]


@dataclass
class Vacation:
    name: str
    start: date
    end: date   # letzter Ferientag


def parse_openholidays(d):
    result = []
    for v in d:
        names = v.get("name") or []
        name = next((n["text"] for n in names if n.get("language") == "DE"), None) \
            or (names[0]["text"] if names else "Ferien")
        result.append(Vacation(name, date.fromisoformat(v["startDate"]), date.fromisoformat(v["endDate"])))
    return sorted(result, key=lambda v: v.start)


def fetch_vacations(cfg):
    hc = cfg["holidays"]
    result = [Vacation(v["name"], date.fromisoformat(str(v["start"])), date.fromisoformat(str(v["end"])))
              for v in hc["extra_school_holidays"]]
    if hc["school_holidays"]:
        today = datetime.now(ZoneInfo(cfg["timezone"])).date()
        d = get_json(OPENHOLIDAYS, {
            "countryIsoCode": "DE", "subdivisionCode": "DE-BY", "languageIsoCode": "DE",
            "validFrom": today.replace(day=1).isoformat(),
            "validTo": date(today.year + 1, 12, 31).isoformat(),
        })
        result += parse_openholidays(d)
    if not result:
        raise NotConfigured("holidays.school_holidays = false und keine eigenen Ferien")
    return sorted(result, key=lambda v: v.start)


def vacation_status(vacations, today):
    """(Ferien, laufen gerade?) – die laufenden oder nächsten Ferien."""
    for v in vacations or []:
        if v.start <= today <= v.end:
            return v, True
        if v.start > today:
            return v, False
    return None, False
