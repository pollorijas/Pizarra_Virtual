"""Ventana transparente que cubre una pantalla y sobre la que se dibuja.

Se crea una superposición por monitor. Así cada una usa el factor de escala
(DPI) de su propia pantalla y los trazos se ven nítidos aunque los monitores
tengan escalados distintos (100 %, 125 %, 150 %...).

Modo zoom: la superposición muestra una captura congelada de su pantalla
ampliada. Todo lo que se dibuja se guarda en coordenadas reales de la
pantalla, así que al salir del zoom los trazos quedan exactamente sobre el
contenido que se señaló.

Efectos de presentación (no forman parte del dibujo ni del historial): cortina,
foco, resaltado del cursor y de los clics, y puntero láser con tinta que se
desvanece. Se dibujan en coordenadas de la ventana, encima de todo.
"""
from __future__ import annotations

import math
import random
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor, QCursor, QFont, QGuiApplication, QImage, QInputDevice, QPainter, QPainterPath, QPen, QPixmap,
    QPointingDevice, QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from . import render, winutil
from .items import ShapeItem, StrokeItem, TextItem
from .tools import SHAPE_TOOLS, Tool

if TYPE_CHECKING:  # pragma: no cover
    from .app import Controller

_FMT = QImage.Format.Format_ARGB32_Premultiplied
_TRANSPARENT = Qt.GlobalColor.transparent
_MIN_POINT_DISTANCE = 0.75

ZOOM_DEFAULT = 2.0
ZOOM_MIN = 1.0
ZOOM_MAX = 10.0
ZOOM_STEP = 1.25
_ZOOM_HINT_MS = 2500

# Estabilizador de la pluma: fracción del movimiento que se aplica en cada evento.
_PEN_SMOOTHING_MOUSE = 0.45
_PEN_SMOOTHING_TABLET = 0.65

# Efectos
SPOTLIGHT_DIM = QColor(0, 0, 0, 190)
CURTAIN_COLOR = QColor(30, 32, 38)
CURTAIN_GRAB = 22                 # px alrededor del borde de la cortina para arrastrarla
HALO_RADIUS = 24
RIPPLE_MS = 450
LASER_HOLD_MS = 900               # la tinta del láser permanece este tiempo tras soltar...
LASER_FADE_MS = 700               # ...y luego se desvanece en este tiempo
CARET_BLINK_MS = 530


def now_ms() -> float:
    return time.monotonic() * 1000.0


def _new_image(size: QSize, dpr: float) -> QImage:
    img = QImage(size, _FMT)
    img.setDevicePixelRatio(dpr)
    img.fill(_TRANSPARENT)
    return img


class LaserTrail:
    __slots__ = ("points", "color", "size", "released")

    def __init__(self, pos: QPointF, color: QColor, size: float):
        self.points = [QPointF(pos)]
        self.color = QColor(color)
        self.size = size
        self.released: float | None = None

    def alpha(self, now: float) -> float:
        if self.released is None:
            return 1.0
        age = now - self.released - LASER_HOLD_MS
        return 1.0 if age <= 0 else max(0.0, 1.0 - age / LASER_FADE_MS)

    def rect(self) -> QRectF:
        xs = [p.x() for p in self.points]
        ys = [p.y() for p in self.points]
        m = self.size * 2 + 4
        return QRectF(min(xs) - m, min(ys) - m, max(xs) - min(xs) + 2 * m, max(ys) - min(ys) + 2 * m)


class Overlay(QWidget):
    def __init__(self, ctrl: "Controller", screen, key: str):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
            # No roba el foco: la barra de herramientas sigue activa y recibe el teclado,
            # y la superposición nunca se coloca por encima de ella.
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        super().__init__(None, flags)
        self.ctrl = ctrl
        self.key = key
        self._screen = screen
        self.setWindowTitle("Pizarra Virtual - lienzo")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.canvas = QImage()
        self.layer = QImage()
        self._dpr = 0.0
        self._layer_rect = QRectF()
        self._pattern_img: QImage | None = None
        self._pattern_key = None

        # Elemento en curso
        self._stroke: StrokeItem | None = None
        self._shape: ShapeItem | None = None
        self._text: TextItem | None = None
        self._state: render.StrokeState | None = None
        self._tablet_active = False
        self._last_pos = QPointF()
        self._last_t = 0
        # Estado de la pluma
        self._smooth = QPointF()
        self._speed_f = 1.0
        self._dir_f = 0.85
        self._press = 0.5
        self._travel = 0.0

        # Texto: cursor parpadeante
        self._caret_on = True
        self._caret_timer = QTimer(self)
        self._caret_timer.setInterval(CARET_BLINK_MS)
        self._caret_timer.timeout.connect(self._blink_caret)

        # Zoom
        self._zoom_img: QImage | None = None
        self._zoom = 1.0
        self._zoom_tl = QPointF(0, 0)
        self._pan_from: tuple[QPointF, QPointF] | None = None
        self._zoom_hint = False
        self._hint_timer = QTimer(self)
        self._hint_timer.setSingleShot(True)
        self._hint_timer.timeout.connect(self._hide_zoom_hint)

        # Efectos de presentación
        self.curtain_y: float | None = None
        self._curtain_drag: float | None = None  # desplazamiento entre el ratón y el borde
        self._cursor_view: QPointF | None = None
        self._ripples: list[tuple[QPointF, float, QColor]] = []
        self._laser: LaserTrail | None = None
        self._trails: list[LaserTrail] = []

        self.winId()  # crea la ventana nativa para poder asignarle la pantalla
        if self.windowHandle() is not None:
            self.windowHandle().setScreen(screen)
        self.sync_geometry()
        screen.geometryChanged.connect(self.sync_geometry)

    # ------------------------------------------------------------------ geometría / DPI

    @property
    def screen_ref(self):
        return self._screen

    def sync_geometry(self, *_):
        self.setGeometry(self._screen.geometry())
        self._ensure_buffers()

    def _ensure_buffers(self) -> None:
        dpr = self.devicePixelRatioF() or 1.0
        need = QSize(max(1, math.ceil(self.width() * dpr)), max(1, math.ceil(self.height() * dpr)))
        if self.canvas.isNull() or self.canvas.size() != need or abs(self._dpr - dpr) > 1e-6:
            self.cancel_current()
            self._dpr = dpr
            self.canvas = _new_image(need, dpr)
            self.layer = _new_image(need, dpr)
            self._layer_rect = QRectF()
            self._pattern_key = None
            self._clamp_zoom()
            self.rebuild()

    def event(self, ev):
        t = ev.type()
        if t in (QEvent.Type.DevicePixelRatioChange, QEvent.Type.ScreenChangeInternal):
            self._ensure_buffers()
            self.ctrl.refresh_cursor(self)
        return super().event(ev)

    def closeEvent(self, ev):  # noqa: N802
        """Alt+F4 sobre esta ventana cierra todo el programa, nunca solo esta ventana."""
        if self.ctrl.shutting_down:
            super().closeEvent(ev)
            return
        ev.ignore()
        self.ctrl.request_close()

    def resizeEvent(self, ev):  # noqa: N802
        self._ensure_buffers()
        super().resizeEvent(ev)

    def showEvent(self, ev):  # noqa: N802
        super().showEvent(ev)
        self._ensure_buffers()
        self.apply_input_mode()

    # ------------------------------------------------------------------ modo de entrada

    def apply_input_mode(self) -> None:
        """Modo dibujo: captura el ratón. Modo ratón libre: los clics atraviesan la ventana."""
        passthrough = not self.ctrl.drawing
        wh = self.windowHandle()
        if wh is not None:
            current = bool(wh.flags() & Qt.WindowType.WindowTransparentForInput)
            if current != passthrough:
                wh.setFlag(Qt.WindowType.WindowTransparentForInput, passthrough)
        if winutil.IS_WINDOWS:
            winutil.set_click_through(int(self.winId()), passthrough)
        if passthrough:
            self.finish_current()
            self.end_zoom()
        self.ctrl.refresh_cursor(self)
        self.update()

    # ------------------------------------------------------------------ zoom

    @property
    def zoom_active(self) -> bool:
        return self._zoom_img is not None

    @property
    def zoom_factor(self) -> float:
        return self._zoom if self.zoom_active else 1.0

    def start_zoom(self, screenshot: QImage, anchor: QPointF, factor: float = ZOOM_DEFAULT) -> None:
        """Muestra ``screenshot`` (la pantalla sin la pizarra) ampliada alrededor de ``anchor``."""
        self.finish_current()
        self._zoom_img = screenshot
        self._zoom = 1.0
        self._zoom_tl = QPointF(0, 0)
        self.set_zoom(factor, anchor)

    def end_zoom(self) -> None:
        if not self.zoom_active:
            return
        self.finish_current()
        self._zoom_img = None
        self._zoom = 1.0
        self._zoom_tl = QPointF(0, 0)
        self._pan_from = None
        self._zoom_hint = False
        self._hint_timer.stop()
        self.ctrl.refresh_cursor(self)
        self.update()

    def set_zoom(self, factor: float, anchor: QPointF) -> None:
        """Cambia el aumento manteniendo fijo el punto de la pantalla que hay bajo ``anchor``."""
        if not self.zoom_active:
            return
        target = self.to_canvas(anchor)
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, factor))
        self._zoom_tl = QPointF(target.x() - anchor.x() / self._zoom, target.y() - anchor.y() / self._zoom)
        self._clamp_zoom()
        self._show_zoom_hint()
        self.ctrl.refresh_cursor(self)
        self.ctrl.zoom_changed(self)
        self.update()

    def _clamp_zoom(self) -> None:
        if not self.zoom_active:
            return
        max_x = max(0.0, self.width() - self.width() / self._zoom)
        max_y = max(0.0, self.height() - self.height() / self._zoom)
        self._zoom_tl = QPointF(min(max(self._zoom_tl.x(), 0.0), max_x), min(max(self._zoom_tl.y(), 0.0), max_y))

    def _show_zoom_hint(self) -> None:
        self._zoom_hint = True
        self._hint_timer.start(_ZOOM_HINT_MS)

    def _hide_zoom_hint(self) -> None:
        self._zoom_hint = False
        self.update()

    def to_canvas(self, pos: QPointF) -> QPointF:
        """Coordenadas de la ventana → coordenadas reales de la pantalla (lienzo)."""
        if not self.zoom_active:
            return QPointF(pos)
        return QPointF(self._zoom_tl.x() + pos.x() / self._zoom, self._zoom_tl.y() + pos.y() / self._zoom)

    def _view_rect(self, rect: QRectF) -> QRect:
        """Rectángulo del lienzo → rectángulo de la ventana (para repintar solo lo necesario)."""
        if not self.zoom_active:
            return rect.toAlignedRect()
        z = self._zoom
        r = QRectF((rect.x() - self._zoom_tl.x()) * z, (rect.y() - self._zoom_tl.y()) * z,
                   rect.width() * z, rect.height() * z)
        return r.toAlignedRect().adjusted(-2, -2, 2, 2)

    def render_view(self, with_drawing: bool = True) -> QImage:
        """Imagen (píxeles físicos, dpr 1) de lo que se ve en modo zoom; se usa para las capturas."""
        img = _new_image(self.canvas.size(), self._dpr or 1.0)
        p = QPainter(img)
        self._paint_zoomed(p, QRectF(0, 0, self.width(), self.height()), with_drawing, hint=False)
        p.end()
        img.setDevicePixelRatio(1.0)
        return img

    # ------------------------------------------------------------------ historial

    def rebuild(self) -> None:
        """Vuelve a dibujar el lienzo completo a partir del historial de la página actual."""
        if self.canvas.isNull():
            return
        self.canvas.fill(_TRANSPARENT)
        self._clear_layer()
        for item in self.ctrl.items_for(self.key):
            render.apply_item_to_canvas(self.canvas, self.layer, item)
        self.update()

    def apply_item(self, item, update: bool = True) -> None:
        if self.canvas.isNull():
            return
        self._clear_layer()
        render.apply_item_to_canvas(self.canvas, self.layer, item)
        if update:
            self.update()

    # ------------------------------------------------------------------ pintado

    @staticmethod
    def _painter(img: QImage) -> QPainter:
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        return p

    def _clear_layer(self) -> None:
        if self._layer_rect.isEmpty() or self.layer.isNull():
            self._layer_rect = QRectF()
            return
        p = QPainter(self.layer)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(self._layer_rect.adjusted(-2, -2, 2, 2), _TRANSPARENT)
        p.end()
        self._layer_rect = QRectF()

    def _composite_layer(self, opacity: float) -> None:
        if self._layer_rect.isEmpty():
            return
        p = QPainter(self.canvas)
        p.setClipRect(self._layer_rect.adjusted(-2, -2, 2, 2))
        p.setOpacity(max(0.0, min(1.0, opacity)))
        p.drawImage(QPointF(0, 0), self.layer)
        p.end()

    def pattern_image(self) -> QImage | None:
        """Pauta de la página actual, en caché (se regenera al cambiar de pauta, fondo o tamaño)."""
        pattern, bg = self.ctrl.pattern, self.ctrl.background
        if pattern == "none" or self.canvas.isNull():
            return None
        key = (pattern, bg, self.canvas.size().toTuple(), self._dpr)
        if key != self._pattern_key:
            img = _new_image(self.canvas.size(), self._dpr)
            p = QPainter(img)
            render.draw_pattern(p, self.width(), self.height(), pattern, bg)
            p.end()
            self._pattern_img = img
            self._pattern_key = key
        return self._pattern_img

    def _draw_drawing(self, p: QPainter) -> None:
        p.drawImage(QPointF(0, 0), self.canvas)
        active = self._stroke or self._shape or self._text
        if active is not None and not render.is_eraser(active):
            p.save()
            p.setOpacity(active.opacity)
            p.drawImage(QPointF(0, 0), self.layer)
            p.restore()
        if self._text is not None and self._caret_on:
            a, b = render.text_caret(self._text)
            p.setPen(QPen(QColor(*self._text.rgba), max(1.5, self._text.size / 18)))
            p.drawLine(a, b)

    def paintEvent(self, ev):  # noqa: N802
        if self.canvas.isNull():
            return
        p = QPainter(self)
        if self.zoom_active:
            self._paint_zoomed(p, QRectF(ev.rect()), True, hint=False)
        else:
            # En «Ratón libre» la hoja (fondo y pauta) se aparta para poder usar el equipo:
            # solo quedan los trazos encima del escritorio. Vuelve al pasar a «Dibujando».
            sheet = self.ctrl.sheet_visible
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(ev.rect(), self.ctrl.background_color(interactive=True) if sheet else QColor(0, 0, 0, 0))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pattern = self.pattern_image() if sheet else None
            if pattern is not None:
                p.drawImage(QPointF(0, 0), pattern)
            self._draw_drawing(p)
        self._paint_effects(p, ev.rect())
        if self.zoom_active and self._zoom_hint:
            self._paint_zoom_hint(p)
        p.end()

    def _paint_zoomed(self, p: QPainter, rect: QRectF, with_drawing: bool, hint: bool) -> None:
        w, h = float(self.width()), float(self.height())
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(rect, QColor(0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.save()
        p.scale(self._zoom, self._zoom)
        p.translate(-self._zoom_tl.x(), -self._zoom_tl.y())
        img = self._zoom_img
        p.drawImage(QRectF(0, 0, w, h), img, QRectF(0, 0, img.width(), img.height()))
        bg = self.ctrl.background_color(interactive=False)
        if bg.alpha() > 0:
            p.fillRect(QRectF(0, 0, w, h), bg)
        pattern = self.pattern_image()
        if pattern is not None:
            p.drawImage(QPointF(0, 0), pattern)
        if with_drawing:
            self._draw_drawing(p)
        p.restore()
        if hint:
            self._paint_zoom_hint(p)

    def _paint_zoom_hint(self, p: QPainter) -> None:
        text = (f"Zoom {self._zoom:.1f}×   ·   rueda: acercar/alejar   ·   "
                "clic derecho y arrastrar: mover   ·   Esc: salir")
        self._paint_banner(p, text)

    def _paint_banner(self, p: QPainter, text: str, y_from_bottom: float = 28) -> None:
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        p.save()
        p.setFont(f)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text) + 28
        th = fm.height() + 14
        box = QRectF((self.width() - tw) / 2, self.height() - th - y_from_bottom, tw, th)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 22, 26, 215))
        p.drawRoundedRect(box, 8, 8)
        p.setPen(QColor(255, 255, 255))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        p.restore()

    # ------------------------------------------------------------------ efectos de presentación

    def _paint_effects(self, p: QPainter, rect: QRect) -> None:
        c = self.ctrl
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.curtain_y is not None:
            self._paint_curtain(p)
        if c.spotlight:
            if self._cursor_view is not None:
                r = float(c.spotlight_radius)
                g = QRadialGradient(self._cursor_view, r)
                g.setColorAt(0.0, QColor(0, 0, 0, 0))
                g.setColorAt(max(0.0, (r - 18) / r), QColor(0, 0, 0, 0))
                g.setColorAt(1.0, SPOTLIGHT_DIM)
                p.fillRect(rect, g)  # fuera del radio el degradado se extiende con el color oscuro
            else:
                p.fillRect(rect, SPOTLIGHT_DIM)
        now = now_ms()
        for trail in [*self._trails, *([self._laser] if self._laser else [])]:
            self._paint_trail(p, trail, trail.alpha(now))
        if c.tool == Tool.LASER and c.drawing and self._cursor_view is not None:
            self._paint_laser_dot(p, self._cursor_view, float(c.size_for(Tool.LASER)), c.color)
        if c.highlight and self._cursor_view is not None:
            p.setPen(QPen(QColor(255, 186, 0, 220), 2.0))
            p.setBrush(QColor(255, 225, 0, 85))
            p.drawEllipse(self._cursor_view, HALO_RADIUS, HALO_RADIUS)
        for pos, t0, color in self._ripples:
            f = min(1.0, (now - t0) / RIPPLE_MS)
            col = QColor(color)
            col.setAlphaF(0.9 * (1 - f))
            p.setPen(QPen(col, 3.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            radius = 8 + 30 * f
            p.drawEllipse(pos, radius, radius)
        p.restore()

    def _paint_curtain(self, p: QPainter) -> None:
        w, h = float(self.width()), float(self.height())
        y = max(0.0, min(h, self.curtain_y))
        p.fillRect(QRectF(0, y, w, h - y), CURTAIN_COLOR)
        p.fillRect(QRectF(0, y, w, 3), QColor(80, 140, 230))
        if h - y > 40:
            pill = QRectF(w / 2 - 70, y + 8, 140, 24)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(70, 74, 84))
            p.drawRoundedRect(pill, 12, 12)
            p.setPen(QColor(220, 223, 228))
            f = QFont(self.font())
            f.setPointSizeF(9.5)
            p.setFont(f)
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, "▼ arrastra o ↓ ↑ ▲")

    @staticmethod
    def _paint_laser_dot(p: QPainter, pos: QPointF, size: float, color: QColor) -> None:
        g = QRadialGradient(pos, size * 1.6)
        core = QColor(color)
        glow = QColor(color)
        glow.setAlpha(110)
        edge = QColor(color)
        edge.setAlpha(0)
        g.setColorAt(0.0, QColor(255, 255, 255))
        g.setColorAt(0.22, core)
        g.setColorAt(0.5, glow)
        g.setColorAt(1.0, edge)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(pos, size * 1.6, size * 1.6)

    @staticmethod
    def _paint_trail(p: QPainter, trail: LaserTrail, alpha: float) -> None:
        if alpha <= 0 or not trail.points:
            return
        path = QPainterPath(trail.points[0])
        for pt in trail.points[1:]:
            path.lineTo(pt)
        if len(trail.points) == 1:
            path.lineTo(trail.points[0] + QPointF(0.01, 0))
        glow = QColor(trail.color)
        glow.setAlphaF(0.30 * alpha)
        core = QColor(trail.color).lighter(130)
        core.setAlphaF(alpha)
        for col, width in ((glow, trail.size * 1.6), (core, max(2.0, trail.size * 0.45))):
            p.setPen(QPen(col, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

    def _effect_rect(self, pos: QPointF | None) -> QRect:
        if pos is None:
            return QRect()
        c = self.ctrl
        r = HALO_RADIUS + 4
        if c.spotlight:
            r = max(r, c.spotlight_radius + 4)
        if c.tool == Tool.LASER:
            r = max(r, c.size_for(Tool.LASER) * 1.6 + 4)
        return QRectF(pos.x() - r, pos.y() - r, 2 * r, 2 * r).toAlignedRect()

    def effects_tick(self, now: float, gpos: QPoint, clicks: list[str]) -> bool:
        """Llamado ~60 veces por segundo mientras haya efectos. Devuelve True si sigue animando."""
        local = QPointF(self.mapFromGlobal(gpos))
        inside = self.rect().contains(local.toPoint())
        new = local if inside else None
        old = self._cursor_view
        moved = (old is None) != (new is None) or (old is not None and new is not None and old != new)
        if moved:
            self._cursor_view = new
            if self.ctrl.spotlight and ((old is None) != (new is None)):
                self.update()  # entra o sale de esta pantalla: cambia toda la oscuridad
            else:
                self.update(self._effect_rect(old).united(self._effect_rect(new)))
        if self.ctrl.highlight and inside:
            for kind in clicks:
                color = QColor(230, 50, 50) if kind == "left" else QColor(50, 120, 240)
                self._ripples.append((QPointF(local), now, color))
        for pos, t0, _ in self._ripples:
            self.update(QRectF(pos.x() - 42, pos.y() - 42, 84, 84).toAlignedRect())
        self._ripples = [r for r in self._ripples if now - r[1] < RIPPLE_MS]
        alive = []
        for trail in self._trails:
            self.update(trail.rect().toAlignedRect())
            if trail.alpha(now) > 0:
                alive.append(trail)
        self._trails = alive
        return bool(self._ripples or self._trails or self._laser)

    def clear_ripples(self) -> None:
        self._ripples.clear()
        self.update()

    # ------------------------------------------------------------------ cortina

    def set_curtain(self, y: float | None) -> None:
        self.curtain_y = None if y is None else max(0.0, min(float(self.height()), y))
        self.update()

    def _curtain_hit(self, pos: QPointF) -> bool:
        return self.curtain_y is not None and pos.y() >= self.curtain_y - CURTAIN_GRAB

    # ------------------------------------------------------------------ dibujo

    def _begin(self, pos: QPointF, pressure: float | None, t: int, eraser: bool = False) -> None:
        if not self.ctrl.drawing:
            return
        self.finish_current()
        c = self.ctrl
        tool = Tool.ERASER if eraser else c.tool
        size = float(c.size_for(tool))
        opacity = c.opacity_for(tool) / 100.0
        rgba = c.color.getRgb()
        if tool in SHAPE_TOOLS:
            self._shape = ShapeItem(tool, rgba, size, opacity, pos.x(), pos.y(), pos.x(), pos.y(),
                                    filled=c.fill_shapes)
            return
        if tool == Tool.TEXT:
            fm_height = size * 1.33
            self._text = TextItem(rgba, size, opacity, pos.x(), pos.y() - fm_height / 2, "", c.text_bold)
            self._caret_on = True
            self._caret_timer.start()
            self._render_text_preview()
            c.begin_text_edit(self)
            return
        seed = random.getrandbits(31)
        self._stroke = StrokeItem(tool, rgba, size, opacity, c.brush_type, seed)
        self._state = render.StrokeState(seed)
        self._last_pos = QPointF(pos)
        self._last_t = t
        self._smooth = QPointF(pos)
        self._speed_f = 1.0
        self._dir_f = 0.85
        self._press = pressure if pressure is not None else 0.5
        self._travel = 0.0
        self._add_point(pos, pressure, t, force=True)

    def _pen_width(self, pos: QPointF, pressure: float | None, t: int) -> float:
        """Grosor de la pluma: presión real o velocidad, dirección del plumín y afinado inicial."""
        size = self._stroke.size
        dx, dy = pos.x() - self._last_pos.x(), pos.y() - self._last_pos.y()
        d = math.hypot(dx, dy)
        self._travel += d
        if d > 0.2:
            theta = math.atan2(dy, dx)
            target = (1.0 - render.PEN_DIRECTION_RANGE) + render.PEN_DIRECTION_RANGE * abs(
                math.sin(theta - render.PEN_NIB_ANGLE))
            self._dir_f += (target - self._dir_f) * 0.25
        if pressure is not None:
            self._press += (max(0.0, min(1.0, pressure)) - self._press) * 0.5
            f = 0.2 + 0.8 * self._press ** 0.8
        else:
            # Sin sensor de presión se simula con la velocidad (en píxeles de la vista):
            # despacio = trazo pleno, rápido = trazo más fino. Cambia de forma gradual.
            dt = max(1, t - self._last_t)
            v = d * self.zoom_factor / dt  # px/ms
            target = 1.0 - 0.45 * min(1.0, v / 2.5)
            self._speed_f += (target - self._speed_f) * 0.2
            f = self._speed_f
        taper = 0.35 + 0.65 * min(1.0, self._travel / render.pen_taper_length(size))
        return max(0.5, size * f * self._dir_f * taper)

    def _width_for(self, pos: QPointF, pressure: float | None, t: int) -> float:
        item = self._stroke
        if item.tool == Tool.PEN:
            return self._pen_width(pos, pressure, t)
        if pressure is not None and item.tool in (Tool.BRUSH, Tool.PENCIL, Tool.HIGHLIGHTER):
            return max(0.5, item.size * (0.35 + 0.65 * max(0.0, min(1.0, pressure))))
        return item.size

    def _add_point(self, pos: QPointF, pressure: float | None, t: int, force: bool = False) -> None:
        item = self._stroke
        pts = item.points
        min_d = _MIN_POINT_DISTANCE / self.zoom_factor
        if not force and pts and math.hypot(pos.x() - pts[-1][0], pos.y() - pts[-1][1]) < min_d:
            return
        w = self._width_for(pos, pressure, t)
        pts.append((pos.x(), pos.y(), w))
        i = len(pts) - 1
        rect = render.segment_rect(item, i)
        if item.tool == Tool.ERASER:
            p = self._painter(self.canvas)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        else:
            p = self._painter(self.layer)
            self._layer_rect = self._layer_rect.united(rect)
        render.draw_segment(p, item, i, self._state)
        p.end()
        self._last_pos = QPointF(pos)
        self._last_t = t
        self.update(self._view_rect(rect))

    def _move(self, pos: QPointF, pressure: float | None, t: int, modifiers) -> None:
        if self._stroke is not None:
            if self._stroke.tool == Tool.PEN:
                # Estabilizador: suaviza el temblor del ratón/lápiz sin perder precisión.
                k = _PEN_SMOOTHING_TABLET if pressure is not None else _PEN_SMOOTHING_MOUSE
                self._smooth = QPointF(self._smooth.x() + (pos.x() - self._smooth.x()) * k,
                                       self._smooth.y() + (pos.y() - self._smooth.y()) * k)
                pos = self._smooth
            self._add_point(pos, pressure, t)
        elif self._shape is not None:
            sh = self._shape
            old = render.shape_rect(sh)
            x2, y2 = pos.x(), pos.y()
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                x2, y2 = render.constrain_shape(sh.tool, sh.x1, sh.y1, x2, y2)
            sh.x2, sh.y2 = x2, y2
            self._clear_layer()
            p = self._painter(self.layer)
            render.draw_shape(p, sh)
            p.end()
            new = render.shape_rect(sh)
            self._layer_rect = new
            self.update(self._view_rect(old.united(new)))

    def _release(self, pos: QPointF, pressure: float | None, t: int, modifiers) -> None:
        if self._shape is not None:
            self._move(pos, pressure, t, modifiers)
        elif self._stroke is not None and self._stroke.tool == Tool.PEN:
            # El trazo termina exactamente donde se levantó la pluma.
            last = self._stroke.points[-1]
            if math.hypot(pos.x() - last[0], pos.y() - last[1]) >= 0.5:
                self._add_point(pos, pressure, t, force=True)
        if self._text is None:  # el texto sigue en edición tras soltar el clic
            self.finish_current()

    def finish_current(self) -> None:
        """Confirma el trazo, figura o texto en curso y lo añade al historial."""
        if self._stroke is not None:
            item = self._stroke
            self._stroke = None
            if item.tool == Tool.PEN:
                # Afinado final + re-render completo como un único contorno limpio.
                render.finalize_pen(item)
                self._clear_layer()
                p = self._painter(self.layer)
                render.draw_stroke(p, item)
                p.end()
                self._layer_rect = render.stroke_rect(item)
            if item.tool != Tool.ERASER:
                self._composite_layer(item.opacity)
                self._clear_layer()
            self.ctrl.push(self.key, item)
            self.update()
        elif self._shape is not None:
            sh = self._shape
            self._shape = None
            self._clear_layer()
            if math.hypot(sh.x2 - sh.x1, sh.y2 - sh.y1) >= 2 / self.zoom_factor:
                self.apply_item(sh, update=False)
                self.ctrl.push(self.key, sh)
            self.update()
        elif self._text is not None:
            item = self._text
            self._text = None
            self._caret_timer.stop()
            self._clear_layer()
            if item.text.strip():
                self.apply_item(item, update=False)
                self.ctrl.push(self.key, item)
            self.update()
            self.ctrl.end_text_edit(self)
        self._state = None

    def cancel_current(self) -> None:
        """Descarta el elemento en curso (la goma ya aplicada se conserva en el historial)."""
        if self._stroke is not None and self._stroke.tool == Tool.ERASER:
            self.finish_current()
            return
        editing_text = self._text is not None
        self._stroke = None
        self._shape = None
        self._text = None
        self._caret_timer.stop()
        self._state = None
        self._clear_layer()
        self.update()
        if editing_text:
            self.ctrl.end_text_edit(self)

    @property
    def busy(self) -> bool:
        return self._stroke is not None or self._shape is not None or self._text is not None

    # ------------------------------------------------------------------ texto

    @property
    def editing_text(self) -> TextItem | None:
        return self._text

    def _render_text_preview(self) -> None:
        if self._text is None:
            return
        old = QRectF(self._layer_rect)
        self._clear_layer()
        p = self._painter(self.layer)
        render.draw_text(p, self._text)
        p.end()
        self._layer_rect = render.item_rect(self._text)
        self.update(self._view_rect(old.united(self._layer_rect)))

    def _blink_caret(self) -> None:
        self._caret_on = not self._caret_on
        if self._text is not None:
            self.update(self._view_rect(render.item_rect(self._text)))

    def restyle_text(self, rgba, size: float, bold: bool) -> None:
        """Aplica color, tamaño y negrita al texto que se está escribiendo."""
        if self._text is None:
            return
        self._text.rgba, self._text.size, self._text.bold = rgba, size, bold
        self._render_text_preview()

    def text_key(self, ev) -> None:
        """Teclas mientras se escribe un texto (las envía el controlador)."""
        item = self._text
        if item is None:
            return
        key, mods = ev.key(), ev.modifiers()
        ctrl_down = bool(mods & Qt.KeyboardModifier.ControlModifier)
        if key == Qt.Key.Key_Escape or (ctrl_down and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self.finish_current()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item.text += "\n"
        elif key == Qt.Key.Key_Backspace:
            item.text = item.text[:-1]
        elif key == Qt.Key.Key_Tab:
            item.text += "    "
        elif ctrl_down and key == Qt.Key.Key_V:
            pasted = QGuiApplication.clipboard().text().replace("\r\n", "\n").replace("\r", "\n")
            item.text += "".join(ch for ch in pasted if ch == "\n" or ch.isprintable())
        else:
            txt = ev.text()
            if not txt or ctrl_down or not txt.isprintable():
                return
            item.text += txt
        self._caret_on = True
        self._render_text_preview()

    # ------------------------------------------------------------------ láser

    def _laser_press(self, view_pos: QPointF) -> None:
        c = self.ctrl
        self._laser = LaserTrail(view_pos, c.color, float(c.size_for(Tool.LASER)))
        self.update(self._laser.rect().toAlignedRect())
        c.ensure_ticking()

    def _laser_move(self, view_pos: QPointF) -> None:
        trail = self._laser
        if trail is None:
            return
        last = trail.points[-1]
        if math.hypot(view_pos.x() - last.x(), view_pos.y() - last.y()) >= 1.0:
            old = trail.rect()
            trail.points.append(QPointF(view_pos))
            self.update(old.united(trail.rect()).toAlignedRect())

    def _laser_release(self) -> None:
        if self._laser is not None:
            self._laser.released = now_ms()
            self._trails.append(self._laser)
            self._laser = None
            self.ctrl.ensure_ticking()

    # ------------------------------------------------------------------ eventos de entrada

    def mousePressEvent(self, e):  # noqa: N802
        if self._tablet_active:
            return
        btn = e.button()
        view = e.position()
        if btn == Qt.MouseButton.LeftButton and self._curtain_hit(view) and not self.busy:
            self._curtain_drag = self.curtain_y - view.y()
            return
        if btn == Qt.MouseButton.LeftButton and self.ctrl.tool == Tool.LASER and self.ctrl.drawing:
            self._laser_press(view)
            return
        if btn == Qt.MouseButton.LeftButton and self._pan_from is None:
            self._begin(self.to_canvas(view), None, e.timestamp())
        elif btn == Qt.MouseButton.RightButton and self.busy:
            self.cancel_current()
        elif btn in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton) and self.zoom_active:
            self._pan_from = (QPointF(view), QPointF(self._zoom_tl))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._tablet_active:
            return
        view = e.position()
        if self._curtain_drag is not None:
            self.set_curtain(view.y() + self._curtain_drag)
        elif self._laser is not None:
            self._laser_move(view)
        elif self._pan_from is not None:
            start, tl = self._pan_from
            delta = view - start
            self._zoom_tl = QPointF(tl.x() - delta.x() / self._zoom, tl.y() - delta.y() / self._zoom)
            self._clamp_zoom()
            self.update()
        elif e.buttons() & Qt.MouseButton.LeftButton:
            self._move(self.to_canvas(view), None, e.timestamp(), e.modifiers())

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._tablet_active:
            return
        btn = e.button()
        if btn == Qt.MouseButton.LeftButton and self._curtain_drag is not None:
            self._curtain_drag = None
        elif btn == Qt.MouseButton.LeftButton and self._laser is not None:
            self._laser_release()
        elif btn in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton) and self._pan_from is not None:
            self._pan_from = None
            self.ctrl.refresh_cursor(self)
        elif btn == Qt.MouseButton.LeftButton:
            self._release(self.to_canvas(e.position()), None, e.timestamp(), e.modifiers())

    def tabletEvent(self, e):  # noqa: N802
        """Lápiz de tableta / Windows Ink: usa la presión real si el dispositivo la ofrece."""
        dev = e.device()
        has_pressure = bool(dev is not None and dev.capabilities() & QInputDevice.Capability.Pressure)
        pressure = e.pressure() if has_pressure else None
        view = e.position()
        pos = self.to_canvas(view)
        t = e.type()
        laser = self.ctrl.tool == Tool.LASER and self.ctrl.drawing
        if t == QEvent.Type.TabletPress:
            eraser = e.pointerType() == QPointingDevice.PointerType.Eraser
            self._tablet_active = True
            if self._curtain_hit(view) and not self.busy:
                self._curtain_drag = self.curtain_y - view.y()
            elif laser and not eraser:
                self._laser_press(view)
            else:
                self._begin(pos, pressure, e.timestamp(), eraser=eraser)
        elif t == QEvent.Type.TabletMove:
            if self._tablet_active:
                if self._curtain_drag is not None:
                    self.set_curtain(view.y() + self._curtain_drag)
                elif self._laser is not None:
                    self._laser_move(view)
                else:
                    self._move(pos, pressure, e.timestamp(), e.modifiers())
        elif t == QEvent.Type.TabletRelease:
            if self._tablet_active:
                if self._curtain_drag is not None:
                    self._curtain_drag = None
                elif self._laser is not None:
                    self._laser_release()
                else:
                    self._release(pos, pressure, e.timestamp(), e.modifiers())
            self._tablet_active = False
        e.accept()

    def wheelEvent(self, e):  # noqa: N802
        d = e.angleDelta().y() or e.angleDelta().x()
        if not d:
            return
        step = 1 if d > 0 else -1
        mods = e.modifiers()
        if mods & Qt.KeyboardModifier.AltModifier and self.ctrl.spotlight:
            self.ctrl.step_spotlight(step)
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            self.ctrl.step_opacity(step)
        elif self.zoom_active and not mods & Qt.KeyboardModifier.ControlModifier:
            if not self.busy:
                self.set_zoom(self._zoom * (ZOOM_STEP if step > 0 else 1 / ZOOM_STEP), e.position())
        else:
            self.ctrl.step_size(step)
        e.accept()


# ---------------------------------------------------------------------- cursores


def make_tool_cursor(tool: Tool, size: float, dpr: float) -> QCursor:
    """Cursor que muestra el tamaño real del pincel / goma (``size`` ya en píxeles de la vista)."""
    if tool in SHAPE_TOOLS:
        return QCursor(Qt.CursorShape.CrossCursor)
    if tool == Tool.TEXT:
        return QCursor(Qt.CursorShape.IBeamCursor)
    if tool == Tool.LASER:
        return QCursor(Qt.CursorShape.BlankCursor)  # el punto láser lo dibuja la pizarra
    d = max(4.0, min(float(size), 180.0))
    side = int(math.ceil(d + 6))
    if tool in (Tool.PEN, Tool.PENCIL):
        side = max(side, 21)  # cruz de precisión visible aunque el trazo sea fino
    if side % 2 == 0:
        side += 1
    pm = QPixmap(max(1, int(math.ceil(side * dpr))), max(1, int(math.ceil(side * dpr))))
    pm.setDevicePixelRatio(dpr)
    pm.fill(_TRANSPARENT)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = side / 2.0
    if tool == Tool.HIGHLIGHTER:
        hw = max(2.0, d * render.HIGHLIGHTER_RATIO)
        rect = QRectF(c - hw / 2, c - d / 2, hw, d)
    else:
        rect = QRectF(c - d / 2, c - d / 2, d, d)
    for color, width in ((QColor(255, 255, 255, 230), 3.0), (QColor(0, 0, 0, 230), 1.2)):
        p.setPen(QPen(color, width))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if tool == Tool.HIGHLIGHTER:
            p.drawRect(rect)
        else:
            p.drawEllipse(rect)
        if tool in (Tool.PEN, Tool.PENCIL):
            gap = d / 2 + 2
            for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p.drawLine(QPointF(c + sx * gap, c + sy * gap), QPointF(c + sx * (c - 1), c + sy * (c - 1)))
    # punto central para precisión
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 200))
    p.drawEllipse(QPointF(c, c), 1.0, 1.0)
    p.end()
    return QCursor(pm, int(c), int(c))
