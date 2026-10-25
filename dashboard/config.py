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
    interval_seconds: int = 180
    rotate180: bool = False
    timezone: str = "Europe/Berlin"
    news_feed: str = "https://www.tagesschau.de/xml/rss2/"
    max_headlines: int = 5


def load(path):
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    known = Config.__dataclass_fields__
    unknown = set(raw) - set(known)
    if unknown:
        raise ValueError(f"Unbekannte Einträge in {path}: {', '.join(sorted(unknown))}")
    return Config(**raw)
