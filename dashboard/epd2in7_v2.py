"""Minimaler Treiber für das Waveshare 2.7inch e-Paper HAT Rev2.1 (V2, SSD1680).

Angelehnt an den offiziellen Waveshare-Treiber ``epd2in7_V2.py``, aber ohne
dessen Abhängigkeiten: nur ``spidev`` und ``gpiozero`` werden benötigt.
Es wird ausschließlich die Vollaktualisierung (schwarz/weiß) verwendet.
"""
import time

WIDTH = 176   # native Ausrichtung (Hochformat)
HEIGHT = 264

# BCM-Pinbelegung des HATs
RST_PIN = 17
DC_PIN = 25
BUSY_PIN = 24
PWR_PIN = 18


class EPD:
    def __init__(self, busy_timeout=30.0):
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

    def _reset(self):
        self._rst.on()
        time.sleep(0.2)
        self._rst.off()
        time.sleep(0.002)
        self._rst.on()
        time.sleep(0.2)

    def _command(self, cmd):
        self._dc.off()
        self._spi.writebytes([cmd])

    def _data(self, *data):
        self._dc.on()
        self._spi.writebytes2(bytes(data))

    def _wait_busy(self):
        deadline = time.monotonic() + self._busy_timeout
        while self._busy.value:  # 1 = beschäftigt
            if time.monotonic() > deadline:
                raise TimeoutError("e-Paper bleibt im BUSY-Zustand")
            time.sleep(0.02)

    def init(self):
        self._reset()
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
        """Wandelt ein PIL-Bild (264x176 oder 176x264) in den Displaypuffer."""
        if image.size == (HEIGHT, WIDTH):
            image = image.rotate(90, expand=True)
        elif image.size != (WIDTH, HEIGHT):
            raise ValueError(f"Bildgröße {image.size} passt nicht zum Display")
        if rotate180:
            image = image.rotate(180)
        return image.convert("1").tobytes("raw")

    def display(self, buf):
        self._command(0x24)
        self._dc.on()
        self._spi.writebytes2(buf)
        self._command(0x22)  # Vollaktualisierung
        self._data(0xF7)
        self._command(0x20)
        self._wait_busy()

    def sleep(self):
        """Tiefschlaf; zum Aufwecken muss erneut ``init()`` aufgerufen werden."""
        self._command(0x10)
        self._data(0x01)
        time.sleep(0.1)

    def close(self):
        self._spi.close()
        self._pwr.off()
        for dev in (self._rst, self._dc, self._pwr, self._busy):
            dev.close()
