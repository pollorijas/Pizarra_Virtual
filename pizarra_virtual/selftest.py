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
    from PySide6.QtCore import Qt
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
