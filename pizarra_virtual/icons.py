"""Iconos vectoriales dibujados con QPainter (sin archivos externos, nítidos en cualquier DPI)."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
    QRadialGradient,
)

FG = "#e6e8eb"


def _pen(c: QColor, w: float = 1.8) -> QPen:
    pen = QPen(c, w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _poly(*pts) -> QPolygonF:
    return QPolygonF([QPointF(x, y) for x, y in pts])


# Cada función dibuja en un espacio de 24x24.

def _brush(p, c):
    p.setPen(_pen(c, 2.4))
    p.drawLine(QPointF(20, 4), QPointF(13, 11))
    path = QPainterPath()
    path.moveTo(13.5, 12.5)
    path.quadTo(14.5, 18, 9, 20)
    path.quadTo(5.5, 21.2, 3, 21)
    path.quadTo(5, 19, 5, 16.5)
    path.quadTo(6, 11, 11.5, 10.5)
    path.closeSubpath()
    p.setPen(_pen(c, 1.2))
    p.setBrush(c)
    p.drawPath(path)


def _pencil(p, c):
    p.translate(12, 12)
    p.rotate(45)
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(-3, -10, 6, 14))
    p.drawLine(QPointF(-3, -7), QPointF(3, -7))
    p.drawPolygon(_poly((-3, 4), (3, 4), (0, 10)))
    p.setBrush(c)
    p.drawPolygon(_poly((-1, 8), (1, 8), (0, 10)))


def _pen_nib(p, c):
    p.translate(12, 12)
    p.rotate(45)
    path = QPainterPath()
    path.moveTo(0, 11)
    path.lineTo(-5, 1)
    path.quadTo(-5, -5, -3, -9)
    path.lineTo(3, -9)
    path.quadTo(5, -5, 5, 1)
    path.closeSubpath()
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.drawLine(QPointF(0, 10), QPointF(0, 2))
    p.setBrush(c)
    p.drawEllipse(QPointF(0, 0.5), 1.3, 1.3)


def _highlighter(p, c):
    p.fillRect(QRectF(2, 18.5, 20, 4), QColor(255, 225, 0, 190))
    p.translate(13, 9)
    p.rotate(45)
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(-4, -9, 8, 10))
    p.setBrush(c)
    p.drawPolygon(_poly((-4, 1), (4, 1), (2.5, 6), (-2.5, 6)))


def _eraser(p, c):
    p.setPen(_pen(c, 1.6))
    p.drawLine(QPointF(8, 21), QPointF(21, 21))
    p.translate(12, 12)
    p.rotate(-45)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-9, -4.5, 18, 9), 1.5, 1.5)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(-9, -4.5, 8, 9), 1.5, 1.5)


def _rect(p, c):
    p.setPen(_pen(c, 2))
    p.drawRect(QRectF(4, 6, 16, 12))


def _ellipse(p, c):
    p.setPen(_pen(c, 2))
    p.drawEllipse(QRectF(3, 5, 18, 14))


def _triangle(p, c):
    p.setPen(_pen(c, 2))
    p.drawPolygon(_poly((12, 4), (21, 19.5), (3, 19.5)))


def _line(p, c):
    p.setPen(_pen(c, 2.2))
    p.drawLine(QPointF(4, 20), QPointF(20, 4))


def _arrow(p, c):
    p.setPen(_pen(c, 2.2))
    p.drawLine(QPointF(4, 20), QPointF(16, 8))
    p.setBrush(c)
    p.setPen(_pen(c, 1.2))
    p.drawPolygon(_poly((20.5, 3.5), (11.5, 6.5), (17.5, 12.5)))


def _undo(p, c):
    path = QPainterPath()
    path.moveTo(5, 10)
    path.lineTo(14, 10)
    path.cubicTo(21, 10, 21, 20, 14, 20)
    path.lineTo(9, 20)
    p.setPen(_pen(c, 2))
    p.drawPath(path)
    p.drawPolyline(_poly((9, 6), (5, 10), (9, 14)))


def _redo(p, c):
    p.translate(24, 0)
    p.scale(-1, 1)
    _undo(p, c)


def _trash(p, c):
    p.setPen(_pen(c, 1.8))
    p.drawLine(QPointF(4, 6.5), QPointF(20, 6.5))
    p.drawPolyline(_poly((9, 6.5), (9, 4), (15, 4), (15, 6.5)))
    p.drawPolyline(_poly((6, 6.5), (7.5, 20.5), (16.5, 20.5), (18, 6.5)))
    p.drawLine(QPointF(10.3, 10), QPointF(10.6, 17))
    p.drawLine(QPointF(13.7, 10), QPointF(13.4, 17))


def _camera(p, c):
    p.setPen(_pen(c, 1.8))
    p.drawRoundedRect(QRectF(3, 7, 18, 13), 2.5, 2.5)
    p.drawPolyline(_poly((8, 7), (9.5, 4.5), (14.5, 4.5), (16, 7)))
    p.drawEllipse(QPointF(12, 13.5), 3.6, 3.6)


def _folder(p, c):
    p.setPen(_pen(c, 1.8))
    p.drawPolygon(_poly((3, 5.5), (9, 5.5), (11, 8), (21, 8), (21, 19), (3, 19)))


def _eye(p, c):
    path = QPainterPath()
    path.moveTo(2, 12)
    path.quadTo(12, 2, 22, 12)
    path.quadTo(12, 22, 2, 12)
    p.setPen(_pen(c, 1.8))
    p.drawPath(path)
    p.setBrush(c)
    p.drawEllipse(QPointF(12, 12), 3, 3)


def _eye_off(p, c):
    _eye(p, c)
    p.setPen(_pen(c, 2))
    p.drawLine(QPointF(4, 4), QPointF(20, 20))


def _power(p, c):
    p.setPen(_pen(c, 2))
    p.drawArc(QRectF(5, 5.5, 14, 14), 125 * 16, 290 * 16)
    p.drawLine(QPointF(12, 3), QPointF(12, 11))


def _mouse(p, c):
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(_poly((6, 3), (6, 19), (10, 15.2), (12.8, 21), (15.4, 19.8), (12.6, 14.2), (18, 14)))


def _help(p, c):
    p.setPen(_pen(c, 1.8))
    p.drawEllipse(QPointF(12, 12), 9, 9)
    f = QFont()
    f.setBold(True)
    f.setPixelSize(13)
    p.setFont(f)
    p.drawText(QRectF(3, 3, 18, 18), Qt.AlignmentFlag.AlignCenter, "?")


def _zoom(p, c):
    p.setPen(_pen(c, 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(10, 10), 6.5, 6.5)
    p.setPen(_pen(c, 2.8))
    p.drawLine(QPointF(15, 15), QPointF(21, 21))
    p.setPen(_pen(c, 1.7))
    p.drawLine(QPointF(7, 10), QPointF(13, 10))
    p.drawLine(QPointF(10, 7), QPointF(10, 13))


def _text(p, c):
    f = QFont()
    f.setFamilies(["Georgia", "Times New Roman", "serif"])
    f.setBold(True)
    f.setPixelSize(19)
    p.setFont(f)
    p.setPen(c)
    p.drawText(QRectF(2, 1, 20, 22), Qt.AlignmentFlag.AlignCenter, "T")
    p.setPen(_pen(c, 1.4))
    p.drawLine(QPointF(17.5, 15), QPointF(17.5, 22))


def _laser(p, c):
    red = QColor(255, 70, 70)
    g = QRadialGradient(QPointF(12, 12), 7)
    g.setColorAt(0, QColor(255, 255, 255))
    g.setColorAt(0.35, red)
    g.setColorAt(1, QColor(255, 70, 70, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(12, 12), 7, 7)
    p.setPen(_pen(c, 1.6))
    for a, b in (((12, 1.5), (12, 4.5)), ((12, 19.5), (12, 22.5)), ((1.5, 12), (4.5, 12)), ((19.5, 12), (22.5, 12)),
                 ((4.5, 4.5), (6.5, 6.5)), ((17.5, 17.5), (19.5, 19.5)), ((4.5, 19.5), (6.5, 17.5)),
                 ((17.5, 6.5), (19.5, 4.5))):
        p.drawLine(QPointF(*a), QPointF(*b))


def _spotlight(p, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c.red(), c.green(), c.blue(), 70))
    p.drawRoundedRect(QRectF(2, 3, 20, 18), 3, 3)
    p.setBrush(QColor(255, 225, 90))
    p.drawEllipse(QPointF(12, 12), 5.5, 5.5)
    p.setPen(_pen(c, 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(2, 3, 20, 18), 3, 3)


def _curtain(p, c):
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(QRectF(3, 3, 18, 18))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawRect(QRectF(3, 11, 18, 10))
    p.setBrush(QColor(80, 140, 230))
    p.drawRect(QRectF(3, 10, 18, 2))
    p.setPen(_pen(c, 1.6))
    p.drawPolyline(_poly((9, 6), (12, 8.5), (15, 6)))


def _highlight(p, c):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 220, 0, 120))
    p.drawEllipse(QPointF(10, 10), 8.5, 8.5)
    p.setPen(_pen(c, 1.5))
    p.setBrush(QColor(30, 32, 37))
    p.drawPolygon(_poly((8, 6), (8, 20), (11.5, 16.6), (14, 22), (16.3, 21), (13.8, 15.8), (18.5, 15.5)))


def _page_prev(p, c):
    p.setPen(_pen(c, 2.2))
    p.drawPolyline(_poly((15, 5), (8, 12), (15, 19)))


def _page_next(p, c):
    p.setPen(_pen(c, 2.2))
    p.drawPolyline(_poly((9, 5), (16, 12), (9, 19)))


def _page_add(p, c):
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(_poly((5, 3), (14, 3), (19, 8), (19, 21), (5, 21)))
    p.drawPolyline(_poly((14, 3), (14, 8), (19, 8)))
    p.setPen(_pen(c, 2))
    p.drawLine(QPointF(12, 11), QPointF(12, 18))
    p.drawLine(QPointF(8.5, 14.5), QPointF(15.5, 14.5))


def _file(p, c):
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(_poly((5, 3), (14, 3), (19, 8), (19, 21), (5, 21)))
    p.drawPolyline(_poly((14, 3), (14, 8), (19, 8)))
    for y in (12, 15, 18):
        p.drawLine(QPointF(8, y), QPointF(16, y))


def _save(p, c):
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(_poly((4, 4), (17, 4), (20, 7), (20, 20), (4, 20)))
    p.drawRect(QRectF(8, 4, 8, 5))
    p.drawRect(QRectF(7, 13, 10, 7))


def _pdf(p, c):
    _file(p, c)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(220, 60, 60))
    p.drawRoundedRect(QRectF(2, 12, 15, 8), 2, 2)
    f = QFont()
    f.setBold(True)
    f.setPixelSize(7)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255))
    p.drawText(QRectF(2, 12, 15, 8), Qt.AlignmentFlag.AlignCenter, "PDF")


def _bold(p, c):
    f = QFont()
    f.setBold(True)
    f.setPixelSize(17)
    p.setFont(f)
    p.setPen(c)
    p.drawText(QRectF(2, 2, 20, 20), Qt.AlignmentFlag.AlignCenter, "B")


def _chevron_up(p, c):
    p.setPen(_pen(c, 2))
    p.drawPolyline(_poly((6, 15), (12, 9), (18, 15)))


def _chevron_down(p, c):
    p.setPen(_pen(c, 2))
    p.drawPolyline(_poly((6, 9), (12, 15), (18, 9)))


_ICONS = {
    "brush": _brush, "pencil": _pencil, "pen": _pen_nib, "highlighter": _highlighter,
    "eraser": _eraser, "rect": _rect, "ellipse": _ellipse, "triangle": _triangle,
    "line": _line, "arrow": _arrow, "undo": _undo, "redo": _redo, "trash": _trash,
    "camera": _camera, "folder": _folder, "eye": _eye, "eye_off": _eye_off, "power": _power,
    "mouse": _mouse, "help": _help, "zoom": _zoom, "text": _text, "laser": _laser, "spotlight": _spotlight,
    "curtain": _curtain, "highlight": _highlight, "page_prev": _page_prev, "page_next": _page_next,
    "page_add": _page_add, "file": _file, "save": _save, "pdf": _pdf, "bold": _bold, "chevron_up": _chevron_up, "chevron_down": _chevron_down,
}


def icon_pixmap(name: str, color: str = FG, size: int = 24, scale: int = 3) -> QPixmap:
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(scale)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    _ICONS[name](p, QColor(color))
    p.end()
    return pm


@lru_cache(maxsize=None)
def icon(name: str, color: str = FG) -> QIcon:
    return QIcon(icon_pixmap(name, color))


def app_icon_image(size: int = 256) -> QImage:
    """Icono de la aplicación: pizarra con trazos de colores."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 256.0, size / 256.0)

    grad = QLinearGradient(0, 0, 0, 256)
    grad.setColorAt(0, QColor("#2f6fd1"))
    grad.setColorAt(1, QColor("#1b3f7a"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(8, 8, 240, 240), 48, 48)

    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(36, 44, 184, 140), 14, 14)

    hl = QPen(QColor(255, 220, 0, 170), 26, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
    p.setPen(hl)
    p.drawLine(QPointF(60, 150), QPointF(190, 150))

    red = QPen(QColor("#e53935"), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(red)
    path = QPainterPath()
    path.moveTo(60, 120)
    path.cubicTo(80, 60, 105, 60, 120, 105)
    path.cubicTo(135, 150, 165, 140, 195, 75)
    p.drawPath(path)

    p.setPen(QPen(QColor("#ffffff"), 12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(96, 184), QPointF(80, 224))
    p.drawLine(QPointF(160, 184), QPointF(176, 224))
    p.end()
    return img


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(QPixmap.fromImage(app_icon_image(s)))
    return ic
