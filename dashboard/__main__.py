"""Startpunkt: python3 -m dashboard [--config config.toml] [--preview DIR | --serve] [--demo]"""
import argparse
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config, layout7in5, sources
from .screens import render_current, render_forecast, render_fuel, render_news

log = logging.getLogger("dashboard")


def build_sources(cfg, demo=False):
    if demo:
        from . import demo as data
        fetch = {
            "weather": lambda: data.CURRENT,
            "hourly": lambda: data.HOURLY,
            "forecast": lambda: data.FORECAST,
            "fuel": lambda: data.STATIONS,
            "news": lambda: data.HEADLINES,
        }
    else:
        fetch = {
            "weather": lambda: sources.fetch_current_weather(cfg),
            "hourly": lambda: sources.fetch_hourly(cfg),
            "forecast": lambda: sources.fetch_forecast(cfg),
            "fuel": lambda: sources.fetch_fuel_prices(cfg),
            "news": lambda: sources.fetch_headlines(cfg),
        }
    # Aktualisierungsintervalle in Sekunden. Tankerkönig erlaubt höchstens
    # eine Abfrage alle 5 Minuten.
    return {
        "weather": sources.Cached("Wetter", fetch["weather"], ttl=10 * 60),
        "hourly": sources.Cached("Stundenwerte", fetch["hourly"], ttl=30 * 60),
        "forecast": sources.Cached("Vorhersage", fetch["forecast"], ttl=60 * 60),
        "fuel": sources.Cached("Tankerkönig", fetch["fuel"], ttl=5 * 60, retry=5 * 60),
        "news": sources.Cached("tagesschau", fetch["news"], ttl=10 * 60),
    }


def build_screens(cfg, data):
    """Liste von (Name, Funktion now -> Bild); die Anzeige wechselt reihum."""
    def screen(renderer, *keys):
        def render(now):
            for key in keys:
                data[key].get()
            return renderer(now)
        return render

    if cfg.display == "7in5":
        return [("dashboard", screen(lambda now: layout7in5.render(cfg, data, now), *data))]
    return [
        ("wetter", screen(lambda now: render_current(cfg, data["weather"], now), "weather")),
        ("vorhersage", screen(lambda now: render_forecast(cfg, data["forecast"], now), "forecast")),
        ("sprit", screen(lambda now: render_fuel(cfg, data["fuel"], now), "fuel")),
        ("nachrichten", screen(lambda now: render_news(cfg, data["news"], now), "news")),
    ]


def preview(screens, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    for i, (name, render) in enumerate(screens, 1):
        path = outdir / f"{i}-{name}.png"
        render(datetime.now()).save(path)
        log.info("geschrieben: %s", path)


def run(cfg, screens):
    from . import epd

    panel = epd.EPD7in5V2() if cfg.display == "7in5" else epd.EPD2in7V2()

    def stop(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    i = 0
    try:
        while True:
            started = time.monotonic()
            name, render = screens[i]
            try:
                buf = panel.getbuffer(render(datetime.now()), cfg.rotate180)
                panel.init()
                panel.display(buf)
                panel.sleep()
                log.info("Anzeige: %s", name)
            except Exception:
                log.exception("Fehler beim Anzeigen von %s", name)
            i = (i + 1) % len(screens)
            time.sleep(max(1.0, cfg.interval_seconds - (time.monotonic() - started)))
    finally:
        panel.close()


def main(argv=None):
    p = argparse.ArgumentParser(prog="dashboard", description="E-Paper-Dashboard")
    p.add_argument("--config", default="config.toml", type=Path)
    p.add_argument("--display", choices=sorted(config.DISPLAYS),
                   help="Display aus der Konfiguration überschreiben")
    p.add_argument("--preview", type=Path, metavar="DIR",
                   help="alle Ansichten als PNG in DIR speichern statt aufs Display")
    p.add_argument("--serve", action="store_true",
                   help="Bild per HTTP für einen ESP32 bereitstellen statt aufs Display")
    p.add_argument("--port", type=int, default=8080, help="Port für --serve (Standard 8080)")
    p.add_argument("--demo", action="store_true", help="Beispieldaten statt Online-Abruf")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.demo and not args.config.exists():
        cfg = config.Config(latitude=52.52, longitude=13.405, location_name="Berlin")
    else:
        cfg = config.load(args.config)
    if args.display:
        cfg.display = args.display
    if cfg.interval_seconds is None:
        cfg.interval_seconds = config.DISPLAYS[cfg.display]
    data = build_sources(cfg, args.demo)
    screens = build_screens(cfg, data)
    if args.preview:
        preview(screens, args.preview)
    elif args.serve:
        from .server import serve
        serve(cfg, screens, data, port=args.port)
    else:
        run(cfg, screens)


if __name__ == "__main__":
    sys.exit(main())
