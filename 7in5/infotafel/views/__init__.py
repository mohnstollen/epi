"""Die vier Ansichten. ``render(ctx)`` liefert ein 800x480-Bild im Modus "1"."""
import logging

from ..render import Canvas
from . import nachrichten, termine, unterwegs, wetter

log = logging.getLogger(__name__)

VIEWS = {
    "unterwegs": unterwegs.draw,
    "wetter": wetter.draw,
    "nachrichten": nachrichten.draw,
    "termine": termine.draw,
}


def render(ctx):
    cv = Canvas()
    try:
        VIEWS[ctx.view](cv, ctx)
    except Exception:
        # Ein Fehler in einer Ansicht soll nicht das ganze Display lahmlegen
        log.exception("Ansicht %s konnte nicht gezeichnet werden", ctx.view)
        cv = Canvas()
        cv.header(ctx, ctx.view, lambda *a: None, stale=True)
        cv.unavailable((0, 48, 800, 480), f"Fehler beim Zeichnen der Ansicht „{ctx.view}“ – siehe Log")
    return cv.image
