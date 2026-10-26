// Kopieren nach config.h (im selben Ordner) und anpassen.
#pragma once

// --- WLAN ---------------------------------------------------------------
#define WIFI_SSID     "MeinWLAN"
#define WIFI_PASSWORD "geheim"

// --- Server auf dem Raspberry Pi (python3 -m dashboard --serve) ---------
// IP-Adresse oder Hostname des Pi; Port wie bei --port (Standard 8080).
#define SERVER_URL "http://192.168.178.50:8080/image.bin"

// --- Display: genau eine Zeile aktiv lassen ------------------------------
// Muss zu "display" in der config.toml auf dem Pi passen.
#define DISPLAY_7IN5      // Waveshare 7.5inch e-Paper V2, 800x480
// #define DISPLAY_2IN7   // Waveshare 2.7inch e-Paper Rev2.1 (V2), 176x264

// --- Verkabelung ---------------------------------------------------------
// Standard: e-Paper-HAT über sein Kabel an einem ESP32-DevKit (WROOM).
//   HAT-Kabel   ESP32
//   VCC         3V3
//   GND         GND
//   DIN         GPIO 23
//   CLK         GPIO 18
//   CS          GPIO 5
//   DC          GPIO 17
//   RST         GPIO 16
//   BUSY        GPIO 4
//   PWR         GPIO 22  (nur Driver HAT Rev2.3; sonst PIN_PWR auf -1 setzen)
// Achtung: Bei ESP32-WROVER-Modulen sind GPIO 16/17 belegt – dort andere Pins wählen.
#define PIN_SCK   18
#define PIN_MOSI  23
#define PIN_CS     5
#define PIN_DC    17
#define PIN_RST   16
#define PIN_BUSY   4
#define PIN_PWR   22

// Für das Waveshare "Universal e-Paper Driver Board" (ESP32, Display direkt
// per Flachbandkabel) stattdessen:
// #define PIN_SCK   13
// #define PIN_MOSI  14
// #define PIN_CS    15
// #define PIN_DC    27
// #define PIN_RST   26
// #define PIN_BUSY  25
// #define PIN_PWR   -1

// Bild um 180° drehen: in der config.toml auf dem Pi (rotate180) einstellen.

// --- Zeiten --------------------------------------------------------------
#define RETRY_SECONDS   60    // nächster Versuch, wenn WLAN oder Server nicht erreichbar
#define DEFAULT_SECONDS 180   // falls der Server keine Wartezeit mitschickt
