"""Controlador principal: herramientas, páginas e historial, modos, efectos de presentación,
sesiones, capturas, bandeja del sistema y atajos."""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid

from PySide6.QtCore import (
    QBuffer, QEvent, QIODevice, QObject, QPointF, QRectF, QSettings, QStandardPaths, Qt, QTimer, Signal,
)
from PySide6.QtGui import QAction, QColor, QCursor, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, capture, icons, session, winutil
from .hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, GlobalHotkeys
from . import templates
from .items import (
    ClearItem, DeleteItem, DuplicateItem, ImageItem, StampItem, TextEditItem, TextItem, TransformItem, flatten,
)
from .timer import TimerWindow
from .overlay import Overlay, make_stamp_cursor, make_tool_cursor, now_ms
from .session import Page
from .toolbar import Toolbar
from .tools import (
    BACKGROUNDS, BRUSH_LABELS, DEFAULT_COLOR, EXTRA_SHAPES, PATTERNS, POLYGON_SIDES, STAMPS, TOOL_SPECS, BrushType,
    Tool,
)

log = logging.getLogger(__name__)

CAPTURE_DELAY_MS = 250  # tiempo para que Windows retire la superposición antes de capturar
EFFECTS_INTERVAL_MS = 16

VK_D, VK_F, VK_H, VK_M, VK_S, VK_Z = 0x44, 0x46, 0x48, 0x4D, 0x53, 0x5A

SPOTLIGHT_MIN, SPOTLIGHT_MAX, SPOTLIGHT_DEFAULT = 60, 600, 170
SPOTLIGHT_SHAPES = {"circle": "Círculo", "rect": "Rectángulo"}
MANUAL_NAME = "Manual de usuario.pdf"


def screen_key(screen) -> str:
    return screen.name() or f"screen-{id(screen)}"


def documents_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or os.path.expanduser("~")
    path = os.path.join(base, "Pizarra Virtual")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return base
    return path


def manual_path() -> str | None:
    """El manual va junto al ejecutable (zip de la versión) o en dist/ al compilar."""
    here = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    for folder in (here, os.path.join(os.path.dirname(here), "dist")):
        path = os.path.join(folder, MANUAL_NAME)
        if os.path.isfile(path):
            return path
    return None


class Controller(QObject):
    state_changed = Signal()

    def __init__(self, app: QApplication, settings: QSettings | None = None,
                 enable_hotkeys: bool = True, enable_tray: bool = True):
        super().__init__()
        self.app = app
        self.settings = settings or QSettings("PizarraVirtual", "PizarraVirtual")

        # Páginas (cada una con su historial, fondo y pauta)
        self.pages: list[Page] = [Page()]
        self.page_index = 0
        self.session_path: str | None = None
        self.dirty = False

        # Estado de herramientas
        self.tool = Tool.BRUSH
        self.brush_type = BrushType.HARD
        self.color = QColor(DEFAULT_COLOR)
        self.sizes = {t: s.default_size for t, s in TOOL_SPECS.items()}
        self.opacities = {t: s.default_opacity for t, s in TOOL_SPECS.items()}
        self.fill_shapes = False
        self.text_bold = False
        self.stamp_kind = "check"
        self.recognize_shapes = False  # «Formas perfectas»: opción que se activa a voluntad
        self.timer_window: TimerWindow | None = None
        self.extra_shape = Tool.HEXAGON  # última figura elegida en «Más figuras»
        self.spotlight_radius = SPOTLIGHT_DEFAULT
        self.spotlight_shape = "circle"  # "circle" o "rect" (franja, p. ej. para leer línea a línea)
        self._load_settings()

        # Estado de la aplicación
        self.drawing = True
        self.visible = True
        self.spotlight = False
        self.highlight = False
        self.text_editor: Overlay | None = None
        self._capturing = False
        self._shutting_down = False
        self._close_pending = False
        self.overlays: dict[str, Overlay] = {}
        self.last_capture: str | None = None

        # Efectos animados (foco, resaltado del cursor, láser): un único temporizador.
        self._fx_timer = QTimer(self)
        self._fx_timer.setInterval(EFFECTS_INTERVAL_MS)
        self._fx_timer.timeout.connect(self._tick)
        self._prev_buttons = (False, False)
        self.button_state = self._system_buttons

        self.toolbar = Toolbar(self)
        self.hotkeys = GlobalHotkeys(self) if enable_hotkeys else None
        self.tray = self._build_tray() if enable_tray and QSystemTrayIcon.isSystemTrayAvailable() else None

        for s in QGuiApplication.screens():
            self._add_screen(s)
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._remove_screen)
        app.installEventFilter(self)  # teclado para la herramienta Texto
        app.aboutToQuit.connect(self._on_about_to_quit)
        self.state_changed.connect(self.toolbar.sync)

    # ================================================================== arranque / salida

    def start(self) -> None:
        for ov in self.overlays.values():
            ov.show()
        self.toolbar.restore_position()
        self.toolbar.show()
        self._raise_toolbar(activate=True)
        self._changed()
        failed = self._register_hotkeys()
        if self.tray is not None:
            self.tray.show()
            msg = "Ctrl+Alt+D activa/desactiva el dibujo. Ctrl+Alt+H oculta la pizarra."
            if failed:
                msg += "\nNo se pudieron registrar: " + ", ".join(failed) + " (en uso por otra app)."
            self.notify("Pizarra Virtual activa", msg)

    def quit(self) -> None:
        self._finish_all()
        if not self.confirm_discard("salir"):
            return
        self.toolbar.save_position()
        self._save_settings()
        self.shutdown()
        self.app.quit()

    @property
    def shutting_down(self) -> bool:
        return self._shutting_down

    def request_close(self) -> None:
        """Una ventana recibió la orden de cerrarse (Alt+F4, barra de tareas...).

        Cerrar solo esa ventana dejaría el resto de la pizarra (siempre encima) sobre el
        escritorio y sin barra para salir, así que se cierra el programa completo.
        Se difiere para no salir desde dentro del closeEvent y para agrupar varias peticiones.
        """
        if self._shutting_down or self._close_pending:
            return
        self._close_pending = True

        def run():
            self._close_pending = False
            self.quit()

        QTimer.singleShot(0, run)

    def _on_about_to_quit(self) -> None:
        # El programa termina por otra vía (p. ej. al cerrar la sesión de Windows)
        if not self._shutting_down:
            try:
                self.toolbar.save_position()
                self._save_settings()
            finally:
                self.shutdown()

    def shutdown(self) -> None:
        """Libera atajos, temporizadores y ventanas (al salir; también lo usan las pruebas)."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self._fx_timer.stop()
        self.app.removeEventFilter(self)
        if self.hotkeys is not None:
            self.hotkeys.unregister_all()
        if self.tray is not None:
            self.tray.hide()
        for ov in list(self.overlays.values()):
            ov.close()
        self.overlays.clear()
        if self.timer_window is not None:
            self.timer_window.close()
            self.timer_window.deleteLater()
            self.timer_window = None
        self.toolbar.close()

    def _register_hotkeys(self) -> list[str]:
        if self.hotkeys is None or not self.hotkeys.available:
            return []
        combos = [
            (MOD_CONTROL | MOD_ALT, VK_D, "Ctrl+Alt+D", self.toggle_drawing),
            (MOD_CONTROL | MOD_ALT, VK_H, "Ctrl+Alt+H", self.toggle_visible),
            (MOD_CONTROL | MOD_ALT, VK_Z, "Ctrl+Alt+Z", self.toggle_zoom),
            (MOD_CONTROL | MOD_ALT, VK_S, "Ctrl+Alt+S", lambda: self.capture(with_drawing=True)),
            (MOD_CONTROL | MOD_ALT | MOD_SHIFT, VK_S, "Ctrl+Alt+Shift+S",
             lambda: self.capture(with_drawing=False)),
            (MOD_CONTROL | MOD_ALT, VK_F, "Ctrl+Alt+F", self.toggle_spotlight),
            (MOD_CONTROL | MOD_ALT, VK_M, "Ctrl+Alt+M", self.toggle_highlight),
        ]
        return [label for mods, vk, label, fn in combos if not self.hotkeys.register(mods, vk, fn)]

    # ================================================================== pantallas

    def _add_screen(self, screen) -> Overlay:
        key = screen_key(screen)
        while key in self.overlays:
            key += "+"
        ov = Overlay(self, screen, key)
        self.overlays[key] = ov
        return ov

    def _on_screen_added(self, screen) -> None:
        ov = self._add_screen(screen)
        if self.visible:
            ov.show()
            self._raise_toolbar()

    def _remove_screen(self, screen) -> None:
        for key, ov in list(self.overlays.items()):
            if ov.screen_ref is screen:
                ov.finish_current()
                del self.overlays[key]
                ov.close()

    def overlay_for_screen(self, screen) -> Overlay | None:
        for ov in self.overlays.values():
            if ov.screen_ref is screen:
                return ov
        return None

    def current_screen(self):
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def screen_keys(self) -> list[str]:
        """Claves de pantalla con la principal primero."""
        primary = self.overlay_for_screen(QGuiApplication.primaryScreen())
        keys = list(self.overlays)
        if primary is not None:
            keys.remove(primary.key)
            keys.insert(0, primary.key)
        return keys

    # ================================================================== herramientas

    def size_for(self, tool: Tool) -> int:
        return self.sizes[tool]

    def opacity_for(self, tool: Tool) -> int:
        return self.opacities[tool]

    def set_tool(self, tool: Tool) -> None:
        tool = Tool(tool)
        if tool in EXTRA_SHAPES:
            self.extra_shape = tool
        if tool != Tool.TEXT:
            self._finish_all()
        self.tool = tool
        if not self.drawing:
            self.set_drawing(True)
        self._changed(cursor=True, repaint=True)

    def set_stamp_kind(self, kind: str) -> None:
        if kind in STAMPS:
            self.stamp_kind = kind
            self.set_tool(Tool.STAMP)
            self._changed(cursor=True)

    # ---- temporizador

    def _timer(self) -> TimerWindow:
        if self.timer_window is None:
            self.timer_window = TimerWindow()
        win = self.timer_window
        if not win.isVisible():
            win.place_on(self.current_screen())
            win.show()
        win.raise_()
        return win

    def start_timer(self, seconds: float) -> None:
        self._timer().start_countdown(seconds)

    def start_stopwatch(self) -> None:
        self._timer().start_stopwatch()

    def ask_timer(self) -> None:
        minutes, ok = QInputDialog.getInt(self.toolbar, "Temporizador", "Minutos:", 5, 1, 300, 1)
        if ok:
            self.start_timer(minutes * 60)

    def hide_timer(self) -> None:
        if self.timer_window is not None:
            self.timer_window.close()

    @property
    def timer_visible(self) -> bool:
        return self.timer_window is not None and self.timer_window.isVisible()

    def set_recognize_shapes(self, on: bool) -> None:
        self.recognize_shapes = bool(on)
        self._changed()

    def toggle_recognize_shapes(self) -> None:
        self.set_recognize_shapes(not self.recognize_shapes)
        self.notify("Formas perfectas " + ("activadas" if self.recognize_shapes else "desactivadas"),
                    "Las líneas, círculos, rectángulos y polígonos dibujados a mano se convierten en figuras."
                    if self.recognize_shapes else "Los trazos se quedan tal como los dibujas.")

    def cycle_stamp(self) -> None:
        """Tecla S: elige la herramienta Sellos; si ya está elegida, pasa al siguiente sello."""
        if self.tool != Tool.STAMP:
            self.set_tool(Tool.STAMP)
            return
        order = list(STAMPS)
        self.set_stamp_kind(order[(order.index(self.stamp_kind) + 1) % len(order)])

    def cycle_polygon(self) -> None:
        """Tecla P: pentágono → hexágono → octágono."""
        order = list(POLYGON_SIDES)
        if self.tool in order:
            self.set_tool(order[(order.index(self.tool) + 1) % len(order)])
        else:
            self.set_tool(self.extra_shape if self.extra_shape in order else Tool.HEXAGON)

    def next_stamp_number(self) -> int:
        """Siguiente número para el sello «número» en la página (sigue la cuenta tras deshacer)."""
        items = flatten([item for _, item in self.history])
        nums = [int(i.label) for i in items if isinstance(i, StampItem) and i.kind == "number" and i.label.isdigit()]
        return max(nums, default=0) + 1

    def make_stamp(self, x: float, y: float) -> StampItem:
        label = str(self.next_stamp_number()) if self.stamp_kind == "number" else ""
        return StampItem(self.stamp_kind, self.color.getRgb(), float(self.sizes[Tool.STAMP]),
                         self.opacities[Tool.STAMP] / 100.0, x, y, label)

    def insert_template(self, key: str) -> None:
        """Inserta una plantilla centrada en la pantalla donde está el cursor (un solo paso de deshacer)."""
        if key not in templates.TEMPLATES:
            return
        self._finish_all()
        if not self.visible:
            self._set_visible(True)
        ov = self.overlay_for_screen(self.current_screen()) or next(iter(self.overlays.values()), None)
        if ov is None:
            return
        if ov.zoom_active:
            ov.end_zoom()
        w, h = ov.width(), ov.height()
        area = QRectF(w * 0.08, h * 0.1, w * 0.84, h * 0.8)
        line = max(2.0, min(6.0, float(self.sizes[Tool.RECT])))
        group = templates.build(key, area, self.color.getRgb(), line)
        self.push(ov.key, group)
        ov.apply_item(group)
        # Lista para escribir: con Texto, un clic sobre cualquier rótulo lo edita.
        self.set_tool(Tool.TEXT)
        self.notify("Plantilla insertada", templates.TEMPLATES[key][0] + ". Haz clic en un texto para cambiarlo; "
                    "Ctrl+Z la quita.")

    def set_brush_type(self, bt: BrushType) -> None:
        self.brush_type = BrushType(bt)
        if self.tool != Tool.BRUSH:
            self.set_tool(Tool.BRUSH)
        self._changed(cursor=True)

    def cycle_brush_type(self) -> None:
        order = list(BRUSH_LABELS)
        nxt = order[(order.index(self.brush_type) + 1) % len(order)] if self.tool == Tool.BRUSH else self.brush_type
        self.set_brush_type(nxt)

    def set_color(self, color: QColor) -> None:
        c = QColor(color)
        c.setAlpha(255)
        self.color = c
        self._restyle_text()
        self._changed()

    def set_size(self, value: int) -> None:
        spec = TOOL_SPECS[self.tool]
        self.sizes[self.tool] = max(spec.min_size, min(spec.max_size, int(value)))
        self._restyle_text()
        self._changed(cursor=True)

    def step_size(self, direction: int) -> None:
        cur = self.sizes[self.tool]
        step = max(1, round(cur * 0.12))
        self.set_size(cur + step * (1 if direction > 0 else -1))

    def set_opacity(self, value: int) -> None:
        self.opacities[self.tool] = max(5, min(100, int(value)))
        self._restyle_text()
        self._changed()

    def step_opacity(self, direction: int) -> None:
        self.set_opacity(self.opacities[self.tool] + (5 if direction > 0 else -5))

    def set_fill(self, on: bool) -> None:
        self.fill_shapes = bool(on)
        self._changed()

    def set_text_bold(self, on: bool) -> None:
        self.text_bold = bool(on)
        self._restyle_text()
        self._changed()

    def _restyle_text(self) -> None:
        if self.text_editor is not None:
            self.text_editor.restyle_text(self.color.getRgb(), float(self.sizes[Tool.TEXT]), self.text_bold,
                                          self.opacities[Tool.TEXT] / 100.0)

    def adopt_text_style(self, item) -> None:
        """Al abrir un texto ya escrito, la barra muestra su color, tamaño, opacidad y negrita."""
        spec = TOOL_SPECS[Tool.TEXT]
        self.color = QColor(*item.rgba[:3])
        self.sizes[Tool.TEXT] = max(spec.min_size, min(spec.max_size, int(round(item.size))))
        self.opacities[Tool.TEXT] = max(5, min(100, int(round(item.opacity * 100))))
        self.text_bold = bool(item.bold)
        self._changed(cursor=True)

    # ---- fondo y pauta (de la página actual)

    @property
    def background(self) -> str:
        return self.page.background

    @background.setter
    def background(self, key: str) -> None:
        self.page.background = key

    @property
    def pattern(self) -> str:
        return self.page.pattern

    def set_background(self, key: str) -> None:
        if key in BACKGROUNDS and key != self.page.background:
            self.page.background = key
            self.dirty = True
            self._changed(repaint=True)

    def set_pattern(self, key: str) -> None:
        if key in PATTERNS and key != self.page.pattern:
            self.page.pattern = key
            self.dirty = True
            self._changed(repaint=True)

    def background_color(self, interactive: bool) -> QColor:
        b = self.background
        if b == "white":
            return QColor(255, 255, 255)
        if b == "chalk":
            return QColor(31, 58, 46)
        if b == "dim":
            return QColor(0, 0, 0, 140)
        # Transparente. En modo dibujo se usa alfa 1/255 (invisible) para que Windows
        # entregue los clics a la superposición en lugar de a la ventana de debajo.
        return QColor(0, 0, 0, 1) if interactive else QColor(0, 0, 0, 0)

    def refresh_cursor(self, ov: Overlay) -> None:
        if self.drawing:
            size = self.sizes[self.tool] * ov.zoom_factor  # con zoom el trazo se ve más grande
            if self.tool == Tool.STAMP:
                ov.setCursor(make_stamp_cursor(self.make_stamp(0, 0), size, ov.devicePixelRatioF() or 1.0))
            else:
                ov.setCursor(make_tool_cursor(self.tool, size, ov.devicePixelRatioF() or 1.0))
        else:
            ov.unsetCursor()

    def _changed(self, cursor: bool = False, repaint: bool = False) -> None:
        if cursor:
            for ov in self.overlays.values():
                self.refresh_cursor(ov)
        if repaint:
            for ov in self.overlays.values():
                ov.update()
        if self.needs_effects:
            self.ensure_ticking()
        self.state_changed.emit()
        self._update_tray()

    # ================================================================== modos

    def set_drawing(self, on: bool) -> None:
        on = bool(on)
        if on and not self.visible:
            self._set_visible(True)
        self.drawing = on
        for ov in self.overlays.values():
            ov.apply_input_mode()
        # Cambiar el modo de entrada puede reordenar las ventanas «siempre encima» y dejar
        # la barra debajo de la hoja: se vuelve a subir ahora y tras procesar ese cambio.
        self._raise_toolbar(activate=on)
        QTimer.singleShot(0, self._keep_toolbar_on_top)
        self._changed(repaint=True)

    def _keep_toolbar_on_top(self) -> None:
        if not self._shutting_down and self.toolbar.isVisible():
            self.toolbar.raise_()
        if not self._shutting_down and self.timer_visible:
            self.timer_window.raise_()

    @property
    def sheet_visible(self) -> bool:
        """La hoja de fondo (color y pauta) solo se muestra en modo «Dibujando»."""
        return self.drawing

    def toggle_drawing(self) -> None:
        self.set_drawing(not self.drawing or not self.visible)

    def _set_visible(self, on: bool) -> None:
        self.visible = on
        for ov in self.overlays.values():
            if on:
                ov.show()
            else:
                ov.finish_current()
                ov.hide()
        if on:
            self._raise_toolbar()

    def toggle_visible(self) -> None:
        if self.visible:
            for ov in self.overlays.values():
                ov.end_zoom()
            self._set_visible(False)
            self.drawing = False
        else:
            self._set_visible(True)
        self._changed()

    def escape(self) -> None:
        """Esc: primero sale del zoom o quita la selección; si no, pasa a «Ratón libre»."""
        if self.zoom_active:
            self.exit_zoom()
        elif self.has_selection:
            for ov in self.overlays.values():
                ov.clear_selection()
        else:
            self.set_drawing(False)

    # ================================================================== texto

    def begin_text_edit(self, ov: Overlay) -> None:
        if self.text_editor is not None and self.text_editor is not ov:
            self.text_editor.finish_current()
        self.text_editor = ov
        # El teclado llega a la barra (la pizarra no toma el foco); se asegura que esté activa.
        self._raise_toolbar(activate=True)

    def end_text_edit(self, ov: Overlay) -> None:
        if self.text_editor is ov:
            self.text_editor = None

    def eventFilter(self, obj, ev):  # noqa: N802 (API de Qt)
        """Mientras se escribe un texto, todas las teclas van al texto (no a los atajos)."""
        if self.text_editor is not None and ev.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            if QApplication.activeModalWidget() is not None:  # p. ej. el selector de color
                return False
            if ev.key() == Qt.Key.Key_F4 and ev.modifiers() & Qt.KeyboardModifier.AltModifier:
                return False  # Alt+F4 siempre cierra el programa, también mientras se escribe
            if ev.type() == QEvent.Type.ShortcutOverride:
                ev.accept()  # impide que la tecla dispare un atajo; llegará como pulsación
                return True
            self.text_editor.text_key(ev)
            return True
        return super().eventFilter(obj, ev)

    # ================================================================== efectos de presentación

    @property
    def needs_effects(self) -> bool:
        return self.spotlight or self.highlight or (self.tool == Tool.LASER and self.drawing and self.visible)

    def ensure_ticking(self) -> None:
        if not self._fx_timer.isActive():
            self._fx_timer.start()
            self._tick()

    @staticmethod
    def _system_buttons() -> tuple[bool, bool]:
        """(izquierdo, derecho) pulsados en todo el sistema, también sobre otras aplicaciones."""
        if winutil.IS_WINDOWS:
            return winutil.mouse_buttons()
        b = QGuiApplication.mouseButtons()
        return bool(b & Qt.MouseButton.LeftButton), bool(b & Qt.MouseButton.RightButton)

    def _tick(self) -> None:
        now = now_ms()
        gpos = QCursor.pos()
        left, right = self.button_state()
        clicks = []
        if left and not self._prev_buttons[0]:
            clicks.append("left")
        if right and not self._prev_buttons[1]:
            clicks.append("right")
        self._prev_buttons = (left, right)
        animating = False
        for ov in self.overlays.values():
            if ov.isVisible():
                animating = ov.effects_tick(now, gpos, clicks) or animating
        if not (animating or self.needs_effects):
            self._fx_timer.stop()

    def toggle_spotlight(self) -> None:
        self.spotlight = not self.spotlight
        if self.spotlight and not self.visible:
            self._set_visible(True)
        self._changed(repaint=True)

    def set_spotlight_shape(self, shape: str) -> None:
        if shape in SPOTLIGHT_SHAPES and shape != self.spotlight_shape:
            self.spotlight_shape = shape
            self._changed(repaint=True)

    def toggle_spotlight_shape(self) -> None:
        """Cambia la forma del foco (círculo ↔ rectángulo) y lo activa si estaba apagado."""
        self.set_spotlight_shape("rect" if self.spotlight_shape == "circle" else "circle")
        if not self.spotlight:
            self.toggle_spotlight()

    def step_spotlight(self, direction: int) -> None:
        r = self.spotlight_radius * (1.15 if direction > 0 else 1 / 1.15)
        self.spotlight_radius = int(max(SPOTLIGHT_MIN, min(SPOTLIGHT_MAX, r)))
        self._changed(repaint=True)

    def toggle_highlight(self) -> None:
        self.highlight = not self.highlight
        if not self.highlight:
            for ov in self.overlays.values():
                ov.clear_ripples()
        self._changed(repaint=True)

    @property
    def curtain_active(self) -> bool:
        return any(ov.curtain_y is not None for ov in self.overlays.values())

    def toggle_curtain(self) -> None:
        """Cortina sobre la pantalla del cursor; se descubre arrastrándola o con ↓ / ↑."""
        if self.curtain_active:
            for ov in self.overlays.values():
                ov.set_curtain(None)
        else:
            if not self.visible:
                self._set_visible(True)
            ov = self.overlay_for_screen(self.current_screen()) or next(iter(self.overlays.values()), None)
            if ov is not None:
                ov.set_curtain(0)
        self._changed()

    def curtain_step(self, direction: int) -> None:
        for ov in self.overlays.values():
            if ov.curtain_y is not None:
                ov.set_curtain(ov.curtain_y + direction * ov.height() * 0.1)

    # ================================================================== zoom

    @property
    def zoom_active(self) -> bool:
        return any(ov.zoom_active for ov in self.overlays.values())

    def toggle_zoom(self) -> None:
        if self.zoom_active:
            self.exit_zoom()
        else:
            self.start_zoom()

    def start_zoom(self) -> None:
        """Congela la pantalla bajo el cursor y la muestra ampliada para señalar detalles."""
        if self._capturing:
            return
        screen = self.current_screen()
        ov = self.overlay_for_screen(screen)
        if ov is None:
            return
        self._capturing = True
        self._finish_all()
        anchor = QPointF(ov.mapFromGlobal(QCursor.pos()))
        toolbar_visible = self.toolbar.isVisible()
        self.toolbar.hide()
        self._hide_timer_for_grab()
        ov.hide()
        QTimer.singleShot(CAPTURE_DELAY_MS, lambda: self._do_start_zoom(screen, ov, anchor, toolbar_visible))

    def _do_start_zoom(self, screen, ov: Overlay, anchor: QPointF, toolbar_visible: bool) -> None:
        try:
            shot = capture.grab_screen(screen)
            if shot.isNull():
                raise OSError("No se pudo capturar la pantalla")
            self.visible = True
            self.drawing = True
            ov.start_zoom(shot, anchor)
        except Exception as exc:  # pragma: no cover - errores del sistema
            log.exception("No se pudo iniciar el zoom")
            self.notify("Error al hacer zoom", str(exc), error=True)
        finally:
            for o in self.overlays.values():
                if self.visible:
                    o.show()
                    o.apply_input_mode()
            self._restore_timer_after_grab()
            if toolbar_visible or self.drawing:
                self._raise_toolbar(activate=self.drawing)
            self._capturing = False
            self._changed(cursor=True)

    def exit_zoom(self) -> None:
        for ov in self.overlays.values():
            ov.end_zoom()
        self._changed(cursor=True)

    def zoom_changed(self, ov: Overlay) -> None:
        self.state_changed.emit()

    def _raise_toolbar(self, activate: bool = False) -> None:
        if not self.toolbar.isVisible():
            self.toolbar.show()
        self.toolbar.raise_()
        if self.timer_visible:
            self.timer_window.raise_()
        if activate:
            self.toolbar.activateWindow()

    # ================================================================== páginas e historial

    @property
    def page(self) -> Page:
        return self.pages[self.page_index]

    @property
    def history(self) -> list:
        return self.page.history

    @property
    def redo_stack(self) -> list:
        return self.page.redo

    def items_for(self, key: str, exclude_uid: str | None = None):
        return self.page.items_for(key, exclude_uid)

    def push(self, key: str, item) -> None:
        self.history.append((key, item))
        self.redo_stack.clear()
        self.dirty = True

    def _rebuild(self, key: str | None) -> None:
        for k, ov in self.overlays.items():
            if key is None or key == k:
                ov.rebuild()

    def _finish_all(self) -> None:
        for ov in self.overlays.values():
            ov.finish_current()
            ov.clear_selection()

    # ---- selección (herramienta Seleccionar)

    def selection_overlay(self) -> Overlay | None:
        return next((ov for ov in self.overlays.values() if ov.selection), None)

    def selection_changed(self) -> None:
        self.state_changed.emit()

    @property
    def has_selection(self) -> bool:
        return self.selection_overlay() is not None

    def delete_selection(self) -> bool:
        ov = self.selection_overlay()
        if ov is None:
            return False
        uids = list(ov.selection)
        ov.clear_selection()
        self.push(ov.key, DeleteItem(uids))
        ov.rebuild()
        return True

    def duplicate_selection(self) -> bool:
        ov = self.selection_overlay()
        if ov is None:
            return False
        uids = [i.uid for i in ov.selected_items()]
        new = [uuid.uuid4().hex for _ in uids]
        ov.clear_selection()
        self.push(ov.key, DuplicateItem(uids, new))
        ov.rebuild()
        ov.set_selection(new)  # la copia queda seleccionada, lista para moverla
        return True

    def select_all(self) -> None:
        if self.tool != Tool.SELECT:
            self.set_tool(Tool.SELECT)
        ov = self.overlay_for_screen(self.current_screen()) or next(iter(self.overlays.values()), None)
        if ov is not None:
            ov.select_all()

    # ---- pegar (Ctrl+V)

    def paste(self) -> bool:
        """Pega lo que haya en el portapapeles: una imagen (o un archivo de imagen) o un texto.

        Se coloca centrado en el cursor y queda seleccionado para moverlo o cambiar su tamaño.
        """
        self._finish_all()
        mime = QGuiApplication.clipboard().mimeData()
        img = QImage()
        if mime is not None and mime.hasImage():
            img = QImage(mime.imageData())
        if img.isNull() and mime is not None and mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    candidate = QImage(url.toLocalFile())
                    if not candidate.isNull():
                        img = candidate
                        break
        if not img.isNull():
            return self.paste_image(img)
        text = mime.text().replace("\r\n", "\n").replace("\r", "\n").strip() if mime is not None else ""
        if text:
            return self.paste_text(text)
        self.notify("Nada que pegar", "Copia una imagen o un texto y vuelve a pulsar Ctrl+V.")
        return False

    def _paste_target(self) -> tuple[Overlay | None, QPointF]:
        ov = self.overlay_for_screen(self.current_screen()) or next(iter(self.overlays.values()), None)
        if ov is None:
            return None, QPointF()
        if not self.visible:
            self._set_visible(True)
        if ov.zoom_active:
            ov.end_zoom()
        local = QPointF(ov.mapFromGlobal(QCursor.pos()))
        if not QRectF(ov.rect()).contains(local):
            local = QPointF(ov.width() / 2, ov.height() / 2)
        return ov, local

    def paste_image(self, img: QImage) -> bool:
        ov, at = self._paste_target()
        if ov is None or img.isNull():
            return False
        dpr = ov.devicePixelRatioF() or 1.0
        # Tamaño natural en la pantalla, reducido si no cabe en la mitad de ella
        w, h = img.width() / dpr, img.height() / dpr
        k = min(1.0, ov.width() * 0.5 / max(w, 1), ov.height() * 0.5 / max(h, 1))
        w, h = max(8.0, w * k), max(8.0, h * k)
        # Se guarda a la resolución necesaria (no más), para que las sesiones no pesen de más
        need_w = max(1, round(w * dpr * 2))
        if img.width() > need_w:
            img = img.scaledToWidth(need_w, Qt.TransformationMode.SmoothTransformation)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        x = max(0.0, min(ov.width() - w, at.x() - w / 2))
        y = max(0.0, min(ov.height() - h, at.y() - h / 2))
        item = ImageItem(bytes(buf.data()), x, y, w, h)
        self.push(ov.key, item)
        ov.apply_item(item)
        self.set_tool(Tool.SELECT)
        ov.set_selection([item.uid])
        return True

    def paste_text(self, text: str) -> bool:
        ov, at = self._paste_target()
        if ov is None:
            return False
        item = TextItem(self.color.getRgb(), float(self.sizes[Tool.TEXT]), self.opacities[Tool.TEXT] / 100.0,
                        at.x(), at.y(), "".join(ch for ch in text if ch == "\n" or ch.isprintable()), self.text_bold)
        self.push(ov.key, item)
        ov.apply_item(item)
        self.set_tool(Tool.SELECT)
        ov.set_selection([item.uid])
        return True

    def delete_key(self) -> None:
        """Supr: borra la selección si la hay; si no, la página (como antes)."""
        if not self.delete_selection():
            self.clear_all()

    def undo(self) -> None:
        self._finish_all()
        if not self.history:
            return
        key, item = self.history.pop()
        self.redo_stack.append((key, item))
        self.dirty = True
        self._rebuild(key)
        if self.tool == Tool.STAMP:  # el cursor muestra el siguiente número
            self._changed(cursor=True)

    def redo(self) -> None:
        self._finish_all()
        if not self.redo_stack:
            return
        key, item = self.redo_stack.pop()
        self.history.append((key, item))
        self.dirty = True
        if self.tool == Tool.STAMP:
            self._changed(cursor=True)
        if isinstance(item, (TextEditItem, TransformItem, DeleteItem, DuplicateItem)):
            # Cambian elementos ya dibujados (editar, mover, eliminar, duplicar): hay que redibujar
            self._rebuild(key)
            return
        for k, ov in self.overlays.items():
            if key is None or key == k:
                ov.apply_item(item)

    def clear_all(self) -> None:
        self._finish_all()
        if not self.history or isinstance(self.history[-1][1], ClearItem):
            return
        self.push(None, ClearItem())
        for ov in self.overlays.values():
            ov.apply_item(ClearItem())

    def go_to_page(self, index: int) -> None:
        self._finish_all()
        index = max(0, min(len(self.pages) - 1, index))
        if index == self.page_index:
            return
        self.page_index = index
        self._rebuild(None)
        self._changed(repaint=True)

    def next_page(self) -> None:
        self.go_to_page(self.page_index + 1)

    def prev_page(self) -> None:
        self.go_to_page(self.page_index - 1)

    def new_page(self) -> None:
        """Página nueva en blanco a continuación de la actual (hereda fondo y pauta)."""
        self._finish_all()
        self.pages.insert(self.page_index + 1, Page(background=self.page.background, pattern=self.page.pattern))
        self.dirty = True
        self.go_to_page(self.page_index + 1)

    def delete_page(self) -> None:
        self._finish_all()
        if len(self.pages) == 1:
            self.pages[0] = Page(background=self.page.background, pattern=self.page.pattern)
        else:
            del self.pages[self.page_index]
            self.page_index = min(self.page_index, len(self.pages) - 1)
        self.dirty = True
        self._rebuild(None)
        self._changed(repaint=True)

    def confirm_delete_page(self) -> None:
        if self.page.has_content():
            answer = QMessageBox.question(
                self.toolbar, "Eliminar página",
                f"¿Eliminar la página {self.page_index + 1} y todo lo dibujado en ella?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.delete_page()

    # ================================================================== sesiones y PDF

    def _ask_path(self, title: str, filt: str, default_name: str, save: bool) -> str | None:
        folder = os.path.dirname(self.session_path) if self.session_path else documents_dir()
        if save:
            path, _ = QFileDialog.getSaveFileName(self.toolbar, title, os.path.join(folder, default_name), filt)
        else:
            path, _ = QFileDialog.getOpenFileName(self.toolbar, title, folder, filt)
        return path or None

    def _session_name(self) -> str:
        return os.path.splitext(os.path.basename(self.session_path))[0] if self.session_path else "Clase"

    def save_session(self, path: str | None = None, ask: bool = False) -> bool:
        self._finish_all()
        if path is None and (ask or not self.session_path):
            path = self._ask_path("Guardar sesión", "Sesión de Pizarra Virtual (*.pizarra)",
                                  self._session_name() + session.FILE_EXTENSION, save=True)
            if not path:
                return False
        path = path or self.session_path
        try:
            self.session_path = session.save_session(path, self.pages, self.screen_keys())
        except OSError as exc:
            log.exception("No se pudo guardar la sesión")
            self._error("No se pudo guardar la sesión", str(exc))
            return False
        self.dirty = False
        self.notify("Sesión guardada", self.session_path)
        self._changed()
        return True

    def open_session(self, path: str | None = None) -> bool:
        self._finish_all()
        if not self.confirm_discard("abrir otra sesión"):
            return False
        path = path or self._ask_path("Abrir sesión", "Sesión de Pizarra Virtual (*.pizarra)", "", save=False)
        if not path:
            return False
        try:
            pages = session.load_session(path, self.screen_keys())
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.exception("No se pudo abrir la sesión")
            self._error("No se pudo abrir la sesión", f"{path}\n\n{exc}")
            return False
        self.pages = pages
        self.page_index = 0
        self.session_path = path
        self.dirty = False
        self._rebuild(None)
        self._changed(repaint=True)
        return True

    def page_images(self) -> list:
        """Una imagen por página (y por pantalla con dibujos) para el PDF."""
        images = []
        keys = self.screen_keys()
        for page in self.pages:
            used = [k for k in keys if any(key == k for key, _ in page.history)] or keys[:1]
            for key in used:
                ov = self.overlays[key]
                items = page.items_for(key)
                images.append(session.render_page(page, items, ov.width(), ov.height()))
        return images

    def export_pdf(self, path: str | None = None) -> str | None:
        self._finish_all()
        path = path or self._ask_path("Exportar a PDF", "Documento PDF (*.pdf)", self._session_name() + ".pdf",
                                      save=True)
        if not path:
            return None
        try:
            out = session.export_pdf(path, self.page_images(), title=self._session_name())
        except OSError as exc:
            log.exception("No se pudo exportar el PDF")
            self._error("No se pudo exportar el PDF", str(exc))
            return None
        self.notify("PDF exportado", out)
        return out

    def confirm_discard(self, action: str) -> bool:
        """Si hay cambios sin guardar pregunta si guardarlos. False = cancelar la acción."""
        if not self.dirty or not any(pg.has_content() for pg in self.pages):
            return True
        box = QMessageBox(QMessageBox.Icon.Question, "Pizarra Virtual",
                          f"Hay cambios sin guardar. ¿Quieres guardarlos antes de {action}?",
                          QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                          | QMessageBox.StandardButton.Cancel, self.toolbar)
        box.button(QMessageBox.StandardButton.Save).setText("Guardar")
        box.button(QMessageBox.StandardButton.Discard).setText("No guardar")
        box.button(QMessageBox.StandardButton.Cancel).setText("Cancelar")
        answer = box.exec()
        if answer == QMessageBox.StandardButton.Save:
            return self.save_session()
        return answer == QMessageBox.StandardButton.Discard

    def _error(self, title: str, text: str) -> None:
        QMessageBox.warning(self.toolbar, title, text)

    # ================================================================== capturas

    def build_capture_menu(self, parent, icon_color: str = icons.FG) -> QMenu:
        menu = QMenu(parent)
        opts = [
            ("Pantalla actual con trazado\tCtrl+Alt+S", True, False),
            ("Pantalla actual sin trazado\tCtrl+Alt+Shift+S", False, False),
            ("Todas las pantallas con trazado", True, True),
            ("Todas las pantallas sin trazado", False, True),
        ]
        for text, with_drawing, all_screens in opts:
            act = QAction(icons.icon("camera", icon_color), text, menu)
            act.triggered.connect(lambda _=False, w=with_drawing, a=all_screens: self.capture(w, a))
            menu.addAction(act)
        menu.addSeparator()
        folder = QAction(icons.icon("folder", icon_color), "Abrir carpeta de capturas", menu)
        folder.triggered.connect(self.open_captures_folder)
        menu.addAction(folder)
        return menu

    def build_file_menu(self, parent, icon_color: str = icons.FG) -> QMenu:
        menu = QMenu(parent)
        entries = [
            ("folder", "Abrir sesión…\tCtrl+O", self.open_session),
            ("save", "Guardar sesión\tCtrl+S", lambda: self.save_session()),
            ("save", "Guardar sesión como…\tCtrl+Shift+S", lambda: self.save_session(ask=True)),
            ("pdf", "Exportar a PDF…\tCtrl+P", self.export_pdf),
        ]
        for icon_name, text, fn in entries:
            act = QAction(icons.icon(icon_name, icon_color), text, menu)
            act.triggered.connect(lambda _=False, f=fn: f())
            menu.addAction(act)
        menu.addSeparator()
        act = QAction(icons.icon("trash", icon_color), "Eliminar esta página…", menu)
        act.triggered.connect(self.confirm_delete_page)
        menu.addAction(act)
        act = QAction(icons.icon("folder", icon_color), "Abrir carpeta de capturas", menu)
        act.triggered.connect(self.open_captures_folder)
        menu.addAction(act)
        return menu

    def capture(self, with_drawing: bool = True, all_screens: bool = False) -> None:
        """Oculta la pizarra, captura la pantalla y guarda el PNG en «Capturas Pizarra»."""
        if self._capturing:
            return
        self._capturing = True
        self._finish_all()
        screens = list(QGuiApplication.screens()) if all_screens else [self.current_screen()]
        restore = (self.visible, self.toolbar.isVisible())
        self.toolbar.hide()
        self._hide_timer_for_grab()
        for ov in self.overlays.values():
            ov.hide()
        QTimer.singleShot(CAPTURE_DELAY_MS, lambda: self._do_capture(screens, with_drawing, restore))

    def _do_capture(self, screens, with_drawing: bool, restore) -> None:
        try:
            parts = []
            for s in screens:
                ov = self.overlay_for_screen(s)
                if ov is not None and ov.zoom_active:
                    # En zoom se guarda exactamente la vista ampliada.
                    shot = ov.render_view(with_drawing)
                else:
                    shot = capture.grab_screen(s)
                    if with_drawing:
                        sheet = self.sheet_visible  # lo mismo que se ve en pantalla
                        shot = capture.compose_drawing(shot, ov.canvas if ov else None,
                                                       self.background_color(interactive=False) if sheet
                                                       else QColor(0, 0, 0, 0),
                                                       ov.pattern_image() if ov and sheet else None)
                parts.append((s.geometry(), shot))
            img = capture.stitch(parts)
            path = capture.save_capture(img)
            self.last_capture = path
            QGuiApplication.clipboard().setImage(img)
            self.notify("Captura guardada", f"{path}\n(También se copió al portapapeles)")
            log.info("Captura guardada en %s", path)
        except Exception as exc:  # pragma: no cover - errores de E/S del sistema
            log.exception("Error al capturar la pantalla")
            self.notify("Error al capturar", str(exc), error=True)
        finally:
            was_visible, toolbar_visible = restore
            if was_visible:
                for ov in self.overlays.values():
                    ov.show()
            self._restore_timer_after_grab()
            if toolbar_visible:
                self._raise_toolbar(activate=self.drawing)
            self._capturing = False

    def _hide_timer_for_grab(self) -> None:
        """El temporizador no debe salir en las capturas ni quedar congelado dentro del zoom."""
        self._timer_was_visible = self.timer_visible
        if self._timer_was_visible:
            self.timer_window.hide()

    def _restore_timer_after_grab(self) -> None:
        if getattr(self, "_timer_was_visible", False) and self.timer_window is not None:
            self.timer_window.show()
            self.timer_window.raise_()
        self._timer_was_visible = False

    def open_captures_folder(self) -> None:
        try:
            winutil.open_folder(capture.captures_dir())
        except Exception as exc:  # pragma: no cover
            log.exception("No se pudo abrir la carpeta de capturas")
            self.notify("Error", str(exc), error=True)

    # ================================================================== bandeja / ayuda

    def _build_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(icons.app_icon(), self)
        tray.setToolTip(f"Pizarra Virtual {__version__}")
        menu = QMenu()
        self._tray_draw = QAction("Modo dibujo\tCtrl+Alt+D", menu, checkable=True)
        self._tray_draw.triggered.connect(lambda c: self.set_drawing(c))
        self._tray_visible = QAction("Mostrar pizarra\tCtrl+Alt+H", menu, checkable=True)
        self._tray_visible.triggered.connect(lambda _c: self.toggle_visible())
        self._tray_spot = QAction("Foco\tCtrl+Alt+F", menu, checkable=True)
        self._tray_spot.triggered.connect(lambda _c: self.toggle_spotlight())
        self._tray_spot_rect = QAction("Foco rectangular\tShift+F", menu, checkable=True)
        self._tray_spot_rect.triggered.connect(lambda on: self.set_spotlight_shape("rect" if on else "circle"))
        self._tray_highlight = QAction("Resaltar cursor y clics\tCtrl+Alt+M", menu, checkable=True)
        self._tray_highlight.triggered.connect(lambda _c: self.toggle_highlight())
        for act in (self._tray_draw, self._tray_visible, self._tray_spot, self._tray_spot_rect, self._tray_highlight):
            menu.addAction(act)
        zoom_act = QAction("Zoom de pantalla\tCtrl+Alt+Z", menu)
        zoom_act.triggered.connect(self.toggle_zoom)
        menu.addAction(zoom_act)
        menu.addSeparator()
        cap_menu = self.build_capture_menu(menu, icon_color="#444444")
        cap_menu.setTitle("Captura de pantalla")
        cap_menu.setIcon(icons.icon("camera", "#444444"))
        menu.addMenu(cap_menu)
        file_menu = self.build_file_menu(menu, icon_color="#444444")
        file_menu.setTitle("Sesión y PDF")
        menu.addMenu(file_menu)
        clear = QAction("Borrar todo", menu)
        clear.triggered.connect(self.clear_all)
        menu.addAction(clear)
        menu.addSeparator()
        help_act = QAction("Ayuda y atajos…", menu)
        help_act.triggered.connect(self.show_help)
        menu.addAction(help_act)
        manual_act = QAction("Manual de usuario", menu)
        manual_act.triggered.connect(self.open_manual)
        menu.addAction(manual_act)
        quit_act = QAction("Salir", menu)
        quit_act.triggered.connect(self.quit)
        menu.addAction(quit_act)
        tray.setContextMenu(menu)
        self._tray_menu = menu
        tray.activated.connect(self._on_tray_activated)
        tray.messageClicked.connect(self._on_message_clicked)
        return tray

    def _update_tray(self) -> None:
        if self.tray is None:
            return
        self._tray_draw.setChecked(self.drawing and self.visible)
        self._tray_visible.setChecked(self.visible)
        self._tray_spot.setChecked(self.spotlight)
        self._tray_spot_rect.setChecked(self.spotlight_shape == "rect")
        self._tray_highlight.setChecked(self.highlight)

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_drawing()

    def _on_message_clicked(self) -> None:
        if self.last_capture:
            self.open_captures_folder()

    def notify(self, title: str, message: str, error: bool = False) -> None:
        if self.tray is not None and self.tray.isVisible():
            icon = QSystemTrayIcon.MessageIcon.Critical if error else QSystemTrayIcon.MessageIcon.Information
            self.tray.showMessage(title, message, icon, 4000)
        else:
            log.info("%s: %s", title, message)

    def show_help(self) -> None:
        box = QMessageBox(self.toolbar)
        box.setWindowTitle("Pizarra Virtual — ayuda")
        box.setIconPixmap(icons.app_icon().pixmap(64, 64))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(HELP_HTML.format(version=__version__, folder=capture.captures_dir()))
        box.exec()

    def open_manual(self) -> None:
        path = manual_path()
        if path is None:
            self._error("Manual de usuario",
                        f"No se encontró «{MANUAL_NAME}» junto al programa.\n"
                        "Está incluido en el archivo .zip de cada versión publicada.")
            return
        try:
            winutil.open_file(path)
        except Exception as exc:  # pragma: no cover
            self._error("Manual de usuario", str(exc))

    # ================================================================== ajustes

    def _load_settings(self) -> None:
        s = self.settings
        try:
            self.tool = Tool(s.value("tool", self.tool.value))
            if self.tool == Tool.LASER:
                self.tool = Tool.BRUSH  # al arrancar no se oculta el cursor
            self.brush_type = BrushType(s.value("brush", self.brush_type.value))
            col = QColor(str(s.value("color", DEFAULT_COLOR)))
            if col.isValid():
                self.color = col
            for key, store in (("sizes", self.sizes), ("opacities", self.opacities)):
                raw = s.value(key)
                if raw:
                    for k, v in json.loads(str(raw)).items():
                        if k in Tool._value2member_map_:
                            spec = TOOL_SPECS[Tool(k)]
                            lo, hi = (spec.min_size, spec.max_size) if key == "sizes" else (5, 100)
                            store[Tool(k)] = max(lo, min(hi, int(v)))
            self.fill_shapes = str(s.value("fill", "false")).lower() == "true"
            self.text_bold = str(s.value("text_bold", "false")).lower() == "true"
            self.recognize_shapes = str(s.value("recognize_shapes", "false")).lower() == "true"
            kind = str(s.value("stamp_kind", "check"))
            self.stamp_kind = kind if kind in STAMPS else "check"
            extra = str(s.value("extra_shape", Tool.HEXAGON.value))
            self.extra_shape = Tool(extra) if extra in Tool._value2member_map_ and Tool(extra) in EXTRA_SHAPES \
                else Tool.HEXAGON
            bg = str(s.value("background", "transparent"))
            self.page.background = bg if bg in BACKGROUNDS else "transparent"
            pat = str(s.value("pattern", "none"))
            self.page.pattern = pat if pat in PATTERNS else "none"
            self.spotlight_radius = max(SPOTLIGHT_MIN, min(SPOTLIGHT_MAX, int(s.value("spotlight_radius",
                                                                                    SPOTLIGHT_DEFAULT))))
            shape = str(s.value("spotlight_shape", "circle"))
            self.spotlight_shape = shape if shape in SPOTLIGHT_SHAPES else "circle"
        except Exception:  # ajustes corruptos: se usan los valores por defecto
            log.exception("Ajustes no válidos; se usan los valores por defecto")

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("tool", self.tool.value)
        s.setValue("brush", self.brush_type.value)
        s.setValue("color", self.color.name())
        s.setValue("sizes", json.dumps({t.value: v for t, v in self.sizes.items()}))
        s.setValue("opacities", json.dumps({t.value: v for t, v in self.opacities.items()}))
        s.setValue("fill", "true" if self.fill_shapes else "false")
        s.setValue("text_bold", "true" if self.text_bold else "false")
        s.setValue("stamp_kind", self.stamp_kind)
        s.setValue("recognize_shapes", "true" if self.recognize_shapes else "false")
        s.setValue("extra_shape", self.extra_shape.value)
        s.setValue("background", self.background)
        s.setValue("pattern", self.pattern)
        s.setValue("spotlight_radius", self.spotlight_radius)
        s.setValue("spotlight_shape", self.spotlight_shape)
        s.sync()


HELP_HTML = """
<h3>Pizarra Virtual {version}</h3>
<p>Dibuja encima de cualquier ventana. Pulsa <b>Ctrl+Alt+D</b> para alternar entre
<i>Dibujando</i> y <i>Ratón libre</i> (los clics llegan a las ventanas de debajo).
El <b>Manual de usuario</b> (PDF) explica todas las funciones.</p>
<table cellspacing="0" cellpadding="2">
<tr><td colspan="2"><b>Atajos globales</b> (desde cualquier aplicación)</td></tr>
<tr><td><b>Ctrl+Alt+D</b></td><td>Activar / desactivar el dibujo</td></tr>
<tr><td><b>Ctrl+Alt+H</b></td><td>Mostrar / ocultar la pizarra</td></tr>
<tr><td><b>Ctrl+Alt+Z</b></td><td>Zoom de la zona bajo el cursor</td></tr>
<tr><td><b>Ctrl+Alt+F</b></td><td>Foco (oscurece todo menos el cursor)</td></tr>
<tr><td><b>Ctrl+Alt+M</b></td><td>Resaltar el cursor y los clics</td></tr>
<tr><td><b>Ctrl+Alt+S</b> / <b>+Shift</b></td><td>Captura con / sin trazado</td></tr>
<tr><td colspan="2"><br><b>Herramientas</b> (en modo dibujo)</td></tr>
<tr><td><b>1</b> … <b>5</b></td><td>Pincel, Lápiz, Pluma, Destacador, Goma</td></tr>
<tr><td><b>6</b> … <b>0</b></td><td>Rectángulo, Elipse, Triángulo, Línea, Flecha</td></tr>
<tr><td><b>T</b> / <b>L</b></td><td>Texto / Puntero láser con tinta temporal</td></tr>
<tr><td><b>P</b> · <b>D</b> · <b>E</b> · <b>Q</b></td><td>Polígonos · Rombo · Estrella · Rectángulo redondeado</td></tr>
<tr><td><b>J</b> · <b>W</b> · <b>U</b> · <b>K</b></td><td>Ejes · Flecha doble · Flecha curva · Llave</td></tr>
<tr><td><b>S</b></td><td>Sellos (otra vez S: siguiente sello) · Plantillas: botón de la barra</td></tr>
<tr><td><b>B</b> · <b>R</b> · <b>C</b></td><td>Tipo de pincel · Relleno de figuras · Color</td></tr>
<tr><td><b>+ / -</b> o rueda</td><td>Grosor (tamaño de letra con Texto)</td></tr>
<tr><td><b>Mayús + rueda</b></td><td>Opacidad</td></tr>
<tr><td><b>Ctrl+Z / Ctrl+Y</b> · <b>Supr</b></td><td>Deshacer / rehacer · Borrar la página</td></tr>
<tr><td colspan="2"><br><b>Presentación</b></td></tr>
<tr><td><b>F</b> · <b>V</b> · <b>M</b></td><td>Foco · Cortina · Resaltar cursor y clics</td></tr>
<tr><td><b>↓ / ↑</b></td><td>Descubrir / cubrir con la cortina</td></tr>
<tr><td><b>Alt + rueda</b></td><td>Tamaño del foco</td></tr>
<tr><td><b>Mayús+F</b></td><td>Foco en círculo o en rectángulo</td></tr>
<tr><td><b>Z</b> · <b>Esc</b></td><td>Zoom · Salir del zoom o pasar a «Ratón libre»</td></tr>
<tr><td colspan="2"><br><b>Páginas y archivos</b></td></tr>
<tr><td><b>AvPág / RePág</b> · <b>N</b></td><td>Página siguiente / anterior · Página nueva</td></tr>
<tr><td><b>Ctrl+S</b> · <b>Ctrl+O</b> · <b>Ctrl+P</b></td><td>Guardar · Abrir sesión · Exportar a PDF</td></tr>
<tr><td colspan="2"><br><b>Escribiendo texto</b>: Intro = nueva línea · Esc o clic fuera = terminar ·
Ctrl+V = pegar · flechas, Inicio y Fin = mover el cursor<br>
<b>Clic sobre un texto ya escrito</b> = editarlo (arrástralo para moverlo)</td></tr>
</table>
<p>Las capturas se guardan en:<br><code>{folder}</code></p>
"""
