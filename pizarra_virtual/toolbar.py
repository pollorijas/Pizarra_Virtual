"""Barra de herramientas flotante (siempre visible, arrastrable y plegable)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QColorDialog, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu,
    QPushButton, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget,
)

from . import icons
from .tools import BACKGROUNDS, BRUSH_LABELS, FILLABLE_SHAPES, PALETTE, TOOL_SPECS, BrushType, Tool

if TYPE_CHECKING:  # pragma: no cover
    from .app import Controller

STYLE = """
#panel { background: rgba(30, 32, 37, 245); border: 1px solid #3b3f47; border-radius: 10px; }
QToolButton { border: none; border-radius: 6px; background: transparent; color: #e6e8eb; padding: 2px; }
QToolButton:hover { background: #3a3e47; }
QToolButton:checked { background: #2f6fd1; }
QToolButton#mode { font-weight: 600; text-align: left; padding: 4px 6px; background: #3a3e47; }
QToolButton#mode:checked { background: #2f6fd1; }
QToolButton::menu-indicator { image: none; }
QLabel { color: #c9ccd1; font-size: 11px; }
QLabel#title { color: #ffffff; font-weight: 600; font-size: 12px; }
QComboBox { background: #2a2d33; color: #e6e8eb; border: 1px solid #454a53; border-radius: 5px;
            padding: 2px 6px; font-size: 11px; }
QComboBox QAbstractItemView { background: #2a2d33; color: #e6e8eb; selection-background-color: #2f6fd1; }
QSlider::groove:horizontal { height: 4px; background: #4a4e57; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #4f9cf9; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: #e6e8eb; }
QPushButton#swatch { border: 1px solid #5a5f69; border-radius: 4px; }
QPushButton#swatch:hover { border: 2px solid #ffffff; }
QPushButton#current { border: 1px solid #5a5f69; border-radius: 5px; font-size: 11px; font-weight: 600; }
QMenu { background: #2a2d33; color: #e6e8eb; border: 1px solid #454a53; }
QMenu::item { padding: 5px 18px; }
QMenu::item:selected { background: #2f6fd1; }
"""

BTN = 32
PANEL_WIDTH = 3 * BTN + 2 * 4 + 2 * 8 + 2


class _Header(QWidget):
    """Zona de arrastre de la barra."""

    def __init__(self, toolbar: "Toolbar"):
        super().__init__(toolbar)
        self._tb = toolbar
        self._offset: QPoint | None = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            wh = self._tb.windowHandle()
            # Movimiento nativo: se comporta bien al pasar entre monitores con distinto DPI.
            if wh is not None and wh.startSystemMove():
                self._offset = None
            else:
                self._offset = e.globalPosition().toPoint() - self._tb.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._offset is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self._tb.move(e.globalPosition().toPoint() - self._offset)

    def mouseReleaseEvent(self, e):  # noqa: N802
        self._offset = None
        self._tb.save_position()


class Toolbar(QWidget):
    def __init__(self, ctrl: "Controller"):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self.ctrl = ctrl
        self.setWindowTitle("Pizarra Virtual")
        self.setWindowIcon(icons.app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self._shortcuts: list[QShortcut] = []
        self._build()
        self._build_shortcuts()
        self.sync()

    # ------------------------------------------------------------------ construcción

    def _tool_button(self, icon_name: str, tip: str, checkable: bool = False) -> QToolButton:
        b = QToolButton()
        b.setIcon(icons.icon(icon_name))
        b.setIconSize(QSize(20, 20))
        b.setFixedSize(BTN, BTN)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return b

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame(self)
        panel.setObjectName("panel")
        outer.addWidget(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(6)

        # Cabecera (arrastrar + plegar)
        header = _Header(self)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        title = QLabel("⠿ Pizarra")
        title.setObjectName("title")
        title.setToolTip("Arrastra desde aquí para mover la barra")
        hl.addWidget(title, 1)
        self.collapse_btn = self._tool_button("chevron_up", "Plegar / desplegar la barra")
        self.collapse_btn.setFixedSize(22, 22)
        self.collapse_btn.setIconSize(QSize(16, 16))
        self.collapse_btn.clicked.connect(self.toggle_collapsed)
        hl.addWidget(self.collapse_btn)
        lay.addWidget(header)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)
        lay.addWidget(self.body)

        # Modo dibujo / ratón libre
        self.mode_btn = QToolButton()
        self.mode_btn.setObjectName("mode")
        self.mode_btn.setCheckable(True)
        self.mode_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mode_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.mode_btn.setIconSize(QSize(18, 18))
        self.mode_btn.setFixedHeight(30)
        self.mode_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.mode_btn.setToolTip("Activar / desactivar el dibujo (Ctrl+Alt+D).\n"
                                 "En «Ratón libre» los clics llegan a las ventanas de debajo.")
        self.mode_btn.clicked.connect(lambda: self.ctrl.toggle_drawing())
        body.addWidget(self.mode_btn)

        # Herramientas
        grid = QGridLayout()
        grid.setSpacing(4)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_buttons: dict[Tool, QToolButton] = {}
        for idx, (tool, spec) in enumerate(TOOL_SPECS.items()):
            b = self._tool_button(spec.icon, f"{spec.label}  [{spec.key}]", checkable=True)
            b.clicked.connect(lambda _=False, t=tool: self.ctrl.set_tool(t))
            self.tool_group.addButton(b)
            self.tool_buttons[tool] = b
            grid.addWidget(b, idx // 3, idx % 3)
        body.addLayout(grid)

        # Tipo de pincel
        self.brush_combo = QComboBox()
        self.brush_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.brush_combo.setToolTip("Tipo de pincel [B]")
        for bt, label in BRUSH_LABELS.items():
            self.brush_combo.addItem(label, bt.value)
        self.brush_combo.currentIndexChanged.connect(
            lambda i: self.ctrl.set_brush_type(BrushType(self.brush_combo.itemData(i))))
        body.addWidget(self.brush_combo)

        # Relleno de figuras
        self.fill_btn = QToolButton()
        self.fill_btn.setText("Relleno")
        self.fill_btn.setCheckable(True)
        self.fill_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fill_btn.setToolTip("Figuras rellenas [F]")
        self.fill_btn.setFixedHeight(24)
        self.fill_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.fill_btn.clicked.connect(lambda c: self.ctrl.set_fill(c))
        body.addWidget(self.fill_btn)

        # Color
        self.color_btn = QPushButton()
        self.color_btn.setObjectName("current")
        self.color_btn.setFixedHeight(26)
        self.color_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.color_btn.setToolTip("Elegir color personalizado [C]")
        self.color_btn.clicked.connect(self.pick_color)
        body.addWidget(self.color_btn)

        sw = QGridLayout()
        sw.setSpacing(4)
        for idx, hexcolor in enumerate(PALETTE):
            b = QPushButton()
            b.setObjectName("swatch")
            b.setFixedSize(22, 22)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(hexcolor)
            b.setStyleSheet(f"background: {hexcolor};")
            b.clicked.connect(lambda _=False, c=hexcolor: self.ctrl.set_color(QColor(c)))
            sw.addWidget(b, idx // 4, idx % 4)
        body.addLayout(sw)

        # Grosor
        self.size_label = QLabel()
        body.addWidget(self.size_label)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.size_slider.setToolTip("Grosor (rueda del ratón sobre la pizarra, o teclas + / -)")
        self.size_slider.valueChanged.connect(lambda v: self.ctrl.set_size(v))
        body.addWidget(self.size_slider)

        # Opacidad
        self.opacity_label = QLabel()
        body.addWidget(self.opacity_label)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.opacity_slider.setToolTip("Opacidad (Mayús + rueda del ratón)")
        self.opacity_slider.valueChanged.connect(lambda v: self.ctrl.set_opacity(v))
        body.addWidget(self.opacity_slider)

        # Fondo
        bg_label = QLabel("Fondo")
        body.addWidget(bg_label)
        self.bg_combo = QComboBox()
        self.bg_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for key, label in BACKGROUNDS.items():
            self.bg_combo.addItem(label, key)
        self.bg_combo.currentIndexChanged.connect(
            lambda i: self.ctrl.set_background(self.bg_combo.itemData(i)))
        body.addWidget(self.bg_combo)

        # Acciones
        actions = QGridLayout()
        actions.setSpacing(4)
        undo = self._tool_button("undo", "Deshacer (Ctrl+Z)")
        undo.clicked.connect(self.ctrl.undo)
        redo = self._tool_button("redo", "Rehacer (Ctrl+Y)")
        redo.clicked.connect(self.ctrl.redo)
        clear = self._tool_button("trash", "Borrar todo (Supr)")
        clear.clicked.connect(self.ctrl.clear_all)

        capture = self._tool_button("camera", "Captura de pantalla")
        capture.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        capture.setMenu(self.ctrl.build_capture_menu(capture))
        folder = self._tool_button("folder", "Abrir la carpeta «Capturas Pizarra»")
        folder.clicked.connect(self.ctrl.open_captures_folder)
        self.hide_btn = self._tool_button("eye_off", "Ocultar la pizarra (Ctrl+Alt+H)")
        self.hide_btn.clicked.connect(self.ctrl.toggle_visible)

        help_btn = self._tool_button("help", "Ayuda y atajos de teclado (F1)")
        help_btn.clicked.connect(self.ctrl.show_help)
        quit_btn = self._tool_button("power", "Salir de Pizarra Virtual")
        quit_btn.clicked.connect(self.ctrl.quit)

        for idx, b in enumerate((undo, redo, clear, capture, folder, self.hide_btn, help_btn, quit_btn)):
            actions.addWidget(b, idx // 3, idx % 3)
        body.addLayout(actions)

        self.setFixedWidth(PANEL_WIDTH)

    def _build_shortcuts(self) -> None:
        c = self.ctrl

        def add(seq: str, fn):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)

        for tool, spec in TOOL_SPECS.items():
            add(spec.key, lambda t=tool: c.set_tool(t))
        add("B", c.cycle_brush_type)
        add("F", lambda: c.set_fill(not c.fill_shapes))
        add("C", self.pick_color)
        add("+", lambda: c.step_size(1))
        add("-", lambda: c.step_size(-1))
        add("]", lambda: c.step_size(1))
        add("[", lambda: c.step_size(-1))
        add("Ctrl+Z", c.undo)
        add("Ctrl+Y", c.redo)
        add("Ctrl+Shift+Z", c.redo)
        add("Del", c.clear_all)
        add("Esc", lambda: c.set_drawing(False))
        add("F1", c.show_help)
        # Duplicados locales de los atajos globales (útiles si el registro global falla).
        add("Ctrl+Alt+D", c.toggle_drawing)
        add("Ctrl+Alt+H", c.toggle_visible)
        add("Ctrl+Alt+S", lambda: c.capture(with_drawing=True))
        add("Ctrl+Alt+Shift+S", lambda: c.capture(with_drawing=False))

    # ------------------------------------------------------------------ acciones

    def pick_color(self) -> None:
        dlg_color = QColorDialog.getColor(self.ctrl.color, self, "Elegir color")
        if dlg_color.isValid():
            self.ctrl.set_color(dlg_color)

    def toggle_collapsed(self) -> None:
        self.body.setVisible(not self.body.isVisible())
        self.collapse_btn.setIcon(icons.icon("chevron_up" if self.body.isVisible() else "chevron_down"))
        self.adjustSize()

    # ------------------------------------------------------------------ estado

    def sync(self) -> None:
        c = self.ctrl
        spec = TOOL_SPECS[c.tool]
        widgets = (self.brush_combo, self.size_slider, self.opacity_slider, self.bg_combo)
        for w in widgets:
            w.blockSignals(True)
        try:
            self.tool_buttons[c.tool].setChecked(True)
            self.mode_btn.setChecked(c.drawing)
            self.mode_btn.setText("Dibujando" if c.drawing else "Ratón libre")
            self.mode_btn.setIcon(icons.icon("pencil" if c.drawing else "mouse"))

            self.brush_combo.setVisible(c.tool == Tool.BRUSH)
            self.brush_combo.setCurrentIndex(self.brush_combo.findData(c.brush_type.value))

            self.fill_btn.setVisible(c.tool in FILLABLE_SHAPES)
            self.fill_btn.setChecked(c.fill_shapes)

            col = c.color
            text_color = "#000000" if col.lightness() > 140 else "#ffffff"
            self.color_btn.setText(col.name().upper())
            self.color_btn.setStyleSheet(f"background: {col.name()}; color: {text_color};")

            self.size_slider.setRange(spec.min_size, spec.max_size)
            self.size_slider.setValue(int(c.size_for(c.tool)))
            self.size_label.setText(f"{spec.label}: {int(c.size_for(c.tool))} px")

            self.opacity_label.setVisible(spec.has_opacity)
            self.opacity_slider.setVisible(spec.has_opacity)
            self.opacity_slider.setValue(int(c.opacity_for(c.tool)))
            self.opacity_label.setText(f"Opacidad: {int(c.opacity_for(c.tool))} %")

            self.bg_combo.setCurrentIndex(max(0, self.bg_combo.findData(c.background)))
            self.hide_btn.setIcon(icons.icon("eye_off" if c.visible else "eye"))
            self.hide_btn.setToolTip(("Ocultar" if c.visible else "Mostrar") + " la pizarra (Ctrl+Alt+H)")
        finally:
            for w in widgets:
                w.blockSignals(False)
        self.adjustSize()

    # ------------------------------------------------------------------ posición

    def restore_position(self) -> None:
        self.adjustSize()
        pos = self.ctrl.settings.value("toolbar/pos")
        if isinstance(pos, QPoint):
            for s in QGuiApplication.screens():
                if s.availableGeometry().adjusted(-20, -20, -40, -40).contains(pos):
                    self.move(pos)
                    return
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.move(avail.left() + 16, avail.top() + max(16, (avail.height() - self.sizeHint().height()) // 2))

    def save_position(self) -> None:
        self.ctrl.settings.setValue("toolbar/pos", self.pos())

    def moveEvent(self, e):  # noqa: N802
        super().moveEvent(e)
        if self.isVisible():
            self.save_position()
