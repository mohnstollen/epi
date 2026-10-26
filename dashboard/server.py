"""HTTP-Server, der das aktuelle Dashboard-Bild für einen ESP32 bereitstellt.

Endpunkte:
  /image.bin  Rohdaten für das Display (Format siehe ``epd.to_buffer``).
              Header ``X-Next-Refresh``: Sekunden bis zum nächsten Bildwechsel.
  /image.png  dasselbe Bild als PNG, zur Kontrolle im Browser
  /           kleine Vorschauseite

Die Zeit wird in Abschnitte von ``interval_seconds`` geteilt; jeder Abschnitt
zeigt eine Ansicht (beim 2.7"-Display reihum). So bleiben Pi und ESP32 ohne
gemeinsamen Zustand im Takt: Der ESP32 schläft einfach bis zum nächsten Abschnitt.
"""
import io
import logging
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import epd

log = logging.getLogger(__name__)

PREFETCH_SECONDS = 60
MARGIN_SECONDS = 2   # ESP32 erst kurz nach dem Wechsel aufwecken
LEAD_SECONDS = 15    # Wer bis zu so viel zu früh fragt (ungenauer Schlaf-Timer
                     # des ESP32), bekommt schon die nächste Ansicht


class Dashboard:
    def __init__(self, cfg, screens, data):
        self._cfg = cfg
        self._screens = screens
        self._data = data
        self._lock = threading.Lock()
        self._slot = None
        self._bin = self._png = b""

    def prefetch_forever(self):
        """Hält die Daten im Hintergrund aktuell, damit Abrufe schnell beantwortet werden."""
        while True:
            with self._lock:
                for cached in self._data.values():
                    cached.get()
            time.sleep(PREFETCH_SECONDS)

    def current(self):
        """Liefert (bin, png, Sekunden bis zum nächsten Wechsel)."""
        interval = self._cfg.interval_seconds
        now = time.time()
        slot = int((now + LEAD_SECONDS) // interval)
        with self._lock:
            if slot != self._slot:
                name, render = self._screens[slot % len(self._screens)]
                image = render(datetime.now())
                self._bin = epd.to_buffer(image, self._cfg.display, self._cfg.rotate180)
                png = io.BytesIO()
                image.save(png, "PNG")
                self._png = png.getvalue()
                self._slot = slot
                log.info("Ansicht gerendert: %s", name)
            bin_, png = self._bin, self._png
        next_refresh = int((slot + 1) * interval - now) + MARGIN_SECONDS
        return bin_, png, next_refresh


PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{refresh}"><title>E-Paper-Dashboard</title>
<style>body{{background:#ddd;font-family:sans-serif;text-align:center;margin:16px}}
img{{max-width:100%;image-rendering:pixelated;border:1px solid #888;background:#fff}}</style>
</head><body><img src="image.png?{slot}" alt="Dashboard"><p>Nächster Wechsel in {refresh} s</p>
</body></html>"""


def make_handler(dashboard):
    class Handler(BaseHTTPRequestHandler):
        server_version = "epi-dashboard"

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path not in ("/", "/image.bin", "/image.png"):
                self.send_error(404)
                return
            try:
                bin_, png, next_refresh = dashboard.current()
            except Exception:
                log.exception("Rendern fehlgeschlagen")
                self.send_error(500)
                return
            if path == "/image.bin":
                body, ctype = bin_, "application/octet-stream"
            elif path == "/image.png":
                body, ctype = png, "image/png"
            else:
                body = PAGE.format(refresh=next_refresh, slot=int(time.time())).encode()
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Next-Refresh", str(next_refresh))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

    return Handler


def serve(cfg, screens, data, host="0.0.0.0", port=8080):
    dashboard = Dashboard(cfg, screens, data)
    threading.Thread(target=dashboard.prefetch_forever, daemon=True).start()
    httpd = ThreadingHTTPServer((host, port), make_handler(dashboard))
    log.info("Server läuft auf http://%s:%d/ (Display %s, Wechsel alle %d s)",
             host, port, cfg.display, cfg.interval_seconds)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
