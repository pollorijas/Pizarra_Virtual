"""Autodiagnóstico sin interfaz: ``PizarraVirtual.exe --selftest``.

Comprueba que Qt y sus plugins se cargan desde el ejecutable empaquetado y que
todas las herramientas producen píxeles. Devuelve 0 si todo es correcto.
"""
from __future__ import annotations

import logging
import os
import tempfile

log = logging.getLogger(__name__)


def render_all_tools():
    """Devuelve {nombre: píxeles pintados} para cada herramienta y tipo de pincel."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QPainter

    from . import render
    from .items import ShapeItem, StrokeItem
    from .tools import SHAPE_TOOLS, BrushType, Tool

    def blank():
        img = QImage(240, 160, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        return img

    def painted(img):
        n = 0
        for y in range(0, img.height(), 2):
            for x in range(0, img.width(), 2):
                if img.pixelColor(x, y).alpha() > 0:
                    n += 1
        return n

    pts = [(20 + i * 4.0, 80 + 30 * ((i % 10) / 10.0), 0.0) for i in range(45)]
    results = {}
    cases = [(Tool.BRUSH, bt) for bt in BrushType] + [(t, BrushType.HARD) for t in
                                                       (Tool.PENCIL, Tool.PEN, Tool.HIGHLIGHTER)]
    for tool, bt in cases:
        item = StrokeItem(tool, (200, 30, 30, 255), 12, 1.0, bt, seed=7,
                          points=[(x, y, 12 if tool != Tool.PEN else 3 + (i % 7)) for i, (x, y, _) in enumerate(pts)])
        img = blank()
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        render.draw_stroke(p, item)
        p.end()
        results[f"{tool.value}:{bt.value}"] = painted(img)

    for tool in SHAPE_TOOLS:
        item = ShapeItem(tool, (30, 30, 200, 255), 4, 1.0, 30, 30, 200, 130, filled=False)
        img = blank()
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        render.draw_shape(p, item)
        p.end()
        results[tool.value] = painted(img)

    # Texto (comprueba que hay fuentes disponibles en el ejecutable) y pautas
    from .items import TextItem

    img = blank()
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    render.draw_text(p, TextItem((20, 20, 20, 255), 28, 1.0, 10, 10, "Pizarra ñ 123"))
    p.end()
    results["text"] = painted(img)
    for pattern in ("grid", "mm", "ruled", "calligraphy", "cartesian", "staff"):
        img = blank()
        p = QPainter(img)
        render.draw_pattern(p, img.width(), img.height(), pattern, "white")
        p.end()
        results[f"pattern:{pattern}"] = painted(img)

    # Sellos y plantillas
    from .items import StampItem, flatten
    from .tools import STAMPS
    from . import templates
    from PySide6.QtCore import QRectF

    for kind in STAMPS:
        img = blank()
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        render.draw_stamp(p, StampItem(kind, (30, 100, 200, 255), 80, 1.0, 120, 80, "7"))
        p.end()
        results[f"stamp:{kind}"] = painted(img)
    for key in templates.TEMPLATES:
        img = QImage(480, 320, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for it in flatten([templates.build(key, QRectF(10, 10, 460, 300), (20, 20, 20, 255), 3)]):
            render.draw_item(p, it)
        p.end()
        results[f"template:{key}"] = painted(img)

    # Imagen pegada (PNG dentro de la sesión) y reconocimiento de formas
    import math

    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor

    from .items import ImageItem
    from .shape_recognition import recognize

    src = QImage(40, 30, QImage.Format.Format_RGB32)
    src.fill(QColor(30, 136, 229))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    src.save(buf, "PNG")
    img = blank()
    p = QPainter(img)
    render.draw_item(p, ImageItem(bytes(buf.data()), 20, 20, 120, 90))
    p.end()
    results["image"] = painted(img)
    circle = StrokeItem(Tool.PEN, (0, 0, 0, 255), 4, points=[(120 + 60 * math.cos(k / 10), 80 + 60 * math.sin(k / 10), 4)
                                                             for k in range(66)])
    shape = recognize(circle)
    results["recognize:circle"] = int(shape is not None and shape.tool == Tool.ELLIPSE)

    # Nota adhesiva, zona tapada y teclas en pantalla (v1.5)
    from .items import CoverItem, NoteItem
    from .keyview import KeyWatcher

    for name, item in (("note", NoteItem((38, 50, 56, 255), 24, 1.0, 30, 30, "Nota")),
                       ("cover", CoverItem(20, 20, 140, 90))):
        img = blank()
        p = QPainter(img)
        render.draw_item(p, item)
        p.end()
        results[name] = painted(img)
    watcher = KeyWatcher()
    watcher.update({0x11})
    results["keys:ctrl+c"] = int(watcher.update({0x11, 0x43}) == ["Ctrl + C"])

    # Instrumentos de geometría: se dibujan, la regla guía un trazo y el compás dibuja un arco
    from . import instruments as inst_mod

    for kind in inst_mod.INSTRUMENTS:
        inst = inst_mod.create(kind, QPointF(100, 100), 200, 200, inst_mod.DEFAULT_PPCM)
        img = blank()
        p = QPainter(img)
        inst.paint(p, 1.0)
        p.end()
        results["instrument:" + kind] = painted(img)
    ruler = inst_mod.Ruler(100, 100, inst_mod.DEFAULT_PPCM, 5)
    follow = ruler.guide(QPointF(100, 100 + ruler.width / 2 + 5), 1.0, 4.0)
    results["instrument:guide"] = int(follow is not None
                                      and abs(follow(QPointF(120, 170)).y() - (100 + ruler.width / 2 + 2)) < 0.01)
    compass = inst_mod.Compass(100, 100, 50)
    compass.press("draw", compass.pencil())
    arc = compass.drag(QPointF(100, 150))
    results["instrument:arc"] = int(len(arc) > 10 and all(abs(math.hypot(q.x() - 100, q.y() - 100) - 50) < 0.01
                                                              for q in arc))

    # La goma debe borrar lo pintado
    img = blank()
    img.fill(Qt.GlobalColor.black)
    before = painted(img)
    eraser = StrokeItem(Tool.ERASER, (0, 0, 0, 255), 30, 1.0, points=[(x, y, 30) for x, y, _ in pts])
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
    render.draw_stroke(p, eraser)
    p.end()
    results["eraser_removed"] = before - painted(img)
    return results


def run() -> int:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from . import icons
    from .capture import save_capture

    app = QApplication.instance() or QApplication([])
    ok = True
    for name, value in render_all_tools().items():
        log.info("selftest %-22s %d", name, value)
        if value <= 0:
            log.error("selftest: %s no dibujó nada", name)
            ok = False
    for name in ("brush", "pencil", "pen", "highlighter", "eraser", "camera", "power"):
        if icons.icon(name).isNull():
            ok = False
    img = icons.app_icon_image(64)
    with tempfile.TemporaryDirectory() as tmp:
        path = save_capture(img, tmp)
        ok = ok and os.path.getsize(path) > 0
    log.info("selftest: pantallas=%d plataforma=%s", len(QGuiApplication.screens()), app.platformName())
    log.info("selftest: %s", "OK" if ok else "FALLÓ")
    return 0 if ok else 1
