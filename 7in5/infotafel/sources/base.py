"""HTTP-Hilfsfunktionen und Cache für die Datenquellen."""
import json
import logging
import time
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

USER_AGENT = "infotafel/1.0 (+https://github.com/mohnstollen/epi)"
BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class NotConfigured(Exception):
    """Die Quelle ist nicht eingerichtet (z. B. kein API-Key) – kein Fehler, nur leer."""


def get(url, params=None, timeout=20, headers=None):
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_json(url, params=None, **kw):
    return json.loads(get(url, params, **kw))


class Cached:
    """Hält den letzten erfolgreichen Wert und erneuert ihn nach ``ttl`` Sekunden.

    Schlägt eine Erneuerung fehl, bleibt der alte Wert erhalten und ``error`` ist
    gesetzt; der nächste Versuch folgt nach ``retry`` Sekunden.
    """

    def __init__(self, name, fetch, ttl, retry=120):
        self.name = name
        self._fetch = fetch
        self.ttl = ttl
        self.retry = retry
        self.value = None
        self.error = None
        self.configured = True
        self.updated = None  # time.time() des letzten Erfolgs
        self._next = 0.0

    @property
    def stale(self):
        return self.configured and self.error is not None

    def refresh(self, force=False):
        now = time.monotonic()
        if not force and now < self._next:
            return
        try:
            self.value = self._fetch()
            self.error = None
            self.configured = True
            self.updated = time.time()
            self._next = now + self.ttl
        except NotConfigured as e:
            self.configured = False
            self.error = str(e)
            self.value = None
            self._next = now + 3600
        except Exception as e:  # Netzwerk, HTTP, Parsing ...
            log.warning("%s: Aktualisierung fehlgeschlagen: %s", self.name, e)
            self.error = f"{type(e).__name__}: {e}"
            self._next = now + self.retry
