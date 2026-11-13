"""Controlador principal: estado de herramientas, historial, ventanas, bandeja y atajos."""
from __future__ import annotations

import json
import logging

from PySide6.QtCore import QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, capture, icons, winutil
from .hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, GlobalHotkeys
from .items import ClearItem
from .overlay import Overlay, make_tool_cursor
from .toolbar import Toolbar
from .tools import BACKGROUNDS, BRUSH_LABELS, DEFAULT_COLOR, TOOL_SPECS, BrushType, Tool

log = logging.getLogger(__name__)

CAPTURE_DELAY_MS = 250  # tiempo para que Windows retire la superposición antes de capturar

VK_D, VK_H, VK_S = 0x44, 0x48, 0x53


def screen_key(screen) -> str:
    return screen.name() or f"screen-{id(screen)}"


class Controller(QObject):
    state_changed = Signal()

    def __init__(self, app: QApplication, settings: QSettings | None = None,
                 enable_hotkeys: bool = True, enable_tray: bool = True):
        super().__init__()
        self.app = app
        self.settings = settings or QSettings("PizarraVirtual", "PizarraVirtual")

        # Estado de herramientas
        self.tool = Tool.BRUSH
        self.brush_type = BrushType.HARD
        self.color = QColor(DEFAULT_COLOR)
        self.sizes = {t: s.default_size for t, s in TOOL_SPECS.items()}
        self.opacities = {t: s.default_opacity for t, s in TOOL_SPECS.items()}
        self.fill_shapes = False
        self.background = "transparent"
        self._load_settings()

        # Estado de la aplicación
        self.drawing = True
        self.visible = True
        self._capturing = False
        self.history: list[tuple[str | None, object]] = []
        self.redo_stack: list[tuple[str | None, object]] = []
        self.overlays: dict[str, Overlay] = {}
        self.last_capture: str | None = None

        self.toolbar = Toolbar(self)
        self.hotkeys = GlobalHotkeys(self) if enable_hotkeys else None
        self.tray = self._build_tray() if enable_tray and QSystemTrayIcon.isSystemTrayAvailable() else None

        for s in QGuiApplication.screens():
            self._add_screen(s)
        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(self._remove_screen)
        self.state_changed.connect(self.toolbar.sync)

    # ================================================================== arranque / salida

    def start(self) -> None:
        for ov in self.overlays.values():
            ov.show()
        self.toolbar.restore_position()
        self.toolbar.show()
        self._raise_toolbar(activate=True)
        failed = self._register_hotkeys()
        if self.tray is not None:
            self.tray.show()
            msg = "Ctrl+Alt+D activa/desactiva el dibujo. Ctrl+Alt+H oculta la pizarra."
            if failed:
                msg += "\nNo se pudieron registrar: " + ", ".join(failed) + " (en uso por otra app)."
            self.notify("Pizarra Virtual activa", msg)

    def quit(self) -> None:
        for ov in self.overlays.values():
            ov.finish_current()
        self.toolbar.save_position()
        self._save_settings()
        if self.hotkeys is not None:
            self.hotkeys.unregister_all()
        if self.tray is not None:
            self.tray.hide()
        for ov in list(self.overlays.values()):
            ov.close()
        self.toolbar.close()
        self.app.quit()

    def _register_hotkeys(self) -> list[str]:
        if self.hotkeys is None or not self.hotkeys.available:
            return []
        combos = [
            (MOD_CONTROL | MOD_ALT, VK_D, "Ctrl+Alt+D", self.toggle_drawing),
            (MOD_CONTROL | MOD_ALT, VK_H, "Ctrl+Alt+H", self.toggle_visible),
            (MOD_CONTROL | MOD_ALT, VK_S, "Ctrl+Alt+S", lambda: self.capture(with_drawing=True)),
            (MOD_CONTROL | MOD_ALT | MOD_SHIFT, VK_S, "Ctrl+Alt+Shift+S",
             lambda: self.capture(with_drawing=False)),
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

    # ================================================================== herramientas

    def size_for(self, tool: Tool) -> int:
        return self.sizes[tool]

    def opacity_for(self, tool: Tool) -> int:
        return self.opacities[tool]

    def set_tool(self, tool: Tool) -> None:
        self.tool = Tool(tool)
        if not self.drawing:
            self.set_drawing(True)
        self._changed(cursor=True)

    def set_brush_type(self, bt: BrushType) -> None:
        self.brush_type = BrushType(bt)
        if self.tool != Tool.BRUSH:
            self.tool = Tool.BRUSH
        self._changed(cursor=True)

    def cycle_brush_type(self) -> None:
        order = list(BRUSH_LABELS)
        nxt = order[(order.index(self.brush_type) + 1) % len(order)] if self.tool == Tool.BRUSH else self.brush_type
        self.set_brush_type(nxt)

    def set_color(self, color: QColor) -> None:
        c = QColor(color)
        c.setAlpha(255)
        self.color = c
        self._changed()

    def set_size(self, value: int) -> None:
        spec = TOOL_SPECS[self.tool]
        self.sizes[self.tool] = max(spec.min_size, min(spec.max_size, int(value)))
        self._changed(cursor=True)

    def step_size(self, direction: int) -> None:
        cur = self.sizes[self.tool]
        step = max(1, round(cur * 0.12))
        self.set_size(cur + step * (1 if direction > 0 else -1))

    def set_opacity(self, value: int) -> None:
        self.opacities[self.tool] = max(5, min(100, int(value)))
        self._changed()

    def step_opacity(self, direction: int) -> None:
        self.set_opacity(self.opacities[self.tool] + (5 if direction > 0 else -5))

    def set_fill(self, on: bool) -> None:
        self.fill_shapes = bool(on)
        self._changed()

    def set_background(self, key: str) -> None:
        if key in BACKGROUNDS:
            self.background = key
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
            ov.setCursor(make_tool_cursor(self.tool, self.sizes[self.tool], ov.devicePixelRatioF() or 1.0))
        else:
            ov.unsetCursor()

    def _changed(self, cursor: bool = False, repaint: bool = False) -> None:
        if cursor:
            for ov in self.overlays.values():
                self.refresh_cursor(ov)
        if repaint:
            for ov in self.overlays.values():
                ov.update()
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
        if on:
            self._raise_toolbar(activate=True)
        self._changed()

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
            self._set_visible(False)
            self.drawing = False
        else:
            self._set_visible(True)
        self._changed()

    def _raise_toolbar(self, activate: bool = False) -> None:
        if not self.toolbar.isVisible():
            self.toolbar.show()
        self.toolbar.raise_()
        if activate:
            self.toolbar.activateWindow()

    # ================================================================== historial

    def items_for(self, key: str):
        return [item for k, item in self.history if k is None or k == key]

    def push(self, key: str, item) -> None:
        self.history.append((key, item))
        self.redo_stack.clear()

    def _rebuild(self, key: str | None) -> None:
        for k, ov in self.overlays.items():
            if key is None or key == k:
                ov.rebuild()

    def _finish_all(self) -> None:
        for ov in self.overlays.values():
            ov.finish_current()

    def undo(self) -> None:
        self._finish_all()
        if not self.history:
            return
        key, item = self.history.pop()
        self.redo_stack.append((key, item))
        self._rebuild(key)

    def redo(self) -> None:
        self._finish_all()
        if not self.redo_stack:
            return
        key, item = self.redo_stack.pop()
        self.history.append((key, item))
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

    def capture(self, with_drawing: bool = True, all_screens: bool = False) -> None:
        """Oculta la pizarra, captura la pantalla y guarda el PNG en «Capturas Pizarra»."""
        if self._capturing:
            return
        self._capturing = True
        self._finish_all()
        screens = list(QGuiApplication.screens()) if all_screens else [self.current_screen()]
        restore = (self.visible, self.toolbar.isVisible())
        self.toolbar.hide()
        for ov in self.overlays.values():
            ov.hide()
        QTimer.singleShot(CAPTURE_DELAY_MS, lambda: self._do_capture(screens, with_drawing, restore))

    def _do_capture(self, screens, with_drawing: bool, restore) -> None:
        try:
            parts = []
            for s in screens:
                shot = capture.grab_screen(s)
                if with_drawing:
                    ov = self.overlay_for_screen(s)
                    shot = capture.compose_drawing(shot, ov.canvas if ov else None,
                                                   self.background_color(interactive=False))
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
            if toolbar_visible:
                self._raise_toolbar(activate=self.drawing)
            self._capturing = False

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
        menu.addAction(self._tray_draw)
        menu.addAction(self._tray_visible)
        menu.addSeparator()
        cap_menu = self.build_capture_menu(menu, icon_color="#444444")
        cap_menu.setTitle("Captura de pantalla")
        cap_menu.setIcon(icons.icon("camera", "#444444"))
        menu.addMenu(cap_menu)
        clear = QAction("Borrar todo", menu)
        clear.triggered.connect(self.clear_all)
        menu.addAction(clear)
        menu.addSeparator()
        help_act = QAction("Ayuda y atajos…", menu)
        help_act.triggered.connect(self.show_help)
        menu.addAction(help_act)
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

    # ================================================================== ajustes

    def _load_settings(self) -> None:
        s = self.settings
        try:
            self.tool = Tool(s.value("tool", self.tool.value))
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
            bg = str(s.value("background", "transparent"))
            self.background = bg if bg in BACKGROUNDS else "transparent"
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
        s.setValue("background", self.background)
        s.sync()


HELP_HTML = """
<h3>Pizarra Virtual {version}</h3>
<p>Dibuja encima de cualquier ventana. Pulsa <b>Ctrl+Alt+D</b> para alternar entre
<i>Dibujando</i> y <i>Ratón libre</i> (los clics llegan a las ventanas de debajo).</p>
<table cellspacing="0" cellpadding="3">
<tr><td colspan="2"><b>Atajos globales</b> (funcionan desde cualquier aplicación)</td></tr>
<tr><td><b>Ctrl+Alt+D</b></td><td>Activar / desactivar el dibujo</td></tr>
<tr><td><b>Ctrl+Alt+H</b></td><td>Mostrar / ocultar la pizarra</td></tr>
<tr><td><b>Ctrl+Alt+S</b></td><td>Captura de la pantalla actual con el trazado</td></tr>
<tr><td><b>Ctrl+Alt+Shift+S</b></td><td>Captura de la pantalla actual sin el trazado</td></tr>
<tr><td colspan="2"><br><b>Herramientas</b> (en modo dibujo)</td></tr>
<tr><td><b>1</b> … <b>5</b></td><td>Pincel, Lápiz, Pluma, Destacador, Goma</td></tr>
<tr><td><b>6</b> … <b>0</b></td><td>Rectángulo, Elipse, Triángulo, Línea, Flecha</td></tr>
<tr><td><b>B</b></td><td>Cambiar tipo de pincel (duro, suave, aerógrafo, caligráfico)</td></tr>
<tr><td><b>F</b></td><td>Figuras rellenas sí/no</td></tr>
<tr><td><b>C</b></td><td>Elegir color</td></tr>
<tr><td><b>+ / -</b> o rueda</td><td>Aumentar / reducir grosor</td></tr>
<tr><td><b>Mayús + rueda</b></td><td>Cambiar opacidad</td></tr>
<tr><td><b>Mayús</b> al arrastrar</td><td>Cuadrado / círculo / ángulos de 15°</td></tr>
<tr><td><b>Clic derecho</b></td><td>Cancelar el trazo o figura en curso</td></tr>
<tr><td><b>Ctrl+Z / Ctrl+Y</b></td><td>Deshacer / rehacer</td></tr>
<tr><td><b>Supr</b></td><td>Borrar todo</td></tr>
<tr><td><b>Esc</b></td><td>Pasar a «Ratón libre»</td></tr>
<tr><td><b>F1</b></td><td>Esta ayuda</td></tr>
</table>
<p>Las capturas se guardan en:<br><code>{folder}</code></p>
"""
