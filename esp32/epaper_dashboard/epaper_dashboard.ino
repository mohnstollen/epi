// E-Paper-Dashboard: ESP32 als Anzeige.
//
// Ablauf: aufwachen -> WLAN -> Bild vom Raspberry Pi laden (/image.bin) ->
// anzeigen -> Tiefschlaf bis zum nächsten Bildwechsel (Header X-Next-Refresh).
// Das e-Paper behält das Bild ohne Strom. Gerendert wird komplett auf dem Pi;
// das Bild kommt bereits im Speicherformat des Displays (1 Bit/Pixel, 1 = weiß).
//
// Benötigt die Bibliothek GxEPD2 (Bibliotheksverwalter: "GxEPD2" von Jean-Marc Zingg).

#include <Arduino.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <WiFi.h>
#include <GxEPD2_BW.h>

#include "config.h"

#if defined(DISPLAY_7IN5)
using Panel = GxEPD2_750_T7;          // GDEW075T7, Waveshare 7.5" V2
#elif defined(DISPLAY_2IN7)
using Panel = GxEPD2_270_GDEY027T91;  // GDEY027T91, Waveshare 2.7" V2
#else
#error "In config.h DISPLAY_7IN5 oder DISPLAY_2IN7 aktivieren"
#endif

static const size_t IMAGE_BYTES = Panel::WIDTH / 8 * Panel::HEIGHT;
static const uint32_t WIFI_TIMEOUT_MS = 20000;
static const uint32_t DOWNLOAD_TIMEOUT_MS = 30000;

Panel epd(PIN_CS, PIN_DC, PIN_RST, PIN_BUSY);

[[noreturn]] void sleepFor(uint32_t seconds) {
  Serial.printf("Schlafe %u s\n", seconds);
  Serial.flush();
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  esp_sleep_enable_timer_wakeup(uint64_t(seconds) * 1000000ULL);
  esp_deep_sleep_start();
}

bool connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > WIFI_TIMEOUT_MS) {
      Serial.println("WLAN: keine Verbindung");
      return false;
    }
    delay(100);
  }
  Serial.printf("WLAN verbunden, IP %s\n", WiFi.localIP().toString().c_str());
  return true;
}

// Lädt das Bild nach buf. Liefert die Sekunden bis zum nächsten Abruf, 0 bei Fehler.
uint32_t download(uint8_t* buf) {
  HTTPClient http;
  http.setTimeout(DOWNLOAD_TIMEOUT_MS);
  if (!http.begin(SERVER_URL)) {
    Serial.println("Ungültige SERVER_URL");
    return 0;
  }
  const char* headers[] = {"X-Next-Refresh"};
  http.collectHeaders(headers, 1);

  int code = http.GET();
  if (code != HTTP_CODE_OK) {
    Serial.printf("HTTP-Fehler %d\n", code);
    http.end();
    return 0;
  }
  if (http.getSize() != int(IMAGE_BYTES)) {
    Serial.printf("Falsche Bildgröße %d statt %u – passt \"display\" auf dem Pi?\n",
                  http.getSize(), unsigned(IMAGE_BYTES));
    http.end();
    return 0;
  }

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
  uint32_t next = http.header("X-Next-Refresh").toInt();
  http.end();

  if (got != IMAGE_BYTES) {
    Serial.printf("Download unvollständig: %u von %u Bytes\n", unsigned(got), unsigned(IMAGE_BYTES));
    return 0;
  }
  return (next >= 10 && next <= 3600) ? next : DEFAULT_SECONDS;
}

void show(const uint8_t* buf) {
  if (PIN_PWR >= 0) {
    pinMode(PIN_PWR, OUTPUT);
    digitalWrite(PIN_PWR, HIGH);
    delay(10);
  }
  SPI.begin(PIN_SCK, -1, PIN_MOSI, PIN_CS);
  epd.init(0, true, 2, false);  // 2 ms Reset-Puls für Waveshare-Platinen
  epd.writeImage(buf, 0, 0, Panel::WIDTH, Panel::HEIGHT);
  epd.refresh(false);           // Vollaktualisierung
  epd.hibernate();
  if (PIN_PWR >= 0) digitalWrite(PIN_PWR, LOW);
}

void setup() {
  Serial.begin(115200);
  Serial.println("\nE-Paper-Dashboard");

  uint8_t* buf = static_cast<uint8_t*>(malloc(IMAGE_BYTES));
  if (!buf) {
    Serial.println("Zu wenig Speicher");
    sleepFor(RETRY_SECONDS);
  }
  if (!connectWifi()) sleepFor(RETRY_SECONDS);

  uint32_t next = download(buf);
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  if (!next) sleepFor(RETRY_SECONDS);  // altes Bild bleibt stehen

  show(buf);
  Serial.println("Bild angezeigt");
  sleepFor(next);
}

void loop() {}
