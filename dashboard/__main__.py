"""Startpunkt: python3 -m dashboard [--config config.toml] [--preview DIR] [--demo]"""
import argparse
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config, sources
from .screens import render_current, render_forecast, render_fuel, render_news

log = logging.getLogger("dashboard")


def build_screens(cfg, demo=False):
    if demo:
        from . import demo as data
        fetch = {
            "weather": lambda: data.CURRENT,
            "forecast": lambda: data.FORECAST,
            "fuel": lambda: data.STATIONS,
            "news": lambda: data.HEADLINES,
        }
    else:
        fetch = {
            "weather": lambda: sources.fetch_current_weather(cfg),
            "forecast": lambda: sources.fetch_forecast(cfg),
            "fuel": lambda: sources.fetch_fuel_prices(cfg),
            "news": lambda: sources.fetch_headlines(cfg),
        }
    # Aktualisierungsintervalle in Sekunden. Tankerkönig erlaubt höchstens
    # eine Abfrage alle 5 Minuten; die Anzeige wechselt ohnehin nur alle 12.
    weather = sources.Cached("Wetter", fetch["weather"], ttl=10 * 60)
    forecast = sources.Cached("Vorhersage", fetch["forecast"], ttl=60 * 60)
    fuel = sources.Cached("Tankerkönig", fetch["fuel"], ttl=5 * 60, retry=5 * 60)
    news = sources.Cached("tagesschau", fetch["news"], ttl=10 * 60)
    return [
        ("wetter", weather, render_current),
        ("vorhersage", forecast, render_forecast),
        ("sprit", fuel, render_fuel),
        ("nachrichten", news, render_news),
    ]


def render(cfg, screen):
    _, cached, renderer = screen
    cached.get()
    return renderer(cfg, cached, datetime.now())


def preview(cfg, screens, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    for i, screen in enumerate(screens, 1):
        path = outdir / f"{i}-{screen[0]}.png"
        render(cfg, screen).save(path)
        log.info("geschrieben: %s", path)


def run(cfg, screens):
    from .epd2in7_v2 import EPD

    epd = EPD()

    def stop(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    i = 0
    try:
        while True:
            started = time.monotonic()
            screen = screens[i]
            try:
                buf = epd.getbuffer(render(cfg, screen), cfg.rotate180)
                epd.init()
                epd.display(buf)
                epd.sleep()
                log.info("Anzeige: %s", screen[0])
            except Exception:
                log.exception("Fehler beim Anzeigen von %s", screen[0])
            i = (i + 1) % len(screens)
            time.sleep(max(1.0, cfg.interval_seconds - (time.monotonic() - started)))
    finally:
        epd.close()


def main(argv=None):
    p = argparse.ArgumentParser(prog="dashboard", description="E-Paper-Dashboard")
    p.add_argument("--config", default="config.toml", type=Path)
    p.add_argument("--preview", type=Path, metavar="DIR",
                   help="alle Ansichten als PNG in DIR speichern statt aufs Display")
    p.add_argument("--demo", action="store_true", help="Beispieldaten statt Online-Abruf")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.demo and not args.config.exists():
        cfg = config.Config(latitude=52.52, longitude=13.405, location_name="Berlin")
    else:
        cfg = config.load(args.config)
    screens = build_screens(cfg, args.demo)
    if args.preview:
        preview(cfg, screens, args.preview)
    else:
        run(cfg, screens)


if __name__ == "__main__":
    sys.exit(main())
