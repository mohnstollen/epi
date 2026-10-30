"""HTTP-Server für den ESP32.

Endpunkte:
  /image.bin   Displaypuffer (48000 Bytes) der aktuellen Ansicht.
               Antwort-Header: ETag, X-Sleep-Seconds (wie lange der ESP32 schlafen soll),
               X-View. Schickt der ESP32 ``If-None-Match`` mit dem ETag seines
               aktuellen Bildes und hat sich nichts geändert, kommt 304 – das Display
               bleibt dann unangetastet (spart Refreshs).
  /image.png   dasselbe als PNG; ?view=wetter zeigt eine bestimmte Ansicht
  /status.json Zustand aller Datenquellen (Fehler, letzte Aktualisierung)
  /            Vorschauseite mit allen Ansichten
"""
import json
import logging
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from .app import etag, make_frame
from .config import VIEWS

log = logging.getLogger(__name__)

PAGE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Infotafel</title>
<style>body{{font-family:system-ui,sans-serif;background:#e5e5e5;margin:16px;color:#111}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:16px}}
figure{{margin:0}}img{{width:100%;background:#fff;border:1px solid #999;image-rendering:pixelated}}
figcaption{{font-weight:600;margin:4px 0}}table{{border-collapse:collapse;margin-top:16px;width:100%}}
td,th{{text-align:left;padding:4px 8px;border-bottom:1px solid #bbb;vertical-align:top}}
.err{{color:#a00}}</style></head><body>
<h1>Infotafel</h1><p>Jetzt: <b>{view}</b> ({mode}), ESP32 schläft danach {sleep} s.</p>
<div class="grid">{figures}</div>
<h2>Datenquellen</h2><table><tr><th>Quelle</th><th>Status</th><th>Stand</th></tr>{rows}</table>
</body></html>"""


class Server:
    def __init__(self, cfg, data):
        self.cfg = cfg
        self.data = data
        self.tz = ZoneInfo(cfg["timezone"])
        self._lock = threading.Lock()

    def now(self):
        return datetime.now(self.tz)

    def frame(self, view=None):
        with self._lock:   # Zeichnen ist schnell; Lock schützt Pillow/Fonts vor Parallelzugriff
            return make_frame(self.cfg, self.data, self.now(), view)

    def page(self):
        f = self.frame()
        figures = "".join(
            f'<figure><figcaption>{v}{" (jetzt)" if v == f.view else ""}</figcaption>'
            f'<img src="image.png?view={v}&t={int(time.time())}" alt="{v}"></figure>'
            for v in VIEWS)
        rows = []
        for name, s in self.data.status().items():
            if not s["configured"]:
                state = f"nicht eingerichtet ({s['error']})"
            elif s["ok"]:
                state = "ok"
            else:
                state = f'<span class="err">{s["error"] or "noch keine Daten"}</span>'
            when = datetime.fromtimestamp(s["updated"], self.tz).strftime("%d.%m. %H:%M:%S") if s["updated"] else "–"
            rows.append(f"<tr><td>{name}</td><td>{state}</td><td>{when}</td></tr>")
        return PAGE.format(view=f.view, mode=f.mode, sleep=f.sleep_seconds,
                           figures=figures, rows="".join(rows)).encode()


def make_handler(server):
    class Handler(BaseHTTPRequestHandler):
        server_version = "infotafel"

        def _send(self, code, body=b"", ctype=None, headers=None):
            self.send_response(code)
            for k, v in (headers or {}).items():
                self.send_header(k, str(v))
            if ctype:
                self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body and self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            try:
                if url.path == "/image.bin":
                    f = server.frame()
                    buf = f.to_buffer(server.cfg["rotate180"])
                    tag = etag(buf)
                    headers = {"ETag": f'"{tag}"', "X-Sleep-Seconds": f.sleep_seconds, "X-View": f.view}
                    if self.headers.get("If-None-Match", "").strip('" ') == tag:
                        self._send(304, headers=headers)
                    else:
                        self._send(200, buf, "application/octet-stream", headers)
                elif url.path == "/image.png":
                    view = query.get("view", [None])[0]
                    if view and view not in VIEWS:
                        self._send(404, b"unbekannte Ansicht", "text/plain; charset=utf-8")
                        return
                    f = server.frame(view)
                    self._send(200, f.png(), "image/png", {"X-View": f.view})
                elif url.path == "/status.json":
                    body = json.dumps(server.data.status(), indent=2, ensure_ascii=False).encode()
                    self._send(200, body, "application/json; charset=utf-8")
                elif url.path == "/":
                    self._send(200, server.page(), "text/html; charset=utf-8")
                else:
                    self._send(404, b"nicht gefunden", "text/plain; charset=utf-8")
            except Exception:
                log.exception("Fehler bei %s", self.path)
                self._send(500, b"interner Fehler", "text/plain; charset=utf-8")

        do_HEAD = do_GET

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

    return Handler


def serve(cfg, data, host="0.0.0.0", port=8080):
    server = Server(cfg, data)
    threading.Thread(target=data.refresh_forever, daemon=True, name="daten").start()
    httpd = ThreadingHTTPServer((host, port), make_handler(server))
    log.info("Infotafel läuft auf http://%s:%d/", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
