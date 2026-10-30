"""Beispieldaten für --demo, die Vorschau-Bilder und Tests."""
import copy
from datetime import datetime, timedelta

from .config import DEFAULTS
from .sources.info import Event, Headline, Quote, Vacation
from .sources.mobility import Departure, Incident, RouteTime, Station
from .sources.weather import Day, Warning, Weather

DEMO_CONFIG = {
    "transit": {"stop_id": "demo", "lines": ["200", "201"], "directions": ["Erlangen"]},
    "fuel": {"api_key": "demo"},
    "traffic": {"tomtom_api_key": "demo",
                "routes": [{"name": "Zuhause → Büro", "from": [49.567, 10.882], "to": [49.597, 11.004]}]},
    "markets": {"items": [
        {"symbol": "^GDAXI", "name": "DAX", "decimals": 0},
        {"symbol": "^GSPC", "name": "S&P 500", "decimals": 0},
        {"symbol": "BZ=F", "name": "Brent", "unit": "$/bbl", "decimals": 2},
        {"symbol": "HG=F", "name": "Kupfer", "unit": "$/lb", "decimals": 2},
        {"symbol": "ADS.DE", "name": "adidas", "unit": "€", "decimals": 2},
    ]},
    "calendar": {"feeds": [{"url": "demo"}]},
    "birthdays": [{"name": "Mama", "date": "1994-11-02"}, {"name": "Lena", "date": "11-14"}],
}


def demo_config():
    from .config import _merge, validate
    cfg = copy.deepcopy(DEFAULTS)
    _merge(cfg, copy.deepcopy(DEMO_CONFIG))
    return validate(cfg)


def demo_values(now):
    tz = now.tzinfo
    today = now.date()
    at = lambda days, h, m=0: datetime(today.year, today.month, today.day, h, m, tzinfo=tz) + timedelta(days=days)

    base = now.replace(second=0, microsecond=0)
    deps = []
    for i, (line, direction, mins, delay) in enumerate([
        ("200", "Erlangen Hbf", 4, 1), ("201", "Erlangen Hbf", 12, 0), ("247", "Höchstadt", 13, 0),
        ("200", "Erlangen Hbf", 24, None), ("201", "Erlangen Hbf", 32, 3), ("200", "Erlangen Hbf", 44, None),
        ("201", "Erlangen Hbf", 52, None),
    ]):
        planned = base + timedelta(minutes=mins)
        deps.append(Departure(line, direction, planned,
                              planned + timedelta(minutes=delay) if delay is not None else None,
                              cancelled=(i == 5)))

    return {
        "weather": Weather(
            temperature=8.4, apparent_temperature=5.2, weather_code=2, is_day=6 <= now.hour < 17,
            wind_speed=18, wind_direction=225, wind_gusts=52,
            days=[
                Day(today, 61, 12.1, 4.3, 3.2, at(0, 6, 59), at(0, 16, 48)),
                Day(today + timedelta(days=1), 3, 10.2, 3.1, 0.4, at(1, 7, 1), at(1, 16, 46)),
                Day(today + timedelta(days=2), 0, 13.0, 0.8, 0.0, at(2, 7, 2), at(2, 16, 44)),
                Day(today + timedelta(days=3), 2, 11.4, 2.2, 0.1, at(3, 7, 4), at(3, 16, 43)),
            ],
        ),
        "warnings": [Warning("moderate", "STURMBÖEN", "Amtliche WARNUNG vor STURMBÖEN",
                             "Es treten Sturmböen mit Geschwindigkeiten um 70 km/h aus südwestlicher Richtung auf.",
                             at(0, 14), at(1, 6))],
        "pollen": {"Hasel": (0.0, 0.0), "Erle": (0.0, 0.0), "Birke": (0.0, 0.0), "Gräser": (0.5, 0.0),
                   "Ambrosia": (1.0, 0.5), "Beifuß": (0.0, 0.0), "Esche": (0.0, 0.0), "Roggen": (0.0, 0.0)},
        "fuel": [
            Station("1", "Aral", "", "Erlanger Straße 30", "Herzogenaurach", 1.2,
                    {"e5": 1.729, "diesel": 1.649}),
            Station("2", "JET", "", "Würzburger Straße 7", "Herzogenaurach", 2.0,
                    {"e5": 1.759, "diesel": 1.619}),
            Station("3", "Shell", "", "Hans-Maier-Straße 2", "Herzogenaurach", 3.4,
                    {"e5": 1.779, "diesel": 1.669}),
        ],
        "departures": deps,
        "routes": [RouteTime("Zuhause → Büro", 28, 20, now + timedelta(minutes=28))],
        "incidents": [
            Incident("A73", "A73 Erlangen-Nord – Baiersdorf-Süd",
                     "Richtung Bamberg · Unfall, rechter Fahrstreifen gesperrt", "unfall", 9.5),
            Incident("A3", "A3 Höchstadt-Ost – Erlangen-West",
                     "Richtung Nürnberg · Baustelle, Fahrbahnverengung, 80 km/h", "baustelle", 6.1),
            Incident("A73", "A73 Erlangen-Bruck – Erlangen-Zentrum",
                     "Richtung Nürnberg · 3 km Stau", "stau", 7.0),
        ],
        "news": [
            Headline("Bundestag beschließt Haushalt für 2027 nach langer Debatte über Investitionen und Schuldenbremse",
                     now - timedelta(minutes=18)),
            Headline("Unwetterwarnung für Teile Bayerns: Sturmböen bis 70 km/h erwartet", now - timedelta(minutes=42)),
            Headline("Inflation im Oktober leicht gesunken", now - timedelta(hours=1, minutes=5)),
            Headline("Bahn kündigt neuen Fahrplan mit mehr Verbindungen zwischen Nürnberg und Berlin an",
                     now - timedelta(hours=1, minutes=40)),
            Headline("Champions League: Bayern gewinnt knapp", now - timedelta(hours=2, minutes=10)),
            Headline("Neue Studie zu Mikroplastik im Grundwasser", now - timedelta(hours=3)),
        ],
        "markets": [
            Quote("DAX", "", 0, 24312.5, 24118.2,
                  [23801, 23955, 24020, 23890, 23710, 23860, 24050, 23980, 24118.2, 24312.5], at(-1, 17, 35)),
            Quote("S&P 500", "", 0, 6784.1, 6804.6,
                  [6702, 6730, 6755, 6790, 6810, 6825, 6812, 6820, 6804.6, 6784.1], at(-1, 22, 0)),
            Quote("Brent", "$/bbl", 2, 71.40, 70.07,
                  [69.2, 68.8, 69.5, 70.1, 69.9, 69.4, 69.8, 70.3, 70.07, 71.40], at(-1, 22, 59)),
            Quote("Kupfer", "$/lb", 2, 4.92, 4.95,
                  [5.01, 4.99, 4.97, 5.02, 4.98, 4.96, 4.94, 4.97, 4.95, 4.92], at(-1, 22, 59)),
            Quote("adidas", "€", 2, 182.85, 178.55,
                  [171.2, 172.8, 174.1, 173.0, 175.6, 176.9, 177.3, 176.0, 178.55, 182.85], at(-1, 17, 35)),
        ],
        "calendar": [
            Event("Elternabend", at(0, 19), False),
            Event("Papiertonne rausstellen", at(1, 0), True, "tonne"),
            Event("Zahnarzt", at(2, 10, 30), False),
            Event("Restmüll", at(4, 0), True, "tonne"),
            Event("Fußball Training", at(4, 18), False),
            Event("Wochenmarkt", at(5, 8), False),
        ],
        "vacations": [
            Vacation("Herbstferien", today + timedelta(days=(7 - today.weekday()) % 7 or 7),
                     today + timedelta(days=((7 - today.weekday()) % 7 or 7) + 4)),
            Vacation("Weihnachtsferien", today + timedelta(days=57), today + timedelta(days=71)),
        ],
    }
