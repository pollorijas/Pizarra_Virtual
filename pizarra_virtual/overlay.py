"""Ventana transparente que cubre una pantalla y sobre la que se dibuja.

Se crea una superposición por monitor. Así cada una usa el factor de escala
(DPI) de su propia pantalla y los trazos se ven nítidos aunque los monitores
tengan escalados distintos (100 %, 125 %, 150 %...).
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QCursor, QImage, QInputDevice, QPainter, QPen, QPixmap, QPointingDevice
from PySide6.QtWidgets import QWidget

from . import render, winutil
from .items import ClearItem, ShapeItem, StrokeItem
from .tools import SHAPE_TOOLS, Tool

if TYPE_CHECKING:  # pragma: no cover
    from .app import Controller

_FMT = QImage.Format.Format_ARGB32_Premultiplied
_TRANSPARENT = Qt.GlobalColor.transparent
_MIN_POINT_DISTANCE = 0.75


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
        self._pressure_mode = False
        self._tablet_active = False
        self._last_pos = QPointF()
        self._last_t = 0
        self._speed_factor = 0.55

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
        self.ctrl.refresh_cursor(self)
        self.update()

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

    def paintEvent(self, ev):  # noqa: N802
        if self.canvas.isNull():
            return
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(ev.rect(), self.ctrl.background_color(interactive=self.ctrl.drawing))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.drawImage(QPointF(0, 0), self.canvas)
        active = self._stroke or self._shape
        if active is not None and not render.is_eraser(active):
            p.setOpacity(active.opacity)
            p.drawImage(QPointF(0, 0), self.layer)
        p.end()

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
        self._pressure_mode = pressure is not None
        self._speed_factor = 0.55
        self._last_pos = QPointF(pos)
        self._last_t = t
        self._add_point(pos, pressure, t, force=True)

    def _width_for(self, pos: QPointF, pressure: float | None, t: int) -> float:
        item = self._stroke
        size = item.size
        if item.tool == Tool.PEN:
            if pressure is not None:
                return max(0.5, size * (0.12 + 0.88 * max(0.0, min(1.0, pressure)) ** 0.9))
            # Sin sensor de presión: se simula a partir de la velocidad del trazo.
            dt = max(1, t - self._last_t)
            v = math.hypot(pos.x() - self._last_pos.x(), pos.y() - self._last_pos.y()) / dt  # px/ms
            target = max(0.3, min(1.25, 1.25 / (1.0 + 0.6 * v)))
            self._speed_factor += (target - self._speed_factor) * 0.35
            return max(0.5, size * self._speed_factor)
        if pressure is not None and item.tool in (Tool.BRUSH, Tool.PENCIL, Tool.HIGHLIGHTER):
            return max(0.5, size * (0.35 + 0.65 * max(0.0, min(1.0, pressure))))
        return size

    def _add_point(self, pos: QPointF, pressure: float | None, t: int, force: bool = False) -> None:
        item = self._stroke
        pts = item.points
        if not force and pts and math.hypot(pos.x() - pts[-1][0], pos.y() - pts[-1][1]) < _MIN_POINT_DISTANCE:
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
        self.update(rect.toAlignedRect())

    def _move(self, pos: QPointF, pressure: float | None, t: int, modifiers) -> None:
        if self._stroke is not None:
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
            self.update(old.united(new).toAlignedRect())

    def finish_current(self) -> None:
        """Confirma el trazo o figura en curso y lo añade al historial."""
        if self._stroke is not None:
            item = self._stroke
            self._stroke = None
            if item.tool != Tool.ERASER:
                self._composite_layer(item.opacity)
                self._clear_layer()
            self.ctrl.push(self.key, item)
            self.update()
        elif self._shape is not None:
            sh = self._shape
            self._shape = None
            self._clear_layer()
            if math.hypot(sh.x2 - sh.x1, sh.y2 - sh.y1) >= 2:
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
        if e.button() == Qt.MouseButton.LeftButton:
            self._begin(e.position(), None, e.timestamp())
        elif e.button() == Qt.MouseButton.RightButton:
            self.cancel_current()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._tablet_active:
            return
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._move(e.position(), None, e.timestamp(), e.modifiers())

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._tablet_active:
            return
        if e.button() == Qt.MouseButton.LeftButton:
            if self._shape is not None:
                self._move(e.position(), None, e.timestamp(), e.modifiers())
            self.finish_current()

    def tabletEvent(self, e):  # noqa: N802
        """Lápiz de tableta / Windows Ink: usa la presión real si el dispositivo la ofrece."""
        dev = e.device()
        has_pressure = bool(dev is not None and dev.capabilities() & QInputDevice.Capability.Pressure)
        pressure = e.pressure() if has_pressure else None
        t = e.type()
        if t == QEvent.Type.TabletPress:
            eraser = e.pointerType() == QPointingDevice.PointerType.Eraser
            self._tablet_active = True
            self._begin(e.position(), pressure, e.timestamp(), eraser=eraser)
        elif t == QEvent.Type.TabletMove:
            if self._tablet_active:
                self._move(e.position(), pressure, e.timestamp(), e.modifiers())
        elif t == QEvent.Type.TabletRelease:
            if self._tablet_active:
                self.finish_current()
            self._tablet_active = False
        e.accept()

    def wheelEvent(self, e):  # noqa: N802
        d = e.angleDelta().y() or e.angleDelta().x()
        if not d:
            return
        step = 1 if d > 0 else -1
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.ctrl.step_opacity(step)
        else:
            self.ctrl.step_size(step)
        e.accept()


# ---------------------------------------------------------------------- cursores


def make_tool_cursor(tool: Tool, size: float, dpr: float) -> QCursor:
    """Cursor que muestra el tamaño real del pincel / goma."""
    if tool in SHAPE_TOOLS:
        return QCursor(Qt.CursorShape.CrossCursor)
    d = max(4.0, min(float(size), 180.0))
    side = int(math.ceil(d + 6))
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
    # punto central para precisión
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 200))
    p.drawEllipse(QPointF(c, c), 1.0, 1.0)
    p.end()
    return QCursor(pm, int(c), int(c))

