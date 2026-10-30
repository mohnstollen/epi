"""Wetter (DWD ICON über Open-Meteo), Unwetterwarnungen (DWD über Bright Sky),
Pollenflug (DWD Open Data) und Mondphase (lokal berechnet)."""
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .base import NotConfigured, get_json

OPEN_METEO_DWD = "https://api.open-meteo.com/v1/dwd-icon"
BRIGHTSKY_ALERTS = "https://api.brightsky.dev/alerts"
DWD_POLLEN = "https://opendata.dwd.de/climate_environment/health/alerts/s31fg.json"


@dataclass
class Day:
    day: date
    weather_code: int
    temp_max: float
    temp_min: float
    precipitation: float | None
    sunrise: datetime | None = None
    sunset: datetime | None = None


@dataclass
class Weather:
    temperature: float
    apparent_temperature: float | None
    weather_code: int
    is_day: bool
    wind_speed: float | None
    wind_direction: float | None
    wind_gusts: float | None
    days: list[Day] = field(default_factory=list)  # days[0] = heute


def _dt(text, tz):
    return datetime.fromisoformat(text).replace(tzinfo=tz) if text else None


def fetch_weather(cfg):
    tz = ZoneInfo(cfg["timezone"])
    d = get_json(OPEN_METEO_DWD, {
        "latitude": cfg["latitude"],
        "longitude": cfg["longitude"],
        "current": "temperature_2m,apparent_temperature,weather_code,is_day,"
                   "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,sunrise,sunset",
        "models": "icon_seamless",  # ICON-D2, danach ICON-EU/global
        "forecast_days": 4,
        "timezone": cfg["timezone"],
    })
    cur, daily = d["current"], d["daily"]
    days = []
    for i, t in enumerate(daily["time"]):
        if daily["weather_code"][i] is None or daily["temperature_2m_max"][i] is None:
            continue
        days.append(Day(
            day=date.fromisoformat(t),
            weather_code=int(daily["weather_code"][i]),
            temp_max=daily["temperature_2m_max"][i],
            temp_min=daily["temperature_2m_min"][i],
            precipitation=daily["precipitation_sum"][i],
            sunrise=_dt(daily.get("sunrise", [None] * (i + 1))[i], tz),
            sunset=_dt(daily.get("sunset", [None] * (i + 1))[i], tz),
        ))
    return Weather(
        temperature=cur["temperature_2m"],
        apparent_temperature=cur.get("apparent_temperature"),
        weather_code=int(cur["weather_code"]),
        is_day=bool(cur.get("is_day", 1)),
        wind_speed=cur.get("wind_speed_10m"),
        wind_direction=cur.get("wind_direction_10m"),
        wind_gusts=cur.get("wind_gusts_10m"),
        days=days,
    )


# --- Warnungen -------------------------------------------------------------

SEVERITY_RANK = {"minor": 1, "moderate": 2, "severe": 3, "extreme": 4}


@dataclass
class Warning:
    severity: str      # minor, moderate, severe, extreme
    event: str         # z. B. "STURMBÖEN"
    headline: str      # z. B. "Amtliche WARNUNG vor STURMBÖEN"
    description: str
    onset: datetime | None
    expires: datetime | None

    @property
    def rank(self):
        return SEVERITY_RANK.get(self.severity, 0)


def parse_alerts(d, tz):
    result = []
    for a in d.get("alerts", []):
        if a.get("status", "actual") != "actual":
            continue
        result.append(Warning(
            severity=(a.get("severity") or "minor").lower(),
            event=(a.get("event_de") or a.get("event_en") or "").strip(),
            headline=(a.get("headline_de") or a.get("headline_en") or "").strip(),
            description=" ".join((a.get("description_de") or a.get("description_en") or "").split()),
            onset=datetime.fromisoformat(a["onset"]).astimezone(tz) if a.get("onset") else None,
            expires=datetime.fromisoformat(a["expires"]).astimezone(tz) if a.get("expires") else None,
        ))
    result.sort(key=lambda w: (-w.rank, w.onset or datetime.max.replace(tzinfo=tz)))
    return result


def fetch_warnings(cfg):
    if not cfg["warnings"]["enabled"]:
        raise NotConfigured("warnings.enabled = false")
    tz = ZoneInfo(cfg["timezone"])
    d = get_json(BRIGHTSKY_ALERTS, {"lat": cfg["latitude"], "lon": cfg["longitude"], "tz": cfg["timezone"]})
    return parse_alerts(d, tz)


def active_warnings(warnings, now, min_severity):
    """Warnungen ab ``min_severity``, die jetzt gelten oder in den nächsten 12 h beginnen."""
    if not warnings:
        return []
    rank = SEVERITY_RANK[min_severity]
    soon = now + timedelta(hours=12)
    return [w for w in warnings
            if w.rank >= rank
            and (w.expires is None or w.expires > now)
            and (w.onset is None or w.onset < soon)]


# --- Pollen ----------------------------------------------------------------

POLLEN_KEYS = {  # Anzeige-Name -> Schlüssel im DWD-JSON
    "Hasel": "Hasel", "Erle": "Erle", "Esche": "Esche", "Birke": "Birke",
    "Gräser": "Graeser", "Roggen": "Roggen", "Beifuß": "Beifuss", "Ambrosia": "Ambrosia",
}


def _level(text):
    """'0', '0-1', '1-2' ... -> 0.0, 0.5, 1.5 ...; '-1' oder Unbekanntes -> None."""
    text = str(text).strip()
    if "-" in text[1:]:
        a, b = text.split("-", 1)
        return (float(a) + float(b)) / 2
    try:
        v = float(text)
    except ValueError:
        return None
    return v if v >= 0 else None


def parse_pollen(d, partregion_id):
    for entry in d.get("content", []):
        pid = entry.get("partregion_id")
        if pid in (-1, None):
            pid = entry.get("region_id")
        if int(pid) != int(partregion_id):
            continue
        pollen = entry.get("Pollen", {})
        result = {}
        for name, key in POLLEN_KEYS.items():
            values = pollen.get(key) or pollen.get(name) or {}
            result[name] = (_level(values.get("today", -1)), _level(values.get("tomorrow", -1)))
        return result
    raise ValueError(f"Pollen: Teilregion {partregion_id} nicht gefunden")


def fetch_pollen(cfg):
    if not cfg["pollen"]["enabled"]:
        raise NotConfigured("pollen.enabled = false")
    return parse_pollen(get_json(DWD_POLLEN), cfg["pollen"]["partregion_id"])


# --- Mond --------------------------------------------------------------------

SYNODIC = 29.530588853
_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
PHASE_NAMES = ["Neumond", "Zunehmende Sichel", "Erstes Viertel", "Zunehmender Mond",
               "Vollmond", "Abnehmender Mond", "Letztes Viertel", "Abnehmende Sichel"]


@dataclass
class Moon:
    age: float           # Tage seit Neumond, 0 … 29.5
    illumination: float  # 0 … 1
    name: str
    days_to_full: int
    days_to_new: int

    @property
    def waxing(self):
        return self.age < SYNODIC / 2


def moon(now):
    age = ((now - _NEW_MOON).total_seconds() / 86400) % SYNODIC
    illum = (1 - math.cos(2 * math.pi * age / SYNODIC)) / 2
    idx = int((age / SYNODIC) * 8 + 0.5) % 8
    to_full = (SYNODIC / 2 - age) % SYNODIC
    to_new = (SYNODIC - age) % SYNODIC
    return Moon(age, illum, PHASE_NAMES[idx], round(to_full), round(to_new))
