// Infotafel – ESP32-Firmware für das Waveshare 7.5" e-Paper V2 (800x480).
//
// Ablauf bei jedem Aufwachen:
//   WLAN verbinden -> GET /image.bin mit "If-None-Match: <ETag des angezeigten Bildes>"
//   200: Bild (48000 Bytes) laden, Vollaktualisierung, ETag merken
//   304: Bild unverändert -> Display bleibt unangetastet (spart Refreshs)
//   danach Tiefschlaf für X-Sleep-Seconds Sekunden (vom Server vorgegeben).
//
// Welche Ansicht wann kommt (Rotation, Nachtruhe 22–6 Uhr, Regeln) entscheidet
// allein der Server – Änderungen dort brauchen kein neues Flashen.
//
// Bibliothek: GxEPD2 von Jean-Marc Zingg (Arduino-Bibliotheksverwalter oder PlatformIO).

#include <Arduino.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <WiFi.h>
#include <esp_sleep.h>
#include <GxEPD2_BW.h>

#include "config.h"

#if defined(PANEL_GDEY075T7)
using Panel = GxEPD2_750_GDEY075T7;   // neuere Waveshare 7.5" V2 (GDEY075T7)
#else
using Panel = GxEPD2_750_T7;          // Waveshare 7.5" V2 (GDEW075T7), Standard
#endif

static const size_t IMAGE_BYTES = Panel::WIDTH / 8 * Panel::HEIGHT;   // 48000
static const uint32_t WIFI_TIMEOUT_MS = 20000;
static const uint32_t DOWNLOAD_TIMEOUT_MS = 30000;

// Bleibt im Tiefschlaf erhalten (RTC-Speicher), nach Stromausfall leer.
RTC_DATA_ATTR char lastEtag[40] = "";
RTC_DATA_ATTR uint8_t failures = 0;

Panel epd(PIN_CS, PIN_DC, PIN_RST, PIN_BUSY);
SPIClass epdSpi(HSPI);

[[noreturn]] void sleepFor(uint32_t seconds) {
  Serial.printf("Schlafe %u s\n", seconds);
  Serial.flush();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  esp_sleep_enable_timer_wakeup(uint64_t(seconds) * 1000000ULL);
  esp_deep_sleep_start();
}

// Nach Fehlern immer länger warten: 1, 2, 4, 8 … höchstens 15 Minuten.
[[noreturn]] void retryLater(const char* reason) {
  Serial.printf("Fehler: %s\n", reason);
  if (failures < 10) failures++;
  uint32_t wait = RETRY_SECONDS << min<uint8_t>(failures - 1, 4);
  sleepFor(min<uint32_t>(wait, 900));
}

bool connectWifi() {
  WiFi.mode(WIFI_STA);
#ifdef WIFI_HOSTNAME
  WiFi.setHostname(WIFI_HOSTNAME);
#endif
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > WIFI_TIMEOUT_MS) return false;
    delay(100);
  }
  Serial.printf("WLAN verbunden, IP %s, RSSI %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  return true;
}

enum class Result { NewImage, Unchanged, Error };

// Fragt das Bild ab. Bei NewImage steht es in buf, das neue ETag in etag.
Result fetchImage(uint8_t* buf, String& etag, uint32_t& sleepSeconds) {
  HTTPClient http;
  http.setTimeout(DOWNLOAD_TIMEOUT_MS);
  http.setReuse(false);
  if (!http.begin(SERVER_URL)) {
    Serial.println("Ungültige SERVER_URL");
    return Result::Error;
  }
  const char* headers[] = {"ETag", "X-Sleep-Seconds", "X-View"};
  http.collectHeaders(headers, 3);
  if (lastEtag[0]) http.addHeader("If-None-Match", String("\"") + lastEtag + "\"");

  int code = http.GET();
  uint32_t s = http.header("X-Sleep-Seconds").toInt();
  sleepSeconds = (s >= 60 && s <= 3600) ? s : DEFAULT_SECONDS;
  Serial.printf("HTTP %d, Ansicht %s, danach %u s\n", code, http.header("X-View").c_str(), sleepSeconds);

  if (code == HTTP_CODE_NOT_MODIFIED) {
    http.end();
    return Result::Unchanged;
  }
  if (code != HTTP_CODE_OK) {
    http.end();
    return Result::Error;
  }
  if (http.getSize() != int(IMAGE_BYTES)) {
    Serial.printf("Falsche Bildgröße %d statt %u\n", http.getSize(), unsigned(IMAGE_BYTES));
    http.end();
    return Result::Error;
  }
  etag = http.header("ETag");
  etag.replace("\"", "");

  WiFiClient* stream = http.getStreamPtr();
  size_t got = 0;
  uint32_t start = millis();
  while (got < IMAGE_BYTES && millis() - start < DOWNLOAD_TIMEOUT_MS) {
    size_t avail = stream->available();
    if (avail) {
      got += stream->readBytes(buf + got, min(avail, IMAGE_BYTES - got));
    } else if (!stream->connected()) {
      break;
    } else {
      delay(5);
    }
  }
  http.end();
  if (got != IMAGE_BYTES) {
    Serial.printf("Download unvollständig: %u von %u Bytes\n", unsigned(got), unsigned(IMAGE_BYTES));
    return Result::Error;
  }
  return Result::NewImage;
}

void showImage(const uint8_t* buf) {
  if (PIN_PWR >= 0) {
    pinMode(PIN_PWR, OUTPUT);
    digitalWrite(PIN_PWR, HIGH);
    delay(10);
  }
  epdSpi.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_CS);
  epd.selectSPI(epdSpi, SPISettings(4000000, MSBFIRST, SPI_MODE0));
  // initial = true: nach dem Tiefschlaf ist der Controller-Zustand unbekannt -> Vollaktualisierung.
  // 2 ms Reset-Puls für Waveshare-Platinen mit "cleverer" Reset-Schaltung.
  epd.init(0, true, 2, false);
  epd.writeImageForFullRefresh(buf, 0, 0, Panel::WIDTH, Panel::HEIGHT);
  epd.refresh(false);
  epd.hibernate();
  if (PIN_PWR >= 0) digitalWrite(PIN_PWR, LOW);
}

void setup() {
  Serial.begin(115200);
  Serial.println("\nInfotafel");
  if (esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_TIMER) {
    lastEtag[0] = '\0';   // Einschalten/Reset: Bild immer neu zeichnen
    failures = 0;
  }

  uint8_t* buf = static_cast<uint8_t*>(malloc(IMAGE_BYTES));
  if (!buf) retryLater("zu wenig Speicher");
  if (!connectWifi()) retryLater("keine WLAN-Verbindung");

  String etag;
  uint32_t sleepSeconds = DEFAULT_SECONDS;
  Result r = fetchImage(buf, etag, sleepSeconds);
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);   // spart Strom während des Refreshs

  if (r == Result::Error) retryLater("Server nicht erreichbar oder falsche Antwort");
  failures = 0;
  if (r == Result::NewImage) {
    showImage(buf);
    strlcpy(lastEtag, etag.c_str(), sizeof(lastEtag));
    Serial.println("Bild angezeigt");
  } else {
    Serial.println("Bild unverändert, kein Refresh");
  }
  sleepFor(sleepSeconds);
}

void loop() {}
