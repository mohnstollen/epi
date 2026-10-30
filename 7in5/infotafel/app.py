"""Bild für einen Zeitpunkt erzeugen: Plan + Daten -> PNG und Displaypuffer."""
import hashlib
import io
from dataclasses import dataclass

from . import schedule
from .render import Context
from .sources.weather import active_warnings
from .views import render


@dataclass
class Frame:
    view: str
    image: object           # PIL-Bild 800x480, Modus "1"
    sleep_seconds: int
    mode: str

    def to_buffer(self, rotate180=False):
        """Displaypuffer für GxEPD2: 1 Bit je Pixel, zeilenweise, MSB links, 1 = weiß (48000 Bytes)."""
        img = self.image.rotate(180) if rotate180 else self.image
        return img.convert("1").tobytes("raw")

    def png(self):
        out = io.BytesIO()
        self.image.save(out, "PNG", optimize=True)
        return out.getvalue()


def etag(buffer):
    return hashlib.sha1(buffer).hexdigest()[:16]


def warnings_for(cfg, data, now, night=False):
    key = "night_min_severity" if night else "min_severity"
    return active_warnings(data.get("warnings"), now, cfg["warnings"][key])


def make_frame(cfg, data, now, view=None):
    """Erzeugt das Bild, das zum Zeitpunkt ``now`` gezeigt wird (oder eine bestimmte Ansicht)."""
    night_warning = bool(warnings_for(cfg, data, now, night=True))
    p = schedule.plan(cfg, now, night_warning)
    shown = view or p.view
    ctx = Context(cfg=cfg, data=data, now=now, view=shown,
                  views=p.views if shown in p.views else cfg["schedule"]["views"],
                  warnings=warnings_for(cfg, data, now), night=p.night)
    return Frame(shown, render(ctx), p.sleep_seconds, p.mode)
