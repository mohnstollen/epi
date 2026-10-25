"""Datenquellen: DWD ICON-D2 (über Open-Meteo), Tankerkönig, tagesschau-RSS."""
import html
import json
import logging
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

USER_AGENT = "epi-dashboard/1.0 (Raspberry Pi e-Paper)"
OPEN_METEO_DWD = "https://api.open-meteo.com/v1/dwd-icon"
TANKERKOENIG_LIST = "https://creativecommons.tankerkoenig.de/json/list.php"


def _get(url, params=None, timeout=20):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_json(url, params=None):
    return json.loads(_get(url, params))


@dataclass
class CurrentWeather:
    temperature: float
    apparent_temperature: float | None
    humidity: float | None
    wind_speed: float | None
    weather_code: int
    is_day: bool


@dataclass
class DayForecast:
    day: date
    weather_code: int
    temp_max: float
    temp_min: float
    precipitation: float | None


@dataclass
class HourValue:
    time: datetime
    temperature: float
    precipitation: float


@dataclass
class Station:
    brand: str
    name: str
    street: str
    place: str
    distance_km: float
    price: float


def fetch_current_weather(cfg):
    """Aktuelles Wetter aus dem DWD-Modell ICON-D2 (2,2 km, nur Mitteleuropa)."""
    params = {
        "latitude": cfg.latitude,
        "longitude": cfg.longitude,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "weather_code,is_day,wind_speed_10m",
        "timezone": cfg.timezone,
    }
    cur = _get_json(OPEN_METEO_DWD, {**params, "models": "icon_d2"})["current"]
    if cur.get("temperature_2m") is None or cur.get("weather_code") is None:
        # Standort außerhalb des ICON-D2-Gebiets: auf ICON-EU/global ausweichen
        log.warning("ICON-D2 liefert keine Daten, verwende icon_seamless")
        cur = _get_json(OPEN_METEO_DWD, {**params, "models": "icon_seamless"})["current"]
    return CurrentWeather(
        temperature=cur["temperature_2m"],
        apparent_temperature=cur.get("apparent_temperature"),
        humidity=cur.get("relative_humidity_2m"),
        wind_speed=cur.get("wind_speed_10m"),
        weather_code=int(cur["weather_code"]),
        is_day=bool(cur.get("is_day", 1)),
    )


def fetch_forecast(cfg, days=3):
    """Tagesvorhersage für die kommenden Tage (ab morgen).

    ICON-D2 reicht nur ca. 48 Stunden in die Zukunft. ``icon_seamless`` nutzt
    ICON-D2 so weit wie möglich und ergänzt danach mit ICON-EU des DWD.
    """
    d = _get_json(OPEN_METEO_DWD, {
        "latitude": cfg.latitude,
        "longitude": cfg.longitude,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "models": "icon_seamless",
        "forecast_days": days + 1,
        "timezone": cfg.timezone,
    })["daily"]
    result = []
    for i in range(1, len(d["time"])):
        if d["weather_code"][i] is None or d["temperature_2m_max"][i] is None:
            continue
        result.append(DayForecast(
            day=date.fromisoformat(d["time"][i]),
            weather_code=int(d["weather_code"][i]),
            temp_max=d["temperature_2m_max"][i],
            temp_min=d["temperature_2m_min"][i],
            precipitation=d["precipitation_sum"][i],
        ))
    return result[:days]


def fetch_hourly(cfg, hours=24):
    """Stündliche Temperatur und Niederschlag ab der aktuellen Stunde (ICON-D2)."""
    params = {
        "latitude": cfg.latitude,
        "longitude": cfg.longitude,
        "hourly": "temperature_2m,precipitation",
        "forecast_days": 2,
        "timezone": cfg.timezone,
    }
    this_hour = datetime.now(ZoneInfo(cfg.timezone)).replace(
        minute=0, second=0, microsecond=0, tzinfo=None)

    def parse(hourly):
        result = []
        for t, temp, prec in zip(hourly["time"], hourly["temperature_2m"],
                                 hourly["precipitation"]):
            t = datetime.fromisoformat(t)
            if t >= this_hour and temp is not None:
                result.append(HourValue(t, temp, prec or 0.0))
        return result[:hours]

    result = parse(_get_json(OPEN_METEO_DWD, {**params, "models": "icon_d2"})["hourly"])
    if len(result) < hours:
        log.warning("ICON-D2 liefert zu wenige Stundenwerte, verwende icon_seamless")
        result = parse(_get_json(OPEN_METEO_DWD, {**params, "models": "icon_seamless"})["hourly"])
    return result


def fetch_fuel_prices(cfg, count=3):
    """Die günstigsten geöffneten Tankstellen für E10, aufsteigend nach Preis."""
    if not cfg.tankerkoenig_api_key:
        raise RuntimeError("Kein Tankerkönig-API-Key konfiguriert")
    d = _get_json(TANKERKOENIG_LIST, {
        "lat": cfg.latitude,
        "lng": cfg.longitude,
        "rad": min(cfg.fuel_radius_km, 25),
        "sort": "price",
        "type": "e10",
        "apikey": cfg.tankerkoenig_api_key,
    })
    if not d.get("ok"):
        raise RuntimeError(f"Tankerkönig: {d.get('message', 'unbekannter Fehler')}")
    stations = []
    for s in d.get("stations", []):
        price = s.get("price")
        if not s.get("isOpen") or not isinstance(price, (int, float)) or price <= 0:
            continue
        street = " ".join(p for p in ((s.get("street") or "").strip(),
                                      (s.get("houseNumber") or "").strip()) if p)
        stations.append(Station(
            brand=(s.get("brand") or "").strip(),
            name=(s.get("name") or "").strip(),
            street=street.title() if street.isupper() else street,
            place=(s.get("place") or "").strip().title(),
            distance_km=float(s.get("dist") or 0),
            price=float(price),
        ))
    stations.sort(key=lambda s: (s.price, s.distance_km))
    return stations[:count]


def fetch_headlines(cfg, limit=10):
    root = ET.fromstring(_get(cfg.news_feed))
    titles = []
    for item in root.iter("item"):
        title = html.unescape(item.findtext("title") or "").strip()
        if title and title not in titles:
            titles.append(" ".join(title.split()))
        if len(titles) >= limit:
            break
    return titles


class Cached:
    """Hält den letzten erfolgreichen Wert und aktualisiert ihn nach ``ttl`` Sekunden.

    Schlägt eine Aktualisierung fehl, bleibt der alte Wert erhalten und
    ``stale`` wird gesetzt; ein erneuter Versuch erfolgt nach ``retry`` Sekunden.
    """

    def __init__(self, name, fetch, ttl, retry=60):
        self.name = name
        self._fetch = fetch
        self._ttl = ttl
        self._retry = retry
        self.value = None
        self.error = None
        self.updated = None  # Zeitpunkt (time.time()) des letzten Erfolgs
        self._next = 0.0

    @property
    def stale(self):
        return self.error is not None

    def get(self):
        now = time.monotonic()
        if now >= self._next:
            try:
                self.value = self._fetch()
                self.error = None
                self.updated = time.time()
                self._next = now + self._ttl
            except Exception as e:  # Netzwerk, HTTP, Parsing ...
                log.warning("%s: Aktualisierung fehlgeschlagen: %s", self.name, e)
                self.error = e
                self._next = now + self._retry
        return self.value
