"""Schlanke Treiber für Waveshare-e-Paper-HATs (nur schwarz/weiß, Vollaktualisierung).

Angelehnt an die offiziellen Waveshare-Treiber ``epd2in7_V2.py`` und
``epd7in5_V2.py``, aber ohne deren Abhängigkeiten: nur ``spidev`` und
``gpiozero`` werden benötigt.
"""
import time

# BCM-Pinbelegung der HATs
RST_PIN = 17
DC_PIN = 25
BUSY_PIN = 24
PWR_PIN = 18  # nur bei neueren HATs (z. B. Driver HAT Rev2.3) belegt


class _EPD:
    WIDTH = HEIGHT = 0      # native Ausrichtung des Panels
    BUSY_LEVEL = 1          # Pegel der BUSY-Leitung, solange das Panel arbeitet

    def __init__(self, busy_timeout=40.0):
        import spidev
        from gpiozero import DigitalInputDevice, DigitalOutputDevice

        self._busy_timeout = busy_timeout
        self._rst = DigitalOutputDevice(RST_PIN)
        self._dc = DigitalOutputDevice(DC_PIN)
        self._pwr = DigitalOutputDevice(PWR_PIN, initial_value=True)
        self._busy = DigitalInputDevice(BUSY_PIN, pull_up=False)
        self._spi = spidev.SpiDev()
        self._spi.open(0, 0)  # Chip Select über CE0 (GPIO 8)
        self._spi.max_speed_hz = 4_000_000
        self._spi.mode = 0b00

    def _reset(self, hold):
        self._rst.on()
        time.sleep(hold)
        self._rst.off()
        time.sleep(0.002)
        self._rst.on()
        time.sleep(hold)

    def _command(self, cmd):
        self._dc.off()
        self._spi.writebytes([cmd])

    def _data(self, *data):
        self._dc.on()
        self._spi.writebytes2(bytes(data))

    def _write(self, buf):
        self._dc.on()
        self._spi.writebytes2(buf)

    def _poll_busy(self):
        """Hook für Controller, die vor jeder BUSY-Abfrage ein Kommando erwarten."""

    def _wait_busy(self):
        deadline = time.monotonic() + self._busy_timeout
        self._poll_busy()
        while self._busy.value == self.BUSY_LEVEL:
            if time.monotonic() > deadline:
                raise TimeoutError("e-Paper bleibt im BUSY-Zustand")
            time.sleep(0.02)
            self._poll_busy()

    def _to_native(self, image, rotate180):
        """Wandelt ein PIL-Bild in die native Ausrichtung des Panels (Modus "1")."""
        if image.size == (self.HEIGHT, self.WIDTH):
            image = image.rotate(90, expand=True)
        elif image.size != (self.WIDTH, self.HEIGHT):
            raise ValueError(f"Bildgröße {image.size} passt nicht zum Display")
        if rotate180:
            image = image.rotate(180)
        return image.convert("1")

    def close(self):
        self._spi.close()
        self._pwr.off()
        for dev in (self._rst, self._dc, self._pwr, self._busy):
            dev.close()


class EPD2in7V2(_EPD):
    """2.7inch e-Paper HAT Rev2.1 (V2), 176x264."""

    WIDTH, HEIGHT = 176, 264
    BUSY_LEVEL = 1

    def init(self):
        self._reset(0.2)
        self._wait_busy()
        self._command(0x12)  # Software-Reset
        self._wait_busy()
        self._command(0x45)  # RAM-Y-Bereich 0..263
        self._data(0x00, 0x00, 0x07, 0x01)
        self._command(0x4F)  # RAM-Y-Zähler
        self._data(0x00, 0x00)
        self._command(0x11)  # Data Entry Mode: X+, Y+
        self._data(0x03)
        self._wait_busy()

    def getbuffer(self, image, rotate180=False):
        return self._to_native(image, rotate180).tobytes("raw")

    def display(self, buf):
        self._command(0x24)
        self._write(buf)
        self._command(0x22)  # Vollaktualisierung
        self._data(0xF7)
        self._command(0x20)
        self._wait_busy()

    def sleep(self):
        """Tiefschlaf; zum Aufwecken muss erneut ``init()`` aufgerufen werden."""
        self._command(0x10)
        self._data(0x01)
        time.sleep(0.1)


class EPD7in5V2(_EPD):
    """7.5inch e-Paper HAT V2, 800x480."""

    WIDTH, HEIGHT = 800, 480
    BUSY_LEVEL = 0

    def _poll_busy(self):
        self._command(0x71)  # Statusabfrage, aktualisiert die BUSY-Leitung

    def init(self):
        self._reset(0.02)
        self._command(0x06)  # Booster Soft Start
        self._data(0x17, 0x17, 0x28, 0x17)
        self._command(0x01)  # Power Setting: VGH/VGL = ±20 V, VDH/VDL = ±15 V
        self._data(0x07, 0x07, 0x3F, 0x3F)
        self._command(0x04)  # Power On
        time.sleep(0.1)
        self._wait_busy()
        self._command(0x00)  # Panel Setting: KW-Modus, LUT aus OTP
        self._data(0x1F)
        self._command(0x61)  # Auflösung 800x480
        self._data(0x03, 0x20, 0x01, 0xE0)
        self._command(0x15)
        self._data(0x00)
        self._command(0x50)  # VCOM and Data Interval
        self._data(0x10, 0x07)
        self._command(0x60)  # TCON
        self._data(0x22)

    def getbuffer(self, image, rotate180=False):
        return self._to_native(image, rotate180).tobytes("raw")

    def display(self, buf):
        self._command(0x10)  # alte Daten
        self._write(buf)
        self._command(0x13)  # neue Daten (0 = weiß)
        self._write(bytes(b ^ 0xFF for b in buf))
        self._command(0x12)  # Display Refresh
        time.sleep(0.1)
        self._wait_busy()

    def sleep(self):
        """Tiefschlaf; zum Aufwecken muss erneut ``init()`` aufgerufen werden."""
        self._command(0x50)
        self._data(0xF7)
        self._command(0x02)  # Power Off
        self._wait_busy()
        self._command(0x07)  # Deep Sleep
        self._data(0xA5)
        time.sleep(0.1)
