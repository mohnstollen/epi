"""Zeichen-Grundlagen: Schriften, Textumbruch, Kopfzeile, Abschnittsüberschriften.

Gezeichnet wird direkt in ein 1-Bit-Bild (Modus "1"): Text ohne Kantenglättung,
damit das e-Paper scharfe Kanten ohne Grauraster zeigt.
"""
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import icons

W, H = 800, 480
HEADER = 48
PAD = 20
BLACK, WHITE = 0, 255
FONT_DIR = Path(__file__).with_name("fonts")

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WEEKDAYS_LONG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


@lru_cache(maxsize=None)
def sans(size, weight="regular"):
    name = {"regular": "Regular", "semibold": "SemiBold", "bold": "Bold"}[weight]
    return ImageFont.truetype(str(FONT_DIR / f"IBMPlexSansCondensed-{name}.ttf"), size)


@lru_cache(maxsize=None)
def mono(size, bold=True):
    return ImageFont.truetype(str(FONT_DIR / f"IBMPlexMono-{'Bold' if bold else 'Medium'}.ttf"), size)


def de_num(value, decimals=0, sign=False):
    """Zahl im deutschen Format: 24.312 / 1,72 / +0,8."""
    text = f"{value:{'+' if sign else ''},.{decimals}f}"
    text = text.replace(",", " ").replace(".", ",").replace(" ", ".")
    return text.replace("-", "−")


def temp(value):
    return f"{round(value)}°".replace("-", "−")


def short_date(d):
    return f"{WEEKDAYS[d.weekday()]} {d.day:02d}.{d.month:02d}."


@dataclass
class Context:
    cfg: dict
    data: object         # sources.Data
    now: datetime
    view: str
    views: list          # aktuelle Rotation (für die Punkte in der Kopfzeile)
    warnings: list       # aktive Warnungen (für die Kopfzeile)
    night: bool = False


class Canvas:
    def __init__(self):
        self.image = Image.new("1", (W, H), WHITE)
        self.draw = ImageDraw.Draw(self.image)
        self.draw.fontmode = "1"

    # --- Text -------------------------------------------------------------------
    def width(self, text, font):
        return self.draw.textlength(text, font=font)

    def text(self, xy, text, font, anchor="la", fill=BLACK):
        self.draw.text(xy, text, font=font, fill=fill, anchor=anchor)

    def fit(self, text, font, max_width):
        """Kürzt ``text`` mit "…", bis er in ``max_width`` passt."""
        if self.width(text, font) <= max_width:
            return text
        while text and self.width(text + "…", font) > max_width:
            text = text[:-1]
        return text.rstrip(" ,.;:–-") + "…"

    def wrap(self, text, font, max_width, max_lines):
        """Bricht an Wortgrenzen um; die letzte Zeile wird bei Bedarf gekürzt."""
        words, lines, line = text.split(), [], ""
        for i, word in enumerate(words):
            candidate = f"{line} {word}".strip()
            if self.width(candidate, font) <= max_width or not line:
                line = candidate
                continue
            lines.append(line)
            line = word
            if len(lines) == max_lines - 1:
                line = " ".join(words[i:])
                break
        if line:
            lines.append(line)
        lines = [self.fit(l, font, max_width) for l in lines[:max_lines]]
        return lines

    # --- Bausteine --------------------------------------------------------------
    def label(self, x0, y, x1, text, right=None):
        """Abschnittsüberschrift in Versalien mit Unterstrich; liefert die y-Position darunter."""
        f = sans(15, "bold")
        self.text((x0, y), text.upper(), f)
        if right:
            self.text((x1, y), right, sans(15), "ra")
        self.draw.rectangle((x0, y + 21, x1, y + 22), fill=BLACK)
        return y + 30

    def hline(self, x0, x1, y, width=1):
        self.draw.rectangle((x0, y, x1, y + width - 1), fill=BLACK)

    def badge(self, x, y, text, font, pad_x=6, pad_y=2, inverted=True, min_width=0, anchor="l"):
        """Text in einem (schwarzen) Kasten. Liefert die Box."""
        ascent, _ = font.getmetrics()
        w = max(self.width(text, font) + 2 * pad_x, min_width)
        h = ascent + 2 * pad_y
        if anchor == "r":
            x -= w
        box = (x, y, x + w - 1, y + h - 1)
        if inverted:
            self.draw.rectangle(box, fill=BLACK)
        else:
            self.draw.rectangle(box, outline=BLACK, width=2)
        self.text((x + w / 2, y + pad_y + ascent), text, font, "ms", WHITE if inverted else BLACK)
        return box

    def unavailable(self, box, text="keine Daten"):
        x0, y0, x1, y1 = box
        self.text(((x0 + x1) / 2, (y0 + y1) / 2), text, sans(17), "mm")

    # --- Kopfzeile --------------------------------------------------------------
    def header(self, ctx, title, icon, stale=False):
        d = self.draw
        d.rectangle((0, 0, W - 1, HEADER - 1), fill=BLACK)
        icon(d, PAD, 11, 26, WHITE)
        f_title = sans(23, "bold")
        self.text((PAD + 36, HEADER // 2), title.upper(), f_title, "lm", WHITE)
        title_end = PAD + 36 + self.width(title.upper(), f_title)

        date = f"{'! ' if stale else ''}{WEEKDAYS[ctx.now.weekday()]} {ctx.now.day:02d}.{ctx.now.month:02d}."
        f_date = mono(20, True)
        self.text((W - PAD, HEADER // 2), date, f_date, "rm", WHITE)
        date_start = W - PAD - self.width(date, f_date)

        if ctx.warnings and ctx.view != "wetter":
            # Aktive Unwetterwarnung statt der Seitenpunkte, zwischen Titel und Datum
            w = ctx.warnings[0]
            text = w.event.upper() or "UNWETTERWARNUNG"
            if w.expires:
                text += f" BIS {'MORGEN ' if w.expires.date() != ctx.now.date() else ''}{w.expires:%H:%M}"
            x0, x1 = title_end + 24, date_start - 24
            d.rectangle((x0 - 10, 6, x1 + 10, HEADER - 7), fill=WHITE)
            f = sans(18, "bold")
            text = self.fit(text, f, x1 - x0 - 32)
            tw = self.width(text, f) + 32
            x = (x0 + x1) / 2 - tw / 2
            icons.warning(d, x, 12, 24, BLACK)
            self.text((x + 32, HEADER // 2), text, f, "lm", BLACK)
        elif len(ctx.views) > 1 and ctx.view in ctx.views:
            n, r, gap = len(ctx.views), 6, 22
            x = W / 2 + 60 - (n - 1) * gap / 2
            for i, v in enumerate(ctx.views):
                box = (x + i * gap - r, HEADER / 2 - r, x + i * gap + r, HEADER / 2 + r)
                if v == ctx.view:
                    d.ellipse(box, fill=WHITE)
                else:
                    d.ellipse(box, outline=WHITE, width=2)
