"""Ventana transparente que cubre una pantalla y sobre la que se dibuja.

Se crea una superposición por monitor. Así cada una usa el factor de escala
(DPI) de su propia pantalla y los trazos se ven nítidos aunque los monitores
tengan escalados distintos (100 %, 125 %, 150 %...).

Modo zoom: la superposición muestra una captura congelada de su pantalla
ampliada. Todo lo que se dibuja se guarda en coordenadas reales de la
pantalla, así que al salir del zoom los trazos quedan exactamente sobre el
contenido que se señaló.

Efectos de presentación (no forman parte del dibujo ni del historial): cortina
(que se descubre desde arriba, abajo, la izquierda o la derecha), foco, resaltado
del cursor, de los clics y de las teclas, y puntero láser con tinta que se
desvanece. Se dibujan en coordenadas de la ventana, encima de todo.

Modo recorte: la superposición muestra la pantalla congelada y se arrastra un
rectángulo para recortar esa zona como imagen.
"""
from __future__ import annotations

import dataclasses
import math
import random
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor, QCursor, QEventPoint, QFont, QGuiApplication, QImage, QInputDevice, QPainter, QPainterPath, QPen,
    QPixmap, QPointingDevice, QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from . import render, shape_recognition, winutil
from .items import (
    ClearItem, CoverItem, DeleteItem, NoteItem, ShapeItem, StrokeItem, TextEditItem, TextItem, TransformItem,
    transformed,
)
from .tools import NOTE_TEXT_RGBA, RECOGNIZABLE_TOOLS, SHAPE_TOOLS, Tool

if TYPE_CHECKING:  # pragma: no cover
    from .app import Controller

_FMT = QImage.Format.Format_ARGB32_Premultiplied
_TRANSPARENT = Qt.GlobalColor.transparent
_MIN_POINT_DISTANCE = 0.75

_TOUCH_EVENTS = (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd, QEvent.Type.TouchCancel)
# Gestos táctiles
TOUCH_MULTI_MS = 250    # un segundo dedo antes de este tiempo convierte el trazo en gesto
TOUCH_SLOP = 24         # px: más movimiento ya no es un «toque»
TOUCH_TAP_MS = 500      # duración máxima de un toque con dos o tres dedos
PALM_SIZE = 70          # px: un contacto más ancho es la palma (o el canto de la mano) → goma
PALM_LATE_MS = 300      # hasta cuándo se acepta que el tamaño de la palma llegue tarde

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
# Foco rectangular: franja ancha y baja (proporciones respecto al «radio» del foco)
SPOTLIGHT_RECT_W, SPOTLIGHT_RECT_H = 1.9, 0.5


def spotlight_rect(center: QPointF, radius: float) -> QRectF:
    w, h = radius * SPOTLIGHT_RECT_W, radius * SPOTLIGHT_RECT_H
    return QRectF(center.x() - w, center.y() - h, 2 * w, 2 * h)
CURTAIN_COLOR = QColor(30, 32, 38)
CURTAIN_GRAB = 22                 # px alrededor del borde de la cortina para arrastrarla
CURTAIN_HINTS = {"top": "▼ arrastra o ↓ ↑", "bottom": "▲ arrastra o ↑ ↓",
                 "left": "▶ arrastra o → ←", "right": "◀ arrastra o ← →"}
COVER_MIN = 8                     # lado mínimo (px) de una zona tapada; menos es un clic
CROP_DIM = QColor(0, 0, 0, 120)
KEY_SHOW_MS = 1600                # cuánto se ve cada tecla pulsada...
KEY_FADE_MS = 400                 # ...y cuánto tarda en desvanecerse
KEY_MAX = 4                       # teclas visibles a la vez
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
        # Pantallas táctiles: un dedo dibuja; dos dedos a la vez deshacen (o mueven el zoom).
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents)

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
        self._caret = 0  # posición del cursor dentro del texto en edición
        self._edit_uid: str | None = None  # uid del texto ya escrito que se está editando
        self._edit_orig: TextItem | None = None
        self._edit_erasers: list = []
        # Selección (herramienta Seleccionar)
        self.selection: list[str] = []  # uids seleccionados
        self._sel_mode: str | None = None  # "move", "scale" o "lasso" mientras se arrastra
        self._sel_start = QPointF()
        self._sel_box = QRectF()  # recuadro de la selección al empezar a arrastrar
        self._sel_t = (0.0, 0.0, 1.0)  # (dx, dy, escala) del arrastre en curso
        self._lasso: list[QPointF] = []
        self._sel_img: QImage | None = None  # vista previa de lo que se mueve
        self._text_drag: tuple[QPointF, float, float] | None = None  # (inicio, x, y) al arrastrar un texto
        self._state: render.StrokeState | None = None
        self._tablet_active = False
        self._touch_active = False  # gesto táctil en curso (el ratón simulado se ignora)
        self._touch: dict | None = None
        self.touch_events = 0  # eventos táctiles recibidos (diagnóstico)
        self.touch_sizes: list = []  # tamaños de contacto vistos (diagnóstico)
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

        # Zona tapada en curso (herramienta «Tapar zona»)
        self._cover_from: QPointF | None = None
        self._cover_hit: str | None = None  # uid de la zona tapada donde empezó el clic
        self._cover: CoverItem | None = None  # vista previa mientras se arrastra

        # Recortar zona: pantalla congelada y rectángulo elegido
        self._crop_img: QImage | None = None
        self._crop_from: QPointF | None = None
        self._crop_rect = QRectF()

        # Efectos de presentación
        self.curtain: float | None = None  # cuánto se ha descubierto (px); None = sin cortina
        self.curtain_side = "top"  # lado desde el que se descubre: top, bottom, left o right
        self._curtain_drag: float | None = None  # desplazamiento entre el ratón y el borde
        self._keys: list[list] = []  # teclas pulsadas visibles: [texto, instante, veces]
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
        if t in _TOUCH_EVENTS:
            self._touch_event(ev)
            return True
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

    # ------------------------------------------------------------------ recortar zona

    @property
    def crop_active(self) -> bool:
        return self._crop_img is not None

    @property
    def crop_rect(self) -> QRectF:
        return QRectF(self._crop_rect)

    def start_crop(self, screenshot: QImage) -> None:
        """Muestra ``screenshot`` (la pantalla congelada) para elegir la zona que se recorta."""
        self.finish_current()
        self._crop_img = screenshot
        self._crop_from = None
        self._crop_rect = QRectF()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def end_crop(self) -> None:
        if not self.crop_active:
            return
        self._crop_img = None
        self._crop_from = None
        self._crop_rect = QRectF()
        self.ctrl.refresh_cursor(self)
        self.update()

    def crop_image(self, rect: QRectF) -> QImage:
        """La parte de la pantalla congelada que ocupa ``rect`` (coordenadas de la ventana)."""
        img = self._crop_img
        if img is None or rect.isEmpty():
            return QImage()
        sx, sy = img.width() / max(1, self.width()), img.height() / max(1, self.height())
        src = QRectF(rect.x() * sx, rect.y() * sy, rect.width() * sx, rect.height() * sy).toAlignedRect()
        out = img.copy(src.intersected(img.rect()))
        out.setDevicePixelRatio(1.0)
        return out

    def _crop_press(self, view: QPointF) -> None:
        self._crop_from = QPointF(view)
        self._crop_rect = QRectF()
        self.update()

    def _crop_move(self, view: QPointF) -> None:
        if self._crop_from is None:
            return
        bounds = QRectF(0, 0, self.width(), self.height())
        self._crop_rect = QRectF(self._crop_from, view).normalized().intersected(bounds)
        self.update()

    def _crop_release(self, view: QPointF) -> None:
        if self._crop_from is None:
            return
        self._crop_move(view)
        self._crop_from = None
        r = self._crop_rect
        if r.width() >= 4 and r.height() >= 4:
            self.ctrl.crop_finished(self, QRectF(r))
        else:  # un clic sin arrastrar: se sigue esperando el rectángulo
            self._crop_rect = QRectF()
            self.update()

    def _paint_crop(self, p: QPainter) -> None:
        full = QRectF(0, 0, self.width(), self.height())
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(full, self._crop_img, QRectF(self._crop_img.rect()))
        r = self._crop_rect
        dim = QPainterPath()
        dim.addRect(full)
        if not r.isEmpty():
            hole = QPainterPath()
            hole.addRect(r)
            dim = dim.subtracted(hole)
        p.fillPath(dim, CROP_DIM)
        if not r.isEmpty():
            p.setPen(QPen(QColor(255, 255, 255), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            pen = QPen(QColor(30, 136, 229), 1.0, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(r)
            label = f"{round(r.width())} × {round(r.height())}"
            f = QFont(self.font())
            f.setPointSizeF(9.5)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(label) + 14
            box = QRectF(r.left(), r.top() - 24 if r.top() >= 26 else r.bottom() + 4, tw, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(20, 22, 26, 215))
            p.drawRoundedRect(box, 5, 5)
            p.setPen(QColor(255, 255, 255))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
        self._paint_banner(p, "Arrastra para elegir la zona que quieres recortar   ·   "
                              "Esc o clic derecho: cancelar")

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
        hidden = set(self.selection) if self._sel_img is not None else set()
        if self._edit_uid is not None:
            hidden.add(self._edit_uid)
        for item in self.ctrl.items_for(self.key, exclude_uid=hidden):
            render.apply_item_to_canvas(self.canvas, self.layer, item)
        if self._text is not None:  # el texto en edición se dibuja aparte, en la capa
            self._render_text_preview()
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
        active = self._stroke or self._shape or self._text or self._cover
        if active is not None and not render.is_eraser(active):
            p.save()
            p.setOpacity(active.opacity)
            p.drawImage(QPointF(0, 0), self.layer)
            p.restore()
        if self._sel_img is not None:
            p.drawImage(QPointF(0, 0), self._sel_img)
        if self.ctrl.tool == Tool.SELECT:
            self._paint_selection(p)
        if self._text is not None:
            # Marco discontinuo: indica qué texto se está escribiendo/editando (y que se puede arrastrar)
            p.save()
            pen = QPen(QColor(90, 140, 230, 170), 1.0, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(render.text_hit_rect(self._text).adjusted(2, 2, -2, -2))
            p.restore()
        if self._text is not None and self._caret_on:
            a, b = render.text_caret(self._text, self._caret)
            p.setPen(QPen(QColor(*self._text.rgba), max(1.5, self._text.size / 18)))
            p.drawLine(a, b)

    def paintEvent(self, ev):  # noqa: N802
        if self.canvas.isNull():
            return
        p = QPainter(self)
        if self.crop_active:
            self._paint_crop(p)
            p.end()
            return
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
        if self.curtain is not None:
            self._paint_curtain(p)
        if c.spotlight:
            if self._cursor_view is not None and c.spotlight_shape == "rect":
                hole = spotlight_rect(self._cursor_view, float(c.spotlight_radius))
                dim = QPainterPath()
                dim.addRect(QRectF(rect))
                inner = QPainterPath()
                inner.addRoundedRect(hole, 10, 10)
                p.fillPath(dim.subtracted(inner), SPOTLIGHT_DIM)
                p.setPen(QPen(QColor(255, 255, 255, 90), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(hole, 10, 10)
            elif self._cursor_view is not None:
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
        if self._keys:
            self._paint_keys(p, now)
        for pos, t0, color in self._ripples:
            f = min(1.0, (now - t0) / RIPPLE_MS)
            col = QColor(color)
            col.setAlphaF(0.9 * (1 - f))
            p.setPen(QPen(col, 3.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            radius = 8 + 30 * f
            p.drawEllipse(pos, radius, radius)
        p.restore()

    # ---- teclas pulsadas

    def show_key(self, label: str, now: float) -> None:
        """Muestra una tecla o combinación (p. ej. «Ctrl + C»); si se repite, suma «×2», «×3»…"""
        if self._keys and self._keys[-1][0] == label and now - self._keys[-1][1] < KEY_SHOW_MS:
            self._keys[-1][1] = now
            self._keys[-1][2] += 1
        else:
            self._keys.append([label, now, 1])
            del self._keys[:-KEY_MAX]
        self.update(self._keys_rect())

    @staticmethod
    def _key_alpha(t0: float, now: float) -> float:
        age = now - t0 - KEY_SHOW_MS
        return 1.0 if age <= 0 else max(0.0, 1.0 - age / KEY_FADE_MS)

    def _key_font(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(int(26 * self.ctrl.touch_scale ** 0.5))
        f.setBold(True)
        return f

    def _keys_rect(self) -> QRect:
        h = 70 * KEY_MAX * self.ctrl.touch_scale ** 0.5
        return QRectF(0, self.height() - 90 - h, self.width(), h + 90).toAlignedRect()

    def _paint_keys(self, p: QPainter, now: float) -> None:
        p.save()
        p.setFont(self._key_font())
        fm = p.fontMetrics()
        y = self.height() - 90.0
        for label, t0, count in reversed(self._keys):
            alpha = self._key_alpha(t0, now)
            if alpha <= 0:
                continue
            text = label + (f"  ×{count}" if count > 1 else "")
            tw, th = fm.horizontalAdvance(text) + 36, fm.height() + 18
            box = QRectF((self.width() - tw) / 2, y - th, tw, th)
            p.setOpacity(alpha)
            p.setPen(QPen(QColor(255, 255, 255, 60), 1.0))
            p.setBrush(QColor(20, 22, 26, 225))
            p.drawRoundedRect(box, 10, 10)
            p.setPen(QColor(255, 255, 255))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
            y -= th + 10
        p.restore()

    def _paint_curtain(self, p: QPainter) -> None:
        w, h = float(self.width()), float(self.height())
        side, e = self.curtain_side, self.curtain_edge()
        p.fillRect(self.curtain_rect(), CURTAIN_COLOR)
        edge = {"top": QRectF(0, e, w, 3), "bottom": QRectF(0, e - 3, w, 3),
                "left": QRectF(e, 0, 3, h), "right": QRectF(e - 3, 0, 3, h)}[side]
        p.fillRect(edge, QColor(80, 140, 230))
        covered = {"top": h - e, "bottom": e, "left": w - e, "right": e}[side]
        if covered > (40 if side in ("top", "bottom") else 160):
            pill = {"top": QRectF(w / 2 - 70, e + 8, 140, 24), "bottom": QRectF(w / 2 - 70, e - 32, 140, 24),
                    "left": QRectF(e + 8, h / 2 - 12, 140, 24), "right": QRectF(e - 148, h / 2 - 12, 140, 24)}[side]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(70, 74, 84))
            p.drawRoundedRect(pill, 12, 12)
            p.setPen(QColor(220, 223, 228))
            f = QFont(self.font())
            f.setPointSizeF(9.5)
            p.setFont(f)
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, CURTAIN_HINTS[side])

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
            r = max(r, c.spotlight_radius * (SPOTLIGHT_RECT_W + 0.1 if c.spotlight_shape == "rect" else 1) + 4)
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
        if self._keys:
            self.update(self._keys_rect())
            self._keys = [k for k in self._keys if self._key_alpha(k[1], now) > 0]
        alive = []
        for trail in self._trails:
            self.update(trail.rect().toAlignedRect())
            if trail.alpha(now) > 0:
                alive.append(trail)
        self._trails = alive
        return bool(self._ripples or self._trails or self._laser or self._keys)

    def clear_ripples(self) -> None:
        self._ripples.clear()
        self.update()

    def clear_keys(self) -> None:
        self._keys.clear()
        self.update()

    @property
    def keys_shown(self) -> list[str]:
        return [label + (f"  ×{count}" if count > 1 else "") for label, _t, count in self._keys]

    # ------------------------------------------------------------------ cortina

    @property
    def _curtain_vertical(self) -> bool:
        return self.curtain_side in ("top", "bottom")

    def _curtain_extent(self) -> float:
        return float(self.height() if self._curtain_vertical else self.width())

    def _curtain_axis(self, pos: QPointF) -> float:
        return pos.y() if self._curtain_vertical else pos.x()

    def curtain_edge(self) -> float:
        """Coordenada (y o x) del borde de la cortina."""
        ext = self._curtain_extent()
        r = max(0.0, min(ext, self.curtain or 0.0))
        return r if self.curtain_side in ("top", "left") else ext - r

    def curtain_rect(self) -> QRectF:
        """Parte de la pantalla que la cortina todavía tapa."""
        w, h, e = float(self.width()), float(self.height()), self.curtain_edge()
        return {"top": QRectF(0, e, w, h - e), "bottom": QRectF(0, 0, w, e),
                "left": QRectF(e, 0, w - e, h), "right": QRectF(0, 0, e, h)}[self.curtain_side]

    def set_curtain(self, revealed: float | None, side: str | None = None) -> None:
        """Cortina descubierta ``revealed`` píxeles desde su lado (None la quita)."""
        if side is not None:
            self.curtain_side = side
        self.curtain = None if revealed is None else max(0.0, min(self._curtain_extent(), float(revealed)))
        self.update()

    def move_curtain_edge(self, coord: float) -> None:
        """Coloca el borde de la cortina en la coordenada ``coord`` (y o x, según el lado)."""
        ext = self._curtain_extent()
        self.set_curtain(coord if self.curtain_side in ("top", "left") else ext - coord)

    def _curtain_hit(self, pos: QPointF) -> bool:
        if self.curtain is None:
            return False
        g = CURTAIN_GRAB * self.ctrl.touch_scale
        grow = {"top": (0, -g, 0, 0), "bottom": (0, 0, 0, g), "left": (-g, 0, 0, 0), "right": (0, 0, g, 0)}
        return self.curtain_rect().adjusted(*grow[self.curtain_side]).contains(pos)

    def _curtain_press(self, view: QPointF) -> None:
        self._curtain_drag = self.curtain_edge() - self._curtain_axis(view)

    def _curtain_move(self, view: QPointF) -> None:
        self.move_curtain_edge(self._curtain_axis(view) + self._curtain_drag)

    # ------------------------------------------------------------------ dibujo

    def _begin(self, pos: QPointF, pressure: float | None, t: int, eraser: bool = False) -> None:
        if not self.ctrl.drawing:
            return
        if not eraser and self.ctrl.tool == Tool.SELECT:
            self.finish_current()
            self._sel_press(pos)
            return
        if not eraser and self.ctrl.tool in (Tool.TEXT, Tool.NOTE) and self._text is not None \
                and render.text_hit_rect(self._text).contains(pos):
            # Clic dentro del texto que se está escribiendo: mueve el cursor (o arrastra el texto).
            self._caret = render.text_index_at(self._text, pos)
            self._text_drag = (QPointF(pos), self._text.x, self._text.y)
            self._caret_on = True
            self.update(self._view_rect(render.item_rect(self._text)))
            return
        self.finish_current()
        c = self.ctrl
        tool = Tool.ERASER if eraser else c.tool
        size = float(c.size_for(tool))
        opacity = c.opacity_for(tool) / 100.0
        rgba = c.color.getRgb()
        if tool == Tool.STAMP:
            item = c.make_stamp(pos.x(), pos.y())
            self.apply_item(item, update=False)
            c.push(self.key, item)
            self.update(self._view_rect(render.item_rect(item)))
            if item.kind == "number":
                c.refresh_cursor(self)  # el cursor pasa a mostrar el número siguiente
            return
        if tool == Tool.COVER:
            hit = self.cover_at(pos)
            self._cover_from = QPointF(pos)
            self._cover_hit = hit.uid if hit is not None else None
            self._cover = None
            return
        if tool in SHAPE_TOOLS:
            self._shape = ShapeItem(tool, rgba, size, opacity, pos.x(), pos.y(), pos.x(), pos.y(),
                                    filled=c.fill_shapes)
            return
        if tool in (Tool.TEXT, Tool.NOTE):
            hit = self.text_at(pos)
            if hit is not None:
                self._open_text(hit, pos)
                return
            if tool == Tool.NOTE:  # la esquina superior izquierda de la nota queda donde se hizo clic
                pad = max(8.0, size * 0.5)
                self._text = NoteItem(NOTE_TEXT_RGBA, size, 1.0, pos.x() + pad, pos.y() + pad, "", c.text_bold,
                                      color=c.note_rgba)
            else:
                fm_height = size * 1.33
                self._text = TextItem(rgba, size, opacity, pos.x(), pos.y() - fm_height / 2, "", c.text_bold)
            self._caret = 0
            self._edit_uid = self._edit_orig = None
            self._text_drag = None
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
        if self._sel_mode is not None:
            self._sel_drag(pos, modifiers)
            return
        if self._cover_from is not None:
            rect = QRectF(self._cover_from, pos).normalized()
            old = QRectF(self._layer_rect)
            self._clear_layer()
            if rect.width() >= COVER_MIN and rect.height() >= COVER_MIN:
                self._cover = CoverItem(rect.x(), rect.y(), rect.width(), rect.height())
                p = self._painter(self.layer)
                render.draw_cover(p, self._cover)
                p.end()
                self._layer_rect = render.item_rect(self._cover)
            else:
                self._cover = None
            self.update(self._view_rect(old.united(self._layer_rect)))
            return
        if self._text is not None and self._text_drag is not None:
            start, x0, y0 = self._text_drag
            dx, dy = pos.x() - start.x(), pos.y() - start.y()
            moved = abs(self._text.x - x0) > 0 or abs(self._text.y - y0) > 0
            if moved or math.hypot(dx, dy) >= 4:  # umbral: un clic con temblor no mueve el texto
                self._text.x, self._text.y = x0 + dx, y0 + dy
                self._render_text_preview()
            return
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
        if self._sel_mode is not None:
            self._sel_finish(pos, modifiers)
            return
        if self._shape is not None or self._cover_from is not None:
            self._move(pos, pressure, t, modifiers)
        elif self._stroke is not None and self._stroke.tool == Tool.PEN:
            # El trazo termina exactamente donde se levantó la pluma.
            last = self._stroke.points[-1]
            if math.hypot(pos.x() - last[0], pos.y() - last[1]) >= 0.5:
                self._add_point(pos, pressure, t, force=True)
        self._text_drag = None
        if self._text is None:  # el texto sigue en edición tras soltar el clic
            self.finish_current()

    def finish_current(self) -> None:
        """Confirma el trazo, figura o texto en curso y lo añade al historial."""
        if self._stroke is not None:
            item = self._stroke
            self._stroke = None
            if self.ctrl.recognize_shapes and item.tool in RECOGNIZABLE_TOOLS:
                shape = shape_recognition.recognize(item)
                if shape is not None:  # «Formas perfectas»: el trazo se sustituye por la figura
                    old = QRectF(self._layer_rect)
                    self._clear_layer()
                    self.apply_item(shape, update=False)
                    self.ctrl.push(self.key, shape)
                    self.update(self._view_rect(old.united(render.item_rect(shape))))
                    self._state = None
                    return
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
            item, uid, orig = self._text, self._edit_uid, self._edit_orig
            self._text = None
            self._edit_uid = self._edit_orig = None
            self._text_drag = None
            self._caret_timer.stop()
            self._clear_layer()
            if uid is None:  # texto nuevo
                if item.text.strip():
                    self.apply_item(item, update=False)
                    self.ctrl.push(self.key, item)
            else:  # texto ya escrito: la edición queda en el historial (se puede deshacer)
                if item != orig:
                    self.ctrl.push(self.key, TextEditItem(uid, item))
                self.rebuild()
            self.update()
            self.ctrl.end_text_edit(self)
        elif self._cover_from is not None:
            cover, hit = self._cover, self._cover_hit
            self._cover_from = self._cover = self._cover_hit = None
            self._clear_layer()
            if cover is not None:  # se arrastró: zona tapada nueva
                self.apply_item(cover, update=False)
                self.ctrl.push(self.key, cover)
            elif hit is not None:  # clic sobre una zona tapada: se descubre (se puede deshacer)
                self.ctrl.push(self.key, DeleteItem([hit]))
                self.rebuild()
            self.update()
        self._state = None

    def cover_at(self, pos: QPointF) -> CoverItem | None:
        """La zona tapada visible (la de más arriba) bajo un punto, o None."""
        for _idx, item, later in reversed(self.selectable_items()):
            if isinstance(item, CoverItem) and render.cover_rect(item).contains(pos) \
                    and render.ink_near(item, later, pos, 2.0):
                return item
        return None

    def cancel_current(self) -> None:
        """Descarta el elemento en curso (la goma ya aplicada se conserva en el historial)."""
        if self._stroke is not None and self._stroke.tool == Tool.ERASER:
            self.finish_current()
            return
        editing_text = self._text is not None
        reopened = self._edit_uid is not None
        self._stroke = None
        self._shape = None
        self._text = None
        self._cover_from = self._cover = self._cover_hit = None
        self._edit_uid = self._edit_orig = None
        self._text_drag = None
        self._caret_timer.stop()
        self._state = None
        self._clear_layer()
        if reopened:
            self.rebuild()  # vuelve a mostrar el texto tal como estaba
        self.update()
        if editing_text:
            self.ctrl.end_text_edit(self)

    @property
    def busy(self) -> bool:
        return (self._stroke is not None or self._shape is not None or self._text is not None
                or self._cover_from is not None)

    # ------------------------------------------------------------------ selección

    def selected_items(self) -> list:
        chosen = set(self.selection)
        return [i for i in self.ctrl.items_for(self.key) if getattr(i, "uid", None) in chosen]

    @staticmethod
    def items_rect(items) -> QRectF:
        rect = QRectF()
        for it in items:
            rect = rect.united(render.item_rect(it))
        return rect

    def _handle_rect(self, box: QRectF) -> QRectF:
        h = 16.0 * self.ctrl.touch_scale / max(self.zoom_factor, 0.01)
        return QRectF(box.right() - h / 2, box.bottom() - h / 2, h, h)

    def selectable_items(self) -> list[tuple[int, object, list | None]]:
        """(índice, elemento, gomas posteriores) de lo que se ve y se puede seleccionar."""
        items = self.ctrl.items_for(self.key)
        out = []
        for idx, item in enumerate(items):
            if isinstance(item, ClearItem) or render.is_eraser(item) or not getattr(item, "uid", None):
                continue
            later = render.erasers_after(items, idx)
            if later is None:  # antes de un «Borrar todo»: no se ve
                continue
            out.append((idx, item, later))
        return out

    def item_at(self, pos: QPointF):
        """El elemento visible (el de más arriba) cuya tinta está bajo el punto, o None."""
        radius = max(4.0, 8.0 / max(self.zoom_factor, 0.01))
        for _idx, item, later in reversed(self.selectable_items()):
            if render.item_rect(item).adjusted(-radius, -radius, radius, radius).contains(pos) \
                    and render.ink_near(item, later, pos, radius):
                return item
        return None

    def set_selection(self, uids) -> None:
        self.selection = list(uids)
        self.update()
        self.ctrl.selection_changed()

    def clear_selection(self) -> None:
        if self.selection or self._lasso or self._sel_img is not None:
            self._sel_mode = None
            self._lasso = []
            had_preview = self._sel_img is not None
            self._sel_img = None
            self.selection = []
            if had_preview:
                self.rebuild()
            self.update()
            self.ctrl.selection_changed()

    def select_all(self) -> None:
        self.set_selection([item.uid for _i, item, later in self.selectable_items()
                            if render.item_visible(item, later)])

    def _sel_press(self, pos: QPointF) -> None:
        box = self.items_rect(self.selected_items()) if self.selection else QRectF()
        if self.selection and self._handle_rect(box).contains(pos):
            self._sel_mode = "scale"
        elif self.selection and box.contains(pos):
            self._sel_mode = "move"
        else:
            hit = self.item_at(pos)
            if hit is not None:
                self.set_selection([hit.uid])
                box = self.items_rect(self.selected_items())
                self._sel_mode = "move"
            else:
                self.set_selection([])
                self._sel_mode = "lasso"
                self._lasso = [QPointF(pos)]
                return
        self._sel_start = QPointF(pos)
        self._sel_box = QRectF(box)
        self._sel_t = (0.0, 0.0, 1.0)
        # Lo seleccionado se oculta del lienzo y se dibuja aparte mientras se arrastra
        self._sel_img = QImage(self.canvas.size(), QImage.Format.Format_ARGB32_Premultiplied)
        self._sel_img.setDevicePixelRatio(self.canvas.devicePixelRatio())
        self._sel_img.fill(_TRANSPARENT)
        self.rebuild()
        self._render_sel_preview()

    def _sel_transform(self) -> tuple[float, float, float, float, float]:
        dx, dy, s = self._sel_t
        return dx, dy, s, self._sel_box.left(), self._sel_box.top()

    def _render_sel_preview(self) -> None:
        if self._sel_img is None:
            return
        self._sel_img.fill(_TRANSPARENT)
        dx, dy, s, ox, oy = self._sel_transform()
        for item in self.selected_items():
            render.apply_item_to_canvas(self._sel_img, self.layer, transformed(item, dx, dy, s, ox, oy))
        self.update()

    def _sel_drag(self, pos: QPointF, modifiers) -> None:
        if self._sel_mode == "lasso":
            if not self._lasso or math.hypot(pos.x() - self._lasso[-1].x(), pos.y() - self._lasso[-1].y()) >= 2:
                self._lasso.append(QPointF(pos))
                self.update()
            return
        if self._sel_mode == "move":
            dx, dy = pos.x() - self._sel_start.x(), pos.y() - self._sel_start.y()
            if modifiers & Qt.KeyboardModifier.ShiftModifier:  # Mayús: solo en horizontal o vertical
                if abs(dx) >= abs(dy):
                    dy = 0.0
                else:
                    dx = 0.0
            self._sel_t = (dx, dy, 1.0)
        elif self._sel_mode == "scale":
            o = self._sel_box.topLeft()
            c = self._sel_box.bottomRight()
            vx, vy = c.x() - o.x(), c.y() - o.y()
            d2 = vx * vx + vy * vy
            if d2 > 1:
                s = ((pos.x() - o.x()) * vx + (pos.y() - o.y()) * vy) / d2
                self._sel_t = (0.0, 0.0, max(0.1, min(10.0, s)))
        self._render_sel_preview()

    def _sel_finish(self, pos: QPointF, modifiers) -> None:
        mode, self._sel_mode = self._sel_mode, None
        if mode == "lasso":
            poly = QPolygonF(self._lasso)
            self._lasso = []
            if len(poly) >= 3 and poly.boundingRect().width() + poly.boundingRect().height() > 8:
                self.set_selection([item.uid for _i, item, later in self.selectable_items()
                                    if _in_lasso(item, poly) and render.item_visible(item, later)])
            self.update()
            return
        self._sel_drag(pos, modifiers)
        dx, dy, s, ox, oy = self._sel_transform()
        self._sel_img = None
        if math.hypot(dx, dy) >= 1.0 or abs(s - 1.0) > 1e-3:
            self.ctrl.push(self.key, TransformItem(list(self.selection), dx, dy, s, ox, oy))
        self.rebuild()
        self.ctrl.selection_changed()

    def _paint_selection(self, p: QPainter) -> None:
        p.save()
        pen = QPen(QColor(30, 136, 229, 230), 1.5, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self._lasso:
            p.drawPolyline(QPolygonF(self._lasso))
        if self.selection:
            box = self.items_rect(self.selected_items())
            if self._sel_mode in ("move", "scale"):
                dx, dy, s, ox, oy = self._sel_transform()
                b = self._sel_box
                box = QRectF(ox + (b.left() - ox) * s + dx, oy + (b.top() - oy) * s + dy, b.width() * s, b.height() * s)
            if not box.isEmpty():
                p.drawRect(box)
                p.setPen(QPen(QColor(255, 255, 255), 1.5))
                p.setBrush(QColor(30, 136, 229))
                p.drawRect(self._handle_rect(box))
        p.restore()

    # ------------------------------------------------------------------ texto

    @property
    def editing_text(self) -> TextItem | None:
        return self._text

    def text_at(self, pos: QPointF) -> TextItem | None:
        """El texto ya escrito (el de más arriba) cuya tinta visible está bajo un punto, o None.

        Solo cuenta lo que se ve: un texto borrado con la goma o con «Borrar todo» no se abre.
        """
        items = self.ctrl.items_for(self.key)
        for idx in range(len(items) - 1, -1, -1):
            item = items[idx]
            if not isinstance(item, TextItem) or not render.text_hit_rect(item).contains(pos):
                continue
            radius = max(6.0, item.size * 0.35)
            if render.text_ink_near(item, render.erasers_after(items, idx), pos, radius):
                return item
        return None

    def _open_text(self, item: TextItem, pos: QPointF) -> None:
        """Abre un texto ya escrito para editarlo (el original se oculta mientras tanto)."""
        c = self.ctrl
        self._edit_uid = item.uid
        self._edit_orig = item
        items = self.ctrl.items_for(self.key)
        idx = next(i for i, it in enumerate(items) if isinstance(it, TextItem) and it.uid == item.uid)
        # La vista previa respeta la goma aplicada después (lo borrado sigue borrado al editar).
        self._edit_erasers = render.erasers_after(items, idx) or []
        self._text = dataclasses.replace(item)
        self._caret = render.text_index_at(self._text, pos)
        self._text_drag = (QPointF(pos), item.x, item.y)
        self._caret_on = True
        self._caret_timer.start()
        c.adopt_text_style(item)
        self.rebuild()  # sin el original; el texto en edición se dibuja en la capa
        c.begin_text_edit(self)

    def _render_text_preview(self) -> None:
        if self._text is None:
            return
        old = QRectF(self._layer_rect)
        self._clear_layer()
        p = self._painter(self.layer)
        render.draw_text(p, self._text)
        if self._edit_uid is not None:
            render.apply_erasers(p, self._edit_erasers)
        p.end()
        self._layer_rect = render.item_rect(self._text)
        self.update(self._view_rect(old.united(self._layer_rect)))

    def _blink_caret(self) -> None:
        self._caret_on = not self._caret_on
        if self._text is not None:
            self.update(self._view_rect(render.item_rect(self._text)))

    def restyle_text(self, rgba, size: float, bold: bool, opacity: float | None = None) -> None:
        """Aplica color, tamaño, negrita y opacidad al texto que se está escribiendo."""
        if self._text is None:
            return
        self._text.size, self._text.bold = size, bold
        if not isinstance(self._text, NoteItem):  # la nota conserva su letra oscura y es opaca
            self._text.rgba = tuple(rgba)
            if opacity is not None:
                self._text.opacity = opacity
        self._render_text_preview()

    def text_key(self, ev) -> None:
        """Teclas mientras se escribe un texto (las envía el controlador)."""
        item = self._text
        if item is None:
            return
        key, mods = ev.key(), ev.modifiers()
        ctrl_down = bool(mods & Qt.KeyboardModifier.ControlModifier)
        text, caret = item.text, max(0, min(len(item.text), self._caret))
        if key == Qt.Key.Key_Escape or (ctrl_down and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self.finish_current()
            return

        def insert(s: str) -> None:
            nonlocal text, caret
            text = text[:caret] + s + text[caret:]
            caret += len(s)

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            insert("\n")
        elif key == Qt.Key.Key_Backspace:
            if caret > 0:
                text, caret = text[:caret - 1] + text[caret:], caret - 1
        elif key == Qt.Key.Key_Delete:
            text = text[:caret] + text[caret + 1:]
        elif key == Qt.Key.Key_Left:
            caret = max(0, caret - 1)
        elif key == Qt.Key.Key_Right:
            caret = min(len(text), caret + 1)
        elif key in (Qt.Key.Key_Home, Qt.Key.Key_End):
            line, _ = render.text_line_col(text, caret)
            if ctrl_down:
                caret = 0 if key == Qt.Key.Key_Home else len(text)
            else:
                caret = render.text_index(text, line, 0 if key == Qt.Key.Key_Home else 10 ** 9)
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            a, _b = render.text_caret(item, caret)
            line, _ = render.text_line_col(text, caret)
            fm_line = render.text_box(dataclasses.replace(item, text="x")).height()
            target = line + (-1 if key == Qt.Key.Key_Up else 1)
            if 0 <= target <= text.count("\n"):
                caret = render.text_index_at(item, QPointF(a.x() - 1, item.y + (target + 0.5) * fm_line))
        elif key == Qt.Key.Key_Tab:
            insert("    ")
        elif ctrl_down and key == Qt.Key.Key_V:
            pasted = QGuiApplication.clipboard().text().replace("\r\n", "\n").replace("\r", "\n")
            insert("".join(ch for ch in pasted if ch == "\n" or ch.isprintable()))
        else:
            txt = ev.text()
            if not txt or ctrl_down or not txt.isprintable():
                return
            insert(txt)
        item.text, self._caret = text, caret
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

    # Pulsar / arrastrar / soltar con el botón izquierdo, el dedo o el lápiz (sin presión)

    def _pointer_press(self, view: QPointF, t: int, eraser: bool = False) -> None:
        if self.crop_active:
            self._crop_press(view)
        elif self._curtain_hit(view) and not self.busy:
            self._curtain_press(view)
        elif self.ctrl.tool == Tool.LASER and self.ctrl.drawing and not eraser:
            self._laser_press(view)
        elif self._pan_from is None:
            self._begin(self.to_canvas(view), None, t, eraser=eraser)

    def _pointer_move(self, view: QPointF, t: int, modifiers) -> None:
        if self.crop_active:
            self._crop_move(view)
        elif self._curtain_drag is not None:
            self._curtain_move(view)
        elif self._laser is not None:
            self._laser_move(view)
        else:
            self._move(self.to_canvas(view), None, t, modifiers)

    def _pointer_release(self, view: QPointF, t: int, modifiers) -> None:
        if self.crop_active:
            self._crop_release(view)
        elif self._curtain_drag is not None:
            self._curtain_drag = None
        elif self._laser is not None:
            self._laser_release()
        else:
            self._release(self.to_canvas(view), None, t, modifiers)

    def mousePressEvent(self, e):  # noqa: N802
        if self._tablet_active or self._touch_active:
            return
        btn = e.button()
        view = e.position()
        if btn == Qt.MouseButton.LeftButton:
            self._pointer_press(view, e.timestamp())
        elif self.crop_active:
            if btn == Qt.MouseButton.RightButton:
                self.ctrl.crop_finished(self, None)
        elif btn == Qt.MouseButton.RightButton and self.busy:
            self.cancel_current()
        elif btn in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton) and self.zoom_active:
            self._pan_from = (QPointF(view), QPointF(self._zoom_tl))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._tablet_active or self._touch_active:
            return
        view = e.position()
        if self._pan_from is not None:
            start, tl = self._pan_from
            delta = view - start
            self._zoom_tl = QPointF(tl.x() - delta.x() / self._zoom, tl.y() - delta.y() / self._zoom)
            self._clamp_zoom()
            self.update()
        elif (self.crop_active or self._curtain_drag is not None or self._laser is not None
              or e.buttons() & Qt.MouseButton.LeftButton):
            self._pointer_move(view, e.timestamp(), e.modifiers())

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._tablet_active or self._touch_active:
            return
        btn = e.button()
        if btn == Qt.MouseButton.LeftButton:
            self._pointer_release(e.position(), e.timestamp(), e.modifiers())
        elif btn in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton) and self._pan_from is not None:
            self._pan_from = None
            self.ctrl.refresh_cursor(self)

    def tabletEvent(self, e):  # noqa: N802
        """Lápiz de tableta / Windows Ink: usa la presión real si el dispositivo la ofrece."""
        dev = e.device()
        has_pressure = bool(dev is not None and dev.capabilities() & QInputDevice.Capability.Pressure)
        pressure = e.pressure() if has_pressure else None
        view = e.position()
        pos = self.to_canvas(view)
        t = e.type()
        laser = self.ctrl.tool == Tool.LASER and self.ctrl.drawing
        if self.crop_active:
            if t == QEvent.Type.TabletPress:
                self._tablet_active = True
                self._crop_press(view)
            elif t == QEvent.Type.TabletMove and self._tablet_active:
                self._crop_move(view)
            elif t == QEvent.Type.TabletRelease:
                self._tablet_active = False
                self._crop_release(view)
            e.accept()
            return
        if t == QEvent.Type.TabletPress:
            eraser = e.pointerType() == QPointingDevice.PointerType.Eraser
            self._tablet_active = True
            if self._curtain_hit(view) and not self.busy:
                self._curtain_press(view)
            elif laser and not eraser:
                self._laser_press(view)
            else:
                self._begin(pos, pressure, e.timestamp(), eraser=eraser)
        elif t == QEvent.Type.TabletMove:
            if self._tablet_active:
                if self._curtain_drag is not None:
                    self._curtain_move(view)
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

    # ------------------------------------------------------------------ pantalla táctil

    def _abort_for_gesture(self) -> None:
        """Al apoyar un segundo dedo se descarta lo que empezó el primero (era un gesto)."""
        self._laser = None
        self._curtain_drag = None
        self._crop_from = None
        if self._sel_mode is not None:
            self._sel_mode = None
            self._lasso = []
            self._sel_img = None
            self.rebuild()
        if self._stroke is not None and self._stroke.tool == Tool.ERASER:
            self._stroke = None  # la goma ya borró en el lienzo: se reconstruye sin ella
            self._state = None
            self.rebuild()
        else:
            self.cancel_current()
        self.update()

    def _touch_event(self, ev) -> None:
        self.touch_events += 1
        t = ev.type()
        now = ev.timestamp()
        g = self._touch
        if t == QEvent.Type.TouchCancel:
            if g is not None and g["mode"] == "one":
                self._abort_for_gesture()
            self._touch = None
            self._touch_active = False
            ev.accept()
            return
        if t == QEvent.Type.TouchBegin or g is None:
            g = self._touch = {"mode": "one", "t0": now, "start": {}, "cur": {}, "primary": None,
                               "fingers": 0, "moved": 0.0, "zoom0": None}
            self._touch_active = True
        for pt in ev.points():
            if pt.state() == QEventPoint.State.Stationary:
                continue  # no se movió (y algunos dispositivos no repiten su posición)
            pid, pos = pt.id(), QPointF(pt.position())
            if pt.state() == QEventPoint.State.Pressed:
                g["start"][pid] = QPointF(pos)
            g["cur"][pid] = pos
            if pid in g["start"]:
                d = g["start"][pid]
                g["moved"] = max(g["moved"], math.hypot(pos.x() - d.x(), pos.y() - d.y()))
        down = [pt for pt in ev.points() if pt.state() != QEventPoint.State.Released]
        g["fingers"] = max(g["fingers"], len(ev.points()))
        mods = ev.modifiers()

        if g["mode"] == "one":
            if g["primary"] is None and len(ev.points()) == 1:
                pt = ev.points()[0]
                g["primary"] = pt.id()
                size = self._contact_size(pt)
                palm = size >= PALM_SIZE
                if palm:
                    self._palm_eraser(g, size)
                self._pointer_press(QPointF(pt.position()), now, eraser=palm)
            elif len(ev.points()) >= 2 and g["primary"] is not None:
                if now - g["t0"] <= TOUCH_MULTI_MS and g["moved"] < TOUCH_SLOP:
                    self._abort_for_gesture()
                    g["mode"] = "multi"
                # (si llega tarde, el segundo dedo se ignora y se sigue dibujando con el primero)
            elif len(ev.points()) >= 2:  # varios dedos a la vez desde el principio
                g["mode"] = "multi"
            if g["mode"] == "one" and g["primary"] is not None:
                prim = next((pt for pt in ev.points() if pt.id() == g["primary"]), None)
                if prim is not None and prim.state() == QEventPoint.State.Released:
                    self._pointer_release(QPointF(prim.position()), now, mods)
                    g["primary"] = -1  # ya soltado
                    self._restore_palm(g)
                elif prim is not None and prim.state() == QEventPoint.State.Updated:
                    size = self._contact_size(prim)
                    if "palm_size" not in g and size >= PALM_SIZE and now - g["t0"] <= PALM_LATE_MS:
                        # Windows a veces informa el tamaño del contacto un instante después de
                        # empezar: lo dibujado hasta ahora se descarta y se borra desde el inicio.
                        self._abort_for_gesture()
                        self._palm_eraser(g, size)
                        self._pointer_press(g["start"].get(g["primary"], QPointF(prim.position())), now, eraser=True)
                    self._pointer_move(QPointF(prim.position()), now, mods)
        if g["mode"] == "multi" and self.zoom_active and len(down) >= 2:
            self._touch_pinch(g, down)

        if t == QEvent.Type.TouchEnd:
            if g["mode"] == "multi" and g["moved"] < TOUCH_SLOP and now - g["t0"] <= TOUCH_TAP_MS:
                if g["fingers"] == 2:
                    self.ctrl.undo()  # toque con dos dedos: deshacer
                elif g["fingers"] >= 3:
                    self.ctrl.redo()  # toque con tres dedos: rehacer
            elif g["mode"] == "one" and g["primary"] not in (None, -1):
                self._pointer_release(g["cur"].get(g["primary"], QPointF()), now, mods)
                self._restore_palm(g)
            self._touch = None
            self._touch_active = False
        ev.accept()

    def _contact_size(self, pt) -> float:
        """Ancho del contacto (px lógicos): el que da Qt o, en Windows, el que informa el sistema."""
        size = max(pt.ellipseDiameters().width(), pt.ellipseDiameters().height(),
                   self.ctrl.touch_contact_size() / (self.devicePixelRatioF() or 1.0))
        self.touch_sizes.append((round(size), pt.state().name))  # diagnóstico
        del self.touch_sizes[:-40]
        return size

    def _palm_eraser(self, g: dict, size: float) -> None:
        """La palma borra, con una goma del tamaño del contacto (se restaura al levantarla)."""
        g["palm_size"] = self.ctrl.sizes[Tool.ERASER]
        self.ctrl.sizes[Tool.ERASER] = int(min(250, max(size, self.ctrl.sizes[Tool.ERASER])))

    def _restore_palm(self, g: dict) -> None:
        if "palm_size" in g:
            self.ctrl.sizes[Tool.ERASER] = g.pop("palm_size")

    def _touch_pinch(self, g: dict, down) -> None:
        """Con el zoom activo, dos dedos acercan/alejan (pellizcar) y desplazan la vista."""
        a, b = QPointF(down[0].position()), QPointF(down[1].position())
        center = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        dist = max(1.0, math.hypot(a.x() - b.x(), a.y() - b.y()))
        if g["zoom0"] is None:
            g["zoom0"] = (self._zoom, dist, self.to_canvas(center))
            return
        z0, d0, anchor = g["zoom0"]
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, z0 * dist / d0))
        self._zoom_tl = QPointF(anchor.x() - center.x() / self._zoom, anchor.y() - center.y() / self._zoom)
        self._clamp_zoom()
        self.ctrl.zoom_changed(self)
        self.update()

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


def _in_lasso(item, poly: QPolygonF) -> bool:
    """¿Queda el elemento dentro del lazo? (trazos: la mayoría de sus puntos; el resto: su centro)."""
    fill = Qt.FillRule.OddEvenFill
    if isinstance(item, StrokeItem) and item.points:
        inside = sum(poly.containsPoint(QPointF(x, y), fill) for x, y, _w in item.points)
        return inside >= len(item.points) * 0.6
    return poly.containsPoint(render.item_rect(item).center(), fill)


def make_stamp_cursor(stamp, view_size: float, dpr: float) -> QCursor:
    """Cursor con la vista previa del sello (semitransparente), centrado en el punto del clic."""
    d = max(12.0, min(float(view_size), 200.0))
    side = int(math.ceil(d * 1.3)) | 1
    pm = QPixmap(max(1, int(math.ceil(side * dpr))), max(1, int(math.ceil(side * dpr))))
    pm.setDevicePixelRatio(dpr)
    pm.fill(_TRANSPARENT)
    p = QPainter(pm)
    p.setOpacity(0.6)
    render.draw_stamp(p, dataclasses.replace(stamp, size=d, x=side / 2, y=side / 2))
    p.end()
    return QCursor(pm, side // 2, side // 2)


def make_tool_cursor(tool: Tool, size: float, dpr: float) -> QCursor:
    """Cursor que muestra el tamaño real del pincel / goma (``size`` ya en píxeles de la vista)."""
    if tool in SHAPE_TOOLS or tool in (Tool.STAMP, Tool.COVER):
        return QCursor(Qt.CursorShape.CrossCursor)
    if tool == Tool.SELECT:
        return QCursor(Qt.CursorShape.ArrowCursor)
    if tool in (Tool.TEXT, Tool.NOTE):
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
