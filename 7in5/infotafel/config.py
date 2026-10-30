"""Konfiguration: config.toml laden, mit Standardwerten ergänzen, ${VARIABLEN} aus .env einsetzen.

Geheimnisse (API-Keys, private Kalender-Links) stehen in der .env-Datei bzw. in
Umgebungsvariablen und werden in der config.toml als "${NAME}" referenziert.
"""
import copy
import logging
import os
import re
import tomllib
from pathlib import Path

log = logging.getLogger(__name__)

VIEWS = ("unterwegs", "wetter", "nachrichten", "termine")
DAYS = ("mo", "di", "mi", "do", "fr", "sa", "so")
SEVERITIES = ("minor", "moderate", "severe", "extreme")
MIN_INTERVAL_MINUTES = 3  # Waveshare empfiehlt mindestens 180 s zwischen zwei Refreshs

DEFAULTS = {
    "timezone": "Europe/Berlin",
    "latitude": 49.5672,
    "longitude": 10.8819,
    "location_name": "Herzogenaurach",
    "rotate180": False,
    "schedule": {
        "interval_minutes": 5,
        "views": list(VIEWS),
        "rules": [],
        "night": {
            "enabled": True,
            "from": "22:00",
            "to": "06:00",
            "view": "termine",
            "check_minutes": 30,
            "warnings_wake": True,
        },
    },
    "warnings": {"enabled": True, "min_severity": "moderate", "night_min_severity": "severe"},
    "pollen": {"enabled": True, "partregion_id": 123, "types": ["Hasel", "Erle", "Birke", "Gräser"]},
    "fuel": {
        "api_key": "",
        "radius_km": 5.0,
        "count": 3,
        "types": ["e5", "diesel"],
        "station_ids": [],
    },
    "transit": {
        "provider": "vgn",
        "stop_id": "",
        "stop_name": "Münchener Straße",
        "lines": [],
        "directions": [],
        "count": 5,
        "min_minutes": 2,
    },
    "traffic": {
        "tomtom_api_key": "",
        "routes": [],
        "autobahnen": ["A73", "A3"],
        "radius_km": 25.0,
        "tomtom_incidents": False,
        "max_items": 3,
    },
    "news": {"title": "tagesschau.de", "feeds": ["https://www.tagesschau.de/xml/rss2/"], "count": 5},
    "markets": {"items": []},
    "calendar": {"feeds": [], "days": 7},
    "birthdays": [],
    "holidays": {"mariae_himmelfahrt": True, "augsburger_friedensfest": False,
                 "school_holidays": True, "extra_school_holidays": []},
}

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def load_env(path):
    """Liest eine einfache .env-Datei (NAME=wert) in os.environ, ohne Vorhandenes zu überschreiben."""
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(name, value)


def _expand(value, missing):
    if isinstance(value, str):
        def repl(m):
            if m.group(1) not in os.environ:
                missing.add(m.group(1))
            return os.environ.get(m.group(1), "")
        return _VAR.sub(repl, value)
    if isinstance(value, list):
        return [_expand(v, missing) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v, missing) for k, v in value.items()}
    return value


def _merge(base, override, path=""):
    for key, value in override.items():
        if key not in base:
            raise ValueError(f"Unbekannter Eintrag in der Konfiguration: {path}{key}")
        if isinstance(base[key], dict) and isinstance(value, dict):
            _merge(base[key], value, f"{path}{key}.")
        else:
            base[key] = value


def _check_time(text, where):
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(text)):
        raise ValueError(f"{where}: Uhrzeit im Format HH:MM erwartet, nicht {text!r}")


def _check_views(views, where):
    if not views:
        raise ValueError(f"{where}: mindestens eine Ansicht angeben")
    for v in views:
        if v not in VIEWS:
            raise ValueError(f"{where}: unbekannte Ansicht {v!r} (möglich: {', '.join(VIEWS)})")


def validate(cfg):
    sch = cfg["schedule"]
    _check_views(sch["views"], "schedule.views")
    if sch["interval_minutes"] < MIN_INTERVAL_MINUTES:
        log.warning("schedule.interval_minutes < %d, verwende %d", MIN_INTERVAL_MINUTES, MIN_INTERVAL_MINUTES)
        sch["interval_minutes"] = MIN_INTERVAL_MINUTES
    for i, rule in enumerate(sch["rules"]):
        where = f"schedule.rules[{i}]"
        for key in ("from", "to"):
            _check_time(rule.get(key), f"{where}.{key}")
        _check_views(rule.get("views", sch["views"]), f"{where}.views")
        for d in rule.get("days", DAYS):
            if d not in DAYS:
                raise ValueError(f"{where}.days: unbekannter Tag {d!r} (möglich: {', '.join(DAYS)})")
        if rule.get("interval_minutes", sch["interval_minutes"]) < MIN_INTERVAL_MINUTES:
            rule["interval_minutes"] = MIN_INTERVAL_MINUTES
    night = sch["night"]
    for key in ("from", "to"):
        _check_time(night[key], f"schedule.night.{key}")
    _check_views([night["view"]], "schedule.night.view")
    night["check_minutes"] = max(night["check_minutes"], MIN_INTERVAL_MINUTES)
    for key in ("min_severity", "night_min_severity"):
        if cfg["warnings"][key] not in SEVERITIES:
            raise ValueError(f"warnings.{key}: eines von {', '.join(SEVERITIES)}")
    if len(cfg["fuel"]["types"]) not in (1, 2):
        raise ValueError("fuel.types: eine oder zwei Sorten (e5, e10, diesel)")
    for t in cfg["fuel"]["types"]:
        if t not in ("e5", "e10", "diesel"):
            raise ValueError(f"fuel.types: unbekannte Sorte {t!r}")
    if cfg["transit"]["provider"] not in ("vgn", "db"):
        raise ValueError("transit.provider: 'vgn' oder 'db'")
    for i, r in enumerate(cfg["traffic"]["routes"]):
        for key in ("name", "from", "to"):
            if key not in r:
                raise ValueError(f"traffic.routes[{i}]: '{key}' fehlt")
    for i, b in enumerate(cfg["birthdays"]):
        if "name" not in b or "date" not in b:
            raise ValueError(f"birthdays[{i}]: 'name' und 'date' angeben")
    return cfg


def load(path=None, env_path=None):
    """Lädt die Konfiguration. Ohne Pfad gelten nur die Standardwerte."""
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        path = Path(path)
        load_env(env_path or path.with_name(".env"))
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        missing = set()
        raw = _expand(raw, missing)
        for name in sorted(missing):
            log.warning("Variable ${%s} ist nicht gesetzt (.env prüfen)", name)
        _merge(cfg, raw)
    return validate(cfg)
