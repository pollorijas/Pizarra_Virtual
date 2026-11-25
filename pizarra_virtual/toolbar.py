"""Barra de herramientas flotante (siempre visible, arrastrable y plegable)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QBoxLayout, QButtonGroup, QColorDialog, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QMenu,
    QPushButton, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget,
)

from . import icons, instruments
from . import templates
from .tools import (
    BACKGROUNDS, BASIC_TOOLS, BRUSH_LABELS, CURTAIN_SIDES, EXTRA_SHAPES, FILLABLE_SHAPES, MAIN_TOOLS, NOTE_COLORS, PALETTE,
    PATTERNS, RECOGNIZABLE_TOOLS, STAMPS, TOOL_SPECS, UNSIZED_TOOLS, BrushType, Tool,
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
INSTRUMENT_KEYS = {"ruler": "I", "protractor": "Y", "compass": "Mayús+C"}  # (texto de los menús)
COL_WIDTH = 3 * BTN + 2 * 4
# Modo táctil: además de los botones más grandes, letras, menús y deslizadores más cómodos para el dedo
TOUCH_STYLE = """
QLabel { font-size: 14px; }
QLabel#title { font-size: 15px; }
QLabel#section { font-size: 12px; }
QComboBox { font-size: 14px; padding: 6px 8px; }
QToolButton { font-size: 13px; }
QSlider::groove:horizontal { height: 8px; border-radius: 4px; }
QSlider::handle:horizontal { width: 26px; height: 26px; margin: -9px 0; border-radius: 13px; }
QMenu { font-size: 15px; }
QMenu::item { padding: 11px 26px; }
"""


def _scoped(css: str) -> str:
    """Limita el estilo oscuro a los controles de la barra (los que están dentro de «#panel»).

    Los diálogos (guardar cambios, ayuda, eliminar página…) son hijos de la barra y heredarían
    su letra clara sobre el fondo claro de Windows, y no se leerían. Los menús sí se mantienen
    oscuros (también los que se abren fuera del panel).
    """
    return "\n".join("#panel " + line if line.startswith("Q") and not line.startswith("QMenu") else line
                      for line in css.splitlines())


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
        self.basic = ctrl.basic_toolbar  # barra básica (lo más usado) o avanzada (todo)
        self._submenus: dict[str, QMenu] = {}
        self.setWindowTitle("Pizarra Virtual")
        self.setWindowIcon(icons.app_icon())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Tamaños (más grandes en el modo táctil)
        k = ctrl.touch_scale
        self.k = k
        self.btn = int(round(BTN * k))
        self.col_width = 3 * self.btn + 2 * 4
        self.setStyleSheet(_scoped(STYLE + (TOUCH_STYLE if ctrl.touch_mode else "")))
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
        b.setIconSize(QSize(int(20 * self.k), int(20 * self.k)))
        b.setFixedSize(self.btn, self.btn)
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

    def build_timer_menu(self, menu: QMenu | None = None) -> QMenu:
        menu = menu if menu is not None else QMenu(self)
        menu.clear()
        for minutes in (1, 2, 3, 5, 10, 15, 20, 30):
            act = menu.addAction(f"{minutes} minuto{'s' if minutes > 1 else ''}")
            act.triggered.connect(lambda _c=False, m=minutes: self.ctrl.start_timer(m * 60))
        menu.addAction("Otro tiempo…").triggered.connect(lambda: self.ctrl.ask_timer())
        menu.addSeparator()
        menu.addAction("Cronómetro (cuenta hacia arriba)").triggered.connect(lambda: self.ctrl.start_stopwatch())
        if self.ctrl.timer_visible:
            menu.addAction("Cerrar el temporizador").triggered.connect(lambda: self.ctrl.hide_timer())
        return menu

    def build_notes_menu(self, menu: QMenu | None = None) -> QMenu:
        menu = menu if menu is not None else QMenu(self)
        menu.clear()
        for key, (label, rgba) in NOTE_COLORS.items():
            act = menu.addAction(icons.swatch_icon(rgba), f"Nota {label.lower()}")
            act.setCheckable(True)
            act.setChecked(self.ctrl.tool == Tool.NOTE and self.ctrl.note_color == key)
            act.triggered.connect(lambda _c=False, k=key: self.ctrl.set_note_color(k))
        return menu

    def build_curtain_menu(self, menu: QMenu | None = None) -> QMenu:
        menu = menu if menu is not None else QMenu(self)
        menu.clear()
        c = self.ctrl
        for side, label in CURTAIN_SIDES.items():
            act = menu.addAction(f"Cortina: {label.lower()}")
            act.setCheckable(True)
            act.setChecked(c.curtain_active and c.curtain_side == side)
            act.triggered.connect(lambda _c=False, sd=side: c.show_curtain(sd))
        if c.curtain_active:
            menu.addSeparator()
            menu.addAction("Quitar la cortina\tV").triggered.connect(lambda: c.toggle_curtain())
        return menu

    def build_instruments_menu(self, menu: QMenu | None = None) -> QMenu:
        menu = menu if menu is not None else QMenu(self)
        menu.clear()
        c = self.ctrl
        for kind, label in instruments.INSTRUMENTS.items():
            act = menu.addAction(icons.icon(kind), f"{label}\t{INSTRUMENT_KEYS[kind]}")
            act.setCheckable(True)
            act.setChecked(c.instrument_visible(kind))
            act.triggered.connect(lambda _c=False, k=kind: c.toggle_instrument(k))
        if c.any_instrument:
            menu.addSeparator()
            menu.addAction("Quitar los instrumentos").triggered.connect(lambda: c.hide_instruments())
        return menu

    def _submenu(self, menu: QMenu, key: str, title: str, build, icon_name: str | None = None) -> None:
        """Añade un submenú que se rehace al abrirlo (se crea una vez y se reutiliza)."""
        sub = self._submenus.get(key)
        if sub is None:
            sub = QMenu(title, self)
            if icon_name:
                sub.setIcon(icons.icon(icon_name))
            sub.aboutToShow.connect(lambda m=sub: build(m))
            self._submenus[key] = sub
        menu.addMenu(sub)

    def _choices_menu(self, menu: QMenu, options: dict, current: str, choose) -> QMenu:
        menu.clear()
        for key, label in options.items():
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(current == key)
            act.triggered.connect(lambda _c=False, k=key: choose(k))
        return menu

    def _check(self, menu: QMenu, icon_name: str, text: str, checked: bool, slot) -> None:
        act = menu.addAction(icons.icon(icon_name), text)
        act.setCheckable(True)
        act.setChecked(checked)
        act.triggered.connect(lambda _c=False: slot())

    def build_basic_menu(self, menu: QMenu | None = None) -> QMenu:
        """Menú «Más» de la barra básica: todo lo que la barra avanzada muestra con botones."""
        menu = menu if menu is not None else QMenu(self)
        menu.clear()
        c = self.ctrl
        self._submenu(menu, "bg", "Fondo de la pizarra",
                      lambda m: self._choices_menu(m, BACKGROUNDS, c.background, c.set_background))
        self._submenu(menu, "pattern", "Pauta",
                      lambda m: self._choices_menu(m, PATTERNS, c.pattern, c.set_pattern))
        menu.addSeparator()
        for tool in (Tool.LINE, Tool.ARROW):
            spec = TOOL_SPECS[tool]
            self._check(menu, spec.icon, f"{spec.label}\t{spec.key}", c.tool == tool, lambda t=tool: c.set_tool(t))
        self._submenu(menu, "shapes", "Más figuras", self.build_shapes_menu, "shapes_more")
        self._submenu(menu, "stamps", "Sellos", self.build_stamps_menu, "stamp")
        self._submenu(menu, "templates", "Plantillas", self.build_templates_menu, "templates")
        self._submenu(menu, "instruments", "Regla, transportador y compás", self.build_instruments_menu, "ruler")
        spec = TOOL_SPECS[Tool.SELECT]
        self._check(menu, spec.icon, "Seleccionar y mover\tA", c.tool == Tool.SELECT,
                    lambda: c.set_tool(Tool.SELECT))
        menu.addAction(icons.icon("paste"), "Pegar imagen o texto\tCtrl+V").triggered.connect(lambda: c.paste())
        menu.addSeparator()
        self._check(menu, "spotlight", "Foco\tF", c.spotlight, c.toggle_spotlight)
        self._submenu(menu, "curtain", "Cortina", self.build_curtain_menu, "curtain")
        spec = TOOL_SPECS[Tool.COVER]
        self._check(menu, spec.icon, "Tapar zona\tH", c.tool == Tool.COVER, lambda: c.set_tool(Tool.COVER))
        self._check(menu, "highlight", "Resaltar cursor y clics\tM", c.highlight, c.toggle_highlight)
        self._check(menu, "keys", "Mostrar teclas pulsadas\tCtrl+Alt+K", c.show_keys, c.toggle_show_keys)
        self._submenu(menu, "timer", "Temporizador", self.build_timer_menu, "timer")
        self._check(menu, "zoom", "Zoom\tZ", c.zoom_active, c.toggle_zoom)
        menu.addSeparator()
        pages = menu.addAction(f"Página {c.page_index + 1} de {len(c.pages)}")
        pages.setEnabled(False)
        prev_act = menu.addAction(icons.icon("page_prev"), "Página anterior\tRePág")
        prev_act.setEnabled(c.page_index > 0)
        prev_act.triggered.connect(lambda: c.prev_page())
        next_act = menu.addAction(icons.icon("page_next"), "Página siguiente\tAvPág")
        next_act.setEnabled(c.page_index < len(c.pages) - 1)
        next_act.triggered.connect(lambda: c.next_page())
        menu.addAction(icons.icon("page_add"), "Página nueva\tN").triggered.connect(lambda: c.new_page())
        menu.addSeparator()
        capture = self.capture_btn.menu()
        capture.setTitle("Captura de pantalla y recortar zona")
        capture.setIcon(icons.icon("camera"))
        menu.addMenu(capture)
        session = self.folder_btn.menu()
        session.setTitle("Sesión y PDF")
        session.setIcon(icons.icon("file"))
        menu.addMenu(session)
        help_menu = self.help_btn.menu()
        help_menu.setTitle("Ayuda")
        help_menu.setIcon(icons.icon("help"))
        menu.addMenu(help_menu)
        menu.addSeparator()
        menu.addAction(icons.icon("options"), "Barra avanzada (todas las opciones)").triggered.connect(
            lambda: c.set_basic_toolbar(False))
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
        header.setMinimumWidth(self.col_width)
        self._header = header
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        title = QLabel("⠿ Pizarra")
        title.setObjectName("title")
        title.setToolTip("Arrastra desde aquí para mover la barra")
        hl.addWidget(title, 1)
        small = int(22 * self.k)
        self.touch_btn = self._tool_button("touch", "Modo táctil: botones y menús más grandes para usar con el dedo\n"
                                                    "(dos dedos: deshacer · tres dedos: rehacer)", checkable=True)
        self.touch_btn.setFixedSize(small, small)
        self.touch_btn.setIconSize(QSize(int(16 * self.k), int(16 * self.k)))
        self.touch_btn.clicked.connect(lambda c: self.ctrl.set_touch_mode(c))
        hl.addWidget(self.touch_btn)
        self.collapse_btn = self._tool_button("chevron_up", "Plegar / desplegar la barra")
        self.collapse_btn.setFixedSize(small, small)
        self.collapse_btn.setIconSize(QSize(int(16 * self.k), int(16 * self.k)))
        self.collapse_btn.clicked.connect(self.toggle_collapsed)
        hl.addWidget(self.collapse_btn)
        self.quit_btn = self._tool_button("power", "Salir de Pizarra Virtual")
        self.quit_btn.setFixedSize(small, small)
        self.quit_btn.setIconSize(QSize(int(16 * self.k), int(16 * self.k)))
        self.quit_btn.clicked.connect(self.ctrl.quit)
        hl.addWidget(self.quit_btn)
        lay.addWidget(header)

        # Cuerpo. Barra avanzada: dos bloques que en pantallas bajas (p. ej. 1366x768 al 150 %) se
        # colocan uno al lado del otro. Barra básica: un solo bloque con lo más usado.
        self.body = QWidget()
        body_lay = QVBoxLayout(self.body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(4)
        # Arriba de todo, «Ocultar» y «Dibujando / Ratón libre» (lado a lado si hay dos columnas)
        self.top = QWidget()
        self.top_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, self.top)
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        self.top_layout.setSpacing(4)
        body_lay.addWidget(self.top)
        self.cols = QWidget()
        self.body_layout = QBoxLayout(QBoxLayout.Direction.TopToBottom, self.cols)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        body_lay.addWidget(self.cols)
        columns = []
        for _ in range(1 if self.basic else 2):
            col = QWidget()
            col.setFixedWidth(self.col_width)
            col_lay = QVBoxLayout(col)
            col_lay.setContentsMargins(0, 0, 0, 0)
            col_lay.setSpacing(4)
            self.body_layout.addWidget(col, 0, Qt.AlignmentFlag.AlignTop)
            columns.append(col_lay)
        self._columns = [lay_.parentWidget() for lay_ in columns]
        lay.addWidget(self.body)

        widgets = self._create_widgets()
        self.top_layout.addWidget(self.hide_btn)
        self.top_layout.addWidget(self.mode_btn)
        if self.basic:
            self._layout_basic(columns[0])
        else:
            self._layout_advanced(*columns)
        # Lo que esta barra no muestra queda guardado en un contenedor oculto: sigue existiendo
        # (sync() lo actualiza y sus menús funcionan), pero nunca se ve.
        self._spare = QWidget(self)
        self._spare.hide()
        for w in widgets:
            if w.parentWidget() is None:
                w.setParent(self._spare)
        self.set_two_columns(False)

    def _wide_button(self, icon_name: str, tip: str, height: int = 30) -> QToolButton:
        """Botón con icono y texto que ocupa todo el ancho de la columna."""
        b = QToolButton()
        b.setObjectName("mode")
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setIcon(icons.icon(icon_name))
        b.setIconSize(QSize(int(18 * self.k), int(18 * self.k)))
        b.setFixedHeight(int(height * self.k))
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        b.setToolTip(tip)
        return b

    def _create_widgets(self) -> list[QWidget]:
        """Crea todos los controles (los dos modos de barra usan los mismos); devuelve la lista."""
        c = self.ctrl
        # Ocultar / mostrar la pizarra: arriba de todo, fácil de encontrar
        self.hide_btn = self._wide_button("eye_off", "Ocultar o mostrar todo lo dibujado (Ctrl+Alt+H)", 28)
        self.hide_btn.setCheckable(True)
        self.hide_btn.clicked.connect(lambda: c.toggle_visible())

        # Modo dibujo / ratón libre
        self.mode_btn = self._wide_button("pencil", "Activar / desactivar el dibujo (Ctrl+Alt+D).\n"
                                                    "En «Ratón libre» los clics llegan a las ventanas de debajo.", 28)
        self.mode_btn.setCheckable(True)
        self.mode_btn.clicked.connect(lambda: c.toggle_drawing())

        # Herramientas
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_buttons: dict[Tool, QToolButton] = {}
        for tool in MAIN_TOOLS:
            spec = TOOL_SPECS[tool]
            b = self._tool_button(spec.icon, f"{spec.label}  [{spec.key}]", checkable=True)
            b.clicked.connect(lambda _=False, t=tool: c.set_tool(t))
            self.tool_group.addButton(b)
            self.tool_buttons[tool] = b
        self.more_shapes_btn = self._menu_button("shapes_more", "Más figuras: polígonos, rombo, estrella, ejes,\n"
                                                                 "flecha doble, flecha curva, llave…", self.build_shapes_menu)
        self.stamp_btn = self._menu_button("stamp", "Sellos: ✔, ✘, estrella, carita, números, ?  [S]",
                                           self.build_stamps_menu)
        self.templates_btn = self._menu_button("templates", "Plantillas: mapa conceptual, línea de tiempo,\n"
                                                            "diagramas de Venn, tablas, esquema de redacción…",
                                               self.build_templates_menu, checkable=False)
        spec = TOOL_SPECS[Tool.SELECT]
        self.select_btn = self._tool_button(spec.icon, "Seleccionar y mover  [A]\nClic en algo o arrastra un lazo; "
                                                       "arrastra para mover, la esquina para cambiar el tamaño.\n"
                                                       "Supr: eliminar · Ctrl+D: duplicar · Ctrl+A: todo",
                                            checkable=True)
        self.select_btn.clicked.connect(lambda: c.set_tool(Tool.SELECT))
        self.tool_group.addButton(self.select_btn)
        self.tool_buttons[Tool.SELECT] = self.select_btn
        self.timer_btn = self._menu_button("timer", "Temporizador en pantalla (cuenta regresiva o cronómetro)",
                                           self.build_timer_menu, checkable=False)
        self.paste_btn = self._tool_button("paste", "Pegar una imagen o un texto copiado  [Ctrl+V]")
        self.paste_btn.clicked.connect(lambda: c.paste())
        self.note_btn = self._menu_button("note", "Nota adhesiva  [O]: haz clic donde quieras pegarla y escribe.\n"
                                                  "Elige aquí el color del papel.", self.build_notes_menu)
        self.instruments_btn = self._menu_button(
            "ruler", "Instrumentos de geometría: regla [I], transportador [Y] y compás [Mayús+C].\n"
                     "Arrástralos para moverlos; el botón azul los gira. Un trazo que empieza\n"
                     "junto a la regla sale recto; el compás dibuja al girar la punta del lápiz.",
            self.build_instruments_menu)
        # Barra básica: un solo botón con lo demás (fondo, pauta, figuras, presentación, páginas…)
        self.more_btn = self._menu_button("more", "Más: fondo y pauta de la pizarra, más figuras, presentación\n"
                                                  "(foco, cortina, temporizador, zoom), páginas, capturas y sesión",
                                          self.build_basic_menu)

        # Opciones de la herramienta
        self.brush_combo = QComboBox()
        self.brush_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.brush_combo.setToolTip("Tipo de pincel [B]")
        for bt, label in BRUSH_LABELS.items():
            self.brush_combo.addItem(label, bt.value)
        self.brush_combo.currentIndexChanged.connect(
            lambda i: c.set_brush_type(BrushType(self.brush_combo.itemData(i))))

        def option(text: str, tip: str, slot) -> QToolButton:
            b = QToolButton()
            b.setText(text)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(tip)
            b.setFixedHeight(int(24 * self.k))
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(slot)
            return b

        self.fill_btn = option("Relleno", "Figuras rellenas [R]", lambda on: c.set_fill(on))
        # Formas perfectas (reconocimiento de formas): opción que se activa a voluntad
        self.recognize_btn = option("Formas perfectas",
                                    "Formas perfectas [G]: al soltar el trazo, las líneas, círculos,\n"
                                    "rectángulos y polígonos dibujados a mano se vuelven figuras exactas.\n"
                                    "Desactívalo para dibujar libremente.", lambda on: c.set_recognize_shapes(on))
        small_font = QFont(self.recognize_btn.font())
        small_font.setPixelSize(int(10 * self.k))
        self.recognize_btn.setFont(small_font)
        self.bold_btn = option("Negrita", "Texto en negrita", lambda on: c.set_text_bold(on))
        self.bold_btn.setIcon(icons.icon("bold"))
        self.bold_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        # Color
        self.color_btn = QPushButton()
        self.color_btn.setObjectName("current")
        self.color_btn.setFixedHeight(int(26 * self.k))
        self.color_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.color_btn.setToolTip("Elegir color personalizado [C]")
        self.color_btn.clicked.connect(self.pick_color)
        self.swatches = QWidget()
        sw = QGridLayout(self.swatches)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(4)
        for idx, hexcolor in enumerate(PALETTE):
            b = QPushButton()
            b.setObjectName("swatch")
            b.setFixedSize(int(22 * self.k), int(22 * self.k))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(hexcolor)
            b.setStyleSheet(f"background: {hexcolor};")
            b.clicked.connect(lambda _=False, col=hexcolor: c.set_color(QColor(col)))
            sw.addWidget(b, idx // 4, idx % 4)

        # Grosor y opacidad
        self.size_label = QLabel()
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.size_slider.setToolTip("Grosor (rueda del ratón sobre la pizarra, o teclas + / -)")
        self.size_slider.valueChanged.connect(lambda v: c.set_size(v))
        self.opacity_label = QLabel()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.opacity_slider.setToolTip("Opacidad (Mayús + rueda del ratón)")
        self.opacity_slider.valueChanged.connect(lambda v: c.set_opacity(v))

        # Fondo y pauta (sin rótulo: la barra debe caber en pantallas bajas)
        self.bg_combo = QComboBox()
        self.bg_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.bg_combo.setToolTip("Fondo de la pizarra: transparente, oscurecer el escritorio, blanca o verde")
        for key, label in BACKGROUNDS.items():
            self.bg_combo.addItem(label, key)
        self.bg_combo.currentIndexChanged.connect(lambda i: c.set_background(self.bg_combo.itemData(i)))
        self.pattern_combo = QComboBox()
        self.pattern_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pattern_combo.setToolTip("Pauta de la página: cuadrícula, rayado, caligrafía, plano cartesiano…")
        for key, label in PATTERNS.items():
            self.pattern_combo.addItem(label, key)
        self.pattern_combo.currentIndexChanged.connect(lambda i: c.set_pattern(self.pattern_combo.itemData(i)))

        # Presentación
        self.spot_btn = self._tool_button("spotlight", "Foco: oscurece todo menos alrededor del cursor\n"
                                                       "[F / Ctrl+Alt+F] · Alt + rueda: tamaño\n"
                                                       "Clic derecho o Shift+F: círculo o rectángulo", checkable=True)
        self.spot_btn.clicked.connect(lambda: c.toggle_spotlight())
        self.spot_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.spot_btn.customContextMenuRequested.connect(self._spotlight_menu)
        self.curtain_btn = self._menu_button("curtain", "Cortina: tapa la pantalla y se descubre poco a poco\n"
                                                         "desde arriba, abajo, la izquierda o la derecha.\n"
                                                         "[V] quitar/poner · [Mayús+V] cambiar de lado ·\n"
                                                         "arrástrala o usa las flechas", self.build_curtain_menu)
        spec = TOOL_SPECS[Tool.COVER]
        self.cover_btn = self._tool_button(spec.icon, "Tapar zona  [H]: arrastra para tapar una parte (p. ej. las\n"
                                                      "respuestas); un clic sobre ella la descubre.", checkable=True)
        self.cover_btn.clicked.connect(lambda: c.set_tool(Tool.COVER))
        self.tool_group.addButton(self.cover_btn)
        self.tool_buttons[Tool.COVER] = self.cover_btn
        self.highlight_btn = self._tool_button("highlight", "Resaltar el cursor y los clics [M / Ctrl+Alt+M]",
                                               checkable=True)
        self.highlight_btn.clicked.connect(lambda: c.toggle_highlight())
        self.keys_btn = self._tool_button("keys", "Mostrar en pantalla los atajos que se pulsan\n"
                                                  "(Ctrl + C, Alt + Tab, Intro…) [Ctrl+Alt+K].\n"
                                                  "El texto que se escribe no se muestra.", checkable=True)
        self.keys_btn.clicked.connect(lambda: c.toggle_show_keys())

        # Páginas
        self.page_label = QLabel()
        self.page_label.setObjectName("section")
        self.prev_btn = self._tool_button("page_prev", "Página anterior [RePág]")
        self.prev_btn.clicked.connect(c.prev_page)
        self.next_btn = self._tool_button("page_next", "Página siguiente [AvPág]")
        self.next_btn.clicked.connect(c.next_page)
        self.add_page_btn = self._tool_button("page_add", "Página nueva [N]")
        self.add_page_btn.clicked.connect(c.new_page)

        # Acciones
        self.undo_btn = self._tool_button("undo", "Deshacer (Ctrl+Z)")
        self.undo_btn.clicked.connect(c.undo)
        self.redo_btn = self._tool_button("redo", "Rehacer (Ctrl+Y)")
        self.redo_btn.clicked.connect(c.redo)
        self.clear_btn = self._tool_button("trash", "Borrar todo (Supr)")
        self.clear_btn.clicked.connect(c.clear_all)
        self.capture_btn = self._tool_button("camera", "Captura de pantalla y recortar zona [X]")
        self.capture_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.capture_btn.setMenu(c.build_capture_menu(self.capture_btn))
        self.folder_btn = self._tool_button("file", "Sesión: abrir, guardar, exportar a PDF")
        self.folder_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.folder_btn.setMenu(c.build_file_menu(self.folder_btn))
        self.zoom_btn = self._tool_button("zoom", "Zoom: ampliar la zona bajo el cursor (Z / Ctrl+Alt+Z)",
                                          checkable=True)
        self.zoom_btn.clicked.connect(lambda: c.toggle_zoom())
        self.help_btn = self._tool_button("help", "Ayuda: atajos de teclado (F1) y manual de usuario")
        self.help_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        help_menu = QMenu(self.help_btn)
        help_menu.addAction(icons.icon("help"), "Atajos de teclado\tF1", c.show_help)
        help_menu.addAction(icons.icon("pdf"), "Manual de usuario (PDF)", c.open_manual)
        self.help_btn.setMenu(help_menu)

        # Barra básica ↔ avanzada
        if self.basic:
            self.layout_btn = self._wide_button("options", "Mostrar todas las herramientas y opciones (barra avanzada)",
                                                26)
            self.layout_btn.setText("Más opciones")
            self.layout_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        else:
            self.layout_btn = self._tool_button("options", "Barra básica: solo las herramientas más usadas\n"
                                                           "(más pequeña, para pantallas de poca resolución)")
        self.layout_btn.clicked.connect(lambda: c.set_basic_toolbar(not self.basic))

        return [w for w in vars(self).values() if isinstance(w, QWidget) and w is not self] + \
            list(self.tool_buttons.values())

    @staticmethod
    def _add_grid(col: QVBoxLayout, buttons, cols: int = 3) -> None:
        """Botones en filas de ``cols``, centrados en la columna."""
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, b in enumerate(buttons):
            grid.addWidget(b, i // cols, i % cols)
        col.addLayout(grid)
        col.setAlignment(grid, Qt.AlignmentFlag.AlignHCenter)

    def _layout_advanced(self, c1: QVBoxLayout, c2: QVBoxLayout) -> None:
        """Barra avanzada: todas las herramientas y opciones."""
        self._add_grid(c1, [self.tool_buttons[t] for t in MAIN_TOOLS] + [
            self.more_shapes_btn, self.stamp_btn, self.templates_btn, self.select_btn, self.note_btn,
            self.instruments_btn])
        for w in (self.brush_combo, self.fill_btn, self.recognize_btn, self.bold_btn, self.color_btn):
            c1.addWidget(w)
        c1.addWidget(self.swatches, 0, Qt.AlignmentFlag.AlignHCenter)
        for w in (self.size_label, self.size_slider, self.opacity_label, self.opacity_slider, self.bg_combo,
                  self.pattern_combo):
            c2.addWidget(w)
        self._add_grid(c2, (self.spot_btn, self.curtain_btn, self.cover_btn, self.highlight_btn,
                            self.keys_btn, self.timer_btn))
        c2.addWidget(self.page_label)
        pages = QHBoxLayout()
        pages.setSpacing(4)
        for b in (self.prev_btn, self.next_btn, self.add_page_btn):
            pages.addWidget(b)
        c2.addLayout(pages)
        c2.setAlignment(pages, Qt.AlignmentFlag.AlignHCenter)
        self._add_grid(c2, (self.undo_btn, self.redo_btn, self.clear_btn, self.zoom_btn, self.capture_btn,
                            self.paste_btn, self.folder_btn, self.help_btn, self.layout_btn))

    def _layout_basic(self, c1: QVBoxLayout) -> None:
        """Barra básica: lo más usado en una columna; lo demás, en el menú «Más»."""
        self._add_grid(c1, [self.tool_buttons[t] for t in BASIC_TOOLS] + [self.note_btn, self.more_btn])
        c1.addWidget(self.color_btn)
        c1.addWidget(self.swatches, 0, Qt.AlignmentFlag.AlignHCenter)
        c1.addWidget(self.size_label)
        c1.addWidget(self.size_slider)
        self._add_grid(c1, (self.undo_btn, self.redo_btn, self.clear_btn))
        c1.addWidget(self.layout_btn)

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
        add("Shift+V", c.cycle_curtain_side)
        add("M", c.toggle_highlight)
        add("Down", lambda: c.curtain_arrow(0, 1))
        add("Up", lambda: c.curtain_arrow(0, -1))
        add("Right", lambda: c.curtain_arrow(1, 0))
        add("Left", lambda: c.curtain_arrow(-1, 0))
        add("X", lambda: c.start_crop())
        add("Ctrl+Alt+R", lambda: c.start_crop())
        add("Ctrl+Alt+K", c.toggle_show_keys)
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
        add("I", lambda: c.toggle_instrument("ruler"))
        add("Y", lambda: c.toggle_instrument("protractor"))
        add("Shift+C", lambda: c.toggle_instrument("compass"))
        add("+", lambda: c.step_size(1))
        add("-", lambda: c.step_size(-1))
        add("]", lambda: c.step_size(1))
        add("[", lambda: c.step_size(-1))
        add("Ctrl+Z", c.undo)
        add("Ctrl+Y", c.redo)
        add("Ctrl+Shift+Z", c.redo)
        add("Del", c.delete_key)
        add("Ctrl+D", c.duplicate_selection)
        add("Ctrl+A", c.select_all)
        add("Ctrl+V", c.paste)
        add("G", c.toggle_recognize_shapes)
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
        containers = [*self._columns, self.top, self.cols, self.body, self.panel]  # de dentro hacia fuera
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

    def set_two_columns(self, two: bool) -> None:
        """Dos columnas lado a lado (y «Ocultar» junto a «Dibujando») o una sola columna."""
        direction = QBoxLayout.Direction.LeftToRight if two else QBoxLayout.Direction.TopToBottom
        self.body_layout.setDirection(direction)
        self.top_layout.setDirection(direction)
        # En una columna, la columna ocupa todo el ancho de la cabecera (los botones, centrados)
        width = self.col_width if two else max(self.col_width, self._header.sizeHint().width())
        for col in self._columns:
            col.setFixedWidth(width)

    def update_orientation(self) -> None:
        """Una columna si la barra cabe en la altura de su pantalla; si no, dos columnas."""
        if self.collapsed:
            self.refit()
        else:
            avail = self._current_screen().availableGeometry()
            # Se mide con las opciones de la herramienta que más ocupa (el pincel: tipo de pincel,
            # formas perfectas, grosor y opacidad) para que la disposición no dependa de la
            # herramienta activa ni cambie al cambiarla. Relleno y negrita nunca se ven con el pincel.
            shown = (self.brush_combo, self.recognize_btn, self.size_label, self.size_slider,
                     self.opacity_label, self.opacity_slider)
            unshown = (self.fill_btn, self.bold_btn)
            saved = {w: not w.isHidden() for w in shown + unshown}
            for w in shown:
                w.setVisible(True)
            for w in unshown:
                w.setVisible(False)
            self.set_two_columns(False)
            self.refit()
            needed = self.height()
            for w, vis in saved.items():
                w.setVisible(vis)
            if needed > avail.height():
                self.set_two_columns(True)
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
            self.note_btn.setChecked(c.tool == Tool.NOTE)
            self.instruments_btn.setChecked(c.any_instrument)
            self.keys_btn.setChecked(c.show_keys)
            self.touch_btn.setChecked(c.touch_mode)
            self.stamp_btn.setIcon(icons.icon("stamp_" + c.stamp_kind if c.tool == Tool.STAMP else "stamp"))
            self.mode_btn.setChecked(c.drawing)
            self.mode_btn.setText("Dibujando" if c.drawing else "Ratón libre")
            self.mode_btn.setIcon(icons.icon("pencil" if c.drawing else "mouse"))

            self.brush_combo.setVisible(c.tool == Tool.BRUSH)
            self.brush_combo.setCurrentIndex(self.brush_combo.findData(c.brush_type.value))

            self.fill_btn.setVisible(c.tool in FILLABLE_SHAPES)
            self.fill_btn.setChecked(c.fill_shapes)
            self.recognize_btn.setVisible(c.tool in RECOGNIZABLE_TOOLS)
            self.recognize_btn.setChecked(c.recognize_shapes)
            self.bold_btn.setVisible(c.tool in (Tool.TEXT, Tool.NOTE))
            self.bold_btn.setChecked(c.text_bold)

            col = c.color
            text_color = "#000000" if col.lightness() > 140 else "#ffffff"
            self.color_btn.setText(col.name().upper())
            self.color_btn.setStyleSheet(f"background: {col.name()}; color: {text_color};")

            self.size_slider.setRange(spec.min_size, spec.max_size)
            self.size_slider.setValue(int(c.size_for(c.tool)))
            what = {Tool.TEXT: "Letra", Tool.NOTE: "Letra", Tool.LASER: "Tamaño",
                    Tool.STAMP: "Tamaño"}.get(c.tool, "Grosor")
            self.size_label.setText(f"{what}: {int(c.size_for(c.tool))} px")
            self.size_label.setToolTip(spec.label)
            sized = c.tool not in UNSIZED_TOOLS  # seleccionar y tapar zona no tienen grosor
            self.size_label.setVisible(sized)
            self.size_slider.setVisible(sized)

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
            self.hide_btn.setText("Ocultar" if c.visible else "Mostrar")
            self.hide_btn.setChecked(not c.visible)  # oculta: el botón queda resaltado
            self.hide_btn.setToolTip(("Ocultar" if c.visible else "Mostrar") + " todo lo dibujado (Ctrl+Alt+H)")
            self.more_btn.setChecked(c.tool not in BASIC_TOOLS and c.tool != Tool.NOTE)
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

    def dispose(self) -> None:
        """La barra se va a sustituir: sus atajos dejan de responder ya (antes de destruirla)."""
        for sc in self._shortcuts:
            sc.setEnabled(False)

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
