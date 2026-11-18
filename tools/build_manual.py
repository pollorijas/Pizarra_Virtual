"""Genera «Manual de usuario.pdf» a partir de docs/manual.html con imágenes de la propia aplicación.

Uso:  python tools/build_manual.py [--out "dist/Manual de usuario.pdf"] [--images carpeta]

Las imágenes (barra de herramientas, ejemplos de dibujo, pautas y herramientas de
presentación) se generan en el momento con Qt en modo «offscreen», así el manual siempre
muestra la versión actual del programa.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMarginsF, QPoint, QRect, QRectF, QSettings, Qt, QUrl  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor, QCursor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextDocument,
)
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QBoxLayout  # noqa: E402

from pizarra_virtual import __version__, icons, session  # noqa: E402
from pizarra_virtual.tools import PATTERNS, Tool  # noqa: E402

W, H = 760, 460  # zona de las capturas de ejemplo (px lógicos)


def _drag(ov, pts, delay=6):
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*pts[0]))
    for x, y in pts[1:]:
        QTest.mouseMove(ov, QPoint(int(x), int(y)), delay)
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*map(int, pts[-1])))


def _type(ctrl, ov, x, y, text, size, color, bold=False):
    ctrl.set_tool(Tool.TEXT)
    ctrl.set_size(size)
    ctrl.set_color(QColor(color))
    ctrl.set_text_bold(bold)
    QTest.mouseClick(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(x, y))
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    for ch in text:
        key = Qt.Key.Key_Return if ch == "\n" else 0
        QApplication.sendEvent(ctrl.toolbar, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier,
                                                       "" if ch == "\n" else ch))
    QTest.keyClick(ctrl.toolbar, Qt.Key.Key_Escape)


def _sample_drawing(ctrl, ov):
    """Una «clase» de ejemplo con varias herramientas."""
    _type(ctrl, ov, 40, 40, "Fotosíntesis", 40, "#1b3f7a", bold=True)
    ctrl.set_tool(Tool.HIGHLIGHTER)
    ctrl.set_color(QColor("#ffeb3b"))
    _drag(ov, [(38, 64), (290, 64)])
    _type(ctrl, ov, 44, 120, "luz + agua + CO₂  →  glucosa + O₂", 26, "#212121")
    ctrl.set_tool(Tool.PEN)
    ctrl.set_size(4)
    ctrl.set_color(QColor("#c62828"))
    _drag(ov, [(150 + 120 * math.cos(a / 12), 230 + 40 * math.sin(a / 12)) for a in range(0, 78)])
    ctrl.set_tool(Tool.ARROW)
    ctrl.set_size(4)
    ctrl.set_color(QColor("#2e7d32"))
    _drag(ov, [(300, 250), (450, 330)])
    ctrl.set_tool(Tool.RECT)
    ctrl.set_color(QColor("#1e88e5"))
    _drag(ov, [(460, 300), (700, 400)])
    _type(ctrl, ov, 478, 350, "¡Importante!", 30, "#1e88e5")
    ctrl.set_tool(Tool.BRUSH)
    ctrl.set_size(10)
    ctrl.set_color(QColor("#8e24aa"))
    _drag(ov, [(560 + 60 * math.cos(a / 8), 170 + 60 * math.sin(a / 8)) for a in range(0, 52)])


def _crop(img: QImage, w=W, h=H) -> QImage:
    d = img.devicePixelRatio()
    out = img.copy(QRect(0, 0, round(w * d), round(h * d)))
    out.setDevicePixelRatio(1.0)
    return out


def _label(img: QImage, text: str) -> QImage:
    out = QImage(img)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    f = QFont()
    f.setPixelSize(max(14, out.height() // 14))
    f.setBold(True)
    p.setFont(f)
    box = QRectF(10, 10, out.width() * 0.7, f.pixelSize() * 1.7)
    box.setWidth(p.fontMetrics().horizontalAdvance(text) + 24)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(30, 32, 38, 220))
    p.drawRoundedRect(box, 6, 6)
    p.setPen(QColor(255, 255, 255))
    p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return out


def _mosaic(images: list[QImage], cols: int, gap: int = 12) -> QImage:
    w, h = images[0].width(), images[0].height()
    rows = math.ceil(len(images) / cols)
    out = QImage(cols * w + (cols - 1) * gap, rows * h + (rows - 1) * gap, QImage.Format.Format_RGB32)
    out.fill(QColor(255, 255, 255))
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for i, img in enumerate(images):
        x, y = (i % cols) * (w + gap), (i // cols) * (h + gap)
        p.drawImage(QRectF(x, y, w, h), img)
        p.setPen(QColor(190, 195, 205))
        p.drawRect(QRectF(x, y, w - 1, h - 1))
    p.end()
    return out


def build_images() -> dict[str, QImage]:
    from pizarra_virtual.app import Controller

    app = QApplication.instance() or QApplication([])
    tmp = tempfile.mkdtemp()
    os.environ["USERPROFILE"] = tmp
    ctrl = Controller(app, settings=QSettings(os.path.join(tmp, "s.ini"), QSettings.Format.IniFormat),
                      enable_hotkeys=False, enable_tray=False)
    ctrl.start()
    app.processEvents()
    ov = next(iter(ctrl.overlays.values()))
    tb = ctrl.toolbar
    images: dict[str, QImage] = {"icono.png": icons.app_icon_image(144)}

    # Barra de herramientas en una columna (la herramienta pincel muestra sus opciones)
    ctrl.set_tool(Tool.BRUSH)
    tb.body_layout.setDirection(QBoxLayout.Direction.TopToBottom)
    tb.refit()
    app.processEvents()
    images["barra.png"] = tb.grab().toImage()
    tb.move(5000, 0)

    # Ejemplo de clase sobre cuadrícula
    ctrl.set_background("white")
    ctrl.set_pattern("grid")
    _sample_drawing(ctrl, ov)
    page_img = session.render_page(ctrl.page, ctrl.items_for(ov.key), ov.width(), ov.height(), scale=2.0)
    images["ejemplo.png"] = _crop(page_img)

    # Pautas
    pats = []
    for key in [k for k in PATTERNS if k != "none"]:
        empty = session.Page(background="white", pattern=key)
        img = session.render_page(empty, [], ov.width(), ov.height(), scale=1.0)
        pats.append(_label(_crop(img, 420, 300), PATTERNS[key]))
    chalk = session.render_page(session.Page(background="chalk", pattern="cartesian"), [], ov.width(), ov.height(),
                                scale=1.0)
    pats.append(_label(_crop(chalk, 420, 300), "Pizarra verde + plano"))
    images["pautas.png"] = _mosaic(pats, 3)

    # Herramientas de presentación sobre el ejemplo
    def shot(name):
        app.processEvents()
        img = ov.grab().toImage()
        return _label(_crop(img), name)

    QCursor.setPos(ov.mapToGlobal(QPoint(170, 130)))
    ctrl.toggle_spotlight()
    ctrl._tick()
    foco = shot("Foco")
    ctrl.toggle_spotlight()
    ctrl.toggle_curtain()
    ov.set_curtain(150)
    cortina = shot("Cortina")
    ctrl.toggle_curtain()
    QCursor.setPos(ov.mapToGlobal(QPoint(380, 220)))
    ctrl.toggle_highlight()
    state = {"b": (False, False)}
    ctrl.button_state = lambda: state["b"]
    ctrl._tick()
    state["b"] = (True, False)
    ctrl._tick()
    QTest.qWait(120)
    state["b"] = (False, False)
    ctrl._tick()
    resaltar = shot("Resaltar cursor y clics")
    ctrl.toggle_highlight()
    ctrl.set_tool(Tool.LASER)
    ctrl.set_color(QColor("#e53935"))
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(470, 150))
    for i in range(36):
        QTest.mouseMove(ov, QPoint(int(470 + 90 * math.cos(i / 5.6)), int(110 + 45 * math.sin(i / 5.6))), 5)
    QCursor.setPos(ov.mapToGlobal(QPoint(560, 110)))
    ctrl._tick()
    laser = shot("Láser con tinta temporal")
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(560, 110))
    images["presentacion.png"] = _mosaic([foco, cortina, resaltar, laser], 2)

    ctrl.dirty = False
    ctrl.shutdown()
    return images


def build_pdf(out: str, images: dict[str, QImage]) -> str:
    with open(os.path.join(ROOT, "docs", "manual.html"), encoding="utf-8") as f:
        html = f.read().replace("{VERSION}", __version__)
    doc = QTextDocument()
    font = QFont()
    font.setFamilies(["Segoe UI", "Arial", "DejaVu Sans", "sans-serif"])
    font.setPointSizeF(10.5)
    doc.setDefaultFont(font)
    doc.setDefaultStyleSheet(
        "h1 { color: #1b3f7a; font-size: 26pt; }"
        "h2 { color: #1b3f7a; font-size: 16pt; margin-top: 16px; }"
        "h3 { color: #2f6fd1; font-size: 12pt; margin-top: 10px; }"
        "th { text-align: left; }"
        "td, th, li, p { font-size: 10pt; }")
    for name, img in images.items():
        doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), img)
    doc.setHtml(html)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    writer = QPdfWriter(out)
    writer.setTitle(f"Pizarra Virtual {__version__} — Manual de usuario")
    writer.setCreator("Pizarra Virtual")
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                     QMarginsF(16, 14, 16, 14), QPageLayout.Unit.Millimeter))
    doc.print_(writer)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "dist", "Manual de usuario.pdf"))
    ap.add_argument("--images", help="guardar también las imágenes en esta carpeta")
    args = ap.parse_args()
    images = build_images()
    if args.images:
        os.makedirs(args.images, exist_ok=True)
        for name, img in images.items():
            img.save(os.path.join(args.images, name))
    path = build_pdf(args.out, images)
    print("Manual generado:", path, os.path.getsize(path), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
