"""Captura de pantalla y guardado en %USERPROFILE%\\Pictures\\Capturas Pizarra."""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QPointF, QRect, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QScreen

CAPTURES_FOLDER_NAME = "Capturas Pizarra"


def captures_dir() -> str:
    """Carpeta de capturas: %USERPROFILE%\\Pictures\\Capturas Pizarra (la crea si no existe)."""
    base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    path = os.path.join(base, "Pictures", CAPTURES_FOLDER_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def unique_capture_path(folder: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    stem = now.strftime("Pizarra_%Y-%m-%d_%H-%M-%S")
    path = os.path.join(folder, stem + ".png")
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{stem}_{n}.png")
        n += 1
    return path


def grab_screen(screen: QScreen) -> QImage:
    """Imagen de la pantalla completa en píxeles físicos (dpr = 1)."""
    img = screen.grabWindow(0).toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(1.0)
    return img


def compose_drawing(shot: QImage, canvas: QImage | None, background: QColor | None,
                    pattern: QImage | None = None) -> QImage:
    """Pinta el fondo (si lo hay), la pauta y el lienzo encima de la captura, escalando a su tamaño."""
    if shot.isNull():
        return shot
    out = shot.copy()
    target = QRectF(0, 0, out.width(), out.height())
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if background is not None and background.alpha() > 0:
        p.fillRect(target, background)
    if pattern is not None and not pattern.isNull():
        p.drawImage(target, pattern, QRectF(0, 0, pattern.width(), pattern.height()))
    if canvas is not None and not canvas.isNull():
        p.drawImage(target, canvas, QRectF(0, 0, canvas.width(), canvas.height()))
    p.end()
    return out


def stitch(parts: list[tuple[QRect, QImage]]) -> QImage:
    """Une varias pantallas en una sola imagen usando su geometría lógica."""
    if len(parts) == 1:
        return parts[0][1]
    union = QRect()
    scale = 1.0
    for geo, img in parts:
        union = union.united(geo)
        if geo.width() > 0:
            scale = max(scale, img.width() / geo.width())
    out = QImage(round(union.width() * scale), round(union.height() * scale), QImage.Format.Format_RGB32)
    out.fill(QColor(0, 0, 0))
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for geo, img in parts:
        r = QRectF(QPointF((geo.x() - union.x()) * scale, (geo.y() - union.y()) * scale),
                   QPointF((geo.right() + 1 - union.x()) * scale, (geo.bottom() + 1 - union.y()) * scale))
        p.drawImage(r, img, QRectF(0, 0, img.width(), img.height()))
    p.end()
    return out


def save_capture(img: QImage, folder: str | None = None) -> str:
    folder = folder or captures_dir()
    os.makedirs(folder, exist_ok=True)
    path = unique_capture_path(folder)
    if not img.convertToFormat(QImage.Format.Format_RGB32).save(path, "PNG"):
        raise OSError(f"No se pudo guardar la captura en {path}")
    return path


__all__ = ["captures_dir", "unique_capture_path", "grab_screen", "compose_drawing", "stitch",
           "save_capture"]
