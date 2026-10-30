"""Alle Datenquellen mit Aktualisierungsintervall, gebündelt in ``Data``."""
import logging
import threading
import time

from . import info, mobility, weather
from .base import Cached

log = logging.getLogger(__name__)

# Name -> (Abruffunktion, Gültigkeit in s, Wiederholung nach Fehler in s)
SOURCES = {
    "weather": (weather.fetch_weather, 15 * 60, 120),
    "warnings": (weather.fetch_warnings, 5 * 60, 120),
    "pollen": (weather.fetch_pollen, 3 * 3600, 600),
    "fuel": (mobility.fetch_fuel, 5 * 60, 300),          # Tankerkönig: höchstens alle 5 min
    "departures": (mobility.fetch_departures, 60, 60),
    "routes": (mobility.fetch_routes, 5 * 60, 180),
    "incidents": (mobility.fetch_incidents, 5 * 60, 180),
    "news": (info.fetch_news, 10 * 60, 180),
    "markets": (info.fetch_markets, 15 * 60, 300),
    "calendar": (info.fetch_calendar, 30 * 60, 300),
    "vacations": (info.fetch_vacations, 24 * 3600, 3600),
}


class Data:
    """Hält die zuletzt geladenen Daten aller Quellen.

    ``refresh()`` holt fällige Quellen neu (im Hintergrund-Thread des Servers);
    beim Zeichnen wird nur gelesen, nie abgerufen.
    """

    def __init__(self, cfg, only=None):
        self.cfg = cfg
        self._lock = threading.Lock()
        self.sources = {
            name: Cached(name, (lambda f=f: f(cfg)), ttl, retry)
            for name, (f, ttl, retry) in SOURCES.items()
            if only is None or name in only
        }

    def refresh(self, force=False):
        for c in self.sources.values():
            c.refresh(force)

    def refresh_forever(self, period=30):
        while True:
            try:
                self.refresh()
            except Exception:
                log.exception("Unerwarteter Fehler beim Aktualisieren")
            time.sleep(period)

    def get(self, name):
        c = self.sources.get(name)
        return c.value if c else None

    def stale(self, *names):
        """True, wenn eine der Quellen eingerichtet ist, aber keine aktuellen Daten hat."""
        return any(self.sources[n].stale for n in names if n in self.sources)

    def status(self):
        return {
            name: {
                "configured": c.configured,
                "ok": c.configured and c.error is None and c.value is not None,
                "error": c.error,
                "updated": c.updated,
            }
            for name, c in self.sources.items()
        }


class StaticData(Data):
    """Feste Werte (Demo-Modus und Tests)."""

    def __init__(self, cfg, values):
        self.cfg = cfg
        self.sources = {}
        for name in SOURCES:
            c = Cached(name, lambda: None, 1e9)
            c.value = values.get(name)
            c.updated = time.time()
            self.sources[name] = c

    def refresh(self, force=False):
        pass
