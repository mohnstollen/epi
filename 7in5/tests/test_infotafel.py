"""Tests ohne Netzwerk: python -m pytest tests  (oder: python -m unittest discover tests)"""
import json
import threading
import unittest
import urllib.request
from datetime import date, datetime, timedelta
from http.server import ThreadingHTTPServer
from zoneinfo import ZoneInfo

from infotafel import config as config_mod
from infotafel import schedule
from infotafel.app import make_frame
from infotafel.config import VIEWS
from infotafel.demo import demo_config, demo_values
from infotafel.server import Server, make_handler
from infotafel.sources import StaticData
from infotafel.sources.info import (bavarian_holidays, easter, parse_chart, parse_feed,
                                    parse_openholidays, upcoming_birthdays)
from infotafel.sources.mobility import (filter_departures, parse_autobahn, parse_db, parse_route,
                                        parse_stations, parse_vgn)
from infotafel.sources.weather import moon, parse_alerts, parse_pollen

TZ = ZoneInfo("Europe/Berlin")


def at(*args):
    return datetime(*args, tzinfo=TZ)


def cfg_with(**schedule_overrides):
    cfg = demo_config()
    cfg["schedule"].update(schedule_overrides)
    return config_mod.validate(cfg)


class ScheduleTest(unittest.TestCase):
    def test_rotation_and_sleep(self):
        cfg = cfg_with(interval_minutes=5)
        p = schedule.plan(cfg, at(2026, 10, 30, 10, 2, 0))
        self.assertIn(p.view, VIEWS)
        self.assertEqual(p.sleep_seconds, 3 * 60 + schedule.MARGIN_SECONDS)
        views = {schedule.plan(cfg, at(2026, 10, 30, 10, 0) + timedelta(minutes=5 * i)).view for i in range(4)}
        self.assertEqual(views, set(VIEWS))

    def test_night(self):
        cfg = cfg_with()
        p = schedule.plan(cfg, at(2026, 10, 30, 23, 10))
        self.assertTrue(p.night)
        self.assertEqual(p.view, "termine")
        self.assertEqual(p.sleep_seconds, 30 * 60 + schedule.MARGIN_SECONDS)
        # kurz vor Mitternacht: Wecken zum Datumswechsel
        p = schedule.plan(cfg, at(2026, 10, 30, 23, 50))
        self.assertEqual(p.sleep_seconds, 10 * 60 + schedule.MARGIN_SECONDS)
        # morgens 05:50: bis 06:00
        p = schedule.plan(cfg, at(2026, 10, 31, 5, 50))
        self.assertEqual(p.sleep_seconds, 10 * 60 + schedule.MARGIN_SECONDS)
        self.assertFalse(schedule.plan(cfg, at(2026, 10, 31, 6, 0)).night)
        self.assertEqual(schedule.plan(cfg, at(2026, 10, 30, 23, 10), night_warning=True).view, "wetter")

    def test_rule(self):
        cfg = cfg_with(rules=[{"name": "morgens", "days": ["mo", "di", "mi", "do", "fr"],
                               "from": "06:30", "to": "08:30", "views": ["unterwegs"], "interval_minutes": 3}])
        p = schedule.plan(cfg, at(2026, 10, 30, 7, 0))   # Freitag
        self.assertEqual((p.view, p.mode), ("unterwegs", "morgens"))
        p = schedule.plan(cfg, at(2026, 10, 31, 7, 0))   # Samstag
        self.assertEqual(p.mode, "standard")
        # Regelende begrenzt den Schlaf
        p = schedule.plan(cfg, at(2026, 10, 30, 8, 29))
        self.assertLessEqual(p.sleep_seconds, schedule.MIN_SLEEP + schedule.MARGIN_SECONDS)

    def test_min_interval(self):
        cfg = cfg_with(interval_minutes=1)
        self.assertEqual(cfg["schedule"]["interval_minutes"], config_mod.MIN_INTERVAL_MINUTES)


class ConfigTest(unittest.TestCase):
    def test_env_expansion(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with open(f"{d}/config.toml", "w") as f:
                f.write('[fuel]\napi_key = "${TEST_TK_KEY}"\n')
            with open(f"{d}/.env", "w") as f:
                f.write('TEST_TK_KEY="abc-123"\n')
            os.environ.pop("TEST_TK_KEY", None)
            cfg = config_mod.load(f"{d}/config.toml")
            self.assertEqual(cfg["fuel"]["api_key"], "abc-123")

    def test_unknown_key(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write("[fuel]\napikey = 1\n")
        with self.assertRaises(ValueError):
            config_mod.load(f.name)

    def test_example_config_loads(self):
        from pathlib import Path
        cfg = config_mod.load(Path(__file__).parent.parent / "config.example.toml")
        self.assertEqual(cfg["location_name"], "Herzogenaurach")


class HolidayTest(unittest.TestCase):
    def test_easter(self):
        self.assertEqual(easter(2026), date(2026, 4, 5))
        self.assertEqual(easter(2027), date(2027, 3, 28))

    def test_bavaria(self):
        days = {h.name: h.day for h in bavarian_holidays(2026, demo_config())}
        self.assertEqual(days["Buß- und Bettag"], date(2026, 11, 18))
        self.assertEqual(days["Fronleichnam"], date(2026, 6, 4))
        self.assertEqual(days["Christi Himmelfahrt"], date(2026, 5, 14))
        self.assertIn("Mariä Himmelfahrt", days)

    def test_birthdays(self):
        cfg = demo_config()
        cfg["birthdays"] = [{"name": "Mama", "date": "1994-10-29"}, {"name": "X", "date": "29.02."}]
        b = upcoming_birthdays(cfg, date(2026, 10, 26))
        self.assertEqual((b[0].name, b[0].day, b[0].age), ("Mama", date(2026, 10, 29), 32))
        self.assertEqual(b[1].day, date(2027, 2, 28))

    def test_openholidays(self):
        d = [{"startDate": "2026-11-02", "endDate": "2026-11-06",
              "name": [{"language": "DE", "text": "Herbstferien"}]}]
        v = parse_openholidays(d)[0]
        self.assertEqual((v.name, v.start, v.end), ("Herbstferien", date(2026, 11, 2), date(2026, 11, 6)))


class ParserTest(unittest.TestCase):
    def test_vgn(self):
        d = {"Abfahrten": [
            {"Linienname": "200", "Richtungstext": "Erlangen Hbf", "Richtung": "Richtung1",
             "AbfahrtszeitSoll": "2026-10-30T07:40:00+01:00", "AbfahrtszeitIst": "2026-10-30T07:42:00+01:00",
             "Prognose": True, "Produkt": "Bus"},
            {"Linienname": "247", "Richtungstext": "Höchstadt", "AbfahrtszeitSoll": "2026-10-30T07:45:00+01:00",
             "AbfahrtszeitIst": "2026-10-30T07:45:00+01:00", "Prognose": False},
        ]}
        deps = parse_vgn(d, TZ)
        self.assertEqual(deps[0].delay_minutes, 2)
        self.assertIsNone(deps[1].realtime)
        cfg = demo_config()
        f = filter_departures(deps, cfg, at(2026, 10, 30, 7, 30))
        self.assertEqual([x.line for x in f], ["200"])

    def test_db(self):
        d = {"departures": [{"when": None, "plannedWhen": "2026-10-30T07:40:00+01:00", "delay": None,
                             "direction": "Erlangen Hbf", "line": {"name": "Bus 200"}, "cancelled": True}]}
        dep = parse_db(d, TZ)[0]
        self.assertEqual((dep.line, dep.cancelled), ("200", True))

    def test_tankerkoenig(self):
        cfg = demo_config()
        d = {"ok": True, "stations": [
            {"id": "a", "brand": "ARAL", "name": "x", "street": "ERLANGER STR.", "houseNumber": "1",
             "place": "HERZOGENAURACH", "dist": 1.2, "e5": 1.799, "e10": 1.739, "diesel": 1.659, "isOpen": True},
            {"id": "b", "brand": "JET", "name": "y", "street": "", "place": "", "dist": 2.0,
             "e5": 1.749, "e10": 1.689, "diesel": None, "isOpen": True},
            {"id": "c", "brand": "Zu", "name": "z", "street": "", "place": "", "dist": 0.5,
             "e5": 1.5, "diesel": 1.5, "isOpen": False},
        ]}
        st = parse_stations(d, cfg)
        self.assertEqual([s.id for s in st], ["b", "a"])
        self.assertIsNone(st[0].prices["diesel"])
        cfg["fuel"]["station_ids"] = ["a"]
        self.assertEqual([s.id for s in parse_stations(d, cfg)], ["a"])

    def test_route(self):
        d = {"routes": [{"summary": {"travelTimeInSeconds": 1680, "historicTrafficTravelTimeInSeconds": 1200,
                                     "noTrafficTravelTimeInSeconds": 1100,
                                     "arrivalTime": "2026-10-30T07:58:00+01:00"}}]}
        r = parse_route(d, "Büro", TZ)
        self.assertEqual((r.minutes, r.typical_minutes, r.extra_minutes), (28, 20, 8))

    def test_autobahn(self):
        d = {"warning": [
            {"title": "A73 | Erlangen-Nord - Baiersdorf-Süd", "subtitle": "Nürnberg Richtung Bamberg",
             "description": ["Beginn: 30.10.26 um 07:12", "A73 Nürnberg -> Bamberg", "Unfall, Stau"],
             "coordinate": {"lat": "49.62", "long": "11.01"}, "future": False},
            {"title": "A73 | weit weg", "coordinate": {"lat": "50.9", "long": "11.0"}, "future": False},
        ]}
        items = parse_autobahn(d, "A73", (49.5672, 10.8819), 25)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "unfall")
        self.assertIn("Unfall", items[0].text)

    def test_alerts(self):
        d = {"alerts": [{"status": "actual", "severity": "moderate", "event_de": "STURMBÖEN",
                         "headline_de": "Amtliche WARNUNG vor STURMBÖEN", "description_de": "Es treten …",
                         "onset": "2026-10-30T13:00:00+00:00", "expires": "2026-10-31T05:00:00+00:00"}]}
        w = parse_alerts(d, TZ)[0]
        self.assertEqual((w.event, w.onset.hour), ("STURMBÖEN", 14))

    def test_pollen(self):
        d = {"content": [{"region_id": 120, "partregion_id": 123, "Pollen": {
            "Graeser": {"today": "1-2", "tomorrow": "1"}, "Hasel": {"today": "0", "tomorrow": "-1"}}}]}
        p = parse_pollen(d, 123)
        self.assertEqual(p["Gräser"], (1.5, 1.0))
        self.assertEqual(p["Hasel"], (0.0, None))

    def test_feed(self):
        raw = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
        <item><title>Erste &amp; beste</title><pubDate>Fri, 30 Oct 2026 07:12:00 +0100</pubDate></item>
        <item><title>Zweite</title></item></channel></rss>"""
        items = parse_feed(raw, TZ)
        self.assertEqual(items[0].title, "Erste & beste")
        self.assertEqual(items[0].published.hour, 7)

    def test_chart(self):
        base = int(at(2026, 10, 26, 9).timestamp())
        d = {"chart": {"result": [{"meta": {"regularMarketPrice": 110.0, "regularMarketTime": base + 4 * 86400,
                                            "chartPreviousClose": 90},
                                   "timestamp": [base + i * 86400 for i in range(5)],
                                   "indicators": {"quote": [{"close": [100, 101, None, 105, 109]}]}}]}}
        q = parse_chart(d, {"symbol": "X", "name": "X"}, TZ)
        self.assertEqual(q.previous, 105)
        self.assertEqual(q.history, [100, 101, 105, 110.0])
        self.assertAlmostEqual(q.change_pct, 4.7619, places=3)

    def test_moon(self):
        self.assertEqual(moon(at(2026, 10, 26, 6)).name, "Vollmond")
        self.assertLess(moon(at(2026, 11, 9, 12)).illumination, 0.03)


class RenderTest(unittest.TestCase):
    def test_all_views_demo(self):
        now = at(2026, 10, 30, 7, 30)
        cfg = demo_config()
        data = StaticData(cfg, demo_values(now))
        for v in VIEWS:
            f = make_frame(cfg, data, now, v)
            self.assertEqual(f.image.size, (800, 480))
            self.assertEqual(len(f.to_buffer()), 48000)

    def test_all_views_without_data(self):
        """Nichts eingerichtet, nichts geladen: darf nicht abstürzen."""
        now = at(2026, 12, 24, 23, 30)
        cfg = config_mod.load()
        data = StaticData(cfg, {})
        for name, c in data.sources.items():
            c.configured = name in ("weather", "news")
        for v in VIEWS:
            f = make_frame(cfg, data, now, v)
            self.assertEqual(len(f.to_buffer()), 48000)

    def test_render_does_not_fall_back_to_error_page(self):
        import logging
        now = at(2026, 10, 30, 12, 0)
        cfg = demo_config()
        data = StaticData(cfg, demo_values(now))
        with self.assertNoLogs("infotafel.views", level=logging.ERROR):
            for v in VIEWS:
                make_frame(cfg, data, now, v)


class ServerTest(unittest.TestCase):
    def test_etag_304(self):
        now = datetime.now(TZ)
        cfg = demo_config()
        srv = Server(cfg, StaticData(cfg, demo_values(now)))
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(srv))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/image.bin") as r:
                body, tag = r.read(), r.headers["ETag"]
                self.assertEqual(len(body), 48000)
                self.assertGreaterEqual(int(r.headers["X-Sleep-Seconds"]), 60)
            req = urllib.request.Request(base + "/image.bin", headers={"If-None-Match": tag})
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req)
            self.assertEqual(e.exception.code, 304)
            with urllib.request.urlopen(base + "/image.png?view=wetter") as r:
                self.assertEqual(r.headers["Content-Type"], "image/png")
            with urllib.request.urlopen(base + "/status.json") as r:
                self.assertIn("weather", json.loads(r.read()))
            with urllib.request.urlopen(base + "/") as r:
                self.assertIn(b"Infotafel", r.read())
        finally:
            httpd.shutdown()


if __name__ == "__main__":
    unittest.main()
