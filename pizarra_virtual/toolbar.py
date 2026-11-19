"""Barra de herramientas flotante (siempre visible, arrastrable y plegable)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QBoxLayout, QButtonGroup, QColorDialog, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QMenu,
    QPushButton, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget,
)

from . import icons
from . import templates
from .tools import (
    BACKGROUNDS, BRUSH_LABELS, EXTRA_SHAPES, FILLABLE_SHAPES, MAIN_TOOLS, PALETTE, PATTERNS, STAMPS, TOOL_SPECS,
    BrushType, Tool,
)

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
QLabel#section { color: #8f949c; font-size: 10px; font-weight: 600; }
QToolButton:disabled { background: transparent; }
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
COL_WIDTH = 3 * BTN + 2 * 4


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
        self.winId()  # ventana nativa: permite saber cuándo pasa a otro monitor
        if self.windowHandle() is not None:
            # Al llevar la barra a otra pantalla se recalcula si cabe en una columna.
            self.windowHandle().screenChanged.connect(lambda *_: QTimer.singleShot(0, self.update_orientation))

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

    def _menu_button(self, icon_name: str, tip: str, build_menu, checkable: bool = True) -> QToolButton:
        """Botón que al pulsarlo despliega un menú (se reconstruye cada vez: muestra la opción actual)."""
        b = self._tool_button(icon_name, tip, checkable=checkable)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        b.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        menu = QMenu(b)
        menu.aboutToShow.connect(lambda m=menu: build_menu(m))
        b.setMenu(menu)
        return b

    def build_shapes_menu(self, menu: QMenu | None = None) -> QMenu:
        menu = menu if menu is not None else QMenu(self)
        menu.clear()
        groups = ((Tool.PENTAGON, Tool.HEXAGON, Tool.OCTAGON), (Tool.DIAMOND, Tool.STAR, Tool.ROUNDED_RECT),
                  (Tool.AXES, Tool.DOUBLE_ARROW, Tool.CURVED_ARROW, Tool.BRACE))
        for gi, group in enumerate(groups):
            if gi:
                menu.addSeparator()
            for tool in group:
                spec = TOOL_SPECS[tool]
                act = menu.addAction(icons.icon(spec.icon), f"{spec.label}\t{spec.key}")
                act.setCheckable(True)
                act.setChecked(self.ctrl.tool == tool)
                act.triggered.connect(lambda _c=False, t=tool: self.ctrl.set_tool(t))
        return menu

    def build_stamps_menu(self, menu: QMenu | None = None) -> QMenu:
        menu = menu if menu is not None else QMenu(self)
        menu.clear()
        for kind, label in STAMPS.items():
            act = menu.addAction(icons.icon("stamp_" + kind), label)
            act.setCheckable(True)
            act.setChecked(self.ctrl.tool == Tool.STAMP and self.ctrl.stamp_kind == kind)
            act.triggered.connect(lambda _c=False, k=kind: self.ctrl.set_stamp_kind(k))
        return menu

    def build_templates_menu(self, menu: QMenu | None = None) -> QMenu:
        menu = menu if menu is not None else QMenu(self)
        menu.clear()
        for key, (label, _fn) in templates.TEMPLATES.items():
            act = menu.addAction(label)
            act.triggered.connect(lambda _c=False, k=key: self.ctrl.insert_template(k))
        return menu

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        # La ventana adopta SIEMPRE el tamaño exacto de su contenido: al plegar la barra
        # se encoge la ventana (no solo su interior) y al desplegarla vuelve a crecer.
        outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        panel = QFrame(self)
        panel.setObjectName("panel")
        self.panel = panel
        outer.addWidget(panel)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(6)

        # Cabecera (arrastrar + plegar)
        header = _Header(self)
        header.setMinimumWidth(COL_WIDTH)
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

        # Cuerpo en dos bloques. En pantallas bajas (p. ej. 1366x768 al 150 %) la barra no
        # cabe en vertical, así que los bloques se colocan uno al lado del otro.
        self.body = QWidget()
        self.body_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        columns = []
        for _ in range(2):
            col = QWidget()
            col.setFixedWidth(COL_WIDTH)
            col_lay = QVBoxLayout(col)
            col_lay.setContentsMargins(0, 0, 0, 0)
            col_lay.setSpacing(6)
            self.body_layout.addWidget(col, 0, Qt.AlignmentFlag.AlignTop)
            columns.append(col_lay)
        self._columns = [lay_.parentWidget() for lay_ in columns]
        c1, c2 = columns
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
        c1.addWidget(self.mode_btn)

        # Herramientas
        grid = QGridLayout()
        grid.setSpacing(4)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_buttons: dict[Tool, QToolButton] = {}
        for idx, tool in enumerate(MAIN_TOOLS):
            spec = TOOL_SPECS[tool]
            b = self._tool_button(spec.icon, f"{spec.label}  [{spec.key}]", checkable=True)
            b.clicked.connect(lambda _=False, t=tool: self.ctrl.set_tool(t))
            self.tool_group.addButton(b)
            self.tool_buttons[tool] = b
            grid.addWidget(b, idx // 3, idx % 3)
        # Más figuras, sellos y plantillas: un botón con menú cada uno
        n = len(MAIN_TOOLS)
        self.more_shapes_btn = self._menu_button("shapes_more", "Más figuras: polígonos, rombo, estrella, ejes,\n"
                                                                 "flecha doble, flecha curva, llave…", self.build_shapes_menu)
        self.stamp_btn = self._menu_button("stamp", "Sellos: ✔, ✘, estrella, carita, números, ?  [S]",
                                           self.build_stamps_menu)
        self.templates_btn = self._menu_button("templates", "Plantillas: mapa conceptual, línea de tiempo,\n"
                                                            "diagramas de Venn, tablas, esquema de redacción…",
                                               self.build_templates_menu, checkable=False)
        for k, b in enumerate((self.more_shapes_btn, self.stamp_btn, self.templates_btn)):
            grid.addWidget(b, (n + k) // 3, (n + k) % 3)
        c1.addLayout(grid)

        # Tipo de pincel
        self.brush_combo = QComboBox()
        self.brush_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.brush_combo.setToolTip("Tipo de pincel [B]")
        for bt, label in BRUSH_LABELS.items():
            self.brush_combo.addItem(label, bt.value)
        self.brush_combo.currentIndexChanged.connect(
            lambda i: self.ctrl.set_brush_type(BrushType(self.brush_combo.itemData(i))))
        c1.addWidget(self.brush_combo)

        # Relleno de figuras
        self.fill_btn = QToolButton()
        self.fill_btn.setText("Relleno")
        self.fill_btn.setCheckable(True)
        self.fill_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fill_btn.setToolTip("Figuras rellenas [R]")
        self.fill_btn.setFixedHeight(24)
        self.fill_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.fill_btn.clicked.connect(lambda c: self.ctrl.set_fill(c))
        c1.addWidget(self.fill_btn)

        # Negrita (texto)
        self.bold_btn = QToolButton()
        self.bold_btn.setText("Negrita")
        self.bold_btn.setIcon(icons.icon("bold"))
        self.bold_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.bold_btn.setCheckable(True)
        self.bold_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.bold_btn.setToolTip("Texto en negrita")
        self.bold_btn.setFixedHeight(24)
        self.bold_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.bold_btn.clicked.connect(lambda c: self.ctrl.set_text_bold(c))
        c1.addWidget(self.bold_btn)

        # Color
        self.color_btn = QPushButton()
        self.color_btn.setObjectName("current")
        self.color_btn.setFixedHeight(26)
        self.color_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.color_btn.setToolTip("Elegir color personalizado [C]")
        self.color_btn.clicked.connect(self.pick_color)
        c1.addWidget(self.color_btn)

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
        c1.addLayout(sw)

        # Grosor
        self.size_label = QLabel()
        c2.addWidget(self.size_label)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.size_slider.setToolTip("Grosor (rueda del ratón sobre la pizarra, o teclas + / -)")
        self.size_slider.valueChanged.connect(lambda v: self.ctrl.set_size(v))
        c2.addWidget(self.size_slider)

        # Opacidad
        self.opacity_label = QLabel()
        c2.addWidget(self.opacity_label)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.opacity_slider.setToolTip("Opacidad (Mayús + rueda del ratón)")
        self.opacity_slider.valueChanged.connect(lambda v: self.ctrl.set_opacity(v))
        c2.addWidget(self.opacity_slider)

        # Fondo
        bg_label = QLabel("Fondo")
        c2.addWidget(bg_label)
        self.bg_combo = QComboBox()
        self.bg_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for key, label in BACKGROUNDS.items():
            self.bg_combo.addItem(label, key)
        self.bg_combo.currentIndexChanged.connect(
            lambda i: self.ctrl.set_background(self.bg_combo.itemData(i)))
        c2.addWidget(self.bg_combo)
        self.pattern_combo = QComboBox()
        self.pattern_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pattern_combo.setToolTip("Pauta de la página: cuadrícula, rayado, caligrafía, plano cartesiano…")
        for key, label in PATTERNS.items():
            self.pattern_combo.addItem(label, key)
        self.pattern_combo.currentIndexChanged.connect(
            lambda i: self.ctrl.set_pattern(self.pattern_combo.itemData(i)))
        c2.addWidget(self.pattern_combo)

        # Presentación: foco, cortina, resaltar cursor
        c2.addWidget(self._section("Presentación"))
        fx = QHBoxLayout()
        fx.setSpacing(4)
        self.spot_btn = self._tool_button("spotlight", "Foco: oscurece todo menos alrededor del cursor\n"
                                                       "[F / Ctrl+Alt+F] · Alt + rueda: tamaño\n"
                                                       "Clic derecho o Shift+F: círculo o rectángulo", checkable=True)
        self.spot_btn.clicked.connect(lambda: self.ctrl.toggle_spotlight())
        self.spot_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.spot_btn.customContextMenuRequested.connect(self._spotlight_menu)
        self.curtain_btn = self._tool_button("curtain", "Cortina: tapa la pantalla y se descubre poco a poco\n"
                                                        "[V] · arrástrala o usa ↓ / ↑", checkable=True)
        self.curtain_btn.clicked.connect(lambda: self.ctrl.toggle_curtain())
        self.highlight_btn = self._tool_button("highlight", "Resaltar el cursor y los clics [M / Ctrl+Alt+M]",
                                               checkable=True)
        self.highlight_btn.clicked.connect(lambda: self.ctrl.toggle_highlight())
        for b in (self.spot_btn, self.curtain_btn, self.highlight_btn):
            fx.addWidget(b)
        c2.addLayout(fx)

        # Páginas
        self.page_label = QLabel()
        self.page_label.setObjectName("section")
        c2.addWidget(self.page_label)
        pages = QHBoxLayout()
        pages.setSpacing(4)
        self.prev_btn = self._tool_button("page_prev", "Página anterior [RePág]")
        self.prev_btn.clicked.connect(self.ctrl.prev_page)
        self.next_btn = self._tool_button("page_next", "Página siguiente [AvPág]")
        self.next_btn.clicked.connect(self.ctrl.next_page)
        add_page = self._tool_button("page_add", "Página nueva [N]")
        add_page.clicked.connect(self.ctrl.new_page)
        for b in (self.prev_btn, self.next_btn, add_page):
            pages.addWidget(b)
        c2.addLayout(pages)

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
        folder = self._tool_button("file", "Sesión: abrir, guardar, exportar a PDF")
        folder.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        folder.setMenu(self.ctrl.build_file_menu(folder))
        self.hide_btn = self._tool_button("eye_off", "Ocultar la pizarra (Ctrl+Alt+H)")
        self.hide_btn.clicked.connect(self.ctrl.toggle_visible)

        self.zoom_btn = self._tool_button("zoom", "Zoom: ampliar la zona bajo el cursor (Z / Ctrl+Alt+Z)",
                                          checkable=True)
        self.zoom_btn.clicked.connect(lambda: self.ctrl.toggle_zoom())

        help_btn = self._tool_button("help", "Ayuda: atajos de teclado (F1) y manual de usuario")
        help_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        help_menu = QMenu(help_btn)
        help_menu.addAction(icons.icon("help"), "Atajos de teclado\tF1", self.ctrl.show_help)
        help_menu.addAction(icons.icon("pdf"), "Manual de usuario (PDF)", self.ctrl.open_manual)
        help_btn.setMenu(help_menu)
        quit_btn = self._tool_button("power", "Salir de Pizarra Virtual")
        quit_btn.clicked.connect(self.ctrl.quit)

        buttons = (undo, redo, clear, self.zoom_btn, capture, folder, self.hide_btn, help_btn, quit_btn)
        for idx, b in enumerate(buttons):
            actions.addWidget(b, idx // 3, idx % 3)
        c2.addLayout(actions)

    def _section(self, text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("section")
        return label

    def _build_shortcuts(self) -> None:
        c = self.ctrl

        def add(seq: str, fn):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(fn)
            self._shortcuts.append(sc)

        for tool, spec in TOOL_SPECS.items():
            if spec.key not in ("P", "S"):  # P y S tienen su propio ciclo (abajo)
                add(spec.key, lambda t=tool: c.set_tool(t))
        add("P", c.cycle_polygon)
        add("S", c.cycle_stamp)
        add("B", c.cycle_brush_type)
        add("R", lambda: c.set_fill(not c.fill_shapes))
        add("F", c.toggle_spotlight)
        add("Shift+F", c.toggle_spotlight_shape)
        add("V", c.toggle_curtain)
        add("M", c.toggle_highlight)
        add("Down", lambda: c.curtain_step(1))
        add("Up", lambda: c.curtain_step(-1))
        add("PgDown", c.next_page)
        add("PgUp", c.prev_page)
        add("N", c.new_page)
        add("Ctrl+S", lambda: c.save_session())
        add("Ctrl+Shift+S", lambda: c.save_session(ask=True))
        add("Ctrl+O", lambda: c.open_session())
        add("Ctrl+P", lambda: c.export_pdf())
        add("Ctrl+Alt+F", c.toggle_spotlight)
        add("Ctrl+Alt+M", c.toggle_highlight)
        add("C", self.pick_color)
        add("+", lambda: c.step_size(1))
        add("-", lambda: c.step_size(-1))
        add("]", lambda: c.step_size(1))
        add("[", lambda: c.step_size(-1))
        add("Ctrl+Z", c.undo)
        add("Ctrl+Y", c.redo)
        add("Ctrl+Shift+Z", c.redo)
        add("Del", c.clear_all)
        add("Esc", c.escape)
        add("Z", c.toggle_zoom)
        add("Ctrl+Alt+Z", c.toggle_zoom)
        add("F1", c.show_help)
        # Duplicados locales de los atajos globales (útiles si el registro global falla).
        add("Ctrl+Alt+D", c.toggle_drawing)
        add("Ctrl+Alt+H", c.toggle_visible)
        add("Ctrl+Alt+S", lambda: c.capture(with_drawing=True))
        add("Ctrl+Alt+Shift+S", lambda: c.capture(with_drawing=False))

    # ------------------------------------------------------------------ acciones

    def build_spotlight_menu(self) -> QMenu:
        """Menú con la forma del foco (clic derecho sobre el botón del foco)."""
        from .app import SPOTLIGHT_SHAPES

        menu = QMenu(self)
        for key, label in SPOTLIGHT_SHAPES.items():
            act = menu.addAction(f"Foco: {label.lower()}")
            act.setCheckable(True)
            act.setChecked(self.ctrl.spotlight_shape == key)
            act.triggered.connect(lambda _c=False, k=key: self._choose_spotlight_shape(k))
        return menu

    def _choose_spotlight_shape(self, key: str) -> None:
        self.ctrl.set_spotlight_shape(key)
        if not self.ctrl.spotlight:
            self.ctrl.toggle_spotlight()

    def _spotlight_menu(self, pos) -> None:
        self.build_spotlight_menu().exec(self.spot_btn.mapToGlobal(pos))

    def pick_color(self) -> None:
        dlg_color = QColorDialog.getColor(self.ctrl.color, self, "Elegir color")
        if dlg_color.isValid():
            self.ctrl.set_color(dlg_color)

    @property
    def collapsed(self) -> bool:
        return self.body.isHidden()

    def set_collapsed(self, collapsed: bool) -> None:
        self.body.setHidden(collapsed)
        self.collapse_btn.setIcon(icons.icon("chevron_down" if collapsed else "chevron_up"))
        self.collapse_btn.setToolTip("Desplegar la barra" if collapsed else "Plegar la barra")
        self.ctrl.settings.setValue("toolbar/collapsed", "true" if collapsed else "false")
        self.update_orientation()

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self.collapsed)

    def refit(self) -> None:
        """Ajusta la ventana al contenido visible, inmediatamente.

        Qt guarda en caché el tamaño preferido de cada sección dentro del layout que la
        contiene; si ese valor se consultó antes de ocultar algo (Windows lo hace, p. ej.
        al mover o activar la ventana), la ventana conservaba el tamaño antiguo y solo
        se reducía su contenido. Aquí se vacían esas cachés (updateGeometry) y se
        invalidan los tres niveles antes de recalcular.
        """
        containers = [*self._columns, self.body, self.panel]  # de dentro hacia fuera
        for w in containers:
            w.updateGeometry()
            w.layout().invalidate()
        self.layout().invalidate()
        self.layout().activate()
        hint = self.layout().totalSizeHint()
        if self.size() != hint:
            self.setFixedSize(hint)

    def _current_screen(self):
        return (QGuiApplication.screenAt(self.frameGeometry().topLeft())
                or QGuiApplication.screenAt(self.frameGeometry().center())
                or self.screen() or QGuiApplication.primaryScreen())

    @property
    def horizontal(self) -> bool:
        return self.body_layout.direction() == QBoxLayout.Direction.LeftToRight

    def update_orientation(self) -> None:
        """Una columna si la barra cabe en la altura de su pantalla; si no, dos columnas."""
        if self.collapsed:
            self.refit()
        else:
            avail = self._current_screen().availableGeometry()
            # Se mide con TODAS las opciones visibles (tipo de pincel, relleno, opacidad) para
            # que la disposición no dependa de la herramienta activa ni cambie al cambiarla.
            optional = (self.brush_combo, self.fill_btn, self.bold_btn, self.opacity_label, self.opacity_slider)
            hidden = [w for w in optional if w.isHidden()]
            for w in hidden:
                w.setVisible(True)
            self.body_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            self.refit()
            needed = self.height()
            for w in hidden:
                w.setVisible(False)
            if needed > avail.height():
                self.body_layout.setDirection(QBoxLayout.Direction.LeftToRight)
            self.refit()
        self.keep_on_screen()

    def keep_on_screen(self) -> None:
        """Mantiene la barra dentro de la pantalla (y la cabecera siempre visible)."""
        avail = self._current_screen().availableGeometry()
        geo = self.frameGeometry()
        x = max(avail.left(), min(geo.left(), avail.right() - geo.width() + 1))
        y = max(avail.top(), min(geo.top(), avail.bottom() - geo.height() + 1))
        if (x, y) != (geo.left(), geo.top()):
            self.move(x, y)

    # ------------------------------------------------------------------ estado

    def sync(self) -> None:
        c = self.ctrl
        spec = TOOL_SPECS[c.tool]
        widgets = (self.brush_combo, self.size_slider, self.opacity_slider, self.bg_combo, self.pattern_combo)
        for w in widgets:
            w.blockSignals(True)
        try:
            if c.tool in self.tool_buttons:
                self.tool_group.setExclusive(True)
                self.tool_buttons[c.tool].setChecked(True)
            else:  # figura del menú o sello: ningún botón principal marcado
                self.tool_group.setExclusive(False)
                for b in self.tool_buttons.values():
                    b.setChecked(False)
            self.more_shapes_btn.setChecked(c.tool in EXTRA_SHAPES)
            self.more_shapes_btn.setIcon(icons.icon(TOOL_SPECS[c.extra_shape].icon if c.tool in EXTRA_SHAPES
                                                    else "shapes_more"))
            self.stamp_btn.setChecked(c.tool == Tool.STAMP)
            self.stamp_btn.setIcon(icons.icon("stamp_" + c.stamp_kind if c.tool == Tool.STAMP else "stamp"))
            self.mode_btn.setChecked(c.drawing)
            self.mode_btn.setText("Dibujando" if c.drawing else "Ratón libre")
            self.mode_btn.setIcon(icons.icon("pencil" if c.drawing else "mouse"))

            self.brush_combo.setVisible(c.tool == Tool.BRUSH)
            self.brush_combo.setCurrentIndex(self.brush_combo.findData(c.brush_type.value))

            self.fill_btn.setVisible(c.tool in FILLABLE_SHAPES)
            self.fill_btn.setChecked(c.fill_shapes)
            self.bold_btn.setVisible(c.tool == Tool.TEXT)
            self.bold_btn.setChecked(c.text_bold)

            col = c.color
            text_color = "#000000" if col.lightness() > 140 else "#ffffff"
            self.color_btn.setText(col.name().upper())
            self.color_btn.setStyleSheet(f"background: {col.name()}; color: {text_color};")

            self.size_slider.setRange(spec.min_size, spec.max_size)
            self.size_slider.setValue(int(c.size_for(c.tool)))
            what = {Tool.TEXT: "Letra", Tool.LASER: "Tamaño", Tool.STAMP: "Tamaño"}.get(c.tool, "Grosor")
            self.size_label.setText(f"{what}: {int(c.size_for(c.tool))} px")
            self.size_label.setToolTip(spec.label)

            self.opacity_label.setVisible(spec.has_opacity)
            self.opacity_slider.setVisible(spec.has_opacity)
            self.opacity_slider.setValue(int(c.opacity_for(c.tool)))
            self.opacity_label.setText(f"Opacidad: {int(c.opacity_for(c.tool))} %")

            self.bg_combo.setCurrentIndex(max(0, self.bg_combo.findData(c.background)))
            self.pattern_combo.setCurrentIndex(max(0, self.pattern_combo.findData(c.pattern)))
            self.spot_btn.setChecked(c.spotlight)
            self.curtain_btn.setChecked(c.curtain_active)
            self.highlight_btn.setChecked(c.highlight)
            self.page_label.setText(f"PÁGINA {c.page_index + 1} DE {len(c.pages)}")
            self.prev_btn.setEnabled(c.page_index > 0)
            self.next_btn.setEnabled(c.page_index < len(c.pages) - 1)
            self.hide_btn.setIcon(icons.icon("eye_off" if c.visible else "eye"))
            self.hide_btn.setToolTip(("Ocultar" if c.visible else "Mostrar") + " la pizarra (Ctrl+Alt+H)")
            self.zoom_btn.setChecked(c.zoom_active)
        finally:
            for w in widgets:
                w.blockSignals(False)
        self.refit()
        if self.isVisible():
            self.keep_on_screen()

    # ------------------------------------------------------------------ posición

    def restore_position(self) -> None:
        if str(self.ctrl.settings.value("toolbar/collapsed", "false")).lower() == "true":
            self.set_collapsed(True)
        pos = self.ctrl.settings.value("toolbar/pos")
        if isinstance(pos, QPoint) and any(
                s.availableGeometry().adjusted(-20, -20, -40, -40).contains(pos) for s in QGuiApplication.screens()):
            self.move(pos)
            self.update_orientation()
            return
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.move(avail.left() + 16, avail.top() + 16)
        self.update_orientation()
        self.move(avail.left() + 16, avail.top() + max(16, (avail.height() - self.height()) // 2))

    def save_position(self) -> None:
        self.ctrl.settings.setValue("toolbar/pos", self.pos())

    def closeEvent(self, ev):  # noqa: N802
        """Alt+F4 sobre esta ventana cierra todo el programa, nunca solo esta ventana."""
        if self.ctrl.shutting_down:
            super().closeEvent(ev)
            return
        ev.ignore()
        self.ctrl.request_close()

    def moveEvent(self, e):  # noqa: N802
        super().moveEvent(e)
        if self.isVisible():
            self.save_position()
