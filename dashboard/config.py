"""Laden der Konfiguration aus einer TOML-Datei."""
import tomllib
from dataclasses import dataclass


@dataclass
class Config:
    latitude: float
    longitude: float
    location_name: str = ""
    tankerkoenig_api_key: str = ""
    fuel_radius_km: float = 5.0
    display: str = "2in7"           # "2in7" oder "7in5"
    interval_seconds: int | None = None  # Standard: 180 (2in7) bzw. 600 (7in5)
    rotate180: bool = False
    timezone: str = "Europe/Berlin"
    news_feed: str = "https://www.tagesschau.de/xml/rss2/"
    max_headlines: int = 5


DISPLAYS = {"2in7": 180, "7in5": 600}  # Display -> Standardintervall in Sekunden


def load(path):
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    known = Config.__dataclass_fields__
    unknown = set(raw) - set(known)
    if unknown:
        raise ValueError(f"Unbekannte Einträge in {path}: {', '.join(sorted(unknown))}")
    cfg = Config(**raw)
    if cfg.display not in DISPLAYS:
        raise ValueError(f"display muss einer von {', '.join(DISPLAYS)} sein, nicht {cfg.display!r}")
    return cfg
