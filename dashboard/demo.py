"""Beispieldaten für --demo (Layout-Test ohne Netzwerk und Display)."""
from datetime import date, timedelta

from .sources import CurrentWeather, DayForecast, Station

_today = date.today()

CURRENT = CurrentWeather(temperature=12.4, apparent_temperature=9.8, humidity=78,
                         wind_speed=14.2, weather_code=2, is_day=True)

FORECAST = [
    DayForecast(_today + timedelta(days=1), 61, 13.6, 6.2, 3.4),
    DayForecast(_today + timedelta(days=2), 3, 11.1, 4.8, 0.0),
    DayForecast(_today + timedelta(days=3), 95, 15.0, -1.4, 8.7),
]

STATIONS = [
    Station("JET", "JET BERLIN", "Holzmarktstr. 12", "Berlin", 1.2, 1.689),
    Station("ARAL", "Aral Tankstelle", "Landsberger Allee 216", "Berlin", 3.4, 1.719),
    Station("Shell", "Shell Berlin", "Karl-Marx-Allee 112", "Berlin", 2.1, 1.729),
]

HEADLINES = [
    "Bundestag beschließt umstrittenes Gesetz zur Reform der Krankenhausfinanzierung",
    "Unwetterwarnung für Süddeutschland: Starkregen und Gewitter erwartet",
    "Liveblog: Die aktuellen Entwicklungen im Überblick",
    "DAX schließt mit leichtem Plus – Anleger warten auf Zinsentscheid der EZB",
    "Fußball-Bundesliga: Spitzenspiel endet unentschieden",
    "Wissenschaftler entdecken neue Tiefseeart vor der Küste Norwegens",
]


def _hourly():
    import math
    from datetime import datetime

    from .sources import HourValue

    start = datetime.now().replace(minute=0, second=0, microsecond=0)
    values = []
    for h in range(24):
        t = start + timedelta(hours=h)
        temp = 8.5 + 5 * math.sin((t.hour - 9) / 24 * 2 * math.pi)
        rain = max(0.0, 1.4 * math.sin((h - 9) / 6 * math.pi)) if 9 <= h <= 15 else 0.0
        values.append(HourValue(t, round(temp, 1), round(rain, 1)))
    return values


HOURLY = _hourly()
