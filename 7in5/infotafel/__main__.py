"""Kommandozeile.

  python -m infotafel serve   [--config config.toml] [--port 8080] [--demo]
  python -m infotafel preview [--config config.toml] [--out preview] [--demo] [--at 2026-10-30T07:30]
  python -m infotafel check   [--config config.toml]       Datenquellen einmal abrufen, Ergebnis zeigen
  python -m infotafel haltestelle "Herzogenaurach Münchener"  Haltestellen-ID suchen
"""
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config as config_mod
from .app import make_frame
from .config import VIEWS


def _load(args):
    if args.demo:
        from .demo import demo_config
        return demo_config()
    path = Path(args.config)
    if not path.is_file():
        sys.exit(f"Konfiguration {path} nicht gefunden. Vorlage: cp config.example.toml config.toml "
                 "(oder --demo für Beispieldaten)")
    return config_mod.load(path)


def _data(cfg, args, now):
    if args.demo:
        from .demo import demo_values
        from .sources import StaticData
        return StaticData(cfg, demo_values(now))
    from .sources import Data
    return Data(cfg)


def _now(cfg, args):
    tz = ZoneInfo(cfg["timezone"])
    if getattr(args, "at", None):
        return datetime.fromisoformat(args.at).replace(tzinfo=tz)
    return datetime.now(tz)


def cmd_serve(args):
    from .server import serve
    cfg = _load(args)
    serve(cfg, _data(cfg, args, _now(cfg, args)), args.host, args.port)


def cmd_preview(args):
    cfg = _load(args)
    now = _now(cfg, args)
    data = _data(cfg, args, now)
    if not args.demo:
        print("Lade Daten …")
        data.refresh(force=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for i, view in enumerate(VIEWS, 1):
        f = make_frame(cfg, data, now, view)
        path = out / f"{i}-{view}.png"
        f.image.save(path)
        print(path)
    f = make_frame(cfg, data, now)
    print(f"Zum Zeitpunkt {now:%d.%m. %H:%M}: Ansicht {f.view} ({f.mode}), danach {f.sleep_seconds} s schlafen")


def cmd_check(args):
    cfg = _load(args)
    from .sources import Data
    data = Data(cfg)
    ok = True
    for name, c in data.sources.items():
        c.refresh(force=True)
        if not c.configured:
            print(f"  –  {name:11} nicht eingerichtet: {c.error}")
            continue
        if c.error:
            ok = False
            print(f"  ✗  {name:11} FEHLER: {c.error}")
            continue
        v = c.value
        summary = f"{len(v)} Einträge" if isinstance(v, (list, dict)) else type(v).__name__
        first = v[0] if isinstance(v, list) and v else None
        print(f"  ✓  {name:11} {summary}" + (f" – z. B. {first}" if first else ""))
    sys.exit(0 if ok else 1)


def cmd_stop(args):
    cfg = _load(args) if Path(args.config).is_file() else config_mod.load()
    if args.provider:
        cfg["transit"]["provider"] = args.provider
    from .sources.mobility import find_stops
    for name, sid in find_stops(cfg, args.name):
        print(f"{sid!s:>12}  {name}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="infotafel", description="E-Paper-Infotafel (7.5\", 800x480)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, demo=True):
        sp.add_argument("--config", default="config.toml")
        if demo:
            sp.add_argument("--demo", action="store_true", help="Beispieldaten statt Online-Abruf")

    sp = sub.add_parser("serve", help="Bildserver für den ESP32 starten")
    common(sp)
    sp.add_argument("--host", default="0.0.0.0")
    sp.add_argument("--port", type=int, default=8080)
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("preview", help="alle Ansichten als PNG speichern")
    common(sp)
    sp.add_argument("--out", default="preview")
    sp.add_argument("--at", help="Zeitpunkt simulieren, z. B. 2026-10-30T07:30")
    sp.set_defaults(func=cmd_preview)

    sp = sub.add_parser("check", help="alle Datenquellen abrufen und Ergebnis anzeigen")
    common(sp, demo=False)
    sp.set_defaults(func=cmd_check, demo=False)

    sp = sub.add_parser("haltestelle", help="Haltestellen-ID suchen")
    sp.add_argument("name")
    sp.add_argument("--config", default="config.toml")
    sp.add_argument("--provider", choices=["vgn", "db"])
    sp.set_defaults(func=cmd_stop, demo=False)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
