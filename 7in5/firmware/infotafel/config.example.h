// Kopieren nach config.h (im selben Ordner) und anpassen. config.h steht in der .gitignore.
#pragma once

// --- WLAN ------------------------------------------------------------------
#define WIFI_SSID     "MeinWLAN"
#define WIFI_PASSWORD "geheim"
#define WIFI_HOSTNAME "infotafel"

// --- Server (python -m infotafel serve) -------------------------------------
// IP-Adresse oder Hostname des Homeservers, Port wie bei --port (Standard 8080).
#define SERVER_URL "http://192.168.178.10:8080/image.bin"

// --- Panel -----------------------------------------------------------------
// Standard: GxEPD2_750_T7 (GDEW075T7) für das Waveshare 7.5" V2.
// Bleibt das Bild leer, blass oder gestört, die neuere Variante probieren:
// #define PANEL_GDEY075T7

// --- Verkabelung -----------------------------------------------------------
// Standard: Waveshare "Universal e-Paper Raw Panel Driver Board" (ESP32),
// Display per Flachbandkabel direkt am Board. Schalter auf dem Board: "B".
#define PIN_SCK   13
#define PIN_MISO  12   // wird nicht benutzt, aber für SPI.begin gebraucht
#define PIN_MOSI  14
#define PIN_CS    15
#define PIN_DC    27
#define PIN_RST   26
#define PIN_BUSY  25
#define PIN_PWR   -1

// Alternative: e-Paper Driver HAT per Kabel an einem ESP32-DevKit (WROOM):
//   HAT-Kabel: VCC->3V3, GND->GND, DIN->23, CLK->18, CS->5, DC->17, RST->16, BUSY->4, PWR->22 (nur HAT Rev2.3)
// #define PIN_SCK   18
// #define PIN_MISO  19
// #define PIN_MOSI  23
// #define PIN_CS     5
// #define PIN_DC    17
// #define PIN_RST   16
// #define PIN_BUSY   4
// #define PIN_PWR   22

// --- Zeiten ------------------------------------------------------------------
#define RETRY_SECONDS   60    // erster Wiederholversuch bei Fehlern (verdoppelt sich bis 15 min)
#define DEFAULT_SECONDS 300   // falls der Server keine Schlafdauer mitschickt
