# E-Paper-Dashboard für Raspberry Pi

Dashboard für das **Waveshare 2.7inch e-Paper HAT Rev2.1** (264×176 Pixel,
schwarz/weiß) an einem Raspberry Pi. Alle 3 Minuten wechselt die Anzeige
zwischen vier Ansichten:

| # | Ansicht | Quelle |
|---|---------|--------|
| 1 | Aktuelles Wetter: großes Icon, Temperatur, Beschreibung, gefühlte Temperatur, Wind, Luftfeuchte | DWD ICON-D2 |
| 2 | Vorhersage der kommenden 3 Tage (ab morgen): Icon, max./min. Temperatur, Niederschlag | DWD ICON-D2 + ICON-EU |
| 3 | E10-Preise der 3 günstigsten geöffneten Tankstellen, aufsteigend nach Preis | Tankerkönig |
| 4 | Aktuelle Schlagzeilen – so viele, wie gut lesbar passen (meist 3–4, max. 5) | tagesschau RSS |

## Datenquellen

* **Wetter:** Die Rohdaten des DWD liegen als GRIB2-Dateien vor, deren
  Verarbeitung einen Pi 2 überfordern würde. Daher werden die ICON-Daten über
  die [DWD-Schnittstelle von Open-Meteo](https://open-meteo.com/en/docs/dwd-api)
  abgerufen (kostenlos, kein Key, Lizenz CC BY 4.0).
  Das aktuelle Wetter kommt direkt aus **ICON-D2** (`models=icon_d2`).
  ICON-D2 rechnet nur ca. 48 Stunden voraus; für den dritten Tag der Vorhersage
  wird deshalb `icon_seamless` genutzt, das ICON-D2 verwendet, solange es
  Daten gibt, und danach mit ICON-EU des DWD ergänzt.
* **Spritpreise:** [Tankerkönig-API](https://creativecommons.tankerkoenig.de)
  (`list.php`, Sorte `e10`, Sortierung nach Preis). Es werden nur geöffnete
  Tankstellen berücksichtigt. Abfrage höchstens alle 5 Minuten, wie von
  Tankerkönig gefordert. Daten: MTS-K, Lizenz CC BY 4.0.
* **Nachrichten:** `https://www.tagesschau.de/xml/rss2/`

Schlägt ein Abruf fehl, bleiben die zuletzt geladenen Daten stehen und in der
Kopfzeile erscheint ein `!` vor der Uhrzeit.

## Installation auf dem Raspberry Pi

1. SPI aktivieren: `sudo raspi-config` → *Interface Options* → *SPI* → *Yes*,
   danach neu starten.
2. Abhängigkeiten installieren:
   ```sh
   sudo apt update
   sudo apt install git python3-pil python3-spidev python3-gpiozero python3-lgpio fonts-dejavu-core
   ```
   (Benötigt Python ≥ 3.11, also Raspberry Pi OS *Bookworm* oder neuer.)
3. Projekt holen und konfigurieren:
   ```sh
   cd ~
   git clone <repo-url> epi
   cd epi
   cp config.example.toml config.toml
   nano config.toml   # Standort und Tankerkönig-API-Key eintragen
   ```
   Den kostenlosen API-Key gibt es unter
   <https://onboarding.tankerkoenig.de>.
4. Testen:
   ```sh
   python3 -m dashboard --preview preview      # Ansichten als PNG, ohne Display
   python3 -m dashboard                         # aufs Display (Strg+C beendet)
   ```
   `--demo` verwendet Beispieldaten statt Online-Abruf.
5. Als Dienst einrichten (startet automatisch beim Booten):
   ```sh
   sudo cp epaper-dashboard.service /etc/systemd/system/
   # ggf. User und Pfade in der Datei anpassen
   sudo systemctl daemon-reload
   sudo systemctl enable --now epaper-dashboard
   journalctl -u epaper-dashboard -f            # Log ansehen
   ```

## Konfiguration (`config.toml`)

| Schlüssel | Bedeutung | Standard |
|-----------|-----------|----------|
| `latitude`, `longitude` | Standort in Dezimalgrad | – |
| `location_name` | Ortsname in der Kopfzeile | leer |
| `tankerkoenig_api_key` | API-Key von Tankerkönig | – |
| `fuel_radius_km` | Suchradius für Tankstellen (max. 25) | 5 |
| `interval_seconds` | Wechselintervall der Ansichten | 180 |
| `rotate180` | Bild um 180° drehen, falls es auf dem Kopf steht | false |
| `max_headlines` | Höchstzahl Schlagzeilen | 5 |
| `timezone` | Zeitzone für die Wetterdaten | Europe/Berlin |

## Hinweise zur Hardware

* Der beiliegende Treiber `dashboard/epd2in7_v2.py` ist für die Rev2.1 (V2)
  des HATs. Er braucht nur `spidev` und `gpiozero`; die Waveshare-Bibliothek
  muss nicht installiert werden.
* Verkabelung (BCM): RST 17, DC 25, BUSY 24, CS = CE0 (GPIO 8), CLK 11,
  DIN 10 – entspricht der Belegung beim Aufstecken auf die Stiftleiste.
* Es wird bei jedem Wechsel eine Vollaktualisierung (kurzes Flackern) gemacht;
  dazwischen schläft das Display. Das Bild bleibt auch ohne Strom stehen.

## Projektstruktur

```
dashboard/
  __main__.py     Hauptschleife, CLI (--config, --preview, --demo)
  sources.py      Abruf von Wetter, Spritpreisen, Schlagzeilen + Cache
  screens.py      Layout der vier Ansichten
  icons.py        Wetter-Icons (mit PIL gezeichnet) und Beschreibungen
  epd2in7_v2.py   Displaytreiber
  demo.py         Beispieldaten
```

## Vorschau (Beispieldaten)

![Wetter](docs/1-wetter.png) ![Vorhersage](docs/2-vorhersage.png)
![Sprit](docs/3-sprit.png) ![Nachrichten](docs/4-nachrichten.png)
