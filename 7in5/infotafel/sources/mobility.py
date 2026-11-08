"""Unterwegs: Spritpreise (Tankerkönig), ÖPNV-Abfahrten (EFA Bahnland Bayern oder VAG), Fahrtzeit und
Verkehrsmeldungen (TomTom, Autobahn GmbH)."""
import math
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .base import NotConfigured, get_json

TANKERKOENIG_LIST = "https://creativecommons.tankerkoenig.de/json/list.php"
VGN_DEPARTURES = "https://start.vag.de/dm/api/v1/abfahrten/VGN/{stop}"
VGN_STOPS = "https://start.vag.de/dm/api/v1/haltestellen/VGN"
TOMTOM_ROUTE = "https://api.tomtom.com/routing/1/calculateRoute/{coords}/json"
TOMTOM_INCIDENTS = "https://api.tomtom.com/traffic/services/5/incidentDetails"
AUTOBAHN = "https://verkehr.autobahn.de/o/autobahn/{road}/services/{kind}"


def distance_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


# --- Sprit -------------------------------------------------------------------

@dataclass
class Station:
    id: str
    brand: str
    name: str
    street: str
    place: str
    distance_km: float
    prices: dict  # Sorte -> Preis in Euro oder None


def _clean(text):
    text = " ".join((text or "").split())
    return text.title() if text.isupper() and len(text) > 4 else text


def parse_stations(d, cfg):
    if not d.get("ok"):
        raise RuntimeError(f"Tankerkönig: {d.get('message', 'unbekannter Fehler')}")
    fc = cfg["fuel"]
    types = fc["types"]
    stations = []
    for s in d.get("stations", []):
        if not s.get("isOpen"):
            continue
        prices = {t: (float(s[t]) if isinstance(s.get(t), (int, float)) and s[t] > 0 else None)
                  for t in types}
        if all(p is None for p in prices.values()):
            continue
        street = " ".join(p for p in (_clean(s.get("street")), (s.get("houseNumber") or "").strip()) if p)
        stations.append(Station(
            id=s.get("id", ""), brand=_clean(s.get("brand")), name=_clean(s.get("name")),
            street=street, place=_clean(s.get("place")),
            distance_km=float(s.get("dist") or 0), prices=prices,
        ))
    if fc["station_ids"]:
        order = {sid: i for i, sid in enumerate(fc["station_ids"])}
        stations = sorted((s for s in stations if s.id in order), key=lambda s: order[s.id])
    else:
        first = types[0]
        stations.sort(key=lambda s: (s.prices[first] is None, s.prices[first] or 0, s.distance_km))
    return stations[: fc["count"]]


def fetch_fuel(cfg):
    fc = cfg["fuel"]
    if not fc["api_key"]:
        raise NotConfigured("fuel.api_key fehlt")
    d = get_json(TANKERKOENIG_LIST, {
        "lat": cfg["latitude"], "lng": cfg["longitude"],
        "rad": min(float(fc["radius_km"]), 25), "type": "all", "sort": "dist",
        "apikey": fc["api_key"],
    })
    return parse_stations(d, cfg)


# --- ÖPNV --------------------------------------------------------------------

@dataclass
class Departure:
    line: str
    direction: str
    planned: datetime
    realtime: datetime | None   # None = keine Echtzeitdaten
    cancelled: bool = False

    @property
    def when(self):
        return self.realtime or self.planned

    @property
    def delay_minutes(self):
        if not self.realtime:
            return 0
        return round((self.realtime - self.planned).total_seconds() / 60)


def _norm_line(name):
    return re.sub(r"^(bus|tram|str|u|s)\s+", "", (name or "").strip(), flags=re.I)


def parse_vgn(d, tz):
    result = []
    for a in d.get("Abfahrten", []):
        planned = a.get("AbfahrtszeitSoll")
        if not planned:
            continue
        actual = a.get("AbfahrtszeitIst")
        has_rt = bool(a.get("Prognose", actual is not None)) and actual
        result.append(Departure(
            line=_norm_line(str(a.get("Linienname", ""))),
            direction=" ".join(str(a.get("Richtungstext", "")).split()),
            planned=datetime.fromisoformat(planned).astimezone(tz),
            realtime=datetime.fromisoformat(actual).astimezone(tz) if has_rt else None,
            cancelled=any(bool(a.get(k)) for k in ("Ausfall", "Fahrtausfall", "IstAusfall")),
        ))
    return result


def _efa_time(text, tz):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(tz) if text else None


def _efa_direction(text):
    # Ziele enthalten manchmal angehängte interne Nummern: "Dechsendorf Grünauweg      113"
    return re.split(r"\s{2,}", str(text or "").strip())[0]


def parse_efa(d, tz):
    """Abfahrten aus einem EFA-DM-Request (rapidJSON), z. B. bahnland-bayern.de."""
    result = []
    for e in d.get("stopEvents") or []:
        planned = _efa_time(e.get("departureTimePlanned"), tz)
        if not planned:
            continue
        t = e.get("transportation") or {}
        status = e.get("realtimeStatus") or []
        result.append(Departure(
            line=_norm_line(str(t.get("number") or t.get("disassembledName") or t.get("name") or "")),
            direction=_efa_direction((t.get("destination") or {}).get("name")),
            planned=planned,
            realtime=_efa_time(e.get("departureTimeEstimated"), tz),
            cancelled=bool(e.get("isCancelled")) or "TRIP_CANCELLED" in status,
        ))
    return result


def filter_departures(deps, cfg, now):
    tc = cfg["transit"]
    lines = {str(x).lower() for x in tc["lines"]}
    dirs = [str(x).lower() for x in tc["directions"]]
    earliest = now + timedelta(minutes=tc["min_minutes"])
    result = [
        d for d in deps
        if (not lines or d.line.lower() in lines)
        and (not dirs or any(x in d.direction.lower() for x in dirs))
        and d.when >= earliest
    ]
    result.sort(key=lambda d: d.when)
    return result


def _efa_base(cfg):
    return cfg["transit"]["efa_url"].rstrip("/") + "/"


def fetch_departures(cfg):
    """Rohe Abfahrten der nächsten Zeit; gefiltert wird erst beim Zeichnen."""
    tc = cfg["transit"]
    if not tc["stop_id"]:
        raise NotConfigured("transit.stop_id fehlt")
    tz = ZoneInfo(cfg["timezone"])
    if tc["provider"] == "efa":
        d = get_json(_efa_base(cfg) + "XML_DM_REQUEST", {
            "outputFormat": "rapidJSON", "mode": "direct", "type_dm": "stop",
            "name_dm": tc["stop_id"], "useRealtime": 1, "limit": 40,
        })
        return parse_efa(d, tz)
    stop = urllib.parse.quote(str(tc["stop_id"]), safe="")
    d = get_json(VGN_DEPARTURES.format(stop=stop), {"timespan": 90, "limitcount": 60})
    return parse_vgn(d, tz)


def find_stops(cfg, name):
    """Haltestellensuche für die Einrichtung: Liste (Name, ID)."""
    if cfg["transit"]["provider"] == "efa":
        d = get_json(_efa_base(cfg) + "XML_STOPFINDER_REQUEST", {
            "outputFormat": "rapidJSON", "type_sf": "any", "anyObjFilter_sf": 2, "name_sf": name,
        })
        return [(s.get("name", ""), s.get("id", "")) for s in d.get("locations") or []
                if s.get("type") == "stop"]
    d = get_json(VGN_STOPS, {"name": name})
    return [(s.get("Haltestellenname", ""), s.get("VGNKennung", "")) for s in d.get("Haltestellen", [])]


# --- Fahrtzeit (TomTom) ----------------------------------------------------

@dataclass
class RouteTime:
    name: str
    minutes: int
    typical_minutes: int | None   # übliche Fahrzeit zu dieser Uhrzeit
    arrival: datetime | None

    @property
    def extra_minutes(self):
        return self.minutes - self.typical_minutes if self.typical_minutes else 0


def parse_route(d, name, tz):
    s = d["routes"][0]["summary"]
    typical = s.get("historicTrafficTravelTimeInSeconds") or s.get("noTrafficTravelTimeInSeconds")
    arrival = s.get("arrivalTime")
    return RouteTime(
        name=name,
        minutes=round(s["travelTimeInSeconds"] / 60),
        typical_minutes=round(typical / 60) if typical else None,
        arrival=datetime.fromisoformat(arrival).astimezone(tz) if arrival else None,
    )


def fetch_routes(cfg):
    tr = cfg["traffic"]
    if not tr["routes"]:
        raise NotConfigured("traffic.routes leer")
    if not tr["tomtom_api_key"]:
        raise NotConfigured("traffic.tomtom_api_key fehlt")
    tz = ZoneInfo(cfg["timezone"])
    result = []
    for r in tr["routes"]:
        coords = f"{r['from'][0]},{r['from'][1]}:{r['to'][0]},{r['to'][1]}"
        params = {
            "key": tr["tomtom_api_key"], "traffic": "true",
            "computeTravelTimeFor": "all", "routeType": "fastest", "travelMode": "car",
        }
        # Ohne Angabe rechnet TomTom auf freien Autobahnen mit real gefahrenen (oft hohen)
        # Geschwindigkeiten; eine Höchstgeschwindigkeit macht lange Strecken realistischer.
        speed = int(r.get("max_speed_kmh", tr["max_speed_kmh"]) or 0)
        if speed > 0:
            params["vehicleMaxSpeed"] = speed
        d = get_json(TOMTOM_ROUTE.format(coords=coords), params)
        result.append(parse_route(d, r["name"], tz))
    return result


# --- Verkehrsmeldungen -----------------------------------------------------

@dataclass
class Incident:
    road: str
    title: str      # z. B. "A73 Erlangen-Nord – Baiersdorf"
    text: str       # kurze Beschreibung
    kind: str       # unfall, stau, sperrung, baustelle, sonstiges
    distance_km: float

    @property
    def rank(self):
        return {"unfall": 0, "sperrung": 1, "stau": 2, "sonstiges": 3, "baustelle": 4}[self.kind]


def _kind(text):
    t = text.lower()
    if "unfall" in t:
        return "unfall"
    if "gesperrt" in t or "sperrung" in t or "vollsperr" in t:
        return "sperrung"
    if "stau" in t or "stockender" in t or "zähfließend" in t:
        return "stau"
    if "baustelle" in t or "bauarbeiten" in t or "fahrbahnverengung" in t:
        return "baustelle"
    return "sonstiges"


_SKIP = re.compile(r"^(beginn|ende|dauer|start|stand|seit|bis)\b|^\d{1,2}\.\d{1,2}\.", re.I)


def parse_autobahn(d, road, home, radius_km):
    result = []
    for key in ("warning", "closure"):
        for w in d.get(key, []):
            if w.get("future"):
                continue
            c = w.get("coordinate") or {}
            try:
                dist = distance_km(home[0], home[1], float(c["lat"]), float(c["long"]))
            except (KeyError, TypeError, ValueError):
                continue
            if dist > radius_km:
                continue
            title = " ".join(str(w.get("title", "")).replace("|", " ").split())
            if not title.upper().startswith(road.upper()):
                title = f"{road} {title}"
            subtitle = " ".join(str(w.get("subtitle", "")).split())
            lines = [" ".join(str(x).split()) for x in w.get("description") or []]
            lines = [x for x in lines if x and not _SKIP.match(x) and x not in (title, subtitle)
                     and not x.upper().startswith(road.upper() + " ")]
            text = " · ".join(p for p in (subtitle, lines[0] if lines else "") if p)
            all_text = " ".join([title, subtitle, *lines])
            kind = _kind(all_text)
            if key == "closure" and kind == "sonstiges":
                kind = "sperrung"
            result.append(Incident(road, title, text, kind, dist))
    return result


def parse_tomtom_incidents(d, home, radius_km):
    result = []
    for f in d.get("incidents", []):
        p = f.get("properties", {})
        if (p.get("magnitudeOfDelay") or 0) < 2 and p.get("iconCategory") not in (1, 8):
            continue
        coords = (f.get("geometry") or {}).get("coordinates") or []
        pt = coords[0] if coords and isinstance(coords[0], list) else coords
        try:
            dist = distance_km(home[0], home[1], float(pt[1]), float(pt[0]))
        except (IndexError, TypeError, ValueError):
            continue
        if dist > radius_km:
            continue
        road = ", ".join(p.get("roadNumbers") or []) or ""
        events = " / ".join(e.get("description", "") for e in p.get("events") or [] if e.get("description"))
        fr, to = p.get("from") or "", p.get("to") or ""
        title = " ".join(x for x in (road, f"{fr} – {to}" if fr and to else fr or to) if x)
        delay = p.get("delay")
        text = events + (f" · +{round(delay / 60)} min" if delay else "")
        kind = {1: "unfall", 6: "stau", 7: "sperrung", 8: "sperrung", 9: "baustelle"}.get(
            p.get("iconCategory"), _kind(events))
        result.append(Incident(road, title or events, text, kind, dist))
    return result


def fetch_incidents(cfg):
    tr = cfg["traffic"]
    home = (cfg["latitude"], cfg["longitude"])
    radius = float(tr["radius_km"])
    result, errors = [], []
    for road in tr["autobahnen"]:
        merged = {}
        for kind in ("warning", "closure"):
            try:
                merged.update(get_json(AUTOBAHN.format(road=urllib.parse.quote(road), kind=kind)))
            except Exception as e:
                errors.append(f"{road}/{kind}: {e}")
        result += parse_autobahn(merged, road, home, radius)
    if tr["tomtom_incidents"] and tr["tomtom_api_key"]:
        dlat = radius / 111.0
        dlon = radius / (111.0 * math.cos(math.radians(home[0])))
        bbox = f"{home[1] - dlon},{home[0] - dlat},{home[1] + dlon},{home[0] + dlat}"
        d = get_json(TOMTOM_INCIDENTS, {
            "key": tr["tomtom_api_key"], "bbox": bbox, "language": "de-DE",
            "timeValidityFilter": "present",
            "fields": "{incidents{type,geometry{type,coordinates},properties{iconCategory,"
                      "magnitudeOfDelay,events{description,code},from,to,roadNumbers,delay}}}",
        })
        result += parse_tomtom_incidents(d, home, radius)
    if errors and not result and len(errors) == 2 * len(tr["autobahnen"]):
        raise RuntimeError("; ".join(errors))
    if not tr["autobahnen"] and not tr["tomtom_incidents"]:
        raise NotConfigured("keine Verkehrsquellen konfiguriert")
    # Gleiche Meldung aus warning und closure nur einmal
    seen, unique = set(), []
    for i in sorted(result, key=lambda i: (i.rank, i.distance_km)):
        if (i.title, i.text) not in seen:
            seen.add((i.title, i.text))
            unique.append(i)
    return unique
