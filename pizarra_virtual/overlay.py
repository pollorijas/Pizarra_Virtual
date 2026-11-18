"""Ventana transparente que cubre una pantalla y sobre la que se dibuja.

Se crea una superposición por monitor. Así cada una usa el factor de escala
(DPI) de su propia pantalla y los trazos se ven nítidos aunque los monitores
tengan escalados distintos (100 %, 125 %, 150 %...).

Modo zoom: la superposición muestra una captura congelada de su pantalla
ampliada. Todo lo que se dibuja se guarda en coordenadas reales de la
pantalla, así que al salir del zoom los trazos quedan exactamente sobre el
contenido que se señaló.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor, QCursor, QFont, QImage, QInputDevice, QPainter, QPen, QPixmap, QPointingDevice,
)
from PySide6.QtWidgets import QWidget

from . import render, winutil
from .items import ClearItem, ShapeItem, StrokeItem
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


def _new_image(size: QSize, dpr: float) -> QImage:
    img = QImage(size, _FMT)
    img.setDevicePixelRatio(dpr)
    img.fill(_TRANSPARENT)
    return img


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

        # Elemento en curso
        self._stroke: StrokeItem | None = None
        self._shape: ShapeItem | None = None
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

        # Zoom
        self._zoom_img: QImage | None = None
        self._zoom = 1.0
        self._zoom_tl = QPointF(0, 0)
        self._pan_from: tuple[QPointF, QPointF] | None = None
        self._zoom_hint = False
        self._hint_timer = QTimer(self)
        self._hint_timer.setSingleShot(True)
        self._hint_timer.timeout.connect(self._hide_zoom_hint)

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
            self._clamp_zoom()
            self.rebuild()

    def event(self, ev):
        t = ev.type()
        if t in (QEvent.Type.DevicePixelRatioChange, QEvent.Type.ScreenChangeInternal):
            self._ensure_buffers()
            self.ctrl.refresh_cursor(self)
        return super().event(ev)

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
        """Vuelve a dibujar el lienzo completo a partir del historial."""
        if self.canvas.isNull():
            return
        self.canvas.fill(_TRANSPARENT)
        for item in self.ctrl.items_for(self.key):
            self.apply_item(item, update=False)
        self.update()

    def apply_item(self, item, update: bool = True) -> None:
        if self.canvas.isNull():
            return
        if isinstance(item, ClearItem):
            self.canvas.fill(_TRANSPARENT)
        elif render.is_eraser(item):
            p = self._painter(self.canvas)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            render.draw_item(p, item)
            p.end()
        else:
            self._clear_layer()
            p = self._painter(self.layer)
            render.draw_item(p, item)
            p.end()
            self._layer_rect = render.item_rect(item)
            self._composite_layer(item.opacity)
            self._clear_layer()
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

    def _draw_drawing(self, p: QPainter) -> None:
        p.drawImage(QPointF(0, 0), self.canvas)
        active = self._stroke or self._shape
        if active is not None and not render.is_eraser(active):
            p.save()
            p.setOpacity(active.opacity)
            p.drawImage(QPointF(0, 0), self.layer)
            p.restore()

    def paintEvent(self, ev):  # noqa: N802
        if self.canvas.isNull():
            return
        p = QPainter(self)
        if self.zoom_active:
            self._paint_zoomed(p, QRectF(ev.rect()), True, hint=self._zoom_hint)
        else:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.fillRect(ev.rect(), self.ctrl.background_color(interactive=self.ctrl.drawing))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            self._draw_drawing(p)
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
        if with_drawing:
            self._draw_drawing(p)
        p.restore()
        if hint:
            self._paint_zoom_hint(p)

    def _paint_zoom_hint(self, p: QPainter) -> None:
        text = (f"Zoom {self._zoom:.1f}×   ·   rueda: acercar/alejar   ·   "
                "clic derecho y arrastrar: mover   ·   Esc: salir")
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        p.setFont(f)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text) + 28
        th = fm.height() + 14
        box = QRectF((self.width() - tw) / 2, self.height() - th - 28, tw, th)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 22, 26, 215))
        p.drawRoundedRect(box, 8, 8)
        p.setPen(QColor(255, 255, 255))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

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
        self.finish_current()

    def finish_current(self) -> None:
        """Confirma el trazo o figura en curso y lo añade al historial."""
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
        self._state = None

    def cancel_current(self) -> None:
        """Descarta el elemento en curso (la goma ya aplicada se conserva en el historial)."""
        if self._stroke is not None and self._stroke.tool == Tool.ERASER:
            self.finish_current()
            return
        self._stroke = None
        self._shape = None
        self._state = None
        self._clear_layer()
        self.update()

    @property
    def busy(self) -> bool:
        return self._stroke is not None or self._shape is not None

    # ------------------------------------------------------------------ eventos de entrada

    def mousePressEvent(self, e):  # noqa: N802
        if self._tablet_active:
            return
        btn = e.button()
        if btn == Qt.MouseButton.LeftButton and self._pan_from is None:
            self._begin(self.to_canvas(e.position()), None, e.timestamp())
        elif btn == Qt.MouseButton.RightButton and self.busy:
            self.cancel_current()
        elif btn in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton) and self.zoom_active:
            self._pan_from = (QPointF(e.position()), QPointF(self._zoom_tl))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._tablet_active:
            return
        if self._pan_from is not None:
            start, tl = self._pan_from
            delta = e.position() - start
            self._zoom_tl = QPointF(tl.x() - delta.x() / self._zoom, tl.y() - delta.y() / self._zoom)
            self._clamp_zoom()
            self.update()
        elif e.buttons() & Qt.MouseButton.LeftButton:
            self._move(self.to_canvas(e.position()), None, e.timestamp(), e.modifiers())

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._tablet_active:
            return
        btn = e.button()
        if btn in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton) and self._pan_from is not None:
            self._pan_from = None
            self.ctrl.refresh_cursor(self)
        elif btn == Qt.MouseButton.LeftButton:
            self._release(self.to_canvas(e.position()), None, e.timestamp(), e.modifiers())

    def tabletEvent(self, e):  # noqa: N802
        """Lápiz de tableta / Windows Ink: usa la presión real si el dispositivo la ofrece."""
        dev = e.device()
        has_pressure = bool(dev is not None and dev.capabilities() & QInputDevice.Capability.Pressure)
        pressure = e.pressure() if has_pressure else None
        pos = self.to_canvas(e.position())
        t = e.type()
        if t == QEvent.Type.TabletPress:
            eraser = e.pointerType() == QPointingDevice.PointerType.Eraser
            self._tablet_active = True
            self._begin(pos, pressure, e.timestamp(), eraser=eraser)
        elif t == QEvent.Type.TabletMove:
            if self._tablet_active:
                self._move(pos, pressure, e.timestamp(), e.modifiers())
        elif t == QEvent.Type.TabletRelease:
            if self._tablet_active:
                self._release(pos, pressure, e.timestamp(), e.modifiers())
            self._tablet_active = False
        e.accept()

    def wheelEvent(self, e):  # noqa: N802
        d = e.angleDelta().y() or e.angleDelta().x()
        if not d:
            return
        step = 1 if d > 0 else -1
        mods = e.modifiers()
        if mods & Qt.KeyboardModifier.ShiftModifier:
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
